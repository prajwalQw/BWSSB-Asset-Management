# BWSSB Digital Twin — Baseline Cybersecurity & Industrial Control System Security Architecture

**Standard Reference**: IEC 62443 (Industrial Communication Networks — Network and System Security) & NIST Cybersecurity Framework (CSF v2.0)  
**Classification**: Operational Technology (OT) / Information Technology (IT) Convergence Architecture  
**Effective Date**: October 2026  
**Status**: ACTIVE — PASSIVE MONITORING & DECISION SUPPORT

---

## 1. Executive Summary & Threat Model

The Bengaluru Water Supply and Sewerage Board (BWSSB) Digital Twin is an operational decision-support platform designed to monitor bulk Cauvery water distribution, reservoir storage (GLRs), pumping stations (Tataguni Stage 1–4), and DMA meter flows.

### Threat Model & Attack Vectors
1. **Unauthorized Actuator / Remote Control Manipulation**:
   - *Threat*: Malicious actor attempts to trip pumps, force open valves, or flood distribution zones via remote network commands.
   - *Mitigation*: **Rule 4 Immutable Safety Lock**. The backend IGNOAPI bridge operates strictly in passive read-only monitoring mode. All actuation endpoints raise `PermissionError` and reject commands at the code level. The system cannot actuate field machinery.
2. **Telemetry Spoofing / Replay Attacks**:
   - *Threat*: Fabricated sensor readings causing operator panic or misinformed pumping dispatches.
   - *Mitigation*: Multi-tier data lineage tags (`REAL`, `SIMULATED`, `LIVE`), sensor physical plausibility checks, flatline / stale watchdog detectors, and isolated OT boundary routing.
3. **Audit Log Tampering / Insider Threat**:
   - *Threat*: Operator or attacker alters logs after acknowledging critical alarms or triggering simulated leaks.
   - *Mitigation*: Append-only SHA-256 hash-chained audit trail ($H(prev\_hash \parallel payload)$) stored in SQLite with mathematical tamper verification.
4. **Denial of Service / Request Exhaustion**:
   - *Threat*: Rapid HTTP request storms overwhelming backend workers.
   - *Mitigation*: Rate limiting via `slowapi` (240 requests/min baseline), connection backoff, and SSE multiplexing replacing unbounded polling loops.

---

## 2. IEC 62443 Zones and Conduits Architecture

```
+-----------------------------------------------------------------------------------+
|  Zone 1: Enterprise & Dispatch Operations (IT Zone)                               |
|  - Web Browser UI (GIS Basemaps, Deck.gl, Recharts, Operator Console)             |
|  - Role-Based Access Control (Viewer, Operator, Admin)                            |
+-----------------------------------------------------------------------------------+
                                       |
                   Conduit C1: HTTPS / TLS 1.3 + WSS (Port 443 / 8000)
                   Strict CSP, HttpOnly SameSite=Strict JWT Cookies, Rate Limited
                                       |
+-----------------------------------------------------------------------------------+
|  Zone 2: Digital Twin Simulation & Supervisory Control (DMZ / Analytics Zone)     |
|  - FastAPI Backend Application Engine                                             |
|  - Always-On Autonomous Monitoring Agent                                         |
|  - 24-Hour Predictive Lookahead Supply Optimizer (scipy.optimize.linprog)         |
|  - Hash-Chained Audit Ledger (data/security.db)                                   |
+-----------------------------------------------------------------------------------+
                                       |
                   Conduit C2: Passive Read-Only Socket (Port 8899)
                   Unidirectional Ingestion Only; Hardware / Software Block on Writes
                                       |
+-----------------------------------------------------------------------------------+
|  Zone 3: Operational Technology (OT Zone - Tataguni / Cauvery Field Stations)    |
|  - 6.6 kV Pump Switchgear, Flowmeters, Level Sensors, IGNOAPI Daemon              |
|  - Isolated SCADA Subnet                                                          |
+-----------------------------------------------------------------------------------+
```

---

## 3. NIST Cybersecurity Framework (CSF) Implementation

| NIST CSF Function | Implementation in BWSSB Digital Twin |
| :--- | :--- |
| **IDENTIFY** | Comprehensive asset inventory (pumping stations, GLRs, pipes, DMA meters) with full provenance metadata (`data_tier`). Regular automated dependency audits (`pip-audit`, `npm audit`). |
| **PROTECT** | Argon2/Bcrypt salted password hashing, JWT HttpOnly tokens, RBAC (`viewer`, `operator`, `admin`), OWASP security headers (CSP, HSTS, X-Content-Type-Options, X-Frame-Options), strict CORS allowlist. |
| **DETECT** | Always-on supervisory monitoring agent running every 5 seconds. Automated incident correlation with confidence ranking. Flatline detection, watchdog timeouts, and cryptographic audit chain verification. |
| **RESPOND** | Automated incident classification with recommended operator mitigation actions, high-priority UI toasts with deduplication, and immediate leak isolation protocol recommendations. |
| **RECOVER** | Supervised background task self-healing with exponential backoff restarts, ring-buffer telemetry history backfilling, and persistent SQLite disaster recovery states. |

---

## 4. Local HTTPS Setup via mkcert

For production or secure local staging with HTTP/2 and secure cookies:

1. **Install mkcert**:
   ```bash
   # Windows (via Chocolatey or Scoop)
   choco install mkcert
   # or
   scoop install mkcert
   ```
2. **Install Local CA**:
   ```bash
   mkcert -install
   ```
3. **Generate Local Certificate for Dev Origins**:
   ```bash
   mkcert localhost 127.0.0.1 ::1
   # Creates: localhost+2.pem and localhost+2-key.pem
   ```
4. **Launch Backend with TLS**:
   ```bash
   uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --ssl-keyfile localhost+2-key.pem --ssl-certfile localhost+2.pem
   ```
5. **Configure Frontend**:
   Update `vite.config.ts` with `server: { https: { key: '...', cert: '...' } }`.
