1. **Yes—in the normative scope and validation rules more than the mandatory field count.** One correction: current [OKF v0.2 §11](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md#11-conformance) requires parseable frontmatter and nonempty `type` for conformance. Optional fields, unknown keys/types, and broken links are tolerated. Its trust signals are advisory, not access control.

   Exactly where kstd overspecifies:

   - L0 requires `standard`, `issuer`, `issued`, and path/digest for listed items. `issued` has no decision effect in this module.
   - [`check()`](/home/mega/kobra/src/kutuphane/kstd.py:204) blocks publication for unrecognized non-`x-` fields, incomplete generator metadata, and reviewer metadata outside `assisted`. These can often remain descriptive errors while the relevant claim becomes untrusted.
   - The SPDX subset rejects `WITH` expressions. Unsupported rights interpretation should block dependent uses, not necessarily registration.
   - [Draft §§2–6](/home/mega/kobra/docs/11-standard-draft.md:21) standardizes eight statement kinds, lifecycle transitions, delegation, erasure, activation and federation semantics before search and answers have demonstrated sufficient value.

   Keep strict digest checks and unambiguous parsing. Separate **readable/importable**, **valid governance evidence**, and **authorized for this operation**. Docs/19 already points toward this.

2. **Require a tiny envelope; require additional evidence before permission.** No metadata can guarantee factual correctness. The achievable guarantee is a correct authorization decision given authenticated evidence and explicit policy.

   | Field | Why |
   |---|---|
   | `version` | Selects decision semantics; unsupported semantics cannot grant permission. |
   | `subject` | Exact content digest, with a locator/selector when needed. Approval must identify the bytes used. Machine-filled. |
   | `issuer` | Identifies who asserts the metadata. Resolve through authenticated ingestion or verified signatures; a name string proves nothing. |
   | `permissions` | Explicit permissions for search and model input, scoped to the requester/use. Missing permission denies. An `ai_use: y` declaration alone does not establish the issuer’s authority or satisfy access policy. |
   | `constraints` | Audience, destination, applicability and time conditions, inline or through a versioned policy reference. Unknown required conditions block release. Explicit unrestricted scope differs from missing scope. |
   | `inputs` — conditional | Required for recorded derivations whose upstream restrictions must carry forward. Missing required ancestors deny; an empty list does not certify independence. |

   Only the first three need exist to register a governance record. The others are evidence needed for a particular permit; they can come from authenticated folder policy rather than repeated form questions. Acceptance can be a condition on that permission, without requiring the entire five-state lifecycle everywhere.

   Requester identity, action, destination, evaluation time and trust configuration are **runtime inputs**, not item labels. Denial wins; unresolved required context or trusted conflicts escalate; escalation releases nothing. A permit names the content and policy versions and expires.

   Move origin taxonomy, generator/reviewer details, tags, detailed lifecycle, mandates, activation, training, federation, erasure protocols and jurisdiction-specific mappings into profiles. Profiles become mandatory when that operation needs them. Missing origin stays `unknown`; ordinary evidence must never silently become a binding rule.

3. **Meaningful as an interoperable enforcement contract; its value as a broad standard remains unproven.**

   The strongest evidence is the failure pattern: [docs/21](/home/mega/kobra/docs/21-labelling-v5-auto-results.md:108) reports 11 false `accepted` and 25 false `assisted` proposals from Qwen. That supports keeping inference separate from authorization. It does not establish that every proposed ontology distinction is useful.

   My strongest doubts:

   - Annotation cost may exceed the benefit. The [radar pilot](/home/mega/kobra/docs/18-pilot-radar.md:64) still exposes retrieval, citation and latency problems that metadata alone cannot solve.
   - Rule 4 lets **any issuer** impose restrictions. An attacker can deny access to everything, undermining rule 8’s availability promise. Restrictive assertions also need an admissibility policy.
   - The implementation weakens the story: [`init()`](/home/mega/kobra/src/kutuphane/kstd.py:370) grants search by default; missing manifests bypass this module’s checks and leave book policy responsible.
   - Docs/21 sometimes argues for semantics because a scenario’s consequential variant must change the result. That reverses validation: desired behavior should determine the test.

   Clear value would be two independent consumers agreeing on independently adjudicated cases, plus real users getting useful answers with fewer unauthorized disclosures, stale-rule citations and manual corrections.

   Stop expanding categories without demonstrated operational benefit, inferring origin from prose, relabelling machine-known facts, and treating reference-engine agreement as independent validation. Concentrate on search, answers and a small portable conformance suite.

4. **Enforce origin at the write boundary, outside the agent’s control.** The runtime records the authenticated writer and production events. An agent cannot assign itself a human principal or certify human authorship—even when instructed to do so. Imported `human` declarations remain attributed claims until supported by trusted provenance.

   Distinguish “an agent copied verified human bytes” from “an agent composed text.” Human review adds a separate, digest-bound attestation; it never erases model involvement. Preserve `unknown` as unknown, even when policy handles it conservatively.

   Signatures establish who asserted something. They cannot prove that a human never used AI.