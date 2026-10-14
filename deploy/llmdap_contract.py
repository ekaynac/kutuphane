"""Live contract check against a REAL LLMDAP gateway (AT-09, AT-11 LLMDAP side; D52). Run it on an installation
before trusting the bridge, and after every LLMDAP upgrade.

    KUTUPHANE_DSN=<a scratch database> KUTUPHANE_LLMDAP_URL=... KUTUPHANE_LLMDAP_KEY=... \\
    python -I deploy/llmdap_contract.py <okf book dir> --chat <route> <model> --embed <route> <model> \\
        --audit-export "<command that prints the verified LLMDAP chain as JSONL>"

LLMDAP must run with GATEWAY_AUTH_MODE=subject-keys and grant Core's subject `llm:invoke` on both routes. The
check publishes the book as `contract-check` into the given database, indexes it, searches, answers, joins the
unified audit with LLMDAP's own chain, and verifies that LLMDAP refuses a claimed subject, a wrong key and the
shared secret. Exit 0 only if every check passes.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kutuphane import answers, audit, authz, catalog, db, llmdap, profiles, search, vectors
from kutuphane.gate import Actor
from kutuphane.policy import make_policy
from kutuphane.source import read_source

BOOK, USER, AGENT = "contract-check", "user:contract-user", "agent:contract-agent"
SHARED_SECRET_ENV = "LLMDAP_GATEWAY_TRUST_SECRET"
QUESTION = "Erişim kayıtları ne kadar süre saklanır?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chat", nargs=2, required=True, metavar=("ROUTE", "MODEL"))
    ap.add_argument("--embed", nargs=2, required=True, metavar=("ROUTE", "MODEL"))
    ap.add_argument("--audit-export", required=True)
    args = ap.parse_args()
    url, key = os.environ[llmdap.ENV["url"]].rstrip("/"), os.environ[llmdap.ENV["key"]]
    chat = llmdap.Bridge(url, args.chat[0], key, "local")
    emb = llmdap.Embedder(llmdap.Bridge(url, args.embed[0], key, "local"), args.embed[1])
    results = {}

    def check(name, ok, detail=""):
        results[name] = bool(ok)
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))

    def status(headers) -> int:
        body = json.dumps({"model": args.chat[1], "messages": [{"role": "user", "content": "x"}]}).encode()
        req = urllib.request.Request(f"{url}/bridge/{args.chat[0]}/v1/chat/completions", data=body, method="POST",
                                     headers={"content-type": "application/json", **headers})
        try:
            with llmdap._OPENER.open(req, timeout=60) as r:  # never follows a redirect (it would carry the key)
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    with db.connect() as conn:
        db.migrate(conn)
        catalog.publish(conn, book=BOOK, title=BOOK, files=read_source(Path(args.book_dir)),
                        policy=make_policy(sensitivity="normal", egress="local_only", protection="standard"),
                        profile=profiles.spec("chunked"))
        authz.grant(conn, f"book:{BOOK}", "read", USER)
        authz.delegate(conn, delegator=USER, delegate_to=AGENT, obj=f"book:{BOOK}", mode="read",
                       expires_at=datetime.now(timezone.utc) + timedelta(hours=1))
        vectors.index(conn, emb, BOOK)
        count = conn.execute("SELECT count(*) FROM chunk_vector WHERE book = %s AND model = %s",
                             (BOOK, emb.model)).fetchone()[0]
        check("index through the embeddings route", count > 0, f"{count} vectors")

        actor = Actor(AGENT, on_behalf_of=USER)
        vector = vectors.query_vector(conn, emb, actor, QUESTION)
        hits = search.search(conn, actor, QUESTION, k=3, vector=vector)
        check("hybrid search with a query vector", vector is not None and hits)
        result = answers.ask(conn, chat, actor, QUESTION, model=args.chat[1], embedder=emb)
        check("answer through the chat route", result["status"] in ("answered", "not_in_library"), result["status"])

        calls = conn.execute("SELECT call_id, derived_correlation_id, http_status FROM model_call "
                             "WHERE correlation_id = %s", (actor.correlation_id,)).fetchall()
        check("every call carries LLMDAP's derived id", calls and all(
            d and d.endswith(":" + c) and s == 200 for c, d, s in calls), f"{len(calls)} calls")
        export = subprocess.run(shlex.split(args.audit_export), capture_output=True, text=True, check=False)
        check("LLMDAP audit chain verifies", export.returncode == 0, f"export exit {export.returncode}")
        entries = [json.loads(line) for line in export.stdout.splitlines() if line.strip()] \
            if export.returncode == 0 else []
        check("unified audit is complete against LLMDAP's chain (AT-09)",
              audit.explain(conn, actor.correlation_id, entries)["complete"])
        mine = [e for e in entries if actor.correlation_id in e.get("correlationId", "")]
        subjects = {e.get("actor") for e in mine}
        check("LLMDAP records one authenticated Core subject and the user served",
              len(subjects) == 1 and all(e.get("forSubject") == USER for e in mine), f"{subjects}")

    good = {"authorization": f"Bearer {key}"}
    check("a header naming another subject is refused (AT-11)", status({**good, "x-llmdap-user": USER}) == 401)
    check("a wrong key is refused", status({"authorization": "Bearer llmdap_sk_" + "x" * 43}) == 401)
    secret = os.environ.get(SHARED_SECRET_ENV)  # the gateway's real GATEWAY_TRUST_SECRET, if it has one
    check("the shared secret alone authenticates nothing" + ("" if secret else f" (dummy; set {SHARED_SECRET_ENV})"),
          status({"x-llmdap-auth": secret or "s" * 40}) == 401)
    print(json.dumps({"passed": sum(results.values()), "of": len(results)}))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
