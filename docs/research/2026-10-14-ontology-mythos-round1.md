Here is my independent proposal.

# Kütüphane ontology, proposal by Claude Mythos (2026-10-14)

Basis: brainstorm doc §2, decisions D24–D52, M1 tests, and the code in `catalog.py`, `profiles.py`, `authz.py`, `search.py`, `answers.py`. The code today enforces three things: sensitivity and egress on a book policy, the four access modes on grants, and the instruction flag on chunks. Everything below is built so that it adds the fewest new tables to that.

## 1. Sections

**Boundary rule.** The section is the markdown heading tree. Each heading starts a section. The section runs until the next heading of the same or higher level. Nested headings are child sections. The paragraph chunker that exists stays below sections: a chunk never crosses a section boundary. Code blocks, lists and tables stay inside their section.

I do not recommend semantic or facet-driven boundaries. A facet-driven boundary is circular: you must know the facet to find the boundary, and you must know the boundary to label the facet. A model-made boundary is not reproducible, so the chunk ordinal in a citation would not be stable. Instead: **if a facet changes inside a section, the human adds a heading.** The text is the only source of boundaries.

Sizes: no minimum. Maximum is the heading section itself; a section with no sub-headings and more than about 8000 characters gets a flag "add headings". Documents with no headings (PDF pages, flat notes) have one section per file, or one per page for PDF. That is acceptable: such documents get one label set, as today.

**Identity across versions.** A section has two keys:

- `section_hash` = SHA-256 of the normalized section text (whitespace folded, frontmatter removed). This is the label anchor. Same text, same hash, in any document, any version.
- `heading_path` = book, path, and the slugged chain of headings. This is the lineage hint.

Labels attach to `section_hash`. On a new content version, a section whose text did not change keeps its labels with no action. A section whose text changed is matched by `heading_path`. Its labels carry over with the mark `inherited`, not `confirmed`. A split produces children that inherit the parent's labels as `inherited`. A merge keeps a label only if all merged parts had the same value; if not, the merged section has no value and goes to the review queue. The decisive point: the system only ever **proposes** a carry-over of changed text. Ground truth is confirmed only on an exact `section_hash`. This satisfies "labels survive where text did not change" with no extra logic.

**Who decides.** The rule decides boundaries. The rule is a profile component, so its version is in the profile id (AT-02 holds). A human corrects a boundary by editing the source: add, move or remove a heading, which makes a new content version. A model never changes a boundary. It may only say "this section seems to hold two functions" and put it in the queue.

## 2. Facets

Principle: a facet exists only if a value changes a gate, ranking, citation, archive or presentation. Six facets. Three exist today.

| Facet | Question | Values | Behavior per value | Vocab | Level | Set by, confirmed by |
|---|---|---|---|---|---|---|
| **sensitivity** (E5) | May this leave the trusted store? | `normal`, `restricted` | `restricted`: no cloud route, not in packages marked for export outside the installation. Pre-filter today. | closed | document | human; rule may propose `restricted` from patterns |
| **egress** (E5) | Which model routes may see it? | `local_only`, `cloud_ok` | selects the LLMDAP route; `restricted` forces `local_only` (today). | closed | document | human |
| **protection** (E8) | How is it stored? | `standard` (M1) | storage path; M2 `envelope`, `sealed`. | closed | document | admin |
| **role** (new, replaces E1 and the instruction flag) | What may the system do with this text? | `cite`, `instruct`, `decide`, `propose`, `record` | see table below | closed | section, inherited down the tree | rule and model propose; human confirms |
| **validity** (new, replaces E4) | Is this text still in force? | `current`, `retired`; `stale` is derived | see §3 | closed | section, inherited down | human sets `retired`; `stale` is automatic |
| **applies_to** (E6) | Where is it valid? | free tags (`platform:x`, `tested_on:...`) | filter only, no gate | open | section | anyone |

Role behaviors:

- `cite`: searchable, usable as evidence, cited as support. Default.
- `instruct`: served only with `activate`; never in evidence without it. This is the existing instruction flag, moved to the section level, so a design doc may hold one `instruct` section without making the whole book K3.
- `decide`: searchable; cited as authority. Answers mark it "decision". It is the only role that may carry a `valid_until` and a `supersedes` link. It is the only role a curator may enact (§4).
- `propose`: searchable; the answer prompt marks the passage "proposed, not decided"; the model is told not to state it as fact. Ranked below `cite` and `decide` hits on ties.
- `record`: searchable; cited with its date; the prompt marks it "report as of date". It is never `current` in the sense of truth, so it needs no review date and never becomes stale. This takes the stale run reports off the review queue.

Removed: E2 (presentation lives in the profile), E3 origin (label provenance, see "set by", not a content facet), E7 audience (changes nothing in the system today), E9 (lives on grants, not content). K1–K8 become **ingest presets**, not stored values: K3 = root section `instruct`; K5 = root `record`; K2 = `cite` with `applies_to` tags; K1 = `cite`. "Does not fit" disappears, because every section has a role. The brief's five "does not fit" documents are `propose` or `cite` plus `decide` sections.

Sensitivity and egress stay at document level. A restricted section makes the document restricted. The pre-filter is per book, and a section-level gate would need chunk-level filtering in every query path. The brief says authorization is per book, so I keep that. The cost is that a mixed document must be split by the curator. I am not sure this cost is acceptable for the MCP-notes document; it is the one open point I would test.

Storage: one append-only table `label(section_hash, facet, value, set_by, confirmed_by, created_at, superseded_at, note)`. Chunks get a `section_hash` column. The policy table stays as is.

