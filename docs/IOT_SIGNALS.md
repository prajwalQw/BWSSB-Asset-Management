# IoT Signal Dictionary & Tag Reference

All telemetry signals adhere to **ISA-5.1** identification letters and **OPC UA / Sparkplug B** message envelopes.

## 1. Instrumentation Signals

### Electromagnetic Bulk Flow Meters (`FIT`)
| Tag | Asset Association | Signal Name | Engineering Unit | Valid Range | Resolution | Accuracy | Source Citation |
|---|---|---|---|---|---|---|---|
| `FIT_TG_H1` | Tataguni High-Lift Pump 1 (TG-HLP-01) | `flow_lps` | L/s | 0.0 – 1200.0 | 0.1 | ±0.5% | Cauvery Stage IV SCADA Specs |
| `FIT_TG_H1` | Tataguni High-Lift Pump 1 (TG-HLP-01) | `forward_totaliser_kl` | kL | 0.0 – 99999999.0 | 0.1 | ±0.5% | Meter Register Standard |
| `FIT_TG_H2` | Tataguni High-Lift Pump 2 (TG-HLP-02) | `flow_lps` | L/s | 0.0 – 1200.0 | 0.1 | ±0.5% | Cauvery Stage IV SCADA Specs |
| `FIT_TG_H3` | Tataguni High-Lift Pump 3 (TG-HLP-03) | `flow_lps` | L/s | 0.0 – 1200.0 | 0.1 | ±0.5% | Cauvery Stage IV SCADA Specs |
| `FIT_TG_DISCHARGE` | Tataguni Common Header | `flow_lps` | L/s | 0.0 – 3500.0 | 0.5 | ±0.5% | BWSSB Transmission Main Spec |
| `FIT_MJ_F1` | Mount Joy Booster Pump 1 (MJ-BST-01) | `flow_lps` | L/s | 0.0 – 600.0 | 0.1 | ±0.5% | GLR Booster SCADA Spec |
| `FIT_MJ_F2` | Mount Joy Booster Pump 2 (MJ-BST-02) | `flow_lps` | L/s | 0.0 – 600.0 | 0.1 | ±0.5% | GLR Booster SCADA Spec |
| `FIT_MJ_INLET` | Mount Joy GLR Inlet | `flow_lps` | L/s | 0.0 – 1500.0 | 0.1 | ±0.5% | Yokogawa 2015 Case Study |
| `FIT_HG_F1` | High Grounds Booster Pump 1 (HG-BST-01) | `flow_lps` | L/s | 0.0 – 750.0 | 0.1 | ±0.5% | GLR Booster SCADA Spec |
| `FIT_HG_F2` | High Grounds Booster Pump 2 (HG-BST-02) | `flow_lps` | L/s | 0.0 – 750.0 | 0.1 | ±0.5% | GLR Booster SCADA Spec |

### Pressure Transmitters (`PIT`)
| Tag | Asset Association | Signal Name | Engineering Unit | Valid Range | Low Alarm | High Alarm | Accuracy |
|---|---|---|---|---|---|---|---|
| `PIT_TG_H1` | Tataguni High-Lift Pump 1 Discharge | `pressure_bar` | bar | 0.0 – 25.0 | 2.0 bar | 16.0 bar | ±0.25% |
| `PIT_TG_H2` | Tataguni High-Lift Pump 2 Discharge | `pressure_bar` | bar | 0.0 – 25.0 | 2.0 bar | 16.0 bar | ±0.25% |
| `PIT_TG_H3` | Tataguni High-Lift Pump 3 Discharge | `pressure_bar` | bar | 0.0 – 25.0 | 2.0 bar | 16.0 bar | ±0.25% |
| `PIT_MJ_F1` | Mount Joy Booster Pump 1 Discharge | `pressure_bar` | bar | 0.0 – 16.0 | 1.5 bar | 8.0 bar | ±0.25% |
| `PIT_MJ_F2` | Mount Joy Booster Pump 2 Discharge | `pressure_bar` | bar | 0.0 – 16.0 | 1.5 bar | 8.0 bar | ±0.25% |
| `PIT_HG_F1` | High Grounds Booster Pump 1 Discharge | `pressure_bar` | bar | 0.0 – 16.0 | 1.5 bar | 9.0 bar | ±0.25% |
| `PIT_HG_F2` | High Grounds Booster Pump 2 Discharge | `pressure_bar` | bar | 0.0 – 16.0 | 1.5 bar | 9.0 bar | ±0.25% |

