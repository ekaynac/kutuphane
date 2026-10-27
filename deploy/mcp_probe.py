"""docs/24 T33, the boundary half: MCP through the deployed reverse proxy, for both protocol versions. Exit 0 only if
every check passes. Run from the host against the ingress (standard library only):

    KUTUPHANE_PROBE_TOKEN=<access token> python3 deploy/mcp_probe.py http://127.0.0.1:8080 [--journal <book>]

The token is read from the environment and never printed. Checks, for a 2025-11-25 client (with `initialize`) and a
2026-07-28 client (per-request `_meta`, `Mcp-Method`/`Mcp-Name` headers, no `initialize`):
- `tools/list` answers twice with the same tools in the same order;
- `search_library` answers with `structuredContent.result` (a list);
- `propose_note` into `--journal`, when that tool is served and a journal is given;
- no token: 401 with the protected-resource metadata in `WWW-Authenticate`;
- 2026-07-28: an `Mcp-Name` header different from the body is refused with -32020 (the proxy passes the headers).
The "internal error" text of an unexpected failure is checked in-process (tests/test_server.py): a live server has no
safe way to make one.
"""
import json
import os
import sys
import urllib.error
import urllib.request

MODERN, LEGACY = "2026-07-28", "2025-11-25"
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def post(base: str, body: dict, headers: dict) -> tuple[int, dict, dict | None]:
    request = urllib.request.Request(f"{base}/mcp", data=json.dumps(body).encode(), headers={**HEADERS, **headers},
                                     method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as r:
            status, head, text = r.status, {k.lower(): v for k, v in r.headers.items()}, r.read().decode()
    except urllib.error.HTTPError as e:
        status, head, text = e.code, {k.lower(): v for k, v in e.headers.items()}, e.read().decode()
    if head.get("content-type", "").startswith("text/event-stream"):
        data = [line[5:] for line in text.splitlines() if line.startswith("data:")]
        return status, head, json.loads(data[-1]) if data else None
    return status, head, json.loads(text) if text.strip().startswith("{") else None


def rpc(base: str, auth: dict, version: str, method: str, params: dict | None = None,
        extra: dict | None = None) -> tuple[int, dict, dict | None]:
    params = dict(params or {})
    if version == MODERN:
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": MODERN,
                           "io.modelcontextprotocol/clientCapabilities": {},
                           "io.modelcontextprotocol/clientInfo": {"name": "kutuphane-mcp-probe", "version": "1"}}
        era = {"MCP-Protocol-Version": MODERN, "Mcp-Method": method,
               **({"Mcp-Name": params["name"]} if "name" in params else {})}
    else:
        init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": LEGACY, "capabilities": {},
                           "clientInfo": {"name": "kutuphane-mcp-probe", "version": "1"}}}
        status, head, msg = post(base, init, auth)
        if status != 200:
            return status, head, msg
        era = {"MCP-Protocol-Version": LEGACY}
    return post(base, {"jsonrpc": "2.0", "id": 2, "method": method, "params": params}, {**era, **auth, **(extra or {})})


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    base = argv[0].rstrip("/")
    journal = argv[argv.index("--journal") + 1] if "--journal" in argv else None
    token = os.environ.get("KUTUPHANE_PROBE_TOKEN")
    if not token:
        print("set KUTUPHANE_PROBE_TOKEN")
        return 2
    auth = {"Authorization": f"Bearer {token}"}
    failures = []

    def check(name: str, ok: bool) -> None:
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
        if not ok:
            failures.append(name)

    for version in (LEGACY, MODERN):
        lists = [rpc(base, auth, version, "tools/list") for _ in range(2)]
        names = [[t["name"] for t in m["result"]["tools"]] if s == 200 and m and "result" in m else None
                 for s, _h, m in lists]
        check(f"{version} tools/list stable", names[0] is not None and names[0] == names[1])
        status, _h, msg = rpc(base, auth, version, "tools/call",
                              {"name": "search_library", "arguments": {"query": "probe"}})
        result = (msg or {}).get("result", {})
        check(f"{version} search_library structuredContent.result",
              status == 200 and not result.get("isError") and isinstance(result.get("structuredContent", {})
                                                                         .get("result"), list))
        if journal and names[0] and "propose_note" in names[0]:
            status, _h, msg = rpc(base, auth, version, "tools/call", {"name": "propose_note", "arguments": {
                "book": journal, "kind": "test_result", "text": f"MCP probe through the proxy ({version})."}})
            result = (msg or {}).get("result", {})
            check(f"{version} propose_note", status == 200 and not result.get("isError"))
        status, head, _m = rpc(base, {}, version, "tools/list")
        check(f"{version} no token -> 401 with resource metadata",
              status == 401 and "resource_metadata=" in head.get("www-authenticate", ""))
    status, _h, msg = rpc(base, auth, MODERN, "tools/call", {"name": "search_library", "arguments": {"query": "x"}},
                          extra={"Mcp-Name": "open_citation"})
    check(f"{MODERN} Mcp-Name mismatch -> -32020",
          status == 400 and (msg or {}).get("error", {}).get("code") == -32020)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
