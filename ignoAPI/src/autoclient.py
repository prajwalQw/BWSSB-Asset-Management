"""
autoclient.py  —  a tiny standalone TCP poller that feeds one ignoAPI variable.

ONE autoclient == ONE ignoAPI variable. ignoAPI creates an autoclient by
duplicating this program to `autoclient_<var>.exe` (or `.py` in dev) alongside
`autoclient_<var>.json`, then launching it. The running program derives its
config filename FROM ITS OWN filename:

    autoclient_mag.exe   ->  reads  autoclient_mag.json   ->  writes var "mag"
    autoclient_odom.exe  ->  reads  autoclient_odom.json  ->  writes var "odom"
    autoclient.exe/.py   ->  reads  autoclient.json       (plain, backward compat)

Each response received from the target device (server_ip:port) is written back
into the ignoAPI variable named in the config ("variable"), via a TCP
create_or_write to ignoapi_host:ignoapi_port (both injected by ignoAPI).

Config (autoclient_<var>.json):
    {
      "variable": "mag",              # ignoAPI variable to feed (ignoAPI sets this)
      "ignoapi_host": "127.0.0.1",    # where to write the value back (ignoAPI sets)
      "ignoapi_port": 8899,           # ignoAPI server port (ignoAPI sets)
      "server_ip": "192.168.1.11",    # the DEVICE to poll
      "mac": "",                      # optional, informational
      "port": 8899,                   # the DEVICE port
      "command": "0x01",
      "poll_interval_sec": 0.1,
      "connect_timeout_sec": 5,
      "read_timeout_sec": 5,
      "log_file": "responses.log",
      "runatstartup": true
    }
"""
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

PERSISTENT_CODE = "0x01"

# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY
#   This program runs as a CONSOLE app so its log is readable, but a poller
#   that lives for the whole session should not have to keep a window on the
#   taskbar. So: a tray icon that toggles the console, and minimise sends it
#   to the tray rather than the taskbar -- the same behaviour as ignoAPI.
#
#   All of it is optional. On a machine without pystray/Pillow, or on a
#   non-Windows host, the program runs exactly as before with a plain console.
#   Feeding the variable is the job; the tray is a convenience and must never
#   be able to stop it.
# ──────────────────────────────────────────────────────────────
_console_visible = True
_tray_icon = None

SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_RESTORE = 9


def _console_hwnd():
    """Handle of this process's console window, or None if there isn't one."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        return hwnd or None
    except Exception:
        return None


def show_console(show=True):
    global _console_visible
    hwnd = _console_hwnd()
    if not hwnd:
        return False
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE if show else SW_HIDE)
        if show:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        _console_visible = bool(show)
        return True
    except Exception:
        return False


def _tray_image(stem):
    """Tray icon: autoclient.ico if it is next to us, else a drawn fallback."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    ico = os.path.join(get_base_dir(), "autoclient.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGB", (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    d.ellipse((14, 14, 50, 50), outline=(90, 165, 255), width=4)   # autoclient blue
    d.ellipse((26, 26, 38, 38), fill=(90, 165, 255))
    return img


def start_tray(stem, variable):
    """Run the tray icon on a daemon thread. Never fatal."""
    global _tray_icon
    try:
        import pystray
    except Exception as e:
        print(f"[tray] not available ({e}) — running with a plain console")
        return

    image = _tray_image(stem)
    if image is None:
        print("[tray] Pillow not available — running with a plain console")
        return

    def on_show(icon, item):
        show_console(True)

    def on_hide(icon, item):
        show_console(False)

    def on_quit(icon, item):
        icon.stop()
        os._exit(0)

    def toggle(icon, item):
        show_console(not _console_visible)

    menu = pystray.Menu(
        pystray.MenuItem(f"{stem}  ->  {variable}", toggle, default=True),
        pystray.MenuItem("Show console", on_show),
        pystray.MenuItem("Hide console", on_hide),
        pystray.MenuItem("Quit", on_quit),
    )
    _tray_icon = pystray.Icon(stem, image, f"autoclient: {variable}", menu)
    threading.Thread(target=_tray_icon.run, daemon=True).start()


def watch_minimise():
    """Send the console to the tray when it is minimised.

    Windows has no event for "my console was minimised" that a console app can
    subscribe to, so this polls IsIconic at 4Hz -- cheap, and it only has to be
    responsive to a human clicking minimise.
    """
    if os.name != "nt":
        return

    def _loop():
        import ctypes
        while True:
            try:
                hwnd = _console_hwnd()
                if hwnd and _console_visible and ctypes.windll.user32.IsIconic(hwnd):
                    show_console(False)      # to the tray, not the taskbar
            except Exception:
                pass
            time.sleep(0.25)

    threading.Thread(target=_loop, daemon=True).start()




def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_self_stem():
    """Basename (no extension) of the running program — 'autoclient_mag' for
    autoclient_mag.exe / autoclient_mag.py, or 'autoclient' for the plain one."""
    if getattr(sys, "frozen", False):
        path = os.path.basename(sys.executable)
    else:
        path = os.path.basename(os.path.abspath(__file__))
    return os.path.splitext(path)[0]


