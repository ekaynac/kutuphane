"""kstd reference decision rule (draft 0.3, docs/11 §4–§5). Small and deterministic: the same case gives the same
result and the same reasons. It exists to make the conformance cases precise, not to be fast.

A case has: `now`, `node` (this node's issuer id), `policy_version`, `trust`, `precedence`, `statements`, `policy`,
`request`. The result is {result: permit|deny|escalate, authority: rule|evidence|none, reasons, notices}.
"""
from datetime import datetime, timedelta

ORDER = {"permit": 0, "escalate": 1, "deny": 2}  # rule 1: the strictest result wins
STRICT = {"export": ["normal", "restricted"], "route": ["cloud_ok", "local_only"]}
DEFAULT_MAX_AGE_DAYS = 30
VIEWS = {"ordinary": {"accepted"}, "review": {"accepted", "pending"}, "history": {"accepted", "withdrawn", "rejected"}}  # rejected: never accepted (D68)


def ts(value) -> datetime:
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def trusted(case, issuer, kind, scope, action) -> dict | None:
    """Rule 4: the node itself is trusted. Another issuer only for an explicit kind × scope × action, with an
    expiry that has not passed. `action=None` asks for trust in kind × scope for any action (restriction
    admissibility)."""
    if issuer == case["node"]:
        return {"issuer": issuer}
    now = ts(case["now"])
    for t in case.get("trust", []):
        if (t["issuer"] == issuer and kind in t["kinds"] and scope in t["scopes"]
                and (action is None or action in t.get("actions", []))
                and "expires" in t and ts(t["expires"]) > now):
            return t
    return None


def about(case, item_id, kind):
    return [s for s in case["statements"] if s["kind"] == kind and s["about"] == item_id]


def latest_per_issuer(statements) -> dict:
    out = {}
    for s in sorted(statements, key=lambda s: ts(s["issued_at"])):
        out[s["issuer"]] = s  # a revision replaces the same issuer's earlier statement; never another issuer's
    return out


def acceptance_of(case, item_id, scope, action, reasons, notices) -> str:
    """Rule 5 (conflicts between trusted issuers) and rule 8 (no untrusted removal of accepted knowledge)."""
    values = {}
    for issuer, s in latest_per_issuer(about(case, item_id, "acceptance")).items():
        if trusted(case, issuer, "acceptance", scope, action):
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


def handling_of(case, src, action, prop) -> tuple[str, list]:
    """Rule 4. A looser value counts only from an issuer trusted for handling × scope × action. A tightening counts
    from the node, the item's own issuer, or an issuer trusted for handling × scope (any action); the strictest
    counted value wins, and with no counted value the strictest value applies (unconfirmed handling, §5).
    A later statement replaces the same issuer's earlier one, except that a loosening that does not count never
    replaces a tightening that counts: the restriction stays in force.
    Returns the value and the issuers of tightenings that do not count (only when the value is not already the
    strictest): they escalate, they never deny."""
    order, scope = STRICT[prop], src["body"]["scope"]
    current = {}  # issuer -> (value, counts)
    statements = [s for s in about(case, src["id"], "handling") if prop in s["body"]]
    for s in sorted(statements, key=lambda s: ts(s["issued_at"])):
        issuer, value = s["issuer"], s["body"][prop]
        tightens = value == order[-1]
        counts = bool(trusted(case, issuer, "handling", scope, action) or (
            tightens and (issuer == src["issuer"] or trusted(case, issuer, "handling", scope, None))))
        held = current.get(issuer)
        if not counts and not tightens and held and held[1] and held[0] == order[-1]:
            continue  # an unauthorized loosening does not supersede an admissible restriction
        current[issuer] = (value, counts)
    counted = [value for value, counts in current.values() if counts]
    untrusted = [issuer for issuer, (value, counts) in current.items() if not counts and value == order[-1]]
    value = max(counted, key=order.index) if counted else order[-1]
    return value, ([] if value == order[-1] else untrusted)


