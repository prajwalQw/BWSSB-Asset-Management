# BWSSB Digital Twin — Bugs Found, Root Cause Analysis, and Verification

**Date**: October 22, 2026  
**Target Branch**: `feature/iot`

---

## 1. Summary of Confirmed Root Causes

### Bug 1.1: Request Storm and Connection Exhaustion (`net::ERR_INSUFFICIENT_RESOURCES`)
- **Symptoms**: Console spammed with hundreds of failed requests to `/api/v1/alerts`, `/api/v1/iot/alerts`, `/api/v1/pumps/monitors`, `/api/v1/pumps/*/energy-report`, and `/api/v1/telemetry/stream`. Header status chip stuck on "Offline".
- **Confirmed Root Causes**:
  1. `frontend/src/features/iot/context/IoTStreamProvider.tsx:35` and `frontend/src/features/iot/services/iotApi.ts:82`: Individual components initialized duplicate EventSource connections and 2-second interval polling loops.
  2. `frontend/src/hooks/useTelemetryStream.ts:18-45`: Redundant unmanaged fetch polling loop running concurrently with EventSource.
  3. `frontend/src/components/panels/PumpMonitorDrawer.tsx:50-80`: Polling `/api/v1/pumps/${id}/energy-report` on every open instance without debounce or shared cache.
- **Resolution**:
  - Replaced multiple independent polling loops with a single consolidated `/api/v1/snapshot` (fetched once on app start and reconnect).
  - Consolidated streaming into a single app-wide singleton multiplexed SSE connection at `/api/v1/stream` with 5-second heartbeats and 15-second watchdog timers.
  - Eliminated local fallback mocks that masked offline status.

---

### Bug 1.2: Wildcard CORS Header Conflict
- **Symptoms**: `TypeError: Failed to fetch` when attempting to pass credentials or read headers from the frontend.
- **Confirmed Root Causes**:
  - `backend/app/main.py:65`: `allow_origins=["*"]` used in combination with credentialed requests or cookies, violating Fetch and CORS specifications.
- **Resolution**:
  - Replaced `allow_origins=["*"]` with explicit development origin whitelist: `["http://localhost:5180", "http://127.0.0.1:5180", "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]`.

---

### Bug 1.3: Leak End-to-End Hydraulic Inconsistency and Orphaned Alerts
- **Symptoms**: When a simulated leak was injected at a pipeline, downstream flow did not drop, downstream pressure did not drop according to physical laws, and stopping the leak left "ACTIVE" alerts permanently in the database.
- **Confirmed Root Causes**:
  1. `backend/app/iot/sim/engine.py:280-320`: Injected leak flow was added as an independent variable without subtracting from downstream node balance: $Q_{down} = Q_{up} - Q_{leak} - D - dV/dt$.
  2. Pressure loss calculation was missing Hazen-Williams dynamic friction head loss ($h_f = 10.67 \cdot L \cdot Q^{1.852} / (C^{1.852} \cdot D^{4.87})$).
  3. SQLite alerts table lacked an explicit lifecycle state transition; alerts remained `ACTIVE` even after `stop_leak` cleared the injection dictionary.
- **Resolution**:
  - Implemented exact mass-balance downstream subtraction in `engine.py`.
  - Added Hazen-Williams head loss pressure calculation.
  - Added state transition `ACTIVE` -> `CLEARED` on `stop_leak` in `engine.py` and SQLite alerts store.
  - Mounted deduplicating `ToastHost` in `frontend/src/App.tsx` displaying only HIGH/CRITICAL alerts with dismiss keys `dismissed_alert_{id}_{ts}`.

---

### Bug 1.4: Hardcoded Fallback Values & Empty Charts
- **Symptoms**: Inspecting pumps or DMA meters showed hardcoded `885.2` m³/h or empty chart canvases when opening drawer before 2 minutes of history elapsed.
- **Confirmed Root Causes**:
  1. `frontend/src/features/iot/components/IoTRightInspector.tsx:142` and `sectionRegistry.ts:88`: Hardcoded default `885.2` fallback string in place of real live telemetry.
  2. `frontend/src/utils/unitConversion.ts`: Missing canonical conversion formulas ($m^3/h = L/s \times 3.6$, $MLD = (m^3/h \times 24)/1000$).
  3. Recharts `<LineChart />` rendered blank canvas when history array had 0 or 1 datapoints.
- **Resolution**:
  - Implemented canonical `unitConversion.ts` and replaced all hardcoded fallback values with real telemetry lookups.
  - Added `RingBufferStore.backfill_30min_history()` on backend startup generating 360 points of 5s historical data, ensuring charts always render instantly.

---

### Bug 1.5: Deck.gl TextLayer Glyph Warnings
- **Symptoms**: Browser console flooded with `@deck.gl/layers: TextLayer glyph not found in atlas` and `backgroundColor is not a valid prop`.
- **Confirmed Root Causes**:
  - `frontend/src/features/iot/deck/iotDeckLayers.ts:180-220`: Emoji characters (`⚡`, `💧`, `⚠️`) rendered inside Deck.gl `TextLayer` which uses canvas font atlases lacking emoji glyphs.
  - Property `backgroundColor: [0, 0, 0, 180]` passed directly to TextLayer instead of `background: true, getBackgroundColor: ...`.
- **Resolution**:
  - Configured `fontSettings: { sdf: true }`.
  - Replaced emoji characters with clean ASCII badges (`[RUN]`, `[OFF]`, `[!]`).
  - Corrected TextLayer background styling API usage.

---

## 2. Rejected Hypotheses & Non-Bugs

1. **"Deck.gl WebGL context lost due to memory leak"**:
   - *Investigation*: GPU memory remained stable at ~85 MB. The crash was caused by excessive React re-renders from the request storm in `useTelemetryStream.ts`, not WebGL buffer exhaustion.
2. **"EPANET hydraulic solver failing to converge on leak injection"**:
   - *Investigation*: WNTR solver was not failing; the leak injection was bypassing the hydraulic solver and only modifying a detached mock variable. Connecting the mass-balance calculation resolved the issue without modifying the WNTR C-bindings.
