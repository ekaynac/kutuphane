"""kstd reference erasure reach (draft 0.2, docs/11 §3 `erase`, §5 Inputs). Deterministic, like decide.py.

A case has `statements` (items with optional `inputs`, and `use_record` statements of kind `use` that record a
delivery to another node) and `request: {erase: [item ids]}`. The result is:
- `erased`: the requested items and every item whose recorded inputs reach an erased item, transitively. A derived
  item is removed whole, never edited; a replacement is a new item with a new id.
- `kept`: all other items.
- `unresolved`: erased items that were already delivered to another node, as `<item>@<node>`.
- `scope_unknown`: kept items that can be derived (origin other than `human`) but record no inputs. They are
  reported, not called clean.
The disposition record holds these ids and no content.
"""


def erase(case: dict) -> dict:
    items = {s["id"]: s["body"] for s in case["statements"] if s["kind"] == "item"}
    erased = set(case["request"]["erase"]) & set(items)
    changed = True
    while changed:  # transitive closure over recorded inputs
        grown = {i for i, body in items.items() if i not in erased and erased & set(body.get("inputs", []))}
        erased |= grown
        changed = bool(grown)
    kept = set(items) - erased
    unresolved = {f"{s['body']['item']}@{s['body']['to']}" for s in case["statements"]
                  if s["kind"] == "use_record" and s["body"].get("type") == "use" and s["body"]["item"] in erased}
    scope_unknown = {i for i in kept if "inputs" not in items[i] and items[i].get("origin", "unknown") != "human"}
    return {"erased": sorted(erased), "kept": sorted(kept), "unresolved": sorted(unresolved),
            "scope_unknown": sorted(scope_unknown)}
