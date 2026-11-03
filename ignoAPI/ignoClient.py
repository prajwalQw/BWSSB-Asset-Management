"""
ignoClient.py — Thread-safe TCP client for ignoAPI server.

Design:
- One persistent socket per OS thread (thread-local storage).
- Auto-reconnect on broken connection — transparent to caller.
- If server is completely unreachable → raises RuntimeError (hard fail).

FIX: Added igo_bulk_write() — single TCP call for many keys (replaces hot loops).
FIX: Added igo_read_all() + background sync thread + fast_read() cache.
     The control loop (10ms) uses fast_read() — zero TCP latency.
     A background thread syncs from server every CACHE_SYNC_INTERVAL seconds.

Public API:
    igo_create(name, value)
    igo_write(name, value)
    igo_create_or_write(name, value)
    igo_bulk_write(data_dict)           ← NEW: single TCP call, many keys
    igo_read(name, fallback=None)
    igo_read_all()                      ← NEW: fetch full snapshot
    igo_delete(name)

Configuring another ignoAPI (one call, one connection, by mDNS name):
    findIgnoAPIs()                      — every ignoAPI on the network
    listModules(host, port)             — what is configured over there
    createAutoClient(host, port, name, server_ip, server_port, command, ...)
    createComClient(host, port, name, com_port, baud, ...)
    createModbusMaster(host, port, name, com_port, baud, ...)
    createModbusSlave(host, port, name, com_port, register_map, ...)
    createSyncIgnoAPI(host, port, name, peers, topology, ...)
    createFTP(host, port, name, folder, ftp_port, user, pass, sharing, ...)
    combineVar(host, port, name, var1, var2, ...)
    deleteModule(host, port, name)      — and everything it owns

Cache API (zero-latency, use in control loops):
    start_cache_sync()                  ← call once at startup
    fast_read(key, fallback=None)       ← reads from local cache
    fast_write(key, value)              ← writes to cache + queues server write
    get_cache_age()                     ← seconds since last successful sync
"""

import json
import socket
import threading
import time
from hardwareCSV import API_PORT
# ──────────────────────────────────────────────────────────────
# CONFIG — must match ignoAPI.py
# ──────────────────────────────────────────────────────────────
SERVER_HOST        = '127.0.0.1'
SERVER_PORT        = API_PORT
CONNECT_TIMEOUT    = 2.0    # seconds
RECV_TIMEOUT       = 3.0    # seconds
CACHE_SYNC_INTERVAL = 0.01  # 10ms — background cache refresh rate

# ──────────────────────────────────────────────────────────────
# THREAD-LOCAL SOCKET
# ──────────────────────────────────────────────────────────────
_thread_local = threading.local()


def _get_socket():
    sock = getattr(_thread_local, 'sock', None)
    if sock is not None:
        return sock
    return _connect()


def _connect():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(CONNECT_TIMEOUT)
        s.connect((SERVER_HOST, SERVER_PORT))
        s.settimeout(RECV_TIMEOUT)
        _thread_local.sock = s
        _thread_local.buf  = ""
        return s
    except (ConnectionRefusedError, OSError, socket.timeout) as e:
        _thread_local.sock = None
        raise RuntimeError(
            f"[ignoClient] Cannot connect to ignoAPI at {SERVER_HOST}:{SERVER_PORT} — {e}\n"
            "Make sure ignoAPI.py is running before starting."
        ) from e


def _close_socket():
    s = getattr(_thread_local, 'sock', None)
    if s:
        try:
            s.close()
        except OSError:
            pass
    _thread_local.sock = None
    _thread_local.buf  = ""


def _send(action, name, value=None):
    """
    Send one JSON request, return the parsed response dict.
    Auto-reconnects once on socket error.
    """
    req = {"action": action, "name": name}
    if value is not None:
        req["value"] = value
    payload = (json.dumps(req) + '\n').encode('utf-8')

    for attempt in range(2):
        try:
            sock = _get_socket()
            sock.sendall(payload)
            buf = getattr(_thread_local, 'buf', "")
            while '\n' not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionResetError("Server closed connection")
                buf += chunk.decode('utf-8')
            line, buf = buf.split('\n', 1)
            _thread_local.buf = buf
            return json.loads(line.strip())
        except (OSError, ConnectionResetError, socket.timeout, json.JSONDecodeError) as e:
            _close_socket()
            if attempt == 1:
                raise RuntimeError(
                    f"[ignoClient] Communication error with ignoAPI: {e}"
                ) from e
    return None


