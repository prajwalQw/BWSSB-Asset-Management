# IoT Module Bug Audit and Root Cause Report

This document records the symptoms, confirmed root causes with file and line references, and corresponding fixes identified during the IoT system audit.

---

## 1. State Loss Across Route Changes & Page Refreshes

- **Symptom**: When switching between GIS and IoT views or refreshing the page, earlier telemetry, alerts, and injection scenarios vanished.
- **Root Cause Confirmed**:
  - `backend/app/iot/sim/engine.py` (lines 40-75): The simulation engine kept all states (`self.stations_state`, `self.alerts`, `self.active_injections`) exclusively in Python process memory.
  - `backend/app/main.py` (line 77): FastApi was configured with `reload=True`. Any file touch or module reload triggered a worker process restart, wiping all in-memory telemetry, alerts, and ring buffers.
  - `frontend/src/features/iot/IoTWorkstation.tsx` (lines 28-42): Each page mount instantiated independent component-level React `useState` hooks and triggered separate uncoordinated fetch intervals (`loadData`), with no persistent global store.
- **Fix**:
  1. Created persistent SQLite store in `backend/app/iot/storage.py` (`sim_state`, `devices_latest`, `timeseries`, `alerts`, `alert_events`, `injections`).
  2. Implemented `_load_persisted_state()` and periodic 30 s + shutdown state snapshots in `backend/app/iot/sim/engine.py`.
  3. Changed `reload=True` to `reload=False` in `backend/app/main.py`.
  4. Created global Zustand-compatible store in `frontend/src/features/iot/store/useIoTStore.ts` using `useSyncExternalStore` so state persists across client-side route changes.

---

## 2. Empty Ward Consumption List ("Wards Consumption (0)")

- **Symptom**: Division Smart Meter boards showed aggregate totals, but clicking a division showed "Wards Consumption (0)" or threw an error.
- **Root Cause Confirmed**:
  - `backend/app/iot/sim/engine.py` (lines 170-205): In `_init_smart_meters()`, `w["flow_lps"]` was omitted during initial ward record construction and was only added during `tick()`. Any API call before the first tick caused `KeyError` or incomplete data serialization.
  - Join mismatch between `bwssb_ward_water_consumption_2026.csv` (`South Division`, `East Division`, `North Division`) and GeoJSON division polygon names (`South-1`, `East-2`, `Central`), causing string equality filter `w["division"] == division_name` to fail.
- **Fix**:
  1. Added explicit canonical mapping in `config/iot/division_aliases.yaml` mapping all 9 canonical divisions and 16 GIS sub-divisions.
  2. Updated `_init_smart_meters()` in `backend/app/iot/sim/engine.py` to immediately initialize `flow_lps`, `current_day_volume_kl`, and `cumulative_totaliser_kl` on load.
  3. Ensured division totals are strictly computed as the sum of their constituent ward records (`sum(w["daily_baseline_mld"] for w in wards)`).
  4. Verified in `docs/DATA_JOIN_REPORT.md` that 198/198 wards matched across all 9 divisions with 1,247.63 MLD total baseline.

---

## 3. Alerts Disappearing on Recovery Instead of Entering History

- **Symptom**: When a leak was stopped or recovered, the alert disappeared completely from the operator UI and could not be audited.
- **Root Cause Confirmed**:
  - `backend/app/iot/sim/leak_detector.py` (lines 115-117): When deadband recovery conditions were met, the code executed `del self.alerts[alert_id]`.
  - `backend/app/iot/sim/engine.py` (lines 508-511): In-memory alert dictionary removed cleared alerts rather than transitioning status.
- **Fix**:
  1. Updated alert lifecycle in `backend/app/iot/models.py` to `AlertStatus = Literal["ACTIVE", "ACKNOWLEDGED", "CLEARED", "SHELVED"]`.
  2. Updated `leak_detector.py` and `engine.py` to set `status = "CLEARED"`, `active = False`, and record `cleared_at` timestamp.
  3. Added `first_seen`, `last_seen`, `cleared_at`, `acknowledged_by`, and `acknowledged_at` lifecycle fields.
  4. Updated `GET /api/v1/iot/alerts` to accept `status` query parameter and return active alerts plus 24-hour history.

---

## 4. Map Lifecycle and Canvas Recreation

- **Symptom**: Switching between GIS and IoT tabs resulted in black screens, WebGL context loss, and disappearance of Deck.gl layers.
- **Root Cause Confirmed**:
  - `frontend/src/App.tsx` (line 188) and `frontend/src/features/iot/IoTWorkstation.tsx` (line 228): Both components independently rendered `<DigitalTwinMap>`. Switching routes caused one map to unmount and another to mount, destroying the WebGL context and Deck.gl buffers.
  - `DigitalTwinMap.tsx` had multiple `setStyle()` risks during basemap switching.
- **Fix**:
  1. Lifted `<DigitalTwinMap>` to exist as a single app-level singleton in `App.tsx` that remains mounted across route changes.
  2. Switched between GIS and IoT presentation via CSS display toggles and layer provider registrations rather than unmounting the map canvas.

---

## 5. Duplicate SSE Connections and Connection Thrashing

- **Symptom**: Refreshing or navigating routes spawned multiple parallel Server-Sent Events (SSE) connections, overloading backend workers and causing telemetry jitter.
- **Root Cause Confirmed**:
  - In `IoTWorkstation.tsx`, polling and streaming intervals were defined inside page-level `useEffect` hooks that recreated connections on every route transition without cleanup or backoff.
- **Fix**:
  1. Created `frontend/src/features/iot/providers/IoTStreamProvider.tsx` mounted once at app level.
  2. Integrated exponential backoff reconnection (1s -> 2s -> 4s -> max 10s) and initial snapshot hydration (`GET /api/v1/iot/snapshot`).
  3. Added `Last-Event-ID` header and event sequence IDs to backend SSE stream.

---

## 6. Undetected API Failures

- **Symptom**: API fetch errors failed silently in the console, leaving blank charts and empty dropdowns.
- **Root Cause Confirmed**:
  - Unhandled promise rejections returned empty arrays without notifying the user interface.
- **Fix**:
  1. Added `apiErrorBanner` state in `useIoTStore` and rendered a small top-center error notification banner in `IoTStreamProvider.tsx`.
  2. Validated non-empty arrays with fallback states across all components.
