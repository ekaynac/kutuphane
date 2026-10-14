# Claude — round 1 (independent proposal)

Test for every facet value: "What does the system do differently with this value?" If the answer is "nothing", remove the value.

## 1. Sections

**Two levels.**
- A **block** is the smallest structural unit, found by a deterministic rule.
  - The rule splits at headings, list groups, tables and code fences.
  - A paragraph run under one heading is one block.
  - A block has no minimum size. Very long blocks (more than ~4,000 characters) split at paragraph boundaries.
- A **section** is a run of adjacent blocks with the same facet values. Sections are derived; nobody draws them.

So the facets decide where a section ends ("a section ends where a facet value changes"), and the structure decides the possible cut points. Humans correct facet values, and boundaries follow. A human can add a cut inside a block in rare cases (an explicit split mark).

**Identity across versions.**
- `block id = sha256(normalized block text)`. The heading path is kept as context, but it is not part of the id.
- If the block text did not change, every label carries over exactly. This matches content-addressed versions.
- If the text changed, the system proposes the old labels on the most similar block (same heading path, similar text) as "inherited, not confirmed".
- An unconfirmed gate facet is fail-closed: it gets the stricter of the book value and the inherited value until a human confirms.

**Who decides.**
- The segmenter is versioned code, like the chunker.
- Facet values come from model proposals, and humans confirm them.
- Retrieval chunks never cross a block boundary, so each chunk belongs to exactly one block and inherits its facets.

**Documents without headings.** They split at paragraph and size boundaries. A single-block document is acceptable.

## 2. Facets (labelled at block level unless noted)

| Facet | Question | Values | Behavior that each value changes | Vocabulary | Set by / confirmed by |
|---|---|---|---|---|---|
| **Function** | What does this text do for its reader? | `states` · `instructs-person` · `instructs-agent` · `records` · `decides` · `proposes` · `derives` | `instructs-agent`: needs `activate`; served whole; never used as answer evidence. `instructs-person`: served as ordered steps; feedback ledger (AT-15). `states`: normal evidence. `records`: evidence shown with its as-of time, never as current truth. `decides`: highest authority in its scope; conflicts in the same scope are flagged. `proposes`: never authority; answers label it "proposal, not decided"; excluded from "what is the current X" answers. `derives`: must link to its sources; agent-derived text needs human acceptance before it is authority. | closed | model proposes; human confirms `instructs-agent` and `decides` |
| **Status** | Is this the accepted version of the idea? | `draft` · `proposed` · `accepted` · `superseded` · `rejected` | `accepted`: citable as authority. `proposed`: shown with a label. `superseded`: hidden by default; a link points to the successor. `rejected`: hidden, kept for history. `draft`: visible only to the author and curators. Applies to `decides`, `proposes`, `instructs-*`, `states`. `records` are immutable and have no status. | closed | see the transition table |
| **Validity** | Is this still true now? | `durable` · `snapshot(as_of)` · `time-boxed(from, until)` | `snapshot`: stale when `now > as_of + window(subject kind)`; stale text goes down in ranking; answers say "as of T". After the archive window it is excluded from default search. `time-boxed`: outside its window it is not authority. `durable`: no decay. | closed + dates | model extracts dates; human confirms `time-boxed` |
| **Provenance** | Who made it, and was it checked? | author kind `human` · `agent` · `model` · `external`; `reviewed` yes/no; source links | An unreviewed agent or model text cannot become `accepted`. `external` (vendor, standard) gets authority only inside its subject. Trust weight in answers. | closed + links | rule (from the commit or ingest metadata) + human |
| **Subject** | What is it about? | open entity tags: system, component, host, product, version | Scoping: answers filter by subject. Conflict detection between `decides` texts on the same subject. The validity window comes from the subject kind. | open, normalized to entity ids | model extracts; human corrects samples |
| **Access** (book level, enforced) | Who may read it; where may a model process it? | sensitivity `normal`/`restricted`; egress `local_only`/`cloud_ok` | Existing gates. Section-level values act as a **lint**: a restricted block in a normal book blocks publication until the block moves to a restricted book. A local-only block makes every model call that includes it local only (the stricter value wins at the call). | closed | human confirms |

