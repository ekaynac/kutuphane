I propose **stable knowledge sections with a small set of behavior rules**. Keep documents as source containers. Keep books as authorization units. Keep search chunks as delivery units.

This proposal extends the [current decisions](/home/mega/kobra/docs/01-direction-decisions.md:99). It preserves the [acceptance requirements](/home/mega/kobra/docs/07-m1-definition.md:58). The new section and validity rules are proposals, not existing capabilities.

**1. Sections**

A section is the smallest passage that can have one clear function, scope, and validity rule without losing necessary context.

Use these boundary rules:

- Start with headings, paragraphs, lists, tables, and code blocks.
- Keep a procedure with its prerequisites. Keep a code block with its explanation.
- Add a boundary when function, scope, authority, or validity changes.
- A confirmed facet difference requires a boundary. A model prediction alone does not.
- Preserve heading nesting. Parents provide context and defaults; children hold exceptions. Never give a mixed parent one false label.
- Without headings, start with paragraphs. A model can propose groups and function changes.

Do not require a minimum size. One permission sentence can need its own section. Start with a soft review limit of 800 words, then measure. Large coherent sections can remain intact. Search chunks can divide them for retrieval. A chunk must not combine sections with different behavior rules.

Rules create the first boundary map. A model proposes changes. A human confirms uncertain boundaries and all boundaries that affect authority or instruction delivery. The editor supports split, join, and move operations, with a preview of affected labels.

Give each section a persistent ID. Store each occurrence with its document version, exact span, text hash, parent, and context references. Do not use path, heading, hash, or ordinal alone as identity.

Across versions:

- Unique unchanged text within established document lineage keeps its section ID and labels.
- Changed context retains the old labels as evidence, but marks affected conclusions for review.
- Changed text gets a new section revision. Old ground truth remains attached to old text.
- Splits and merges keep explicit predecessor links. Transfer labels only where their full target span survives unchanged. Treat broader conclusions as proposals.
- Duplicate passages and uncertain moves require confirmation.

Security restrictions remain in force during review. Uncertainty must not increase authority or access.

Keep citations unchanged: book, content ID, profile ID, path, ordinal. A separate mapping connects citations to sections.

**2. Facets**

All behavior vocabularies below are closed. Adding a value requires a defined behavior and a test. Free tags are outside the core ontology.

“Owner” means a person authorized to approve knowledge in the stated scope. “Administrator” means a person authorized to change access policy.

| Facet and question | Values and exact behavior | Level; setter and confirmation |
|---|---|---|
| **Sensitivity:** What handling restriction applies? | `normal`: no sensitivity-based cloud prohibition. `restricted`: cloud delivery prohibited, including derived text and vectors. Neither value grants access. | Document declaration, enforced through book policy. Rule/model proposes; administrator confirms. |
| **Egress:** Where may content go? | `local_only`: local processing only. `cloud_ok`: approved cloud processing permitted, subject to sensitivity and authorization. | Document declaration, enforced through book policy. Rule/model proposes; administrator confirms. |
| **Function:** How may the system use this passage? | `evidence`: supports descriptive claims, but does not establish a rule. `proposal`: available for options and proposal questions; cannot establish a settled rule. `directive`: can establish a rule only when approved, applicable, and valid. | Section, with document defaults. Rule/model proposes; owner confirms. |
| **Agent instruction:** Does agent delivery require activation? | `yes`: all agent delivery requires book `activate` in addition to required access modes. `no`: no additional activation requirement. | Section, conservatively aggregated for whole-document delivery. Rules/model propose; curator confirms. Removing `yes` requires explicit review. |
| **Standing:** Has the owner accepted this section for use? | `pending`: review and proposal retrieval only; excluded from normal authoritative answers. `approved`: eligible under its function and validity rules. `retired`: archive retrieval only; excluded from current guidance. Approval does not prove truth. | Section, with document defaults. Owner sets and confirms; model can recommend. |
| **Time basis:** When does it apply? | `durable`: no automatic time expiry. `as_of(t)`: supports claims about that time, not present-state claims. `window(start,end)`: eligible only within that interval. | Section. Rule/model proposes dates with source spans; owner confirms. |
| **Scope:** Where does it apply? | `unbounded`: no applicability filter. `bounded`: typed identifiers and version ranges must match the request. Missing request context blocks directive use; it prompts clarification. | Section, with document defaults. Owner confirms model proposals. Identifier vocabulary is open; matching operators are closed. |

An approved proposal remains a proposal. To make it a rule, the owner must also change its function to `directive`.

Retain three existing controls outside the section-label form:

| Control | Behavior and responsibility |
|---|---|
| **E2 presentation profile** | Closed implemented values `whole` and `chunked` select delivery and indexing. Curator selects at document level; publication confirms. |
| **E8 protection** | `standard` is the only accepted M1 value. It requires deployment-level disk protection. Reject unsupported values. Administrator confirms book policy. |
| **E9 access modes** | Independent `discover/read/use/activate` rights control their corresponding operations. They belong to book grants, not section labels. Authorized administrators grant rights; users confirm delegations within their current rights. |

