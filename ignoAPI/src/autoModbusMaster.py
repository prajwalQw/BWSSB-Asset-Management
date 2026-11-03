"""
autoModbusMaster — one Modbus RTU master per ignoAPI variable.

ignoAPI duplicates this program as <variable>_automodbusmaster.exe and writes
<variable>_automodbusmaster.json next to it. Like autoclient, the instance
works out which config to read from its OWN filename, so a single build serves
every variable with no arguments.

WHY THIS IS A SEPARATE PROCESS
    A serial port is exclusive-access: whoever opens it owns it. If ignoAPI
    also drove the port from a thread, the two would simply fight over it, so
    there has to be exactly one owner — and it is this program. Modbus RTU is
    also timing-sensitive (inter-frame gaps, response timeouts), and a
    dedicated process is not competing with a 30fps pygame loop for the GIL.

HOW IT IS DRIVEN
    Five ignoAPI variables, all named after the master's variable (`mag`):

        mag_readReg    "<ids>,<addr>[,<count>]"   read holding register(s)
        mag_readCoil   "<ids>,<addr>[,<count>]"   read coil(s)
        mag_writeReg   "<ids>,<addr>,<value>"     write a holding register
        mag_writeCoil  "<ids>,<addr>,<value>"     write a coil
        mag_status     connection state / errors  (written by us)

    Results land in `mag` itself. See parse_command() for the addressing
    syntax, and the module docstring in ignoAPI for the user-facing summary.

    Writing into one command field CLEARS THE OTHER THREE. Only one command
    is active at a time — the fields are a mode selector, not a queue, and
    leaving a stale command in a field the user has stopped looking at is how
    you get a register written by something you forgot about.

ONE RULE: EVERY COMMAND RUNS ONCE, UNLESS YOU SAY LOOP
    Put a command in a field and it executes exactly once, then the field
    clears itself. That applies to reads and writes alike — the field going
    empty is your receipt that it ran.

    A command left standing would be re-issued several times a second
    forever, which for a register meaning "start", "home" or "reset" is not a
    harmless repeat; and a read that latched by itself meant that merely
    glancing at a register left the master hammering it with nothing on
    screen to say so.

    When you DO want repetition, ask for it:

        mag_writeReg   3,0x1801,0x4002,LOOP
        mag_readReg    1,0x1015,LOOP

    The field is then left in place and the command repeats every poll, at
    the master's own poll_interval_sec, with a live count and rate in
    <var>_status. Clear the field to stop it.

    LOOP is the supported way to drive a register continuously — an external
    script rewriting a one-shot field cannot do it as fast or as evenly,
    because the pacing belongs next to the port rather than a socket away.

pymodbus: this uses the SAME api as pymodbus7_8.py (pymodbus 2.5.3):
    from pymodbus.client.sync import ModbusSerialClient
    client.read_holding_registers(addr, count, unit=id)
    client.write_register(addr, value, unit=id)
Pinning to that is deliberate — pymodbus 3.x renamed `unit` to `slave` and
moved the client module, so code written for one silently fails on the other.
"""
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

try:
    from pymodbus.client.sync import ModbusSerialClient
except ImportError:                                    # pragma: no cover
    ModbusSerialClient = None
    _PYMODBUS_IMPORT_ERROR = sys.exc_info()[1]
else:
    _PYMODBUS_IMPORT_ERROR = None


# Suffixes of the five companion variables. Must match MM_CMD_SUFFIXES and
# mm_status_var() in ignoAPI.py.
CMD_SUFFIXES = ["readReg", "writeReg", "readCoil", "writeCoil"]
STATUS_SUFFIX = "status"

RETRY_SEC = 3.0          # gap between reconnect attempts while the port is down
BROADCAST_ID = 0         # Modbus unit 0 = broadcast; no slave replies


