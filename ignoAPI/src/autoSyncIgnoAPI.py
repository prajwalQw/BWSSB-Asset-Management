"""
autoSyncIgnoAPI.py — link one variable on THIS ignoAPI to one on ANOTHER
computer's ignoAPI, in both directions.

ONE sync == ONE variable pair. ignoAPI creates a sync by duplicating this
program to `<var>_autosyncignoapi.exe` (or `.py` in dev) alongside
`<var>_autosyncignoapi.json`, then launching it -- exactly the way autoclient,
autocom and autoModbusMaster are created. The running program derives its
config filename FROM ITS OWN filename:

    r1var_autosyncignoapi.exe  ->  r1var_autosyncignoapi.json  ->  var "r1var"

WHAT IT DOES

Syncing `r1var` against ONE peer gives you four boxes, two on each machine:

    THIS computer                        THE OTHER computer
    -------------                        ------------------
    r1var_tx   ----------------------->  r1var_rx
    r1var_rx   <-----------------------  r1var_tx

Type (or write from code) into `_tx` on either side and it appears in the
other side's `_rx`. The `_tx` box is CLEARED once its contents have been
delivered, which is what makes it usable as a send box: an empty field means
"nothing pending", so sending the same value twice actually sends it twice.

SEVERAL PEERS

`server_ip` may be a comma separated list -- 10.0.0.5,10.0.0.6,10.0.0.7. Then:

  * r1var_tx is BROADCAST: every peer gets it, and the box clears once every
    REACHABLE peer has it. Holding it for a switched-off machine would mean
    one dead peer stops the whole fleet from sending.

  * each peer gets its OWN inbound box, r1var_rx_10_0_0_5 and so on, because
    a single _rx holds one value and several peers can speak in the same
    poll -- the others would be silently overwritten. Plain r1var_rx is kept
    as "most recent from anyone".

  * each peer polls on ITS OWN THREAD, so a machine that is switched off
    costs nothing but its own retries. With one shared loop it would stall
    every other peer for the length of its connect timeout.

  * r1var_peers reports "host=UP,host=DOWN" -- what ignoAPI's View Network
    diagram is drawn from.

MODE  (config "mode")

    0x01  LEVEL  -- the received value STAYS in `_rx` until a new one
                    arrives. This is the one to use for a reading you want
                    to watch: a speed, a status word, a position.

    0x02  PULSE  -- the received value appears in `_rx` and is then cleared
                    again after `pulse_ms`. Use it for an EVENT: a trigger,
                    a button, a one-shot command. With level mode a repeated
                    trigger is invisible (the box already holds that value);
                    a pulse returns to empty, so the next one is a change
                    again.

Config (<var>_autosyncignoapi.json — ignoAPI writes all of it):
    {
      "variable": "r1var",            # the local pair name (this creates
                                      #   r1var_tx / r1var_rx / r1var_status)
      "ignoapi_host": "127.0.0.1",    # THIS ignoAPI
      "ignoapi_port": 8899,
      "server_ip": "192.168.1.50",    # the OTHER computer's ignoAPI
      "mac": "",                      # optional; ignoAPI re-resolves the IP
      "port": 8899,                   # the OTHER ignoAPI's port
      "remote_var": "r1var",          # the pair name over there
      "mode": "0x01",                 # 0x01 level | 0x02 pulse
      "pulse_ms": 300,
      "poll_interval_sec": 0.1,
      "connect_timeout_sec": 5,
      "read_timeout_sec": 5,
      "log_file": "sync.log",
      "runatstartup": true
    }
"""
import json
import os
import re
import socket
import sys
import threading
import time
from datetime import datetime

MODE_LEVEL = "0x01"
MODE_PULSE = "0x02"

RX_SUFFIX = "rx"
TX_SUFFIX = "tx"
STATUS_SUFFIX = "status"
PEERS_SUFFIX = "peers"

RETRY_SEC = 2.0          # gap between reconnect attempts while the peer is down

