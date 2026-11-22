"""Builds the snapshot of the contracts a consumer depends on (#242): MCP tools, HTTP routes, error texts, and the
shape of real results.

`python -m tests.contract.snapshot` prints it; `--write` rewrites tests/contract/*.json. Both need
KUTUPHANE_TEST_DSN (a database whose name ends in `_test`: it is RESET, as the `conn` fixture does).
Writing the files does not authorise a contract change (see test_contract.py).

- tools.json: the tools of a deployment WITHOUT a model gateway (no `ask_library`, no job tools): name, description,
  input schema, output schema. The tools of the deployment with a gateway are recorded as the client receives them,
  by the `tools/list` cases over POST /mcp in results_http.json.
- http.json: every HTTP route: path and all its methods (HEAD included).
- errors.json: the HTTP status and text of every expected error class, the value of every public module-level string constant
  of those modules (SKILL_BLOCKED, CLOUD_OK, NOT_IN_LIBRARY, ...), and every message literal in a `raise` of the
  modules the API and the tools run, as written. The executed cases of the results files hold the texts a caller gets.
- matrix.json: which kinds of case (ok, not found, bad request, unauthorized, HEAD) the results cover for each tool
  and route, with the reason for each kind that does not apply (matrix.py).
- results_mcp.json, results_http.json: the shape (keys and types, no values) of what every tool and route returns
  for the cases of the matrix, from the controlled fixture of scenario.py. MCP keeps the whole result envelope
  (content blocks, structuredContent, isError, _meta); HTTP keeps status and content type (and, for HEAD, that the
  body is empty).
"""
import argparse
import ast
import asyncio
import importlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.routing import Mount, Route
from starlette.testclient import TestClient

from kutuphane import server
from kutuphane.identity import Verifier

from . import matrix

HERE = Path(__file__).parent
SRC = Path(server.__file__).parent
ISSUER, AUDIENCE, PUBLIC_URL = "https://idp.contract.test/", "kutuphane", "https://kutuphane.contract.test"
# Command line, passkey web and dev-login messages are not part of the API or tool contract.
NOT_API = {"cli.py", "curatorweb.py", "passkey.py", "devauth.py", "__init__.py"}


def _verifier(tmp: Path) -> tuple[Verifier, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    path = tmp / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISSUER, AUDIENCE, path), key


def tools(verifier: Verifier, *, answering: bool) -> list[dict]:
    mcp = server.build_mcp(dsn="postgresql://contract.invalid/none", verifier=verifier,
                           bridge=object() if answering else None, model="contract-model" if answering else None,
                           public_url=PUBLIC_URL)
    out = []
    for t in asyncio.run(mcp.list_tools()):  # list order is fixed by build_mcp
        out.append({"name": t.name, "description": t.description, "input_schema": t.input_schema,
                    **({"output_schema": t.output_schema} if t.output_schema else {})})
    return out


PROBE_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def probe_mcp(app, key) -> dict[str, dict[str, dict]]:
    """How the MCP endpoint answers each method, with a valid token, in each protocol era: {method: {era: {status,
    content type, Allow}}}. A route table cannot say it: the endpoint is an ASGI app that decides by method."""
    now = int(time.time())
    token = jwt.encode({"iss": ISSUER, "aud": AUDIENCE, "sub": "probe", "iat": now, "exp": now + 300}, key,
                       algorithm="RS256", headers={"kid": "k1"})
    answers: dict[str, dict[str, dict]] = {m: {} for m in PROBE_METHODS}
    with TestClient(app, base_url=PUBLIC_URL) as client:
        for method in PROBE_METHODS:
            for era in matrix.ERAS:
                headers = {"Authorization": f"Bearer {token}", "MCP-Protocol-Version": era,
                           "Accept": "application/json, text/event-stream"}
                with client.stream(method, "/mcp", headers=headers) as r:  # the headers only: a GET may be a stream
                    answers[method][era] = {"status": r.status_code, "allow": r.headers.get("allow"),
                                            "content_type": r.headers.get("content-type", "").split(";")[0] or None}
    return answers


