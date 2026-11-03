"""
autoModbusSlave — a Modbus RTU SLAVE backed by ignoAPI variables.

ignoAPI duplicates this program as <variable>_automodbusslave.exe and writes
<variable>_automodbusslave.json next to it. Like autocom and
autoModbusMaster, the instance works out which config to read from its OWN
filename, so one build serves every slave with no arguments.

(Named "slave" rather than "client": in Modbus the device that ANSWERS is the
slave, also called the server. A file called ...client next to
autoModbusMaster.py would read as the opposite of what it is.)

WHAT IT DOES
    A master on the bus reads and writes registers and coils. This program
    answers, and the values it answers with ARE ignoAPI variables — so a
    register is visible and editable in the ignoAPI table, and a master
    writing to it updates the row in front of you.

THE REGISTER MAP
    A CSV, chosen from a file dialog when the slave is created:

        0x0001,1000
        0x1012,2000
        0x1045                  <- no value: starts at 0
        0x0005,1,coil           <- third column selects the table
        # anything after a hash is a comment

    Addresses may be hex (0x0001) or decimal. The optional third column is
    `reg` (default, holding register) or `coil`. Each entry becomes a
    variable under the parent name:

        mag_reg_0x0001  = 1000
        mag_coil_0x0005 = 1

    The type is in the NAME because a coil and a register may share an
    address — they are separate address spaces in Modbus, and mag_0x0001
    alone could not say which one a master had asked for.

WHY A LOCAL CACHE
    A Modbus master expects an answer within milliseconds. Fetching each
    value from ignoAPI inside the response path would put a TCP round-trip in
    the middle of an RTU frame and blow the timeout. So values are mirrored
    into a local dict, refreshed by a background thread, and answers come
    from the mirror. Writes go the other way: applied to the mirror at once
    (so the next read is consistent) and pushed to ignoAPI asynchronously.

pymodbus: same version and api as pymodbus7_8.py (2.5.3) —
    from pymodbus.server.sync import StartSerialServer
    from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
3.x reorganised all of this, so the pin matters.
"""
import csv
import json
import os
import socket
import sys
import threading
import time
from datetime import datetime

try:
    from pymodbus.server.sync import StartSerialServer
    from pymodbus.datastore import (ModbusSparseDataBlock, ModbusSlaveContext,
                                    ModbusServerContext)
    from pymodbus.device import ModbusDeviceIdentification
except ImportError:                                    # pragma: no cover
    StartSerialServer = None
    _PYMODBUS_IMPORT_ERROR = sys.exc_info()[1]
else:
    _PYMODBUS_IMPORT_ERROR = None


STATUS_SUFFIX = "status"
REG_PREFIX = "reg"
COIL_PREFIX = "coil"

MIRROR_REFRESH_SEC = 0.2      # how often the cache is re-read from ignoAPI


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
    """mag_automodbusslave -> mag. Case-insensitive: Windows filenames are."""
    stem = get_self_stem()
    suffix = "_automodbusslave"
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


def log_line(log_path, text):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}"
    print(line)
    if not log_path:
        return
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ──────────────────────────────────────────────────────────────
# THE REGISTER MAP
# ──────────────────────────────────────────────────────────────
class MapError(ValueError):
    """A register-map CSV that cannot be used as written."""


def parse_address(tok):
    """0x0001 / 1045h / 4097 -> int.

    int(tok, 0) alone would read a LEADING-ZERO decimal like '0012' as octal
    and quietly return 10 — a wrong register with no error anywhere.
    """
    t = str(tok).strip().lower().replace("_", "")
    if not t:
        raise MapError("empty address")
    try:
        if t.startswith("0x"):
            return int(t[2:], 16)
        if t.endswith("h"):
            return int(t[:-1], 16)
        return int(t, 10)
    except ValueError:
        raise MapError(f"{tok!r} is not an address (use 0x0001 or 4097)")


def var_name(variable, kind, addr):
    """mag + reg + 1 -> 'mag_reg_0x0001'.

    The address is formatted back to 4-digit hex rather than echoed, so
    '0x1', '1' and '0x0001' in the CSV all name the SAME variable instead of
    three rows that a master cannot tell apart.
    """
    return f"{variable}_{kind}_0x{addr:04X}"


