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
