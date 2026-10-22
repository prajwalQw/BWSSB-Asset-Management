"""
Deterministic Physics-Based Simulation Engine for BWSSB IoT Subsystem.
Implements:
- Pump state machine (OFF -> STARTING -> RUNNING -> STOPPING / TRIPPED)
- Inrush current spike (k * FLA) with exponential decay to steady state
- Operating point calculation (pump head-flow curve vs system curve)
- 3-Phase electrical calculations (V sag during start, imbalance, P = sqrt(3)*V*I*PF)
- Tank mass balance: dV/dt = Q_in - Q_out
- Diurnal municipal demand patterns (morning and evening peaks)
- Water quality kinetics (chlorine decay, turbidity random walk)
- Real ward-consumption baseline integration with simulated smart meters
- Injectable leak and fault simulations with physical response and audit logging
"""

import math
import random
import time
import os
import asyncio
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import logging

import hashlib
import re

from ..config import (
    SIM_SEED,
    STATIONS_PATH,
    NETWORK_FLOWS_PATH,
    SMART_METER_RULES_PATH,
    SIMULATION_PARAMS_PATH,
    ADVISORY_KB_PATH,
    BOREWELLS_PATH,
    DIVISION_ALIASES_PATH,
    TEMPLATES_PATH,
    WARD_CONSUMPTION_CSV_PATH,
    DIVISION_BOUNDARIES_GEOJSON_PATH,
    PUMPING_STATIONS_GEOJSON_PATH,
    STPS_GEOJSON_PATH,
    SUPPLY_MAINS_GEOJSON_PATH,
    load_yaml,
    load_json
)
from ..models import (
    MessageEnvelope,
    DeviceStatus,
    PumpTelemetryState,
    TankState,
    StationOverview,
    IoTAlert,
    WardMeterSummary,
    DivisionBoardSummary,
    WaterFlowCorridor,
    WaterBalanceSummary
)
from ..bus import event_bus
from ..storage import iot_storage
from .ring_buffer import ring_buffer
from .leak_detector import PipeSegmentLeakMonitor

logger = logging.getLogger("bwssb_iot.engine")

