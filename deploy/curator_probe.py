"""T-DEP (docs/25 §3.2, §12.2): check the deployed curator web sidecar from a device of the operator's tailnet.

    python3 deploy/curator_probe.py https://kutuphane-curator.<tailnet>.ts.net [--compose-project kutuphane]

Checks, each printed as PASS or FAIL:
  1. HTTPS 443 answers with the curator page and the strict headers (CSP frame-ancestors 'none', nosniff,
     no-referrer); plain HTTP 80 and another port do not answer;
  2. `tailscale funnel status` inside the sidecar container is empty (also run it again after a sidecar restart);
  3. the curator container has no published port, and Core's network cannot reach it (curator:8090 from `core`);
  4. a POST from another origin is refused (403).
Standard library and the docker CLI only. It changes nothing.
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


def docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30).stdout


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
    sidecar = f"{args.compose_project}-tailscale-1"
    funnel = docker("exec", sidecar, "tailscale", "funnel", "status", "--json")
    try:
        on = bool(json.loads(funnel or "{}").get("AllowFunnel"))
    except ValueError:
        on = True
    results.append(check("Funnel is off in the sidecar", not on, funnel.strip()[:120]))
    ports = docker("port", f"{args.compose_project}-curator-1")
    results.append(check("the curator container publishes no port", not ports.strip(), ports.strip()))
    reach = subprocess.run(["docker", "exec", f"{args.compose_project}-core-1", "python", "-c",
                            "import socket; socket.create_connection(('curator', 8090), timeout=3)"],
                           capture_output=True, text=True, timeout=30)
    results.append(check("Core cannot reach curator web", reach.returncode != 0))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
