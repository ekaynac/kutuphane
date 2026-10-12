"""`kutuphane` command line. Output is JSON so agents and scripts can drive it (operator principle §2).

Authorization arrives in M1b; until then the CLI is an operator tool on the host.
"""
import argparse
import dataclasses
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import authz, catalog, db, gate
from .policy import EGRESS, PROTECTION_M1, SENSITIVITY, PolicyError, make_policy
from .source import SourceError, read_source


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_migrate(conn, _args) -> int:
    _print({"applied": db.migrate(conn)})
    return 0


def cmd_ingest(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    files = read_source(Path(args.path))
    result = catalog.publish(conn, book=args.book, title=args.title or args.book, files=files, policy=policy,
                             profile=catalog.whole_profile())
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
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        with db.connect() as conn:
            return args.fn(conn, args)
    except (SourceError, PolicyError, authz.AuthzError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
