"""AT-10 network half: run INSIDE the core container; exit 0 only if core reaches nothing but its allowed peers.

    docker compose --profile app exec -T core python -I - < deploy/egress_probe.py

Allowed: postgres (and llmdap once it joins the core network). Everything else must fail: the internet, DNS
names outside the compose network, and the host's own model servers.
"""
import socket
import sys

ALLOWED = [("postgres", 5432)]
FORBIDDEN = [("1.1.1.1", 443), ("8.8.8.8", 53), ("huggingface.co", 443), ("host.docker.internal", 11434),
             ("172.17.0.1", 11434)]


def reachable(host: str, port: int) -> bool:
    try:
        socket.create_connection((host, port), timeout=3).close()
        return True
    except OSError:
        return False


failures = [f"cannot reach allowed {h}:{p}" for h, p in ALLOWED if not reachable(h, p)]
failures += [f"REACHED forbidden {h}:{p}" for h, p in FORBIDDEN if reachable(h, p)]
print("\n".join(failures) or "egress ok: only allowed peers reachable")
sys.exit(1 if failures else 0)
