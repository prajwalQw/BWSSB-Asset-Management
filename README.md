# Bengaluru Water Network Digital Twin

**Interactive Map-Based Asset Management & Hydraulic Twin for BWSSB Operations**

---

## 1. Quick Start (One-Command Runner)

### Prerequisites
- Python 3.10+ (Virtual environment `.venv` with `wntr`, `fastapi`, `shapely`, `pydantic`)
- Node.js 18+ & npm

### Launching the Application
In this project root (`c:\Users\nagra\Desktop\Bwssb1`), double-click or run:
```cmd
start_all.bat
```
or via Python:
```bash
python run_app.py
```

This single command concurrently orchestrates:
1. **FastAPI Backend (Dual PostGIS / SpatiaLite):** `http://127.0.0.1:8000` (Swagger docs at `/docs`)
2. **Vite React MapLibre Frontend:** `http://localhost:5180`
3. Automatically launches your default web browser to the interactive dashboard.

---

## 2. Strict Compliance with Operational Rules

### Rule 1: Data Tiers (`REAL`, `SIMULATED`, `LIVE`)
Every asset card, popup, graph, and map layer carries a prominent **Provenance Chip**:
- `REAL` (Emerald Badge): Ground-truth infrastructure sourced from OpenCity / BWSSB published datasets, displaying source title and publication date (e.g., `2026-10-16`).
- `SIMULATED` (Purple Badge): Dynamic hydraulic elements synthesized by the WNTR (EPANET) engine.
- `LIVE` (Cyan Badge): Live actuator telemetry streaming via the IGNOAPI bridge (Port 8899).

### Rule 2: Nothing Hardcoded (Admin Portal)
- Pump rating curves, allowable head/power tolerances, junction pressure limits, and DMA Minimum Night Flow (MNF) burst thresholds live in `config/network_rules.json` and `config/simulated_zone.yaml`.
- All operational rules, sensor variable mappings, and parameters are editable on-the-fly via the built-in **Admin Portal** with instant hot-reload and schema validation.

### Rule 3: Simulated Infrastructure Transparency
- Simulated assets are strictly demarcated. Every synthetic node, pipe, and virtual meter is labeled `"Simulated Infrastructure"` with an amber/purple alert banner to prevent confusion with BWSSB's physical assets.

### Rule 4: Read-Only IGNOAPI Bridge
- `ignoAPI.exe` and `ignoAPI.py` are treated as immutable binaries.
- The backend bridge communicates strictly over TCP port 8899 using `{"action": "read_all", "name": "__all__"}` with an automatic exponential backoff mechanism.
- All write, create, and delete commands are blocked by a software safety lock unless `IGNOAPI_ALLOW_WRITES=true` is explicitly configured.

### Rule 5: Open & Licensed Basemaps
- Complies fully with map tile usage policies. Supports:
  - **Carto Dark Matter** (Default)
  - **Carto Positron** (Light mode)
  - **OpenStreetMap Standard** (Attributed)
  - **Esri World Imagery** (Open Satellite layer with full attribution)
  - Zero scraping of unauthorized Google imagery.

### Rule 6: Human-in-the-Loop Governance
- System alerts algorithmically recommend interventions (`requires_human_approval: true`).
- The **Alert Center** enforces an operator sign-off workflow where municipal engineers inspect, approve, or defer maintenance actions. The digital twin performs **no automatic control actions**.

---

## 3. System Architecture

```
+-------------------------------------------------------------------------+
|                  REACT + TYPESCRIPT MAPLIBRE FRONTEND                   |
|   MapLibre GL JS • deck.gl • TailwindCSS • Lucide • Recharts            |
|   - Real Vector Layers (Mains >300mm, STPs, Pumping Stations, Lakes)   |
|   - WNTR Simulated Zone (South-Central Corridor, 20 Nodes, 3 Pumps)     |
|   - Decision Support Alert Center • Admin Dynamic Rules Portal          |
+------------------------------------+------------------------------------+
                                     | SSE Stream & REST API
+------------------------------------v------------------------------------+
|                          FASTAPI BACKEND CORE                           |
|   - Dual Spatial Repository (SpatiaLite Default / PostGIS switch)       |
|   - WNTR (EPANET) Simulation Engine (Leak Injection, Pump Trips)        |
|   - Read-Only IGNOAPI Socket Bridge (Port 8899 Telemetry)               |
+------------------------------------+------------------------------------+
                                     |
+------------------------------------v------------------------------------+
|                         CONFIGURATION & DATA                            |
|   - data/raw/checksums_and_origins.json (Verified SHA-256 Checksums)    |
|   - config/network_rules.json (Editable Thresholds & Pump Ratings)      |
|   - config/simulated_zone.yaml (WNTR EPANET Calibration Config)         |
+-------------------------------------------------------------------------+
```