def load_register_map(path):
    """Read the CSV into [(kind, address, initial_value), ...].

    Tolerant on purpose -- this file is hand-written and often pasted from a
    drive manual: blank lines, # comments, a header row, hex or decimal, and
    a missing value column are all accepted. What is NOT accepted is a
    duplicate (kind, address), because two variables would then claim the
    same register and which one a master saw would depend on dict ordering.
    """
    if not path or not os.path.exists(path):
        raise MapError(f"register map not found: {path!r}")

    entries = []
    seen = {}
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        for lineno, row in enumerate(csv.reader(f), 1):
            if not row:
                continue
            cells = [c.strip() for c in row]
            if not cells[0] or cells[0].lstrip().startswith("#"):
                continue
            # A header row ("address,value") is common when the file came out
            # of a spreadsheet; skip it rather than failing on line 1.
            if lineno == 1 and not cells[0][:1].isdigit():
                low = cells[0].lower()
                if low.startswith(("addr", "reg", "register")) and len(cells) > 1:
                    continue

            try:
                addr = parse_address(cells[0])
            except MapError as e:
                raise MapError(f"line {lineno}: {e}")
            if not (0 <= addr <= 0xFFFF):
                raise MapError(f"line {lineno}: address 0x{addr:X} out of range "
                               f"(0x0000-0xFFFF)")

            value = 0
            if len(cells) > 1 and cells[1]:
                try:
                    value = parse_address(cells[1])
                except MapError:
                    raise MapError(f"line {lineno}: {cells[1]!r} is not a value")

            kind = REG_PREFIX
            if len(cells) > 2 and cells[2]:
                k = cells[2].strip().lower()
                if k in ("coil", "coils", "c", "bit"):
                    kind = COIL_PREFIX
                elif k in ("reg", "register", "registers", "r", "hr", "holding"):
                    kind = REG_PREFIX
                else:
                    raise MapError(f"line {lineno}: {cells[2]!r} is not a type "
                                   f"(use 'reg' or 'coil')")

            if kind == COIL_PREFIX:
                value = 1 if value else 0
            elif not (0 <= value <= 0xFFFF):
                raise MapError(f"line {lineno}: value {value} does not fit in a "
                               f"16-bit register (0-65535)")

            key = (kind, addr)
            if key in seen:
                raise MapError(f"line {lineno}: {kind} 0x{addr:04X} is already "
                               f"defined on line {seen[key]} -- two variables "
                               f"cannot serve the same register")
            seen[key] = lineno
            entries.append((kind, addr, value))

    if not entries:
        raise MapError(f"{os.path.basename(path)} defines no registers")
    return entries


