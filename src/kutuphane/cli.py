"""`kutuphane` command line. Output is JSON so agents and scripts can drive it (operator principle §2).

Administrative commands (ingest, grant, delegate) trust the operator on the host; content commands (read, search)
go through the authorization gate. Network surfaces (API, MCP) arrive in M1e and require a verified token.
"""
import argparse
import dataclasses
import getpass
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import (answers, audit, authz, catalog, coderepo, curatorqueue, datascan, db, decisions, devauth, gate,
               gitorigin, identity, kstd, llmdap, noteimport, notes, packages, passagemap, passkey, profiles, quotes,
               search, retrieval, signing, skillscan, vectors)
from .policy import EGRESS, PROTECTION_M1, SENSITIVITY, make_policy
from .source import AcceptedFinding, read_source


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_migrate(conn, _args) -> int:
    _print({"applied": db.migrate(conn)})
    return 0


def cmd_ingest(conn, args) -> int:
    policy = make_policy(sensitivity=args.sensitivity, egress=args.egress, protection=args.protection)
    files = read_source(Path(args.path), _accepted(args), _names(args))
    embedder, settings = _indexing()  # a configuration error stops here, before anything is published
    result = catalog.publish(conn, book=args.book, title=args.title or args.book, files=files, policy=policy,
                             profile=profiles.spec(args.profile), approved_by=args.by or f"user:{getpass.getuser()}")
    for a in result.accepted_findings:  # on record in the publication; say so where a person looks
        print(f"accepted finding (reviewed exception): {a['path']}@sha256:{a['sha256']}:{a['rule']}", file=sys.stderr)
    print(_report_data_findings(result.data_findings), file=sys.stderr)
    return _published_then_index(conn, result, embedder, settings)


def _warn_quarantined(result: catalog.Published) -> None:
    """Quarantined files are published (stored, listed) but not searchable; say so where a person looks."""
    for q in result.quarantined:
        print(f"quarantined (stored, not indexed): {q['path']}: {q['reason']}", file=sys.stderr)


def _warn_skills(scans: list[dict]) -> None:
    """A blocked skill is published but refused to agents (D71); say so where a person looks."""
    for s in scans:
        if s["blocking"]:
            verdict = f"{s['recommendation']} {s['score']}, coverage {s['completeness']}" if s["status"] == "scanned" \
                else f"scan failed: {s['reason']}"
            if s.get("carried_from"):
                verdict += f", carried from scan record {s['carried_from']}: the same skill bytes"
            print(f"skill blocked for agents ({verdict}): {s['skill_path']}; `kutuphane skill show` lists the "
                  "findings, a curator lifts the block with `kutuphane skill clear`", file=sys.stderr)
        elif s["status"] == "not_scanned":
            print(f"skill not scanned: {s['skill_path']}: {s['reason']}", file=sys.stderr)


def _warn_stale(counts: dict) -> None:
    """A cited or linked passage with no successor in the new version stays on record as `stale` (#140)."""
    if counts.get("none"):
        print(f"{counts['none']} cited or linked passages of earlier versions have no successor in this version: "
              "notes show them as stale", file=sys.stderr)


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
    _warn_skills(published.skill_scans)
    _warn_stale(published.passage_map)
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


def cmd_reindex_map(conn, args) -> int:
    """#140: map the cited and linked passages of earlier versions of a book to its current version (idempotent). For
    books published before migration 040; a publication maps its book itself."""
    with conn.transaction():
        if not conn.execute("SELECT 1 FROM book WHERE slug = %s FOR UPDATE", (args.book,)).fetchone():
            print(f"no such book: {args.book}", file=sys.stderr)
            return 1
        counts = passagemap.map_book(conn, args.book, write=not args.dry_run)
    _print({**counts, "dry_run": args.dry_run})
    _warn_stale(counts)
    return 0


