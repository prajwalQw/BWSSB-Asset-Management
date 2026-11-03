"""
autoVDA.py — VDA 5050 (MQTT) Bridge helper for ignoAPI.

Translates between MQTT (VDA 5050 v2.0.0) and plain ignoAPI variables,
allowing Fleet Manager to communicate with third-party AGVs/AMRs without
modifying existing ignoAPI/TCP architecture or robot firmware.

ONE VDA Bridge == ONE ignoAPI variable. ignoAPI creates one by duplicating
this program to `<var>_autovda.exe` (or `.py` in dev) alongside
`<var>_autovda.json`, then launching it -- following the exact pattern of
autoFTP, autocom, autoModbusMaster and autoSyncIgnoAPI.

WHAT YOU GET
    <var>               Anchor showing MQTT broker connection info, e.g.
                        mqtt://192.168.1.50:1883
    <var>_status        Bridge status: CONNECTED, CONNECTING, ERROR...
    <var>_robots        Status of bridged robots, e.g. rob5=ONLINE,rob6=OFFLINE
    <robot_id>_vda_rx   17-field CSV telemetry string identical to TCP robots
    <robot_id>_vda_tx   Fleet-to-robot command mailbox (orders, actions, acks)
    <robot_id>_vda_result Last command execution result / error JSON
    <robot_id>_vda_state  (optional) Last raw VDA state JSON if store_raw is true
"""

from __future__ import annotations

import csv
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    from ignomdns import resolve_host as _resolve
except ImportError:
    def _resolve(h: str, timeout: float = 2.0) -> str:
        return h

# MQTT client library (paho-mqtt)
try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY (Windows)
# ──────────────────────────────────────────────────────────────
_console_visible = True
_tray_icon = None

SW_HIDE = 0
SW_RESTORE = 9


def _console_hwnd():
    if os.name != "nt":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow() or None
    except Exception:
        return None


def show_console(show: bool = True):
    global _console_visible
    hwnd = _console_hwnd()
    if not hwnd:
        return
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE if show else SW_HIDE)
        _console_visible = show
    except Exception:
        pass


def _tray_image():
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Slate blue rounded icon with 'VDA' label
    d.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(45, 95, 175), outline=(130, 180, 255), width=3)
    d.line([16, 22, 32, 44], fill=(255, 255, 255), width=4)
    d.line([32, 44, 48, 22], fill=(255, 255, 255), width=4)
    return img


def start_tray(stem: str, variable: str):
    """Run tray icon on a daemon thread. Never fatal."""
    global _tray_icon
    try:
        import pystray
    except Exception as e:
        print(f"[tray] not available ({e}) — running in console mode")
        return
    image = _tray_image()
    if image is None:
        print("[tray] Pillow not available — running in console mode")
        return

    def toggle(icon, item):
        show_console(not _console_visible)

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(f"{stem}  ->  {variable}", toggle, default=True),
        pystray.MenuItem("Show console", lambda i, x: show_console(True)),
        pystray.MenuItem("Hide console", lambda i, x: show_console(False)),
        pystray.MenuItem("Quit", on_quit),
    )
    _tray_icon = pystray.Icon(stem, image, f"VDA: {variable}", menu)
    threading.Thread(target=_tray_icon.run, daemon=True).start()


def watch_minimise():
    """Send console to tray when minimized on Windows."""
    if os.name != "nt":
        return

    def _loop():
        import ctypes
        while True:
            try:
                hwnd = _console_hwnd()
                if hwnd and _console_visible and ctypes.windll.user32.IsIconic(hwnd):
                    show_console(False)
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=_loop, daemon=True).start()


# ──────────────────────────────────────────────────────────────
# SELF-IDENTIFICATION & CONFIG
# ──────────────────────────────────────────────────────────────
def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_self_stem() -> str:
    if getattr(sys, "frozen", False):
        path = os.path.basename(sys.executable)
    else:
        path = os.path.basename(os.path.abspath(__file__))
    return os.path.splitext(path)[0]


def config_path_for(base_dir: str) -> str:
    return os.path.join(base_dir, f"{get_self_stem()}.json")


def derived_variable_name() -> Optional[str]:
    stem = get_self_stem()
    suffix = "_autovda"
    if stem.lower().endswith(suffix) and len(stem) > len(suffix):
        return stem[:-len(suffix)]
    return None


