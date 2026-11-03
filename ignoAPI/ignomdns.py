"""
ignomdns.py — answer "<name>.local" on the LAN, so nothing has to know an IP.

WHY THIS EXISTS
    Setting up a sync meant finding out the other machine's IP address, and
    an IP is the one thing about a robot PC that changes on its own. Give
    ignoAPI a NAME instead -- ADDRESS = "helloworld" -- and every other
    machine reaches it at `ignoapi_helloworld.local`, whatever DHCP does.

    The IP and MAC routes are untouched. This is a third way to say where a
    machine is, not a replacement for the two that already work.

WHAT IT IS
    A deliberately small mDNS responder: it answers A queries for ONE name
    and does nothing else. It is not a Bonjour implementation and does not
    try to be -- no service registration, no browsing, no PTR/SRV/TXT. That
    is what keeps it ~200 lines with no dependency, and it is all that
    resolving a name needs.

WHAT RESOLVES IT
    Windows 10 and later resolve `.local` names over mDNS with no extra
    software, as do macOS and any Linux running Avahi. Nothing needs to be
    installed on the machine doing the LOOKING.

WHAT WILL BREAK IT (know these before relying on it)
    * A VPN or corporate DNS policy that claims the .local suffix.
    * Multicast being blocked between VLANs -- mDNS never crosses a router.
    * Another responder already claiming the same name. This does no conflict
      probing, so two ignoAPIs sharing one ADDRESS is a misconfiguration that
      shows up as an unstable answer, not as an error.
"""
import socket
import struct
import threading
import time

MDNS_ADDR = "224.0.0.251"
MDNS_PORT = 5353
TTL = 120                 # seconds a resolver may cache the answer

QTYPE_A = 1
QTYPE_ANY = 255
CLASS_IN = 1
CACHE_FLUSH = 0x8000      # top bit of the class in a RESPONSE
UNICAST_REPLY = 0x8000    # top bit of the class in a QUESTION ("QU")

HOST_PREFIX = "ignoapi_"


def local_ipv4s():
    """Every IPv4 address this machine holds, most-likely-LAN first.

    A machine with a VPN adapter (Radmin, Hamachi, Tailscale, a corporate
    client) has more than one, and the one the OS picks for multicast is
    NOT necessarily the one the LAN is on -- on Windows the VPN adapter
    routinely wins, because its route to 224.0.0.0/4 has the lower metric.
    Listening on one interface and answering out of another is invisible
    locally and total from every other machine, so the responder uses all
    of them.
    """
    out = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       socket.AF_INET):
            ip = info[4][0]
            if ip not in out:
                out.append(ip)
    except OSError:
        pass
    # The route to the internet is the best single guess at the real LAN
    # address, so it goes first -- it is the one written into the answer.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        primary = probe.getsockname()[0]
        probe.close()
        if primary in out:
            out.remove(primary)
        out.insert(0, primary)
    except OSError:
        pass
    return [ip for ip in out if ip and not ip.startswith("127.")] or ["0.0.0.0"]

def same_network(a, b):
    """True if two IPv4 addresses share a /24.

    A rough test, and the right one here: mDNS is link-local, so anything
    that can hear the query is on the same segment, and the netmask is not
    worth going to the OS for."""
    try:
        return a.rsplit(".", 1)[0] == b.rsplit(".", 1)[0]
    except (AttributeError, IndexError):
        return False

def hostname_for(address):
    """'helloworld' -> 'ignoapi_helloworld.local'.

    Returns "" for a blank address, which is how the caller knows the feature
    is switched off. Sanitised to what DNS labels actually allow: letters,
    digits and hyphens. A name with a space or an underscore in the middle
    resolves on nothing, and failing silently later is worse than fixing it
    here.
    """
    raw = str(address or "").strip().lower()
    if not raw:
        return ""
    if raw.startswith(HOST_PREFIX):
        raw = raw[len(HOST_PREFIX):]
    cleaned = "".join(c if (c.isalnum() or c == "-") else "-" for c in raw)
    cleaned = cleaned.strip("-")
    return f"{HOST_PREFIX}{cleaned}.local" if cleaned else ""