def _send_raw(payload_bytes):
    """Send raw bytes (used for bulk_write / read_all)."""
    for attempt in range(2):
        try:
            sock = _get_socket()
            sock.sendall(payload_bytes)
            buf = getattr(_thread_local, 'buf', "")
            while '\n' not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    raise ConnectionResetError("Server closed connection")
                buf += chunk.decode('utf-8')
            line, buf = buf.split('\n', 1)
            _thread_local.buf = buf
            return json.loads(line.strip())
        except (OSError, ConnectionResetError, socket.timeout, json.JSONDecodeError) as e:
            _close_socket()
            if attempt == 1:
                raise RuntimeError(
                    f"[ignoClient] Communication error with ignoAPI: {e}"
                ) from e
    return None


# ──────────────────────────────────────────────────────────────
# PUBLIC API
# ──────────────────────────────────────────────────────────────

def igo_create(name, value):
    with _write_queue_lock:
        _write_queue.pop(name, None)
    resp = _send("create", name, value)
    if resp and resp.get("status") == "error":
        print(f"[ignoClient] create '{name}': {resp['message']}")


def igo_write(name, value):
    with _write_queue_lock:
        _write_queue.pop(name, None)
    resp = _send("write", name, value)
    if resp and resp.get("status") == "error":
        print(f"[ignoClient] write '{name}': {resp['message']}")


def igo_create_or_write(name, value):
    """Upsert — recommended for robot control loop."""
    with _write_queue_lock:
        _write_queue.pop(name, None)
    resp = _send("create_or_write", name, value)
    if resp and resp.get("status") == "error":
        print(f"[ignoClient] create_or_write '{name}': {resp['message']}")


def igo_bulk_write(data: dict):
    """
    Write multiple keys in a single TCP call.
    Use this in hardware update loops to replace N individual igo_create_or_write calls.

    Example:
        igo_bulk_write({
            "a_id": None,
            "a_x": 12.5,
            "a_y": -3.2,
        })
    """
    req = {"action": "bulk_write", "name": "bulk", "data": data}
    payload = (json.dumps(req) + '\n').encode('utf-8')
    resp = _send_raw(payload)
    if resp and resp.get("status") == "error":
        print(f"[ignoClient] bulk_write error: {resp['message']}")


def igo_read(name, fallback=None):
    """
    Read a variable from the server.
    Returns fallback (default None) if not found.
    Raises RuntimeError if server unreachable.
    """
    resp = _send("read", name)
    if resp is None:
        return fallback
    if resp.get("status") == "success":
        return resp.get("value")
    return fallback


def igo_read_all():
    """
    Fetch the entire variable store as a dict in a single TCP call.
    Used by the background cache sync thread.
    """
    req = {"action": "read_all", "name": "__all__"}
    payload = (json.dumps(req) + '\n').encode('utf-8')
    resp = _send_raw(payload)
    if resp and resp.get("status") == "success":
        return resp.get("value", {})
    return {}


def igo_delete(name):
    with _write_queue_lock:
        _write_queue.pop(name, None)
    resp = _send("delete", name)
    if resp and resp.get("status") == "error":
        print(f"[ignoClient] delete '{name}': {resp['message']}")


# ──────────────────────────────────────────────────────────────
# LOCAL CACHE  (zero-latency reads for control loop)
# ──────────────────────────────────────────────────────────────

_cache_lock        = threading.Lock()
_cache             = {}               # local mirror of server store
_cache_last_update = 0.0              # epoch time of last successful sync
_write_queue_lock  = threading.Lock()
_write_queue       = {}               # pending fast_write() values to push
_cache_running     = False


