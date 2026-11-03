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

## Priority 3: Hardcoded Values, Timeseries Backfill, and DeckGL Modernization
1. **Unit Conversion Utility**:
   - Standardized in `frontend/src/utils/unitConversion.ts` using canonical relationships:
     $m^3/h = L/s \times 3.6$
     $MLD = (m^3/h \times 24) / 1000 = (L/s \times 86.4) / 1000$
   - Replaced all manual calculation literals across `IoTRightInspector.tsx` and removed hardcoded `885.2` fallbacks.
2. **Timeseries Backfill & Non-Empty Chart Rendering**:
   - At engine startup, `RingBufferStore.backfill_30min_history()` pre-populates 30 minutes of history at 5-second resolution (360 points) following diurnal profiles and physics baselines.
   - `get_timeseries()` guarantees at least 2 data points for any queried tag/signal so Recharts line charts always render visible lines with fixed heights and axes.
3. **deck.gl Modernization**:
   - Replaced deprecated `backgroundColor` in `TextLayer` with `background: true, getBackgroundColor: ...`.
   - Added `fontSettings: { sdf: true }` to text layers for crisp outline rendering.
   - Stripped raw emoji characters from label text to prevent WebGL glyph rendering warnings.

## Priority 4: Automatic Supply Plan & Water Movement Simulation
1. **Tataguni Pumping Complex & Multi-Zone Configuration**:
   - Configured Tataguni 1200 kW pumps, Mount Joy GLR (22 MLD), High Grounds GLR (35 MLD), and 4 operational supply zones (Basavanagudi, Central CBD, Rajajinagar, Padmanabhanagar).
   - Real ward demands derived from the 2026 BWSSB data catalog.
   - Time-of-Use electricity tariffs: Off-Peak (22:00-06:00) ₹4.50/kWh, Normal (06:00-18:00) ₹7.20/kWh, Peak (18:00-22:00) ₹10.50/kWh.
2. **Optimization Model (`scipy.optimize.linprog`)**:
   - 24-hour lookahead at 15-minute intervals (96 time steps). Minimizes $\sum \text{Tariff}(t) \cdot \text{Energy}(t)$.
   - Constraints:
     - Mass balance: Tank levels maintained within [20%, 95%] storage bounds.
     - Cumulative demand lower bound: $\sum Q_{pump} \ge \sum Q_{demand}$, ensuring pumping dispatches shift predominantly into low-cost off-peak windows.
     - Fallback to deterministic rule-based greedy scheduler if linprog is slow or infeasible.
3. **Water Movement & TripsLayer Pipe Trails**:
   - Pipe velocity: $v = Q / A$ where $A = \pi (D/2)^2$. Travel delay along pipe: $\tau = L / v$.
   - Active flow corridors identified dynamically where $Q > 0.05$ MLD.
   - Animated water movement trails visualized with `TripsLayer` or directional flow vectors.
4. **Mandatory UI Clarification Labels**:
   - UI explicitly displays:
     - `"Automatic (simulated)"` mode tag
     - `"Ward-to-reservoir assignment is simulated"`
     - `"Decision-support schedule, not BWSSB's actual schedule"`
5. **Simulation Clock Control**:
   - Synchronized backend/frontend sim clock with Play, Pause, and speed multipliers (1x, 60x, 600x) via `POST /api/v1/iot/sim/clock`.

## Priority 5: Autonomous Monitoring Agent
1. **Supervisory Architecture**:
   - Supervised background agent running every 5 seconds.
   - Health checks (6/6):
     - Sensor flatline watchdog: alerts if reading variance is zero over 30 ticks without pump stop.
     - Heartbeat monitor: tracks age of last bridge packet.
     - Tick lag detector: verifies simulation loop tick interval is within 2.5s.
     - Task supervision: monitors detector, scheduler, and bridge background tasks; performs auto-restart with exponential backoff if failed.
2. **Alert Correlation & Incident Diagnosis**:
   - Correlates raw alerts into consolidated incidents. E.g., simultaneous drop in downstream pressure, drop in flow, and upstream tank drawdown is diagnosed as `PIPE_BURST_OR_MAJOR_LEAK` with 88% confidence and recommended isolation steps.
3. **Advisory Generation & UI Component**:
   - Exposes `/api/v1/agent/status` and `/api/v1/agent/log`.
   - Dedicated `MonitorPanel.tsx` in IoT module showing heartbeat pulse, 6/6 health check cards, live activity stream, and advisory incident reports.

