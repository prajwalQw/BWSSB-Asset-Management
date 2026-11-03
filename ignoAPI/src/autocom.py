"""
autocom — one serial (COM) reader per ignoAPI variable.

ignoAPI duplicates this program as <variable>_autocom.exe and writes
<variable>_autocom.json next to it. Like autoclient and autoModbusMaster, the
instance works out which config to read from its OWN filename, so one build
serves every variable with no arguments.

WHY THIS IS A SEPARATE PROCESS
    It used to be a thread inside ignoAPI, which cost on both ends:

      * STARTUP. Serial autodetect has to OPEN each candidate port and wait
        for the board to boot before probing -- seconds per port. Done inside
        ignoAPI that delay lands squarely on application startup, before the
        window is usable. Out here it happens in a child, concurrently, while
        ignoAPI is already up.

      * LATENCY. A reader polling at 10Hz was competing with a 30fps pygame
        loop for the GIL. Neither is heavy, but the serial side is the one
        with a device on the other end waiting.

    And the same rule as the Modbus master applies: a serial port is
    EXCLUSIVE-ACCESS, so exactly one process may own it. Making that a
    dedicated program removes any chance of ignoAPI and a child fighting.

WHAT IT OWNS
    <variable>                 latest line received from the device
    <variable>_tx              write here -> transmitted, then cleared
    <variable>_<port>_status   link state / error detail

    Reconnects forever on failure: a USB-serial adapter unplugged and
    replugged, or a device powered up after ignoAPI, recovers on its own.
"""
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime

# Shared with ignoAPI so the two cannot drift apart -- see comserial.py.
from comserial import (CC_LISTEN_CMD, CC_MAX_BUF, list_com_ports,
                       _cc_probe_port, _cc_read_latest, _cc_encode_command,
                       _cc_explain)

CC_RETRY_SEC = 3.0          # gap between reconnect attempts while down



# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY
#   Console app so the traffic is readable, but a reader that lives for the
#   whole session should not keep a window on the taskbar. All optional: on a
#   machine without pystray/Pillow it runs exactly the same with a plain
#   console. Feeding the variable is the job; the tray must never be able to
#   stop it.
# ──────────────────────────────────────────────────────────────
_console_visible = True
_tray_icon = None


def _console_hwnd():
    if os.name != "nt":
        return None
    try:
        import ctypes
        return ctypes.windll.kernel32.GetConsoleWindow() or None
    except Exception:
        return None


def show_console(show=True):
    global _console_visible
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(hwnd, 9 if show else 0)
        if show:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        _console_visible = bool(show)
        return True
    except Exception:
        return False