def fast_read(key, fallback=None):
    """
    Zero-latency read from local cache.
    Use this in the 10ms control loop instead of igo_read().
    Returns fallback if key not present.

    IMPORTANT: cache is refreshed every CACHE_SYNC_INTERVAL (50ms).
    For freshness checking, use get_cache_age().
    """
    with _cache_lock:
        return _cache.get(key, fallback)


def fast_write(key, value):
    """
    Write to local cache immediately, and queue a server push.
    The background sync thread will push queued writes on next iteration.
    Use for values that must be readable via fast_read() immediately.
    """
    with _cache_lock:
        _cache[key] = value
    with _write_queue_lock:
        _write_queue[key] = value


def get_cache_age():
    """Return seconds since the cache was last successfully synced from server."""
    return time.time() - _cache_last_update


def _safe_read_val(val):
    """
    Normalise a value read from the server/cache.
    Converts "None" string → Python None.
    Converts numeric strings → float/int where unambiguous.
    """
    if val is None:
        return None
    if isinstance(val, str):
        if val.strip().lower() in ("none", "null", ""):
            return None
    return val


def _cache_sync_thread():
    """
    Background thread:
      1. Every CACHE_SYNC_INTERVAL seconds, fetch the full store from server.
      2. Update local cache.
      3. Push any queued fast_write() values back to server (single bulk call).
    """
    global _cache_last_update

    while True:
        time.sleep(CACHE_SYNC_INTERVAL)
        try:
            # ── Push queued writes first ──────────────────────
            with _write_queue_lock:
                pending = dict(_write_queue)
                _write_queue.clear()

            if pending:
                igo_bulk_write(pending)

            # ── Pull full snapshot from server ────────────────
            snapshot = igo_read_all()
            if snapshot:
                # Normalise None-like values
                normalised = {k: _safe_read_val(v) for k, v in snapshot.items()}
                with _cache_lock:
                    _cache.update(normalised)
                _cache_last_update = time.time()

        except Exception as e:
            # Don't crash the sync thread — log and retry next cycle
            print(f"[ignoClient/cache] sync error: {e}")


def start_cache_sync():
    """
    Start the background cache synchronisation thread.
    Call this ONCE at application startup (after verifying server connection).

    Example:
        # In pymodbuscode main():
        igo_create_or_write("__ping__", 1)   # verify server
        start_cache_sync()
    """
    global _cache_running
    if _cache_running:
        return
    _cache_running = True
    t = threading.Thread(target=_cache_sync_thread, daemon=True)
    t.name = "ignoClient-cache-sync"
    t.start()
    print(f"[ignoClient] Cache sync started (interval={CACHE_SYNC_INTERVAL*1000:.0f}ms)")


# ══════════════════════════════════════════════════════════════
# CONFIGURING ANOTHER IGNOAPI
# ══════════════════════════════════════════════════════════════
# Everything above talks to ONE server, the one in SERVER_HOST, over a
# socket kept open per thread. The functions below are the other shape:
# they configure a NAMED machine, once, and hang up. A setup script talks
# to a dozen machines and to none of them twice, so a persistent
# connection per host would be a dozen sockets held open for nothing.
#
# ADDRESS THEM BY mDNS NAME -- ignoapi_abi.local, not 192.168.1.27. An IP
# moves with DHCP and a script holding one quietly configures the wrong
# machine, or none. Pass an IP only where a machine has no ADDRESS set.


def _rpc(host, port, req, timeout=5.0):
    """One request, one reply, one connection. Raises on a refusal."""
    with socket.create_connection((str(host), int(port)),
                                  timeout=timeout) as sk:
        sk.settimeout(timeout)
        f = sk.makefile("rwb")
        f.write((json.dumps(req) + "\n").encode("utf-8"))
        f.flush()
        line = f.readline()
    if not line:
        raise RuntimeError("%s:%s closed the connection without answering"
                           % (host, port))
    resp = json.loads(line.decode("utf-8"))
    if resp.get("status") != "success":
        raise RuntimeError("%s:%s refused: %s"
                           % (host, port, resp.get("message", "?")))
    return resp


