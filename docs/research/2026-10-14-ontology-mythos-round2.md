The draft is clear enough to critique. Here is my round-2 review.

# Round 2 critique of `docs/09-ontology-v2.md` (co-author: Mythos)

## 1. Canon test

**Role (§2).** `evidence` and `rule`: no finding. `proposal` fails partly. Its behavior ("proposed, not decided", answers only for option questions) is the same behavior that Standing `pending` claims ("review and proposal answers only"). The preset `design/plan = proposal + pending` shows the overlap. Decide one owner: `proposal` owns the presentation ("not decided"), `pending` owns authority only. Then a `proposal + approved` block has a meaning: the owner accepts that this is a real option.

**Agent instruction (§2).** `yes` says "never used as answer evidence". That is a citation behavior, and Role owns citation. For an instruction block, Role has no effect. Say so: when `instruction = yes`, Role is not applicable. Change the preset `agent file` to `instruction = yes` only.

**Time basis (§2, §3.2).** `as_of(t)` and an ended `window` have the same effect: history only, cited with a date, never stale. Make `as_of(t)` a shorthand for `window(t, t)`. The facet then has two values: `durable` and `window`.

**Standing `retired`, ended `window`, `as_of` (§2, §4).** Three values claim the archive behavior ("history only", "archive-ready"). Define "history only" once: is the text in current search or not? Then give the behavior to one facet.

**Sensitivity and Egress (§2).** `restricted` claims "no cloud route". Egress `local_only` claims the same route. D24 says sensitivity is not egress, so keep two facets, but give each one behavior: Sensitivity owns export and packaging; Egress owns the route. A policy preset sets `local_only` when a document becomes `restricted`. The facet text must not say "forces".

**Missing value.** The draft removes "does not fit" (§2), so navigation text, licence headers and boilerplate become `evidence`. They then support claims. Add Role `none`: not indexed, not cited. This value has one named behavior, so it passes canon 1.

**Origin (§2).** No finding on behavior. One gap: ingest metadata is per file, but "an agent cannot approve its own text" needs the author per block.

## 2. Transitions

**Conflict 1 (§1.2 vs §3.1).** §1.2 says an unchanged anchor keeps every label with no action. §3.1 says "the context of the block changed" sets `approved → pending`. The anchor does not contain the heading path, so a renamed heading, or a block moved under a new heading, is "unchanged". Nothing detects the context change. Define context as the heading path, store it on the anchor row, and make a context change set non-gate labels to unconfirmed, not to `pending`.

**Conflict 2 (§1.2 vs §2).** §1.2 proposes old labels as `inherited`. Standing has no value `inherited`. Say: `inherited` is not a value; it is an annotation event with `confirmed_by = null`. Standing is never inherited; it always goes to `pending` on a text change.

**§1.2 step 3** says "the stricter of the old and the new value". On a changed block there is no new value until a model proposes one. Write "old confirmed value or model proposal, whichever is stricter".

**Missing transitions (§3.1).**
- A block that disappears in a new version has no row. Add `approved/pending → retired`, system, automatic (it tightens).
- "Reopen" after a superseded successor is retired: reopen to `pending`, not to `approved`. Otherwise the system loosens.
- Time and Scope changes are missing from §3.3. `durable → window` and `unbounded → bounded` tighten. The reverse loosens. An owner who extends a window loosens.

**Replace §3.3 with one order per facet.** Role: `rule > evidence > proposal > none`. Standing: `approved > pending > retired`. Time: `durable > window`. Scope: `unbounded > bounded`. Instruction: `no > yes` for the gate. Egress: `cloud_ok > local_only`. Then one rule: a move down is automatic; a move up needs the actor named in §2. The table in §3.3 becomes unnecessary.

**Inheritance (§1.1).** No finding on the default rule. One rule is missing: resolve the effective value as explicit block event, then parent effective value, then profile default. Apply "stricter of" after resolution.

**Preset application (§2, §5.3 step 4).** A document preset `canon/decision` moves `evidence → rule`. That is a loosening. The labeller in §5 is not always the owner. Say: a preset by a non-owner records proposals, not confirmed values. Say also: a document preset sets the root default only, and child exceptions stay. The `runbook` preset names `review_by` without a date; a preset cannot supply a date.

