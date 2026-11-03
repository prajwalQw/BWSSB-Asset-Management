"""
ROBOT CONNECTOR
============================================================

DISCOVERY MODES
---------------

1. mDNS MODE
   Scans:

       ignoapi_rob1.local
       ignoapi_rob2.local
       ...
       ignoapi_rob99.local

2. UDP MODE
   Uses the same discovery method as ignodiscover.py:

       Broadcast:  ignoAPI?
       UDP Port:   8899

   Expected reply:

       <ip>,<name>,<port>

   Example:

       192.168.1.101,ignoapi_rob1.local,8899

FEATURES
--------

- Borderless fullscreen-sized window
- Military radar UI
- Animated radar sweep
- mDNS / UDP switch
- mDNS hostname scanning
- UDP broadcast discovery
- Connect selected robot
- Connect all robots
- Scrollable robot list
- Robot status display
- ESC to exit
- R to manually rescan

INSTALL
-------

    pip install pygame

"""

import math
import os
import platform
import random
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import pygame

# ignoClient.py lives in the same folder as this file, so a plain
# import finds it without needing sys.path touched.
import ignoClient as c


# ============================================================
# CONFIGURATION
# ============================================================

FPS = 60


# ============================================================
# mDNS CONFIGURATION
# ============================================================

HOSTNAME_PREFIX = "ignoapi_rob"

ROBOT_START = 1
ROBOT_END = 99

# Port used if mDNS hostname resolution succeeds.
# Change this if your ignoAPI TCP server uses another port.
MDNS_TCP_PORT = 8899

MDNS_SCAN_WORKERS = 20

MDNS_SCAN_INTERVAL = 8.0


# ============================================================
# UDP DISCOVERY CONFIGURATION
# ============================================================

DISCOVER_PORT = 8899

PROBE = "ignoAPI?"

RECV_SIZE = 512

UDP_SCAN_TIMEOUT = 1.5

UDP_SCAN_INTERVAL = 5.0


# ============================================================
# MAC / ARP DISCOVERY CONFIGURATION
#   A typed-in MAC address is resolved to an IP via the OS ARP
#   table (topping it up with a sweep when the MAC isn't in it
#   yet), the same trick ignoAPI.py itself uses for its
#   MAC-based sync peers. Ported here as a small self-contained
#   copy rather than imported, because importing ignoAPI.py runs
#   its whole server (mDNS, watchdogs, tray icon) as an import-
#   time side effect.
# ============================================================

# Port used once a MAC resolves to an IP -- same TCP port every
# other discovery mode in this file connects on.
MAC_TCP_PORT = 8899

MAC_SCAN_INTERVAL = 8.0

ARP_SWEEP_PORT = 9          # discard; nothing has to listen for ARP to happen

ARP_SWEEP_WORKERS = 64

ARP_SWEEP_SETTLE = 1.2      # seconds for replies to land in the OS ARP table

ARP_SWEEP_GRACE = 3.0       # extra seconds to keep re-reading the table for


# ============================================================
# TCP CONNECTION CONFIGURATION
# ============================================================

TCP_CONNECT_TIMEOUT = 2.0

# How many times the LINK workflow retries a single robot's connection
# before giving up on it and marking it SYNC FAILED.
SYNC_CONNECT_MAX_ATTEMPTS = 3

# Pause between retry attempts, so a robot that's momentarily busy
# (e.g. still booting its TCP server) gets a beat to recover.
SYNC_CONNECT_RETRY_DELAY = 1.0

# After creating the star syncs on the hub, the hub still has to
# provision the matching boxes (fleet_cid_tx / server_tx / their
# _rx / _status peers) across every robot in the background --
# createSyncIgnoAPI() returns once the hub has ACCEPTED the request,
# not once every peer is actually wired up. Per-robot link attempts
# that start too soon after this can hit a robot whose wiring isn't
# finished yet, which shows up as an intermittent "link did not
# propagate" failure that seems to move between robots run to run
# (whichever robot's fan-out happens to be slow that time). This
# fixed pause after both syncs are created gives that fan-out time
# to catch up before any per-robot link attempt starts.
SYNC_FANOUT_SETTLE_DELAY = 3.0

# How long RobotSyncManager.verify_server_links_on_hub() waits, after
# each robot's link is accepted, for that robot's data to show up in
# its server_rx box (server_<host_tag>_rx once a 2nd peer joins the
# sync) on the HUB before giving up and marking the robot SYNC
# FAILED. ignoAPI pushes the link's value automatically
# -- see the note in combine_and_link() -- so this is purely a passive
# wait, not a retry budget; it only needs to cover normal network/
# scheduling latency plus ignoAPI's own poll interval, on top of the
# star sync's own hop from the robot up to the hub.
LINK_PROPAGATION_TIMEOUT = 5.0

# If a robot still ends up SYNC FAILED after a LINK/RECONNECT run, keep
# retrying it automatically (no button click needed) until it comes up
# LINKED or this many extra rounds have been tried, whichever comes
# first. 0 disables auto-reconnect and restores the old "click
# RECONNECT FAILED yourself" behavior.
AUTO_RECONNECT_MAX_ATTEMPTS = 5

# Pause between automatic reconnect rounds, so a robot that's flaky
# or still booting gets a real beat to recover instead of being
# hammered every frame.
AUTO_RECONNECT_DELAY = 4.0


# ============================================================
# STAR SYNC / ID-FORWARDING CONFIGURATION
#   (same idea as make_sync.py: this machine is the hub, the robots
#   you tick in the list are the peers)
# ============================================================

SYNC_HUB = "127.0.0.1"

SYNC_API_PORT = MDNS_TCP_PORT

# The "server" sync: robot's r_id/battery/odometry/obstacle combined,
# then linked to server_tx.
SYNC_VARIABLE = "server"

# The "fleet_cid" sync: robot's c_id linked to fleet_cid_tx directly
# (single variable, no combine needed on the robot side). On the HUB,
# every connected robot's incoming c_id is combined and linked back
# into the hub's OWN fleet_cid_tx, so the combined roster broadcasts
# back out to the whole fleet.
FLEET_CID_VARIABLE = "fleet_cid"

# Every variable a robot needs before it can be synced. Checked on
# connect; anything missing is created (blank) rather than failing.
FLEET_VARIABLES = [
    "ADDRESS",
    "c_id",
    "r_id",
    "battery_percentage",
    "odometry",
    "obstacle",
    "magnetometer",
    "acknowledgement",
    "fleet_response",
    "execution", 
    "cline",
    "ignoController_status",
    "ignoBattery_status",
    "ignoVision_status",
    "ignoManual_status",
    "ignoServer_status",
    "ignoCommunicationPaint_status",
    "ignoCommunicationDisp_status",
    "RIGHT_MOTOR_ENCODER_VAL",
    "LEFT_MOTOR_ENCODER_VAL",
    "speed",
]


# ============================================================
# FLEET FTP CONFIGURATION
#   One FTP server on the hub, shared with every currently-linked
#   robot -- (re)created each time the linked-robot roster changes.
# ============================================================

FLEET_FTP_NAME = "fleet_ftp"

FLEET_FTP_FOLDER = r"C:\FleetShare"

FLEET_FTP_PORT = 2121

# How many times configure_fleet_ftp() retries the createFTP() RPC
# before giving up on a single LINK/RECONNECT run. run() itself is
# already re-entered on a timer by the AUTO_RECONNECT loop for any
# robot still SYNC FAILED, so this only needs to smooth over a
# transient failure (hub briefly unreachable, autoFTP.exe mid
# respawn) within one run, not retry forever.
FLEET_FTP_MAX_RETRY_ATTEMPTS = 5

# Pause between fleet-FTP retry attempts.
FLEET_FTP_RETRY_DELAY = 2.0

# The two ways the fleet FTP server's shared ftp:// link can address
# this (hub) machine.
FTP_LINK_MODE_MDNS = "MDNS"

FTP_LINK_MODE_IP = "IP"

FTP_LINK_MODES = [FTP_LINK_MODE_MDNS, FTP_LINK_MODE_IP]

# The ignoAPI variable that decides the hostname half of the link
# (see RobotSyncManager.configure_fleet_ftp() and ignoAPI.py's own
# "NAMING THIS MACHINE" section: ADDRESS set -> ftp://ignoapi_<addr>
# .local:PORT, ADDRESS blank -> falls back to this machine's LAN IP).
IGNOAPI_ADDRESS_VAR = "ADDRESS"


class AppSettings:
    """
    Live, user-editable settings for the sync/link workflow. Starts
    from the FLEET_FTP_FOLDER / FLEET_VARIABLES defaults above --
    changed from the in-app Settings panel (the gear icon), not by
    editing this file. RobotSyncManager reads these at call time,
    so a change here takes effect on the next LINK, no restart
    needed.
    """

    ftp_folder = FLEET_FTP_FOLDER

    variables = list(FLEET_VARIABLES)

    # MAC addresses typed into the MAC discovery panel -- each one
    # is resolved to an IP (via the ARP table) by MACRobotScanner.
    manual_macs = []

    # Whether the fleet FTP server's shared link reads
    # ftp://ignoapi_<address>.local:PORT (MDNS) or ftp://<lan ip>:PORT
    # (IP). See RobotSyncManager.configure_fleet_ftp().
    ftp_link_mode = FTP_LINK_MODE_MDNS


# ============================================================
# UI CONFIGURATION
# ============================================================

RADAR_WIDTH_RATIO = 0.66

PANEL_PADDING = 18

SWEEP_SPEED_DEGREES = 75.0

DEVICE_CARD_HEIGHT = 122

DEVICE_CARD_GAP = 8


# ============================================================
# DISCOVERY MODES
# ============================================================

MODE_MDNS = "MDNS"

MODE_UDP = "UDP"

MODE_MAC = "MAC"


# ============================================================
# ROBOT STATES
# ============================================================

ROBOT_DISCONNECTED = "ROBOT DISCONNECTED"

ROBOT_CONNECTING = "CONNECTING"

ROBOT_CONNECTED = "ROBOT CONNECTED"

CONNECTION_FAILED = "CONNECTION FAILED"


# ============================================================
# COLORS
# ============================================================
#
# A cleaner, slightly desaturated "modern HUD" palette:
# fewer near-duplicate greens, more deliberate contrast between
# background / surface / border / text layers.

BACKGROUND = (7, 12, 12)

RADAR_BACKGROUND = (9, 20, 18)

GRID_DARK = (18, 46, 40)

GRID = (30, 84, 68)

GREEN = (64, 235, 166)

GREEN_BRIGHT = (150, 255, 210)

TEXT_DIM = (117, 150, 143)

TEXT = (223, 245, 236)

PANEL_BG = (12, 20, 19)

PANEL_BG_ALT = (15, 24, 23)

CARD_BG = (17, 28, 27)

CARD_HOVER = (23, 38, 36)

CARD_SELECTED = (20, 48, 42)

CARD_BORDER = (34, 54, 50)

ACCENT = (64, 235, 166)

CONNECTED = (72, 235, 160)

CONNECTING = (245, 191, 92)

FAILED = (240, 96, 96)

DISCONNECTED = (110, 170, 235)

BUTTON_BG = (24, 46, 41)

BUTTON_HOVER = (32, 66, 57)

BUTTON_ACCENT = (35, 110, 84)

BUTTON_ACCENT_HOVER = (44, 140, 106)

BUTTON_DISABLED = (22, 28, 27)

BORDER = (40, 66, 60)

BORDER_BRIGHT = (64, 235, 166)

MODE_ACTIVE = (64, 235, 166)

MODE_INACTIVE = (24, 38, 35)

SLIDER_TRACK = (18, 30, 28)

SLIDER_KNOB = (64, 235, 166)

SHADOW = (0, 0, 0)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_local_ipv4s():
    """
    Get local IPv4 addresses.

    This follows the same basic idea used by ignodiscover.py:
    try to discover all local IPv4 addresses and ignore loopback.
    """

    addresses = []

    try:

        hostname = socket.gethostname()

        info_list = socket.getaddrinfo(
            hostname,
            None,
            socket.AF_INET
        )

        for info in info_list:

            ip_address = info[4][0]

            if (
                ip_address not in addresses and
                not ip_address.startswith("127.")
            ):

                addresses.append(
                    ip_address
                )

    except OSError:

        pass

    # Extra fallback.
    try:

        test_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        test_socket.connect(
            ("8.8.8.8", 80)
        )

        ip_address = (
            test_socket.getsockname()[0]
        )

        test_socket.close()

        if (
            ip_address not in addresses and
            not ip_address.startswith("127.")
        ):

            addresses.append(
                ip_address
            )

    except Exception:

        pass

    if not addresses:

        addresses.append(
            "0.0.0.0"
        )

    return addresses


_LOCAL_IPV4_CACHE = None


def get_local_ipv4s_cached():
    """
    Cached wrapper around get_local_ipv4s() -- discovery scans call this
    frequently (every mDNS/UDP pass) and the machine's own interfaces
    don't change mid-run, so there's no need to re-resolve every time.
    """

    global _LOCAL_IPV4_CACHE

    if _LOCAL_IPV4_CACHE is None:
        _LOCAL_IPV4_CACHE = set(get_local_ipv4s())

    return _LOCAL_IPV4_CACHE


def is_own_ip(ip_address):
    """
    True if `ip_address` belongs to this machine, so discovery results
    that are actually just this PC (e.g. a probe looped back, or a
    hostname that happens to resolve locally) can be filtered out
    before they're ever added to the registry as a "robot".
    """

    return ip_address in get_local_ipv4s_cached()


# ============================================================
# MAC / ARP HELPERS
#   Self-contained port of ignoAPI.py's norm_mac()/arp_table()/
#   arp_sweep()/ip_from_mac() -- see the MAC/ARP DISCOVERY
#   CONFIGURATION block above for why this isn't just imported.
# ============================================================

def norm_mac(mac):
    """
    A MAC in one shape: lower case, colon separated. Typed, pasted
    and OS-reported MACs differ in case and separator (aa-BB-cc vs
    AA:bb:CC), so comparing them as-written can miss a MAC that is
    plainly there.
    """

    digits = re.sub(
        r"[^0-9a-fA-F]", "", str(mac or "")
    ).lower()

    if len(digits) != 12:
        return str(mac or "").strip().lower().replace("-", ":")

    return ":".join(
        digits[k:k + 2] for k in range(0, 12, 2)
    )


def arp_table():
    """
    {mac: ip} for everything the OS currently has cached.
    """

    out = {}

    try:

        if platform.system() == "Windows":

            output = subprocess.check_output(
                "arp -a", shell=True,
                creationflags=getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                )
            ).decode(errors="ignore")

            pattern = re.compile(
                r"(\d+\.\d+\.\d+\.\d+)\s+([\da-fA-F][\da-fA-F:-]{10,})"
            )

        else:

            output = subprocess.check_output(
                "ip neigh show", shell=True
            ).decode(errors="ignore")

            pattern = re.compile(
                r"(\d+\.\d+\.\d+\.\d+).*lladdr\s+([\da-fA-F:]+)"
            )

    except Exception:

        return out

    for line in output.splitlines():

        match = pattern.search(line)

        if not match:
            continue

        ip_address, mac = match.groups()

        mac = norm_mac(mac)

        if mac and mac not in (
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00"
        ):
            out[mac] = ip_address

    return out


def arp_sweep():
    """
    Touch every address on this machine's local /24(s) so the OS
    ARP table fills in. One UDP datagram per host -- UDP because it
    needs no handshake, no reply and no privileges, and the ARP
    entry appears whether or not the datagram itself is accepted.
    (ICMP/ping is the obvious alternative and the wrong one: a stock
    Windows firewall blocks it by default.)
    """

    mine = [
        ip for ip in get_local_ipv4s()
        if ip and not ip.startswith("127.")
    ]

    if not mine:
        return 0

    targets = []

    prefixes = []

    for ip in mine:

        prefix = ip.rsplit(".", 1)[0]

        if prefix in prefixes:
            continue

        prefixes.append(prefix)

        targets += [
            f"{prefix}.{n}" for n in range(1, 255)
            if f"{prefix}.{n}" not in mine
        ]

    def touch(chunk):

        try:

            sock = socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM
            )

            sock.settimeout(0.05)

            for host in chunk:

                try:
                    sock.sendto(b"\x00", (host, ARP_SWEEP_PORT))
                except OSError:
                    pass

            sock.close()

        except OSError:

            pass

    chunk_size = max(
        1, len(targets) // ARP_SWEEP_WORKERS
    )

    threads = []

    for k in range(0, len(targets), chunk_size):

        t = threading.Thread(
            target=touch,
            args=(targets[k:k + chunk_size],),
            daemon=True
        )

        t.start()

        threads.append(t)

    for t in threads:
        t.join(timeout=3.0)

    time.sleep(ARP_SWEEP_SETTLE)

    return len(targets)


_mac_ip_cache = {}          # mac -> last known good ip

_mac_ip_cache_lock = threading.Lock()


def ip_from_mac(target_mac, sweep=True):
    """
    Resolve an IPv4 from a MAC. Returns the IP, or None. Looks in
    the ARP table first; if the MAC isn't there and `sweep` is set,
    fills the table (arp_sweep()) and looks again -- on a quiet
    network the first look alone very often misses.
    """

    want = norm_mac(target_mac)

    if not want or len(want) != 17:
        return None

    table = arp_table()

    if want in table:

        with _mac_ip_cache_lock:
            _mac_ip_cache[want] = table[want]

        return table[want]

    if not sweep:
        return None

    arp_sweep()

    table = arp_table()

    deadline = time.time() + ARP_SWEEP_GRACE

    while want not in table and time.time() < deadline:

        time.sleep(0.25)

        table = arp_table()

    if want in table:

        with _mac_ip_cache_lock:
            _mac_ip_cache[want] = table[want]

        return table[want]

    # Fall back to the last address this MAC was seen at -- a
    # machine that's briefly unreachable has usually not moved, and
    # the caller can still fail honestly when it can't connect.
    with _mac_ip_cache_lock:
        return _mac_ip_cache.get(want)


def parse_udp_reply(text):
    """
    Parse:

        <ip>,<name>,<port>

    Example:

        192.168.1.10,ignoapi_rob1.local,8899

    The name may be empty:

        192.168.1.10,,8899
    """

    try:

        parts = [
            part.strip()
            for part in str(text).split(",")
        ]

        if len(parts) < 3:

            return None

        ip_address = parts[0]

        name = parts[1]

        port = int(
            parts[2]
        )

        if not ip_address:

            return None

        return {
            "ip": ip_address,
            "name": name,
            "port": port
        }

    except Exception:

        return None


def draw_text(
    surface,
    text,
    font,
    color,
    x,
    y,
    anchor="topleft"
):

    rendered = font.render(
        str(text),
        True,
        color
    )

    rect = rendered.get_rect()

    setattr(
        rect,
        anchor,
        (
            int(x),
            int(y)
        )
    )

    surface.blit(
        rendered,
        rect
    )

    return rect