### Level Transmitters (`LIT`)
| Tag | Tank / Reservoir | Signal Name | Engineering Unit | Valid Range | Low Alarm | High Alarm |
|---|---|---|---|---|---|---|
| `LIT_TG_01` | Tataguni Balancing Reservoir | `level_pct` | % | 0.0 – 100.0 | 25.0% | 85.0% |
| `LIT_TG_01` | Tataguni Balancing Reservoir | `level_m` | m | 0.0 – 10.0 | 2.5 m | 8.5 m |
| `LIT_MJ_01` | Mount Joy Ground Level Reservoir | `level_pct` | % | 0.0 – 100.0 | 20.0% | 85.0% |
| `LIT_HG_01` | High Grounds Ground Level Reservoir | `level_pct` | % | 0.0 – 100.0 | 20.0% | 85.0% |

### Water Quality Analysers (`AIT`)
All alarm limits strictly follow **IS 10500:2012**.
| Tag | Location | Signal Name | Unit | Acceptable | Permissible | Alarm Limits |
|---|---|---|---|---|---|---|
| `AIT_TG_01` | Tataguni WTP Outlet | `turbidity_ntu` | NTU | 1.0 | 5.0 | > 5.0 NTU |
| `AIT_TG_01` | Tataguni WTP Outlet | `ph` | pH | 6.5 – 8.5 | 6.5 – 8.5 | < 6.5 or > 8.5 |
| `AIT_TG_01` | Tataguni WTP Outlet | `residual_chlorine_mgl` | mg/L | 0.2 min | 1.0 max | < 0.2 mg/L |
| `AIT_MJ_01` | Mount Joy GLR Outlet | `residual_chlorine_mgl` | mg/L | 0.2 min | 1.0 max | < 0.2 mg/L |
| `AIT_HG_01` | High Grounds GLR Outlet | `residual_chlorine_mgl` | mg/L | 0.2 min | 1.0 max | < 0.2 mg/L |

---

## 2. Pump Electrical and Condition Monitoring Signals (`PMM`)

| Signal Identifier | Description | Unit | Normal Band | Starter Inrush Multiplier |
|---|---|---|---|---|
| `voltage_r`, `voltage_y`, `voltage_b` | 3-Phase Line-to-Line Voltage | V | Nominal ±5% | Sag: 4–6% during starting |
| `current_r`, `current_y`, `current_b` | 3-Phase Phase Current | A | 0.75 – 1.05 × FLA | k × FLA (DOL: 7.0, Star-Delta: 2.5, Soft: 2.0) |
| `active_power_kw` | Real Active Power | kW | P = √3 × V × I × PF | - |
| `power_factor` | Operating Power Factor | PF | 0.85 – 0.91 | - |
| `vibration_rms_mms` | Bearing Housing Vibration | mm/s RMS | 1.2 – 3.8 mm/s | Alarm > 7.1 mm/s |
| `run_state` | State Machine State | enum | OFF, STARTING, RUNNING, STOPPING, TRIPPED | - |
| `run_hours` | Total Lifetime Operating Hours | h | 0 – 99999.0 | - |
| `starts_count` | Number of Motor Starts | count | 0 – 65535 | - |

---

## 3. Ward Smart Meter Signals (`SMR`)

| Signal Identifier | Description | Unit | Baseline Origin |
|---|---|---|---|
| `flow_lps` | Instantaneous Ward Consumption Rate | L/s | Simulated Diurnal Profile anchored to daily baseline |
| `daily_baseline_mld` | Published Ward Daily Demand | MLD | Authentic data.gov.in BWSSB Ward Dataset |
| `current_day_volume_kl` | Cumulative Volume Today | kL | Integrated simulated flow rate |
| `battery_pct` | Internal Battery Capacity | % | 75 – 99% nominal |
| `signal_strength_dbm` | Cellular / LoRaWAN RSSI | dBm | -95 to -65 dBm |
| `flags` | Anomaly Event Bits | bitfield | `leak_suspected`, `continuous_flow`, `high_usage`, `tamper` |