def _flag(v):
    """TRUE / true / 1 / yes -> "true". The forms a call site actually
    writes, rather than only Python's True."""
    if isinstance(v, str):
        return "true" if v.strip().lower() in ("true", "1", "yes", "on") \
            else "false"
    return "true" if v else "false"


def _hosts(value):
    """A peer list in any of the shapes a caller writes it.

    Accepts a dict {host: port}, a list of hosts or host:port strings, or
    an already-joined string. Returns "host:port,host:port" -- empty when
    there is nothing, which every field here reads as "not set".
    """
    if not value:
        return ""
    if isinstance(value, dict):
        parts = ["%s:%s" % (h, p) if p else str(h)
                 for h, p in value.items()]
    elif isinstance(value, (list, tuple, set)):
        parts = [str(v) for v in value]
    else:
        parts = [p for p in str(value).strip().strip("{}").split(",")]
    return ",".join(p.strip() for p in parts if str(p).strip())


def createModule(host, api_port, kind, name, fields=None):
    """The one that all of the others call.

    `kind` is one of the names listModules() reports. Anything not in
    `fields` keeps the value the create form would have shown, so a
    caller sets only what it cares about.

    The settings go in a DICT rather than as keyword arguments because
    every module has a `port` of its own -- a serial port, an FTP port,
    the port of the server an autoclient polls -- and it collided with the
    port of the machine being configured. A field called host, kind or
    name would have collided the same way.
    """
    return _rpc(host, api_port, {
        "action": "create_module", "kind": kind, "name": name,
        "fields": {k: v for k, v in (fields or {}).items()
                   if v is not None},
    })["message"]


def deleteModule(host, api_port, name, kind=None):
    """Remove a module and everything it owns. `kind` is worked out from
    the name when it is left out."""
    req = {"action": "delete_module", "name": name}
    if kind:
        req["kind"] = kind
    return _rpc(host, api_port, req)["message"]


def listModules(host, api_port):
    """{kind: [names]} of everything configured on that machine."""
    return _rpc(host, api_port, {"action": "list_modules"})["value"]


# ── one function per module ───────────────────────────────────────
def createAutoClient(host, api_port, name, server_ip, server_port,
                     command, runatstartup=False, **extra):
    """A TCP poller: `name` on `host` polls `server_ip:server_port`.

        createAutoClient("ignoapi_abi.local", 8899, "mag",
                         "ignoapi_komal.local", 8899, "0x01", True)

    NOTE the third argument. An autoclient IS a variable, so it has to be
    named -- the signature this was asked for had no room for one, and
    without it there is nothing for the poller to write into.
    """
    return createModule(host, api_port, "autoclient", name, dict(
        {"server_ip": server_ip, "port": server_port,
         "command": command,
         "runatstartup": _flag(runatstartup)}, **extra))


def createFTP(host, api_port, name, folder, ftp_port=2121, userid="",
              password="", sharing=None, runatstartup=False,
              read_only=False, **extra):
    """An FTP server on `host` sharing `folder`.

        createFTP("ignoapi_abi.local", 8899, "drop", r"C:\\Folder",
                  sharing={"ignoapi_komal.local": 8899,
                           "ignoapi_aditya.local": 8888})

    An empty userid and password means anonymous, and empty sharing means
    the link is not sent anywhere -- both are simply left out.
    """
    return createModule(host, api_port, "ftp", name, dict(
        {"folder": folder, "port": ftp_port,
         "username": userid, "password": password,
         "share_with": _hosts(sharing),
         "read_only": _flag(read_only),
         "runatstartup": _flag(runatstartup)}, **extra))


def createVdaBridge(host, api_port, name, broker_host, broker_port=1883,
                    robots="", username="", password="", use_tls=False,
                    runatstartup=False, **extra):
    """A VDA 5050 (MQTT) bridge translating between MQTT and ignoAPI variables.

        createVdaBridge("ignoapi_fleet.local", 8899, "vda_fleet",
                        "192.168.1.50", 1883,
                        robots="rob5:VendorX:AGV-07,rob6:VendorY:AMR-02")
    """
    return createModule(host, api_port, "vda", name, dict(
        {"broker_host": broker_host, "broker_port": broker_port,
         "robots": robots, "username": username, "password": password,
         "use_tls": _flag(use_tls),
         "runatstartup": _flag(runatstartup)}, **extra))


