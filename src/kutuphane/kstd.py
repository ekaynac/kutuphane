"""kstd L0: the `kstd.yaml` manifest (docs/11 §7–§8). It describes a folder: who answers for it, the rights of
its files, their origin, validity and applicability.

A book whose files contain `kstd.yaml` at the root follows it:
- an invalid manifest blocks publication (fail closed);
- a file with `ai_use.search` not `y` is not indexed;
- a passage with `ai_use.ai_input` not `y` is never sent to a model (embedding, reranking, answers);
- a file with `personal_data` not `no` or `synthetic` is exported only with a recorded legal basis (DPV codes);
- an exported package marks files with origin `model` or `unknown` as AI-generated; `assisted` files (model output
  that a named person reviewed) are not marked and carry `reviewed_by` (EU AI Act Art. 50(4));
- search results, citations and answers show the item information.

A book without `kstd.yaml` behaves as before: only its book policy applies. `ai_use` keeps three states: an
absent term is "not stated" and is reported as absent, but every decision treats it as `n`; an unknown license
gives no permission (docs/11 §4 rule 3, §5). The `kstd.yaml` issuer publishes into this node, so its `synthetic`
declaration is trusted here.

The SPDX identifiers in `spdx_ids.txt` come from https://github.com/spdx/license-list-data (`json/licenses.json`).
"""
import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .ids import normalize_path

MANIFEST = "kstd.yaml"
STANDARD = "kstd/0.2"
MAX_MANIFEST_BYTES = 1024 * 1024
AI_USE = ("search", "ai_input", "train")
ORIGINS = ("human", "assisted", "model", "unknown")
AI_GENERATED = ("model", "unknown")  # `unknown` counts as `model` (docs/11 §5)
PERSONAL_DATA = ("yes", "no", "synthetic", "unknown")
NO_LEGAL_BASIS_NEEDED = ("no", "synthetic")
# DPV legal bases for GDPR (https://w3id.org/dpv/legal/eu/gdpr): Art. 6(1)(a)–(f) and Art. 9(2)(a)–(j).
LEGAL_BASES = frozenset([f"eu-gdpr:A6-1-{c}" for c in "abcdef"] + [f"eu-gdpr:A9-2-{c}" for c in "abcdefghij"])
RIGHTS_KEYS = {"license", "holder", "ai_use", "personal_data"}
TOP_KEYS = {"standard", "issuer", "issued", "rights", "notices", "items"}
ITEM_KEYS = {"path", "digest", "origin", "reviewed_by", "valid_from", "valid_to", "applies_to", "rights", "notices"}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}\Z")
LICENSE_REF = re.compile(r"^(DocumentRef-[A-Za-z0-9.-]+:)?LicenseRef-[A-Za-z0-9.-]+\Z")
SPDX_IDS = frozenset(line for line in (Path(__file__).parent / "spdx_ids.txt").read_text().splitlines()
                     if line and not line.startswith("#"))


class KstdError(ValueError):
    pass


class _StrictLoader(yaml.SafeLoader):
    """No aliases, no merge keys, no duplicate keys: a later key must never silently replace a restriction."""

    def compose_node(self, parent, index):
        if self.check_event(yaml.AliasEvent):
            raise yaml.YAMLError("YAML aliases are not allowed in kstd.yaml")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        keys = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise yaml.YAMLError("YAML merge keys (<<) are not allowed in kstd.yaml")
            key = self.construct_object(key_node, deep=True)
            try:
                if key in keys:
                    raise yaml.YAMLError(f"duplicate key {key!r}")
            except TypeError:
                raise yaml.YAMLError("a mapping key must be a scalar") from None
            keys.add(key)
        return super().construct_mapping(node, deep=deep)


def parse(data: bytes) -> dict:
    if len(data) > MAX_MANIFEST_BYTES:
        raise KstdError(f"{MANIFEST}: larger than {MAX_MANIFEST_BYTES} bytes")
    try:
        doc = yaml.load(data.decode("utf-8"), Loader=_StrictLoader)
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise KstdError(f"{MANIFEST}: not valid UTF-8 YAML ({exc})") from None
    except RecursionError:
        raise KstdError(f"{MANIFEST}: nested too deeply") from None
    if not isinstance(doc, dict):
        raise KstdError(f"{MANIFEST}: the top level must be a mapping")
    return doc


