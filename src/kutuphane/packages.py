"""Signed packages between installations (D23, D29, AT-13, AT-14). Network and physical media carry the same file.

Package = uncompressed tar with exactly: MANIFEST.json (canonical JSON), MANIFEST.sig (base64 Ed25519 over those
bytes) and content/<path> for every file the manifest lists. Nothing is extracted to disk; members are read in
memory with size limits; links, devices and unexpected names are refused.

Receiving side: receive() quarantines, verifies (trusted and unrevoked key, signature, every digest, recomputed
content id, sequence newer than any accepted), scans and diffs, and stores the verdict — rejected packages are
kept. Nothing reaches the catalog until a person approves: approve() re-checks key and sequence under row locks
(the key row FOR SHARE, so a revocation either lands first and refuses, or waits for the approval to finish) and
publishes in ONE transaction, with the receiving installation's own policy (D23). Any failure leaves the catalog
unchanged and the failure on record.
"""
import base64
import io
import json
import re
import tarfile
import time

from psycopg.types.json import Jsonb

from . import agentfiles, catalog, ids, kstd, profiles, signing
from .policy import check_policy
from .source import MAX_FILE_BYTES, MAX_SOURCE_BYTES, TEXT_TYPES, SourceError, read_file

FORMAT = "kutuphane-package/1"
MANIFEST, SIGNATURE, CONTENT = "MANIFEST.json", "MANIFEST.sig", "content/"
MAX_PACKAGE_BYTES = MAX_SOURCE_BYTES + 1024 * 1024
# Instruction-like phrases worth a human look before approval (findings never approve or reject by themselves).
MANIFEST_FIELDS = {"issuer": str, "book": str, "title": str, "content_id": str, "sequence": int, "created_at": int,
                   "files": list}
FILE_FIELDS = {"path": str, "sha256": str, "size": int}
SUSPICIOUS = re.compile(r"(?i)(ignore (all |the )?(previous|above) instructions|önceki talimatları (yok say|unut)|"
                        r"system prompt|sistem istemi|you are now|bundan sonra sen)")


class PackageError(ValueError):
    pass


# --- export -----------------------------------------------------------------------------------------------

def export(conn, book: str, key, legal_basis: str | None = None) -> bytes:
    """Sign the book's current version. The sequence for (this key, book) advances in the same transaction.
    kstd: a file whose personal_data is not `no` or `synthetic` leaves the node only with a recorded legal basis
    (DPV codes, docs/11 §5); the basis goes into the signed manifest. Files with origin `model`/`unknown` are listed
    as `ai_generated`; `assisted` files are listed in `reviewed` with their reviewer (EU AI Act Art. 50(4)); `tool`
    files are listed in `tool_made` with their software agent and carry no AI mark (docs/17)."""
    issuer = signing.fingerprint(key.public_key())
    state = catalog.book_state(conn, book)
    if state is None:
        raise PackageError(f"no such book: {book}")
    rights = kstd.Rights(conn)
    infos = {e["path"]: info for e in state["files"]
             if (info := rights.info(book, state["content_id"], e["path"])) is not None}
    personal = [p for p, i in infos.items() if i["personal_data"] not in kstd.NO_LEGAL_BASIS_NEEDED]
    basis = None
    if personal:
        if not (isinstance(legal_basis, str) and legal_basis.strip()):
            raise PackageError(f"{len(personal)} file(s) may contain personal data ({', '.join(personal[:3])}"
                               f"{', …' if len(personal) > 3 else ''}); export needs a legal basis")
        try:
            basis = kstd.legal_basis(legal_basis)
        except kstd.KstdError as exc:
            raise PackageError(str(exc)) from None
    origin = origin_marks(infos)
    files = []
    for entry in state["files"]:
        data = catalog.read_file(conn, book, state["content_id"], entry["path"])
        files.append((entry["path"], data))
    with conn.transaction():
        seq = conn.execute(
            "INSERT INTO export_sequence (issuer, book, last_sequence) VALUES (%s, %s, 1) "
            "ON CONFLICT (issuer, book) DO UPDATE SET last_sequence = export_sequence.last_sequence + 1 "
            "RETURNING last_sequence", (issuer, book)).fetchone()[0]
    manifest = {
        "format": FORMAT, "issuer": issuer, "book": book, "title": state["title"],
        "content_id": state["content_id"], "sequence": seq, "created_at": int(time.time()),
        "policy_suggestion": state["policy"],
        **({"legal_basis": basis} if basis else {}),
        **origin,
        "files": [{"path": p, "sha256": ids.sha256_hex(d), "size": len(d)} for p, d in sorted(files)],
    }
    body = ids.canonical(manifest)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=tarfile.PAX_FORMAT) as tar:
        members = [(MANIFEST, body), (SIGNATURE, base64.b64encode(key.sign(body)))]
        members += [(CONTENT + p, d) for p, d in sorted(files)]
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()



