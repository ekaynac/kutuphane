"""`kutuphane` command line. Output is JSON so agents and scripts can drive it (operator principle §2).

Administrative commands (ingest, grant, delegate) trust the operator on the host; content commands (read, search)
go through the authorization gate. Network surfaces (API, MCP) arrive in M1e and require a verified token.
"""
import argparse
import dataclasses
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (answers, audit, authz, catalog, coderepo, db, decisions, devauth, gate, identity, kstd, llmdap, notes,
               packages, profiles, search, retrieval, signing, vectors)
from .policy import EGRESS, PROTECTION_M1, SENSITIVITY, make_policy
from .source import AcceptedFinding, read_source


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_migrate(conn, _args) -> int:
    _print({"applied": db.migrate(conn)})
    return 0


def cmd_ingest(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    files = read_source(Path(args.path), _accepted(args))
    embedder, settings = _indexing()  # a configuration error stops here, before anything is published
    result = catalog.publish(conn, book=args.book, title=args.title or args.book, files=files, policy=policy,
                             profile=profiles.spec(args.profile))
    for a in result.accepted_findings:  # on record in the publication; say so where a person looks
        print(f"accepted finding (reviewed exception): {a['path']}@sha256:{a['sha256']}:{a['rule']}", file=sys.stderr)
    return _published_then_index(conn, result, embedder, settings)


def _warn_quarantined(result: catalog.Published) -> None:
    """Quarantined files are published (stored, listed) but not searchable; say so where a person looks."""
    for q in result.quarantined:
        print(f"quarantined (stored, not indexed): {q['path']}: {q['reason']}", file=sys.stderr)


INDEX_INCOMPLETE = 3  # exit code: the version is published (live), but some of its passages have no vector yet


def _indexing(**overrides) -> tuple[llmdap.Routed | None, vectors.Settings]:
    """The embeddings route (None: search stays full text) and the index settings (KUTUPHANE_INDEX_*, options)."""
    return llmdap.Routed.from_env(llmdap.EMBED_ENV), vectors.Settings.from_env(**overrides)


def _index_problem(report: dict) -> str | None:
    if "index_error" in report:
        return report["index_error"]
    if report.get("failed") or report.get("not_attempted"):
        return f"{len(report['failed'])} passages failed, {report['not_attempted']} not attempted"
    return None


def _published_then_index(conn, published: catalog.Published, embedder: llmdap.Routed | None,
                          settings: vectors.Settings) -> int:
    """A published version is live; indexing comes after it and cannot undo it (G12). The publication result is
    always printed; an index failure is reported with it, and the exit code is then INDEX_INCOMPLETE."""
    _warn_quarantined(published)
    report = {}
    if embedder:
        try:
            report = vectors.index(conn, embedder, published.book, settings).report()
        except (ValueError, OSError, RuntimeError) as exc:  # EgressError is a RuntimeError
            report = {"index_error": str(exc)}
    _print({**dataclasses.asdict(published), **report})
    problem = _index_problem(report)
    if problem:
        print(f"error: {published.book} {published.content_id} is published and live, but its index is incomplete: "
              f"{problem}; `kutuphane index {published.book}` adds the missing vectors", file=sys.stderr)
        return INDEX_INCOMPLETE
    return 0


def cmd_index(conn, args) -> int:
    embedder, settings = _indexing(batch=args.batch, batch_chars=args.batch_chars, concurrency=args.concurrency)
    if embedder is None:
        print(f"no embeddings route: set {llmdap.EMBED_ENV['route']}", file=sys.stderr)
        return 1
    report = vectors.index(conn, embedder, args.book, settings).report()
    _print({"book": args.book, **report})
    problem = _index_problem(report)
    if problem:
        print(f"error: index of {args.book} is incomplete: {problem}; run `kutuphane index {args.book}` again",
              file=sys.stderr)
        return INDEX_INCOMPLETE
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


def cmd_repo_add(conn, args) -> int:
    _print(coderepo.add(conn, args.book, args.slug, args.git_dir, args.refs, by=args.by))
    return 0


def cmd_repo_remove(conn, args) -> int:
    _print({"removed": coderepo.remove(conn, args.book, args.slug)})
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


def _scope_options(parser) -> None:
    parser.add_argument("--book", action="append", help="only this book (repeatable)")
    parser.add_argument("--path", help="only files whose path starts with this prefix (e.g. data/)")
    parser.add_argument("--origin", action="append", choices=kstd.ORIGINS, help="only files with this kstd origin "
                        "(repeatable; a book without kstd.yaml counts as unknown)")
    parser.add_argument("--current-only", action="store_true", help="only files whose kstd validity includes now")


def _scope(args) -> search.Scope:
    return search.Scope.of(args.book, args.path, args.origin, args.current_only)


def cmd_search(conn, args) -> int:
    actor = gate.Actor(args.principal, args.on_behalf_of)
    hits = retrieval.retrieve(conn, actor, args.query, args.k, retrieval.Stages.from_env(), _scope(args))
    rights = kstd.Rights(conn)
    _print([{"citation": h.citation.handle, "page": h.page, "line": h.line, "score": round(h.score, 4),
             "text": h.text, "item": rights.info(h.citation.book, h.citation.content_id, h.citation.path)}
            for h in hits])
    return 0


def _accepted(args) -> list[AcceptedFinding]:
    return [AcceptedFinding.parse(spec) for spec in args.accept_finding]


def _accept_finding_option(parser, effect: str) -> None:
    parser.add_argument("--accept-finding", action="append", default=[], metavar="PATH@sha256:DIGEST:RULE",
                        help="accept one reviewed credential-scan finding: that rule, in exactly that file content "
                             f"(sha256 of the file); repeatable; a changed file needs a new review; {effect}")


def cmd_kstd_init(_conn, args) -> int:
    """Write a starting kstd.yaml that lists every file with its digest; all rights start as unknown."""
    root = Path(args.path)
    target = root / kstd.MANIFEST
    files = read_source(root, _accepted(args))  # the same reviewed exceptions that ingest will need
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)  # never overwrite a curated manifest
    with os.fdopen(fd, "w") as f:
        f.write(kstd.init(files, args.issuer))
    print(f"wrote {target}: set the license, ai_use and personal_data, then run `kutuphane kstd-check {root}`")
    return 0


