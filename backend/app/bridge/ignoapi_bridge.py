"""
Dedicated Read-Only Ingestion Bridge for IGNOAPI.
Strictly adheres to Rule 4:
- Reads variables only via TCP port 8899 {"action": "read_all", "name": "__all__"}
- Never sends write/command/delete commands unless allow_writes: true is explicitly configured in settings.
- Handles socket disconnection, timeout, and reconnection with exponential backoff.
- Tags every arrived measurement with data_tier: "LIVE".
- Validates physical range and staleness.
- Exposes true 12 V DC and 2 A DC auxiliary telemetry on "Pump control panel (auxiliary supply)" with LIVE chip.
- 6.6 kV pump channels, flow meters, and pressure sensors stay SIMULATED with Simulated chip.
- Exposes per-sensor feed health ("Updated Ns ago").
"""

import socket
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional
from pathlib import Path
import yaml
import math

from ..config import (
    IGNOAPI_HOST,
    IGNOAPI_PORT,
    IGNOAPI_ALLOW_WRITES,
    VARIABLES_YAML_PATH,
    SENSOR_MAP_PATH,
    PROJECT_ROOT
)

logger = logging.getLogger("ignoapi_bridge")

class IgnoApiReadOnlyBridge:
    def __init__(self, host: str = IGNOAPI_HOST, port: int = IGNOAPI_PORT):
        self.host = host
        self.port = port
        self.allow_writes = IGNOAPI_ALLOW_WRITES
        self.running = False
        self.connected = False
        self.last_packet_time = 0.0

        self.raw_telemetry: Dict[str, Any] = {}
        
        # Load sensor map and variables config
        self.sensor_map: Dict[str, Any] = {}
        self.variables_config: Dict[str, Any] = {}
        self._load_configs()

        # Cached sensor feed health: sensor_id -> feed health dict
        self.sensor_feed_health: Dict[str, Dict[str, Any]] = {}
        self.last_telemetry: Dict[str, Any] = {
            "speed": 360.0,
            "motor_temp_c": 70.0,
            "motor_current_a": 2.0,
            "voltage_v": 12.0,
            "alarmLM": 0,
            "switch_status": 0,
            "status": "DISCONNECTED",
            "data_tier": "SIMULATED",
            "last_packet_time": time.time()
        }
        self._evaluate_all_sensor_health()

    @property
    def is_connected(self) -> bool:
        return self.connected

    def send_command(self, action: str, *args, **kwargs):
        """Enforces read-only allowlist for bridge operations."""
        allowed_actions = {"read_all", "read_variable", "get_status"}
        if action not in allowed_actions or not self.allow_writes:
            raise PermissionError("Field control is intentionally unavailable. Passive read-only monitoring mode.")

    def write_variable(self, name: str, value: Any):
        """Strictly forbidden in passive read-only monitoring mode."""
        raise PermissionError("Field control is intentionally unavailable. Passive read-only monitoring mode.")

    def set_actuator(self, *args, **kwargs):
        """Strictly forbidden in passive read-only monitoring mode."""
        raise PermissionError("Field control is intentionally unavailable. Passive read-only monitoring mode.")

    def _load_configs(self):
        try:
            if SENSOR_MAP_PATH.exists():
                with open(SENSOR_MAP_PATH, "r", encoding="utf-8") as f:
                    self.sensor_map = yaml.safe_load(f) or {}
            if VARIABLES_YAML_PATH.exists():
                with open(VARIABLES_YAML_PATH, "r", encoding="utf-8") as f:
                    self.variables_config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading bridge configs: {e}")

    async def start(self):
        """Starts asynchronous bridge worker."""
        self.running = True
        logger.info(f"Starting IGNOAPI Read-Only Bridge to {self.host}:{self.port} (allow_writes={self.allow_writes})")
        asyncio.create_task(self._poll_loop())

    async def stop(self):
        self.running = False

    async def _poll_loop(self):
        backoff = 1.0
        while self.running:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect((self.host, self.port))
                self.connected = True
                backoff = 1.0
                logger.info(f"Connected to IGNOAPI at {self.host}:{self.port} (Strict Read-Only Mode)")

                while self.running:
                    # Strict Read-Only Request (Rule 4 Compliance)
                    req = {"action": "read_all", "name": "__all__"}
                    payload = json.dumps(req) + "\n"
                    sock.sendall(payload.encode("utf-8"))

                    # Read single response line
                    buf = ""
                    while "\n" not in buf:
                        chunk = sock.recv(4096).decode("utf-8")
                        if not chunk:
                            raise ConnectionResetError("IGNOAPI closed connection")
                        buf += chunk

                    line = buf.split("\n", 1)[0].strip()
                    if line:
                        resp = json.loads(line)
                        raw_vars = resp.get("value", resp.get("data", resp))
                        if isinstance(raw_vars, dict):
                            self._process_variables(raw_vars)

                    await asyncio.sleep(0.5)

            except Exception as e:
                self.connected = False
                # Try passive disk fallback if local vars.json exists
                if not self._read_passive_vars_file():
                    self._tick_live_fallback()
                await asyncio.sleep(min(backoff, 5.0))
                backoff = min(backoff * 1.5, 10.0)
            finally:
                if sock:
                    try:
                        sock.close()
                    except Exception:
                        pass

    def _read_passive_vars_file(self) -> bool:
        """Passive file fallback: reads vars.json read-only without modifying anything."""
        vars_file = PROJECT_ROOT / "ignoAPI" / "vars.json"
        if vars_file.exists():
            try:
                with open(vars_file, "r", encoding="utf-8") as f:
                    raw_vars = json.load(f)
                    if isinstance(raw_vars, dict):
                        self._process_variables(raw_vars, is_passive_file=True)
                        return True
            except Exception:
                pass
        return False

    def _process_variables(self, raw_vars: Dict[str, Any], is_passive_file: bool = False):
        now = time.time()
        self.last_packet_time = now
        self.raw_telemetry = raw_vars

        packet = {
            "speed": float(raw_vars.get("speed", 360.0)),
            "motor_temp_c": float(raw_vars.get("motor_temp_c", 70.0)),
            "motor_current_a": float(raw_vars.get("motor_current_a", 2.0)),
            "voltage_v": float(raw_vars.get("voltage_v", 12.0)),
            "alarmLM": int(raw_vars.get("alarmLM", 0)),
            "switch_status": int(raw_vars.get("switch_status", 0)),
            "status": "PASSIVE_FILE_SYNC" if is_passive_file else "CONNECTED_LIVE",
            "data_tier": "LIVE",
            "last_packet_time": now
        }
        self.last_telemetry = packet
        self._evaluate_all_sensor_health()

    def _tick_live_fallback(self):
        """Advances simulated fallback values when IGNOAPI is disconnected."""
        now = time.time()
        drift = math.sin(now / 5.0) * 0.2
        self.last_telemetry["speed"] = round(360.0 + drift * 5.0, 1)
        self.last_telemetry["motor_temp_c"] = round(70.0 + (drift / 2.0), 1)
        self.last_telemetry["motor_current_a"] = round(2.0 + (drift / 10.0), 2)
        self.last_telemetry["voltage_v"] = round(12.0 + (drift / 20.0), 2)
        self.last_telemetry["last_packet_time"] = now
        self.last_telemetry["status"] = "DISCONNECTED"
        self.last_telemetry["data_tier"] = "SIMULATED"
        self._evaluate_all_sensor_health()

    def _evaluate_all_sensor_health(self):
        """Evaluates health, range validation, and staleness for every mapped sensor."""
        now = time.time()
        packet_age = now - self.last_packet_time if self.last_packet_time > 0 else 999.0
        is_stale = packet_age > 3.0

        health_map: Dict[str, Dict[str, Any]] = {}

        # 1. PUMP CONTROL PANEL (AUXILIARY SUPPLY) - LIVE CHANNELS
        aux_panels = self.sensor_map.get("auxiliary_panels", [])
        for panel in aux_panels:
            pname = panel.get("name", "Pump control panel (auxiliary supply)")
            channels = panel.get("channels", {})
            for ch_key, ch_cfg in channels.items():
                cid = ch_cfg.get("channel_id", f"{panel.get('panel_id')}_{ch_key}")
                var_name = ch_cfg.get("ignoapi_variable")
                raw_val = self.raw_telemetry.get(var_name)
                # Live validation
                health_map[cid] = self._validate_sensor_value(
                    cid, 
                    ch_cfg, 
                    raw_val, 
                    packet_age, 
                    is_stale, 
                    asset_name=pname,
                    forced_tier="LIVE"
                )

        # 2. 6.6 kV PUMP MAIN MOTORS - SIMULATED CHANNELS
        pumps = self.sensor_map.get("pumps", [])
        for p in pumps:
            pid = p["pump_id"]
            pname = p.get("name", pid)
            channels = p.get("channels", {})
            for ch_name, ch_cfg in channels.items():
                cid = f"{pid}_{ch_name}"
                health_map[cid] = {
                    "sensor_id": cid,
                    "name": f"{pname} - {ch_cfg.get('label', ch_name)}",
                    "asset_name": pname,
                    "type": "PUMP_MAIN_MOTOR",
                    "feed_health": "FALLBACK_SIMULATED",
                    "data_tier": "SIMULATED",
                    "source_variable": None,
                    "value": None,
                    "unit": ch_cfg.get("unit", "-"),
                    "staleness_sec": round(packet_age, 1),
                    "updated_text": "Simulated Channel",
                    "reason": ch_cfg.get("notes", "6.6 kV motor channel operating in SIMULATED tier.")
                }

        # 3. FLOW METERS - SIMULATED CHANNELS
        flow_meters = self.sensor_map.get("flow_meters", [])
        for fm in flow_meters:
            sid = fm["sensor_id"]
            health_map[sid] = {
                "sensor_id": sid,
                "name": fm.get("name"),
                "asset_name": fm.get("name"),
                "type": "FLOW_METER",
                "feed_health": "FALLBACK_SIMULATED",
                "data_tier": "SIMULATED",
                "source_variable": None,
                "value": None,
                "unit": fm.get("unit", "LPS"),
                "staleness_sec": round(packet_age, 1),
                "updated_text": "Simulated Channel",
                "reason": "Variable not present in IGNOAPI. Operating in SIMULATED tier."
            }

        # 4. PRESSURE SENSORS - SIMULATED CHANNELS
        pressure_sensors = self.sensor_map.get("pressure_sensors", [])
        for ps in pressure_sensors:
            sid = ps["sensor_id"]
            health_map[sid] = {
                "sensor_id": sid,
                "name": ps.get("name"),
                "asset_name": ps.get("name"),
                "type": "PRESSURE_SENSOR",
                "feed_health": "FALLBACK_SIMULATED",
                "data_tier": "SIMULATED",
                "source_variable": None,
                "value": None,
                "unit": ps.get("unit", "bar"),
                "staleness_sec": round(packet_age, 1),
                "updated_text": "Simulated Channel",
                "reason": "Variable not present in IGNOAPI. Operating in SIMULATED tier."
            }

        self.sensor_feed_health = health_map

    def _validate_sensor_value(
        self,
        sensor_id: str,
        cfg: Dict[str, Any],
        raw_val: Any,
        packet_age: float,
        is_stale: bool,
        asset_name: str = "",
        forced_tier: str = "LIVE"
    ) -> Dict[str, Any]:
        """Validates range and staleness for a live mapped variable."""
        label = cfg.get("label", cfg.get("name", sensor_id))
        var_name = cfg.get("ignoapi_variable")
        unit = cfg.get("unit", "-")

        if raw_val is None:
            return {
                "sensor_id": sensor_id,
                "name": label,
                "asset_name": asset_name,
                "type": "AUXILIARY_LIVE_CHANNEL",
                "feed_health": "FALLBACK_SIMULATED",
                "data_tier": "SIMULATED",
                "source_variable": var_name,
                "value": None,
                "unit": unit,
                "staleness_sec": round(packet_age, 1),
                "updated_text": f"Offline ({round(packet_age, 1)}s)",
                "reason": f"Variable '{var_name}' currently missing from stream."
            }

        try:
            val = float(raw_val)
        except (ValueError, TypeError):
            val = raw_val

        # Range check
        v_range = cfg.get("valid_range", {})
        v_min = v_range.get("min")
        v_max = v_range.get("max")
        out_of_bounds = False
        if isinstance(val, (int, float)):
            if v_min is not None and val < v_min:
                out_of_bounds = True
            if v_max is not None and val > v_max:
                out_of_bounds = True

        scale = cfg.get("scale_factor", 1.0)
        offset = cfg.get("offset", 0.0)
        scaled_val = (val * scale + offset) if isinstance(val, (int, float)) else val

        if out_of_bounds:
            feed_health = "OUT_OF_BOUNDS"
            data_tier = "SIMULATED"
            reason = f"Telemetry value {val} out of valid range [{v_min}, {v_max}]. Dropped to SIMULATED."
            updated_text = f"Out of bounds ({round(packet_age, 1)}s ago)"
        elif is_stale:
            feed_health = "STALE_LIVE"
            data_tier = forced_tier
            reason = f"Telemetry packet is {round(packet_age, 1)}s old (> 3.0s threshold)."
            updated_text = f"Updated {round(packet_age, 1)}s ago (Stale)"
        else:
            feed_health = "HEALTHY_LIVE"
            data_tier = forced_tier
            reason = f"Live telemetry arriving nominal from IGNOAPI ({var_name})."
            updated_text = f"Updated {round(packet_age, 1)}s ago"

        return {
            "sensor_id": sensor_id,
            "name": label,
            "asset_name": asset_name,
            "type": "AUXILIARY_LIVE_CHANNEL",
            "feed_health": feed_health,
            "data_tier": data_tier,
            "source_variable": var_name,
            "raw_value": val,
            "value": round(scaled_val, 2) if isinstance(scaled_val, float) else scaled_val,
            "unit": unit,
            "staleness_sec": round(packet_age, 1),
            "updated_text": updated_text,
            "reason": reason
        }

    def get_latest_telemetry(self) -> Dict[str, Any]:
        return self.last_telemetry

    def get_sensor_feed_health(self) -> Dict[str, Any]:
        """Returns feed health breakdown for every sensor."""
        healthy_count = sum(1 for h in self.sensor_feed_health.values() if h["feed_health"] == "HEALTHY_LIVE")
        stale_count = sum(1 for h in self.sensor_feed_health.values() if h["feed_health"] == "STALE_LIVE")
        simulated_count = sum(1 for h in self.sensor_feed_health.values() if h["feed_health"] == "FALLBACK_SIMULATED")
        out_of_bounds_count = sum(1 for h in self.sensor_feed_health.values() if h["feed_health"] == "OUT_OF_BOUNDS")

        return {
            "bridge_connected": self.connected,
            "packet_age_seconds": round(time.time() - self.last_packet_time, 1) if self.last_packet_time > 0 else None,
            "summary": {
                "total_sensors": len(self.sensor_feed_health),
                "healthy_live": healthy_count,
                "stale_live": stale_count,
                "simulated_fallback": simulated_count,
                "out_of_bounds": out_of_bounds_count
            },
            "sensors": self.sensor_feed_health
        }

bridge = IgnoApiReadOnlyBridge()
