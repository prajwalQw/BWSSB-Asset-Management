# IoT Module: Limitations & Integrity Boundaries

This document defines the clear boundaries between **authentic public data**, **physics-based simulation**, and **governance constraints** in the Bengaluru Water Supply and Sewerage Board (BWSSB) Digital Twin.

---

## 1. What is REAL (Documented & Public Data)

1. **GIS Asset Inventory & Locations**:
   - Pumping station geographic coordinates (e.g. Tataguni Terminal, Mount Joy Booster, High Grounds Booster) are anchored to real BWSSB facility coordinates from `data/raw/geojson/bwssb_pumping_stations.geojson`.
   - BWSSB administrative division boundaries and centroids are loaded from official GeoJSON boundaries.
   - 200 BBMP Ward names, ward numbers, and daily water consumption figures (MLD) are derived directly from the published data.gov.in BWSSB ward consumption records (`data/raw/bwssb_ward_water_consumption_2026.csv`).
2. **Plant Capacities & Conveyance Milestones**:
   - Cauvery Stages I through IV cumulative capacity (1,475 MLD) is verified from JICA Phase 3 Final Report Part 4 (p. 17-9) and Yokogawa SCADA documentation.
   - Cauvery Stage V commissioning throughput (775 MLD) is verified from BWSSB 2023 official commissioning releases.
   - Water quality limits for turbidity, pH, and free residual chlorine are taken directly from the Bureau of Indian Standards specification **IS 10500:2012**.
3. **Auxiliary Hardware Live Stream**:
   - The existing read-only auxiliary supply telemetry channel (12V DC, 2A) from the IGNOAPI bridge remains authentic and unchanged.

---

## 2. What is SIMULATED (Synthetic Physics Layer)

1. **High-Frequency Sensor Telemetry (1-second tick)**:
   - Instantaneous bulk flow rates (L/s), discharge pressure (bar), tank levels (m and %), and water quality values (NTU, pH, residual chlorine) are synthesized by the deterministic simulation engine (`backend/app/iot/sim/engine.py`).
   - Every simulated element and response carries `data_tier: "SIMULATED"` and the visual "Simulated" badge per component.
2. **Pump Electrical Dynamics & Inrush Kinetics**:
   - Three-phase voltages and currents are computed from motor nameplate specifications (FLA, rated kW, rated kV) and starter curves (Direct-on-Line inrush factor k=7.0, Star-Delta k=2.5, Soft-Starter k=2.0).
   - The inrush spike decaying exponentially over the startup window is simulated using motor electromechanical physics models.
3. **Diurnal Demand & Hourly Profiles**:
   - While the daily baseline volume for each ward is real, hourly variations, minimum night flows (MNF), and peak demand factors are simulated from standard municipal diurnal curves.
4. **Fault & Leak Injections**:
   - Injected pipeline bursts, pump trips, and sensor dropouts are synthetic scenarios for training, operational analysis, and acoustic verification dispatch.

---

## 3. What is NOT Claimed (Anti-Hallucination & Governance Boundaries)

1. **No Real-Time SCADA Control**:
   - The IoT digital twin is an advisory, supervisory monitoring interface. It does **not** issue control commands (start/stop pump, modulate valve) to physical BWSSB actuators. Pump auto-control mode is simulated locally for state machine realism.
2. **Never Claim Acoustic Pin-Point**:
   - Mass-balance leak detection flags a suspected pipeline segment and estimated volume loss with an uncertainty corridor (e.g. ±350 m). It does **never** claim pinpoint sub-meter precision; field verification with acoustic correlation listening rods is always required.
3. **No Unverified Borewell Counts**:
   - Public borewell quantities vary across government reports (16,000 public borewells reported by BWSSB with 1,800 active IoT units; 3,000 pilot wells reported in JICA survey; 2,150 operational municipal wells in annual reports). The digital twin transparently displays these source conflicts rather than hardcoding a single arbitrary number.
4. **Unverified Capacities Excluded from Totals**:
   - Facilities without published authoritative capacity records (e.g. Machilibetta Reservoir) are explicitly labeled **"Unverified"** and excluded from mass-balance arithmetic.