def cmd_kstd_check(_conn, args) -> int:
    files = read_source(Path(args.path), _accepted(args))
    found = [f for f in files if f.path == kstd.MANIFEST]
    if not found:
        print(f"no {kstd.MANIFEST} in {args.path}", file=sys.stderr)
        return 1
    errors, warnings = kstd.check(kstd.parse(found[0].data), {f.path: f.sha256 for f in files})
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print("kstd L0: " + ("FAIL" if errors else "PASS") + f" ({len(files) - 1} files)")
    return 1 if errors else 0


def cmd_ask(conn, args) -> int:
    actor = gate.Actor(args.principal, args.on_behalf_of)
    _print({**answers.ask(conn, llmdap.Bridge.from_env(), actor, args.question, model=args.model,
                          stages=retrieval.Stages.from_env(answer_model=args.model), scope=_scope(args)),
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
                             agent=args.agent, act=args.act, client_id=args.client_id))
    return 0


def cmd_keygen(_conn, args) -> int:
    _print(signing.generate(Path(args.private_key)))
    return 0


def cmd_trust(conn, args) -> int:
    fp = packages.trust(conn, Path(args.public_key).read_bytes(), expected_fingerprint=args.fingerprint,
                        name=args.name, by=args.by)
    _print({"trusted": fp})
    return 0


def cmd_untrust(conn, args) -> int:
    _print({"revoked": packages.revoke_key(conn, args.fingerprint)})
    return 0


def cmd_export(conn, args) -> int:
    data = packages.export(conn, args.book, signing.load_private(), legal_basis=args.legal_basis)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    _print({"package": args.out, "bytes": len(data)})
    return 0


def cmd_receive(conn, args) -> int:
    with open(args.package, "rb") as f:  # at most one byte past the limit: an oversized file is refused, not loaded
        data = f.read(packages.MAX_PACKAGE_BYTES + 1)
    result = packages.receive(conn, data)
    _print(result)
    return 0 if result["status"] == "verified" else 5


