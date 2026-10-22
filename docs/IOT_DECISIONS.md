# IoT Module: Design Decisions

> **Feature flag**: `IOT_ENABLED` (env var, default `false`). When `false` the app
> behaviour is identical to the pre-IoT build – the router is not mounted, the
> `/iot` route renders a placeholder, and no IoT layers are registered.

---

## D-01 · Isolation strategy

All new code lives in exactly three new directories:

| Domain | Path |
|--------|------|
| Frontend | `frontend/src/features/iot/` |
| Backend | `backend/app/iot/` |
| Config | `config/iot/` |

Existing files are touched only for the four additive registrations listed in
`docs/IOT_TOUCHED_FILES.md`.

---

## D-02 · Feature flag

`IOT_ENABLED` is read from the environment at both levels:

* **Backend** – `backend/app/iot/config.py` reads `os.environ.get("IOT_ENABLED","false")`.
  When false the router returns 404 for all `/api/v1/iot/*` endpoints.
* **Frontend** – `import.meta.env.VITE_IOT_ENABLED` (string `"true"` / `"false"`).
  When false the top-bar switch and `/iot` route are not rendered.

Default in both cases: **false** (no behaviour change for existing users).

---

## D-03 · Simulation seed and tick

* Default seed: `SIM_SEED=42`. Override via env var.
* Simulation tick: **1 second** (Python `asyncio` task, deterministic RNG from seed).
* Ring-buffer depth: **24 h at 5 s resolution** → 17 280 samples per signal.
* SQLite snapshot: every **60 s**. File: `data/iot_history.db`.

---

## D-04 · Pump starter types and inrush multipliers

| Starter type | Inrush factor k (× FLA) | Ramp-down window |
|---|---|---|
| DOL | 7.0 (range 6–8, midpoint) | 8 s |
| Star-delta | 2.5 (range 2–3, midpoint) | 15 s |
| Soft-starter | 2.0 (range 1.5–3, config) | 20 s |

Source: IEC 60034-1 and standard motor-starter engineering references. Values are
configurable per pump in `config/iot/stations.yaml`.

---

## D-05 · Pipe diameter range for BWSSB bulk meters

The task specification states "reported as 100–1200 mm". BWSSB's published
documents (Karnataka Urban Infrastructure Development & Finance Corporation
project reports, BWSSB Cauvery Stage V DPR summaries) mention bulk meter
installations at 100 mm to 1 000 mm; 1 200 mm is used on the largest
transmission mains.

**Status: unverified from a single authoritative public source.**
Stored in `config/iot/device_types.yaml` with tag `verified: false` and
source note `"BWSSB project DPR references; single authoritative public doc not
located"`.

---

## D-06 · IS 10500:2012 water-quality alarm limits

| Parameter | Acceptable limit | Permissible limit | Alarm |
|---|---|---|---|
| Turbidity (NTU) | 1 | 5 | > 5 NTU (configurable) |
| pH | 6.5–8.5 | 6.5–8.5 | < 6.5 or > 8.5 |
| Free residual chlorine (mg/L) | 0.2 min | 1.0 max | < 0.2 or > 5.0 |

Source: IS 10500:2012 (BIS), "Drinking Water – Specification (Second Revision)".
Verified values. Stored in `config/iot/device_types.yaml`.

---

## D-07 · Borewell count

Multiple BWSSB sources quote different counts:

| Source | Count |
|--------|-------|
| BWSSB Annual Report 2022-23 | ~2 150 borewells |
| Karnataka Groundwater Authority 2021 | ~900 operational |
| data.gov.in BWSSB borewell dataset | depends on filter |

**Decision**: borewell count is **not hardcoded**. The IoT config shows
documented ranges with source citations. The simulation seeds as many IoT
packages as there are borewell points in the GIS dataset at the time of load.

---

## D-08 · WTP names used

Only WTPs with verified names from official BWSSB sources:

| Site | Verified name | Source |
|------|--------------|--------|
| TK Halli | T.K. Halli Water Treatment Plant (Cauvery Stage I/II) | BWSSB official |
| Torekadanahalli (TKH) | Torekadanahalli WTP (Cauvery Stage III/IV) | BWSSB official |
| Harohalli | Harohalli WTP (Cauvery Stage V) | BWSSB Cauvery-5 DPR |
| Tataguni | Tataguni WTP / Clear Water Reservoir complex | BWSSB official |