def config_path_for(base_dir):
    """The config file this instance should read, from its own filename."""
    return os.path.join(base_dir, f"{get_self_stem()}.json")


def derived_variable_name():
    """Variable name inferred from the filename suffix (autoclient_mag -> mag),
    used only if the config doesn't state 'variable' explicitly. None for the
    plain 'autoclient'."""
    stem = get_self_stem()
    prefix = "autoclient_"
    if stem.startswith(prefix) and len(stem) > len(prefix):
        return stem[len(prefix):]
    return None


def load_config(base_dir):
    config_path = config_path_for(base_dir)
    if not os.path.exists(config_path):
        print(f"[fatal] {os.path.basename(config_path)} not found at {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return json.load(f)


def log_response(log_path, text):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {text}"
    print(line)
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def parse_value(raw):
    """Turn a raw device response string into a JSON-friendly value: a number
    or bool/null if it parses as JSON, otherwise the trimmed string."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


class IgnoApiWriter:
    """Writes the latest device response into one ignoAPI variable. Uses a
    short-lived connection per write (robust; ignoAPI is local, so cheap)."""
    def __init__(self, host, port, variable):
        self.host = host
        self.port = port
        self.variable = variable
        self.enabled = bool(host and port and variable)

    def write(self, value):
        if not self.enabled:
            return
        try:
            req = json.dumps({"action": "create_or_write",
                              "name": self.variable, "value": value}) + "\n"
            with socket.create_connection((self.host, int(self.port)), timeout=2.0) as s:
                s.sendall(req.encode("utf-8"))
                try:
                    s.recv(1024)   # read + discard the ack
                except socket.timeout:
                    pass
        except OSError as e:
            print(f"[autoclient] ignoAPI write failed: {e}")


def request_response_loop(cfg, log_path, writer):
    host = cfg["server_ip"]
    port = cfg["port"]
    command = cfg["command"]
    interval = cfg.get("poll_interval_sec", 1.0)
    connect_timeout = cfg.get("connect_timeout_sec", 5)
    read_timeout = cfg.get("read_timeout_sec", 5)

    while True:
        try:
            with socket.create_connection((host, port), timeout=connect_timeout) as s:
                s.settimeout(read_timeout)
                s.sendall((command + "\n").encode("utf-8"))
                try:
                    data = s.recv(4096)
                    text = data.decode("utf-8", errors="replace").strip()
                    log_response(log_path, f"RECV: {text}")
                    writer.write(parse_value(text))
                except socket.timeout:
                    log_response(log_path, "RECV TIMEOUT: no response")
        except (ConnectionRefusedError, socket.timeout, OSError) as e:
            log_response(log_path, f"CONN ERROR: {e}")

        time.sleep(interval)


def persistent_listen_loop(cfg, log_path, writer):
    host = cfg["server_ip"]
    port = cfg["port"]
    connect_timeout = cfg.get("connect_timeout_sec", 5)
    read_timeout = cfg.get("read_timeout_sec", 5)

    while True:
        try:
            with socket.create_connection((host, port), timeout=connect_timeout) as s:
                s.settimeout(read_timeout)
                log_response(log_path, "CONNECTED (persistent mode)")
                buffer = b""
                while True:
                    try:
                        chunk = s.recv(4096)
                        if not chunk:
                            log_response(log_path, "CONN CLOSED BY SERVER")
                            break
                        buffer += chunk
                        while b"\n" in buffer:
                            line, buffer = buffer.split(b"\n", 1)
                            text = line.decode("utf-8", errors="replace").strip()
                            log_response(log_path, f"RECV: {text}")
                            writer.write(parse_value(text))
                    except socket.timeout:
                        continue
        except (ConnectionRefusedError, OSError) as e:
            log_response(log_path, f"CONN ERROR: {e}, retrying in 2s")
            time.sleep(2)


def main():
    base_dir = get_base_dir()
    cfg = load_config(base_dir)
    log_path = os.path.join(base_dir, cfg.get("log_file", "responses.log"))

    variable = cfg.get("variable") or derived_variable_name()
    writer = IgnoApiWriter(cfg.get("ignoapi_host", "127.0.0.1"),
                           cfg.get("ignoapi_port"), variable)

    print(f"Config loaded: {cfg}")
    print(f"Feeding ignoAPI variable: {variable!r} "
          f"({'enabled' if writer.enabled else 'DISABLED — no ignoapi target'})")

    # Tray last, so a tray problem can never stop the poller from starting.
    start_tray(get_self_stem(), variable)
    watch_minimise()
    print("[tray] icon active — double-click it to show/hide this console")
    try:
        if str(cfg.get("command")) == PERSISTENT_CODE:
            persistent_listen_loop(cfg, log_path, writer)
        else:
            request_response_loop(cfg, log_path, writer)
    except KeyboardInterrupt:
        print("\n[stopped by user]")


if __name__ == "__main__":
    main()