def cmd_approve(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    embedder, settings = _indexing()
    published = packages.approve(conn, args.id, by=args.by, policy=policy, profile=args.profile)
    return _published_then_index(conn, published, embedder, settings)


def cmd_reject(conn, args) -> int:
    _print({"rejected": packages.reject(conn, args.id, by=args.by, reason=args.reason)})
    return 0


def cmd_imports(conn, _args) -> int:
    rows = conn.execute("SELECT id, received_at, status, issuer, book, sequence, reasons, findings, diff, decided_by "
                        "FROM package_import ORDER BY id DESC LIMIT 50").fetchall()
    keys = ("id", "received_at", "status", "issuer", "book", "sequence", "reasons", "findings", "diff", "decided_by")
    _print([{**dict(zip(keys, r)), "received_at": r[1].isoformat()} for r in rows])
    return 0


def cmd_journal_create(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    _print(notes.create_journal(conn, book=args.book, title=args.title or args.book, search=args.search == "y",
                                ai_input=args.ai_input == "y", train=args.train == "y", policy=policy, by=args.by))
    return 0


def cmd_journal_restrict(conn, args) -> int:
    _print(notes.restrict_journal(conn, args.book, search=args.no_search, ai_input=args.no_ai_input,
                                  train=args.no_train))
    return 0


def cmd_decisions_export(conn, args) -> int:
    """docs/24 §21.4: JSONL decision records through the read gate; text only with ai_input and train."""
    if os.path.lexists(args.out):
        raise ValueError(f"{args.out} exists; the export writes a new file")
    try:
        records, summary = decisions.export(conn, gate.Actor(args.principal, args.on_behalf_of), args.book)
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)  # it can hold note text
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in records)
    _print({"out": args.out, **summary})
    return 0


