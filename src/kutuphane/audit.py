"""Unified audit (D35, AT-09): one query explains who, for whom, which version and policy, which grants, and which
model calls — Kütüphane's access log joined with LLMDAP's egress log by correlation id.

LLMDAP has no HTTP audit query; its records come from `llmdap-audit-export` (verified JSONL), which also works
offline. A model call Kütüphane made but LLMDAP did not record is reported as missing, never silently dropped.
"""
import json
from pathlib import Path

ACCESS_FIELDS = ("at", "principal", "on_behalf_of", "action", "object", "mode", "allowed", "reason", "policy_id",
                 "grant_ids", "delegation_id", "content_id", "path", "profile_id", "items")
CALL_FIELDS = ("at", "call_id", "principal", "on_behalf_of", "route", "model", "source_books", "http_status", "error",
               "derived_correlation_id")
EXPECTED_OK = {"llm.authz", "llm.result"}  # a completed call leaves both on LLMDAP's side
EXPECTED_REFUSED = {"llm.authz"}           # a call LLMDAP refused still leaves its authorization record


def read_llmdap_export(path: Path) -> list[dict]:
    records = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                raise ValueError(f"{path}:{n}: not JSON") from None
    return records


def _rows(conn, sql: str, correlation_id: str, fields) -> list[dict]:
    out = []
    for row in conn.execute(sql, (correlation_id,)):
        item = dict(zip(fields, row))
        item["at"] = item["at"].isoformat()
        out.append(item)
    return out


def explain(conn, correlation_id: str, llmdap_records: list[dict]) -> dict:
    access = _rows(conn, f"SELECT {', '.join(ACCESS_FIELDS)} FROM access_event WHERE correlation_id = %s ORDER BY id",
                   correlation_id, ACCESS_FIELDS)
    calls = _rows(conn, f"SELECT {', '.join(CALL_FIELDS)} FROM model_call WHERE correlation_id = %s ORDER BY id",
                  correlation_id, CALL_FIELDS)
    by_id = {}
    for rec in llmdap_records:
        by_id.setdefault(rec.get("correlationId"), []).append(rec)
    for call in calls:
        call["llmdap"] = sorted(by_id.get(call["derived_correlation_id"], []) if call["derived_correlation_id"] else [],
                                key=lambda r: r.get("seq", 0))
        call["llmdap_status"] = _status(call)
    return {"correlation_id": correlation_id, "found": bool(access or calls), "access": access,
            "model_calls": calls, "complete": all(c["llmdap_status"] != "missing" for c in calls)}


def _status(call: dict) -> str:
    """complete: LLMDAP holds every record this call must have left; missing: it does not (or we cannot tell);
    not_sent: the call never reached LLMDAP (refused by our egress check, or unreachable)."""
    if call["http_status"] is None and call["derived_correlation_id"] is None:
        return "not_sent"
    expected = EXPECTED_OK if call["http_status"] and 200 <= call["http_status"] < 300 else EXPECTED_REFUSED
    seen = {r.get("type") for r in call["llmdap"]}
    return "complete" if call["derived_correlation_id"] and expected <= seen else "missing"
