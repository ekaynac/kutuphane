# Knowledge ontology v2 — draft

**Status:** APPROVED as v2.0 by the operator on 2026-10-15 (D54); all five decisions in §7 are "yes". The draft numbering 0.1/0.2 stays for history.
**Co-authors:** Claude, Astra (GPT-6), Claude Mythos 5.1.
- Round 1: three independent proposals, merged into 0.1.
- Round 2: Astra and Mythos critiqued 0.1. This draft applies their findings; §9 lists the changes.

**Language:** ASD-STE100 Simplified Technical English.
**Scope:** it replaces E1 and K1–K8 of D24 when the operator approves it.

## 0. Canon (operator, 2026-10-14; D53)

1. **Knowledge facets must have meaningful behavioral distinctions.** Each value of a facet must change what the system does: gate, ranking, citation authority, archive, delegation or presentation. A value that changes nothing is removed.
2. **State changes are planned before implementation.**
3. **The ontology is the core.** The implementation stays small: one Python app, Postgres, the fewest tables.
4. Categories are functional, not human genres. Readers and writers can be agents.

Derived rules:
- **R1. Uncertainty never increases authority or access.**
- **R2. One owner for each behavior.** Two facets never control the same behavior. A common combination is a *preset*, not a new value.
- **R3. Strictness order.** Each facet has a strictness order (§3.1). A move to a stricter value can be automatic. A move to a looser value needs the actor that §3.2 names, and it is audited.

## 1. Units

| Unit | What it is | Role |
|---|---|---|
| Book | catalog unit | authorization, access policy, versions (unchanged) |
| Document | one file in a book version | source container; citations stay `book@content/profile/path#ordinal` |
| **Block** | the smallest structural part of a document version | label anchor |
| **Section** | a run of adjacent blocks that have equal effective facet values | derived view; never stored, never drawn by hand |
| Chunk | retrieval unit | never crosses a block boundary, so it has the facets of exactly one block |

### 1.1 Block rule (deterministic, versioned in the profile)

1. A heading starts a block. The heading tree gives each block its parent.
2. Inside a heading section, the rule makes one block for each of these:
   - a paragraph run;
   - a list group (the whole list, not each item);
   - a code fence *together with the paragraph immediately before it*;
   - a table.
3. **Exception for tables with an id column:** when the first column holds unique ids (for example `D24`), each row is a block. Then one row can be retired alone.
4. A block of more than about 4,000 characters splits at paragraph boundaries. A long table splits at row boundaries. A long code fence stays whole, and the review queue flags it.
5. Documents without headings: paragraphs are blocks. A PDF also splits at pages; a block that continues across a page break is joined.
6. A model never draws boundaries. It can flag "this block mixes functions". A curator can then add a **split mark** at a text position. The split mark is an annotation, so the source does not change. On a new version, the split mark is applied again where its surrounding text still matches exactly. If the text does not match, the split mark goes to the review queue.

### 1.2 Block identity and continuity

- **Block reference (immutable):** `book@content_id/profile_id/path#block_ordinal`. It has the same form as a citation, and it names one block of one source version. Labels attach to block references, so ground truth always includes the source version and the block rule version.
- **Continuity links** connect the blocks of two versions. The system computes them:

| Case | Detection | Labels |
|---|---|---|
| Same text, same heading path | `block_hash` and heading path equal | all confirmed labels carry over |
| Same text, new heading path (renamed or moved heading) | `block_hash` equal, path differs | gate labels carry over; other labels carry over **unconfirmed**; Standing goes to `pending` (§3) |
| Changed text | heading path + text similarity | the old labels become **proposals** (unconfirmed); Standing goes to `pending` |
| Renamed or moved file | the block hashes of a removed path appear under one new path | carry over as unconfirmed |
| Identical blocks in one file | match by order with the previous version | a shift in order makes the labels unconfirmed |
| Block removed | no link | Standing → `retired` (automatic, it tightens) |

- `block_hash` = SHA-256 of the normalized text. The normalizer is a profile component. A new normalizer version maps old hashes to new hashes one to one, with no human action.
- "Inherited" is **not a value**. It is an annotation event with `confirmed_by = null`.

## 2. Facets

### 2.1 Labelled facets