def _tray_image():
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    ico = os.path.join(get_base_dir(), "autocom.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGB", (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    d.ellipse((14, 14, 50, 50), outline=(255, 225, 40), width=4)   # COM yellow
    d.ellipse((26, 26, 38, 38), fill=(255, 225, 40))
    return img


def start_tray(stem, variable):
    """Run the tray icon on a daemon thread. Never fatal."""
    global _tray_icon
    try:
        import pystray
    except Exception as e:
        print(f"[tray] not available ({e}) — running with a plain console")
        return
    image = _tray_image()
    if image is None:
        print("[tray] Pillow not available — running with a plain console")
        return

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        pystray.MenuItem(f"{stem}  ->  {variable}",
                         lambda i, x: show_console(not _console_visible),
                         default=True),
        pystray.MenuItem("Show console", lambda i, x: show_console(True)),
        pystray.MenuItem("Hide console", lambda i, x: show_console(False)),
        pystray.MenuItem("Quit", on_quit),
    )
    _tray_icon = pystray.Icon(stem, image, f"autocom: {variable}", menu)
    threading.Thread(target=_tray_icon.run, daemon=True).start()


def watch_minimise():
    """Send the console to the tray when minimised. Windows gives a console app
    no event for this, so poll IsIconic at 4Hz."""
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
# SELF-IDENTIFICATION
# ──────────────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_self_stem():
    if getattr(sys, "frozen", False):
        path = os.path.basename(sys.executable)
    else:
        path = os.path.basename(os.path.abspath(__file__))
    return os.path.splitext(path)[0]


def derived_variable_name():
    """mag_autocom -> mag. Case-insensitive, because Windows filenames are."""
    stem = get_self_stem()
    suffix = "_autocom"
    if stem.lower().endswith(suffix) and len(stem) > len(suffix):
        return stem[: -len(suffix)]
    return None


def load_config(base_dir):
    p = os.path.join(base_dir, f"{get_self_stem()}.json")
    if not os.path.exists(p):
        print(f"[fatal] {os.path.basename(p)} not found at {p}")
        sys.exit(1)
    with open(p, "r") as f:
        return json.load(f)


# ──────────────────────────────────────────────────────────────
# ignoAPI LINK
# ──────────────────────────────────────────────────────────────
class IgnoApi:
    """Line-JSON client for ignoAPI over ONE PERSISTENT connection.

    Connection-per-call exhausts Windows' ~16k ephemeral ports at any real
    rate (every closed socket sits in TIME_WAIT for ~2 minutes), and the
    resulting failure reads as "ignoAPI is unreachable" -- a problem at
    entirely the wrong end. ignoAPI's server reads newline-delimited requests
    in a loop per connection, so one socket serves everything, and reconnects
    by itself if ignoAPI restarts.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = int(port) if port else 0
        self.enabled = bool(host and port)
        self._warned = False
        self._sock = None
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

    def _connect(self, timeout):
        self._close()
        self._sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self._sock.settimeout(timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _readline(self):
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise OSError("ignoAPI closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace").strip()

    def _rpc(self, payload, timeout=2.0):
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
                            print(f"[autocom] ignoAPI link error: {e}")
                            self._warned = True
                        return None
        return None

    def read(self, name):
        r = self._rpc({"action": "read", "name": name})
        return r.get("value") if r and r.get("status") == "success" else None

    def write(self, name, value):
        self._rpc({"action": "create_or_write", "name": name, "value": value})

def cc_status_var(variable, port):
    """mag + COM8 -> 'mag_com8_status'. Must match ignoAPI's cc_status_var."""
    p = str(port or "").strip().lower().replace(" ", "")
    return f"{variable}_{p}_status" if p else f"{variable}_com_status"


def _cc_log(log_file, name, text):
    if not log_file:
        return
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {name}: {text}\n")
    except OSError:
        pass


class ComReader:
    def __init__(self, cfg, variable, api):
        self.cfg = cfg
        self.variable = variable
        self.api = api
        self.tx_var = f"{variable}_tx"
        self.log_file = cfg.get("log_file") or ""
        self.port = str(cfg.get("port", "")).strip()
        self.status_var = cc_status_var(variable, self.port)
        self._last_status = None
        self.last_tx = None

    def set_status(self, text, also_value=False):
        """Publish link state. Deduplicated -- the poll loop would otherwise
        rewrite an unchanged status several times a second."""
        if text != self._last_status:
            self._last_status = text
            self.api.write(self.status_var, text)
        if also_value:
            self.api.write(self.variable, text)

    def pump_tx(self, ser):
        """Send whatever is sitting in <name>_tx, then clear it.

        The field is cleared BEFORE the write is attempted. Cleared afterwards,
        a write that raised would leave the text pending and it would be
        re-sent on every reconnect, forever. Losing one failed transmission is
        the better failure: the error is reported and it can be retyped.
        """
        pending = self.api.read(self.tx_var)
        if pending is None:
            return None
        text = str(pending)
        if not text.strip():
            return None
        self.api.write(self.tx_var, "")
        try:
            ser.write(_cc_encode_command(text))
            try:
                ser.flush()
            except Exception:
                pass
            self.last_tx = text
            self.set_status(f"TX {len(text)} bytes: {text[:60]}")
            _cc_log(self.log_file, self.variable, f"TX: {text}")
            print(f"[autocom] TX -> {text!r}")
            return text
        except Exception as e:
            self.set_status(f"TX FAILED: {e}")
            print(f"[autocom] TX failed: {e}")
            return None

    def resolve_port(self):
        """Pick the port to open, autodetecting first if a probe is configured.

        This ran inside ignoAPI at startup, where it was the single biggest
        cause of a slow launch: every candidate port is opened, given two
        seconds to boot, then probed. Out here it costs the CHILD time, in
        parallel, while ignoAPI is already usable.
        """
        probe = (self.cfg.get("probe") or "").strip()
        if not probe:
            return self.port
        baud = int(self.cfg.get("baud", 115200) or 115200)

        # Try the remembered port FIRST. A COM number is not stable across
        # reboots or USB sockets, but it is usually right, and checking it
        # first turns the common case into one probe instead of a full sweep.
        if self.port:
            self.set_status(f"AUTODETECT: checking {self.port} first", also_value=True)
            hit, reply = _cc_probe_port(self.port, probe, baud)
            if hit:
                print(f"[autocom] autodetect: {self.port} still answers OK")
                return self.port

        self.set_status("AUTODETECT: sweeping every port", also_value=True)
        for dev in list_com_ports():
            if dev == self.port:
                continue                      # already tried above
            hit, reply = _cc_probe_port(dev, probe, baud)
            print(f"[autocom] autodetect: {dev} -> {'OK' if hit else reply[:60]!r}")
            if hit:
                print(f"[autocom] autodetect: using {dev}")
                self.port = dev
                self.status_var = cc_status_var(self.variable, dev)
                return dev
        self.set_status(f"AUTODETECT: no port answered {probe!r}", also_value=True)
        return self.port

    def run(self):
        try:
            import serial
        except Exception as e:
            self.set_status(f"ERROR: pyserial not installed ({e})", also_value=True)
            return

        port = self.resolve_port()
        ser = None
        buf_holder = {"buf": b""}
        rx_total = 0
        last_rx_t = None
        last_note_t = 0.0
        opened_at = 0.0

        while True:
            baud = int(self.cfg.get("baud", 115200) or 115200)
            command = str(self.cfg.get("command", "")).strip()
            interval = float(self.cfg.get("poll_interval_sec", 0.1) or 0.1)
            read_to = float(self.cfg.get("read_timeout_sec", 1) or 1)
            listen_only = (command == CC_LISTEN_CMD)

            # ── connect ──────────────────────────────────────────────
            if ser is None:
                try:
                    self.set_status(f"CONNECTING {port} @ {baud}", also_value=True)
                    ser = serial.Serial(
                        port=port, baudrate=baud, timeout=read_to,
                        write_timeout=float(self.cfg.get("connect_timeout_sec", 5) or 5))
                    buf_holder["buf"] = b""   # stale fragments must not survive
                    # Many USB-serial bridges (and some Bluetooth SPP stacks)
                    # hold the device in reset, or simply refuse to transmit,
                    # until DTR and RTS are asserted. The port opens perfectly
                    # either way, so the symptom is exactly "CONNECTED, no data".
                    for _line in ("dtr", "rts"):
                        try:
                            setattr(ser, _line, True)
                        except Exception as _e:
                            print(f"[autocom] could not set {_line.upper()}: {_e}")
                    try:
                        ser.reset_input_buffer()
                    except Exception:
                        pass
                    rx_total = 0
                    last_rx_t = None
                    last_note_t = 0.0
                    opened_at = time.time()
                    self.set_status(f"CONNECTED {port} @ {baud} — waiting for data",
                                    also_value=True)
                    print(f"[autocom] connected on {port} @ {baud}")
                except Exception as e:
                    self.set_status(f"DISCONNECTED {port}: {_cc_explain(e, port)}",
                                    also_value=True)
                    ser = None
                    time.sleep(CC_RETRY_SEC)
                    continue

            # ── one poll ─────────────────────────────────────────────
            try:
                self.pump_tx(ser)

                # Only send a command if we are NOT in listen mode, and not
                # mid-reception. The listen-only half matters: without it a
                # command==0x01 client writes the listen SENTINEL to the device
                # every poll and -- worse -- calls reset_input_buffer(),
                # throwing away readings that have already arrived.
                if not listen_only and command and not buf_holder.get("buf"):
                    ser.reset_input_buffer()
                    ser.write(_cc_encode_command(command))
                text, n_rx = _cc_read_latest(ser, buf_holder)
                if n_rx:
                    rx_total += n_rx
                    last_rx_t = time.time()
                if text:
                    # REPLACE, never append: the variable holds the LATEST line.
                    self.api.write(self.variable, text)
                    _cc_log(self.log_file, self.variable, text)

                # Silence is a DIAGNOSIS, not a dead end: "waiting for data"
                # alone cannot distinguish "link up, device mute" from "bytes
                # arriving but nothing parses". Publish the byte counter.
                now_note = time.time()
                if now_note - last_note_t >= 2.0:
                    last_note_t = now_note
                    if rx_total == 0:
                        idle = int(now_note - opened_at)
                        self.set_status(
                            f"CONNECTED {port} @ {baud} — NO DATA ({idle}s, 0 bytes). "
                            f"Check the device is sending, and that {port} is the "
                            f"right port (a Bluetooth pair makes an Incoming AND an "
                            f"Outgoing COM port — you need the one the phone sends to).",
                            also_value=(text is None))
                    elif text is None:
                        quiet = int(now_note - (last_rx_t or now_note))
                        self.set_status(
                            f"CONNECTED {port} @ {baud} — {rx_total} bytes received, "
                            f"none parsed yet (last {quiet}s ago). If the value never "
                            f"updates the data has no delimiter this can split on.")
                    else:
                        self.set_status(f"CONNECTED {port} @ {baud} — {rx_total} bytes")
            except Exception as e:
                self.set_status(f"LINK LOST {port}: {e}", also_value=True)
                print(f"[autocom] link lost: {e}")
                try:
                    ser.close()
                except Exception:
                    pass
                ser = None
                time.sleep(CC_RETRY_SEC)
                continue

            time.sleep(max(0.01, interval))


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)
    cfg = load_config(base_dir)

    variable = cfg.get("variable") or derived_variable_name()
    if not variable:
        print("[fatal] no 'variable' in the config and none derivable from the filename")
        sys.exit(1)

    log_file = cfg.get("log_file") or ""
    if log_file and not os.path.isabs(log_file):
        cfg["log_file"] = os.path.join(base_dir, log_file)

    api = IgnoApi(cfg.get("ignoapi_host"), cfg.get("ignoapi_port"))

    print("=" * 62)
    print(f"  autocom — {get_self_stem()}")
    print(f"  variable : {variable}")
    print(f"  port     : {cfg.get('port')} @ {cfg.get('baud')}")
    print(f"  command  : {cfg.get('command')!r}"
          + ("   (listen-only)" if str(cfg.get('command')).strip() == CC_LISTEN_CMD else ""))
    print(f"  transmit : {variable}_tx")
    print("=" * 62)

    # Tray last, so a tray problem can never stop the reader from starting.
    start_tray(get_self_stem(), variable)
    watch_minimise()

    reader = ComReader(cfg, variable, api)
    try:
        reader.run()
    except KeyboardInterrupt:
        print("\n[autocom] stopping")


if __name__ == "__main__":
    main()