def _known(where: str, mapping: dict, allowed: set, errors: list) -> None:
    for key in mapping:
        if key not in allowed and not str(key).startswith("x-"):  # x- keys are extensions; they never decide
            errors.append(f"{where}: unknown field {key!r} (extensions must start with 'x-')")


def _license_ok(value) -> bool:
    """`unknown`, or an SPDX expression of ids and LicenseRef-… joined by AND/OR, with balanced parentheses.
    WITH exceptions are not supported in kstd/0.2."""
    if value == "unknown":
        return True
    if not isinstance(value, str) or len(value) > 1000:
        return False
    tokens = value.replace("(", " ( ").replace(")", " ) ").split()
    pos = 0

    def term() -> bool:  # term := id | "(" expr ")"
        nonlocal pos
        if pos < len(tokens) and tokens[pos] == "(":
            pos += 1
            if not expr() or pos >= len(tokens) or tokens[pos] != ")":
                return False
            pos += 1
            return True
        if pos < len(tokens) and (tokens[pos].removesuffix("+") in SPDX_IDS or LICENSE_REF.match(tokens[pos])):
            pos += 1
            return True
        return False

    def expr() -> bool:  # expr := term (("AND" | "OR") term)*
        nonlocal pos
        if not term():
            return False
        while pos < len(tokens) and tokens[pos] in ("AND", "OR"):
            pos += 1
            if not term():
                return False
        return True

    try:
        return expr() and pos == len(tokens)
    except RecursionError:
        return False


def _yn(value):
    """Some YAML 1.1 loaders read y/n as booleans; accept both spellings."""
    return {True: "y", False: "n"}.get(value, value) if isinstance(value, bool) else value


def _pd(value):
    """YAML 1.1 reads an unquoted yes/no as a boolean; for personal_data that is what the writer meant."""
    return {True: "yes", False: "no"}.get(value, value) if isinstance(value, bool) else value


