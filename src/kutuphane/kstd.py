"""kstd L0: the `kstd.yaml` manifest (docs/11 §7–§8). It describes a folder: who answers for it, the rights of
its files, their origin, validity and applicability.

A book whose files contain `kstd.yaml` at the root follows it. Validation has three separate results (docs/11 §7):
- **readable**: a manifest that cannot be read unambiguously (YAML tricks, wrong types), a wrong envelope
  (`standard`, `issuer`, a file digest) or a term with a wrong value blocks publication (fail closed);
- **valid evidence**: an unknown field (not `x-`) is ignored, and an origin claim without its evidence
  (`assisted` without `reviewed_by`, `tool` without `software_agent`) counts as `unknown` (= model); reviewer or
  generator data for another origin is ignored. Each one gives a notice on the item and a `kstd-check` warning,
  and publication goes on;
- **authorized**: each operation reads only the fields that it needs:
  - a file with `ai_use.search` not `y` is not indexed;
  - a passage with `ai_use.ai_input` not `y` is never sent to a model (embedding, reranking, answers);
  - a file with `personal_data` not `no` or `synthetic` is exported only with a recorded legal basis (DPV codes);
  - an exported package marks files with origin `model` or `unknown` as AI-generated; `assisted` files (model
    output that a named person reviewed) are not marked and carry `reviewed_by` (EU AI Act Art. 50(4)); `tool`
    files (made by software that runs only written rules, or records events; no learned model) are not marked and
    carry their `software_agent` (docs/17, D63); `human` files carry their optional `entered_by` and
    `confirmed_by` (docs/25 §7.6: who entered the words, and the person who confirmed them as their own);
  - search results, citations and answers show the item information.

A book without `kstd.yaml` behaves as before: only its book policy applies. `ai_use` keeps three states: an
absent term is "not stated" and is reported as absent, but every decision treats it as `n`; an unknown license
gives no permission (docs/11 §4 rule 3, §5). The `kstd.yaml` issuer publishes into this node, so its `synthetic`
declaration is trusted here.

The SPDX identifiers in `spdx_ids.txt` come from https://github.com/spdx/license-list-data (`json/licenses.json`).
"""
import hashlib
import re
from datetime import date, datetime, time, timezone
from pathlib import Path

import yaml

from .ids import normalize_path

MANIFEST = "kstd.yaml"
STANDARD = "kstd/0.3"
READABLE = ("kstd/0.2", STANDARD)  # 0.3 only relaxes the 0.2 validation (docs/11 §11): a 0.2 manifest reads the same
MAX_MANIFEST_BYTES = 1024 * 1024
AI_USE = ("search", "ai_input", "train")
ORIGINS = ("human", "assisted", "model", "tool", "unknown")
AI_GENERATED = ("model", "unknown")  # `unknown` counts as `model` (docs/11 §5)
PERSONAL_DATA = ("yes", "no", "synthetic", "unknown")
NO_LEGAL_BASIS_NEEDED = ("no", "synthetic")
# DPV legal bases for GDPR (https://w3id.org/dpv/legal/eu/gdpr): Art. 6(1)(a)–(f) and Art. 9(2)(a)–(j).
LEGAL_BASES = frozenset([f"eu-gdpr:A6-1-{c}" for c in "abcdef"] + [f"eu-gdpr:A9-2-{c}" for c in "abcdefghij"])
RIGHTS_KEYS = {"license", "holder", "ai_use", "personal_data"}
TOP_KEYS = {"standard", "issuer", "issued", "rights", "notices", "items"}
ITEM_KEYS = {"path", "digest", "origin", "reviewed_by", "software_agent", "entered_by", "confirmed_by", "valid_from",
             "valid_to", "applies_to", "rights", "notices"}
HUMAN_DETAILS = ("entered_by", "confirmed_by")  # optional for `human`: the provenance of a confirmation (docs/25 §7.6)
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


def _unknown(where: str, mapping, allowed) -> list[str]:
    """Notices for unknown fields. They are ignored: a field outside the standard never decides (docs/11 §2)."""
    return [f"{where}: unknown field {key!r} ignored (extensions start with 'x-')" for key in mapping
            if key not in allowed and not str(key).startswith("x-")] if isinstance(mapping, dict) else []