def cmd_note_standing(conn, args) -> int:
    """The curator act (docs/24 §8.2): connected with KUTUPHANE_CURATOR_DSN, the only credential that can write
    Standing. The CLI trusts its operator and records the curator named here, who must hold `curate` now."""
    try:
        _print(notes.set_standing(conn, args.ref, args.value, curator=args.curator, reason=args.reason))
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_note_rollback(conn, args) -> int:
    """Rollback along `derived_from` (docs/24 §20): the curator act on the root, a system retirement of every note
    derived from it, and the report of the reads, answers and exports that used them."""
    try:
        _print(notes.rollback(conn, args.ref, curator=args.curator, reason=args.reason))
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
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
    _accept_finding_option(ing, "recorded in the publication")
    ing.set_defaults(fn=cmd_ingest)
    ix = sub.add_parser("index", help="give a book's current chunks a vector: copy unchanged ones, embed the rest "
                                      "(through LLMDAP)")
    ix.add_argument("book")
    ix.add_argument("--batch", type=int, help=f"passages per embedding call (env {vectors.SETTINGS_ENV['batch']}, "
                                              f"default {vectors.Settings.batch})")
    ix.add_argument("--batch-chars", type=int, help="embedded characters per call "
                                                    f"(env {vectors.SETTINGS_ENV['batch_chars']}, "
                                                    f"default {vectors.Settings.batch_chars})")
    ix.add_argument("--concurrency", type=int, help="embedding calls in flight "
                                                    f"(env {vectors.SETTINGS_ENV['concurrency']}, "
                                                    f"default {vectors.Settings.concurrency})")
    ix.set_defaults(fn=cmd_index)
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
    rp = sub.add_parser("repo", help="code repositories of a journal (docs/24 §10.2); Kütüphane never fetches")
    rsub = rp.add_subparsers(dest="repo_cmd", required=True)
    ra = rsub.add_parser("add", help="register a bare mirror inside KUTUPHANE_REPO_ROOTS for a journal")
    ra.add_argument("book")
    ra.add_argument("slug")
    ra.add_argument("git_dir", help="absolute path of the bare repository (no symlink)")
    ra.add_argument("--ref", dest="refs", action="append", required=True,
                    help="a ref pattern whose commits can be cited, e.g. 'refs/heads/*' (repeatable, at most 10)")
    ra.add_argument("--by", required=True, help="the administrator, e.g. user:admin")
    ra.set_defaults(fn=cmd_repo_add)
    rr = rsub.add_parser("remove", help="stop new scopes and citations; verification becomes unverifiable")
    rr.add_argument("book")
    rr.add_argument("slug")
    rr.set_defaults(fn=cmd_repo_remove)
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
    _scope_options(se)
    se.set_defaults(fn=cmd_search)
    ak = sub.add_parser("ask", help="answer from the library with citations, through LLMDAP")
    ak.add_argument("principal")
    ak.add_argument("question")
    ak.add_argument("--model", required=True)
    ak.add_argument("--on-behalf-of")
    _scope_options(ak)
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
    dt.add_argument("--client-id", help="the OAuth client the token is issued to (recorded only)")
    dt.set_defaults(fn=cmd_dev_token, no_db=True)
    kg = sub.add_parser("keygen", help="create this installation's Ed25519 package signing key")
    kg.add_argument("private_key")
    kg.set_defaults(fn=cmd_keygen, no_db=True)
    tr = sub.add_parser("trust", help="trust a signing key; give the fingerprint you confirmed out of band")
    tr.add_argument("public_key")
    tr.add_argument("--fingerprint", required=True)
    tr.add_argument("--name", required=True)
    tr.add_argument("--by", required=True, help="the administrator, e.g. user:admin")
    tr.set_defaults(fn=cmd_trust)
    ut = sub.add_parser("untrust", help="revoke a trusted signing key")
    ut.add_argument("fingerprint")
    ut.set_defaults(fn=cmd_untrust)
    ex_ = sub.add_parser("export", help="write a signed package of a book's current version (KUTUPHANE_SIGNING_KEY)")
    ex_.add_argument("book")
    ex_.add_argument("--out", required=True)
    ex_.add_argument("--legal-basis", help="DPV codes, e.g. eu-gdpr:A6-1-b (several: space separated); required "
                     "when kstd.yaml marks files as personal data yes/unknown; "
                     "recorded in the signed package")
    ex_.set_defaults(fn=cmd_export)
    rc = sub.add_parser("receive", help="quarantine and verify a package; nothing is published")
    rc.add_argument("package")
    rc.set_defaults(fn=cmd_receive)
    ap_ = sub.add_parser("approve-import", help="publish a verified package with THIS installation's policy")
    ap_.add_argument("id", type=int)
    ap_.add_argument("--by", required=True)
    ap_.add_argument("--sensitivity", required=True, choices=SENSITIVITY)
    ap_.add_argument("--egress", required=True, choices=EGRESS)
    ap_.add_argument("--protection", required=True, choices=PROTECTION_M1)
    ap_.add_argument("--profile", choices=("chunked", "whole"), default="chunked")
    ap_.set_defaults(fn=cmd_approve)
    rj = sub.add_parser("reject-import", help="refuse a verified package (kept on record)")
    rj.add_argument("id", type=int)
    rj.add_argument("--by", required=True)
    rj.add_argument("--reason", required=True)
    rj.set_defaults(fn=cmd_reject)
    sub.add_parser("imports", help="received packages and their verdicts").set_defaults(fn=cmd_imports)
    ki = sub.add_parser("kstd-init", help="write a starting kstd.yaml for a folder (no database)")
    ki.add_argument("path")
    ki.add_argument("--issuer", required=True, help="who answers for this folder, e.g. 'ACME <kb@acme.example>'")
    _accept_finding_option(ki, "give the same acceptances to ingest")
    ki.set_defaults(fn=cmd_kstd_init, no_db=True)
    kc = sub.add_parser("kstd-check", help="validate a folder's kstd.yaml: digests, SPDX ids, terms (no database)")
    kc.add_argument("path")
    _accept_finding_option(kc, "give the same acceptances to ingest")
    kc.set_defaults(fn=cmd_kstd_check, no_db=True)
    sub.add_parser("whoami", help="verify an access token read from stdin").set_defaults(fn=cmd_whoami)
    ex = sub.add_parser("explain", help="unified audit for a correlation id (or, with --answer, an answer id)")
    ex.add_argument("id")
    ex.add_argument("--answer", action="store_true", help="the id is an answer id")
    ex.add_argument("--llmdap-export", help="JSONL from llmdap-audit-export")
    ex.set_defaults(fn=cmd_explain)
    jr = sub.add_parser("journal", help="journals: books whose items are agent notes (docs/24)")
    jsub = jr.add_subparsers(dest="journal_cmd", required=True)
    jc = jsub.add_parser("create", help="create a journal (a new book); search and AI input must both be stated")
    jc.add_argument("book")
    jc.add_argument("--title")
    jc.add_argument("--search", required=True, choices=("y", "n"), help="notes get full text and vectors")
    jc.add_argument("--ai-input", required=True, choices=("y", "n"), help="note text may be sent to models")
    jc.add_argument("--train", choices=("y", "n"), default="n",
                    help="note text may be exported as training data (default n: missing = deny)")
    jc.add_argument("--sensitivity", required=True, choices=SENSITIVITY)
    jc.add_argument("--egress", required=True, choices=EGRESS)
    jc.add_argument("--protection", required=True, choices=PROTECTION_M1)
    jc.add_argument("--by", required=True, help="the administrator, e.g. user:admin")
    jc.set_defaults(fn=cmd_journal_create)
    jt = jsub.add_parser("restrict", help="tighten a journal (loosening needs a new journal)")
    jt.add_argument("book")
    jt.add_argument("--no-search", action="store_true")
    jt.add_argument("--no-ai-input", action="store_true")
    jt.add_argument("--no-train", action="store_true")
    jt.set_defaults(fn=cmd_journal_restrict)
    nt = sub.add_parser("note", help="notes (curation needs KUTUPHANE_CURATOR_DSN)")
    nsub = nt.add_subparsers(dest="note_cmd", required=True)
    ns = nsub.add_parser("standing", help="set the Standing of a note as a curator")
    ns.add_argument("ref", help="<book>@nt_<64 hex>")
    ns.add_argument("value", choices=notes.STANDINGS)
    ns.add_argument("--curator", required=True, help="user:<name>, who holds curate on the book")
    ns.add_argument("--reason", required=True)
    ns.set_defaults(fn=cmd_note_standing, curator_db=True)
    nr = nsub.add_parser("rollback", help="retire a note and every note derived from it; report who used them")
    nr.add_argument("ref", help="<book>@nt_<64 hex>")
    nr.add_argument("--curator", required=True, help="user:<name>, who holds curate on the book of the note")
    nr.add_argument("--reason", required=True)
    nr.set_defaults(fn=cmd_note_rollback, curator_db=True)
    dc = sub.add_parser("decisions", help="decision records of journals (docs/24 §21)")
    dcsub = dc.add_subparsers(dest="decisions_cmd", required=True)
    de = dcsub.add_parser("export", help="write JSONL decision records the principal may read; text only with "
                                         "ai_input and train")
    de.add_argument("principal")
    de.add_argument("--out", required=True, help="a new file")
    de.add_argument("--book", action="append", help="only this journal (repeatable); default: every readable one")
    de.add_argument("--on-behalf-of")
    de.set_defaults(fn=cmd_decisions_export)
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if getattr(args, "no_db", False):
            return args.fn(None, args)
        if getattr(args, "curator_db", False) and not os.environ.get(db.CURATOR_DSN_ENV):
            print(f"error: {db.CURATOR_DSN_ENV} is not set (the curator credential)", file=sys.stderr)
            return 2
        # The owner credential writes Standing and applies migrations; without it, migrate uses KUTUPHANE_DSN
        # (a single-role development database).
        owner = getattr(args, "curator_db", False) or args.fn is cmd_migrate
        with db.connect(os.environ.get(db.CURATOR_DSN_ENV) if owner else None) as conn:
            return args.fn(conn, args)
    except (ValueError, OSError, RuntimeError) as exc:  # SourceError, PolicyError, AuthzError are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