Note: "Torekadanahalli" and "TK Halli" are sometimes used interchangeably in
older documents. The digital twin treats them as distinct sites matching the
most recent BWSSB zone map.

---

## D-09 · Three seed pumping stations

Stations are anchored to real BWSSB locations from the existing dataset:

| Station ID | Name | Coordinates | Class | Pumps |
|---|---|---|---|---|
| PS_TATAGUNI | Tataguni Terminal PS | 77.5148, 12.8690 | High-lift | H1, H2, H3 |
| PS_MOUNT_JOY_BOOSTER | Mount Joy Booster PS | 77.5621, 12.9372 | Booster | F1, F2 |
| PS_HIGH_GROUNDS_BOOSTER | High Grounds Booster PS | 77.5843, 12.9912 | Booster | F1, F2 |

All generated elements carry `data_tier: "SIMULATED"`.

---

## D-10 · Leak detection algorithm

* **Mass-balance estimator**: `Q_leak = Q_up – Q_down – Q_branch_expected – dV/dt`
* **Uncertainty tolerance**: `k × sqrt(σ_up² + σ_down² + σ_demand²)`, k = 2.0 (95 % CI), configurable.
* **Persistence**: 4 of 5 consecutive windows (each 60 s) must show leak > threshold.
* **Deadband to clear**: leak_estimate < 0.5 × threshold for 3 consecutive windows.
* **Confirmation**: pressure drop ≥ 0.1 bar at downstream PIT required.
* **Sensor health first**: stuck/flat/offline sensors suppress leak alarms.

---

## D-11 · Smart meter anomaly rules

All thresholds in `config/iot/smart_meter_rules.yaml`:

| Rule | Default threshold |
|---|---|
| Leak suspected (night flow) | Q_night > 1.5 × median night flow |
| Continuous flow | Zero Q-hours in 24 h = 0 |
| High usage | daily volume > median + 3 × MAD |
| Low battery | battery_pct < 15 % |
| Comms lost | last_seen > 4 h |

---

## D-12 · Data tier labelling

Every simulated value carries `data_tier: "SIMULATED"`. The "Simulated" chip is
shown **per element** in the inspector and on meter boards. It is **never** placed
on the app title bar.

---

## D-13 · SignalSource interface (future MQTT/OPC-UA readiness)

```python
class SignalSource(Protocol):
    async def subscribe(self, tag: str) -> AsyncIterator[MessageEnvelope]: ...
    async def publish(self, envelope: MessageEnvelope) -> None: ...
```

`SimulatedSource` implements this. A real `MQTTSparkplugSource` or
`OPCUASource` can replace it without UI changes.

---

## D-14 · In-process event bus

Topic pattern: `bwssb/{zone}/{site}/{asset}/{signal}`
Example: `bwssb/south/tataguni/PUMP_TG_01/current_r`

SSE endpoint `/api/v1/iot/stream` multiplexes all subscribed tags to the browser
as `text/event-stream`.

---

## D-15 · MLD flow capacities

Only figures from verified, citable BWSSB sources are used as "real" values.
The Cauvery Stage V (Phase 2) adds 775 MLD (BWSSB, 2023 commissioning report).
Existing stages supply ~1 460 MLD combined (BWSSB Annual Report 2022-23).
Any per-corridor figure not found in a citable source is labelled **"Unverified"**
and excluded from water-balance totals.

---

## D-16 · Ward consumption data

Daily ward consumption is read from the `data/` directory (data.gov.in BWSSB
ward dataset). Hourly readings are **simulated** from a diurnal profile anchored
to the real daily total. Label: "Daily baseline: real data.gov.in; hourly
readings: simulated".

---

## D-17 · No hardcoded coordinates, thresholds, or MLD values

All such values are in YAML/JSON config files under `config/iot/`. CI grep
check is documented in `docs/IOT_DECISIONS.md` (this file) and performed in the
Done Criteria step.

---

## D-18 · Chart constraints

All charts have:
* Fixed pixel height: sparkline 96 px, main 220 px.
* Wrapper with explicit height and `min-width: 0` to prevent flex overflow.
* Three states: skeleton, error with retry, "No data yet".
* Tabular numerals; unit suffix on every value.

---

## D-19 · No browser/server start

Per task rules, the dev server is never started. Static verification only:
`tsc --noEmit` and `eslint` for frontend; `pytest backend/tests/iot/` for
backend.

---

## D-20 · eslint config

The existing `eslint.config.js` is not modified. New IoT files conform to the
same rules (React, TypeScript strict).

---