## 3. State changes

Only `validity` has states. `role` and `sensitivity` are set, not transitioned; a change is a new label row.

| From | To | Trigger | Who | Automatic | Audited | Reversible |
|---|---|---|---|---|---|---|
| current | stale | `review_by` date passed | clock | yes, derived at query time | no row written; the query result shows it | yes: new `review_by` |
| current or stale | current | human confirms "still valid", sets new `review_by` | curator | no | yes | yes |
| current or stale | retired | human, optional `successor` citation | curator | no | yes | yes, new row |
| current (role `decide`) | retired | a newer `decide` section with `supersedes` = this hash is confirmed | rule, on confirm | yes | yes | yes, by retiring the successor |
| retired | current | human reopens | curator | no | yes | yes |

Behavior: `stale` keeps search and citation, but the answer prompt gets "snapshot, review date passed". `retired` is out of search by default; an old citation still opens (AT-07) and shows the successor if one exists.

A facet change is an **event**: a new row in `label`. It is not a content version, because the text did not change and the content hash must not move. It is not a separate facet version id either; the access log records the label row ids in force, as it records grant ids today. That gives AT-09 "which labels decided this" with no new id scheme.

Time-based change without a person: store `review_by`; compute `stale` in the query. No job, no cron, no state write.

## 4. Decisions and permissions inside documents

Options:

1. Leave them in the text. Simple. The system cannot tell "decided" from "noted". Fails the operator's TTL finding.
2. Extract decisions as first-class records with scope and TTL. Precise. Two sources of truth, and a second editing surface.
3. Map permissions in text to the grant system. Executable. A document would then change authorization, which is a prompt-injection path.

Recommendation: **1 plus the `decide` role, and 3 only through a human hand.**

- A decision is a section with role `decide`. Its structured fields are a small frontmatter-style block inside the section: `id`, `valid_until`, `supersedes`, `scope`. The text stays the source of truth. A derived index of these fields can be rebuilt from the text at any time, so there is no second truth.
- A permission in a document ("agent X may use book Y for 30 days") is a `decide` section. It is **not** executable by itself. A curator with grant rights may "enact" it: the system creates the grant or delegation with the expiry from the section, and writes the section's citation handle into the grant's `purpose`. The grant table is the truth for behavior. The document is the truth for intent.
- When they disagree (text changed, grant did not; grant revoked, text still says allowed), the system does nothing automatic. It lists the pair in a "drift" view by comparing `purpose` handles with current `decide` sections. A human closes the gap.
- Who may enact: a human with admin on the object. Never an agent, never on import, never from a package. A package may carry `decide` sections; enactment happens in the receiving installation.

This keeps "document TTL" (`review_by`) and "permission TTL" (grant `expires_at`) as two fields in two tables, which is what the operator described.

## 5. Labelling protocol

Target: under 45 seconds per document. The human confirms; the system proposes.

1. The system parses the heading tree and proposes per section: `role` from rules first (frontmatter `type`, heading words such as Decision, Karar, Status, Proposal, Report, dates in the heading, file name patterns), then a model only for sections the rules leave unknown. Each proposal has a confidence.
2. The screen shows one document as its heading tree, with the proposed role per heading and a document-level sensitivity and egress. Sections with confidence above a threshold are collapsed and pre-accepted.
3. The human does three things: tap sensitivity and egress for the document; tap any role that is wrong in the visible, low-confidence sections; tap "retired" if the whole document is dead. Save.
4. Thirty percent of documents stay blind (D43): no proposals shown. These measure anchoring and give the honest agreement number.
5. Ground truth is written per `section_hash`, so a later version of the document costs zero seconds for unchanged sections.

Decisions found in text are not labelled in this pass. They appear as `decide` sections only; the `valid_until` field is filled later by the curator who enacts them.

I am not sure a 2.6-minute document drops to 45 seconds on the first pass. The gain comes on the second version and on the many `record` documents, which take one tap.

## 6. Agent-to-agent future

- Facets are verbs, not genres. `cite`, `instruct`, `decide`, `propose`, `record` say what a reader may do. An agent does not need to know what a "design document" is.
- Every facet is in the `kutuphane:` frontmatter block (D21), so a package carries labels, and an agent writes labels the same way a human does.
- Agents may write `propose` and `record` sections and label them so. They may not confirm `decide`, `instruct` or sensitivity. The confirmation right is a grant like any other, so one day a trusted agent can get it, and the audit shows it.
- Section hash plus citation handle give an agent a stable pointer to a claim. An agent can say "I acted on decision `<hash>`", and the audit can later show it was retired.
- Derived `stale` and the supersede chain let an agent ask "what was current on date D" from the label table alone.

## 7. Risks, and what I would not do

- **Mixed-sensitivity documents.** Document-level sensitivity forces splits. If the labelling shows many such documents, section-level sensitivity must be built, and it touches every query path. I would measure before building.
- **Heading quality.** The whole design depends on headings. Documents written by agents often have good headings; old notes may not. The "add headings" flag will make noise at first.
- **Role creep.** Someone will ask for `faq`, `lesson`, `standard`. Refuse unless a behavior is named. A lesson is `cite`; a standard is `cite` or `decide`.
- **Enactment by accident.** Keep enactment a human, logged, per-object action. No bulk enact.

I would not: let a model set boundaries; put labels into the content hash; store `stale` as a value; give sections their own grants; build a decision database separate from the text; or label E7 audience or E3 origin as content facets when nothing reads them.