# ──────────────────────────────────────────────────────────────
# ignoAPI LINK
# ──────────────────────────────────────────────────────────────
class IgnoApi:
    """Line-JSON client for ignoAPI over ONE PERSISTENT connection.

    Connection-per-call exhausts Windows' ~16k ephemeral ports at any real
    rate (every closed socket sits in TIME_WAIT for ~2 minutes) and then
    fails in a way that reads as "ignoAPI is unreachable". One socket, held
    open, reconnecting by itself.
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
                            print(f"[slave] ignoAPI link error: {e}")
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
# THE DATASTORE
# ──────────────────────────────────────────────────────────────
def _coerce(raw, coil):
    """Turn a variable's value (which the user may have typed) into a number
    the Modbus layer can serve. Anything unparseable reads as 0 rather than
    raising -- a typo in one row must not take the whole bus down."""
    if raw is None:
        return 0
    if isinstance(raw, bool):
        return 1 if raw else 0
    try:
        if isinstance(raw, (int, float)):
            v = int(raw)
        else:
            t = str(raw).strip()
            if not t:
                return 0
            v = parse_address(t)
    except (MapError, ValueError, TypeError):
        return 0
    if coil:
        return 1 if v else 0
    return max(0, min(0xFFFF, v))


class VariableBlock(ModbusSparseDataBlock):
    """A sparse Modbus data block whose values ARE ignoAPI variables.

    Sparse rather than sequential because the map is scattered -- 0x0001,
    0x1012, 0x1045 -- and a sequential block would have to allocate every
    address in between and would happily answer for registers the CSV never
    mentioned.

    getValues answers from the mirror, never from the network: a master's
    response deadline is milliseconds and a TCP round-trip inside the frame
    would blow it.
    """

    def __init__(self, slave, kind, addresses):
        self.slave = slave
        self.kind = kind
        self.coil = (kind == COIL_PREFIX)
        # ModbusSparseDataBlock indexes by the address the master sends.
        super().__init__({a: 0 for a in addresses} or {0: 0})
        self._addrs = set(addresses)

    def validate(self, address, count=1):
        """Only answer for addresses the CSV actually defines.

        The default sparse block answers for anything it holds; being strict
        here means a master reading an undefined register gets a proper
        ILLEGAL DATA ADDRESS exception instead of a silent zero, which is the
        difference between "your map is wrong" and "the device says 0".
        """
        return all((address + i) in self._addrs for i in range(count))

    def getValues(self, address, count=1):
        out = []
        for i in range(count):
            a = address + i
            out.append(self.slave.get(self.kind, a))
        return out

    def setValues(self, address, values):
        """A master wrote to us: update the mirror now, ignoAPI shortly after.

        The mirror is updated synchronously so an immediate read-back is
        consistent; the push to ignoAPI is queued because it must not happen
        inside the RTU response window.
        """
        if not isinstance(values, (list, tuple)):
            values = [values]
        for i, v in enumerate(values):
            self.slave.set_from_master(self.kind, address + i, v)


class Slave:
    """Owns the mirror, the ignoAPI sync, and the two data blocks."""

    def __init__(self, cfg, variable, api, entries, log_path):
        self.cfg = cfg
        self.variable = variable
        self.api = api
        self.log_path = log_path
        self.status_var = f"{variable}_{STATUS_SUFFIX}"
        self.persist = bool(cfg.get("persist_csv"))
        self.map_file = cfg.get("register_map") or ""

        self._lock = threading.Lock()
        self._mirror = {}            # (kind, addr) -> int
        self._names = {}             # (kind, addr) -> variable name
        self._pending = {}           # variable name -> value, waiting to be pushed
        self._dirty = False          # a master wrote; the CSV needs rewriting
        self._last_status = None
        self.writes_seen = 0
        self.reads_seen = 0

        for kind, addr, value in entries:
            self._mirror[(kind, addr)] = value
            self._names[(kind, addr)] = var_name(variable, kind, addr)

    # ── mirror access ────────────────────────────────────────────────
    def get(self, kind, addr):
        with self._lock:
            self.reads_seen += 1
            return self._mirror.get((kind, addr), 0)

    def set_from_master(self, kind, addr, value):
        key = (kind, addr)
        name = self._names.get(key)
        if name is None:
            return                      # not in the map; validate() rejects it
        v = _coerce(value, kind == COIL_PREFIX)
        with self._lock:
            self._mirror[key] = v
            self._pending[name] = v
            self._dirty = True
            self.writes_seen += 1
        log_line(self.log_path, f"master wrote {kind} 0x{addr:04X} = {v}  ({name})")

    # ── ignoAPI sync ─────────────────────────────────────────────────
    def publish_initial(self):
        """Create every register variable with its CSV value."""
        data = {}
        for key, name in self._names.items():
            data[name] = self._mirror[key]
        self.api.bulk_write(data)
        print(f"[slave] published {len(data)} register variables")

    def sync_loop(self):
        """Keep the mirror and ignoAPI in step, both directions.

        Master writes are pushed FIRST, then the snapshot is read back. That
        order matters: doing it the other way round would read a stale
        snapshot and overwrite the value a master had just written, silently
        undoing it.
        """
        while True:
            try:
                with self._lock:
                    pending, self._pending = self._pending, {}
                if pending:
                    self.api.bulk_write(pending)

                snapshot = self.api.read_all()
                if snapshot is not None:
                    with self._lock:
                        for key, name in self._names.items():
                            if name in pending:
                                continue        # we just wrote it; do not fight
                            if name in snapshot:
                                self._mirror[key] = _coerce(
                                    snapshot[name], key[0] == COIL_PREFIX)

                if self._dirty and self.persist:
                    self.save_csv()
            except Exception as e:
                print(f"[slave] sync error: {e}")
            time.sleep(MIRROR_REFRESH_SEC)

    def save_csv(self):
        """Write the live values back over the register map.

        OFF unless persist_csv is set. Left off by default deliberately: the
        CSV is something you hand-write and may keep in version control, and
        a slave silently rewriting it every time a master pokes a register is
        a surprise. Turn it on when you want the map to survive a restart
        with whatever the master last wrote.
        """
        if not self.map_file:
            return
        tmp = self.map_file + ".tmp"
        try:
            with self._lock:
                rows = [(k, a, self._mirror[(k, a)]) for (k, a) in sorted(
                    self._mirror, key=lambda x: (x[0], x[1]))]
                self._dirty = False
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["# written by autoModbusSlave -- live values"])
                for kind, addr, value in rows:
                    w.writerow([f"0x{addr:04X}", value, kind])
            os.replace(tmp, self.map_file)
        except OSError as e:
            print(f"[slave] could not save the register map: {e}")

    # ── status ───────────────────────────────────────────────────────
    def set_status(self, text):
        """Deduplicated -- the heartbeat would otherwise rewrite an unchanged
        status several times a second and make the row flicker."""
        if text != self._last_status:
            self._last_status = text
            self.api.write(self.status_var, text)

    def heartbeat_loop(self, port, unit):
        while True:
            with self._lock:
                r, w = self.reads_seen, self.writes_seen
            self.set_status(
                f"LISTENING {port} @ {self.cfg.get('baud')} as id {unit} — "
                f"{len(self._names)} registers, {r} reads, {w} writes")
            time.sleep(1.0)

    # ── the server ───────────────────────────────────────────────────
    def build_context(self, unit):
        regs = sorted(a for (k, a) in self._mirror if k == REG_PREFIX)
        coils = sorted(a for (k, a) in self._mirror if k == COIL_PREFIX)
        store = ModbusSlaveContext(
            hr=VariableBlock(self, REG_PREFIX, regs),
            ir=VariableBlock(self, REG_PREFIX, regs),   # input regs mirror holding
            co=VariableBlock(self, COIL_PREFIX, coils),
            di=VariableBlock(self, COIL_PREFIX, coils), # discrete inputs mirror coils
            zero_mode=True,     # address N means register N, not N+1
        )
        return ModbusServerContext(slaves={unit: store}, single=False)


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
    status_var = f"{variable}_{STATUS_SUFFIX}"

    if StartSerialServer is None:
        api.write(status_var, f"ERROR: pymodbus not installed ({_PYMODBUS_IMPORT_ERROR})")
        print(f"[fatal] pymodbus not available: {_PYMODBUS_IMPORT_ERROR}")
        sys.exit(1)

    try:
        entries = load_register_map(cfg.get("register_map"))
    except MapError as e:
        # A bad map is fatal and must SAY SO in the table: starting a slave
        # that answers for nothing looks identical to a wiring fault.
        api.write(status_var, f"ERROR in register map: {e}")
        print(f"[fatal] {e}")
        sys.exit(1)

    unit = int(cfg.get("slave_id", 1) or 1)
    port = str(cfg.get("port", "")).strip()

    slave = Slave(cfg, variable, api, entries, log_path)
    slave.publish_initial()

    n_reg = sum(1 for k, _, _ in entries if k == REG_PREFIX)
    n_coil = len(entries) - n_reg
    print("=" * 66)
    print(f"  autoModbusSlave — {get_self_stem()}")
    print(f"  variable  : {variable}")
    print(f"  slave id  : {unit}")
    print(f"  port      : {port} @ {cfg.get('baud')} "
          f"{cfg.get('bytesize', 8)}{cfg.get('parity', 'N')}{cfg.get('stopbits', 1)}")
    print(f"  map       : {os.path.basename(cfg.get('register_map') or '?')} "
          f"-- {n_reg} registers, {n_coil} coils")
    persist_txt = ("yes -- master writes are saved back to the CSV"
                   if slave.persist else "no (the CSV is the initial map only)")
    print(f"  persist   : {persist_txt}")
    print("=" * 66)

    threading.Thread(target=slave.sync_loop, daemon=True).start()
    threading.Thread(target=slave.heartbeat_loop, args=(port, unit), daemon=True).start()

    identity = ModbusDeviceIdentification()
    identity.VendorName = "ignoAPI"
    identity.ProductName = "autoModbusSlave"
    identity.ModelName = variable

    context = slave.build_context(unit)
    while True:
        try:
            slave.set_status(f"STARTING {port} @ {cfg.get('baud')} as id {unit}")
            # Blocks until the port dies.
            StartSerialServer(
                context, identity=identity, port=port,
                baudrate=int(cfg.get("baud", 38400) or 38400),
                parity=str(cfg.get("parity", "N") or "N")[:1].upper(),
                stopbits=int(cfg.get("stopbits", 1) or 1),
                bytesize=int(cfg.get("bytesize", 8) or 8),
                timeout=float(cfg.get("timeout_sec", 1.0) or 1.0),
            )
            slave.set_status(f"STOPPED {port} — the server returned")
        except KeyboardInterrupt:
            print("\n[slave] stopping")
            return
        except Exception as e:
            msg = str(e)
            if "permission" in msg.lower() or "access is denied" in msg.lower():
                # On Windows a COM port is exclusive-access: this almost never
                # means a permissions problem, it means something else has the
                # port open.
                msg = (f"PORT BUSY — {port} is already open in another program "
                       f"(a master, a terminal, a second slave). [{msg}]")
            slave.set_status(f"DISCONNECTED {port}: {msg}")
            log_line(log_path, f"server error: {e}")
        time.sleep(3.0)


if __name__ == "__main__":
    main()
