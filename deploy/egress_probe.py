"""AT-10 network half: run INSIDE the core container; exit 0 only if core reaches nothing but its allowed peers.

    docker compose -f deploy/compose.full.yaml --env-file .env --profile app exec -T core python -I - [host:port ...] \
        < deploy/egress_probe.py
    docker compose exec -T core python -I - --light < deploy/egress_probe.py

Allowed: postgres and llmdap; with `--light` (the light install, #76), postgres only, and llmdap is forbidden too.
The ingress proxy shares the `web` network with core, so core can open a connection to
it; that is a known peer, not a way out (`web` has no route out). It is reported, not failed. Three things are
checked separately (Astra
review #4), because one failed connection does not say which layer stopped it:
- no default route: an internal compose network has none, so no address outside it is routable at all;
- outside names do not resolve: DNS is not a way out either;
- forbidden addresses do not accept a connection: public hosts, the host gateway, the host's model servers, plus
  any `host:port` given as arguments (this installation's real model or gateway addresses).
"""
import socket
import sys

ALLOWED = [("postgres", 5432), ("llmdap", 8787)]
KNOWN_PEERS = [("ingress", 8080)]  # reachable by design of compose networks; reported (Astra review #7)
OUTSIDE_NAMES = ["huggingface.co", "pypi.org", "host.docker.internal"]
FORBIDDEN = [("1.1.1.1", 443), ("8.8.8.8", 53), ("172.17.0.1", 11434)]


def default_route() -> str | None:
    """Gateway of the default route from /proc/net/route (destination 00000000), or None."""
    with open("/proc/net/route") as f:
        for line in f.readlines()[1:]:
            fields = line.split()
            if fields[1] == "00000000":
                return socket.inet_ntoa(bytes.fromhex(fields[2])[::-1])
    return None


def resolves(name: str) -> bool:
    try:
        return bool(socket.getaddrinfo(name, None))
    except OSError:
        return False


def reachable(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True
    except OSError:
        return False


def target(arg: str) -> tuple[str, int]:
    host, _, port = arg.rpartition(":")
    return host, int(port)


light = "--light" in sys.argv[1:]
args = [a for a in sys.argv[1:] if a != "--light"]
allowed, gone = (ALLOWED[:1], ALLOWED[1:]) if light else (ALLOWED, [])
forbidden = FORBIDDEN + gone + [target(a) for a in args]
failures = [f"cannot reach allowed {h}:{p}" for h, p in allowed if not reachable(h, p)]
gateway = default_route()
failures += [f"HAS a default route via {gateway}"] if gateway else []
failures += [f"RESOLVED outside name {n}" for n in OUTSIDE_NAMES if resolves(n)]
failures += [f"REACHED forbidden {h}:{p}" for h, p in forbidden if reachable(h, p)]
peers = [f"{h}:{p}" for h, p in KNOWN_PEERS if reachable(h, p)]
print("\n".join(failures) or "egress ok: no default route, no outside names, only allowed peers reachable"
      + (f" (known peers also reachable: {', '.join(peers)})" if peers else ""))
sys.exit(1 if failures else 0)