---

## 4. Single Representative Simulated Zone (WNTR)

- **Anchors:**
  - **Source:** Tataguni Clear Water Sump (`12.8685° N, 77.5140° E`, Elev: 820m MSL)
  - **Pumps:** 3 Centrifugal Pumping Units (2 Duty @ 60 MLD, 1 Standby)
  - **Balancing Reservoirs (2 GLRs):**
    - Mount Joy GLR (Basavanagudi: `12.9372° N, 77.5621° E`, Capacity: 35 MLD)
    - High Grounds Master GLR (Sheshadripuram: `12.9912° N, 77.5843° E`, Capacity: 45 MLD)
  - **Meters & Nodes:** 9 DMA Bulk Flow Meters and 20 Demand Junctions following the real Kanakapura Road -> Basavanagudi -> KR Market corridor with 24-hour diurnal patterns.

---

## 5. Leak Detection & Localisation Engine

The digital twin includes an automated, config-driven leak detection, night-flow anomaly, and hydraulic gradient localisation engine.

### Key Capabilities
1. **Segment-Level Mass Balance:**
   $$\Delta Q_{\text{imbalance}}(t) = \sum Q_{\text{inflow}}(t) - \sum Q_{\text{outflow}}(t) - \sum D_{\text{expected}}(t) - \Delta V_{\text{storage}}$$
   Evaluated dynamically against composite Root-Sum-Square (RSS) sensor instrument noise tolerances with persistence filtering ($N=3$ of $M=4$ intervals) to suppress transient spikes.
2. **Minimum Night Flow (MNF) Analysis:**
   Evaluates nocturnal flow ratios between 02:00 and 04:00 AM (the diurnal demand nadir). Sustained elevations ($>25\%$ over baseline MNF) corroborate physical pipe fractures over legitimate consumer consumption variations.
3. **Sensor Fault Sanity Filtering:**
   Continuously checks for stuck/flat-line sensors ($\text{Var} < 0.001$) and out-of-range physical bounds ($<0$ or $>2000\text{ LPS}$). When instrumentation fails, the engine flags `SENSOR_FAULT_SUSPECTED` and suppresses false leak alarms.
4. **Probabilistic Localisation (Never Claim a Pin-Point):**
   Matches boundary pressure gradients across suspect pipes to compute estimated distance $x^*$ with explicit uncertainty bounds $\pm \delta$ meters (e.g. $307\text{m} \pm 35\text{m}$). Displays continuous probability density curves for acoustic leak survey crews.
5. **Impact & Non-Revenue Water (NRW) Cost Modeling:**
   Calculates daily loss in LPS, Litres/min, and $\text{m}^3/\text{day}$, non-revenue water revenue loss (using configured tariff ₹48.0/kL), downstream pressure drop, affected customer connection count, and extra pump energy (kWh/day).
6. **Automated Validation Suite (`docs/LEAK_VALIDATION.md`):**
   Benchmarks performance across varying injected leak sizes (0, 5, 15, 30, 60, 100 LPS) and sensor faults:
   - **Detection Rate ($\ge 15\text{ LPS}$):** $80.0\%$
   - **Mean Detection Delay:** $1.5\text{ hours}$
   - **False Alarms / Day (Baseline):** $0\text{ / day}$
   - **Mean Localisation Error:** $2.0\text{ meters}$

### Automated Testing
Run the complete automated test suite (11/11 tests passing):
```bash
.venv\Scripts\python.exe -m pytest backend/tests/ -v
```

