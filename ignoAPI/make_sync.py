"""
make_sync.py — set up a STAR sync from this machine to rob1 and rob2.

    python make_sync.py --check     # probe everything, change nothing
    python make_sync.py             # create it
    python make_sync.py --remove    # take it down again

WHAT IT BUILDS

    ignoapi_rob1.local ─┐
                        ├─► this machine, variable "server"
    ignoapi_rob2.local ─┘

A STAR: both robots talk to this machine and to neither each other. Every
peer gets its own pair of boxes here, so a value from rob1 cannot be
overwritten by one from rob2 arriving in the same poll, and this machine can
address either robot on its own:

    server_tx                          -> both robots
    server_ignoapi_rob1.local_tx       -> rob1 only
    server_ignoapi_rob1.local_rx       <- what rob1 sent
    server_ignoapi_rob2.local_tx       -> rob2 only
    server_ignoapi_rob2.local_rx       <- what rob2 sent
    server_rx                             most recent from either
    server_status / server_peers          how the link is doing

runatstartup is TRUE, so the sync child comes back with ignoAPI rather than
having to be started by hand after a reboot.

WHY IT CHECKS FIRST
    A sync pointed at a name that does not resolve still gets created: the
    child starts and retries forever, and the only sign is a status row nobody
    is looking at. Two seconds of probing up front turns that into a sentence.
"""
import argparse
import sys

sys.path.insert(0, r"C:\Users\abira\PycharmProjects\enMac-jk2")

import ignoClient as c
import ignodiscover
import ignomdns

# ── what to build ────────────────────────────────────────────────────
VARIABLE = "server"
PEERS = ["ignoapi_rob1.local", "ignoapi_rob2.local"]
TOPOLOGY = "star"
RUN_AT_STARTUP = True
API_PORT = 8899

# The hub is THIS machine. Loopback rather than its own mDNS name: an address
# is preferred over a name because names move with DHCP, and loopback is the
# one address that cannot -- it is always this machine, and it works even when
# nothing has been typed into ADDRESS yet.
HUB = "127.0.0.1"


def probe(peers, api_port):
    """Resolve and reach every peer. Returns (ok, [(peer, note)])."""
    seen = {}
    try:
        for m in ignodiscover.scan(timeout=1.5):
            if m["name"]:
                seen[m["name"].lower()] = m
    except Exception:
        pass

    rows, ok = [], True
    for p in peers:
        ip = None
        try:
            ip = ignomdns.resolve(p, timeout=2.0)
        except Exception:
            pass
        if ip is None and p.lower() in seen:
            ip = seen[p.lower()]["ip"]
        if ip is None:
            rows.append((p, "NOT FOUND — is ignoAPI running there, with "
                            "ADDRESS set?"))
            ok = False
            continue
        try:
            mods = c.listModules(p, api_port)
            n = sum(len(v) for v in mods.values())
            rows.append((p, "%s — answering, %d module(s) configured" % (ip, n)))
        except Exception as e:
            rows.append((p, "%s — resolves, but will not answer on %d (%s)"
                         % (ip, api_port, e)))
            ok = False
    return ok, rows


def show_rows(host, api_port, variable):
    """Print the boxes the sync owns, and what is in them."""
    try:
        store = c.igo_read_all() if host in ("127.0.0.1", "localhost") else None
    except Exception:
        store = None
    if store is None:
        try:
            store = c._rpc(host, api_port, {"action": "read_all"})["value"]
        except Exception as e:
            print("   (could not read the rows back: %s)" % e)
            return
    mine = sorted(k for k in store if k == variable or k.startswith(variable + "_"))
    if not mine:
        print("   (no rows yet — the child creates them on its first poll)")
        return
    for k in mine:
        v = store[k]
        v = "" if v is None else str(v)
        print("   %-42s %s" % (k, (v[:46] + "...") if len(v) > 46 else repr(v)))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--hub", default=HUB,
                    help="the machine that hosts the sync (default: this one)")
    ap.add_argument("--port", type=int, default=API_PORT)
    ap.add_argument("--name", default=VARIABLE, help="the variable to sync")
    ap.add_argument("--peers", nargs="*", default=PEERS)
    ap.add_argument("--topology", default=TOPOLOGY, choices=["star", "delta"])
    ap.add_argument("--check", action="store_true",
                    help="probe only; change nothing")
    ap.add_argument("--remove", action="store_true",
                    help="delete the sync, here and on the peers")
    ap.add_argument("--force", action="store_true",
                    help="create it even if a peer did not answer")
    a = ap.parse_args()

    print("hub      : %s:%d" % (a.hub, a.port))
    print("variable : %s" % a.name)
    print("topology : %s" % a.topology.upper())
    print("peers    : %s" % ", ".join(a.peers))
    print()

    if a.remove:
        try:
            print(c.deleteModule(a.hub, a.port, a.name))
            print("\nGone — here and on each peer that answered.")
        except RuntimeError as e:
            print("could not remove it:", e)
            return 1
        return 0

    print("checking the peers...")
    ok, rows = probe(a.peers, a.port)
    for peer, note in rows:
        print("   %-22s %s" % (peer, note))
    print()

    if a.check:
        print("Check only — nothing was changed.")
        return 0 if ok else 1

    if not ok and not a.force:
        print("Not creating it: a sync pointed at a machine that is not there")
        print("starts a child that retries forever, and the only sign is a")
        print("status row nobody reads. Fix the peer, or pass --force.")
        return 1

    try:
        msg = c.createSyncIgnoAPI(a.hub, a.port, a.name, a.peers,
                                  topology=a.topology,
                                  runatstartup=True)
    except RuntimeError as e:
        print("could not create it:", e)
        return 1
    print(msg)

    print("\nrows on the hub:")
    show_rows(a.hub, a.port, a.name)

    print("\nSend to one robot on its own:")
    for p in a.peers:
        print("   %s_%s_tx" % (a.name, p))
    print("Send to both:")
    print("   %s_tx" % a.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