## D-21 · SQLite state persistence and snapshotting

State is persisted to `data/iot_state.db` across restarts and client reconnections:
- Tables: `sim_state`, `devices_latest`, `timeseries` (24 h retention window), `alerts`, `alert_events`, `injections`.
- Snapshots: Periodic background snapshot every 30 s and synchronous snapshot on FastAPI lifespan shutdown.
- Worker reloading: `uvicorn` is executed with `reload=False` to prevent state wiping during development.

---

## D-22 · Alert lifecycle specification

Alerts strictly follow the ISA-18.2 compliant lifecycle:
- States: `ACTIVE` -> `ACKNOWLEDGED` -> `CLEARED` (or `SHELVED`).
- Alerts are never deleted on condition recovery; they transition to `CLEARED` with `cleared_at` recorded.
- Stable identifiers derived from hashing rule ID, asset/segment ID, and time bucket.
- Query endpoint `GET /api/v1/iot/alerts` supports status filtering and returns active alerts plus the last 24 hours of cleared history.

---

## D-23 · Division and ward normalization

- Data source: `data/bwssb_ward_water_consumption_2026.csv` contains 198 wards.
- Aliases mapping: `config/iot/division_aliases.yaml` maps all 9 canonical divisions and 16 GIS sub-divisions.
- Ground truth rule: Division board totals are strictly computed as the sum of constituent ward records (`sum(w.daily_baseline_mld for w in div.wards)`).

---

## D-24 · Single app-level SSE telemetry stream

- Only one `EventSource` connection is created at the app root level via `IoTStreamProvider`.
- Automatic reconnect with exponential backoff (1 s, 2 s, 4 s, up to 10 s max).
- Supports `Last-Event-ID` replay.
- Global client state stored in `useIoTStore` (`useSyncExternalStore`) to prevent reset on route change.

---

## D-25 · Single Maplibre & Deck.gl overlay lifecycle

- Single `<DigitalTwinMap>` canvas mounted once at root level.
- Route transitions between GIS and IoT toggle visibility via CSS and layer provider sets without destroying WebGL context or calling `setStyle()`.

---

## D-26 · IoT Map Layer Visibility, Dimmed Context & GIS Auto-Templating

- Single Map Mount: App-level `<DigitalTwinMap activeModule={activeModule} />` preserves WebGL canvas across GIS and IoT mode switches.
- Pipe Context Dimming: When `activeModule === 'IOT'`, GIS pipe casing and core PathLayers are dimmed to `0.35` opacity.
- Auto-Templating GIS Assets: All 41 pumping stations and 34 STPs from GeoJSON are automatically templated using `config/iot/templates.yaml` with deterministic random seeds per asset ID.
- Default Layer Toggles: All 13 IoT layers default to ON (`pumpingStations`, `stps`, `tanks`, `wtps`, `flowMeters`, `pressureSensors`, `levelSensors`, `qualityAnalysers`, `borewells`, `valves`, `smartMeters`, `mldCorridors`, `gisPipes`).
- Interactive Left Rail: Added `Layers` tab with live toggle switches and symbology legend. Removed arbitrary slice limits on divisions and wards.

---

## D-27 · Click-to-Inspect Telemetry Standards (GIS & IoT)

- Pump Inspector: Header with pump name and Active/Not active chip (Automatic mode); 3-phase Voltage (V) & Current (A), kW, PF, cumulative kWh, run hours, and flow/pressure sensor readings.
- Twin 220px Line Charts: Bus Voltage vs time (normal band ±5% shaded) and Motor Current vs time (normal band shaded with startup inrush marker) plus thin ON/OFF step strip.
- Station & STP Inspector: Summary KPI row, equipment list with 96px sparklines (clickable to drill down into pump telemetry), and twin 220px trends (Total power kW, Discharge flow MLD).
- Sensor Inspector: Sensor-specific instrumentation displays:
  - Flow meter: flow in L/s, m³/h, and MLD with mechanical/LCD `MeterBoard` register, pipe full/forward flags.
  - Pressure: bar with low/high alarm limits.
  - Level: % and depth in meters.
  - Water quality: pH, turbidity (NTU), free chlorine (mg/L) with IS 10500:2012 limits.
  - Valves & Borewells: valve % open, groundwater depth, extraction rate.
- Cross-Module Inspect: `sectionRegistry` enables telemetry inspection directly from the GIS map while preserving source attributes, rendering "Not published" for blank parameters.

---

*Updated: 2026-10-22*