# Written into <var>_status on the PEER. ignoAPI over there matches this exact
# prefix to colour those rows as a sync and group them together, so it is a
# CONTRACT between the two programs -- changing the wording here means
# changing REMOTE_SYNC_MARK in ignoAPI.py to match.
REMOTE_MARK = "SYNCED FROM "


def my_lan_ip():
    """This machine's LAN address, as the peer would see it.

    Connecting a UDP socket sets a local address without sending anything, so
    this picks the interface that would actually be used to reach the outside
    -- which is the address worth telling the other machine about. A hostname
    lookup can hand back 127.0.0.1 on a multi-homed box, which would be
    useless in the marker.
    """
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
            return "?"

# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY
#   Same arrangement as the other helper programs: a console app so the log
#   is readable, plus a tray icon so it does not have to hold a taskbar slot
#   all session. Entirely optional -- without pystray/Pillow, or off Windows,
#   it runs as a plain console and syncs exactly the same.
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
    ico = os.path.join(get_base_dir(), "autoSyncIgnoAPI.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGB", (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    # two boxes and an arrow between them -- this program is a link
    d.rectangle((8, 22, 26, 42), outline=(120, 180, 255), width=3)
    d.rectangle((38, 22, 56, 42), outline=(120, 180, 255), width=3)
    d.line((26, 28, 38, 28), fill=(120, 180, 255), width=3)
    d.line((38, 36, 26, 36), fill=(120, 180, 255), width=3)
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
    _tray_icon = pystray.Icon(stem, image, f"ignoAPI sync: {variable}", menu)
    threading.Thread(target=_tray_icon.run, daemon=True).start()


def watch_minimise():
    """Send the console to the tray when minimised. Windows gives a console app
    no event for this, so poll IsIconic at 4Hz — cheap, and it only has to keep
    up with a human clicking minimise."""
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
# SELF-IDENTIFICATION  (which variable am I?)
# ──────────────────────────────────────────────────────────────
def get_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_self_stem():
    """Basename without extension: 'r1var_autosyncignoapi' for the duplicated
    copy, 'autoSyncIgnoAPI' for the original."""
    if getattr(sys, "frozen", False):
        path = os.path.basename(sys.executable)
    else:
        path = os.path.basename(os.path.abspath(__file__))
    return os.path.splitext(path)[0]


def config_path_for(base_dir):
    return os.path.join(base_dir, f"{get_self_stem()}.json")


def derived_variable_name():
    """Variable inferred from the filename (r1var_autosyncignoapi -> r1var),
    used only when the config does not state 'variable'. Case-insensitive on
    the suffix because Windows filenames are."""
    stem = get_self_stem()
    suffix = "_autosyncignoapi"
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


# ──────────────────────────────────────────────────────────────
# ignoAPI LINK
# ──────────────────────────────────────────────────────────────
class IgnoApi:
    """Read/write ignoAPI variables over its line-JSON TCP API, on ONE
    PERSISTENT connection.

    The obvious implementation -- connect, send, read, close, per call -- is
    what autoclient does, and at one poll a second it is fine. This program
    polls several times a second against TWO servers, and at that rate it
    dies:

        OSError [WinError 10048] Only one usage of each socket address ...

    Every closed client socket sits in TIME_WAIT for around two minutes and
    Windows has only ~16k ephemeral ports, so a fast poll works through the
    whole range and then cannot connect at all -- and the failure reads as
    "the other computer is unreachable", which sends you looking in the wrong
    place entirely. One reused connection removes it, and drops a TCP
    handshake from every call.

    It reconnects by itself, so an ignoAPI restart at either end is
    survivable, and the same class serves the local and the remote server --
    there is nothing special about "remote" here beyond the address.
    """

    def __init__(self, host, port, label="ignoAPI"):
        self.host = host
        self.port = int(port) if port else 0
        self.label = label
        self.enabled = bool(host and port)
        self._warned = False
        self._sock = None
        self._buf = b""

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
        self._sock = socket.create_connection((self.host, self.port),
                                              timeout=timeout)
        self._sock.settimeout(timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _readline(self):
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise OSError(f"{self.label} closed the connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode("utf-8", errors="replace").strip()

    def _rpc(self, payload, timeout=2.0):
        if not self.enabled:
            return None
        req = (json.dumps(payload) + "\n").encode("utf-8")
        for attempt in (1, 2):
            try:
                if self._sock is None:
                    self._connect(timeout)
                self._sock.sendall(req)
                line = self._readline()
                self._warned = False
                return json.loads(line) if line else None
            except (OSError, ValueError) as e:
                # One reconnect covers the normal case (the other end
                # restarted); a second failure means it is genuinely down, and
                # the caller waits rather than spinning.
                self._close()
                if attempt == 2:
                    if not self._warned:
                        # A name that does not resolve is a TYPO nine times in
                        # ten, and "getaddrinfo failed" does not say so.
                        if isinstance(e, socket.gaierror):
                            print(f"[sync] {self.label}: '{self.host}' could not "
                                  f"be resolved — check the address (an IP is "
                                  f"four numbers separated by dots)")
                        else:
                            print(f"[sync] {self.label} unreachable: {e}")
                        self._warned = True
                    return None
        return None

    @property
    def up(self):
        return self._sock is not None

    def read_all(self):
        r = self._rpc({"action": "read_all"})
        if r and r.get("status") == "success" and isinstance(r.get("value"), dict):
            return r["value"]
        return None

    def write(self, name, value):
        r = self._rpc({"action": "create_or_write", "name": name, "value": value})
        return bool(r and r.get("status") == "success")


# ──────────────────────────────────────────────────────────────
# THE SYNC
# ──────────────────────────────────────────────────────────────
COMMAND_HELP = """\
readData(name)              read `name` from EVERY peer; with more than one
                            the answer is one slot each, in peer order
readData(name,10.0.0.5)     read it from that peer only
writeData(name,"data")      write "data" into `name` on EVERY peer, creating
                            it where it is not there yet
writeData(name,42,10.0.0.5) write it to that peer only
writeData(name,42)          unquoted numbers, true/false/null go across as
                            numbers and booleans, not as text

The box is a REQUEST/RESPONSE field: what you get back is either the value, OK,
or ERROR: <reason>. Overwrite it with the next command."""

_CMD_RE = re.compile(r"^\s*(readData|writeData)\s*\((.*)\)\s*$",
                     re.IGNORECASE | re.DOTALL)


class CommandError(ValueError):
    """A command that cannot be carried out as written."""


def _unquote(tok):
    t = str(tok).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1]
    return t


def parse_value(tok):
    """The value half of writeData.

    A QUOTED token is taken literally, always. An unquoted one is offered to
    JSON first, so writeData(speed,42) sends the number 42 and not the string
    "42" -- the receiving end almost always wants to do arithmetic with it.
    Anything JSON cannot read is sent as plain text, which is what makes
    writeData(msg,hello world) work without quotes.
    """
    t = str(tok).strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ("'", '"'):
        return t[1:-1]
    if t == "":
        return ""
    try:
        return json.loads(t)
    except (json.JSONDecodeError, ValueError):
        return t


def _split_target(args, is_peer):
    """Peel an optional trailing peer address off a command's arguments.

    Only peeled when the last field IS a configured peer of this sync. A value
    can contain commas, so a trailing token has to earn being read as an
    address -- otherwise writeData(pose,"1,2,3") would lose its last number to
    a peer that does not exist.
    """
    head, sep, last = args.rpartition(",")
    if not sep:
        return args, None
    cand = _unquote(last)
    if cand and is_peer is not None and is_peer(cand) is not None:
        return head, cand
    return args, None


def parse_command(raw, is_peer=None):
    """'readData(fid)' -> ('read', 'fid', None, None), or None if not a command.

    The fourth item is the peer to talk to, or None for "all of them".

    Returning None rather than raising for unrecognised text matters: the box
    holds the ANSWER after a command runs, and an answer must not be mistaken
    for the next request.
    """
    text = str(raw if raw is not None else "").strip()
    if not text:
        return None
    m = _CMD_RE.match(text)
    if not m:
        return None
    kind = m.group(1).lower()
    args, target = _split_target(m.group(2), is_peer)

    if kind == "readdata":
        name = _unquote(args)
        if not name:
            raise CommandError("readData() needs a variable name")
        if "," in name:
            # The only way a comma survives here is a second field that is not
            # one of this sync's peers -- almost always a mistyped address.
            raise CommandError(
                "readData takes a name and an optional PEER address — "
                "use readData(fid) or readData(fid,10.0.0.5)")
        return ("read", name, None, target)

    # writeData: split on the FIRST comma only, so a value may contain commas
    if "," not in args:
        raise CommandError('writeData needs a name AND a value, '
                           'e.g. writeData(fid,"5")')
    name, _, value = args.partition(",")
    name = _unquote(name)
    if not name:
        raise CommandError("writeData() needs a variable name")
    return ("write", name, parse_value(value), target)


def norm_host(raw):
    """Repair a peer address typed with the wrong separator.

    `10:28:14:210` is an IP with colons where the dots should be. Left alone
    it is treated as a HOSTNAME, and the only symptom is

        [Errno 11001] getaddrinfo failed

    which reads as "the other computer is off" rather than "look at what you
    typed". ignoAPI now rejects it at the modal, but a config written before
    that check existed is still on disk, so repair it here too.

    Deliberately narrow: EXACTLY four groups of 1-3 digits, each 0-255. That
    cannot collide with a real hostname or an IPv6 literal.
    """
    h = str(raw or "").strip()
    if not h:
        return h
    parts = [p for p in re.split(r"[\s:;,/|]+", h) if p != ""]
    if (len(parts) == 4 and all(p.isdigit() and len(p) <= 3 and int(p) <= 255
                                for p in parts)):
        return ".".join(parts)
    return h


def is_blank(v):
    """An empty box. Only "" / None count -- 0 and False are real values a
    sync is very likely to be carrying, and treating them as "nothing to
    send" would drop exactly the signals people use for a state bit."""
    return v is None or (isinstance(v, str) and v.strip() == "")


def split_hosts(raw):
    """'10.0.0.5, 10.0.0.6' -> ['10.0.0.5', '10.0.0.6'], each normalised."""
    out = []
    for part in str(raw or "").split(","):
        h = norm_host(part)
        if h and h not in out:      # a duplicate peer would double every write
            out.append(h)
    return out


def host_slug(host):
    """A host as a variable-name fragment: 10.28.14.210 -> 10_28_14_210."""
    return re.sub(r"[^A-Za-z0-9]+", "_", str(host)).strip("_")


class Peer:
    """One remote ignoAPI, with its OWN connection, clock and failure state.

    Each peer polls on its own thread. With one shared loop a single switched-
    off machine stalls every other peer for the length of its connect timeout,
    twice per retry -- so three peers and one dead machine would make the two
    live ones respond in fits. Separate threads mean a dead peer costs nothing
    but its own retries.
    """

    def __init__(self, host, port, remote_var, variable, interval, timeout):
        self.host = host
        self.port = int(port)
        self.label = f"{host}:{port}"
        self.slug = host_slug(host)
        self.remote_var = remote_var
        self.remote_tx = f"{remote_var}_{TX_SUFFIX}"
        self.remote_rx = f"{remote_var}_{RX_SUFFIX}"
        # Where THIS machine keeps what this peer sends. One box per peer:
        # with several peers a single _rx can only hold one of them, and the
        # other values would be silently overwritten in the same poll --
        # a data loss that looks exactly like a flaky link.
        self.local_rx = f"{variable}_{RX_SUFFIX}_{self.slug}"
        self.api = IgnoApi(host, port, label=self.label)
        self.lock = threading.Lock()          # the poller and the writer share the socket
        self.snapshot = None
        self.up = False
        # Set by Sync once it knows its own address and mode. Empty until
        # then, and an empty marker is never written -- a peer row saying
        # "SYNCED FROM :" would be worse than an unmarked one.
        self.mark_text = ""
        self._marked = None
        self.interval = interval
        self.timeout = timeout
        self.pulse_clear_at = None
        self.sent = 0
        self.recv = 0
        self._stop = False

    # ── the socket, used from two threads ───────────────────────────
    def read_all(self):
        with self.lock:
            return self.api.read_all()

    def write(self, name, value):
        with self.lock:
            return self.api.write(name, value)

    # ── the poller ──────────────────────────────────────────────────
    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while not self._stop:
            snap = self.read_all()
            if snap is None:
                was = self.up
                self.up = False
                self.snapshot = None
                if was:
                    print(f"[sync] {self.label} went DOWN")
                time.sleep(RETRY_SEC)
            else:
                if not self.up:
                    print(f"[sync] {self.label} is UP")
                self.up = True
                self.snapshot = snap
                time.sleep(self.interval)

    def ensure_vars(self):
        """Create this peer's _rx / _tx over there, and say who owns them."""
        snap = self.snapshot if self.snapshot is not None else self.read_all()
        if snap is None:
            return False
        for v in (self.remote_tx, self.remote_rx):
            if v not in snap:
                self.write(v, "")
                print(f"[sync] created {v} on {self.label}")
        self.mark()
        return True

    def mark(self):
        """Write the ownership marker on the peer, only when it CHANGES.

        Unconditionally rewriting it would be one more identical write per
        poll for the life of the program, on a row nobody is watching change.
        """
        if not self.mark_text or self._marked == self.mark_text:
            return
        if self.write(f"{self.remote_var}_{STATUS_SUFFIX}", self.mark_text):
            self._marked = self.mark_text


class Sync:
    def __init__(self, cfg, variable, local, log_path):
        self.cfg = cfg
        self.variable = variable
        self.local = local
        self.log_path = log_path

        remote_var = str(cfg.get("remote_var") or "").strip() or variable
        self.remote_var = remote_var

        hosts = split_hosts(cfg.get("server_ip"))
        raw = str(cfg.get("server_ip") or "").strip()
        if hosts and ",".join(hosts) != raw.replace(" ", ""):
            print(f"[sync] peer address {raw!r} read as {', '.join(hosts)}")
        try:
            interval = max(0.02, float(cfg.get("poll_interval_sec") or 0.1))
        except (TypeError, ValueError):
            interval = 0.1
        try:
            timeout = max(0.5, float(cfg.get("connect_timeout_sec") or 5))
        except (TypeError, ValueError):
            timeout = 5.0
        self.interval = interval
        self.peers = [Peer(h, cfg.get("port") or 8899, remote_var, variable,
                           interval, timeout) for h in hosts]

        self.local_tx = f"{variable}_{TX_SUFFIX}"
        self.local_rx = f"{variable}_{RX_SUFFIX}"
        self.status = f"{variable}_{STATUS_SUFFIX}"
        # The topology view in ignoAPI reads this: "host=UP,host=DOWN".
        self.peers_var = f"{variable}_{PEERS_SUFFIX}"

        mode = str(cfg.get("mode") or MODE_LEVEL).strip().lower()
        self.pulse = mode in (MODE_PULSE, "2", "pulse")
        try:
            self.pulse_s = max(0.02, float(cfg.get("pulse_ms") or 300) / 1000.0)
        except (TypeError, ValueError):
            self.pulse_s = 0.3

        # Tell every peer what to stamp on the rows it creates over there.
        # Done here rather than in Peer.__init__ because the marker names the
        # MODE, which is only decided a few lines above this.
        self._my_ip = my_lan_ip()
        _mark = (f"{REMOTE_MARK}{self._my_ip}:{self.local.port} "
                 f"[{variable}] {'PULSE' if self.pulse else 'LEVEL'}")
        for p in self.peers:
            p.mark_text = _mark

        self._local_clear_at = None
        self._last_status = None
        self._last_peers = None
        self._sent = 0
        self._recv = 0
        self._cmds = 0
        # The answer is written back into the command box, so remember what we
        # put there: without this, a peer value that happens to read like a
        # command would be executed as one on the very next poll.
        self._last_answer = None

    # ── housekeeping ────────────────────────────────────────────────
    @property
    def peer_label(self):
        return ", ".join(p.label for p in self.peers) or "(no peer)"

    def set_status(self, text):
        """Publish status, but only when it CHANGES.

        A status write every poll is a write every 100ms for the life of the
        program, all of it identical -- it would dominate the log and the
        variable's update traffic for no information at all.
        """
        if text == self._last_status:
            return
        self._last_status = text
        self.local.write(self.status, text)

    def publish_peers(self):
        """host=UP,host=DOWN — what the topology diagram draws."""
        text = ",".join(f"{p.host}={'UP' if p.up else 'DOWN'}" for p in self.peers)
        if text != self._last_peers:
            self._last_peers = text
            self.local.write(self.peers_var, text)

    def find_peer(self, token):
        """The peer an address refers to. Accepts the ip, or host:port."""
        t = norm_host(token)
        for p in self.peers:
            if t in (p.host, p.label) or t == f"{p.host}:{p.port}":
                return p
        return None

    def ensure_vars(self):
        snap = self.local.read_all() or {}
        wanted = [self.local_tx, self.local_rx]
        wanted += [p.local_rx for p in self.peers] if len(self.peers) > 1 else []
        for v in wanted:
            if v not in snap:
                self.local.write(v, "")
        ok = False
        for p in self.peers:
            ok = p.ensure_vars() or ok
        return ok

    # ── the two directions ──────────────────────────────────────────
    def push(self, lsnap):
        """local _tx -> every peer's _rx."""
        v = lsnap.get(self.local_tx)
        if is_blank(v):
            return
        live = [p for p in self.peers if p.up]
        if not live:
            return                      # keep it queued until someone answers
        failed = []
        for p in live:
            if p.write(p.remote_rx, v):
                p.sent += 1
                if self.pulse:
                    p.pulse_clear_at = time.time() + self.pulse_s
            else:
                failed.append(p.label)
        if failed:
            # Leave the box alone. Clearing it would report the value as sent
            # when it never reached those machines.
            log_line(self.log_path,
                     f"SEND FAILED to {', '.join(failed)} — kept in {self.local_tx}")
            return
        if len(live) < len(self.peers):
            down = [p.label for p in self.peers if not p.up]
            log_line(self.log_path,
                     f"TX {v!r} -> {len(live)}/{len(self.peers)} peers "
                     f"(down: {', '.join(down)})")
        else:
            log_line(self.log_path, f"TX {self.local_tx} -> all peers: {v!r}")
        self.local.write(self.local_tx, "")
        self._sent += 1

    def pull(self):
        """each peer's _tx -> that peer's own _rx box here."""
        multi = len(self.peers) > 1
        for p in self.peers:
            snap = p.snapshot
            if snap is None:
                continue
            v = snap.get(p.remote_tx)
            if is_blank(v):
                continue
            self.local.write(p.local_rx if multi else self.local_rx, v)
            if multi:
                # Also the plain box, as "most recent from anyone" -- handy
                # when you do not care who sent it. The per-peer box is the
                # one that never loses anything.
                self.local.write(self.local_rx, v)
            p.write(p.remote_tx, "")
            p.recv += 1
            self._recv += 1
            log_line(self.log_path,
                     f"RX {p.label}:{p.remote_tx} -> "
                     f"{p.local_rx if multi else self.local_rx}: {v!r}")
            if self.pulse:
                self._local_clear_at = time.time() + self.pulse_s
                p.pulse_clear_at = time.time() + self.pulse_s

    def expire_pulses(self):
        """Wipe a pulsed value once its window is up. Pulse mode only -- in
        level mode the value is meant to sit there, which is the whole
        difference between the two."""
        now = time.time()
        multi = len(self.peers) > 1
        if self._local_clear_at and now >= self._local_clear_at:
            self._local_clear_at = None
            self.local.write(self.local_rx, "")
            if multi:
                for p in self.peers:
                    self.local.write(p.local_rx, "")
        for p in self.peers:
            if p.pulse_clear_at and now >= p.pulse_clear_at:
                p.pulse_clear_at = None
                if p.up:
                    p.write(p.remote_rx, "")

    # ── commands ────────────────────────────────────────────────────
    def answer(self, text):
        """Put the outcome back in the command box the request came from."""
        self._last_answer = text
        self.local.write(self.variable, text)

    def run_command(self, lsnap):
        """Obey a readData/writeData sitting in the sync's own row."""
        raw = lsnap.get(self.variable)
        if raw is None or str(raw).strip() == "":
            return False
        if self._last_answer is not None and raw == self._last_answer:
            return False          # this is our own answer, not a new request

        try:
            cmd = parse_command(raw, self.find_peer)
        except CommandError as e:
            self.answer(f"ERROR: {e}")
            log_line(self.log_path, f"bad command {raw!r}: {e}")
            return True
        if cmd is None:
            return False          # not a command at all — leave it alone

        kind, name, value, target = cmd
        if target is not None:
            peer = self.find_peer(target)
            if peer is None:
                self.answer(f"ERROR: {target} is not one of this sync's peers "
                            f"({self.peer_label})")
                return True
            peers = [peer]
        else:
            peers = self.peers
        if not peers:
            self.answer("ERROR: this sync has no peers configured")
            return True

        self._cmds += 1
        if kind == "read":
            return self._do_read(name, peers, targeted=target is not None)
        return self._do_write(name, value, peers, targeted=target is not None)

    def _do_read(self, name, peers, targeted):
        """One peer -> the bare value. Several -> one slot each, in order.

        The positional form is the same one a MODBUS multi-read uses, and for
        the same reason: you read the answer by position, so a peer that is
        down or missing the variable has to leave its slot there rather than
        collapse the list.
        """
        # A command reads LIVE, not from the background snapshot. The snapshot
        # is up to one poll old, so a variable written on the peer a moment ago
        # would be reported as "no such variable" -- an answer that is wrong
        # and looks authoritative.
        fresh = {}
        for p in peers:
            got = p.read_all() if p.up else None
            fresh[p.label] = got if got is not None else p.snapshot

        slots, notes = [], []
        for p in peers:
            snap = fresh.get(p.label)
            if snap is None:
                slots.append("DOWN")
                notes.append(f"{p.host} down")
            elif name not in snap:
                slots.append("")
                notes.append(f"{p.host} has no {name!r}")
            else:
                v = snap.get(name)
                slots.append("" if v is None else str(v))
        if len(peers) == 1:
            p = peers[0]
            snap = fresh.get(p.label)
            if snap is None:
                self.answer(f"ERROR: {p.label} is not answering")
            elif name not in snap:
                self.answer(f"ERROR: no variable {name!r} on {p.label}")
            else:
                got = snap.get(name)
                self.answer(got if got is not None else "")
            log_line(self.log_path, f"readData({name}) @ {p.label} -> {slots[0]!r}")
            return True
        out = ",".join(slots)
        self.answer(out)
        log_line(self.log_path,
                 f"readData({name}) x{len(peers)} -> {out!r}"
                 + (f"  [{'; '.join(notes)}]" if notes else ""))
        return True

    def _do_write(self, name, value, peers, targeted):
        done, failed = [], []
        for p in peers:
            snap = p.read_all() if p.up else None
            existed = snap is not None and name in snap
            if not p.up or not p.write(name, value):
                failed.append(p.host)
                continue
            done.append(f"{p.host}({'updated' if existed else 'CREATED'})")
        if failed and not done:
            self.answer(f"ERROR: could not write {name!r} on {', '.join(failed)}")
        elif failed:
            self.answer(f"OK {len(done)}/{len(peers)} — failed: {', '.join(failed)}")
        else:
            self.answer("OK")
        log_line(self.log_path,
                 f"writeData({name},{value!r}) -> " + (", ".join(done) or "nothing")
                 + (f"  FAILED: {', '.join(failed)}" if failed else ""))
        return True

    # ── main loop ───────────────────────────────────────────────────
    def run(self):
        mode_name = "PULSE" if self.pulse else "LEVEL"
        self.set_status("STARTING")
        for p in self.peers:
            p.start()
        created = set()
        while True:
            lsnap = self.local.read_all()
            if lsnap is None:
                self.set_status("LOCAL ignoAPI DOWN")
                time.sleep(RETRY_SEC)
                continue

            # A peer that has just come up (or was restarted with a fresh
            # store) needs its boxes put back, once, rather than on every poll.
            for p in self.peers:
                if p.up and p.snapshot is not None:
                    if (p.remote_tx not in p.snapshot
                            or p.remote_rx not in p.snapshot):
                        p.ensure_vars()
                        created.add(p.host)
                elif not p.up:
                    created.discard(p.host)

            try:
                self.run_command(lsnap)
                self.push(lsnap)
                self.pull()
                self.expire_pulses()
            except Exception as e:                          # never let one bad
                log_line(self.log_path, f"sync error (continuing): {e}")  # poll kill the link

            up = sum(1 for p in self.peers if p.up)
            self.publish_peers()
            if up == 0 and self.peers:
                self.set_status(f"ALL {len(self.peers)} PEER(S) DOWN — {self.peer_label}")
            else:
                self.set_status(
                    f"LIVE {mode_name} {up}/{len(self.peers)} <-> "
                    f"{self.peer_label}:{self.remote_var}  "
                    f"tx={self._sent} rx={self._recv}"
                    + (f" cmd={self._cmds}" if self._cmds else ""))
            time.sleep(self.interval)


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

    local = IgnoApi(cfg.get("ignoapi_host", "127.0.0.1"),
                    cfg.get("ignoapi_port"), label="local ignoAPI")
    sync = Sync(cfg, variable, local, log_path)

    print("=" * 70)
    print(f"  autoSyncIgnoAPI — {get_self_stem()}")
    print(f"  peers    : {len(sync.peers)}")
    for p in sync.peers:
        print(f"             {p.label}   {sync.local_tx} -> {p.remote_rx}"
              f"   |   {p.local_rx if len(sync.peers) > 1 else sync.local_rx}"
              f" <- {p.remote_tx}")
    if cfg.get("mac"):
        print(f"  mac      : {cfg.get('mac')}")
    print("  mode     : " + (f"0x02 PULSE — clears again after {sync.pulse_s * 1000:.0f}ms"
                             if sync.pulse else
                             "0x01 LEVEL — value stays until replaced"))
    print(f"  status   : {sync.status}      peers: {sync.peers_var}")
    print(f"  commands : type into {variable} —")
    for line in COMMAND_HELP.splitlines():
        print("             " + line)
    print("=" * 70)

    # Tray last, so a tray problem can never stop the sync from starting.
    start_tray(get_self_stem(), variable)
    watch_minimise()

    sync.ensure_vars()
    try:
        sync.run()
    except KeyboardInterrupt:
        print("\n[sync] stopping")
        sync.set_status("STOPPED")


if __name__ == "__main__":
    main()
