"""
autoFTP.py — an FTP server that shares one folder, run per ignoAPI variable.

ONE FTP server == ONE ignoAPI variable. ignoAPI creates one by duplicating
this program to `<var>_autoftp.exe` (or `.py` in dev) alongside
`<var>_autoftp.json`, then launching it -- the same pattern as autoclient,
autocom, autoModbusMaster and autoSyncIgnoAPI. The running program derives its
config filename FROM ITS OWN filename:

    drop_autoftp.exe  ->  drop_autoftp.json  ->  variable "drop"

WHAT YOU GET

    drop            the address to connect to, e.g.
                        ftp://ignoapi_helloworld.local:2121
    drop_ftp_status what the server is doing: who connected, what was
                    uploaded or downloaded, what failed

The link uses this machine's ignoAPI NAME when it has one (ADDRESS is set),
because that is the address that keeps working when DHCP moves the machine.
It falls back to the LAN IP when there is no name.

CREDENTIALS

    Give a username and password and only that user can log in.
    Leave BOTH blank and the server accepts anonymous connections.

    An anonymous server is READ AND WRITE to anyone who can reach the port.
    That is what "no credentials" means and it is the right choice on an
    isolated robot network; it is the wrong one on an office LAN. The status
    row says which mode it is in, every time it starts, so it cannot be a
    surprise later.

Config (<var>_autoftp.json — ignoAPI writes all of it):
    {
      "variable": "drop",
      "ignoapi_host": "127.0.0.1",
      "ignoapi_port": 8899,
      "folder": "C:/shared",        # what gets served
      "port": 2121,
      "username": "",               # both blank -> anonymous
      "password": "",
      "read_only": false,
      "log_file": "ftp.log",
      "runatstartup": true
    }
"""
import json
import os
import socket

try:                       # our own mDNS, for names Windows cannot resolve
    from ignomdns import resolve_host as _resolve
except ImportError:        # standalone: behave exactly as before
    def _resolve(h, timeout=2.0):
        return h
import sys
import threading
import time
from datetime import datetime

STATUS_SUFFIX = "ftp_status"
SHARES_SUFFIX = "ftp_shares"
DIR_SUFFIX = "Dir"

# The port another ignoAPI listens on, when the address does not say.
DEFAULT_IGNOAPI_PORT = 8899
SHARE_INTERVAL_SEC = 5.0


def parse_targets(raw, default_port=DEFAULT_IGNOAPI_PORT):
    """'10.0.0.5, ignoapi_bot.local:8899' -> [(host, port), ...]

    A bare host takes the default port, so the common case is just a list of
    addresses. An IPv6 literal is not supported here on purpose: ignoAPI binds
    IPv4, and silently accepting something that can never connect is worse
    than not accepting it.
    """
    out = []
    for chunk in str(raw or "").replace(";", ",").split(","):
        item = chunk.strip().strip("{}").strip()
        if not item:
            continue
        host, port = item, default_port
        if ":" in item:
            head, _, tail = item.rpartition(":")
            if head and tail.strip().isdigit():
                host, port = head.strip(), int(tail.strip())
        host = host.strip().rstrip("/")
        if host:
            out.append((host, port))
    return out

# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY
#   Same arrangement as the other helper programs: a console app so the
#   transfer log is readable, plus a tray icon so it does not have to hold a
#   taskbar slot all session. Entirely optional.
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