def routes(verifier: Verifier, key) -> list[dict]:
    app = server.create_app(dsn="postgresql://contract.invalid/none", verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC_URL)
    out = []
    for r in app.routes:
        if isinstance(r, Route):
            out.append({"path": r.path, "methods": sorted(r.methods) if r.methods else []})
        elif isinstance(r, Mount):
            out.append({"path": r.path or "/", "mount": True})
            for inner in getattr(r.app, "routes", []):  # the routes the mount serves: /mcp, the metadata
                entry = {"path": (r.path or "") + inner.path, "inside": r.path or "/",
                         "methods": sorted(inner.methods) if getattr(inner, "methods", None) else []}
                if not entry["methods"]:  # an ASGI endpoint: ask it which methods it serves
                    answers = probe_mcp(app, key)
                    entry["answers"] = answers
                    entry["methods"] = sorted(m for m, eras in answers.items()
                                              if any(a["status"] not in (404, 405) for a in eras.values()))
                out.append(entry)
    return sorted(out, key=lambda r: (r["path"], r.get("methods", [])))


def raised() -> dict[str, list[str]]:
    """{module file: the first argument of every `raise X(...)`, as written}."""
    texts = {}
    for path in sorted(SRC.glob("*.py")):
        if path.name in NOT_API:
            continue
        found = set()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                found.add(ast.unparse(node.exc.args[0]))
        if found:
            texts[path.name] = sorted(found)
    return texts


def constants() -> dict[str, str]:
    """The VALUE of every public module-level string constant of the API and tool modules (an UPPER_CASE name without
    a leading underscore, one line): `SKILL_BLOCKED`, `CLOUD_OK`, `NOT_IN_LIBRARY`, the environment variable names...
    A raise or a response that names a constant would otherwise change its text with no change in the snapshot."""
    found = {}
    for path in sorted(SRC.glob("*.py")):
        if path.name in NOT_API:
            continue
        module = importlib.import_module(f"kutuphane.{path.stem}")
        for name, value in sorted(vars(module).items()):
            if name.isupper() and not name.startswith("_") and isinstance(value, str) and "\n" not in value \
                    and name in _assigned_names(path):
                found[f"{path.stem}.{name}"] = value
    return found


def _assigned_names(path: Path) -> set[str]:
    """The names a module assigns itself (not the ones it imports)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {t.id for node in tree.body if isinstance(node, ast.Assign) for target in node.targets
            for t in ast.walk(target) if isinstance(t, ast.Name)}


def errors() -> dict:
    texts = raised()
    return {
        "http": [{"class": kind.__name__, "status": status, "text": text} for kind, status, text in server.ERRORS],
        "unexpected": "internal error",
        "constants": constants(),
        "raised": texts,
    }


DSN_ENV = "KUTUPHANE_TEST_DSN"
RESULTS = ("results_mcp.json", "results_http.json")


def build_static() -> dict[str, object]:
    """The files that need no database."""
    with tempfile.TemporaryDirectory() as tmp:
        verifier, key = _verifier(Path(tmp))
        return {"tools.json": {"without_model_gateway": tools(verifier, answering=False)},
                "http.json": routes(verifier, key), "errors.json": errors(), "matrix.json": matrix.snapshot()}


def build_results(dsn: str) -> dict[str, object]:
    from . import scenario
    return {f"{name}.json": value for name, value in scenario.collect(dsn).items()}


def dump(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="rewrite tests/contract/*.json (needs contract approval)")
    args = ap.parse_args(argv)
    dsn = os.environ.get(DSN_ENV)
    if not dsn:
        sys.exit(f"{DSN_ENV} is not set (a database whose name ends in _test; it is reset)")
    built = {**build_static(), **build_results(dsn)}
    for name, value in built.items():
        if args.write:
            (HERE / name).write_text(dump(value), encoding="utf-8")
            print(f"wrote tests/contract/{name}")
        else:
            print(f"== {name}\n{dump(value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