def get_status_color(status):

    if status == ROBOT_CONNECTED:

        return CONNECTED

    if status == ROBOT_CONNECTING:

        return CONNECTING

    if status == CONNECTION_FAILED:

        return FAILED

    return DISCONNECTED


def draw_button(
    surface,
    rect,
    text,
    font,
    mouse_pos,
    enabled=True,
    accent=False
):

    hovered = (
        enabled and
        rect.collidepoint(mouse_pos)
    )

    if not enabled:

        background = BUTTON_DISABLED

        border_color = BORDER

    elif accent:

        background = (
            BUTTON_ACCENT_HOVER
            if hovered
            else BUTTON_ACCENT
        )

        border_color = BORDER_BRIGHT

    elif hovered:

        background = BUTTON_HOVER

        border_color = BORDER_BRIGHT

    else:

        background = BUTTON_BG

        border_color = BORDER

    radius = min(
        10,
        rect.height // 2
    )

    # Soft drop shadow for a bit of depth.
    if enabled:

        shadow_rect = rect.move(
            0,
            2
        )

        shadow_surface = pygame.Surface(
            (
                shadow_rect.width,
                shadow_rect.height
            ),
            pygame.SRCALPHA
        )

        pygame.draw.rect(
            shadow_surface,
            (
                *SHADOW,
                60
            ),
            shadow_surface.get_rect(),
            border_radius=radius
        )

        surface.blit(
            shadow_surface,
            shadow_rect.topleft
        )

    pygame.draw.rect(
        surface,
        background,
        rect,
        border_radius=radius
    )

    pygame.draw.rect(
        surface,
        border_color,
        rect,
        width=1,
        border_radius=radius
    )

    if enabled and accent:

        text_color = (
            BACKGROUND
            if not hovered
            else BACKGROUND
        )

    elif enabled:

        text_color = TEXT

    else:

        text_color = TEXT_DIM

    draw_text(
        surface,
        text,
        font,
        text_color,
        rect.centerx,
        rect.centery,
        "center"
    )


# ============================================================
# ROBOT DATA
# ============================================================

@dataclass
class Robot:

    key: str

    name: str

    hostname: str

    ip_address: str

    port: int

    discovery_mode: str

    # Set only for MODE_MAC robots -- the MAC address it was resolved
    # from. Carried through to the hub's star syncs (see
    # RobotSyncManager.run()) so ignoAPI's own watchdog keeps
    # re-resolving this robot by MAC too, not just by whatever IP it
    # had at LINK time.
    mac: str = ""

    status: str = ROBOT_DISCONNECTED

    x_offset: float = 0.0

    y_offset: float = 0.0

    last_seen: float = field(
        default_factory=time.time
    )

    socket_connection: object = None

    connection_lock: object = field(
        default_factory=threading.Lock
    )

    # Ticked in the list to be included the next time
    # "LINK SELECTED ROBOTS" runs.
    sync_selected: bool = False

    # Result of the last star-sync / combine+link attempt for this
    # robot, e.g. "LINKED", "SYNC FAILED". Blank until it has been tried.
    sync_status: str = ""

    # WHY the last sync attempt failed (e.g. "c_id does not exist on
    # this robot"). Blank when there was no failure. Shown in the UI
    # so a failed sync isn't just a red "SYNC FAILED" with no reason.
    sync_error: str = ""


# ============================================================
# ROBOT REGISTRY
# ============================================================

class RobotRegistry:

    def __init__(self):

        self.robots = {}

        self.lock = threading.RLock()

        # Survives clear() -- unlike self.robots, which gets wiped on
        # every mode switch / manual rescan. mDNS and UDP discovery
        # key robots completely differently (hostname vs "udp:<ip>"),
        # and a rescan in the SAME mode still tears down and rebuilds
        # every Robot object from scratch -- so without this, "LINKED"
        # / "SYNC FAILED" status is forgotten every time you switch
        # modes or rescan, even though the robot's actual link
        # configuration on ignoAPI is untouched. ip_address is the one
        # field both discovery modes populate the same way, so it's
        # what ties "the same robot" together across a mode switch.
        self.link_state_by_ip = {}

    def clear(self):

        with self.lock:

            for robot in self.robots.values():

                with robot.connection_lock:

                    if robot.socket_connection:

                        try:

                            robot.socket_connection.close()

                        except Exception:

                            pass

                # Snapshot sync state before this Robot object is
                # thrown away, so it can be restored if the same IP
                # is rediscovered (possibly under a different mode /
                # a different registry key).
                if robot.ip_address:

                    self.link_state_by_ip[robot.ip_address] = {
                        "sync_selected": robot.sync_selected,
                        "sync_status": robot.sync_status,
                        "sync_error": robot.sync_error
                    }

            self.robots.clear()

    def add_or_update(
        self,
        key,
        name,
        hostname,
        ip_address,
        port,
        discovery_mode,
        mac=""
    ):

        with self.lock:

            if key in self.robots:

                robot = self.robots[key]

                robot.name = name
                robot.hostname = hostname
                robot.ip_address = ip_address
                robot.port = port
                robot.discovery_mode = discovery_mode
                robot.mac = mac
                robot.last_seen = time.time()

                return robot

            robot = Robot(
                key=key,
                name=name,
                hostname=hostname,
                ip_address=ip_address,
                port=port,
                discovery_mode=discovery_mode,
                mac=mac
            )

            # Restore sync state from a previous clear(), if this IP
            # was seen and linked/failed before -- e.g. rediscovered
            # after a mode switch or manual rescan. Only fires for a
            # BRAND NEW Robot object; a robot found again without an
            # intervening clear() already keeps its own state via the
            # "key in self.robots" branch above. Only terminal
            # statuses are restored -- a transient one like
            # "LINKING..." or "QUEUED" would be stale/misleading here,
            # since whatever background thread was driving it wasn't
            # necessarily still running by the time this fires.
            previous = self.link_state_by_ip.get(ip_address)

            if previous and previous["sync_status"] in (
                "LINKED", "SYNC FAILED", ""
            ):

                robot.sync_selected = previous["sync_selected"]
                robot.sync_status = previous["sync_status"]
                robot.sync_error = previous["sync_error"]

            angle = random.uniform(
                0,
                math.pi * 2
            )

            distance = random.uniform(
                0.20,
                0.88
            )

            robot.x_offset = (
                math.cos(angle) *
                distance
            )

            robot.y_offset = (
                math.sin(angle) *
                distance
            )

            self.robots[key] = robot

            print(
                "[ROBOT FOUND]"
            )

            print(
                f"  NAME: {robot.name}"
            )

            print(
                f"  IP: {robot.ip_address}"
            )

            print(
                f"  PORT: {robot.port}"
            )

            print(
                f"  MODE: {robot.discovery_mode}"
            )

            return robot

    def get_robot(self, key):

        with self.lock:

            return self.robots.get(
                key
            )

    def get_robots(self):

        with self.lock:

            return list(
                self.robots.values()
            )

    def count(self):

        with self.lock:

            return len(
                self.robots
            )

    def close_all_connections(self):

        robots = self.get_robots()

        for robot in robots:

            with robot.connection_lock:

                if robot.socket_connection:

                    try:

                        robot.socket_connection.close()

                    except Exception:

                        pass

                    robot.socket_connection = None

                robot.status = (
                    ROBOT_DISCONNECTED
                )


# ============================================================
# mDNS HOSTNAME SCANNER
# ============================================================

class MDNSRobotScanner:

    def __init__(
        self,
        registry,
        on_status=None
    ):

        self.registry = registry

        self.on_status = on_status

        self.running = False

        self.thread = None

        self.currently_scanning = False

        self.scan_lock = threading.Lock()

    def set_status(self, message):

        if self.on_status:

            self.on_status(
                message
            )

    def start(self):

        if self.running:

            return

        self.running = True

        self.thread = threading.Thread(
            target=self.scan_loop,
            daemon=True
        )

        self.thread.start()

        print(
            "[MDNS] Scanner started."
        )

    def stop(self):

        self.running = False

        print(
            "[MDNS] Scanner stopped."
        )

    def scan_loop(self):

        while self.running:

            self.scan_once()

            elapsed = 0.0

            while (
                self.running and
                elapsed < MDNS_SCAN_INTERVAL
            ):

                time.sleep(0.2)

                elapsed += 0.2

    def scan_once(self):

        if not self.running:

            return

        if not self.scan_lock.acquire(
            blocking=False
        ):

            return

        try:

            self.currently_scanning = True

            self.set_status(
                "mDNS: SCANNING ignoapi_rob1.local "
                "TO ignoapi_rob99.local"
            )

            print(
                "[MDNS] Starting scan..."
            )

            tasks = []

            with ThreadPoolExecutor(
                max_workers=MDNS_SCAN_WORKERS
            ) as executor:

                for number in range(
                    ROBOT_START,
                    ROBOT_END + 1
                ):

                    hostname = (
                        f"{HOSTNAME_PREFIX}"
                        f"{number}.local"
                    )

                    future = executor.submit(
                        self.resolve_robot,
                        number,
                        hostname
                    )

                    tasks.append(
                        future
                    )

                for future in as_completed(
                    tasks
                ):

                    if not self.running:

                        break

                    try:

                        result = future.result()

                        if result:

                            (
                                number,
                                hostname,
                                ip_address
                            ) = result

                            # Skip this machine's own IP -- not a robot.
                            if is_own_ip(ip_address):

                                continue

                            name = (
                                f"ROBOT {number}"
                            )

                            self.registry.add_or_update(
                                key=hostname,
                                name=name,
                                hostname=hostname,
                                ip_address=ip_address,
                                port=MDNS_TCP_PORT,
                                discovery_mode=MODE_MDNS
                            )

                    except Exception:

                        pass

            count = (
                self.registry.count()
            )

            self.set_status(
                f"mDNS: {count} ROBOT(S) FOUND"
            )

            print(
                f"[MDNS] Scan complete. "
                f"{count} robot(s) found."
            )

        finally:

            self.currently_scanning = False

            self.scan_lock.release()

    def resolve_robot(
        self,
        number,
        hostname
    ):

        if not self.running:

            return None

        try:

            ip_address = (
                socket.gethostbyname(
                    hostname
                )
            )

            if (
                not ip_address or
                ip_address.startswith("127.")
            ):

                return None

            return (
                number,
                hostname,
                ip_address
            )

        except socket.gaierror:

            return None

        except OSError:

            return None

        except Exception:

            return None


# ============================================================
# UDP DISCOVERY SCANNER
# ============================================================

class UDPRobotScanner:

    def __init__(
        self,
        registry,
        on_status=None
    ):

        self.registry = registry

        self.on_status = on_status

        self.running = False

        self.thread = None

        self.currently_scanning = False

        self.scan_lock = threading.Lock()

    def set_status(self, message):

        if self.on_status:

            self.on_status(
                message
            )

    def start(self):

        if self.running:

            return

        self.running = True

        self.thread = threading.Thread(
            target=self.scan_loop,
            daemon=True
        )

        self.thread.start()

        print(
            "[UDP] Scanner started."
        )

    def stop(self):

        self.running = False

        print(
            "[UDP] Scanner stopped."
        )

    def scan_loop(self):

        while self.running:

            self.scan_once()

            elapsed = 0.0

            while (
                self.running and
                elapsed < UDP_SCAN_INTERVAL
            ):

                time.sleep(0.2)

                elapsed += 0.2

    def scan_once(self):

        if not self.running:

            return

        if not self.scan_lock.acquire(
            blocking=False
        ):

            return

        self.currently_scanning = True

        self.set_status(
            "UDP: BROADCASTING ignoAPI?"
        )

        try:

            found = self.broadcast_scan()

            if not self.running:

                return

            for index, hit in enumerate(
                found,
                start=1
            ):

                ip_address = (
                    hit["ip"]
                )

                # Skip this machine's own IP -- not a robot.
                if is_own_ip(ip_address):

                    continue

                hostname = (
                    hit["name"]
                )

                port = (
                    hit["port"]
                )

                # If no name was returned,
                # use IP as the display name.
                if hostname:

                    display_name = (
                        hostname
                    )

                else:

                    display_name = (
                        f"ROBOT @ {ip_address}"
                    )

                key = (
                    f"udp:{ip_address}"
                )

                self.registry.add_or_update(
                    key=key,
                    name=display_name,
                    hostname=hostname,
                    ip_address=ip_address,
                    port=port,
                    discovery_mode=MODE_UDP
                )

            count = (
                self.registry.count()
            )

            self.set_status(
                f"UDP: {count} ROBOT(S) FOUND"
            )

            print(
                f"[UDP] Scan complete. "
                f"{count} robot(s) found."
            )

        except Exception as error:

            print(
                f"[UDP] Scan error: "
                f"{error}"
            )

            self.set_status(
                "UDP DISCOVERY ERROR"
            )

        finally:

            self.currently_scanning = False

            self.scan_lock.release()

    def broadcast_scan(self):

        """
        Same basic discovery flow as ignodiscover.py.

        1. Open UDP socket.
        2. Enable broadcast.
        3. Send 'ignoAPI?' to:
             255.255.255.255
             x.x.x.255 for every local interface
        4. Collect replies.
        5. Parse:
             ip,name,port
        6. Deduplicate by reported IP.
        """

        udp_socket = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM
        )

        udp_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

        udp_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_BROADCAST,
            1
        )

        udp_socket.bind(
            ("", 0)
        )

        udp_socket.settimeout(
            0.3
        )

        found = {}

        try:

            probe = PROBE.encode(
                "utf-8"
            )

            local_ips = (
                get_local_ipv4s()
            )

            print(
                "[UDP] Local interfaces:"
            )

            for ip_address in local_ips:

                print(
                    f"  {ip_address}"
                )

                targets = [
                    "255.255.255.255"
                ]

                try:

                    subnet_broadcast = (
                        ip_address.rsplit(
                            ".",
                            1
                        )[0] +
                        ".255"
                    )

                    targets.append(
                        subnet_broadcast
                    )

                except Exception:

                    pass

                for target in targets:

                    try:

                        udp_socket.sendto(
                            probe,
                            (
                                target,
                                DISCOVER_PORT
                            )
                        )

                        print(
                            "[UDP] Sent "
                            f"{PROBE} -> "
                            f"{target}:"
                            f"{DISCOVER_PORT}"
                        )

                    except OSError as error:

                        print(
                            "[UDP] Send failed "
                            f"to {target}: "
                            f"{error}"
                        )

            end_time = (
                time.time() +
                UDP_SCAN_TIMEOUT
            )

            while (
                self.running and
                time.time() < end_time
            ):

                try:

                    data, address = (
                        udp_socket.recvfrom(
                            RECV_SIZE
                        )
                    )

                except socket.timeout:

                    continue

                except OSError:

                    break

                try:

                    text = data.decode(
                        "utf-8",
                        "ignore"
                    )

                    hit = parse_udp_reply(
                        text
                    )

                    if hit and not is_own_ip(hit["ip"]):

                        found[
                            hit["ip"]
                        ] = hit

                        print(
                            "[UDP] Reply:"
                        )

                        print(
                            f"  FROM: "
                            f"{address[0]}"
                        )

                        print(
                            f"  DATA: "
                            f"{hit}"
                        )

                except Exception:

                    continue

        finally:

            try:

                udp_socket.close()

            except Exception:

                pass

        return [
            found[key]
            for key in sorted(found)
        ]


# ============================================================
# MAC ROBOT SCANNER
#   Doesn't scan a subnet or a hostname range -- it resolves
#   whatever MAC addresses the user has typed into the MAC panel
#   (AppSettings.manual_macs) to IPs via the ARP table, same as
#   the mDNS/UDP scanners resolve hostnames/broadcasts.
# ============================================================

class MACRobotScanner:

    def __init__(
        self,
        registry,
        on_status=None
    ):

        self.registry = registry

        self.on_status = on_status

        self.running = False

        self.thread = None

        self.currently_scanning = False

        self.scan_lock = threading.Lock()

    def set_status(self, message):

        if self.on_status:

            self.on_status(
                message
            )

    def start(self):

        if self.running:

            return

        self.running = True

        self.thread = threading.Thread(
            target=self.scan_loop,
            daemon=True
        )

        self.thread.start()

        print(
            "[MAC] Scanner started."
        )

    def stop(self):

        self.running = False

        print(
            "[MAC] Scanner stopped."
        )

    def scan_loop(self):

        while self.running:

            self.scan_once()

            elapsed = 0.0

            while (
                self.running and
                elapsed < MAC_SCAN_INTERVAL
            ):

                time.sleep(0.2)

                elapsed += 0.2

    def scan_once(self):

        if not self.running:

            return

        if not self.scan_lock.acquire(
            blocking=False
        ):

            return

        self.currently_scanning = True

        macs = list(
            AppSettings.manual_macs
        )

        if not macs:

            self.set_status(
                "MAC: NO ADDRESSES ADDED"
            )

            self.currently_scanning = False

            self.scan_lock.release()

            return

        self.set_status(
            f"MAC: RESOLVING {len(macs)} ADDRESS(ES)..."
        )

        try:

            # One sweep serves every MAC being resolved this pass,
            # rather than a full subnet sweep per MAC.
            arp_sweep()

            table = arp_table()

            found_count = 0

            for typed_mac in macs:

                mac = norm_mac(
                    typed_mac
                )

                ip_address = table.get(
                    mac
                )

                if not ip_address:

                    with _mac_ip_cache_lock:

                        ip_address = (
                            _mac_ip_cache.get(mac)
                        )

                if not ip_address:

                    print(
                        f"[MAC] {mac}: not found on the LAN"
                    )

                    continue

                with _mac_ip_cache_lock:

                    _mac_ip_cache[mac] = ip_address

                found_count += 1

                key = (
                    f"mac:{mac}"
                )

                self.registry.add_or_update(
                    key=key,
                    name=f"ROBOT @ {ip_address}",
                    hostname="",
                    ip_address=ip_address,
                    port=MAC_TCP_PORT,
                    discovery_mode=MODE_MAC,
                    mac=mac
                )

            if not self.running:

                return

            self.set_status(
                f"MAC: {found_count}/{len(macs)} RESOLVED"
            )

            print(
                f"[MAC] Scan complete. "
                f"{found_count}/{len(macs)} MAC(s) resolved."
            )

        except Exception as error:

            print(
                f"[MAC] Scan error: {error}"
            )

            self.set_status(
                "MAC DISCOVERY ERROR"
            )

        finally:

            self.currently_scanning = False

            self.scan_lock.release()


# ============================================================
# ROBOT CONNECTION MANAGER
# ============================================================

