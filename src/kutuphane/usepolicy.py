"""Use policies (D85 S2, grill Q6-Q8): a curator's standing decision that a book may be published from one trusted
signing key without a per-package act, when the package carries a signed consumer attestation (`accepted_by` in the
manifest) from one of the policy's attesters and nothing in it needs a person.

`admission()` is the one place that holds the rule (Q8). A package that fails any part of it stays `verified` for a
person (`approve-import`), which always works. `publish_admitted()` is the timer entry (`kutuphane imports
publish-admitted`); it publishes through `packages.approve`, which re-verifies under the same locks as a person's
approval. The acceptance kind is `consumer_attested`; `approved_by` is the attester, `decided_by` is `policy:<id>`.
"""
import re
from contextlib import nullcontext
from dataclasses import dataclass

import psycopg.errors
from psycopg.types.json import Jsonb

from . import agentfiles, authz, catalog, identity, ids, kstd, packages
from .policy import check_policy, make_policy

SLUG = re.compile(rf"^{ids.SLUG}\Z")


class NotAdmitted(Exception):
    """The package stays `verified` for a person. Not a ValueError: the import is not marked failed."""


@dataclass(frozen=True)
class Admission:
    id: int
    policy: dict
    principal: str


def _attesters(prefixes) -> list[str]:
    """The same rule as the principal prefixes of an issuer (identity.PREFIX), `user:` only: never a whole kind."""
    if not (isinstance(prefixes, (list, tuple)) and prefixes
            and all(isinstance(p, str) and identity.PREFIX.match(p) and p.startswith("user:") for p in prefixes)):
        raise ValueError("an attester is user:<start of a name>, for example user:im.; never user: alone or agent:")
    return sorted(set(prefixes))


def _book_policy(policy: dict) -> dict:
    """Q8: a use policy never makes restricted content or a cloud_ok book without a person."""
    policy = check_policy(policy)
    if policy["sensitivity"] == "restricted" or policy["egress"] == "cloud_ok":
        raise ValueError("a use policy never applies restricted sensitivity or cloud_ok egress: a person approves "
                         "such a package")
    return policy


def add(conn, book: str, key: str, attesters, *, sensitivity: str, egress: str, protection: str, by: str) -> int:
    if not SLUG.match(book):
        raise ValueError(f"{book!r} is not a book slug")
    if not (isinstance(by, str) and by.startswith("user:") and authz.PRINCIPAL.match(by)):
        raise ValueError("--by must be a user: principal such as user:<name>")
    catalog.require_curate(conn, by, book)
    policy = _book_policy(make_policy(sensitivity=sensitivity, egress=egress, protection=protection))
    attesters = _attesters(attesters)
    trusted = conn.execute("SELECT revoked_at FROM trusted_key WHERE fingerprint = %s", (key,)).fetchone()
    if trusted is None or trusted[0] is not None:
        raise ValueError(f"{key} is not a trusted signing key (or it is revoked): `kutuphane trust` first")
    try:
        return conn.execute("INSERT INTO use_policy (book, issuer, attesters, policy, created_by) "
                            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                            (book, key, attesters, Jsonb(policy), by)).fetchone()[0]
    except psycopg.errors.UniqueViolation:
        raise ValueError(f"{book} already has an active use policy for {key}: revoke it first") from None


def revoke(conn, policy_id: int, *, by: str) -> bool:
    """Later publications only: a version that the policy admitted stays published (as a person's approval does)."""
    if not (isinstance(by, str) and by.startswith("user:") and authz.PRINCIPAL.match(by)):
        raise ValueError("--by must be a user: principal such as user:<name>")
    row = conn.execute("SELECT book FROM use_policy WHERE id = %s", (policy_id,)).fetchone()
    if row is None:
        raise ValueError(f"no use policy {policy_id}")
    catalog.require_curate(conn, by, row[0])
    return conn.execute("UPDATE use_policy SET revoked_at = now(), revoked_by = %s WHERE id = %s AND revoked_at IS NULL "
                        "RETURNING id", (by, policy_id)).fetchone() is not None


def listing(conn, book: str | None = None) -> list[dict]:
    rows = conn.execute("SELECT id, book, issuer, attesters, policy, created_by, created_at, revoked_at, revoked_by "
                        "FROM use_policy WHERE book = %s OR %s::text IS NULL ORDER BY id", (book, book)).fetchall()
    return [{"id": i, "book": b, "issuer": k, "attesters": a, "policy": p, "created_by": c, "created_at": t.isoformat(),
             "revoked_at": r.isoformat() if r else None, "revoked_by": rb} for i, b, k, a, p, c, t, r, rb in rows]