def restrict(results, reasons, notices, handling, strictest, reason) -> None:
    """Rule 4: a counted strictest value denies; a tightening that does not count escalates and names its issuer."""
    if any(value == strictest for value, _ in handling):
        results.append("deny"); reasons.append(reason)
    elif any(untrusted for _, untrusted in handling):
        results.append("escalate"); reasons.append("restriction-untrusted")
        notices.extend(f"restricted-by:{issuer}" for _, untrusted in handling for issuer in untrusted)


def statements_after(case, item_id, moment) -> bool:
    return any(ts(s["issued_at"]) > moment for s in case["statements"]
               if s.get("about") == item_id or s.get("id") == item_id)


def lineage(case, item) -> tuple[list, bool]:
    """§5 Inputs: every recorded ancestor of `item`, transitively (inputs of inputs), each once, so a cycle ends.
    Returns (ancestor statements, whether a recorded input is missing). A missing ancestor fails closed."""
    items = {s["id"]: s for s in case["statements"] if s["kind"] == "item"}
    seen, todo, found, missing = {item["id"]}, list(item["body"].get("inputs", [])), [], False
    while todo:
        input_id = todo.pop()
        if input_id in seen:
            continue
        seen.add(input_id)
        if input_id not in items:
            missing = True
            continue
        found.append(items[input_id])
        todo.extend(items[input_id]["body"].get("inputs", []))
    return found, missing


def personal_data_of(case, src, action) -> str:
    """§5: personal data unknown counts as yes; only a trusted issuer can declare data synthetic."""
    personal = src["body"].get("rights", {}).get("personal_data", "unknown")
    if personal == "synthetic" and not trusted(case, src["issuer"], "item", src["body"]["scope"], action):
        return "unknown"
    return personal