ORIGIN_MARKS = ("ai_generated", "reviewed", "tool_made")


def origin_marks(infos: dict) -> dict:
    """The origin lists of a package manifest, from the item information of each file ({} without kstd.yaml).
    Export writes them; receive recomputes them from the enclosed kstd.yaml and refuses any difference."""
    if not infos:
        return {}
    return {
        "ai_generated": sorted(p for p, i in infos.items() if i["origin"] in kstd.AI_GENERATED),
        "reviewed": {p: i["reviewed_by"] for p, i in sorted(infos.items()) if i["origin"] == "assisted"},
        "tool_made": {p: i["software_agent"] for p, i in sorted(infos.items()) if i["origin"] == "tool"},
    }

# --- receive ----------------------------------------------------------------------------------------------

def _members(data: bytes) -> dict[str, bytes]:
    if len(data) > MAX_PACKAGE_BYTES:
        raise PackageError("package too large")
    out, total = {}, 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
            for m in tar:
                if not m.isreg():
                    raise PackageError(f"{m.name!r}: only regular files are allowed")
                if m.name in out:
                    raise PackageError(f"{m.name!r}: duplicate member")
                if m.name not in (MANIFEST, SIGNATURE) and not m.name.startswith(CONTENT):
                    raise PackageError(f"{m.name!r}: unexpected member")
                if m.size > MAX_FILE_BYTES or total + m.size > MAX_SOURCE_BYTES:
                    raise PackageError(f"{m.name!r}: too large")
                total += m.size
                out[m.name] = tar.extractfile(m).read()
    except tarfile.TarError as exc:
        raise PackageError(f"not a valid package: {exc}") from None
    return out


def _has_nul(value) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(k) or _has_nul(v) for k, v in value.items())
    return isinstance(value, list) and any(_has_nul(v) for v in value)


def _manifest(body: bytes) -> dict:
    """Parse and type-check before anything else reads a field: a malformed manifest is a recorded rejection."""
    try:
        manifest = json.loads(body)
        canonical = ids.canonical(manifest)
    except (ValueError, RecursionError):  # includes lone surrogates that cannot be re-encoded
        raise PackageError("manifest is not valid JSON") from None
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise PackageError("unknown package format")
    if canonical != body:
        raise PackageError("manifest is not in canonical form")
    if _has_nul(manifest):  # PostgreSQL text and jsonb cannot hold it
        raise PackageError("manifest contains a NUL character")
    for name, kind in MANIFEST_FIELDS.items():
        if type(manifest.get(name)) is not kind:
            raise PackageError(f"manifest field {name!r} is missing or not a {kind.__name__}")
    for f in manifest["files"]:
        if not isinstance(f, dict) or any(type(f.get(n)) is not k for n, k in FILE_FIELDS.items()):
            raise PackageError("every manifest file entry needs path, sha256 and size")
    return manifest


