"""`kutuphane` command line. Output is JSON so agents and scripts can drive it (operator principle §2).

Authorization arrives in M1b; until then the CLI is an operator tool on the host.
"""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

from . import catalog, db
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


def cmd_cat(conn, args) -> int:
    data = catalog.read_file(conn, args.book, args.content_id, args.path)
    if data is None:
        print(f"not found: {args.book}@{args.content_id}:{args.path}", file=sys.stderr)
        return 1
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
    cat = sub.add_parser("cat", help="print one file of a specific content version")
    cat.add_argument("book")
    cat.add_argument("content_id")
    cat.add_argument("path")
    cat.set_defaults(fn=cmd_cat)
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        with db.connect() as conn:
            return args.fn(conn, args)
    except (SourceError, PolicyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