def encode_name(name):
    """'a.b' -> b'\\x01a\\x01b\\x00'"""
    out = b""
    for label in name.rstrip(".").split("."):
        lb = label.encode("utf-8")[:63]
        out += bytes([len(lb)]) + lb
    return out + b"\x00"


def decode_name(data, offset):
    """Read a (possibly compressed) name. Returns (name, next_offset).

    Compression pointers are followed, but the offset returned is the one
    AFTER the pointer -- that is what the caller needs to keep parsing.
    """
    labels = []
    jumped = False
    end = offset
    hops = 0
    while True:
        if offset >= len(data):
            break
        ln = data[offset]
        if ln == 0:
            offset += 1
            if not jumped:
                end = offset
            break
        if ln & 0xC0 == 0xC0:                      # pointer
            if offset + 1 >= len(data):
                break
            ptr = ((ln & 0x3F) << 8) | data[offset + 1]
            if not jumped:
                end = offset + 2
            offset = ptr
            jumped = True
            hops += 1
            if hops > 16:                          # malformed / hostile loop
                break
            continue
        offset += 1
        labels.append(data[offset:offset + ln].decode("utf-8", "replace"))
        offset += ln
        if not jumped:
            end = offset
    return ".".join(labels), end


def parse_questions(data):
    """[(name, qtype, qclass)] from a DNS message. [] if it is not a query."""
    if len(data) < 12:
        return []
    _id, flags, qd, _an, _ns, _ar = struct.unpack("!6H", data[:12])
    if flags & 0x8000:                             # a response, not a query
        return []
    out = []
    off = 12
    for _ in range(min(qd, 32)):                   # cap: a query with 60000
        try:                                       # questions is not a query
            name, off = decode_name(data, off)
            qtype, qclass = struct.unpack("!2H", data[off:off + 4])
            off += 4
        except (struct.error, IndexError):
            break
        out.append((name, qtype, qclass))
    return out


def build_response(name, ip, query_id=0, ttl=TTL):
    """One authoritative A answer for `name`."""
    header = struct.pack("!6H", query_id, 0x8400, 0, 1, 0, 0)
    body = encode_name(name)
    body += struct.pack("!2HIH", QTYPE_A, CLASS_IN | CACHE_FLUSH, ttl, 4)
    body += socket.inet_aton(ip)
    return header + body


