"""kstd reference decision rule (draft 0.2, docs/11 §4). Small and deterministic: the same case gives the same
result and the same reasons. It exists to make the conformance cases precise, not to be fast.

A case has: `now`, `node` (this node's issuer id), `trust`, `precedence`, `statements`, `policy`, `request`.
The result is {result: permit|deny|escalate, authority: rule|evidence|none, reasons: [...], notices: [...]}.
"""
from datetime import datetime, timedelta

ORDER = {"permit": 0, "escalate": 1, "deny": 2}  # rule 1: the strictest result wins
STRICT = {"export": ["normal", "restricted"], "route": ["cloud_ok", "local_only"]}
DEFAULT_MAX_AGE_DAYS = 30


def ts(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def trusted(case, issuer, kind, scope, action=None) -> dict | None:
    """The node itself is always trusted. Trust is issuer × kind × scope × action, with an expiry (rule 4)."""
    if issuer == case["node"]:
        return {"issuer": issuer, "max_status_age_days": None}
    now = ts(case["now"])
    for t in case.get("trust", []):
        if (t["issuer"] == issuer and kind in t["kinds"] and scope in t["scopes"]
                and (action is None or action in t.get("actions", [action]))
                and ("expires" not in t or ts(t["expires"]) > now)):
            return t
    return None


def latest_per_issuer(statements) -> dict:
    out = {}
    for s in sorted(statements, key=lambda s: ts(s["issued_at"])):
        out[s["issuer"]] = s  # a revision replaces the same issuer's earlier statement; never another issuer's
    return out


def resolve_acceptance(case, item_id, scope, reasons, notices) -> str:
    """Rule 5 (conflict between trusted issuers) and rule 8 (no untrusted removal of accepted knowledge)."""
    stmts = [s for s in case["statements"] if s["kind"] == "acceptance" and s["about"] == item_id]
    values = {}
    for issuer, s in latest_per_issuer(stmts).items():
        if trusted(case, issuer, "acceptance", scope):
            values[issuer] = s["body"]["value"]
        elif s["body"]["value"] == "withdrawn":
            notices.append(f"contested-by:{issuer}")  # an untrusted withdrawal is only a visible contest mark
    if not values:
        return "pending"
    if len(set(values.values())) > 1:
        for issuer in case.get("precedence", []):
            if issuer in values:
                return values[issuer]
        reasons.append("conflict-no-precedence")
        return "conflict"
    return next(iter(values.values()))


def held(case, item_id, scope) -> bool:
    now = ts(case["now"])
    return any(s["kind"] == "hold" and s["about"] == item_id and trusted(case, s["issuer"], "hold", scope)
               and ts(s["body"]["review_by"]) > now for s in case["statements"])


def effective_handling(case, item_id, scope, prop) -> str:
    """Rule 4: a tightening applies from anybody; a value from a trusted issuer counts; the strictest wins."""
    order = STRICT[prop]
    counted = []
    for issuer, s in latest_per_issuer([s for s in case["statements"]
                                        if s["kind"] == "handling" and s["about"] == item_id
                                        and prop in s["body"]]).items():
        value = s["body"][prop]
        if trusted(case, issuer, "handling", scope) or value == order[-1]:
            counted.append(value)
    return max(counted, key=order.index) if counted else order[-1]  # unconfirmed: the strictest (draft §5)


def decide(case: dict) -> dict:
    req, now = case["request"], ts(case["now"])
    reasons, notices = [], []
    item = next((s for s in case["statements"] if s["kind"] == "item" and s["id"] == req["item"]), None)
    if item is None:
        return {"result": "deny", "authority": "none", "reasons": ["unknown-item"], "notices": []}
    body, scope = item["body"], item["body"]["scope"]
    results = []

    # --- authority for answers -------------------------------------------------------------------------------
    acceptance = resolve_acceptance(case, item["id"], scope, reasons, notices)
    if acceptance == "conflict":
        results.append("escalate")
    if held(case, item["id"], scope):
        acceptance = "suspended"
        reasons.append("held")
    authority = "evidence" if acceptance == "accepted" else "none"
    if acceptance in ("pending", "withdrawn"):
        reasons.append(f"not-accepted:{acceptance}")
    if authority == "evidence":
        mandated = any(s["kind"] == "mandate" and s["about"] == item["id"]
                       and trusted(case, s["issuer"], "mandate", scope) for s in case["statements"])
        app = body.get("applicability", {})
        in_time = (("valid_from" not in app or ts(app["valid_from"]) <= now)
                   and ("valid_to" not in app or now < ts(app["valid_to"])))
        ctx, conditions = req.get("context", {}), app.get("conditions", {})
        missing = [k for k in conditions if k not in ctx]
        outside = [k for k, v in conditions.items() if k in ctx and ctx[k] != v]
        excluded = [k for k, v in app.get("exclusions", {}).items() if ctx.get(k) == v]
        if mandated and in_time and not outside and not excluded:
            if missing and req.get("want") == "rule":
                reasons.append("context-missing")
                results.append("escalate")  # rule 3: unknown applicability context escalates
            elif not missing:
                authority = "rule"
        if not in_time:
            reasons.append("outside-valid-time")
        if outside or excluded:
            reasons.append("outside-conditions")
    if authority == "rule" and item["issuer"] != case["node"]:  # rule 6: status freshness of imported items
        source = trusted(case, item["issuer"], "status", scope) or {}
        max_age = source.get("max_status_age_days", DEFAULT_MAX_AGE_DAYS)
        checks = [ts(s["body"]["checked_at"]) for s in case["statements"]
                  if s["kind"] == "status" and s["about"] == item["id"] and s["issuer"] == item["issuer"]]
        last = max(checks) if checks else None
        if max_age == "never":
            if last is None or now - last > timedelta(days=DEFAULT_MAX_AGE_DAYS):
                notices.append("status-not-checked")
        elif last is None or now - last > timedelta(days=max_age):
            authority = "evidence"
            reasons.append("status-stale")

    # --- the requested action ----------------------------------------------------------------------------------
    action, rights = req["action"], body.get("rights", {})
    rules = [r for r in case.get("policy", []) if action in r["actions"] and scope in r["scopes"]
             and req["actor"] in r["subjects"] and ("purposes" not in r or req.get("purpose") in r["purposes"])]
    if any(r["effect"] == "prohibit" for r in rules):
        results.append("deny"); reasons.append("prohibited")
    elif not any(r["effect"] == "permit" for r in rules):
        results.append("deny"); reasons.append("no-permission")  # rule 2
    if action in ("derive", "train", "forward") and rights.get("license", "unknown") == "unknown":
        results.append("deny"); reasons.append("rights-unknown")  # rule 3
    ai_use = rights.get("ai_use", {})
    if action == "train" and ai_use.get("train") != "y":
        results.append("deny"); reasons.append("rights-reserved:train")
    if action == "infer" and ai_use.get("ai_input") != "y":
        results.append("deny"); reasons.append("rights-reserved:ai_input")
    if action == "forward":
        if effective_handling(case, item["id"], scope, "export") == "restricted":
            results.append("deny"); reasons.append("handling-restricted")
        if rights.get("personal_data", "unknown") != "no" and not req.get("legal_basis"):
            results.append("deny"); reasons.append("personal-data-basis-missing")
    if req.get("destination") == "cloud" and effective_handling(case, item["id"], scope, "route") == "local_only":
        results.append("deny"); reasons.append("route-local-only")
    prior = req.get("prior_permit")
    if prior and (prior["item_version"] != item["id"] or ts(prior["expires"]) <= now):
        results.append("deny"); reasons.append("permit-stale")  # rule 7

    result = max(results, key=ORDER.get) if results else "permit"
    return {"result": result, "authority": authority, "reasons": sorted(set(reasons)), "notices": sorted(set(notices))}