def cmd_grant(conn, args) -> int:
    if args.mode == "member":
        _print({"id": authz.add_member(conn, args.object, args.subject)})
    else:
        if args.mode == "curate":
            identity.refuse_curate(args.subject)
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
    parser.add_argument("--platform", help="request context: leave out files whose kstd applies_to names other "
                        "platforms")
    parser.add_argument("--version", help="request context: leave out files whose kstd applies_to version range "
                        "excludes this version (e.g. 7.0.3)")


def _scope(args) -> search.Scope:
    context = {k: v for k, v in (("platform", args.platform), ("version", args.version)) if v is not None}
    return search.Scope.of(args.book, args.path, args.origin, args.current_only, context or None)


def cmd_search(conn, args) -> int:
    actor = gate.Actor(args.principal, args.on_behalf_of)
    scope = _scope(args)
    hits, found = quotes.quoted(conn, actor, retrieval.retrieve(conn, actor, args.query, args.k,
                                                                retrieval.Stages.from_env(), scope), scope)
    rights = kstd.Rights(conn, scope.context)
    _print([{"citation": h.citation.handle, "page": h.page, "line": h.line, "score": round(h.score, 4),
             "text": h.text, "item": rights.info(h.citation.book, h.citation.content_id, h.citation.path),
             "quoted_records": quotes.handles(found, h.citation)}
            for h in hits])
    return 0


def _accepted(args) -> list[AcceptedFinding]:
    return [AcceptedFinding.parse(spec) for spec in args.accept_finding]


def _names(args):
    return datascan.load_names(Path(args.deny_names)) if args.deny_names else None


def _report_data_findings(found: list[dict]) -> str:
    """Print each open personal-data finding to stderr; return the summary line. `found`: catalog.data_findings of
    the read_source scan, so ingest, kstd-init and kstd-check report one scan the same way (G35)."""
    counts = {}
    for d in found:
        where = " of the extracted text" if d.get("text") else ""
        for line in d["lines"]:
            print(f"personal-data finding (labelling, not refused): {d['path']} line {line}{where} ({d['rule']})",
                  file=sys.stderr)
        counts[d["rule"]] = counts.get(d["rule"], 0) + len(d["lines"])
    flagged = len({d["path"] for d in found})
    return "personal-data findings: " + (", ".join(f"{r} {n}" for r, n in sorted(counts.items()))
                                         + f" ({flagged} file{'s' if flagged != 1 else ''})" if counts else "none")


def _scan_options(parser, effect: str) -> None:
    parser.add_argument("--accept-finding", action="append", default=[], metavar="PATH@sha256:DIGEST:RULE",
                        help="accept one reviewed credential or personal-data finding: that rule, in exactly that file "
                             f"content (sha256 of the file); repeatable; a changed file needs a new review; {effect}")
    parser.add_argument("--deny-names", metavar="FILE",
                        help="a file of names (customers, sites), one per line: each match is a personal-data "
                             "finding (listed-name); never shown, never stored")


def cmd_kstd_init(_conn, args) -> int:
    """Write a starting kstd.yaml that lists every file with its digest; all rights start as unknown. With
    --source-repo, the origin of each file is proposed from the commit trailers of a local repository (G34);
    personal-data findings propose `personal_data: unknown` for their file (G35)."""
    root = Path(args.path)
    target = root / kstd.MANIFEST
    if args.commit and not args.source_repo:
        raise ValueError("--commit needs --source-repo")
    files = read_source(root, _accepted(args), _names(args))  # the same reviewed exceptions that ingest will need
    proposals = gitorigin.propose(args.source_repo, files, args.commit or "HEAD") if args.source_repo else None
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)  # never overwrite a curated manifest
    with os.fdopen(fd, "w") as f:
        f.write(kstd.init(files, args.issuer, proposals=proposals))
    summary = _report_data_findings(catalog.data_findings(files))
    print(f"wrote {target}: set the license, ai_use and personal_data, then run `kutuphane kstd-check {root}`")
    if proposals is not None:
        origins = [p.origin for p in proposals.items.values()]
        print(f"origin proposals from git: model {origins.count('model')}, unknown {origins.count('unknown')} "
              f"(at {proposals.commit}); a proposal is not authority: check each one in {kstd.MANIFEST}")
    print(summary + ("; their files propose personal_data: unknown" if any(f.data_findings for f in files) else ""))
    return 0