class MdnsResponder:
    """Answers A queries for whatever `name_fn()` currently returns.

    The name and the IP are read through CALLBACKS rather than passed in, so
    renaming ignoAPI or moving to a different network takes effect without a
    restart -- which is the whole point of naming the machine instead of
    addressing it.

    NOT a threading.Thread subclass, deliberately. Thread owns a pile of
    underscore attributes -- _handle, _stop, _target, _args, _started -- and
    a method of the same name silently shadows one of them. The first version
    of this class did exactly that twice over: self._handle(data, addr) called
    Thread's `_handle` and died with

        TypeError: '_thread._ThreadHandle' object is not callable

    while self._stop = Event() had quietly replaced the method Thread calls on
    itself when the thread exits. Holding a thread instead of being one makes
    that whole class of collision impossible.
    """

    def __init__(self, name_fn, ip_fn, on_log=None):
        # Filled in by _open: every interface the group was joined on.
        self.ifaces = []
        self.name_fn = name_fn
        self.ip_fn = ip_fn
        self.log = on_log or (lambda m: None)
        self.sock = None
        self.thread = None
        self.stopping = threading.Event()
        self._last = ("", "")          # (name, ip) last announced
        self.answered = 0

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._serve, daemon=True)
            self.thread.start()
        return self

    def is_alive(self):
        return bool(self.thread and self.thread.is_alive())

    # ── socket ─────────────────────────────────────────────────────
    def _open(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:                                        # not on Windows
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            pass
        s.bind(("", MDNS_PORT))
        # JOIN ON EVERY INTERFACE. Joining only the address ignoAPI thinks
        # is its LAN one means a query arriving on any other adapter is
        # never seen; joining them all costs nothing and cannot be wrong.
        self.ifaces = []
        for ip in local_ipv4s():
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                             socket.inet_aton(MDNS_ADDR) + socket.inet_aton(ip))
                self.ifaces.append(ip)
            except OSError:
                continue
        if not self.ifaces:
            # Better on the group by the default route than not on it.
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                             socket.inet_aton(MDNS_ADDR)
                             + socket.inet_aton("0.0.0.0"))
                self.ifaces = ["0.0.0.0"]
            except OSError:
                pass
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.settimeout(1.0)
        self.log("[mdns] listening on " + ", ".join(self.ifaces))
        return s

    def reachable_ip(self, peer=None, iface=None):
        """The address to PUT IN the answer, for this asker.

        One A record can carry one address, so which one it carries
        decides whether the asker can reach us. The address on the same
        network as the asker is the only one that certainly can; the
        primary LAN address is the fallback, because a machine routing to
        us from further away will be coming through it."""
        primary = self.ip_fn() or (self.ifaces[0] if self.ifaces else None)
        for cand in (peer, iface):
            if not cand:
                continue
            for own in self.ifaces:
                if same_network(own, cand):
                    return own
        return primary

    def _send_multicast(self, make_pkt):
        """Send out of EVERY interface, one packet built PER interface.

        Without IP_MULTICAST_IF the OS chooses, and on a machine with a VPN
        adapter it chooses that -- so the answer to a LAN query goes down
        the tunnel and the machine that asked hears nothing. The name then
        resolves here and nowhere else, which is exactly what it looks
        like when a VPN client is installed."""
        sent = 0
        for ip in (self.ifaces or ["0.0.0.0"]):
            pkt = make_pkt(ip)
            if not pkt:
                continue
            try:
                self.sock.setsockopt(socket.IPPROTO_IP,
                                     socket.IP_MULTICAST_IF,
                                     socket.inet_aton(ip))
                self.sock.sendto(pkt, (MDNS_ADDR, MDNS_PORT))
                sent += 1
            except OSError:
                continue
        return sent

    def announce(self):
        """Send an unsolicited answer, so resolvers update without asking.

        Sent when the name or the address CHANGES -- on a rename, or when
        DHCP moves this machine. Without it everything holding a cached
        answer keeps the old address for up to the TTL.
        """
        name, ip = self.name_fn(), self.ip_fn()
        if not (name and ip and self.sock):
            return False
        try:
            # Each interface announces the address that reaches us THERE.
            n = self._send_multicast(
                lambda src: build_response(name, self.reachable_ip(iface=src),
                                           query_id=0))
            if not n:
                self.log("[mdns] announce reached no interface")
                return False
            self._last = (name, ip)
            self.log(f"[mdns] announced {name} -> {ip} on {n} interface(s)")
            return True
        except OSError as e:
            self.log(f"[mdns] announce failed: {e}")
            return False

    def stop(self):
        self.stopping.set()

    # ── main loop ──────────────────────────────────────────────────
    def _serve(self):
        while not self.stopping.is_set():
            if self.sock is None:
                try:
                    self.sock = self._open()
                    self.log(f"[mdns] listening on {MDNS_ADDR}:{MDNS_PORT}")
                    self.announce()
                except OSError as e:
                    # Port 5353 in use usually means Bonjour or Avahi is
                    # already running. Say so once and keep trying: that
                    # other responder may go away.
                    self.log(f"[mdns] cannot open the mDNS port ({e}) — "
                             f"retrying; is Bonjour/Avahi running?")
                    self.stopping.wait(10.0)
                    continue
            try:
                data, addr = self.sock.recvfrom(9000)
            except socket.timeout:
                # Quiet moment: a rename or a new IP is announced here.
                if (self.name_fn(), self.ip_fn()) != self._last:
                    self.announce()
                continue
            except OSError:
                try:
                    self.sock.close()
                except OSError:
                    pass
                self.sock = None
                continue
            self._answer_query(data, addr)
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def _answer_query(self, data, addr):
        name = (self.name_fn() or "").lower()
        ip = self.ip_fn()
        if not (name and ip):
            return
        for qname, qtype, qclass in parse_questions(data):
            if qtype not in (QTYPE_A, QTYPE_ANY):
                continue
            if qname.lower().rstrip(".") != name:
                continue
            unicast = bool(qclass & UNICAST_REPLY)
            try:
                # The address that reaches US from where the query came.
                ip = self.reachable_ip(peer=addr[0]) or ip
                if unicast:
                    # The asker set the QU bit: answer it directly. Echo its
                    # id, because a unicast reply is matched against it.
                    qid = struct.unpack("!H", data[:2])[0]
                    self.sock.sendto(build_response(name, ip, qid), addr)
                else:
                    self._send_multicast(
                        lambda src: build_response(
                            name, self.reachable_ip(peer=addr[0], iface=src), 0))
                self.answered += 1
                self.log(f"[mdns] answered {qname} -> {ip} "
                         f"({'unicast' if unicast else 'multicast'} to {addr[0]})")
            except OSError as e:
                self.log(f"[mdns] reply failed: {e}")
            return