class RobotConnectionManager:

    @staticmethod
    def connect_robot(robot):

        with robot.connection_lock:

            if robot.status in (
                ROBOT_CONNECTED,
                ROBOT_CONNECTING
            ):

                return

            robot.status = (
                ROBOT_CONNECTING
            )

        thread = threading.Thread(
            target=(
                RobotConnectionManager
                .connect_worker
            ),
            args=(robot,),
            daemon=True
        )

        thread.start()

    @staticmethod
    def connect_worker(robot):

        print(
            "[CONNECT]"
        )

        print(
            f"  ROBOT: {robot.name}"
        )

        print(
            f"  IP: {robot.ip_address}"
        )

        print(
            f"  PORT: {robot.port}"
        )

        sock = None

        try:

            sock = socket.create_connection(
                (
                    robot.ip_address,
                    robot.port
                ),
                timeout=TCP_CONNECT_TIMEOUT
            )

            sock.settimeout(
                None
            )

            with robot.connection_lock:

                if robot.socket_connection:

                    try:

                        robot.socket_connection.close()

                    except Exception:

                        pass

                robot.socket_connection = (
                    sock
                )

                robot.status = (
                    ROBOT_CONNECTED
                )

            print(
                f"[CONNECT] SUCCESS: "
                f"{robot.name}"
            )

        except Exception as error:

            if sock:

                try:

                    sock.close()

                except Exception:

                    pass

            with robot.connection_lock:

                robot.socket_connection = None

                robot.status = (
                    CONNECTION_FAILED
                )

            print(
                f"[CONNECT] FAILED: "
                f"{robot.name}"
            )

            print(
                f"[CONNECT] REASON: "
                f"{error}"
            )

    @staticmethod
    def connect_robot_blocking(robot):
        """
        Same connect as connect_robot(), but BLOCKS until it succeeds or
        fails instead of firing a background thread. Used by the sync
        workflow, which is already running off the UI thread and needs
        to know the outcome before moving on to the next step.

        Returns True if the robot ends up connected.
        """

        with robot.connection_lock:

            if robot.status == ROBOT_CONNECTED:
                return True

            robot.status = ROBOT_CONNECTING

        RobotConnectionManager.connect_worker(robot)

        return robot.status == ROBOT_CONNECTED


# ============================================================
# STAR SYNC / ID-FORWARDING  (ported from make_sync.py)
#
#   This is the same three-step chain make_sync.py sets up from the
#   command line, driven here by which robots are ticked in the list:
#
#       createSyncIgnoAPI  ->  star sync, this machine as hub
#       combine(id,c_id,r_id)  on each robot  ->  id_combined
#       link(id_combined, <var>_tx)  on each robot
#
#   The link step carries the same fix as make_sync.py: it unlinks by
#   DESTINATION (whatever currently feeds <var>_tx, whatever it is
#   named) rather than guessing old source names, and it checks the
#   link RPC's response instead of assuming it worked -- ignoAPI allows
#   only one writer per target, so a stale link left in place would
#   otherwise silently win over the new one.
#
#   Two more fixes live in here, both found the same way -- by reading
#   ignoAPI.py's actual link/combine engine rather than guessing at its
#   behaviour from the outside:
#
#   1. combine_and_link() no longer "pokes" the linked value to force
#      propagation. ignoAPI's link_add() already forces one push of the
#      source's CURRENT value on the very next _link_loop tick
#      (~50ms), whether or not that value has "changed" -- see
#      link_add()'s `_link_last.pop(src, None)`. The old poke wrote a
#      sentinel string ("__radarui_poke__") straight into the linked
#      variable to force a change event ignoAPI was already going to
#      produce on its own; for a combine's output that box is being
#      recomputed live several times a second, so the poke could win a
#      single tick and get forwarded before the real recompute
#      overwrote it -- and when the link target is itself broadcast to
#      the whole fleet (fleet_cid_tx), that sentinel is what every
#      other robot briefly saw. For the single-peer fleet_cid case it
#      was worse: the "combined_var" being poked there IS the raw
#      "c_id" variable itself, so poking it fought whatever else on
#      that robot legitimately owns it. Fixed by simply watching for
#      propagation instead of forcing it.
#
#   2. run() now takes the FULL current robot roster (`all_robots`),
#      not just the subset it is connecting/linking this call, and
#      uses it to build the peer list handed to createSyncIgnoAPI() and
#      configure_hub_fleet_cid(). createSyncIgnoAPI() REPLACES a sync's
#      peer list wholesale rather than merging into it, so a partial
#      run -- e.g. "RECONNECT FAILED", which only passes the SYNC
#      FAILED subset -- was silently narrowing the hub's star syncs
#      (and its fleet_cid combine) down to just that subset, dropping
#      every already-LINKED robot the run didn't happen to touch. That
#      was the "combined c_id only shows some of the robots" bug.
# ============================================================

