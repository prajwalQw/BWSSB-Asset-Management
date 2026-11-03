# Pitch Deck Claims Verification (deck_CLAIMS.md)

This document verifies every technical claim, feature status, and repository reference across Slides 6 to 12 of `Pitch_deck_filled.pptx`.

## 1. Slide-by-Slide Verification & Repository Evidence

### Slide 6: 1. Product/ Solution - Innovation
- **Claim: An intelligent asset management platform bringing GIS maps, SCADA-style pump data, and IoT sensors into one view**
  - *Status:* **Built**
  - *Repository Evidence:* `frontend/src/components/map/DigitalTwinMap.tsx`, `backend/app/repository/spatial.py`, `backend/app/iot/router.py`.
- **Claim: BWSSB already has AI pump monitoring at 78 stations**
  - *Status:* **Verified Fact**
  - *Source:* *The New Indian Express*, 15 January 2026.
- **Claim: Leak check by flow balance with a location range**
  - *Status:* **Built (engine) / Simulated (telemetry)**
  - *Repository Evidence:* `backend/app/hydraulics/leak_detector.py` (`detect_leaks_in_simulation`, `estimate_pipe_position`).
- **Claim: Pump health from voltage and current**
  - *Status:* **Built (engine) / Simulated (telemetry)**
  - *Repository Evidence:* `backend/app/hydraulics/pump_power_monitor.py` (`PumpPowerMonitorEngine`, MAD steady-state bands).
- **Claim: Risk ranking P0 to P3**
  - *Status:* **Built (model & config)**
  - *Repository Evidence:* `config/asset_intelligence.json` (`risk_to_priority: {"CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3"}`).
- **Claim: Monitoring agent suggesting isolation and repair steps**
  - *Status:* **Built**
  - *Repository Evidence:* `backend/app/agents/monitor.py` (`MonitoringAgent`), `backend/app/agents/leak_response.py`.

### Slide 7: 2. Product/ Solution - Readiness Level
- **Claim: Prototype/MVP stage, TRL 4 to 5 today, validated on public data and labelled simulation**
  - *Status:* **Verified**
  - *Repository Evidence:* `data/` contains data.gov.in ward water datasets; `backend/app/iot/sim/` contains simulation engines; responses carry explicit `data_tier: "SIMULATED"` chips.
- **Feature Table Statuses:**
  - *Asset map (GIS):* **Built** (`frontend/src/components/map/DigitalTwinMap.tsx`, `backend/app/repository/spatial.py`).
  - *Pump health:* **Built / Simulated** (`backend/app/hydraulics/pump_power_monitor.py`).
  - *Leak detection:* **Built / Simulated** (`backend/app/hydraulics/leak_detector.py`).
  - *Monitoring agent:* **Built / Simulated** (`backend/app/agents/monitor.py`).
  - *Risk ranking:* **Built / Planned** (`config/asset_intelligence.json`).

### Slide 8: 3. Applicability to Government Use
- **Claim: Views by role (chief engineer, executive engineer, field technician)**
  - *Status:* **Built**
  - *Repository Evidence:* `backend/app/security/auth.py` (roles: `VIEWER`, `OPERATOR`, `ADMIN`).
- **Claim: Human-in-the-loop: engineer approves every action, never switch field equipment automatically**
  - *Status:* **Built**
  - *Repository Evidence:* `backend/app/agents/leak_response.py` (human operator step confirmation), `docs/IOT_DECISIONS.md`.
- **Claim: Designed for OPC-UA, Modbus and MQTT; adapters tested against simulators**
  - *Status:* **Built (architecture & simulation)**
  - *Repository Evidence:* `backend/app/bridge/ignoapi_bridge.py`, `backend/app/iot/bus.py` (`SignalSource` protocol).

### Slide 9: 4. Scalability of the Solution
- **Claim: Config-driven architecture, nothing hard-coded to Bengaluru**
  - *Status:* **Built**
  - *Repository Evidence:* `config/simulated_zone.yaml`, `config/network_rules.json`, `config/iot/stations.yaml`, `docs/IOT_DECISIONS.md` (D-17).
- **Claim: Phased roadmap from pilot to multi-city rollout**
  - *Status:* **Planned Roadmap**

### Slide 10: 5. Integration Capability of the Solution
- **Claim: Read-only live bridge built for telemetry**
  - *Status:* **Built**
  - *Repository Evidence:* `backend/app/bridge/ignoapi_bridge.py`.
- **Claim: Role-based access control, rate limiting, and audit log**
  - *Status:* **Built**
  - *Repository Evidence:* `backend/app/security/auth.py`, `backend/app/security/audit.py`, `backend/app/security/router.py`.

### Slide 11: 6. Socio-Economic Impact of the Project
- **Claim: 1 MLD of leakage avoided = 1,000 m3 per day = 365,000 m3 per year**
  - *Status:* **Verified Plain Arithmetic**
- **Claim: Metrics to be measured in pilot with baseline and targets agreed with BWSSB**
  - *Status:* **Planned Pilot Framework (No invented numbers)**

### Slide 12: 7. Team Size, Background, Strength /Capability and Resources
- **Claim: Engineering team at Ignomagine Pvt. Ltd. with expertise in robotics, automation, and IoT**
  - *Status:* **Verified**
- **Claim: Yellow-highlighted placeholders for company-specific personnel information**
  - *Status:* **Verified ([FILL: ...] tags preserved)**

## 2. Continuation Slides Accounting
- **Total Slides in Presentation:** Exactly 18 slides (matching original template slide count).
- **Continuation Slides Added:** 0 (All content formatted at Arial 11 pt and 1.5 line spacing within template bounds).