def _verify(conn, members: dict[str, bytes]) -> tuple[dict, list]:
    """Returns (manifest, source files). Raises PackageError with the first reason it is not acceptable."""
    if MANIFEST not in members or SIGNATURE not in members:
        raise PackageError("manifest or signature missing")
    body = members[MANIFEST]
    manifest = _manifest(body)
    key = conn.execute("SELECT public_key, revoked_at FROM trusted_key WHERE fingerprint = %s FOR SHARE",
                       (manifest["issuer"],)).fetchone()
    if key is None:
        raise PackageError("signed by an unknown key")
    if key[1] is not None:
        raise PackageError("signed by a revoked key")
    try:
        signature = base64.b64decode(members[SIGNATURE], validate=True)
    except ValueError:
        raise PackageError("signature is not base64") from None
    if not signing.verify(bytes(key[0]), signature, body):
        raise PackageError("signature does not verify")
    listed = manifest["files"]
    if not listed:
        raise PackageError("manifest lists no files")
    names = {CONTENT + f["path"] for f in listed}
    if names != {n for n in members if n.startswith(CONTENT)} or len(names) != len(listed):
        raise PackageError("package content does not match the manifest file list")
    files = []
    for f in listed:
        data = members[CONTENT + f["path"]]
        if ids.sha256_hex(data) != f["sha256"] or len(data) != f["size"]:
            raise PackageError(f"{f['path']}: digest or size mismatch")
        try:
            files.append(read_file(f["path"], data))
        except (SourceError, ValueError) as exc:
            raise PackageError(str(exc)) from None
    if ids.content_id({sf.path: sf.sha256 for sf in files}) != manifest["content_id"]:
        raise PackageError("content id does not match the files")
    try:  # the origin lists are claims of the sender: they must follow from the enclosed, valid kstd.yaml
        enclosed = kstd.validate(files)
    except kstd.KstdError as exc:
        raise PackageError(f"enclosed {kstd.MANIFEST} is not valid: {exc}") from None
    infos = {f.path: info for f in files if enclosed and (info := kstd.effective(enclosed, f.path)) is not None}
    expected = origin_marks(infos)
    if {k: manifest[k] for k in ORIGIN_MARKS if k in manifest} != expected:
        raise PackageError(f"origin lists ({', '.join(ORIGIN_MARKS)}) do not match the enclosed {kstd.MANIFEST}")
    if not 1 <= manifest["sequence"] < 2**63:  # a bigint column
        raise PackageError("invalid sequence")
    last = _last_sequence(conn, manifest["issuer"], manifest["book"])
    if manifest["sequence"] <= last:
        raise PackageError(f"replay: sequence {manifest['sequence']} is not newer than accepted {last}")
    return manifest, files


def _last_sequence(conn, issuer, book, lock=False) -> int:
    row = conn.execute("SELECT last_sequence FROM package_sequence WHERE issuer = %s AND book = %s"
                       + (" FOR UPDATE" if lock else ""), (issuer, book)).fetchone()
    return row[0] if row else 0


def _scan(files) -> list[dict]:
    findings, skills = [], agentfiles.skill_dirs(f.path for f in files)
    for f in files:
        if agentfiles.is_instruction({"path": f.path, "okf_type": f.okf_type}, skills):
            findings.append({"path": f.path, "kind": "agent_instruction",
                             "note": "Ajan talimatı (K3): etkinleştirme ayrı izin ister"})
        if f.quarantine:
            findings.append({"path": f.path, "kind": "quarantined", "note": f.quarantine})
        if f.media_type.startswith("text/") or f.media_type in TEXT_TYPES.values():
            for m in SUSPICIOUS.finditer(f.data.decode("utf-8", errors="replace")):
                findings.append({"path": f.path, "kind": "instruction_like_text", "match": m.group(0)})
    return findings


def _diff(conn, book: str, files) -> dict:
    state = catalog.book_state(conn, book)
    before = {f["path"]: f["sha256"] for f in (state["files"] if state and state["files"] else [])}
    after = {f.path: f.sha256 for f in files}
    return {"added": sorted(after.keys() - before.keys()), "removed": sorted(before.keys() - after.keys()),
            "changed": sorted(p for p in after.keys() & before.keys() if after[p] != before[p])}


def receive(conn, data: bytes) -> dict:
    """Quarantine + verify + scan + diff. Never touches the catalog. Every outcome is recorded."""
    try:
        manifest, files = _verify(conn, _members(data))
    except PackageError as exc:
        kept = data if len(data) <= MAX_PACKAGE_BYTES else b""  # an oversized input is not stored, only refused
        pid = conn.execute("INSERT INTO package_import (status, package, reasons) VALUES ('rejected', %s, %s) "
                           "RETURNING id", (kept, Jsonb([str(exc)]))).fetchone()[0]
        return {"id": pid, "status": "rejected", "reasons": [str(exc)]}
    findings, diff = _scan(files), _diff(conn, manifest["book"], files)
    pid = conn.execute(
        "INSERT INTO package_import (status, issuer, book, sequence, content_id, manifest, package, findings, diff) "
        "VALUES ('verified', %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (manifest["issuer"], manifest["book"], manifest["sequence"], manifest["content_id"], Jsonb(manifest), data,
         Jsonb(findings), Jsonb(diff))).fetchone()[0]
    return {"id": pid, "status": "verified", "book": manifest["book"], "sequence": manifest["sequence"],
            "findings": findings, "diff": diff, "policy_suggestion": manifest.get("policy_suggestion"),
            "legal_basis": manifest.get("legal_basis"), "ai_generated": manifest.get("ai_generated"),
            "reviewed": manifest.get("reviewed"), "tool_made": manifest.get("tool_made")}