class RobotSyncManager:

    # The peer set (frozenset of peer_address() strings) the fleet FTP
    # server was last successfully (re)created for. configure_fleet_ftp()
    # compares against this and skips the createFTP() RPC entirely when
    # the roster hasn't changed -- see that method's docstring for why
    # this exists: without it, every AUTO_RECONNECT_DELAY-spaced retry
    # round (and every manual RECONNECT click) re-fires createFTP() even
    # when nothing about the linked robots changed, which respawns
    # fleet_ftp_autoftp.exe on the hub before the OS has released its
    # previous instance's hold on FLEET_FTP_PORT -- surfacing as
    # "WinError 10048: Only one usage of each socket address..." in the
    # autoFTP console.
    _ftp_configured_peers = None

    @staticmethod
    def peer_address(robot):
        """
        Prefer the UDP-discovered IP address over the .local hostname.
        Some networks (e.g. mobile hotspots) allow UDP broadcast discovery
        but don't resolve mDNS .local hostnames, which causes
        getaddrinfo failures during sync/link RPCs. Every RPC in this file
        addresses the robot by whatever this returns, so fall back to the
        hostname only when no IP address was discovered.
        """
        return robot.ip_address or robot.hostname

    @staticmethod
    def host_tag(host):
        """
        Must match ignoAPI's sy_host_tag() exactly, or the per-peer
        inbound box name we compute for the hub side (fleet_cid_<tag>_rx)
        will not match the box ignoAPI actually created.
        """
        return re.sub(
            r"[^A-Za-z0-9._-]+", "_", str(host)
        ).strip("_")

    @staticmethod
    def robot_folder_name(peer):
        """
        "rob2" out of "ignoapi_rob2.local" (or any peer string with a
        rob<N> in it, case-insensitive). Falls back to a filesystem-safe
        version of the whole peer string when nothing matches -- e.g. a
        UDP robot whose hostname is blank and peer is a bare IP.

        This is the FALLBACK naming scheme, used only when a peer's
        "address" variable (see robot_ftp_folder_name()) can't be read
        or is blank.
        """
        match = re.search(r"rob(\d+)", str(peer), re.IGNORECASE)

        if match:
            return "rob%s" % match.group(1)

        return RobotSyncManager.host_tag(peer)

    @staticmethod
    def robot_ftp_folder_name(peer, api_port, log):
        """
        Folder name for `peer`'s FTP share, taken from the "address"
        variable in that robot's own ignoAPI store (read via
        read_peer_store(), the same read_all RPC used elsewhere in this
        file) rather than parsed out of the peer's IP/hostname string.
        Sanitized through host_tag() so it's always filesystem-safe.

        Falls back to robot_folder_name(peer) -- the old hostname/IP
        based scheme -- when the peer can't be reached, doesn't have an
        "address" variable, or that variable is blank.
        """
        try:
            store = RobotSyncManager.read_peer_store(peer, api_port)
            address = str(store.get("ADDRESS") or "").strip()

            if address:
                return RobotSyncManager.host_tag(address)

            log(
                None,
                "peer %s has no \"address\" variable set, "
                "falling back to hostname/IP for its ftp folder name"
                % peer
            )

        except Exception as error:
            log(
                None,
                "could not read \"address\" variable from %s (%s), "
                "falling back to hostname/IP for its ftp folder name"
                % (peer, error)
            )

        return RobotSyncManager.robot_folder_name(peer)

    @staticmethod
    def ensure_fleet_ftp_folders(peers, api_port, log):
        """
        Creates <FLEET_FTP_FOLDER>/<robot_ftp_folder_name(peer)> for
        every peer, if it does not already exist. Runs locally
        (os.makedirs) rather than over RPC, since the FTP server -- and
        this folder -- live on the hub, which is the same machine this
        code is running on. The folder names themselves come from each
        peer's own "address" variable, read over RPC (see
        robot_ftp_folder_name()).
        """

        for peer in peers:

            folder_name = RobotSyncManager.robot_ftp_folder_name(
                peer, api_port, log
            )

            folder_path = os.path.join(
                AppSettings.ftp_folder, folder_name
            )

            try:
                os.makedirs(folder_path, exist_ok=True)
                log(None, "ftp folder ready: %s" % folder_path)

            except Exception as error:
                log(
                    None,
                    "could not create ftp folder %s: %s"
                    % (folder_path, error)
                )

    @staticmethod
    def read_peer_store(peer, api_port):
        response = c._rpc(
            peer,
            api_port,
            {"action": "read_all"}
        )

        if response is None:
            raise RuntimeError("No response from robot")

        store = response.get("value")

        if store is None:
            raise RuntimeError("ignoAPI returned no variable store")

        return store

    @staticmethod
    def remove_old_link(peer, api_port, name):
        """
        Unlink whatever is currently attached to `name`, whether `name`
        is the SOURCE or the DESTINATION of the link. Called with the
        destination (<var>_tx) so it does not matter what the old
        source used to be called.
        """
        try:
            c._rpc(
                peer,
                api_port,
                {"action": "unlink", "name": name}
            )
        except Exception:
            pass  # fine if nothing was linked

    @staticmethod
    def wait_for_vars(host, api_port, names, timeout, poll=0.2):
        """
        Blocks until every name in `names` exists in `host`'s variable
        store, or `timeout` seconds pass. Returns (ok, last_store).
        """
        deadline = time.time() + timeout
        store = {}

        while time.time() < deadline:
            store = RobotSyncManager.read_peer_store(host, api_port)
            if all(name in store for name in names):
                return True, store
            time.sleep(poll)

        return False, store

    @staticmethod
    def ensure_variables_exist(peer, api_port, variable_names, log):
        """
        Makes sure every name in `variable_names` exists on `peer`,
        creating any that are missing (blank value). Returns
        (ok, message).
        """
        try:
            store = RobotSyncManager.read_peer_store(peer, api_port)

            missing = [
                name for name in variable_names
                if name not in store
            ]

            if not missing:
                return True, ""

            log(
                peer,
                "creating missing variable(s): %s..."
                % ", ".join(missing)
            )

            for name in missing:
                c._rpc(
                    peer,
                    api_port,
                    {
                        "action": "create_or_write",
                        "name": name,
                        "value": ""
                    }
                )

            ok, store = RobotSyncManager.wait_for_vars(
                peer, api_port, missing, timeout=5.0
            )

            if not ok:
                still_missing = [
                    name for name in missing
                    if name not in store
                ]
                return False, (
                    "could not create: %s"
                    % ", ".join(still_missing)
                )

            return True, ""

        except Exception as error:
            return False, str(error)

    @staticmethod
    def delete_variable(peer, api_port, name):
        """
        Deletes a variable on `peer` via ignoAPI's "delete" action
        (confirmed against ignoAPI.py's handle_client_request / _delete).
        Best-effort, like remove_old_link: deleting a name that doesn't
        exist makes ignoAPI return status "error", which ignoClient's
        _rpc() turns into a RuntimeError -- caught and ignored here,
        since "nothing to delete" is a fine outcome.
        """
        try:
            c._rpc(
                peer,
                api_port,
                {"action": "delete", "name": name}
            )
        except Exception:
            pass  # fine if it didn't exist

    @staticmethod
    def reset_stale_combine(peer, api_port, combine_row, combined_var, store, log):
        """
        If `combine_row` and/or `combined_var` already exist on `peer`
        (left over from a previous sync run), delete both before a
        fresh combine() is created -- otherwise the old boxes just get
        overwritten in place, which is fine most of the time, but can
        leave a stale definition behind if the source list changed
        between runs. Deleting first guarantees a clean re-create.
        """

        stale = [
            name for name in (combine_row, combined_var)
            if name in store
        ]

        if not stale:
            return

        log(
            peer,
            "found existing %s, deleting before recreate..."
            % " and ".join(stale)
        )

        for name in stale:
            RobotSyncManager.delete_variable(peer, api_port, name)

    @staticmethod
    def combine_and_link(
        host, api_port, combine_row, sources, link_target, log,
        wait_for_target_timeout=10.0
    ):
        """
        On `host`:

            combine(combine_row, *sources)  ->  <combine_row>_combined
            link(<combine_row>_combined, link_target)

        If there is only ONE source, the combine step is skipped and
        that single variable is linked directly -- no point wrapping
        one value in a combine just to unwrap it again.

        If `combine_row` or `<combine_row>_combined` already exists on
        `host` (e.g. left over from a previous run), both are deleted
        first so the combine is recreated from scratch rather than
        just overwritten in place.

        Carries the make_sync.py fix: unlinks by DESTINATION (whatever
        currently feeds `link_target`) before linking, and checks the
        link RPC's response instead of assuming it worked, since
        ignoAPI only allows one writer per target and a stale link left
        in place would otherwise silently keep winning.

        This function only creates the combine/link and confirms the
        link RPC was ACCEPTED by `host` -- it does not reconnect to
        `host` afterward to check whether the value actually
        propagated. That direct robot-side check depended on being
        able to freely re-open a connection to `host`, which does not
        hold for a robot only reachable by MAC (mDNS/UDP discovery
        unavailable): the re-check itself could time out or fail even
        when the robot was actually linked fine, misreporting "link
        did not propagate". For the server/id_combined link, real
        propagation is instead confirmed hub-side, from data the hub
        already has -- see verify_server_links_on_hub().

        Returns (ok, message). Never raises.
        """

        try:
            if len(sources) == 1:

                combined_var = sources[0]

                # --- clear any stale combine artifacts for this row,
                #     even though we're skipping combine creation this
                #     time. If an earlier run (or an earlier version of
                #     this script) DID create a combine for this row,
                #     its leftover "<combine_row>_combined" box can
                #     still be hanging around and, worse, still be the
                #     thing actually linked to link_target -- so THIS
                #     run's direct link never gets a chance to take
                #     over. Only matters for whichever robot happens to
                #     carry that leftover state, which is exactly what
                #     "the same robot fails every time, the rest link
                #     fine" looks like.
                try:
                    existing_store = RobotSyncManager.read_peer_store(
                        host, api_port
                    )
                except Exception:
                    existing_store = {}

                stale_combined = "%s_combined" % combine_row

                if stale_combined in existing_store:

                    log(
                        host,
                        "found leftover %s from an earlier run, deleting..."
                        % stale_combined
                    )

                    RobotSyncManager.delete_variable(
                        host, api_port, stale_combined
                    )

            else:

                combined_var = "%s_combined" % combine_row

                # --- wipe any stale combine boxes before recreating ----
                try:
                    existing_store = RobotSyncManager.read_peer_store(
                        host, api_port
                    )
                except Exception:
                    existing_store = {}

                RobotSyncManager.reset_stale_combine(
                    host, api_port, combine_row, combined_var,
                    existing_store, log
                )

                request_row = "__radarui_%s_request" % combine_row

                log(
                    host,
                    "creating combine(%s,%s)..."
                    % (combine_row, ",".join(sources))
                )

                c._rpc(
                    host,
                    api_port,
                    {
                        "action": "create_or_write",
                        "name": request_row,
                        "value": "combine(%s,%s)" % (
                            combine_row, ",".join(sources)
                        )
                    }
                )

                ok, store = RobotSyncManager.wait_for_vars(
                    host, api_port, [combined_var], timeout=5.0
                )

                if not ok:
                    return False, (
                        "combine did not create %s" % combined_var
                    )

            # --- wait for the target to exist (e.g. the sync's own
            #     _tx box, created when the sync itself was set up) --
            log(host, "checking %s..." % link_target)

            ok, store = RobotSyncManager.wait_for_vars(
                host, api_port, [link_target],
                timeout=wait_for_target_timeout
            )

            if not ok:
                return False, "%s does not exist" % link_target

            # --- make sure combined_var itself isn't ALREADY wired as
            #     the DESTINATION of some other stale link. If it is
            #     (leftover from an earlier run, or from testing before
            #     this fleet_cid wiring existed), ignoAPI's one-writer-
            #     per-target rule means our own create_or_write pokes
            #     below get silently overridden/ignored by whatever
            #     still feeds it -- so the poke looks like it "does
            #     nothing" every single time, on that one robot only,
            #     regardless of retries. Unlinking it first guarantees
            #     it's a plain, freely-writable variable again.
            log(host, "clearing old link configuration for %s..." % combined_var)

            RobotSyncManager.remove_old_link(host, api_port, combined_var)

            # --- clear whatever currently feeds link_target, then
            #     create the link and CHECK the result --------------
            log(host, "clearing old link configuration for %s..." % link_target)

            RobotSyncManager.remove_old_link(host, api_port, link_target)

            log(host, "linking %s -> %s..." % (combined_var, link_target))

            link_response = c._rpc(
                host,
                api_port,
                {
                    "action": "link",
                    "name": combined_var,
                    "value": link_target
                }
            )

            if not link_response or link_response.get("status") == "error":
                return False, "link rejected: %s" % (
                    (link_response or {}).get("message", "no response")
                )

            # --- done: RPC accepted, nothing more to check HERE ------
            # This function intentionally does NOT wait to see whether
            # combined_var's value actually reaches link_target. That
            # used to be checked by reconnecting to `host` itself and
            # polling its own store -- but when `host` is a robot only
            # reachable by MAC (mDNS/UDP discovery unavailable), that
            # re-check is itself a fresh connection attempt, and can
            # time out or misfire even though the original link is
            # fine, incorrectly reporting "link did not propagate".
            #
            # ignoAPI's link_add() forces one push of the source's
            # CURRENT value into the target on the very next
            # _link_loop tick (~50ms) as soon as the link is created,
            # regardless of whether that value has "changed" -- see
            # ignoAPI.py: link_add() does `_link_last.pop(src, None)`
            # specifically "so it takes effect" -- so the RPC being
            # accepted is a strong signal the push will happen.
            # Confirming it actually LANDED (for the server/id_combined
            # case) is now the hub's job -- see
            # verify_server_links_on_hub(), which checks the hub's own
            # variable store instead of reconnecting to the robot.
            log(
                host,
                "link accepted: %s -> %s" % (combined_var, link_target)
            )

            return True, "link accepted"

        except Exception as error:
            return False, str(error)

    @staticmethod
    def server_variables():
        """
        Which of AppSettings.variables actually get combined and sent
        through server_tx on each robot. Any variable the user adds in
        Settings lands in AppSettings.variables and therefore shows up here
        automatically, with no separate list to keep in sync.

        Shared by configure_robot() (what actually gets combined) and
        the Settings panel (what's shown as "sent in server_tx") so
        the two can never drift apart.
        """

        return [
            name for name in AppSettings.variables
        ]

    @staticmethod
    def configure_robot(peer, api_port, log):
        """
        On ONE robot, once it is connected and has all of FLEET_VARIABLES:

            c_id                              -> fleet_cid_tx
            combine(id,r_id,c_id,battery,odometry,obstacle) -> id_combined -> server_tx

        Returns (ok, message).
        """

        fleet_cid_tx = "%s_tx" % FLEET_CID_VARIABLE
        server_tx = "%s_tx" % SYNC_VARIABLE

        ok, message = RobotSyncManager.combine_and_link(
            peer, api_port, "c_id", ["c_id"], fleet_cid_tx, log
        )

        if not ok:
            return False, "fleet_cid link failed: %s" % message

        rest_of_variables = RobotSyncManager.server_variables()

        ok, message = RobotSyncManager.combine_and_link(
            peer, api_port, "id", rest_of_variables, server_tx, log
        )

        if not ok:
            return False, "server link failed: %s" % message

        return True, "LINKED"

    @staticmethod
    def configure_hub_fleet_cid(hub, api_port, peers, log):
        """
        On the HUB (this computer): combine every connected robot's
        incoming c_id (fleet_cid_<host>_rx, one box per peer, created
        by the star sync itself) and link the result back into the
        hub's own fleet_cid_tx -- so the combined roster of every
        robot's c_id broadcasts back out to the whole fleet.

        No override is passed to combine_and_link() here, so its
        single-source shortcut applies to the hub the same way it
        applies everywhere else in this file: if exactly one robot is
        connected, `sources` has one entry, no "fleet_cid_combine" /
        "fleet_cid_combine_combined" boxes are created at all, and
        that one fleet_cid_<host>_rx is linked directly into
        fleet_cid_tx -- the same link() RPC configure_robot() already
        uses for c_id -> fleet_cid_tx on each robot.

        Returns (ok, message).
        """

        sources = [
            "%s_%s_%s" % (
                FLEET_CID_VARIABLE,
                RobotSyncManager.host_tag(peer),
                "rx"
            )
            for peer in peers
        ]

        fleet_cid_tx = "%s_tx" % FLEET_CID_VARIABLE

        ok, store = RobotSyncManager.wait_for_vars(
            hub, api_port, sources, timeout=10.0
        )

        if not ok:
            missing = [name for name in sources if name not in store]
            return False, (
                "hub is missing inbound box(es): %s"
                % ", ".join(missing)
            )

        return RobotSyncManager.combine_and_link(
            hub, api_port, "fleet_cid_combine", sources, fleet_cid_tx, log
        )

    @staticmethod
    def verify_server_links_on_hub(
        hub, api_port, robots, log,
        timeout=LINK_PROPAGATION_TIMEOUT, peer_count=None
    ):
        """
        Hub-side replacement for the propagation check combine_and_link()
        used to do by reconnecting to each robot. combine_and_link()
        now only confirms ignoAPI ACCEPTED the id_combined -> server_tx
        link RPC on the robot; it no longer reconnects afterward to see
        whether the value actually arrived, because that direct
        robot-side re-check can misreport "link did not propagate" when
        the robot is only reachable by MAC (mDNS/UDP discovery
        unavailable) and a fresh IP-based reconnect to re-check it
        fails or times out even though the robot is actually linked
        fine.

        Instead, this checks the thing that actually matters -- whether
        each robot's data really made it onto the HUB -- by reading the
        fleet computer's (`hub`'s) OWN variable store and comparing,
        for every robot in `robots`, its inbound rx box (created by the
        star sync itself) against that robot's current `id_combined`
        value. `id_combined` is read directly from the robot each poll,
        since that is the value combine_and_link() linked into
        server_tx and is expected to show up, unchanged, in this
        hub-side rx box once the star sync has forwarded it.

        The rx box name mirrors createSyncIgnoAPI()'s own single-peer
        shortcut (the same one configure_hub_fleet_cid() relies on for
        fleet_cid -- see its docstring): when the star sync has exactly
        ONE peer, ignoAPI does not suffix the box with a per-peer host
        tag at all, it just creates a bare `server_rx`. The per-peer
        `server_<host_tag>_rx` naming only appears once a second peer
        is added to the same sync. `peer_count` is the total number of
        peers currently in the star sync (NOT len(robots), which may be
        a subset being (re)verified this round while other peers stay
        LINKED from an earlier run) -- pass it explicitly. If omitted,
        it defaults to len(robots), which is only correct when `robots`
        already represents every peer in the sync.

        A robot is marked LINKED as soon as its rx box matches; a
        robot still unmatched when `timeout` elapses is marked
        SYNC FAILED. This mutates robot.sync_status / robot.sync_error
        directly for every robot in `robots` -- callers don't need to
        do anything further with those robots afterward.

        Never raises -- a read failure against the hub or a robot is
        treated as "not yet confirmed" and retried on the next poll,
        up until `timeout`.
        """

        pending = {
            robot.key: robot
            for robot in robots
        }

        if peer_count is None:
            peer_count = len(robots)

        if peer_count == 1:

            # Single-peer star sync: ignoAPI creates one bare
            # `server_rx` box with no host-tag suffix at all -- the
            # one robot.key in `robots` maps straight to it.
            rx_names = {
                robot.key: "%s_%s" % (
                    SYNC_VARIABLE,
                    "rx"
                )
                for robot in robots
            }

        else:

            rx_names = {
                robot.key: "%s_%s_%s" % (
                    SYNC_VARIABLE,
                    RobotSyncManager.host_tag(
                        RobotSyncManager.peer_address(robot)
                    ),
                    "rx"
                )
                for robot in robots
            }

        deadline = time.time() + timeout

        while pending and time.time() < deadline:

            try:
                hub_store = RobotSyncManager.read_peer_store(hub, api_port)
            except Exception:
                time.sleep(0.2)
                continue

            for key in list(pending.keys()):

                robot = pending[key]
                rx_name = rx_names[key]

                try:
                    robot_store = RobotSyncManager.read_peer_store(
                        RobotSyncManager.peer_address(robot), api_port
                    )
                except Exception:
                    continue

                combined_value = robot_store.get("id_combined")
                rx_value = hub_store.get(rx_name)

                if (
                    rx_name in hub_store
                    and str(rx_value) == str(combined_value)
                ):
                    robot.sync_status = "LINKED"
                    robot.sync_error = ""
                    log(
                        robot,
                        "confirmed on hub: %s matches id_combined"
                        % rx_name
                    )
                    del pending[key]

            if pending:
                time.sleep(0.2)

        for robot in pending.values():

            rx_name = rx_names[robot.key]

            robot.sync_status = "SYNC FAILED"
            robot.sync_error = (
                "link did not propagate to hub: %s did not match "
                "id_combined within %.1fs" % (rx_name, timeout)
            )
            log(robot, robot.sync_error)

    @staticmethod
    def read_hub_variable(hub, api_port, name):
        """
        Reads a single variable straight off the hub's own ignoAPI
        store (the "read" RPC action -- see ignoAPI.py's
        handle_client_request()). Returns "" (rather than raising)
        when the variable doesn't exist yet or the hub can't be
        reached, since ADDRESS being unset is a normal, expected
        state, not an error.
        """
        try:
            response = c._rpc(
                hub, api_port, {"action": "read", "name": name}
            )

            if response is None:
                return ""

            value = response.get("value")

            return "" if value is None else str(value)

        except Exception:
            return ""

    @staticmethod
    def write_hub_variable(hub, api_port, name, value):
        """
        Sets a single variable on the hub's own ignoAPI store
        ("create_or_write" -- creates it if it doesn't exist yet,
        overwrites it otherwise). Swallows errors rather than raising:
        callers use this for the ADDRESS blank/restore dance around
        createFTP(), and a failure to restore ADDRESS afterward should
        not itself fail the whole LINK run.
        """
        try:
            c._rpc(
                hub,
                api_port,
                {
                    "action": "create_or_write",
                    "name": name,
                    "value": value or ""
                }
            )

            return True

        except Exception as error:

            log_message = (
                "could not set hub variable %r to %r: %s"
                % (name, value, error)
            )

            print("[RobotSyncManager] %s" % log_message)

            return False

    @staticmethod
    def configure_fleet_ftp(hub, api_port, peers, log):
        """
        Creates or updates the fleet-wide FTP server on the HUB and
        shares it with every robot in `peers`. Also makes sure each of
        those robots has its own subfolder under FLEET_FTP_FOLDER, named
        after that robot's own "address" variable (e.g.
        FLEET_FTP_FOLDER/<address> -- read from the robot over RPC, see
        robot_ftp_folder_name()) -- existing folders are left alone,
        missing ones are created.

        createFTP() (via createModule) REPLACES the module's sharing
        list wholesale rather than merging into it -- same as
        createSyncIgnoAPI's peer list -- so `peers` must always be the
        FULL current roster of linked robots, not just whichever ones
        this run touched, or previously-linked robots would silently
        lose their FTP access the next time this runs.

        SKIPS the createFTP() RPC entirely when `peers` is the exact
        same set _ftp_configured_peers was last set to. createFTP()
        respawns fleet_ftp_autoftp.exe on the hub every time it's
        called, even when the sharing list it's given is identical to
        what's already running -- there is no "nothing to do" no-op on
        ignoAPI's side. run() calls this after every successful batch,
        including every AUTO_RECONNECT_DELAY-spaced auto-reconnect
        round, so without this guard an unrelated robot's retry loop
        respawns the FTP server on a timer even though the actual
        linked-peer roster never moved -- and if two of those spawns
        land close enough together, the new process loses the race to
        bind FLEET_FTP_PORT before the old one has released it
        (WinError 10048 on Windows).

        SHARE LINK ADDRESSING (AppSettings.ftp_link_mode):
        ignoAPI builds the ftp:// link it writes into the shared
        variable from the HUB's own ADDRESS variable -- a name set
        ("ignoapi_<address>.local") if ADDRESS holds one, the hub's
        LAN IP if it doesn't (see ignoAPI.py's "NAMING THIS MACHINE"
        section). There's no per-call switch for this on the createFTP
        RPC itself, so to get an IP-style link on demand this
        temporarily blanks the hub's ADDRESS before the RPC and puts
        whatever it held before back immediately after, however the
        call turns out. Left alone entirely when ftp_link_mode is
        MDNS -- whatever ADDRESS the hub is already using keeps being
        used, exactly like before this setting existed.

        RETRIES up to FLEET_FTP_MAX_RETRY_ATTEMPTS times, pausing
        FLEET_FTP_RETRY_DELAY seconds between attempts, before giving
        up on a failing createFTP() call -- e.g. the hub being
        momentarily unreachable or autoFTP.exe still mid-respawn from
        a previous run.

        Returns (ok, message). Never raises.
        """

        peer_set = frozenset(peers)

        if peer_set == RobotSyncManager._ftp_configured_peers:

            log(
                None,
                "fleet ftp: peer roster unchanged, skipping rebuild"
            )

            return True, "unchanged, skipped rebuild"

        use_ip_link = (
            AppSettings.ftp_link_mode == FTP_LINK_MODE_IP
        )

        previous_address = None

        if use_ip_link:

            previous_address = RobotSyncManager.read_hub_variable(
                hub, api_port, IGNOAPI_ADDRESS_VAR
            )

            log(
                None,
                "ftp link mode is IP -- temporarily clearing hub "
                "ADDRESS so the shared link falls back to the LAN IP"
            )

            RobotSyncManager.write_hub_variable(
                hub, api_port, IGNOAPI_ADDRESS_VAR, ""
            )

        try:
            RobotSyncManager.ensure_fleet_ftp_folders(peers, api_port, log)

            last_error = "unknown error"

            for attempt in range(1, FLEET_FTP_MAX_RETRY_ATTEMPTS + 1):

                log(
                    None,
                    "creating/updating fleet FTP server "
                    "(attempt %d/%d)..."
                    % (attempt, FLEET_FTP_MAX_RETRY_ATTEMPTS)
                )

                try:
                    result = c.createFTP(
                        hub,
                        api_port,
                        FLEET_FTP_NAME,
                        AppSettings.ftp_folder,
                        ftp_port=FLEET_FTP_PORT,
                        sharing=peers,
                        runatstartup=True
                    )

                    log(None, "fleet ftp: %s" % result)

                    RobotSyncManager._ftp_configured_peers = peer_set

                    return True, str(result)

                except Exception as error:

                    last_error = str(error)

                    log(
                        None,
                        "fleet ftp attempt %d/%d failed: %s"
                        % (
                            attempt,
                            FLEET_FTP_MAX_RETRY_ATTEMPTS,
                            last_error
                        )
                    )

                    if attempt < FLEET_FTP_MAX_RETRY_ATTEMPTS:

                        time.sleep(FLEET_FTP_RETRY_DELAY)

            log(
                None,
                "COULD NOT CREATE FTP after %d attempts: %s"
                % (FLEET_FTP_MAX_RETRY_ATTEMPTS, last_error)
            )

            return False, last_error

        finally:

            if use_ip_link:

                log(
                    None,
                    "restoring hub ADDRESS to %r"
                    % previous_address
                )

                RobotSyncManager.write_hub_variable(
                    hub,
                    api_port,
                    IGNOAPI_ADDRESS_VAR,
                    previous_address
                )

    @staticmethod
    def run(hub, api_port, robots, log, done, all_robots=None):
        """
        The full "CONNECT & LINK" chain for whatever robots are ticked:

            1. connect to each robot
            2. create the "server" and "fleet_cid" star syncs on the
               hub, with every connected robot as a peer, then pause
               SYNC_FANOUT_SETTLE_DELAY seconds so the hub's fan-out
               of the matching boxes to every peer has time to finish
               before any robot gets linked
            3. make sure c_id / r_id / battery / odometry / obstacle
               exist on each connected robot (create any that are
               missing)
            4. on each robot: c_id -> fleet_cid_tx,
               combine(rest) -> server_tx
            5. on the hub: combine everyone's incoming c_id -> hub's
               own fleet_cid_tx
            6. on the hub: create/update the fleet FTP server, shared
               with every currently-linked robot

        One robot failing a step does not stop the others -- it is
        marked SYNC FAILED with the reason and left out of the rest of
        the chain. `log(robot_or_None, text)` reports progress; `done()`
        runs once at the end. Runs in a background thread.

        `robots` is just whoever THIS call should connect/(re)link --
        e.g. only the ticked robots for "LINK SELECTED", or only the
        SYNC FAILED ones for "RECONNECT FAILED". `all_robots` is the
        full current roster (every robot the registry knows about,
        whatever its status); it defaults to `robots` when not given.
        The peer list handed to the hub's star syncs, and the source
        list for the hub's fleet_cid combine, are always built from
        `all_robots`' already-LINKED robots plus `robots` -- never
        from `robots` alone -- because createSyncIgnoAPI() REPLACES a
        sync's peer list wholesale rather than merging into it. Using
        only `robots` would mean a partial run silently narrows the
        hub's syncs down to whichever subset it happened to touch,
        dropping every other already-linked robot from the fleet.
        """

        if all_robots is None:
            all_robots = robots

        ready = []

        # --- 1: connect -----------------------------------------
        for robot in robots:
            robot.sync_status = "CONNECTING..."
            robot.sync_error = ""

        for robot in robots:

            connected = False

            for attempt in range(1, SYNC_CONNECT_MAX_ATTEMPTS + 1):

                if attempt == 1:
                    log(robot, "connecting...")
                else:
                    log(
                        robot,
                        "retrying connection (attempt %d/%d)..."
                        % (attempt, SYNC_CONNECT_MAX_ATTEMPTS)
                    )
                    time.sleep(SYNC_CONNECT_RETRY_DELAY)

                connected = RobotConnectionManager.connect_robot_blocking(
                    robot
                )

                if connected:
                    break

            if not connected:
                robot.sync_status = "SYNC FAILED"
                robot.sync_error = (
                    "could not connect after %d attempt(s)"
                    % SYNC_CONNECT_MAX_ATTEMPTS
                )
                log(
                    robot,
                    "could not connect after %d attempt(s)"
                    % SYNC_CONNECT_MAX_ATTEMPTS
                )
                continue

            ready.append(robot)

        if not ready:
            log(None, "no robots connected")
            done()
            return

        # Full peer list for the hub's star syncs: whichever robots
        # are already LINKED from an earlier run (and are not part of
        # THIS run) plus whoever this run is connecting/linking. See
        # the note on `all_robots` above run()'s signature -- this is
        # what stops a partial "RECONNECT FAILED" run from narrowing
        # the sync down to just the robot(s) it touched.
        ready_keys = {robot.key for robot in ready}

        already_linked = [
            robot for robot in all_robots
            if robot.sync_status == "LINKED"
            and robot.key not in ready_keys
        ]

        peers = [
            RobotSyncManager.peer_address(robot)
            for robot in already_linked + ready
        ]

        # Positionally aligned with `peers` -- blank for any peer
        # that wasn't discovered by MAC. ignoAPI's own sync watchdog
        # (syncpeer_launch's per-launch MAC re-resolution) uses this
        # to keep re-pointing that peer at its current IP even if it
        # moves after LINK time, exactly like it already does for
        # MAC-based syncs created outside this app.
        peer_macs = [
            robot.mac
            for robot in already_linked + ready
        ]

        # --- 2: create both star syncs on the hub FIRST ------------
        try:
            log(None, "creating STAR sync 'server' on hub...")

            result = c.createSyncIgnoAPI(
                hub, api_port, SYNC_VARIABLE, peers,
                topology="star", runatstartup=True,
                mac=",".join(peer_macs)
            )

            log(None, "server sync: %s" % result)

            log(None, "creating STAR sync 'fleet_cid' on hub...")

            result = c.createSyncIgnoAPI(
                hub, api_port, FLEET_CID_VARIABLE, peers,
                topology="star", runatstartup=True,
                mac=",".join(peer_macs)
            )

            log(None, "fleet_cid sync: %s" % result)

        except Exception as error:
            log(None, "COULD NOT CREATE SYNC: %s" % error)
            for robot in ready:
                robot.sync_status = "SYNC FAILED"
                robot.sync_error = "could not create star sync on hub: %s" % error
            done()
            return

        # createSyncIgnoAPI() returns once the hub has ACCEPTED the
        # request, not once every peer's boxes are actually wired up
        # and ready to forward. Give that fan-out a fixed head start
        # before any per-robot link attempt starts -- see
        # SYNC_FANOUT_SETTLE_DELAY above for why.
        log(
            None,
            "waiting %.1fs for sync fan-out to settle across %d peer(s)..."
            % (SYNC_FANOUT_SETTLE_DELAY, len(peers))
        )

        time.sleep(SYNC_FANOUT_SETTLE_DELAY)

        sync_created_at = time.time()

        # --- 3: required variables, created manually if missing ----
        still_ready = []

        for robot in ready:

            robot.sync_status = "CHECKING VARS..."

            log(robot, "checking required variables...")

            ok, message = RobotSyncManager.ensure_variables_exist(
                RobotSyncManager.peer_address(robot),
                api_port,
                AppSettings.variables,
                lambda peer, text, robot=robot: log(robot, text)
            )

            if not ok:
                robot.sync_status = "SYNC FAILED"
                robot.sync_error = message
                log(robot, message)
                continue

            still_ready.append(robot)

        ready = still_ready

        if not ready:
            log(None, "no robots had all required variables")
            done()
            return

        # --- 4: configure each robot --------------------------------
        # This only creates the robot-side combine/link and confirms
        # ignoAPI ACCEPTED the link RPC -- it does not yet mean the
        # data has reached the hub. See combine_and_link()'s docstring
        # for why that check moved off the robot. Robots that get
        # accepted here go to "VERIFYING..." and are confirmed for
        # real (LINKED / SYNC FAILED) in step 4b, hub-side.
        verify_candidates = []

        for robot in ready:

            robot.sync_status = "LINKING..."

            log(
                robot,
                "linking (%.1fs since sync fan-out started)..."
                % (time.time() - sync_created_at)
            )

            ok, message = RobotSyncManager.configure_robot(
                RobotSyncManager.peer_address(robot),
                api_port,
                lambda peer, text, robot=robot: log(robot, text)
            )

            if not ok:
                robot.sync_status = "SYNC FAILED"
                robot.sync_error = message
                log(robot, message)
                continue

            robot.sync_status = "VERIFYING..."
            robot.sync_error = ""
            log(robot, message)

            verify_candidates.append(robot)

        # --- 4b: hub-side verification -------------------------------
        # Confirms each accepted robot's server_tx data actually
        # arrived at the hub's server_<host_tag>_rx box (or the bare
        # server_rx box, if this star sync only has one peer -- see
        # verify_server_links_on_hub()'s docstring), instead of
        # reconnecting to the robot to check propagation there. Sets
        # each candidate's final sync_status directly.
        #
        # peer_count=len(peers) is the FULL current star sync roster
        # (already_linked + ready, computed above), not just
        # len(verify_candidates) -- a "RECONNECT FAILED" run only
        # verifies the subset that failed, but the single-vs-multi rx
        # box naming depends on how many peers are actually in the
        # sync right now, not how many this round is (re)checking.
        if verify_candidates:

            log(None, "verifying links on hub...")

            RobotSyncManager.verify_server_links_on_hub(
                hub, api_port, verify_candidates, log,
                peer_count=len(peers)
            )

        # --- 5: hub-side fleet_cid aggregate ------------------------
        # Recomputed from the FULL roster, not just `ready`/this run's
        # batch, so a robot that was already LINKED before this run --
        # and untouched by it -- is not dropped from the combined c_id
        # roster just because reconnecting some OTHER robot happened
        # to trigger a rebuild of this combine.
        linked_peers = [
            RobotSyncManager.peer_address(robot)
            for robot in all_robots
            if robot.sync_status == "LINKED"
        ]

        if linked_peers:

            log(None, "combining fleet c_id on hub...")

            ok, message = RobotSyncManager.configure_hub_fleet_cid(
                hub, api_port, linked_peers,
                lambda peer, text: log(None, text)
            )

            log(None, "hub fleet_cid: %s" % message)

        # --- 6: fleet-wide FTP server on the hub, shared with every
        # currently-linked robot. Uses the same `linked_peers` full
        # roster as step 5, so previously-linked robots keep their FTP
        # access even when this run only touched some subset of them.
        if linked_peers:

            RobotSyncManager.configure_fleet_ftp(
                hub, api_port, linked_peers, log
            )

        done()

    # ========================================================
    # DISCONNECT  (full reverse of run() / configure_robot())
    # ========================================================

    @staticmethod
    def erase_hub_syncs(hub, api_port, log):
        """
        Completely erases the hub's sync configuration -- both star
        sync MODULES ("server" and "fleet_cid", via deleteModule() on
        each variable name, which cascades through ignoAPI's own
        delete_variable() to their _rx/_tx/_status boxes here AND the
        matching rows on every currently-linked peer) and the hub's
        own fleet_cid combine artifacts, which live OUTSIDE either
        module's box set (see clear_hub_fleet_cid_leftovers()) and so
        are never touched by deleteModule() alone.

        This does NOT recreate anything -- disconnect() calls this
        first, unconditionally, then re-runs the exact same
        CONNECT & LINK chain (RobotSyncManager.run()) used for a fresh
        "LINK SELECTED ROBOTS" to rebuild from nothing but the robots
        that remain. Nuking both syncs down to bare variables first,
        rather than trying to trim a peer out of a live sync, is what
        guarantees no stale combine formula or leftover box can carry
        a disconnected robot's data forward -- see
        configure_hub_fleet_cid()'s single-source shortcut, which is
        exactly the path that was leaving a disconnected robot's c_id
        behind when only one peer remained.

        Never raises -- failures are reported through `log` the same
        way the rest of this class does.
        """

        for sync_name in (SYNC_VARIABLE, FLEET_CID_VARIABLE):

            log(None, "deleting sync module '%s' on hub..." % sync_name)

            try:
                result = c.deleteModule(
                    hub, api_port, sync_name, kind="sync"
                )
                log(None, "%s: %s" % (sync_name, result))

            except Exception as error:
                log(
                    None,
                    "could not delete sync module '%s': %s"
                    % (sync_name, error)
                )

        log(None, "clearing hub fleet_cid combine artifacts...")

        RobotSyncManager.clear_hub_fleet_cid_leftovers(
            hub, api_port, log
        )

    @staticmethod
    def clear_robot_link_artifacts(peer, api_port, log):
        """
        Reverses configure_robot() on ONE robot: removes every
        variable the linking process created there --

            server_*        (the "server" star sync's rx/tx/status/
                              peers boxes, plus the id_combined link)
            fleet_cid_*      (the "fleet_cid" star sync's boxes)
            id               (the combine row configure_robot() uses
                              for the "server" combine)
            id_combined      (that combine's output)

        -- using igo_delete() (via ignoClient's "delete" RPC, the same
        one delete_variable() already wraps) for each variable, plus
        deleteModule() for any sync module the robot may have
        registered for itself. Best-effort throughout: a variable or
        module that never existed is simply skipped, same as
        remove_old_link() / delete_variable() elsewhere in this file.
        """

        try:
            store = RobotSyncManager.read_peer_store(peer, api_port)
        except Exception as error:
            log(
                peer,
                "could not read variable store, skipping cleanup: %s"
                % error
            )
            store = {}

        stale_names = sorted(
            name for name in store
            if name.startswith("%s_" % SYNC_VARIABLE)
            or name.startswith("%s_" % FLEET_CID_VARIABLE)
            or name in ("id", "id_combined")
        )

        if stale_names:

            log(
                peer,
                "removing leftover variable(s): %s..."
                % ", ".join(stale_names)
            )

            for name in stale_names:
                RobotSyncManager.delete_variable(peer, api_port, name)

        else:
            log(peer, "no leftover link variables found")

        # Defensive: the sync module itself normally lives only on the
        # hub, with the fan-out simply writing plain variables into
        # each peer -- but if this robot ever registered a "server" or
        # "fleet_cid" sync module for itself, deleteModule() removes
        # it and everything it owns, the same way the hub's own sync
        # modules are torn down in erase_hub_syncs().
        try:
            modules = c.listModules(peer, api_port)
        except Exception as error:
            log(peer, "could not list modules to clean up: %s" % error)
            modules = {}

        for module_name in modules.get("sync", []):

            if module_name in (SYNC_VARIABLE, FLEET_CID_VARIABLE):

                log(
                    peer,
                    "deleting leftover sync module '%s'..." % module_name
                )

                try:
                    result = c.deleteModule(
                        peer, api_port, module_name, kind="sync"
                    )
                    log(peer, "%s: %s" % (module_name, result))

                except Exception as error:
                    log(
                        peer,
                        "could not delete module '%s': %s"
                        % (module_name, error)
                    )

    @staticmethod
    def clear_hub_fleet_cid_leftovers(hub, api_port, log):
        """
        Called instead of configure_hub_fleet_cid() when NO robots
        remain linked -- there is nothing left to combine, so this
        just removes the combine's own leftover boxes (fleet_cid_tx
        itself is already gone, deleted along with the sync module in
        erase_hub_syncs()).
        """
        log(None, "clearing hub fleet_cid combine leftovers...")
        RobotSyncManager.delete_variable(
            hub, api_port, "fleet_cid_combine"
        )
        RobotSyncManager.delete_variable(
            hub, api_port, "fleet_cid_combine_combined"
        )

    @staticmethod
    def disconnect(hub, api_port, robots, log, done, all_robots=None):
        """
        The full "DISCONNECT SELECTED" chain:

            1. work out which robots REMAIN linked once `robots` are
               taken out of the picture
            2. completely erase the hub's sync configuration --
               deleteModule() on BOTH "server" and "fleet_cid" (which
               cascades to their _rx/_tx/_status boxes here and on
               every currently-linked peer), plus the hub's own
               fleet_cid combine artifacts, which live outside either
               module's box set -- see erase_hub_syncs()
            3. on EACH disconnected robot: delete every leftover
               server_* / fleet_cid_* / id / id_combined variable the
               linking process created there, and any sync module it
               registered for itself
            4. if any robots remain linked, rebuild EVERYTHING for
               them by re-running RobotSyncManager.run() -- the exact
               same CONNECT & LINK chain a fresh "LINK SELECTED
               ROBOTS" uses -- so the star syncs, per-robot links, hub
               fleet_cid aggregate, and fleet FTP server are all
               recreated from nothing but the remaining robots, with
               the same CONNECTING/CHECKING VARS/LINKING progression
               shown in the UI as an original connect. If none remain,
               the fleet FTP server is deleted too and nothing is
               rebuilt.

        Step 2 erasing BOTH syncs completely, rather than trying to
        trim one peer out of a live sync, is what guarantees no stale
        combine formula or leftover box can carry the disconnected
        robot's data forward into the rebuild in step 4 -- see
        erase_hub_syncs()'s docstring.

        `robots` is whoever THIS call should disconnect -- e.g. the
        ticked robots for "DISCONNECT SELECTED". `all_robots` is the
        full current roster, used the same way run() uses it: to work
        out who REMAINS linked, never just from `robots` alone.
        """

        if all_robots is None:
            all_robots = robots

        target_keys = {robot.key for robot in robots}

        # Snapshot who remains linked BEFORE marking the targets as
        # disconnecting, so this robot's own current "LINKED" status
        # isn't accidentally read after being overwritten below.
        remaining_linked = [
            robot for robot in all_robots
            if robot.sync_status == "LINKED"
            and robot.key not in target_keys
        ]

        for robot in robots:
            robot.sync_status = "DISCONNECTING..."
            robot.sync_error = ""

        # --- 2: erase the hub's sync configuration completely -------
        log(None, "erasing hub sync configuration completely...")

        RobotSyncManager.erase_hub_syncs(hub, api_port, log)

        # --- 3: strip each disconnected robot's own link artifacts ---
        for robot in robots:

            peer = RobotSyncManager.peer_address(robot)

            log(robot, "removing link data from robot...")

            try:
                RobotSyncManager.clear_robot_link_artifacts(
                    peer, api_port,
                    lambda p, text, robot=robot: log(robot, text)
                )

                robot.sync_status = ""
                robot.sync_error = ""
                robot.sync_selected = False

                log(robot, "disconnected")

            except Exception as error:
                robot.sync_status = "SYNC FAILED"
                robot.sync_error = "disconnect cleanup failed: %s" % error
                log(robot, "disconnect cleanup failed: %s" % error)

        # --- 4: rebuild from nothing but the remaining robots --------
        if not remaining_linked:

            log(
                None,
                "no robots remain linked -- deleting fleet FTP server..."
            )

            try:
                result = c.deleteModule(
                    hub, api_port, FLEET_FTP_NAME, kind="ftp"
                )
                log(None, "fleet ftp: %s" % result)

                # The server this cache pointed at is gone -- clear it
                # so the next configure_fleet_ftp() call (even for the
                # exact same peer set as before) doesn't mistake this
                # for "unchanged, nothing to do" and skip recreating it.
                RobotSyncManager._ftp_configured_peers = None

            except Exception as error:
                log(
                    None,
                    "could not delete fleet FTP server: %s" % error
                )

            done()
            return

        log(
            None,
            "rebuilding sync for %d remaining robot(s)..."
            % len(remaining_linked)
        )

        # RobotSyncManager.run() treats `remaining_linked` as a fresh
        # "LINK SELECTED ROBOTS" run -- it reconnects (a no-op for a
        # robot that's already ROBOT_CONNECTED), recreates both star
        # syncs, waits out the fan-out settle delay, and re-links each
        # robot, driving robot.sync_status through the same
        # CONNECTING.../CHECKING VARS.../LINKING... progression the UI
        # shows for an original connect -- rather than leaving these
        # robots sitting at "LINKED" throughout a silent rebuild.
        # `all_robots=remaining_linked` here (not the full roster)
        # is deliberate: the hub side was JUST erased down to nothing
        # in step 2, so the peer list for the new star syncs should be
        # built from exactly these robots, not from any other robot's
        # possibly-stale "LINKED" flag.
        RobotSyncManager.run(
            hub, api_port, remaining_linked, log, done,
            all_robots=remaining_linked
        )