def _rights_unknown(where: str, rights) -> list[str]:
    if not isinstance(rights, dict):
        return []
    return _unknown(where, rights, RIGHTS_KEYS) + _unknown(f"{where} ai_use", rights.get("ai_use"), AI_USE)


def _folder_notices(manifest: dict) -> list[str]:
    return _unknown(MANIFEST, manifest, TOP_KEYS) + _rights_unknown(f"{MANIFEST} rights", manifest.get("rights"))


def _claims(item: dict, where: str) -> tuple[dict, list[str]]:
    """The origin claim of one item as decisions use it, and a notice for each claim that is not valid evidence
    (docs/11 §7). An origin without its evidence counts as `unknown` (= model); data for another origin is ignored."""
    origin, notices = item.get("origin", "unknown"), _unknown(where, item, ITEM_KEYS)
    notices += _rights_unknown(f"{where} rights", item.get("rights"))
    claim = {"origin": origin, "reviewed_by": None, "software_agent": None, "entered_by": None, "confirmed_by": None}
    reviewer, agent = item.get("reviewed_by"), item.get("software_agent")
    if origin == "assisted":
        if isinstance(reviewer, str) and reviewer.strip():
            claim["reviewed_by"] = reviewer
        else:
            claim["origin"] = "unknown"
            notices.append(f"{where}: origin 'assisted' not trusted: it needs reviewed_by (the person who reviewed "
                           f"it); handled as unknown")
    elif "reviewed_by" in item:
        notices.append(f"{where}: reviewed_by ignored: it is only for origin assisted")
    if origin == "tool":
        if _software_agent_ok(agent):
            claim["software_agent"] = agent
        else:
            claim["origin"] = "unknown"
            notices.append(f"{where}: origin 'tool' not trusted: it needs software_agent: {{name, version}} of the "
                           f"generator or recorder, as strings (quote a version such as \"1.10\"); handled as unknown")
    elif "software_agent" in item:
        notices.append(f"{where}: software_agent ignored: it is only for origin tool")
    for key in HUMAN_DETAILS:  # optional: `human` stays `human` without them; ignored for another origin
        if key not in item:
            continue
        if origin != "human":
            notices.append(f"{where}: {key} ignored: it is only for origin human")
        elif isinstance(item[key], str) and item[key].strip():
            claim[key] = item[key]
        else:
            notices.append(f"{where}: {key} ignored: it must be a non-empty string")
    return claim, notices


def _license_ok(value) -> bool:
    """`unknown`, or an SPDX expression of ids and LicenseRef-… joined by AND/OR, with balanced parentheses.
    WITH exceptions are not supported in kstd/0.3."""
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


def _software_agent_ok(value) -> bool:
    """{name, version}: both non-empty STRINGS. A YAML number would lose the exact version (1.10 → 1.1), so a
    numeric-looking version must be quoted: version: "1.10"."""
    return (isinstance(value, dict) and set(value) == {"name", "version"}
            and all(isinstance(value[k], str) and value[k].strip() for k in ("name", "version")))