def createSyncIgnoAPI(host, api_port, name, peers, remote_var="",
                      topology="star", mode="0x01",
                      runatstartup=False, **extra):
    """Link `name` on `host` to the same variable on other machines.

        createSyncIgnoAPI("ignoapi_abi.local", 8899, "abiserver",
                          ["ignoapi_komal.local", "ignoapi_aditya.local"],
                          topology="star")

    `peers` takes the same shapes as createFTP's sharing. An empty
    remote_var means "the same name over there", which is the usual case.
    """
    return createModule(host, api_port, "sync", name, dict(
        {"server_ip": _hosts(peers), "remote_var": remote_var,
         "topology": topology, "mode": mode,
         "runatstartup": _flag(runatstartup)}, **extra))


def createComClient(host, api_port, name, com_port, baud=115200,
                    command=None, runatstartup=False, **extra):
    """A serial reader: `name` on `host` reads COM `com_port`.

        createComClient("ignoapi_abi.local", 8899, "scale", "COM3", 9600)
    """
    f = dict({"port": com_port, "baud": baud,
              "runatstartup": _flag(runatstartup)}, **extra)
    if command is not None:
        f["command"] = command
    return createModule(host, api_port, "com", name, f)


def createModbusMaster(host, api_port, name, com_port, baud=38400,
                       parity="N",
                       stopbits=1, bytesize=8, runatstartup=False, **extra):
    """A MODBUS RTU master on `com_port`.

        createModbusMaster("ignoapi_abi.local", 8899, "plc", "COM4", 19200)

    Creates the four command rows beside it -- readReg, writeReg, readCoil,
    writeCoil -- which is how you actually talk to the bus.
    """
    return createModule(host, api_port, "modbusmaster", name, dict(
        {"port": com_port, "baud": baud, "parity": parity,
         "stopbits": stopbits, "bytesize": bytesize,
         "runatstartup": _flag(runatstartup)}, **extra))


def createModbusSlave(host, api_port, name, com_port, register_map,
                      slave_id=1, baud=38400, parity="N", stopbits=1,
                      bytesize=8, runatstartup=False, **extra):
    """A MODBUS RTU slave answering on `com_port`.

    `register_map` is a CSV path ON THAT MACHINE -- it is read there, not
    here, so a path from this machine's drive will not resolve.
    """
    return createModule(host, api_port, "modbusslave", name, dict(
        {"port": com_port, "register_map": register_map,
         "slave_id": slave_id, "baud": baud, "parity": parity,
         "stopbits": stopbits, "bytesize": bytesize,
         "runatstartup": _flag(runatstartup)}, **extra))


def combineVar(host, api_port, name, *variables):
    """Make `name` a live join of other variables, in the order given.

        combineVar("ignoapi_abi.local", 8899, "row", "a", "b", "c")

    writes  combine {a},{b},{c}  into `name`, and ignoAPI keeps
    `name_combined` filled in from those three as they change. A variable
    that does not exist leaves an EMPTY slot rather than being dropped:
    the result is read by position, and a missing third value silently
    shifting the fourth into its place is the one failure that would not
    look like one.
    """
    names = [str(v).strip() for v in variables if str(v).strip()]
    if not names:
        raise ValueError("combineVar needs at least one variable to combine")
    spec = "combine " + ",".join("{%s}" % n for n in names)
    _rpc(host, api_port, {"action": "create_or_write", "name": name,
                      "value": spec})
    return spec


def findIgnoAPIs(timeout=1.5):
    """Every ignoAPI on the network, by UDP broadcast.

    Returns [{"ip", "name", "port"}]. Use the "name" when it is set --
    see the note at the top of this section about IPs and DHCP.
    """
    import ignodiscover
    return ignodiscover.scan(timeout=timeout)