def resolve(name, timeout=2.0):
    """Ask the LAN for a name ourselves, without the OS resolver.

    ignoAPI uses this to CHECK a name is reachable before saving a sync that
    depends on it -- on a machine whose OS will not do mDNS, socket.getaddrinfo
    simply fails and the user is left guessing whether the name or the network
    is at fault.
    """
    name = str(name or "").strip().rstrip(".")
    if not name:
        return None
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        s.bind(("", 0))
        s.settimeout(0.4)
        # QU bit set: ask for the answer straight back to this socket.
        q = struct.pack("!6H", 0x4321, 0, 1, 0, 0, 0)
        q += encode_name(name) + struct.pack("!2H", QTYPE_A, CLASS_IN | UNICAST_REPLY)
        end = time.time() + timeout
        ifaces = local_ipv4s()
        while time.time() < end:
            # Asked out of EVERY interface, for the same reason the
            # responder answers on every one: the default is not
            # necessarily the one the other machine is on.
            asked = 0
            for src in ifaces:
                try:
                    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(src))
                    s.sendto(q, (MDNS_ADDR, MDNS_PORT))
                    asked += 1
                except OSError:
                    continue
            if not asked:
                return None
            try:
                while True:
                    data, _addr = s.recvfrom(9000)
                    ip = _answer_a(data, name)
                    if ip:
                        return ip
            except socket.timeout:
                continue
        return None
    finally:
        s.close()


def _answer_a(data, want):
    """The A record for `want` out of a response, or None."""
    if len(data) < 12:
        return None
    _id, flags, qd, an, _ns, _ar = struct.unpack("!6H", data[:12])
    if not (flags & 0x8000) or an == 0:
        return None
    off = 12
    for _ in range(min(qd, 32)):
        try:
            _n, off = decode_name(data, off)
            off += 4
        except (struct.error, IndexError):
            return None
    for _ in range(min(an, 32)):
        try:
            rname, off = decode_name(data, off)
            rtype, _rclass, _ttl, rdlen = struct.unpack("!2HIH", data[off:off + 10])
            off += 10
            rdata = data[off:off + rdlen]
            off += rdlen
        except (struct.error, IndexError):
            return None
        if rtype == QTYPE_A and rdlen == 4 and rname.lower().rstrip(".") == want.lower():
            return socket.inet_ntoa(rdata)
    return None