def admission(conn, manifest: dict, files: list, findings: list) -> Admission:
    """The rule of Q8, once. `manifest`, `files`: as re-verified (packages._verify); `findings`: those of `receive`.
    The book's current policy must still be the use policy's (Q8), else a person decides.
    Returns the admitting use policy, or raises NotAdmitted with the first reason. The policy row is read FOR SHARE,
    so a revocation either lands first or waits for the publication."""
    row = conn.execute("SELECT u.id, u.attesters, u.policy FROM use_policy u JOIN trusted_key k "
                       "ON k.fingerprint = u.issuer AND k.revoked_at IS NULL "
                       "WHERE u.book = %s AND u.issuer = %s AND u.revoked_at IS NULL FOR SHARE OF u",
                       (manifest["book"], manifest["issuer"])).fetchone()
    if row is None:
        raise NotAdmitted("no active use policy for this book and signing key")
    policy_id, attesters, doc = row
    try:
        policy = _book_policy(doc)
    except ValueError as exc:
        raise NotAdmitted(f"the use policy {policy_id} is not allowed: {exc}") from None
    current = conn.execute("SELECT b.current_policy, v.doc FROM book b LEFT JOIN policy_version v "
                           "ON v.id = b.current_policy WHERE b.slug = %s FOR UPDATE OF b", (manifest["book"],)).fetchone()
    if current is not None and current[0] is not None:  # a first publication has none: the use policy applies
        if current[0] != ids.policy_id(policy):
            raise NotAdmitted(f"the book policy changed after use policy {policy_id}; a person decides")
        try:
            _book_policy(current[1])
        except ValueError:
            raise NotAdmitted("the book policy is restricted or cloud_ok; a person decides") from None
    attested = manifest.get("accepted_by")
    if attested is None:
        raise NotAdmitted("the manifest has no accepted_by")
    if not attested["principal"].startswith(tuple(attesters)):
        raise NotAdmitted(f"{attested['principal']} is outside the attesters of use policy {policy_id}")
    if findings:
        kinds = sorted({f.get("kind", "?") for f in findings})
        raise NotAdmitted(f"{len(findings)} finding(s) for a person ({', '.join(kinds)})")
    enclosed = kstd.validate(files)
    unlicensed = sorted(f.path for f in files if enclosed and (info := kstd.effective(enclosed, f.path)) is not None
                        and info["license"] == "unknown")
    if unlicensed:
        raise NotAdmitted(f"license unknown: {', '.join(unlicensed[:3])}")
    skills = agentfiles.skill_dirs(f.path for f in files)
    instructions = sorted(f.path for f in files
                          if agentfiles.is_instruction({"path": f.path, "okf_type": f.okf_type}, skills))
    if instructions:
        raise NotAdmitted(f"agent instruction file (K3): {', '.join(instructions[:3])}")
    return Admission(policy_id, policy, attested["principal"])


def publish_admitted(conn, *, dry_run: bool = False):
    """Yields (result, catalog.Published or None) for each `verified` import; result is {import, book, status, ...}:
    status `published`, `would_publish` (dry run: all of it is done and rolled back), `skipped` (stays verified, with
    the reason) or `rejected` (the re-verification refused the package, as at a person's approval). Idempotent."""
    rows = conn.execute("SELECT i.id, i.book, i.issuer, k.revoked_at IS NOT NULL, u.id FROM package_import i "
                        "LEFT JOIN trusted_key k ON k.fingerprint = i.issuer "
                        "LEFT JOIN use_policy u ON u.book = i.book AND u.issuer = i.issuer AND u.revoked_at IS NULL "
                        "WHERE i.status = 'verified' ORDER BY i.id").fetchall()
    for import_id, book, issuer, key_revoked, policy_id in rows:
        out = {"import": import_id, "book": book}
        if key_revoked:
            yield {**out, "status": "skipped", "reason": "the signing key is revoked"}, None
            continue
        if policy_id is None:
            yield {**out, "status": "skipped", "reason": "no active use policy for this book and signing key"}, None
            continue
        try:
            with conn.transaction(force_rollback=True) if dry_run else nullcontext():  # a refusal is kept on record
                published = packages.approve(conn, import_id, by=f"policy:{policy_id}", admit=admission)
        except NotAdmitted as exc:
            yield {**out, "status": "skipped", "reason": str(exc)}, None
        except packages.PackageError as exc:
            yield {**out, "status": "rejected" if not dry_run else "would_reject", "reason": str(exc)}, None
        except ValueError as exc:
            yield {**out, "status": "skipped", "reason": f"publication failed: {exc}"}, None
        else:
            yield {**out, "status": "would_publish" if dry_run else "published", "use_policy": policy_id,
                   "content_id": published.content_id}, None if dry_run else published
