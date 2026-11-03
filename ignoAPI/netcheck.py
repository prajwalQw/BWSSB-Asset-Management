"""
netcheck.py — why ignoAPI cannot see the other machines on THIS network.

    python netcheck.py                       # what this machine can do
    python netcheck.py 192.168.1.17          # ...and whether it can reach that
    python netcheck.py ignoapi_rob1.local

    netcheck --listen        on one machine   } does the NETWORK carry
    netcheck --probe         on another       } multicast and broadcast?

Run it on a machine at the site and send back the output. It tests each layer
ignoAPI depends on separately, because they fail independently and the symptom
is the same every time -- "it cannot find the other computers".

    mDNS name   ignoapi_x.local   IP MULTICAST   224.0.0.251, link-local
    discovery   "ignoAPI?"        IP BROADCAST   255.255.255.255, link-local
    subnet scan the peer list     unicast TCP    every address in the subnet
    MAC         a4:97:b1:...      ARP            same layer-2 segment
    sync/auto   once it has an IP unicast TCP    routable, works over a WAN

A network that blocks multicast and broadcast -- most enterprise WiFi, most
guest VLANs, anything with a managed switch and no IGMP querier -- kills the
first two and leaves the rest working. That is exactly the report "MAC syncs,
mDNS does not".
"""
import re
import socket
import struct
import subprocess
import sys
import threading
import time

MDNS_ADDR, MDNS_PORT = "224.0.0.251", 5353
DISCOVER_PORT = 8899
API_PORT = 8899

OK, BAD, WARN, INFO = "  ok  ", " FAIL ", " WARN ", "      "


def say(mark, text, detail=""):
    print("[%s] %s" % (mark, text))
    if detail:
        for line in str(detail).splitlines():
            print("            %s" % line)


def run(cmd):
    try:
        return subprocess.check_output(
            cmd, shell=True, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        ).decode(errors="ignore")
    except Exception:
        return ""


# ── 1. the interfaces, and their REAL netmask ────────────────────────
def interfaces():
    """[(ip, prefix_length)] for every IPv4 on this machine.

    The netmask is the point. ignoAPI sweeps and broadcasts as though every
    network were a /24; on a /16 or a /22 that reaches a fraction of it and
    misses every machine outside the first 254 addresses.
    """
    out = []
    ps = run('powershell -NoProfile -Command '
             '"Get-NetIPAddress -AddressFamily IPv4 | '
             'ForEach-Object { $_.IPAddress + \' \' + $_.PrefixLength }"')
    for line in ps.splitlines():
        m = re.match(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s*$", line)
        if m and not m.group(1).startswith("127."):
            out.append((m.group(1), int(m.group(2))))
    if out:
        return out
    # ipconfig, for a machine where PowerShell is locked down
    ip = None
    for line in run("ipconfig").splitlines():
        m = re.search(r"IPv4[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if m:
            ip = m.group(1)
        m = re.search(r"(?:Subnet Mask|Mask)[^:]*:\s*(\d+\.\d+\.\d+\.\d+)", line)
        if m and ip:
            bits = bin(struct.unpack("!I",
                                     socket.inet_aton(m.group(1)))[0]).count("1")
            if not ip.startswith("127."):
                out.append((ip, bits))
            ip = None
    return out


def net_of(ip, bits):
    n = struct.unpack("!I", socket.inet_aton(ip))[0]
    mask = (0xFFFFFFFF << (32 - bits)) & 0xFFFFFFFF
    return n & mask, (n & mask) | (~mask & 0xFFFFFFFF)


def as_ip(n):
    return socket.inet_ntoa(struct.pack("!I", n))



# ── two machines: does the NETWORK carry it, not just this stack ─────
def two_machine_mode():
    """--listen on one machine, --probe on another.

    The single-machine tests above send to themselves. A switch that drops
    multicast between ports passes that test and still breaks every mDNS name
    on the site, so the only honest answer needs a second machine.
    """
    import argparse
    if "--listen" in sys.argv:
        print("LISTENING for netcheck probes. Run this on the OTHER machine:")
        print("    netcheck --probe")
        print("Ctrl+C to stop.\n")
        socks = []
        m = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        m.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        m.bind(("", MDNS_PORT))
        for ip, _b in interfaces():
            try:
                m.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                             socket.inet_aton(MDNS_ADDR) + socket.inet_aton(ip))
            except OSError:
                pass
        socks.append(("multicast", m))
        b = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        b.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        b.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        b.bind(("", DISCOVER_PORT + 1))
        socks.append(("broadcast", b))
        seen = set()
        try:
            while True:
                for kind, sk in socks:
                    sk.settimeout(0.4)
                    try:
                        data, addr = sk.recvfrom(2048)
                    except socket.timeout:
                        continue
                    except OSError:
                        continue
                    if b"netcheck" in data and (kind, addr[0]) not in seen:
                        seen.add((kind, addr[0]))
                        say(OK, "%s ARRIVED from %s" % (kind.upper(), addr[0]))
        except KeyboardInterrupt:
            print()
            for kind in ("multicast", "broadcast"):
                got = [a for k, a in seen if k == kind]
                say(OK if got else BAD,
                    "%s from another machine: %s"
                    % (kind, ", ".join(got) if got else "NOTHING ARRIVED"),
                    "" if got else
                    "This network does not carry %s between machines.\n"
                    "=> %s" % (kind,
                               "mDNS names will never resolve here."
                               if kind == "multicast"
                               else "the ignoAPI? scanner will find nothing."))
        return True

    if "--probe" in sys.argv:
        print("SENDING probes. Watch the machine running --listen.\n")
        for _ in range(10):
            for ip, bits in interfaces():
                try:
                    s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s1.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                  socket.inet_aton(ip))
                    s1.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
                    s1.sendto(b"netcheck-probe", (MDNS_ADDR, MDNS_PORT))
                    s1.close()
                except OSError:
                    pass
                _lo, hi = net_of(ip, bits)
                for tgt in ("255.255.255.255", as_ip(hi),
                            ip.rsplit(".", 1)[0] + ".255"):
                    try:
                        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                        s2.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                        s2.bind((ip, 0))
                        s2.sendto(b"netcheck-bcast", (tgt, DISCOVER_PORT + 1))
                        s2.close()
                    except OSError:
                        pass
            time.sleep(0.5)
        say(OK, "sent 10 rounds from every interface")
        return True
    return False


