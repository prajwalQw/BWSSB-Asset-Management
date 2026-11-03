"""
ignodiscover.py — find every ignoAPI on the network with one UDP broadcast.

    scanner  ---- "ignoAPI?" (broadcast, UDP 8899) --->  every machine
    scanner  <--- "192.168.1.10,ignoapi_abi.local,8899" ---  each responder

WHY UDP AND NOT THE TCP SCAN
    ignoAPI already has scan_ignoapi_hosts(), which opens a TCP connection to
    every address on the subnet in turn. That works, but it takes as long as
    the slowest firewall (a silently dropped SYN costs the full timeout) and it
    only finds machines on a subnet you already know to sweep. One broadcast
    reaches every machine on every attached network at once, and the answers
    come back in the time it takes them to reply.

WHAT COMES BACK
    Three fields, comma separated, in the order asked for:

        <ip>,<mdns name>,<tcp port>

    The mDNS field is empty when that machine has no ADDRESS set -- the name
    only exists once somebody types one -- so a scanner must handle
    "192.168.1.10,,8899" and fall back to the IP.

THE INTERFACE TRAP, AGAIN
    The same one mDNS hit: a machine with a VPN adapter has more than one
    network, and the OS picks ONE for a broadcast. Broadcasting out of the
    default interface finds only the machines on that interface -- which on a
    Windows box with Radmin or Hamachi installed is usually the wrong one. So
    the scanner sends from EVERY interface, and the responder answers with the
    address that reaches it from where the question came.
"""
import socket
import threading
import time

try:                                    # the interface helpers live with mDNS
    from ignomdns import local_ipv4s, same_network
except ImportError:                     # standalone use
    def local_ipv4s():
        out = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                if info[4][0] not in out:
                    out.append(info[4][0])
        except OSError:
            pass
        return [i for i in out if not i.startswith("127.")] or ["0.0.0.0"]

    def same_network(a, b):
        try:
            return a.rsplit(".", 1)[0] == b.rsplit(".", 1)[0]
        except (AttributeError, IndexError):
            return False


# UDP 8899 -- the same NUMBER as the data port, which is a different namespace
# from TCP, so nothing collides. One number to remember instead of two.
DISCOVER_PORT = 8899

# What a scanner sends. Matched case-insensitively, and the trailing "?" is
# optional, because the point is to be easy to speak from anything -- a shell
# one-liner, an Arduino, a PLC.
PROBE = "ignoAPI?"
_PROBE_KEY = "ignoapi"

RECV_SIZE = 512


def reply_text(ip, mdns_name, port):
    """The one line a responder sends back."""
    return "%s,%s,%s" % (ip or "", mdns_name or "", port)


def parse_reply(text):
    """A reply line -> {"ip", "name", "port"}, or None if it is not one.

    Kept beside the builder so the two cannot drift, and lenient about the
    name being empty -- a machine with no ADDRESS set has no mDNS name and
    still deserves to be found.
    """
    parts = [p.strip() for p in str(text or "").split(",")]
    if len(parts) < 3 or not parts[0]:
        return None
    try:
        port = int(parts[2])
    except (TypeError, ValueError):
        return None
    return {"ip": parts[0], "name": parts[1], "port": port}


def is_probe(data):
    """True if this datagram is asking who is out there."""
    try:
        text = data.decode("utf-8", "ignore")
    except Exception:
        return False
    return _PROBE_KEY in text.strip().lower()


class DiscoveryResponder(threading.Thread):
    """Answers "ignoAPI?" broadcasts with this machine's address.

    `name_fn` and `port_fn` are read at ANSWER time, not at construction, so
    renaming the machine (typing into the ADDRESS row) takes effect on the
    next question rather than on the next restart.
    """

    daemon = True

    def __init__(self, name_fn, port_fn, on_log=None, port=DISCOVER_PORT):
        super().__init__(name="ignodiscover", daemon=True)
        self.name_fn = name_fn
        self.port_fn = port_fn
        self.port = int(port)
        self.on_log = on_log
        self.stopping = threading.Event()
        self.sock = None
        self.answered = 0

    def log(self, msg):
        if self.on_log:
            self.on_log(msg)

    def reachable_ip(self, peer):
        """The address of ours that `peer` can actually reach.

        Answering with the wrong one is worse than not answering: the scanner
        lists a machine and then cannot connect to it.
        """
        ips = local_ipv4s()
        for own in ips:
            if same_network(own, peer):
                return own
        return ips[0] if ips else ""

    def stop(self):
        self.stopping.set()
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass

    def run(self):
        while not self.stopping.is_set():
            if self.sock is None:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    s.bind(("", self.port))
                    s.settimeout(1.0)
                    self.sock = s
                    self.log("[discover] answering ignoAPI? on UDP %d" % self.port)
                except OSError as e:
                    self.log("[discover] cannot open UDP %d (%s) — retrying"
                             % (self.port, e))
                    self.stopping.wait(10.0)
                    continue
            try:
                data, addr = self.sock.recvfrom(RECV_SIZE)
            except socket.timeout:
                continue
            except OSError:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
                continue
            if not is_probe(data):
                continue
            try:
                line = reply_text(self.reachable_ip(addr[0]),
                                  self.name_fn() or "", self.port_fn())
                # Answered UNICAST, straight back to the asker. A broadcast
                # reply would be heard by every machine on the network and
                # tells them nothing they asked for.
                self.sock.sendto(line.encode("utf-8"), addr)
                self.answered += 1
                self.log("[discover] answered %s -> %s" % (addr[0], line))
            except OSError as e:
                self.log("[discover] reply failed: %s" % e)
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


def scan(timeout=1.5, port=DISCOVER_PORT):
    """Broadcast "ignoAPI?" and collect every answer.

    Returns a list of {"ip", "name", "port"}, sorted by address, one entry per
    machine. Sent from EVERY interface, because the OS would otherwise pick
    one and the machines on the others would simply not be found.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("", 0))
    s.settimeout(0.3)
    found = {}
    try:
        probe = PROBE.encode("utf-8")
        for src in local_ipv4s():
            for target in ("255.255.255.255",
                           src.rsplit(".", 1)[0] + ".255"):
                try:
                    s.sendto(probe, (target, port))
                except OSError:
                    continue
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, addr = s.recvfrom(RECV_SIZE)
            except socket.timeout:
                continue
            except OSError:
                break
            hit = parse_reply(data.decode("utf-8", "ignore"))
            if hit:
                # Keyed on the address it reported, so a machine answering on
                # two interfaces is listed once per reachable address rather
                # than twice for the same one.
                found[hit["ip"]] = hit
    finally:
        s.close()
    return [found[k] for k in sorted(found)]


if __name__ == "__main__":
    print("broadcasting %r on UDP %d ..." % (PROBE, DISCOVER_PORT))
    hits = scan()
    if not hits:
        print("no ignoAPI answered.")
        print("  - is one running, with the responder started?")
        print("  - a firewall may be blocking inbound UDP %d" % DISCOVER_PORT)
    for h in hits:
        print("  %-15s  %-28s  %s"
              % (h["ip"], h["name"] or "(no mDNS name set)", h["port"]))
    print("%d ignoAPI(s) found." % len(hits))
