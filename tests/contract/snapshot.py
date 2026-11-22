"""Builds the snapshot of the contracts a consumer depends on (#242): MCP tools, HTTP routes, error texts.

`python -m tests.contract.snapshot` prints it; `--write` rewrites tests/contract/*.json.
Writing the files does not authorise a contract change (see test_contract.py).

What is covered (nothing here needs a database):
- tools.json: for every MCP tool: name, description, input schema, output schema (when declared). Two builds: the
  full one (with a model gateway: `ask_library` and the job tools) and the one without.
- http.json: every HTTP route: path and methods. Starlette has no OpenAPI document and the handlers declare no
  response models, so there is no response schema to record; the route table is the contract that exists.
- errors.json: the HTTP status and text of every expected error class, the named error constants, and every message
  literal in a `raise` of the modules the API and the tools run (the text a caller can read).
"""
import argparse
import ast
import asyncio
import json
import sys
import tempfile
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.routing import Mount, Route

from kutuphane import server
from kutuphane.identity import Verifier

HERE = Path(__file__).parent
SRC = Path(server.__file__).parent
ISSUER, AUDIENCE, PUBLIC_URL = "https://idp.contract.test/", "kutuphane", "https://kutuphane.contract.test"
# Command line, passkey web and dev-login messages are not part of the API or tool contract.
NOT_API = {"cli.py", "curatorweb.py", "passkey.py", "devauth.py", "__init__.py"}
ERROR_CONSTANTS = {"server": ("NO_ANSWERS", "PASSAGE_NOT_FOUND"), "notes": ("MALFORMED_PASSAGE", "WITHHELD"),
                   "decisions": ("WITHHELD",)}


def _verifier(tmp: Path) -> Verifier:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    path = tmp / "jwks.json"
    path.write_text(json.dumps({"keys": [{**jwk, "kid": "k1", "use": "sig", "alg": "RS256"}]}))
    return Verifier.from_files(ISSUER, AUDIENCE, path)


def tools(verifier: Verifier, *, answering: bool) -> list[dict]:
    mcp = server.build_mcp(dsn="postgresql://contract.invalid/none", verifier=verifier,
                           bridge=object() if answering else None, model="contract-model" if answering else None,
                           public_url=PUBLIC_URL)
    out = []
    for t in asyncio.run(mcp.list_tools()):  # list order is fixed by build_mcp
        out.append({"name": t.name, "description": t.description, "input_schema": t.input_schema,
                    **({"output_schema": t.output_schema} if t.output_schema else {})})
    return out


def routes(verifier: Verifier) -> list[dict]:
    app = server.create_app(dsn="postgresql://contract.invalid/none", verifier=verifier, bridge=None, model=None,
                            public_url=PUBLIC_URL)
    out = []
    for r in app.routes:
        if isinstance(r, Route):
            out.append({"path": r.path, "methods": sorted(r.methods - {"HEAD"}) if r.methods else []})
        elif isinstance(r, Mount):
            out.append({"path": r.path or "/", "mount": True})
    return sorted(out, key=lambda r: (r["path"], r.get("methods", [])))


def raised_texts() -> dict[str, list[str]]:
    found = {}
    for path in sorted(SRC.glob("*.py")):
        if path.name in NOT_API:
            continue
        texts = set()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                texts.add(ast.unparse(node.exc.args[0]))
        if texts:
            found[path.name] = sorted(texts)
    return found


def errors() -> dict:
    import importlib
    return {
        "http": [{"class": kind.__name__, "status": status, "text": text} for kind, status, text in server.ERRORS],
        "unexpected": "internal error",
        "constants": {f"{mod}.{name}": getattr(importlib.import_module(f"kutuphane.{mod}"), name)
                      for mod, names in ERROR_CONSTANTS.items() for name in names},
        "raised": raised_texts(),
    }


def build() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        verifier = _verifier(Path(tmp))
        return {"tools.json": {"with_model_gateway": tools(verifier, answering=True),
                               "without_model_gateway": tools(verifier, answering=False)},
                "http.json": routes(verifier), "errors.json": errors()}


def dump(value) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--write", action="store_true", help="rewrite tests/contract/*.json (needs contract approval)")
    args = ap.parse_args(argv)
    built = build()
    for name, value in built.items():
        if args.write:
            (HERE / name).write_text(dump(value), encoding="utf-8")
            print(f"wrote tests/contract/{name}")
        else:
            print(f"== {name}\n{dump(value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