## Priority 6: Baseline Cybersecurity, RBAC, and Cryptographic Audit
1. **Passive Read-Only OT Protection (Rule 4 Enforcement)**:
   - Bridge methods `write_variable`, `set_actuator`, and `send_command` explicitly raise `PermissionError("Field control is intentionally unavailable. Passive read-only monitoring mode.")`.
   - System is architected to prevent remote control of industrial machinery.
2. **Authentication & Role-Based Access Control (RBAC)**:
   - Passwords hashed using bcrypt.
   - JWT access and refresh tokens stored in `HttpOnly`, `SameSite=Strict` cookies (with `Secure` in HTTPS).
   - Roles: `viewer`, `operator`, `admin`.
   - Refuses production startup if default secrets are detected.
3. **Cryptographic Append-Only Audit Ledger**:
   - Audit events (logins, logouts, acknowledgements, simulated leak injections) stored in SQLite with SHA-256 hash chaining:
     $H_i = \text{SHA-256}(H_{i-1} \parallel \text{who} \parallel \text{what} \parallel \text{from\_where} \parallel \text{details} \parallel \text{timestamp})$.
   - Full-chain verification algorithm (`verify_chain()`) detects any modified, deleted, or inserted rows.
4. **Rate Limiting & Security Headers**:
   - `slowapi` rate limiting middleware (240 requests/minute per client IP).
   - Security headers middleware injecting `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `X-XSS-Protection`, and `Referrer-Policy`.
5. **Security Posture Drawer in UI**:
   - Integrated into `AdminDrawer.tsx` under "Security", providing live audit chain verification and posture display.

## Priority 7: Fast Self-Contained Leak Demo Flow & Agent Response
1. **End-to-End Demo State Machine (`backend/app/agents/leak_response.py`)**:
   - Self-contained asynchronous state machine driving the full operational lifecycle:
     `IDLE -> LEAK_INJECTED -> DETECTED -> AGENT_DIAGNOSED -> AWAITING_APPROVAL / COUNTDOWN -> ISOLATING -> ISOLATED -> REPAIR_DISPATCHED -> REPAIR_IN_PROGRESS -> VERIFYING -> RESTORING -> RESTORED`.
   - Wall-time acceleration and timings configured in `config/demo.yaml`. Demo preset completes in ~90 seconds of wall time.
2. **Dynamic Network Graph Resolution (`resolve_from_network_graph`)**:
   - Avoids hardcoded pump or valve IDs. Dynamically resolves corridor `CORR_TATAGUNI_MOUNT_JOY` through `config/iot/network_flows.yaml`, `config/iot/stations.yaml`, and `config/simulated_zone.yaml`.
   - Resolves:
     - Feeding pump: `PUMP_TG_H1` (High-Lift Pump 1, 1200 kW).
     - Isolation valve: `BFV-104` (Motorised Butterfly Valve).
     - Terminals: Tataguni Terminal Complex -> Mount Joy GLR.
     - Impacted wards: Basavanagudi, Hanumanthanagar, Chamarajpet.
     - Alternate source: Harohalli Stage V via High Grounds GLR (covers 65% for 4 hours).
3. **Physical Simulator Integration (SIMULATED Only)**:
   - All actions strictly manipulate digital twin simulated state; real IGNOAPI bridge remains strictly passive read-only.
   - Isolation: Feeding pump commanded to `STOPPING` -> `OFF` with `[LOCKED]` tag and current dropping to 0 A. Valve `BFV-104` transitions to `CLOSED`. Leaking segment depressurises and leak loss decays to 0 L/s.
   - Restoration: Hydrostatic pressure verification test passes. Valve reopens. Pump starts via soft-start ramp profile (inrush current spike followed by exponential decay to nominal operating current plateau).
4. **Governance & Role-Based Approval Modes**:
   - `auto` mode: 3-second supervisor countdown with an immediate Cancel button.
   - `ask` mode: Pauses in `AWAITING_APPROVAL` until approved.
   - RBAC: `OPERATOR` and `ADMIN` roles are authorized to approve/reject isolation; `VIEWER` and read-only users receive HTTP 403 Forbidden (`VIEWER_UNAUTHORIZED`).
5. **Deck.gl & UI Symbology**:
   - Deck.gl pipeline overlay: leaking section turns red with uncertainty halo scatterplot layer; isolated section turns grey with halted flow particle animation; valve shows closed icon; repair crew wrench icon displayed at chainage 6+400; pump unit shows OFF state with stopped impeller.
6. **Post-Mortem Incident Closure Report**:
   - Generates downloadable print-to-PDF ready HTML report (`/api/v1/demo/report/html`) with full timeline, cumulative volume lost, energy saved, operator sign-off, and compliance disclaimers.