def cmd_kstd_check(_conn, args) -> int:
    files = read_source(Path(args.path), _accepted(args), _names(args))
    found = [f for f in files if f.path == kstd.MANIFEST]
    if not found:
        print(f"no {kstd.MANIFEST} in {args.path}", file=sys.stderr)
        return 1
    errors, warnings = kstd.check(kstd.parse(found[0].data), {f.path: f.sha256 for f in files})
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    print(_report_data_findings(catalog.data_findings(files)))  # a labelling question: never a FAIL
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
    published = packages.approve(conn, args.id, by=args.by, policy=policy, profile=args.profile,
                                 accept=_accepted(args))
    return _published_then_index(conn, published, embedder, settings)


def cmd_reject(conn, args) -> int:
    _print({"rejected": packages.reject(conn, args.id, by=args.by, reason=args.reason)})
    return 0


def cmd_imports(conn, _args) -> int:
    rows = conn.execute("SELECT id, received_at, status, issuer, book, sequence, reasons, findings, diff, decided_by, "
                        "submitted_by, submitted_for, submitted_channel "
                        "FROM package_import ORDER BY id DESC LIMIT 50").fetchall()
    keys = ("id", "received_at", "status", "issuer", "book", "sequence", "reasons", "findings", "diff", "decided_by",
            "submitted_by", "submitted_for", "submitted_channel")
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


def cmd_note_import(conn, args) -> int:
    """Bulk import (docs/24 §23): JSONL records of an orchestrator's local memory become `pending` notes of a
    journal, written as the principal named by --by, who must hold `propose` on the journal now."""
    lines = noteimport.read(args.file)
    embedder = llmdap.Routed.from_env(llmdap.EMBED_ENV)  # a configuration error stops here, before any write
    try:
        _print(noteimport.run(conn, gate.Actor(args.by), args.book, lines, embedder))
    except (gate.Denied, gate.NotFound) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_skill_show(conn, args) -> int:
    try:
        _print(skillscan.show(conn, args.book))
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_skill_rescan(conn, args) -> int:
    try:
        scans = skillscan.rescan(conn, args.book)
    except LookupError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    _warn_skills(scans)
    _print(scans)
    return 0


def cmd_skill_clear(conn, args) -> int:
    """The curator act (docs/24 §22): connected with KUTUPHANE_CURATOR_DSN, the only credential that can write a
    clearance. The CLI records the curator named here, who must hold `curate` on the book now."""
    try:
        _print(skillscan.clear(conn, args.book, args.path, curator=args.curator, reason=args.reason))
    except (PermissionError, LookupError) as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    return 0


def cmd_curator_enroll(conn, args) -> int:
    """docs/25 §3.4: a one-time code (15 minutes, one passkey) for a person, as a URL fragment of curator web. The
    owner credential is the root of trust: only it makes a person and an enrollment."""
    cfg = passkey.Config.from_env()
    eid, code = passkey.enroll(conn, args.principal, created_by=os.environ.get("USER") or "operator")
    expires = conn.execute("SELECT expires_at FROM curator_enrollment WHERE id = %s", (eid,)).fetchone()[0]
    _print({"enrollment": eid, "principal": args.principal, "url": f"{cfg.origin}/enroll#{code}",
            "expires_at": expires.isoformat(),
            "next": "open the URL on the person's phone; then check `kutuphane curator passkeys`"})
    return 0


def cmd_curator_passkeys(conn, args) -> int:
    rows = conn.execute(
        "SELECT p.credential_id, p.principal, p.backup_eligible, p.created_at, p.revoked_at, max(a.at) "
        "FROM passkey p LEFT JOIN curator_act a ON a.credential_id = p.credential_id "
        "WHERE %(p)s::text IS NULL OR p.principal = %(p)s GROUP BY p.credential_id ORDER BY p.created_at",
        {"p": args.principal}).fetchall()
    _print([{"id": passkey.b64u(bytes(c)), "principal": p, "synced": be, "created_at": ca.isoformat(),
             "revoked_at": ra.isoformat() if ra else None, "last_act": la.isoformat() if la else None}
            for c, p, be, ca, ra, la in rows])
    return 0