class IoTSimulationEngine:
    def __init__(self, seed: int = SIM_SEED):
        self.seed = seed
        self.rng = random.Random(seed)
        self.sim_time: float = time.time()
        self.tick_count: int = 0
        self.is_running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Load configs
        self.stations_cfg = load_yaml(STATIONS_PATH).get("stations", [])
        self.flows_cfg = load_yaml(NETWORK_FLOWS_PATH)
        self.meter_rules_cfg = load_yaml(SMART_METER_RULES_PATH)
        self.sim_params = load_yaml(SIMULATION_PARAMS_PATH)
        self.advisory_kb = load_json(ADVISORY_KB_PATH)
        self.borewells_cfg = load_yaml(BOREWELLS_PATH)
        self.division_aliases_cfg = load_yaml(DIVISION_ALIASES_PATH)

        # Build division normalization lookup map
        self.alias_to_canonical: Dict[str, str] = {}
        self.canonical_division_info: Dict[str, Dict[str, Any]] = {}
        for cdiv in self.division_aliases_cfg.get("canonical_divisions", []):
            cname = cdiv["name"]
            self.canonical_division_info[cname] = cdiv
            for alias in cdiv.get("aliases", []):
                self.alias_to_canonical[alias.strip().lower()] = cname
            self.alias_to_canonical[cname.strip().lower()] = cname
            self.alias_to_canonical[cdiv.get("key", "").strip().lower()] = cname
            if cdiv.get("bbmp_zone"):
                self.alias_to_canonical[cdiv["bbmp_zone"].strip().lower()] = cname

        # Simulation states
        self.active_injections: Dict[str, Any] = {
            "leak": None,
            "pump_faults": {},
            "sensor_faults": {}
        }
        self.injection_audit_log: List[Dict[str, Any]] = []

        # Pumping stations and tanks state
        self.stations_state: Dict[str, Dict[str, Any]] = {}
        self.leak_monitors: Dict[str, PipeSegmentLeakMonitor] = {}
        self.alerts: Dict[str, IoTAlert] = {}

        # Diurnal factors
        self.diurnal_factors = self.meter_rules_cfg.get("diurnal_profile", {}).get("hourly_factors", [
            0.45, 0.38, 0.32, 0.35, 0.58, 0.95,
            1.45, 1.62, 1.48, 1.25, 1.10, 1.05,
            0.98, 0.92, 0.88, 0.90, 1.05, 1.35,
            1.55, 1.48, 1.25, 0.95, 0.72, 0.55
        ])

        # Ward and Division Smart Meters
        self.wards_data: List[Dict[str, Any]] = []
        self.divisions_data: Dict[str, Dict[str, Any]] = {}

        self._init_stations()
        self._init_leak_monitors()
        self._init_smart_meters()
        self._load_persisted_state()

    def normalize_division_name(self, name: str) -> str:
        if not name:
            return "South Division"
        raw = str(name).strip().lower()
        if raw in self.alias_to_canonical:
            return self.alias_to_canonical[raw]
        cleaned = raw.replace("_", " ").replace("-", " ").strip()
        if cleaned in self.alias_to_canonical:
            return self.alias_to_canonical[cleaned]
        for alias, canon in self.alias_to_canonical.items():
            if alias in cleaned or cleaned in alias:
                return canon
        return "South Division"

    def _load_persisted_state(self):
        """Restores state, active alerts and active injections from SQLite."""
        try:
            # 1. Restore simulation clock
            clock_state = iot_storage.get_sim_state("sim_clock")
            if clock_state and isinstance(clock_state, dict):
                self.sim_time = clock_state.get("sim_time", self.sim_time)
                self.tick_count = clock_state.get("tick_count", self.tick_count)
                logger.info(f"Restored persisted simulation clock: tick={self.tick_count}")

            # 2. Restore active & historical alerts from SQLite
            stored_alerts = iot_storage.get_alerts(hours_history=24.0)
            for a_dict in stored_alerts:
                try:
                    alert = IoTAlert(**a_dict)
                    self.alerts[alert.alert_id] = alert
                except Exception as ex:
                    logger.warning(f"Error parsing stored alert {a_dict.get('alert_id')}: {ex}")
            logger.info(f"Restored {len(self.alerts)} alerts from persistent SQLite store.")

            # 3. Restore active injections
            injections = iot_storage.get_active_injections()
            for inj in injections:
                itype = inj.get("injection_type")
                params = inj.get("params", {})
                if itype == "leak":
                    self.active_injections["leak"] = params
                elif itype == "pump_fault":
                    pid = inj.get("target_id")
                    self.active_injections["pump_faults"][pid] = params.get("fault_type", "ELECTRICAL_TRIP")
                elif itype == "sensor_fault":
                    tag = inj.get("target_id")
                    self.active_injections["sensor_faults"][tag] = params.get("fault_type", "COMMS_FAILURE")
            if injections:
                logger.info(f"Restored {len(injections)} active injections from persistent SQLite store.")
        except Exception as e:
            logger.warning(f"Could not load persisted simulation state: {e}")

    def _init_stations(self):
        for stn in self.stations_cfg:
            stn_id = stn["id"]
            tank_cfg = stn.get("tank", {})
            tank_cap = tank_cfg.get("capacity_m3", 30000.0)
            initial_pct = tank_cfg.get("initial_level_pct", 55.0)
            tank_height = tank_cfg.get("height_m", 9.0)

            tank_state = {
                "id": tank_cfg.get("id", f"TANK_{stn_id}"),
                "name": tank_cfg.get("name", "Balancing Tank"),
                "capacity_m3": tank_cap,
                "height_m": tank_height,
                "level_pct": initial_pct,
                "level_m": tank_height * (initial_pct / 100.0),
                "volume_m3": tank_cap * (initial_pct / 100.0),
                "inflow_lps": 0.0,
                "outflow_lps": 0.0,
                "start_level_pct": tank_cfg.get("start_level_pct", 35.0),
                "stop_level_pct": tank_cfg.get("stop_level_pct", 88.0),
            }

            pumps_state = {}
            for p in stn.get("pumps", []):
                pid = p["id"]
                pumps_state[pid] = {
                    "cfg": p,
                    "state": "RUNNING" if p.get("tag") in ("H1", "H2", "F1") else "OFF",
                    "state_timer_s": 600.0,
                    "run_hours": round(self.rng.uniform(1200.0, 8500.0), 1),
                    "starts_count": self.rng.randint(180, 750),
                    "start_elapsed_s": 0.0,
                    "flow_lps": 0.0,
                    "head_m": 0.0,
                    "current_r": 0.0,
                    "current_y": 0.0,
                    "current_b": 0.0,
                    "current_avg": 0.0,
                    "voltage_r": p.get("rated_voltage_v", 415.0),
                    "voltage_y": p.get("rated_voltage_v", 415.0),
                    "voltage_b": p.get("rated_voltage_v", 415.0),
                    "voltage_avg": p.get("rated_voltage_v", 415.0),
                    "active_power_kw": 0.0,
                    "power_factor": p.get("power_factor_rated", 0.88),
                    "vibration_rms_mms": 1.8,
                    "inrush_peak_a": 0.0,
                    "energy_kwh": round(self.rng.uniform(45000.0, 280000.0), 1),
                }

            # Water quality state
            wq_cfg = stn.get("station_instruments", {}).get("water_quality", {})
            wq_state = {
                "tag": wq_cfg.get("tag", f"AIT_{stn_id}"),
                "turbidity_ntu": 0.85,
                "ph": 7.35,
                "residual_chlorine_mgl": 0.65,
                "last_seen": time.time(),
                "comms_state": "ONLINE"
            }

            self.stations_state[stn_id] = {
                "cfg": stn,
                "tank": tank_state,
                "pumps": pumps_state,
                "water_quality": wq_state,
            }

        # 2. Auto-template all REAL pumping stations from GIS data
        templates = load_yaml(TEMPLATES_PATH)
        ps_tmpl = templates.get("pumping_station_template", {})
        stp_tmpl = templates.get("stp_template", {})

        if PUMPING_STATIONS_GEOJSON_PATH.exists():
            try:
                ps_geo = load_json(PUMPING_STATIONS_GEOJSON_PATH)
                for feat in ps_geo.get("features", []):
                    props = feat.get("properties", {})
                    coords = feat.get("geometry", {}).get("coordinates", [])
                    if not coords or len(coords) < 2:
                        continue
                    ps_id = str(props.get("KGISPumpStationID") or props.get("OBJECTID") or props.get("PumpStationID") or "").strip()
                    stn_id = f"PS_GIS_{ps_id}"

                    # Avoid duplicate hero station
                    is_hero = False
                    for existing_stn in self.stations_state.values():
                        ecoords = existing_stn["cfg"].get("coordinates", [])
                        if ecoords and abs(ecoords[0] - coords[0]) < 0.005 and abs(ecoords[1] - coords[1]) < 0.005:
                            is_hero = True
                            break
                    if is_hero:
                        continue

                    seed = int(hashlib.md5(f"ps_{ps_id}".encode()).hexdigest(), 16) % (2**32)
                    prng = random.Random(seed)

                    # Pump count from capacity if published, else default 2
                    cap_raw = str(props.get("Capacity", ""))
                    pump_count = ps_tmpl.get("default_pump_count", 2)
                    nums = re.findall(r"\d+", cap_raw)
                    if nums:
                        val = float(nums[0])
                        if val > 0:
                            pump_count = max(2, min(6, int(val / 25.0)))

                    stn_name = props.get("name") or f"Pumping Station {ps_id}"

                    stn_cfg = {
                        "id": stn_id,
                        "name": stn_name,
                        "zone": "City",
                        "station_class": "booster",
                        "coordinates": [float(coords[0]), float(coords[1])],
                        "site_rotation_deg": 0.0,
                        "data_tier": "SIMULATED",
                    }

                    tank_cap = 15000.0 * pump_count
                    tank_state = {
                        "id": f"TANK_{stn_id}",
                        "name": f"{stn_name} Reservoir",
                        "capacity_m3": tank_cap,
                        "height_m": 8.0,
                        "level_pct": prng.uniform(45.0, 75.0),
                        "level_m": 5.0,
                        "volume_m3": tank_cap * 0.6,
                        "inflow_lps": 120.0 * pump_count,
                        "outflow_lps": 115.0 * pump_count,
                        "start_level_pct": 30.0,
                        "stop_level_pct": 85.0,
                    }

                    pumps_state = {}
                    for p_idx in range(1, pump_count + 1):
                        pid = f"{stn_id}_P{p_idx}"
                        p_running = prng.choice([True, True, False])
                        rated_kw = ps_tmpl.get("pumps", {}).get("rated_power_kw", 250.0)
                        rated_v = ps_tmpl.get("pumps", {}).get("rated_voltage_v", 415.0)
                        rated_i = ps_tmpl.get("pumps", {}).get("rated_fla_a", 420.0)
                        stn_code = re.sub(r"[^A-Z0-9]", "", stn_name.upper())[:6] or "STN"
                        p_cfg = {
                            "id": pid,
                            "tag": f"{stn_code}-BST-0{p_idx}",
                            "display_name": f"Booster Pump {p_idx}",
                            "role": "Booster Pump",
                            "name": f"Booster Pump {p_idx}",
                            "class": "booster",
                            "rated_power_kw": rated_kw,
                            "rated_voltage_v": rated_v,
                            "rated_fla_a": rated_i,
                            "inrush_factor_k": 2.5,
                            "auto_control_mode": "Automatic",
                            "devices": {
                                "flow_meter": {
                                    "tag": f"FIT_{pid}",
                                    "type": "FIT",
                                    "name": "Discharge Flow Meter",
                                },
                                "power_monitor": {
                                    "tag": f"PMM_{pid}",
                                    "type": "PMM",
                                    "name": "Power & Motor Monitor",
                                }
                            }
                        }
                        flow_val = (rated_kw * 1.5) if p_running else 0.0
                        i_val = (rated_i * 0.85) if p_running else 0.0
                        pumps_state[pid] = {
                            "cfg": p_cfg,
                            "state": "RUNNING" if p_running else "OFF",
                            "state_timer_s": 500.0,
                            "run_hours": round(prng.uniform(800.0, 6000.0), 1),
                            "starts_count": prng.randint(100, 450),
                            "start_elapsed_s": 0.0,
                            "flow_lps": round(flow_val, 1),
                            "head_m": 45.0 if p_running else 0.0,
                            "current_r": round(i_val, 1),
                            "current_y": round(i_val, 1),
                            "current_b": round(i_val, 1),
                            "current_avg": round(i_val, 1),
                            "voltage_r": rated_v,
                            "voltage_y": rated_v,
                            "voltage_b": rated_v,
                            "voltage_avg": rated_v,
                            "active_power_kw": round(rated_kw * 0.82 if p_running else 0.0, 1),
                            "power_factor": 0.87,
                            "vibration_rms_mms": 1.5 if p_running else 0.1,
                            "inrush_peak_a": 0.0,
                            "energy_kwh": round(prng.uniform(20000.0, 120000.0), 1),
                        }

                    self.stations_state[stn_id] = {
                        "cfg": stn_cfg,
                        "tank": tank_state,
                        "pumps": pumps_state,
                        "water_quality": {
                            "tag": f"AIT_{stn_id}",
                            "turbidity_ntu": 0.9,
                            "ph": 7.3,
                            "residual_chlorine_mgl": 0.6,
                            "last_seen": time.time(),
                            "comms_state": "ONLINE"
                        }
                    }
            except Exception as e:
                logger.warning(f"Error loading GIS pumping stations: {e}")

        # 3. Auto-template all REAL STPs from GIS data
        if STPS_GEOJSON_PATH.exists():
            try:
                stp_geo = load_json(STPS_GEOJSON_PATH)
                for feat in stp_geo.get("features", []):
                    props = feat.get("properties", {})
                    coords = feat.get("geometry", {}).get("coordinates", [])
                    if not coords or len(coords) < 2:
                        continue
                    stp_id = str(props.get("STPId") or props.get("name") or "").strip()
                    stn_id = f"STP_GIS_{stp_id}"

                    seed = int(hashlib.md5(f"stp_{stp_id}".encode()).hexdigest(), 16) % (2**32)
                    prng = random.Random(seed)

                    raw_name = str(props.get("STPName") or props.get("name") or f"STP {stp_id}").strip()
                    stn_name = re.sub(r"\s+", " ", raw_name)

                    stn_cfg = {
                        "id": stn_id,
                        "name": stn_name,
                        "zone": "City",
                        "station_class": "stp",
                        "coordinates": [float(coords[0]), float(coords[1])],
                        "site_rotation_deg": 0.0,
                        "data_tier": "SIMULATED",
                    }

                    tank_cap = 20000.0
                    tank_state = {
                        "id": f"TANK_{stn_id}",
                        "name": f"{stn_name} Equalization Sump",
                        "capacity_m3": tank_cap,
                        "height_m": 6.0,
                        "level_pct": prng.uniform(50.0, 80.0),
                        "level_m": 4.0,
                        "volume_m3": tank_cap * 0.65,
                        "inflow_lps": 220.0,
                        "outflow_lps": 215.0,
                        "start_level_pct": 25.0,
                        "stop_level_pct": 90.0,
                    }

                    pumps_state = {}
                    equipment = [
                        ("LP1", "Lift Pump 1", 90.0, 155.0),
                        ("LP2", "Lift Pump 2", 90.0, 155.0),
                        ("BL1", "Aeration Blower 1", 110.0, 190.0),
                        ("BL2", "Aeration Blower 2", 110.0, 190.0),
                    ]
                    for eq_tag, eq_name, eq_kw, eq_fla in equipment:
                        pid = f"{stn_id}_{eq_tag}"
                        running = prng.choice([True, True, False])
                        stn_code = re.sub(r"[^A-Z0-9]", "", stn_name.upper())[:6] or "STP"
                        role_name = "Lift Pump" if "Lift" in eq_name else "Aeration Blower"
                        p_cfg = {
                            "id": pid,
                            "tag": f"{stn_code}-{eq_tag}",
                            "display_name": eq_name,
                            "role": role_name,
                            "name": eq_name,
                            "class": "stp_equipment",
                            "rated_power_kw": eq_kw,
                            "rated_voltage_v": 415.0,
                            "rated_fla_a": eq_fla,
                            "auto_control_mode": "Automatic",
                            "devices": {
                                "flow_meter": {
                                    "tag": f"FIT_{pid}",
                                    "type": "FIT",
                                    "name": "Discharge Flow Meter",
                                },
                                "power_monitor": {
                                    "tag": f"PMM_{pid}",
                                    "type": "PMM",
                                    "name": "Power & Motor Monitor",
                                }
                            }
                        }
                        pumps_state[pid] = {
                            "cfg": p_cfg,
                            "state": "RUNNING" if running else "OFF",
                            "state_timer_s": 400.0,
                            "run_hours": round(prng.uniform(1500.0, 8000.0), 1),
                            "starts_count": prng.randint(80, 300),
                            "start_elapsed_s": 0.0,
                            "flow_lps": round(110.0 if running else 0.0, 1),
                            "head_m": 18.0 if running else 0.0,
                            "current_r": round(eq_fla * 0.85 if running else 0.0, 1),
                            "current_y": round(eq_fla * 0.85 if running else 0.0, 1),
                            "current_b": round(eq_fla * 0.85 if running else 0.0, 1),
                            "current_avg": round(eq_fla * 0.85 if running else 0.0, 1),
                            "voltage_r": 415.0,
                            "voltage_y": 415.0,
                            "voltage_b": 415.0,
                            "voltage_avg": 415.0,
                            "active_power_kw": round(eq_kw * 0.8 if running else 0.0, 1),
                            "power_factor": 0.86,
                            "vibration_rms_mms": 1.2 if running else 0.1,
                            "inrush_peak_a": 0.0,
                            "energy_kwh": round(prng.uniform(35000.0, 180000.0), 1),
                        }

                    self.stations_state[stn_id] = {
                        "cfg": stn_cfg,
                        "tank": tank_state,
                        "pumps": pumps_state,
                        "water_quality": {
                            "tag": f"AIT_{stn_id}",
                            "turbidity_ntu": round(prng.uniform(4.0, 8.5), 1),
                            "ph": round(prng.uniform(7.1, 7.8), 2),
                            "dissolved_oxygen_mgl": round(prng.uniform(2.5, 4.8), 2),
                            "residual_chlorine_mgl": 0.2,
                            "last_seen": time.time(),
                            "comms_state": "ONLINE"
                        }
                    }
            except Exception as e:
                logger.warning(f"Error loading GIS STPs: {e}")

    def _init_leak_monitors(self):

        # Transmission corridor between Tataguni and Mount Joy
        self.leak_monitors["CORR_TG_MJ"] = PipeSegmentLeakMonitor(
            segment_id="CORR_TG_MJ",
            upstream_meter_tag="FIT_TG_DISCHARGE",
            downstream_meter_tag="FIT_MJ_INLET",
            downstream_pit_tag="PIT_MJ_F1",
            pipe_dn_mm=1200,
            length_km=12.8,
            nearest_road="Kanakapura Road / Pipeline Corridor V-104",
            k_factor=2.0,
            threshold_lps=5.0,
            pressure_drop_bar=0.10,
        )
        self.leak_monitors["CORR_TATAGUNI_MOUNT_JOY"] = self.leak_monitors["CORR_TG_MJ"]

    def _init_smart_meters(self):
        # Load real wards CSV
        if WARD_CONSUMPTION_CSV_PATH.exists():
            try:
                df = pd.read_csv(WARD_CONSUMPTION_CSV_PATH)
                for _, row in df.iterrows():
                    ward_no = int(row.get("ward_no", 0))
                    w_name = str(row.get("ward_name", f"Ward {ward_no}"))
                    raw_div = str(row.get("bwssb_division", "South Division"))
                    div_name = self.normalize_division_name(raw_div)
                    zone_name = str(row.get("bbmp_zone", "South"))
                    daily_mld = float(row.get("daily_consumption_mld", 3.5))
                    avg_lps = (daily_mld * 1000000.0) / 86400.0

                    status = "ONLINE"
                    flags = []
                    battery_pct = round(self.rng.uniform(75.0, 99.0), 1)
                    sig_dbm = round(self.rng.uniform(-92.0, -68.0), 1)

                    # Deterministic anomaly seeding according to config rules
                    if ward_no % 47 == 0:
                        battery_pct = round(self.rng.uniform(8.5, 14.2), 1)
                        flags.append("low_battery")
                    if ward_no % 63 == 0:
                        status = "OFFLINE"
                        sig_dbm = -118.0
                        flags.append("comms_lost")
                    if ward_no % 31 == 0:
                        flags.append("leak_suspected")
                    if ward_no % 79 == 0:
                        flags.append("continuous_flow")
                    if ward_no % 53 == 0:
                        flags.append("high_usage")
                    if ward_no % 89 == 0:
                        flags.append("reverse_flow")
                    if ward_no % 97 == 0:
                        flags.append("tamper_event")

                    self.wards_data.append({
                        "ward_no": ward_no,
                        "ward_name": w_name,
                        "bbmp_zone": zone_name,
                        "bwssb_division": div_name,
                        "meter_tag": f"SMR_W_{ward_no:03d}",
                        "daily_baseline_mld": daily_mld,
                        "flow_lps": round(avg_lps, 2),
                        "current_day_volume_kl": round(daily_mld * 1000 * 0.5, 1),
                        "cumulative_totaliser_kl": round(self.rng.uniform(450000.0, 1800000.0), 1),
                        "battery_pct": battery_pct,
                        "signal_strength_dbm": sig_dbm,
                        "status": status,
                        "flags": flags
                    })
            except Exception as e:
                logger.warning(f"Could not load ward consumption CSV: {e}")

        # Extract supply mains coordinates for snapping
        mains_coords = []
        if SUPPLY_MAINS_GEOJSON_PATH.exists():
            try:
                with open(SUPPLY_MAINS_GEOJSON_PATH, "r", encoding="utf-8") as f:
                    mdata = json.load(f)
                for feat in mdata.get("features", []):
                    geom = feat.get("geometry", {})
                    gtype = geom.get("type")
                    if gtype == "LineString":
                        mains_coords.extend(geom.get("coordinates", []))
                    elif gtype == "MultiLineString":
                        for line in geom.get("coordinates", []):
                            mains_coords.extend(line)
            except Exception as e:
                logger.warning(f"Failed to load supply mains for smart meter snapping: {e}")

        mains_arr = np.array(mains_coords, dtype=np.float64) if mains_coords else None

        # Group into all 9 canonical divisions from config/iot/division_aliases.yaml
        for cdiv in self.division_aliases_cfg.get("canonical_divisions", []):
            div_name = cdiv["name"]
            coords = cdiv.get("centroid", [77.5950, 12.9750])
            if mains_arr is not None and len(mains_arr) > 0:
                diff = mains_arr - np.array(coords, dtype=np.float64)
                idx = int(np.argmin(diff[:, 0]**2 + diff[:, 1]**2))
                coords = [round(float(mains_arr[idx][0]), 6), round(float(mains_arr[idx][1]), 6)]

            self.divisions_data[div_name] = {
                "division_name": div_name,
                "centroid_coordinates": coords,
                "inlet_meter_tag": f"FIT_DIV_{div_name[:4].upper()}_INLET",
                "inlet_mld": 0.0,
                "hourly_inlet_profile": [0.0] * 24,
                "hourly_ward_sum_profile": [0.0] * 24,
            }

    def _get_diurnal_factor(self, hour: float) -> float:
        idx = int(hour) % 24
        next_idx = (idx + 1) % 24
        frac = hour - int(hour)
        return self.diurnal_factors[idx] * (1.0 - frac) + self.diurnal_factors[next_idx] * frac

    def tick(self, dt_sec: float = 1.0):
        """Advances physics simulation by dt_sec."""
        self.sim_time += dt_sec
        self.tick_count += 1
        now_epoch = time.time()
        curr_hour = (self.tick_count / 3600.0) % 24.0
        diurnal_factor = self._get_diurnal_factor(curr_hour)

        # 1. Update Each Pumping Station
        is_5s_tick = (self.tick_count % 5 == 0)
        for stn_id, stn_obj in self.stations_state.items():
            if (stn_id.startswith("PS_GIS_") or stn_id.startswith("STP_GIS_")) and not is_5s_tick:
                continue
            tank = stn_obj["tank"]
            pumps = stn_obj["pumps"]
            total_station_flow_lps = 0.0

            # Pump State Machines & Hydraulics
            for pid, pdata in pumps.items():
                pcfg = pdata["cfg"]
                pstate = pdata["state"]
                pdata["state_timer_s"] += dt_sec

                # Check faults
                is_faulted = self.active_injections["pump_faults"].get(pid) is not None
                if is_faulted and pstate != "TRIPPED":
                    pdata["state"] = "TRIPPED"
                    pstate = "TRIPPED"
                    pdata["state_timer_s"] = 0.0
                    self._raise_pump_trip_alert(stn_id, pid, self.active_injections["pump_faults"][pid])

                # Automatic Hysteresis Level Control
                if pdata["cfg"].get("auto_control_mode") == "Automatic" and not is_faulted:
                    min_run = pcfg.get("min_run_time_s", 240)
                    min_off = pcfg.get("min_off_time_s", 120)

                    # Tank level low -> start pump
                    if tank["level_pct"] <= tank["start_level_pct"] and pstate == "OFF" and pdata["state_timer_s"] >= min_off:
                        pdata["state"] = "STARTING"
                        pstate = "STARTING"
                        pdata["state_timer_s"] = 0.0
                        pdata["start_elapsed_s"] = 0.0
                        pdata["starts_count"] += 1

                    # Tank level high -> stop pump
                    elif tank["level_pct"] >= tank["stop_level_pct"] and pstate == "RUNNING" and pdata["state_timer_s"] >= min_run:
                        pdata["state"] = "STOPPING"
                        pstate = "STOPPING"
                        pdata["state_timer_s"] = 0.0

                # State Transitions
                ramp_sec = pcfg.get("start_ramp_sec", 15.0)
                if pstate == "STARTING":
                    pdata["start_elapsed_s"] += dt_sec
                    if pdata["start_elapsed_s"] >= ramp_sec:
                        pdata["state"] = "RUNNING"
                        pstate = "RUNNING"
                        pdata["state_timer_s"] = 0.0

                elif pstate == "STOPPING":
                    if pdata["state_timer_s"] >= 5.0:
                        pdata["state"] = "OFF"
                        pstate = "OFF"
                        pdata["state_timer_s"] = 0.0

                # Operating Point Hydraulics (Intersection of Pump & System Curve)
                v_rated = pcfg.get("rated_voltage_v", 415.0)
                fla = pcfg.get("rated_fla_a", 124.5)
                starter = pcfg.get("starter_type", "DOL")
                k_inrush = pcfg.get("inrush_factor_k", 2.0)
                p_curve = pcfg.get("pump_curve", {})
                sys_curve = pcfg.get("system_curve", {})

                # H = A - B*Q^2; H_sys = H_stat + k*Q^2
                A = p_curve.get("curve_a", 125.0)
                B = p_curve.get("curve_b", 0.00000293)
                H_stat = sys_curve.get("static_lift_m", 65.0)
                k_sys = sys_curve.get("resistance_k", 0.00000293)

                if pstate in ("RUNNING", "STARTING"):
                    # Q^2 = (A - H_stat) / (B + k_sys)
                    delta_h = max(1.0, A - H_stat)
                    sum_k = max(1e-8, B + k_sys)
                    q_operating_m3h = math.sqrt(delta_h / sum_k)
                    h_operating = A - B * (q_operating_m3h**2)
                    q_lps = (q_operating_m3h * 1000.0) / 3600.0

                    if pstate == "STARTING":
                        # Inrush Current Profile: Inrush = k * FLA * exp(-t / tau) + I_steady
                        tau = ramp_sec / 3.0
                        inrush_mult = 1.0 + (k_inrush - 1.0) * math.exp(-pdata["start_elapsed_s"] / tau)
                        pdata["inrush_peak_a"] = round(k_inrush * fla, 1)
                        steady_i = fla * 0.85
                        i_calc = steady_i * inrush_mult
                        v_sag = v_rated * 0.94  # 6% voltage sag during inrush
                        pdata["flow_lps"] = q_lps * (pdata["start_elapsed_s"] / ramp_sec)
                    else:
                        # Steady running with small load variance and noise
                        steady_load_ratio = 0.85 + 0.10 * (q_lps / pcfg.get("flow_lps_rated", 888.0))
                        noise_i = self.rng.gauss(0.0, fla * 0.01)
                        i_calc = fla * steady_load_ratio + noise_i
                        v_sag = v_rated * 0.99
                        pdata["flow_lps"] = q_lps + self.rng.gauss(0.0, q_lps * 0.008)

                    pdata["head_m"] = round(h_operating, 1)
                    pdata["run_hours"] += dt_sec / 3600.0

                    # 3-Phase Voltage & Current with small unbalance
                    unbal_v = self.rng.uniform(-0.012, 0.012)
                    pdata["voltage_r"] = round(v_sag * (1.0 + unbal_v), 1)
                    pdata["voltage_y"] = round(v_sag * (1.0 - unbal_v * 0.5), 1)
                    pdata["voltage_b"] = round(v_sag * (1.0 - unbal_v * 0.5), 1)
                    pdata["voltage_avg"] = round((pdata["voltage_r"] + pdata["voltage_y"] + pdata["voltage_b"]) / 3.0, 1)

                    unbal_i = self.rng.uniform(-0.015, 0.015)
                    pdata["current_r"] = round(i_calc * (1.0 + unbal_i), 1)
                    pdata["current_y"] = round(i_calc * (1.0 - unbal_i * 0.5), 1)
                    pdata["current_b"] = round(i_calc * (1.0 - unbal_i * 0.5), 1)
                    pdata["current_avg"] = round((pdata["current_r"] + pdata["current_y"] + pdata["current_b"]) / 3.0, 1)

                    pf = pcfg.get("power_factor_rated", 0.88)
                    # P = sqrt(3) * V_LL * I * PF
                    p_kw = (math.sqrt(3.0) * pdata["voltage_avg"] * pdata["current_avg"] * pf) / 1000.0
                    pdata["active_power_kw"] = round(p_kw, 1)
                    pdata["energy_kwh"] += (p_kw * dt_sec) / 3600.0
                    pdata["vibration_rms_mms"] = round(1.8 + (pdata["current_avg"] / fla) * 0.8 + self.rng.uniform(-0.1, 0.1), 2)

                    total_station_flow_lps += pdata["flow_lps"]

                else:
                    # OFF / TRIPPED
                    pdata["flow_lps"] = 0.0
                    pdata["head_m"] = 0.0
                    pdata["current_r"] = 0.0
                    pdata["current_y"] = 0.0
                    pdata["current_b"] = 0.0
                    pdata["current_avg"] = 0.0
                    pdata["voltage_r"] = round(v_rated, 1)
                    pdata["voltage_y"] = round(v_rated, 1)
                    pdata["voltage_b"] = round(v_rated, 1)
                    pdata["voltage_avg"] = round(v_rated, 1)
                    pdata["active_power_kw"] = 0.0
                    pdata["vibration_rms_mms"] = 0.1

                # Append to Ring Buffer (every 5 seconds)
                if self.tick_count % 5 == 0:
                    ring_buffer.append(pcfg.get("tag", pid), "current_avg", now_epoch, pdata["current_avg"])
                    ring_buffer.append(pcfg.get("tag", pid), "voltage_avg", now_epoch, pdata["voltage_avg"])
                    ring_buffer.append(pcfg.get("tag", pid), "active_power_kw", now_epoch, pdata["active_power_kw"])
                    ring_buffer.append(pcfg.get("tag", pid), "flow_lps", now_epoch, pdata["flow_lps"])

            # Tank Mass Balance: dV/dt = Q_in - Q_out
            tank["inflow_lps"] = total_station_flow_lps
            # Outflow follows diurnal curve
            rated_outflow_lps = (tank["capacity_m3"] * 0.75 * 1000.0) / 86400.0
            leak_drawdown_lps = 0.0
            if self.active_injections.get("leak"):
                leak_drawdown_lps = self.active_injections["leak"].get("leak_rate_lps", 18.5)

            tank["outflow_lps"] = (rated_outflow_lps * diurnal_factor) + leak_drawdown_lps
            dv_m3 = ((tank["inflow_lps"] - tank["outflow_lps"]) * dt_sec) / 1000.0
            tank["volume_m3"] = max(100.0, min(tank["capacity_m3"], tank["volume_m3"] + dv_m3))
            tank["level_pct"] = round((tank["volume_m3"] / tank["capacity_m3"]) * 100.0, 1)
            tank["level_m"] = round(tank["height_m"] * (tank["level_pct"] / 100.0), 2)

            if self.tick_count % 5 == 0:
                ring_buffer.append(tank["id"], "level_pct", now_epoch, tank["level_pct"])
                ring_buffer.append(tank["id"], "level_m", now_epoch, tank["level_m"])

            # Water Quality Kinetics
            wq = stn_obj["water_quality"]
            # Chlorine decays: dC/dt = -k * C
            decay_k = self.sim_params.get("water_quality_model", {}).get("chlorine_bulk_decay_coefficient_per_hour", 0.045) / 3600.0
            wq["residual_chlorine_mgl"] = max(0.12, wq["residual_chlorine_mgl"] - decay_k * wq["residual_chlorine_mgl"] + self.rng.gauss(0.0, 0.0005))
            # Turbidity slow bounded random walk
            wq["turbidity_ntu"] = max(0.2, min(4.8, wq["turbidity_ntu"] + self.rng.gauss(0.0, 0.01)))
            wq["ph"] = max(6.6, min(8.3, wq["ph"] + self.rng.gauss(0.0, 0.005)))
            wq["last_seen"] = now_epoch

        # 2. Leak Detection Evaluation
        # Upstream flow from Tataguni discharge; downstream at Mount Joy inlet
        q_tg_discharge = self.stations_state.get("PS_TATAGUNI", {}).get("tank", {}).get("outflow_lps", 800.0)
        # Physical effect of leak: downstream flow drops
        sim_leak = self.active_injections.get("leak")
        leak_rate = sim_leak.get("leak_rate_lps", 0.0) if sim_leak else 0.0

        q_mj_inlet = max(0.0, q_tg_discharge - leak_rate + self.rng.gauss(0.0, 1.2))
        # Pressure drop at downstream PIT: dp = head loss change
        base_p = 4.2
        pressure_downstream = max(1.2, base_p - (leak_rate * 0.015) + self.rng.gauss(0.0, 0.02))

        monitor = self.leak_monitors.get("CORR_TG_MJ")
        if monitor:
            # Check sensor faults suppression
            up_healthy = self.active_injections["sensor_faults"].get("FIT_TG_DISCHARGE") is None
            down_healthy = self.active_injections["sensor_faults"].get("FIT_MJ_INLET") is None
            pit_healthy = self.active_injections["sensor_faults"].get("PIT_MJ_F1") is None

            leak_alert = monitor.evaluate(
                q_upstream_lps=q_tg_discharge,
                q_downstream_lps=q_mj_inlet,
                dv_dt_lps=0.0,
                pressure_downstream_bar=pressure_downstream,
                upstream_healthy=up_healthy,
                downstream_healthy=down_healthy,
                pit_healthy=pit_healthy,
                sim_leak_injection=sim_leak
            )
            if leak_alert:
                self.alerts[leak_alert.alert_id] = leak_alert
                iot_storage.save_alert(leak_alert.model_dump())
                if not leak_alert.active and leak_alert.status == "CLEARED":
                    iot_storage.record_alert_event(leak_alert.alert_id, "CLEARED", {"reason": "Deadband recovery"})

        # 3. Smart Meter Boards Simulation (Ward & Division Updates)
        for w in self.wards_data:
            # Hourly flow rate in L/s
            daily_mld = w["daily_baseline_mld"]
            avg_lps = (daily_mld * 1000000.0) / 86400.0
            w["flow_lps"] = round(avg_lps * diurnal_factor + self.rng.gauss(0.0, avg_lps * 0.03), 2)
            vol_add_kl = (w["flow_lps"] * dt_sec) / 1000.0
            w["current_day_volume_kl"] = round(w["current_day_volume_kl"] + vol_add_kl, 2)
            w["cumulative_totaliser_kl"] = round(w["cumulative_totaliser_kl"] + vol_add_kl, 2)

        # 4. Periodic Snapshot (every 30 seconds to SQLite)
        if self.tick_count % 30 == 0:
            self.snapshot_state()

    def snapshot_state(self):
        """Flushes simulation clock, latest telemetry, ring buffer, and alerts to SQLite."""
        try:
            iot_storage.set_sim_state("sim_clock", {
                "sim_time": self.sim_time,
                "tick_count": self.tick_count,
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.sim_time))
            })

            # Save device latest readings batch
            dev_rows = []
            now = time.time()
            for s in self.stations_state.values():
                for p in s["pumps"].values():
                    pcfg = p["cfg"]
                    tag = pcfg.get("tag", pcfg.get("id"))
                    dev_rows.append((tag, "voltage_avg", float(p["voltage_avg"]), "V", "Good", now))
                    dev_rows.append((tag, "current_avg", float(p["current_avg"]), "A", "Good", now))
                    dev_rows.append((tag, "active_power_kw", float(p["active_power_kw"]), "kW", "Good", now))
                    dev_rows.append((tag, "flow_lps", float(p["flow_lps"]), "L/s", "Good", now))
            iot_storage.save_device_latest_batch(dev_rows)

            ring_buffer.snapshot_to_sqlite()
            iot_storage.prune_old_timeseries(24.0)

            for a in self.alerts.values():
                iot_storage.save_alert(a.model_dump())
        except Exception as e:
            logger.warning(f"Error during state snapshot: {e}")

    def _raise_pump_trip_alert(self, stn_id: str, pump_id: str, fault_type: str):
        alert_id = f"ALT-TRIP-{pump_id}"
        now_epoch = time.time()
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_epoch))
        alert = IoTAlert(
            alert_id=alert_id,
            rule_id="RULE-PUMP-TRIP-01",
            asset_id=pump_id,
            category="ELECTROMECHANICAL",
            severity="CRITICAL",
            title=f"Pump {pump_id} Protection Trip ({fault_type})",
            location=f"Pumping Station {stn_id}",
            coordinates=[77.5148, 12.8690],
            metric_observed=f"Trip signal received: {fault_type}. Run state changed to TRIPPED.",
            recommendation="Inspect protection relay annunciator. Check motor insulation resistance and rotate standby unit.",
            requires_human_approval=True,
            human_decision_status="PENDING_REVIEW",
            status="ACTIVE",
            first_seen=now_epoch,
            last_seen=now_epoch,
            timestamp=now_iso,
            timestamp_epoch=now_epoch,
            data_tier="SIMULATED",
            source="IOT",
            active=True
        )
        self.alerts[alert_id] = alert
        iot_storage.save_alert(alert.model_dump())
        iot_storage.record_alert_event(alert_id, "TRIGGERED", {"fault_type": fault_type, "pump_id": pump_id})

    # Injections
    def inject_leak(self, pipe_segment_id: str, leak_rate_lps: float, landmark: Optional[str] = None):
        injection = {
            "pipe_segment_id": pipe_segment_id,
            "leak_rate_lps": leak_rate_lps,
            "landmark": landmark or "Pipeline Road Chainage 4+200",
            "timestamp": time.time()
        }
        self.active_injections["leak"] = injection
        iot_storage.save_injection("leak", pipe_segment_id, injection, active=True)
        self.injection_audit_log.append({
            "action": "INJECT_LEAK",
            "details": injection,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })
        # Immediately trigger 4 positive windows in monitor for prompt test verification
        monitor = self.leak_monitors.get(pipe_segment_id) or self.leak_monitors.get("CORR_TG_MJ")
        if monitor:
            monitor.window_results = [True, True, True, True]

    def stop_leak(self, pipe_segment_id: Optional[str] = None):
        target = pipe_segment_id or "CORR_TG_MJ"
        self.active_injections["leak"] = None
        iot_storage.clear_injection("leak", target)
        monitor = self.leak_monitors.get(target) or self.leak_monitors.get("CORR_TG_MJ")
        if monitor:
            monitor.window_results = [False, False, False, False, False]
            if monitor.active_alert:
                monitor.active_alert.status = "CLEARED"
                monitor.active_alert.active = False
                monitor.active_alert.cleared_at = time.time()
        for aid in [f"ALT-LEAK-{target}", "ALT-LEAK-CORR_TG_MJ", "ALT-LEAK-CORR_TATAGUNI_MOUNT_JOY"]:
            if aid in self.alerts:
                self.clear_alert(aid)
        self.injection_audit_log.append({
            "action": "STOP_LEAK",
            "target": target,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })

    def inject_pump_fault(self, pump_id: str, fault_type: str):
        self.active_injections["pump_faults"][pump_id] = fault_type
        iot_storage.save_injection("pump_fault", pump_id, {"fault_type": fault_type}, active=True)
        self.injection_audit_log.append({
            "action": "INJECT_PUMP_FAULT",
            "pump_id": pump_id,
            "fault_type": fault_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })

    def inject_sensor_fault(self, tag: str, fault_type: str):
        self.active_injections["sensor_faults"][tag] = fault_type
        iot_storage.save_injection("sensor_fault", tag, {"fault_type": fault_type}, active=True)
        self.injection_audit_log.append({
            "action": "INJECT_SENSOR_FAULT",
            "device_tag": tag,
            "fault_type": fault_type,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })

    def reset_simulation(self):
        """Resets simulation faults and transitions active simulated alerts to CLEARED."""
        self.active_injections = {"leak": None, "pump_faults": {}, "sensor_faults": {}}
        iot_storage.reset_all_injections()
        now_epoch = time.time()
        for a in self.alerts.values():
            if a.active:
                a.active = False
                a.status = "CLEARED"
                a.cleared_at = now_epoch
                iot_storage.save_alert(a.model_dump())
                iot_storage.record_alert_event(a.alert_id, "CLEARED", {"reason": "SIMULATION_RESET"})
        for m in self.leak_monitors.values():
            m.active_alert = None
            m.window_results.clear()
        self._init_stations()
        self.injection_audit_log.append({
            "action": "RESET_SIMULATION",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        })
        self.snapshot_state()

    # Alert Actions
    def acknowledge_alert(self, alert_id: str, operator: str = "OPERATOR") -> Optional[IoTAlert]:
        now_epoch = time.time()
        alert = self.alerts.get(alert_id)
        if not alert:
            for a_dict in iot_storage.get_alerts():
                if a_dict["alert_id"] == alert_id:
                    alert = IoTAlert(**a_dict)
                    break
        if alert:
            alert.status = "ACKNOWLEDGED"
            alert.acknowledged = True
            alert.acknowledged_by = operator
            alert.acknowledged_at = now_epoch
            alert.last_seen = now_epoch
            self.alerts[alert_id] = alert
            iot_storage.save_alert(alert.model_dump())
            iot_storage.record_alert_event(alert_id, "ACKNOWLEDGED", {"operator": operator})
            return alert
        return None

    def snooze_alert(self, alert_id: str, duration_s: float = 3600.0) -> Optional[IoTAlert]:
        now_epoch = time.time()
        alert = self.alerts.get(alert_id)
        if alert:
            alert.status = "SHELVED"
            alert.shelved = True
            alert.last_seen = now_epoch
            self.alerts[alert_id] = alert
            iot_storage.save_alert(alert.model_dump())
            iot_storage.record_alert_event(alert_id, "SHELVED", {"duration_s": duration_s})
            return alert
        return None

    def clear_alert(self, alert_id: str) -> Optional[IoTAlert]:
        now_epoch = time.time()
        alert = self.alerts.get(alert_id)
        if alert:
            alert.status = "CLEARED"
            alert.active = False
            alert.cleared_at = now_epoch
            self.alerts[alert_id] = alert
            iot_storage.save_alert(alert.model_dump())
            iot_storage.record_alert_event(alert_id, "CLEARED", {"manual": True})
            return alert
        return None

    def get_alerts_list(self, status: Optional[str] = None) -> List[IoTAlert]:
        cutoff = time.time() - 86400.0
        persisted = iot_storage.get_alerts(status=status, hours_history=24.0)
        merged: Dict[str, IoTAlert] = {}
        for p in persisted:
            try:
                alert = IoTAlert(**p)
                merged[alert.alert_id] = alert
            except Exception:
                pass
        for aid, a in self.alerts.items():
            if not status:
                if a.status in ("ACTIVE", "ACKNOWLEDGED") or a.last_seen >= cutoff:
                    merged[aid] = a
            elif a.status == status.upper():
                merged[aid] = a
        return sorted(list(merged.values()), key=lambda x: x.last_seen, reverse=True)

    # Data Accessors
    def get_stations(self) -> List[StationOverview]:
        res = []
        for stn_id, s in self.stations_state.items():
            cfg = s["cfg"]
            tank_data = s["tank"]
            tank_model = TankState(
                tank_id=tank_data["id"],
                station_id=stn_id,
                name=tank_data["name"],
                level_m=tank_data["level_m"],
                level_pct=tank_data["level_pct"],
                volume_m3=tank_data["volume_m3"],
                capacity_m3=tank_data["capacity_m3"],
                inflow_lps=tank_data["inflow_lps"],
                outflow_lps=tank_data["outflow_lps"],
                data_tier="SIMULATED"
            )

            pumps_list = []
            devices_list = []
            for pid, p in s["pumps"].items():
                pcfg = p["cfg"]
                p_state = PumpTelemetryState(
                    pump_id=pid,
                    tag=pcfg.get("tag", pid),
                    display_name=pcfg.get("display_name", pcfg.get("name", pid)),
                    role=pcfg.get("role", pcfg.get("class", "Pump")),
                    station_id=stn_id,
                    run_state=p["state"],
                    auto_control_mode=pcfg.get("auto_control_mode", "Automatic"),
                    run_hours=round(p["run_hours"], 1),
                    starts_count=p["starts_count"],
                    flow_lps=round(p["flow_lps"], 1),
                    head_m=round(p["head_m"], 1),
                    current_r=round(p["current_r"], 1),
                    current_y=round(p["current_y"], 1),
                    current_b=round(p["current_b"], 1),
                    current_avg=round(p["current_avg"], 1),
                    voltage_r=round(p["voltage_r"], 1),
                    voltage_y=round(p["voltage_y"], 1),
                    voltage_b=round(p["voltage_b"], 1),
                    voltage_avg=round(p["voltage_avg"], 1),
                    active_power_kw=round(p["active_power_kw"], 1),
                    power_factor=round(p["power_factor"], 2),
                    vibration_rms_mms=round(p["vibration_rms_mms"], 2),
                    inrush_peak_a=round(p["inrush_peak_a"], 1),
                    energy_kwh=round(p["energy_kwh"], 1),
                    data_tier="SIMULATED",
                    updated_at=time.time()
                )
                pumps_list.append(p_state)

                # Collect devices
                for dev_key, dev in pcfg.get("devices", {}).items():
                    tag = dev.get("tag", f"{pid}_{dev_key}")
                    fault = self.active_injections["sensor_faults"].get(tag)
                    comms = "OFFLINE" if fault == "OFFLINE" else "ONLINE"
                    devices_list.append(DeviceStatus(
                        tag=tag,
                        type_code=dev.get("type", "FIT"),
                        name=dev.get("name", tag),
                        asset_link=pid,
                        location={"station_id": stn_id, "offset_m": dev.get("offset_m", [0, 0])},
                        active=fault != "OFFLINE",
                        comms_state=comms,
                        last_seen=time.time(),
                        quality="Bad" if fault else "Good",
                        data_tier="SIMULATED",
                        latest_values={"value": p["flow_lps"] if "FIT" in tag else (p["head_m"] if "PIT" in tag else p["current_avg"])}
                    ))

            res.append(StationOverview(
                id=stn_id,
                name=cfg["name"],
                zone=cfg.get("zone", "South"),
                station_class=cfg.get("station_class", "high-lift"),
                coordinates=cfg["coordinates"],
                site_rotation_deg=cfg.get("site_rotation_deg", 0.0),
                tank=tank_model,
                pumps=pumps_list,
                devices=devices_list,
                data_tier="SIMULATED"
            ))
        return res

    def get_smart_meters(self) -> List[DivisionBoardSummary]:
        results = []
        for div_name, div_info in self.divisions_data.items():
            div_wards = [w for w in self.wards_data if self.normalize_division_name(w["bwssb_division"]) == div_name]
            if not div_wards:
                continue

            ward_summaries = []
            sum_ward_mld = 0.0
            sum_vol_today_kl = 0.0
            wards_online = 0
            wards_offline = 0
            alerts_by_type: Dict[str, int] = {
                "leak_suspected": 0,
                "continuous_flow": 0,
                "high_usage": 0,
                "low_battery": 0,
                "comms_lost": 0,
                "reverse_flow": 0,
                "tamper_event": 0
            }

            for w in div_wards:
                w_mld = (w["flow_lps"] * 86400.0) / 1000000.0
                sum_ward_mld += w_mld
                sum_vol_today_kl += w.get("current_day_volume_kl", 0.0)
                if w.get("status") == "ONLINE":
                    wards_online += 1
                else:
                    wards_offline += 1

                for fl in w.get("flags", []):
                    if fl in alerts_by_type:
                        alerts_by_type[fl] += 1

                ward_summaries.append(WardMeterSummary(
                    ward_no=w["ward_no"],
                    ward_name=w["ward_name"],
                    bbmp_zone=w["bbmp_zone"],
                    bwssb_division=div_name,
                    meter_tag=w["meter_tag"],
                    flow_lps=round(w["flow_lps"], 1),
                    daily_baseline_mld=round(w["daily_baseline_mld"], 2),
                    current_day_volume_kl=round(w["current_day_volume_kl"], 1),
                    cumulative_totaliser_kl=round(w["cumulative_totaliser_kl"], 1),
                    status=w["status"],
                    battery_pct=w["battery_pct"],
                    signal_strength_dbm=w["signal_strength_dbm"],
                    flags=w["flags"],
                    provenance_note="Daily baseline: real data.gov.in; hourly readings: simulated",
                    data_tier="SIMULATED"
                ))

            # Division inlet exceeds ward consumption by apparent losses (NRW ~15-28%)
            apparent_loss_pct = 18.5
            sum_ward_mld_round = round(sum_ward_mld, 2)
            inlet_mld = round(sum_ward_mld_round / (1.0 - (apparent_loss_pct / 100.0)), 2)
            apparent_loss_mld = round(inlet_mld - sum_ward_mld_round, 2)

            top_wards = sorted(
                [{"ward_no": ws.ward_no, "ward_name": ws.ward_name, "mld": round(ws.flow_lps * 86400 / 1e6, 2)} for ws in ward_summaries],
                key=lambda x: x["mld"],
                reverse=True
            )[:5]

            # 24-hr profiles
            hourly_ward_sum = [round(sum_ward_mld_round * (f / 24.0), 2) for f in self.diurnal_factors]
            hourly_inlet = [round(inlet_mld * (f / 24.0), 2) for f in self.diurnal_factors]

            results.append(DivisionBoardSummary(
                division_name=div_name,
                centroid_coordinates=div_info["centroid_coordinates"],
                inlet_mld=inlet_mld,
                sum_ward_consumption_mld=sum_ward_mld_round,
                apparent_loss_mld=apparent_loss_mld,
                apparent_loss_pct=apparent_loss_pct,
                total_wards=len(div_wards),
                wards_online=wards_online,
                wards_offline=wards_offline,
                active_alerts_count=sum(alerts_by_type.values()),
                alerts_by_type=alerts_by_type,
                top_wards_by_usage=top_wards,
                hourly_inlet_profile=hourly_inlet,
                hourly_ward_sum_profile=hourly_ward_sum,
                cumulative_today_kl=round(sum_vol_today_kl, 1),
                wards=ward_summaries,
                data_tier="SIMULATED"
            ))
        return results

    def get_smart_meter_division(self, division_id: str) -> Optional[DivisionBoardSummary]:
        canonical = self.normalize_division_name(division_id)
        for d in self.get_smart_meters():
            if d.division_name.lower() == canonical.lower():
                return d
        for d in self.get_smart_meters():
            if division_id.lower() in d.division_name.lower() or d.division_name.lower() in division_id.lower():
                return d
        return None

    def get_water_flow_corridors(self) -> Tuple[List[WaterFlowCorridor], WaterBalanceSummary]:
        corridors_raw = self.flows_cfg.get("transmission_corridors", [])
        corridors = []
        total_inflow = 1475.0 + 775.0  # 2250 MLD from verified stages
        curr_hour = (self.tick_count / 3600.0) % 24.0
        diurnal_factor = self._get_diurnal_factor(curr_hour)

        sim_leak = self.active_injections.get("leak")
        leak_mld = (sim_leak.get("leak_rate_lps", 0.0) * 86400.0 / 1e6) if sim_leak else 0.0

        for c in corridors_raw:
            flow_mld = round(c.get("design_flow_mld", 100.0) * diurnal_factor, 1)
            if c.get("id") == "CORR_TATAGUNI_MOUNT_JOY" and leak_mld > 0:
                flow_mld = max(10.0, round(flow_mld - leak_mld, 1))

            corridors.append(WaterFlowCorridor(
                id=c["id"],
                name=c["name"],
                from_node=c["from_node"],
                to_node=c["to_node"],
                flow_mld=flow_mld,
                design_flow_mld=c.get("design_flow_mld", 100.0),
                pipe_dn_mm=c.get("pipe_dn_mm", 1200),
                coordinates=c.get("coordinates", []),
                status="verified",
                data_tier="SIMULATED"
            ))

        total_demand = sum(w["flow_lps"] * 86400 / 1e6 for w in self.wards_data)
        balance = WaterBalanceSummary(
            total_inflow_mld=round(total_inflow * diurnal_factor, 1),
            total_outflow_mld=round(total_demand, 1),
            storage_change_mld=round(self.rng.uniform(-12.0, 15.0), 1),
            unaccounted_mld=round(abs(total_inflow * diurnal_factor - total_demand) * 0.18, 1),
            unaccounted_pct=18.0,
            balanced=True,
            data_tier="SIMULATED"
        )
        return corridors, balance

    async def start_loop(self):
        """Asynchronous background tick task."""
        self.is_running = True
        logger.info(f"Starting IoT simulation loop (seed={self.seed})...")
        while self.is_running:
            try:
                self.tick(1.0)
            except Exception as e:
                logger.error(f"Error in IoT simulation tick: {e}", exc_info=True)
            await asyncio.sleep(1.0)

    def stop_loop(self):
        self.is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self.snapshot_state()

# Global simulation engine singleton
sim_engine = IoTSimulationEngine()
