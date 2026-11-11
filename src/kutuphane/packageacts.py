"""Passkey approval of received packages (D85 S3, decision Q13/Q14; docs/25 §4.7).

Curator web only *records* a signed `package` act: a statement of 1..50 items {import_id, book, manifest_sha256,
content_id, decision, policy | reason}. It never publishes and has no catalog rights. The owner-run publisher
(`kutuphane imports publish-admitted`, `apply` here) applies each item that still holds, in one transaction per
import: the same re-verification as `approve-import`, the signed manifest digest and content id, and `curate` of the
signer now. An item that no longer holds is not applied: the import stays `verified` and the line says why.
"""
import json
from contextlib import nullcontext

import psycopg

from . import authz, curation, gate, ids, packages
from .policy import check_policy

MAX_ITEMS = curation.MAX_ITEMS
DECISIONS = ("approve", "reject")
CLOUD_OK = ("a passkey cannot approve egress cloud_ok: the operator runs `kutuphane approve-import "
            "--egress cloud_ok --accept-finding …` (D85)")


def _rows(conn, ids: list[int]) -> dict:
    return {r[0]: r for r in conn.execute("SELECT id, status, book, package FROM package_import WHERE id = ANY(%s)",
                                          (ids,)).fetchall()}


def _check(conn, principal: str, items) -> None:
    """Every rule of the statement that the database state decides now, with no write: the shape, the rights, the
    state of each import, the signed digest, and the policy. Raises ValueError, gate.Denied or curation.Changed."""
    authz.curator(principal, "package")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS or not all(isinstance(i, dict) for i in items):
        raise ValueError(f"an act has 1..{MAX_ITEMS} items")
    found = _rows(conn, [i["import_id"] for i in items if type(i.get("import_id")) is int and 0 < i["import_id"] < 2**63])
    if len({i.get("import_id") for i in items}) != len(items):
        raise ValueError("the same import is given twice")
    for item in items:
        row = found.get(item.get("import_id"))
        if row is None:
            raise gate.NotFound(f"no such import: {item.get('import_id')}")
        _, status, book, package = row
        if status != "verified":
            raise curation.Changed(f"import {row[0]} is {status}, not verified: reload")
        for mode in ("curate", "read"):
            if not authz.direct(conn, principal, f"book:{book}", mode).allowed:
                raise gate.Denied(f"{principal} does not hold {mode} on book:{book}")
        try:
            packages.check_signed(packages._members(bytes(package))[packages.MANIFEST], item)
        except packages.PackageError:
            raise curation.Changed(f"import {row[0]} changed since it was shown: reload") from None
        if item["decision"] == "approve":
            if check_policy(item["policy"])["egress"] == "cloud_ok":
                raise gate.Denied(CLOUD_OK)
        elif item["decision"] != "reject":
            raise ValueError(f"decision is one of {', '.join(DECISIONS)}")


def fields(conn, principal: str, body: dict) -> dict:
    """The statement fields for the options of a `package` act. The person sends {import_id, decision, policy |
    reason}; the book, manifest digest and content id come from the stored import, never from the client."""
    sent = body.get("items")
    if not isinstance(sent, list) or not 1 <= len(sent) <= MAX_ITEMS or not all(isinstance(i, dict) for i in sent):
        raise ValueError(f"an act has 1..{MAX_ITEMS} items")
    found = _rows(conn, [i["import_id"] for i in sent if type(i.get("import_id")) is int and 0 < i["import_id"] < 2**63])
    items = []
    for i in sent:
        decision = i.get("decision")
        if decision not in DECISIONS or set(i) - {"import_id", "decision", "policy", "reason"}:
            raise ValueError("an item is {import_id, decision, policy (approve) | reason (reject)}")
        row = found.get(i.get("import_id"))
        if row is None:
            raise gate.NotFound(f"no such import: {i.get('import_id')}")
        manifest = packages._members(bytes(row[3]))[packages.MANIFEST]
        extra = ({"policy": check_policy(i.get("policy"))} if decision == "approve" and "reason" not in i
                 else {"reason": i.get("reason")} if decision == "reject" and "policy" not in i else None)
        if extra is None:
            raise ValueError("an approve item has a policy, a reject item a reason")
        items.append({"import_id": row[0], "book": row[2], "manifest_sha256": ids.sha256_hex(manifest),
                      "content_id": json.loads(manifest)["content_id"], "decision": decision, **extra})
    items.sort(key=lambda i: i["import_id"])
    _check(conn, principal, items)
    if any(i["decision"] == "reject" and not (isinstance(i["reason"], str) and 1 <= len(i["reason"]) <= 500)
           for i in items):
        raise ValueError("a reject item has a reason of 1..500 characters")
    return {"items": items}