# ============================================================
# RADAR
# ============================================================

class Radar:

    def __init__(
        self,
        center_x,
        center_y,
        radius
    ):

        self.center_x = center_x

        self.center_y = center_y

        self.radius = radius

        self.angle = 0.0

    def update(self, dt):

        self.angle += (
            SWEEP_SPEED_DEGREES *
            dt
        )

        self.angle %= 360

    def draw(
        self,
        surface,
        robots
    ):

        center = (
            int(self.center_x),
            int(self.center_y)
        )

        pygame.draw.circle(
            surface,
            RADAR_BACKGROUND,
            center,
            int(self.radius)
        )

        # Radar rings.
        for index in range(1, 6):

            ring_radius = int(
                self.radius *
                index /
                5
            )

            pygame.draw.circle(
                surface,
                GRID_DARK,
                center,
                ring_radius,
                width=1
            )

        # Outer ring.
        pygame.draw.circle(
            surface,
            GRID,
            center,
            int(self.radius),
            width=2
        )

        # Cross lines.
        pygame.draw.line(
            surface,
            GRID_DARK,
            (
                int(
                    self.center_x -
                    self.radius
                ),
                int(self.center_y)
            ),
            (
                int(
                    self.center_x +
                    self.radius
                ),
                int(self.center_y)
            ),
            width=1
        )

        pygame.draw.line(
            surface,
            GRID_DARK,
            (
                int(self.center_x),
                int(
                    self.center_y -
                    self.radius
                )
            ),
            (
                int(self.center_x),
                int(
                    self.center_y +
                    self.radius
                )
            ),
            width=1
        )

        diagonal = int(
            self.radius /
            math.sqrt(2)
        )

        pygame.draw.line(
            surface,
            GRID_DARK,
            (
                int(
                    self.center_x -
                    diagonal
                ),
                int(
                    self.center_y -
                    diagonal
                )
            ),
            (
                int(
                    self.center_x +
                    diagonal
                ),
                int(
                    self.center_y +
                    diagonal
                )
            ),
            width=1
        )

        pygame.draw.line(
            surface,
            GRID_DARK,
            (
                int(
                    self.center_x -
                    diagonal
                ),
                int(
                    self.center_y +
                    diagonal
                )
            ),
            (
                int(
                    self.center_x +
                    diagonal
                ),
                int(
                    self.center_y -
                    diagonal
                )
            ),
            width=1
        )

        self.draw_sweep(
            surface
        )

        pygame.draw.circle(
            surface,
            GREEN,
            center,
            5
        )

        pygame.draw.circle(
            surface,
            GREEN_BRIGHT,
            center,
            11,
            width=1
        )

        for robot in robots:

            self.draw_robot(
                surface,
                robot,
                robot.sync_selected
            )

    def draw_sweep(self, surface):

        center = (
            int(self.center_x),
            int(self.center_y)
        )

        radians = math.radians(
            self.angle - 90
        )

        end_x = int(
            self.center_x +
            math.cos(radians) *
            self.radius
        )

        end_y = int(
            self.center_y +
            math.sin(radians) *
            self.radius
        )

        pygame.draw.line(
            surface,
            GREEN_BRIGHT,
            center,
            (
                end_x,
                end_y
            ),
            width=2
        )

        for index in range(1, 25):

            trail_angle = (
                self.angle -
                index * 2
            )

            radians = math.radians(
                trail_angle - 90
            )

            end_x = int(
                self.center_x +
                math.cos(radians) *
                self.radius
            )

            end_y = int(
                self.center_y +
                math.sin(radians) *
                self.radius
            )

            intensity = max(
                5,
                120 -
                index * 4
            )

            pygame.draw.line(
                surface,
                (
                    0,
                    intensity,
                    intensity // 2
                ),
                center,
                (
                    end_x,
                    end_y
                ),
                width=1
            )

    def draw_robot(
        self,
        surface,
        robot,
        selected
    ):

        x = int(
            self.center_x +
            robot.x_offset *
            self.radius
        )

        y = int(
            self.center_y +
            robot.y_offset *
            self.radius
        )

        position = (
            x,
            y
        )

        color = get_status_color(
            robot.status
        )

        if selected:

            pygame.draw.circle(
                surface,
                color,
                position,
                18,
                width=1
            )

            pygame.draw.circle(
                surface,
                color,
                position,
                12,
                width=1
            )

        pygame.draw.circle(
            surface,
            color,
            position,
            8 if selected else 5
        )


# ============================================================
# MAIN APPLICATION
# ============================================================

