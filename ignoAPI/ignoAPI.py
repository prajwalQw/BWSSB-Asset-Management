"""
ignoAPI.py — Central variable server for the robot vision system.
- All reads/writes from dualvision go through here via TCP.
- In-memory store is the SINGLE SOURCE OF TRUTH.
- Buffered JSON flush every 200ms (crash safety, no I/O lag).
- Structured DB writes every 500ms to:
    myMarker.db     → enmac      (bottom camera / marker data)
    myMarkerLane.db → lane_data  (front camera / lane data)
    motor.db        → enmac      (motor / hardware data)

FIX: Added bulk_write action to reduce TCP round-trips in hot loops.
FIX: a_id is always written (None when no marker) — never stale.
"""

import json
import os
import re
import socket
import sqlite3
import threading
import time
import sys
import platform
import subprocess
import shutil
import atexit
import pygame
import math
from hardwareCSV import API_PORT
import ctypes
import ignoclip as _ignoclip
import pystray
from PIL import Image, ImageDraw
import winreg  # ADDED FOR WINDOWS STARTUP

import os
import sys

# --- DYNAMIC WORKING DIRECTORY (SUPPORTS .EXE AND .PY) ---
if getattr(sys, 'frozen', False):
    # If running as a compiled .exe
    SCRIPT_DIR = os.path.dirname(sys.executable)
else:
    # If running as a standard .py script
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(SCRIPT_DIR)
# --------------------------------------------------------

# ──────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────
HOST = '127.0.0.1'
PORT = API_PORT
BOUND_HOST = HOST         # the interface actually bound at startup (for display)

FILE_PATH         = "vars.json"
CREATED_AT_FILE   = "var_created_at.json"  # name -> epoch time.time() of first creation (for sort-by-date)
AUTOCLIENTS_FILE  = "autoclients.json"   # registry of autoclient variables -> config
FLUSH_INTERVAL    = 0.2   # seconds — JSON flush interval
DB_WRITE_INTERVAL = 0.5   # seconds — structured DB write interval


# ──────────────────────────────────────────────────────────────
# NETWORK HELPERS  (host-on-LAN option + MAC->IP lookup)
# ──────────────────────────────────────────────────────────────
def get_lan_ip():
    """This machine's primary LAN IPv4 (the one other devices would use to
    reach it), without sending any traffic. Falls back to 127.0.0.1."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no packets sent for UDP connect
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def norm_mac(mac):
    """A MAC in one shape: lower case, colon separated.

    Typed, pasted and OS-reported MACs differ in case and separator (aa-BB-cc
    vs AA:bb:CC), and comparing them as written is why a MAC that is plainly
    there can fail to match.
    """
    m = re.sub(r"[^0-9a-fA-F]", "", str(mac or "")).lower()
    if len(m) != 12:
        return str(mac or "").strip().lower().replace("-", ":")
    return ":".join(m[k:k + 2] for k in range(0, 12, 2))


_local_mac_cache = {}


def local_macs():
    """{ipv4: mac} for this machine's own adapters.

    Read from the OS rather than uuid.getnode(): a robot PC has several
    adapters and getnode() returns ONE of them, chosen arbitrarily -- so the
    MAC it gives you is quite likely not the one on the network you are
    actually using, which makes it worse than useless for telling somebody
    else what to type in.

    Cached: the answer changes only when hardware does, and shelling out to
    ipconfig on every frame would be absurd.
    """
    if _local_mac_cache:
        return dict(_local_mac_cache)
    out = {}
    try:
        if platform.system() == "Windows":
            txt = subprocess.check_output(
                "ipconfig /all", shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ).decode(errors="ignore")
            mac = None
            for line in txt.splitlines():
                m = re.search(r"Physical Address[.\s]*:\s*([\da-fA-F-]{17})", line)
                if m:
                    mac = norm_mac(m.group(1))
                    continue
                m = re.search(r"IPv4 Address[.\s]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
                if m and mac:
                    out[m.group(1)] = mac
        else:
            txt = subprocess.check_output("ip -o addr", shell=True).decode(errors="ignore")
            links = subprocess.check_output("ip -o link", shell=True).decode(errors="ignore")
            byname = {}
            for line in links.splitlines():
                m = re.search(r"^\d+:\s*([^:]+):.*link/ether\s+([\da-fA-F:]{17})", line)
                if m:
                    byname[m.group(1).strip()] = norm_mac(m.group(2))
            for line in txt.splitlines():
                m = re.search(r"^\d+:\s*(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)", line)
                if m and m.group(1) in byname:
                    out[m.group(2)] = byname[m.group(1)]
    except Exception:
        pass
    _local_mac_cache.update(out)
    return dict(out)


def local_mac(ip=None):
    """The MAC of the adapter holding `ip` (default: the LAN address).

    Falls back to any adapter we could read, so something useful is shown even
    when the address-to-adapter match fails.
    """
    macs = local_macs()
    want = ip or get_lan_ip()
    if want in macs:
        return macs[want]
    for other in local_ipv4s():
        if other in macs:
            return macs[other]
    return next(iter(macs.values()), "")


# ──────────────────────────────────────────────────────────────
# NAMING THIS MACHINE
#   ADDRESS is a plain variable, sat next to RUN_AT_STARTUP. Put "helloworld"
#   in it and this ignoAPI answers to `ignoapi_helloworld.local` on the LAN.
#
#   The point is that an IP is the one thing about a robot PC that changes by
#   itself -- a DHCP lease, a move to another AP -- and every sync configured
#   against it then has to be found and edited. A name does not change unless
#   somebody changes it.
#
#   IP and MAC both still work exactly as before. This is a third way to say
#   where a machine is, not a replacement.
# ──────────────────────────────────────────────────────────────
ADDRESS_VAR = "ADDRESS"
_mdns = None
_discover = None


def ignoapi_address():
    """The ADDRESS variable's current value ("" if unset)."""
    try:
        return str(_read(ADDRESS_VAR) or "").strip()
    except Exception:
        return ""


def ignoapi_hostname():
    """`ignoapi_<address>.local`, or "" when ADDRESS is blank."""
    return ignomdns.hostname_for(ignoapi_address())


def start_discovery():
    """Answer "ignoAPI?" UDP broadcasts, so a scanner can find this
    machine without sweeping the subnet a connection at a time.

    Started beside mDNS because it answers the same question by a
    different route: mDNS resolves a name you already know, this one
    tells you which machines are out there at all."""
    global _discover
    if _discover is not None:
        return _discover
    try:
        _discover = ignodiscover.DiscoveryResponder(
            ignoapi_hostname, lambda: PORT, on_log=lambda m: print(m))
        _discover.start()
    except Exception as e:
        print(f"[ignoAPI] discovery not started ({e}) — the TCP scan still works")
    return _discover


def start_mdns():
    """Publish this machine's name on the LAN. Never fatal.

    Started even when ADDRESS is empty: the responder reads the name through
    a callback on every pass, so typing a name into the row starts answering
    for it without a restart, and clearing the row stops.
    """
    global _mdns
    if _mdns is not None:
        return _mdns
    try:
        _mdns = ignomdns.MdnsResponder(ignoapi_hostname, get_lan_ip,
                                       on_log=lambda m: print(m))
        _mdns.start()
        name = ignoapi_hostname()
        if name:
            print(f"[ignoAPI] answering to {name} on the LAN")
        else:
            print(f"[ignoAPI] no {ADDRESS_VAR} set — put a name in that row "
                  f"and this machine becomes ignoapi_<name>.local")
    except Exception as e:
        print(f"[ignoAPI] mDNS not started ({e}) — IP and MAC still work")
    return _mdns


def arp_table():
    """{mac: ip} for everything the OS currently has cached."""
    out = {}
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output(
                "arp -a", shell=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            ).decode(errors="ignore")
            pattern = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F][\da-fA-F:-]{10,})")
        else:
            output = subprocess.check_output(
                "ip neigh show", shell=True).decode(errors="ignore")
            pattern = re.compile(r"(\d+\.\d+\.\d+\.\d+).*lladdr\s+([\da-fA-F:]+)")
    except Exception:
        return out
    for line in output.splitlines():
        m = pattern.search(line)
        if m:
            ip, mac = m.groups()
            mac = norm_mac(mac)
            if mac and mac not in ("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"):
                out[mac] = ip
    return out


ARP_SWEEP_PORT = 9        # discard; nothing has to be listening for ARP to happen
ARP_SWEEP_WORKERS = 64
ARP_SWEEP_SETTLE = 1.2    # seconds for the replies to land in the OS table
ARP_SWEEP_GRACE  = 3.0    # extra seconds to keep re-reading the table for


def local_ipv4s():
    """Every IPv4 address this machine holds, loopback excluded.

    A robot PC routinely has more than one: a wired LAN, a Wi-Fi link, a VPN
    adapter. Which one get_lan_ip() returns is an accident of routing, so a
    sweep that trusts it can miss the very subnet the peer is on.
    """
    found = []
    primary = get_lan_ip()
    if primary and not primary.startswith("127."):
        found.append(primary)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def arp_sweep(base_ip=None, quiet=True):
    """Touch every address on the local /24 so the ARP table fills in.

    One UDP datagram per host. UDP because it needs no handshake, no reply and
    no privileges -- the datagram may be refused or dropped and the ARP entry
    still appears, because the machine had to resolve the MAC before it could
    send anything at all. Ping would be the obvious choice and is the wrong
    one: ICMP is blocked by default on a stock Windows firewall, so a machine
    that is right there answers nothing.

    Returns the number of addresses touched.
    """
    mine = [base_ip] if base_ip else local_ipv4s()
    mine = [ip for ip in mine if ip and not ip.startswith("127.")]
    if not mine:
        return 0
    targets, prefixes = [], []
    for ip in mine:
        prefix = ip.rsplit(".", 1)[0]
        if prefix in prefixes:
            continue                       # two addresses on one subnet
        prefixes.append(prefix)
        targets += [f"{prefix}.{n}" for n in range(1, 255)
                    if f"{prefix}.{n}" not in mine]

    def touch(chunk):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(0.05)
            for host in chunk:
                try:
                    sock.sendto(b"\x00", (host, ARP_SWEEP_PORT))
                except OSError:
                    pass
            sock.close()
        except OSError:
            pass

    size = max(1, len(targets) // ARP_SWEEP_WORKERS)
    threads = []
    for k in range(0, len(targets), size):
        t = threading.Thread(target=touch, args=(targets[k:k + size],), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=3.0)
    time.sleep(ARP_SWEEP_SETTLE)
    if not quiet:
        print(f"[ignoAPI] ARP sweep: touched {len(targets)} addresses on "
              + ", ".join(f"{p}.0/24" for p in prefixes))
    return len(targets)


SCAN_WORKERS = 96
SCAN_TIMEOUT = 0.35


def scan_ignoapi_hosts(port=None, timeout=SCAN_TIMEOUT):
    """Every address on this machine's subnets that ACCEPTS a connection on
    the ignoAPI port.

    An ARP sweep says which machines exist; this says which of them are
    running ignoAPI, which is the only question worth asking when you are
    filling in a peer list. A refused connection is a definite no, so the scan
    is fast: only a firewall that silently drops costs the full timeout.
    """
    port = int(port or PORT)
    mine = [ip for ip in local_ipv4s() if ip and not ip.startswith("127.")]
    targets, prefixes = [], []
    for ip in mine:
        prefix = ip.rsplit(".", 1)[0]
        if prefix in prefixes:
            continue
        prefixes.append(prefix)
        targets += [f"{prefix}.{n}" for n in range(1, 255)
                    if f"{prefix}.{n}" not in mine]
    found, lock = [], threading.Lock()

    def probe(chunk):
        for host in chunk:
            try:
                with socket.create_connection((host, port), timeout=timeout):
                    with lock:
                        found.append(host)
            except OSError:
                pass

    size = max(1, len(targets) // SCAN_WORKERS)
    threads = []
    for k in range(0, len(targets), size):
        t = threading.Thread(target=probe, args=(targets[k:k + size],), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join(timeout=timeout * 6 + 5)
    return sorted(found, key=lambda h: [int(x) for x in h.split(".")])


_mac_cache = {}            # mac -> ip, last known good
_mac_cache_lock = threading.Lock()


def ip_from_mac(target_mac, sweep=True):
    """Resolve an IPv4 from a MAC. Returns the IP, or None.

    Looks in the ARP table first; if the MAC is not there and `sweep` is set,
    fills the table and looks again. That second step is the whole point: on a
    quiet network the first look almost always misses, which is what made this
    report "same network, still says ping the subnet".
    """
    want = norm_mac(target_mac)
    if not want or len(want) != 17:
        return None
    table = arp_table()
    if want in table:
        with _mac_cache_lock:
            _mac_cache[want] = table[want]
        return table[want]
    if not sweep:
        return None
    arp_sweep()
    # Poll rather than sleep once: a machine that answers immediately is found
    # immediately, and a slow one still gets its couple of seconds.
    table = arp_table()
    deadline = time.time() + ARP_SWEEP_GRACE
    while want not in table and time.time() < deadline:
        time.sleep(0.25)
        table = arp_table()
    if want in table:
        with _mac_cache_lock:
            _mac_cache[want] = table[want]
        print(f"[ignoAPI] MAC {want} found at {table[want]} after an ARP sweep")
        return table[want]
    # Fall back to the last address this MAC was seen at. Better than nothing:
    # a machine that is briefly unreachable has usually not changed address,
    # and the caller can still fail honestly when it cannot connect.
    with _mac_cache_lock:
        last = _mac_cache.get(want)
    if last:
        print(f"[ignoAPI] MAC {want} not in ARP — using last known {last}")
    return last


ARP_CHECK_INTERVAL_SEC = 15.0     # while something is down
ARP_KEEP_INTERVAL_SEC = 120.0     # routine re-check of everything


def _mac_recover_down():
    """Re-resolve the MACs of anything that is currently NOT working.

    This is the case the old code could not help with: once a peer is
    unreachable, nothing was going to notice that its address had changed, so
    the link stayed broken until somebody edited it by hand.
    """
    fixed = 0
    with _sy_lock:
        syncs = list(_syncpeers.keys())
    with _ac_lock:
        acs = [(n, dict(c)) for n, c in _autoclients.items()]

    # Everything that is broken AND has a MAC, gathered first so the whole
    # pass costs ONE sweep. Per-item sweeping would mean three dead children
    # scanning the subnet three times over, every fifteen seconds.
    wanted = []
    for name in syncs:
        if any(sy_macs(name)) and sy_peers_down(name):
            wanted += [norm_mac(m) for m in sy_macs(name) if m]
    for name, cfg in acs:
        if (cfg.get("mac") or "").strip() and not autoclient_is_live(name):
            wanted.append(norm_mac(cfg["mac"]))
    if not wanted:
        return 0
    table = arp_table()
    if any(m not in table for m in wanted):
        arp_sweep()
        table = arp_table()
    with _mac_cache_lock:
        _mac_cache.update(table)

    for name in syncs:
        try:
            if not any(sy_macs(name)):
                continue
            if not sy_peers_down(name):
                continue
            moved = sy_resolve_macs(name, sweep=False)
            if moved:
                for old, new in moved:
                    print(f"[ignoAPI] sync '{name}': MAC now answers at {new} "
                          f"(was {old}) — reconnecting")
                syncpeer_launch(name)
                fixed += 1
        except Exception as e:
            print(f"[ignoAPI] MAC recovery for sync '{name}' failed: {e}")

    for name, cfg in acs:
        mac = (cfg.get("mac") or "").strip()
        if not mac or autoclient_is_live(name):
            continue
        try:
            found = table.get(norm_mac(mac))
            if found and found != (cfg.get("server_ip") or ""):
                print(f"[ignoAPI] autoclient '{name}': MAC now answers at "
                      f"{found} (was {cfg.get('server_ip') or '(unset)'}) — reconnecting")
                _ac_repoint(name, found)
                fixed += 1
        except Exception as e:
            print(f"[ignoAPI] MAC recovery for autoclient '{name}' failed: {e}")
    return fixed


def _mac_recover_all():
    """Routine sweep: re-point anything whose MAC has moved, working or not."""
    try:
        arp_sweep()
        table = arp_table()
    except Exception:
        return
    with _mac_cache_lock:
        _mac_cache.update(table)
    with _sy_lock:
        syncs = list(_syncpeers.keys())
    for name in syncs:
        try:
            if any(sy_macs(name)) and sy_resolve_macs(name, sweep=False):
                syncpeer_launch(name)
        except Exception:
            pass
    with _ac_lock:
        acs = [(n, dict(c)) for n, c in _autoclients.items()]
    for name, cfg in acs:
        mac = (cfg.get("mac") or "").strip()
        if not mac:
            continue
        found = table.get(norm_mac(mac))
        if found and found != (cfg.get("server_ip") or ""):
            print(f"[ignoAPI] autoclient '{name}': MAC moved to {found} — reconnecting")
            try:
                _ac_repoint(name, found)
            except Exception:
                pass


def _arp_keeper_loop():
    """Two cadences on one thread.

    FAST, and only while something is down: a broken link is the moment the
    address is most likely to be wrong, and the moment you least want to wait
    two minutes. SLOW otherwise, so a healthy system does no network scanning
    at all -- a sweep every fifteen seconds forever would be rude on a shared
    network for no benefit.
    """
    last_full = 0.0
    while True:
        time.sleep(ARP_CHECK_INTERVAL_SEC)
        if _shutting_down:
            continue
        try:
            if not mac_configured_children():
                continue             # nothing uses MAC lookup — never scan
            _mac_recover_down()
            if time.time() - last_full >= ARP_KEEP_INTERVAL_SEC:
                last_full = time.time()
                _mac_recover_all()
        except Exception as e:
            print(f"[ignoAPI] MAC keeper error (ignored): {e}")


# DB_BOTTOM = "myMarker.db"
# DB_FRONT  = "myMarkerLane.db"
# DB_MOTOR  = "motor.db"

# ──────────────────────────────────────────────────────────────
# IN-MEMORY STORE + LOCK
# ──────────────────────────────────────────────────────────────
_store_lock = threading.Lock()
_dirty      = False

# Set whenever EXEC/EXECFLAG changes, so the supervisor reacts to a toggle at
# once instead of on its next poll. Declared here because _create_or_write
# (below) signals it long before the exec section is defined.
_exec_wake = threading.Event()


def _load_variables():
    if os.path.exists(FILE_PATH):
        try:
            with open(FILE_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: vars.json corrupt — starting fresh.")
    return {}


def _load_created_at():
    if os.path.exists(CREATED_AT_FILE):
        try:
            with open(CREATED_AT_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: var_created_at.json corrupt — starting fresh.")
    return {}


_variable_store  = _load_variables()
_var_created_at  = _load_created_at()   # name -> epoch float; backfilled below for pre-existing vars
for _vn in _variable_store:
    _var_created_at.setdefault(_vn, 0.0)  # unknown creation time -> sorts as "oldest"

if not os.path.exists("Hardware.csv"):
    print("[ignoAPI] Hardware.csv not found. Generating default with API_PORT=8899.")
    with open("Hardware.csv", "w") as f:
        f.write("Setting,Value\n")
        f.write("API_PORT,8899\n")
# ------------------------------------------
# ──────────────────────────────────────────────────────────────
# JSON PERSISTENCE
# ──────────────────────────────────────────────────────────────

def _flush_to_disk():
    global _dirty
    tmp = FILE_PATH + '.tmp'
    ca_tmp = CREATED_AT_FILE + '.tmp'
    with _store_lock:
        if not _dirty:
            return
        snapshot = dict(_variable_store)
        created_snapshot = dict(_var_created_at)
        _dirty = False
    try:
        with open(tmp, 'w') as f:
            json.dump(snapshot, f, indent=2)
        try:
            os.replace(tmp, FILE_PATH)
        except OSError:
            import shutil
            shutil.copy2(tmp, FILE_PATH)
            os.remove(tmp)
    except OSError as e:
        print(f"[ignoAPI] Disk flush error: {e}")
    try:
        with open(ca_tmp, 'w') as f:
            json.dump(created_snapshot, f, indent=2)
        os.replace(ca_tmp, CREATED_AT_FILE)
    except OSError as e:
        print(f"[ignoAPI] Disk flush error (created_at): {e}")


def _flush_loop():
    while True:
        time.sleep(FLUSH_INTERVAL)
        _flush_to_disk()


_flush_thread = threading.Thread(target=_flush_loop, daemon=True)
_flush_thread.start()
print(f"[ignoAPI] Loaded {len(_variable_store)} variables from {FILE_PATH}")


# ──────────────────────────────────────────────────────────────
# VARIABLE OPERATIONS  (all in-memory)
# ──────────────────────────────────────────────────────────────

def _create(name, value):
    global _dirty
    with _store_lock:
        if name not in _variable_store:
            _var_created_at[name] = time.time()
        _variable_store[name] = value
        _dirty = True

def _read(name):
    with _store_lock:
        if name in _variable_store:
            return _variable_store[name]
    raise NameError(f"'{name}' not found")

def _write(name, value):
    global _dirty
    with _store_lock:
        if name not in _variable_store:
            raise NameError(f"'{name}' does not exist. Use create first.")
        _variable_store[name] = value
        _dirty = True

def _create_or_write(name, value):
    global _dirty
    with _store_lock:
        if name not in _variable_store:
            _var_created_at[name] = time.time()
        _variable_store[name] = value
        _dirty = True
    # Nudge the exec supervisor the instant EXEC/EXECFLAG changes -- whether
    # that came from the GUI or over TCP -- so flipping the flag acts
    # immediately rather than after the next poll. The name test is inlined
    # (rather than calling is_exec_row) because this runs before the exec
    # section is defined, and on a hot path.
    if str(name).strip().lower() in ("exec", "execflag"):
        _exec_wake.set()
    # heartbeat: any value update to a registered autoclient variable counts
    # as "still hearing from the device" -- see autoclient_is_live below
    with _ac_lock:
        if name in _autoclients:
            _ac_last_seen[name] = time.time()

def _bulk_write(data: dict):
    global _dirty
    with _store_lock:
        now = time.time()
        for k, v in data.items():
            if k not in _variable_store:
                _var_created_at[k] = now
            _variable_store[k] = v
        _dirty = True

def _read_all():
    with _store_lock:
        return dict(_variable_store)

def _delete(name):
    global _dirty
    with _store_lock:
        if name not in _variable_store:
            raise NameError(f"'{name}' not found.")
        del _variable_store[name]
        _var_created_at.pop(name, None)
        _dirty = True
def restart_application():
    """Forces a data flush, then spawns a fresh instance and exits this one.

    Previously used os.execv(sys.executable, ['python'] + sys.argv) to replace
    the running process in-place. That works for a plain `python ignoAPI.py`
    but reliably crashes the frozen .exe build with
    "ModuleNotFoundError: No module named 'pygame.constants'": a PyInstaller
    onefile exe unpacks itself into a temp _MEI... directory at startup and
    registers cleanup for when the process exits; os.execv() on Windows is
    emulated (spawn + exit, there is no true in-place exec), so the outgoing
    process's teardown can race the incoming image's imports and rip a
    C-extension submodule out from under it mid-load. Spawning an independent
    subprocess and then cleanly exiting this one avoids the race entirely --
    each instance gets its own untouched extraction directory."""
    print("\n[ignoAPI] SYSTEM REBOOT INITIATED...")
    _flush_to_disk()
    _stop_all_autoclients()
    _stop_all_execs()
    if getattr(sys, 'frozen', False):
        # sys.executable IS the built exe -- relaunch it directly, no interpreter needed.
        cmd = [sys.executable] + sys.argv[1:]
    else:
        cmd = [sys.executable, os.path.abspath(__file__)] + sys.argv[1:]
    subprocess.Popen(cmd, cwd=os.getcwd())
    pygame.quit()
    sys.exit(0)


def toggle_windows_startup(enable: bool):
    """Adds or removes the application from the Windows Startup Registry."""
    if os.name != 'nt':
        return

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "ignoAPI_Server"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)

        if enable:
            # --- DYNAMIC REGISTRY COMMAND (SUPPORTS .EXE AND .PY) ---
            if getattr(sys, 'frozen', False):
                # If compiled, sys.executable is the path to ignoAPI.exe
                command = f'"{sys.executable}"'
            else:
                # If script, use python.exe + script path
                script_path = os.path.abspath(__file__)
                command = f'"{sys.executable}" "{script_path}"'
            # --------------------------------------------------------

            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
            print(f"[ignoAPI] OS REGISTRY UPDATED: Startup ENABLED -> {command}")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                print(f"[ignoAPI] OS REGISTRY UPDATED: Startup DISABLED")
            except FileNotFoundError:
                pass

        winreg.CloseKey(key)
    except Exception as e:
        print(f"[ignoAPI] OS Registry Error: {e}")
def _append(name, value):
    global _dirty
    with _store_lock:
        if name not in _variable_store:
            raise NameError(f"'{name}' not found.")
        cur = _variable_store[name]
        if isinstance(cur, str):
            _variable_store[name] = cur + str(value)
        elif isinstance(cur, list):
            cur.append(value)
        elif isinstance(cur, (int, float)):
            if not isinstance(value, (int, float)):
                raise TypeError("Can only add numbers to a numeric variable.")
            _variable_store[name] = cur + value
        else:
            raise TypeError(f"Cannot append to type {type(cur).__name__}")
        _dirty = True


# ──────────────────────────────────────────────────────────────
# REQUEST ROUTER
# ──────────────────────────────────────────────────────────────

def handle_client_request(req):
    action = req.get("action")
    name   = req.get("name")
    value  = req.get("value")

    if not action:
        return {"status": "error", "message": "Missing 'action'"}

    if action == "bulk_write":
        data = req.get("data", {})
        if not isinstance(data, dict):
            return {"status": "error", "message": "'data' must be a dict"}
        try:
            _bulk_write(data)
            return {"status": "success", "message": f"bulk_write {len(data)} keys"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    if action in ("link", "unlink", "list_links"):
        return handle_link_request(req)

    if action in ("create_module", "delete_module", "list_modules"):
        # Defined further down, once every module's create function
        # exists. Looked up at CALL time, so the order of definitions in
        # this file does not decide whether the action works.
        return handle_module_request(req)

    if action == "read_all":
        try:
            snapshot = _read_all()
            return {"status": "success", "value": snapshot}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    if not name:
        return {"status": "error", "message": "Missing 'name'"}

    try:
        if action == "create":
            _create(name, value)
            return {"status": "success", "message": f"Created '{name}'"}
        elif action == "read":
            val = _read(name)
            return {"status": "success", "value": val}
        elif action == "write":
            _write(name, value)
            return {"status": "success", "message": f"Wrote '{name}'"}
        elif action == "create_or_write":
            _create_or_write(name, value)
            return {"status": "success", "message": f"Set '{name}'"}
        elif action == "append":
            _append(name, value)
            return {"status": "success", "message": f"Appended '{name}'"}
        elif action == "delete":
            _delete(name)
            return {"status": "success", "message": f"Deleted '{name}'"}
        else:
            return {"status": "error", "message": f"Unknown action: '{action}'"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ──────────────────────────────────────────────────────────────
# STRUCTURED DB WRITER
# ──────────────────────────────────────────────────────────────

# def _ensure_rows():
#     for db, table in [(DB_BOTTOM, "enmac"), (DB_FRONT, "lane_data"), (DB_MOTOR, "enmac")]:
#         try:
#             conn = sqlite3.connect(db)
#             conn.execute(f"INSERT OR IGNORE INTO {table} (id) VALUES (1)")
#             conn.commit()
#             conn.close()
#         except Exception as e:
#             pass
#
# def _structured_db_writer():
#     _ensure_rows()
#     conn_bottom = sqlite3.connect(DB_BOTTOM, check_same_thread=False)
#     conn_front  = sqlite3.connect(DB_FRONT,  check_same_thread=False)
#     conn_motor  = sqlite3.connect(DB_MOTOR,  check_same_thread=False)
#
#     while True:
#         time.sleep(DB_WRITE_INTERVAL)
#         with _store_lock:
#             data = dict(_variable_store)
#
#         try:
#             conn_bottom.execute("""
#                 UPDATE enmac SET a_id=?, last_a_id=?, a_x=?, a_y=?, a_x_mm=?, a_y_mm=?, a_ang=?, a_hyp=?, a_hyp_mm=?, a_adj=?, a_opp=?, a_thetha=?, r_id=?, cmd=?, align_id=?, confidence=?, gate_open=?, stable_count=? WHERE id=1
#             """, (data.get("a_id"), data.get("last_a_id"), data.get("a_x"), data.get("a_y"), data.get("a_x_mm"), data.get("a_y_mm"), data.get("a_ang"), data.get("a_hyp"), data.get("a_hyp_mm"), data.get("a_adj"), data.get("a_opp"), data.get("a_thetha"), data.get("r_id"), data.get("cmd"), data.get("align_id"), data.get("confidence"), data.get("gate_open"), data.get("stable_count")))
#             conn_bottom.commit()
#         except Exception: pass
#
#         try:
#             conn_front.execute("""
#                 UPDATE lane_data SET left_id=?, right_id=?, l_hyp=?, l_adj=?, l_opp=?, n_hyp=?, n_adj=?, n_opp=?, t_hyp=?, t_adj=?, t_opp=?, detection_mode=?, lane_detection_enabled=?, align_id=?, FIDCH=?, confidence=?, gate_open=?, stable_count=?, VEL=?, DISTANCE_MM=?, VELRUN_SLOWDOWN_TIME=?, VELRUN_DISTANCE_MM=?, THRESHOLD_ENCODER=? WHERE id=1
#             """, (data.get("left_id"), data.get("right_id"), data.get("l_hyp"), data.get("l_adj"), data.get("l_opp"), data.get("n_hyp"), data.get("n_adj"), data.get("n_opp"), data.get("t_hyp"), data.get("t_adj"), data.get("t_opp"), data.get("detection_mode"), data.get("lane_detection_enabled"), data.get("align_id"), data.get("FIDCH"), data.get("confidence"), data.get("gate_open"), data.get("stable_count"), data.get("VEL"), data.get("DISTANCE_MM"), data.get("VELRUN_SLOWDOWN_TIME"), data.get("VELRUN_DISTANCE_MM"), data.get("THRESHOLD_ENCODER")))
#             conn_front.commit()
#         except Exception: pass
#
#         try:
#             conn_motor.execute("""
#                 UPDATE enmac SET RIGHT_MOTOR_ENCODER_VAL=?, LEFT_MOTOR_ENCODER_VAL=?, RIGHT_TURN_ENCODER_VAL=?, LEFT_TURN_ENCODER_VAL=?, RIGHT_MOTOR_PR=?, LEFT_MOTOR_PR=?, RIGHT_TURN_PR=?, LEFT_TURN_PR=?, Rgpio7=?, Rgpio6=?, Lgpio7=?, Lgpio6=?, alarmRM=?, alarmLM=?, alarmRT=?, alarmLT=?, obstacle=?, battery_percentage=?, charging_status=?, switch_status=?, cmd=?, response=?, acknowledgement=?, fleet_response=?, speed=?, timestamp=?, distance=?, lidar_y=? WHERE id=1
#             """, (data.get("RIGHT_MOTOR_ENCODER_VAL"), data.get("LEFT_MOTOR_ENCODER_VAL"), data.get("RIGHT_TURN_ENCODER_VAL"), data.get("LEFT_TURN_ENCODER_VAL"), data.get("RIGHT_MOTOR_PR"), data.get("LEFT_MOTOR_PR"), data.get("RIGHT_TURN_PR"), data.get("LEFT_TURN_PR"), data.get("Rgpio7"), data.get("Rgpio6"), data.get("Lgpio7"), data.get("Lgpio6"), data.get("alarmRM"), data.get("alarmLM"), data.get("alarmRT"), data.get("alarmLT"), data.get("obstacle"), data.get("battery_percentage"), data.get("charging_status"), data.get("switch_status"), data.get("cmd"), data.get("response"), data.get("acknowledgement"), data.get("fleet_response"), data.get("speed"), data.get("timestamp"), data.get("distance"), data.get("lidar_y")))
#             conn_motor.commit()
#         except Exception: pass
#
#
# _db_thread = threading.Thread(target=_structured_db_writer, daemon=True)
# _db_thread.start()


# ──────────────────────────────────────────────────────────────
# TCP SERVER
# ──────────────────────────────────────────────────────────────

def client_thread(conn, addr):
    buf = ""
    try:
        while True:
            chunk = conn.recv(4096)
            if not chunk: break
            buf += chunk.decode('utf-8')

            # Discovery ping, checked on the RAW buffer -- fires the instant
            # "ignoAPI" (any case) shows up, even if the client never sends a
            # trailing newline. A simple LAN-scan client doing a bare
            # socket.send(b"ignoAPI") with no framing is normal, but the
            # line-based protocol below only ever fires on a COMPLETE
            # newline-terminated line, so an unterminated probe would
            # otherwise sit in the buffer forever with no reply. Skipped
            # whenever the buffered data looks like the start of real JSON
            # (starts with '{' or '['), so a legitimate request whose VALUE
            # happens to mention "ignoAPI" is never intercepted here -- it
            # always falls through to the normal JSON handling below.
            stripped = buf.lstrip()
            if stripped and not stripped.startswith(('{', '[')) and "ignoapi" in buf.lower():
                conn.sendall(b"OK\n")
                idx = buf.lower().find("ignoapi")
                after = buf[idx + len("ignoapi"):]
                nl = after.find('\n')
                buf = after[nl + 1:] if nl != -1 else ""

            while '\n' in buf:
                line, buf = buf.split('\n', 1)
                line = line.strip()
                if not line: continue
                try:
                    req  = json.loads(line)
                    resp = handle_client_request(req)
                except json.JSONDecodeError:
                    # discovery ping: a client scanning the LAN for the right
                    # server IP can send a bare, non-JSON probe containing
                    # "ignoAPI" in any case (ignoapi / IgnoAPI / IGNOAPI / ...)
                    # and gets a plain "OK" back -- lets it identify which IP
                    # is actually running this server without needing valid
                    # JSON or auth. Only reached when the line ISN'T valid
                    # JSON, so a real JSON request that merely mentions
                    # "ignoAPI" in a value (e.g. a log string) is never
                    # intercepted by this and is handled normally above.
                    if "ignoapi" in line.lower():
                        conn.sendall(b"OK\n")
                        continue
                    resp = {"status": "error", "message": "Invalid JSON"}
                conn.sendall((json.dumps(resp) + '\n').encode('utf-8'))
    except Exception: pass
    finally: conn.close()

def start_server():
    global BOUND_HOST
    # NETWORK mode binds 0.0.0.0 so other devices on the LAN can reach the DB;
    # LOCAL mode binds 127.0.0.1 (localhost only). The flag lives in the store
    # (like RUN_AT_STARTUP) so it's already loaded here; changing it needs a
    # reboot to re-bind, which the header toggle triggers.
    network = bool(_variable_store.get("API_NETWORK_HOST", False))
    bind_host = "0.0.0.0" if network else "127.0.0.1"
    BOUND_HOST = bind_host
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind_host, PORT))
    srv.listen(16)
    print(f"[ignoAPI] Server listening on {bind_host}:{PORT}"
          + (f"  (LAN IP: {get_lan_ip()})" if network else "  (localhost only)"))
    try:
        while True:
            conn, addr = srv.accept()
            t = threading.Thread(target=client_thread, args=(conn, addr), daemon=True)
            t.start()
    except Exception: pass
    finally: srv.close()


# ──────────────────────────────────────────────────────────────
# AUTOCLIENT MANAGER
#   An "autoclient variable" is fed by a duplicated autoclient program
#   (autoclient_<name>.exe / .py) polling a device and writing the response
#   back into this variable. The registry (autoclients.json) maps var name ->
#   config; live processes are tracked in-memory (green = process alive).
# ──────────────────────────────────────────────────────────────
AC_FIELDS = ["server_ip", "mac", "port", "command", "poll_interval_sec",
             "connect_timeout_sec", "read_timeout_sec", "log_file", "runatstartup"]


def ac_default_fields():
    """Blank create-modal field values (strings, as the UI edits them)."""
    return {"server_ip": "", "mac": "", "port": "8899", "command": "0x01",
            "poll_interval_sec": "0.1", "connect_timeout_sec": "5",
            "read_timeout_sec": "5", "log_file": "responses.log",
            "runatstartup": "false"}


def ac_fields_from_config(cfg):
    """Prefill the edit modal from an existing autoclient config."""
    f = ac_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def ac_cast_fields(fields):
    """Turn the modal's string fields into a properly-typed config dict."""
    def num(s, cast, default):
        try:
            return cast(str(s).strip())
        except (ValueError, TypeError):
            return default
    return {
        "server_ip":           (fields.get("server_ip") or "").strip(),
        "mac":                 (fields.get("mac") or "").strip(),
        "port":                num(fields.get("port"), int, 0),
        "command":             (fields.get("command") or "").strip(),
        "poll_interval_sec":   num(fields.get("poll_interval_sec"), float, 1.0),
        "connect_timeout_sec": num(fields.get("connect_timeout_sec"), float, 5),
        "read_timeout_sec":    num(fields.get("read_timeout_sec"), float, 5),
        "log_file":            (fields.get("log_file") or "responses.log").strip() or "responses.log",
        "runatstartup":        str(fields.get("runatstartup", "false")).strip().lower() in ("true", "1", "yes", "on"),
    }


def _load_autoclients():
    if os.path.exists(AUTOCLIENTS_FILE):
        try:
            with open(AUTOCLIENTS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: autoclients.json corrupt — starting fresh.")
    return {}


_autoclients  = _load_autoclients()     # name -> config dict
_ac_procs     = {}                      # name -> subprocess.Popen (in-memory)
_ac_last_seen = {}                      # name -> time.time() of last value update while registered
_ac_disabled  = set()                   # names the user explicitly Disconnected -- watchdog leaves these alone
_ac_lock      = threading.Lock()


def _save_autoclients():
    tmp = AUTOCLIENTS_FILE + ".tmp"
    try:
        with _ac_lock:
            snapshot = dict(_autoclients)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, AUTOCLIENTS_FILE)
    except OSError as e:
        print(f"[ignoAPI] autoclients save error: {e}")


def _ac_paths(name):
    """(source, target, json_path, is_exe) for autoclient <name>. Prefers the
    compiled autoclient.exe; falls back to autoclient.py in dev so the feature
    works before the exe is built."""
    exe_src = os.path.join(SCRIPT_DIR, "autoclient.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoclient.py")
    if os.path.exists(exe_src):
        return exe_src, os.path.join(SCRIPT_DIR, f"autoclient_{name}.exe"), \
               os.path.join(SCRIPT_DIR, f"autoclient_{name}.json"), True
    return py_src, os.path.join(SCRIPT_DIR, f"autoclient_{name}.py"), \
           os.path.join(SCRIPT_DIR, f"autoclient_{name}.json"), False


def _write_ac_config(name, cfg):
    """Write autoclient_<name>.json, injecting the write-back target (this
    server) and the variable name so the duplicated program feeds this var."""
    _, _, json_path, _ = _ac_paths(name)
    full = {k: cfg.get(k) for k in AC_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def is_autoclient(name):
    with _ac_lock:
        return name in _autoclients


def autoclient_config(name):
    with _ac_lock:
        return dict(_autoclients.get(name, {}))


def autoclient_is_live(name):
    """LIVE (green) means the poller process is running AND has recently fed
    a value back -- so an unreachable device, or a bad configuration, shows
    red even while the process itself is still alive and retrying."""
    with _ac_lock:
        proc = _ac_procs.get(name)
        cfg  = dict(_autoclients.get(name, {}))
        last = _ac_last_seen.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        interval = float(cfg.get("poll_interval_sec") or 1.0)
    except (TypeError, ValueError):
        interval = 1.0
    timeout = max(3.0 * interval, 5.0)
    return last is not None and (time.time() - last) <= timeout


def _kill_process_tree(proc):
    """Terminate `proc` AND everything it spawned.

    proc.terminate() only kills the top-level process Popen tracked. A onefile
    PyInstaller .exe's bootloader commonly spawns/execs into a SEPARATE child
    process to run the actual payload -- terminate() leaves that child running,
    which keeps the .exe file locked (Windows reports "File In Use") even
    though we think it stopped. taskkill /T kills the whole tree."""
    if proc is None or proc.poll() is not None:
        return
    if os.name == 'nt':
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except Exception:
            pass
    try: proc.terminate()
    except Exception: pass


def _child_launch_cmd(target, is_exe):
    """Command line to start a duplicated child program, or None if it cannot
    be started from here.

    THE TRAP THIS EXISTS FOR: the obvious fallback for a .py child is
    [sys.executable, target]. From source that is python.exe and works. From a
    PyInstaller build sys.executable is IGNOAPI.EXE, and the bootloader
    ignores the trailing script path -- so every "child" launch started
    another complete ignoAPI, each of which started its own children, with the
    watchdogs relaunching the casualties every five seconds. The result looks
    exactly like a fork bomb, because it is one.

    Frozen builds therefore refuse to run a .py child at all. There is no
    interpreter to hand it to, and guessing at one on PATH would be a
    different program from the one the user tested against.
    """
    if not _RUNNING_AS_APP:
        # IMPORTED, not run. Every per-variable launcher goes through here, so
        # this one line is what stops an import spawning helpers: a test that
        # imports ignoAPI reads the REAL registries next to it, and its
        # watchdogs would then launch a second copy of every child belonging
        # to the ignoAPI already running on that machine -- two FTP servers on
        # one port, two syncs writing the same rows. (Observed, not imagined.)
        return None
    if is_exe:
        return [target]
    if getattr(sys, "frozen", False):
        return None
    return [sys.executable, target]


# True only when ignoAPI is the program being RUN. Nothing may start a child
# process while it is False -- see _child_launch_cmd and exec_launch.
_RUNNING_AS_APP = False


def _frozen_child_hint(name, exe_name):
    return (f"ERROR: {exe_name} not found next to ignoAPI.exe. A packaged "
            f"ignoAPI cannot run the .py version of '{name}' -- build "
            f"{exe_name} and put it in the same folder.")


# Every helper ignoAPI duplicates per variable. The .exe wins whenever it
# exists, so each of these is a place a stale build can hide.
HELPER_PROGRAMS = ["autoclient", "autocom", "autoModbusMaster",
                   "autoModbusSlave", "autoSyncIgnoAPI", "autoVDA"]

# A rebuild and a source edit can land in the same second; only flag a
# difference big enough to be a real "forgot to rebuild".
STALE_SKEW_SEC = 5.0


def stale_helpers():
    """[(stem, py_mtime, exe_mtime)] for helpers whose .exe predates its .py."""
    out = []
    for stem in HELPER_PROGRAMS:
        py = os.path.join(SCRIPT_DIR, stem + ".py")
        exe = os.path.join(SCRIPT_DIR, stem + ".exe")
        try:
            if not (os.path.exists(py) and os.path.exists(exe)):
                continue          # source-only is fine: the .py is then used
            pm, em = os.path.getmtime(py), os.path.getmtime(exe)
        except OSError:
            continue
        if pm > em + STALE_SKEW_SEC:
            out.append((stem, pm, em))
    return out


def warn_stale_helpers():
    """Say so, loudly, at startup. Never fatal — an out-of-date helper still
    runs, it just runs the old code."""
    stale = stale_helpers()
    if not stale:
        return []
    print("\n" + "!" * 70)
    print("[ignoAPI] STALE BUILD — these helpers have a .py NEWER than their .exe.")
    print("          The .exe is the one that runs, so recent changes to the")
    print("          source are NOT in effect:")
    for stem, pm, em in stale:
        print(f"            {stem:<20} py {time.strftime('%Y-%m-%d %H:%M', time.localtime(pm))}"
              f"   exe {time.strftime('%Y-%m-%d %H:%M', time.localtime(em))}")
    print("          Rebuild:  python build_all.py "
          + " ".join(stem for stem, _p, _e in stale))
    print("!" * 70 + "\n")
    return stale


# ── RELAUNCH GATE ─────────────────────────────────────────────────
# A child that dies within seconds of every launch is not going to be
# fixed by launching it again. The commonest cause is a port already in
# use, which no amount of retrying frees -- and the retry loop buries the
# one line saying so under a copy of the traceback every five seconds.
#
# So each module/variable gets a counter. Three fast deaths and the
# watchdog stops, says why once, and writes the reason where the table
# can show it. A child that ran for longer than RELAUNCH_FAST_SEC counts
# as a real run and clears the count, so an occasional crash still
# restarts forever, which is what a watchdog is for.
RELAUNCH_FAST_SEC = 12.0
RELAUNCH_MAX_FAILS = 3

_relaunch_gate = {}          # (kind, name) -> [fails, launched_at]
# Said once per module, not once per watchdog tick -- the whole point
# is to stop the console scrolling.
relaunch_gave_up_said = {}
_relaunch_lock = threading.Lock()


def relaunch_allowed(kind, name):
    """True if the watchdog should start this one again."""
    now = time.time()
    with _relaunch_lock:
        st = _relaunch_gate.get((kind, name))
        if st is None:
            _relaunch_gate[(kind, name)] = [0, now]
            return True
        fails, started = st
        if now - started >= RELAUNCH_FAST_SEC:
            st[0] = 0                    # it ran properly; forgive the past
        else:
            st[0] = fails + 1
        st[1] = now
        return st[0] < RELAUNCH_MAX_FAILS


def relaunch_gave_up(kind, name):
    with _relaunch_lock:
        st = _relaunch_gate.get((kind, name))
    return bool(st and st[0] >= RELAUNCH_MAX_FAILS)


def relaunch_reset(kind, name):
    """Forget the failures -- a person asked for it again."""
    with _relaunch_lock:
        _relaunch_gate.pop((kind, name), None)

def _kill_stale_by_image(target):
    """Kill anything still running the duplicate at `target`.

    _kill_process_tree only reaches the process this ignoAPI started. A
    child that outlived the ignoAPI that launched it is invisible to it --
    the registry of running processes is in memory and went with the
    restart -- so the watchdog calls the module dead, launches a second
    copy, and that one cannot bind the port the orphan is still holding.
    The loop that follows never ends, because retrying does not free a
    port.

    Matching on the IMAGE NAME is safe here precisely because every module
    is duplicated per variable: only this variable's child is ever called
    commonshares_autoftp.exe, so this cannot reach anything else.
    """
    exe = os.path.basename(target or "")
    if not exe.lower().endswith(".exe") or os.name != "nt":
        return 0
    try:
        r = subprocess.run(
            ["taskkill", "/F", "/T", "/IM", exe],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        return 0
    if r.returncode == 0:
        print(f"[ignoAPI] reclaimed an orphaned {exe} from a previous run")
        time.sleep(0.35)
        return 1
    return 0

def _refresh_duplicate(source, target):
    """Copy `source` to `target` if the target is missing OR OUT OF DATE.

    Returns (ok, error_message).

    The out-of-date half is the point. Both autoclient and the modbus master
    work by DUPLICATING one program per variable, and the original code copied
    only when the target did not exist. So the copy was made once, at create
    time, and then never again -- every later improvement to autoclient.py or
    autoModbusMaster.py was invisible to every variable already using it.

    That failure is genuinely baffling from the outside: the source plainly
    contains the feature, the program is plainly running, and the feature
    plainly does nothing. It cost real debugging time when a LOOP command was
    ignored by a master duplicated an hour before LOOP existed.

    Comparing mtime AND size rather than hashing keeps this cheap enough to
    run on every launch, which is what makes it reliable -- a refresh that
    only happens on request is a refresh that gets forgotten.

    The caller must have stopped the process first: on Windows a running .exe
    cannot be overwritten. That is enforced here rather than trusted --
    see _kill_stale_by_image for why the caller's stop is not enough on its
    own.
    """
    _kill_stale_by_image(target)
    if not os.path.exists(source):
        # Nothing to copy from. An existing target still runs -- a missing
        # build is not a reason to break a working deployment.
        return (os.path.exists(target),
                None if os.path.exists(target) else f"{os.path.basename(source)} not found")
    try:
        if os.path.exists(target):
            s, t = os.stat(source), os.stat(target)
            if int(t.st_mtime) >= int(s.st_mtime) and t.st_size == s.st_size:
                return True, None       # already current
            print(f"[ignoAPI] refreshing {os.path.basename(target)} "
                  f"-- {os.path.basename(source)} is newer")
        shutil.copy2(source, target)
        return True, None
    except OSError as e:
        # A stale copy that still runs beats no copy at all, so this is only
        # fatal when there is nothing to fall back to.
        if os.path.exists(target):
            print(f"[ignoAPI] could not refresh {os.path.basename(target)} "
                  f"({e}) -- continuing with the existing copy")
            return True, None
        return False, str(e)


def autoclient_stop(name):
    with _ac_lock:
        proc = _ac_procs.pop(name, None)
        _ac_last_seen.pop(name, None)
    _kill_process_tree(proc)


def autoclient_launch(name):
    """Duplicate the autoclient program for <name> if needed, then (re)start
    it. Re-resolves the IP from MAC (if a MAC is configured) fresh on EVERY
    launch -- covers create, reconnect, edit-relaunch, and startup autoload --
    so a device that moved to a new DHCP lease is still found. If no MAC is
    set, the configured server_ip is used directly, unchanged. A failed
    lookup doesn't block the launch; the connectivity heartbeat
    (autoclient_is_live) will simply show red once the connection can't be
    made. Returns True on launch."""
    source, target, _, is_exe = _ac_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] autoclient: no autoclient.exe/.py found to duplicate for '{name}'")
        return False

    # Stop before copying: a running .exe is locked on Windows. autoclient_stop
    # is called again further down for the port/state reasons -- stopping an
    # already-stopped client is a no-op.
    autoclient_stop(name)
    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] autoclient: could not duplicate program for '{name}': {err}")
        return False

    with _ac_lock:
        cfg = dict(_autoclients.get(name, {}))
    mac = (cfg.get("mac") or "").strip()
    if mac:
        found = ip_from_mac(mac)
        if found:
            cfg["server_ip"] = found
            with _ac_lock:
                if name in _autoclients:
                    _autoclients[name]["server_ip"] = found
            _save_autoclients()
            print(f"[ignoAPI] autoclient '{name}': resolved IP {found} from MAC {mac}")
        else:
            print(f"[ignoAPI] autoclient '{name}': MAC {mac} not in ARP table -- "
                  f"keeping last known IP {cfg.get('server_ip') or '(none)'}")
    _write_ac_config(name, cfg)

    autoclient_stop(name)
    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        print(f"[ignoAPI] autoclient '{name}': " + _frozen_child_hint(name, "autoclient.exe"))
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _ac_lock:
            _ac_procs[name] = proc
            _ac_last_seen.pop(name, None)   # fresh run -- not yet confirmed live
            _ac_disabled.discard(name)      # an explicit (re)launch always re-arms the watchdog
        print(f"[ignoAPI] autoclient '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] autoclient launch failed for '{name}': {e}")
        return False


def autoclient_create(name, cfg):
    """Register + configure + launch a new autoclient for variable <name>.
    Returns (ok, error_message). Refuses up front (no registry entry, no
    variable row created) if neither autoclient.exe nor autoclient.py exists
    next to ignoAPI to duplicate -- previously this was only ever noticed
    later as a silent console print from autoclient_launch(), with the
    autoclient still "created" (registered, greyed out, never live) and no
    way to know why from the GUI."""
    exe_src = os.path.join(SCRIPT_DIR, "autoclient.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoclient.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        msg = "autoclient.exe (or autoclient.py) not found next to ignoAPI -- cannot create an autoclient."
        print(f"[ignoAPI] autoclient create '{name}' refused: {msg}")
        return False, msg
    with _ac_lock:
        _autoclients[name] = {k: cfg.get(k) for k in AC_FIELDS}
    _save_autoclients()
    _write_ac_config(name, cfg)
    if name not in _variable_store:      # show the row right away
        _create_or_write(name, "")
    autoclient_launch(name)
    return True, None


def autoclient_edit(name, cfg):
    """Rewrite an existing autoclient's config; relaunch if it was running."""
    was_live = autoclient_is_live(name)
    with _ac_lock:
        _autoclients[name] = {k: cfg.get(k) for k in AC_FIELDS}
    _save_autoclients()
    _write_ac_config(name, cfg)
    if was_live:
        autoclient_launch(name)


def autoclient_reconnect(name):
    if is_autoclient(name):
        autoclient_launch(name)


def autoclient_disconnect(name):
    autoclient_stop(name)
    with _ac_lock:
        _ac_disabled.add(name)   # user-initiated stop -- watchdog must NOT auto-relaunch this


def _remove_with_retry(path, attempts=5, delay=0.2):
    """os.remove(), retrying briefly on PermissionError/OSError -- Windows can
    take a moment to actually release a just-killed process's file lock even
    after taskkill returns, so a single immediate attempt can spuriously fail
    and silently leave the .exe/.json behind."""
    for i in range(attempts):
        try:
            if os.path.exists(path):
                os.remove(path)
            return True
        except OSError:
            if i == attempts - 1:
                print(f"[ignoAPI] could not remove {path} (still locked?) -- leaving it in place")
                return False
            time.sleep(delay)


def autoclient_delete(name):
    """Stop the process, unregister, and remove the duplicated exe/py + json.
    (The variable itself is removed separately by the caller's normal delete.)"""
    autoclient_stop(name)
    with _ac_lock:
        _autoclients.pop(name, None)
        _ac_disabled.discard(name)
    _save_autoclients()
    _, target, json_path, _ = _ac_paths(name)
    for p in (target, json_path):
        _remove_with_retry(p)


_shutting_down = False  # once True, the watchdog stops resurrecting anything --
                        # otherwise it can race a shutdown-in-progress and relaunch
                        # a process in the same instant _stop_all_autoclients kills it


def _stop_all_autoclients():
    """Terminate every running autoclient_<name>.exe/.py subprocess. Call this
    whenever ignoAPI itself is going away (normal quit, restart) -- otherwise
    the spawned pollers keep running in the background as orphans after
    ignoAPI closes."""
    global _shutting_down
    _shutting_down = True
    with _ac_lock:
        names = list(_ac_procs.keys())
    for name in names:
        autoclient_stop(name)


atexit.register(_stop_all_autoclients)  # backstop: any exit path (crash, unhandled
                                         # exception, Ctrl+C) also reaps autoclient children


def autoclient_startup_launch_all():
    """On ignoAPI startup, (re)launch every autoclient whose runatstartup is set."""
    with _ac_lock:
        items = list(_autoclients.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            autoclient_launch(name)


AC_WATCHDOG_INTERVAL_SEC = 5.0


def _ac_watchdog_loop():
    """Without this, a newly-created autoclient whose subprocess dies or never
    comes up (crash, transient antivirus lock on the just-duplicated exe, ARP
    not yet settled, etc.) stayed dead for the rest of the session -- the only
    way to recover was to close and reopen ignoAPI (which re-runs
    autoclient_startup_launch_all()) or manually hit Reconnect. This relaunches
    any registered autoclient whose process has exited, every few seconds, so
    new data starts flowing again without a restart. Skips anything the user
    explicitly Disconnected (see _ac_disabled)."""
    while True:
        time.sleep(AC_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _ac_lock:
            names = [n for n in _autoclients if n not in _ac_disabled]
        for name in names:
            with _ac_lock:
                proc = _ac_procs.get(name)
            if proc is None or proc.poll() is not None:
                print(f"[ignoAPI] autoclient watchdog: '{name}' is not running -- relaunching")
                autoclient_launch(name)


_ac_watchdog_thread = threading.Thread(target=_ac_watchdog_loop, daemon=True)
_ac_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# COM CLIENT MANAGER
#   A "COM variable" is fed by a serial port. Unlike an autoclient (which
#   spawns autoclient_<name>.exe to poll a *remote* TCP device), a serial port
#   is local, so each COM variable is driven by an in-process reader THREAD.
#   That is deliberate: no exe to duplicate/lock, and the thread can report
#   connection state instantly, which is what makes the "keep retrying and
#   show the status" behaviour possible.
#
#   Every COM variable owns a companion status variable named
#       <name>_com<port>_status        e.g. mag on COM8 -> mag_com8_status
#   holding the live connection state / error code. It is created with the
#   COM variable and deleted with it.
# ──────────────────────────────────────────────────────────────
COMCLIENTS_FILE = "comclients.json"

CC_FIELDS = ["port", "baud", "probe", "command", "poll_interval_sec",
             "connect_timeout_sec", "read_timeout_sec", "log_file", "runatstartup"]

CC_BAUD_CHOICES = ["4800", "9600", "38400", "115200"]

# The probe lives in comserial so ignoAPI and autocom cannot disagree about
# what "the device answered OK" means. ignoAPI needs it only for the modal's
# Detect button -- a deliberate user action. Startup autodetect happens inside
# each autocom child now, so it no longer delays the window appearing.
import ignodiscover
import ignomdns
import ignotext
from comserial import list_com_ports, _cc_probe_port, CC_PROBE_REPLY_RE

# command == this  ->  pure listen: read whatever the device streams.
# anything else    ->  write the command, then read the reply.
CC_LISTEN_CMD = "0x01"

CC_RETRY_SEC = 3.0          # gap between reconnect attempts while down


def cc_default_fields():
    """Blank create-modal field values (strings, as the UI edits them)."""
    return {"port": (list_com_ports() or [""])[0], "baud": "115200",
            "probe": "", "command": CC_LISTEN_CMD, "poll_interval_sec": "0.1",
            "connect_timeout_sec": "5", "read_timeout_sec": "1",
            "log_file": "com_responses.log", "runatstartup": "false"}


def cc_fields_from_config(cfg):
    """Prefill the edit modal from an existing COM client config."""
    f = cc_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def cc_cast_fields(fields):
    """Turn the modal's string fields into a properly-typed config dict."""
    def num(s, cast, default):
        try:
            return cast(str(s).strip())
        except (ValueError, TypeError):
            return default
    return {
        "port":                (fields.get("port") or "").strip().upper(),
        "baud":                num(fields.get("baud"), int, 115200),
        # Probe string for autodetect. Blank = this client keeps whatever port
        # it was given and is never re-discovered.
        "probe":               (fields.get("probe") or "").strip(),
        "command":             (fields.get("command") or "").strip(),
        "poll_interval_sec":   num(fields.get("poll_interval_sec"), float, 0.1),
        "connect_timeout_sec": num(fields.get("connect_timeout_sec"), float, 5),
        "read_timeout_sec":    num(fields.get("read_timeout_sec"), float, 1),
        "log_file":            (fields.get("log_file") or "com_responses.log").strip() or "com_responses.log",
        "runatstartup":        str(fields.get("runatstartup", "false")).strip().lower() in ("true", "1", "yes", "on"),
    }


def cc_status_var(name, port=None):
    """Companion status variable name: mag + COM8 -> 'mag_com8_status'."""
    if port is None:
        port = (comclient_config(name) or {}).get("port", "")
    p = str(port or "").strip().lower().replace(" ", "")
    return f"{name}_{p}_status" if p else f"{name}_com_status"


def cc_tx_var(name):
    """Companion TRANSMIT variable: 'mag' -> 'mag_tx'.

    Whatever is put in here is sent out of the port -- same port, same baud as
    the reader -- and the field is then cleared back to "". The clear is what
    makes it usable as a command box: an empty field means "nothing pending",
    so typing the same command twice in a row actually sends it twice.

    It is unconditionally named <name>_tx (unlike the status companion, which
    carries the port) because the user types into this one, and a name that
    changes when the port is reassigned would be a moving target.
    """
    return f"{name}_tx"


def is_com_tx_var(name):
    """True for the auto-created <name>_tx companions."""
    with _cc_lock:
        owners = list(_comclients.keys())
    return any(name == cc_tx_var(o) for o in owners)


def cc_tx_owner(name):
    """The COM variable a _tx companion belongs to, or None."""
    with _cc_lock:
        owners = list(_comclients.keys())
    for o in owners:
        if name == cc_tx_var(o):
            return o
    return None


def _load_comclients():
    if os.path.exists(COMCLIENTS_FILE):
        try:
            with open(COMCLIENTS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: comclients.json corrupt — starting fresh.")
    return {}


_comclients   = _load_comclients()   # name -> config dict
_cc_procs     = {}                   # name -> subprocess.Popen
_cc_disabled  = set()                # names the user explicitly Disconnected
_cc_lock      = threading.Lock()


def _save_comclients():
    tmp = COMCLIENTS_FILE + ".tmp"
    try:
        with _cc_lock:
            snapshot = dict(_comclients)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, COMCLIENTS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save comclients.json: {e}")


def is_comclient(name):
    with _cc_lock:
        return name in _comclients


def comclient_config(name):
    with _cc_lock:
        return dict(_comclients.get(name, {}))


def is_com_status_var(name):
    """True for the auto-created <name>_com<port>_status companions."""
    with _cc_lock:
        owners = list(_comclients.keys())
    for owner in owners:
        if name == cc_status_var(owner):
            return True
    return False


def is_com_row(name):
    """True for a COM variable OR either of its companions (_status, _tx).

    The UI needs "does this row belong to the serial family?" in several
    places -- the SERIAL filter, the exclusion list for the plain-variables
    filter, row colouring -- and listing the three predicates at each site is
    how one of them ends up missing a companion.
    """
    return is_comclient(name) or is_com_status_var(name) or is_com_tx_var(name)


def comclient_is_live(name):
    """Green dot: the reader PROCESS is running AND the link is actually up.

    Both halves are needed. The process stays alive while it retries a port
    that is not there, so "running" alone would show green for a device that
    has never connected; and the status variable is the only thing that knows,
    because the port is owned by a different process now.
    """
    with _cc_lock:
        proc = _cc_procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        st = _read(cc_status_var(name))
    except Exception:
        return False
    return str(st or "").strip().upper().startswith(("CONNECTED", "TX "))


def _cc_paths(name):
    """(source, target, json_path, is_exe) for COM reader <name>.

    Prefers the compiled autocom.exe and falls back to autocom.py, so the
    feature works in development before the exe has ever been built.
    """
    exe_src = os.path.join(SCRIPT_DIR, "autocom.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autocom.py")
    if os.path.exists(exe_src):
        return (exe_src,
                os.path.join(SCRIPT_DIR, f"{name}_autocom.exe"),
                os.path.join(SCRIPT_DIR, f"{name}_autocom.json"), True)
    return (py_src,
            os.path.join(SCRIPT_DIR, f"{name}_autocom.py"),
            os.path.join(SCRIPT_DIR, f"{name}_autocom.json"), False)


def _write_cc_config(name, cfg):
    """Write <name>_autocom.json, injecting the write-back target so the
    duplicated program knows which ignoAPI and which variable to feed."""
    _, _, json_path, _ = _cc_paths(name)
    full = {k: cfg.get(k) for k in CC_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def cc_autodetect_port(probe, baud, exclude_bluetooth=True, skip_ports=()):
    """Find the port whose device replies OK to `probe`.

    Returns (port_or_None, report_lines).
    """
    probe = str(probe or "").strip()
    if not probe:
        return None, ["no probe command given"]

    try:
        import serial.tools.list_ports
        candidates = list(serial.tools.list_ports.comports())
    except Exception as e:
        return None, [f"cannot enumerate serial ports: {e}"]

    report = []
    for info in candidates:
        dev = info.device
        desc = (getattr(info, "description", "") or "")
        hwid = (getattr(info, "hwid", "") or "")
        if dev in skip_ports:
            report.append(f"{dev}: skipped (already in use by another COM client)")
            continue
        # Probing a Bluetooth SPP port makes Windows dial the paired device,
        # which blocks for a long time and answers nothing useful.
        if exclude_bluetooth and ("bluetooth" in desc.lower()
                                  or "bthenum" in hwid.lower()):
            report.append(f"{dev}: skipped (Bluetooth)")
            continue
        ok, reply = _cc_probe_port(dev, probe, baud)
        if ok:
            report.append(f"{dev}: replied {reply!r}  <-- MATCH")
            return dev, report
        report.append(f"{dev}: {reply[:60]!r}" if reply else f"{dev}: no reply")
    return None, report


def comclient_launch(name):
    """Refresh the duplicated reader program for <name>, then (re)start it."""
    source, target, _, is_exe = _cc_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] COM: no autocom.exe/.py found to duplicate for '{name}'")
        _create_or_write(cc_status_var(name),
                         "ERROR: autocom.exe (or autocom.py) not found next to ignoAPI")
        return False

    # Stop BEFORE copying. The old process owns the exclusive-access serial
    # port -- a second one would open straight into PermissionError(13) -- and
    # on Windows a running .exe is locked against being overwritten.
    comclient_stop(name)

    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] COM: could not duplicate program for '{name}': {err}")
        _create_or_write(cc_status_var(name),
                         f"ERROR: could not create {os.path.basename(target)}: {err}")
        return False

    # Make sure the companions exist. Doing it on every launch (rather than
    # only on create) is what gives clients saved before a companion existed
    # their row back, with no migration step.
    try:
        if _read(cc_tx_var(name)) is None:
            _create_or_write(cc_tx_var(name), "")
    except Exception:
        _create_or_write(cc_tx_var(name), "")
    _write_cc_config(name, comclient_config(name))

    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        msg = _frozen_child_hint(name, "autocom.exe")
        print(f"[ignoAPI] COM client '{name}': {msg}")
        _create_or_write(cc_status_var(name), msg)
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _cc_lock:
            _cc_procs[name] = proc
            _cc_disabled.discard(name)
        print(f"[ignoAPI] COM client '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] COM client launch failed for '{name}': {e}")
        _create_or_write(cc_status_var(name), f"ERROR: launch failed: {e}")
        return False


def comclient_stop(name):
    with _cc_lock:
        proc = _cc_procs.pop(name, None)
    _kill_process_tree(proc)


def comclient_create(name, cfg):
    """Register `name` as a COM variable and start it. Returns (ok, err)."""
    port = str(cfg.get("port", "")).strip()
    if not port:
        return False, "Pick a COM port"
    if is_autoclient(name):
        return False, f"'{name}' is already an autoclient"
    with _cc_lock:
        _comclients[name] = {k: cfg.get(k) for k in CC_FIELDS}
    _save_comclients()
    exe_src = os.path.join(SCRIPT_DIR, "autocom.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autocom.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        # Refuse UP FRONT rather than registering a client that can never run.
        msg = "autocom.exe (or autocom.py) not found next to ignoAPI — cannot create a COM client."
        print(f"[ignoAPI] COM create '{name}' refused: {msg}")
        with _cc_lock:
            _comclients.pop(name, None)
        return False, msg
    if name not in _variable_store:      # show the row right away
        _create_or_write(name, "")
    # companions, created up-front so they are visible immediately
    _create_or_write(cc_status_var(name), "CREATED — not connected yet")
    _create_or_write(cc_tx_var(name), "")
    comclient_launch(name)
    return True, ""


def comclient_edit(name, cfg):
    """Update the config and restart the reader so it takes effect at once."""
    old_status = cc_status_var(name)
    with _cc_lock:
        _comclients[name] = {k: cfg.get(k) for k in CC_FIELDS}
    _save_comclients()
    new_status = cc_status_var(name)
    if new_status != old_status:
        # the port changed, so the companion's name changed with it
        try:
            _delete(old_status)
        except Exception:
            pass
    comclient_launch(name)


def comclient_reconnect(name):
    if is_comclient(name):
        # A person asked for it: forget the failures, or the watchdog
        # would refuse to start something they have just fixed.
        relaunch_reset("com", name)
        relaunch_gave_up_said.pop(("com", name), None)
        comclient_launch(name)


def comclient_disconnect(name):
    """Stop the reader and leave it stopped (the watchdog skips disabled names)."""
    comclient_stop(name)
    with _cc_lock:
        _cc_disabled.add(name)
    _create_or_write(cc_status_var(name), "DISCONNECTED (by user)")
    print(f"[ignoAPI] COM client '{name}' disconnected by user")


def comclient_delete(name):
    """Stop the reader, unregister, and delete the companion status variable.
    (The variable itself is removed by the caller's normal delete.)"""
    # Resolve the companion names BEFORE unregistering — cc_status_var() looks
    # the port up in the registry, so after the pop it would return the wrong
    # name and strand the very variable it is meant to clean up.
    companions = [cc_status_var(name), cc_tx_var(name)]
    comclient_stop(name)
    with _cc_lock:
        _comclients.pop(name, None)
        _cc_disabled.discard(name)
    _save_comclients()
    # The companions exist only to serve this COM variable, so they go with
    # it — otherwise deleting 'mag' would strand 'mag_com8_status' and
    # 'mag_tx' as permanent orphans with no owner to clean them up.
    for cv in companions:
        try:
            _delete(cv)
            print(f"[ignoAPI] removed companion variable '{cv}'")
        except Exception as e:
            print(f"[ignoAPI] could not remove '{cv}': {e}")
    # Remove the duplicated program and its config too, so a later client of
    # the same name cannot silently inherit a stale exe.
    _, target, json_path, _ = _cc_paths(name)
    for path in (json_path, target):
        if os.path.exists(path):
            _remove_with_retry(path)


def _stop_all_comclients():
    """Stop every reader process when ignoAPI itself is going away."""
    with _cc_lock:
        names = list(_cc_procs.keys())
    for name in names:
        comclient_stop(name)


atexit.register(_stop_all_comclients)


def comclient_startup_launch_all():
    """On ignoAPI startup, connect every COM client whose runatstartup is set.
    A port that is not there yet does NOT fail permanently — the reader thread
    publishes the error and keeps retrying on its own."""
    with _cc_lock:
        items = list(_comclients.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            comclient_launch(name)


CC_WATCHDOG_INTERVAL_SEC = 5.0


def _cc_watchdog_loop():
    """Restart any reader process that has exited. Connection failures are the
    child's own business -- it retries and reports into its status variable --
    so this only covers the process itself dying. Skips names the user
    explicitly Disconnected."""
    while True:
        time.sleep(CC_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _cc_lock:
            names = [n for n in _comclients if n not in _cc_disabled]
            procs = {n: _cc_procs.get(n) for n in names}
        for name in names:
            proc = procs.get(name)
            if proc is None or proc.poll() is not None:
                if not relaunch_allowed("com", name):
                    if not relaunch_gave_up_said.get(("com", name)):
                        relaunch_gave_up_said[("com", name)] = True
                        print(f"[ignoAPI] '{name}' died on every start "
                              f"-- giving up. The usual cause is the port "
                              f"already being in use: read the traceback "
                              f"above, fix that, then Reconnect.")
                        try:
                            _create_or_write(cc_status_var(name),
                                             "STOPPED — kept crashing on start; see the console")
                        except Exception:
                            pass
                    continue
                print(f"[ignoAPI] COM watchdog: '{name}' is not running -- restarting")
                comclient_launch(name)


_cc_watchdog_thread = threading.Thread(target=_cc_watchdog_loop, daemon=True)
_cc_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# MODBUS MASTER MANAGER
#   A "MODBUS variable" speaks Modbus RTU over a serial port. It is the third
#   kind of fed variable, after autoclients (TCP) and COM clients (raw serial).
#
#   It follows the AUTOCLIENT model, not the COM one: the traffic runs in a
#   separate process (<name>_automodbusmaster.exe), never in an ignoAPI
#   thread. Two reasons, and the first is the important one:
#
#     * A serial port is exclusive-access. If ignoAPI also opened it in a
#       thread, the external program could never connect -- the two would
#       simply fight over the port. Choosing ONE owner removes the whole
#       class of problem.
#     * Modbus RTU is latency-sensitive (inter-frame gaps, response
#       timeouts). A dedicated process is not competing with a 30fps pygame
#       loop for the GIL.
#
#   Creating a master on variable `mag` also creates five companions:
#       mag_readReg    "<ids>,<addr>[,<count>]"  -> read holding register(s)
#       mag_readCoil   "<ids>,<addr>[,<count>]"  -> read coil(s)
#       mag_writeReg   "<ids>,<addr>,<value>"    -> write a holding register
#       mag_writeCoil  "<ids>,<addr>,<value>"    -> write a coil
#       mag_status     connection state / error codes
#   Results land in `mag` itself. See MODBUS_COMMAND_HELP below for the
#   addressing syntax.
# ──────────────────────────────────────────────────────────────
MODBUSMASTERS_FILE = "modbusmasters.json"

MM_FIELDS = ["port", "baud", "parity", "stopbits", "bytesize",
             "timeout_sec", "poll_interval_sec", "log_file", "runatstartup"]

MM_BAUD_CHOICES   = ["4800", "9600", "19200", "38400", "57600", "115200"]
MM_PARITY_CHOICES = ["N", "E", "O"]
MM_STOPBIT_CHOICES = ["1", "2"]
MM_BYTESIZE_CHOICES = ["8", "7"]

# The four command companions, in the order they appear in the table.
MM_CMD_SUFFIXES = ["readReg", "writeReg", "readCoil", "writeCoil"]

# Both the master and the slave publish <name>_status. Named once so the two
# managers cannot drift onto different suffixes.
MM_STATUS_SUFFIX = "status"

MODBUS_COMMAND_HELP = """\
Device ids:  1            a single slave
             1-4-9        several slaves, in this order
             b            broadcast (unit 0, writes only -- nothing replies)

  mag_readReg    1,0x1015         read holding register 0x1015 from slave 1
  mag_readReg    1-4-9,0x0001     read 0x0001 from slaves 1, 4 and 9
                                  -> mag becomes "{id1},{id4},{id9}"
  mag_readReg    1,0x1015,4       read 4 consecutive registers from slave 1
  mag_writeReg   2,0x0001,0x01    write 0x01 to register 0x0001 of slave 2
  mag_writeReg   1-2-4-7,0x0001,5525
  mag_writeReg   b,0x0001,0x01    broadcast the write to every slave
  mag_readCoil / mag_writeCoil    identical, on coils

A count is only allowed with a SINGLE id -- with a list, "1,2,3" would be
ambiguous between "three slaves" and "three registers".

EVERY COMMAND RUNS ONCE and then clears its own field -- reads and writes
alike. The field going empty is the receipt that it ran.

To repeat one, add LOOP:

  mag_writeReg   3,0x1801,0x4002,LOOP    write it every poll, forever
  mag_readReg    1,0x1015,LOOP           re-read it every poll, forever

The field then stays put and mag_status shows a live count and rate. Clear
the field (right-click -> Clear command) to stop it."""


def mm_default_fields():
    """Blank create-modal field values (strings, as the UI edits them)."""
    return {"port": (list_com_ports() or [""])[0], "baud": "38400",
            "parity": "N", "stopbits": "1", "bytesize": "8",
            "timeout_sec": "1", "poll_interval_sec": "0.2",
            "log_file": "modbus_master.log", "runatstartup": "false"}


def mm_fields_from_config(cfg):
    f = mm_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def mm_cast_fields(fields):
    """Turn the modal's string fields into a properly-typed config dict."""
    def num(s, cast, default):
        try:
            return cast(str(s).strip())
        except (ValueError, TypeError):
            return default
    parity = (fields.get("parity") or "N").strip().upper()[:1]
    return {
        "port":              (fields.get("port") or "").strip().upper(),
        "baud":              num(fields.get("baud"), int, 38400),
        "parity":            parity if parity in ("N", "E", "O") else "N",
        "stopbits":          num(fields.get("stopbits"), int, 1),
        "bytesize":          num(fields.get("bytesize"), int, 8),
        "timeout_sec":       num(fields.get("timeout_sec"), float, 1.0),
        "poll_interval_sec": num(fields.get("poll_interval_sec"), float, 0.2),
        "log_file":          (fields.get("log_file") or "modbus_master.log").strip()
                             or "modbus_master.log",
        "runatstartup":      str(fields.get("runatstartup", "false")).strip().lower()
                             in ("true", "1", "yes", "on"),
    }


def mm_status_var(name):
    """Companion status variable: 'mag' -> 'mag_status'."""
    return f"{name}_{MM_STATUS_SUFFIX}"


def mm_cmd_vars(name):
    """The four command companions, e.g. ['mag_readReg', ...]."""
    return [f"{name}_{suf}" for suf in MM_CMD_SUFFIXES]


def mm_sub_vars(name):
    """Every companion a master owns: the four commands plus the status."""
    return mm_cmd_vars(name) + [mm_status_var(name)]


def _load_modbusmasters():
    if os.path.exists(MODBUSMASTERS_FILE):
        try:
            with open(MODBUSMASTERS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: modbusmasters.json corrupt — starting fresh.")
    return {}


_modbusmasters = _load_modbusmasters()   # name -> config dict
_mm_procs      = {}                      # name -> subprocess.Popen
_mm_disabled   = set()                   # names the user explicitly Disconnected
_mm_lock       = threading.Lock()


def _save_modbusmasters():
    tmp = MODBUSMASTERS_FILE + ".tmp"
    try:
        with _mm_lock:
            snapshot = dict(_modbusmasters)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, MODBUSMASTERS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save modbusmasters.json: {e}")


def is_modbusmaster(name):
    with _mm_lock:
        return name in _modbusmasters


def modbusmaster_config(name):
    with _mm_lock:
        return dict(_modbusmasters.get(name, {}))


def is_modbus_sub_var(name):
    """True for any of the five auto-created companions of a master."""
    with _mm_lock:
        owners = list(_modbusmasters.keys())
    for owner in owners:
        if name in mm_sub_vars(owner):
            return True
    return False


def is_modbus_row(name):
    """True for a MODBUS variable or any of its companions."""
    return is_modbusmaster(name) or is_modbus_sub_var(name)


def modbus_sub_owner(name):
    """The master a companion belongs to, or None."""
    with _mm_lock:
        owners = list(_modbusmasters.keys())
    for owner in owners:
        if name in mm_sub_vars(owner):
            return owner
    return None


def _mm_paths(name):
    """(source, target, json_path, is_exe) for master <name>.

    Prefers the compiled autoModbusMaster.exe and falls back to the .py, so
    the feature works in development before the exe has ever been built.
    """
    exe_src = os.path.join(SCRIPT_DIR, "autoModbusMaster.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoModbusMaster.py")
    if os.path.exists(exe_src):
        return (exe_src,
                os.path.join(SCRIPT_DIR, f"{name}_automodbusmaster.exe"),
                os.path.join(SCRIPT_DIR, f"{name}_automodbusmaster.json"), True)
    return (py_src,
            os.path.join(SCRIPT_DIR, f"{name}_automodbusmaster.py"),
            os.path.join(SCRIPT_DIR, f"{name}_automodbusmaster.json"), False)


def _write_mm_config(name, cfg):
    """Write <name>_automodbusmaster.json, injecting the write-back target so
    the duplicated program knows which ignoAPI and which variable to feed."""
    _, _, json_path, _ = _mm_paths(name)
    full = {k: cfg.get(k) for k in MM_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def modbusmaster_is_live(name):
    """Green dot: the process is running AND the status variable says the port
    is open. The process being alive is not enough -- it stays alive while it
    retries a port that is not there, and that must not read as healthy."""
    with _mm_lock:
        proc = _mm_procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        st = _read(mm_status_var(name))
    except Exception:
        return False
    return bool(st) and str(st).strip().upper().startswith(("CONNECTED", "OK"))


def modbusmaster_stop(name):
    with _mm_lock:
        proc = _mm_procs.pop(name, None)
    _kill_process_tree(proc)


def _mm_ensure_sub_vars(name):
    """Create the five companions if they are missing, leaving any existing
    values alone. Called on every launch, so a master saved before a companion
    was added gets it back with no migration step."""
    for v in mm_cmd_vars(name):
        try:
            if _read(v) is None:
                _create_or_write(v, "")
        except Exception:
            try:
                _create_or_write(v, "")
            except Exception:
                pass
    try:
        if _read(mm_status_var(name)) is None:
            _create_or_write(mm_status_var(name), "CREATED — not started yet")
    except Exception:
        try:
            _create_or_write(mm_status_var(name), "CREATED — not started yet")
        except Exception:
            pass


def modbusmaster_launch(name):
    """Refresh the duplicated master program for <name>, then (re)start it."""
    source, target, _, is_exe = _mm_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] modbus: no autoModbusMaster.exe/.py to duplicate for '{name}'")
        _create_or_write(mm_status_var(name),
                         "ERROR: autoModbusMaster.exe (or .py) not found next to ignoAPI")
        return False

    # Stop BEFORE copying, for two reasons: the old process owns the
    # exclusive-access serial port (a second one would open straight into
    # PermissionError(13)), and on Windows a running .exe is locked against
    # being overwritten.
    modbusmaster_stop(name)

    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] modbus: could not duplicate program for '{name}': {err}")
        _create_or_write(mm_status_var(name),
                         f"ERROR: could not create {os.path.basename(target)}: {err}")
        return False

    _mm_ensure_sub_vars(name)
    _write_mm_config(name, modbusmaster_config(name))

    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        msg = _frozen_child_hint(name, "autoModbusMaster.exe")
        print(f"[ignoAPI] modbus master '{name}': {msg}")
        _create_or_write(mm_status_var(name), msg)
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _mm_lock:
            _mm_procs[name] = proc
            _mm_disabled.discard(name)
        print(f"[ignoAPI] modbus master '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] modbus master launch failed for '{name}': {e}")
        _create_or_write(mm_status_var(name), f"ERROR: launch failed: {e}")
        return False


def modbusmaster_create(name, cfg):
    """Register + configure + launch a master for variable <name>.
    Returns (ok, error_message)."""
    if not str(cfg.get("port", "")).strip():
        return False, "Pick a COM port"
    if is_autoclient(name):
        return False, f"'{name}' is already an autoclient"
    if is_comclient(name):
        return False, f"'{name}' is already a COM client"
    exe_src = os.path.join(SCRIPT_DIR, "autoModbusMaster.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoModbusMaster.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        # Refuse UP FRONT rather than registering a master that can never run.
        # The autoclient version of this check was added after exactly that
        # failure: a registered, permanently-dead entry with no visible reason.
        msg = "autoModbusMaster.exe (or .py) not found next to ignoAPI — cannot create a master."
        print(f"[ignoAPI] modbus create '{name}' refused: {msg}")
        return False, msg

    with _mm_lock:
        _modbusmasters[name] = {k: cfg.get(k) for k in MM_FIELDS}
    _save_modbusmasters()
    if name not in _variable_store:      # show the row right away
        _create_or_write(name, "")
    _mm_ensure_sub_vars(name)
    # Print the syntax once, on creation. Five new rows appearing with no
    # indication of what to type into them is the moment the reference is
    # actually wanted, and the modal has nowhere near enough space for it.
    print(f"\n[ignoAPI] MODBUS master '{name}' — command syntax:\n"
          + "\n".join("    " + ln for ln in MODBUS_COMMAND_HELP.splitlines()) + "\n")
    modbusmaster_launch(name)
    return True, ""


def modbusmaster_edit(name, cfg):
    """Rewrite the config and relaunch so it takes effect at once."""
    with _mm_lock:
        _modbusmasters[name] = {k: cfg.get(k) for k in MM_FIELDS}
    _save_modbusmasters()
    modbusmaster_launch(name)


def modbusmaster_reconnect(name):
    if is_modbusmaster(name):
        # A person asked for it: forget the failures, or the watchdog
        # would refuse to start something they have just fixed.
        relaunch_reset("modbusmaster", name)
        relaunch_gave_up_said.pop(("modbusmaster", name), None)
        modbusmaster_launch(name)


def modbusmaster_disconnect(name):
    """Stop the process and leave it stopped (the watchdog skips disabled names)."""
    modbusmaster_stop(name)
    with _mm_lock:
        _mm_disabled.add(name)
    try:
        _create_or_write(mm_status_var(name), "DISCONNECTED (by user)")
    except Exception:
        pass
    print(f"[ignoAPI] modbus master '{name}' disconnected by user")


def modbusmaster_delete(name):
    """Stop the process, unregister, and delete all five companions.
    (The variable itself is removed by the caller's normal delete.)"""
    # Resolve companion names BEFORE unregistering — afterwards the registry
    # lookups would come back empty and the companions would be stranded.
    companions = mm_sub_vars(name)
    modbusmaster_stop(name)
    with _mm_lock:
        _modbusmasters.pop(name, None)
        _mm_disabled.discard(name)
    _save_modbusmasters()
    for cv in companions:
        try:
            _delete(cv)
            print(f"[ignoAPI] removed companion variable '{cv}'")
        except Exception as e:
            print(f"[ignoAPI] could not remove '{cv}': {e}")
    # Remove the duplicated program + its config too, so a later master of the
    # same name does not silently inherit a stale exe.
    _, target, json_path, _ = _mm_paths(name)
    for path in (json_path, target):
        if os.path.exists(path):
            _remove_with_retry(path)


def _stop_all_modbusmasters():
    with _mm_lock:
        names = list(_mm_procs.keys())
    for name in names:
        modbusmaster_stop(name)


atexit.register(_stop_all_modbusmasters)


def modbusmaster_startup_launch_all():
    """On ignoAPI startup, start every master whose runatstartup is set. A port
    that is not there yet is NOT a permanent failure — the external program
    publishes the error to <name>_status and keeps retrying on its own."""
    with _mm_lock:
        items = list(_modbusmasters.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            modbusmaster_launch(name)


MM_WATCHDOG_INTERVAL_SEC = 5.0


def _mm_watchdog_loop():
    """Restart any master process that has exited. Connection failures are the
    external program's own business (it retries and reports); this only covers
    the process itself dying. Skips names the user explicitly Disconnected."""
    while True:
        time.sleep(MM_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _mm_lock:
            names = [n for n in _modbusmasters if n not in _mm_disabled]
            procs = {n: _mm_procs.get(n) for n in names}
        for name in names:
            proc = procs.get(name)
            if proc is None or proc.poll() is not None:
                if not relaunch_allowed("modbusmaster", name):
                    if not relaunch_gave_up_said.get(("modbusmaster", name)):
                        relaunch_gave_up_said[("modbusmaster", name)] = True
                        print(f"[ignoAPI] '{name}' died on every start "
                              f"-- giving up. The usual cause is the port "
                              f"already being in use: read the traceback "
                              f"above, fix that, then Reconnect.")
                        try:
                            _create_or_write(mm_status_var(name),
                                             "STOPPED — kept crashing on start; see the console")
                        except Exception:
                            pass
                    continue
                print(f"[ignoAPI] modbus watchdog: '{name}' is not running -- restarting")
                modbusmaster_launch(name)


_mm_watchdog_thread = threading.Thread(target=_mm_watchdog_loop, daemon=True)
_mm_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# MODBUS SLAVE MANAGER
#   The mirror image of the master: instead of asking other devices for
#   registers, this HOSTS them. A master elsewhere on the bus reads and
#   writes, and the values it sees are ignoAPI variables -- so a register is
#   an editable row in the table, and a master writing to it updates that row
#   in front of you.
#
#   Registers come from a CSV register map chosen when the slave is created:
#
#       0x0001,1000
#       0x1012,2000
#       0x1045              <- no value: starts at 0
#       0x0005,1,coil       <- third column selects the table
#
#   Creating a slave on variable `mag` creates one variable per entry:
#       mag_reg_0x0001, mag_reg_0x1012, mag_coil_0x0005, ...
#   plus mag_status. The type is in the NAME because coils and registers are
#   separate address spaces in Modbus and may share an address.
#
#   Like the master it runs as a SEPARATE PROCESS: a serial port has exactly
#   one owner, and an RTU slave must answer within milliseconds, which is not
#   something to ask of a thread sharing the GIL with a 30fps GUI.
# ──────────────────────────────────────────────────────────────
MODBUSSLAVES_FILE = "modbusslaves.json"

MS_FIELDS = ["port", "baud", "parity", "stopbits", "bytesize", "slave_id",
             "timeout_sec", "register_map", "persist_csv", "log_file",
             "runatstartup"]

MS_SLAVE_ID_CHOICES = [str(i) for i in range(1, 11)]


def ms_default_fields():
    return {"port": (list_com_ports() or [""])[0], "baud": "38400",
            "parity": "N", "stopbits": "1", "bytesize": "8", "slave_id": "1",
            "timeout_sec": "1", "register_map": "", "persist_csv": "false",
            "log_file": "modbus_slave.log", "runatstartup": "false"}


def ms_fields_from_config(cfg):
    f = ms_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def ms_cast_fields(fields):
    def num(v, cast, default):
        try:
            return cast(str(v).strip())
        except (ValueError, TypeError):
            return default
    parity = (fields.get("parity") or "N").strip().upper()[:1]
    return {
        "port":         (fields.get("port") or "").strip().upper(),
        "baud":         num(fields.get("baud"), int, 38400),
        "parity":       parity if parity in ("N", "E", "O") else "N",
        "stopbits":     num(fields.get("stopbits"), int, 1),
        "bytesize":     num(fields.get("bytesize"), int, 8),
        "slave_id":     max(1, min(247, num(fields.get("slave_id"), int, 1))),
        "timeout_sec":  num(fields.get("timeout_sec"), float, 1.0),
        "register_map": (fields.get("register_map") or "").strip(),
        "persist_csv":  str(fields.get("persist_csv", "false")).strip().lower()
                        in ("true", "1", "yes", "on"),
        "log_file":     (fields.get("log_file") or "modbus_slave.log").strip()
                        or "modbus_slave.log",
        "runatstartup": str(fields.get("runatstartup", "false")).strip().lower()
                        in ("true", "1", "yes", "on"),
    }


def ms_status_var(name):
    return f"{name}_{MM_STATUS_SUFFIX}"


def ms_read_map(path):
    """Parse a register map for the UI: [(kind, addr, value), ...].

    This is the SAME parser the slave uses, imported rather than reimplemented
    -- ignoAPI needs it to know which variables to create and delete, and two
    parsers would eventually disagree about which registers exist.
    """
    from autoModbusSlave import load_register_map
    return load_register_map(path)


def ms_var_names(name, path=None):
    """Every variable a slave owns: one per map entry, plus the status row."""
    names = []
    path = path if path is not None else (modbusslave_config(name) or {}).get("register_map")
    try:
        from autoModbusSlave import var_name
        for kind, addr, _v in ms_read_map(path):
            names.append(var_name(name, kind, addr))
    except Exception:
        # A map that has gone missing or become unreadable must not stop the
        # status row being found -- otherwise the slave cannot even be deleted.
        pass
    names.append(ms_status_var(name))
    return names


def _load_modbusslaves():
    if os.path.exists(MODBUSSLAVES_FILE):
        try:
            with open(MODBUSSLAVES_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: modbusslaves.json corrupt — starting fresh.")
    return {}


_modbusslaves = _load_modbusslaves()
_ms_procs     = {}
_ms_disabled  = set()
_ms_lock      = threading.Lock()
_ms_varcache  = {}      # name -> [variable names], so a map that disappears
                        # later cannot strand the rows it created


def _save_modbusslaves():
    tmp = MODBUSSLAVES_FILE + ".tmp"
    try:
        with _ms_lock:
            snapshot = dict(_modbusslaves)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, MODBUSSLAVES_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save modbusslaves.json: {e}")


def is_modbusslave(name):
    with _ms_lock:
        return name in _modbusslaves


def modbusslave_config(name):
    with _ms_lock:
        return dict(_modbusslaves.get(name, {}))


def is_modbusslave_sub_var(name):
    with _ms_lock:
        owners = list(_modbusslaves.keys())
    for owner in owners:
        if name in _ms_varcache.get(owner, []) or name == ms_status_var(owner):
            return True
    return False


def is_modbusslave_row(name):
    return is_modbusslave(name) or is_modbusslave_sub_var(name)


def _ms_paths(name):
    exe_src = os.path.join(SCRIPT_DIR, "autoModbusSlave.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoModbusSlave.py")
    if os.path.exists(exe_src):
        return (exe_src,
                os.path.join(SCRIPT_DIR, f"{name}_automodbusslave.exe"),
                os.path.join(SCRIPT_DIR, f"{name}_automodbusslave.json"), True)
    return (py_src,
            os.path.join(SCRIPT_DIR, f"{name}_automodbusslave.py"),
            os.path.join(SCRIPT_DIR, f"{name}_automodbusslave.json"), False)


def _write_ms_config(name, cfg):
    _, _, json_path, _ = _ms_paths(name)
    full = {k: cfg.get(k) for k in MS_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def modbusslave_is_live(name):
    """Green dot: the process is running AND it says it is listening."""
    with _ms_lock:
        proc = _ms_procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        st = _read(ms_status_var(name))
    except Exception:
        return False
    return str(st or "").strip().upper().startswith("LISTENING")


def modbusslave_stop(name):
    with _ms_lock:
        proc = _ms_procs.pop(name, None)
    _kill_process_tree(proc)


def _ms_ensure_vars(name, cfg):
    """Create one variable per map entry, keeping any value already there.

    Existing values are kept because a slave that has been running holds live
    register contents -- re-reading the CSV on a restart must not reset them
    to whatever the file said hours ago.
    """
    created = []
    try:
        from autoModbusSlave import var_name
        entries = ms_read_map(cfg.get("register_map"))
    except Exception as e:
        _create_or_write(ms_status_var(name), f"ERROR in register map: {e}")
        print(f"[ignoAPI] modbus slave '{name}': {e}")
        return None
    for kind, addr, value in entries:
        vn = var_name(name, kind, addr)
        created.append(vn)
        try:
            if _read(vn) is None:
                _create_or_write(vn, value)
        except Exception:
            _create_or_write(vn, value)
    with _ms_lock:
        _ms_varcache[name] = list(created)
    try:
        if _read(ms_status_var(name)) is None:
            _create_or_write(ms_status_var(name), "CREATED — not started yet")
    except Exception:
        _create_or_write(ms_status_var(name), "CREATED — not started yet")
    return created


def modbusslave_launch(name):
    """Refresh the duplicated slave program for <name>, then (re)start it."""
    source, target, _, is_exe = _ms_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] modbus slave: no autoModbusSlave.exe/.py to duplicate for '{name}'")
        _create_or_write(ms_status_var(name),
                         "ERROR: autoModbusSlave.exe (or .py) not found next to ignoAPI")
        return False

    # Stop before copying: the old process owns the exclusive-access port, and
    # on Windows a running .exe cannot be overwritten.
    modbusslave_stop(name)

    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] modbus slave: could not duplicate program for '{name}': {err}")
        _create_or_write(ms_status_var(name),
                         f"ERROR: could not create {os.path.basename(target)}: {err}")
        return False

    cfg = modbusslave_config(name)
    if _ms_ensure_vars(name, cfg) is None:
        return False            # the map is broken; the status says why
    _write_ms_config(name, cfg)

    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        msg = _frozen_child_hint(name, "autoModbusSlave.exe")
        print(f"[ignoAPI] modbus slave '{name}': {msg}")
        _create_or_write(ms_status_var(name), msg)
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _ms_lock:
            _ms_procs[name] = proc
            _ms_disabled.discard(name)
        print(f"[ignoAPI] modbus slave '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] modbus slave launch failed for '{name}': {e}")
        _create_or_write(ms_status_var(name), f"ERROR: launch failed: {e}")
        return False


def modbusslave_create(name, cfg):
    """Register + configure + launch a slave for variable <name>.
    Returns (ok, error_message)."""
    if not str(cfg.get("port", "")).strip():
        return False, "Pick a COM port"
    if not str(cfg.get("register_map", "")).strip():
        return False, "Choose a register map CSV"
    if is_autoclient(name):
        return False, f"'{name}' is already an autoclient"
    if is_comclient(name):
        return False, f"'{name}' is already a COM client"
    if is_modbusmaster(name):
        return False, f"'{name}' is already a MODBUS master"
    exe_src = os.path.join(SCRIPT_DIR, "autoModbusSlave.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoModbusSlave.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        msg = "autoModbusSlave.exe (or .py) not found next to ignoAPI — cannot create a slave."
        print(f"[ignoAPI] modbus slave create '{name}' refused: {msg}")
        return False, msg

    # Parse the map BEFORE registering anything. A bad CSV should be a message
    # in the modal you can act on, not a registered slave that dies quietly.
    try:
        entries = ms_read_map(cfg.get("register_map"))
    except Exception as e:
        return False, f"register map: {e}"

    with _ms_lock:
        _modbusslaves[name] = {k: cfg.get(k) for k in MS_FIELDS}
    _save_modbusslaves()
    if name not in _variable_store:
        _create_or_write(name, "")
    _ms_ensure_vars(name, cfg)
    n_reg = sum(1 for k, _, _ in entries if k == "reg")
    print(f"[ignoAPI] MODBUS slave '{name}': {n_reg} registers, "
          f"{len(entries) - n_reg} coils from "
          f"{os.path.basename(cfg.get('register_map'))}")
    modbusslave_launch(name)
    return True, ""


def modbusslave_edit(name, cfg):
    """Rewrite the config and relaunch. A CHANGED register map leaves the old
    variables behind on purpose -- they may hold values worth keeping, and
    silently deleting rows on an edit is not something to do by surprise."""
    with _ms_lock:
        _modbusslaves[name] = {k: cfg.get(k) for k in MS_FIELDS}
    _save_modbusslaves()
    modbusslave_launch(name)


def modbusslave_reconnect(name):
    if is_modbusslave(name):
        modbusslave_launch(name)


def modbusslave_disconnect(name):
    modbusslave_stop(name)
    with _ms_lock:
        _ms_disabled.add(name)
    try:
        _create_or_write(ms_status_var(name), "DISCONNECTED (by user)")
    except Exception:
        pass
    print(f"[ignoAPI] modbus slave '{name}' disconnected by user")


def modbusslave_delete(name):
    """Stop the process, unregister, and delete every register variable."""
    with _ms_lock:
        companions = list(_ms_varcache.get(name, []))
    if not companions:
        companions = ms_var_names(name)
    if ms_status_var(name) not in companions:
        companions.append(ms_status_var(name))
    modbusslave_stop(name)
    with _ms_lock:
        _modbusslaves.pop(name, None)
        _ms_disabled.discard(name)
        _ms_varcache.pop(name, None)
    _save_modbusslaves()
    for cv in companions:
        try:
            _delete(cv)
        except Exception:
            pass
    print(f"[ignoAPI] removed {len(companions)} register variable(s) for '{name}'")
    _, target, json_path, _ = _ms_paths(name)
    for path in (json_path, target):
        if os.path.exists(path):
            _remove_with_retry(path)


def _stop_all_modbusslaves():
    with _ms_lock:
        names = list(_ms_procs.keys())
    for name in names:
        modbusslave_stop(name)


atexit.register(_stop_all_modbusslaves)


def modbusslave_startup_launch_all():
    with _ms_lock:
        items = list(_modbusslaves.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            modbusslave_launch(name)
    # Slaves that are NOT auto-started still need their variables visible, or
    # the rows vanish from the table until someone hits Reconnect.
    for name, cfg in items:
        if not cfg.get("runatstartup"):
            _ms_ensure_vars(name, cfg)


MS_WATCHDOG_INTERVAL_SEC = 5.0


def _ms_watchdog_loop():
    """Restart any slave process that has exited. Port failures are the
    child's own business -- it retries and reports -- so this only covers the
    process itself dying."""
    while True:
        time.sleep(MS_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _ms_lock:
            names = [n for n in _modbusslaves if n not in _ms_disabled]
            procs = {n: _ms_procs.get(n) for n in names}
        for name in names:
            proc = procs.get(name)
            if proc is None or proc.poll() is not None:
                print(f"[ignoAPI] modbus slave watchdog: '{name}' is not running -- restarting")
                modbusslave_launch(name)


_ms_watchdog_thread = threading.Thread(target=_ms_watchdog_loop, daemon=True)
_ms_watchdog_thread.start()





# ──────────────────────────────────────────────────────────────
# CLIPBOARD  (copy/paste for every editable value field)
# ──────────────────────────────────────────────────────────────
# ──────────────────────────────────────────────────────────────
# SYNC IGNOAPI MANAGER
#   Links ONE variable on this ignoAPI to one on ANOTHER computer's ignoAPI,
#   in both directions. Syncing `r1var` creates four boxes, two per machine:
#
#       this computer            the other computer
#       r1var_tx   ──────────>   r1var_rx
#       r1var_rx   <──────────   r1var_tx
#
#   Write into _tx on either side and it lands in the other side's _rx. The
#   _tx box is cleared once delivered, so sending the same value twice
#   actually sends it twice -- the same convention as a COM client's _tx.
#
#   MODE decides how the receiving box behaves:
#       0x01 LEVEL  the value stays in _rx until a new one replaces it
#       0x02 PULSE  the value appears, then clears again after pulse_ms
#   Level is for a reading you watch; pulse is for an event. A repeated
#   trigger is invisible in level mode (the box already holds that value),
#   which is exactly the case pulse exists for.
#
#   Only ONE machine needs to run the program: it creates the peer's boxes
#   itself over the same TCP API. Like every other helper it runs as a
#   SEPARATE PROCESS (<name>_autosyncignoapi.exe), so a peer that goes away
#   blocks its own retry loop and not ignoAPI's GUI thread.
# ──────────────────────────────────────────────────────────────
SYNCPEERS_FILE = "syncpeers.json"

SY_FIELDS = ["server_ip", "mac", "port", "remote_var", "mode", "topology",
             "pulse_ms", "poll_interval_sec", "connect_timeout_sec",
             "read_timeout_sec", "log_file", "runatstartup"]

SY_MODE_CHOICES = ["0x01", "0x02"]

# STAR   — the machines are wired to THIS one and to nothing else. Each peer
#          can read and write our boxes; two peers cannot reach each other.
# DELTA  — every machine talks to every other. The peers still have only one
#          connection each (to here), so this machine RELAYS: what one peer
#          sends is written into every other peer as well, under the sender's
#          own name. Nothing has to be installed or configured on the peers
#          for this -- the boxes appear on them the same way the star ones do.
#          The trade is that the relay is this machine: with it switched off,
#          peer-to-peer traffic stops too.
SY_TOPOLOGY_CHOICES = ["star", "delta"]

# The sync's OWN row is a request/response command box, the same
# arrangement the MODBUS master's command rows use. Printed once on
# creation, because a row that looks empty is exactly when you want to
# know what it accepts.
SYNC_COMMAND_HELP = """\
readData(name)              read `name` from the peer; the value comes back
                            in this same box
writeData(name,"data")      write "data" into `name` on the peer, creating
                            it if it is not there yet
writeData(name,42)          unquoted numbers, true/false/null cross as
                            numbers and booleans, not as text

The answer replaces the command: the value, OK, or ERROR: <reason>."""

SY_RX_SUFFIX = "rx"
SY_TX_SUFFIX = "tx"
SY_STATUS_SUFFIX = "status"


def sy_default_fields():
    """Blank create-modal field values (strings, as the UI edits them).

    remote_var is left EMPTY on purpose: blank means "the same name over
    there", which is what a sync usually is, and prefilling it would make a
    deliberate choice look like one that had already been made.
    """
    return {"server_ip": "", "mac": "", "port": "8899", "remote_var": "",
            "mode": "0x01", "topology": "star", "pulse_ms": "300",
            "poll_interval_sec": "0.1",
            "connect_timeout_sec": "5", "read_timeout_sec": "5",
            "log_file": "sync.log", "runatstartup": "false"}


def sy_fields_from_config(cfg):
    f = sy_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def sy_norm_host(raw):
    """Clean up a typed peer address. Returns (host, note).

    Four decimal groups separated by anything but a dot is an IP typed with
    the wrong key -- 10:28:14:210, 10,28,14,210, 10 28 14 210. It is repaired
    rather than rejected because there is exactly one thing it could have
    meant, and a rejection here would just be a puzzle.

    Deliberately narrow: EXACTLY four groups of 1-3 digits, each 0-255. That
    cannot collide with a hostname or an IPv6 literal, so nothing legitimate
    is rewritten.
    """
    h = str(raw or "").strip()
    if not h:
        return "", ""
    parts = re.split(r"[\s:;,/|]+", h)
    if (len(parts) == 4 and all(p.isdigit() and len(p) <= 3 and int(p) <= 255
                                for p in parts)):
        fixed = ".".join(parts)
        if fixed != h:
            return fixed, f"read {h!r} as {fixed}"
        return fixed, ""
    return h, ""


def sy_norm_hosts(raw):
    """Clean a whole peer list. Returns ([host, ...], [note, ...]).

    Split on commas FIRST, then repair each address on its own, so a list can
    contain a slip without the repair rule (four decimal groups) being
    confused by the other entries.
    """
    hosts, notes = [], []
    for part in str(raw or "").split(","):
        if not part.strip():
            continue
        h, note = sy_norm_host(part)
        if not h:
            continue
        if h in hosts:
            # A duplicate peer would be written to twice per send.
            notes.append(f"dropped repeated peer {h}")
            continue
        hosts.append(h)
        if note:
            notes.append(note)
    return hosts, notes


def sy_host_is_ip(host):
    """True for a bare IPv4 literal, false for a name like ignoapi_x.local."""
    parts = str(host or "").strip().rstrip(".").split(".")
    return (len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255
                                    for p in parts))


def sy_host_is_usable(host):
    """Could this string ever be connected to? Syntax only -- whether the
    machine is switched on is the child's business, not the modal's."""
    # A trailing dot is the fully-qualified form of a name and is legal;
    # dropping it here stops "ignoapi_x.local." reading as an empty label.
    h = str(host or "").strip().rstrip(".")
    if not h:
        return False
    parts = h.split(".")
    if any(p == "" for p in parts):
        return False
    if all(p.isdigit() for p in parts):
        # All-numeric can only be an IPv4 -- a hostname label may not be all
        # digits. So `10.28.14` is a TRUNCATED address, not a machine name,
        # and letting the hostname rule below accept it would send it off to
        # DNS to fail there instead of here.
        return len(parts) == 4 and all(0 <= int(p) <= 255 for p in parts)
    # A hostname: letters, digits, dots, hyphens and UNDERSCORES, not
    # starting or ending in punctuation. The underscore matters here -- our
    # own mDNS names are `ignoapi_<name>.local`, and without it ignoAPI would
    # reject the very names it publishes.
    return bool(re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9_\-.]*[A-Za-z0-9])?",
                             h.rstrip(".")))


def sy_cast_fields(fields):
    def num(v, cast, default):
        try:
            return cast(str(v).strip())
        except (ValueError, TypeError):
            return default
    mode = (fields.get("mode") or "0x01").strip().lower()
    if mode not in ("0x01", "0x02"):
        mode = "0x01"
    topo = (fields.get("topology") or "star").strip().lower()
    if topo not in SY_TOPOLOGY_CHOICES:
        topo = "star"
    hosts, _notes = sy_norm_hosts(fields.get("server_ip"))
    # Blank slots are preserved: ",,aa:bb:.." is how the THIRD peer gets a MAC
    # while the first two keep none, so the list stays positional.
    macs = [norm_mac(m) if m.strip() else ""
            for m in str(fields.get("mac") or "").split(",")]
    while macs and not macs[-1]:
        macs.pop()
    return {
        "server_ip":           ",".join(hosts),
        "mac":                 ",".join(macs),
        "port":                num(fields.get("port"), int, 8899),
        "remote_var":          (fields.get("remote_var") or "").strip(),
        "mode":                mode,
        "topology":            topo,
        "pulse_ms":            num(fields.get("pulse_ms"), int, 300),
        "poll_interval_sec":   num(fields.get("poll_interval_sec"), float, 0.1),
        "connect_timeout_sec": num(fields.get("connect_timeout_sec"), float, 5),
        "read_timeout_sec":    num(fields.get("read_timeout_sec"), float, 5),
        "log_file":            (fields.get("log_file") or "sync.log").strip() or "sync.log",
        "runatstartup":        str(fields.get("runatstartup", "false")).strip().lower()
                               in ("true", "1", "yes", "on"),
    }


def sy_rx_var(name):
    """'r1var' -> 'r1var_rx' — what the peer sends us."""
    return f"{name}_{SY_RX_SUFFIX}"


def sy_tx_var(name):
    """'r1var' -> 'r1var_tx' — what we send the peer. Cleared once delivered."""
    return f"{name}_{SY_TX_SUFFIX}"


def sy_status_var(name):
    return f"{name}_{SY_STATUS_SUFFIX}"


def sy_peers_var(name):
    """The row the child publishes 'host=UP,host=DOWN' into — what the
    topology diagram is drawn from."""
    return f"{name}_peers"


def sy_host_tag(host):
    """A machine's name as it appears inside a box name.

    The address is kept as it was TYPED -- dots and all -- because that is what
    makes the row readable: `ADITYA_ignoapi_komal.local_rx` says which machine
    at a glance, where `ADITYA_rx_ignoapi_komal_local` has to be decoded. Only
    characters that could confuse the command syntax are replaced.

    So an mDNS name stays an mDNS name and an address stays an address: the IP
    shows up in the row only when an IP is what the sync was given.

    Must match autoSyncIgnoAPI.host_tag, or ignoAPI would not recognise the
    boxes the child creates.
    """
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(host)).strip("_")


# The marker autoSyncIgnoAPI stamps on the rows it creates on a PEER. This
# is a contract between the two programs: it must match REMOTE_MARK there.
REMOTE_SYNC_MARK = "SYNCED FROM "

_remote_sync = {"rows": set(), "groups": {}}
_remote_sync_lock = threading.Lock()


def scan_remote_syncs(snapshot):
    """Find sync rows that a sync on ANOTHER machine created here.

    This machine has no syncpeer registered for them -- they arrived over the
    network -- so nothing local knows what they are, and they rendered as
    ordinary variables with no hint of where they came from. They are found by
    the marker the other end writes into <var>_status.

    Returns (rows, groups): every row belonging to a remote sync, and
    {status_row: [its rx/tx rows]} so they can be shown together.
    """
    rows, groups = set(), {}
    for name, val in snapshot.items():
        if not name.endswith("_" + SY_STATUS_SUFFIX):
            continue
        if not isinstance(val, str) or not val.startswith(REMOTE_SYNC_MARK):
            continue
        base = name[: -(len(SY_STATUS_SUFFIX) + 1)]
        if is_syncpeer(base):
            continue          # ours: already known, already coloured
        # Any inbound or outbound box of that sync, not only the two plain
        # ones: a DELTA puts a per-machine pair here as well
        # (`<base>_ignoapi_komal.local_rx` and its _tx), and those are just as
        # much part of the sync -- leaving them out would draw half a group as
        # ordinary variables.
        kids = sorted(v for v in snapshot
                      if v.startswith(base + "_")
                      and (v.endswith("_" + SY_RX_SUFFIX)
                           or v.endswith("_" + SY_TX_SUFFIX)))
        if not kids:
            continue          # a marker with no boxes is not a pair
        groups[name] = kids
        rows.add(name)
        rows.update(kids)
    return rows, groups


def refresh_remote_syncs(snapshot):
    """Recompute the cache from a snapshot the caller already has.

    Called once per frame from the draw loop, which is holding a full
    snapshot anyway -- so this costs a dictionary walk and no extra reads.
    """
    rows, groups = scan_remote_syncs(snapshot)
    with _remote_sync_lock:
        _remote_sync["rows"] = rows
        _remote_sync["groups"] = groups
    return rows


def is_remote_sync_row(name):
    with _remote_sync_lock:
        return name in _remote_sync["rows"]


def remote_sync_groups():
    with _remote_sync_lock:
        return {k: list(v) for k, v in _remote_sync["groups"].items()}


def sy_hosts(name, cfg=None):
    """The peer addresses configured for this sync, in order."""
    cfg = cfg if cfg is not None else syncpeer_config(name)
    return [h.strip() for h in str(cfg.get("server_ip") or "").split(",")
            if h.strip()]


def sy_peer_rx_var(name, host):
    """What one named machine has sent us: `<var>_<machine>_rx`.

    The machine goes in the MIDDLE, so the row still ends in the suffix that
    says which way it points -- the same shape as the plain `<var>_rx` beside
    it, and the reason a column of these reads as pairs.
    """
    return f"{name}_{sy_host_tag(host)}_{SY_RX_SUFFIX}"


def sy_peer_tx_var(name, host):
    """The box that sends to ONE named machine.

    Wanted wherever there is more than one machine to talk to, which is
    every delta and any star with two or more peers. The shared `<var>_tx`
    goes to everybody at once, so it is the wrong box for "tell komal, and
    only komal". A single-peer star does not need one: there, "everybody"
    and "that machine" are the same place.
    """
    return f"{name}_{sy_host_tag(host)}_{SY_TX_SUFFIX}"


def sy_topology(name, cfg=None):
    """'star' or 'delta'. Anything unrecognised (or an old config written
    before this existed) reads as star, which is what it was."""
    cfg = cfg if cfg is not None else syncpeer_config(name)
    t = str(cfg.get("topology") or "star").strip().lower()
    return t if t in SY_TOPOLOGY_CHOICES else "star"


def sy_is_delta(name, cfg=None):
    return sy_topology(name, cfg) == "delta"


def sy_macs(name, cfg=None):
    """The MACs configured for this sync, positionally paired with the IPs.

    One MAC per peer, in the same order: 'aa:..,bb:..' goes with
    '10.0.0.5,10.0.0.6'. Fewer MACs than peers is fine -- the rest simply have
    none and are never re-resolved. A blank slot (',,bb:..') is how you give
    the third peer a MAC and leave the first two alone.
    """
    cfg = cfg if cfg is not None else syncpeer_config(name)
    return [m.strip() for m in str(cfg.get("mac") or "").split(",")]


def sy_resolve_macs(name, sweep=True):
    """Re-point any peer whose MAC now answers at a different address.

    Returns the list of (old, new) it changed. The caller relaunches; this
    only decides. Nothing is written when nothing moved, so a healthy sync is
    never restarted for no reason -- a restart drops the link it was checking.
    """
    cfg = syncpeer_config(name)
    hosts = sy_hosts(name, cfg)
    macs = sy_macs(name, cfg)
    if not any(macs):
        return []
    # ONE sweep for the whole list, not one per MAC. Three unknown MACs would
    # otherwise mean three full subnet sweeps back to back, and the peers are
    # all on the same network anyway.
    table = arp_table()
    if sweep and any(m and norm_mac(m) not in table for m in macs):
        arp_sweep()
        table = arp_table()
    with _mac_cache_lock:
        _mac_cache.update(table)

    moved = []
    for i, mac in enumerate(macs):
        if not mac:
            continue
        found = table.get(norm_mac(mac))
        if not found:
            with _mac_cache_lock:
                found = _mac_cache.get(norm_mac(mac))   # last known good
        if not found:
            continue
        if i < len(hosts):
            if not sy_host_is_ip(hosts[i]):
                # A peer given by NAME already survives an address change --
                # that is what the name is for. Overwriting it with today's IP
                # would throw that away, and rename every box named after it
                # into a number nobody typed.
                continue
            if found != hosts[i]:
                moved.append((hosts[i], found))
                hosts[i] = found
        else:
            # A MAC with no address yet -- the peer had not been seen when the
            # sync was made. Filling it in here is the whole point.
            moved.append(("(unset)", found))
            hosts.append(found)
    if not moved:
        return []
    with _sy_lock:
        if name in _syncpeers:
            _syncpeers[name]["server_ip"] = ",".join(hosts)
    _save_syncpeers()
    return moved


def sy_peers_down(name):
    """True if any configured peer is not answering (or never has).

    Read from the row the child publishes. A sync whose child is not running
    at all counts as down too -- that is the case where the address being
    wrong is most likely.
    """
    states = sy_peer_states(name)
    if not states:
        return False
    return any(st is not True for _h, st in states)


def sy_peer_states(name):
    """[(host, up)] for a sync, from the row its child publishes.

    The CONFIG is the source of truth for WHICH peers exist and the published
    row only says which are answering -- so a peer that has never come up is
    still drawn, greyed out, instead of being invisible exactly when you are
    looking for it.
    """
    live = {}
    try:
        raw = _read(sy_peers_var(name))
    except Exception:
        raw = None
    for part in str(raw or "").split(","):
        if "=" in part:
            host, _, state = part.partition("=")
            live[host.strip()] = state.strip().upper() == "UP"
    return [(h, live.get(h)) for h in sy_hosts(name)]


def sy_sub_vars(name, cfg=None):
    """Every row this sync owns.

    With more than one peer each machine gets its OWN pair of boxes: an
    inbound one because a single _rx holds one value and several peers can
    speak in the same poll, and an outbound one because the shared _tx goes
    to EVERYBODY -- without a per-machine box there is no way to say
    something to one of them only. That is true of a star hub as much as of
    a delta; a star was creating the inbound half and not the outbound one.

    A DELTA keeps both even for a single peer: there the name of the machine
    is part of the address, so the boxes are named the same way whether
    there is one peer or five.
    """
    out = [sy_rx_var(name), sy_tx_var(name), sy_status_var(name),
           sy_peers_var(name)]
    cfg = cfg if cfg is not None else syncpeer_config(name)
    hosts = sy_hosts(name, cfg)
    if sy_is_delta(name, cfg) or len(hosts) > 1:
        for h in hosts:
            out += [sy_peer_rx_var(name, h), sy_peer_tx_var(name, h)]
    return out


def _load_syncpeers():
    if os.path.exists(SYNCPEERS_FILE):
        try:
            with open(SYNCPEERS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: syncpeers.json corrupt — starting fresh.")
    return {}


_syncpeers  = _load_syncpeers()     # name -> config dict
_sy_procs   = {}                    # name -> subprocess.Popen
_sy_disabled = set()                # names the user explicitly Disconnected
_sy_lock    = threading.Lock()


def _save_syncpeers():
    tmp = SYNCPEERS_FILE + ".tmp"
    try:
        with _sy_lock:
            snapshot = dict(_syncpeers)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, SYNCPEERS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save syncpeers.json: {e}")


def is_syncpeer(name):
    with _sy_lock:
        return name in _syncpeers


def syncpeer_config(name):
    with _sy_lock:
        return dict(_syncpeers.get(name, {}))


def is_sync_sub_var(name):
    """True for any of the three auto-created companions of a sync."""
    with _sy_lock:
        owners = list(_syncpeers.keys())
    for owner in owners:
        if name in sy_sub_vars(owner):
            return True
    return False


def sync_sub_owner(name):
    with _sy_lock:
        owners = list(_syncpeers.keys())
    for owner in owners:
        if name in sy_sub_vars(owner):
            return owner
    return None


def is_sync_row(name):
    """True for a sync variable or any of its companions — including one this
    machine did not create, but another machine's sync did."""
    return is_syncpeer(name) or is_sync_sub_var(name) or is_remote_sync_row(name)


def _sy_paths(name):
    """(source, target, json_path, is_exe) for sync <name>. Prefers the
    compiled exe and falls back to the .py, so it works in development before
    the exe has ever been built."""
    exe_src = os.path.join(SCRIPT_DIR, "autoSyncIgnoAPI.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoSyncIgnoAPI.py")
    if os.path.exists(exe_src):
        return (exe_src,
                os.path.join(SCRIPT_DIR, f"{name}_autosyncignoapi.exe"),
                os.path.join(SCRIPT_DIR, f"{name}_autosyncignoapi.json"), True)
    return (py_src,
            os.path.join(SCRIPT_DIR, f"{name}_autosyncignoapi.py"),
            os.path.join(SCRIPT_DIR, f"{name}_autosyncignoapi.json"), False)


def _write_sy_config(name, cfg):
    """Write <name>_autosyncignoapi.json, injecting this server as the local
    end so the duplicated program knows which ignoAPI and which pair it owns."""
    _, _, json_path, _ = _sy_paths(name)
    full = {k: cfg.get(k) for k in SY_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def syncpeer_is_live(name):
    """Green dot: the process is running AND its status says the link is up.
    A running process is not enough -- it stays alive retrying a peer that is
    switched off, and that must not read as healthy."""
    with _sy_lock:
        proc = _sy_procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        st = _read(sy_status_var(name))
    except Exception:
        return False
    return bool(st) and str(st).strip().upper().startswith("LIVE")


def syncpeer_stop(name):
    with _sy_lock:
        proc = _sy_procs.pop(name, None)
    _kill_process_tree(proc)


def _sy_ensure_sub_vars(name):
    """Create the companions if missing, leaving existing values alone.

    Called on every launch, so a sync saved before a companion existed gets it
    back with no migration step -- which is also how a star turned into a
    delta picks up its per-machine outbound boxes.

    The peers row is left out: it is published by the child, and creating it
    empty here would show a sync with no peers at all until the first poll.
    """
    for v in [x for x in sy_sub_vars(name)
              if x not in (sy_status_var(name), sy_peers_var(name))]:
        try:
            if _read(v) is None:
                _create_or_write(v, "")
        except Exception:
            try:
                _create_or_write(v, "")
            except Exception:
                pass
    try:
        if _read(sy_status_var(name)) is None:
            _create_or_write(sy_status_var(name), "CREATED — not started yet")
    except Exception:
        pass
    _sy_drop_old_layout(name)


def _sy_drop_old_layout(name):
    """Remove per-machine boxes left over from the OLD naming.

    They used to be `<var>_rx_<machine>` with the address flattened to
    underscores; they are now `<var>_<machine>_rx` with the address as typed.
    Rows in the old shape belong to nothing after the rename -- they are never
    written again and stop being coloured as part of the sync, so they would
    sit in the table looking like ordinary variables that had gone quiet.

    Only rows that are EMPTY are removed. A leftover holding a value is the
    last thing that arrived before the rename, and throwing that away silently
    is not this function's call to make.
    """
    try:
        snap = _read_all()
    except Exception:
        return
    keep = set(sy_sub_vars(name))
    for h in sy_hosts(name):
        old_tag = re.sub(r"[^A-Za-z0-9]+", "_", str(h)).strip("_")
        for old in (f"{name}_{SY_RX_SUFFIX}_{old_tag}",
                    f"{name}_{SY_TX_SUFFIX}_{old_tag}"):
            if old in keep or old not in snap:
                continue
            if snap.get(old) not in ("", None):
                continue
            try:
                _delete(old)
                print(f"[ignoAPI] sync '{name}': removed old-style row {old!r}")
            except Exception:
                pass


def syncpeer_launch(name):
    """Refresh the duplicated program for <name>, then (re)start it.

    Re-resolves the IP from MAC on EVERY launch, exactly like autoclient: the
    other computer is a DHCP client too, and a sync that silently talks to a
    stale address is worse than one that reports the peer as down.
    """
    source, target, _, is_exe = _sy_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] sync: no autoSyncIgnoAPI.exe/.py to duplicate for '{name}'")
        _create_or_write(sy_status_var(name), "ERROR — autoSyncIgnoAPI.exe/.py missing")
        return False

    syncpeer_stop(name)                 # a running .exe is locked on Windows
    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] sync: could not duplicate program for '{name}': {err}")
        _create_or_write(sy_status_var(name), f"ERROR — copy failed: {err}")
        return False

    with _sy_lock:
        cfg = dict(_syncpeers.get(name, {}))
    # Heal addresses typed with the wrong separator, ONCE, rather than leaving
    # the child to re-repair the same config on every start.
    _hosts, _notes = sy_norm_hosts(cfg.get("server_ip"))
    if _notes:
        cfg["server_ip"] = ",".join(_hosts)
        with _sy_lock:
            if name in _syncpeers:
                _syncpeers[name]["server_ip"] = cfg["server_ip"]
        _save_syncpeers()
        for _n in _notes:
            print(f"[ignoAPI] sync '{name}': {_n}")
    # Resolve EVERY peer that has a MAC, positionally. Done on every launch --
    # including the one at boot, where the peer may not have had its lease yet
    # when the address was last written down.
    if any(m.strip() for m in str(cfg.get("mac") or "").split(",")):
        moved = sy_resolve_macs(name)
        for old, new in moved:
            print(f"[ignoAPI] sync '{name}': MAC resolved to {new} (was {old})")
        cfg = syncpeer_config(name) or cfg
        if not moved:
            print(f"[ignoAPI] sync '{name}': MAC(s) already point at "
                  f"{cfg.get('server_ip') or '(none)'}")
    _write_sy_config(name, cfg)
    _sy_ensure_sub_vars(name)

    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        print(f"[ignoAPI] sync '{name}': " + _frozen_child_hint(name, "autoSyncIgnoAPI.exe"))
        _create_or_write(sy_status_var(name), "ERROR — build autoSyncIgnoAPI.exe first")
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _sy_lock:
            _sy_procs[name] = proc
            _sy_disabled.discard(name)   # an explicit (re)launch re-arms the watchdog
        print(f"[ignoAPI] sync '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] sync launch failed for '{name}': {e}")
        _create_or_write(sy_status_var(name), f"ERROR — {e}")
        return False


def syncpeer_create(name, cfg):
    """Register + configure + launch a sync for variable <name>.
    Returns (ok, error_message)."""
    hosts = [h for h in str(cfg.get("server_ip", "")).split(",") if h.strip()]
    mac   = str(cfg.get("mac", "")).strip()
    if not hosts and not mac:
        return False, "Enter the other computer's IP (or a MAC to look it up)"
    for host in hosts:
        if not sy_host_is_usable(host):
            # Caught HERE rather than in the child: down there it can only
            # appear as "getaddrinfo failed", which reads like the peer is
            # switched off. Names the offending entry, since a list of five
            # with one typo is otherwise a hunt.
            return False, (f"'{host}' is not a valid IP or hostname "
                           f"(an IP is four numbers separated by dots, "
                           f"e.g. 10.28.14.210)")
    port = cfg.get("port")
    try:
        if not (0 < int(port) < 65536):
            raise ValueError
    except (TypeError, ValueError):
        return False, f"Port {port!r} is not a number between 1 and 65535"
    # A name can only belong to one family: every one of them creates
    # companions from the same <name>_<suffix> pattern, and two owners of the
    # same row would fight over it every poll.
    if is_autoclient(name):
        return False, f"'{name}' is already an autoclient"
    if is_comclient(name):
        return False, f"'{name}' is already a COM client"
    if is_modbusmaster(name):
        return False, f"'{name}' is already a MODBUS master"
    if is_modbusslave(name):
        return False, f"'{name}' is already a MODBUS slave"
    if is_vdabridge(name):
        return False, f"'{name}' is already a VDA bridge"
    exe_src = os.path.join(SCRIPT_DIR, "autoSyncIgnoAPI.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoSyncIgnoAPI.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        msg = "autoSyncIgnoAPI.exe (or .py) not found next to ignoAPI — cannot create a sync."
        print(f"[ignoAPI] sync create '{name}' refused: {msg}")
        return False, msg

    with _sy_lock:
        _syncpeers[name] = {k: cfg.get(k) for k in SY_FIELDS}
    _save_syncpeers()
    if name not in _variable_store:      # show the row right away
        _create_or_write(name, "")
    _sy_ensure_sub_vars(name)
    peer = (cfg.get("remote_var") or "").strip() or name
    _hosts = [h for h in str(cfg.get("server_ip") or "").split(",") if h.strip()]
    if len(_hosts) > 1:
        print(f"[ignoAPI] SYNC {name!r}: {len(_hosts)} peers — {name}_tx goes to "
              f"ALL of them, and each gets its own inbound box "
              f"{sy_peer_rx_var(name, _hosts[0])}")
    if sy_is_delta(name, cfg):
        print(f"[ignoAPI] SYNC {name!r}: DELTA — every machine talks to every "
              f"other one. Each peer also gets an inbound and an outbound box "
              f"per other machine, and this computer carries what they send "
              f"each other. Send to one machine with "
              f"{sy_peer_tx_var(name, _hosts[0] if _hosts else '<machine>')}; "
              f"{name}_tx still goes to all of them.")
    print("\n[ignoAPI] SYNC '%s' — command syntax for the '%s' row:\n" % (name, name)
          + "\n".join("    " + ln for ln in SYNC_COMMAND_HELP.splitlines()))
    print(f"\n[ignoAPI] SYNC '{name}' -> {cfg.get('server_ip')}:{cfg.get('port')}\n"
          f"    type into  {sy_tx_var(name)}   -> appears in  {peer}_tx's partner "
          f"({peer}_rx) over there\n"
          f"    watch      {sy_rx_var(name)}   <- whatever they put in {peer}_tx\n"
          f"    mode       {cfg.get('mode')} "
          f"({'PULSE — clears after %sms' % cfg.get('pulse_ms') if str(cfg.get('mode')) == '0x02' else 'LEVEL — value stays'})\n")
    syncpeer_launch(name)
    return True, ""


def syncpeer_edit(name, cfg):
    """Rewrite the config and relaunch so it takes effect at once.

    Boxes the NEW settings no longer have are removed here, in ONE place.
    Which per-machine rows a sync owns depends on the peer list AND on the
    topology -- dropping a peer, or turning a delta back into a star, leaves
    rows behind that nothing owns any more, and an unowned row does not merely
    look untidy: it stops being coloured as a sync and sits in the table as an
    ordinary variable that nobody ever writes again.
    """
    was = set(sy_sub_vars(name))
    with _sy_lock:
        _syncpeers[name] = {k: cfg.get(k) for k in SY_FIELDS}
    _save_syncpeers()
    for v in was - set(sy_sub_vars(name)):
        try:
            _delete(v)
            print(f"[ignoAPI] sync '{name}': removed stale companion '{v}'")
        except Exception:
            pass
    _sy_ensure_sub_vars(name)
    syncpeer_launch(name)


def syncpeer_reconnect(name):
    if is_syncpeer(name):
        syncpeer_launch(name)


def syncpeer_disconnect(name):
    """Stop the process and leave it stopped (the watchdog skips disabled names)."""
    syncpeer_stop(name)
    with _sy_lock:
        _sy_disabled.add(name)
    try:
        _create_or_write(sy_status_var(name), "DISCONNECTED (by user)")
    except Exception:
        pass
    print(f"[ignoAPI] sync '{name}' disconnected by user")


def delete_variable(name):
    """Remove a variable AND everything it owns.

    Every module that hangs things off a variable gets its say here: the
    child process it started, the companion rows beside it, the files it
    duplicated, and -- for a sync -- the rows it created on the other
    machines. There is one of these rather than one per delete button,
    because the second copy is always the one that gets forgotten when a
    module is added.
    """
    link_forget(name)
    if is_autoclient(name):
        autoclient_delete(name)
    if is_comclient(name):
        # also removes <name>_com<port>_status and <name>_tx
        comclient_delete(name)
    if is_modbusmaster(name):
        # also removes all five companions
        modbusmaster_delete(name)
    if is_modbusslave(name):
        # also removes every register variable
        modbusslave_delete(name)
    if is_ftpserver(name):
        # the SHARED FOLDER is left alone
        ftpserver_delete(name)
    if is_vdabridge(name):
        vdabridge_delete(name)
    if is_syncpeer(name):
        # also removes _rx / _tx / _status here, AND the rows this sync
        # created on each linked machine
        syncpeer_delete(name)
    try:
        _delete(name)
    except Exception:
        pass

# ──────────────────────────────────────────────────────────────
# MODULES OVER THE WIRE
# ──────────────────────────────────────────────────────────────
# Everything the right-click menu can create, a client can create too.
# ONE table: the kind a client names, the function that builds it, the
# caster that turns typed strings into a config, and the blank field set
# a caller's values are merged over. A module added to the UI is added
# here in one line, and the alternative -- a branch per kind in the
# request handler -- is how one of them ends up missing.
def _module_table():
    return {
        "autoclient":   (autoclient_create,   autoclient_delete,
                         ac_cast_fields,  ac_default_fields,  is_autoclient),
        "com":          (comclient_create,    comclient_delete,
                         cc_cast_fields,  cc_default_fields,  is_comclient),
        "modbusmaster": (modbusmaster_create, modbusmaster_delete,
                         mm_cast_fields,  mm_default_fields,  is_modbusmaster),
        "modbusslave":  (modbusslave_create,  modbusslave_delete,
                         ms_cast_fields,  ms_default_fields,  is_modbusslave),
        "sync":         (syncpeer_create,     syncpeer_delete,
                         sy_cast_fields,  sy_default_fields,  is_syncpeer),
        "ftp":          (ftpserver_create,    ftpserver_delete,
                         ft_cast_fields,  ft_default_fields,  is_ftpserver),
        "vda":          (vdabridge_create,    vdabridge_delete,
                         vd_cast_fields,  vd_default_fields,  is_vdabridge),
    }


def module_kinds():
    """The kinds a client may ask for."""
    return sorted(_module_table())


def module_create(kind, name, fields):
    """Create one module. Returns (ok, message).

    `fields` are merged OVER the blank set, so a caller sends only what it
    cares about and every other setting keeps the value the create form
    would have shown. They arrive as strings, the way the form edits them,
    and go through the same caster the form uses."""
    table = _module_table()
    if kind not in table:
        return False, "unknown module kind %r — try one of: %s" % (
            kind, ", ".join(module_kinds()))
    if not str(name or '').strip():
        return False, "a module needs a variable name"
    create, _delete_fn, cast, blank, _is = table[kind]
    merged = blank()
    for k, v in (fields or {}).items():
        if k in merged:
            merged[k] = "" if v is None else str(v)
    try:
        ok, err = create(name, cast(merged))
    except Exception as e:
        return False, str(e)
    return bool(ok), (err or ("created %s '%s'" % (kind, name)))


def module_delete(kind, name):
    """Remove one module and everything it owns. Returns (ok, message).

    `kind` may be None: the module is then worked out from the name, which
    is what a caller who just wants it GONE actually knows."""
    table = _module_table()
    if kind and kind not in table:
        return False, "unknown module kind %r" % kind
    if not str(name or '').strip():
        return False, "which variable?"
    if kind is None:
        for k, (_c, _d, _cast, _b, is_it) in table.items():
            if is_it(name):
                kind = k
                break
    if kind is None:
        return False, "'%s' is not a module" % name
    try:
        delete_variable(name)
    except Exception as e:
        return False, str(e)
    return True, "deleted %s '%s'" % (kind, name)


def module_list():
    """{kind: [names]} for every module configured here."""
    out = {}
    try:
        names = list(_read_all())
    except Exception:
        names = []
    for kind, (_c, _d, _cast, _b, is_it) in _module_table().items():
        out[kind] = sorted(n for n in names if is_it(n))
    return out


def handle_link_request(req):
    """link / unlink / list_links, as the line protocol sees them.

    A link pushes every change of one variable into another, and lives in
    varlinks.json rather than in a variable -- so unlike a combine, it
    cannot be set up just by writing a value, and needs saying out loud.
    """
    action = req.get("action")
    if action == "list_links":
        return {"status": "success", "value": link_map()}
    src = str(req.get("name") or req.get("src") or "").strip()
    if not src:
        return {"status": "error", "message": "which variable?"}
    if action == "unlink":
        gone = link_remove(src)
        return {"status": "success",
                "message": ("unlinked " + ", ".join("%s -> %s" % p for p in gone)
                            if gone else "'%s' was not linked" % src)}
    dst = str(req.get("value") or req.get("dst") or "").strip()
    ok, msg = link_add(src, dst)
    return {"status": "success" if ok else "error", "message": msg}

def handle_module_request(req):
    """The three module actions, as the line protocol sees them."""
    action = req.get("action")
    if action == "list_modules":
        return {"status": "success", "value": module_list(),
                "kinds": module_kinds()}
    kind = req.get("kind")
    name = req.get("name")
    if action == "delete_module":
        ok, msg = module_delete(kind, name)
    else:
        ok, msg = module_create(kind, name, req.get("fields") or {})
    return {"status": "success" if ok else "error", "message": msg}

def _remote_delete(host, port, names, timeout=3.0):
    """Delete `names` on another ignoAPI. Returns (done, failed).

    One short-lived connection carrying every delete, because this runs at
    the moment a row is removed and a peer that has been switched off must
    not hold up the UI: the timeout is the whole cost, once, not once per
    name.
    """
    done, failed = [], []
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sk:
            sk.settimeout(timeout)
            f = sk.makefile('rwb')
            for nm in names:
                f.write((json.dumps({'action': 'delete', 'name': nm})
                         + "\n").encode("utf-8"))
                f.flush()
                line = f.readline()
                try:
                    ok = json.loads(line.decode('utf-8')).get('status') == 'success'
                except Exception:
                    ok = False
                (done if ok else failed).append(nm)
    except OSError:
        # The machine is off, or unreachable. Its rows are still over there;
        # saying so is better than reporting a delete that never happened.
        return done, [n for n in names if n not in done]
    return done, failed

def _sy_delete_on_peers(name):
    """Remove the rows this sync created on each linked machine."""
    cfg = syncpeer_config(name)
    if not cfg:
        return
    remote = str(cfg.get('remote_var') or name).strip() or name
    port = cfg.get('port') or PORT
    hosts = sy_hosts(name, cfg)
    if not hosts:
        return
    # The peer's own layout, named from ITS side: the shared pair, and -- in
    # a delta -- one pair per machine it was told to address.
    tags = [sy_host_tag(h) for h in hosts]
    # This machine's name in the delta boxes on the peers: the mDNS name
    # when ADDRESS is set, which is what the child writes over there.
    me = sy_host_tag(ignoapi_hostname() or ignoapi_address())
    for h in hosts:
        # The child creates _tx and _rx over there, and stamps a _status
        # row saying who owns them (Peer.mark). All three are this sync's,
        # so all three go -- the status row was being left behind, which is
        # the one that makes it look like the delete did nothing.
        want = [f'{remote}_{SY_TX_SUFFIX}', f'{remote}_{SY_RX_SUFFIX}',
                f'{remote}_{SY_STATUS_SUFFIX}']
        if sy_is_delta(name, cfg):
            others = [me] + [t for t in tags if t and t != sy_host_tag(h)]
            for t in others:
                want += [f'{remote}_{t}_{SY_RX_SUFFIX}',
                         f'{remote}_{t}_{SY_TX_SUFFIX}']
        done, failed = _remote_delete(h, port, want)
        if done:
            print(f"[ignoAPI] sync '{name}': removed {len(done)} row(s) on {h}")
        if failed:
            print(f"[ignoAPI] sync '{name}': {h} did not answer — "
                  f"{len(failed)} row(s) still there")

def syncpeer_delete(name):
    """Stop the process, unregister, and remove the three companions plus the
    duplicated program. (The variable itself is removed by the caller.)

    The rows this sync created ON THE PEERS go too. They exist because this
    machine put them there and are written by nothing once the sync stops,
    so leaving them behind meant deleting the same variable by hand on every
    linked machine -- and a row nobody writes looks exactly like a row that
    has gone quiet. Only the boxes this sync owns are touched; anything else
    on the peer is left alone.

    A peer that is switched off is REPORTED, not retried: its rows are still
    there, and pretending otherwise would be worse than saying so.
    """
    companions = sy_sub_vars(name)       # resolve BEFORE unregistering
    # STOP THE CHILD FIRST. It calls ensure_vars on every poll -- ten times
    # a second -- so deleting the peer's rows while it is still running
    # just has it put them straight back, and the delete looks like it did
    # nothing at all. The config is still registered at this point, which
    # is what _sy_delete_on_peers needs to know where to send.
    syncpeer_stop(name)
    _sy_delete_on_peers(name)
    with _sy_lock:
        _syncpeers.pop(name, None)
        _sy_disabled.discard(name)
    _save_syncpeers()
    for cv in companions:
        try:
            _delete(cv)
            print(f"[ignoAPI] removed companion variable '{cv}'")
        except Exception as e:
            print(f"[ignoAPI] could not remove '{cv}': {e}")
    _, target, json_path, _ = _sy_paths(name)
    for path in (json_path, target):
        if os.path.exists(path):
            _remove_with_retry(path)


def _ac_repoint(name, ip):
    with _ac_lock:
        if name in _autoclients:
            _autoclients[name]["server_ip"] = ip
    _save_autoclients()
    autoclient_launch(name)


def _sy_repoint(name, ip):
    with _sy_lock:
        if name in _syncpeers:
            _syncpeers[name]["server_ip"] = ip
    _save_syncpeers()
    syncpeer_launch(name)


def mac_configured_children():
    """Everything that identifies its target by MAC, and how to move it.

    [(kind, name, mac, current_ip, apply_ip)] — the ARP keeper walks this and
    re-points anything whose machine has taken a new lease.
    """
    out = []
    with _ac_lock:
        items = [(n, dict(c)) for n, c in _autoclients.items()]
    for name, cfg in items:
        mac = (cfg.get("mac") or "").strip()
        if mac:
            out.append(("autoclient", name, mac, cfg.get("server_ip") or "",
                        lambda ip, _n=name: _ac_repoint(_n, ip)))
    with _sy_lock:
        items = [(n, dict(c)) for n, c in _syncpeers.items()]
    for name, cfg in items:
        mac = (cfg.get("mac") or "").strip()
        hosts = [h.strip() for h in str(cfg.get("server_ip") or "").split(",")
                 if h.strip()]
        # MACs are positional, one per peer, so a LIST is handled too -- the
        # recovery loop resolves each slot on its own rather than collapsing
        # the list down to a single address.
        if mac:
            out.append(("sync", name, mac, hosts[0] if hosts else "",
                        lambda ip, _n=name: _sy_repoint(_n, ip)))
    return out


_arp_keeper_thread = threading.Thread(target=_arp_keeper_loop, daemon=True)
_arp_keeper_thread.start()


def _stop_all_syncpeers():
    with _sy_lock:
        names = list(_sy_procs.keys())
    for name in names:
        syncpeer_stop(name)


atexit.register(_stop_all_syncpeers)


def syncpeer_startup_launch_all():
    with _sy_lock:
        items = list(_syncpeers.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            syncpeer_launch(name)


SY_WATCHDOG_INTERVAL_SEC = 5.0


def _sy_watchdog_loop():
    """Restart any sync process that has exited. A peer being unreachable is
    the child's own business (it retries and reports through its status row);
    this only covers the process itself dying."""
    while True:
        time.sleep(SY_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _sy_lock:
            names = [n for n in _syncpeers if n not in _sy_disabled]
            procs = {n: _sy_procs.get(n) for n in names}
        for name in names:
            proc = procs.get(name)
            if proc is None or proc.poll() is not None:
                print(f"[ignoAPI] sync watchdog: '{name}' is not running -- restarting")
                syncpeer_launch(name)


_sy_watchdog_thread = threading.Thread(target=_sy_watchdog_loop, daemon=True)
_sy_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# VARIABLE LINKS
#   Link r_id -> fleetmanagercoputer_tx and whatever r_id produces is pushed
#   into that box. One source may feed several targets; a target may be fed
#   by only one source, because two writers on one row is just a race.
#
#   PUSHED ON CHANGE, NOT CONTINUOUSLY. That distinction is the whole design:
#   a _tx box is CLEARED by its reader once the value has gone out, so a
#   continuous push would refill it and transmit the same value forever. On
#   change means "r_id became 4" sends once, and says nothing until it
#   becomes something else.
#
#   Linked rows are drawn ADJACENT with a connector between them, so a value
#   arriving somewhere unexpected has a visible cause instead of being a
#   mystery two hundred rows apart.
# ──────────────────────────────────────────────────────────────
VARLINKS_FILE = "varlinks.json"


def _load_varlinks():
    if os.path.exists(VARLINKS_FILE):
        try:
            with open(VARLINKS_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # {src: [dst, ...]} — normalise stray scalars
                return {k: (list(v) if isinstance(v, (list, tuple)) else [v])
                        for k, v in data.items()}
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: varlinks.json corrupt — starting fresh.")
    return {}


_varlinks   = _load_varlinks()    # src -> [dst, ...]
_link_last  = {}                  # src -> last value pushed (change detection)
_link_lock  = threading.Lock()


def _save_varlinks():
    tmp = VARLINKS_FILE + ".tmp"
    try:
        with _link_lock:
            snapshot = {k: list(v) for k, v in _varlinks.items()}
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, VARLINKS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save varlinks.json: {e}")


def link_map():
    """{src: [dst, ...]} — a copy, safe to iterate while the pusher runs."""
    with _link_lock:
        return {k: list(v) for k, v in _varlinks.items()}


def link_targets(name):
    with _link_lock:
        return list(_varlinks.get(name, []))


def link_source_of(name):
    """Which variable pushes INTO this one, or None."""
    with _link_lock:
        for src, dsts in _varlinks.items():
            if name in dsts:
                return src
    return None


def is_link_src(name):
    with _link_lock:
        return bool(_varlinks.get(name))


def is_link_dst(name):
    return link_source_of(name) is not None


def is_linked(name):
    return is_link_src(name) or is_link_dst(name)


def link_add(src, dst):
    """Link src -> dst. Returns (ok, message)."""
    src = str(src or "").strip()
    dst = str(dst or "").strip()
    if not dst:
        return False, "Type the variable to push into"
    if dst == src:
        return False, "A variable cannot push into itself"
    with _link_lock:
        if dst in _varlinks.get(src, []):
            return False, f"'{src}' already pushes into '{dst}'"
        # One writer per target. Two sources pushing into one row would take
        # turns overwriting each other, and which one you saw would depend on
        # timing -- a bug that looks like the value flickering.
        for other, dsts in _varlinks.items():
            if dst in dsts and other != src:
                return False, f"'{dst}' is already fed by '{other}' — unlink that first"
        # A -> B -> A would push forever, each write making the other change.
        if src in _varlinks.get(dst, []):
            return False, f"'{dst}' already pushes into '{src}' — that would loop"
        _varlinks.setdefault(src, []).append(dst)
        _link_last.pop(src, None)      # force one push now, so it takes effect
    _save_varlinks()
    if dst not in _variable_store:
        _create_or_write(dst, "")
    print(f"[ignoAPI] linked '{src}' -> '{dst}'")
    return True, ""


def link_remove(name):
    """Unlink `name` whether it is the source or the target.

    From a row you can only see the pair, not which end you clicked, so both
    ends do the same understandable thing rather than offering two menu items
    that differ in a way nobody wants to think about.
    """
    removed = []
    with _link_lock:
        if _varlinks.get(name):
            removed = [(name, d) for d in _varlinks.pop(name, [])]
            _link_last.pop(name, None)
        else:
            for src, dsts in list(_varlinks.items()):
                if name in dsts:
                    dsts.remove(name)
                    removed.append((src, name))
                    if not dsts:
                        _varlinks.pop(src, None)
                    _link_last.pop(src, None)
    if removed:
        _save_varlinks()
        for a, b in removed:
            print(f"[ignoAPI] unlinked '{a}' -> '{b}'")
    return removed


def link_forget(name):
    """Drop every link mentioning `name` — called when it is deleted, so a
    dangling link cannot keep recreating the row that was just removed."""
    return link_remove(name) if is_linked(name) else []


LINK_INTERVAL_SEC = 0.05


def _link_loop():
    """Push each source's value into its targets WHEN IT CHANGES."""
    while True:
        time.sleep(LINK_INTERVAL_SEC)
        if _shutting_down:
            continue
        links = link_map()
        if not links:
            continue
        try:
            snapshot = _read_all()
        except Exception:
            continue
        for src, dsts in links.items():
            if src not in snapshot:
                continue
            val = snapshot.get(src)
            with _link_lock:
                # `in` first, then compare. Testing a sentinel value instead
                # would swallow the first push of a variable whose value is
                # genuinely None or "".
                if src in _link_last and _link_last[src] == val:
                    continue
                _link_last[src] = val
            for dst in dsts:
                try:
                    _create_or_write(dst, val)
                except Exception as e:
                    print(f"[ignoAPI] link {src} -> {dst} failed: {e}")


_link_thread = threading.Thread(target=_link_loop, daemon=True)
_link_thread.start()


def order_linked_rows(items):
    """Reorder so every target sits immediately under its source.

    Sorting by name or date scatters a linked pair; the point of a link is
    that the two belong together, so the pair overrides the sort -- but only
    for the target's POSITION. The source stays exactly where the sort put it,
    so the table still reads the way the sort button says it does.
    """
    links = row_pair_map()
    if not links:
        return items
    vals = dict(items)
    present = set(vals)
    tgts = {s: [d for d in ds if d in present]
            for s, ds in links.items() if s in present}
    tgts = {s: d for s, d in tgts.items() if d}
    if not tgts:
        return items

    moved = {d for ds in tgts.values() for d in ds}
    out, seen = [], set()

    def emit(k):
        if k in seen:
            return
        seen.add(k)
        out.append((k, vals[k]))
        for d in tgts.get(k, []):
            emit(d)

    for k, _v in items:
        if k in moved:
            continue                 # its source emits it
        emit(k)
    for k, v in items:               # cycles or orphans: nothing may vanish
        if k not in seen:
            seen.add(k)
            out.append((k, v))
    return out


# ──────────────────────────────────────────────────────────────
# COMBINE
#   Type this into ANY variable's value and press Enter:
#
#       combine{a_id},{ar_kp},{vr_kp}
#
#   and a companion row `<name>_combined` appears holding `1,35,44` -- the
#   three values, in the order written, kept up to date continuously. Change
#   the line and the companion follows on the next tick.
#
#   NO REGISTRY, NO BUTTON. The command IS the definition and it lives in the
#   variable, so it is already saved with everything else in vars.json,
#   already editable in the table, and already deleted when the row is. A
#   registry file would be a second copy of the same fact, and the two would
#   eventually disagree.
#
#   It is a TEMPLATE, not a list of names: every {name} is replaced and
#   everything else is kept exactly as typed. That is why the commas come out
#   as commas without a separator setting anywhere, and it means
#   `combine POS={x} ANG={y}` works the same way for free.
# ──────────────────────────────────────────────────────────────
COMBINED_SUFFIX = "_combined"
COMBINE_INTERVAL_SEC = 0.05

# `combine` then a template with at least one {placeholder}. Requiring a
# placeholder is what keeps an ordinary value that happens to start with the
# word "combine" from being treated as a command.
_COMBINE_RE = re.compile(r"^\s*combine\s*(.*\{[^{}]+\}.*)$",
                         re.IGNORECASE | re.DOTALL)
_COMBINE_FIELD_RE = re.compile(r"\{([^{}]+)\}")

_combine_active = set()      # names currently holding a combine command
_combine_lock = threading.Lock()


def combined_var(name):
    """'combi' -> 'combi_combined'."""
    return f"{name}{COMBINED_SUFFIX}"


def combine_spec(value):
    """The template out of a combine command, or None if this is not one."""
    if not isinstance(value, str):
        return None
    m = _COMBINE_RE.match(value)
    return m.group(1).strip() if m else None


def combine_names(spec):
    """The variable names a template refers to, in order, with repeats kept."""
    return [n.strip() for n in _COMBINE_FIELD_RE.findall(spec or "")]


def render_combine(spec, snapshot):
    """Fill the template from a snapshot of the store.

    A name that does not exist becomes an EMPTY slot rather than being
    dropped: the whole point is reading the result by position, and a missing
    third value silently shifting the fourth into its place is the one failure
    that would not look like a failure.
    """
    def one(m):
        name = m.group(1).strip()
        if name not in snapshot:
            return ""
        v = snapshot.get(name)
        return "" if v is None else str(v)
    return _COMBINE_FIELD_RE.sub(one, spec)


def combine_map():
    """{src: [src_combined]} for every live combine — the same shape as the
    link map, so the row ordering and the connector can treat both alike."""
    with _combine_lock:
        return {n: [combined_var(n)] for n in _combine_active}


def is_combine_src(name):
    with _combine_lock:
        return name in _combine_active


def is_combined_var(name):
    if not name.endswith(COMBINED_SUFFIX):
        return False
    with _combine_lock:
        return name[: -len(COMBINED_SUFFIX)] in _combine_active


def is_combine_row(name):
    return is_combine_src(name) or is_combined_var(name)


# ──────────────────────────────────────────────────────────────
# REQUESTS THAT ARRIVE IN A VARIABLE
# ──────────────────────────────────────────────────────────────
# A request is a value that asks for something to be done, rather than a
# value to be read. It is carried out and the ANSWER is written back over
# it -- and that replacement is the whole mechanism: the box says who did
# the work and whether it worked, and the same text arriving again is a
# NEW request rather than the old one being obeyed on every tick.
#
# This is what lets one machine set up a link on another with no special
# channel: put the text anywhere that reaches it -- a sync's _tx, a shared
# variable, a write from a script -- and it happens where it lands.
#
# QUOTES ARE OPTIONAL. A value that has been round a JSON store and back
# often arrives wrapped, and a quoted link(a,b) is plainly the same request
# as a bare one.
REQUEST_INTERVAL_SEC = 0.1

_REQUEST_RE = re.compile(
    r'^\s*["\']?\s*(link|unlink|combine)\s*\(([^()]*)\)\s*["\']?\s*$',
    re.IGNORECASE)


def parse_request(value):
    """A request out of a value: (kind, [args]), or None.

    None for anything else, which is nearly everything -- this is asked of
    every variable ten times a second."""
    if not isinstance(value, str):
        return None
    m = _REQUEST_RE.match(value)
    if not m:
        return None
    kind = m.group(1).lower()
    args = [a.strip().strip('\'\"') for a in m.group(2).split(',')]
    args = [a for a in args if a]
    # The wrong number of names is not a request at all. Treating it as a
    # broken one would answer FAILED into a row that was only ever holding
    # a value that happened to look like this.
    if kind == "link" and len(args) != 2:
        return None
    if kind == "unlink" and len(args) != 1:
        return None
    if kind == "combine" and len(args) < 2:
        return None
    return kind, args


def request_answer(kind, ok, why=''):
    """The text written back over a request.

    Named after THIS machine, so an answer that has travelled says which
    one did the work -- on a sync with three peers the replies land in
    three different rows and would otherwise be indistinguishable."""
    who = ignoapi_hostname() or get_lan_ip()
    tail = "ok" if ok else ("FAILED: %s" % why if why else "FAILED")
    return "%s_%s_%s" % (who, kind, tail)


def run_request(where, kind, args):
    """Carry one out. Returns (ok, note_for_the_log).

    `where` is the variable the request arrived in, so a request cannot ask
    to combine into the very row that is carrying it."""
    if kind == "link":
        src, dst = args
        ok, msg = link_add(src, dst)
        return ok, "link %s -> %s: %s" % (src, dst, msg)
    if kind == "unlink":
        gone = link_remove(args[0])
        if gone:
            return True, "unlink %s: %s" % (
                args[0], ", ".join("%s -> %s" % g for g in gone))
        return False, "unlink %s: was not linked" % args[0]
    # combine(new, a, b, c): `new` holds the recipe, and this build's
    # combine engine keeps new_combined filled in from it, live.
    new, sources = args[0], args[1:]
    if new == where:
        return False, "combine %s: a row cannot combine into itself" % new
    spec = "combine " + ",".join("{%s}" % v for v in sources)
    _create_or_write(new, spec)
    return True, "combine %s <- %s" % (new, ", ".join(sources))


def _request_loop():
    """Obey requests sitting in variables, and answer in place."""
    while True:
        time.sleep(REQUEST_INTERVAL_SEC)
        if _shutting_down:
            continue
        try:
            snapshot = _read_all()
        except Exception:
            continue
        for name, val in snapshot.items():
            # A SYNC'S OWN ROW belongs to its child, not here. That row is
            # the readData/writeData box, and the child answers into it --
            # two things obeying the same text and writing over each
            # other's answer is a race whose winner changes every tick, and
            # it made link() and combine() typed there behave at random.
            # A request meant for the peers goes through the child; one
            # meant for this machine goes in any other variable.
            if is_syncpeer(name):
                continue
            req = parse_request(val)
            if req is None:
                continue
            kind, args = req
            try:
                ok, note = run_request(name, kind, args)
            except Exception as e:
                ok, note = False, "%s failed: %s" % (kind, e)
            # Answered whether it worked or not. A request left in the box
            # would be obeyed again on every tick, ten times a second, for
            # as long as it sat there.
            why = note.split(": ", 1)[-1] if not ok else ""
            try:
                _create_or_write(name, request_answer(kind, ok, why))
            except Exception:
                pass
            print("[ignoAPI] %s (asked in %s)" % (note, name))


_request_thread = threading.Thread(target=_request_loop, daemon=True)
_request_thread.start()

def _combine_loop():
    """Keep every <name>_combined in step with its command."""
    global _combine_active
    while True:
        time.sleep(COMBINE_INTERVAL_SEC)
        if _shutting_down:
            continue
        try:
            snapshot = _read_all()
        except Exception:
            continue

        active = {}
        for name, val in snapshot.items():
            # A result row is never itself a command; without this, writing a
            # template into one would have it combine its own output.
            if name.endswith(COMBINED_SUFFIX):
                continue
            spec = combine_spec(val)
            if spec is not None:
                active[name] = spec

        for name, spec in active.items():
            out = render_combine(spec, snapshot)
            target = combined_var(name)
            # Only on CHANGE. Writing every tick would be twenty identical
            # writes a second per combine, for as long as the program runs.
            if target not in snapshot or snapshot.get(target) != out:
                try:
                    _create_or_write(target, out)
                except Exception as e:
                    print(f"[ignoAPI] combine {name} failed: {e}")

        with _combine_lock:
            gone = _combine_active - set(active)
            _combine_active = set(active)
        for name in gone:
            # The command was edited away or deleted. Remove the result too: a
            # frozen leftover looks live, which is worse than it being absent.
            target = combined_var(name)
            try:
                if target in snapshot:
                    _delete(target)
                    print(f"[ignoAPI] combine '{name}' removed — dropped {target}")
            except Exception:
                pass


_combine_thread = threading.Thread(target=_combine_loop, daemon=True)
_combine_thread.start()


def row_pair_map():
    """Every 'this row feeds that row' pair: links AND combines.

    One map so the adjacency and the connector cannot disagree about which
    rows belong together -- they are the same statement drawn two ways.
    """
    pairs = link_map()
    # A remote sync has no local "source" row, so its _status is the anchor --
    # it is the row that says what the group IS.
    for src, dsts in remote_sync_groups().items():
        pairs.setdefault(src, []).extend(d for d in dsts if d not in pairs.get(src, []))
    for src, dsts in combine_map().items():
        pairs.setdefault(src, []).extend(d for d in dsts if d not in pairs.get(src, []))
    return pairs


# ──────────────────────────────────────────────────────────────
# FTP SERVER MANAGER
#   Right-click a variable -> Create FTP Server, pick a folder, and that
#   folder is shared on the network. The variable itself holds the LINK:
#
#       drop              ftp://ignoapi_helloworld.local:2121
#       drop_ftp_status   CONNECT / LOGIN / RECEIVED file.csv (12KB) / ...
#
#   The link uses this machine's ADDRESS name when it has one, because that
#   is the address that survives a DHCP lease changing. It falls back to the
#   LAN IP when no name is set.
#
#   Leave the username and password EMPTY for an anonymous server. That means
#   anyone who can reach the port can read and write those files, which is a
#   reasonable thing on an isolated robot network and a bad one elsewhere --
#   so the status row says which mode it is in, every time it starts.
#
#   Runs as a SEPARATE PROCESS (<name>_autoftp.exe), like every other helper:
#   a file transfer must not compete with the GUI thread, and a crash in a
#   server that accepts connections must not take ignoAPI with it.
# ──────────────────────────────────────────────────────────────
FTPSERVERS_FILE = "ftpservers.json"

FT_FIELDS = ["folder", "port", "username", "password", "read_only",
             "share_with", "log_file", "runatstartup"]

FT_STATUS_SUFFIX = "ftp_status"


def ft_default_fields():
    return {"folder": "", "port": "2121", "username": "", "password": "",
            "read_only": "false", "share_with": "",
            "log_file": "ftp.log", "runatstartup": "false"}


def ft_fields_from_config(cfg):
    f = ft_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def ft_cast_fields(fields):
    def num(v, cast, default):
        try:
            return cast(str(v).strip())
        except (ValueError, TypeError):
            return default
    return {
        "folder":       (fields.get("folder") or "").strip(),
        "port":         num(fields.get("port"), int, 2121),
        # NOT stripped: a password may legitimately begin or end with a space,
        # and quietly trimming one is a login failure nobody can explain.
        "username":     (fields.get("username") or "").strip(),
        "password":     (fields.get("password") or ""),
        "read_only":    str(fields.get("read_only", "false")).strip().lower()
                        in ("true", "1", "yes", "on"),
        # Left as typed: it is a list of addresses, and autoFTP is the one
        # place that knows how to split it -- parsing it in two places is how
        # the two come to disagree about what "host:port" means.
        "share_with":   (fields.get("share_with") or "").strip(),
        "log_file":     (fields.get("log_file") or "ftp.log").strip() or "ftp.log",
        "runatstartup": str(fields.get("runatstartup", "false")).strip().lower()
                        in ("true", "1", "yes", "on"),
    }


def ft_status_var(name):
    return f"{name}_{FT_STATUS_SUFFIX}"


def ft_shares_var(name):
    return f"{name}_ftp_shares"


def ft_sub_vars(name):
    return [ft_status_var(name), ft_shares_var(name)]


def _load_ftpservers():
    if os.path.exists(FTPSERVERS_FILE):
        try:
            with open(FTPSERVERS_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: ftpservers.json corrupt — starting fresh.")
    return {}


_ftpservers = _load_ftpservers()
_ft_procs   = {}
_ft_disabled = set()
_ft_lock    = threading.Lock()


def _save_ftpservers():
    tmp = FTPSERVERS_FILE + ".tmp"
    try:
        with _ft_lock:
            snapshot = dict(_ftpservers)
        with open(tmp, "w") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, FTPSERVERS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save ftpservers.json: {e}")


def is_ftpserver(name):
    with _ft_lock:
        return name in _ftpservers


def ftpserver_config(name):
    with _ft_lock:
        return dict(_ftpservers.get(name, {}))


def is_ftp_sub_var(name):
    with _ft_lock:
        owners = list(_ftpservers.keys())
    return any(name in ft_sub_vars(o) for o in owners)


# Rows whose VALUE is an ftp:// link, refreshed once a frame from the
# snapshot the table already holds. A set lookup, because this is asked of
# every variable on every frame and reading the store per row would not be.
_ftp_link_names = set()


def note_ftp_links(data):
    """Remember which rows currently hold an ftp:// link."""
    global _ftp_link_names
    _ftp_link_names = {
        k for k, v in (data or {}).items()
        if str(v if v is not None else "").strip().strip('"')
           .lower().startswith("ftp://")}


def is_ftp_link_var(name):
    """A row holding an ftp:// link but owned by no local server.

    A link SHARED to another ignoAPI arrives there as an ordinary variable:
    the registry that makes a row gold lives on the machine running the
    server, so on every other machine the link read as a plain string. It
    is the same thing on both sides and should look like it.
    """
    return (name in _ftp_link_names
            and not is_ftpserver(name) and not is_ftp_sub_var(name))


def is_ftp_row(name):
    return is_ftpserver(name) or is_ftp_sub_var(name) or is_ftp_link_var(name)


def _ft_paths(name):
    exe_src = os.path.join(SCRIPT_DIR, "autoFTP.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoFTP.py")
    if os.path.exists(exe_src):
        return (exe_src,
                os.path.join(SCRIPT_DIR, f"{name}_autoftp.exe"),
                os.path.join(SCRIPT_DIR, f"{name}_autoftp.json"), True)
    return (py_src,
            os.path.join(SCRIPT_DIR, f"{name}_autoftp.py"),
            os.path.join(SCRIPT_DIR, f"{name}_autoftp.json"), False)


def _write_ft_config(name, cfg):
    _, _, json_path, _ = _ft_paths(name)
    full = {k: cfg.get(k) for k in FT_FIELDS}
    full["variable"]     = name
    full["ignoapi_host"] = "127.0.0.1"
    full["ignoapi_port"] = PORT
    with open(json_path, "w") as f:
        json.dump(full, f, indent=2)
    return json_path


def ftpserver_is_live(name):
    """Green dot: the process is up AND its status row says it is serving.
    A process that is alive but failed to bind the port is not live."""
    with _ft_lock:
        proc = _ft_procs.get(name)
    if proc is None or proc.poll() is not None:
        return False
    try:
        st = _read(ft_status_var(name))
    except Exception:
        return False
    return bool(st) and not str(st).strip().upper().startswith(
        ("ERROR", "STOPPED", "STARTING", "DISCONNECTED"))


def ftpserver_stop(name):
    with _ft_lock:
        proc = _ft_procs.pop(name, None)
    _kill_process_tree(proc)


def _ft_ensure_sub_vars(name):
    for v in ft_sub_vars(name):
        try:
            if _read(v) is None:
                _create_or_write(v, "CREATED — not started yet")
        except Exception:
            pass


def ftpserver_launch(name):
    source, target, _, is_exe = _ft_paths(name)
    if not os.path.exists(source) and not os.path.exists(target):
        print(f"[ignoAPI] ftp: no autoFTP.exe/.py to duplicate for '{name}'")
        _create_or_write(ft_status_var(name), "ERROR — autoFTP.exe/.py missing")
        return False

    ftpserver_stop(name)
    ok, err = _refresh_duplicate(source, target)
    if not ok:
        print(f"[ignoAPI] ftp: could not duplicate program for '{name}': {err}")
        _create_or_write(ft_status_var(name), f"ERROR — copy failed: {err}")
        return False

    with _ft_lock:
        cfg = dict(_ftpservers.get(name, {}))
    _write_ft_config(name, cfg)
    _ft_ensure_sub_vars(name)

    cmd = _child_launch_cmd(target, is_exe)
    if cmd is None:
        print(f"[ignoAPI] ftp '{name}': " + _frozen_child_hint(name, "autoFTP.exe"))
        _create_or_write(ft_status_var(name), "ERROR — build autoFTP.exe first")
        return False
    try:
        proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _ft_lock:
            _ft_procs[name] = proc
            _ft_disabled.discard(name)
        print(f"[ignoAPI] ftp '{name}' launched ({os.path.basename(target)})")
        return True
    except Exception as e:
        print(f"[ignoAPI] ftp launch failed for '{name}': {e}")
        _create_or_write(ft_status_var(name), f"ERROR — {e}")
        return False


def ftpserver_create(name, cfg):
    """Register + configure + launch an FTP server for <name>.
    Returns (ok, error_message)."""
    folder = str(cfg.get("folder") or "").strip()
    if not folder:
        return False, "Pick the folder to share"
    if not os.path.isdir(folder):
        # Refused rather than created: a typo'd path would otherwise silently
        # share an empty folder somewhere nobody meant.
        return False, f"'{folder}' is not a folder that exists"
    try:
        port = int(cfg.get("port"))
        if not (1 <= port <= 65535):
            raise ValueError
    except (TypeError, ValueError):
        return False, f"Port {cfg.get('port')!r} is not a number between 1 and 65535"
    if is_autoclient(name) or is_comclient(name) or is_modbusmaster(name) \
            or is_modbusslave(name) or is_syncpeer(name) or is_vdabridge(name):
        return False, f"'{name}' is already used by another connection"
    exe_src = os.path.join(SCRIPT_DIR, "autoFTP.exe")
    py_src  = os.path.join(SCRIPT_DIR, "autoFTP.py")
    if not os.path.exists(exe_src) and not os.path.exists(py_src):
        msg = "autoFTP.exe (or .py) not found next to ignoAPI — cannot create an FTP server."
        print(f"[ignoAPI] ftp create '{name}' refused: {msg}")
        return False, msg

    with _ft_lock:
        _ftpservers[name] = {k: cfg.get(k) for k in FT_FIELDS}
    _save_ftpservers()
    if name not in _variable_store:
        _create_or_write(name, "")
    _ft_ensure_sub_vars(name)

    anon = not str(cfg.get("username") or "").strip()
    if anon:
        login_desc = (
            "ANONYMOUS — anyone who can reach the port can read"
            + ("" if cfg.get("read_only") else " AND WRITE")
            + " these files"
        )
    else:
        login_desc = cfg.get("username")

    print(f"\n[ignoAPI] FTP SERVER '{name}'\n"
          f"    sharing : {folder}\n"
          f"    port    : {port}\n"
          f"    login   : {login_desc}\n"
          f"    the link appears in the '{name}' row once it starts\n")
    ftpserver_launch(name)
    return True, ""


def ftpserver_edit(name, cfg):
    with _ft_lock:
        _ftpservers[name] = {k: cfg.get(k) for k in FT_FIELDS}
    _save_ftpservers()
    ftpserver_launch(name)


def ftpserver_reconnect(name):
    if is_ftpserver(name):
        # A person asked for it: forget the failures, or the watchdog
        # would refuse to start something they have just fixed.
        relaunch_reset("ftp", name)
        relaunch_gave_up_said.pop(("ftp", name), None)
        ftpserver_launch(name)


def ftpserver_disconnect(name):
    ftpserver_stop(name)
    with _ft_lock:
        _ft_disabled.add(name)
    try:
        _create_or_write(ft_status_var(name), "STOPPED (by user)")
    except Exception:
        pass
    print(f"[ignoAPI] ftp server '{name}' stopped by user")


def ftpserver_delete(name):
    """Stop the server, unregister, remove the status row and the duplicated
    program. THE SHARED FOLDER AND ITS FILES ARE NOT TOUCHED -- deleting a
    variable must never delete somebody's files."""
    companions = ft_sub_vars(name)
    ftpserver_stop(name)
    with _ft_lock:
        _ftpservers.pop(name, None)
        _ft_disabled.discard(name)
    _save_ftpservers()
    for cv in companions:
        try:
            _delete(cv)
        except Exception:
            pass
    _, target, json_path, _ = _ft_paths(name)
    for path in (json_path, target):
        if os.path.exists(path):
            _remove_with_retry(path)


def _stop_all_ftpservers():
    with _ft_lock:
        names = list(_ft_procs.keys())
    for name in names:
        ftpserver_stop(name)


atexit.register(_stop_all_ftpservers)


def ftpserver_startup_launch_all():
    with _ft_lock:
        items = list(_ftpservers.items())
    for name, cfg in items:
        if cfg.get("runatstartup"):
            ftpserver_launch(name)


FT_WATCHDOG_INTERVAL_SEC = 5.0


def _ft_watchdog_loop():
    while True:
        time.sleep(FT_WATCHDOG_INTERVAL_SEC)
        if _shutting_down:
            continue
        with _ft_lock:
            names = [n for n in _ftpservers if n not in _ft_disabled]
            procs = {n: _ft_procs.get(n) for n in names}
        for name in names:
            proc = procs.get(name)
            if proc is None or proc.poll() is not None:
                if not relaunch_allowed("ftp", name):
                    if not relaunch_gave_up_said.get(("ftp", name)):
                        relaunch_gave_up_said[("ftp", name)] = True
                        print(f"[ignoAPI] '{name}' died on every start "
                              f"-- giving up. The usual cause is the port "
                              f"already being in use: read the traceback "
                              f"above, fix that, then Reconnect.")
                        try:
                            _create_or_write(ft_status_var(name),
                                             "STOPPED — kept crashing on start; see the console")
                        except Exception:
                            pass
                    continue
                print(f"[ignoAPI] ftp watchdog: '{name}' is not running -- restarting")
                ftpserver_launch(name)


_ft_watchdog_thread = threading.Thread(target=_ft_watchdog_loop, daemon=True)
_ft_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# VDA 5050 BRIDGES (MQTT)
# ──────────────────────────────────────────────────────────────
VDABRIDGES_FILE = "vdabridges.json"

VD_FIELDS = [
    "broker_host", "broker_port", "username", "password", "use_tls",
    "tls_ca", "client_id", "interface", "vda_major", "protocol_version",
    "robots", "qos_order", "qos_state", "stale_after_sec", "node_map_csv",
    "subscribe_visualization", "store_raw", "log_file", "runatstartup"
]


def vd_default_fields():
    return {
        "broker_host": "127.0.0.1", "broker_port": "1883",
        "username": "", "password": "", "use_tls": "false",
        "tls_ca": "", "client_id": "", "interface": "uagv",
        "vda_major": "v2", "protocol_version": "2.0.0",
        "robots": "", "qos_order": "1", "qos_state": "0",
        "stale_after_sec": "10", "node_map_csv": "",
        "subscribe_visualization": "false", "store_raw": "false",
        "log_file": "vda.log", "runatstartup": "true"
    }


def vd_fields_from_config(cfg):
    f = vd_default_fields()
    for k in f:
        if cfg.get(k) is not None:
            f[k] = str(cfg.get(k))
    return f


def parse_vda_robots(raw):
    """Parse 'rob5:VendorX:AGV-07, rob6:VendorY:AMR-02' into robot dicts."""
    out = []
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
            out.append({"robot_id": rid, "manufacturer": mfr, "serial_number": serial})
    return out


def format_vda_robots(robot_list):
    return ",".join(f"{r['robot_id']}:{r['manufacturer']}:{r['serial_number']}" for r in robot_list)


def vd_cast_fields(fields):
    def num(v, cast, default):
        try:
            return cast(str(v).strip())
        except (ValueError, TypeError):
            return default
    return {
        "broker_host":              (fields.get("broker_host") or "127.0.0.1").strip(),
        "broker_port":              num(fields.get("broker_port"), int, 1883),
        "username":                 (fields.get("username") or "").strip(),
        "password":                 (fields.get("password") or ""),
        "use_tls":                  str(fields.get("use_tls", "false")).strip().lower()
                                    in ("true", "1", "yes", "on"),
        "tls_ca":                   (fields.get("tls_ca") or "").strip(),
        "client_id":                (fields.get("client_id") or "").strip(),
        "interface":                (fields.get("interface") or "uagv").strip(),
        "vda_major":                (fields.get("vda_major") or "v2").strip(),
        "protocol_version":         (fields.get("protocol_version") or "2.0.0").strip(),
        "robots":                   (fields.get("robots") or "").strip(),
        "qos_order":                num(fields.get("qos_order"), int, 1),
        "qos_state":                num(fields.get("qos_state"), int, 0),
        "stale_after_sec":          num(fields.get("stale_after_sec"), float, 10.0),
        "node_map_csv":             (fields.get("node_map_csv") or "").strip(),
        "subscribe_visualization":  str(fields.get("subscribe_visualization", "false")).strip().lower()
                                    in ("true", "1", "yes", "on"),
        "store_raw":                str(fields.get("store_raw", "false")).strip().lower()
                                    in ("true", "1", "yes", "on"),
        "log_file":                 (fields.get("log_file") or "vda.log").strip(),
        "runatstartup":             str(fields.get("runatstartup", "false")).strip().lower()
                                    in ("true", "1", "yes", "on"),
    }


def vd_status_var(name):
    return f"{name}_status"


def vd_robots_var(name):
    return f"{name}_robots"


def vd_sub_vars(name, cfg=None):
    """All companion variables owned by this VDA bridge."""
    if cfg is None:
        cfg = vdabridge_config(name)
    out = [vd_status_var(name), vd_robots_var(name)]
    raw_robots = cfg.get("robots", "")
    for r in parse_vda_robots(raw_robots):
        rid = r["robot_id"]
        out.extend([f"{rid}_vda_rx", f"{rid}_vda_tx", f"{rid}_vda_result"])
        if str(cfg.get("store_raw", "")).lower() in ("true", "1", "yes", "on"):
            out.extend([f"{rid}_vda_state", f"{rid}_vda_order"])
    return out


_vdabridges = {}
_vd_procs = {}
_vd_disabled = set()
_vd_lock = threading.Lock()


def _vd_file_path():
    return os.path.join(SCRIPT_DIR, VDABRIDGES_FILE)


def _load_vdabridges():
    path = _vd_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[ignoAPI] could not read {VDABRIDGES_FILE}: {e}")
        return {}


def _save_vdabridges():
    path = _vd_file_path()
    tmp = path + ".tmp"
    with _vd_lock:
        data = dict(_vdabridges)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f"[ignoAPI] could not save {VDABRIDGES_FILE}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


_vdabridges.update(_load_vdabridges())


def is_vdabridge(name):
    with _vd_lock:
        return name in _vdabridges


def vdabridge_config(name):
    with _vd_lock:
        return dict(_vdabridges.get(name, {}))


def is_vda_sub_var(name):
    with _vd_lock:
        bridges = list(_vdabridges.items())
    for b_name, cfg in bridges:
        if name in vd_sub_vars(b_name, cfg):
            return True
    return False


def is_vda_row(name):
    return is_vdabridge(name) or is_vda_sub_var(name)


def _vd_paths(name):
    """(source, target, json_path, is_exe)"""
    exe_src = os.path.join(SCRIPT_DIR, "autoVDA.exe")
    py_src = os.path.join(SCRIPT_DIR, "autoVDA.py")
    if os.path.exists(exe_src):
        return exe_src, os.path.join(SCRIPT_DIR, f"{name}_autovda.exe"), os.path.join(SCRIPT_DIR, f"{name}_autovda.json"), True
    return py_src, os.path.join(SCRIPT_DIR, f"{name}_autovda.py"), os.path.join(SCRIPT_DIR, f"{name}_autovda.json"), False


def _write_vd_config(name, cfg):
    _src, _tgt, json_path, _is_exe = _vd_paths(name)
    payload = dict(cfg)
    payload["variable"] = name
    payload["ignoapi_host"] = "127.0.0.1"
    payload["ignoapi_port"] = port
    tmp = json_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, json_path)


def vdabridge_is_live(name):
    with _vd_lock:
        p = _vd_procs.get(name)
    if p is None or p.poll() is not None:
        return False
    st = str(current_data.get(vd_status_var(name), "")).strip().upper()
    return st.startswith("CONNECTED")


def vdabridge_stop(name):
    with _vd_lock:
        p = _vd_procs.pop(name, None)
    if p is not None:
        try:
            p.terminate()
            p.wait(timeout=2.0)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def vdabridge_launch(name):
    vdabridge_stop(name)
    cfg = vdabridge_config(name)
    if not cfg:
        return
    src, tgt, json_path, is_exe = _vd_paths(name)
    if not os.path.exists(src):
        print(f"[ignoAPI] vda: neither autoVDA.exe nor autoVDA.py found in {SCRIPT_DIR}")
        return
    _refresh_duplicate(src, tgt)
    _write_vd_config(name, cfg)

    # Ensure companion variables exist
    for sub in vd_sub_vars(name, cfg):
        if sub not in current_data:
            _create_or_write(sub, "")

    cmd = _child_launch_cmd(tgt, is_exe)
    try:
        p = subprocess.Popen(cmd, cwd=SCRIPT_DIR)
        with _vd_lock:
            _vd_procs[name] = p
        print(f"[ignoAPI] vda '{name}' launched ({os.path.basename(tgt)})")
    except Exception as e:
        print(f"[ignoAPI] failed to launch vda '{name}': {e}")


def vdabridge_create(name, cfg):
    if not name or not re.match(r'^[A-Za-z0-9_]+$', name):
        return False, "Name must be alphanumeric + underscore"
    if is_autoclient(name) or is_comclient(name) or is_modbusmaster(name) or is_modbusslave(name) or is_syncpeer(name) or is_ftpserver(name) or is_vdabridge(name):
        return False, f"'{name}' is already used by another connection"

    b_host = cfg.get("broker_host", "").strip()
    if not b_host:
        return False, "Broker host is required"
    b_port = cfg.get("broker_port")
    if not b_port or not str(b_port).isdigit() or not (1 <= int(b_port) <= 65535):
        return False, "Valid broker port (1-65535) is required"

    src, _tgt, _j, _e = _vd_paths(name)
    if not os.path.exists(src):
        return False, "autoVDA.py / autoVDA.exe helper is missing"

    with _vd_lock:
        _vdabridges[name] = cfg
        _vd_disabled.discard(name)
    _save_vdabridges()

    _create_or_write(name, f"mqtt://{b_host}:{b_port}")
    for sub in vd_sub_vars(name, cfg):
        _create_or_write(sub, "")

    vdabridge_launch(name)
    return True, ""


def vdabridge_edit(name, cfg):
    old_sub = set(vd_sub_vars(name, vdabridge_config(name)))
    new_sub = set(vd_sub_vars(name, cfg))
    removed = old_sub - new_sub
    for rem in removed:
        try:
            _delete(rem)
        except Exception:
            pass

    with _vd_lock:
        _vdabridges[name] = cfg
        _vd_disabled.discard(name)
    _save_vdabridges()
    vdabridge_launch(name)


def vdabridge_reconnect(name):
    relaunch_reset("vda", name)
    with _vd_lock:
        _vd_disabled.discard(name)
    print(f"[ignoAPI] reconnecting vda '{name}'")
    vdabridge_launch(name)


def vdabridge_disconnect(name):
    with _vd_lock:
        _vd_disabled.add(name)
    vdabridge_stop(name)
    try:
        _create_or_write(vd_status_var(name), "STOPPED (by user)")
    except Exception:
        pass
    print(f"[ignoAPI] vda '{name}' disconnected by user")


def vdabridge_delete(name):
    vdabridge_stop(name)
    cfg = vdabridge_config(name)
    sub = vd_sub_vars(name, cfg)
    with _vd_lock:
        _vdabridges.pop(name, None)
        _vd_disabled.discard(name)
    _save_vdabridges()

    for s in sub:
        try:
            _delete(s)
        except Exception:
            pass

    # Remove duplicated exe/py and json
    _src, tgt, json_path, _e = _vd_paths(name)
    for p in (tgt, json_path):
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass
    print(f"[ignoAPI] vda '{name}' deleted")


def _stop_all_vdabridges():
    with _vd_lock:
        procs = list(_vd_procs.items())
        _vd_procs.clear()
    for name, p in procs:
        try:
            p.terminate()
            p.wait(timeout=1.0)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


atexit.register(_stop_all_vdabridges)


def vdabridge_startup_launch_all():
    with _vd_lock:
        names = [k for k, v in _vdabridges.items() if v.get("runatstartup")]
    for name in names:
        vdabridge_launch(name)


VD_WATCHDOG_INTERVAL_SEC = 5.0


def _vd_watchdog_loop():
    while True:
        time.sleep(VD_WATCHDOG_INTERVAL_SEC)
        with _vd_lock:
            active = [(k, _vd_procs.get(k)) for k in _vdabridges if k not in _vd_disabled]
        for name, proc in active:
            if proc is None or proc.poll() is not None:
                if not relaunch_allowed("vda", name):
                    if not relaunch_gave_up_said.get(("vda", name)):
                        relaunch_gave_up_said[("vda", name)] = True
                        print(f"[ignoAPI] vda '{name}' died repeatedly -- giving up.")
                        try:
                            _create_or_write(vd_status_var(name), "STOPPED — kept crashing; see logs")
                        except Exception:
                            pass
                    continue
                print(f"[ignoAPI] vda watchdog: '{name}' is not running -- restarting")
                vdabridge_launch(name)


_vd_watchdog_thread = threading.Thread(target=_vd_watchdog_loop, daemon=True)
_vd_watchdog_thread.start()



OPENABLE_SCHEMES = ("ftp://", "http://", "https://", "file://", "smb://")


def openable_target(value):
    """What this row points at, or None if it points at nothing.

    Offered on ANY row rather than only FTP ones: a shared link arrives on the
    other machine as an ordinary variable, and it would be strange for the row
    that says ftp://... to be openable on the machine that made it and not on
    the machine it was sent to.
    """
    v = str(value if value is not None else "").strip().strip('"')
    if not v:
        return None
    for scheme in OPENABLE_SCHEMES:
        if v.lower().startswith(scheme):
            # Something has to follow the scheme: a bare "ftp://" opens a
            # window onto nowhere and looks like the feature is broken.
            return v if len(v) > len(scheme) else None
    # A local path, but only if it EXISTS -- otherwise every string with a
    # backslash in it would offer to open something that is not there.
    try:
        if (len(v) > 2 and (v[1:3] == ":\\" or v.startswith("\\\\"))
                and os.path.exists(v)):
            return v
    except (OSError, ValueError):
        pass
    return None


def open_command(target):
    """The command that opens `target`, as a list. None to use the shell default.

    WHY ftp:// IS NOT LEFT TO THE SHELL
        os.startfile("ftp://...") hands the URL to whatever owns the ftp
        protocol, which on a normal Windows box is the browser -- and Chrome
        and Edge REMOVED FTP support, so it opens a tab that does nothing.
        explorer.exe takes the same URL and mounts it as a browsable folder,
        which is the whole point of the FTP module having a link.

    A local path goes to Explorer for the same reason: it is a folder, and
    that is what should open.

    http/https keep the shell default, because there the browser IS right.
    """
    if os.name != "nt":
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        return [opener, target]
    low = target.lower()
    if low.startswith("ftp://"):
        # A trailing slash: Explorer treats ftp://host:2121 without one as a
        # file to fetch rather than a directory to list.
        return ["explorer.exe", target if target.endswith("/") else target + "/"]
    if low.startswith(("http://", "https://")):
        return None                       # the browser is the right handler
    return ["explorer.exe", os.path.normpath(target)]


def open_target(value):
    """Open what a row points at. Returns (ok, message).

    No credentials are ever put in the URL: Explorer asks for them, and a
    password in a URL ends up in the shell history, the recent-places list and
    anyone's screenshot.
    """
    target = openable_target(value)
    if not target:
        return False, "nothing to open in this row"
    cmd = open_command(target)
    try:
        if cmd is None:
            os.startfile(target)                       # noqa: S606
        else:
            # explorer.exe returns 1 even when it worked, so the exit code is
            # deliberately not checked -- treating that as failure would
            # report every successful open as broken.
            subprocess.Popen(cmd)
        print(f"[ignoAPI] opening {target}"
              + (f" via {cmd[0]}" if cmd else " (shell default)"))
        return True, f"opening {target}"
    except Exception as e:
        print(f"[ignoAPI] could not open {target}: {e}")
        return False, f"could not open: {e}"


def pick_folder(title="Pick the folder to share over FTP"):
    """Native folder picker. Returns "" if cancelled or unavailable."""
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        print(f"[ignoAPI] no folder dialog available ({e}) — type the path instead")
        return ""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return filedialog.askdirectory(title=title, mustexist=True) or ""
    finally:
        root.destroy()


# ──────────────────────────────────────────────────────────────
# UI PREFERENCES
#   VIEW and SORT are remembered across restarts. They live in their own file
#   rather than in the variable store, because they are settings for the
#   window and would otherwise appear as two more rows in the table they are
#   sorting.
# ──────────────────────────────────────────────────────────────
UIPREFS_FILE = "uiprefs.json"


def load_uiprefs():
    if os.path.exists(UIPREFS_FILE):
        try:
            with open(UIPREFS_FILE, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            print("[ignoAPI] Warning: uiprefs.json corrupt — using defaults.")
    return {}


def save_uiprefs(**kw):
    """Merge and write. Never fatal: a settings file that cannot be written
    must not stop the window from working."""
    data = load_uiprefs()
    data.update(kw)
    tmp = UIPREFS_FILE + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, UIPREFS_FILE)
    except OSError as e:
        print(f"[ignoAPI] Warning: could not save uiprefs.json: {e}")


# The Win32 clipboard used to live here. It moved to ignoclip so the
# mapper's text boxes could use it without importing this module (which
# would start the servers). These two names stay because the rest of the
# file calls them, but there is only one implementation now.
clipboard_set = _ignoclip.clipboard_set
clipboard_get = _ignoclip.clipboard_get

def _ctrl_held():
    return bool(pygame.key.get_mods() & pygame.KMOD_CTRL)


def _clip_line():
    """Clipboard text flattened to one line.

    Kept for callers outside the text boxes; the boxes themselves no longer
    need it, because a single-line ignotext.Editor already turns a pasted
    newline into a space rather than swallowing it.
    """
    return clipboard_get().replace("\r", " ").replace("\n", " ").strip()


def pick_exe_files():
    """Native multi-select file picker for applications to supervise.

    A throwaway hidden Tk root is created and destroyed per call so nothing
    lingers competing with pygame's event loop."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try: root.attributes("-topmost", True)
        except Exception: pass
        paths = filedialog.askopenfilenames(
            title="Select applications for ignoAPI to run and supervise",
            filetypes=[("Executables", "*.exe"),
                       ("Scripts", "*.bat;*.cmd;*.py"),
                       ("All files", "*.*")])
        root.destroy()
        return [p for p in paths]
    except Exception as e:
        print(f"[ignoAPI] file picker unavailable: {e}")
        return []


def pick_register_map():
    """Native picker for a MODBUS SLAVE register-map CSV.

    Same throwaway-Tk-root approach as pick_exe_files: created and destroyed
    per call so nothing lingers competing with pygame's event loop.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass
        path = filedialog.askopenfilename(
            title="Select the MODBUS register map (address,value[,reg|coil])",
            filetypes=[("Register map", "*.csv"),
                       ("Text files", "*.txt"),
                       ("All files", "*.*")])
        root.destroy()
        return path or ""
    except Exception as e:
        print(f"[ignoAPI] file picker unavailable: {e}")
        return ""


# ──────────────────────────────────────────────────────────────
# EXEC: run and supervise external applications
#
#   EXEC      {C:\path\a.exe},{C:\path\b.exe},...   the list
#   EXECFLAG  true / false                          master switch
#
# With the flag on, every listed program is started and kept running: if one
# exits or is closed, it is relaunched. That lets several robotics programs be
# brought up and held up by ignoAPI alone. Both variables are created empty at
# startup so they are always visible and editable.
#
# The variable NAMES are matched case-insensitively ("exec", "Exec", "EXEC"),
# so whichever spelling a user types is the one that is honoured.
# ──────────────────────────────────────────────────────────────
EXEC_VAR = "EXEC"
EXECFLAG_VAR = "EXECFLAG"
EXEC_WATCHDOG_INTERVAL_SEC = 1.5

_exec_procs = {}                 # path -> subprocess.Popen
_exec_lock = threading.Lock()


def is_exec_var(name):
    return str(name).strip().lower() == EXEC_VAR.lower()


def is_execflag_var(name):
    return str(name).strip().lower() == EXECFLAG_VAR.lower()


def is_exec_row(name):
    """True for either of the two supervisor variables -- both are styled the
    same way in the table."""
    return is_exec_var(name) or is_execflag_var(name)


def parse_exec_list(raw):
    """Paths out of '{a},{b},{c}'.

    Braces are the documented form, but a plain comma-separated list is
    accepted too, and surrounding quotes/whitespace are stripped -- a path
    pasted from Explorer usually arrives quoted."""
    if raw is None:
        return []
    s = str(raw).strip()
    if not s:
        return []
    found = re.findall(r"\{([^{}]*)\}", s)
    if not found:
        found = s.split(",")
    out = []
    for p in found:
        p = p.strip().strip('"').strip("'").strip()
        if p:
            out.append(p)
    return out


def format_exec_list(paths):
    """The canonical '{a},{b}' form written back into the EXEC variable."""
    return ",".join("{" + str(p).strip() + "}" for p in paths if str(p).strip())


def _find_var(predicate, default):
    """The store key matching `predicate`, whatever case it was created in."""
    with _store_lock:
        for k in _variable_store:
            if predicate(k):
                return k
    return default


def exec_var_name():
    return _find_var(is_exec_var, EXEC_VAR)


def execflag_var_name():
    return _find_var(is_execflag_var, EXECFLAG_VAR)


def _matching_values(predicate):
    """Values of EVERY store key matching `predicate`.

    Deliberately plural. 'exec', 'Exec' and 'EXEC' are all accepted spellings,
    so a store can end up holding more than one of them -- e.g. a hand-created
    'exec' alongside the 'EXEC' made at startup. Reading only the first match
    then means the user edits one row while the supervisor reads the other:
    the flag looks permanently off, so nothing ever starts, yet the 'flag is
    off' branch still stops whatever is running. Considering all of them makes
    the row you edited the one that counts, whichever spelling it is.

    Note the two lock acquisitions are SEQUENTIAL, never nested --
    threading.Lock is not reentrant."""
    with _store_lock:
        keys = [k for k in _variable_store if predicate(k)]
    with _store_lock:
        return keys, [_variable_store.get(k) for k in keys]


def _is_truthy(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def exec_paths():
    _keys, raws = _matching_values(is_exec_var)
    out = []
    for raw in raws:
        for p in parse_exec_list(raw):
            if p not in out:
                out.append(p)
    return out


def exec_flag_on():
    """ON if ANY execflag-named variable is set -- see _matching_values."""
    _keys, vals = _matching_values(is_execflag_var)
    return any(_is_truthy(v) for v in vals)


def exec_is_running(path):
    with _exec_lock:
        proc = _exec_procs.get(path)
    return proc is not None and proc.poll() is None


def exec_status():
    """(running, total) across the configured list."""
    paths = exec_paths()
    return sum(1 for p in paths if exec_is_running(p)), len(paths)


def exec_launch(path):
    if not _RUNNING_AS_APP:
        return False              # imported, not run — see _child_launch_cmd
    if not os.path.exists(path):
        print(f"[ignoAPI] exec: '{path}' does not exist -- skipping")
        return False
    if exec_is_running(path):
        return True
    try:
        # Same trap as the child launchers: from a frozen build sys.executable
        # is ignoAPI.exe, so handing it a .py would start ANOTHER ignoAPI.
        if path.lower().endswith(".py"):
            if getattr(sys, "frozen", False):
                print(f"[ignoAPI] exec: cannot run '{path}' from a packaged "
                      f"ignoAPI -- there is no interpreter to hand it to. "
                      f"Point the EXEC list at an .exe instead.")
                return False
            cmd = [sys.executable, path]
        else:
            cmd = [path]
        # start it in its OWN folder: most applications look for their config
        # and data files relative to the working directory
        cwd = os.path.dirname(os.path.abspath(path)) or SCRIPT_DIR
        proc = subprocess.Popen(cmd, cwd=cwd)
        with _exec_lock:
            _exec_procs[path] = proc
        print(f"[ignoAPI] exec launched: {os.path.basename(path)}")
        return True
    except Exception as e:
        print(f"[ignoAPI] exec launch failed for '{path}': {e}")
        return False


def exec_stop(path):
    with _exec_lock:
        proc = _exec_procs.pop(path, None)
    _kill_process_tree(proc)


def _stop_all_execs():
    """Stop every supervised application. ignoAPI is their supervisor, so they
    go down with it rather than being orphaned."""
    with _exec_lock:
        paths = list(_exec_procs)
    for p in paths:
        exec_stop(p)


def _exec_shutdown():
    """Stop the supervised applications FOR GOOD.

    Plain _stop_all_execs() is not enough on its own: the watchdog would see
    them missing a moment later and dutifully bring them back. The shutdown
    flag has to be set first. It matters here because atexit runs handlers in
    REVERSE registration order, so this fires BEFORE the autoclient shutdown
    that would otherwise have set the flag."""
    global _shutting_down
    _shutting_down = True
    _stop_all_execs()


atexit.register(_exec_shutdown)


def exec_startup_launch_all():
    """Bring up the configured applications, if the flag is set."""
    if not exec_flag_on():
        return
    for p in exec_paths():
        exec_launch(p)


def _exec_watchdog_loop():
    """Keep the configured applications running.

    Relaunches anything that has exited, stops anything dropped from the list,
    and stops everything when the flag is cleared -- so toggling EXECFLAG off
    takes effect immediately instead of only at the next restart."""
    warned = [None]
    while True:
        # wait on the change signal, not a plain sleep: flipping EXECFLAG acts
        # immediately instead of up to a full interval later
        _exec_wake.wait(timeout=EXEC_WATCHDOG_INTERVAL_SEC)
        _exec_wake.clear()
        if _shutting_down:
            continue
        try:
            paths = exec_paths()
            on = exec_flag_on()
            dupes = ([k for k in _matching_values(is_exec_var)[0]] +
                     [k for k in _matching_values(is_execflag_var)[0]])
            if len(dupes) > 2 and warned[0] != tuple(dupes):
                warned[0] = tuple(dupes)
                print(f"[ignoAPI] exec: more than one spelling in use {dupes} -- "
                      f"all of them are honoured, but consider deleting the spares")
            if not on:
                with _exec_lock:
                    running = list(_exec_procs)
                for p in running:
                    print(f"[ignoAPI] EXECFLAG off -> stopping {os.path.basename(p)}")
                    exec_stop(p)
                continue
            for p in paths:
                if not exec_is_running(p):
                    exec_launch(p)
            with _exec_lock:
                tracked = list(_exec_procs)
            for p in tracked:
                if p not in paths:
                    print(f"[ignoAPI] exec: '{os.path.basename(p)}' removed from the "
                          f"list -> stopping")
                    exec_stop(p)
        except Exception as e:
            print(f"[ignoAPI] exec watchdog error: {e}")


_exec_watchdog_thread = threading.Thread(target=_exec_watchdog_loop, daemon=True)
_exec_watchdog_thread.start()


# ──────────────────────────────────────────────────────────────
# PYGAME LIVE VISUALIZER UI (MAXIMIZABLE WINDOW)
# ──────────────────────────────────────────────────────────────
def draw_logo(surface, x, y):
    """Draws a stylized tech/robotics logo using Pygame primitives."""
    # Outer ring
    pygame.draw.circle(surface, (150, 150, 150), (x, y), 25, 2)
    # Inner elements
    pygame.draw.circle(surface, (100, 200, 100), (x, y), 10)

    # Draw "gears" or nodes extending from the center
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        end_x = x + math.cos(rad) * 25
        end_y = y + math.sin(rad) * 25
        pygame.draw.line(surface, (150, 150, 150), (x, y), (end_x, end_y), 2)
        pygame.draw.circle(surface, (200, 200, 200), (int(end_x), int(end_y)), 3)


def run_visualizerOld():
    pygame.init()

    # Initial Setup - Windowed and Resizable
    WINDOW_WIDTH, WINDOW_HEIGHT = 1200, 800
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("ignoAPI Live Dashboard")
    clock = pygame.time.Clock()
    # --- SET WINDOW ICON ---
    icon_surf = pygame.Surface((32, 32), pygame.SRCALPHA)
    pygame.draw.circle(icon_surf, (150, 150, 150), (16, 16), 14, 2)
    pygame.draw.circle(icon_surf, (100, 200, 100), (16, 16), 8)
    pygame.display.set_icon(icon_surf)
    # -----------------------
    # UI Colors
    BG_COLOR = (25, 25, 25)
    HEADER_COLOR = (40, 40, 40)
    ROW_COLOR_1 = (32, 32, 32)
    ROW_COLOR_2 = (38, 38, 38)
    TEXT_COLOR = (230, 230, 230)
    HIGHLIGHT_COLOR = (120, 220, 120)
    GRID_COLOR = (60, 60, 60)
    MATCH_COLOR = (80, 80, 40)  # Dark yellow for highlighted search rows

    font = pygame.font.SysFont("consolas", 18)
    title_font = pygame.font.SysFont("consolas", 36, bold=True)
    header_font = pygame.font.SysFont("consolas", 20, bold=True)
    small_font = pygame.font.SysFont("consolas", 14)

    scroll_y = 0
    row_height = 35
    header_height = 80  # Taller for the big logo

    # Layout Calculations
    col_1_x = 50
    col_2_x = WINDOW_WIDTH // 2

    # Search Bar State
    search_text = ""
    search_active = False
    search_rect = pygame.Rect(WINDOW_WIDTH - 300, 25, 250, 30)
    # add these near ac_modal = None and cc_modal = None
    # autoclient / right-click / filter state
    ctx_menu = None  # {"pos":(x,y), "items":[(label,enabled),...], "target":name}
    ac_modal = None  # create/edit autoclient form (see AC_FIELDS)
    cc_modal = None  # create/edit COM client form (see CC_FIELDS)
    cc_dropdown = None  # which dropdown is open: 'port' | 'baud' | None


    running = True

    while running:
        text_changed_this_frame = False

        # 1. Handle Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button in (1, 3):  # Left or right click
                    # Toggle search focus based on click position
                    search_active = search_rect.collidepoint(event.pos)
                elif event.button == 4:  # Scroll up
                    scroll_y += 25
                elif event.button == 5:  # Scroll down
                    scroll_y -= 25
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif search_active:
                    if event.key == pygame.K_RETURN:
                        text_changed_this_frame = True  # Still allows pressing Enter to force a re-jump
                    elif event.key == pygame.K_BACKSPACE:
                        search_text = search_text[:-1]
                        text_changed_this_frame = True
                    else:
                        search_text += event.unicode
                        text_changed_this_frame = True
            elif event.type == pygame.VIDEORESIZE:
                WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
                screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                col_2_x = WINDOW_WIDTH // 2
                search_rect.x = WINDOW_WIDTH - 300  # Keep anchored to the right

        # 2. Fetch Data Directly
        current_data = _read_all()
        items = sorted(current_data.items())

        # Auto-scroll instantly as the user types
        if text_changed_this_frame and search_text:
            for idx, (k, v) in enumerate(items):
                if search_text.lower() in str(k).lower() or search_text.lower() in str(v).lower():
                    target_y = idx * row_height
                    scroll_y = -target_y + (WINDOW_HEIGHT // 3)
                    break

        # Clamp Scrolling
        total_content_height = len(items) * row_height
        max_scroll = min(0, WINDOW_HEIGHT - header_height - total_content_height - 50)

        if scroll_y > 0:
            scroll_y = 0
        elif scroll_y < max_scroll:
            scroll_y = max_scroll

        # 3. Draw Background
        screen.fill(BG_COLOR)

        # 4. Draw Rows
        y_offset = header_height + scroll_y + 40  # Added gap for table header

        for i, (key, val) in enumerate(items):
            if y_offset + row_height > header_height and y_offset < WINDOW_HEIGHT:

                # Highlight logic for search matching
                is_match = False
                if search_text and (search_text.lower() in str(key).lower() or search_text.lower() in str(val).lower()):
                    rect_color = MATCH_COLOR
                    is_match = True
                else:
                    rect_color = ROW_COLOR_1 if i % 2 == 0 else ROW_COLOR_2

                pygame.draw.rect(screen, rect_color, (0, y_offset, WINDOW_WIDTH, row_height))

                pygame.draw.line(screen, GRID_COLOR, (0, y_offset), (WINDOW_WIDTH, y_offset))
                pygame.draw.line(screen, GRID_COLOR, (col_2_x - 20, y_offset), (col_2_x - 20, y_offset + row_height))

                # If matching, force text to be white for contrast, otherwise use standard coloring
                key_color = (255, 255, 255) if is_match else TEXT_COLOR
                key_surface = font.render(str(key), True, key_color)

                # Highlight strings differently from numbers
                if isinstance(val, float):
                    val_str = f"{val:.5f}"
                    val_color = (255, 255, 255) if is_match else HIGHLIGHT_COLOR
                elif isinstance(val, str):
                    val_str = f'"{val}"'
                    val_color = (255, 255, 255) if is_match else (180, 200, 255)
                else:
                    val_str = str(val)
                    val_color = (255, 255, 255) if is_match else HIGHLIGHT_COLOR

                val_surface = font.render(val_str, True, val_color)

                screen.blit(key_surface, (col_1_x, y_offset + (row_height - key_surface.get_height()) // 2))
                screen.blit(val_surface, (col_2_x, y_offset + (row_height - val_surface.get_height()) // 2))

            y_offset += row_height

        # 5. Draw Top Dashboard Header (Stays Fixed)
        pygame.draw.rect(screen, HEADER_COLOR, (0, 0, WINDOW_WIDTH, header_height))
        pygame.draw.line(screen, HIGHLIGHT_COLOR, (0, header_height), (WINDOW_WIDTH, header_height), 3)

        # Draw Logo and Title
        draw_logo(screen, 60, header_height // 2)
        title_surf = title_font.render("ignoAPI", True, (255, 255, 255))
        screen.blit(title_surf, (110, (header_height - title_surf.get_height()) // 2))

        # --- Draw Search Bar ---
        # Search Box Outline Color
        box_color = HIGHLIGHT_COLOR if search_active else (100, 100, 100)
        pygame.draw.rect(screen, (30, 30, 30), search_rect)
        pygame.draw.rect(screen, box_color, search_rect, 2)

        # Blinking cursor effect
        cursor = "|" if search_active and time.time() % 1 > 0.5 else ""
        search_surf = font.render(search_text + cursor, True, (255, 255, 255))

        # Clip text if it gets too long for the box
        screen.set_clip(search_rect)
        screen.blit(search_surf,
                    (search_rect.x + 10, search_rect.y + (search_rect.height - search_surf.get_height()) // 2))
        screen.set_clip(None)

        # Search Label updated
        lbl_surf = small_font.render("Live Search:", True, TEXT_COLOR)
        screen.blit(lbl_surf, (search_rect.x - lbl_surf.get_width() - 10,
                               search_rect.y + (search_rect.height - lbl_surf.get_height()) // 2))
        # -----------------------

        # Status & Instructions
        status_text = f"HOST: {HOST}:{PORT} | ESC: QUIT"
        status_surf = small_font.render(status_text, True, HIGHLIGHT_COLOR)
        screen.blit(status_surf, (search_rect.x - lbl_surf.get_width() - status_surf.get_width() - 40,
                                  (header_height - status_surf.get_height()) // 2))

        # Draw Table Sub-Header
        table_header_y = header_height
        pygame.draw.rect(screen, (30, 30, 30), (0, table_header_y, WINDOW_WIDTH, 40))
        pygame.draw.line(screen, GRID_COLOR, (0, table_header_y + 40), (WINDOW_WIDTH, table_header_y + 40))
        pygame.draw.line(screen, GRID_COLOR, (col_2_x - 20, table_header_y), (col_2_x - 20, table_header_y + 40))

        h_key = header_font.render("Variable Name", True, (180, 180, 180))
        h_val = header_font.render("Current Value", True, (180, 180, 180))
        screen.blit(h_key, (col_1_x, table_header_y + (40 - h_key.get_height()) // 2))
        screen.blit(h_val, (col_2_x, table_header_y + (40 - h_val.get_height()) // 2))

        # 6. Update Display
        pygame.display.flip()
        clock.tick(30)

    # Teardown
    print("\n[ignoAPI] Shutting down visualizer and server...")
    _flush_to_disk()
    pygame.quit()
    sys.exit()


# Context-menu geometry. These live here as constants because the menu is
# built in one place, hit-tested in a second and drawn in a third; when the
# sizes were literals in all three, changing one silently misaligned the
# clickable area from the thing the user can see.
CTX_MENU_W = 200
CTX_ITEM_H = 28


_NET_FONTS = {}


def _net_font(size, bold=False):
    """A cached font at an arbitrary size.

    The panel scales, so its text has to scale with it -- and building a font
    object per string per frame would cost more than everything else the
    window does put together.
    """
    key = (max(8, int(size)), bool(bold))
    f = _NET_FONTS.get(key)
    if f is None:
        f = pygame.font.SysFont("consolas", key[0], bold=key[1])
        _NET_FONTS[key] = f
    return f


# ──────────────────────────────────────────────────────────────
# TEXT BOXES
#   Every field in this window goes through ONE editor, so a caret, a
#   selection, ctrl+A/C/X/V, ctrl+Z, word jumps, Home/End and click-to-position
#   work the same everywhere. Before this each field appended to the end and
#   backspaced from it, so fixing a character in the middle of an address
#   meant deleting back to it.
#
#   The editors live in one dict keyed by (owner, field). The owner is the
#   modal (or "search" / "row" / "add"), so two forms open at once cannot
#   share a caret, and closing a form does not leak its state into the next.
# ──────────────────────────────────────────────────────────────
_editors = {}

# Fields that hold a LIST rather than one value. Double-clicking one opens the
# editor that shows a line per entry, because a dozen addresses in a
# single-line box is a box you cannot read.
LIST_FIELDS = ("server_ip", "mac", "share_with", "macs", "hosts", "robots")

# Fields that are a SWITCH, not a box: they have two legal values and clicking
# or pressing a key flips them. They must never reach the editor, or typing "t"
# into one would put a "t" where a "true"/"false" is expected.
AC_TOGGLE_FIELDS = ("runatstartup", "mode", "read_only", "topology", "use_tls", "subscribe_visualization", "store_raw")
CC_TOGGLE_FIELDS = ("runatstartup", "persist_csv")


def tb(owner, field, text="", multiline=False):
    """The editor for one box, created on first use and kept in step.

    `text` is the value the CALLER holds. It is pushed in whenever it differs
    from what the editor last produced, so a value changed elsewhere -- loaded
    from a config, picked from a dialog -- appears in the box without the
    caret jumping while somebody is typing.
    """
    key = (owner, field)
    ed = _editors.get(key)
    if ed is None:
        ed = ignotext.Editor(text, multiline=multiline)
        _editors[key] = ed
    elif str(text) != ed.text:
        ed.set_text(text, keep_caret=True)
    return ed


def tb_forget(owner):
    """Drop a form's editors when it closes."""
    for k in [k for k in _editors if k[0] == owner]:
        _editors.pop(k, None)


def tb_key(ed, event):
    """Feed a pygame KEYDOWN to an editor. True if it consumed the key."""
    mods = pygame.key.get_mods()
    return ed.key(event.key, event.unicode,
                  ctrl=bool(mods & pygame.KMOD_CTRL),
                  shift=bool(mods & pygame.KMOD_SHIFT),
                  clip_get=clipboard_get, clip_set=clipboard_set,
                  K=pygame)


def tb_click(ed, font, rect, mx, scroll=0):
    """Put the caret where the click landed."""
    ed.caret = ed.index_at_x(lambda t: font.size(t)[0], mx - rect.x - 6 - scroll)
    ed.sel = None
    return ed.caret


def tb_draw(screen, font, ed, rect, focused, scroll=0,
            text_col=(235, 240, 255), sel_col=(40, 80, 140)):
    """Draw the text, the selection and the caret. Returns the scroll to keep.

    The scroll follows the CARET rather than the end of the text: typing in
    the middle of a long address has to keep the caret visible, and an
    end-anchored view scrolls away from where you are working.
    """
    measure = lambda t: font.size(t)[0]
    caret_px = ed.caret_x(measure)
    inner = rect.width - 12
    scroll = min(0, scroll)
    if focused:
        # An unfocused box has no caret to follow, so it stays at the start
        # of its value -- which is the part worth reading in a list of fields.
        if caret_px + scroll > inner:
            scroll = inner - caret_px
        if caret_px + scroll < 0:
            scroll = -caret_px
    else:
        scroll = 0
    screen.set_clip(rect)
    r = ed.sel_range()
    if r and focused:
        x0 = measure(ed.text[:r[0]]) + rect.x + 6 + scroll
        x1 = measure(ed.text[:r[1]]) + rect.x + 6 + scroll
        pygame.draw.rect(screen, sel_col,
                         (x0, rect.y + 3, max(1, x1 - x0), rect.height - 6))
    surf = font.render(ed.text, True, text_col)
    screen.blit(surf, (rect.x + 6 + scroll,
                       rect.y + (rect.height - surf.get_height()) // 2))
    if focused and time.time() % 1 > 0.5:
        cx = rect.x + 6 + scroll + caret_px
        pygame.draw.line(screen, text_col, (cx, rect.y + 4),
                         (cx, rect.bottom - 4), 2)
    screen.set_clip(None)
    return scroll


def tb_line_starts(text):
    """Character index each line begins at."""
    out, pos = [], 0
    for ln in text.split("\n"):
        out.append(pos)
        pos += len(ln) + 1
    return out


def tb_num_width(font):
    """Width of the line-number gutter in the list editor."""
    return font.size("9999 ")[0]


def tb_draw_lines(screen, font, ed, rect, top=0, focused=True,
                  text_col=(235, 240, 255), sel_col=(40, 80, 140),
                  num_col=(110, 120, 140)):
    """Draw a multi-line editor -- one entry per numbered row.

    Returns the first visible line, moved if it has to be so that the caret
    stays on screen: an editor that scrolls away from the line you are typing
    on is worse than no scrolling at all.
    """
    lh = font.get_linesize()
    rows = max(1, rect.height // lh)
    lines = ed.text.split("\n")
    starts = tb_line_starts(ed.text)
    cl = ed.text[:ed.caret].count("\n")
    top = max(0, min(int(top), max(0, len(lines) - rows)))
    if cl < top:
        top = cl
    elif cl >= top + rows:
        top = cl - rows + 1
    numw = tb_num_width(font)
    r = ed.sel_range()
    screen.set_clip(rect)
    for i in range(top, min(len(lines), top + rows)):
        y = rect.y + (i - top) * lh
        ns = font.render(str(i + 1), True, num_col)
        screen.blit(ns, (rect.x + numw - 10 - ns.get_width(), y))
        x0 = rect.x + numw
        if r:
            a = max(r[0], starts[i]) - starts[i]
            b = min(r[1], starts[i] + len(lines[i])) - starts[i]
            if b > a:
                sx = x0 + font.size(lines[i][:a])[0]
                sw = font.size(lines[i][a:b])[0]
                pygame.draw.rect(screen, sel_col, (sx, y, max(1, sw), lh))
        screen.blit(font.render(lines[i], True, text_col), (x0, y))
        if focused and i == cl and time.time() % 1 > 0.5:
            cx = x0 + font.size(lines[i][:ed.caret - starts[i]])[0]
            pygame.draw.line(screen, text_col, (cx, y + 1), (cx, y + lh - 2), 2)
    screen.set_clip(None)
    return top


def tb_click_lines(ed, font, rect, mx, my, top=0):
    """Put the caret where a click landed in a multi-line box."""
    lh = font.get_linesize()
    lines = ed.text.split("\n")
    starts = tb_line_starts(ed.text)
    i = max(0, min(len(lines) - 1, int(top) + (my - rect.y) // lh))
    ed.caret = ed.index_at_x(lambda t: font.size(t)[0],
                             mx - rect.x - tb_num_width(font),
                             line_start=starts[i],
                             line_end=starts[i] + len(lines[i]))
    ed.sel = None
    return ed.caret


def list_save(lm, ac_modal=None, net_modal=None, cc_modal=None):
    """Fold the list editor's lines back into the field that opened it.

    Returns None so the caller can write `list_modal = list_save(...)` and
    have the editor close in the same breath.
    """
    if not lm:
        return None
    if lm.get("owner") == "exec":
        # Straight into the variable, not into a form: the EXEC row IS the
        # field, so there is no modal underneath to fold it back into.
        paths = [ln.strip() for ln in str(lm.get("text", "")).splitlines()
                 if ln.strip()]
        _create_or_write(lm["field"], format_exec_list(paths))
        print(f"[ignoAPI] exec list now has {len(paths)} application(s)")
        tb_forget("list")
        return None
    owner = {"ac": ac_modal, "net": net_modal, "cc": cc_modal}.get(lm.get("owner"))
    if owner is not None:
        owner["fields"][lm["field"]] = ignotext.from_lines(lm.get("text", ""))
    tb_forget("list")
    return None


def ctx_menu_place(mx, my, n_items, win_w, win_h):
    """Top-left corner for a context menu opened at the cursor.

    The menu used to always grow DOWNWARD from the click, so right-clicking a
    row near the bottom of the window pushed most of the items past the edge
    of the screen -- on the last row, every item. Real menus flip up when they
    do not fit below, and that is what this does: try below the cursor first,
    and if the whole menu does not fit there, hang it ABOVE the cursor
    instead. Only if it fits in neither direction (a menu taller than the
    window) does it fall back to clamping, which at least keeps the top items
    reachable.
    """
    h = n_items * CTX_ITEM_H
    x = max(0, min(mx, win_w - CTX_MENU_W))

    if my + h <= win_h:
        y = my                     # normal case: below the cursor
    elif my - h >= 0:
        y = my - h                 # flip up: the menu ends at the cursor
    else:
        y = max(0, win_h - h)      # taller than the window; show what we can
    return (x, y)


def _cc_modal_actions(kind):
    """(cast, create, edit) for the serial modal's three kinds.

    One lookup rather than a chain of conditionals at each of the two save
    sites (mouse and Enter): with three kinds the ternaries stopped being
    readable, and the two sites had to be kept in step by hand.
    """
    if kind == "modbusslave":
        return ms_cast_fields, modbusslave_create, modbusslave_edit
    if kind == "modbus":
        return mm_cast_fields, modbusmaster_create, modbusmaster_edit
    return cc_cast_fields, comclient_create, comclient_edit


def _ac_modal_actions(kind):
    """(cast, create, edit) for the autoclient-shaped modal's two kinds.

    One lookup rather than a conditional at each of the two save sites (mouse
    and Enter) -- the pair has to stay in step, and a chain of ternaries in
    two places is how they stop being in step.
    """
    if kind == "sync":
        return sy_cast_fields, syncpeer_create, syncpeer_edit
    if kind == "ftp":
        return ft_cast_fields, ftpserver_create, ftpserver_edit
    if kind == "vda":
        return vd_cast_fields, vdabridge_create, vdabridge_edit
    return ac_cast_fields, autoclient_create, autoclient_edit


AC_FIELD_DEFS = [("server_ip", "Server IP"), ("mac", "MAC (optional)"),
                 ("port", "Port"), ("command", "Command"),
                 ("poll_interval_sec", "Poll interval (s)"),
                 ("connect_timeout_sec", "Connect timeout (s)"),
                 ("read_timeout_sec", "Read timeout (s)"),
                 ("log_file", "Log file"), ("runatstartup", "Run at startup")]

# `mode` and `runatstartup` are CLICK-TO-TOGGLE, not text: mode has exactly
# two legal values, and a typed field would accept "0x03" and then silently
# fall back to level.
SY_FIELD_DEFS = [("server_ip", "Peer IP(s), comma separated"),
                 ("mac", "MAC(s), one per peer"),
                 ("port", "Peer port"),
                 ("remote_var", "Their variable (blank = same)"),
                 ("mode", "Mode"), ("topology", "Topology"),
                 ("pulse_ms", "Pulse length (ms)"),
                 ("poll_interval_sec", "Poll interval (s)"),
                 ("connect_timeout_sec", "Connect timeout (s)"),
                 ("read_timeout_sec", "Read timeout (s)"),
                 ("log_file", "Log file"), ("runatstartup", "Run at startup")]


# `read_only` and `runatstartup` are click-to-toggle; `folder` gets a Browse
# button beside it, because typing a path by hand is how you end up sharing
# the wrong directory.
FT_FIELD_DEFS = [("folder", "Folder to share"), ("port", "Port"),
                 ("username", "Username (blank = anonymous)"),
                 ("password", "Password"),
                 ("read_only", "Read only"),
                 ("share_with", "Share with (host or host:port, comma sep)"),
                 ("log_file", "Log file"),
                 ("runatstartup", "Run at startup")]

VD_FIELD_DEFS = [("broker_host", "Broker host/IP"),
                 ("broker_port", "Broker port"),
                 ("robots", "Robots (id:mfr:serial, comma sep)"),
                 ("username", "Username (blank = anonymous)"),
                 ("password", "Password"),
                 ("use_tls", "Use TLS"),
                 ("client_id", "Client ID (blank = auto)"),
                 ("interface", "Interface (default uagv)"),
                 ("vda_major", "VDA major (default v2)"),
                 ("protocol_version", "Protocol version (2.0.0)"),
                 ("qos_order", "QoS Order"),
                 ("qos_state", "QoS State"),
                 ("stale_after_sec", "Stale timeout (s)"),
                 ("node_map_csv", "Node map CSV path"),
                 ("subscribe_visualization", "Visualization"),
                 ("store_raw", "Store raw JSON rows"),
                 ("log_file", "Log file"),
                 ("runatstartup", "Run at startup")]


def ac_field_defs_for(kind):
    if kind == "sync":
        return SY_FIELD_DEFS
    if kind == "ftp":
        return FT_FIELD_DEFS
    if kind == "vda":
        return VD_FIELD_DEFS
    return AC_FIELD_DEFS


def modal_layout(field_defs, modal, win_w, win_h, top_limit,
                 extra_rows=0, base_w=560):
    """Geometry for a create/edit modal: ratio-sized, draggable, always on screen.

    Two problems this solves.

    SIZE -- the panel used to be a fixed 560x(90+40*n). On a 5" screen that is
    taller than the display, so the Save/Cancel buttons sat below the bottom
    edge and could not be reached at all. Everything is now derived from the
    window, and if the rows still do not fit the ROW PITCH is squeezed until
    they do. The footer is reserved first, so the buttons are the one thing
    that can never be pushed off.

    POSITION -- the panel was rebuilt centred on every frame, so dragging it
    snapped straight back. The dragged position lives in modal["pos"] and is
    only defaulted when the modal is first opened; it is re-clamped each frame
    so a window resize cannot strand it off-screen.

    Returns (panel, field_rects, ok_rect, cancel_rect, metrics).
    """
    ms = max(0.55, min(1.0, min(win_w / 900.0, win_h / 720.0)))

    head = max(40, int(70 * ms))       # title bar (also the drag handle)
    foot = max(38, int(56 * ms))       # Save / Cancel row
    fh = max(18, int(30 * ms))         # field height
    pitch = max(22, int(40 * ms))      # row pitch
    labw = max(96, int(210 * ms))      # label column width
    padr = max(60, int(110 * ms))      # right padding (room for side buttons)

    n = max(1, len(field_defs) + extra_rows)
    pw = int(min(base_w * ms, win_w - 20))
    avail_h = win_h - 12               # a modal may cover the header; it is modal
    ph = head + n * pitch + foot
    if ph > avail_h:
        # Squeeze the rows, never the footer -- the buttons must stay reachable.
        pitch = max(16, (avail_h - head - foot) // n)
        fh = max(14, min(fh, pitch - 4))
        ph = head + n * pitch + foot

    if modal.get("pos") is None:
        modal["pos"] = ((win_w - pw) // 2, max(top_limit, (win_h - ph) // 2))
    px, py = modal["pos"]
    px = max(0, min(int(px), win_w - pw))          # keep it fully on screen
    py = max(0, min(int(py), win_h - ph))
    modal["pos"] = (px, py)

    panel = pygame.Rect(px, py, pw, ph)
    rects = {}
    fy0 = panel.y + head
    for i, (fk, _lbl) in enumerate(field_defs):
        rects[fk] = pygame.Rect(panel.x + labw, fy0 + i * pitch,
                                max(60, pw - labw - padr), fh)
    bw = max(64, int(90 * ms))
    bh = max(24, int(32 * ms))
    ok = pygame.Rect(panel.right - 2 * bw - 20, panel.bottom - bh - 10, bw, bh)
    cancel = pygame.Rect(panel.right - bw - 10, panel.bottom - bh - 10, bw, bh)
    metrics = {"ms": ms, "head": head, "pitch": pitch, "fh": fh,
               "labw": labw, "bw": bw, "bh": bh}
    return panel, rects, ok, cancel, metrics


def run_visualizer():
    pygame.init()

    # ── Window icon from ignoAPI.png ─────────────────────────────────────
    try:
        icon_path = os.path.join(SCRIPT_DIR, "ignoAPI.png")
        icon_img  = pygame.image.load(icon_path)
        pygame.display.set_icon(icon_img)
    except Exception:
        pass

    # ── Start maximized at full screen resolution ────────────────────────
    info = pygame.display.Info()
    WINDOW_WIDTH  = info.current_w
    WINDOW_HEIGHT = info.current_h
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("ignoAPI Live Dashboard")
    if os.name == 'nt':
        ctypes.windll.user32.ShowWindow(pygame.display.get_wm_info()["window"], 3)  # SW_MAXIMIZE
        WINDOW_WIDTH, WINDOW_HEIGHT = screen.get_size()

    clock = pygame.time.Clock()

    # ── Colors ───────────────────────────────────────────────────────────
    BG_COLOR        = (25, 25, 25)
    HEADER_COLOR    = (40, 40, 40)
    ROW_COLOR_1     = (32, 32, 32)
    ROW_COLOR_2     = (38, 38, 38)
    TEXT_COLOR      = (230, 230, 230)
    HIGHLIGHT_COLOR = (120, 220, 120)
    GRID_COLOR      = (60, 60, 60)
    MATCH_COLOR     = (80, 80, 40)
    TACTICAL_GREEN  = (20, 180, 20)
    EDIT_BG_COLOR   = (20, 60, 100)
    SCROLLBAR_BG    = (35, 35, 35)
    SCROLLBAR_FG    = (90, 90, 90)
    SCROLLBAR_HOVER = (140, 140, 140)

    SCROLLBAR_W = 12   # vertical bar width (right edge)
    SCROLLBAR_H = 12   # horizontal bar height (bottom edge)

    # ── Scale fonts and layout to screen size ────────────────────────────
    def make_fonts(w, h):
        sc = max(0.35, min(w / 1200.0, h / 800.0))
        return (
            pygame.font.SysFont("consolas", max(9,  int(18 * sc))),
            pygame.font.SysFont("consolas", max(14, int(36 * sc)), bold=True),
            pygame.font.SysFont("consolas", max(10, int(20 * sc)), bold=True),
            pygame.font.SysFont("consolas", max(7,  int(14 * sc))),
            sc,
        )

    def make_layout(w, h, sc):
        rh  = max(18, int(35 * sc))
        trh = max(34, int(56 * sc))     # title row: logo + "ignoAPI" text only, no buttons
        brh = max(26, int(44 * sc))     # button row: ADD/HOST/FILTER/SORT/SEARCH/STARTUP/REBOOT
        hh  = trh + brh                 # total header height (both rows)
        ib  = max(22, int(28 * sc))     # info-bar strip below the header buttons
        c1  = max(8,  int(50 * sc))
        c2  = w // 2
        return rh, hh, ib, c1, c2, trh

    def make_header_rects(w, h):
        """All header button rects computed together (not derived ad-hoc from
        one another later) so nothing can silently overlap as buttons are
        added.

        Laid out from BOTH edges inward, not from one fixed offset, so every
        button stays fully on-screen on any monitor/aspect ratio: previously
        ADD/HOST/FILTER were anchored at a hardcoded `w - 1240` from the
        right, which went NEGATIVE (i.e. off the left edge of the window,
        invisible) on any window narrower than ~1240px -- exactly what
        happens on a smaller/secondary monitor. Now:
          - Left cluster (ADD, HOST, FILTER) grows rightward from the left
            margin -- always starts at a small positive x.
          - Right cluster (SEARCH, STARTUP, REBOOT) grows leftward from the
            right margin -- always ends before the right edge.
        Button widths scale with the same `sc` factor as fonts/rows, and are
        squeezed further (proportionally, both widths and gaps) if the two
        clusters would otherwise collide in the middle on a very narrow
        window, so nothing overlaps regardless of resolution.

        Buttons live in their OWN row below the logo/title row (title_row_height)
        -- they used to share the title row, which put ADD/HOST/FILTER/SORT
        directly on top of the logo and "ignoAPI" text."""
        btn_row_h = header_height - title_row_height
        btn_h  = min(30, max(18, btn_row_h - 8))
        btn_y  = title_row_height + max(2, (btn_row_h - btn_h) // 2)
        margin = max(8, int(20 * _scale))
        gap    = max(6, int(10 * _scale))

        w_add, w_host, w_filter, w_sort = int(110 * _scale), int(190 * _scale), int(150 * _scale), int(170 * _scale)
        w_search, w_startup, w_rr       = int(200 * _scale), int(160 * _scale), int(120 * _scale)

        left_total   = w_add + w_host + w_filter + w_sort + 3 * gap
        right_total  = w_search + w_startup + w_rr + 2 * gap
        available    = max(1, w - 2 * margin)
        total_needed = left_total + right_total + gap  # + gap between the two clusters

        if total_needed > available:
            squeeze = max(0.45, available / total_needed)
            w_add, w_host, w_filter, w_sort = (int(w_add * squeeze), int(w_host * squeeze),
                                                int(w_filter * squeeze), int(w_sort * squeeze))
            w_search, w_startup, w_rr = int(w_search * squeeze), int(w_startup * squeeze), int(w_rr * squeeze)
            gap = max(3, int(gap * squeeze))

        ad = pygame.Rect(margin, btn_y, w_add, btn_h)
        ho = pygame.Rect(ad.right + gap, btn_y, w_host, btn_h)
        fi = pygame.Rect(ho.right + gap, btn_y, w_filter, btn_h)
        so = pygame.Rect(fi.right + gap, btn_y, w_sort, btn_h)

        rr = pygame.Rect(w - margin - w_rr, btn_y, w_rr, btn_h)
        su = pygame.Rect(rr.left - gap - w_startup, btn_y, w_startup, btn_h)
        sr = pygame.Rect(su.left - gap - w_search, btn_y, w_search, btn_h)

        return sr, su, rr, ad, ho, fi, so

    font, title_font, header_font, small_font, _scale = make_fonts(WINDOW_WIDTH, WINDOW_HEIGHT)
    row_height, header_height, info_bar_height, col_1_x, col_2_x, title_row_height = make_layout(WINDOW_WIDTH, WINDOW_HEIGHT, _scale)
    search_rect, startup_rect, restart_rect, add_rect, host_rect, filter_rect, sort_rect = make_header_rects(WINDOW_WIDTH, WINDOW_HEIGHT)

    # ── System tray ─────────────────────────────────────────────────────
    def _tray_image():
        """The real ignoAPI.ico if we can find it, else a drawn placeholder.

        The tray used to ALWAYS draw the placeholder -- a grey ring with a
        green dot -- even though ignoAPI.ico sits right next to the exe and is
        already the window/taskbar icon. The tray is where you look to find a
        background app, so it should show the same mark as everything else.
        """
        for cand in (os.path.join(SCRIPT_DIR, "ignoAPI.ico"),
                     os.path.join(getattr(sys, "_MEIPASS", SCRIPT_DIR), "ignoAPI.ico")):
            try:
                if os.path.exists(cand):
                    return Image.open(cand)
            except Exception as e:
                print(f"[tray] could not load {cand}: {e}")
        # Fallback so a missing icon can never stop the tray from appearing.
        img = Image.new('RGB', (64, 64), color=(25, 25, 25))
        d = ImageDraw.Draw(img)
        d.ellipse((16, 16, 48, 48), outline=(150, 150, 150), width=4)
        d.ellipse((26, 26, 38, 38), fill=(100, 200, 100))
        return img

    def setup_tray_icon():
        image = _tray_image()

        def on_show(icon, item):
            if os.name == 'nt':
                ctypes.windll.user32.ShowWindow(pygame.display.get_wm_info()["window"], 9)

        def on_quit(icon, item):
            icon.stop()
            os._exit(0)

        menu = pystray.Menu(
            pystray.MenuItem("Show Dashboard", on_show, default=True),
            pystray.MenuItem("Restart Server", lambda icon, item: restart_application()),
            pystray.MenuItem("Shutdown", on_quit),
        )
        pystray.Icon("ignoAPI", image, "ignoAPI Server", menu).run()

    threading.Thread(target=setup_tray_icon, daemon=True).start()

    # ── Startup registry sync ────────────────────────────────────────────
    try:
        startup_enabled = _read("RUN_AT_STARTUP")
    except NameError:
        startup_enabled = False
        _create_or_write("RUN_AT_STARTUP", False)
    toggle_windows_startup(startup_enabled)

    # ADDRESS sits beside RUN_AT_STARTUP and starts EMPTY. Empty means "no
    # name published" -- a default like the Windows hostname would put a name
    # on the network that nobody chose and nobody knows.
    if ADDRESS_VAR not in _variable_store:
        _create_or_write(ADDRESS_VAR, "")
    start_mdns()
    start_discovery()

    # relaunch any autoclients marked run-at-startup
    autoclient_startup_launch_all()

    # Start any COM clients marked run-at-startup. Autodetect is NOT done
    # here any more: probing every port means opening each one and waiting
    # seconds for the board to boot, and doing that here put the whole delay
    # on application startup, before the window was usable. Each child now
    # probes for itself, in parallel, while ignoAPI is already up.
    comclient_startup_launch_all()

    # start any MODBUS masters marked run-at-startup. There is no autodetect
    # step here: a Modbus slave only answers a well-formed request addressed to
    # its own id, so there is no "who is there?" broadcast to sweep with.
    modbusmaster_startup_launch_all()
    modbusslave_startup_launch_all()

    # start any ignoAPI<->ignoAPI syncs marked run-at-startup
    syncpeer_startup_launch_all()
    ftpserver_startup_launch_all()
    vdabridge_startup_launch_all()

    # Checked AFTER the launches, so the warning is the last thing printed and
    # is still on screen rather than scrolled away by startup chatter.
    warn_stale_helpers()

    # ── EXEC supervisor ──────────────────────────────────────────────────
    # Both variables always exist so they are visible and editable straight
    # away; they start EMPTY, so nothing runs until paths are actually added.
    with _store_lock:
        has_exec = any(is_exec_var(k) for k in _variable_store)
        has_flag = any(is_execflag_var(k) for k in _variable_store)
    if not has_exec:
        _create_or_write(EXEC_VAR, "")
    if not has_flag:
        _create_or_write(EXECFLAG_VAR, False)
    exec_startup_launch_all()

    # ── State ────────────────────────────────────────────────────────────
    scroll_y      = 0
    scroll_x      = 0
    search_text   = ""
    search_active = False
    editing_key   = None
    editing_text  = ""
    # Escape with nothing open used to set running = False and the window
    # simply vanished, mid-edit, with no way back. It asks now.
    quit_modal    = None       # {"sel": 0 = close, 1 = stay}
    # The combine selection mode: armed from the right-click menu, then
    # rows are clicked to pick them.
    combine_pick  = None       # {"names": [...], "target": name}

    # add-variable / delete state
    adding        = False
    add_name      = ""
    add_val       = ""
    add_focus     = "name"     # "name" or "value"
    add_scroll    = {}         # how far each add box is scrolled sideways
    add_last_fk   = None       # last add box clicked, for double-click detection
    add_last_t    = 0.0
    edit_scroll   = 0          # ditto for the inline row editor
    row_last_key  = None       # last row value clicked, for double-click
    row_last_t    = 0.0
    search_scroll = 0          # ditto for the search bar
    search_last_t = 0.0        # for double-click in the search bar
    list_modal    = None       # the double-click editor: one address per line
    del_armed     = None       # key awaiting a 2nd click to confirm delete

    # autoclient / right-click / filter state
    ctx_menu      = None       # {"pos":(x,y), "items":[(label,enabled),...], "target":name}
    ac_modal      = None       # create/edit autoclient form (see AC_FIELDS)
    cc_modal      = None       # create/edit COM client form (see CC_FIELDS)
    cc_dropdown   = None       # which dropdown is open: 'port' | 'baud' | None
    # Inbox for the background autodetect thread. A list, not a variable, so
    # the worker can hand the answer back without a nonlocal declaration.
    cc_modal_detect_result = []
    # Same arrangement for the MAC lookup: it now fills the ARP table
    # before reading it, which takes a couple of seconds. On the draw
    # thread that is a frozen window; the worker drops its answer here
    # and a later frame picks it up.
    mac_lookup_result = []
    # Same again for the network scan, which takes seconds.
    net_scan_result = []
    SORT_MODES    = ["name_asc", "name_desc", "date_desc", "date_asc"]
    SORT_LABELS   = {"name_asc": "[SORT:NAME A-Z]", "name_desc": "[SORT:NAME Z-A]",
                     "date_desc": "[SORT:NEWEST]",  "date_asc":  "[SORT:OLDEST]"}
    # VIEW_MODES / VIEW_LABEL / VIEW_COLOUR come from VIEW_DEFS below, which
    # is defined with the palette it references.
    # VIEW and SORT are where you left them, not where the program prefers
    # them. Validated against the known lists rather than trusted: a hand-
    # edited or older prefs file must not leave the table in a state no button
    # can cycle out of.
    _prefs        = load_uiprefs()
    view_filter   = str(_prefs.get("view_filter") or "all")
    sort_mode     = _prefs.get("sort_mode") if _prefs.get("sort_mode") in SORT_MODES else "name_asc"
    link_modal    = None       # {"src": name, "dst": typed, "msg": ...}
    net_modal     = None       # topology view for one sync variable
    AC_BLUE       = (90, 165, 255)   # autoclient variable text/box colour
    AC_BLUE_DIM   = (60, 110, 175)
    EXEC_RED      = (255, 95, 95)    # EXEC / EXECFLAG supervisor rows
    EXEC_RED_DIM  = (170, 60, 60)
    COM_YELLOW    = (255, 225, 40)   # COM (serial) variable rows + their status
    COM_YELLOW_DIM = (170, 150, 25)
    MB_GREEN      = (60, 230, 170)   # MODBUS master rows + their command rows
    MB_GREEN_DIM  = (40, 150, 112)
    SY_VIOLET     = (190, 140, 255)   # SYNC rows (linked to another ignoAPI)
    SY_VIOLET_DIM = (130, 95, 180)
    LINK_CYAN     = (80, 220, 220)   # the link connector + linked names
    LINK_CYAN_DIM = (45, 140, 145)
    CMB_ORANGE    = (255, 165, 70)   # combine command rows + their result
    CMB_ORANGE_DIM = (170, 110, 45)
    FTP_GOLD      = (255, 205, 90)   # FTP server rows + their status
    FTP_GOLD_DIM  = (170, 135, 55)
    VDA_TEAL      = (70, 200, 230)   # VDA 5050 MQTT bridge rows
    VDA_TEAL_DIM  = (40, 130, 150)

    # ── THE VIEW TABLE ───────────────────────────────────────────────
    # Every view is one row here: key, button label, (bright, dim) colour,
    # and the predicate that says which variables belong to it. The cycle
    # order, the label, the button colour, the filtering and the saved
    # preference all read from this list.
    #
    # ADDING A MODULE MEANS ADDING ONE ROW. It used to mean five edits in
    # five places, and the FTP module shipped with no view at all because
    # one of them was missed -- silently, because a missing view looks
    # exactly like a view nobody selected.
    #
    # "all" and "vars" are special: all matches everything, and vars is
    # DERIVED as "claimed by no other view", so a new module leaves the
    # plain-variables list on its own rather than needing to be added to an
    # exclusion list as well.
    VIEW_DEFS = [
        ("all",         "[VIEW:ALL]",     (AC_BLUE, (70, 130, 200)),   None),
        ("vars",        "[VIEW:VARS]",    (AC_BLUE, (70, 130, 200)),   "plain"),
        ("autoclients", "[VIEW:AUTO]",    (AC_BLUE, AC_BLUE_DIM),      is_autoclient),
        ("exec",        "[VIEW:EXEC]",    (EXEC_RED, EXEC_RED_DIM),    is_exec_row),
        ("com",         "[VIEW:SERIAL]",  (COM_YELLOW, COM_YELLOW_DIM), is_com_row),
        ("modbus",      "[VIEW:MODBUS]",  (MB_GREEN, MB_GREEN_DIM),
         lambda k: is_modbus_row(k) or is_modbusslave_row(k)),
        ("sync",        "[VIEW:SYNC]",    (SY_VIOLET, SY_VIOLET_DIM),  is_sync_row),
        ("combine",     "[VIEW:COMBINE]", (CMB_ORANGE, CMB_ORANGE_DIM), is_combine_row),
        ("ftp",         "[VIEW:FTP]",     (FTP_GOLD, FTP_GOLD_DIM),    is_ftp_row),
        ("vda",         "[VIEW:VDA]",     (VDA_TEAL, VDA_TEAL_DIM),    is_vda_row),
    ]
    VIEW_MODES = [v[0] for v in VIEW_DEFS]
    VIEW_LABEL = {v[0]: v[1] for v in VIEW_DEFS}
    VIEW_COLOUR = {v[0]: v[2] for v in VIEW_DEFS}
    VIEW_MATCH = {v[0]: v[3] for v in VIEW_DEFS}
    # Everything that belongs to SOME module: what VARS excludes.
    VIEW_CLAIMED = [v[3] for v in VIEW_DEFS if callable(v[3])]
    if view_filter not in VIEW_MODES:
        # A hand-edited or older prefs file must not leave the table in a
        # state no button can cycle out of.
        view_filter = "all"

    def view_keeps(mode, key):
        """Does row `key` belong in view `mode`?"""
        m = VIEW_MATCH.get(mode)
        if m is None:                     # "all"
            return True
        if m == "plain":
            return not any(f(key) for f in VIEW_CLAIMED)
        try:
            return bool(m(key))
        except Exception:
            return False

    dragging_vbar = False
    dragging_hbar = False
    drag_origin   = (0, 0)
    drag_scroll   = (0, 0)
    # ADD MISSING MODAL VARIABLES HERE:
    dragging_modal = None
    modal_drag_offset = (0, 0)
    field_scroll = {}

    running = True
    running = True

    while running:
        text_changed = False
        current_data = _read_all()
        note_ftp_links(current_data)
        # sort view: alphabetical (A-Z / Z-A) or by creation date (newest / oldest first)
        if sort_mode == "name_asc":
            items = sorted(current_data.items(), key=lambda kv: kv[0].lower())
        elif sort_mode == "name_desc":
            items = sorted(current_data.items(), key=lambda kv: kv[0].lower(), reverse=True)
        elif sort_mode == "date_desc":
            items = sorted(current_data.items(), key=lambda kv: _var_created_at.get(kv[0], 0.0), reverse=True)
        else:  # "date_asc"
            items = sorted(current_data.items(), key=lambda kv: _var_created_at.get(kv[0], 0.0))
        # One filter for every view, driven by VIEW_DEFS. Each view shows a
        # module's rows AND its companions -- the COM status next to its port,
        # the sync _rx/_tx next to their command row -- because a problem and
        # the value it affects belong on the same screen.
        if view_filter != "all":
            items = [it for it in items if view_keeps(view_filter, it[0])]
        # A linked target is pulled up under its source, whatever the sort
        # says. Done AFTER filtering so a hidden source cannot drag a target
        # into a view it was filtered out of.
        # Before the rows are ordered: what counts as a sync row depends on
        # this, and it is computed from the snapshot this frame already holds.
        refresh_remote_syncs(current_data)
        items = order_linked_rows(items)
        mouse_pos    = pygame.mouse.get_pos()

        # host-mode + autoclient status, computed once per frame and reused by
        # both the header buttons and the info bar beneath them
        network_on = bool(current_data.get("API_NETWORK_HOST", False))
        n_live = sum(1 for k in current_data if is_autoclient(k) and autoclient_is_live(k))
        n_ac   = sum(1 for k in current_data if is_autoclient(k))

        # ── Compute content and scroll limits ────────────────────────────
        table_top = header_height + info_bar_height + 40
        table_w   = WINDOW_WIDTH  - SCROLLBAR_W
        table_h   = WINDOW_HEIGHT - table_top - SCROLLBAR_H
        total_h   = max(1, len(items) * row_height)

        max_key_px = max((font.size(str(k))[0] for k, _ in items), default=0) if items else 0
        max_val_px = max((font.size(str(v))[0] for _, v in items), default=0) if items else 0
        content_w  = col_1_x + max_key_px + (col_2_x - col_1_x) + max_val_px + 40

        max_sy = min(0, table_h - total_h)
        max_sx = min(0, table_w - content_w)
        scroll_y = max(max_sy, min(0, scroll_y))
        scroll_x = max(max_sx, min(0, scroll_x))

        # ── Scrollbar geometry ────────────────────────────────────────────
        vbar_track = pygame.Rect(table_w, table_top, SCROLLBAR_W, table_h)
        if total_h > table_h:
            vthumb_h = max(20, int(vbar_track.height * table_h / total_h))
            vthumb_y = vbar_track.y + int((-scroll_y / total_h) * vbar_track.height)
        else:
            vthumb_h, vthumb_y = vbar_track.height, vbar_track.y
        vbar_thumb = pygame.Rect(vbar_track.x + 2, vthumb_y, SCROLLBAR_W - 4, vthumb_h)

        hbar_track = pygame.Rect(0, WINDOW_HEIGHT - SCROLLBAR_H, table_w, SCROLLBAR_H)
        if content_w > table_w:
            hthumb_w = max(20, int(hbar_track.width * table_w / content_w))
            hthumb_x = hbar_track.x + int((-scroll_x / content_w) * hbar_track.width)
        else:
            hthumb_w, hthumb_x = hbar_track.width, hbar_track.x
        hbar_thumb = pygame.Rect(hthumb_x, hbar_track.y + 2, hthumb_w, SCROLLBAR_H - 4)

        # ── Delete-button width + add-variable panel geometry ─────────────
        del_bw = max(18, min(row_height - 4, 26))
        del_x0 = table_w - del_bw - 6            # left edge of the per-row ✕ button
        ap_w, ap_h = min(520, table_w - 20), 96
        add_panel = pygame.Rect((WINDOW_WIDTH - ap_w) // 2, table_top + 12, ap_w, ap_h)
        fy = add_panel.y + 44
        add_name_rect = pygame.Rect(add_panel.x + 14, fy, int(ap_w * 0.40), 28)
        add_val_rect  = pygame.Rect(add_name_rect.right + 10, fy, int(ap_w * 0.28), 28)
        add_ok_rect   = pygame.Rect(add_panel.right - 128, fy, 56, 28)
        add_cancel_rect = pygame.Rect(add_panel.right - 66, fy, 52, 28)

        # (host_rect / filter_rect now come from make_header_rects, computed
        # together with the other header buttons — see above)

        # ── Autoclient create/edit modal geometry ─────────────────────────
        ac_kind = (ac_modal or {}).get("kind", "autoclient")
        ac_field_defs = ac_field_defs_for(ac_kind)
        (ac_panel, ac_field_rects, ac_ok_rect, ac_cancel_rect,
         ac_m) = modal_layout(ac_field_defs, ac_modal if ac_modal else {},
                              WINDOW_WIDTH, WINDOW_HEIGHT, table_top + 6)
        acp_w, acp_h = ac_panel.width, ac_panel.height
        # The Lookup-IP button only exists when the form HAS a mac field. The
        # autoclient and sync forms do; the FTP form does not, and building
        # this unconditionally crashed the whole window with KeyError: 'mac'
        # the moment the FTP modal opened. Off-screen when there is no field,
        # so every later collidepoint() is simply false.
        if "mac" in ac_field_rects:
            ac_maclookup_rect = pygame.Rect(ac_field_rects["mac"].right + 6,
                                            ac_field_rects["mac"].y,
                                            max(56, int(90 * ac_m["ms"])),
                                            ac_field_rects["mac"].height)
        else:
            ac_maclookup_rect = pygame.Rect(-100, -100, 1, 1)

        # ── Link modal geometry ───────────────────────────────────────────
        # One field. It still goes through modal_layout so it drags, scales and
        # stays on screen like every other panel -- a one-off little box would
        # be the only thing in the window that did none of those.
        lk_field_defs = [("dst", "Push into")]
        (lk_panel, lk_field_rects, lk_ok_rect, lk_cancel_rect,
         lk_m) = modal_layout(lk_field_defs, link_modal if link_modal else {},
                              WINDOW_WIDTH, WINDOW_HEIGHT, table_top + 6,
                              extra_rows=1, base_w=520)

        # ── Network topology geometry ─────────────────────────────────────
        # Sized from the window like the others, but wider and taller: it is a
        # DIAGRAM, and a diagram squeezed into a form-sized panel is unreadable.
        if net_modal is not None:
            # Everything below is derived from ONE scale factor, so the panel
            # is usable on a 5" panel PC and does not look like a postage
            # stamp on a 27" monitor. A fixed inner layout inside a
            # proportional panel is the worst of both: the box grows and the
            # diagram inside it stays the same size.
            _nw = int(max(420, min(WINDOW_WIDTH - 24, WINDOW_WIDTH * 0.86, 1100)))
            _nh = int(max(340, min(WINDOW_HEIGHT - 24, WINDOW_HEIGHT * 0.88, 780)))
            _ns = max(0.55, min(1.30, min(_nw / 900.0, _nh / 620.0)))
            net_m = {
                "s": _ns,
                "head": max(34, int(58 * _ns)),
                "pad": max(10, int(20 * _ns)),
                "fh": max(20, int(28 * _ns)),        # field height
                "bh": max(24, int(32 * _ns)),        # button height
                "bw": max(74, int(110 * _ns)),
                "labw": max(74, int(120 * _ns)),
                "node": max(13, int(26 * _ns)),      # peer circle radius
                "me": max(18, int(34 * _ns)),        # this-machine radius
                "chip": max(18, int(24 * _ns)),
            }
            if net_modal.get("pos") is None:
                net_modal["pos"] = ((WINDOW_WIDTH - _nw) // 2,
                                    max(table_top + 6, (WINDOW_HEIGHT - _nh) // 2))
            # Re-clamped every frame, so resizing the window (or dragging the
            # panel and then resizing) can never strand it off screen.
            _nx = max(0, min(int(net_modal["pos"][0]), WINDOW_WIDTH - _nw))
            _ny = max(0, min(int(net_modal["pos"][1]), WINDOW_HEIGHT - _nh))
            net_modal["pos"] = (_nx, _ny)
            net_panel = pygame.Rect(_nx, _ny, _nw, _nh)

            _bh, _pad, _fh = net_m["bh"], net_m["pad"], net_m["fh"]
            _row_btn = net_panel.bottom - _pad - _bh
            _row_chip = _row_btn - _pad // 2 - net_m["chip"]
            _row_mac = _row_chip - int(_pad * 0.8) - _fh
            _row_ip = _row_mac - int(_pad * 0.5) - _fh
            _fx = net_panel.x + _pad + net_m["labw"]
            _fw = net_panel.right - _pad - _fx
            net_field_rect = pygame.Rect(_fx, _row_ip, _fw, _fh)
            net_mac_rect = pygame.Rect(_fx, _row_mac, _fw, _fh)
            net_ok_rect = pygame.Rect(net_panel.x + _pad, _row_btn, net_m["bw"], _bh)
            net_scan_rect = pygame.Rect(net_ok_rect.right + _pad // 2, _row_btn,
                                        int(net_m["bw"] * 1.4), _bh)
            net_close_rect = pygame.Rect(net_panel.right - _pad - net_m["bw"],
                                         _row_btn, net_m["bw"], _bh)
            net_m["diagram_bottom"] = _row_ip - _pad
            net_found_rects = []
            for _i, _h in enumerate(net_modal.get("found") or []):
                _w = max(int(70 * _ns), int(len(_h) * 7.5 * _ns) + 16)
                _rx = net_panel.x + _pad + net_m["labw"] + (_w + 6) * _i
                if _rx + _w > net_panel.right - _pad:
                    break                       # one row of chips is enough
                net_found_rects.append(
                    pygame.Rect(_rx, _row_chip, _w, net_m["chip"]))
        else:
            net_panel = pygame.Rect(0, 0, 0, 0)
            net_field_rect = net_ok_rect = net_scan_rect = net_close_rect = net_panel
            net_mac_rect = net_panel
            net_found_rects = []
            net_m = {"s": 1.0, "head": 40, "pad": 20, "fh": 28, "bh": 32,
                     "bw": 110, "labw": 120, "node": 26, "me": 34, "chip": 24,
                     "diagram_bottom": 0}

        # ── List editor geometry (opened by double-clicking a list field) ─
        # A dozen addresses on one line is a line you cannot read, so a field
        # that holds a LIST opens here instead, with one entry per row.
        if list_modal is not None:
            _lw = int(max(360, min(WINDOW_WIDTH - 24, WINDOW_WIDTH * 0.62, 760)))
            _lh = int(max(240, min(WINDOW_HEIGHT - 24, WINDOW_HEIGHT * 0.70, 560)))
            if list_modal.get("pos") is None:
                list_modal["pos"] = ((WINDOW_WIDTH - _lw) // 2,
                                     max(table_top + 6,
                                         (WINDOW_HEIGHT - _lh) // 2))
            _lx = max(0, min(int(list_modal["pos"][0]), WINDOW_WIDTH - _lw))
            _ly = max(0, min(int(list_modal["pos"][1]), WINDOW_HEIGHT - _lh))
            list_modal["pos"] = (_lx, _ly)
            ls_panel = pygame.Rect(_lx, _ly, _lw, _lh)
            ls_head = max(34, int(52 * _scale))
            ls_bh = max(24, int(32 * _scale))
            ls_area = pygame.Rect(ls_panel.x + 14, ls_panel.y + ls_head,
                                  ls_panel.width - 28,
                                  ls_panel.height - ls_head - ls_bh - 30)
            ls_ok_rect = pygame.Rect(ls_panel.x + 14,
                                     ls_panel.bottom - ls_bh - 12,
                                     max(70, int(96 * _scale)), ls_bh)
            ls_cancel_rect = pygame.Rect(ls_panel.right - 14 - max(70, int(96 * _scale)),
                                         ls_panel.bottom - ls_bh - 12,
                                         max(70, int(96 * _scale)), ls_bh)
            # Only the EXEC list has anything to browse FOR, so the picker
            # button exists only there -- an empty rect elsewhere can never
            # be hit.
            if list_modal.get("owner") == "exec":
                ls_pick_rect = pygame.Rect(
                    ls_ok_rect.right + 10, ls_ok_rect.y,
                    max(110, int(150 * _scale)), ls_bh)
            else:
                ls_pick_rect = pygame.Rect(0, 0, 0, 0)
        else:
            ls_panel = pygame.Rect(0, 0, 0, 0)
            ls_area = ls_ok_rect = ls_cancel_rect = ls_pick_rect = ls_panel
            ls_head = 0

        # ── COM client create/edit modal geometry ─────────────────────────
        # `port` and `baud` are DROPDOWNS (the whole point of the request), the
        # rest are plain text fields, laid out exactly like the autoclient form.
        # cc_modal serves BOTH serial kinds: kind == "com" (raw serial) and
        # kind == "modbus" (RTU master). Everything that differs is looked up
        # from the kind, so the drag, the ratio sizing, the dropdowns and the
        # keyboard navigation exist in exactly one place.
        cc_kind = (cc_modal or {}).get("kind", "com")
        if cc_kind == "modbusslave":
            cc_field_defs = [("port", "COM port"), ("baud", "Baud rate"),
                             ("parity", "Parity"), ("stopbits", "Stop bits"),
                             ("bytesize", "Data bits"),
                             ("slave_id", "Slave id"),
                             ("timeout_sec", "Timeout (s)"),
                             ("register_map", "Register map"),
                             ("persist_csv", "Save writes to CSV"),
                             ("runatstartup", "Run at startup")]
            cc_drop_fields = ("port", "baud", "parity", "stopbits", "bytesize",
                              "slave_id")
        elif cc_kind == "modbus":
            cc_field_defs = [("port", "COM port"), ("baud", "Baud rate"),
                             ("parity", "Parity"), ("stopbits", "Stop bits"),
                             ("bytesize", "Data bits"),
                             ("timeout_sec", "Response timeout (s)"),
                             ("poll_interval_sec", "Poll interval (s)"),
                             ("log_file", "Log file"),
                             ("runatstartup", "Run at startup")]
            # Every serial parameter is a dropdown here: an RTU link fails
            # SILENTLY on a parity or stop-bit mismatch (it just times out),
            # so the fewer of them can be typo'd, the better.
            cc_drop_fields = ("port", "baud", "parity", "stopbits", "bytesize")
        else:
            cc_field_defs = [("port", "COM port"), ("baud", "Baud rate"),
                             ("probe", "Autodetect cmd"),
                             ("command", "Command"),
                             ("poll_interval_sec", "Poll interval (s)"),
                             ("connect_timeout_sec", "Connect timeout (s)"),
                             ("read_timeout_sec", "Read timeout (s)"),
                             ("log_file", "Log file"), ("runatstartup", "Run at startup")]
            cc_drop_fields = ("port", "baud")
        # extra_rows=1 reserves a line for the hint under the command field, so
        # it cannot be squeezed on top of the next row.
        (cc_panel, cc_field_rects, cc_ok_rect, cc_cancel_rect,
         cc_m) = modal_layout(cc_field_defs, cc_modal if cc_modal else {},
                              WINDOW_WIDTH, WINDOW_HEIGHT, table_top + 6,
                              extra_rows=1)
        ccp_w, ccp_h = cc_panel.width, cc_panel.height
        cc_refresh_rect = pygame.Rect(cc_field_rects["port"].right + 6,
                                      cc_field_rects["port"].y,
                                      max(56, int(90 * cc_m["ms"])),
                                      cc_field_rects["port"].height)
        # No autodetect for Modbus: there is no probe string to send. A slave
        # only answers a well-formed request addressed to ITS id, so "shout and
        # see who says OK" has no equivalent -- you would have to sweep 247 ids
        # across every port. Hence the field, and this button, are COM-only.
        # Browse button for the register map. Same geometry as Rescan/Detect,
        # so the three side buttons line up whichever modal is open.
        if "register_map" in cc_field_rects:
            cc_browse_rect = pygame.Rect(cc_field_rects["register_map"].right + 6,
                                         cc_field_rects["register_map"].y,
                                         max(56, int(90 * cc_m["ms"])),
                                         cc_field_rects["register_map"].height)
        else:
            cc_browse_rect = pygame.Rect(-100, -100, 1, 1)   # never hit
        if "probe" in cc_field_rects:
            cc_detect_rect = pygame.Rect(cc_field_rects["probe"].right + 6,
                                         cc_field_rects["probe"].y,
                                         max(56, int(90 * cc_m["ms"])),
                                         cc_field_rects["probe"].height)
        else:
            cc_detect_rect = pygame.Rect(-100, -100, 1, 1)   # never hit

        def _cc_dropdown_options(which):
            if which == "port":
                opts = list((cc_modal or {}).get("ports") or [])
                return opts or ["(no ports found)"]
            if which == "parity":
                return list(MM_PARITY_CHOICES)
            if which == "stopbits":
                return list(MM_STOPBIT_CHOICES)
            if which == "bytesize":
                return list(MM_BYTESIZE_CHOICES)
            if which == "slave_id":
                return list(MS_SLAVE_ID_CHOICES)
            return list(MM_BAUD_CHOICES if cc_kind == "modbus" else CC_BAUD_CHOICES)

        def _cc_dropdown_rects(which):
            base = cc_field_rects[which]
            _dh = max(16, base.height - 2)      # scales with the modal
            return [pygame.Rect(base.x, base.bottom + 2 + i * _dh, base.width, _dh)
                    for i in range(len(_cc_dropdown_options(which)))]

        # ── Events ───────────────────────────────────────────────────────
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.WINDOWMINIMIZED:
                if os.name == 'nt':
                    ctypes.windll.user32.ShowWindow(pygame.display.get_wm_info()["window"], 0)

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    dragging_vbar = False
                    dragging_hbar = False
                    dragging_modal = None  # Add this to drop the window

            elif event.type == pygame.MOUSEMOTION:
                # Add this to move the modal panels
                # Store the dragged position IN THE MODAL. Moving the rect
                # alone did nothing lasting: the geometry block rebuilds the
                # panel centred on every frame, so the window snapped back the
                # instant you let go (in fact on the very next frame).
                if dragging_modal == "ac" and ac_modal is not None:
                    ac_modal["pos"] = (event.pos[0] - modal_drag_offset[0],
                                       event.pos[1] - modal_drag_offset[1])
                    ac_panel.topleft = ac_modal["pos"]
                elif dragging_modal == "cc" and cc_modal is not None:
                    cc_modal["pos"] = (event.pos[0] - modal_drag_offset[0],
                                       event.pos[1] - modal_drag_offset[1])
                    cc_panel.topleft = cc_modal["pos"]
                elif dragging_modal == "net" and net_modal is not None:
                    net_modal["pos"] = (event.pos[0] - modal_drag_offset[0],
                                        event.pos[1] - modal_drag_offset[1])
                    net_panel.topleft = net_modal["pos"]
                elif dragging_modal == "list" and list_modal is not None:
                    list_modal["pos"] = (event.pos[0] - modal_drag_offset[0],
                                         event.pos[1] - modal_drag_offset[1])
                    ls_panel.topleft = list_modal["pos"]
                if dragging_vbar and total_h > table_h:
                    dy       = event.pos[1] - drag_origin[1]
                    scroll_y = drag_scroll[1] - int(dy * total_h / vbar_track.height)
                if dragging_hbar and content_w > table_w:
                    dx       = event.pos[0] - drag_origin[0]
                    scroll_x = drag_scroll[0] - int(dx * content_w / hbar_track.width)

            elif event.type == pygame.MOUSEBUTTONDOWN:
                mx, my = event.pos
                # Check for modal header clicks to start dragging.
                # The list editor is checked FIRST because it is drawn on top
                # of whichever form opened it -- its header sits over that
                # form's fields, and the one underneath must not take the click.
                if list_modal is not None and pygame.Rect(
                        ls_panel.x, ls_panel.y, ls_panel.width,
                        ls_head).collidepoint(mx, my):
                    dragging_modal = "list"
                    modal_drag_offset = (mx - ls_panel.x, my - ls_panel.y)
                    continue

                if cc_modal is not None and pygame.Rect(
                        cc_panel.x, cc_panel.y, cc_panel.width,
                        cc_m["head"]).collidepoint(mx, my):
                    dragging_modal = "cc"
                    modal_drag_offset = (mx - cc_panel.x, my - cc_panel.y)
                    continue

                if ac_modal is not None and pygame.Rect(
                        ac_panel.x, ac_panel.y, ac_panel.width,
                        ac_m["head"]).collidepoint(mx, my):
                    dragging_modal = "ac"
                    modal_drag_offset = (mx - ac_panel.x, my - ac_panel.y)
                    continue

                if net_modal is not None and pygame.Rect(
                        net_panel.x, net_panel.y, net_panel.width,
                        net_m["head"]).collidepoint(mx, my):
                    dragging_modal = "net"
                    modal_drag_offset = (mx - net_panel.x, my - net_panel.y)
                    continue
                if event.button == 1:
                    # ── List editor intercepts all clicks (it is on top) ────
                    if list_modal is not None:
                        if ls_area.collidepoint(mx, my):
                            _ed = tb("list", "text", list_modal["text"],
                                     multiline=True)
                            _now = time.time()
                            _dbl = _now - list_modal.get("last_t", 0) < 0.4
                            list_modal["last_t"] = _now
                            tb_click_lines(_ed, font, ls_area, mx, my,
                                           list_modal.get("top", 0))
                            if _dbl:
                                _a, _b = _ed.word_at(_ed.caret)
                                _ed.sel, _ed.caret = _a, _b
                        elif ls_pick_rect.collidepoint(mx, my):
                            # Append what the dialog returns, skipping
                            # anything already in the box -- picking the
                            # same file twice should not run it twice.
                            _picked = pick_exe_files()
                            if _picked:
                                _ed = tb("list", "text",
                                         list_modal["text"], multiline=True)
                                _have = [ln.strip() for ln in
                                         _ed.text.splitlines() if ln.strip()]
                                for _p in _picked:
                                    if _p not in _have:
                                        _have.append(_p)
                                list_modal["text"] = "\n".join(_have)
                                _ed.set_text(list_modal["text"])
                        elif ls_ok_rect.collidepoint(mx, my):
                            list_modal = list_save(list_modal, ac_modal,
                                                   net_modal, cc_modal)
                        elif ls_cancel_rect.collidepoint(mx, my):
                            list_modal = None
                            tb_forget("list")
                        elif not ls_panel.collidepoint(mx, my):
                            list_modal = None       # same as Cancel, as elsewhere
                            tb_forget("list")
                        continue

                    # ── COM client create/edit modal intercepts all clicks ──
                    if cc_modal is not None:
                        # An open dropdown eats the click first, otherwise the
                        # field underneath it would take it instead.
                        if cc_dropdown is not None:
                            picked = False
                            for opt, r in zip(_cc_dropdown_options(cc_dropdown),
                                              _cc_dropdown_rects(cc_dropdown)):
                                if r.collidepoint(mx, my):
                                    if not opt.startswith("("):
                                        cc_modal["fields"][cc_dropdown] = opt
                                    picked = True
                                    break
                            cc_dropdown = None
                            if picked:
                                continue
                        hit_field = False
                        for fk, _lbl in cc_field_defs:
                            if cc_field_rects[fk].collidepoint(mx, my):
                                hit_field = True
                                if fk in ("runatstartup", "persist_csv"):
                                    cur = str(cc_modal["fields"].get(fk, "false")).lower() in ("true", "1", "yes", "on")
                                    cc_modal["fields"][fk] = "false" if cur else "true"
                                elif fk in cc_drop_fields:
                                    cc_dropdown = None if cc_dropdown == fk else fk
                                    cc_modal["focus"] = fk
                                else:
                                    cc_modal["focus"] = fk
                                    _ed = tb("cc", fk, cc_modal["fields"].get(fk, ""))
                                    _now = time.time()
                                    _dbl = (cc_modal.get("last_fk") == fk
                                            and _now - cc_modal.get("last_t", 0) < 0.4)
                                    cc_modal["last_fk"], cc_modal["last_t"] = fk, _now
                                    tb_click(_ed, font, cc_field_rects[fk], mx,
                                             field_scroll.get(fk, 0))
                                    if _dbl:
                                        _a, _b = _ed.word_at(_ed.caret)
                                        _ed.sel, _ed.caret = _a, _b
                                break
                        if not hit_field:
                            if cc_browse_rect.collidepoint(mx, my):
                                picked = pick_register_map()
                                if picked:
                                    cc_modal["fields"]["register_map"] = picked
                                    try:
                                        n = len(ms_read_map(picked))
                                        cc_modal["msg"] = f"{n} register(s) in {os.path.basename(picked)}"
                                        cc_modal["msg_is_error"] = False
                                    except Exception as e:
                                        # Say so NOW, in the modal, rather than
                                        # letting a bad CSV become a slave that
                                        # dies the moment it starts.
                                        cc_modal["msg"] = f"{os.path.basename(picked)}: {e}"
                                        cc_modal["msg_is_error"] = True
                            elif cc_detect_rect.collidepoint(mx, my):
                                _probe = (cc_modal["fields"].get("probe") or "").strip()
                                if not _probe:
                                    cc_modal["msg"] = ("Type the command your hardware "
                                                       "answers OK to, e.g. ignocontroller")
                                    cc_modal["msg_is_error"] = True
                                else:
                                    _baud = cc_modal["fields"].get("baud", "115200")
                                    cc_modal["msg"] = f"probing every port at {_baud} baud..."
                                    cc_modal["msg_is_error"] = False
                                    # Probing blocks on each port, so it CANNOT run on
                                    # the draw thread -- the window would freeze for
                                    # seconds. Run it in the background and let the
                                    # modal pick the answer up on a later frame.
                                    def _detect(_p=_probe, _b=_baud):
                                        found, rep = cc_autodetect_port(_p, _b)
                                        for line in rep:
                                            print(f"[ignoAPI] autodetect: {line}")
                                        cc_modal_detect_result.append((found, rep))
                                    cc_modal_detect_result.clear()
                                    threading.Thread(target=_detect, daemon=True).start()
                            elif cc_refresh_rect.collidepoint(mx, my):
                                cc_modal["ports"] = list_com_ports()
                                cc_modal["msg"] = (f"{len(cc_modal['ports'])} port(s) found"
                                                   if cc_modal["ports"] else "No COM ports detected")
                                cc_modal["msg_is_error"] = not cc_modal["ports"]
                            elif cc_ok_rect.collidepoint(mx, my):
                                _cast, _create, _edit = _cc_modal_actions(cc_kind)
                                cfg = _cast(cc_modal["fields"])
                                if cc_modal["mode"] == "create":
                                    ok, err = _create(cc_modal["target"], cfg)
                                    if ok:
                                        cc_modal = None
                                    else:
                                        cc_modal["msg"] = err
                                        cc_modal["msg_is_error"] = True
                                else:
                                    _edit(cc_modal["target"], cfg)
                                    cc_modal = None
                            elif cc_cancel_rect.collidepoint(mx, my):
                                cc_modal = None
                            elif not cc_panel.collidepoint(mx, my):
                                cc_modal = None
                        continue

                    # ── Network topology intercepts all clicks ──────────────
                    if net_modal is not None:
                        tgt = net_modal["target"]
                        if (net_field_rect.collidepoint(mx, my)
                                or net_mac_rect.collidepoint(mx, my)):
                            _nf = ("hosts" if net_field_rect.collidepoint(mx, my)
                                   else "macs")
                            _nr = net_field_rect if _nf == "hosts" else net_mac_rect
                            net_modal["focus"] = _nf
                            _ed = tb("net", _nf, net_modal["fields"].get(_nf, ""))
                            _now = time.time()
                            _dbl = (net_modal.get("last_fk") == _nf
                                    and _now - net_modal.get("last_t", 0) < 0.4)
                            net_modal["last_fk"], net_modal["last_t"] = _nf, _now
                            # The panel scales, so the caret has to be placed
                            # with the SAME font the row is drawn in.
                            tb_click(_ed, _net_font(int(15 * net_m["s"])), _nr, mx,
                                     net_modal.get("scroll", {}).get(_nf, 0))
                            if _dbl:
                                # Both boxes here ARE lists -- of addresses and
                                # of MACs -- so a double-click opens the editor
                                # that shows one per line.
                                list_modal = {
                                    "owner": "net", "field": _nf,
                                    "title": ("Addresses" if _nf == "hosts"
                                              else "MAC addresses"),
                                    "text": ignotext.to_lines(
                                        net_modal["fields"].get(_nf, "")),
                                    "msg": ""}
                        elif net_ok_rect.collidepoint(mx, my):
                            cfg = syncpeer_config(tgt)
                            hosts, notes = sy_norm_hosts(net_modal["fields"]["hosts"])
                            bad = [h for h in hosts if not sy_host_is_usable(h)]
                            if bad:
                                net_modal["msg"] = f"{bad[0]!r} is not a valid address"
                                net_modal["msg_is_error"] = True
                            elif not hosts:
                                net_modal["msg"] = "Enter at least one address"
                                net_modal["msg_is_error"] = True
                            else:
                                # The boxes of a peer being dropped are removed
                                # by syncpeer_edit, which compares what the sync
                                # owned before the save with what it owns after
                                # -- so this does not have to work out which
                                # rows the change orphaned, and cannot get that
                                # list wrong when the rules change again.
                                cfg["server_ip"] = ",".join(hosts)
                                cfg["mac"] = ",".join(
                                    norm_mac(m) if m.strip() else ""
                                    for m in str(net_modal["fields"].get("macs", "")).split(","))
                                syncpeer_edit(tgt, cfg)
                                net_modal["fields"]["hosts"] = ",".join(hosts)
                                net_modal["fields"]["macs"] = cfg["mac"]
                                net_modal["msg"] = (f"saved — {len(hosts)} peer(s), "
                                                    f"reconnecting")
                                net_modal["msg_is_error"] = False
                        elif net_scan_rect.collidepoint(mx, my):
                            net_modal["msg"] = ("scanning both subnets for machines "
                                                "running ignoAPI...")
                            net_modal["msg_is_error"] = False
                            net_modal["found"] = None

                            def _scan(_p=syncpeer_config(tgt).get("port") or PORT):
                                arp_sweep()
                                net_scan_result.append(scan_ignoapi_hosts(_p))
                            net_scan_result.clear()
                            threading.Thread(target=_scan, daemon=True).start()
                        elif any(r.collidepoint(mx, my) for r in net_found_rects):
                            for r, host in zip(net_found_rects,
                                               net_modal.get("found") or []):
                                if r.collidepoint(mx, my):
                                    cur = [h.strip() for h in
                                           str(net_modal["fields"]["hosts"]).split(",")
                                           if h.strip()]
                                    if host in cur:
                                        cur.remove(host)      # click again to drop it
                                    else:
                                        cur.append(host)
                                    net_modal["fields"]["hosts"] = ",".join(cur)
                                    break
                        elif net_close_rect.collidepoint(mx, my):
                            net_modal = None
                        elif not net_panel.collidepoint(mx, my):
                            net_modal = None
                        continue

                    # ── Link modal intercepts all clicks ────────────────────
                    if link_modal is not None:
                        if lk_field_rects["dst"].collidepoint(mx, my):
                            link_modal["focus"] = "dst"
                            _ed = tb("link", "dst",
                                     link_modal["fields"].get("dst", ""))
                            _now = time.time()
                            _dbl = _now - link_modal.get("last_t", 0) < 0.4
                            link_modal["last_t"] = _now
                            tb_click(_ed, font, lk_field_rects["dst"], mx)
                            if _dbl:
                                _a, _b = _ed.word_at(_ed.caret)
                                _ed.sel, _ed.caret = _a, _b
                        elif lk_ok_rect.collidepoint(mx, my):
                            ok, err = link_add(link_modal["src"],
                                               link_modal["fields"].get("dst", ""))
                            if ok:
                                link_modal = None
                                tb_forget("link")
                            else:
                                link_modal["msg"] = err
                                link_modal["msg_is_error"] = True
                        elif lk_cancel_rect.collidepoint(mx, my):
                            link_modal = None
                            tb_forget("link")
                        elif not lk_panel.collidepoint(mx, my):
                            link_modal = None
                            tb_forget("link")
                        continue

                    # ── Autoclient create/edit modal intercepts all clicks ──
                    if ac_modal is not None:
                        hit_field = False
                        for fk, _lbl in ac_field_defs:
                            if ac_field_rects[fk].collidepoint(mx, my):
                                hit_field = True
                                if fk == "runatstartup":
                                    cur = str(ac_modal["fields"].get("runatstartup", "false")).lower() in ("true", "1", "yes", "on")
                                    ac_modal["fields"]["runatstartup"] = "false" if cur else "true"
                                elif fk == "mode":
                                    cur = str(ac_modal["fields"].get("mode", "0x01")).strip().lower()
                                    ac_modal["fields"]["mode"] = "0x01" if cur == "0x02" else "0x02"
                                elif fk == "topology":
                                    cur = str(ac_modal["fields"].get("topology", "star")).strip().lower()
                                    ac_modal["fields"]["topology"] = "star" if cur == "delta" else "delta"
                                elif fk == "read_only":
                                    cur = str(ac_modal["fields"].get("read_only", "false")).lower() in ("true", "1", "yes", "on")
                                    ac_modal["fields"]["read_only"] = "false" if cur else "true"
                                elif fk in ("use_tls", "subscribe_visualization", "store_raw"):
                                    cur = str(ac_modal["fields"].get(fk, "false")).lower() in ("true", "1", "yes", "on")
                                    ac_modal["fields"][fk] = "false" if cur else "true"
                                elif fk == "folder":
                                    picked = pick_folder()
                                    if picked:
                                        ac_modal["fields"]["folder"] = picked
                                    else:
                                        ac_modal["focus"] = fk
                                else:
                                    ac_modal["focus"] = fk
                                    _ed = tb("ac", fk, ac_modal["fields"].get(fk, ""))
                                    # The caret goes WHERE YOU CLICKED, and a double-click
                                    # selects -- a word normally, or the whole list editor
                                    # for a field that holds several addresses.
                                    _now = time.time()
                                    _dbl = (ac_modal.get("last_fk") == fk
                                        and _now - ac_modal.get("last_t", 0) < 0.4)
                                    ac_modal["last_fk"], ac_modal["last_t"] = fk, _now
                                    tb_click(_ed, font, ac_field_rects[fk], mx,
                                         field_scroll.get(fk, 0))
                                    if _dbl:
                                        if fk in LIST_FIELDS:
                                            list_modal = {
                                                "owner": "ac", "field": fk,
                                                "title": dict(ac_field_defs).get(fk, fk),
                                                "text": ignotext.to_lines(
                                                    ac_modal["fields"].get(fk, "")),
                                                "msg": ""}
                                        else:
                                            _a, _b = _ed.word_at(_ed.caret)
                                            _ed.sel, _ed.caret = _a, _b
                                break
                        if not hit_field:
                            if ac_maclookup_rect.collidepoint(mx, my):
                                _mac = ac_modal["fields"].get("mac", "").strip()
                                if not _mac:
                                    ac_modal["msg"] = "Type the MAC first (aa:bb:cc:dd:ee:ff)"
                                    ac_modal["msg_is_error"] = True
                                else:
                                    ac_modal["msg"] = ("searching the network for "
                                                       f"{norm_mac(_mac)}...")
                                    ac_modal["msg_is_error"] = False

                                    def _find(_m=_mac):
                                        mac_lookup_result.append((_m, ip_from_mac(_m)))
                                    mac_lookup_result.clear()
                                    threading.Thread(target=_find, daemon=True).start()
                            elif ac_ok_rect.collidepoint(mx, my):
                                _cast, _create, _edit = _ac_modal_actions(ac_kind)
                                cfg = _cast(ac_modal["fields"])
                                if ac_modal["mode"] == "create":
                                    ok, err = _create(ac_modal["target"], cfg)
                                    if ok:
                                        ac_modal = None
                                    else:
                                        ac_modal["msg"] = err
                                        ac_modal["msg_is_error"] = True
                                else:
                                    _edit(ac_modal["target"], cfg)
                                    ac_modal = None
                            elif ac_cancel_rect.collidepoint(mx, my):
                                ac_modal = None
                            elif not ac_panel.collidepoint(mx, my):
                                ac_modal = None
                        continue

                    # ── Right-click context menu intercepts next ──
                    if ctx_menu is not None:
                        for idx, (label, enabled) in enumerate(ctx_menu["items"]):
                            r = pygame.Rect(ctx_menu["pos"][0],
                                            ctx_menu["pos"][1] + idx * CTX_ITEM_H,
                                            CTX_MENU_W, CTX_ITEM_H)
                            if r.collidepoint(mx, my) and enabled:
                                tgt = ctx_menu["target"]
                                if label == "Create Autoclient":
                                    ac_modal = {"mode": "create", "target": tgt,
                                                "kind": "autoclient",
                                                "fields": ac_default_fields(), "focus": "server_ip", "msg": ""}
                                elif label == "Go to":
                                    open_target(current_data.get(tgt))
                                elif label == "Create FTP Server":
                                    _f = ac_default_fields()
                                    ac_modal = {"mode": "create", "target": tgt,
                                                "kind": "ftp",
                                                "fields": ft_default_fields(),
                                                "focus": "port", "msg": ""}
                                    # Straight into the folder picker: it is
                                    # the one field with no sensible default
                                    # and the one you must not get wrong.
                                    _picked = pick_folder()
                                    if _picked:
                                        ac_modal["fields"]["folder"] = _picked
                                elif label == "Share FTP link":
                                    # The same form, focused on the one field
                                    # this is about -- a separate modal would
                                    # be a second place to keep in step.
                                    ac_modal = {"mode": "edit", "target": tgt,
                                                "kind": "ftp",
                                                "fields": ft_fields_from_config(ftpserver_config(tgt)),
                                                "focus": "share_with", "msg": ""}
                                elif label == "Edit FTP Server":
                                    ac_modal = {"mode": "edit", "target": tgt,
                                                "kind": "ftp",
                                                "fields": ft_fields_from_config(ftpserver_config(tgt)),
                                                "focus": "port", "msg": ""}
                                elif label == "FTP Restart":
                                    ftpserver_reconnect(tgt)
                                elif label == "FTP Stop":
                                    ftpserver_disconnect(tgt)
                                elif label == "Create VDA Bridge":
                                    ac_modal = {"mode": "create", "target": tgt,
                                                "kind": "vda",
                                                "fields": vd_default_fields(),
                                                "focus": "broker_host", "msg": ""}
                                elif label == "Edit VDA Bridge":
                                    ac_modal = {"mode": "edit", "target": tgt,
                                                "kind": "vda",
                                                "fields": vd_fields_from_config(vdabridge_config(tgt)),
                                                "focus": "broker_host", "msg": ""}
                                elif label == "VDA Reconnect":
                                    vdabridge_reconnect(tgt)
                                elif label == "VDA Disconnect":
                                    vdabridge_disconnect(tgt)
                                elif label == "Sync IgnoAPI":
                                    ac_modal = {"mode": "create", "target": tgt,
                                                "kind": "sync",
                                                "fields": sy_default_fields(),
                                                "focus": "server_ip", "msg": ""}
                                elif label == "Edit Sync":
                                    ac_modal = {"mode": "edit", "target": tgt,
                                                "kind": "sync",
                                                "fields": sy_fields_from_config(syncpeer_config(tgt)),
                                                "focus": "server_ip", "msg": ""}
                                elif label == "View Network":
                                    net_modal = {"target": tgt, "msg": "",
                                                 "msg_is_error": False,
                                                 "fields": {"hosts": ",".join(sy_hosts(tgt)),
                                                            "macs": ",".join(sy_macs(tgt))},
                                                 "focus": "hosts"}
                                elif label == "Sync Reconnect":
                                    syncpeer_reconnect(tgt)
                                elif label == "Sync Disconnect":
                                    syncpeer_disconnect(tgt)
                                elif label == "Edit Autoclient":
                                    ac_modal = {"mode": "edit", "target": tgt,
                                                "kind": "autoclient",
                                                "fields": ac_fields_from_config(autoclient_config(tgt)),
                                                "focus": "server_ip", "msg": ""}
                                elif label == "Reconnect":
                                    autoclient_reconnect(tgt)
                                elif label == "Disconnect":
                                    autoclient_disconnect(tgt)
                                elif label == "COM Client":
                                    cc_modal = {"mode": "create", "target": tgt,
                                                "kind": "com",
                                                "fields": cc_default_fields(),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "Edit COM Client":
                                    cc_modal = {"mode": "edit", "target": tgt,
                                                "kind": "com",
                                                "fields": cc_fields_from_config(comclient_config(tgt)),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "MODBUS Master":
                                    cc_modal = {"mode": "create", "target": tgt,
                                                "kind": "modbus",
                                                "fields": mm_default_fields(),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "Edit MODBUS Master":
                                    cc_modal = {"mode": "edit", "target": tgt,
                                                "kind": "modbus",
                                                "fields": mm_fields_from_config(modbusmaster_config(tgt)),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "MODBUS Slave":
                                    cc_modal = {"mode": "create", "target": tgt,
                                                "kind": "modbusslave",
                                                "fields": ms_default_fields(),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "Edit MODBUS Slave":
                                    cc_modal = {"mode": "edit", "target": tgt,
                                                "kind": "modbusslave",
                                                "fields": ms_fields_from_config(modbusslave_config(tgt)),
                                                "focus": "port", "msg": "",
                                                "ports": list_com_ports()}
                                elif label == "MODBUS Reconnect":
                                    # One pair of labels serves master and
                                    # slave -- only one of these can be true.
                                    if is_modbusslave(tgt):
                                        modbusslave_reconnect(tgt)
                                    else:
                                        modbusmaster_reconnect(tgt)
                                elif label == "MODBUS Disconnect":
                                    if is_modbusslave(tgt):
                                        modbusslave_disconnect(tgt)
                                    else:
                                        modbusmaster_disconnect(tgt)
                                elif label == "Link to variable":
                                    link_modal = {"src": tgt, "fields": {"dst": ""},
                                                  "focus": "dst", "msg": "",
                                                  "msg_is_error": False}
                                elif label == "Unlink":
                                    gone = link_remove(tgt)
                                    print(f"[ignoAPI] unlinked {len(gone)} link(s) on '{tgt}'")
                                elif label == "Clear command":
                                    _create_or_write(tgt, "")
                                elif label == "COM Reconnect":
                                    comclient_reconnect(tgt)
                                elif label == "COM Disconnect":
                                    comclient_disconnect(tgt)
                                elif label == "Add EXE files...":
                                    picked = pick_exe_files()
                                    if picked:
                                        # append, skipping anything already listed
                                        cur = exec_paths()
                                        for p in picked:
                                            if p not in cur:
                                                cur.append(p)
                                        _create_or_write(tgt, format_exec_list(cur))
                                        print(f"[ignoAPI] exec list now has {len(cur)} application(s)")
                                elif label == "Clear list":
                                    _create_or_write(tgt, "")
                                    _stop_all_execs()
                                elif label == "Toggle ON/OFF":
                                    _create_or_write(tgt, not exec_flag_on())
                                elif label == "Copy value":
                                    try:    cv = _read(tgt)
                                    except Exception: cv = ""
                                    clipboard_set("" if cv is None else str(cv))
                                elif label == "Copy name":
                                    clipboard_set(str(tgt))
                                elif label == "Combine":
                                    # Arm the picker. The row it was opened
                                    # on is where the command will be
                                    # written, and it starts out unpicked --
                                    # combining a row into itself is a loop.
                                    combine_pick = {"target": tgt, "names": []}
                                elif label == "Paste value":
                                    pasted = clipboard_get()
                                    try:
                                        nv = json.loads(pasted.lower()
                                                        if pasted.strip().lower() in ("true", "false", "null")
                                                        else pasted)
                                    except (json.JSONDecodeError, ValueError):
                                        nv = pasted
                                    _create_or_write(tgt, nv)
                                elif label == "Delete":
                                    delete_variable(tgt)
                                break
                        ctx_menu = None
                        continue

                    # Host-mode toggle (LOCAL <-> NETWORK) — reboot to re-bind
                    if host_rect.collidepoint(mx, my):
                        try:    cur_net = _read("API_NETWORK_HOST")
                        except: cur_net = False
                        _create_or_write("API_NETWORK_HOST", not cur_net)
                        restart_application()
                        continue

                    # Filter cycle: ALL -> VARIABLES -> AUTOCLIENTS -> ALL
                    if filter_rect.collidepoint(mx, my):
                        _i = (VIEW_MODES.index(view_filter)
                              if view_filter in VIEW_MODES else 0)
                        view_filter = VIEW_MODES[(_i + 1) % len(VIEW_MODES)]
                        save_uiprefs(view_filter=view_filter)
                        continue

                    # Sort cycle: NAME A-Z -> NAME Z-A -> NEWEST -> OLDEST -> NAME A-Z
                    if sort_rect.collidepoint(mx, my):
                        sort_mode = SORT_MODES[(SORT_MODES.index(sort_mode) + 1) % len(SORT_MODES)]
                        save_uiprefs(sort_mode=sort_mode)
                        continue

                    # Vertical scrollbar drag / jump
                    if vbar_thumb.collidepoint(mx, my):
                        dragging_vbar = True
                        drag_origin   = (mx, my)
                        drag_scroll   = (scroll_x, scroll_y)
                        continue
                    if vbar_track.collidepoint(mx, my):
                        frac     = (my - vbar_track.y) / vbar_track.height
                        scroll_y = int(-frac * total_h)
                        continue

                    # Horizontal scrollbar drag / jump
                    if hbar_thumb.collidepoint(mx, my):
                        dragging_hbar = True
                        drag_origin   = (mx, my)
                        drag_scroll   = (scroll_x, scroll_y)
                        continue
                    if hbar_track.collidepoint(mx, my):
                        frac     = (mx - hbar_track.x) / hbar_track.width
                        scroll_x = int(-frac * content_w)
                        continue

                    if restart_rect.collidepoint(mx, my):
                        restart_application()
                        continue

                    if startup_rect.collidepoint(mx, my):
                        try:    cur_su = _read("RUN_AT_STARTUP")
                        except: cur_su = False
                        nv = not cur_su
                        _create_or_write("RUN_AT_STARTUP", nv)
                        toggle_windows_startup(nv)
                        continue

                    # + ADD button → open the add-variable panel
                    if add_rect.collidepoint(mx, my):
                        adding = True; add_name = ""; add_val = ""; add_focus = "name"
                        search_active = False; editing_key = None; del_armed = None
                        tb_forget("add")
                        continue

                    # Clicks inside the add panel (fields / create / cancel)
                    if adding:
                        for _r, _fk in ((add_name_rect, "name"),
                                        (add_val_rect, "value")):
                            if _r.collidepoint(mx, my):
                                add_focus = _fk
                                _ed = tb("add", _fk,
                                         add_name if _fk == "name" else add_val)
                                _now = time.time()
                                _dbl = (add_last_fk == _fk
                                        and _now - add_last_t < 0.4)
                                add_last_fk, add_last_t = _fk, _now
                                tb_click(_ed, font, _r, mx,
                                         add_scroll.get(_fk, 0))
                                if _dbl:
                                    _a, _b = _ed.word_at(_ed.caret)
                                    _ed.sel, _ed.caret = _a, _b
                                break
                        else:
                            if add_ok_rect.collidepoint(mx, my):
                                if add_name.strip():
                                    try:
                                        v = json.loads(add_val.lower() if add_val.lower() in
                                                       ['true', 'false', 'null'] else add_val)
                                    except json.JSONDecodeError:
                                        v = add_val
                                    _create_or_write(add_name.strip(), v)
                                adding = False; tb_forget("add")
                            elif add_cancel_rect.collidepoint(mx, my):
                                adding = False; tb_forget("add")
                            elif not add_panel.collidepoint(mx, my):
                                adding = False       # click outside closes it
                                tb_forget("add")
                        continue

                    search_active = search_rect.collidepoint(mx, my)
                    if search_active:
                        editing_key = None
                        _ed = tb("search", "q", search_text)
                        _now = time.time()
                        _dbl = _now - search_last_t < 0.4
                        search_last_t = _now
                        tb_click(_ed, font, search_rect, mx, search_scroll)
                        if _dbl:
                            _a, _b = _ed.word_at(_ed.caret)
                            _ed.sel, _ed.caret = _a, _b
                        continue

                    # THE QUIT QUESTION takes every click while it is up,
                    # so a stray click behind it cannot edit a row that is
                    # about to be closed.
                    if quit_modal is not None:
                        for _i, _r in enumerate(quit_modal.get("rects", [])):
                            if _r.collidepoint(mx, my):
                                if _i == 0:
                                    running = False
                                quit_modal = None
                                break
                        continue

                    # PICKING FOR COMBINE takes the click whole: while the
                    # mode is armed a row click means 'include this one', not
                    # 'edit its value', and clicking a picked row again drops
                    # it. Nothing else on the row responds until Enter or Esc.
                    if combine_pick is not None and my > table_top and mx < table_w:
                        _rel = my - table_top - scroll_y
                        _ci = _rel // row_height
                        if 0 <= _ci < len(items):
                            _nm = items[_ci][0]
                            if _nm == combine_pick["target"]:
                                pass            # a row cannot combine itself
                            elif _nm in combine_pick["names"]:
                                combine_pick["names"].remove(_nm)
                            else:
                                combine_pick["names"].append(_nm)
                        continue

                    # Row click: delete button (far right) or value edit
                    if my > table_top and not search_active:
                        rel_y = my - table_top - scroll_y
                        cidx  = rel_y // row_height
                        if 0 <= cidx < len(items):
                            k, v = items[cidx]
                            if del_x0 <= mx <= del_x0 + del_bw:
                                # per-row ✕ : first click arms, second click deletes
                                if del_armed == k:
                                    # The SAME teardown the context menu
                                    # runs. This used to stop at
                                    # autoclient_delete, so deleting a sync
                                    # (or a COM, MODBUS or FTP row) from
                                    # here left its child running and its
                                    # companions behind.
                                    delete_variable(k)
                                    del_armed = None; editing_key = None
                                else:
                                    del_armed = k; editing_key = None
                            elif mx > col_2_x - 10 + scroll_x:
                                # The EXEC row is a LIST of applications, so
                                # a double-click opens the line-per-entry
                                # editor rather than a one-line box you have
                                # to scroll sideways through.
                                _now = time.time()
                                _dbl_row = (row_last_key == k
                                            and _now - row_last_t < 0.4)
                                if is_exec_var(k) and _dbl_row:
                                    list_modal = {
                                        "owner": "exec", "field": k,
                                        "title": "Applications to keep running",
                                        "text": "\n".join(exec_paths()),
                                        "msg": ""}
                                    tb_forget("list")
                                    row_last_key, row_last_t = None, 0.0
                                    editing_key = None
                                    continue
                                if editing_key != k:
                                    tb_forget("row")     # a different row's caret
                                    edit_scroll = 0
                                editing_key  = k
                                editing_text = str(v)
                                search_active = False; del_armed = None
                                _eb = pygame.Rect(col_2_x - 10 + scroll_x, 0,
                                                  table_w - (col_2_x - 10 + scroll_x),
                                                  row_height)
                                _ed = tb("row", "value", editing_text)
                                _now = time.time()
                                _dbl = (row_last_key == k
                                        and _now - row_last_t < 0.4)
                                row_last_key, row_last_t = k, _now
                                tb_click(_ed, font, _eb, mx, edit_scroll)
                                if _dbl:
                                    _a, _b = _ed.word_at(_ed.caret)
                                    _ed.sel, _ed.caret = _a, _b
                            else:
                                editing_key = None; del_armed = None
                        else:
                            editing_key = None; del_armed = None

                elif event.button == 3:   # right-click → per-row context menu
                    ctx_menu = None
                    if ac_modal is None and cc_modal is None and my > table_top and mx < table_w:
                        rel_y = my - table_top - scroll_y
                        cidx  = rel_y // row_height
                        if 0 <= cidx < len(items):
                            k, v = items[cidx]
                            if is_exec_var(k):
                                its = [("Add EXE files...", True), ("Clear list", True),
                                       ("Copy value", True), ("Paste value", True)]
                            elif is_execflag_var(k):
                                its = [("Toggle ON/OFF", True),
                                       ("Copy value", True), ("Paste value", True)]
                            elif is_autoclient(k):
                                its = [("Reconnect", True), ("Disconnect", True),
                                       ("Edit Autoclient", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            elif is_comclient(k):
                                its = [("COM Reconnect", True), ("COM Disconnect", True),
                                       ("Edit COM Client", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            elif is_com_tx_var(k):
                                # The transmit box: type into it and the
                                # reader sends it. There is no "Send again"
                                # any more -- the reader is a separate process
                                # now and clears the field itself, so ignoAPI
                                # never sees what was transmitted and could
                                # only offer to repeat a payload it does not
                                # have. Paste value covers the same ground.
                                its = [("Copy value", True), ("Paste value", True)]
                            elif is_com_status_var(k):
                                # owned by its COM variable — deleting it alone
                                # would just leave the reader recreating it
                                its = [("Copy value", True)]
                            elif is_modbusmaster(k):
                                its = [("MODBUS Reconnect", True), ("MODBUS Disconnect", True),
                                       ("Edit MODBUS Master", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            elif is_modbusslave(k):
                                its = [("MODBUS Reconnect", True), ("MODBUS Disconnect", True),
                                       ("Edit MODBUS Slave", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            elif is_ftpserver(k):
                                its = [("FTP Restart", True), ("FTP Stop", True),
                                       ("Share FTP link", True),
                                       ("Edit FTP Server", True),
                                       ("Copy value", True),
                                       ("Delete", True)]
                            elif is_ftp_sub_var(k):
                                # written by the server; editing it would just
                                # be overwritten by the next transfer
                                its = [("Copy value", True)]
                            elif is_vdabridge(k):
                                its = [("VDA Reconnect", True), ("VDA Disconnect", True),
                                       ("Edit VDA Bridge", True),
                                       ("Copy value", True),
                                       ("Delete", True)]
                            elif is_vda_sub_var(k):
                                if k.endswith("_vda_tx"):
                                    its = [("Copy value", True), ("Paste value", True)]
                                else:
                                    its = [("Copy value", True)]
                            elif is_syncpeer(k):
                                # The row itself is the readData/writeData box,
                                # so it gets Clear command, like a master's
                                # command rows do.
                                its = [("View Network", True),
                                       ("Sync Reconnect", True), ("Sync Disconnect", True),
                                       ("Edit Sync", True), ("Clear command", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            elif is_sync_sub_var(k) or is_remote_sync_row(k):
                                # _tx is the send box, so it is editable. _rx is
                                # written by the peer and _status by the child,
                                # so offering Paste there would just be a value
                                # overwritten again on the next poll.
                                # _tx is the send box on THIS side too, even
                                # when the sync is driven from the other
                                # machine -- typing into it is how you reply.
                                if k.endswith("_tx"):
                                    its = [("Copy value", True), ("Paste value", True)]
                                else:
                                    its = [("Copy value", True)]
                            elif is_modbusslave_sub_var(k):
                                # A register row IS the register: editing it
                                # changes what a master reads back. The status
                                # row is written by the slave, so read-only.
                                if k.endswith("_status"):
                                    its = [("Copy value", True)]
                                else:
                                    its = [("Copy value", True), ("Paste value", True)]
                            elif is_modbus_sub_var(k):
                                # command rows are edited in place; the status
                                # row is written by the master, so read-only
                                if k.endswith("_status"):
                                    its = [("Copy value", True)]
                                else:
                                    its = [("Clear command", True),
                                           ("Copy value", True), ("Paste value", True)]
                            else:
                                its = [("Create Autoclient", True),
                                       ("COM Client", True),
                                       ("MODBUS Master", True),
                                       ("MODBUS Slave", True),
                                       ("Sync IgnoAPI", True),
                                       ("Create FTP Server", True),
                                       ("Create VDA Bridge", True),
                                       ("Copy value", True), ("Paste value", True),
                                       ("Delete", True)]
                            # "Go to" is offered whenever the VALUE points at
                            # something openable -- an ftp:// link, a URL, or a
                            # path that exists. Prepended so it is the first
                            # thing under the cursor on a row whose whole
                            # purpose is to be opened.
                            if openable_target(current_data.get(k)):
                                its = [("Go to", True)] + its
                            # Linking is offered on EVERY kind of row, so it
                            # is appended once here rather than added to each
                            # of the eight lists above -- where it would
                            # eventually be missing from one of them.
                            # Copy name and Combine, like Link, belong on
                            # EVERY kind of row -- appended once here rather
                            # than added to each of the eighteen lists above,
                            # where they would eventually be missing from one.
                            _lk = (("Unlink", True) if is_linked(k)
                                   else ("Link to variable", True))
                            _extra = [("Copy name", True), ("Combine", True), _lk]
                            if its and its[-1][0] == "Delete":
                                its = its[:-1] + _extra + [its[-1]]
                            else:
                                its = its + _extra
                            ctx_menu = {"pos": ctx_menu_place(mx, my, len(its),
                                                              min(table_w, WINDOW_WIDTH),
                                                              WINDOW_HEIGHT),
                                        "items": its, "target": k}
                            editing_key = None; del_armed = None

                elif event.button == 4:   # scroll wheel up
                    if list_modal is not None:
                        list_modal["top"] = max(0, list_modal.get("top", 0) - 3)
                    elif ac_modal and ac_modal.get("focus"):
                        field_scroll[ac_modal["focus"]] = min(0, field_scroll.get(ac_modal["focus"], 0) + 20)
                    elif cc_modal and cc_modal.get("focus"):
                        field_scroll[cc_modal["focus"]] = min(0, field_scroll.get(cc_modal["focus"], 0) + 20)
                    else:
                        scroll_y = min(0, scroll_y + 30)
                elif event.button == 5:   # scroll wheel down
                    if list_modal is not None:
                        list_modal["top"] = list_modal.get("top", 0) + 3
                    elif ac_modal and ac_modal.get("focus"):
                        field_scroll[ac_modal["focus"]] = field_scroll.get(ac_modal["focus"], 0) - 20
                    elif cc_modal and cc_modal.get("focus"):
                        field_scroll[cc_modal["focus"]] = field_scroll.get(cc_modal["focus"], 0) - 20
                    else:
                        scroll_y = max(max_sy, scroll_y - 30)
                elif event.button == 6:   # horizontal wheel left
                    scroll_x = min(0, scroll_x + 30)
                elif event.button == 7:   # horizontal wheel right
                    scroll_x = max(max_sx, scroll_x - 30)

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if list_modal is not None:
                        # Drawn on top of the form that opened it, so it is the
                        # first thing Escape closes -- otherwise Escape would
                        # shut the form underneath and leave the editor
                        # floating over nothing.
                        list_modal = None
                        tb_forget("list")
                    elif net_modal is not None:
                        net_modal = None
                    elif link_modal is not None:
                        # Same trap the serial modal hit: this outer branch
                        # catches EVERY Escape, so a case further down could
                        # never run and Escape would quit the application while
                        # the panel says "Esc: cancel".
                        link_modal = None
                    elif cc_modal is not None:
                        # The serial modal (COM and MODBUS) MUST be handled
                        # here. This outer branch catches every Escape, so
                        # without this case a modal-open Escape fell straight
                        # through to `running = False` and quit the whole
                        # application -- while the modal's own header says
                        # "Esc: cancel". The matching case further down, inside
                        # `elif cc_modal is not None`, could never run.
                        if cc_dropdown is not None:
                            cc_dropdown = None      # first Esc closes the dropdown
                        else:
                            cc_modal = None         # second Esc closes the modal
                    elif ac_modal is not None:
                        ac_modal = None
                    elif ctx_menu is not None:
                        ctx_menu = None
                    elif adding:
                        adding = False
                    elif combine_pick is not None:
                        combine_pick = None     # Esc: cancel combining
                    elif editing_key:
                        editing_key = None
                    elif quit_modal is not None:
                        quit_modal = None       # Esc on the question means no
                    else:
                        quit_modal = {"sel": 1}   # default: stay

                elif quit_modal is not None:
                    # Modal, and placed FIRST so no other branch can claim a
                    # key while the window is asking whether to close.
                    if event.key in (pygame.K_LEFT, pygame.K_RIGHT,
                                     pygame.K_TAB):
                        quit_modal["sel"] = 1 - quit_modal["sel"]
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if quit_modal["sel"] == 0:
                            running = False
                        quit_modal = None
                    elif event.unicode.lower() == "y":
                        running = False
                    elif event.unicode.lower() == "n":
                        quit_modal = None

                elif combine_pick is not None:
                    # Enter combines what has been picked; everything else
                    # is ignored, so a stray key cannot half-commit it.
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        _names = combine_pick["names"]
                        if _names:
                            # A combine command is the word then a TEMPLATE,
                            # so the picked names become placeholders. Comma
                            # separated, because reading the result by
                            # position is the whole point of combining.
                            _create_or_write(
                                combine_pick["target"],
                                "combine " + ",".join("{%s}" % n for n in _names))
                        combine_pick = None

                elif list_modal is not None:
                    _ed = tb("list", "text", list_modal["text"], multiline=True)
                    if _ctrl_held() and event.key in (pygame.K_RETURN,
                                                      pygame.K_KP_ENTER):
                        # Enter starts a new entry here, so SAVING is
                        # ctrl+Enter -- the bargain every multi-line box makes.
                        list_modal = list_save(list_modal, ac_modal,
                                               net_modal, cc_modal)
                    elif tb_key(_ed, event):
                        list_modal["text"] = _ed.text

                elif cc_modal is not None:
                    foc = cc_modal["focus"]
                    mods = pygame.key.get_mods()
                    # (Escape is handled in the branch above — it can never
                    # reach here, because the outer `if` claims every Escape.)
                    if event.key == pygame.K_TAB:
                        order = [fk for fk, _ in cc_field_defs]
                        i = order.index(foc) if foc in order else -1
                        step = -1 if (mods & pygame.KMOD_SHIFT) else 1
                        cc_modal["focus"] = order[(i + step) % len(order)]
                        cc_dropdown = None
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if cc_dropdown is not None:
                            cc_dropdown = None
                        else:
                            _cast, _create, _edit = _cc_modal_actions(cc_kind)
                            cfg = _cast(cc_modal["fields"])
                            if cc_modal["mode"] == "create":
                                ok, err = _create(cc_modal["target"], cfg)
                                if ok:
                                    cc_modal = None
                                else:
                                    cc_modal["msg"] = err
                                    cc_modal["msg_is_error"] = True
                            else:
                                _edit(cc_modal["target"], cfg)
                                cc_modal = None
                    elif foc in cc_drop_fields and event.key in (pygame.K_UP, pygame.K_DOWN):
                        # cycle the dropdown without opening it
                        opts = [o for o in _cc_dropdown_options(foc) if not o.startswith("(")]
                        if opts:
                            curv = str(cc_modal["fields"].get(foc, ""))
                            i = opts.index(curv) if curv in opts else -1
                            i = (i + (1 if event.key == pygame.K_DOWN else -1)) % len(opts)
                            cc_modal["fields"][foc] = opts[i]
                    elif foc in CC_TOGGLE_FIELDS and event.key == pygame.K_SPACE:
                        cur = str(cc_modal["fields"].get(foc, "false")).lower() in ("true", "1", "yes", "on")
                        cc_modal["fields"][foc] = "false" if cur else "true"
                    elif foc not in CC_TOGGLE_FIELDS:
                        _ed = tb("cc", foc, cc_modal["fields"].get(foc, ""))
                        if tb_key(_ed, event):
                            cc_modal["fields"][foc] = _ed.text

                elif net_modal is not None:
                    fld = net_modal["fields"]
                    foc = net_modal.get("focus", "hosts")
                    _ed = tb("net", foc, fld.get(foc, ""))
                    if tb_key(_ed, event):
                        fld[foc] = _ed.text
                    elif event.key == pygame.K_TAB:
                        net_modal["focus"] = "macs" if foc == "hosts" else "hosts"
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        pygame.event.post(pygame.event.Event(
                            pygame.MOUSEBUTTONDOWN, button=1,
                            pos=net_ok_rect.center))

                elif link_modal is not None:
                    _ed = tb("link", "dst", link_modal["fields"].get("dst", ""))
                    if tb_key(_ed, event):
                        link_modal["fields"]["dst"] = _ed.text
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        ok, err = link_add(link_modal["src"],
                                           link_modal["fields"].get("dst", ""))
                        if ok:
                            link_modal = None
                            tb_forget("link")
                        else:
                            link_modal["msg"] = err
                            link_modal["msg_is_error"] = True

                elif ac_modal is not None:
                    order = [fk for fk, _ in ac_field_defs]
                    foc   = ac_modal["focus"]
                    # The shared editor gets first refusal: it owns the caret,
                    # the selection and every ctrl combination, and returns
                    # False only for the keys the FORM owns (Enter, Tab) or for
                    # a field that is a toggle rather than a text box.
                    _ed = (None if foc in AC_TOGGLE_FIELDS
                           else tb("ac", foc, ac_modal["fields"].get(foc, "")))
                    if _ed is not None and tb_key(_ed, event):
                        ac_modal["fields"][foc] = _ed.text
                    elif event.key == pygame.K_RETURN:
                        _cast, _create, _edit = _ac_modal_actions(ac_kind)
                        cfg = _cast(ac_modal["fields"])
                        if ac_modal["mode"] == "create":
                            ok, err = _create(ac_modal["target"], cfg)
                            if ok:
                                ac_modal = None
                            else:
                                ac_modal["msg"] = err
                                ac_modal["msg_is_error"] = True
                        else:
                            _edit(ac_modal["target"], cfg)
                            ac_modal = None
                    elif event.key == pygame.K_TAB:
                        i = order.index(foc) if foc in order else 0
                        ac_modal["focus"] = order[(i + 1) % len(order)]
                    elif foc == "runatstartup":
                        cur = str(ac_modal["fields"].get("runatstartup", "false")).lower() in ("true", "1", "yes", "on")
                        ac_modal["fields"]["runatstartup"] = "false" if cur else "true"
                    elif foc == "read_only":
                        cur = str(ac_modal["fields"].get("read_only", "false")).lower() in ("true", "1", "yes", "on")
                        ac_modal["fields"]["read_only"] = "false" if cur else "true"
                    elif foc in ("use_tls", "subscribe_visualization", "store_raw"):
                        cur = str(ac_modal["fields"].get(foc, "false")).lower() in ("true", "1", "yes", "on")
                        ac_modal["fields"][foc] = "false" if cur else "true"
                    elif foc == "topology":
                        cur = str(ac_modal["fields"].get("topology", "star")).strip().lower()
                        ac_modal["fields"]["topology"] = "star" if cur == "delta" else "delta"
                    elif foc == "mode":
                        # Two legal values, so any key flips it rather than
                        # typing into it -- a text field here would take
                        # "0x03" and silently fall back to level mode.
                        cur = str(ac_modal["fields"].get("mode", "0x01")).strip().lower()
                        ac_modal["fields"]["mode"] = "0x01" if cur == "0x02" else "0x02"

                elif adding:
                    _ed = tb("add", add_focus,
                             add_name if add_focus == "name" else add_val)
                    if tb_key(_ed, event):
                        if add_focus == "name": add_name = _ed.text
                        else:                   add_val = _ed.text
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        if add_name.strip():
                            try:
                                v = json.loads(add_val.lower() if add_val.lower() in
                                               ['true', 'false', 'null'] else add_val)
                            except json.JSONDecodeError:
                                v = add_val
                            _create_or_write(add_name.strip(), v)
                        adding = False
                        tb_forget("add")
                    elif event.key == pygame.K_TAB:
                        add_focus = "value" if add_focus == "name" else "name"

                elif editing_key:
                    _ed = tb("row", "value", editing_text)
                    if tb_key(_ed, event):
                        editing_text = _ed.text
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        try:
                            nv = json.loads(editing_text.lower() if editing_text.lower() in ['true', 'false', 'null'] else editing_text)
                        except json.JSONDecodeError:
                            nv = editing_text
                        _create_or_write(editing_key, nv)
                        editing_key = None
                        tb_forget("row")

                elif search_active:
                    _ed = tb("search", "q", search_text)
                    if tb_key(_ed, event):
                        search_text  = _ed.text
                        text_changed = True
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        text_changed = True

            elif event.type == pygame.VIDEORESIZE:
                WINDOW_WIDTH, WINDOW_HEIGHT = event.w, event.h
                screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)
                font, title_font, header_font, small_font, _scale = make_fonts(WINDOW_WIDTH, WINDOW_HEIGHT)
                row_height, header_height, info_bar_height, col_1_x, col_2_x, title_row_height = make_layout(WINDOW_WIDTH, WINDOW_HEIGHT, _scale)
                search_rect, startup_rect, restart_rect, add_rect, host_rect, filter_rect, sort_rect = make_header_rects(WINDOW_WIDTH, WINDOW_HEIGHT)

        # ── Editors belong to whatever is open ────────────────────────────
        # ONE place decides whose caret survives, instead of a tb_forget()
        # sprinkled at each of the dozen or so points a form can close --
        # which is exactly the kind of list that ends up missing an entry, and
        # then the next form opened under the same name inherits a stale caret
        # and a stale selection.
        for _own, _alive in (("ac", ac_modal is not None),
                             ("cc", cc_modal is not None),
                             ("net", net_modal is not None),
                             ("link", link_modal is not None),
                             ("list", list_modal is not None),
                             ("add", adding),
                             ("row", editing_key is not None)):
            if not _alive:
                tb_forget(_own)

        # ── Auto-scroll to search match ───────────────────────────────────
        if text_changed and search_text:
            for idx, (k, v) in enumerate(items):
                if search_text.lower() in str(k).lower() or search_text.lower() in str(v).lower():
                    scroll_y = -idx * row_height + table_h // 3
                    break

        # ── Draw background ───────────────────────────────────────────────
        screen.fill(BG_COLOR)

        # ── Draw rows (clipped to content area) ───────────────────────────
        screen.set_clip(pygame.Rect(0, table_top, table_w, table_h))
        for i, (key, val) in enumerate(items):
            row_y = table_top + scroll_y + i * row_height
            if row_y + row_height < table_top or row_y > table_top + table_h:
                continue

            is_match = bool(search_text and (
                search_text.lower() in str(key).lower() or
                search_text.lower() in str(val).lower()
            ))
            is_ac = is_autoclient(key)
            is_ex = is_exec_row(key)
            is_cc = is_comclient(key)
            is_cs = (not is_cc) and (is_com_status_var(key) or is_com_tx_var(key))
            is_sy = is_syncpeer(key)
            is_ss = (not is_sy) and (is_sync_sub_var(key) or is_remote_sync_row(key))
            is_ft = is_ftpserver(key)
            # a shared link is not a server and owns no sub-rows, but it
            # is the same thing seen from the other machine
            is_fs = (not is_ft) and (is_ftp_sub_var(key) or is_ftp_link_var(key))
            is_vd = is_vdabridge(key)
            is_vs = (not is_vd) and is_vda_sub_var(key)
            is_cb = is_combine_src(key)
            is_cr = is_combined_var(key)
            is_mm = is_modbusmaster(key) or is_modbusslave(key)
            is_ms = (not is_mm) and (is_modbus_sub_var(key)
                                     or is_modbusslave_sub_var(key))
            rc = MATCH_COLOR if is_match else (ROW_COLOR_1 if i % 2 == 0 else ROW_COLOR_2)
            pygame.draw.rect(screen, rc, (0, row_y, table_w, row_height))
            pygame.draw.line(screen, GRID_COLOR, (0, row_y), (table_w, row_y))
            div_x = col_2_x - 20 + scroll_x
            pygame.draw.line(screen, GRID_COLOR, (div_x, row_y), (div_x, row_y + row_height))

            # autoclient rows: a live dot (green = process alive, red = not) in
            # the left margin, and blue name/value to mark "fed by an autoclient"
            if is_ac:
                live = autoclient_is_live(key)
                dot_c = (40, 210, 70) if live else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_ex:
                # same live dot for the supervisor: green only when every
                # configured application is actually up
                n_up, n_tot = exec_status()
                dot_c = ((40, 210, 70) if (n_tot and n_up == n_tot)
                         else ((215, 55, 55) if exec_flag_on() else (110, 110, 110)))
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_cc:
                # green only when the serial port is actually open
                dot_c = (40, 210, 70) if comclient_is_live(key) else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_ft:
                # green only when the server says it is actually serving: a
                # process that came up and failed to bind the port is not
                # sharing anything
                dot_c = (40, 210, 70) if ftpserver_is_live(key) else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_vd:
                dot_c = (40, 210, 70) if vdabridge_is_live(key) else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_sy:
                # green only when the peer is actually answering -- the
                # process stays alive retrying a computer that is switched
                # off, and that must not read as a working link
                dot_c = (40, 210, 70) if syncpeer_is_live(key) else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))
            elif is_mm:
                # green only when the process is alive AND actually on the bus
                _live = (modbusslave_is_live(key) if is_modbusslave(key)
                         else modbusmaster_is_live(key))
                dot_c = (40, 210, 70) if _live else (215, 55, 55)
                pygame.draw.circle(screen, dot_c,
                                   (max(10, col_1_x - 16), row_y + row_height // 2),
                                   max(3, row_height // 6))

            kc = ((255, 255, 255) if is_match else
                  (AC_BLUE if is_ac else
                   (EXEC_RED if is_ex else
                    (COM_YELLOW if is_cc else
                     (COM_YELLOW_DIM if is_cs else
                      (MB_GREEN if is_mm else
                       (MB_GREEN_DIM if is_ms else
                        (SY_VIOLET if is_sy else
                         (SY_VIOLET_DIM if is_ss else
                          (CMB_ORANGE if is_cb else
                           (CMB_ORANGE_DIM if is_cr else
                            (FTP_GOLD if is_ft else
                             (FTP_GOLD_DIM if is_fs else
                              (VDA_TEAL if is_vd else
                               (VDA_TEAL_DIM if is_vs else TEXT_COLOR)))))))))))))))
            # While the combine picker is armed a chosen name says so twice:
            # in orange, and inside a box. Colour alone is not enough on a
            # table where several kinds of row are already coloured.
            _picked = (combine_pick is not None
                       and key in combine_pick["names"])
            if _picked:
                kc = CMB_ORANGE
            ks = font.render(str(key), True, kc)
            _kx = col_1_x + scroll_x
            _ky = row_y + (row_height - ks.get_height()) // 2
            if _picked:
                pygame.draw.rect(screen, CMB_ORANGE,
                                 (_kx - 4, row_y + 2,
                                  ks.get_width() + 8, row_height - 4), 1)
            elif combine_pick is not None and key == combine_pick["target"]:
                # where the command will be written
                pygame.draw.rect(screen, CMB_ORANGE_DIM,
                                 (_kx - 4, row_y + 2,
                                  ks.get_width() + 8, row_height - 4), 1)
            screen.blit(ks, (_kx, _ky))

            if key == editing_key:
                eb = pygame.Rect(col_2_x - 10 + scroll_x, row_y + 2,
                                 table_w - (col_2_x - 10 + scroll_x), row_height - 4)
                pygame.draw.rect(screen, EDIT_BG_COLOR, eb)
                pygame.draw.rect(screen, HIGHLIGHT_COLOR, eb, 1)
                _ed = tb("row", "value", editing_text)
                edit_scroll = tb_draw(screen, font, _ed, eb, True, edit_scroll,
                                      text_col=(255, 255, 255))
                screen.set_clip(pygame.Rect(0, table_top, table_w, table_h))
            else:
                if isinstance(val, float):
                    val_str = f"{val:.5f}"
                elif isinstance(val, str):
                    val_str = f'"{val}"'
                else:
                    val_str = str(val)
                # autoclient values render blue (with a subtle box) to show the
                # value is being driven live by an autoclient, not typed
                if is_match:
                    vc = (255, 255, 255)
                elif is_ac:
                    vc = AC_BLUE
                elif is_ex:
                    vc = EXEC_RED
                elif isinstance(val, str):
                    vc = (180, 200, 255)
                else:
                    vc = HIGHLIGHT_COLOR
                # EXEC shows "n/m running" beside the raw list -- the paths are
                # long, so the count is what you actually want to read
                if is_ex and is_exec_var(key):
                    n_up, n_tot = exec_status()
                    val_str = f"{val_str}   [{n_up}/{n_tot} running]" if n_tot else val_str
                if (is_ac or is_ex) and not is_match:
                    vb = pygame.Rect(col_2_x - 10 + scroll_x, row_y + 2,
                                     min(font.size(val_str)[0] + 24, table_w - (col_2_x - 10 + scroll_x) - del_bw - 10),
                                     row_height - 4)
                    pygame.draw.rect(screen, AC_BLUE_DIM if is_ac else EXEC_RED_DIM, vb, 1)
                vs = font.render(val_str, True, vc)
                screen.blit(vs, (col_2_x + scroll_x, row_y + (row_height - vs.get_height()) // 2))

            # per-row delete button (armed = red "SURE?", else grey ✕)
            db = pygame.Rect(del_x0, row_y + 2, del_bw, row_height - 4)
            armed = (del_armed == key)
            dhov = db.collidepoint(mouse_pos)
            dcol = (220, 60, 60) if (armed or dhov) else (110, 70, 70)
            pygame.draw.rect(screen, (45, 25, 25) if armed else (30, 30, 30), db)
            pygame.draw.rect(screen, dcol, db, 1)
            dtxt = small_font.render("!" if armed else "x", True, dcol)
            screen.blit(dtxt, (db.centerx - dtxt.get_width() // 2,
                               db.centery - dtxt.get_height() // 2))

        # ── the link diagram ─────────────────────────────────────────────
        # A bracket down the left gutter joining a source to what it feeds,
        # with the arrow on the target. Drawn AFTER the rows: each row paints
        # its own background, so a connector drawn first would be covered.
        # Rows are already adjacent, so this is short -- it exists to say
        # WHICH way the value flows, which adjacency alone cannot.
        _row_at = {k: idx for idx, (k, _v) in enumerate(items)}
        _gx = max(4, col_1_x - 38)          # gutter, left of the live dots
        for _src, _dsts in row_pair_map().items():
            if _src not in _row_at:
                continue
            _y1 = table_top + scroll_y + _row_at[_src] * row_height + row_height // 2
            for _dst in _dsts:
                if _dst not in _row_at:
                    continue
                _y2 = table_top + scroll_y + _row_at[_dst] * row_height + row_height // 2
                if max(_y1, _y2) < table_top or min(_y1, _y2) > table_top + table_h:
                    continue
                pygame.draw.line(screen, LINK_CYAN_DIM, (_gx, _y1), (_gx, _y2), 2)
                pygame.draw.line(screen, LINK_CYAN_DIM, (_gx, _y1), (_gx + 10, _y1), 2)
                pygame.draw.line(screen, LINK_CYAN, (_gx, _y2), (_gx + 10, _y2), 2)
                pygame.draw.circle(screen, LINK_CYAN_DIM, (_gx, _y1), 3)
                # arrowhead into the target
                pygame.draw.polygon(screen, LINK_CYAN,
                                    [(_gx + 16, _y2), (_gx + 8, _y2 - 4),
                                     (_gx + 8, _y2 + 4)])
        screen.set_clip(None)

        # ── Fixed header ─────────────────────────────────────────────────
        # Two rows: the logo/title live in their own row up top (title_row_height);
        # the button row sits below it (see make_header_rects). They used to
        # share one row, which put the ADD/HOST/FILTER/SORT buttons directly
        # on top of the logo and "ignoAPI" text.
        pygame.draw.rect(screen, HEADER_COLOR, (0, 0, WINDOW_WIDTH, header_height))
        pygame.draw.line(screen, HIGHLIGHT_COLOR, (0, header_height), (WINDOW_WIDTH, header_height), 2)
        pygame.draw.line(screen, GRID_COLOR, (0, title_row_height), (WINDOW_WIDTH, title_row_height))
        draw_logo(screen, max(30, int(50 * _scale)), title_row_height // 2)
        ts = title_font.render("ignoAPI", True, (255, 255, 255))
        screen.blit(ts, (max(60, int(100 * _scale)), (title_row_height - ts.get_height()) // 2))

        # Search bar
        bc = HIGHLIGHT_COLOR if search_active else (100, 100, 100)
        pygame.draw.rect(screen, (30, 30, 30), search_rect)
        pygame.draw.rect(screen, bc, search_rect, 2)
        _ed = tb("search", "q", search_text)
        search_scroll = tb_draw(screen, font, _ed, search_rect,
                                bool(search_active and not editing_key),
                                search_scroll, text_col=(255, 255, 255))
        lbl = small_font.render("Search:", True, TEXT_COLOR)
        screen.blit(lbl, (search_rect.x - lbl.get_width() - 4,
                          search_rect.y + (search_rect.height - lbl.get_height()) // 2))

        # Startup button
        try:    su_on = _read("RUN_AT_STARTUP")
        except: su_on = False
        su_hov = startup_rect.collidepoint(mouse_pos)
        su_c   = (TACTICAL_GREEN if su_hov else (10, 150, 10)) if su_on else ((150, 50, 50) if su_hov else (100, 30, 30))
        su_txt = "[STARTUP:ON ]" if su_on else "[STARTUP:OFF]"
        pygame.draw.rect(screen, (30, 30, 30), startup_rect)
        pygame.draw.rect(screen, su_c, startup_rect, 2)
        su_s = font.render(su_txt, True, su_c)
        screen.blit(su_s, (startup_rect.x + (startup_rect.width - su_s.get_width()) // 2,
                           startup_rect.y + (startup_rect.height - su_s.get_height()) // 2))

        # Restart button
        rb_hov = restart_rect.collidepoint(mouse_pos)
        rb_c   = TACTICAL_GREEN if rb_hov else (10, 100, 10)
        pygame.draw.rect(screen, (30, 30, 30), restart_rect)
        pygame.draw.rect(screen, rb_c, restart_rect, 2)
        rb_s = font.render("[ REBOOT ]", True, rb_c)
        screen.blit(rb_s, (restart_rect.x + (restart_rect.width - rb_s.get_width()) // 2,
                           restart_rect.y + (restart_rect.height - rb_s.get_height()) // 2))

        # + ADD variable button
        ad_hov = add_rect.collidepoint(mouse_pos)
        ad_c   = TACTICAL_GREEN if (ad_hov or adding) else (10, 130, 10)
        pygame.draw.rect(screen, (30, 30, 30), add_rect)
        pygame.draw.rect(screen, ad_c, add_rect, 2)
        ad_s = font.render("[ + ADD ]", True, ad_c)
        screen.blit(ad_s, (add_rect.x + (add_rect.width - ad_s.get_width()) // 2,
                           add_rect.y + (add_rect.height - ad_s.get_height()) // 2))

        # HOST-mode toggle (LOCAL / NETWORK)
        h_hov = host_rect.collidepoint(mouse_pos)
        h_c   = (AC_BLUE if h_hov else (60, 120, 200)) if network_on else ((150, 150, 60) if h_hov else (110, 110, 40))
        h_txt = "[HOST:NETWORK]" if network_on else "[HOST:LOCAL]"
        pygame.draw.rect(screen, (30, 30, 30), host_rect)
        pygame.draw.rect(screen, h_c, host_rect, 2)
        h_s = font.render(h_txt, True, h_c)
        screen.blit(h_s, (host_rect.x + (host_rect.width - h_s.get_width()) // 2,
                          host_rect.y + (host_rect.height - h_s.get_height()) // 2))

        # FILTER cycle button (ALL / VARS / AUTOCLIENTS / EXEC / SERIAL)
        f_hov  = filter_rect.collidepoint(mouse_pos)
        # Label and colour both come from VIEW_DEFS, so the button matches the
        # rows it is showing without a second list to keep in step.
        f_lbl  = VIEW_LABEL.get(view_filter, "[VIEW:ALL]")
        _bright, _dim = VIEW_COLOUR.get(view_filter, (AC_BLUE, (70, 130, 200)))
        f_c = _bright if f_hov else _dim
        pygame.draw.rect(screen, (30, 30, 30), filter_rect)
        pygame.draw.rect(screen, f_c, filter_rect, 2)
        f_s = font.render(f_lbl, True, f_c)
        screen.blit(f_s, (filter_rect.x + (filter_rect.width - f_s.get_width()) // 2,
                          filter_rect.y + (filter_rect.height - f_s.get_height()) // 2))

        # SORT cycle button (Name A-Z / Name Z-A / Newest / Oldest — like Windows Explorer's Sort by)
        so_hov = sort_rect.collidepoint(mouse_pos)
        so_c   = AC_BLUE if so_hov else (70, 130, 200)
        pygame.draw.rect(screen, (30, 30, 30), sort_rect)
        pygame.draw.rect(screen, so_c, sort_rect, 2)
        so_s = font.render(SORT_LABELS[sort_mode], True, so_c)
        screen.blit(so_s, (sort_rect.x + (sort_rect.width - so_s.get_width()) // 2,
                           sort_rect.y + (sort_rect.height - so_s.get_height()) // 2))
        # ── Info bar: one combined status line below the button row ───────
        # (was previously two separate pieces of text drawn INSIDE the button
        # row and squeezed under a button — both rendered behind/under the
        # buttons on some window sizes. Now it's its own full-width strip.)
        info_y = header_height
        pygame.draw.rect(screen, (24, 26, 32), (0, info_y, WINDOW_WIDTH, info_bar_height))
        pygame.draw.line(screen, GRID_COLOR, (0, info_y + info_bar_height), (WINDOW_WIDTH, info_y + info_bar_height))
        # The MAC is here for the same reason the IP is: it is what you read
        # out to the other machine so it can find this one. Without it you have
        # to go and dig it out of ipconfig.
        _my_mac = local_mac()
        _mac_txt = f"  MAC {_my_mac}" if _my_mac else ""
        _my_name = ignoapi_hostname()
        if _my_name:
            _mac_txt += f"  {_my_name}"
        if network_on:
            host_txt = (f"HOST: {BOUND_HOST}:{PORT}  "
                        f"(LAN {get_lan_ip()}:{PORT}{_mac_txt})")
        else:
            host_txt = f"HOST: {BOUND_HOST}:{PORT}  (local only{_mac_txt})"
        n_ex_up, n_ex_tot = exec_status()
        exec_txt = (f"   |   EXEC {'ON' if exec_flag_on() else 'off'}: "
                    f"{n_ex_up}/{n_ex_tot} running") if n_ex_tot else ""
        info_txt = (f"{host_txt}   |   Autoclients live: {n_live}/{n_ac}"
                    f"{exec_txt}   |   ESC: QUIT")
        info_s = small_font.render(info_txt, True, HIGHLIGHT_COLOR)
        screen.blit(info_s, (max(16, int(50 * _scale)), info_y + (info_bar_height - info_s.get_height()) // 2))

        # ── Sub-header (fixed, above table) ──────────────────────────────
        sub_top = header_height + info_bar_height
        pygame.draw.rect(screen, (30, 30, 30), (0, sub_top, table_w, 40))
        pygame.draw.line(screen, GRID_COLOR, (0, table_top), (table_w, table_top))
        pygame.draw.line(screen, GRID_COLOR, (col_2_x - 20, sub_top), (col_2_x - 20, table_top))
        hk = header_font.render("Variable Name", True, (180, 180, 180))
        hv = header_font.render("Current Value (Click to Edit)", True, (180, 180, 180))
        screen.blit(hk, (col_1_x, sub_top + (40 - hk.get_height()) // 2))
        screen.blit(hv, (col_2_x, sub_top + (40 - hv.get_height()) // 2))

        # ── Scrollbars ────────────────────────────────────────────────────
        pygame.draw.rect(screen, SCROLLBAR_BG, vbar_track)
        vhov = vbar_thumb.collidepoint(mouse_pos) or dragging_vbar
        pygame.draw.rect(screen, SCROLLBAR_HOVER if vhov else SCROLLBAR_FG, vbar_thumb, border_radius=4)

        pygame.draw.rect(screen, SCROLLBAR_BG, hbar_track)
        hhov = hbar_thumb.collidepoint(mouse_pos) or dragging_hbar
        pygame.draw.rect(screen, SCROLLBAR_HOVER if hhov else SCROLLBAR_FG, hbar_thumb, border_radius=4)

        # Corner fill between the two scrollbars
        pygame.draw.rect(screen, SCROLLBAR_BG,
                         pygame.Rect(table_w, WINDOW_HEIGHT - SCROLLBAR_H, SCROLLBAR_W, SCROLLBAR_H))

        # ── Add-variable panel (modal overlay on top) ─────────────────────
        if adding:
            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 120)); screen.blit(dim, (0, 0))
            pygame.draw.rect(screen, (34, 34, 38), add_panel, border_radius=6)
            pygame.draw.rect(screen, HIGHLIGHT_COLOR, add_panel, 2, border_radius=6)
            title = header_font.render("Add variable", True, (230, 230, 230))
            screen.blit(title, (add_panel.x + 14, add_panel.y + 10))
            hint = small_font.render("Tab: switch   Enter: create   Esc: cancel",
                                     True, (150, 150, 150))
            screen.blit(hint, (add_panel.right - hint.get_width() - 14, add_panel.y + 14))
            for rect, txt, ph, foc in (
                    (add_name_rect, add_name, "name", "name"),
                    (add_val_rect, add_val, "value", "value")):
                focused = (add_focus == foc)
                pygame.draw.rect(screen, (20, 20, 24), rect)
                pygame.draw.rect(screen, HIGHLIGHT_COLOR if focused else (100, 100, 100), rect, 2)
                if not txt and not focused:
                    ts2 = font.render(ph, True, (110, 110, 110))
                    screen.set_clip(rect)
                    screen.blit(ts2, (rect.x + 5,
                                      rect.y + (rect.height - ts2.get_height()) // 2))
                    screen.set_clip(None)
                else:
                    _ed = tb("add", foc, txt)
                    add_scroll[foc] = tb_draw(screen, font, _ed, rect, focused,
                                              add_scroll.get(foc, 0),
                                              text_col=(255, 255, 255))
            for rect, label, col in ((add_ok_rect, "Create", (20, 180, 20)),
                                     (add_cancel_rect, "Cancel", (170, 60, 60))):
                pygame.draw.rect(screen, (30, 30, 30), rect)
                pygame.draw.rect(screen, col, rect, 2)
                ls = small_font.render(label, True, col)
                screen.blit(ls, (rect.centerx - ls.get_width() // 2,
                                 rect.centery - ls.get_height() // 2))
        # (rect layout is done once per frame by modal_layout above,
        #  which also keeps a dragged panel on screen after a resize)
        # ── Autoclient create/edit modal (on top of everything) ───────────
        if ac_modal is not None:
            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 140)); screen.blit(dim, (0, 0))
            pygame.draw.rect(screen, (30, 32, 40), ac_panel, border_radius=8)
            pygame.draw.rect(screen, AC_BLUE, ac_panel, 2, border_radius=8)
            ttl = header_font.render(
                ("Create" if ac_modal["mode"] == "create" else "Edit")
                + (" Sync IgnoAPI" if ac_kind == "sync"
                   else (" FTP Server" if ac_kind == "ftp"
                         else (" VDA Bridge" if ac_kind == "vda" else " Autoclient")))
                + f" — {ac_modal['target']}",
                True, AC_BLUE)
            screen.blit(ttl, (ac_panel.x + 16, ac_panel.y + 12))
            hint = small_font.render("Tab: next   Enter: save   Esc: cancel", True, (150, 150, 150))
            screen.blit(hint, (ac_panel.right - hint.get_width() - 14, ac_panel.y + 16))
            for fk, lbl in ac_field_defs:
                rect = ac_field_rects[fk]
                ls = font.render(lbl, True, (200, 210, 230))
                screen.blit(ls, (ac_panel.x + 18, rect.y + (rect.height - ls.get_height()) // 2))
                focused = (ac_modal["focus"] == fk)
                if fk in ("runatstartup", "use_tls", "subscribe_visualization", "store_raw"):
                    on = str(ac_modal["fields"].get(fk, "false")).lower() in ("true", "1", "yes", "on")
                    box = pygame.Rect(rect.x, rect.y, 60, rect.height)
                    pygame.draw.rect(screen, (25, 70, 35) if on else (60, 30, 30), box)
                    pygame.draw.rect(screen, (40, 200, 70) if on else (200, 70, 70), box, 2)
                    vs = font.render("TRUE" if on else "FALSE", True, (40, 200, 70) if on else (210, 90, 90))
                    screen.blit(vs, (box.x + 6, box.y + (box.height - vs.get_height()) // 2))
                elif fk == "read_only":
                    on = str(ac_modal["fields"].get("read_only", "false")).lower() in ("true", "1", "yes", "on")
                    box = pygame.Rect(rect.x, rect.y, 120, rect.height)
                    pygame.draw.rect(screen, (25, 40, 60) if on else (45, 35, 20), box)
                    pygame.draw.rect(screen, (90, 165, 255) if on else FTP_GOLD, box, 2)
                    vs = font.render("READ ONLY" if on else "READ/WRITE", True,
                                     (90, 165, 255) if on else FTP_GOLD)
                    screen.blit(vs, (box.x + 6, box.y + (box.height - vs.get_height()) // 2))
                elif fk == "topology":
                    # Named, not coded, and with the consequence spelled out:
                    # the difference between these two is which machines can
                    # talk to which, and that is not recoverable from the word
                    # alone.
                    delta = str(ac_modal["fields"].get("topology", "star")).strip().lower() == "delta"
                    box = pygame.Rect(rect.x, rect.y, max(150, rect.width // 2), rect.height)
                    col = SY_VIOLET if delta else (90, 165, 255)
                    pygame.draw.rect(screen, (24, 22, 34) if delta else (18, 24, 34), box)
                    pygame.draw.rect(screen, col, box, 2)
                    vs = font.render("DELTA  mesh" if delta else "STAR  hub", True, col)
                    screen.blit(vs, (box.x + 6, box.y + (box.height - vs.get_height()) // 2))
                    hs = small_font.render(
                        "every machine talks to every other (relayed by this one)"
                        if delta else
                        "the peers talk to this machine only",
                        True, (140, 145, 160))
                    screen.blit(hs, (box.right + 8, box.y + (box.height - hs.get_height()) // 2))
                elif fk == "mode":
                    # rather than shown as "0x01", because which of the two
                    # codes means what is the one thing worth reading here.
                    pulse = str(ac_modal["fields"].get("mode", "0x01")).strip().lower() == "0x02"
                    box = pygame.Rect(rect.x, rect.y, max(150, rect.width // 2), rect.height)
                    col = SY_VIOLET if pulse else (90, 165, 255)
                    pygame.draw.rect(screen, (24, 22, 34) if pulse else (18, 24, 34), box)
                    pygame.draw.rect(screen, col, box, 2)
                    vs = font.render("0x02  PULSE" if pulse else "0x01  LEVEL", True, col)
                    screen.blit(vs, (box.x + 6, box.y + (box.height - vs.get_height()) // 2))
                    hs = small_font.render("(click to change)", True, (140, 145, 160))
                    screen.blit(hs, (box.right + 8, box.y + (box.height - hs.get_height()) // 2))
                else:
                    pygame.draw.rect(screen, (18, 20, 26), rect)
                    pygame.draw.rect(screen, AC_BLUE if focused else (90, 100, 120), rect, 2)
                    _ed = tb("ac", fk, ac_modal["fields"].get(fk, ""))
                    field_scroll[fk] = tb_draw(screen, font, _ed, rect, focused,
                                               field_scroll.get(fk, 0))
                    # Mini scrollbar, if the value is wider than its box
                    _tw = font.size(_ed.text)[0]
                    if _tw > rect.width - 12:
                        scroll_offset = field_scroll[fk]
                        max_scroll = min(0, rect.width - _tw - 12)
                        sb_width = max(10, int((rect.width / _tw) * rect.width))
                        sb_x = rect.x + int(
                            (-scroll_offset / -max_scroll) * (rect.width - sb_width)) if max_scroll < 0 else rect.x
                        pygame.draw.rect(screen, (100, 100, 100), (rect.x, rect.bottom - 4, rect.width, 4))
                        pygame.draw.rect(screen, AC_BLUE if focused else (150, 150, 150),
                                         (sb_x, rect.bottom - 4, sb_width, 4))
                    if fk in LIST_FIELDS and focused:
                        ds = small_font.render("double-click: list editor", True,
                                               (120, 130, 150))
                        screen.blit(ds, (rect.right - ds.get_width() - 6,
                                         rect.bottom + 1))
                if fk == "folder":
                    bs = small_font.render("click to browse", True, (140, 145, 160))
                    screen.blit(bs, (rect.right - bs.get_width() - 6,
                                     rect.y + (rect.height - bs.get_height()) // 2))
                if fk == "mac" and "mac" in ac_field_rects:
                    ml_hov = ac_maclookup_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(screen, (30, 40, 55), ac_maclookup_rect)
                    pygame.draw.rect(screen, AC_BLUE if ml_hov else (80, 120, 170), ac_maclookup_rect, 2)
                    mls = small_font.render("Lookup IP", True, AC_BLUE if ml_hov else (150, 180, 220))
                    screen.blit(mls, (ac_maclookup_rect.centerx - mls.get_width() // 2,
                                      ac_maclookup_rect.centery - mls.get_height() // 2))
            if ac_modal.get("msg"):
                msg_c = (230, 90, 90) if ac_modal.get("msg_is_error") else (200, 200, 120)
                ms = small_font.render(ac_modal["msg"], True, msg_c)
                screen.blit(ms, (ac_panel.x + 18, ac_ok_rect.y - 20))
            for rect, label, col in ((ac_ok_rect, "Save", (40, 190, 90)),
                                     (ac_cancel_rect, "Cancel", (200, 80, 80))):
                hov = rect.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (30, 30, 34), rect)
                pygame.draw.rect(screen, col, rect, 2)
                ls = font.render(label, True, col if not hov else (255, 255, 255))
                screen.blit(ls, (rect.centerx - ls.get_width() // 2, rect.centery - ls.get_height() // 2))

        # ── Link modal (on top of everything) ────────────────────────────
        if link_modal is not None:
            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 140)); screen.blit(dim, (0, 0))
            pygame.draw.rect(screen, (30, 32, 40), lk_panel, border_radius=8)
            pygame.draw.rect(screen, LINK_CYAN, lk_panel, 2, border_radius=8)
            ttl = header_font.render(f"Link — {link_modal['src']}", True, LINK_CYAN)
            screen.blit(ttl, (lk_panel.x + 16, lk_panel.y + 12))
            hint = small_font.render("Enter: link   Esc: cancel", True, (150, 150, 150))
            screen.blit(hint, (lk_panel.right - hint.get_width() - 14, lk_panel.y + 16))

            rect = lk_field_rects["dst"]
            ls = font.render("Push into", True, (200, 210, 230))
            screen.blit(ls, (lk_panel.x + 18, rect.y + (rect.height - ls.get_height()) // 2))
            pygame.draw.rect(screen, (18, 20, 26), rect)
            pygame.draw.rect(screen, LINK_CYAN, rect, 2)
            typed = str(link_modal["fields"].get("dst", ""))
            _ed = tb("link", "dst", typed)
            link_modal["scroll"] = tb_draw(screen, font, _ed, rect, True,
                                           link_modal.get("scroll", 0))

            # What the link will DO, spelled out with the names in it. The
            # direction is the one thing that is easy to get backwards, and
            # reading it here costs nothing.
            flow = small_font.render(
                f"{link_modal['src']}  ──▶  {typed or '?'}"
                f"      (every change to {link_modal['src']} is written there)",
                True, LINK_CYAN_DIM)
            screen.blit(flow, (lk_panel.x + 18, rect.bottom + 8))

            if link_modal.get("msg"):
                msg_c = (230, 90, 90) if link_modal.get("msg_is_error") else (200, 200, 120)
                ms = small_font.render(link_modal["msg"], True, msg_c)
                screen.blit(ms, (lk_panel.x + 18, lk_ok_rect.y - 20))
            for r, label, col in ((lk_ok_rect, "Link", (40, 190, 90)),
                                  (lk_cancel_rect, "Cancel", (200, 80, 80))):
                hov = r.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (30, 30, 34), r)
                pygame.draw.rect(screen, col, r, 2)
                ls2 = font.render(label, True, col if not hov else (255, 255, 255))
                screen.blit(ls2, (r.centerx - ls2.get_width() // 2,
                                  r.centery - ls2.get_height() // 2))

        # ── Network topology (on top of everything) ──────────────────────
        # A picture rather than a list, because the question it answers is
        # "how many machines am I talking to and which ones are answering" --
        # which is a shape, not a table. Green ring = answering, red = not,
        # grey = configured but never yet seen.
        #
        # Every size comes from net_m, which is derived from the window, so
        # the diagram grows and shrinks with it instead of sitting at one
        # fixed size inside a panel that resizes around it.
        if net_modal is not None:
            _t = net_modal["target"]
            _s = net_m["s"]
            _pad = net_m["pad"]
            f_big = _net_font(int(20 * _s), bold=True)
            f_mid = _net_font(int(15 * _s))
            f_sm = _net_font(max(9, int(12 * _s)))

            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 170)); screen.blit(dim, (0, 0))
            pygame.draw.rect(screen, (26, 28, 36), net_panel, border_radius=10)
            pygame.draw.rect(screen, SY_VIOLET, net_panel, 2, border_radius=10)
            # the title bar is the drag handle, so it is drawn as one
            pygame.draw.rect(screen, (32, 34, 46),
                             (net_panel.x + 2, net_panel.y + 2,
                              net_panel.width - 4, net_m["head"] - 4),
                             border_top_left_radius=8, border_top_right_radius=8)

            _cfg = syncpeer_config(_t)
            _delta = sy_is_delta(_t, _cfg)
            ttl = f_big.render(
                f"Network — {_t}   [{'DELTA' if _delta else 'STAR'}]",
                True, SY_VIOLET)
            screen.blit(ttl, (net_panel.x + _pad, net_panel.y + max(6, int(10 * _s))))
            hint = f_sm.render("drag this bar to move    Esc: close    Tab: IP/MAC",
                               True, (150, 150, 150))
            screen.blit(hint, (net_panel.right - hint.get_width() - _pad,
                               net_panel.y + max(8, int(14 * _s))))

            peers = sy_peer_states(_t)
            _macs = sy_macs(_t, _cfg)
            up_n = sum(1 for _h, st in peers if st)

            my_mac = local_mac()
            summary = f_sm.render(
                f"{up_n}/{len(peers)} answering    this machine: "
                f"{get_lan_ip()}:{PORT}" + (f"  {my_mac}" if my_mac else ""),
                True, (170, 175, 195))
            screen.blit(summary, (net_panel.x + _pad,
                                  net_panel.y + net_m["head"] - max(12, int(16 * _s))))

            # ── the diagram, inside whatever vertical room is left ────────
            top = net_panel.y + net_m["head"] + _pad
            bottom = net_m["diagram_bottom"]
            me_y = top + net_m["me"] + max(8, int(10 * _s))
            base_y = bottom - max(26, int(40 * _s))
            me_x = net_panel.centerx
            n = max(1, len(peers))
            span = net_panel.width - 2 * (_pad + net_m["node"])
            step = span // n

            def _peer_x(i):
                return net_panel.x + _pad + net_m["node"] + step * i + step // 2

            # ── the peer-to-peer edges, delta only ───────────────────────
            # Drawn BEFORE the nodes and the spokes so they sit underneath
            # rather than over the circles, and as brackets rising above the
            # row rather than straight chords -- a straight line from peer 1 to
            # peer 3 would run through peer 2 and read as a link to it.
            if _delta and len(peers) > 1:
                for i in range(len(peers)):
                    for j in range(i + 1, len(peers)):
                        both = peers[i][1] and peers[j][1]
                        ec = (60, 210, 90) if both else (110, 100, 130)
                        lift = net_m["node"] + max(6, int(9 * _s)) * (j - i)
                        y0 = base_y - net_m["node"]
                        yt = max(me_y + net_m["me"] + 2, y0 - lift)
                        pygame.draw.lines(
                            screen, ec, False,
                            [(_peer_x(i), y0), (_peer_x(i), yt),
                             (_peer_x(j), yt), (_peer_x(j), y0)],
                            max(1, int(2 * _s)))

            for i, (host, state) in enumerate(peers):
                px = _peer_x(i)
                col = ((60, 210, 90) if state else
                       ((215, 60, 60) if state is False else (120, 120, 130)))
                pygame.draw.line(screen, col, (me_x, me_y + net_m["me"]),
                                 (px, base_y - net_m["node"]), 2)
                pygame.draw.circle(screen, col,
                                   ((me_x + px) // 2,
                                    (me_y + net_m["me"] + base_y - net_m["node"]) // 2),
                                   max(2, int(3 * _s)))
                pygame.draw.circle(screen, (18, 20, 26), (px, base_y), net_m["node"])
                pygame.draw.circle(screen, col, (px, base_y), net_m["node"], max(2, int(3 * _s)))
                ic = f_sm.render("PC", True, col)
                screen.blit(ic, (px - ic.get_width() // 2, base_y - ic.get_height() // 2))
                # Labels are clipped to their own slot, so a long address on a
                # crowded diagram cannot run into its neighbour.
                lab_y = base_y + net_m["node"] + max(3, int(5 * _s))
                slot = pygame.Rect(px - step // 2, lab_y, step, max(30, int(46 * _s)))
                screen.set_clip(slot)
                hs = f_sm.render(host, True, (220, 225, 240))
                screen.blit(hs, (px - hs.get_width() // 2, lab_y))
                st = f_sm.render("UP" if state else ("DOWN" if state is False else "unseen"),
                                 True, col)
                screen.blit(st, (px - st.get_width() // 2, lab_y + hs.get_height() + 1))
                if i < len(_macs) and _macs[i]:
                    ms2 = f_sm.render(_macs[i], True, LINK_CYAN_DIM)
                    screen.blit(ms2, (px - ms2.get_width() // 2,
                                      lab_y + hs.get_height() * 2 + 2))
                screen.set_clip(None)

            pygame.draw.circle(screen, (20, 24, 34), (me_x, me_y), net_m["me"])
            pygame.draw.circle(screen, SY_VIOLET, (me_x, me_y), net_m["me"], max(2, int(3 * _s)))
            ms_ = f_mid.render("THIS", True, SY_VIOLET)
            screen.blit(ms_, (me_x - ms_.get_width() // 2, me_y - ms_.get_height() // 2))
            leg = f_sm.render(
                ("delta — every machine also talks to every other; "
                 "this one relays, so it has to stay on"
                 if _delta else
                 "star — the peers reach this machine and no other; "
                 "edit the sync to make it a delta"),
                True, SY_VIOLET_DIM)
            screen.blit(leg, (net_panel.x + _pad, me_y - net_m["me"] - leg.get_height() - 2))

            # ── the editable rows ────────────────────────────────────────
            net_modal.setdefault("scroll", {})
            for rect, key, label in ((net_field_rect, "hosts", "Peer IPs"),
                                     (net_mac_rect, "macs", "Peer MACs")):
                focused = net_modal.get("focus", "hosts") == key
                ls = f_mid.render(label, True, (200, 210, 230))
                screen.blit(ls, (net_panel.x + _pad,
                                 rect.y + (rect.height - ls.get_height()) // 2))
                pygame.draw.rect(screen, (18, 20, 26), rect)
                pygame.draw.rect(screen, SY_VIOLET if focused else (90, 100, 120), rect, 2)
                _ed = tb("net", key, net_modal["fields"].get(key, ""))
                net_modal["scroll"][key] = tb_draw(
                    screen, f_mid, _ed, rect, focused,
                    net_modal["scroll"].get(key, 0))
                if focused:
                    ds = f_sm.render("double-click: list editor", True,
                                     (120, 130, 150))
                    screen.blit(ds, (rect.right - ds.get_width() - 6,
                                     rect.bottom + 1))

            # the machines the scan found — click to add or remove
            for r, host in zip(net_found_rects, net_modal.get("found") or []):
                inlist = host in [h.strip() for h in
                                  str(net_modal["fields"]["hosts"]).split(",")]
                col = (60, 210, 90) if inlist else LINK_CYAN
                pygame.draw.rect(screen, (22, 30, 34), r)
                pygame.draw.rect(screen, col, r, 2)
                cs = f_sm.render(("- " if inlist else "+ ") + host, True, col)
                screen.blit(cs, (r.centerx - cs.get_width() // 2,
                                 r.centery - cs.get_height() // 2))
            if not net_modal.get("found"):
                note = f_sm.render(
                    "one MAC per peer, in the same order — a peer with a MAC "
                    "finds itself again when its address changes",
                    True, (140, 145, 165))
                screen.blit(note, (net_field_rect.x, net_mac_rect.bottom + 3))

            if net_modal.get("msg"):
                mc = (230, 90, 90) if net_modal.get("msg_is_error") else (200, 200, 120)
                msg = f_sm.render(net_modal["msg"], True, mc)
                screen.set_clip(pygame.Rect(net_panel.x + _pad, net_ok_rect.y - 18,
                                            net_panel.width - 2 * _pad, 18))
                screen.blit(msg, (net_panel.x + _pad, net_ok_rect.y - 17))
                screen.set_clip(None)
            for r, label, col in ((net_ok_rect, "Save", (40, 190, 90)),
                                  (net_scan_rect, "Scan network", SY_VIOLET),
                                  (net_close_rect, "Close", (200, 80, 80))):
                hov = r.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (30, 30, 34), r)
                pygame.draw.rect(screen, col, r, 2)
                ls3 = f_mid.render(label, True, col if not hov else (255, 255, 255))
                screen.set_clip(r)
                screen.blit(ls3, (r.centerx - ls3.get_width() // 2,
                                  r.centery - ls3.get_height() // 2))
                screen.set_clip(None)

        # Pick up a finished network scan.
        if net_modal is not None and net_scan_result:
            hosts = net_scan_result.pop()
            net_modal["found"] = hosts
            here = [h for h in local_ipv4s()]
            net_modal["msg"] = (
                f"{len(hosts)} machine(s) answering on this port"
                + (" — click one to add or remove it" if hosts else
                   "; nothing else is running ignoAPI on these subnets")
                + (f"   (this machine: {', '.join(here)})" if here else ""))
            net_modal["msg_is_error"] = not hosts

        # Pick up a finished MAC lookup.
        if ac_modal is not None and mac_lookup_result:
            _m, _found = mac_lookup_result.pop()
            if _found:
                cur = str(ac_modal["fields"].get("server_ip", "")).strip()
                # In a peer LIST the found address is added, not substituted:
                # replacing the list would quietly delete the other peers.
                if ac_kind == "sync" and "," in cur:
                    parts = [p.strip() for p in cur.split(",") if p.strip()]
                    if _found not in parts:
                        parts.append(_found)
                    ac_modal["fields"]["server_ip"] = ",".join(parts)
                    ac_modal["msg"] = f"{_found} found from MAC — added to the list"
                else:
                    ac_modal["fields"]["server_ip"] = _found
                    ac_modal["msg"] = f"{_found} found from MAC"
                ac_modal["msg_is_error"] = False
            else:
                ac_modal["msg"] = (f"{norm_mac(_m)} did not answer — it is off, "
                                   f"on another subnet, or the MAC is wrong")
                ac_modal["msg_is_error"] = True

        # Pick up a finished autodetect (it runs off-thread so the UI keeps
        # drawing while each port is probed).
        if cc_modal is not None and cc_modal_detect_result:
            _found, _rep = cc_modal_detect_result.pop()
            if _found:
                cc_modal["fields"]["port"] = _found
                if _found not in (cc_modal.get("ports") or []):
                    cc_modal["ports"] = list_com_ports()
                cc_modal["msg"] = f"found {_found} — it answered OK"
                cc_modal["msg_is_error"] = False
            else:
                cc_modal["msg"] = "no port answered OK (see console for detail)"
                cc_modal["msg_is_error"] = True

        # ── COM client create/edit modal (on top of everything) ───────────
        if cc_modal is not None:
            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 140)); screen.blit(dim, (0, 0))
            _msk = (cc_kind == "modbusslave")
            _mbk = (cc_kind == "modbus") or _msk
            ACC = MB_GREEN if _mbk else COM_YELLOW
            pygame.draw.rect(screen, (20, 34, 30) if _mbk else (34, 32, 22),
                             cc_panel, border_radius=8)
            pygame.draw.rect(screen, ACC, cc_panel, 2, border_radius=8)
            _what = (" MODBUS Slave — " if _msk else
                     (" MODBUS Master — " if _mbk else " COM Client — "))
            ttl = header_font.render(
                ("Create" if cc_modal["mode"] == "create" else "Edit")
                + _what + f"{cc_modal['target']}",
                True, ACC)
            screen.blit(ttl, (cc_panel.x + 16, cc_panel.y + 12))
            hint = small_font.render("Tab: next   Enter: save   Esc: cancel", True, (150, 150, 150))
            screen.blit(hint, (cc_panel.right - hint.get_width() - 14, cc_panel.y + 16))

            for fk, lbl in cc_field_defs:
                rect = cc_field_rects[fk]
                ls = font.render(lbl, True, (235, 225, 180))
                screen.blit(ls, (cc_panel.x + 18, rect.y + (rect.height - ls.get_height()) // 2))
                focused = (cc_modal["focus"] == fk)

                if fk in ("runatstartup", "persist_csv"):
                    on = str(cc_modal["fields"].get(fk, "false")).lower() in ("true", "1", "yes", "on")
                    box = pygame.Rect(rect.x, rect.y, 60, rect.height)
                    pygame.draw.rect(screen, (25, 70, 35) if on else (60, 30, 30), box)
                    pygame.draw.rect(screen, (40, 200, 70) if on else (200, 70, 70), box, 2)
                    vs = font.render("TRUE" if on else "FALSE", True,
                                     (40, 200, 70) if on else (210, 90, 90))
                    screen.blit(vs, (box.x + 6, box.y + (box.height - vs.get_height()) // 2))
                elif fk in cc_drop_fields:
                    # dropdown: closed shows the value + a caret
                    pygame.draw.rect(screen, (22, 20, 14), rect)
                    pygame.draw.rect(screen, ACC if focused else (120, 110, 60), rect, 2)
                    txt = str(cc_modal["fields"].get(fk, ""))
                    vs = font.render(txt, True, (255, 250, 220))
                    screen.set_clip(rect)
                    screen.blit(vs, (rect.x + 6, rect.y + (rect.height - vs.get_height()) // 2))
                    screen.set_clip(None)
                    cs = font.render("v", True, ACC)
                    screen.blit(cs, (rect.right - 18, rect.y + (rect.height - cs.get_height()) // 2))
                else:
                    pygame.draw.rect(screen, (22, 20, 14), rect)
                    pygame.draw.rect(screen, ACC if focused else (120, 110, 60), rect, 2)
                    _ed = tb("cc", fk, cc_modal["fields"].get(fk, ""))
                    field_scroll[fk] = tb_draw(screen, font, _ed, rect, focused,
                                               field_scroll.get(fk, 0),
                                               text_col=(255, 250, 220))
                    # Mini scrollbar, if the value is wider than its box
                    _tw = font.size(_ed.text)[0]
                    if _tw > rect.width - 12:
                        scroll_offset = field_scroll[fk]
                        max_scroll = min(0, rect.width - _tw - 12)
                        sb_width = max(10, int((rect.width / _tw) * rect.width))
                        sb_x = rect.x + int(
                            (-scroll_offset / -max_scroll) * (rect.width - sb_width)) if max_scroll < 0 else rect.x
                        pygame.draw.rect(screen, (100, 100, 100), (rect.x, rect.bottom - 4, rect.width, 4))
                        pygame.draw.rect(screen, ACC if focused else (150, 150, 150),
                                         (sb_x, rect.bottom - 4, sb_width, 4))

                if fk == "port":
                    rf_hov = cc_refresh_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(screen, (48, 44, 24), cc_refresh_rect)
                    pygame.draw.rect(screen, ACC if rf_hov else (140, 125, 60), cc_refresh_rect, 2)
                    rs = small_font.render("Rescan", True,
                                           ACC if rf_hov else (215, 205, 150))
                    screen.blit(rs, (cc_refresh_rect.centerx - rs.get_width() // 2,
                                     cc_refresh_rect.centery - rs.get_height() // 2))
                if fk == "register_map":
                    br_hov = cc_browse_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(screen, (24, 48, 40), cc_browse_rect)
                    pygame.draw.rect(screen, ACC if br_hov else (60, 130, 105),
                                     cc_browse_rect, 2)
                    bs = small_font.render("Browse", True,
                                           ACC if br_hov else (150, 210, 190))
                    screen.blit(bs, (cc_browse_rect.centerx - bs.get_width() // 2,
                                     cc_browse_rect.centery - bs.get_height() // 2))
                if fk == "probe":
                    dt_hov = cc_detect_rect.collidepoint(mouse_pos)
                    pygame.draw.rect(screen, (48, 44, 24), cc_detect_rect)
                    pygame.draw.rect(screen, ACC if dt_hov else (140, 125, 60),
                                     cc_detect_rect, 2)
                    ds = small_font.render("Detect", True,
                                           ACC if dt_hov else (215, 205, 150))
                    screen.blit(ds, (cc_detect_rect.centerx - ds.get_width() // 2,
                                     cc_detect_rect.centery - ds.get_height() // 2))
                if fk == "command":
                    note = small_font.render(
                        f"{CC_LISTEN_CMD} = listen to everything; anything else is sent, reply stored",
                        True, (170, 160, 110))
                    screen.blit(note, (rect.x, rect.bottom + 2))
                if _mbk and not _msk and fk == "bytesize":
                    # Name the rows this master will create, right where the
                    # user is deciding to create it -- five new variables
                    # appearing unannounced is otherwise a surprise.
                    note = small_font.render(
                        "creates: " + ", ".join(mm_sub_vars(cc_modal["target"])),
                        True, (110, 180, 150))
                    screen.blit(note, (rect.x, rect.bottom + 2))
                if _msk and fk == "persist_csv":
                    note = small_font.render(
                        "off: the CSV is the initial map only. on: a master's "
                        "writes are saved back over it.",
                        True, (110, 180, 150))
                    screen.blit(note, (rect.x, rect.bottom + 2))

            if cc_modal.get("msg"):
                msg_c = (230, 90, 90) if cc_modal.get("msg_is_error") else (215, 205, 130)
                ms = small_font.render(cc_modal["msg"], True, msg_c)
                screen.blit(ms, (cc_panel.x + 18, cc_ok_rect.y - 20))

            for rect, label, col in ((cc_ok_rect, "Save", (40, 190, 90)),
                                     (cc_cancel_rect, "Cancel", (200, 80, 80))):
                hov = rect.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (30, 30, 34), rect)
                pygame.draw.rect(screen, col, rect, 2)
                ls = font.render(label, True, col if not hov else (255, 255, 255))
                screen.blit(ls, (rect.centerx - ls.get_width() // 2,
                                 rect.centery - ls.get_height() // 2))

            # The open dropdown is drawn LAST so it sits over the fields below
            # it — otherwise the list is painted under them and unclickable.
            if cc_dropdown is not None:
                for opt, r in zip(_cc_dropdown_options(cc_dropdown),
                                  _cc_dropdown_rects(cc_dropdown)):
                    hov = r.collidepoint(mouse_pos)
                    pygame.draw.rect(screen, (58, 54, 30) if hov else (26, 24, 16), r)
                    pygame.draw.rect(screen, ACC, r, 1)
                    sel = (str(cc_modal["fields"].get(cc_dropdown, "")) == opt)
                    oc = (255, 255, 255) if hov else (ACC if sel else (215, 205, 150))
                    os_ = small_font.render(opt, True, oc)
                    screen.blit(os_, (r.x + 8, r.y + (r.height - os_.get_height()) // 2))

        # ── List editor (above the form that opened it) ───────────────────
        # The same value as the single-line box, laid out the way a list wants
        # to be read: one entry per numbered row, with a caret you can put
        # anywhere. Enter starts a new entry; ctrl+Enter saves.
        if list_modal is not None:
            dim = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 150)); screen.blit(dim, (0, 0))
            pygame.draw.rect(screen, (26, 28, 36), ls_panel, border_radius=8)
            pygame.draw.rect(screen, LINK_CYAN, ls_panel, 2, border_radius=8)
            ttl = header_font.render(f"{list_modal.get('title', 'List')} — one per line",
                                     True, LINK_CYAN)
            screen.blit(ttl, (ls_panel.x + 16, ls_panel.y + 12))
            hint = small_font.render("Ctrl+Enter: save   Esc: cancel",
                                     True, (150, 150, 150))
            screen.blit(hint, (ls_panel.right - hint.get_width() - 14,
                               ls_panel.y + 16))
            pygame.draw.rect(screen, (16, 18, 24), ls_area)
            pygame.draw.rect(screen, (70, 90, 110), ls_area, 1)
            _ed = tb("list", "text", list_modal["text"], multiline=True)
            list_modal["top"] = tb_draw_lines(screen, font, _ed, ls_area,
                                              list_modal.get("top", 0))
            _n = len([l for l in _ed.text.splitlines() if l.strip()])
            cs = small_font.render(f"{_n} entr{'y' if _n == 1 else 'ies'}",
                                   True, (140, 150, 170))
            screen.blit(cs, (ls_area.x, ls_area.bottom + 4))
            _btns = [(ls_ok_rect, "Save", (40, 190, 90)),
                     (ls_cancel_rect, "Cancel", (200, 80, 80))]
            if ls_pick_rect.width:
                _btns.insert(1, (ls_pick_rect, "Select files...", EXEC_RED))
            for rect, label, col in _btns:
                hov = rect.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (30, 30, 34), rect)
                pygame.draw.rect(screen, col, rect, 2)
                ls = font.render(label, True, col if not hov else (255, 255, 255))
                screen.blit(ls, (rect.centerx - ls.get_width() // 2,
                                 rect.centery - ls.get_height() // 2))

        # ── Right-click context menu (topmost) ────────────────────────────
        if ctx_menu is not None:
            cx, cy = ctx_menu["pos"]
            mw = CTX_MENU_W
            for idx, (label, enabled) in enumerate(ctx_menu["items"]):
                r = pygame.Rect(cx, cy + idx * CTX_ITEM_H, mw, CTX_ITEM_H)
                hov = r.collidepoint(mouse_pos)
                pygame.draw.rect(screen, (48, 52, 62) if hov else (34, 36, 44), r)
                pygame.draw.rect(screen, (80, 90, 110), r, 1)
                if label in ("COM Client", "Edit COM Client",
                             "COM Reconnect", "COM Disconnect"):
                    col = COM_YELLOW
                elif label in ("MODBUS Master", "Edit MODBUS Master",
                               "MODBUS Slave", "Edit MODBUS Slave",
                               "MODBUS Reconnect", "MODBUS Disconnect",
                               "Clear command"):
                    col = MB_GREEN
                elif label in ("Create Autoclient", "Edit Autoclient", "Reconnect", "Disconnect"):
                    col = AC_BLUE
                elif label in ("Add EXE files...", "Clear list", "Toggle ON/OFF"):
                    col = EXEC_RED
                elif label == "Combine":
                    col = CMB_ORANGE
                elif label == "Delete":
                    col = (215, 90, 90)
                else:
                    col = (220, 220, 220)
                ls = small_font.render(label, True, col if enabled else (100, 100, 100))
                screen.blit(ls, (r.x + 10, r.y + (r.height - ls.get_height()) // 2))

        # ── THE COMBINE PICKER ────────────────────────────────────────
        # A banner rather than a modal: the whole point is picking rows in
        # the table underneath, so it must not cover them.
        if combine_pick is not None:
            _cn = combine_pick["names"]
            _cw = min(WINDOW_WIDTH - 40, 620)
            _ch = 78
            _cx = (WINDOW_WIDTH - _cw) // 2
            _cy = WINDOW_HEIGHT - _ch - 18
            _panel = pygame.Surface((_cw, _ch), pygame.SRCALPHA)
            _panel.fill((26, 20, 12, 244))
            screen.blit(_panel, (_cx, _cy))
            pygame.draw.rect(screen, CMB_ORANGE, (_cx, _cy, _cw, _ch), 2)
            _t = small_font.render(
                "COMBINE into  %s" % combine_pick["target"], True, CMB_ORANGE)
            screen.blit(_t, (_cx + 12, _cy + 8))
            _hint = ("click variable names to pick them   "
                     "Enter: combine   Esc: cancel"
                     if _cn else
                     "click the variable names to combine   Esc: cancel")
            screen.blit(small_font.render(_hint, True, (170, 150, 120)),
                        (_cx + 12, _cy + _ch - 20))
            # what has been picked, in the order it was picked, because
            # that is the order the values will appear in
            _sel = ", ".join("%d.%s" % (i + 1, n) for i, n in enumerate(_cn))
            _box = pygame.Rect(_cx + 12, _cy + 28, _cw - 24, 22)
            pygame.draw.rect(screen, (16, 12, 8), _box)
            pygame.draw.rect(screen, CMB_ORANGE_DIM, _box, 1)
            _st = small_font.render(_sel or "(nothing picked yet)", True,
                                    CMB_ORANGE if _cn else (120, 105, 85))
            _clip = screen.get_clip()
            screen.set_clip(_box.inflate(-6, -2))
            screen.blit(_st, (_box.x + 5, _box.y + 3))
            screen.set_clip(_clip)

        # ── THE QUIT QUESTION ─────────────────────────────────────────
        if quit_modal is not None:
            _veil = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
            _veil.set_alpha(170)
            _veil.fill((0, 0, 0))
            screen.blit(_veil, (0, 0))
            _qw, _qh = 430, 158
            _qx, _qy = (WINDOW_WIDTH - _qw) // 2, (WINDOW_HEIGHT - _qh) // 2
            pygame.draw.rect(screen, (30, 33, 40), (_qx, _qy, _qw, _qh), border_radius=8)
            pygame.draw.rect(screen, (215, 90, 90), (_qx, _qy, _qw, _qh), 2,
                             border_radius=8)
            screen.blit(font.render("Close ignoAPI?", True, (255, 235, 235)),
                        (_qx + 20, _qy + 16))
            screen.blit(small_font.render(
                "Autoclients, COM readers, MODBUS and sync children keep",
                True, (170, 178, 190)), (_qx + 20, _qy + 46))
            screen.blit(small_font.render(
                "running unless they were told to stop.",
                True, (170, 178, 190)), (_qx + 20, _qy + 62))
            _qbtn = []
            for _i, _lbl in enumerate(("Close", "Stay")):
                _r = pygame.Rect(_qx + 20 + _i * 200, _qy + _qh - 48, 185, 32)
                _on = (quit_modal["sel"] == _i)
                _hov = _r.collidepoint(mouse_pos)
                _c = ((215, 90, 90) if _i == 0 else (70, 110, 165))
                if not _on:
                    _c = tuple(int(x * 0.55) for x in _c)
                if _hov:
                    _c = tuple(min(255, x + 40) for x in _c)
                pygame.draw.rect(screen, _c, _r, border_radius=6)
                _ts = small_font.render(_lbl, True, (255, 255, 255))
                screen.blit(_ts, (_r.centerx - _ts.get_width() // 2,
                                  _r.centery - _ts.get_height() // 2))
                _qbtn.append(_r)
            quit_modal["rects"] = _qbtn
            screen.blit(small_font.render(
                "Enter: choose   left/right: swap   Y / N   Esc: stay",
                True, (120, 128, 140)), (_qx + 20, _qy + _qh - 14))
        pygame.display.flip()
        clock.tick(30)

    print("\n[ignoAPI] Shutting down visualizer and server...")
    _flush_to_disk()
    _stop_all_autoclients()
    _stop_all_execs()
    pygame.quit()
    sys.exit()
# ──────────────────────────────────────────────────────────────
# MAIN EXECUTION
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # From here on this IS the application, so it may start its children.
    _RUNNING_AS_APP = True
    api_thread = threading.Thread(target=start_server, daemon=True)
    api_thread.start()
    run_visualizer()