def handler(conn, act) -> dict:
    """The act row is the only write (the caller made it). The checks are those of the options, again."""
    _check(conn, act.principal, act.payload["items"])
    return {"act": act.seq, "signed": [{"import": i["import_id"], "decision": i["decision"]}
                                       for i in act.payload["items"]]}


def listing(conn, principal: str) -> dict:
    """The `verified` imports of the books where the person holds `curate` and `read`, with what the person reads
    before signing: findings, diff, submitter, attestation and the manifest's policy suggestion."""
    out = []
    shown = [b for (b,) in conn.execute("SELECT DISTINCT book FROM package_import WHERE status = 'verified' "
                                        "ORDER BY book").fetchall()   # a first package may name a book not yet made
             if all(authz.direct(conn, principal, f"book:{b}", mode).allowed for mode in ("curate", "read"))]
    for pid, book, issuer, sequence, received, manifest, findings, diff, by, for_, package in conn.execute(
            "SELECT id, book, issuer, sequence, received_at, manifest, findings, diff, submitted_by, submitted_for, "
            "package FROM package_import WHERE status = 'verified' AND book = ANY(%s) ORDER BY id", (shown,)):
        body = packages._members(bytes(package))[packages.MANIFEST]
        out.append({"import_id": pid, "book": book, "title": manifest["title"], "issuer": issuer,
                    "sequence": sequence, "received_at": received.isoformat(), "findings": findings, "diff": diff,
                    "submitted_by": by, "submitted_for": for_, "accepted_by": manifest.get("accepted_by"),
                    "policy_suggestion": manifest.get("policy_suggestion"), "content_id": manifest["content_id"],
                    "manifest_sha256": ids.sha256_hex(body), "files": len(manifest["files"])})
    return {"items": out, "max_items": MAX_ITEMS}


def _pending(conn):
    """For each `verified` import, the newest `package` act that names it, with its item: the latest decision wins."""
    return conn.execute(
        "SELECT n.act, n.signer, i.id, n.item, i.package FROM package_import i JOIN LATERAL ("
        "  SELECT a.seq AS act, a.principal AS signer, x AS item FROM curator_act a "
        "  JOIN curator_challenge c ON c.id = a.challenge CROSS JOIN jsonb_array_elements(c.payload -> 'items') x "
        "  WHERE a.action = 'package' AND (x ->> 'import_id')::bigint = i.id ORDER BY a.seq DESC LIMIT 1) n ON true "
        "WHERE i.status = 'verified' ORDER BY i.id").fetchall()


def apply(conn, *, dry_run: bool = False):
    """Yields (result, catalog.Published or None) for each `verified` import that a `package` act names. result:
    {import, book, act, signer, decision, status, ...}; status `published`, `rejected` (the signed rejection),
    `would_publish` / `would_reject` (dry run: done and rolled back) or `skipped` with the reason. Idempotent: an
    applied import is no longer `verified`."""
    for act, signer, import_id, item, package in _pending(conn):
        out = {"import": import_id, "book": item["book"], "act": act, "signer": signer, "decision": item["decision"]}
        published, result = None, {}
        try:
            with conn.transaction(force_rollback=True) if dry_run else nullcontext():
                if item["decision"] == "approve":
                    if check_policy(item["policy"])["egress"] == "cloud_ok":
                        raise ValueError(CLOUD_OK)
                    published = packages.approve(conn, import_id, by=signer, policy=item["policy"],
                                                 signed=(act, item))
                    result = {"status": "would_publish" if dry_run else "published",
                              "content_id": published.content_id}
                else:
                    with conn.transaction():  # the lock, then the digest, then the signer's right
                        conn.execute("SELECT 1 FROM package_import WHERE id = %s AND status = 'verified' FOR UPDATE",
                                     (import_id,))
                        packages.check_signed(packages._members(bytes(package))[packages.MANIFEST], item)
                        if not packages.reject(conn, import_id, by=signer, reason=item["reason"]):
                            raise ValueError("the import is no longer verified")
                    result = {"status": "would_reject" if dry_run else "rejected"}
        except (ValueError, psycopg.Error) as exc:  # PackageError is a ValueError
            yield {**out, "status": "skipped", "reason": str(exc)}, None
        else:
            yield {**out, **result}, None if dry_run else published
