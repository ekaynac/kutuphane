#!/usr/bin/env python3
"""Labelling v5, automatic gold, slice `auto/docs` (docs/20 §3.1, D67).

Builds about 115 whole-document cases from four sources that declare status,
supersession and approval in their own metadata:

- Python PEPs (python/peps at a pinned commit; peps.python.org JSON APIs)
- IETF RFCs (rfc-editor.org JSON + text; datatracker IESG ballot positions)
- Kubernetes KEPs (kubernetes/enhancements at a pinned commit; PRR files)
- mozilla/fxa MADR ADRs (pinned commit)

Output (git-ignored): research/labelling-v5/auto/
  docs/<case_id>/case.json + file copies
  docs.cases.jsonl, docs.gold.jsonl

Rules kept here (docs/research/2026-10-26-real-gold-sources.md §1-§2):
- gold is the SOURCE declaration; it never goes into case.json evidence;
- `Updates` is not supersession; an assigned reviewer/approver is not an approval;
  a publication date is not validity;
- a Final PEP with Superseded-By stays accepted (successor in another scope);
- KEP approver comes only from the PRR file;
- a decided PEP is pinned to the last revision at or before the decision post (artifact_status vs
  current_source_status);
- the item licence comes only from a declaration that covers the file; a repository LICENSE is `repo_license`
  (kstd §5);
- RFC obsoletion keeps its scope ("portions of" = partial); `updates` stays a separate relation;
- rejected = withdrawn + acceptance_reason + prior_acceptance false; a decision body is `decided_by`, never
  inferred;
- fetched content is never executed.

Usage: python3 build.py [--out DIR] [--cache DIR]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

# ---------------------------------------------------------------- pins
PEP_REPO = "python/peps"
PEP_SHA = "227e111a01246a83de569e0053ddfcf6a978c5e6"  # main, 2026-10-26
KEP_REPO = "kubernetes/enhancements"
KEP_SHA = "ea3e81a0d41dd3df7dae584ea584c31de56cd3cb"  # master, 2026-10-26
FXA_REPO = "mozilla/fxa"
FXA_SHA = "ce9627cc7ed7aa4ec89e50a79a57c72458bb9f6a"  # main, 2026-10-26

PEPS_JSON = "https://peps.python.org/api/peps.json"
RELEASE_CYCLE_JSON = "https://peps.python.org/api/release-cycle.json"
RFC_EDITOR = "https://www.rfc-editor.org"
DATATRACKER = "https://datatracker.ietf.org"

MAX_BYTES = 2 * 1024 * 1024
TODAY = dt.date(2026, 10, 26)

# ---------------------------------------------------------------- selection
PEP_CHAINS = {
    "python/peps:248-249-dbapi": [248, 249],
    "python/peps:333-3333-wsgi": [333, 3333],
    "python/peps:409-415": [409, 415],
    "python/peps:metadata-241-566": [241, 314, 345, 426, 566],
    "python/peps:manylinux-600": [513, 571, 599, 600],
    "python/peps:annotations-563": [563, 649, 749],
    "python/peps:finally-601-765": [601, 765],
}
PEP_APPROVAL = [700, 714, 735, 770, 752, 703, 688, 701, 772, 794]
PEP_ENDED = [6, 501, 722, 759, 736]
PEP_RELEASE = [373, 537, 619, 664, 745]

RFC_FAMILIES = {
    "ietf/rfc:tls": ("supersession", [4346, 5246, 8446, 9846]),
    "ietf/rfc:json": ("supersession", [4627, 7158, 7159, 8259]),
    "ietf/rfc:smtp": ("supersession", [2821, 5321]),
    "ietf/rfc:pkix": ("supersession", [3280, 5280]),
    "ietf/rfc:http-partial": ("supersession", [2616, 7230, 7234, 9110, 9111, 9112]),
    "ietf/rfc:3986": ("updates", [3986]),
    "ietf/rfc:6749": ("updates", [6749]),
    "ietf/rfc:7519": ("updates", [7519]),
    "ietf/rfc:4291": ("updates", [4291]),
    "ietf/rfc:2119": ("updates", [2119]),
    "ietf/rfc:5322": ("updates", [5322]),
    "ietf/rfc:isatap": ("stream-approval", [4214, 5214]),
    "ietf/rfc:ldap-printer": ("stream-approval", [3712, 7612]),
    "ietf/rfc:sntp": ("stream-approval", [4330]),
    "ietf/rfc:security-glossary": ("stream-approval", [4949]),
}

KEP_FAMILIES = {
    "k8s/keps:2451-1205": ["keps/sig-storage/2451-service-account-token-volumes",
                           "keps/sig-auth/1205-bound-service-account-tokens"],
    "k8s/keps:3130-3299": ["keps/sig-auth/3130-kms-observability",
                           "keps/sig-auth/3299-kms-v2-improvements"],
    "k8s/keps:536-2433": ["keps/sig-network/536-topology-aware-routing",
                          "keps/sig-network/2433-topology-aware-hints"],
    "k8s/keps:2133": ["keps/sig-cloud-provider/2133-out-of-tree-credential-provider",
                      "keps/sig-node/2133-kubelet-credential-providers"],
    "k8s/keps:1177-1739": ["keps/sig-cluster-lifecycle/kubeadm/1177-kubeadm-with-kustomize",
                           "keps/sig-cluster-lifecycle/kubeadm/1739-customization-with-patches"],
    "k8s/keps:5339": ["keps/sig-multicluster/5339-clusterprofile-plugin-credentials"],
    "k8s/keps:4153": ["keps/sig-api-machinery/4153-declarative-validation"],
}
KEP_WITHDRAWN = [
    "keps/sig-api-machinery/2558-publish-version-openapi",
    "keps/sig-auth/600-dynamic-audit-configuration",
    "keps/sig-network/2593-multiple-cluster-cidrs",
    "keps/sig-network/2943-networkpolicy-status",
    "keps/sig-node/3063-dynamic-resource-allocation",
]
KEP_IMPLEMENTED = [
    "keps/sig-network/1138-ipv6",  # resolved by number below; no PRR file (trap)
    "keps/sig-node/1287-in-place-update-pod-resources",
    "keps/sig-network/3070-reserved-service-ip-range",
    "keps/sig-node/3545-improved-multi-numa-alignment",
    "keps/sig-apps/2232-suspend-jobs",
    "keps/sig-api-machinery/3488-cel-admission-control",
    "keps/sig-auth/4601-authorize-with-selectors",
    "keps/sig-windows/2258-node-log-query",
]
# Successors that the source declares only in prose or through an old path.
KEP_SUCCESSOR_NOTES = {
    "keps/sig-multicluster/5339-clusterprofile-plugin-credentials": (
        "https://github.com/kubernetes/enhancements/tree/{sha}/keps/sig-multicluster/4322-cluster-inventory",
        "README.md prose: 'This KEP has been replaced by KEP-4322'; kep.yaml superseded-by is empty"),
    "keps/sig-cloud-provider/2133-out-of-tree-credential-provider": (
        None,
        "successor kep.yaml (sig-node/2133) `replaces` the old path "
        "keps/sig-cloud-provider/20191004-out-of-tree-credential-providers.md; commit cb1e56b9e9 "
        "('Migrate some cloud-provider keps to new template') moved that file to this folder"),
    "keps/sig-cluster-lifecycle/kubeadm/1177-kubeadm-with-kustomize": (
        None,
        "README.md note 'this KEP was replaced by the KEP tracked in #1739'; 1739 kep.yaml `replaces` "
        "the old file path of this KEP"),
}

ADR_FAMILIES = {
    "mozilla/fxa:settings-auth": ["0014-auth-for-settings-redesign.md",
                                  "0017-switch-settings-auth-to-sessiontoken.md"],
    "mozilla/fxa:hawk": ["0022-deprecate-hawk.md", "0050-bearer-token-prefix-naming.md"],
    "mozilla/fxa:graphql": ["0016-use-graphql-and-apollo-for-settings-redesign.md",
                            "0044-use-rest-over-gql-when-convenient.md",
                            "0047-remove-graphql-from-fxa-settings.md"],
}
ADR_SINGLE = [
    "0000-use-markdown-architectural-decision-records.md",
    "0007-subscription-claim-jwt-access-token.md",
    "0008-redis-lua-scripts.md",
    "0009-testing-stacks.md",
    "0012-next-two-factor-authentication.md",
    "0025-retire-fxa-auth-db-mysql.md",
    "0030-disable-squash-and-merge.md",
    "0038-use-esbuild-in-production.md",
    "0041-gcp-cloud-tasks-for-job-queuing.md",
    "0042-use-node-oidc-for-oauth.md",
    "0043-react-functional-tests.md",
    "0046-monorepo-split.md",
    "0048-refresh-tokens-and-account-level-authorization.md",
]
# ADRs with no Deciders line that still name a real person.
ADR_PD_NOTE = {
    "0000-use-markdown-architectural-decision-records.md":
        "No Deciders line; the text names only a cited author (Michael Nygard) and a GitHub user in a URL. "
        "personal_data 'yes' is our reading, not a source declaration.",
}

# ---------------------------------------------------------------- fetch helpers
CACHE: Path = Path("/tmp")
UA = {"User-Agent": "kobra-labelling-v5-auto-docs/1.0 (research; contact via github ekaynac)"}


def _cache_path(key: str) -> Path:
    return CACHE / hashlib.sha256(key.encode()).hexdigest()


def get(url: str) -> bytes:
    cp = _cache_path(url)
    if cp.exists():
        return cp.read_bytes()
    req = urllib.request.Request(url, headers=UA)
    last: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            cp.write_bytes(data)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            last = e
        except Exception as e:  # network errors: retry
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {url}: {last}")


def get_json(url: str):
    return json.loads(get(url))


def gh(path: str):
    cp = _cache_path("gh:" + path)
    if cp.exists():
        return json.loads(cp.read_bytes())
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(f"gh api {path}: {out.stderr.strip()[:300]}")
    cp.write_text(out.stdout)
    return json.loads(out.stdout)


def raw_url(repo: str, sha: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{sha}/{path}"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def dtj(path: str):
    sep = "&" if "?" in path else "?"
    return get_json(DATATRACKER + path + sep + "format=json")


# ---------------------------------------------------------------- case model
class Case:
    def __init__(self, cid, group, source, family, operation, questions, why):
        self.id = cid
        self.group = group
        self.source = source
        self.family = family
        self.operation = operation
        self.questions = questions
        self.why = why
        self.files: list[dict] = []
        self.blobs: dict[str, bytes] = {}
        self.evidence: dict = {}
        self.statements: list[dict] = []
        self.gold: dict = {}
        self.gold_source: list[str] = []
        self.notes: list[str] = []

    def add_file(self, local_path, data: bytes, *, path, url, ref, license_item,
                 copy=True, redistribute=True, note=None):
        if len(data) > MAX_BYTES:
            raise ValueError(f"{self.id}: {local_path} is {len(data)} bytes, over the 2 MB limit")
        f = {"path": path, "url": url, "ref": ref, "sha256": sha256(data), "bytes": len(data),
             "copy": copy, "local_path": local_path if copy else None,
             "license_item": license_item, "redistribute": redistribute}
        if note:
            f["note"] = note
        self.files.append(f)
        if copy:
            self.blobs[local_path] = data
        # One item statement per file: identity only, never an answer under test.
        self.statements.append({"kind": "item", "issuer": self.source,
                                "body": {"path": path, "digest": "sha256:" + f["sha256"],
                                         "source_url": url, "ref": ref}})

    def case_json(self):
        return {"id": self.id, "set": "auto", "group": self.group, "source": self.source,
                "family": self.family, "operation": self.operation, "questions": self.questions,
                "why_selected": self.why, "files": self.files, "evidence": self.evidence,
                "statements": self.statements}

    def gold_json(self):
        gold = {**self.gold, "decided_by": self.gold.get("decided_by")}
        return {"id": self.id, "gold": gold, "gold_source": "; ".join(self.gold_source),
                "notes": " ".join(self.notes)}


# ================================================================ PEPs
def pep_header(text: str) -> dict:
    h, key = {}, None
    for line in text.splitlines():
        if not line.strip():
            if h:
                break
            continue
        m = re.match(r"^([A-Za-z-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            h[key] = m.group(2).strip()
        elif key and line[:1] in (" ", "\t"):
            h[key] += " " + line.strip()
    return h


def pep_res_date(h: dict):
    m = re.search(r"(\d{1,2}-[A-Z][a-z]{2}-\d{4})", h.get("Resolution", ""))
    return dt.datetime.strptime(m.group(1), "%d-%b-%Y").date() if m else None


def pep_res_url(h: dict):
    m = re.search(r"(https?://[^\s<>`]+)", h.get("Resolution", ""))
    return m.group(1).rstrip(">`_") if m else None


def pep_licence(text: str) -> str:
    if "CC0-1.0-Universal" in text:
        return "CC0-1.0"
    if re.search(r"public\s+domain", text, re.I):
        return "LicenseRef-PublicDomain"
    return "unknown"


def pep_delegate(h: dict):
    for k in ("PEP-Delegate", "BDFL-Delegate"):
        if h.get(k):
            return k, h[k]
    return None, None


def person_name(s: str) -> str:
    return re.sub(r"\s*<[^>]*>", "", s).strip()


def pep_paths(n: int):
    return [f"peps/pep-{n:04d}.rst", f"pep-{n:04d}.rst", f"pep-{n:04d}.txt"]


def pep_commits(n: int):
    out = set()
    for p in pep_paths(n):
        page = 1
        while True:
            cs = gh(f"repos/{PEP_REPO}/commits?path={p}&sha={PEP_SHA}&per_page=100&page={page}")
            for c in cs:
                out.add((c["commit"]["committer"]["date"], c["sha"], p))
            if len(cs) < 100:
                break
            page += 1
    return sorted(out)


def pep_decision_time(url: str | None, rdate: dt.date):
    """The decision timestamp: the created_at of the discuss.python.org post that the Resolution header links.

    Falls back to the start of the Resolution day (UTC) when the link is not a Discourse post, or when the post
    date is more than one day from the Resolution date. Returns (iso timestamp, precision, provenance)."""
    m = re.match(r"https://discuss\.python\.org/t/(?:([^/]+)/)?(\d+)(?:/(\d+))?/?$", url or "")
    if m:
        slug, topic, post = m.groups()
        if slug and slug.isdigit():  # /t/<topic>/<post>
            topic, post = slug, topic
        pn = int(post) if post else 1
        purl = f"https://discuss.python.org/posts/by_number/{topic}/{pn}.json"
        try:
            created = get_json(purl)["created_at"]
        except (urllib.error.HTTPError, KeyError):
            created = None
        if created and abs((dt.date.fromisoformat(created[:10]) - rdate).days) <= 1:
            return created, "second", f"created_at of post {pn} in topic {topic} ({purl})"
    return f"{rdate.isoformat()}T00:00:00Z", "day", "start of the Resolution date (no usable post timestamp)"


def pep_version_at(n: int, when: str):
    """The last revision whose commit (committer date) is at or before `when`."""
    before = [c for c in pep_commits(n) if c[0] <= when]
    if not before:
        return None
    date, sha, path = before[-1]
    return sha, path, date, get(raw_url(PEP_REPO, sha, path))


def pep_status_history(n: int) -> list[str]:
    """The Status header of every revision of the PEP file, oldest first."""
    out = []
    for _, sha, path in pep_commits(n):
        try:
            out.append(pep_header(get(raw_url(PEP_REPO, sha, path)).decode("utf-8", "replace")).get("Status"))
        except urllib.error.HTTPError:
            continue
    return out


def pep_case_id(n: int) -> str:
    return f"auto-pep-{n:04d}"


def build_peps(cases: list[Case], meta: dict):
    peps_raw = get(PEPS_JSON)
    rc_raw = get(RELEASE_CYCLE_JSON)
    peps = json.loads(peps_raw)
    rc = json.loads(rc_raw)
    meta["peps_json_sha256"] = sha256(peps_raw)
    meta["release_cycle_json_sha256"] = sha256(rc_raw)
    rc_by_pep = {str(v["pep"]): (ver, v) for ver, v in rc.items()}

    selected: dict[int, tuple[str, str]] = {}
    for fam, nums in PEP_CHAINS.items():
        for n in nums:
            selected[n] = (fam, "supersession")
    for n in PEP_APPROVAL:
        selected[n] = (f"python/peps:{n}", "approval")
    for n in PEP_ENDED:
        selected[n] = (f"python/peps:{n}", "withdrawal")
    for n in PEP_RELEASE:
        selected[n] = (f"python/peps:release-{n}", "validity")
    # successor families for ended PEPs with a successor outside the set
    selected[501] = ("python/peps:501-750", "withdrawal")
    selected[722] = ("python/peps:722-723", "withdrawal")

    def ref_for(m: int) -> str:
        return pep_case_id(m) if m in selected else f"https://peps.python.org/pep-{m:04d}/"

    for n, (family, group) in sorted(selected.items()):
        cur_path = f"peps/pep-{n:04d}.rst"
        cur = get(raw_url(PEP_REPO, PEP_SHA, cur_path))
        h = pep_header(cur.decode())
        status = peps[str(n)]["status"]
        rdate = pep_res_date(h)
        version, decision = None, None
        if status in ("Final", "Accepted", "Active") and not h.get("Superseded-By") and pep_res_url(h) and rdate:
            decision = pep_decision_time(pep_res_url(h), rdate)
            version = pep_version_at(n, decision[0])

        if version:
            vsha, vpath, vdate, data = version
            text_note = (f"Text pinned at commit {vsha[:12]} ({vdate}), the last revision at or before the "
                         f"decision time {decision[0]} ({decision[2]}). This is the text that was decided; "
                         f"later commits record the decision and can also edit the text.")
        else:
            vsha, vpath, vdate, data = PEP_SHA, cur_path, None, cur
            text_note = "Text pinned at the current main commit."
            if status in ("Final", "Accepted") and pep_res_url(h) and not rdate:
                text_note += " The Resolution header has no date, so no decision-time version was taken."
        th = pep_header(data.decode("utf-8", "replace"))
        lic = pep_licence(data.decode("utf-8", "replace"))

        op = {"supersession": "search", "withdrawal": "search",
              "approval": "model-answer", "validity": "model-answer"}[group]
        qs = {"supersession": ["Q13", "Q17", "Q21"], "withdrawal": ["Q13"],
              "approval": ["Q16", "Q24"], "validity": ["Q15", "Q17"]}[group]
        sup = [int(x) for x in re.findall(r"\d+", h.get("Superseded-By", ""))]
        rep = [int(x) for x in re.findall(r"\d+", h.get("Replaces", ""))]
        dkey, dval = pep_delegate(h)

        why = {
            "supersession": (
                f"PEP {n} is in a replacement chain ({family.split(':')[1]}); the library must serve the "
                f"current text and mark the replaced one." if status != "Final" or not sup else
                f"PEP {n} is Final and has Superseded-By: the successor covers another scope, so this is "
                f"not a withdrawal."),
            "approval": (f"PEP {n} names a delegate who decided it; the answer must name the real approver."
                         if dkey else
                         f"PEP {n} has a Resolution record but names no delegate; the metadata names no "
                         f"decision maker, so no approver may be invented."),
            "withdrawal": f"PEP {n} ended without being in force ({status}); it must not be served as current.",
            "validity": f"Release PEP {n} has a validity window in release-cycle.json; a model answer must "
                        f"say whether that release is still supported on the evaluation date.",
        }[group]
        c = Case(pep_case_id(n), group, PEP_REPO, family, op, qs, why)
        c.add_file(f"pep-{n:04d}.rst", data, path=vpath, url=raw_url(PEP_REPO, vsha, vpath),
                   ref={"repo": PEP_REPO, "commit": vsha, "path": vpath}, license_item=lic,
                   copy=True, redistribute=lic != "unknown")
        c.evidence = {"title": th.get("Title"), "pep_type": th.get("Type"), "created": th.get("Created"),
                      "python_version": th.get("Python-Version"), "discussions_to": th.get("Discussions-To")}

        g = c.gold
        g["source_status"] = status
        g["current_source_status"] = status
        g["artifact_status"] = th.get("Status")
        if status in ("Final", "Accepted", "Active"):
            g["acceptance"] = "accepted"
        elif status in ("Superseded", "Withdrawn", "Rejected"):
            g["acceptance"] = "withdrawn"
            g["acceptance_reason"] = status.lower()
            if status == "Rejected":
                g["prior_acceptance"] = False
                c.gold_source.append("prior_acceptance: Rejected means the PEP was never accepted (PEP 1)")
            else:
                hist = pep_status_history(n)
                g["prior_acceptance"] = any(s in ("Accepted", "Final", "Active") for s in hist)
                c.gold_source.append(f"prior_acceptance: Status headers of all {len(hist)} revisions in the git "
                                     f"history ({' > '.join(dict.fromkeys(s for s in hist if s))})")
        else:
            g["acceptance"] = "pending"
        g["superseded_by"] = [ref_for(m) for m in sup] or None
        if sup:
            g["supersession_scope"] = "other-scope" if status in ("Final", "Active") else "full"
        if rep:
            g["replaces"] = [ref_for(m) for m in rep]
        # approver: only a person that the source names (delegate header). A body is never inferred.
        g["approver"] = None
        g["decided_by"] = None
        if pep_res_url(h) and dval and status != "Withdrawn":
            g["decided_by"] = [{"name": person_name(dval), "kind": "person", "source": f"{dkey} header"}]
            c.gold_source.append(f"decided_by: {dkey} header")
        if status in ("Final", "Accepted", "Active", "Superseded") and pep_res_url(h):
            if dval:
                g["approver"] = [person_name(dval)]
                g["approver_kind"] = "person"
                c.gold_source.append(f"approver: {dkey} header")
            else:
                c.notes.append("A Resolution record exists, but no delegate header: the metadata names no "
                               "decision maker. The approver is not inferred (for example, the Steering "
                               "Council from the date).")
            g["approval_date"] = rdate.isoformat() if rdate else None
            g["approval_record"] = pep_res_url(h)
            if decision:
                g["decision_time"] = decision[0]
                g["decision_time_precision"] = decision[1]
                c.gold_source.append(f"decision_time: {decision[2]}")
        elif status in ("Rejected", "Withdrawn") and pep_res_url(h):
            g["decision_date"] = rdate.isoformat() if rdate else None
            g["decision_record"] = pep_res_url(h)
            if status == "Withdrawn":
                c.notes.append("Withdrawn by the authors: the delegate (if any) did not decide it.")
            elif not dval:
                c.notes.append("Rejected with a Resolution record but no delegate header: the metadata names "
                               "no decision maker.")
        # validity: only release PEPs, from release-cycle.json
        if group == "validity":
            ver, r = rc_by_pep[str(n)]
            g["valid_from"] = r["first_release"]
            g["valid_to"] = r["end_of_life"]
            g["valid_to_precision"] = "day" if len(r["end_of_life"]) == 10 else "month"
            eol_start = dt.date.fromisoformat(r["end_of_life"] + ("-01" if len(r["end_of_life"]) == 7 else ""))
            g["valid_to_planned"] = eol_start > TODAY
            g["applies_to"] = f"CPython {ver}"
            g["release_status"] = r["status"]
            c.gold_source.append(f"validity: {RELEASE_CYCLE_JSON} (key {ver}, sha256 {meta['release_cycle_json_sha256'][:12]}); "
                                 f"release-cycle.json is made by a tool from the peps repository")
            c.files.append({"path": "release-cycle.json", "url": RELEASE_CYCLE_JSON,
                            "ref": {"url": RELEASE_CYCLE_JSON, "retrieved": meta["retrieved"]},
                            "sha256": meta["release_cycle_json_sha256"], "bytes": len(rc_raw),
                            "copy": False, "local_path": None, "license_item": "unknown",
                            "redistribute": False, "note": "gold source for validity; reference only"})
        g["license"] = lic
        g["personal_data"] = "yes"
        c.gold_source.append(f"status/Superseded-By/Replaces: {PEPS_JSON} (sha256 {meta['peps_json_sha256'][:12]}) "
                             f"and the PEP header at {PEP_SHA[:12]}")
        c.gold_source.append("license: the Copyright section of the pinned text (an item-level declaration)")
        c.gold_source.append("personal_data: Author header names (and e-mail addresses)")
        c.notes.append(text_note)
        c.notes.append("The text contains the Status header (and Resolution / Superseded-By / Replaces "
                       "headers where present); they are left out of evidence.")
        if status in ("Final", "Active") and sup:
            c.notes.append("Final with Superseded-By: the source keeps it Final; the successor covers another "
                           "scope (for example another API version), so acceptance stays accepted.")
        if status == "Superseded" and not sup:
            c.notes.append("Status Superseded with no Superseded-By header: the source names no successor.")
        if status == "Rejected" and sup:
            c.notes.append("Rejected with a Superseded-By header: the successor took up the topic; this "
                           "PEP was never accepted.")
        if status in ("Rejected", "Withdrawn", "Superseded"):
            c.notes.append(f"kstd has no '{status.lower()}' state; source status {status} maps to withdrawn "
                           f"with acceptance_reason={status.lower()} (history). prior_acceptance tells whether "
                           f"the source ever declared it accepted.")
        if g["artifact_status"] != status:
            c.notes.append(f"artifact_status: the pinned text says Status: {g['artifact_status']}; "
                           f"current_source_status (peps.json now) is {status}. The acceptance gold follows the "
                           f"current source declaration.")
        if lic == "unknown":
            c.notes.append("The pinned text has no Copyright section, so the item licence is unknown.")
        if lic == "LicenseRef-PublicDomain":
            c.notes.append("The text says only 'public domain' (no SPDX id).")
        if group == "validity":
            c.notes.append("valid_from/valid_to describe the CPython release line, from release-cycle.json; "
                           "the PEP Created date is not validity.")
        cases.append(c)


# ================================================================ RFCs
def rfc_case_id(n: int) -> str:
    return f"auto-rfc-{n}"


def rfc_num(s: str) -> int:
    return int(re.sub(r"\D", "", s))


def ballot_positions(draft: str):
    """Raw IESG ballot position events for a draft; comment texts are dropped."""
    objs, url = [], f"/api/v1/doc/ballotpositiondocevent/?doc__name={draft}&limit=200"
    while url:
        d = dtj(url)
        objs += d["objects"]
        url = d["meta"]["next"]
        if url:
            url = url.replace("&format=json", "").replace("format=json&", "")
    return objs


_person: dict[str, str] = {}
_ballot: dict[str, dict] = {}


def dt_person(uri: str) -> str:
    if uri not in _person:
        _person[uri] = dtj(uri)["name"]
    return _person[uri]


def dt_ballot(uri: str) -> dict:
    if uri not in _ballot:
        b = dtj(uri)
        bt = dtj(b["ballot_type"])
        _ballot[uri] = {"time": b["time"], "type": bt["slug"]}
    return _ballot[uri]


def flat(text: bytes) -> str:
    return " ".join(text.decode("utf-8", "replace").split())


# The copyright notice of an RFC is its item-level licence declaration. None of them has an SPDX id.
RFC_LICENCES = [
    ("LicenseRef-IETF-Trust-TLP", re.compile(r"subject to BCP 78 and the IETF Trust's Legal Provisions", re.I),
     "notice: 'subject to BCP 78 and the IETF Trust's Legal Provisions Relating to IETF Documents'"),
    ("LicenseRef-IETF-BCP78", re.compile(r"subject to the rights, licenses and restrictions contained in BCP 78", re.I),
     "notice: 'subject to the rights, licenses and restrictions contained in BCP 78' (2004-2008 form)"),
    ("LicenseRef-ISOC-Full-Copyright-Statement",
     re.compile(r"Copyright \(C\) The Internet Society \(\d{4}\)\.\s*All Rights Reserved.*Full Copyright Statement",
                re.I),
     "Internet Society copyright notice and its Full Copyright Statement (before BCP 78)"),
]


def rfc_licence(text: bytes) -> tuple[str, str]:
    t = flat(text)
    for lic, rx, how in RFC_LICENCES:
        if rx.search(t):
            return lic, how
    return "unknown", "the text has no copyright or licence notice"


PARTIAL = re.compile(r"(?:portions?|parts?) of (?:RFCs? ?)?((?:\[?(?:RFC ?)?\d{3,5}\]?(?:,? (?:and )?)?)+)", re.I)


def obsolete_scope(src: int, target: int) -> dict:
    """Scope of 'RFC src obsoletes RFC target', from the words of the obsoleting RFC (src).

    The header line 'Obsoletes:' carries no scope; the abstract or introduction can say 'portions of'."""
    t = flat(get(f"{RFC_EDITOR}/rfc/rfc{src}.txt"))[:30000]
    for sentence in re.split(r"(?<=\.) ", t):
        if "obsolet" not in sentence.lower():
            continue
        for m in PARTIAL.finditer(sentence):
            if target in [int(x) for x in re.findall(r"\d{3,5}", m.group(1))]:
                return {"scope": "partial", "note": f"RFC {src}: \"{sentence.strip()[:300]}\""}
    return {"scope": "full", "note": f"RFC {src} header 'Obsoletes: {target}'; its text names no partial scope"}


def build_rfcs(cases: list[Case], meta: dict):
    members = {n: (fam, grp) for fam, (grp, ns) in RFC_FAMILIES.items() for n in ns}

    def ref_for(s: str) -> str:
        m = rfc_num(s)
        return rfc_case_id(m) if m in members else f"https://www.rfc-editor.org/info/rfc{m}"

    for n, (family, group) in sorted(members.items()):
        jurl = f"{RFC_EDITOR}/rfc/rfc{n}.json"
        turl = f"{RFC_EDITOR}/rfc/rfc{n}.txt"
        jraw = get(jurl)
        j = json.loads(jraw)
        text = get(turl)
        doc = dtj(f"/api/v1/doc/document/rfc{n}/")
        stream = doc["stream"].rstrip("/").split("/")[-1] if doc.get("stream") else None
        draft = j.get("draft")
        draft_base = re.sub(r"-\d\d$", "", draft) if draft else None

        # ballot (raw events, comments removed)
        events = ballot_positions(draft_base) if draft_base else []
        approve_ballots = {}
        for o in events:
            b = dt_ballot(o["ballot"])
            if b["type"] == "approve":
                approve_ballots.setdefault(o["ballot"], []).append(o)
        ballot_file = None
        yes_names, final_pos, ballot_uri = None, None, None
        if approve_ballots:
            ballot_uri = max(approve_ballots, key=lambda u: _ballot[u]["time"])
            evs = sorted(approve_ballots[ballot_uri], key=lambda o: (o["time"], o["id"]))
            raw_events = [{"time": o["time"], "balloter": dt_person(o["balloter"]),
                           "balloter_uri": o["balloter"],
                           "pos": o["pos"].rstrip("/").split("/")[-1], "rev": o.get("rev"),
                           "event_id": o["id"]} for o in evs]
            last = {}
            for e in raw_events:
                last[e["balloter_uri"]] = e
            final_pos = {}
            for e in last.values():
                final_pos.setdefault(e["pos"], []).append(e["balloter"])
            final_pos = {k: sorted(v) for k, v in final_pos.items()}
            yes_names = final_pos.get("yes", [])
            ballot_file = json.dumps({"doc": draft_base, "ballot": DATATRACKER + ballot_uri,
                                      "ballot_type": "approve", "ballot_time": _ballot[ballot_uri]["time"],
                                      "events": raw_events,
                                      "note": "datatracker ballotpositiondocevent records, oldest first; "
                                              "comment and discuss texts removed"},
                                     ensure_ascii=False, indent=1).encode()
        other_ballots = sorted({_ballot[o["ballot"]]["type"] for o in events} - {"approve"}) if events else []

        obs_by = j.get("obsoleted_by") or []
        status = j.get("status")
        op = {"supersession": "search", "updates": "model-answer", "stream-approval": "model-answer"}[group]
        qs = {"supersession": ["Q13", "Q17", "Q21"], "updates": ["Q13", "Q17"],
              "stream-approval": ["Q16", "Q23"]}[group]
        obsoleted_by = [{"target": ref_for(s), **obsolete_scope(rfc_num(s), n)} for s in obs_by]
        partial = [r for r in obsoleted_by if r["scope"] == "partial"]
        if group == "supersession" and partial:
            why = (f"RFC {n} is obsoleted only in part by {len(partial)} of its {len(obs_by)} successors; the "
                   f"library must mark it and point to the right successor per topic.")
        elif group == "supersession" and len(obs_by) > 1:
            why = (f"RFC {n} has {len(obs_by)} successors that each declare a full obsoletion; the library must "
                   f"mark it and point to the right successor per topic.")
        elif group == "supersession" and obs_by:
            why = f"RFC {n} is obsoleted; a search must serve its successor as current and this one as history."
        elif group == "supersession":
            why = f"RFC {n} is the current end of a replacement chain; it must be served as current."
        elif group == "updates":
            why = (f"RFC {n} is updated by later RFCs but not obsoleted; an update is not a supersession, so it "
                   f"stays current.")
        else:
            why = (f"RFC {n} is on the {stream} stream; the IESG did not approve its content, so no IESG "
                   f"member is its approver." + (" Its datatracker 'approve' ballot is only an IESG review."
                                                 if approve_ballots else ""))
        c = Case(rfc_case_id(n), group, "rfc-editor.org", family, op, qs, why)
        lic, lic_how = rfc_licence(text)
        c.add_file(f"rfc{n}.txt", text, path=f"rfc{n}.txt", url=turl,
                   ref={"url": turl, "version": f"RFC {n} (immutable once published)", "retrieved": meta["retrieved"]},
                   license_item=lic, copy=True, redistribute=(stream == "ietf" and lic != "unknown"),
                   note="the IETF terms allow verbatim copies of IETF stream documents; coverage of other streams "
                        "and of texts with no notice is not verified, so those are reference-only for the public set")
        c.add_file(f"rfc{n}.json", jraw, path=f"rfc/rfc{n}.json", url=jurl,
                   ref={"url": jurl, "retrieved": meta["retrieved"]}, license_item="unknown", copy=True,
                   redistribute=False,
                   note="RFC Editor metadata record (raw source declaration of status and relations); "
                        "local copy for adapters, reference-only in the public set")
        if ballot_file:
            c.add_file("iesg-ballot.json", ballot_file, path=f"doc/{draft_base}/ballot",
                       url=f"{DATATRACKER}/doc/{draft_base}/ballot/",
                       ref={"url": f"{DATATRACKER}/api/v1/doc/ballotpositiondocevent/?doc__name={draft_base}",
                            "retrieved": meta["retrieved"]},
                       license_item="unknown", copy=True, redistribute=False,
                       note="reduced export of datatracker ballot events (names, positions, times)")
        c.evidence = {"title": j.get("title"), "doc_id": j.get("doc_id"), "pub_date": j.get("pub_date"),
                      "page_count": j.get("page_count"), "draft": draft}

        g = c.gold
        g["source_status"] = status
        g["artifact_status"] = status
        g["stream"] = stream
        if obs_by or status == "HISTORIC":
            g["acceptance"] = "withdrawn"
            g["acceptance_reason"] = "obsoleted" if obs_by else "historic"
            g["prior_acceptance"] = True
            c.gold_source.append(f"prior_acceptance: published in the RFC series as {status}")
        else:
            g["acceptance"] = "accepted"
        g["superseded_by"] = [ref_for(s) for s in obs_by] or None
        g["obsoleted_by"] = obsoleted_by or None
        if obs_by:
            g["supersession_scope"] = ("partial" if partial else "full-multiple" if len(obs_by) > 1 else "full")
            succ_dates = {}
            for s in obs_by:
                sj = get_json(f"{RFC_EDITOR}/rfc/rfc{rfc_num(s)}.json")
                succ_dates[s] = sj.get("pub_date")
            g["successor_pub_dates"] = succ_dates
            c.gold_source.append("obsoleted_by scope: the words of each obsoleting RFC ('portions of' = partial)")
        g["obsoletes"] = [{"target": ref_for(s), **obsolete_scope(n, rfc_num(s))}
                          for s in (j.get("obsoletes") or [])] or None
        g["updated_by"] = [ref_for(s) for s in (j.get("updated_by") or [])] or None
        g["updates"] = [ref_for(s) for s in (j.get("updates") or [])] or None
        g["approver"] = None
        g["decided_by"] = None
        if yes_names is not None and stream == "ietf":
            g["approver"] = yes_names or None
            g["approver_kind"] = "person"
            g["decided_by"] = [{"name": "IESG", "kind": "body", "source": f"{DATATRACKER}{ballot_uri}"}]
            g["iesg_final_positions"] = final_pos
            c.gold_source.append(f"approver: names with a final 'yes' position on the last approve ballot "
                                 f"{DATATRACKER}{ballot_uri} (last event per balloter); decided_by: the IESG as the "
                                 f"body that holds that ballot")
        elif stream == "ietf":
            c.notes.append("IETF stream, but datatracker holds no approve ballot for this document "
                           f"({'no draft name' if not draft else 'too old or not recorded'}); no named approver "
                           f"and no recorded decision maker.")
        if stream == "ise":
            g["decided_by"] = [{"name": "Independent Submissions Editor", "kind": "role",
                                "source": f"{DATATRACKER}/api/v1/doc/document/rfc{n}/ (stream ise)"}]
            c.gold_source.append("decided_by: the stream of the document (ise) names its decision maker")
            if yes_names is not None:
                g["iesg_final_positions"] = final_pos
                c.gold_source.append(f"iesg_final_positions: {DATATRACKER}{ballot_uri}")
                c.notes.append("Stream ise: the datatracker 'approve' ballot is the IESG review of an independent "
                               "submission (RFC 3932 era: publish, or publish with an IESG note), not an approval "
                               "of the content. The 'yes' names are not approvers.")
            else:
                c.notes.append("Stream ise: no IESG approve ballot"
                               + (f" (only {', '.join(other_ballots)} ballot)" if other_ballots else "")
                               + "; the RFC Editor publication is not an IETF approval.")
        g["license"] = lic
        g["license_source"] = f"rfc{n}.txt {lic_how}"
        g["personal_data"] = "yes"
        c.gold_source.append(f"status/obsoleted_by/updates: {jurl}")
        c.gold_source.append(f"stream: {DATATRACKER}/api/v1/doc/document/rfc{n}/")
        c.gold_source.append(f"license: the copyright notice in the text ({lic_how}); no SPDX id exists")
        c.gold_source.append("personal_data: author names and addresses (Authors' Addresses section)")
        c.notes.append("The RFC text itself never shows later obsoletion; rfc{n}.json does. The parsed "
                       "status and relations are left out of evidence.".replace("{n}", str(n)))
        if obs_by and status not in ("HISTORIC", "OBSOLETE"):
            c.notes.append(f"The status field still says {status} after obsoletion; acceptance comes from "
                           f"obsoleted_by.")
        if g["updated_by"] and not obs_by:
            c.notes.append("updated_by is not a supersession: the document stays current with its updates.")
        if partial:
            c.notes.append("At least one successor obsoletes only portions of this RFC (see obsoleted_by[].note). "
                           "The RFC series still lists it as obsoleted; a supersession applies only in the "
                           "shared scope (kstd §6).")
        elif len(obs_by) > 1:
            c.notes.append("Each successor declares a full obsoletion in its header; each one covers a part of the "
                           "topic in practice.")
        if lic == "unknown":
            c.notes.append("The text has no copyright notice, so the item licence is unknown.")
        c.notes.append("No validity window: the RFC gives a publication date only; pub_date and "
                       "successor_pub_dates are not valid_from/valid_to.")
        cases.append(c)


# ================================================================ repository files: item licence, history
NO_ITEM_LICENCE = ("no item-level licence declaration covers this file (no header, no REUSE.toml or .reuse/dep5); "
                   "the repository LICENSE is a separate claim (repo_license), so the item licence is unknown "
                   "(kstd §5) and the public set holds a reference + hash only")
SPDX_RX = re.compile(rb"SPDX-License-Identifier:\s*([A-Za-z0-9.+\-() ]+?)\s*(?:-->|\*/|$)", re.M)
_repo_lic: dict[tuple[str, str], dict] = {}


def spdx_header(data: bytes) -> str | None:
    m = SPDX_RX.search(data[:4096])
    return m.group(1).decode().strip() if m else None


def item_licence(values) -> str:
    """The case licence: the one item-level declaration of its files, or unknown when any file has none."""
    vals = set(values)
    return vals.pop() if len(vals) == 1 and None not in vals else "unknown"


def repo_license_claim(repo: str, sha: str, blobs: set[str]) -> dict:
    """The repository licence as a separate claim, with its provenance. Fails when a REUSE declaration exists,
    because that would be an item-level declaration that this builder does not read."""
    if (repo, sha) not in _repo_lic:
        reuse = sorted(p for p in blobs if p == "REUSE.toml" or p.endswith("/REUSE.toml") or p == ".reuse/dep5")
        if reuse:
            raise RuntimeError(f"{repo}: REUSE declaration {reuse} must be read as item-level licence")
        lic = gh(f"repos/{repo}/license?ref={sha}")
        _repo_lic[(repo, sha)] = {
            "license": lic["license"]["spdx_id"],
            "source": f"{lic['path']} at {repo}@{sha[:12]} (GitHub licence detection: {lic['license']['key']})",
            "url": raw_url(repo, sha, lic["path"]),
            "scope": "repository root licence file; it names no files, so it is not an item-level declaration"}
    return _repo_lic[(repo, sha)]


def git_history(repo: str, sha: str, path: str) -> list[tuple[str, str]]:
    """(committer date, commit sha) of every commit that touched `path`, oldest first."""
    out, page = [], 1
    while True:
        cs = gh(f"repos/{repo}/commits?path={path}&sha={sha}&per_page=100&page={page}")
        out += [(c["commit"]["committer"]["date"], c["sha"]) for c in cs]
        if len(cs) < 100:
            return sorted(out)
        page += 1


def kep_status_history(path: str) -> list[str]:
    out = []
    for _, csha in git_history(KEP_REPO, KEP_SHA, path):
        try:
            out.append(str((yaml.safe_load(get(raw_url(KEP_REPO, csha, path))) or {}).get("status")))
        except (urllib.error.HTTPError, yaml.YAMLError, ValueError):
            continue
    return out


# ================================================================ KEPs
def kep_case_id(folder: str) -> str:
    parts = folder.split("/")
    sig = parts[1].replace("sig-", "")
    num = parts[-1].split("-")[0]
    return f"auto-kep-{sig}-{num}"


def norm_handle(h) -> str:
    h = str(h).strip()
    return h if h.startswith("@") else "@" + h


KEP_ACCEPT = {"implemented": "accepted", "implementable": "accepted", "provisional": "pending",
              "deferred": "pending", "withdrawn": "withdrawn", "rejected": "withdrawn",
              "replaced": "withdrawn", "superseded": "withdrawn", "removed": "withdrawn"}


def build_keps(cases: list[Case], meta: dict):
    tree = gh(f"repos/{KEP_REPO}/git/trees/{KEP_SHA}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError("KEP tree truncated")
    blobs = {t["path"] for t in tree["tree"] if t["type"] == "blob"}
    # resolve 1138 folder by number
    impl = []
    for f in KEP_IMPLEMENTED:
        if f.endswith("/1138-ipv6"):
            hits = sorted(p.rsplit("/", 1)[0] for p in blobs
                          if re.match(r"keps/sig-network/1138-[^/]+/kep\.yaml$", p))
            f = hits[0]
        impl.append(f)

    selected: dict[str, tuple[str, str]] = {}
    for fam, folders in KEP_FAMILIES.items():
        for f in folders:
            selected[f] = (fam, "supersession")
    for f in KEP_WITHDRAWN:
        selected[f] = (f"k8s/keps:{f.split('/')[-1].split('-')[0]}", "withdrawal")
    for f in impl:
        selected[f] = (f"k8s/keps:{f.split('/')[-1].split('-')[0]}", "approval")

    # reverse `replaces` index over every kep.yaml (source-declared successors)
    all_yaml = sorted(p for p in blobs if p.startswith("keps/") and p.endswith("/kep.yaml"))
    kmeta = {}

    def load(p):
        try:
            kmeta[p] = yaml.safe_load(get(raw_url(KEP_REPO, KEP_SHA, p)))
        except Exception as e:  # malformed upstream yaml: skip in the index only
            print(f"warn: {p}: {e}", file=sys.stderr)

    with ThreadPoolExecutor(16) as ex:
        list(ex.map(load, all_yaml))
    replaced_by: dict[str, list[str]] = {}
    for p, v in kmeta.items():
        for r in (v or {}).get("replaces") or []:
            r = str(r).strip().strip("()")
            m = re.search(r"(keps/[^\s)]+)", r)
            if not m:
                continue
            target = m.group(1).rstrip("/")
            if target.endswith(".md"):
                continue  # old single-file path; handled by KEP_SUCCESSOR_NOTES
            replaced_by.setdefault(target, []).append(p.rsplit("/", 1)[0])

    for folder, (family, group) in sorted(selected.items()):
        ky_path = f"{folder}/kep.yaml"
        ky_raw = get(raw_url(KEP_REPO, KEP_SHA, ky_path))
        ky = yaml.safe_load(ky_raw)
        readme_path = f"{folder}/README.md"
        readme = get(raw_url(KEP_REPO, KEP_SHA, readme_path)) if readme_path in blobs else None
        sig, num = ky.get("owning-sig"), ky.get("kep-number")
        prr_path = f"keps/prod-readiness/{sig}/{num}.yaml"
        prr_raw = get(raw_url(KEP_REPO, KEP_SHA, prr_path)) if prr_path in blobs else None
        prr = yaml.safe_load(prr_raw) if prr_raw else None
        status = str(ky.get("status"))

        op = {"supersession": "search", "withdrawal": "search", "approval": "model-answer"}[group]
        qs = {"supersession": ["Q13", "Q21"], "withdrawal": ["Q13"], "approval": ["Q16", "Q24"]}[group]
        why = {
            "supersession": f"KEP {num} is in a replacement pair; superseded-by in kep.yaml is usually empty, so "
                            f"the successor must come from the successor's `replaces` or the README.",
            "withdrawal": f"KEP {num} was withdrawn; it must not be served as current Kubernetes behaviour.",
            "approval": (f"KEP {num} lists assigned approvers in kep.yaml, but the real named approval is only in "
                         f"the PRR file." if prr else
                         f"KEP {num} is implemented but has no PRR file; the assigned approvers in kep.yaml are "
                         f"not proof of approval."),
        }[group]
        c = Case(kep_case_id(folder), group, KEP_REPO, family, op, qs, why)
        repo_lic = repo_license_claim(KEP_REPO, KEP_SHA, blobs)
        datas = {"README.md": readme, "kep.yaml": ky_raw, "prr.yaml": prr_raw}
        file_lic = {k: spdx_header(v) for k, v in datas.items() if v}
        lic = item_licence(file_lic.values())

        def common(name):
            fl = file_lic[name] or "unknown"
            return dict(license_item=fl, copy=True, redistribute=fl != "unknown",
                        note=None if fl != "unknown" else NO_ITEM_LICENCE)
        if readme:
            c.add_file("README.md", readme, path=readme_path, url=raw_url(KEP_REPO, KEP_SHA, readme_path),
                       ref={"repo": KEP_REPO, "commit": KEP_SHA, "path": readme_path}, **common("README.md"))
        c.add_file("kep.yaml", ky_raw, path=ky_path, url=raw_url(KEP_REPO, KEP_SHA, ky_path),
                   ref={"repo": KEP_REPO, "commit": KEP_SHA, "path": ky_path}, **common("kep.yaml"))
        if prr_raw:
            c.add_file("prr.yaml", prr_raw, path=prr_path, url=raw_url(KEP_REPO, KEP_SHA, prr_path),
                       ref={"repo": KEP_REPO, "commit": KEP_SHA, "path": prr_path}, **common("prr.yaml"))
        c.evidence = {"title": ky.get("title"), "kep_number": num, "owning_sig": sig,
                      "creation_date": str(ky.get("creation-date")) if ky.get("creation-date") else None,
                      "kep_yaml_reviewers_assigned": ky.get("reviewers") or [],
                      "kep_yaml_approvers_assigned": ky.get("approvers") or [],
                      "prr_file_present": bool(prr_raw),
                      "repo_license": repo_lic}

        g = c.gold
        g["source_status"] = status
        g["artifact_status"] = status
        g["acceptance"] = KEP_ACCEPT.get(status)
        if g["acceptance"] == "withdrawn":
            g["acceptance_reason"] = status
            if status == "rejected":
                g["prior_acceptance"] = False
            else:
                hist = kep_status_history(ky_path)
                g["prior_acceptance"] = True if any(s in ("implementable", "implemented") for s in hist) else None
                c.gold_source.append(f"prior_acceptance: status of the {len(hist)} revisions of kep.yaml in git "
                                     f"({' > '.join(dict.fromkeys(hist)) or 'none'})")
                if g["prior_acceptance"] is None:
                    c.notes.append("No revision of kep.yaml shows implementable/implemented; older revisions "
                                   "can be in a moved file, so prior_acceptance is not determined (null).")
        succ = None
        declared = [s for s in as_list(ky.get("superseded-by")) if s]
        if declared:
            succ = [str(s) for s in declared]
            c.gold_source.append("superseded_by: kep.yaml superseded-by")
        elif folder in replaced_by:
            succ = replaced_by[folder]
            c.gold_source.append("superseded_by: `replaces` in the successor kep.yaml")
        elif folder in KEP_SUCCESSOR_NOTES:
            url, how = KEP_SUCCESSOR_NOTES[folder]
            if url:
                succ = [url.format(sha=KEP_SHA)]
            c.gold_source.append(f"superseded_by: {how}")
        if folder in KEP_SUCCESSOR_NOTES and not succ:
            # successor named through an old path: resolve to the folder in the same family
            others = [f for f in KEP_FAMILIES.get(family, []) if f != folder]
            succ = others or None
        if succ:
            succ = [kep_case_id(s) if s in selected else
                    (s if s.startswith("http") else f"https://github.com/{KEP_REPO}/tree/{KEP_SHA}/{s}")
                    for s in succ]
        g["superseded_by"] = succ
        if succ:
            g["supersession_scope"] = "full"
        reps = [str(r) for r in as_list(ky.get("replaces")) if str(r).strip()]
        if reps:
            g["replaces"] = [kep_case_id(r.strip("/")) if r.strip("/") in selected else r for r in reps]
        if prr:
            by_stage = {s: norm_handle(prr[s]["approver"]) for s in ("alpha", "beta", "stable")
                        if isinstance(prr.get(s), dict) and prr[s].get("approver")}
            g["approver"] = sorted(set(by_stage.values())) or None
            g["approver_by_stage"] = by_stage
            g["approver_kind"] = "person"
            g["approval_scope"] = "production readiness review (PRR) per stage"
            c.gold_source.append(f"approver: {prr_path} only")
        else:
            g["approver"] = None
            c.notes.append("No PRR file: kep.yaml reviewers/approvers are assigned people, not an approval.")
        if prr and g["acceptance"] == "withdrawn":
            c.notes.append("The PRR approval is a real past approval of a stage; the KEP is now withdrawn, so it "
                           "gives no current authority.")
        g["applicability"] = {"latest_milestone": ky.get("latest-milestone"), "stage": ky.get("stage"),
                              "milestone": ky.get("milestone")}
        g["license"] = lic
        g["license_source"] = ("SPDX header in the files" if lic != "unknown" else
                               "no item-level declaration: no licence header in the files, no REUSE.toml or "
                               ".reuse/dep5 in the repository")
        g["repo_license"] = repo_lic
        g["personal_data"] = "yes"
        c.gold_source.append(f"status: kep.yaml at {KEP_SHA[:12]}")
        c.gold_source.append(f"license: {g['license_source']} (kstd §5: a package licence does not replace an "
                             f"item licence); repo_license: {repo_lic['source']}")
        c.gold_source.append("personal_data: GitHub handles of authors/reviewers in kep.yaml")
        c.notes.append("kep.yaml contains the status field; it is left out of evidence.")
        c.notes.append("Milestones are applicability (Kubernetes versions), not a validity window.")
        if status not in ("implemented", "implementable", "provisional", "deferred", "withdrawn",
                          "rejected", "replaced"):
            c.notes.append(f"Status '{status}' is not in the KEP status list; mapped to {g['acceptance']}.")
        if status in ("replaced", "superseded") and not succ:
            c.notes.append("The source declares a replacement but names no successor.")
        cases.append(c)


# ================================================================ ADRs
ADR_FIELDS = ("status", "deciders", "date", "consulted", "informed", "technical story")


def adr_meta(text: str) -> dict:
    m: dict[str, str] = {}
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":  # YAML front matter
        end = lines.index("---", 1)
        fm = yaml.safe_load("\n".join(lines[1:end])) or {}
        return {str(k).lower(): str(v) for k, v in fm.items()}
    key = None
    for line in lines[:30]:
        mm = re.match(r"^\s*(?:[-*]\s*)?(?:\*\*)?([A-Za-z ]+?)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$", line)
        if mm and mm.group(1).strip().lower() in ADR_FIELDS:
            key = mm.group(1).strip().lower()
            m[key] = mm.group(2).strip()
        elif key and line.startswith("  ") and line.strip():
            m[key] += " " + line.strip()
        else:
            key = None
    return m


def adr_case_id(fname: str) -> str:
    return f"auto-adr-fxa-{fname[:4]}"


def split_names(s: str) -> list[str]:
    return [x.strip() for x in s.split(",") if x.strip()]


def adr_status_history(path: str) -> list[str]:
    """The lower-case Status value of every revision that has one, oldest first."""
    out = []
    for _, csha in git_history(FXA_REPO, FXA_SHA, path):
        try:
            st = adr_meta(get(raw_url(FXA_REPO, csha, path)).decode("utf-8", "replace")).get("status")
        except urllib.error.HTTPError:
            continue
        if st:
            out.append(st.lower())
    return out


def build_adrs(cases: list[Case], meta: dict):
    selected = {}
    for fam, fs in ADR_FAMILIES.items():
        for f in fs:
            selected[f] = (fam, "supersession")
    for f in ADR_SINGLE:
        selected[f] = (f"mozilla/fxa:adr-{f[:4]}", "approval")

    for fname, (family, group) in sorted(selected.items()):
        path = f"docs/adr/{fname}"
        data = get(raw_url(FXA_REPO, FXA_SHA, path))
        text = data.decode()
        m = adr_meta(text)
        title = next((l.lstrip("# ").strip() for l in text.splitlines() if l.startswith("#")), None)
        status_raw = m.get("status")
        s = (status_raw or "").lower()
        sup = re.findall(r"\(([^)]+?)\)", status_raw or "") if s.startswith("superseded") else []
        if not status_raw:
            acc = None
        elif s.startswith("superseded") or s.startswith("deprecated"):
            acc = "withdrawn"
        elif s.startswith("rejected"):
            acc = "withdrawn"
        elif s.startswith("accepted") or s == "final" or s.startswith("partially implemented"):
            acc = "accepted"
        elif s.startswith("proposed"):
            acc = "pending"
        else:
            acc = None

        op = "search" if group == "supersession" else "model-answer"
        qs = ["Q13", "Q16"] if group == "supersession" else ["Q16", "Q24"]
        if group == "supersession":
            why = (f"ADR {fname[:4]} is part of a decision line ({family.split(':')[1]}); the library must "
                   f"serve only what the source declares as superseded, not what prose suggests.")
        elif not status_raw:
            why = f"ADR {fname[:4]} has no status line; its acceptance is not declared and must not be guessed."
        else:
            why = f"ADR {fname[:4]} declares a status and deciders; the answer must not treat proposers or " \
                  f"consulted people as approvers."
        c = Case(adr_case_id(fname), group, FXA_REPO, family, op, qs, why)
        tree = gh(f"repos/{FXA_REPO}/git/trees/{FXA_SHA}?recursive=1")
        if tree.get("truncated"):
            raise RuntimeError("fxa tree truncated")
        repo_lic = repo_license_claim(FXA_REPO, FXA_SHA, {t["path"] for t in tree["tree"] if t["type"] == "blob"})
        lic = spdx_header(data) or "unknown"
        c.add_file(fname, data, path=path, url=raw_url(FXA_REPO, FXA_SHA, path),
                   ref={"repo": FXA_REPO, "commit": FXA_SHA, "path": path}, license_item=lic,
                   copy=True, redistribute=lic != "unknown", note=None if lic != "unknown" else NO_ITEM_LICENCE)
        c.evidence = {"title": title, "file": fname, "date_line": m.get("date"), "repo_license": repo_lic}

        g = c.gold
        g["source_status"] = status_raw
        g["artifact_status"] = status_raw
        g["acceptance"] = acc
        if acc == "withdrawn":
            g["acceptance_reason"] = "rejected" if s.startswith("rejected") else s.split()[0]
            if s.startswith("rejected"):
                g["prior_acceptance"] = False
            else:
                hist = adr_status_history(path)
                g["prior_acceptance"] = True if any(h.startswith("accepted") for h in hist) else None
                c.gold_source.append(f"prior_acceptance: Status line of the {len(hist)} revisions with one "
                                     f"({' > '.join(dict.fromkeys(hist)) or 'none'})")
                if g["prior_acceptance"] is None:
                    c.notes.append("No revision says 'accepted', so prior_acceptance is not determined (null).")
        g["superseded_by"] = None
        if sup:
            succ = []
            for target in sup:
                t = target.split("/")[-1]
                t = t if t.endswith(".md") else t + ".md"
                succ.append(adr_case_id(t) if t in selected else
                            f"https://github.com/{FXA_REPO}/blob/{FXA_SHA}/docs/adr/{t}")
            g["superseded_by"] = succ
            g["supersession_scope"] = "full"
        deciders = split_names(m.get("deciders", ""))
        if acc in ("accepted",) or (acc == "withdrawn" and s.startswith("superseded")):
            g["approver"] = deciders or None
            g["approver_kind"] = "person"
            c.gold_source.append("approver: Deciders line (MADR)")
        elif acc == "withdrawn" and s.startswith("rejected"):
            g["approver"] = None
            g["decided_by"] = [{"name": d, "kind": "person", "source": "Deciders line"} for d in deciders] or None
            c.gold_source.append("decided_by: Deciders line (rejected decision)")
        else:
            g["approver"] = None
            if deciders:
                c.notes.append("Deciders are listed, but the source declares no accepted decision, so they "
                               "are not approvers.")
        g["license"] = lic
        g["license_source"] = ("SPDX header in the file" if lic != "unknown" else
                               "no item-level declaration: no licence header in the file, no REUSE.toml or "
                               ".reuse/dep5 in the repository")
        g["repo_license"] = repo_lic
        if deciders:
            g["personal_data"] = "yes"
        elif fname in ADR_PD_NOTE:
            g["personal_data"] = "yes"
            c.notes.append(ADR_PD_NOTE[fname])
        else:
            g["personal_data"] = "unknown"
        c.gold_source.append(f"status: Status line of the file at {FXA_SHA[:12]}")
        c.gold_source.append(f"license: {g['license_source']} (kstd §5); repo_license: {repo_lic['source']}")
        c.gold_source.append("personal_data: names in the Deciders line")
        if status_raw:
            c.notes.append("The text contains the Status line; it is left out of evidence.")
        else:
            c.notes.append("No Status line: acceptance null = not declared (the kstd default 'pending' applies).")
        if acc and s not in ("accepted", "proposed", "rejected") and not s.startswith("superseded"):
            c.notes.append(f"Status '{status_raw}' is not a MADR keyword; mapped to {acc} by us.")
        if m.get("consulted") or m.get("informed"):
            c.notes.append("Consulted/Informed people are not approvers.")
        cases.append(c)
    # second pass: an ADR that is named as successor gets a back link
    by_id = {c.id: c for c in cases if c.source == FXA_REPO}
    for c in by_id.values():
        for sid in c.gold.get("superseded_by") or []:
            if sid in by_id:
                by_id[sid].gold.setdefault("replaces", []).append(c.id)
                by_id[sid].notes.append(f"{c.id} declares this ADR as its successor, but this ADR's own "
                                        f"status is '{by_id[sid].gold['source_status']}'.")


def as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


# ================================================================ main
def main():
    global CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path("/home/mega/kobra/research/labelling-v5/auto")))
    ap.add_argument("--cache", default="/tmp/claude-1000/-home-mega-kobra/ontology-work/auto-docs-cache")
    args = ap.parse_args()
    CACHE = Path(args.cache)
    CACHE.mkdir(parents=True, exist_ok=True)
    out = Path(args.out)
    get(PEPS_JSON)  # first network read; its cache time is the retrieval time of this build
    fetched = dt.datetime.fromtimestamp(_cache_path(PEPS_JSON).stat().st_mtime, dt.timezone.utc)
    meta = {"retrieved": fetched.strftime("%Y-%m-%dT%H:%MZ")}

    cases: list[Case] = []
    build_peps(cases, meta)
    build_rfcs(cases, meta)
    build_keps(cases, meta)
    build_adrs(cases, meta)

    ids = [c.id for c in cases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate case ids")

    slice_dir = out / "docs"
    if slice_dir.exists():
        shutil.rmtree(slice_dir)
    slice_dir.mkdir(parents=True)
    with open(out / "docs.cases.jsonl", "w") as fc, open(out / "docs.gold.jsonl", "w") as fg:
        for c in cases:
            d = slice_dir / c.id
            d.mkdir()
            for name, blob in c.blobs.items():
                (d / name).write_bytes(blob)
            cj = c.case_json()
            (d / "case.json").write_text(json.dumps(cj, ensure_ascii=False, indent=1) + "\n")
            fc.write(json.dumps(cj, ensure_ascii=False) + "\n")
            fg.write(json.dumps(c.gold_json(), ensure_ascii=False) + "\n")
    print(json.dumps({"cases": len(cases), "retrieved": meta["retrieved"],
                      "by_source": {s: sum(1 for c in cases if c.source == s)
                                    for s in sorted({c.source for c in cases})}}))


if __name__ == "__main__":
    main()