# ──────────────────────────────────────────────────────────────
# SYSTEM TRAY + CONSOLE VISIBILITY
#   Same deal as autoclient: this runs as a console app so its log is
#   readable, but it lives for the whole session and should not have to keep a
#   window on the taskbar. All of it is optional — on a machine without
#   pystray/Pillow, or a non-Windows host, the program runs exactly as before
#   with a plain console. Driving the bus is the job; the tray is a
#   convenience and must never be able to stop it.
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
    ico = os.path.join(get_base_dir(), "autoModbusMaster.ico")
    if os.path.exists(ico):
        try:
            return Image.open(ico)
        except Exception:
            pass
    img = Image.new("RGB", (64, 64), (25, 25, 25))
    d = ImageDraw.Draw(img)
    d.ellipse((14, 14, 50, 50), outline=(60, 230, 170), width=4)   # modbus green
    d.ellipse((26, 26, 38, 38), fill=(60, 230, 170))
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
    _tray_icon = pystray.Icon(stem, image, f"modbus master: {variable}", menu)
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
    """Basename without extension: 'mag_automodbusmaster' for the duplicated
    copy, 'autoModbusMaster' for the original."""
    if getattr(sys, "frozen", False):
        path = os.path.basename(sys.executable)
    else:
        path = os.path.basename(os.path.abspath(__file__))
    return os.path.splitext(path)[0]


def config_path_for(base_dir):
    return os.path.join(base_dir, f"{get_self_stem()}.json")


def derived_variable_name():
    """Variable inferred from the filename (mag_automodbusmaster -> mag), used
    only when the config does not state 'variable'. Case-insensitive on the
    suffix because Windows filenames are."""
    stem = get_self_stem()
    suffix = "_automodbusmaster"
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
    polls several times a second and makes two or three calls per poll, and
    at that rate it dies:

        OSError [WinError 10048] Only one usage of each socket address ...

    Every closed client socket sits in TIME_WAIT for around two minutes and
    Windows has only ~16k ephemeral ports, so a fast poll interval works
    through the whole range and then cannot connect at all -- and because the
    failure looks like "ignoAPI is unreachable", it reads as a problem at the
    other end. Reusing one connection removes it outright, and drops a TCP
    handshake from every call.

    ignoAPI's server reads newline-delimited requests in a loop per
    connection, so this needs nothing special from the other end. It
    reconnects by itself, so an ignoAPI restart is still survivable.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = int(port) if port else 0
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
                raise OSError("ignoAPI closed the connection")
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
                # One reconnect covers the normal case (ignoAPI restarted to
                # change host mode); a second failure means it is genuinely
                # down, and the caller waits rather than spinning.
                self._close()
                if attempt == 2:
                    if not self._warned:
                        # Once, not every poll -- several times a second would
                        # bury everything else in the log.
                        print(f"[modbus] ignoAPI link error: {e}")
                        self._warned = True
                    return None
        return None

    def read_all(self):
        r = self._rpc({"action": "read_all"})
        if r and r.get("status") == "success" and isinstance(r.get("value"), dict):
            return r["value"]
        return None

    def write(self, name, value):
        self._rpc({"action": "create_or_write", "name": name, "value": value})

    def bulk_write(self, data):
        if data:
            self._rpc({"action": "bulk_write", "data": data})


# ──────────────────────────────────────────────────────────────
# COMMAND PARSING
# ──────────────────────────────────────────────────────────────
class CommandError(ValueError):
    """A command string that cannot be executed as written."""


def parse_number(tok):
    """Accept 0x1015, 1015h, 0b1010, or plain decimal.

    int(tok, 0) alone would read a LEADING-ZERO decimal like '0012' as octal
    and quietly return 10 — on a register address that is a wrong-register
    write with no error anywhere.
    """
    t = str(tok).strip().lower().replace("_", "")
    if not t:
        raise CommandError("empty number")
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    try:
        if t.startswith("0x"):
            v = int(t[2:], 16)
        elif t.endswith("h"):
            v = int(t[:-1], 16)
        elif t.startswith("0b"):
            v = int(t[2:], 2)
        else:
            v = int(t, 10)
    except ValueError:
        raise CommandError(f"{tok!r} is not a number (use 1234 or 0x04D2)")
    return -v if neg else v