def cmd_curator_revoke_passkey(conn, args) -> int:
    """A revoked passkey signs nothing, and its sessions end now (docs/25 §3.4)."""
    cred = passkey.unb64u(args.id)
    with conn.transaction():
        done = conn.execute("UPDATE passkey SET revoked_at = clock_timestamp() WHERE credential_id = %s "
                            "AND revoked_at IS NULL RETURNING principal", (cred,)).fetchone()
        ended = conn.execute("UPDATE curator_session SET ended_at = clock_timestamp() WHERE credential_id = %s "
                             "AND ended_at IS NULL", (cred,)).rowcount if done else 0
    if done is None:
        print("error: no live passkey with this id", file=sys.stderr)
        return 2
    _print({"revoked": args.id, "principal": done[0], "sessions_ended": ended})
    return 0


def cmd_curator_end_sessions(conn, args) -> int:
    """End every live session of a person (a stolen cookie; the passkeys stay)."""
    ended = conn.execute("UPDATE curator_session SET ended_at = clock_timestamp() WHERE principal = %s "
                         "AND ended_at IS NULL AND clock_timestamp() < expires_at", (args.principal,)).rowcount
    _print({"principal": args.principal, "ended": ended})
    return 0


def cmd_curator_cancel_enrollment(conn, args) -> int:
    """A leaked enrollment code: cancel it before it registers a passkey; its session ends."""
    with conn.transaction():
        done = conn.execute("UPDATE curator_enrollment e SET cancelled_at = clock_timestamp() WHERE id = %s "
                            "AND cancelled_at IS NULL AND NOT EXISTS (SELECT 1 FROM passkey p WHERE p.enrollment = e.id) "
                            "RETURNING principal", (args.id,)).fetchone()
        ended = conn.execute("UPDATE curator_session SET ended_at = clock_timestamp() WHERE enrollment = %s "
                             "AND ended_at IS NULL", (args.id,)).rowcount if done else 0
    if done is None:
        print("error: no open enrollment with this id (used: revoke its passkey instead)", file=sys.stderr)
        return 2
    _print({"cancelled": args.id, "principal": done[0], "sessions_ended": ended})
    return 0


def cmd_curator_verify_acts(conn, args) -> int:
    """docs/25 §5.6: every stored act again, offline. Exit 1 when a problem is found."""
    out = passkey.verify_acts(conn, passkey.Config.from_env(), since=args.since)
    _print(out)
    return 1 if out["problems"] else 0


def cmd_curator_queue(conn, args) -> int:
    """docs/25 §6 (G36): the queue of a curator in risk order, as curator web shows it (no suggestion, no sample
    mark). Read only; the view is logged as `curate_view` for the named curator, as on the page."""
    try:
        with conn.transaction():
            _print(curatorqueue.queue(conn, args.curator, w=args.as_of, cursor=args.cursor, limit=args.limit,
                                      book=args.book))
    except gate.Denied as exc:
        print(f"denied: {exc}", file=sys.stderr)
        return 3
    return 0


def _when(text: str) -> datetime:
    """An ISO date or time; with no zone, UTC."""
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def cmd_curator_report(conn, args) -> int:
    """docs/25 §6.7: curator seconds per approved note, the share still pending after 7 days, who decided, and the
    delegations. Read only."""
    _print(curatorqueue.report(conn, _when(args.start), _when(args.end)))
    return 0


def cmd_curator_web(_conn, args) -> int:
    import uvicorn
    uvicorn.run("kutuphane.curatorweb:app_from_env", factory=True, host=args.host, port=args.port)
    return 0