**Loop risk (§3.1).** Each real edit sets `approved → pending`. A document that changes weekly never has authority. This is by design, so no change, but measure it on the blind slice: "share of approved blocks that lose standing per version".

## 3. Units and anchors

- **Moved file (§1.2).** `path` is in the anchor. A directory reorganization makes every block new. All labels are lost. Add rename detection: when a path disappears and its block hashes appear under one new path, propose the labels as unconfirmed.
- **Reordered identical blocks.** `occurrence` is positional. Insert a duplicate before the original, and the labels of the original move to the copy. Assign `occurrence` by stable matching with the previous version, and mark any shift unconfirmed.
- **Duplicated boilerplate.** The same "Confidential" line in 200 files is 200 anchors and 200 reviews. A rule "same hash in more than N files" proposes Role `none` and skips the queue. A restricted boilerplate line must not tighten 200 documents; this is one more reason for `none`.
- **Quoted rule in a review.** The heading words ("Decision") make the rule-based proposer (§5.1) propose `rule`. Two approved rules with the same text then conflict. Rule: a block whose hash equals an approved `rule` in the book gets `evidence` with a link to the original.
- **Table of rules (§1.1).** A table is one block. `docs/01-direction-decisions.md` is a table with one decision per row. The draft cannot retire one row. Each edit changes the hash of the whole table. Make a table row a block when the table has an id column. The split annotation in §1.1 does not help, because the hash moves at each edit.
- **Hash stability (§1.2).** "Normalized text" is not defined. The normalizer is a profile component (§1.1). A new normalizer version changes every hash. Define the migration: old hash to new hash, one to one, no human action.
- **"Code fence with its explanation paragraph" (§1.1).** Before or after? The rule is not deterministic until this is written.

## 4. Decisions and permissions

The three parts are enough for grants. These items are missing:

- Enactment is an access event with the anchor and the annotation ids in force. AT-09 then shows the chain.
- Drift (§4) lacks two cases: the block was retired, and a successor rule was approved.
- Store the source handle in a column, not in free-text `purpose`. The drift view must join on it.
- "Checked for conflicts" (§2, `rule`) is not defined. Most rules are `unbounded`, so every pair overlaps. Define: at approval, the owner sees the list of approved rules in overlapping scope. There is no automatic conflict decision.
- A prohibition in text ("agent X may not use book Y") has no grant to compare. Accept this gap and add it to §8.
- Decisions that change policy (not grants) have no enact path. Say: the administrator makes the policy version by hand with the block handle in its reason.

## 5. Open points

1. **Record.** Keep the preset. A role `record` would copy the `evidence` behavior. With `as_of = window(t, t)` the preset is `evidence + window`.
2. **`review_by`.** Keep it, optional, on `durable` only. The model may propose it, only the owner sets it. Reason: it creates human queue work, so it must not be automatic.
3. **Mixed sensitivity.** Measure first, but write the threshold now (for example 10 % of blind documents). The form in §5.2 shows only document-level sensitivity, so it cannot measure the mix. Add a block-level "restricted" mark that tightens the document.
4. **`curate`.** Add it. Map the actors once: owner = book owner grant; curator = `curate` grant for Role, Standing, Time, Scope, Instruction; administrator = policy for Sensitivity and Egress. Reason: §3.1 says owner, §3.3 says curator and administrator, and §6 needs one grant that an agent can get.
5. **`expires_at`.** Add the nullable column. Delegations have it, and AT-06 already tests expiry. The check uses one code path.
6. **Rule quality.** Measure it on the existing D43 labels with a K1–K8 to preset map. No new page is necessary for precision.

## 6. Overcomplication and gaps

**Remove.** §3.3 (replaced by the facet orders). `as_of` as a third value. "Forces" between Sensitivity and Egress. `inherited` as a state. The separate "document default" for Standing, because the document root is the top parent block.

**Change.** "A chunk never crosses a block boundary" (§1) makes one-sentence chunks for lists. Change it to "a chunk never crosses a section boundary". A section has one facet set, so the guarantee holds.

**Missing, important.** A model that proposes labels reads the text before Sensitivity is confirmed. By the derived rule in §0, the default before confirmation must be `local_only`. The draft does not say this. Add it to §5.1.

**Missing, small.** The deleted-block transition (§3.1), the resolution order (§1.1), Role `none` (§2), rename detection (§1.2), and row-level blocks for id tables (§1.1).