# --- decide -----------------------------------------------------------------------------------------------

def approve(conn, import_id: int, *, by: str, policy: dict, profile: str = "chunked") -> catalog.Published:
    """A person approves; this installation's own policy applies. Atomic: all of it or none of it."""
    policy = check_policy(policy)
    try:
        with conn.transaction():
            row = conn.execute("SELECT status, package FROM package_import WHERE id = %s FOR UPDATE",
                               (import_id,)).fetchone()
            if row is None:
                raise PackageError(f"no such import: {import_id}")
            if row[0] != "verified":
                raise PackageError(f"import {import_id} is {row[0]}, not verified")
            members = _members(bytes(row[1]))
            manifest = json.loads(members[MANIFEST])
            # Serialize concurrent approvals for this (key, book): make sure the row exists, then lock it.
            conn.execute("INSERT INTO package_sequence (issuer, book, last_sequence) VALUES (%s, %s, 0) "
                         "ON CONFLICT (issuer, book) DO NOTHING", (manifest["issuer"], manifest["book"]))
            _last_sequence(conn, manifest["issuer"], manifest["book"], lock=True)
            manifest, files = _verify(conn, members)  # key may be revoked or a newer package accepted meanwhile
            published = catalog.publish(conn, book=manifest["book"], title=manifest["title"], files=files,
                                        policy=policy, profile=profiles.spec(profile))
            conn.execute("UPDATE package_sequence SET last_sequence = GREATEST(last_sequence, %s) "
                         "WHERE issuer = %s AND book = %s", (manifest["sequence"], manifest["issuer"], manifest["book"]))
            conn.execute("UPDATE package_import SET status = 'published', decided_by = %s, decided_at = now() "
                         "WHERE id = %s", (by, import_id))
            return published
    except PackageError as exc:  # the package itself is not acceptable (any more): final
        conn.execute("UPDATE package_import SET status = 'rejected', reasons = reasons || %s, decided_by = %s, "
                     "decided_at = now() WHERE id = %s AND status = 'verified'",
                     (Jsonb([f"at approval: {exc}"]), by, import_id))
        raise
    except ValueError as exc:  # the chosen publication failed (e.g. profile limits): on record, can be retried
        conn.execute("UPDATE package_import SET reasons = reasons || %s WHERE id = %s AND status = 'verified'",
                     (Jsonb([f"approval by {by} failed: {exc}"]), import_id))
        raise


def reject(conn, import_id: int, *, by: str, reason: str) -> bool:
    row = conn.execute("UPDATE package_import SET status = 'rejected', reasons = reasons || %s, decided_by = %s, "
                       "decided_at = now() WHERE id = %s AND status = 'verified' RETURNING id",
                       (Jsonb([f"rejected by {by}: {reason}"]), by, import_id)).fetchone()
    return row is not None


# --- trust ------------------------------------------------------------------------------------------------

def trust(conn, public_pem: bytes, *, expected_fingerprint: str, name: str, by: str) -> str:
    """Trust root: the administrator must state the fingerprint they confirmed out of band; a mismatch refuses."""
    public = signing.load_public(public_pem)
    actual = signing.fingerprint(public)
    if actual != expected_fingerprint:
        raise PackageError(f"fingerprint mismatch: key is {actual}")
    conn.execute("INSERT INTO trusted_key (fingerprint, public_key, name, added_by) VALUES (%s, %s, %s, %s)",
                 (actual, signing.raw_public(public), name, by))
    return actual


def revoke_key(conn, fingerprint: str) -> bool:
    row = conn.execute("UPDATE trusted_key SET revoked_at = now() WHERE fingerprint = %s AND revoked_at IS NULL "
                       "RETURNING fingerprint", (fingerprint,)).fetchone()
    return row is not None