def cmd_decider_run(_conn, args) -> int:
    """docs/25 §8.3: one run of the decider runner with its own role (KUTUPHANE_DECIDER_DSN) and LLMDAP subject key.
    Shadow mode writes suggestions only (the first decider, §14 Q9)."""
    from . import decider
    spec = decider.load_spec(args.spec)
    bridge = decider.bridge_of(spec)
    dsn = os.environ.get(decider.DSN_ENV)
    if not dsn:
        print(f"error: {decider.DSN_ENV} is not set (the kutuphane_decider role)", file=sys.stderr)
        return 2
    with db.connect(dsn) as conn:
        _print(decider.run(conn, spec, bridge, books=decider.books_from_env(), shadow=args.shadow,
                           limit=args.limit))
    return 0


def cmd_decider_spec(_conn, args) -> int:
    """The decider id and spec digest that a `delegate` act names, and the runner code digest that it includes."""
    from . import decider
    spec = decider.load_spec(args.spec)
    _print({"decider": spec.decider, "approver": spec.approver, "spec_sha256": spec.sha256.hex(),
            "runner_code": decider.runner_code()})
    return 0


def cmd_delegation_list(conn, args) -> int:
    from . import delegation
    _print(delegation.list_(conn, [args.book] if args.book else None))
    return 0


def cmd_delegation_report(conn, args) -> int:
    from . import delegation
    try:
        _print(delegation.report(conn, args.id))
    except gate.NotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


def cmd_delegation_agreement(conn, args) -> int:
    from . import decider, delegation
    spec = decider.load_spec(args.spec)
    _print({"decider": spec.decider, "spec_sha256": spec.sha256.hex(), "book": args.book, "kind": args.kind,
            "min_shadow": delegation.min_shadow(),
            "agreement": delegation.agreement(conn, spec.decider, spec.sha256, args.book, args.kind)})
    return 0