if two_machine_mode():
    sys.exit(0)

print("=" * 72)
print("  ignoAPI network check")
print("=" * 72)

print("\n-- 1. this machine's networks " + "-" * 42)
_all = interfaces()
# 169.254.x is APIPA: the adapter asked for a DHCP lease and got none.
# It is not a network anyone is on, and listing one per idle adapter
# buries the two lines that matter.
ifaces = [(ip, b) for ip, b in _all if not ip.startswith("169.254.")]
_apipa = [ip for ip, _b in _all if ip.startswith("169.254.")]
if _apipa:
    say(INFO, "%d adapter(s) with no DHCP lease (169.254.x), ignored: %s"
        % (len(_apipa), ", ".join(_apipa[:4])
           + (" ..." if len(_apipa) > 4 else "")))
if not ifaces:
    say(BAD, "no usable IPv4 address -- this machine is not on a network")
narrow = []
for ip, bits in ifaces:
    lo, hi = net_of(ip, bits)
    size = hi - lo - 1
    note = "%s/%d   %s .. %s   (%d usable)" % (ip, bits, as_ip(lo + 1),
                                               as_ip(hi - 1), size)
    if bits == 24:
        say(OK, note)
    elif bits > 24:
        say(WARN, note, "smaller than a /24 -- the sweep will probe addresses "
                        "outside this subnet, which is slow but harmless")
    else:
        narrow.append((ip, bits, size))
        say(BAD, note,
            "ignoAPI assumes a /24. It will only sweep and scan %s.1-254,\n"
            "which is %d of the %d addresses here -- every machine outside\n"
            "that range is invisible to discovery and to the peer scan."
            % (ip.rsplit(".", 1)[0], 254, size))

print("\n-- 2. multicast (mDNS names) " + "-" * 43)
got = []


def mrx():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", MDNS_PORT))
    except OSError as e:
        got.append(("bind", str(e)))
        return
    for ip, _b in ifaces:
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                         socket.inet_aton(MDNS_ADDR) + socket.inet_aton(ip))
        except OSError:
            pass
    s.settimeout(4)
    end = time.time() + 4
    while time.time() < end:
        try:
            data, addr = s.recvfrom(2048)
        except socket.timeout:
            break
        if data == b"netcheck-probe":
            got.append(("rx", addr[0]))
            break
    s.close()


t = threading.Thread(target=mrx, daemon=True)
t.start()
time.sleep(0.8)
sent = 0
for ip, _b in ifaces:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                     socket.inet_aton(ip))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.sendto(b"netcheck-probe", (MDNS_ADDR, MDNS_PORT))
        s.close()
        sent += 1
    except OSError:
        # an address the OS still lists but will not bind: noise unless
        # every interface fails, which the verdict below catches
        pass
t.join(6)
binds = [g for g in got if g[0] == "bind"]
if binds:
    say(WARN, "could not bind UDP %d" % MDNS_PORT, binds[0][1]
        + "\nusually Bonjour or Avahi already has it -- mDNS may still work,\n"
          "but ignoAPI's own responder cannot start")
elif any(g[0] == "rx" for g in got):
    say(OK, "multicast works on this machine (%d interface(s))" % sent,
        "This proves the LOCAL stack only. Whether the switch carries it\n"
        "BETWEEN machines needs two of them -- see --listen / --probe below.")
else:
    say(BAD, "MULTICAST IS BLOCKED",
        "Nothing sent to 224.0.0.251 came back, not even our own packet.\n"
        "=> ignoapi_<name>.local will NOT resolve on this network.\n"
        "Common causes: WiFi client isolation, a managed switch with IGMP\n"
        "snooping and no querier, or a guest/segregated VLAN.")

print("\n-- 3. broadcast (the ignoAPI? scanner) " + "-" * 33)
bgot = []