def _tray_image():
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    ico = os.path.join(get_base_dir(), "autoFTP.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGB", (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    # a folder with an arrow into it
    d.rectangle((10, 20, 54, 48), outline=(255, 190, 80), width=3)
    d.line((32, 26, 32, 42), fill=(255, 190, 80), width=3)
    d.polygon([(32, 46), (26, 38), (38, 38)], fill=(255, 190, 80))
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
    _tray_icon = pystray.Icon(stem, image, f"FTP: {variable}", menu)
    threading.Thread(target=_tray_icon.run, daemon=True).start()


def watch_minimise():
    """Send the console to the tray when minimised."""
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


def config_path_for(base_dir):
    return os.path.join(base_dir, f"{get_self_stem()}.json")


def derived_variable_name():
    stem = get_self_stem()
    suffix = "_autoftp"
    if stem.lower().endswith(suffix) and len(stem) > len(suffix):
        return stem[: -len(suffix)]
    return None


def load_config(base_dir):
    config_path = config_path_for(base_dir)
    if not os.path.exists(config_path):
        print(f"[fatal] {os.path.basename(config_path)} not found at {config_path}")
        sys.exit(1)
    with open(config_path, "r") as f:
        return json.load(f)


def log_line(log_path, text):
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


def my_lan_ip():
    """This machine's LAN address, as another machine would see it."""
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sk.connect(("8.8.8.8", 80))
            return sk.getsockname()[0]
        finally:
            sk.close()
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


# ──────────────────────────────────────────────────────────────
# ignoAPI LINK
# ──────────────────────────────────────────────────────────────
class IgnoApi:
    """Read/write ignoAPI variables over its line-JSON TCP API, on ONE
    persistent connection. Same class the other helpers use: a connection per
    call exhausts Windows' ephemeral ports at any real rate."""

    def __init__(self, host, port, label="ignoAPI"):
        self.host = host
        self.port = int(port) if port else 0
        self.label = label
        self.enabled = bool(host and port)
        self._warned = False
        self._sock = None
        self._buf = b""
        self._lock = threading.Lock()      # transfer callbacks arrive on
                                           # pyftpdlib's thread

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
        self._sock = socket.create_connection((_resolve(self.host), self.port),
                                              timeout=timeout)
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
                            print(f"[ftp] {self.label} unreachable: {e}")
                            self._warned = True
                        return None
        return None

    def write(self, name, value):
        r = self._rpc({"action": "create_or_write", "name": name, "value": value})
        return bool(r and r.get("status") == "success")

    def read(self, name):
        r = self._rpc({"action": "read", "name": name})
        return r.get("value") if r and r.get("status") == "success" else None


# ──────────────────────────────────────────────────────────────
# THE SERVER
# ──────────────────────────────────────────────────────────────
class Server:
    def __init__(self, cfg, variable, api, log_path):
        self.cfg = cfg
        self.variable = variable
        self.api = api
        self.log_path = log_path
        self.status_var = f"{variable}_{STATUS_SUFFIX}"

        self.folder = os.path.abspath(str(cfg.get("folder") or get_base_dir()))
        try:
            self.port = int(cfg.get("port") or 2121)
        except (TypeError, ValueError):
            self.port = 2121
        self.user = str(cfg.get("username") or "").strip()
        self.password = str(cfg.get("password") or "")
        self.anonymous = not self.user
        self.read_only = bool(cfg.get("read_only"))
        self.server = None
        self._last_status = None
        self.transfers = 0

        self.shares_var = f"{variable}_{SHARES_SUFFIX}"
        self.targets = parse_targets(cfg.get("share_with"))
        # host -> the IgnoApi that talks to it, and whether it answered last
        self.peers = {f"{h}:{p}": IgnoApi(h, p, label=f"{h}:{p}")
                      for h, p in self.targets}
        self.peer_up = {k: None for k in self.peers}
        self._last_shares = None

    # ── the address to hand out ────────────────────────────────────
    def link(self):
        """ftp://<name-or-ip>:<port>.

        Prefers this machine's ignoAPI NAME. That name is the whole point of
        ADDRESS: it survives the DHCP lease changing, and an FTP link pasted
        into a document outlives the address it was written with.
        """
        host = None
        try:
            addr = self.api.read("ADDRESS")
            addr = str(addr or "").strip()
            if addr:
                host = addr if addr.endswith(".local") else f"ignoapi_{addr}.local"
        except Exception:
            host = None
        return f"ftp://{host or my_lan_ip()}:{self.port}"

    def set_status(self, text):
        """Publish status, but only when it CHANGES -- otherwise an idle
        server rewrites the same line forever."""
        if text == self._last_status:
            return
        self._last_status = text
        self.api.write(self.status_var, text)

    def note(self, text):
        """A transfer or a connection: logged AND published.

        These are events rather than states, so unlike set_status they are
        written every time -- that is the point of watching the row.
        """
        log_line(self.log_path, text)
        self._last_status = text
        self.api.write(self.status_var, text)

    # ── sharing ────────────────────────────────────────────────────
    def share_prefix(self):
        """What the shared rows are named after: this machine.

        The ADDRESS name when there is one, because that is the word the
        person reading the other machine's table will recognise. An address
        slug otherwise -- unhelpful, but never blank, and a row called
        "_sampleFTP" would be worse than an ugly one.
        """
        try:
            addr = str(self.api.read("ADDRESS") or "").strip()
        except Exception:
            addr = ""
        if addr:
            addr = addr[len("ignoapi_"):] if addr.startswith("ignoapi_") else addr
            addr = addr.split(".local")[0]
        if not addr:
            addr = my_lan_ip().replace(".", "_")
        return "".join(c if (c.isalnum() or c == "_") else "_" for c in addr)

    def push_shares(self):
        """Write this share into every listed machine's table.

        Repeated on a timer rather than sent once: a machine that was off when
        the share was set up gets it when it comes back, and the link follows
        an ADDRESS change on this side. Writing the same value again is
        harmless -- create_or_write is idempotent.
        """
        if not self.peers:
            return
        prefix = self.share_prefix()
        link = self.link()
        name = f"{prefix}_{self.variable}"
        n_up = 0
        for key, api in self.peers.items():
            # BOTH rows have to land before the peer counts as delivered. The
            # folder goes with the link -- the link says where to connect,
            # this says what you are looking at -- and a machine that got one
            # and not the other is not shared with, it is half shared with.
            # Tracking only the first write reported a peer UP whose second
            # write had already failed.
            ok = api.write(name, link)
            if ok:
                ok = api.write(f"{name}_{DIR_SUFFIX}", self.folder)
            was = self.peer_up.get(key)
            self.peer_up[key] = ok
            if ok:
                n_up += 1
            if was is not ok:
                log_line(self.log_path,
                         f"share {name} -> {key}: {'DELIVERED' if ok else 'UNREACHABLE'}")
        detail = ", ".join(f"{k} {'UP' if self.peer_up[k] else 'DOWN'}"
                           for k in self.peers)
        text = f"{n_up}/{len(self.peers)} live — {name} — {detail}"
        if text != self._last_shares:
            self._last_shares = text
            self.api.write(self.shares_var, text)

    # ── build and run ──────────────────────────────────────────────
    def build(self):
        from pyftpdlib.authorizers import DummyAuthorizer
        from pyftpdlib.handlers import FTPHandler
        from pyftpdlib.servers import FTPServer

        if not os.path.isdir(self.folder):
            try:
                os.makedirs(self.folder, exist_ok=True)
                log_line(self.log_path, f"created the shared folder {self.folder}")
            except OSError as e:
                self.set_status(f"ERROR — cannot use folder {self.folder}: {e}")
                raise

        # elradfmwMT = full read/write. Read-only drops the writing ones.
        perm = "elr" if self.read_only else "elradfmwMT"
        auth = DummyAuthorizer()
        if self.anonymous:
            auth.add_anonymous(self.folder, perm=perm)
        else:
            auth.add_user(self.user, self.password, self.folder, perm=perm)

        outer = self

        class Handler(FTPHandler):
            """Every event is reported to the ignoAPI row, which is what the
            status variable is FOR -- watching transfers from the table
            without opening a console."""

            def on_connect(self):
                outer.note(f"CONNECT from {self.remote_ip}:{self.remote_port}")

            def on_disconnect(self):
                outer.note(f"DISCONNECT {self.remote_ip}")

            def on_login(self, username):
                outer.note(f"LOGIN {username or 'anonymous'} from {self.remote_ip}")

            def on_login_failed(self, username, password):
                # Deliberately does NOT echo the password back into a variable
                # anyone can read in the table.
                outer.note(f"LOGIN FAILED for {username!r} from {self.remote_ip}")

            def on_file_sent(self, file):
                outer.transfers += 1
                outer.note(f"SENT {os.path.basename(file)} "
                           f"({_size(file)}) to {self.remote_ip}")

            def on_file_received(self, file):
                outer.transfers += 1
                outer.note(f"RECEIVED {os.path.basename(file)} "
                           f"({_size(file)}) from {self.remote_ip}")

            def on_incomplete_file_sent(self, file):
                outer.note(f"INCOMPLETE send of {os.path.basename(file)}")

            def on_incomplete_file_received(self, file):
                outer.note(f"INCOMPLETE upload of {os.path.basename(file)} "
                           f"— partial file left in place")

        Handler.authorizer = auth
        Handler.banner = f"ignoAPI autoFTP [{self.variable}]"
        # A modest cap: this shares one folder on a robot, it is not a public
        # file service, and an unbounded connection count is a way to be
        # knocked over by accident.
        self.server = FTPServer(("0.0.0.0", self.port), Handler)
        self.server.max_cons = 32
        self.server.max_cons_per_ip = 8
        return self.server

    def run(self):
        mode = "ANONYMOUS (no login)" if self.anonymous else f"user '{self.user}'"
        access = "read-only" if self.read_only else "read/write"
        link = self.link()
        self.api.write(self.variable, link)
        self.set_status(f"STARTING {link}  {mode}  {access}  folder={self.folder}")

        print("=" * 66)
        print(f"  autoFTP — {get_self_stem()}")
        print(f"  variable : {self.variable}")
        print(f"  link     : {link}")
        print(f"  folder   : {self.folder}")
        print(f"  access   : {mode}, {access}")
        print(f"  status   : {self.status_var}")
        if self.anonymous:
            print()
            print("  ANONYMOUS: anyone who can reach this port can read"
                  + ("" if self.read_only else " AND WRITE") + " these files.")
        print("=" * 66)

        try:
            self.build()
        except Exception as e:
            self.set_status(f"ERROR — {e}")
            log_line(self.log_path, f"could not start: {e}")
            raise

        self.set_status(f"LIVE {link}  {mode}  {access}  folder={self.folder}")
        log_line(self.log_path, f"serving {self.folder} at {link} ({mode}, {access})")

        # Keep the link fresh: ADDRESS can be set or changed while this is
        # running, and the row should say where the server actually is.
        def _watch():
            while True:
                time.sleep(5.0)
                try:
                    now = self.link()
                    if now != link_holder[0]:
                        link_holder[0] = now
                        self.api.write(self.variable, now)
                        log_line(self.log_path, f"address changed -> {now}")
                except Exception:
                    pass

        link_holder = [link]
        threading.Thread(target=_watch, daemon=True).start()

        if self.peers:
            print(f"  sharing to {len(self.peers)} machine(s): "
                  + ", ".join(self.peers))
            print(f"  they will see: {self.share_prefix()}_{self.variable}"
                  f" and {self.share_prefix()}_{self.variable}_{DIR_SUFFIX}")

            def _share_loop():
                while True:
                    try:
                        self.push_shares()
                    except Exception as e:
                        log_line(self.log_path, f"share error (continuing): {e}")
                    time.sleep(SHARE_INTERVAL_SEC)

            threading.Thread(target=_share_loop, daemon=True).start()

        self.server.serve_forever()


def _size(path):
    try:
        n = os.path.getsize(path)
    except OSError:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}GB"


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)
    cfg = load_config(base_dir)

    variable = cfg.get("variable") or derived_variable_name()
    if not variable:
        print("[fatal] no 'variable' in the config and none derivable from the filename")
        sys.exit(1)

    log_path = cfg.get("log_file") or ""
    if log_path and not os.path.isabs(log_path):
        log_path = os.path.join(base_dir, log_path)

    api = IgnoApi(cfg.get("ignoapi_host", "127.0.0.1"), cfg.get("ignoapi_port"))
    server = Server(cfg, variable, api, log_path)

    start_tray(get_self_stem(), variable)
    watch_minimise()

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n[ftp] stopping")
        server.set_status("STOPPED")
    except Exception as e:
        server.set_status(f"ERROR — {e}")
        raise


if __name__ == "__main__":
    main()