def cmd_delegation_end(conn, args) -> int:
    """docs/25 §8.2: a curator ends a delegation (owner credential; ending only tightens). An end is final."""
    from . import delegation
    try:
        _print(delegation.end(conn, args.id, curator=args.curator, reason=args.reason))
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
    ing.add_argument("--by", help="who publishes, recorded in the publication (default: user:<the CLI user>)")
    _scan_options(ing, "recorded in the publication")
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
    rm = sub.add_parser("reindex-map", help="map the cited and linked passages of earlier versions of a book to its "
                                            "current version, so notes follow a re-index (idempotent)")
    rm.add_argument("book")
    rm.add_argument("--dry-run", action="store_true", help="count the matches and write nothing")
    rm.set_defaults(fn=cmd_reindex_map)
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
    ap_.add_argument("--accept-finding", action="append", default=[], metavar="PATH@sha256:DIGEST:RULE",
                     help="accept one reviewed personal-data finding that `receive` listed: that rule, in exactly "
                          "that file content; repeatable; needed for a cloud_ok book (--egress cloud_ok)")
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
    ki.add_argument("--source-repo", metavar="REPO",
                    help="a local git repository that the folder was copied from: propose each file's origin from "
                         "its commit trailers (model or unknown, never human or assisted)")
    ki.add_argument("--commit", metavar="REV", help="the commit of --source-repo that the copy was taken at "
                                                     "(default HEAD)")
    _scan_options(ki, "give the same acceptances to ingest")
    ki.set_defaults(fn=cmd_kstd_init, no_db=True)
    kc = sub.add_parser("kstd-check", help="validate a folder's kstd.yaml: digests, SPDX ids, terms; list the "
                                           "personal-data findings, as kstd-init and ingest do (no database)")
    kc.add_argument("path")
    _scan_options(kc, "give the same acceptances to ingest")
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
    ni = nsub.add_parser("import", help="import JSONL records of an orchestrator's local memory as pending notes")
    ni.add_argument("book", help="the journal")
    ni.add_argument("file", help="JSONL: one record per line (docs/guide/agent-memory.md)")
    ni.add_argument("--by", required=True, help="the importer, who holds propose on the journal: user:<name> "
                                                "(origin unknown) or agent:<name> (origin model)")
    ni.set_defaults(fn=cmd_note_import)
    dc = sub.add_parser("decisions", help="decision records of journals (docs/24 §21)")
    dcsub = dc.add_subparsers(dest="decisions_cmd", required=True)
    de = dcsub.add_parser("export", help="write JSONL decision records the principal may read; text only with "
                                         "ai_input and train")
    de.add_argument("principal")
    de.add_argument("--out", required=True, help="a new file")
    de.add_argument("--book", action="append", help="only this journal (repeatable); default: every readable one")
    de.add_argument("--on-behalf-of")
    de.set_defaults(fn=cmd_decisions_export)
    sk = sub.add_parser("skill", help="SkillSpector scans of skill folders (D71, docs/24 §22)")
    sksub = sk.add_subparsers(dest="skill_cmd", required=True)
    ss = sksub.add_parser("show", help="the scan records of a book's current version: proposals, blocks, clearances")
    ss.add_argument("book")
    ss.set_defaults(fn=cmd_skill_show)
    sr = sksub.add_parser("rescan", help="scan again where no fresh record of the configured tool version exists "
                                         f"({skillscan.BIN_ENV})")
    sr.add_argument("--book", help="only this book; default: every book")
    sr.set_defaults(fn=cmd_skill_rescan)
    sc = sksub.add_parser("clear", help="lift the scan block of one skill as a curator (needs KUTUPHANE_CURATOR_DSN)")
    sc.add_argument("book")
    sc.add_argument("path", help="the skill folder (the folder of its SKILL.md; '.' for the book root)")
    sc.add_argument("--curator", required=True, help="user:<name>, who holds curate on the book")
    sc.add_argument("--reason", required=True)
    sc.set_defaults(fn=cmd_skill_clear, curator_db=True)
    cu = sub.add_parser("curator", help="curator web: passkeys and acts (docs/25; needs KUTUPHANE_CURATOR_DSN)")
    cusub = cu.add_subparsers(dest="curator_cmd", required=True)
    ce = cusub.add_parser("enroll", help="a one-time enrollment URL (15 minutes, one passkey) for a person")
    ce.add_argument("principal", help="user:<name>")
    ce.set_defaults(fn=cmd_curator_enroll, curator_db=True)
    cp = cusub.add_parser("passkeys", help="the registered passkeys (synced or device-bound, last act)")
    cp.add_argument("principal", nargs="?")
    cp.set_defaults(fn=cmd_curator_passkeys, curator_db=True)
    cr = cusub.add_parser("revoke-passkey", help="a revoked passkey signs nothing and its sessions end (a lost phone: "
                                                 "revoke, then enroll)")
    cr.add_argument("id", help="the passkey id from `curator passkeys`")
    cr.set_defaults(fn=cmd_curator_revoke_passkey, curator_db=True)
    cx = cusub.add_parser("end-sessions", help="end every live session of a person (a stolen cookie)")
    cx.add_argument("principal", help="user:<name>")
    cx.set_defaults(fn=cmd_curator_end_sessions, curator_db=True)
    cc = cusub.add_parser("cancel-enrollment", help="cancel an unused enrollment code (a leaked code)")
    cc.add_argument("id", help="the enrollment id (en_…) that `curator enroll` printed")
    cc.set_defaults(fn=cmd_curator_cancel_enrollment, curator_db=True)
    cv = cusub.add_parser("verify-acts", help="check every stored act again: statement, signature with UV, effects")
    cv.add_argument("--since", type=int, default=0, help="only acts with a higher seq")
    cv.set_defaults(fn=cmd_curator_verify_acts, curator_db=True)
    cq = cusub.add_parser("queue", help="the pending notes of a curator in risk order, with their same_as groups")
    cq.add_argument("--curator", required=True, help="user:<name>, who holds curate and read on the books")
    cq.add_argument("--book", help="only this book")
    cq.add_argument("--as-of", type=int, help="the watermark w (default: now); the same w gives the same queue")
    cq.add_argument("--cursor", help="next_cursor of the previous page")
    cq.add_argument("--limit", type=int, default=curatorqueue.PAGE_GROUPS, help="groups per page")
    cq.set_defaults(fn=cmd_curator_queue, curator_db=True)
    cm = cusub.add_parser("report", help="curator seconds per approved note, the share pending after 7 days, "
                                         "who decided, delegations")
    cm.add_argument("--from", dest="start", required=True, help="ISO date or time (UTC if no zone), inclusive")
    cm.add_argument("--to", dest="end", required=True, help="ISO date or time (UTC if no zone), exclusive")
    cm.set_defaults(fn=cmd_curator_report, curator_db=True)
    cw = cusub.add_parser("web", help="serve curator web (KUTUPHANE_CURATOR_WEB_DSN, KUTUPHANE_WEBAUTHN_*)")
    cw.add_argument("--host", default="127.0.0.1")
    cw.add_argument("--port", type=int, default=8090)
    cw.set_defaults(fn=cmd_curator_web, no_db=True)
    dr = sub.add_parser("decider", help="the decider runner: model suggestions and delegated uses (docs/25 §8.3)")
    drsub = dr.add_subparsers(dest="decider_cmd", required=True)
    drr = drsub.add_parser("run", help="one run (KUTUPHANE_DECIDER_DSN, KUTUPHANE_DECIDER_LLMDAP_KEY, "
                                       "KUTUPHANE_DECIDER_BOOKS)")
    drr.add_argument("--spec", required=True, help="the decider spec file (deploy/deciders/*.json)")
    drr.add_argument("--shadow", action="store_true", help="suggestions only: no delegated use")
    drr.add_argument("--limit", type=int, default=100, help="at most this many model calls")
    drr.set_defaults(fn=cmd_decider_run, no_db=True)
    drs = drsub.add_parser("spec", help="check a spec; print its decider id and spec_sha256")
    drs.add_argument("spec")
    drs.set_defaults(fn=cmd_decider_spec, no_db=True)
    dg = sub.add_parser("delegation", help="D73 delegated curate (docs/25 §8; needs KUTUPHANE_CURATOR_DSN)")
    dgsub = dg.add_subparsers(dest="delegation_cmd", required=True)
    dgl = dgsub.add_parser("list", help="every delegation with its state and use counts")
    dgl.add_argument("--book")
    dgl.set_defaults(fn=cmd_delegation_list, curator_db=True)
    dgr = dgsub.add_parser("report", help="the act, the end, every use with its model call; agreement, outcomes")
    dgr.add_argument("id")
    dgr.set_defaults(fn=cmd_delegation_report, curator_db=True)
    dga = dgsub.add_parser("agreement", help="the shadow agreement of a decider spec in one (book, kind)")
    dga.add_argument("--spec", required=True)
    dga.add_argument("--book", required=True)
    dga.add_argument("--kind", required=True)
    dga.set_defaults(fn=cmd_delegation_agreement, curator_db=True)
    dge = dgsub.add_parser("end", help="end a delegation as a curator (final)")
    dge.add_argument("id")
    dge.add_argument("--curator", required=True, help="user:<name>, who holds curate on the book")
    dge.add_argument("--reason", required=True)
    dge.set_defaults(fn=cmd_delegation_end, curator_db=True)
    return ap


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    try:
        if getattr(args, "no_db", False):
            return args.fn(None, args)
        # A curate grant makes a curator, so it needs the curator credential, as the curation it allows (#67).
        curator_db = getattr(args, "curator_db", False) or (args.fn is cmd_grant and args.mode == "curate")
        if curator_db and not os.environ.get(db.CURATOR_DSN_ENV):
            print(f"error: {db.CURATOR_DSN_ENV} is not set (the curator credential)", file=sys.stderr)
            return 2
        # The owner credential writes Standing and applies migrations; without it, migrate uses KUTUPHANE_DSN
        # (a single-role development database).
        owner = curator_db or args.fn is cmd_migrate
        with db.connect(os.environ.get(db.CURATOR_DSN_ENV) if owner else None) as conn:
            return args.fn(conn, args)
    except (ValueError, OSError, RuntimeError) as exc:  # SourceError, PolicyError, AuthzError are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