def brx():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.bind(("", DISCOVER_PORT + 1))
    except OSError as e:
        bgot.append(("bind", str(e)))
        return
    s.settimeout(4)
    end = time.time() + 4
    while time.time() < end:
        try:
            data, addr = s.recvfrom(2048)
        except socket.timeout:
            break
        if data == b"netcheck-bcast":
            bgot.append(("rx", addr[0]))
            break
    s.close()


t = threading.Thread(target=brx, daemon=True)
t.start()
time.sleep(0.8)
for ip, bits in ifaces:
    _lo, hi = net_of(ip, bits)
    for target in ("255.255.255.255", as_ip(hi)):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.bind((ip, 0))
            s.sendto(b"netcheck-bcast", (target, DISCOVER_PORT + 1))
            s.close()
        except OSError:
            pass
t.join(6)
if any(g[0] == "rx" for g in bgot):
    say(OK, "broadcast works on this machine",
        "Local stack only, as above.")
else:
    say(BAD, "BROADCAST IS BLOCKED",
        "=> the ignoAPI? scanner will find nothing on this network.\n"
        "Same causes as multicast. Use MAC or a typed IP instead.")
for ip, bits in ifaces:
    _lo, hi = net_of(ip, bits)
    if bits < 24:
        say(WARN, "the real broadcast address here is %s, not %s.255"
            % (as_ip(hi), ip.rsplit(".", 1)[0]),
            "ignoAPI broadcasts to the wrong one on a network this size.")

print("\n-- 4. the peer, if one was named " + "-" * 39)
target = sys.argv[1] if len(sys.argv) > 1 else None
if not target:
    say(INFO, "no peer given -- pass one to test reachability:")
    say(INFO, "    python netcheck.py 192.168.1.17")
else:
    ip = None
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", target):
        ip = target
        say(INFO, "%s is an address, so no name lookup is needed" % target)
    else:
        try:
            sys.path.insert(0, ".")
            import ignomdns
            ip = ignomdns.resolve(target, timeout=3.0)
            say(OK if ip else BAD,
                "our own mDNS resolver: %s -> %s" % (target, ip or "NOT FOUND"))
        except ImportError:
            # netcheck is designed to be copied on its own; ignomdns is a
            # bonus when the whole project is there, not a requirement.
            say(INFO, "ignomdns not beside this file -- using the Windows "
                      "resolver only (copy ignomdns.py here to test ours too)")
        except Exception as e:
            say(WARN, "our mDNS resolver raised", e)
        try:
            osip = socket.gethostbyname(target)
            say(OK, "Windows resolver: %s -> %s" % (target, osip))
            ip = ip or osip
        except OSError as e:
            say(BAD, "Windows resolver cannot resolve %s" % target, e)
    if ip:
        try:
            with socket.create_connection((ip, API_PORT), timeout=3):
                say(OK, "TCP %s:%d is OPEN -- sync and autoclient can work "
                        "by address" % (ip, API_PORT))
        except OSError as e:
            say(BAD, "TCP %s:%d refused or unreachable" % (ip, API_PORT), e)
        if ip in [own for own, _b in ifaces]:
            say(WARN, "%s is THIS machine" % ip,
                "So the test above only proved ignoAPI is listening here.\n"
                "Give the address of ANOTHER machine to test the path to it.")
        else:
            # A real arp -a line carries an IP *and* a MAC. The "Interface:"
            # header carries the address too, and matching it reported a
            # neighbour that was never there.
            arp = run("arp -a")
            hit = [l.strip() for l in arp.splitlines()
                   if ip in l and re.search(r"([\da-fA-F]{2}[-:]){5}[\da-fA-F]{2}",
                                            l)]
            say(OK if hit else WARN,
                "ARP entry for %s: %s" % (ip, hit[0] if hit else "none"),
                "" if hit else "no ARP entry means it is NOT on this layer-2\n"
                               "segment -- MAC-based sync cannot find it either.")

print("\n-- 5. this machine's firewall " + "-" * 42)
fw = run("netsh advfirewall show allprofiles state")
prof = re.findall(r"(\w[\w\s]*Profile)\s+Settings:.*?State\s+(\w+)", fw, re.S)
if prof:
    for name, state in prof:
        say(WARN if state.upper() == "ON" else OK,
            "%s: %s" % (name.strip(), state))
    say(INFO, "A firewall that is ON does not block ignoAPI by itself, but a")
    say(INFO, "network Windows has classed as PUBLIC blocks inbound by")
    say(INFO, "default -- so the other machines cannot connect back to this")
    say(INFO, "one. Check: Settings > Network > change to Private.")
else:
    say(INFO, "could not read the firewall state")

print("\n" + "=" * 72)
print("""SUMMARY OF WHAT DEPENDS ON WHAT

  works over a WAN / across routers   sync and autoclient BY IP ADDRESS
  same broadcast domain only          mDNS names, the ignoAPI? scanner
  same layer-2 segment only           MAC addresses, the ARP sweep

mDNS and broadcast are link-local BY DESIGN. They cannot cross a router and
never will -- that is not an ignoAPI limitation. Over a WAN, or between VLANs,
peers have to be given an address.""")
print("=" * 72)