def instant(value) -> datetime | None:
    """A date or timestamp as a timezone-aware datetime; a date alone, or a timestamp without a zone, is UTC (a date
    is its 00:00 UTC). None for anything else."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return instant(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _bound(value) -> str | None:
    """A validity bound as text, without losing its time (Astra review #12: `valid_from: 2026-10-27T23:59:00Z` cut to
    its date was current at noon that day). 00:00 UTC is written as the date alone, any other time as a UTC
    timestamp."""
    moment = instant(value)
    if moment is None:
        return None
    moment = moment.astimezone(timezone.utc)
    return moment.date().isoformat() if moment.timetz() == time(tzinfo=timezone.utc) else \
        moment.isoformat().replace("+00:00", "Z")


def _rights(where: str, rights, errors: list) -> None:
    if not isinstance(rights, dict):
        errors.append(f"{where}: rights must be a mapping")
        return
    if "license" in rights and not _license_ok(rights["license"]):
        errors.append(f"{where}: license {rights['license']!r} is not an SPDX expression (AND/OR of SPDX ids or "
                      f"LicenseRef-…; WITH is not supported) or 'unknown'")
    if "holder" in rights and not (isinstance(rights["holder"], str) and rights["holder"].strip()):
        errors.append(f"{where}: holder must be a non-empty string")
    if "ai_use" in rights:
        use = rights["ai_use"]
        if not isinstance(use, dict) or any(k in AI_USE and _yn(v) not in ("y", "n") for k, v in use.items()):
            errors.append(f"{where}: ai_use terms take y or n ({', '.join(AI_USE)})")
    if "personal_data" in rights and _pd(rights["personal_data"]) not in PERSONAL_DATA:
        errors.append(f"{where}: personal_data must be one of {', '.join(PERSONAL_DATA)}")


def _notices(where: str, notices, errors: list) -> None:
    if not isinstance(notices, list) or not all(isinstance(n, str) and n.strip() for n in notices):
        errors.append(f"{where}: notices must be a list of non-empty strings")


def check(manifest: dict, files: dict[str, str]) -> tuple[list[str], list[str]]:
    """Errors (the manifest is not readable: publication is refused) and warnings (publication goes on; this
    includes every claim that is not valid evidence, with the notice that its item shows). `files`: {normalized
    path: sha256 hex} of the folder."""
    errors, warnings = [], _folder_notices(manifest)
    if manifest.get("standard") not in READABLE:
        errors.append(f"{MANIFEST}: standard must be {STANDARD!r} (or {READABLE[0]!r})")
    if not (isinstance(manifest.get("issuer"), str) and manifest["issuer"].strip()):
        errors.append(f"{MANIFEST}: issuer is required (who answers for this folder)")
    if "issued" in manifest and instant(manifest["issued"]) is None:
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
        if item.get("origin", "unknown") not in ORIGINS:
            errors.append(f"{where}: origin must be one of {', '.join(ORIGINS)}")
        warnings += _claims(item, where)[1]
        start, end = item.get("valid_from"), item.get("valid_to")
        for key, value in (("valid_from", start), ("valid_to", end)):
            if value is not None and instant(value) is None:
                errors.append(f"{where}: {key} must be a date")
        if instant(start) and instant(end) and instant(start) >= instant(end):
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
    start, end = (item or {}).get("valid_from"), (item or {}).get("valid_to")
    claim, untrusted = _claims(item or {}, f"{MANIFEST} {path}")
    return {
        "issuer": manifest["issuer"],
        "listed": item is not None,
        **claim,
        "license": own.get("license", base.get("license", "unknown")),
        "holder": own.get("holder", base.get("holder")),
        "ai_use": {k: _yn(v) for k, v in ai_use.items() if k in AI_USE},
        "personal_data": _pd(own.get("personal_data", base.get("personal_data", "unknown"))),
        "valid_from": _bound(start),
        "valid_to": _bound(end),
        "applies_to": (item or {}).get("applies_to"),
        "notices": list(manifest.get("notices", [])) + list((item or {}).get("notices", []))
                   + _folder_notices(manifest) + untrusted,
    }


def is_current(info: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    start, end = instant(info.get("valid_from")), instant(info.get("valid_to"))
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


def _quoted(value: str) -> str:
    return yaml.safe_dump(value, default_style='"', allow_unicode=True, width=1_000_000).strip()


def init(files: list, issuer: str, today: date | None = None) -> str:
    """A starting manifest for a folder: every file listed with its digest, all rights unknown, no `ai_use` term
    stated (deny: nothing is indexed or sent to a model until the issuer states the terms, D74), origin unknown."""
    lines = [
        f"standard: {STANDARD}",
        f"issuer: {_quoted(issuer)}   # who answers for this folder",
        f"issued: {(today or date.today()).isoformat()}",
        "rights:                               # defaults for every item",
        "  license: unknown                    # an SPDX id, e.g. CC-BY-4.0; unknown gives no permission",
        "  holder: " + _quoted(issuer),
        "  # ai_use: {search: y|n, ai_input: y|n, train: y|n}   # not stated = deny: no file is indexed or sent to a model",
        "  personal_data: unknown              # yes | no | synthetic | unknown (= yes)",
        "items:",
    ]
    for f in sorted(files, key=lambda f: f.path):
        if f.path == MANIFEST:
            continue
        lines += [f"  - path: {_quoted(f.path)}",
                  f"    digest: sha256:{hashlib.sha256(f.data).hexdigest()}",
                  "    origin: unknown                   # human | assisted (+ reviewed_by) | model | tool (+ software_agent) | unknown (= model)"]
    return "\n".join(lines) + "\n"
