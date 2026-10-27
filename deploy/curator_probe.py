"""T-DEP (docs/25 §3.2, §12.2): check the deployed curator web sidecar on the docker host, which is on the tailnet.

    python3 deploy/curator_probe.py https://kutuphane-curator.<tailnet>.ts.net [--compose-project kutuphane]

Checks, each printed as PASS or FAIL:
  1. HTTPS 443 answers with the curator page and the strict headers (CSP frame-ancestors 'none', nosniff,
     no-referrer); plain HTTP 80 and another port do not answer;
  2. `tailscale funnel status --json` inside the sidecar container shows no AllowFunnel (also run it again after a
     sidecar restart);
  3. the curator container has no published port, and Core's network cannot reach it (curator:8090 from `core`);
  4. a POST from another origin is refused (403).
Standard library and the docker CLI only. It changes nothing. Checks 2 and 3 run docker on the host of the containers
(`<project>-tailscale-1`, `-curator-1`, `-core-1`): a docker failure, a missing container or an empty Funnel status is
FAIL, and Core "cannot reach" curator only on a DNS or connection error.
"""
import argparse
import http.client
import json
import socket
import ssl
import subprocess
import sys
import urllib.parse


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    return ok


def https(host: str, method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    conn = http.client.HTTPSConnection(host, 443, timeout=10, context=ssl.create_default_context())
    conn.request(method, path, body=body, headers=headers or {})
    r = conn.getresponse()
    return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()


def closed(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=5):
            return False
    except OSError:
        return True


UNREACHABLE = "UNREACHABLE"
# Inside Core: only a DNS or a connection error means "cannot reach"; any other failure is not a test (exit 1).
REACH = ("import socket, sys\n"
         "try:\n"
         "    socket.create_connection(('curator', 8090), timeout=3)\n"
         "except (socket.gaierror, ConnectionError, TimeoutError) as exc:\n"
         f"    print('{UNREACHABLE}', type(exc).__name__); sys.exit(3)\n")


def docker(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["docker", *args], 127, "", str(exc))


def failed(r: subprocess.CompletedProcess) -> str:
    return f"docker exit {r.returncode}: {(r.stderr or '').strip()[:120]}"


def docker_checks(project: str) -> list[bool]:
    """Checks 2 and 3. Each one fails when docker fails or cannot see its container: run the probe where they run."""
    names = {k: f"{project}-{k}-1" for k in ("tailscale", "curator", "core")}
    seen = {k: docker("inspect", "--type", "container", n).returncode == 0 for k, n in names.items()}
    results = [check(f"container {n} exists", seen[k]) for k, n in names.items()]
    if seen["tailscale"]:
        r = docker("exec", names["tailscale"], "tailscale", "funnel", "status", "--json")
        try:
            status = json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None
        except ValueError:
            status = None
        ok = isinstance(status, dict) and not status.get("AllowFunnel")
        results.append(check("Funnel is off in the sidecar", ok,
                             r.stdout.strip()[:120] if r.returncode == 0 and r.stdout.strip()
                             else failed(r) if r.returncode else "empty funnel status"))
    if seen["curator"]:
        r = docker("port", names["curator"])
        results.append(check("the curator container publishes no port", r.returncode == 0 and not r.stdout.strip(),
                             r.stdout.strip() if r.returncode == 0 else failed(r)))
    if seen["core"] and seen["curator"]:
        r = docker("exec", names["core"], "python", "-c", REACH)
        results.append(check("Core cannot reach curator web", r.returncode == 3 and UNREACHABLE in r.stdout,
                             r.stdout.strip()[:120] or failed(r)))
    return results




def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("origin")
    ap.add_argument("--compose-project", default="kutuphane")
    args = ap.parse_args()
    host = urllib.parse.urlsplit(args.origin).hostname
    results = []
    status, headers, body = https(host, "GET", "/")
    csp = headers.get("content-security-policy", "")
    results.append(check("443 serves the curator page with strict headers",
                         status == 200 and "Kütüphane curator".encode() in body
                         and "frame-ancestors 'none'" in csp and headers.get("x-content-type-options") == "nosniff"
                         and headers.get("referrer-policy") == "no-referrer", f"status {status}"))
    results.append(check("port 80 does not answer", closed(host, 80)))
    results.append(check("port 8443 does not answer", closed(host, 8443)))
    status, _, _ = https(host, "POST", "/auth/passkey/options", b"{}", {"content-type": "application/json",
                                                                       "origin": "https://evil.example"})
    results.append(check("a POST from another origin is refused", status == 403, f"status {status}"))
    results.extend(docker_checks(args.compose_project))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
