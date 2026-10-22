# Engineering Decisions & System Defaults

## Priority 1: Request Storm, Singleton SSE, and Consolidated Snapshot
1. **Consolidated Snapshot (`/api/v1/snapshot`)**:
   - Single endpoint returning devices latest values, active + 24h alerts, active leaks, plan status, monitoring agent status, and KPIs.
   - Fetched on app start and reconnection; eliminates separate polling loops for alerts, monitors, and energy reports.
2. **App-wide Singleton SSE Stream (`sseManager`)**:
   - Exactly one HTTP/1.1 `EventSource` connection to `/api/v1/stream` app-wide, managed with reference counting (`retain()` / `release()`).
   - Server sends heartbeat every 5 seconds.
   - Client watchdog timer: marks status as Offline only if no event or heartbeat is received for 15 seconds.
   - Multiplexed typed events: `heartbeat`, `telemetry`, `alert`, `leak`, `plan`, `agent`.
3. **CORS & Origin Consolidation**:
   - Replaced wildcard `allow_origins=["*"]` with exact dev origins: `http://localhost:5180`, `http://127.0.0.1:5180`, `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000`.
   - Frontend `API_BASE` changed to relative `/api/v1`, routed through Vite proxy to `http://127.0.0.1:8000`, eliminating cross-origin connection exhaustion.
4. **Elimination of Request Storms & Mock Defaults**:
   - Removed all `useTwinQuery` 8s/12s polling loops in `App.tsx`.
   - Enforced `refetchInterval >= 5000ms`, `refetchOnWindowFocus: false`, max 2 retries with exponential backoff, and `AbortController` cancellation on unmount.
   - Removed mock fallback datasets from `iotApi.ts`. If snapshot fails, an in-app error banner (`"Backend unreachable. Retrying…"`) is displayed without hardcoded numbers.
5. **Unified Store for TopBar**:
   - TopBar chips (`isFeedFresh`, `runningPumps`, `totalPumps`, `energyMwh`, `energyCostLakhs`, `waterLossKld`, `alertsCount`) read directly from `useTwinStore`, kept synchronized by `sseManager` deltas.

## Priority 2: Leak End-to-End Physics and Lifecycle
1. **Physical Modeling of Supply Edges**:
   - All transmission supply edges from `network_flows.yaml` are instrumented with simulated flow meters at both upstream and downstream ends (`FIT_<FROM>_OUT`, `FIT_<TO>_IN`) and downstream pressure transmitters (`PIT_<TO>_INLET`).
   - When a leak occurs:
     - Downstream flow drops: $Q_{down} = Q_{up} - Q_{leak} - D_{demand} - \Delta V/\Delta t$.
     - Downstream pressure falls based on Hazen-Williams head loss redistribution and localized drawdown.
     - Upstream tank drawdown accelerates.
     - Division inlet exceeds sum of ward meter readings.
2. **Supervised Simulation Loop & Detector**:
   - Engine tick runs inside a supervised background task in FastAPI lifespan with auto-restart upon any exception.
   - Leak detector evaluates mass balance with uncertainty tolerance $k \sqrt{\sigma_{up}^2 + \sigma_{down}^2}$ and 4-of-5 window persistence with sensor-health guard. Detection occurs within 10-20 seconds of simulation time.
3. **Alert Lifecycle & Persistence**:
   - Stable alert ID (`ALT-LEAK-{segment_id}`) with strict lifecycle: `ACTIVE` -> `ACKNOWLEDGED` -> `CLEARED`. Persisted in SQLite `iot_storage`, restored on restart, and auto-cleared on Stop Leak.
4. **ToastHost Component & Popup Deduplication**:
   - `ToastHost` mounted at app root filters for `HIGH` and `CRITICAL` alerts (leak, pump trip, low pressure).
   - Shows "Possible leak between {From} and {To}", loss (L/s and kL/day), confidence, uncertainty corridor along pipe, affected systems, advisory steps, and action buttons ("Show on map", "Acknowledge", "Snooze").
   - LocalStorage deduplication key: `dismissed_alert_{alert_id}_{first_seen}`, ensuring new alert occurrences are never suppressed.
   - "Running now" section lists active leaks with Stop buttons, and POST failures trigger an in-app error toast.