**Derived, not labelled.**
- **Presentation** (E2/E7) comes from Function: `instructs-agent` is served whole; tables and schemas are served structured; everything else is chunked.
- **K1–K8 become saved views.** Example: runbook = `instructs-person` + `accepted` + `durable`.

**Mapping to E1–E9.**

| Axis | Becomes |
|---|---|
| E1 | Function |
| E3 | Provenance |
| E4 | Status + Validity |
| E5 | Access |
| E6 | Subject |
| E2, E7 | derived |
| E8, E9 | unchanged, book level |

## 3. State changes

Facet assignments are **append-only events**: `(block id, facet, value, by, confirmed_by, at, reason)`. The current value is the latest confirmed event.
- A facet change is not a content version; the content id is unchanged.
- An answer stores the facet values it used, so it can be explained later.

**Rule for every facet:**
- A model may propose any value.
- A change that tightens access or gates may apply automatically.
- A change that loosens access or gates needs a human, and the change is audited.

**Status transitions**

| From | To | Trigger | Who | Auto? | Reversible |
|---|---|---|---|---|---|
| draft | proposed | the author submits | author (human or agent) | no | yes (withdraw) |
| proposed | accepted | review | human curator of the book | no | yes, curator only, with a reason |
| proposed | rejected | review | human curator | no | yes, curator only |
| accepted | superseded | a new accepted text with the same subject declares `supersedes` | rule, after the curator accepts the new text | yes | yes, curator only |
| any | draft | the author withdraws the text | author | no | — |

**Validity** is computed at read time: `fresh`, `stale` and `archived` come from `now`, `as_of` and the windows, with **no background job**. A human "confirm still current" event sets a new `as_of`.

**Function changes**
- A change to `instructs-agent` is automatic, because it tightens the gate.
- A change away from `instructs-agent` needs a human.

## 4. Decisions and permissions inside documents

- **Normative decisions** (canon, rules) stay as blocks with Function `decides`, plus Status, Validity and Subject. The block *is* the decision; there is no new table. `supersedes` links make a chain.
- **Executable permissions and consents** ("agent X may do Y until T"):
  - The **grant system is the source of truth**: grants with expiry already exist.
  - The text block is evidence and rationale.
  - The system proposes a grant from the block. A human with authority approves it.
  - The grant stores a provenance link to the block.
- **Disagreement.** The grant wins for enforcement. A lint shows drift, for example "the text says it expired; the grant is still active". This keeps the "document TTL is not decision TTL" distinction:
  - a decision block has its own `time-boxed` validity;
  - a permission has its grant expiry;
  - a document has no TTL of its own (it is archive-ready when all its blocks are stale, superseded or rejected).

## 5. Labelling protocol (< 45 s per document)

1. The system segments the document. The model proposes facets for each block, with a confidence value and the evidence text.
2. The page shows the document as colored strips (one color for each Function). It marks restricted and local-only blocks, and it shows the extracted dates.
3. The human confirms the access and gate facets, plus any block that the model marks as low confidence. Everything else needs one tap: "confirm".
4. A sample (about 20 %) of the non-gate facets is double-checked to measure quality.
5. The blind slice stays, to measure anchoring.

## 6. Agent-to-agent future

- Function values are speech acts, not human genres, so they stay valid when agents write for agents.
- Gate facets have closed, small vocabularies. Subject tags normalize to entity ids, not words.
- Facets travel with signed packages. The receiver can override access (D23).
- Agent-authored content enters as `proposed` with `agent` provenance. An agent cannot accept its own text.

## 7. Risks and what I would not do

- I would not make the section a unit of authorization. Access stays per book, and the lint catches mismatches.
- I would not let a model loosen any gate.
- I would not use open vocabularies on gate facets.
- I would not run background decay jobs.
- **Risk:** the model's quality on Function and Status decides the labelling speed. Measure it on the blind slice first.
- **Risk:** reviews ("evaluates") are folded into `records` + Subject. If review findings must change the trust of what they review, a later facet is needed. **Open question.**