class RobotConnectorApplication:

    def __init__(self):

        pygame.init()

        pygame.display.set_caption(
            "ROBOT CONNECTOR"
        )

        # Get desktop resolution.
        desktop_sizes = (
            pygame.display.get_desktop_sizes()
        )

        if desktop_sizes:

            (
                desktop_width,
                desktop_height
            ) = desktop_sizes[0]

        else:

            info = (
                pygame.display.Info()
            )

            desktop_width = (
                info.current_w
            )

            desktop_height = (
                info.current_h
            )

        # Borderless fullscreen-sized window.
        self.screen = pygame.display.set_mode(
            (
                desktop_width,
                desktop_height
            ),
            pygame.NOFRAME
        )

        (
            self.window_width,
            self.window_height
        ) = self.screen.get_size()

        self.clock = pygame.time.Clock()

        # Fonts.
        self.font_small = (
            pygame.font.SysFont(
                "consolas",
                14
            )
        )

        self.font_normal = (
            pygame.font.SysFont(
                "consolas",
                17
            )
        )

        self.font_large = (
            pygame.font.SysFont(
                "consolas",
                25,
                bold=True
            )
        )

        self.font_title = (
            pygame.font.SysFont(
                "consolas",
                34,
                bold=True
            )
        )

        # Layout.
        self.radar_area_width = int(
            self.window_width *
            RADAR_WIDTH_RATIO
        )

        self.radar_center_x = (
            self.radar_area_width //
            2
        )

        # Nudge the radar down from dead-center so it sits a
        # bit lower under the header.
        self.radar_vertical_offset = 55

        self.radar_center_y = (
            self.window_height //
            2
        ) + self.radar_vertical_offset

        self.radar_radius = min(
            self.radar_center_x - 80,
            (
                self.window_height -
                self.radar_center_y
            ) - 90
        )

        self.radar_radius = max(
            100,
            self.radar_radius
        )

        self.radar = Radar(
            self.radar_center_x,
            self.radar_center_y,
            self.radar_radius
        )

        # Robot registry.
        self.registry = RobotRegistry()

        # UI state.
        self.running = True

        # Clicking a robot's card toggles robot.sync_selected -- that
        # one flag now drives card highlighting, the radar highlight,
        # and which robots LINK acts on. There is no separate
        # single "selected" robot any more.
        self.scroll_offset = 0

        self.robot_rects = {}

        # -- star sync / id-forwarding (ported from make_sync.py) --
        self.sync_button_rect = None

        self.reconnect_failed_button_rect = None

        self.disconnect_button_rect = None

        self.syncing = False

        self.mdns_mode_rect = None

        self.udp_mode_rect = None

        self.mac_mode_rect = None

        self.mode_switch_rect = None

        self.discovery_mode = (
            MODE_MDNS
        )

        # -- settings panel (gear icon, top-right of the side panel) --
        self.panel_view = "robots"   # "robots" | "settings" | "mac_entry"

        self.settings_icon_rect = None

        self.settings_back_rect = None

        # FTP folder field: buffer is what's on screen/being typed;
        # AppSettings.ftp_folder is only updated when SAVE is clicked.
        self.settings_ftp_folder_rect = None

        self.settings_ftp_folder_buffer = AppSettings.ftp_folder

        self.settings_ftp_save_rect = None

        # FTP link addressing (MDNS / IP ADDRESS) buttons -- takes
        # effect immediately on click, no buffer/SAVE step needed
        # since there's nothing to type.
        self.settings_ftp_link_mdns_rect = None

        self.settings_ftp_link_ip_rect = None

        # Variables list: existing ones each get a remove ("x") rect;
        # the add box/button work the same buffer-then-commit way as
        # the FTP folder field above.
        self.settings_variable_remove_rects = {}

        self.settings_new_variable_rect = None

        self.settings_new_variable_buffer = ""

        self.settings_add_variable_rect = None

        # -- MAC entry panel (opened from the mode switch's MAC
        # segment) -- same buffer-then-commit / removable-row pattern
        # as the variables list above, but editing AppSettings.manual_macs.
        self.mac_entry_back_rect = None

        self.mac_remove_rects = {}

        self.mac_new_mac_rect = None

        self.mac_new_mac_buffer = ""

        self.mac_add_rect = None

        self.mac_connect_rect = None

        # Which single-line field (if any) currently has keyboard
        # focus: None | "ftp_folder" | "new_variable" | "new_mac".
        self.active_text_field = None

        # 0.0 = knob parked on mDNS side, 0.5 = MAC, 1.0 = UDP side.
        # Animated smoothly in update().
        self.mode_slider_pos = 0.0

        self.status_message = (
            "mDNS DISCOVERY READY"
        )

        # Discovery scanners.
        self.mdns_scanner = (
            MDNSRobotScanner(
                self.registry,
                self.set_status
            )
        )

        self.udp_scanner = (
            UDPRobotScanner(
                self.registry,
                self.set_status
            )
        )

        self.mac_scanner = (
            MACRobotScanner(
                self.registry,
                self.set_status
            )
        )

        # Start default mode.
        self.start_discovery_mode(
            MODE_MDNS
        )

    # ========================================================
    # STATUS
    # ========================================================

    def set_status(self, message):

        self.status_message = (
            message
        )

    # ========================================================
    # SETTINGS PANEL
    # ========================================================

    def open_settings(self):

        self.panel_view = "settings"

        # Refresh the folder buffer from the live setting each time
        # the panel opens, so it never shows a stale unsaved edit
        # from a previous visit.
        self.settings_ftp_folder_buffer = AppSettings.ftp_folder

        self.active_text_field = None

    def close_settings(self):

        self.panel_view = "robots"

        self.active_text_field = None

    def toggle_settings(self):

        if self.panel_view == "settings":
            self.close_settings()
        else:
            self.open_settings()

    def commit_ftp_folder(self):

        folder = self.settings_ftp_folder_buffer.strip()

        if not folder:

            self.set_status(
                "FTP FOLDER CANNOT BE BLANK"
            )

            return

        AppSettings.ftp_folder = folder

        self.settings_ftp_folder_buffer = folder

        self.active_text_field = None

        self.set_status(
            f"FTP FOLDER SET: {folder}"
        )

    def commit_new_variable(self):

        name = self.settings_new_variable_buffer.strip()

        if not name:
            return

        if name in AppSettings.variables:

            self.set_status(
                f"'{name}' IS ALREADY IN THE LIST"
            )

        else:

            AppSettings.variables.append(name)

            self.set_status(
                f"ADDED VARIABLE: {name}"
            )

        self.settings_new_variable_buffer = ""

    def remove_variable(self, name):

        if name in AppSettings.variables:

            AppSettings.variables.remove(name)

            self.set_status(
                f"REMOVED VARIABLE: {name}"
            )

    # ========================================================
    # MAC ENTRY PANEL
    #   Opened from the MAC segment of the mode switch. Lets the
    #   user type in one or more MAC addresses (ADD appends each
    #   one, same pattern as the variables list above) before
    #   CONNECT actually switches discovery into MODE_MAC.
    # ========================================================

    def open_mac_entry(self):

        self.panel_view = "mac_entry"

        self.mac_new_mac_buffer = ""

        self.active_text_field = None

    def close_mac_entry(self):

        self.panel_view = "robots"

        self.active_text_field = None

    def commit_new_mac(self):

        typed = self.mac_new_mac_buffer.strip()

        if not typed:
            return

        mac = norm_mac(typed)

        if len(mac) != 17:

            self.set_status(
                f"'{typed}' DOESN'T LOOK LIKE A MAC ADDRESS"
            )

            return

        if mac in AppSettings.manual_macs:

            self.set_status(
                f"{mac} IS ALREADY IN THE LIST"
            )

        else:

            AppSettings.manual_macs.append(mac)

            self.set_status(
                f"ADDED MAC: {mac}"
            )

        self.mac_new_mac_buffer = ""

    def remove_manual_mac(self, mac):

        if mac in AppSettings.manual_macs:

            AppSettings.manual_macs.remove(mac)

            self.set_status(
                f"REMOVED MAC: {mac}"
            )

    def connect_mac_mode(self):
        """
        CONNECT on the MAC panel -- requires at least one MAC typed
        in, then actually switches discovery into MODE_MAC (same
        transition as clicking the mDNS/UDP segments) and returns to
        the robot list.
        """

        if not AppSettings.manual_macs:

            self.set_status(
                "ADD AT LEAST ONE MAC ADDRESS FIRST"
            )

            return

        self.close_mac_entry()

        self.start_discovery_mode(
            MODE_MAC
        )

    # ========================================================
    # STAR SYNC / ID-FORWARDING  (ported from make_sync.py)
    # ========================================================

    def run_star_sync(self, robots, retry_round=0):
        """
        Runs off the UI thread: connects every ticked robot, makes sure
        it has the required variables, creates the "server" and
        "fleet_cid" star syncs on the hub, then wires up each robot's
        combine()+link() (and the hub's own fleet_cid combine).

        `robots` may be a partial subset (e.g. RECONNECT FAILED only
        passes the SYNC FAILED ones) -- RobotSyncManager.run() also
        gets the full registry snapshot so it never narrows the hub's
        syncs down to just this subset. See run()'s docstring.

        `retry_round` counts automatic reconnect passes this same batch
        of robots has already been through (0 the first time it's
        called, whether that's from the LINK button or the RECONNECT
        FAILED button). Whatever is still SYNC FAILED when this batch
        finishes gets requeued and retried automatically -- no button
        click needed -- until it's LINKED or AUTO_RECONNECT_MAX_ATTEMPTS
        extra rounds have been tried. self.syncing stays True across
        every round of the same batch, so the UI keeps showing
        "CONNECTING & LINKING..." until it's genuinely done, not just
        done with one round.
        """

        def log(robot, text):

            if robot is None:
                self.set_status(f"SYNC: {text}")
            else:
                self.set_status(f"SYNC {robot.name}: {text}")

            print(
                f"[SYNC] "
                f"{robot.name if robot else 'HUB'}: {text}"
            )

        def done():

            linked = sum(
                robot.sync_status == "LINKED"
                for robot in robots
            )

            still_failed = [
                robot for robot in robots
                if robot.sync_status == "SYNC FAILED"
            ]

            if still_failed and retry_round < AUTO_RECONNECT_MAX_ATTEMPTS:

                self.set_status(
                    f"SYNC: {linked}/{len(robots)} LINKED -- "
                    f"AUTO-RECONNECTING {len(still_failed)} FAILED "
                    f"ROBOT(S) IN {AUTO_RECONNECT_DELAY:.0f}s "
                    f"(RETRY {retry_round + 1}/{AUTO_RECONNECT_MAX_ATTEMPTS})..."
                )

                def retry_after_delay():

                    time.sleep(AUTO_RECONNECT_DELAY)

                    for robot in still_failed:
                        robot.sync_status = "QUEUED"
                        robot.sync_error = ""

                    self.run_star_sync(
                        still_failed,
                        retry_round=retry_round + 1
                    )

                threading.Thread(
                    target=retry_after_delay,
                    daemon=True
                ).start()

                # Left True on purpose -- the batch isn't actually
                # finished, it's just waiting out AUTO_RECONNECT_DELAY
                # before the next round.
                return

            self.syncing = False

            if still_failed:

                self.set_status(
                    f"SYNC GAVE UP: {linked}/{len(robots)} LINKED -- "
                    f"{len(still_failed)} STILL FAILED AFTER "
                    f"{retry_round + 1} ATTEMPT(S)"
                )

            else:

                self.set_status(
                    f"SYNC COMPLETE: {linked}/{len(robots)} LINKED"
                )

        RobotSyncManager.run(
            SYNC_HUB,
            SYNC_API_PORT,
            robots,
            log,
            done,
            all_robots=self.registry.get_robots()
        )

    def run_disconnect_selected(self, robots):
        """
        Runs off the UI thread: the full reverse of run_star_sync()
        for `robots` -- rebuilds the hub's star syncs, fleet_cid
        combine and fleet FTP server from whichever robots REMAIN
        linked, and strips every RoboSync-created variable off each
        disconnected robot. See RobotSyncManager.disconnect()'s
        docstring for the full chain.
        """

        def log(robot, text):

            if robot is None:
                self.set_status(f"DISCONNECT: {text}")
            else:
                self.set_status(f"DISCONNECT {robot.name}: {text}")

            print(
                f"[DISCONNECT] "
                f"{robot.name if robot else 'HUB'}: {text}"
            )

        def done():

            self.syncing = False

            failed = [
                robot for robot in robots
                if robot.sync_status == "SYNC FAILED"
            ]

            if failed:
                self.set_status(
                    f"DISCONNECT: {len(robots) - len(failed)}/"
                    f"{len(robots)} DISCONNECTED -- "
                    f"{len(failed)} FAILED TO CLEAN UP"
                )
            else:
                self.set_status(
                    f"DISCONNECTED {len(robots)} ROBOT(S)"
                )

        RobotSyncManager.disconnect(
            SYNC_HUB,
            SYNC_API_PORT,
            robots,
            log,
            done,
            all_robots=self.registry.get_robots()
        )

    # ========================================================
    # DISCOVERY MODE SWITCH
    # ========================================================

    def start_discovery_mode(
        self,
        mode
    ):

        print(
            f"[SYSTEM] Switching discovery mode "
            f"to {mode}"
        )

        # Stop all scanners first.
        self.mdns_scanner.stop()

        self.udp_scanner.stop()

        self.mac_scanner.stop()

        # Disconnect old robots.
        self.registry.close_all_connections()

        # Clear robot list.
        self.registry.clear()

        self.scroll_offset = 0

        self.discovery_mode = mode

        if mode == MODE_MDNS:

            self.set_status(
                "mDNS: STARTING DISCOVERY"
            )

            self.mdns_scanner.start()

        elif mode == MODE_UDP:

            self.set_status(
                "UDP: STARTING BROADCAST DISCOVERY"
            )

            self.udp_scanner.start()

        elif mode == MODE_MAC:

            self.set_status(
                "MAC: RESOLVING ADDRESS(ES)..."
            )

            self.mac_scanner.start()

    # ========================================================
    # PANEL
    # ========================================================

    def get_panel_rect(self):

        return pygame.Rect(
            self.radar_area_width,
            0,
            (
                self.window_width -
                self.radar_area_width
            ),
            self.window_height
        )

    # ========================================================
    # EVENTS
    # ========================================================

    def handle_events(self):

        for event in pygame.event.get():

            if event.type == pygame.QUIT:

                self.running = False

            elif event.type == pygame.KEYDOWN:

                if self.active_text_field:

                    self.handle_text_field_keydown(
                        event
                    )

                elif event.key == pygame.K_ESCAPE:

                    if self.panel_view == "settings":
                        self.close_settings()
                    elif self.panel_view == "mac_entry":
                        self.close_mac_entry()
                    else:
                        self.running = False

                elif event.key == pygame.K_r:

                    self.manual_rescan()

            elif event.type == pygame.MOUSEWHEEL:

                self.scroll_offset -= (
                    event.y * 45
                )

                self.scroll_offset = max(
                    0,
                    self.scroll_offset
                )

            elif event.type == pygame.MOUSEBUTTONDOWN:

                if event.button == 1:

                    self.handle_click(
                        event.pos
                    )

    def handle_text_field_keydown(self, event):
        """
        Routes a keypress to whichever buffer self.active_text_field
        names. ESCAPE just blurs the field (does not quit the app --
        the ESCAPE-quits-app case in handle_events only fires when no
        field is focused). ENTER commits the field, same as clicking
        its SAVE/ADD button.
        """

        if event.key == pygame.K_ESCAPE:

            self.active_text_field = None

            return

        if event.key == pygame.K_RETURN:

            if self.active_text_field == "ftp_folder":
                self.commit_ftp_folder()
            elif self.active_text_field == "new_variable":
                self.commit_new_variable()
            elif self.active_text_field == "new_mac":
                self.commit_new_mac()

            return

        if self.active_text_field == "ftp_folder":
            buffer_name = "settings_ftp_folder_buffer"
            max_length = 240
        elif self.active_text_field == "new_mac":
            buffer_name = "mac_new_mac_buffer"
            max_length = 17
        else:
            buffer_name = "settings_new_variable_buffer"
            max_length = 60

        buffer = getattr(self, buffer_name)

        if event.key == pygame.K_BACKSPACE:

            buffer = buffer[:-1]

        elif event.unicode and event.unicode.isprintable():

            if len(buffer) < max_length:
                buffer += event.unicode

        setattr(self, buffer_name, buffer)

    # ========================================================
    # MANUAL RESCAN
    # ========================================================

    def manual_rescan(self):

        print(
            "[SYSTEM] Manual rescan requested."
        )

        self.registry.close_all_connections()

        self.registry.clear()

        self.scroll_offset = 0

        if self.discovery_mode == MODE_MDNS:

            threading.Thread(
                target=self.mdns_scanner.scan_once,
                daemon=True
            ).start()

        elif self.discovery_mode == MODE_UDP:

            threading.Thread(
                target=self.udp_scanner.scan_once,
                daemon=True
            ).start()

        elif self.discovery_mode == MODE_MAC:

            threading.Thread(
                target=self.mac_scanner.scan_once,
                daemon=True
            ).start()

    # ========================================================
    # CLICK HANDLING
    # ========================================================

    def handle_click(self, mouse_pos):

        # ----------------------------------------------------
        # Settings icon -- toggles the panel between the robot list
        # and the settings view. Checked first, before anything else,
        # so it always works regardless of which view is showing.
        # ----------------------------------------------------

        if (
            self.settings_icon_rect and
            self.settings_icon_rect.collidepoint(
                mouse_pos
            )
        ):

            self.toggle_settings()

            return

        # ----------------------------------------------------
        # Settings view -- everything else on the panel in this
        # branch is settings-only widgets, handled separately so
        # they do not fall through into the robot-list click logic
        # below (which assumes the robot list is what's showing).
        # ----------------------------------------------------

        if self.panel_view == "settings":

            self.handle_settings_click(
                mouse_pos
            )

            return

        # ----------------------------------------------------
        # MAC entry panel -- same idea as the settings branch
        # above: while this dialog is open, every click on the
        # panel belongs to it.
        # ----------------------------------------------------

        if self.panel_view == "mac_entry":

            self.handle_mac_entry_click(
                mouse_pos
            )

            return

        # ----------------------------------------------------
        # Discovery mode switch.
        # ----------------------------------------------------

        if (
            self.mdns_mode_rect and
            self.mdns_mode_rect.collidepoint(
                mouse_pos
            )
        ):

            if self.discovery_mode != MODE_MDNS:

                self.start_discovery_mode(
                    MODE_MDNS
                )

            return

        # MAC doesn't switch modes directly on click -- it opens the
        # MAC entry dialog so a MAC address can be typed in first;
        # CONNECT inside that dialog is what actually switches
        # discovery into MODE_MAC (see connect_mac_mode()).
        if (
            self.mac_mode_rect and
            self.mac_mode_rect.collidepoint(
                mouse_pos
            )
        ):

            self.open_mac_entry()

            return

        if (
            self.udp_mode_rect and
            self.udp_mode_rect.collidepoint(
                mouse_pos
            )
        ):

            if self.discovery_mode != MODE_UDP:

                self.start_discovery_mode(
                    MODE_UDP
                )

            return

        # ----------------------------------------------------
        # Robot selection -- clicking a card TOGGLES it in/out of the
        # selected set (robot.sync_selected). A second click on the
        # same card deselects it. This selected set is what LINK
        # acts on -- there is no separate single "target" robot or
        # tick-box any more.
        # ----------------------------------------------------

        for key, rect in list(
            self.robot_rects.items()
        ):

            if rect.collidepoint(
                mouse_pos
            ):

                robot = (
                    self.registry.get_robot(
                        key
                    )
                )

                if robot:

                    robot.sync_selected = (
                        not robot.sync_selected
                    )

                    self.set_status(
                        f"{'SELECTED' if robot.sync_selected else 'DESELECTED'}: "
                        f"{robot.name}"
                    )

                    print(
                        f"[UI] "
                        f"{'Selected' if robot.sync_selected else 'Deselected'} "
                        f"{robot.name}"
                    )

                return

        # ----------------------------------------------------
        # Connect + link selected (connect, ensure variables, create
        # both star syncs, then combine/link -- runs against whatever
        # is ticked).
        # ----------------------------------------------------

        if (
            self.sync_button_rect and
            self.sync_button_rect.collidepoint(
                mouse_pos
            )
        ):

            if self.syncing:
                return

            robots = [
                robot
                for robot in self.registry.get_robots()
                if robot.sync_selected
            ]

            if not robots:

                self.set_status(
                    "SELECT ROBOTS TO LINK FIRST"
                )

                return

            for robot in robots:

                robot.sync_status = "QUEUED"
                robot.sync_error = ""

            self.syncing = True

            self.set_status(
                f"CONNECTING & LINKING {len(robots)} ROBOT(S)..."
            )

            threading.Thread(
                target=self.run_star_sync,
                args=(robots,),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # Reconnect only the robots currently marked SYNC FAILED --
        # same CONNECT & LINK chain as the LINK button, just scoped
        # to the failed subset instead of whatever is ticked. Does
        # NOT touch selection (robot.sync_selected) at all.
        # ----------------------------------------------------

        if (
            self.reconnect_failed_button_rect and
            self.reconnect_failed_button_rect.collidepoint(
                mouse_pos
            )
        ):

            if self.syncing:
                return

            failed_robots = [
                robot
                for robot in self.registry.get_robots()
                if robot.sync_status == "SYNC FAILED"
            ]

            if not failed_robots:

                self.set_status(
                    "NO SYNC FAILED ROBOTS TO RECONNECT"
                )

                return

            for robot in failed_robots:

                robot.sync_status = "QUEUED"
                robot.sync_error = ""

            self.syncing = True

            self.set_status(
                f"RECONNECTING {len(failed_robots)} FAILED ROBOT(S)..."
            )

            threading.Thread(
                target=self.run_star_sync,
                args=(failed_robots,),
                daemon=True
            ).start()

            return

        # ----------------------------------------------------
        # Disconnect selected -- full reverse of LINK: rebuilds the
        # hub's sync/FTP configuration from whichever robots remain
        # linked, and strips every RoboSync-created variable off each
        # disconnected robot. Acts only on the currently-LINKED robots
        # among whatever is ticked -- a selected robot that was never
        # linked has nothing to disconnect.
        # ----------------------------------------------------

        if (
            self.disconnect_button_rect and
            self.disconnect_button_rect.collidepoint(
                mouse_pos
            )
        ):

            if self.syncing:
                return

            robots = [
                robot
                for robot in self.registry.get_robots()
                if robot.sync_selected
                and robot.sync_status == "LINKED"
            ]

            if not robots:

                self.set_status(
                    "SELECT LINKED ROBOTS TO DISCONNECT FIRST"
                )

                return

            self.syncing = True

            self.set_status(
                f"DISCONNECTING {len(robots)} ROBOT(S)..."
            )

            threading.Thread(
                target=self.run_disconnect_selected,
                args=(robots,),
                daemon=True
            ).start()

    # ========================================================
    # UPDATE
    # ========================================================

    def update(self, dt):

        self.radar.update(
            dt
        )

        # Animate the mDNS / MAC / UDP slider knob toward whichever
        # third matches the active discovery mode.
        if self.discovery_mode == MODE_MDNS:
            slider_target = 0.0
        elif self.discovery_mode == MODE_MAC:
            slider_target = 0.5
        else:
            slider_target = 1.0

        slider_diff = (
            slider_target -
            self.mode_slider_pos
        )

        slider_step = min(
            1.0,
            dt * 12.0
        )

        self.mode_slider_pos += (
            slider_diff *
            slider_step
        )

        if abs(
            slider_target -
            self.mode_slider_pos
        ) < 0.001:

            self.mode_slider_pos = (
                slider_target
            )

        robots = (
            self.registry.get_robots()
        )

        panel = (
            self.get_panel_rect()
        )

        device_top = 155

        device_bottom = (
            self.window_height -
            230
        )

        visible_height = (
            device_bottom -
            device_top
        )

        content_height = (
            len(robots) *
            (
                DEVICE_CARD_HEIGHT +
                DEVICE_CARD_GAP
            )
        )

        max_scroll = max(
            0,
            content_height -
            visible_height
        )

        self.scroll_offset = max(
            0,
            min(
                self.scroll_offset,
                max_scroll
            )
        )

    # ========================================================
    # HEADER
    # ========================================================

    def draw_header(self):

        draw_text(
            self.screen,
            "ROBOT CONNECTOR",
            self.font_title,
            GREEN,
            25,
            20
        )

        subtitle = (
            "MULTI-ROBOT NETWORK DISCOVERY"
        )

        draw_text(
            self.screen,
            subtitle,
            self.font_small,
            TEXT_DIM,
            27,
            65
        )

        if (
            self.discovery_mode ==
            MODE_MDNS
        ):

            active_scanning = (
                self.mdns_scanner
                .currently_scanning
            )

        else:

            active_scanning = (
                self.udp_scanner
                .currently_scanning
            )

        indicator_color = (
            CONNECTING
            if active_scanning
            else GREEN
        )

        pygame.draw.circle(
            self.screen,
            indicator_color,
            (
                29,
                98
            ),
            5
        )

        draw_text(
            self.screen,
            self.status_message,
            self.font_small,
            TEXT,
            43,
            92
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (
                25,
                125
            ),
            (
                self.radar_area_width -
                25,
                125
            ),
            width=1
        )

    # ========================================================
    # MODE SWITCH
    # ========================================================

    def draw_mode_switch(
        self,
        panel,
        mouse_pos
    ):

        # A single pill-shaped slider switch, now in three equal
        # thirds -- mDNS, MAC, UDP -- with a rounded knob that
        # glides to whichever third matches the active mode.

        x = (
            panel.left +
            PANEL_PADDING
        )

        y = 88

        total_width = (
            panel.width -
            PANEL_PADDING * 2
        )

        track_height = 44

        track_rect = pygame.Rect(
            x,
            y,
            total_width,
            track_height
        )

        self.mode_switch_rect = (
            track_rect
        )

        third_width = (
            total_width //
            3
        )

        # Three logical hit-zones -- left = mDNS, middle = MAC,
        # right = UDP. The last zone soaks up any rounding
        # remainder so the three always cover the full track.
        self.mdns_mode_rect = (
            pygame.Rect(
                x,
                y,
                third_width,
                track_height
            )
        )

        self.mac_mode_rect = (
            pygame.Rect(
                x + third_width,
                y,
                third_width,
                track_height
            )
        )

        self.udp_mode_rect = (
            pygame.Rect(
                x + third_width * 2,
                y,
                total_width - third_width * 2,
                track_height
            )
        )

        track_radius = (
            track_height //
            2
        )

        # Track background.
        pygame.draw.rect(
            self.screen,
            SLIDER_TRACK,
            track_rect,
            border_radius=track_radius
        )

        pygame.draw.rect(
            self.screen,
            BORDER,
            track_rect,
            width=1,
            border_radius=track_radius
        )

        # Sliding knob.
        knob_padding = 4

        knob_width = (
            third_width -
            knob_padding * 2
        )

        knob_height = (
            track_height -
            knob_padding * 2
        )

        knob_left_x = (
            x +
            knob_padding
        )

        knob_travel = (
            total_width -
            knob_padding * 2 -
            knob_width
        )

        knob_x = int(
            knob_left_x +
            knob_travel *
            self.mode_slider_pos
        )

        knob_rect = pygame.Rect(
            knob_x,
            y + knob_padding,
            knob_width,
            knob_height
        )

        # Soft glow behind the knob.
        glow_surface = pygame.Surface(
            (
                knob_rect.width + 16,
                knob_rect.height + 16
            ),
            pygame.SRCALPHA
        )

        pygame.draw.rect(
            glow_surface,
            (
                *ACCENT,
                60
            ),
            glow_surface.get_rect(),
            border_radius=(
                knob_height // 2 + 8
            )
        )

        self.screen.blit(
            glow_surface,
            (
                knob_rect.x - 8,
                knob_rect.y - 8
            )
        )

        pygame.draw.rect(
            self.screen,
            SLIDER_KNOB,
            knob_rect,
            border_radius=(
                knob_height //
                2
            )
        )

        # Labels. The label under the knob is drawn dark for
        # contrast against the bright knob; the other labels are
        # dimmed to show they're inactive.
        mdns_active = (
            self.discovery_mode ==
            MODE_MDNS
        )

        mac_active = (
            self.discovery_mode ==
            MODE_MAC
        )

        udp_active = (
            self.discovery_mode ==
            MODE_UDP
        )

        mdns_color = (
            BACKGROUND
            if mdns_active
            else TEXT_DIM
        )

        mac_color = (
            BACKGROUND
            if mac_active
            else TEXT_DIM
        )

        udp_color = (
            BACKGROUND
            if udp_active
            else TEXT_DIM
        )

        draw_text(
            self.screen,
            "mDNS",
            self.font_normal,
            mdns_color,
            self.mdns_mode_rect.centerx,
            self.mdns_mode_rect.centery,
            "center"
        )

        draw_text(
            self.screen,
            "MAC",
            self.font_normal,
            mac_color,
            self.mac_mode_rect.centerx,
            self.mac_mode_rect.centery,
            "center"
        )

        draw_text(
            self.screen,
            "UDP",
            self.font_normal,
            udp_color,
            self.udp_mode_rect.centerx,
            self.udp_mode_rect.centery,
            "center"
        )

    # ========================================================
    # ROBOT PANEL
    # ========================================================

    # ========================================================
    # SYNC FAILURE TOOLTIP
    #   Hovering a device card whose last sync attempt failed shows
    #   the actual reason (from robot.sync_error) instead of just
    #   the bare "SYNC FAILED" label.
    # ========================================================

    def draw_sync_error_tooltip(self, card_rect, message):

        text = "WHY: %s" % message

        rendered = self.font_small.render(
            text,
            True,
            TEXT
        )

        padding_x = 10
        padding_y = 6

        box_width = rendered.get_width() + padding_x * 2
        box_height = rendered.get_height() + padding_y * 2

        box_x = card_rect.left
        box_y = card_rect.top - box_height - 6

        # Keep the tooltip on screen even if the card is near the
        # top or the panel's right edge.
        if box_y < 4:
            box_y = card_rect.bottom + 6

        max_right = self.window_width - 8
        if box_x + box_width > max_right:
            box_x = max_right - box_width

        box_rect = pygame.Rect(
            box_x,
            box_y,
            box_width,
            box_height
        )

        pygame.draw.rect(
            self.screen,
            PANEL_BG_ALT,
            box_rect,
            border_radius=6
        )

        pygame.draw.rect(
            self.screen,
            FAILED,
            box_rect,
            width=1,
            border_radius=6
        )

        self.screen.blit(
            rendered,
            (
                box_rect.left + padding_x,
                box_rect.top + padding_y
            )
        )

    def handle_settings_click(self, mouse_pos):
        """
        Click routing while self.panel_view == "settings". Anywhere
        that isn't one of these specific widgets just blurs whatever
        text field was focused -- clicking off a field is how you
        stop typing in it without discarding the buffer.
        """

        if (
            self.settings_back_rect and
            self.settings_back_rect.collidepoint(mouse_pos)
        ):
            self.close_settings()
            return

        if (
            self.settings_ftp_folder_rect and
            self.settings_ftp_folder_rect.collidepoint(mouse_pos)
        ):
            self.active_text_field = "ftp_folder"
            return

        if (
            self.settings_ftp_save_rect and
            self.settings_ftp_save_rect.collidepoint(mouse_pos)
        ):
            self.commit_ftp_folder()
            return

        if (
            self.settings_ftp_link_mdns_rect and
            self.settings_ftp_link_mdns_rect.collidepoint(mouse_pos)
        ):
            AppSettings.ftp_link_mode = FTP_LINK_MODE_MDNS
            return

        if (
            self.settings_ftp_link_ip_rect and
            self.settings_ftp_link_ip_rect.collidepoint(mouse_pos)
        ):
            AppSettings.ftp_link_mode = FTP_LINK_MODE_IP
            return

        if (
            self.settings_new_variable_rect and
            self.settings_new_variable_rect.collidepoint(mouse_pos)
        ):
            self.active_text_field = "new_variable"
            return

        if (
            self.settings_add_variable_rect and
            self.settings_add_variable_rect.collidepoint(mouse_pos)
        ):
            self.commit_new_variable()
            return

        for name, rect in list(
            self.settings_variable_remove_rects.items()
        ):

            if rect.collidepoint(mouse_pos):
                self.remove_variable(name)
                return

        self.active_text_field = None

    def handle_mac_entry_click(self, mouse_pos):
        """
        Click routing while self.panel_view == "mac_entry". Mirrors
        handle_settings_click's pattern above.
        """

        if (
            self.mac_entry_back_rect and
            self.mac_entry_back_rect.collidepoint(mouse_pos)
        ):
            self.close_mac_entry()
            return

        if (
            self.mac_new_mac_rect and
            self.mac_new_mac_rect.collidepoint(mouse_pos)
        ):
            self.active_text_field = "new_mac"
            return

        if (
            self.mac_add_rect and
            self.mac_add_rect.collidepoint(mouse_pos)
        ):
            self.commit_new_mac()
            return

        if (
            self.mac_connect_rect and
            self.mac_connect_rect.collidepoint(mouse_pos)
        ):
            self.connect_mac_mode()
            return

        for mac, rect in list(
            self.mac_remove_rects.items()
        ):

            if rect.collidepoint(mouse_pos):
                self.remove_manual_mac(mac)
                return

        self.active_text_field = None

    def draw_gear_icon(self, center, radius, color):

        pygame.draw.circle(
            self.screen,
            color,
            center,
            radius,
            width=2
        )

        teeth = 8

        tooth_len = 4

        for index in range(teeth):

            angle = (
                (2 * math.pi / teeth) * index
            )

            inner = (
                center[0] + math.cos(angle) * radius,
                center[1] + math.sin(angle) * radius
            )

            outer = (
                center[0] + math.cos(angle) * (radius + tooth_len),
                center[1] + math.sin(angle) * (radius + tooth_len)
            )

            pygame.draw.line(
                self.screen,
                color,
                inner,
                outer,
                width=2
            )

        pygame.draw.circle(
            self.screen,
            color,
            center,
            max(2, radius // 3),
            width=2
        )

    def draw_text_input(self, rect, buffer, active, mouse_pos, max_chars_shown=48):

        hovered = rect.collidepoint(mouse_pos)

        pygame.draw.rect(
            self.screen,
            PANEL_BG_ALT,
            rect,
            border_radius=6
        )

        pygame.draw.rect(
            self.screen,
            ACCENT if active else (
                BORDER_BRIGHT if hovered else CARD_BORDER
            ),
            rect,
            width=1,
            border_radius=6
        )

        shown = buffer

        if len(shown) > max_chars_shown:
            shown = "..." + shown[-(max_chars_shown - 3):]

        if active and int(pygame.time.get_ticks() / 500) % 2 == 0:
            shown += "|"

        draw_text(
            self.screen,
            shown,
            self.font_small,
            TEXT_DIM if not buffer else GREEN_BRIGHT,
            rect.left + 10,
            rect.centery,
            "midleft"
        )

    def draw_settings_panel(self, panel, mouse_pos):

        x = (
            panel.left +
            PANEL_PADDING
        )

        content_width = (
            panel.width -
            PANEL_PADDING * 2
        )

        draw_text(
            self.screen,
            "SETTINGS",
            self.font_large,
            GREEN,
            x,
            25
        )

        self.settings_back_rect = draw_text(
            self.screen,
            "< BACK",
            self.font_small,
            ACCENT,
            panel.right - PANEL_PADDING,
            33,
            "topright"
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (x, 70),
            (panel.right - PANEL_PADDING, 70),
            width=1
        )

        # -- FTP share folder --------------------------------------
        draw_text(
            self.screen,
            "FTP SHARE FOLDER",
            self.font_normal,
            GREEN,
            x,
            92
        )

        self.settings_ftp_folder_rect = pygame.Rect(
            x, 118, content_width, 36
        )

        self.draw_text_input(
            self.settings_ftp_folder_rect,
            self.settings_ftp_folder_buffer,
            self.active_text_field == "ftp_folder",
            mouse_pos
        )

        self.settings_ftp_save_rect = pygame.Rect(
            panel.right - PANEL_PADDING - 140, 162, 140, 30
        )

        unsaved = (
            self.settings_ftp_folder_buffer.strip()
            != AppSettings.ftp_folder
        )

        draw_button(
            self.screen,
            self.settings_ftp_save_rect,
            "SAVE FOLDER*" if unsaved else "SAVE FOLDER",
            self.font_small,
            mouse_pos,
            enabled=True,
            accent=unsaved
        )

        draw_text(
            self.screen,
            f"currently: {AppSettings.ftp_folder}",
            self.font_small,
            TEXT_DIM,
            x,
            206
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (x, 232),
            (panel.right - PANEL_PADDING, 232),
            width=1
        )

        # -- fleet FTP share link addressing (MDNS vs IP) ------------
        # Two plain buttons rather than the radar's slider widget --
        # this is a one-off setting, not something switched mid-scan,
        # so it doesn't need the slider's animation/drag machinery.
        draw_text(
            self.screen,
            "FTP LINK USES",
            self.font_normal,
            GREEN,
            x,
            248
        )

        button_gap = 8

        button_width = (
            (content_width - button_gap) // 2
        )

        self.settings_ftp_link_mdns_rect = pygame.Rect(
            x, 274, button_width, 32
        )

        self.settings_ftp_link_ip_rect = pygame.Rect(
            x + button_width + button_gap, 274, button_width, 32
        )

        draw_button(
            self.screen,
            self.settings_ftp_link_mdns_rect,
            "MDNS",
            self.font_small,
            mouse_pos,
            enabled=True,
            accent=(
                AppSettings.ftp_link_mode == FTP_LINK_MODE_MDNS
            )
        )

        draw_button(
            self.screen,
            self.settings_ftp_link_ip_rect,
            "IP ADDRESS",
            self.font_small,
            mouse_pos,
            enabled=True,
            accent=(
                AppSettings.ftp_link_mode == FTP_LINK_MODE_IP
            )
        )

        draw_text(
            self.screen,
            f"currently: {AppSettings.ftp_link_mode}   "
            f"(shown as ftp://ignoapi_<address>.local:PORT for MDNS, "
            f"ftp://<lan ip>:PORT for IP)",
            self.font_small,
            TEXT_DIM,
            x,
            314
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (x, 340),
            (panel.right - PANEL_PADDING, 340),
            width=1
        )

        # -- variables combined and sent through server_tx ----------
        # c_id is deliberately left out here -- it's still checked /
        # created on each robot like the rest, but it's forwarded
        # through fleet_cid_tx (not server_tx), so it isn't one of the
        # variables this panel is describing. Add a variable below and
        # it's automatically combined into server_tx too -- see
        # RobotSyncManager.server_variables(), which this list mirrors.
        draw_text(
            self.screen,
            "VARIABLES SENT IN SERVER_TX",
            self.font_normal,
            GREEN,
            x,
            358
        )

        add_row_y = self.window_height - 60

        list_top = 386

        row_height = 32

        max_rows = max(
            0,
            (add_row_y - 12 - list_top) // row_height
        )

        self.settings_variable_remove_rects = {}

        variables = RobotSyncManager.server_variables()

        visible = variables[:max_rows]

        for index, name in enumerate(visible):

            row_y = list_top + index * row_height

            row_rect = pygame.Rect(
                x, row_y, content_width, row_height - 6
            )

            pygame.draw.rect(
                self.screen,
                CARD_BG,
                row_rect,
                border_radius=6
            )

            draw_text(
                self.screen,
                name,
                self.font_small,
                GREEN_BRIGHT,
                row_rect.left + 12,
                row_rect.centery,
                "midleft"
            )

            remove_rect = pygame.Rect(
                row_rect.right - 30, row_rect.top + 4,
                22, row_rect.height - 8
            )

            remove_hovered = remove_rect.collidepoint(mouse_pos)

            draw_text(
                self.screen,
                "x",
                self.font_small,
                FAILED if remove_hovered else TEXT_DIM,
                remove_rect.centerx,
                remove_rect.centery,
                "center"
            )

            self.settings_variable_remove_rects[name] = remove_rect

        if len(variables) > max_rows:

            draw_text(
                self.screen,
                f"+ {len(variables) - max_rows} more not shown",
                self.font_small,
                TEXT_DIM,
                x,
                list_top + max_rows * row_height + 4
            )

        # -- add variable --------------------------------------------
        self.settings_new_variable_rect = pygame.Rect(
            x, add_row_y, content_width - 90, 30
        )

        self.draw_text_input(
            self.settings_new_variable_rect,
            self.settings_new_variable_buffer,
            self.active_text_field == "new_variable",
            mouse_pos,
            max_chars_shown=30
        )

        self.settings_add_variable_rect = pygame.Rect(
            self.settings_new_variable_rect.right + 8,
            add_row_y,
            content_width - (content_width - 90) - 8,
            30
        )

        draw_button(
            self.screen,
            self.settings_add_variable_rect,
            "ADD",
            self.font_small,
            mouse_pos,
            enabled=bool(self.settings_new_variable_buffer.strip()),
            accent=True
        )

    def draw_mac_entry_panel(self, panel, mouse_pos):
        """
        The dialog opened from the MAC segment of the mode switch.
        Same layout idea as draw_settings_panel's variables list:
        a text field + ADD button, and each already-typed MAC gets
        its own removable row. CONNECT is what actually switches
        discovery into MODE_MAC (see connect_mac_mode()).
        """

        x = (
            panel.left +
            PANEL_PADDING
        )

        content_width = (
            panel.width -
            PANEL_PADDING * 2
        )

        draw_text(
            self.screen,
            "CONNECT BY MAC ADDRESS",
            self.font_large,
            GREEN,
            x,
            25
        )

        self.mac_entry_back_rect = draw_text(
            self.screen,
            "< BACK",
            self.font_small,
            ACCENT,
            panel.right - PANEL_PADDING,
            33,
            "topright"
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (x, 70),
            (panel.right - PANEL_PADDING, 70),
            width=1
        )

        draw_text(
            self.screen,
            "TYPE THE ROBOT'S MAC ADDRESS, THEN ADD.",
            self.font_small,
            TEXT_DIM,
            x,
            88
        )

        draw_text(
            self.screen,
            "ADD AS MANY AS YOU LIKE, THEN CONNECT.",
            self.font_small,
            TEXT_DIM,
            x,
            108
        )

        # -- typed MAC addresses -------------------------------------
        # Two rows are reserved at the bottom below the scrollable
        # list: the "type a MAC + ADD" row, then the CONNECT button
        # under it.
        add_row_y = self.window_height - 104

        connect_row_y = self.window_height - 60

        list_top = 134

        row_height = 32

        max_rows = max(
            0,
            (add_row_y - 12 - list_top) // row_height
        )

        self.mac_remove_rects = {}

        macs = list(AppSettings.manual_macs)

        visible = macs[:max_rows]

        for index, mac in enumerate(visible):

            row_y = list_top + index * row_height

            row_rect = pygame.Rect(
                x, row_y, content_width, row_height - 6
            )

            pygame.draw.rect(
                self.screen,
                CARD_BG,
                row_rect,
                border_radius=6
            )

            draw_text(
                self.screen,
                mac,
                self.font_small,
                GREEN_BRIGHT,
                row_rect.left + 12,
                row_rect.centery,
                "midleft"
            )

            remove_rect = pygame.Rect(
                row_rect.right - 30, row_rect.top + 4,
                22, row_rect.height - 8
            )

            remove_hovered = remove_rect.collidepoint(mouse_pos)

            draw_text(
                self.screen,
                "x",
                self.font_small,
                FAILED if remove_hovered else TEXT_DIM,
                remove_rect.centerx,
                remove_rect.centery,
                "center"
            )

            self.mac_remove_rects[mac] = remove_rect

        if not macs:

            draw_text(
                self.screen,
                "no MAC addresses added yet",
                self.font_small,
                TEXT_DIM,
                x,
                list_top + 4
            )

        elif len(macs) > max_rows:

            draw_text(
                self.screen,
                f"+ {len(macs) - max_rows} more not shown",
                self.font_small,
                TEXT_DIM,
                x,
                list_top + max_rows * row_height + 4
            )

        # -- add a MAC -------------------------------------------------
        self.mac_new_mac_rect = pygame.Rect(
            x, add_row_y, content_width - 90, 30
        )

        self.draw_text_input(
            self.mac_new_mac_rect,
            self.mac_new_mac_buffer,
            self.active_text_field == "new_mac",
            mouse_pos,
            max_chars_shown=30
        )

        self.mac_add_rect = pygame.Rect(
            self.mac_new_mac_rect.right + 8,
            add_row_y,
            content_width - (content_width - 90) - 8,
            30
        )

        draw_button(
            self.screen,
            self.mac_add_rect,
            "ADD",
            self.font_small,
            mouse_pos,
            enabled=bool(self.mac_new_mac_buffer.strip()),
            accent=True
        )

        # -- connect -----------------------------------------------------
        self.mac_connect_rect = pygame.Rect(
            x,
            connect_row_y,
            content_width,
            34
        )

        draw_button(
            self.screen,
            self.mac_connect_rect,
            "CONNECT",
            self.font_normal,
            mouse_pos,
            enabled=bool(macs),
            accent=True
        )

    def draw_panel(self, mouse_pos):

        panel = (
            self.get_panel_rect()
        )

        pygame.draw.rect(
            self.screen,
            PANEL_BG,
            panel
        )

        pygame.draw.line(
            self.screen,
            BORDER,
            (
                panel.left,
                0
            ),
            (
                panel.left,
                self.window_height
            ),
            width=1
        )

        # -- settings icon: always drawn, top-right of the panel,
        # regardless of which view is showing --------------------
        self.settings_icon_rect = pygame.Rect(
            panel.right - 34,
            8,
            26,
            26
        )

        settings_active = (
            self.panel_view == "settings"
        )

        if settings_active:

            pygame.draw.rect(
                self.screen,
                BUTTON_ACCENT,
                self.settings_icon_rect,
                border_radius=6
            )

        self.draw_gear_icon(
            self.settings_icon_rect.center,
            9,
            ACCENT if settings_active else TEXT_DIM
        )

        if self.panel_view == "settings":

            self.draw_settings_panel(
                panel,
                mouse_pos
            )

            return

        if self.panel_view == "mac_entry":

            self.draw_mac_entry_panel(
                panel,
                mouse_pos
            )

            return

        x = (
            panel.left +
            PANEL_PADDING
        )

        draw_text(
            self.screen,
            "DISCOVERED ROBOTS",
            self.font_large,
            GREEN,
            x,
            25
        )

        draw_text(
            self.screen,
            f"{self.registry.count()} FOUND",
            self.font_small,
            TEXT_DIM,
            panel.right -
            PANEL_PADDING,
            33,
            "topright"
        )

        self.draw_mode_switch(
            panel,
            mouse_pos
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (
                x,
                145
            ),
            (
                panel.right -
                PANEL_PADDING,
                145
            ),
            width=1
        )

        robots = (
            self.registry.get_robots()
        )

        robots.sort(
            key=lambda robot: (
                robot.name.lower(),
                robot.ip_address
            )
        )

        self.robot_rects = {}

        card_start_y = (
            155 -
            self.scroll_offset
        )

        clip_rect = pygame.Rect(
            panel.left,
            150,
            panel.width,
            self.window_height -
            390
        )

        old_clip = (
            self.screen.get_clip()
        )

        self.screen.set_clip(
            clip_rect
        )

        # Populated below if the mouse is hovering a card whose last
        # sync attempt failed, so we can draw a tooltip with the
        # reason after the clip rect is lifted.
        hovered_sync_failure = None

        for index, robot in enumerate(
            robots
        ):

            y = int(
                card_start_y +
                index *
                (
                    DEVICE_CARD_HEIGHT +
                    DEVICE_CARD_GAP
                )
            )

            card_rect = pygame.Rect(
                x,
                y,
                (
                    panel.width -
                    PANEL_PADDING * 2
                ),
                DEVICE_CARD_HEIGHT
            )

            if card_rect.colliderect(
                clip_rect
            ):

                self.robot_rects[
                    robot.key
                ] = card_rect

            if robot.sync_selected:

                card_color = (
                    CARD_SELECTED
                )

            elif card_rect.collidepoint(
                mouse_pos
            ):

                card_color = (
                    CARD_HOVER
                )

            else:

                card_color = (
                    CARD_BG
                )

            is_selected = robot.sync_selected

            # Soft shadow for a bit of depth.
            shadow_rect = card_rect.move(
                0,
                2
            )

            shadow_surface = pygame.Surface(
                (
                    shadow_rect.width,
                    shadow_rect.height
                ),
                pygame.SRCALPHA
            )

            pygame.draw.rect(
                shadow_surface,
                (
                    *SHADOW,
                    45
                ),
                shadow_surface.get_rect(),
                border_radius=10
            )

            self.screen.blit(
                shadow_surface,
                shadow_rect.topleft
            )

            pygame.draw.rect(
                self.screen,
                card_color,
                card_rect,
                border_radius=10
            )

            pygame.draw.rect(
                self.screen,
                (
                    BORDER_BRIGHT
                    if is_selected
                    else CARD_BORDER
                ),
                card_rect,
                width=1,
                border_radius=10
            )

            if is_selected:

                accent_rect = pygame.Rect(
                    card_rect.left,
                    card_rect.top + 8,
                    3,
                    card_rect.height - 16
                )

                pygame.draw.rect(
                    self.screen,
                    ACCENT,
                    accent_rect,
                    border_radius=2
                )

            status_color = (
                get_status_color(
                    robot.status
                )
            )

            pygame.draw.circle(
                self.screen,
                status_color,
                (
                    card_rect.left + 18,
                    card_rect.top + 19
                ),
                5
            )

            draw_text(
                self.screen,
                robot.name,
                self.font_normal,
                TEXT,
                card_rect.left + 32,
                card_rect.top + 10
            )

            draw_text(
                self.screen,
                f"IP  {robot.ip_address}",
                self.font_small,
                TEXT_DIM,
                card_rect.left + 16,
                card_rect.top + 42
            )

            # The mDNS name as returned by discovery (UDP broadcast
            # reply's <name> field, or the .local hostname in MDNS
            # mode) -- blank whenever the robot answered discovery
            # without one, which shows up here as "None" instead of
            # silently disappearing.
            mdns_display_name = (
                robot.hostname
                if robot.hostname
                else "None"
            )

            draw_text(
                self.screen,
                f"MDNS  {mdns_display_name}",
                self.font_small,
                TEXT_DIM,
                card_rect.left + 16,
                card_rect.top + 64
            )

            draw_text(
                self.screen,
                f"PORT  {robot.port}",
                self.font_small,
                TEXT_DIM,
                card_rect.left + 16,
                card_rect.top + 86
            )

            draw_text(
                self.screen,
                robot.status,
                self.font_small,
                status_color,
                card_rect.right - 10,
                card_rect.top + 10,
                "topright"
            )

            if robot.sync_status:

                sync_color = (
                    CONNECTED
                    if robot.sync_status == "LINKED"
                    else FAILED
                    if robot.sync_status == "SYNC FAILED"
                    else CONNECTING
                )

                bottom_right_text = robot.sync_status
                bottom_right_color = sync_color

            else:

                bottom_right_text = robot.discovery_mode
                bottom_right_color = GREEN

            draw_text(
                self.screen,
                bottom_right_text,
                self.font_small,
                bottom_right_color,
                card_rect.right - 10,
                card_rect.bottom - 8,
                "bottomright"
            )

            # Remember if this failed card is being hovered so we can
            # show WHY it failed (robot.sync_error) as a tooltip once
            # we're done drawing the clipped card list.
            if (
                robot.sync_status == "SYNC FAILED" and
                robot.sync_error and
                card_rect.collidepoint(mouse_pos) and
                card_rect.colliderect(clip_rect)
            ):

                hovered_sync_failure = (
                    card_rect,
                    robot.sync_error
                )

        self.screen.set_clip(
            old_clip
        )

        if hovered_sync_failure:

            self.draw_sync_error_tooltip(
                *hovered_sync_failure
            )

        # ----------------------------------------------------
        # CONTROLS
        # ----------------------------------------------------

        controls_y = (
            self.window_height -
            215
        )

        pygame.draw.line(
            self.screen,
            GRID,
            (
                x,
                controls_y - 12
            ),
            (
                panel.right -
                PANEL_PADDING,
                controls_y - 12
            ),
            width=1
        )

        # A robot is "selected" by clicking its card (toggles
        # robot.sync_selected). Whatever is selected right now is what
        # LINK acts on -- click to add or remove a robot from the
        # set, no separate tick-box needed.
        selected_robots = [
            robot
            for robot in self.registry.get_robots()
            if robot.sync_selected
        ]

        selected_count = len(selected_robots)

        if selected_count:

            draw_text(
                self.screen,
                f"SELECTED: {selected_count} ROBOT(S)",
                self.font_small,
                TEXT,
                x,
                controls_y
            )

        else:

            draw_text(
                self.screen,
                "SELECTED: NONE  (CLICK A ROBOT TO SELECT)",
                self.font_small,
                TEXT_DIM,
                x,
                controls_y
            )

        # ---- link selected (star sync + combine/link) -------------
        self.sync_button_rect = (
            pygame.Rect(
                x,
                controls_y + 28,
                (
                    panel.width -
                    PANEL_PADDING * 2
                ),
                34
            )
        )

        if self.syncing:

            sync_label = "CONNECTING & LINKING..."

        elif selected_count:

            sync_label = (
                f"LINK {selected_count} SELECTED ROBOT(S)"
            )

        else:

            sync_label = "SELECT ROBOTS TO LINK"

        draw_button(
            self.screen,
            self.sync_button_rect,
            sync_label,
            self.font_small,
            mouse_pos,
            (not self.syncing) and selected_count > 0,
            accent=True
        )

        # ---- reconnect only the robots marked SYNC FAILED ----------
        failed_count = sum(
            robot.sync_status == "SYNC FAILED"
            for robot in self.registry.get_robots()
        )

        self.reconnect_failed_button_rect = (
            pygame.Rect(
                x,
                controls_y + 74,
                (
                    panel.width -
                    PANEL_PADDING * 2
                ),
                34
            )
        )

        if self.syncing:

            reconnect_label = "CONNECTING & LINKING..."

        elif failed_count:

            reconnect_label = (
                f"RECONNECT {failed_count} FAILED ROBOT(S)"
            )

        else:

            reconnect_label = "NO FAILED ROBOTS"

        draw_button(
            self.screen,
            self.reconnect_failed_button_rect,
            reconnect_label,
            self.font_small,
            mouse_pos,
            (not self.syncing) and failed_count > 0
        )

        # ---- disconnect selected (full reverse of LINK) ------------
        linked_selected_count = sum(
            robot.sync_selected and robot.sync_status == "LINKED"
            for robot in self.registry.get_robots()
        )

        self.disconnect_button_rect = (
            pygame.Rect(
                x,
                controls_y + 120,
                (
                    panel.width -
                    PANEL_PADDING * 2
                ),
                34
            )
        )

        if self.syncing:

            disconnect_label = "CONNECTING & LINKING..."

        elif linked_selected_count:

            disconnect_label = (
                f"DISCONNECT {linked_selected_count} SELECTED ROBOT(S)"
            )

        else:

            disconnect_label = "SELECT LINKED ROBOTS TO DISCONNECT"

        draw_button(
            self.screen,
            self.disconnect_button_rect,
            disconnect_label,
            self.font_small,
            mouse_pos,
            (not self.syncing) and linked_selected_count > 0
        )

    # ========================================================
    # FOOTER
    # ========================================================

    def draw_footer(self):

        robots = (
            self.registry.get_robots()
        )

        connected = sum(
            robot.status ==
            ROBOT_CONNECTED
            for robot in robots
        )

        connecting = sum(
            robot.status ==
            ROBOT_CONNECTING
            for robot in robots
        )

        disconnected = sum(
            robot.status ==
            ROBOT_DISCONNECTED
            for robot in robots
        )

        failed = sum(
            robot.status ==
            CONNECTION_FAILED
            for robot in robots
        )

        footer = (
            f"MODE: {self.discovery_mode}   "
            f"ROBOTS: {len(robots)}   "
            f"CONNECTED: {connected}   "
            f"CONNECTING: {connecting}   "
            f"DISCONNECTED: {disconnected}   "
            f"FAILED: {failed}   "
            f"[R] RESCAN   "
            f"[ESC] EXIT"
        )

        draw_text(
            self.screen,
            footer,
            self.font_small,
            TEXT_DIM,
            25,
            self.window_height - 25
        )

    # ========================================================
    # DRAW
    # ========================================================

    def draw(self):

        self.screen.fill(
            BACKGROUND
        )

        mouse_pos = (
            pygame.mouse.get_pos()
        )

        robots = (
            self.registry.get_robots()
        )

        self.draw_header()

        self.radar.draw(
            self.screen,
            robots
        )

        self.draw_panel(
            mouse_pos
        )

        self.draw_footer()

        pygame.display.flip()

    # ========================================================
    # SHUTDOWN
    # ========================================================

    def shutdown(self):

        print(
            "[SYSTEM] Shutting down..."
        )

        try:

            self.mdns_scanner.stop()

        except Exception:

            pass

        try:

            self.udp_scanner.stop()

        except Exception:

            pass

        try:

            self.registry.close_all_connections()

        except Exception:

            pass

        pygame.quit()

    # ========================================================
    # RUN
    # ========================================================

    def run(self):

        try:

            while self.running:

                dt = (
                    self.clock.tick(FPS) /
                    1000.0
                )

                self.handle_events()

                self.update(
                    dt
                )

                self.draw()

        except KeyboardInterrupt:

            print(
                "[SYSTEM] Keyboard interrupt."
            )

        finally:

            self.shutdown()


# ============================================================
# PROGRAM ENTRY
# ============================================================

if __name__ == "__main__":

    app = RobotConnectorApplication()

    app.run()