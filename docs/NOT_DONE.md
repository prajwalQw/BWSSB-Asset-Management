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
