# BWSSB Digital Twin — Deferred & Out-of-Scope Items (NOT_DONE.md)

**Date**: October 22, 2026  
**Target Branch**: `feature/iot`  
**Reference**: Project Scope & Safety Constraints

---

The following items were evaluated and intentionally deferred or scoped out in accordance with safety rules, deadline constraints, and architectural boundaries:

## 1. Remote Actuation and Field Control (SCADA Write Commands)
- **Status**: Intentionally Blocked / Forbidden.
- **Rationale**: Strict compliance with **Rule 4: Read-Only IGNOAPI Bridge** and **IEC 62443 Zone Separation**. The BWSSB Digital Twin is strictly a passive monitoring and supervisory decision-support tool. All write/actuator commands raise `PermissionError("Field control is intentionally unavailable. Passive read-only monitoring mode.")`. Physical actuators must remain under local PLC / SCADA interlock control.

## 2. Refactoring Legacy EPANET / WNTR Hydraulic Solver
- **Status**: Deferred / Preserved without alteration.
- **Rationale**: Minimal intervention rule specified "no refactors". The legacy EPANET C-bindings in WNTR function correctly for bulk network flows. Refactoring or replacing this solver with an in-house Python solver would introduce instability and violate deadline constraints.

## 3. Real-Time Consumer Billing & Payment Gateway Integration
- **Status**: Out of Scope.
- **Rationale**: The supply plan optimizer models dynamic time-of-use tariffs (Off-Peak ₹4.50, Normal ₹7.20, Peak ₹10.50 per kWh) for pumping energy cost minimization. Integration with BWSSB consumer revenue collection and payment gateways is outside the scope of hydraulic twin simulation.

## 4. Hardware Security Module (HSM) Key Storage
- **Status**: Deferred to Enterprise Deployment.
- **Rationale**: In the local environment, JWT secrets and credentials are managed via environment variables and `.env` files with production refusal guards. Cloud HSM or Vault integration is deferred to the on-premise datacenter rollout.

## 5. Repaired Legacy Breakages in Demo & Alert Chain
During implementation of Priority 7, the following legacy issues in the preexisting chain were identified and repaired to ensure seamless end-to-end demo execution:
1. **Missing Root Popup Host**:
   - `IoTLeakDetectionPopup` was previously only mounted inside `frontend/src/features/iot/IoTWorkstation.tsx`. If an operator triggered a leak or ran the demo from the global topbar, the popup never appeared on map view. It was elevated to `frontend/src/App.tsx` and connected to the singleton `sseManager` demo channel.
2. **Current Trend 0 A Display Bug**:
   - In `frontend/src/features/iot/components/IoTRightInspector.tsx`, `pumpData.current_avg || 110.0` caused 0 A current to be replaced with 110.0 A when a pump was stopped by the monitoring agent. Replaced with nullish coalescing `pumpData.current_avg ?? 0.0`.
3. **IgnoApiReadOnlyBridge `__init__` Syntax Defect**:
   - An accidentally placed `@property is_connected` in `backend/app/bridge/ignoapi_bridge.py` truncated `__init__`, leaving `self.last_telemetry` uninitialized on clean test startups. Corrected method placement.
4. **Auth Password Hash Migration**:
   - When running without optional `bcrypt` package, preexisting `$2b$` bcrypt hashes in `data/security.db` caused login failures. Updated `init_security_db` to auto-migrate seeded hashes to standard PBKDF2-SHA256 when `bcrypt` is unavailable.