def parse_ids(tok):
    """'1' -> [1];  '1-4-9' -> [1,4,9];  'b'/'broadcast'/'*' -> [0].

    Returns (ids, is_broadcast).
    """
    t = str(tok).strip().lower()
    if t in ("b", "broadcast", "*", "all"):
        return [BROADCAST_ID], True
    ids = []
    for part in t.split("-"):
        part = part.strip()
        if not part:
            raise CommandError(f"empty device id in {tok!r} (use 1-4-9)")
        v = parse_number(part)
        if not (0 <= v <= 247):
            raise CommandError(f"device id {v} out of range (1-247, or b to broadcast)")
        ids.append(v)
    if not ids:
        raise CommandError("no device id given")
    return ids, False


LOOP_TOKEN = "loop"


def parse_command(kind, raw):
    """Parse one command field into a dict describing what to do.

    kind is one of readReg / writeReg / readCoil / writeCoil.
    Returns None for a blank field. Raises CommandError on anything malformed
    — which is reported to the status variable rather than retried, because a
    typo does not fix itself and retrying it several times a second just fills
    the log.

    Every command runs ONCE and clears its own field. A LOOP token anywhere
    in the command makes it repeat instead:

        3,0x1801,0x4002,LOOP    write 0x4002 every poll, forever
        1,0x1015,LOOP           re-read 0x1015 every poll, forever

    Stop a loop by clearing the field (right-click -> Clear command).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    parts = [p.strip() for p in text.split(",")]
    is_read = kind.startswith("read")
    is_coil = kind.endswith("Coil")

    # Pull LOOP out before anything positional is read, so it does not have to
    # be counted when working out which field is the value or the count.
    #
    # Reads used to be treated as implicitly looping. They are NOT any more:
    # every command, read or write, runs ONCE and clears its own field unless
    # LOOP is given. A read that latched by itself meant that glancing at a
    # register left the master hammering it forever, with no indication that
    # anything had been started -- you had to know to go and clear the field.
    # One rule for everything is both safer and easier to remember.
    loop = any(p.lower() == LOOP_TOKEN for p in parts)
    parts = [p for p in parts if p.lower() != LOOP_TOKEN]

    if len(parts) < 2:
        raise CommandError(
            "expected <ids>,<addr>" + ("[,<count>]" if is_read else ",<value>")
            + f" — got {text!r}")

    ids, broadcast = parse_ids(parts[0])
    addr = parse_number(parts[1])
    if not (0 <= addr <= 0xFFFF):
        raise CommandError(f"address {addr} out of range (0x0000-0xFFFF)")

    if is_read:
        if broadcast:
            # Unit 0 means "every slave, answer nobody". If they all replied
            # at once they would collide on the wire and none would arrive.
            raise CommandError("cannot read from a broadcast — b is for writes only")
        count = 1
        if len(parts) >= 3 and parts[2]:
            count = parse_number(parts[2])
            if count < 1 or count > 125:
                raise CommandError(f"count {count} out of range (1-125)")
            if len(ids) > 1:
                # With several ids the reply is "{id1},{id2},{id3}"; adding a
                # count would make "5,9,3" ambiguous between values and slaves.
                raise CommandError("a count is only allowed with a single device id")
        return {"kind": kind, "ids": ids, "addr": addr, "count": count,
                "coil": is_coil, "read": True, "broadcast": False,
                "loop": loop, "raw": text}

    if len(parts) < 3:
        raise CommandError(f"a write needs a value: <ids>,<addr>,<value> — got {text!r}")
    value = parse_number(parts[2])
    if is_coil:
        # Anything non-zero is ON: a coil is one bit, and rejecting 0x01 or 255
        # here would just be pedantry.
        value = 1 if value else 0
    elif not (0 <= value <= 0xFFFF):
        raise CommandError(f"value {value} out of range for a 16-bit register (0-65535)")
    return {"kind": kind, "ids": ids, "addr": addr, "value": value,
            "coil": is_coil, "read": False, "broadcast": broadcast,
            "loop": loop, "raw": text}


# ──────────────────────────────────────────────────────────────
# THE MASTER
# ──────────────────────────────────────────────────────────────
class ModbusMaster:
    def __init__(self, cfg, variable, api, log_path):
        self.cfg = cfg
        self.variable = variable
        self.api = api
        self.log_path = log_path
        self.client = None
        self.port = str(cfg.get("port", "")).strip()
        self.status_var = f"{variable}_{STATUS_SUFFIX}"
        self.cmd_vars = {suf: f"{variable}_{suf}" for suf in CMD_SUFFIXES}
        self._last_status = None
        self._last_logged = None
        # LOOP bookkeeping: how many iterations of the CURRENT looping command
        # have run, when it started, and when its status was last published.
        self._loop_key = None
        self._loop_n = 0
        self._loop_t0 = 0.0
        self._loop_pub = 0.0

    # ── status ───────────────────────────────────────────────────────
    def set_status(self, text):
        """Publish connection state / errors. Deduplicated: the poll loop runs
        several times a second and would otherwise rewrite an unchanged status
        constantly, making the row flicker and the log unreadable."""
        if text == self._last_status:
            return
        self._last_status = text
        self.api.write(self.status_var, text)

    # ── LOOP bookkeeping ─────────────────────────────────────────────
    def _loop_reset(self):
        self._loop_key = None
        self._loop_n = 0

    def _loop_status(self, cmd, status, ok):
        """Status line for a repeating command, with a live iteration count.

        A completely static status on a LOOP reads as frozen -- you cannot
        tell a master running flat out from one that has hung. So the count
        and rate are appended.

        They are recomputed every iteration but only PUBLISHED about once a
        second: at poll rate a changing string would defeat set_status's
        deduplication, rewrite the variable hundreds of times a minute and
        make the row flicker unreadably. An error is published at once,
        because that is the thing you must not have to wait a second to see.
        """
        key = (cmd["kind"], cmd["raw"])
        now = time.time()
        if key != self._loop_key:
            self._loop_key = key
            self._loop_n = 0
            self._loop_t0 = now
            self._loop_pub = 0.0
        self._loop_n += 1

        elapsed = max(now - self._loop_t0, 1e-6)
        text = f"{status}  (LOOP #{self._loop_n}, {self._loop_n / elapsed:.1f}/s)"
        if ok and (now - self._loop_pub) < 1.0:
            return self._last_status if self._last_status is not None else text
        self._loop_pub = now
        return text

    # ── connection ───────────────────────────────────────────────────
    def connect(self):
        if ModbusSerialClient is None:
            self.set_status(f"ERROR: pymodbus not installed ({_PYMODBUS_IMPORT_ERROR})")
            return False
        try:
            self.client = ModbusSerialClient(
                method="rtu",
                port=self.port,
                baudrate=int(self.cfg.get("baud", 38400) or 38400),
                parity=str(self.cfg.get("parity", "N") or "N")[:1].upper(),
                stopbits=int(self.cfg.get("stopbits", 1) or 1),
                bytesize=int(self.cfg.get("bytesize", 8) or 8),
                timeout=float(self.cfg.get("timeout_sec", 1.0) or 1.0),
            )
            if not self.client.connect():
                self.client = None
                self.set_status(f"DISCONNECTED {self.port}: port did not open "
                                f"(not present, or already open in another program)")
                return False
        except Exception as e:
            self.client = None
            self.set_status(f"DISCONNECTED {self.port}: {explain(e, self.port)}")
            return False
        self.set_status(f"CONNECTED {self.port} @ {self.cfg.get('baud')} "
                        f"{self.cfg.get('bytesize', 8)}{self.cfg.get('parity', 'N')}"
                        f"{self.cfg.get('stopbits', 1)}")
        log_line(self.log_path, f"connected on {self.port}")
        return True

    def disconnect(self):
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None

    # ── one transaction ──────────────────────────────────────────────
    def _read_one(self, unit, addr, count, coil):
        """Read from one slave. Returns (ok, value_or_error_text)."""
        try:
            if coil:
                rr = self.client.read_coils(addr, count, unit=unit)
            else:
                rr = self.client.read_holding_registers(addr, count, unit=unit)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if rr is None:
            return False, "no response"
        if rr.isError():
            # An exception RESPONSE (illegal address/function) is a different
            # fault from silence (wrong id, wrong baud, unplugged) and they
            # need different fixes, so keep the drive's own words.
            return False, str(rr)
        try:
            vals = list(rr.bits[:count]) if coil else list(rr.registers[:count])
        except Exception as e:
            return False, f"malformed reply: {e}"
        if coil:
            vals = [1 if v else 0 for v in vals]
        return True, vals

    def _write_one(self, unit, addr, value, coil):
        try:
            if coil:
                wr = self.client.write_coil(addr, bool(value), unit=unit)
            else:
                wr = self.client.write_register(addr, value, unit=unit)
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        if unit == BROADCAST_ID:
            # Nothing answers a broadcast, so there is nothing to check. Any
            # non-exception return means the frame went out.
            return True, "broadcast sent"
        if wr is None:
            return False, "no response"
        if wr.isError():
            return False, str(wr)
        return True, "ok"

    # ── run one parsed command ───────────────────────────────────────
    def execute(self, cmd):
        """Run one command. Returns (value_for_variable, status_text, ok)."""
        if cmd["read"]:
            results = []
            errors = []
            for unit in cmd["ids"]:
                ok, out = self._read_one(unit, cmd["addr"], cmd["count"], cmd["coil"])
                if ok:
                    # A single id with count 1 reports a bare value; anything
                    # else is comma-joined, so "{id1},{id2},{id3}" and a
                    # multi-register read read the same way.
                    results.extend(str(v) for v in out)
                else:
                    # ERR keeps the POSITION, so with 1-4-9 you can still tell
                    # which slave failed. Dropping it would silently shift
                    # every later value one slot to the left.
                    results.append("ERR")
                    errors.append(f"id {unit}: {out}")
            value = results[0] if len(results) == 1 else ",".join(results)
            what = ("coil" if cmd["coil"] else "reg")
            ids_txt = "-".join(str(i) for i in cmd["ids"])
            if errors:
                return value, (f"ERROR {cmd['kind']} {what} 0x{cmd['addr']:04X} "
                               f"[{ids_txt}]: " + "; ".join(errors)), False
            return value, (f"OK {cmd['kind']} {what} 0x{cmd['addr']:04X} "
                           f"[{ids_txt}] -> {value}"), True

        errors = []
        for unit in cmd["ids"]:
            ok, out = self._write_one(unit, cmd["addr"], cmd["value"], cmd["coil"])
            if not ok:
                errors.append(f"id {unit}: {out}")
        what = ("coil" if cmd["coil"] else "reg")
        ids_txt = "broadcast" if cmd["broadcast"] else "-".join(str(i) for i in cmd["ids"])
        if errors:
            return None, (f"ERROR {cmd['kind']} {what} 0x{cmd['addr']:04X} "
                          f"[{ids_txt}] = {cmd['value']}: " + "; ".join(errors)), False
        return None, (f"OK {cmd['kind']} {what} 0x{cmd['addr']:04X} "
                      f"[{ids_txt}] = {cmd['value']}"), True

    # ── main loop ────────────────────────────────────────────────────
    def run(self):
        interval = float(self.cfg.get("poll_interval_sec", 0.2) or 0.2)
        while True:
            if self.client is None:
                if not self.connect():
                    time.sleep(RETRY_SEC)
                    continue

            snapshot = self.api.read_all()
            if snapshot is None:
                # ignoAPI is unreachable — there is nothing to obey and
                # nowhere to report, so wait rather than spin.
                time.sleep(max(interval, 0.5))
                continue

            active = self._pick_active(snapshot)
            if active is None:
                self.set_status(self._idle_status())
                time.sleep(interval)
                continue

            suffix, raw = active
            try:
                cmd = parse_command(suffix, raw)
            except CommandError as e:
                # A malformed command is cleared, not retried: it cannot fix
                # itself, and leaving it in place would repeat the same error
                # several times a second forever.
                self.set_status(f"ERROR {self.cmd_vars[suffix]}: {e}")
                log_line(self.log_path, f"bad command in {self.cmd_vars[suffix]}: {raw!r} — {e}")
                self.api.write(self.cmd_vars[suffix], "")
                time.sleep(interval)
                continue
            if cmd is None:
                time.sleep(interval)
                continue

            try:
                value, status, ok = self.execute(cmd)
            except Exception as e:
                # Anything unexpected is treated as a lost link: drop the
                # client so the next pass reconnects from scratch.
                self.set_status(f"LINK LOST {self.port}: {type(e).__name__}: {e}")
                log_line(self.log_path, f"link lost: {e}")
                self.disconnect()
                time.sleep(RETRY_SEC)
                continue

            updates = {}
            if value is not None:
                updates[self.variable] = value
            # Clear the three fields that are not the active one, so exactly
            # one command is ever live.
            for suf, var in self.cmd_vars.items():
                if suf != suffix and str(snapshot.get(var, "")).strip():
                    updates[var] = ""
            if not cmd["loop"]:
                # A plain write is ONE-SHOT: clear the field that fired, so it
                # cannot be re-issued several times a second forever. With
                # LOOP the field stays put and this is exactly what repeats.
                updates[self.cmd_vars[suffix]] = ""
            self.api.bulk_write(updates)

            if cmd["loop"]:
                self.set_status(self._loop_status(cmd, status, ok))
            else:
                self._loop_reset()
                self.set_status(status)

            # Log one-shots and failures. A healthy LOOP is logged only when
            # its status text CHANGES -- at poll rate it would otherwise be
            # thousands of identical lines an hour, which buries the one line
            # that matters when it starts failing.
            if not ok or not cmd["loop"] or status != self._last_logged:
                log_line(self.log_path, status)
                self._last_logged = status

            time.sleep(interval)

    def _pick_active(self, snapshot):
        """The one command field that is non-empty, as (suffix, raw).

        If several are filled (an API client wrote two at once), the FIRST in
        CMD_SUFFIXES order wins and the rest are cleared by the caller — a
        deterministic choice beats running whichever the dict happened to
        yield first.
        """
        for suf in CMD_SUFFIXES:
            raw = snapshot.get(self.cmd_vars[suf])
            if raw is not None and str(raw).strip():
                return suf, raw
        return None

    def _idle_status(self):
        return (f"CONNECTED {self.port} @ {self.cfg.get('baud')} — idle "
                f"(fill {self.variable}_readReg, _writeReg, _readCoil or _writeCoil)")


def explain(exc, port):
    """Turn a pyserial/pymodbus error into something actionable.

    'Access is denied' on Windows almost never means a permissions problem —
    it means the port is ALREADY OPEN somewhere else, because Windows COM
    ports are exclusive-access.
    """
    msg = str(exc)
    low = msg.lower()
    if "permission" in low or "access is denied" in low or "errno 13" in low:
        return (f"PORT BUSY — {port} is already open in another program "
                f"(a second master, a terminal, the drive's own tool). [{msg}]")
    if "filenotfound" in low or "could not open port" in low:
        return f"PORT NOT FOUND — {port} is not plugged in. [{msg}]"
    return msg


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

    api = IgnoApi(cfg.get("ignoapi_host"), cfg.get("ignoapi_port"))

    print("=" * 62)
    print(f"  autoModbusMaster — {get_self_stem()}")
    print(f"  variable : {variable}")
    print(f"  port     : {cfg.get('port')} @ {cfg.get('baud')} "
          f"{cfg.get('bytesize', 8)}{cfg.get('parity', 'N')}{cfg.get('stopbits', 1)}")
    print(f"  commands : " + ", ".join(f"{variable}_{s}" for s in CMD_SUFFIXES))
    print(f"  status   : {variable}_{STATUS_SUFFIX}")
    print("=" * 62)

    # Tray last, so a tray problem can never stop the master from starting.
    start_tray(get_self_stem(), variable)
    watch_minimise()

    master = ModbusMaster(cfg, variable, api, log_path)
    try:
        master.run()
    except KeyboardInterrupt:
        print("\n[modbus] stopping")
    finally:
        master.disconnect()


if __name__ == "__main__":
    main()