def decide(case: dict) -> dict:
    req, now = case["request"], ts(case["now"])
    reasons, notices, results = [], [], []
    item = next((s for s in case["statements"] if s["kind"] == "item" and s["id"] == req["item"]), None)
    if item is None:
        return {"result": "deny", "authority": "none", "reasons": ["unknown-item"], "notices": []}
    body, scope, action = item["body"], item["body"]["scope"], req["action"]

    # --- availability: acceptance in the requested view (§5, rule 8) -----------------------------------------
    acceptance = acceptance_of(case, item["id"], scope, action, reasons, notices)
    held = any(trusted(case, s["issuer"], "hold", scope, action) and ts(s["body"]["review_by"]) > now
               for s in about(case, item["id"], "hold"))
    if acceptance == "conflict":
        results.append("escalate")
    elif held:
        acceptance = "suspended"
        reasons.append("held")
    if acceptance != "conflict" and acceptance not in VIEWS[req.get("view", "ordinary")]:
        results.append("deny")
        if not held:
            reasons.append(f"not-accepted:{acceptance}")

    # --- authority for answers ---------------------------------------------------------------------------------
    authority = "evidence" if acceptance == "accepted" else "none"
    if authority == "evidence":
        mandated = any(trusted(case, s["issuer"], "mandate", scope, action) for s in about(case, item["id"], "mandate"))
        app = body.get("applicability", {})
        in_time = (("valid_from" not in app or ts(app["valid_from"]) <= now)
                   and ("valid_to" not in app or now < ts(app["valid_to"])))
        ctx, conditions = req.get("context", {}), app.get("conditions", {})
        missing = [k for k in conditions if k not in ctx]
        outside = [k for k, v in conditions.items() if k in ctx and ctx[k] != v] + \
                  [k for k, v in app.get("exclusions", {}).items() if ctx.get(k) == v]
        wants_rule = req.get("want") == "rule"
        if not in_time:
            reasons.append("outside-valid-time")
        if outside:
            reasons.append("outside-conditions")
        if mandated and in_time and not outside:
            if not missing:
                authority = "rule"
            elif wants_rule:
                reasons.append("context-missing")
        if wants_rule and authority != "rule" and (missing or outside or not in_time) and mandated:
            results.append("escalate")  # rule 3 and §5: authority is needed but the context does not fit
    if authority == "rule" and item["issuer"] != case["node"]:  # rule 6: status freshness of imported items
        source = trusted(case, item["issuer"], "status", scope, action) or {}
        max_age = source.get("max_status_age_days", DEFAULT_MAX_AGE_DAYS)
        checks = [ts(s["body"]["checked_at"]) for s in about(case, item["id"], "status") if s["issuer"] == item["issuer"]]
        last = max(checks) if checks else None
        if max_age == "never":
            if last is None or now - last > timedelta(days=DEFAULT_MAX_AGE_DAYS):
                notices.append("status-not-checked")
        elif last is None or now - last > timedelta(days=max_age):
            authority = "evidence"
            reasons.append("status-stale")

    # --- the requested action ----------------------------------------------------------------------------------
    rules = [r for r in case.get("policy", []) if action in r["actions"] and scope in r["scopes"]
             and req["actor"] in r["subjects"] and ("purposes" not in r or req.get("purpose") in r["purposes"])]
    if any(r["effect"] == "prohibit" for r in rules):
        results.append("deny"); reasons.append("prohibited")
    elif not any(r["effect"] == "permit" for r in rules):
        results.append("deny"); reasons.append("no-permission")  # rule 2
    # §3 derive / §5 inputs: the item AND every recorded ancestor (inputs of inputs, transitively) are checked for
    # this use: rights, AI-use terms and personal data per source; handling is inherited, the strictest value wins.
    ancestors, missing = lineage(case, item)
    if missing:
        results.append("deny"); reasons.append("input-unknown")
    sources = [item] + ancestors
    destination = str(req.get("destination", ""))
    to_cloud = destination == "cloud" or destination.startswith("cloud:")  # `cloud` or `cloud:<host>`
    # §5 personal data: `forward`, and `infer` to a model outside the node (a cloud destination), need a legal basis.
    discloses = action == "forward" or (action == "infer" and to_cloud)
    for src in sources:
        tag, src_rights = ("" if src is item else "input-"), src["body"].get("rights", {})
        if action in ("derive", "train", "forward") and src_rights.get("license", "unknown") == "unknown":
            results.append("deny"); reasons.append(f"{tag}rights-unknown")  # rule 3
        ai_use = src_rights.get("ai_use", {})
        if req.get("operation") == "search" and ai_use.get("search") != "y":  # an embedding search needs no ai_input
            results.append("deny"); reasons.append(f"{tag}rights-reserved:search")
        if action == "train" and ai_use.get("train") != "y":
            results.append("deny"); reasons.append(f"{tag}rights-reserved:train")
        if action == "infer" and ai_use.get("ai_input") != "y":
            results.append("deny"); reasons.append(f"{tag}rights-reserved:ai_input")
        if (discloses and personal_data_of(case, src, action) not in ("no", "synthetic")
                and not req.get("legal_basis")):
            results.append("deny"); reasons.append(f"{tag}personal-data-basis-missing")
    if action == "forward":
        restrict(results, reasons, notices, [handling_of(case, s, action, "export") for s in sources],
                 "restricted", "handling-restricted")
    if to_cloud:
        restrict(results, reasons, notices, [handling_of(case, s, action, "route") for s in sources],
                 "local_only", "route-local-only")
    prior = req.get("prior_permit")  # rule 7: a permit is bound to exact versions and has an expiry
    if prior and (prior["item_version"] != item["id"] or prior["policy_version"] != case.get("policy_version")
                  or statements_after(case, item["id"], ts(prior["issued_at"])) or ts(prior["expires"]) <= now):
        results.append("deny"); reasons.append("permit-stale")

    result = max(results, key=ORDER.get) if results else "permit"
    return {"result": result, "authority": authority, "reasons": sorted(set(reasons)), "notices": sorted(set(notices))}
