"""`kutuphane` command line. Output is JSON so agents and scripts can drive it (operator principle §2).

Administrative commands (ingest, grant, delegate) trust the operator on the host; content commands (read, search)
go through the authorization gate. Network surfaces (API, MCP) arrive in M1e and require a verified token.
"""
import argparse
import dataclasses
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import answers, audit, authz, catalog, db, devauth, gate, identity, llmdap, profiles, search
from .policy import EGRESS, PROTECTION_M1, SENSITIVITY, make_policy
from .source import read_source


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_migrate(conn, _args) -> int:
    _print({"applied": db.migrate(conn)})
    return 0


def cmd_ingest(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    files = read_source(Path(args.path))
    result = catalog.publish(conn, book=args.book, title=args.title or args.book, files=files, policy=policy,
                             profile=profiles.spec(args.profile))
    _print(dataclasses.asdict(result))
    return 0


def cmd_show(conn, args) -> int:
    state = catalog.book_state(conn, args.book)
    if state is None:
        print(f"no such book: {args.book}", file=sys.stderr)
        return 1
    _print(state)
    return 0


def cmd_grant(conn, args) -> int:
    if args.mode == "member":
        _print({"id": authz.add_member(conn, args.object, args.subject)})
    else:
        _print({"id": authz.grant(conn, args.object, args.mode, args.subject)})
    return 0


def cmd_revoke(conn, args) -> int:
    _print({"revoked": authz.revoke(conn, args.object, args.mode, args.subject)})
    return 0


def cmd_delegate(conn, args) -> int:
    expires = datetime.now(timezone.utc) + timedelta(hours=args.hours)
    did = authz.delegate(conn, delegator=args.user, delegate_to=args.agent, obj=args.object, mode=args.mode,
                         expires_at=expires, purpose=args.purpose)
    _print({"id": did, "expires_at": expires.isoformat()})
    return 0


def cmd_undelegate(conn, args) -> int:
    _print({"revoked": authz.revoke_delegation(conn, args.id)})
    return 0


def cmd_read(conn, args) -> int:
    try:
        data = gate.deliver_file(conn, gate.Actor(args.principal, args.on_behalf_of), args.book, args.content_id,
                                 args.path)
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    sys.stdout.buffer.write(data)
    return 0


def cmd_search(conn, args) -> int:
    hits = search.search(conn, gate.Actor(args.principal, args.on_behalf_of), args.query, args.k)
    _print([{"citation": h.citation.handle, "page": h.page, "score": round(h.score, 4), "text": h.text}
            for h in hits])
    return 0


def cmd_ask(conn, args) -> int:
    actor = gate.Actor(args.principal, args.on_behalf_of)
    _print({**answers.ask(conn, llmdap.Bridge.from_env(), actor, args.question, model=args.model),
            "correlation_id": actor.correlation_id})
    return 0


def cmd_reopen(conn, args) -> int:
    try:
        _print(answers.reopen(conn, gate.Actor(args.principal, args.on_behalf_of), args.answer_id))
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_dev_keys(_conn, args) -> int:
    _print(devauth.make_keys(Path(args.directory)))
    return 0


def cmd_dev_token(_conn, args) -> int:
    print(devauth.make_token(Path(args.private_key), issuer=args.issuer, audience=args.audience, sub=args.sub,
                             agent=args.agent, act=args.act))
    return 0


def cmd_whoami(_conn, args) -> int:
    token = sys.stdin.readline().strip()  # never on the command line (shell history, process list)
    try:
        actor = identity.Verifier.from_env().verify(token)
    except identity.AuthenticationError as exc:
        print(f"unauthenticated: {exc}", file=sys.stderr)
        return 4
    _print({"principal": actor.principal, "on_behalf_of": actor.on_behalf_of})
    return 0


def cmd_explain(conn, args) -> int:
    records = audit.read_llmdap_export(Path(args.llmdap_export)) if args.llmdap_export else []
    if args.answer:
        _print(audit.explain_answer(conn, args.id, records))
    else:
        _print(audit.explain(conn, args.id, records))
    return 0


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kutuphane")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply database migrations").set_defaults(fn=cmd_migrate)
    ing = sub.add_parser("ingest", help="publish a bundle directory or a single file as a book version")
    ing.add_argument("path")
    ing.add_argument("--book", required=True, help="book slug, e.g. kvkk")
    ing.add_argument("--title")
    ing.add_argument("--sensitivity", required=True, choices=SENSITIVITY)
    ing.add_argument("--egress", required=True, choices=EGRESS)
    ing.add_argument("--protection", required=True, choices=PROTECTION_M1)
    ing.add_argument("--profile", choices=("chunked", "whole"), default="chunked")
    ing.set_defaults(fn=cmd_ingest)
    show = sub.add_parser("show", help="current versions and files of a book")
    show.add_argument("book")
    show.set_defaults(fn=cmd_show)
    for name, fn, text in (("grant", cmd_grant, "give a mode (or role membership) to a subject"),
                           ("revoke", cmd_revoke, "revoke a grant or membership")):
        g = sub.add_parser(name, help=text)
        g.add_argument("object", help="book:<slug>, or role:<name> for membership")
        g.add_argument("mode", choices=(*authz.MODES, "member"))
        g.add_argument("subject", help="user:/agent:/role:<name>#member")
        g.set_defaults(fn=fn)
    dl = sub.add_parser("delegate", help="time-boxed user→agent delegation (one level)")
    dl.add_argument("user")
    dl.add_argument("agent")
    dl.add_argument("object")
    dl.add_argument("mode", choices=authz.MODES)
    dl.add_argument("--hours", type=float, required=True)
    dl.add_argument("--purpose")
    dl.set_defaults(fn=cmd_delegate)
    ud = sub.add_parser("undelegate", help="revoke a delegation")
    ud.add_argument("id", type=int)
    ud.set_defaults(fn=cmd_undelegate)
    rd = sub.add_parser("read", help="read a file through the authorization gate")
    rd.add_argument("principal")
    rd.add_argument("book")
    rd.add_argument("content_id")
    rd.add_argument("path")
    rd.add_argument("--on-behalf-of")
    rd.set_defaults(fn=cmd_read)
    se = sub.add_parser("search", help="search the books the principal may read now")
    se.add_argument("principal")
    se.add_argument("query")
    se.add_argument("--on-behalf-of")
    se.add_argument("-k", type=int, default=search.DEFAULT_K)
    se.set_defaults(fn=cmd_search)
    ak = sub.add_parser("ask", help="answer from the library with citations, through LLMDAP")
    ak.add_argument("principal")
    ak.add_argument("question")
    ak.add_argument("--model", required=True)
    ak.add_argument("--on-behalf-of")
    ak.set_defaults(fn=cmd_ask)
    ro = sub.add_parser("reopen", help="show a stored answer and its evidence again (no model call)")
    ro.add_argument("principal")
    ro.add_argument("answer_id")
    ro.add_argument("--on-behalf-of")
    ro.set_defaults(fn=cmd_reopen)
    dk = sub.add_parser("dev-keys", help="DEVELOPMENT ONLY: signing key + JWKS (needs KUTUPHANE_DEV=1)")
    dk.add_argument("directory")
    dk.set_defaults(fn=cmd_dev_keys, no_db=True)
    dt = sub.add_parser("dev-token", help="DEVELOPMENT ONLY: sign a token (needs KUTUPHANE_DEV=1)")
    dt.add_argument("sub")
    dt.add_argument("--private-key", required=True)
    dt.add_argument("--issuer", required=True)
    dt.add_argument("--audience", default="kutuphane")
    dt.add_argument("--agent", action="store_true", help="the subject is an agent")
    dt.add_argument("--act", help="agent acting for the user `sub` (RFC 8693)")
    dt.set_defaults(fn=cmd_dev_token, no_db=True)
    sub.add_parser("whoami", help="verify an access token read from stdin").set_defaults(fn=cmd_whoami)
    ex = sub.add_parser("explain", help="unified audit for a correlation id (or, with --answer, an answer id)")
    ex.add_argument("id")
    ex.add_argument("--answer", action="store_true", help="the id is an answer id")
    ex.add_argument("--llmdap-export", help="JSONL from llmdap-audit-export")
    ex.set_defaults(fn=cmd_explain)
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if getattr(args, "no_db", False):
            return args.fn(None, args)
        with db.connect() as conn:
            return args.fn(conn, args)
    except (ValueError, OSError, RuntimeError) as exc:  # SourceError, PolicyError, AuthzError are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