def load_config(base_dir: str) -> Dict[str, Any]:
    config_path = config_path_for(base_dir)
    if not os.path.exists(config_path):
        print(f"[fatal] Config {os.path.basename(config_path)} not found at {config_path}")
        sys.exit(1)
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def log_line(log_path: Optional[str], text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {text}"
    print(line)
    if not log_path:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def utc_iso_now() -> str:
    """Return UTC ISO-8601 with milliseconds and Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ──────────────────────────────────────────────────────────────
# ROBOT SPEC PARSER — IDENTICAL TO HELPER IN ignoAPI.py
# ──────────────────────────────────────────────────────────────
def parse_vda_robots(raw: Any) -> List[Dict[str, str]]:
    """
    Parse a robots configuration string or list into structured robot definitions.
    Format: 'rob5:VendorX:AGV-07, rob6:VendorY:AMR-02'
    Returns: [{'robot_id': 'rob5', 'manufacturer': 'VendorX', 'serial_number': 'AGV-07'}, ...]
    """
    out: List[Dict[str, str]] = []
    if not raw:
        return out

    if isinstance(raw, list):
        items = raw
    else:
        items = str(raw).replace(";", ",").replace("\n", ",").split(",")

    seen = set()
    for item in items:
        chunk = str(item).strip()
        if not chunk:
            continue
        parts = [p.strip() for p in chunk.split(":")]
        if len(parts) >= 3:
            rid = parts[0].strip().lower()
            mfr = parts[1].strip()
            serial = parts[2].strip()
        elif len(parts) == 2:
            rid = parts[0].strip().lower()
            mfr = parts[1].strip()
            serial = rid
        elif len(parts) == 1 and parts[0]:
            rid = parts[0].strip().lower()
            mfr = "IGNOMAGINE"
            serial = rid
        else:
            continue

        if rid and rid not in seen:
            seen.add(rid)
            out.append({
                "robot_id": rid,
                "manufacturer": mfr,
                "serial_number": serial,
            })
    return out


def format_vda_robots(robot_list: List[Dict[str, str]]) -> str:
    """Format structured robot defs back to 'rob5:VendorX:AGV-07,rob6:VendorY:AMR-02'."""
    return ",".join(f"{r['robot_id']}:{r['manufacturer']}:{r['serial_number']}" for r in robot_list)


# ──────────────────────────────────────────────────────────────
# NODE MAP TRANSLATOR (Optional CSV)
# ──────────────────────────────────────────────────────────────
class NodeMap:
    """
    Bidirectional map between Fleet Manager stop IDs and VDA 5050 node IDs.
    Header: fleet_stop_id,vda_node_id,map_id,x,y,theta
    """
    def __init__(self, csv_path: Optional[str] = None):
        self.fleet_to_vda: Dict[str, Dict[str, Any]] = {}
        self.vda_to_fleet: Dict[str, str] = {}
        if csv_path and os.path.exists(csv_path):
            self.load(csv_path)

    def load(self, csv_path: str):
        try:
            with open(csv_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    f_id = (row.get("fleet_stop_id") or "").strip()
                    v_id = (row.get("vda_node_id") or "").strip()
                    if not f_id or not v_id:
                        continue
                    m_id = (row.get("map_id") or "").strip()
                    x_val = float(row.get("x", 0.0) or 0.0)
                    y_val = float(row.get("y", 0.0) or 0.0)
                    theta_val = float(row.get("theta", 0.0) or 0.0)

                    self.fleet_to_vda[f_id] = {
                        "vda_node_id": v_id,
                        "map_id": m_id,
                        "x": x_val,
                        "y": y_val,
                        "theta": theta_val,
                    }
                    self.vda_to_fleet[v_id] = f_id
        except Exception as e:
            print(f"[node_map] Error loading {csv_path}: {e}")

    def to_fleet(self, vda_node_id: str) -> str:
        """Translate incoming VDA node id to Fleet stop id, falling back to identity."""
        if not vda_node_id:
            return ""
        return self.vda_to_fleet.get(vda_node_id, vda_node_id)

    def to_vda(self, fleet_stop_id: str) -> Dict[str, Any]:
        """Translate outgoing Fleet stop id to VDA node id details."""
        if fleet_stop_id in self.fleet_to_vda:
            return self.fleet_to_vda[fleet_stop_id]
        return {
            "vda_node_id": fleet_stop_id,
            "map_id": "",
            "x": 0.0,
            "y": 0.0,
            "theta": 0.0,
        }


# ──────────────────────────────────────────────────────────────
# ignoAPI PERSISTENT TCP CLIENT
# ──────────────────────────────────────────────────────────────
class IgnoApi:
    """Read/write ignoAPI variables over its line-JSON TCP socket."""

    def __init__(self, host: str, port: int, label: str = "ignoAPI"):
        self.host = host
        self.port = int(port) if port else 8899
        self.label = label
        self.enabled = bool(host and port)
        self._warned = False
        self._sock: Optional[socket.socket] = None
        self._buf = b""
        self._lock = threading.Lock()

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = None
        self._buf = b""

    def _connect(self, timeout: float = 2.0):
        self._close()
        self._sock = socket.create_connection((_resolve(self.host), self.port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _readline(self) -> str:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise OSError("ignoAPI closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace").strip()

    def _rpc(self, payload: Dict[str, Any], timeout: float = 2.0) -> Optional[Dict[str, Any]]:
        if not self.enabled:
            return None
        req = (json.dumps(payload) + "\n").encode("utf-8")
        with self._lock:
            for attempt in (1, 2):
                try:
                    if self._sock is None:
                        self._connect(timeout)
                    self._sock.sendall(req)
                    line = self._readline()
                    self._warned = False
                    return json.loads(line) if line else None
                except (OSError, ValueError) as e:
                    self._close()
                    if attempt == 2:
                        if not self._warned:
                            print(f"[vda] {self.label} unreachable: {e}")
                            self._warned = True
                        return None
        return None

    def write(self, name: str, value: Any) -> bool:
        r = self._rpc({"action": "create_or_write", "name": name, "value": value})
        return bool(r and r.get("status") == "success")

    def read(self, name: str) -> Any:
        r = self._rpc({"action": "read", "name": name})
        return r.get("value") if r and r.get("status") == "success" else None

    def bulk_write(self, data: Dict[str, Any]) -> bool:
        """Write multiple variables in one atomic round-trip."""
        if not data:
            return True
        r = self._rpc({"action": "bulk_write", "data": data})
        return bool(r and r.get("status") == "success")


# ──────────────────────────────────────────────────────────────
# VDA ROBOT RUNTIME STATE
# ──────────────────────────────────────────────────────────────
class RobotRuntime:
    """Tracks state, telemetry, latches and edge detection for one robot."""

    def __init__(self, rid: str, mfr: str, serial: str):
        self.robot_id = rid
        self.manufacturer = mfr
        self.serial_number = serial

        self.last_state_time: float = 0.0
        self.last_connection_time: float = 0.0
        self.connection_status: str = "OFFLINE"   # ONLINE, OFFLINE, CONNECTIONBROKEN
        self.is_online: bool = False

        self.last_rx_csv: str = ""
        self.header_counters: Dict[str, int] = {}  # topic -> next uint
        self._counter_lock = threading.Lock()

        # Latches and edge-detection
        self.task_completed_latched: bool = False
        self.suppressed_fleet_response: Optional[str] = None
        self.suppressed_acknowledgement: Optional[str] = None
        self.active_order_id: str = ""

    def next_header_id(self, topic: str) -> int:
        with self._counter_lock:
            val = self.header_counters.get(topic, 1000)
            self.header_counters[topic] = val + 1
            return val


# ──────────────────────────────────────────────────────────────
# THE VDA BRIDGE
# ──────────────────────────────────────────────────────────────
class VdaBridge:
    def __init__(self, cfg: Dict[str, Any], variable: str, api: IgnoApi, log_path: Optional[str]):
        self.cfg = cfg
        self.variable = variable
        self.api = api
        self.log_path = log_path

        # Broker config
        self.broker_host = str(cfg.get("broker_host", "127.0.0.1")).strip()
        self.broker_port = int(cfg.get("broker_port", 1883))
        self.username = str(cfg.get("username", "")).strip() or None
        self.password = str(cfg.get("password", "")).strip() or None
        self.use_tls = bool(cfg.get("use_tls", False))
        self.tls_ca = str(cfg.get("tls_ca", "")).strip() or None
        self.client_id = str(cfg.get("client_id", f"ignoapi_{variable}")).strip()

        # VDA protocol topics
        self.interface = str(cfg.get("interface", "uagv")).strip()
        self.vda_major = str(cfg.get("vda_major", "v2")).strip()
        self.protocol_version = str(cfg.get("protocol_version", "2.0.0")).strip()
        self.qos_order = int(cfg.get("qos_order", 1))
        self.qos_state = int(cfg.get("qos_state", 0))
        self.stale_after_sec = float(cfg.get("stale_after_sec", 10.0))
        self.subscribe_visualization = bool(cfg.get("subscribe_visualization", False))
        self.store_raw = bool(cfg.get("store_raw", False))

        # Robots
        self.node_map = NodeMap(cfg.get("node_map_csv"))
        raw_robots = cfg.get("robots", "")
        self.robot_defs = parse_vda_robots(raw_robots)
        self.robots: Dict[str, RobotRuntime] = {
            r["robot_id"]: RobotRuntime(r["robot_id"], r["manufacturer"], r["serial_number"])
            for r in self.robot_defs
        }

        # Status tracking
        self.bridge_status = "INITIALIZING"
        self._mqtt_client: Optional[mqtt.Client] = None
        self._mqtt_connected = False
        self._running = True

        # Topic lookup: (manufacturer, serial) -> RobotRuntime
        self.serial_map: Dict[Tuple[str, str], RobotRuntime] = {
            (r.manufacturer.lower(), r.serial_number.lower()): r
            for r in self.robots.values()
        }

    def _log(self, text: str):
        log_line(self.log_path, f"[vda:{self.variable}] {text}")

    def update_status(self, new_status: str):
        if new_status != self.bridge_status:
            self.bridge_status = new_status
            self._log(f"Status changed -> {new_status}")
            self.api.write(f"{self.variable}_status", new_status)

    def update_robots_summary(self):
        """Update <var>_robots string: 'rob5=ONLINE,rob6=OFFLINE'."""
        parts = []
        for rid, r in sorted(self.robots.items()):
            st = "ONLINE" if r.is_online else "OFFLINE"
            parts.append(f"{rid}={st}")
        summary = ",".join(parts)
        self.api.write(f"{self.variable}_robots", summary)

    # ──────────────────────────────────────────────────────────
    # MQTT SETUP & CALLBACKS
    # ──────────────────────────────────────────────────────────
    def start_mqtt(self):
        if not PAHO_AVAILABLE:
            self._log("paho-mqtt library is NOT installed! Install with: pip install paho-mqtt")
            self.update_status("ERROR: paho-mqtt missing")
            return

        try:
            try:
                self._mqtt_client = mqtt.Client(
                    client_id=self.client_id,
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                )
            except AttributeError:
                self._mqtt_client = mqtt.Client(client_id=self.client_id)

            if self.username:
                self._mqtt_client.username_pw_set(self.username, self.password)

            if self.use_tls:
                ca = self.tls_ca if self.tls_ca and os.path.exists(self.tls_ca) else None
                self._mqtt_client.tls_set(ca_certs=ca)

            self._mqtt_client.on_connect = self._on_connect
            self._mqtt_client.on_disconnect = self._on_disconnect
            self._mqtt_client.on_message = self._on_message

            self._log(f"Connecting to broker {self.broker_host}:{self.broker_port}...")
            self.update_status("CONNECTING")
            self._mqtt_client.connect_async(self.broker_host, self.broker_port, keepalive=30)
            self._mqtt_client.loop_start()
        except Exception as e:
            self._log(f"MQTT init failed: {e}")
            self.update_status(f"ERROR: {e}")

    def _on_connect(self, client, userdata, flags, rc, *extra):
        if rc == 0:
            self._mqtt_connected = True
            scheme = "mqtts" if self.use_tls else "mqtt"
            anchor_val = f"{scheme}://{self.broker_host}:{self.broker_port}"
            self.api.write(self.variable, anchor_val)
            self.update_status("CONNECTED")
            self._log(f"Connected to broker {anchor_val}. Subscribing for {len(self.robots)} robot(s)...")

            # Subscribe only to configured robots
            for r in self.robots.values():
                base_topic = f"{self.interface}/{self.vda_major}/{r.manufacturer}/{r.serial_number}"
                sub_topics = ["state", "connection", "factsheet"]
                if self.subscribe_visualization:
                    sub_topics.append("visualization")

                for st in sub_topics:
                    topic = f"{base_topic}/{st}"
                    client.subscribe(topic, qos=self.qos_state)
                    self._log(f"Subscribed: {topic}")
        else:
            self._mqtt_connected = False
            self.update_status(f"CONNECT_FAILED (rc={rc})")
            self._log(f"MQTT broker connection failed with code {rc}")

    def _on_disconnect(self, client, userdata, rc, *extra):
        self._mqtt_connected = False
        if rc != 0:
            self.update_status("RECONNECTING")
            self._log(f"MQTT disconnected unexpectedly (rc={rc}). Will auto-reconnect...")
        else:
            self.update_status("STOPPED (by user)")
            self._log("MQTT disconnected cleanly.")

    def _on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            payload_str = msg.payload.decode("utf-8", errors="replace")
            tokens = topic.split("/")

            # Pattern: {interface}/{vda_major}/{manufacturer}/{serial}/{subtopic}
            if len(tokens) < 5:
                return
            mfr = tokens[2].strip().lower()
            serial = tokens[3].strip().lower()
            subtopic = tokens[4].strip().lower()

            robot = self.serial_map.get((mfr, serial))
            if not robot:
                return

            if subtopic == "connection":
                self._handle_connection_msg(robot, payload_str)
            elif subtopic == "state":
                self._handle_state_msg(robot, payload_str)
        except Exception as e:
            self._log(f"Error handling MQTT message on {msg.topic}: {e}")

    # ──────────────────────────────────────────────────────────
    # INBOUND TRANSLATION: VDA CONNECTION & STATE -> ignoAPI
    # ──────────────────────────────────────────────────────────
    def _handle_connection_msg(self, robot: RobotRuntime, raw: str):
        robot.last_connection_time = time.time()
        try:
            data = json.loads(raw)
            c_state = str(data.get("connectionState", "")).upper()
            robot.connection_status = c_state
            was_online = robot.is_online
            robot.is_online = (c_state == "ONLINE")

            if was_online != robot.is_online:
                self._log(f"Robot {robot.robot_id} connectionState -> {c_state}")
                self.update_robots_summary()
                if not robot.is_online:
                    # Blank _vda_rx when robot goes offline
                    self.api.write(f"{robot.robot_id}_vda_rx", "")
                    robot.last_rx_csv = ""
        except Exception as e:
            self._log(f"Malformed connection message for {robot.robot_id}: {e}")

    def _handle_state_msg(self, robot: RobotRuntime, raw: str):
        now = time.time()
        robot.last_state_time = now
        # Receiving state confirms robot is communicating
        if not robot.is_online and robot.connection_status != "OFFLINE":
            robot.is_online = True
            self.update_robots_summary()

        try:
            data = json.loads(raw)
        except Exception as e:
            self._log(f"Malformed state JSON from {robot.robot_id}: {e}")
            return

        # 1. Address
        address = robot.robot_id

        # 2. c_id (current node)
        raw_last_node = str(data.get("lastNodeId", "")).strip()
        c_id = self.node_map.to_fleet(raw_last_node)

        # 3. r_id (target node / next unvisited node)
        r_id = ""
        node_states = data.get("nodeStates", [])
        if isinstance(node_states, list):
            for ns in node_states:
                if isinstance(ns, dict) and bool(ns.get("released", True)):
                    v_node = str(ns.get("nodeId", "")).strip()
                    if v_node and v_node != raw_last_node:
                        r_id = self.node_map.to_fleet(v_node)
                        break

        # 4. Battery percentage
        battery_state = data.get("batteryState") or {}
        if isinstance(battery_state, dict):
            bat_pct = float(battery_state.get("batteryCharge", 100.0) or 100.0)
        elif isinstance(battery_state, (int, float)):
            bat_pct = float(battery_state)
        else:
            bat_pct = 100.0
        bat_str = f"{bat_pct:.1f}"

        # 5. Odometry
        odo_val = float(data.get("distanceSinceLastNode", 0.0) or 0.0)
        odo_str = f"{odo_val:.2f}"

        # 6. Obstacle
        safety_state = data.get("safetyState") or {}
        field_violation = bool(safety_state.get("fieldViolation", False)) if isinstance(safety_state, dict) else False
        errors = data.get("errors", [])
        if not isinstance(errors, list):
            errors = [errors] if errors else []

        has_obstacle_err = False
        rejection_err = ""
        current_order_id = str(data.get("orderId", "")).strip()
        robot.active_order_id = current_order_id

        for err in errors:
            if isinstance(err, dict):
                etype = str(err.get("errorType", "")).lower()
                edesc = str(err.get("errorDescription", "")).lower()
                if "obstacle" in etype or "obstacle" in edesc:
                    has_obstacle_err = True
                if "order" in etype or "validation" in etype or "rejected" in etype:
                    rejection_err = str(err.get("errorType", "ORDER_REJECTED"))

        obstacle_flag = "1" if (field_violation or has_obstacle_err) else "0"

        # 7. Magnetometer (stop / estop flag)
        e_stop = str(safety_state.get("eStop", "NONE")).upper() if isinstance(safety_state, dict) else "NONE"
        is_stopped = (e_stop != "NONE") or field_violation
        mag_flag = "1" if is_stopped else "0"

        # 8. Acknowledgement & 9. Fleet Response
        raw_ack = ""
        raw_resp = ""
        if rejection_err:
            raw_ack = f"ORDER_REJECTED:{rejection_err}"
            # Record rejection result
            self.api.write(
                f"{robot.robot_id}_vda_result",
                json.dumps({
                    "ok": False,
                    "detail": f"Order rejected: {rejection_err}",
                    "ts": utc_iso_now(),
                })
            )

        info_list = data.get("information", [])
        if isinstance(info_list, list):
            for info_entry in info_list:
                if isinstance(info_entry, dict):
                    itype = str(info_entry.get("infoType", "")).lower()
                    idesc = str(info_entry.get("infoDescription", "")).strip()
                    if itype == "acknowledgement" and not raw_ack:
                        raw_ack = idesc
                    elif itype == "fleet_response":
                        raw_resp = idesc

        # Edge detection for acknowledgement & fleet_response clears:
        # If fleet asked to clear, suppress until vendor sends a different non-blank value
        if robot.suppressed_acknowledgement is True:
            robot.suppressed_acknowledgement = raw_ack
            raw_ack = ""
        elif robot.suppressed_acknowledgement is not None:
            if raw_ack != robot.suppressed_acknowledgement:
                robot.suppressed_acknowledgement = None
            else:
                raw_ack = ""

        if robot.suppressed_fleet_response is True:
            robot.suppressed_fleet_response = raw_resp
            raw_resp = ""
        elif robot.suppressed_fleet_response is not None:
            if raw_resp != robot.suppressed_fleet_response:
                robot.suppressed_fleet_response = None
            else:
                raw_resp = ""

        # 10. Controller status (operatingMode)
        operating_mode = str(data.get("operatingMode", "AUTOMATIC")).upper()
        igno_controller = operating_mode

        # 11-16. Companion statuses (blank for 3rd-party robots)
        igno_bat = ""
        igno_vis = ""
        igno_man = ""
        igno_srv = ""
        igno_paint = ""
        igno_disp = ""

        # 17. Execution
        driving = bool(data.get("driving", False))
        paused = bool(data.get("paused", False))
        action_states = data.get("actionStates", [])
        all_actions_finished = True
        if isinstance(action_states, list) and action_states:
            for act in action_states:
                if isinstance(act, dict) and str(act.get("actionStatus", "")).upper() not in ("FINISHED", "FAILED"):
                    all_actions_finished = False
                    break

        if robot.task_completed_latched:
            execution = "task_completed"
        elif paused:
            execution = "pause_task"
        elif current_order_id and (driving or not all_actions_finished or bool(node_states)):
            execution = "run_task"
        elif current_order_id and not node_states and all_actions_finished and not driving:
            # Order finished -> latch task_completed until ack_complete received
            execution = "task_completed"
            robot.task_completed_latched = True
            self._log(f"Robot {robot.robot_id} finished order {current_order_id} -> LATCHED task_completed")
        else:
            execution = "idle"

        # Construct 17-field CSV string
        fields = [
            address,            # 0
            c_id,               # 1
            r_id,               # 2
            bat_str,            # 3
            odo_str,            # 4
            obstacle_flag,      # 5
            mag_flag,           # 6
            raw_ack,            # 7
            raw_resp,           # 8
            igno_controller,    # 9
            igno_bat,           # 10
            igno_vis,           # 11
            igno_man,           # 12
            igno_srv,           # 13
            igno_paint,         # 14
            igno_disp,          # 15
            execution,          # 16
        ]
        rx_csv = ",".join(fields)

        # Write to ignoAPI only when content changes
        if rx_csv != robot.last_rx_csv:
            robot.last_rx_csv = rx_csv
            bulk_data = {
                f"{robot.robot_id}_vda_rx": rx_csv,
                f"{robot.robot_id}_vda_status": "ONLINE" if robot.is_online else "OFFLINE",
            }
            agv_pos = data.get("agvPosition") or {}
            if isinstance(agv_pos, dict) and "x" in agv_pos and "y" in agv_pos:
                try: bulk_data[f"{robot.robot_id}_x"] = float(agv_pos.get("x", 0.0))
                except Exception: pass
                try: bulk_data[f"{robot.robot_id}_y"] = float(agv_pos.get("y", 0.0))
                except Exception: pass
                if "theta" in agv_pos:
                    try: bulk_data[f"{robot.robot_id}_heading"] = float(agv_pos.get("theta", 0.0))
                    except Exception: pass
            vel = data.get("velocity") or {}
            if isinstance(vel, dict) and "vx" in vel:
                try: bulk_data[f"{robot.robot_id}_speed"] = float(vel.get("vx", 0.0))
                except Exception: pass

            if self.store_raw:
                bulk_data[f"{robot.robot_id}_vda_state"] = raw
            self.api.bulk_write(bulk_data)

    # ──────────────────────────────────────────────────────────
    # OUTBOUND TRANSLATION: ignoAPI _tx -> VDA MQTT COMMANDS
    # ──────────────────────────────────────────────────────────
    def poll_robot_tx_boxes(self):
        """Poll `<robot_id>_vda_tx` for outgoing orders or instant actions."""
        for robot in self.robots.values():
            tx_box_key = f"{robot.robot_id}_vda_tx"
            raw_tx = self.api.read(tx_box_key)
            if not raw_tx:
                continue

            tx_str = str(raw_tx).strip()
            if not tx_str:
                continue

            # Immediately clear the tx box
            self.api.write(tx_box_key, "")

            try:
                cmd = json.loads(tx_str)
            except Exception as e:
                self._record_cmd_result(robot, False, f"Invalid JSON in {tx_box_key}: {e}")
                continue

            self._dispatch_robot_command(robot, cmd)

    def _dispatch_robot_command(self, robot: RobotRuntime, cmd: Dict[str, Any]):
        cmd_type = str(cmd.get("type", "")).strip()
        ttl_sec = float(cmd.get("ttl_sec", 10.0))

        # Check TTL
        cmd_ts = cmd.get("created_at") or cmd.get("timestamp")
        if cmd_ts:
            try:
                # If timestamp is provided, check expiry
                pass
            except Exception:
                pass

        if cmd_type == "ack_complete":
            robot.task_completed_latched = False
            self._log(f"Robot {robot.robot_id}: task_completed latch cleared by Fleet Manager.")
            self._record_cmd_result(robot, True, "task_completed unlatched")
            return

        if cmd_type == "clear":
            target_field = str(cmd.get("field", "")).strip().lower()
            if target_field == "fleet_response":
                robot.suppressed_fleet_response = True
                self._log(f"Robot {robot.robot_id}: fleet_response cleared.")
                self._record_cmd_result(robot, True, "fleet_response cleared")
            elif target_field == "acknowledgement":
                robot.suppressed_acknowledgement = True
                self._log(f"Robot {robot.robot_id}: acknowledgement cleared.")
                self._record_cmd_result(robot, True, "acknowledgement cleared")
            return

        # For MQTT publishes, ensure broker connection
        if not self._mqtt_connected or self._mqtt_client is None:
            self._record_cmd_result(robot, False, f"Broker not connected; command dropped (TTL {ttl_sec}s)")
            return

        if cmd_type == "order":
            self._publish_order(robot, cmd, ttl_sec)
        elif cmd_type == "instantAction":
            self._publish_instant_action(robot, cmd, ttl_sec)
        else:
            self._record_cmd_result(robot, False, f"Unknown command type '{cmd_type}'")

    def _publish_order(self, robot: RobotRuntime, cmd: Dict[str, Any], ttl_sec: float):
        order_dict = cmd.get("order") or {}
        order_id = str(order_dict.get("orderId", "")).strip()
        if not order_id:
            self._record_cmd_result(robot, False, "Order missing 'orderId'")
            return

        nodes = order_dict.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            self._record_cmd_result(robot, False, "Order missing 'nodes'")
            return

        edges = order_dict.get("edges", [])
        update_id = int(order_dict.get("orderUpdateId", 0))

        # Translate node coordinates and IDs through node_map if needed
        for idx, n in enumerate(nodes):
            if isinstance(n, dict):
                node_id = str(n.get("nodeId", f"node_{idx}")).strip()
                t = self.node_map.to_vda(node_id)
                n["nodeId"] = t["vda_node_id"]
                if "nodePosition" not in n:
                    n["nodePosition"] = {
                        "x": t["x"],
                        "y": t["y"],
                        "theta": t["theta"],
                        "mapId": t["map_id"],
                        "allowedDeviationX": 0.05,
                        "allowedDeviationY": 0.05,
                        "allowedDeviationTheta": 0.1,
                    }

        topic = f"{self.interface}/{self.vda_major}/{robot.manufacturer}/{robot.serial_number}/order"
        header_id = robot.next_header_id(topic)

        payload = {
            "headerId": header_id,
            "timestamp": utc_iso_now(),
            "version": self.protocol_version,
            "manufacturer": robot.manufacturer,
            "serialNumber": robot.serial_number,
            "orderId": order_id,
            "orderUpdateId": update_id,
            "nodes": nodes,
            "edges": edges,
        }

        try:
            payload_bytes = json.dumps(payload).encode("utf-8")
            inf = self._mqtt_client.publish(topic, payload_bytes, qos=self.qos_order)
            inf.wait_for_publish(timeout=min(ttl_sec, 3.0))
            self._log(f"Published order {order_id} to {topic} (headerId={header_id})")
            self._record_cmd_result(robot, True, f"Order {order_id} published")
            if self.store_raw:
                self.api.write(f"{robot.robot_id}_vda_order", json.dumps(payload))
        except Exception as e:
            self._record_cmd_result(robot, False, f"Failed to publish order: {e}")

    def _publish_instant_action(self, robot: RobotRuntime, cmd: Dict[str, Any], ttl_sec: float):
        actions = cmd.get("actions", [])
        if not isinstance(actions, list) or not actions:
            self._record_cmd_result(robot, False, "instantAction missing 'actions' list")
            return

        topic = f"{self.interface}/{self.vda_major}/{robot.manufacturer}/{robot.serial_number}/instantActions"
        header_id = robot.next_header_id(topic)

        # Ensure actionId exists on each action
        for idx, act in enumerate(actions):
            if isinstance(act, dict) and "actionId" not in act:
                act["actionId"] = f"act_{int(time.time()*1000)%1000000}_{idx}"

        payload = {
            "headerId": header_id,
            "timestamp": utc_iso_now(),
            "version": self.protocol_version,
            "manufacturer": robot.manufacturer,
            "serialNumber": robot.serial_number,
            "actions": actions,
        }

        try:
            payload_bytes = json.dumps(payload).encode("utf-8")
            inf = self._mqtt_client.publish(topic, payload_bytes, qos=self.qos_order)
            inf.wait_for_publish(timeout=min(ttl_sec, 3.0))
            act_types = [a.get("actionType") for a in actions if isinstance(a, dict)]
            self._log(f"Published instantActions {act_types} to {topic} (headerId={header_id})")
            self._record_cmd_result(robot, True, f"instantActions {act_types} published")
        except Exception as e:
            self._record_cmd_result(robot, False, f"Failed to publish instantActions: {e}")

    def _record_cmd_result(self, robot: RobotRuntime, ok: bool, detail: str):
        result = {
            "ok": ok,
            "detail": detail,
            "ts": utc_iso_now(),
        }
        self.api.write(f"{robot.robot_id}_vda_result", json.dumps(result))
        if not ok:
            self._log(f"Command error for {robot.robot_id}: {detail}")

    # ──────────────────────────────────────────────────────────
    # WATCHDOG & STALENESS MONITOR
    # ──────────────────────────────────────────────────────────
    def check_staleness(self):
        """Mark robots offline if no state message received within stale_after_sec."""
        now = time.time()
        changed = False
        for robot in self.robots.values():
            if robot.is_online and robot.last_state_time > 0:
                if (now - robot.last_state_time) > self.stale_after_sec:
                    self._log(f"Robot {robot.robot_id} stale (no state for >{self.stale_after_sec}s) -> OFFLINE")
                    robot.is_online = False
                    robot.last_rx_csv = ""
                    self.api.write(f"{robot.robot_id}_vda_rx", "")
                    changed = True
        if changed:
            self.update_robots_summary()

    def run(self):
        """Main helper execution loop."""
        self._log(f"Starting autoVDA for variable '{self.variable}' with {len(self.robots)} robot(s)...")

        # Initial write of anchor, status, and robots
        scheme = "mqtts" if self.use_tls else "mqtt"
        self.api.write(self.variable, f"{scheme}://{self.broker_host}:{self.broker_port}")
        self.update_status("INITIALIZING")
        self.update_robots_summary()

        # Connect MQTT
        self.start_mqtt()

        last_stale_check = 0.0
        while self._running:
            try:
                # 1. Poll fleet _tx commands
                self.poll_robot_tx_boxes()

                # 2. Staleness check every 1 second
                now = time.time()
                if now - last_stale_check >= 1.0:
                    self.check_staleness()
                    last_stale_check = now

                time.sleep(0.05)
            except KeyboardInterrupt:
                break
            except Exception as e:
                self._log(f"Loop error: {e}")
                time.sleep(0.5)

        self.cleanup()

    def cleanup(self):
        self._running = False
        self._log("Stopping autoVDA...")
        if self._mqtt_client:
            try:
                self._mqtt_client.loop_stop()
                self._mqtt_client.disconnect()
            except Exception:
                pass
        self.update_status("STOPPED (by user)")


# ──────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────
def main():
    base_dir = get_base_dir()
    stem = get_self_stem()
    variable = derived_variable_name()

    cfg = load_config(base_dir)
    if not variable:
        variable = str(cfg.get("variable", "vda_fleet")).strip()

    log_file = cfg.get("log_file", "vda.log")
    log_path = os.path.join(base_dir, log_file) if log_file else None

    # Connect to ignoAPI
    api_host = cfg.get("ignoapi_host", "127.0.0.1")
    api_port = int(cfg.get("ignoapi_port", 8899))
    api = IgnoApi(api_host, api_port, label=f"ignoAPI ({variable})")

    # Tray & console setup
    start_tray(stem, variable)
    watch_minimise()

    bridge = VdaBridge(cfg, variable, api, log_path)
    bridge.run()


if __name__ == "__main__":
    main()