For mixed books, enforce the strongest document restrictions across the book. Section labels cannot weaken them. Separating books is the available route to different access policies.

E1 becomes function plus the instruction gate. E3 remains provenance, never a trust score. E4 becomes standing and time basis. E5 remains two distinct controls. E6 becomes scope. E7 becomes a request presentation preference. E8 and E9 remain enforced.

K1–K8 cease to be mandatory labels. Keep useful product names and compatibility mappings. Preserve K3 activation. K7 remains an experiment; K8 remains outside M1 secret-use support. This requires an explicit revision of D24/D25, not silent relabeling.

**3. State changes**

All stored changes are audited. Reversal means a new event; it never deletes history.

| From → to | Trigger; authorized actor | Automatic? | Reversal |
|---|---|---|---|
| pending → approved | Review complete; owner | No | Return to pending |
| approved → pending | Relevant text/context change; system, or owner concern | Yes for detected changes | New approval |
| pending/approved → retired | Rejected, replaced, or withdrawn; owner | No | Owner review |
| retired → pending | Reconsideration; owner | No | Retire again |
| window: future → valid | Clock reaches start; confirmed owner rule | Yes | Amend interval |
| window: valid → expired | Clock reaches end; confirmed owner rule | Yes | New approved interval |
| Any time basis → another | Correct evidence or validity policy; owner | No | New revision |
| Any function/scope/instruction value → another | Correction or adoption; owner/curator | No | Reviewed revision |
| Any sensitivity/egress value → another | Handling-policy change; administrator | No | New policy revision |
| Any profile → supported profile | Delivery change; curator | No | Select prior profile |
| Absent → active grant/delegation | Explicit authorization; administrator/user | No | Revoke |
| Active → revoked | Withdrawal; authorized administrator/delegator | No | New authorization |
| Active delegation → expired | Clock reaches expiry | Yes | New delegation |

Evaluate time at each request. Do not depend on a scheduled job. Record the evaluated time and rule revision in the access or answer record. There need not be a stored “expiry happened” event.

Facet edits create immutable annotation revisions plus audit events. They do not change source bytes. Policy edits create policy versions. Changes to chunk production create profile versions. Source edits alone change content identity.

A snapshot does not become false with age. Its `as_of` value already prevents present-state use. Expired guidance leaves current retrieval automatically but remains available for history.

**4. Decisions and permissions inside documents**

There are three useful options:

- **Text only:** simplest, but cannot reliably enforce scope, expiry, or conflicts.
- **Structured decision record:** supports explicit standing, scope, validity, and replacement.
- **Grant/delegation:** enforces supported authorization, but cannot represent every operational decision.

I recommend selective structured extraction.

Keep the exact source span. Create a decision record only when separate governance is needed. Store its statement, scope, approver, time basis, standing, and replacement links. This can use the same annotation machinery as sections.

The document proves what was written. The approved record determines current governed status. A disagreement must be visible. A document edit cannot silently modify the record.

Map a permission to grants only when book, subject, mode, and duration match exactly. Never widen a section permission into a book permission. Never infer authorization from prose.

[Current authorization code](/home/mega/kobra/src/kutuphane/authz.py:1) expires delegations, but direct grants have no expiry field. A temporary direct permission therefore needs explicit support before execution.

Only an authorized owner can adopt a decision. Only the existing authorization path can issue rights. A model may propose both. Approval of a decision does not itself authorize an external action.

**5. Labelling protocol**

Target a median below 45 seconds for initial review, not complete annotation of every complex document.

The system prepares boundaries, inherited defaults, exception spans, proposed dates, and a short list of uncertain items. It preserves unchanged human labels.

The human confirms:

- Sensitivity and egress.
- Instruction presence.
- Clear standing/time defaults.
- Highlighted boundary exceptions.

Offer “needs detailed review.” This is a workflow result, not a knowledge type. Unreviewed fields are not ground truth.

Keep about 30% blind, as D43 requires. Measure blind agreement, boundary errors, missed instructions, corrections, and total time including deferred work. Review disagreements separately.

I cannot promise complete, correct section labels for long mixed documents in 45 seconds. The target is credible only with reuse, defaults, and selective deeper review.

**6. Agent-to-agent future**

Define the ontology through operations, identity, scope, and time. Keep natural-language descriptions optional. Structured messages and binary artifacts can use the same envelope.

Agents can propose content and annotations. Their identity, model/version, source evidence, and approval history remain explicit. A signature proves origin; it does not prove truth or grant authority.

**7. Risks and limits**

The main risks are wrong boundaries, lost context, inherited authority, and model suggestions that bias human review.

I would not add automatic permission extraction, section ACLs, confidence-as-truth, arbitrary policy languages, or a universal TTL.

Start with section mappings and annotation revisions in the existing Python/Postgres app. Extend signed packages to carry them through local import approval. Preserve old citations and current-rights checks. Add complexity only when a measured governance need requires it.