| Facet | Question | Values → behavior | Level | Confirmed by |
|---|---|---|---|---|
| **Role** | What kind of claim is this? | `rule` → can establish a requirement: highest citation authority when current (§2.3). When a curator approves a rule, the system lists the current rules with overlapping scope, and the curator decides. There is no automatic conflict decision. `evidence` → supports claims; cited as support. `none` → not indexed, not cited (navigation, license headers, boilerplate). | block | curator |
| **Agent instruction** | Is this text an instruction to an agent? | `yes` → delivery to an agent needs `activate` (D37). Never used as answer evidence. Role does not apply. `no` → no extra gate. | block | curator for `yes → no` |
| **Standing** | Did a curator accept this text? | `approved` → can be current (§2.3). `pending` → not current; shown only when the request asks for open or proposed items, and marked "not accepted". `retired` → history only, with a link to the successor if one exists. | block | curator |
| **Time basis** | When is this true? | `durable` → no time limit. Optional `review_by`, set only by a curator: after that date, answers warn "review date passed" and the curator queue lists the block. `window(start, end)` → current only inside the window. `as_of(t)` is a shorthand for `window(t, t)`: a report about time *t* is history at any later time. | block | curator |
| **Scope** | Where does it apply? | `unbounded` → no filter. `bounded(ids, version ranges)` → current only when the request context matches. For a bounded `rule` with no request context, the system asks for the context and does not answer with authority. Bounded `evidence` with no request context is shown with its scope. | block | curator |
| **Sensitivity** | Which handling restriction applies? | `restricted` → **owns export:** never in a package for an outside installation; vectors and derived text follow the same rule. `normal` → adds no restriction and never overrides the book policy. | document → book policy. A block marked `restricted` makes its document `restricted` (it tightens). | administrator |
| **Egress** | Where may a model process it? | `local_only` → **owns the route:** local model routes only. `cloud_ok` → approved cloud routes allowed. `restricted` + `cloud_ok` is an invalid combination, and the system refuses it, as `check_policy` does today. | document → book policy | administrator |

**Before confirmation:** a document that has no confirmed sensitivity is `local_only` for every model call, including the labelling model (R1).

### 2.2 Valid combinations

| Combination | Result |
|---|---|
| `instruction = yes` | Role, Scope and Time are not applicable to answers. The block is delivered only as an instruction, with `activate`. |
| `role = none` | other facets are ignored; the block never makes its document stricter |
| `rule` + `pending` | a **proposed rule** (a design, plan or proposal): not current; shown as "proposed, not accepted" |
| `evidence` + `pending` | an unverified claim: not current |
| `restricted` + `cloud_ok` | invalid; refused |

### 2.3 Effective value and "current"

**Effective value of one facet on one block**, in this order:
1. the latest **confirmed** event on the block;
2. else the effective value of the parent block (the document root is the top parent);
3. else the profile or book default.

Then apply R1. An unconfirmed proposal applies only when it is stricter **and** its facet is a gate facet: Agent instruction, Standing, Sensitivity or Egress. An unconfirmed Role, Time or Scope proposal does not apply, so a model proposal of `none` cannot hide a block before a curator confirms it. Book policy restrictions always apply, and a block can never weaken them. When two restrictions cannot be compared (two different scopes or windows), both apply; this is their intersection.

**A block is current when all of these are true:**
- its Standing is `approved`;
- `now` is inside its window (`durable` is always inside);
- its scope matches the request (or it is unbounded);
- its role is not `none`;
- its agent instruction is `no`.

Agent-instruction blocks follow their own delivery path.

**Search sets:**
- **current** (the default);
- **open** (pending, only on request);
- **history** (retired, or out of window; only on request, always with its date or successor).

This is the only definition of "history only".

### 2.4 Recorded, not labelled

- **Origin** (who wrote the text: human, agent, model, external; source links) is metadata from ingest. It is shown in explanations. It has no gate of its own, because approval needs `curate`, and `curate` is human-only (§3.2).
- **Presentation** (E2/E7), **protection** (E8) and **access modes** (E9) are unchanged.

### 2.5 Presets (form shortcuts, not stored values)

| Preset | Values |
|---|---|
| record / report | `evidence` + `as_of(date)` (the claim date, which the labeller confirms; the document date is only a proposal) |
| design / plan / proposal | `rule` + `pending` |
| canon / decision | `rule` + `durable` (+ curator approval) |
| runbook | `evidence` + `durable` (`review_by` only if the curator gives a date) |
| agent file | `instruction = yes` |
| boilerplate | `none` |

- A preset sets the **root default**. Child exceptions stay.
- When a non-curator applies a preset, it records **proposals**, not confirmed values.
- A preset never removes an existing restriction.

**Mapping.**

