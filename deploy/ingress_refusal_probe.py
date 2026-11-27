"""#268: Core's early refusals of `POST /v1/packages` through the deployed reverse proxy. Exit 0 only if every answer
is Core's own JSON refusal and never a proxy 502. Run from the host against the ingress (standard library only):

    KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/ingress_refusal_probe.py http://127.0.0.1:8080 \
        [--repeat 50] [--mib 20]

The client streams the whole body like a real uploader, so the proxy is still sending when Core answers. Checks:
- no token, then a bad token, each `--repeat` times: 401 `{"error": "unauthenticated"}` every time;
- with the token (read from the environment, never printed): a body of 250 MiB, above `MAX_PACKAGE_BYTES`, `--repeat`
  times (at least 1, at most 20), 413 with Core's text every time. Without a token this check is skipped.
Nothing is stored: every request is refused before Core reads the package. Before the fix of #268 about one in ten
requests got `502 Bad Gateway` from nginx (a unit test of the same fault without a proxy: tests/test_package_submit.py).
"""
import argparse
import json
import os
import socket
import sys
import urllib.parse

MIB = 1024 * 1024
CHUNK = b"x" * 65536


def post(base: str, size: int, token: str | None) -> tuple[int, dict | None, bool]:
    """POST `size` bytes to /v1/packages. Returns (status, JSON of the answer or None, the body was sent whole)."""
    url = urllib.parse.urlsplit(base)
    head = {"Host": url.netloc, "Content-Type": "application/x-tar", "Content-Length": str(size),
            "Connection": "close"}
    if token:
        head["Authorization"] = f"Bearer {token}"
    sent_whole = True
    with socket.create_connection((url.hostname, url.port or 80), timeout=120) as s:
        s.sendall(("POST /v1/packages HTTP/1.1\r\n" + "".join(f"{k}: {v}\r\n" for k, v in head.items())
                   + "\r\n").encode())
        try:
            for _ in range(size // len(CHUNK)):
                s.sendall(CHUNK)
        except OSError:
            sent_whole = False
        raw = b""
        try:
            while part := s.recv(65536):
                raw += part
        except OSError:
            pass
    if not raw.startswith(b"HTTP/1."):
        return 0, None, sent_whole
    try:
        body = json.loads(raw.partition(b"\r\n\r\n")[2])
    except ValueError:
        body = None  # an HTML page: the proxy answered, not Core
    return int(raw.split(b" ", 2)[1]), body, sent_whole


def check(base: str, label: str, repeat: int, size: int, token: str | None, status: int, text: str) -> bool:
    bad = []
    for _ in range(repeat):
        got, body, _ = post(base, size, token)
        if got != status or not isinstance(body, dict) or text not in body.get("error", ""):
            bad.append(got)
    print(f"{'ok  ' if not bad else 'FAIL'} {label}: {repeat - len(bad)}/{repeat} gave Core's {status}"
          + (f"; others: {sorted(set(bad))}" if bad else ""))
    return not bad


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("base", help="ingress URL, for example http://127.0.0.1:8080")
    p.add_argument("--repeat", type=int, default=50)
    p.add_argument("--mib", type=int, default=20, help="body size of the 401 checks")
    args = p.parse_args(argv)
    token = os.environ.get("KUTUPHANE_PROBE_TOKEN")
    ok = check(args.base, "no token", args.repeat, args.mib * MIB, None, 401, "unauthenticated")
    ok = check(args.base, "bad token", args.repeat, args.mib * MIB, "x.y.z", 401, "unauthenticated") and ok
    if token:
        ok = check(args.base, "declared 250 MiB", min(max(args.repeat, 1), 20), 250 * MIB, token, 413,
                   "too large") and ok
    else:
        print("skip 413 check: set KUTUPHANE_PROBE_TOKEN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