def _date(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return _date(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _rights(where: str, rights, errors: list) -> None:
    if not isinstance(rights, dict):
        errors.append(f"{where}: rights must be a mapping")
        return
    _known(where, rights, RIGHTS_KEYS, errors)
    if "license" in rights and not _license_ok(rights["license"]):
        errors.append(f"{where}: license {rights['license']!r} is not an SPDX expression (AND/OR of SPDX ids or "
                      f"LicenseRef-…; WITH is not supported) or 'unknown'")
    if "holder" in rights and not (isinstance(rights["holder"], str) and rights["holder"].strip()):
        errors.append(f"{where}: holder must be a non-empty string")
    if "ai_use" in rights:
        use = rights["ai_use"]
        if not isinstance(use, dict) or any(k not in AI_USE or _yn(v) not in ("y", "n") for k, v in use.items()):
            errors.append(f"{where}: ai_use takes only {', '.join(AI_USE)} with y or n")
    if "personal_data" in rights and _pd(rights["personal_data"]) not in PERSONAL_DATA:
        errors.append(f"{where}: personal_data must be one of {', '.join(PERSONAL_DATA)}")


def _notices(where: str, notices, errors: list) -> None:
    if not isinstance(notices, list) or not all(isinstance(n, str) and n.strip() for n in notices):
        errors.append(f"{where}: notices must be a list of non-empty strings")


def check(manifest: dict, files: dict[str, str]) -> tuple[list[str], list[str]]:
    """Errors (publication is refused) and warnings. `files`: {normalized path: sha256 hex} of the folder."""
    errors, warnings = [], []
    _known(MANIFEST, manifest, TOP_KEYS, errors)
    if manifest.get("standard") != STANDARD:
        errors.append(f"{MANIFEST}: standard must be {STANDARD!r}")
    if not (isinstance(manifest.get("issuer"), str) and manifest["issuer"].strip()):
        errors.append(f"{MANIFEST}: issuer is required (who answers for this folder)")
    if _date(manifest.get("issued")) is None:
        errors.append(f"{MANIFEST}: issued must be a date (YYYY-MM-DD)")
    if "rights" in manifest:
        _rights(f"{MANIFEST} rights", manifest["rights"], errors)
    if "notices" in manifest:
        _notices(f"{MANIFEST} notices", manifest["notices"], errors)
    items = manifest.get("items", [])
    if not isinstance(items, list):
        errors.append(f"{MANIFEST}: items must be a list")
        items = []
    seen = set()
    for n, item in enumerate(items):
        where = f"{MANIFEST} items[{n}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        _known(where, item, ITEM_KEYS, errors)
        try:
            path = normalize_path(str(item.get("path", "")))
        except ValueError:
            errors.append(f"{where}: path is missing or not a safe relative path")
            continue
        where = f"{MANIFEST} {path}"
        if path in seen:
            errors.append(f"{where}: listed twice")
        seen.add(path)
        if path == MANIFEST:
            errors.append(f"{where}: the manifest cannot describe itself")
        elif path not in files:
            errors.append(f"{where}: no such file in the folder")
        digest = item.get("digest")
        if not (isinstance(digest, str) and DIGEST.match(digest)):
            errors.append(f"{where}: digest must be sha256:<64 lowercase hex>")
        elif path in files and digest != f"sha256:{files[path]}":
            errors.append(f"{where}: digest does not match the file")
        origin = item.get("origin", "unknown")
        if origin not in ORIGINS:
            errors.append(f"{where}: origin must be one of {', '.join(ORIGINS)}")
        reviewer = item.get("reviewed_by")
        if origin == "assisted" and not (isinstance(reviewer, str) and reviewer.strip()):
            errors.append(f"{where}: origin assisted needs reviewed_by (the person who reviewed it)")
        elif "reviewed_by" in item and origin != "assisted":
            errors.append(f"{where}: reviewed_by is only for origin assisted")
        start, end = item.get("valid_from"), item.get("valid_to")
        for key, value in (("valid_from", start), ("valid_to", end)):
            if value is not None and _date(value) is None:
                errors.append(f"{where}: {key} must be a date")
        if _date(start) and _date(end) and _date(start) >= _date(end):
            errors.append(f"{where}: valid_from must be before valid_to")
        if "applies_to" in item and not (isinstance(item["applies_to"], str) and item["applies_to"].strip()):
            errors.append(f"{where}: applies_to must be a non-empty string")
        if "rights" in item:
            _rights(f"{where} rights", item["rights"], errors)
        if "notices" in item:
            _notices(f"{where} notices", item["notices"], errors)
    unlisted = sorted(p for p in files if p != MANIFEST and p not in seen)
    if unlisted:
        warnings.append(f"{len(unlisted)} file(s) not listed: they get the folder defaults and origin 'unknown'")
    if not isinstance(manifest.get("rights"), dict) or "ai_use" not in manifest["rights"]:
        warnings.append("no default ai_use: files without their own ai_use are neither searchable nor sent to models")
    if not isinstance(manifest.get("rights"), dict) or manifest["rights"].get("license", "unknown") == "unknown":
        warnings.append("no default license: derivation and forwarding need a license for each file")
    return errors, warnings


def validate(files: list) -> dict | None:
    """The parsed manifest of a folder (SourceFile list), or None if it has none. Raises KstdError if invalid."""
    found = [f for f in files if f.path == MANIFEST]
    if not found:
        return None
    manifest = parse(found[0].data)
    errors, _ = check(manifest, {f.path: f.sha256 for f in files})
    if errors:
        raise KstdError("; ".join(errors))
    return manifest


def effective(manifest: dict, path: str) -> dict | None:
    """The item information of one file under a valid manifest (None for the manifest file itself)."""
    if path == MANIFEST:
        return None
    item = next((i for i in manifest.get("items", []) if normalize_path(str(i["path"])) == path), None)
    base, own = manifest.get("rights", {}), (item or {}).get("rights", {})
    ai_use = base.get("ai_use", {}) | own.get("ai_use", {})  # stated terms only; allows() treats absent as n
    start, end = _date((item or {}).get("valid_from")), _date((item or {}).get("valid_to"))
    return {
        "issuer": manifest["issuer"],
        "listed": item is not None,
        "origin": (item or {}).get("origin", "unknown"),
        "reviewed_by": (item or {}).get("reviewed_by"),
        "license": own.get("license", base.get("license", "unknown")),
        "holder": own.get("holder", base.get("holder")),
        "ai_use": {k: _yn(v) for k, v in ai_use.items()},
        "personal_data": _pd(own.get("personal_data", base.get("personal_data", "unknown"))),
        "valid_from": start.date().isoformat() if start else None,
        "valid_to": end.date().isoformat() if end else None,
        "applies_to": (item or {}).get("applies_to"),
        "notices": list(manifest.get("notices", [])) + list((item or {}).get("notices", [])),
    }


def is_current(info: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    start, end = _date(info.get("valid_from")), _date(info.get("valid_to"))
    return (start is None or start <= now) and (end is None or now < end)


def allows(info: dict | None, use: str) -> bool:
    """A file without a manifest follows its book policy only (True here)."""
    return info is None or info["ai_use"].get(use) == "y"


def legal_basis(value) -> list[str]:
    """One or more DPV legal-basis codes, separated by spaces or commas (e.g. `eu-gdpr:A6-1-b`)."""
    codes = [c for c in re.split(r"[\s,]+", value.strip()) if c] if isinstance(value, str) else []
    wrong = [c for c in codes if c not in LEGAL_BASES]
    if not codes or wrong:
        raise KstdError(f"legal basis must be DPV codes such as eu-gdpr:A6-1-b or eu-gdpr:A9-2-a"
                        f"{f' (not valid: {wrong[0]})' if wrong else ''}")
    return sorted(set(codes))


class Rights:
    """Item information per (book, content id, path) within one request. Content versions are immutable, so a
    manifest is read and parsed at most once per version here."""

    def __init__(self, conn):
        self.conn, self._manifests = conn, {}

    def manifest(self, book: str, content_id: str) -> dict | None:
        key = (book, content_id)
        if key not in self._manifests:
            from . import catalog  # catalog imports kstd for publication checks
            data = catalog.read_file(self.conn, book, content_id, MANIFEST)
            self._manifests[key] = parse(data) if data is not None else None
        return self._manifests[key]

    def info(self, book: str, content_id: str, path: str) -> dict | None:
        manifest = self.manifest(book, content_id)
        if manifest is None:
            return None
        info = effective(manifest, path)
        return info and {**info, "current": is_current(info)}

    def allows(self, book: str, content_id: str, path: str, use: str) -> bool:
        return allows(self.info(book, content_id, path), use)


def init(files: list, issuer: str, today: date | None = None) -> str:
    """A starting manifest for a folder: every file listed with its digest, all rights unknown, origin unknown."""
    lines = [
        f"standard: {STANDARD}",
        f"issuer: {yaml.safe_dump(issuer, default_style=chr(34)).strip()}   # who answers for this folder",
        f"issued: {(today or date.today()).isoformat()}",
        "rights:                               # defaults for every item",
        "  license: unknown                    # an SPDX id, e.g. CC-BY-4.0; unknown gives no permission",
        "  holder: " + yaml.safe_dump(issuer, default_style=chr(34)).strip(),
        "  ai_use: {search: y, ai_input: n, train: n}   # absent = not stated; decisions treat it as n",
        "  personal_data: unknown              # yes | no | synthetic | unknown (= yes)",
        "items:",
    ]
    for f in sorted(files, key=lambda f: f.path):
        if f.path == MANIFEST:
            continue
        lines += [f"  - path: {yaml.safe_dump(f.path, default_style=chr(34)).strip()}",
                  f"    digest: sha256:{hashlib.sha256(f.data).hexdigest()}",
                  "    origin: unknown                   # human | assisted (+ reviewed_by) | model | unknown (= model)"]
    return "\n".join(lines) + "\n"