| From | To |
|---|---|
| K1–K8 | presets |
| E1 | Role + Agent instruction |
| E3 | Origin (metadata) |
| E4 | Standing + Time basis |
| E5 | Sensitivity (export) + Egress (route) |
| E6 | Scope |
| E2, E7, E8, E9 | unchanged |

D24 and D25 need an explicit revision decision.

## 3. State changes

Every change is an **append-only annotation event**: `(block ref, facet, value, set_by, confirmed_by, at, reason)`.
- A change is not a content version.
- An access or answer record stores the ids of the events in force (AT-09).
- Reversal is a new event. History is never deleted.
- Time is evaluated at each request, with no background job and no stored "expired" event.

### 3.1 Strictness order (stricter on the right)

| Facet | Order |
|---|---|
| Role | `rule` → `evidence` → `none` |
| Agent instruction | `no` → `yes` |
| Standing | `approved` → `pending` → `retired` |
| Time basis | `durable` → `window`; a narrower window is stricter |
| Scope | `unbounded` → `bounded`; a narrower scope is stricter |
| Sensitivity | `normal` → `restricted` |
| Egress | `cloud_ok` → `local_only` |

### 3.2 Actors

| Actor | Right | Changes |
|---|---|---|
| system | — | stricter moves only: the continuity table §1.2, block removed, supersession (§3.3) |
| model (labelling) | — | proposals only |
| curator | new mode **`curate`** on the book; **only `user:` principals** can hold it (a database check, as for delegation). Allowing agents needs a new decision. | looser moves of Role, Agent instruction, Standing, Time basis, Scope |
| administrator | policy rights (unchanged) | looser moves of Sensitivity and Egress (new policy version) |
| grant holder | grant rights (unchanged) | enactment (§4) |

### 3.3 Standing transitions

| From → to | Trigger | Actor | Automatic |
|---|---|---|---|
| (new block) → pending | ingest | system | yes |
| pending → approved | review | curator | no |
| approved → pending | text or heading path changed (§1.2) | system | yes |
| retired → (any) | — | **never automatic**: a text change keeps `retired` | — |
| pending/approved → retired | rejected, withdrawn or replaced | curator | no |
| pending/approved → retired | block removed in the new version | system | yes |
| approved → retired | **supersession**: a successor `rule` is approved, it declares `supersedes`, its window has started, and the predecessor's scope is inside the successor's scope. For a partial overlap, the curator narrows the predecessor's scope instead. | system | yes |
| retired → pending | reopen, or the successor lost approval or expired | curator | no |

`supersedes` links can never form a cycle or point to the block itself; the system refuses them. A **planned window** that a curator approved starts automatically on its date. That is not a looser move without a human, because the approval covered the dates and the scope.

**Measured risk:** a document that changes weekly loses `approved` weekly. This is by design. The blind slice measures "approved blocks that lose standing for each version".

## 4. Decisions and permissions inside documents

1. **A decision** is a block with role `rule`. Its fields (scope, window, `supersedes`) are annotations, so there is no separate decision database. The text is the source of truth for **intent**. The annotations say how the system **uses** the text now. A policy change that a decision requires is made by an administrator as a new policy version, with the block reference in its reason.
2. **A permission in text is never executable by itself.** There is no automatic extraction, no permission from prose and nothing on import. A grant holder can **enact** it:
   - The enactment form states the exact grant: subject, mode, book, scope, start, expiry and delegation limit. The human reviews this exact grant.
   - The system checks the human's grant rights, and that the block is current (approved, in window, in scope).
   - The grant or delegation stores a **structured source column**: the block reference plus the annotation event ids in force. It does not use free-text `purpose`.
   - Enactment is an access event (AT-09). Repeated enactment of the same block does not make a duplicate grant.
   - The enactment never widens the text: a block permission never becomes a broader grant.
3. **The grant table is the truth for behavior**, and authorization enforces the expiry on each request.
   - **Direct grants need `expires_at`**, a nullable column, with the same check as delegations.
   - When the source block is **retired** (by a curator, by supersession or by removal), the system **suspends** the linked grant. This is automatic, because it tightens. Only a grant holder restores it.
   - A text change alone does not suspend the grant, because the grant came from a confirmed earlier version. The drift view shows it.
   - A grant holder can always revoke a grant, without a document change.
4. **The drift view** compares linked grants with their blocks. It shows these cases:
   - the text changed;
   - a successor rule was approved;
   - the window ended, but the grant is still active;
   - the grant was revoked, but the text still allows the action.

   A human closes each case.
5. **Document TTL is not permission TTL.**
   - A document has no TTL of its own; it is archive-ready when all its blocks are `retired` or history.
   - A decision has its own window.
   - A permission has its grant expiry.
