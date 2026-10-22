"""kstd reference erasure reach (draft 0.2, docs/11 §3 `erase`, §5 Inputs). Deterministic, like decide.py.

A case has `statements` (items with optional `inputs`, and `use_record` statements of kind `use` that record a
delivery to another node) and `request: {erase: [item ids]}`. The result is:
- `erased`: the local items among the requested ids and every local item whose recorded inputs reach a requested
  id, transitively. The traversal starts from every requested id, also one that is not held here (remote, or
  already removed): its local descendants are still reached. A derived item is removed whole, never edited; a
  replacement is a new item with a new id.
- `kept`: all other items.
- `unresolved`: reached items (requested or derived, local or not) that were already delivered to another node, as
  `<item>@<node>`.
- `scope_unknown`: kept items that can be derived (origin other than `human`) but record no inputs. An empty
  `inputs` list records none either: it is not proof that the item has no inputs. They are reported, not called
  clean.
The disposition record holds these ids and no content.
"""


def erase(case: dict) -> dict:
    items = {s["id"]: s["body"] for s in case["statements"] if s["kind"] == "item"}
    reached = set(case["request"]["erase"])  # seed with every requested id, local or not
    changed = True
    while changed:  # transitive closure over recorded inputs
        grown = {i for i, body in items.items() if i not in reached and reached & set(body.get("inputs") or [])}
        reached |= grown
        changed = bool(grown)
    erased = reached & set(items)  # only local items are removed here
    kept = set(items) - erased
    unresolved = {f"{s['body']['item']}@{s['body']['to']}" for s in case["statements"]
                  if s["kind"] == "use_record" and s["body"].get("type") == "use" and s["body"]["item"] in reached}
    scope_unknown = {i for i in kept if not items[i].get("inputs") and items[i].get("origin", "unknown") != "human"}
    return {"erased": sorted(erased), "kept": sorted(kept), "unresolved": sorted(unresolved),
            "scope_unknown": sorted(scope_unknown)}