6. **Accepted gap:** a prohibition in text ("agent X may not …") has no grant to compare against. It stays a `rule` that answers can cite. Enforcement is the absence of a grant.

## 5. Labelling protocol

1. **Rules first**, then a model, both **on local routes only** until sensitivity is confirmed. The rules propose presets from these signals:
   - frontmatter `type`;
   - heading words (Decision/Karar, Status, Proposal/Öneri, Report/Rapor, Plan);
   - dates in headings and file names;
   - path patterns.

   More rules:
   - A block whose hash appears in more than N files gets the proposal `none`, and it skips the queue.
   - A block whose hash equals a current `rule` elsewhere in the book is a quotation: the proposal is `evidence`, with a link to the original.
   - Each proposal has a confidence value and its evidence text.
2. **The screen** shows one document as its heading tree:
   - one colored strip per section;
   - document-level sensitivity and egress, plus a block-level "restricted" mark;
   - extracted dates;
   - collapsed high-confidence sections.
3. **The human** does these steps:
   1. confirms sensitivity and egress;
   2. confirms agent-instruction blocks;
   3. corrects the visible low-confidence blocks;
   4. selects a document preset (the root default). If the labeller is not a curator, the result is proposals;
   5. can select "needs detailed review". This is a workflow result, not a label.
4. **Blind slice:** about 30 % of documents (D43). The measures are:
   - agreement;
   - boundary errors;
   - missed instructions;
   - **missed restrictions and false authority** (a wrong `rule` or `approved`);
   - corrections;
   - total time, including deferred work;
   - standing loss per version.
5. **Ground truth** is on block references. Unchanged blocks in a later version cost no time.
6. **Target:** a median below 45 s for the first review pass. Detail on long mixed documents is deferred work.
7. **Before building the page:** measure the rule proposer on the 14 existing labels and the 163 drafts. Map K1–K8 to presets for this. No new page is necessary for this measurement.

## 6. Agent-to-agent

- Role values are kinds of claims (`rule`, `evidence`, `none`), not genres.
- Labels travel in signed packages. The receiving installation approves them, and it can override access (D23).
- Agents can write text and propose labels. To confirm, a principal needs `curate`, which is human-only today. If agents ever get `curate`, that is a new decision, and the audit shows every use.
- An agent can point to a claim with a block reference ("I acted on rule X"). Later the audit can show that the rule was retired, and which rule replaced it.

## 7. Operator decisions (2026-10-15: yes to all five)

1. **Mixed sensitivity:** a document-level gate plus a block mark that tightens the document. Threshold: if more than 10 % of blind documents are mixed, design section-level gates. Measure first. **Approved.**
2. **`curate` is human-only now.** **Approved.**
3. **Grant `expires_at`** and **automatic suspension** of grants whose source block is retired. **Approved.**
4. **Table rows as blocks** (id column). This affects `docs/01` itself. **Approved.**
5. **Order of work** (**approved**):
   1. this document;
   2. D53 (canon) and the D24 revision;
   3. measure the rule proposer;
   4. build the labelling page v2;
   5. label;
   6. implement the annotation events.

## 8. What we will not do

- section ACLs;
- model-drawn boundaries;
- automatic permission extraction;
- confidence as truth;
- labels inside the content hash;
- stored "stale" or "expired" values;
- a separate decision database;
- open vocabularies on gate facets;
- new values without a named behavior;
- `curate` for agents without a new decision;
- bulk enactment;
- automatic conflict resolution between rules.

## 9. Changes from 0.1 (round-2 findings)

**From Astra:**
- `proposal` removed from Role; Standing owns acceptance;
- instruction and evidence conflict resolved (§2.2);
- effective-value rule (§2.3);
- retirement is never reopened automatically;
- supersession limited to the shared scope and a started window; no cycles;
- structured enactment and a source column (§4);
- automatic suspension on retirement;
- `curate` only for content review, with policy and grants unchanged;
- origin is metadata;
- block references per source version (§1.2).

**From Mythos:**
- strictness orders replace the gate table (§3.1);
- `as_of` = `window(t, t)`;
- one definition of history (§2.3);
- export owned by Sensitivity, route owned by Egress;
- role `none`;
- context change and rename detection;
- duplicate-block matching;
- table rows with ids as blocks;
- normalizer migration;
- code fence bound to the paragraph before it;
- local-only before confirmation;
- quotation rule;
- block removal → retired;
- presets record proposals for non-curators;
- prohibitions accepted as a gap.
