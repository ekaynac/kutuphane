# Briefs: in-toto attestation (#67 and predicate registration) and MCP SEP-1913

I checked every source below on 2026-10-22 with `gh`, `curl` and fetches. Text marked "not verified" or "estimate" is not confirmed. I posted nothing and changed no repo files. The W3C CLA does not apply to either group, because neither is a W3C group.

---

## (a) in-toto Attestation Framework (CNCF)

### 1. What the group wants
- **[Issue #67](https://github.com/in-toto/attestation/issues/67)** has been open since 2021, with no assignee and no PR. It asks for a way to revoke a set of attestations without revoking the whole key.
  - In 2023, a maintainer proposed short-lived VSAs as the revocation path.
  - The [2026-10-02 comment](https://github.com/in-toto/attestation/issues/67#issuecomment-5949499765) asks three questions: is the statement authentic, is the signer authorized, and what is the effect? It separates revoked, superseded, invalidated-for-window and withdrawn. It also proposes a test: *"two valid revocation statements … only the first should alter verifier acceptance."*
- **The rule that conflicts with revocation:** the [parsing rules](https://github.com/in-toto/attestation/blob/main/spec/v1/README.md#parsing-rules) say that ignoring an attestation must "never turn a DENY decision into an ALLOW". "Deny if a revocation exists" breaks this rule.
- **How to register a predicate:** read the [New Predicate Guidelines](https://github.com/in-toto/attestation/blob/main/docs/new_predicate_guidelines.md) and [ITE-9](https://github.com/in-toto/ITE/tree/master/ITE/9).
  - Open a PR with `spec/predicates/<name>.md` that follows the [template](https://github.com/in-toto/attestation/blob/main/spec/predicates/template/template.md): Purpose, Use Cases, Model, Schema, Parsing Rules, Fields, a full-Statement example. Add the predicate to the README list. A protobuf file is optional.
  - Field names use lowerCamelCase. Timestamps use RFC 3339 with "Z".
  - *"Your predicate is yours"*: the maintainers review it, but they do not write it.
  - Registration is optional. `predicateType` can be any TypeURI.
- **No date or deadline is given.**
- **Review state:**
  - 19 predicate PRs are open, and many are about AI.
  - The last addition to the vetted list was SVR in March 2026.
  - On 2026-10-20 a maintainer [asked](https://github.com/in-toto/attestation/pull/603) whether an AI-specific type is necessary instead of "a more generic change review predicate".
  - [PR #597](https://github.com/in-toto/attestation/pull/597) proposes conformance vectors (a verdict plus reason codes). No maintainer has reviewed it.

### 2. What we bring
- Rules 4, 5, 6 and 8 of `docs/11-standard-draft.md` §4.
- `kstd/reference/decide.py` (`trusted()`, `acceptance_of()`).
- `kstd/tests/decision/cases.yaml`: the cases for rules 4, 5, 6 and 8.
- DSSE raw-byte signing (docs/11 §2).

### 3. Comparison
| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| Authentic ≠ authorized | rule 4: trust per issuer × kind × scope × action, with an expiry | match | For us, authority is verifier policy, not a predicate field |
| Effect of an unauthorized revocation | rule 8: it becomes a `contested-by:` notice only | match | |
| Revoked, superseded, withdrawn | `withdrawn` + successor or terminal reason; `suspended` (hold + `review_by`) | partial | We have no states for a time window |
| Selectors (time range, builder) | exact ids only | we lack | |
| Monotonic principle | rule 6: status freshness, maximum age | partial | Stale status removes rule authority only, not access |
| Two authorities disagree | rule 5: `escalate`, or local precedence | match | |
| lowerCamelCase, full Statement | snake_case, `issuer`/`about`/`kind` | we differ | `kind` → `predicateType`; `issuer` comes from the signature |
| Conformance vectors (#597) | `cases.yaml` (result + reasons) | match | |

### 4. Reason
- **For them:** they get tested answers to the three open questions, and a way to make revocation monotonic. This is close to the maintainer's own VSA idea.
- **For us:** kstd statements become in-toto Statements (landscape §3.1). The group then reviews our status and withdrawal model.

### 5. Consequences
- **IPR and licensing:**
  - An issue comment is under GitHub ToS only. Whether the repo license applies to comments is not verified.
  - A PR needs a DCO `Signed-off-by` ([in-toto CONTRIBUTING](https://github.com/in-toto/community/blob/main/CONTRIBUTING.md)) and goes under Apache-2.0, which includes a patent grant. The company must permit the operator to sign the DCO.
- **If they accept:**
  - We rename fields to lowerCamelCase for the in-toto binding (`issuedAt`, `reviewBy`).
  - The `status` and `acceptance` kinds map to the shared predicate.
- **If they reject:** we keep the kstd types under our own URI. Nothing is lost.
- **Effort (estimate):**
  - The comment takes about 3 hours.
  - The predicate PR takes 2–4 days.
  - Review can take months.
- **Risks:**
  - Our comment can be lost among the AI-predicate proposals.
  - Maintainers prefer generic types, so we must not propose "kstd-…" types.
  - We must not link to the private repo.

### 6. Steps for the operator
1. Wait until the repo is public. If you post earlier, put the vectors inline.
2. Use a personal GitHub account and show the company affiliation. Post the #67 comment.
3. Join CNCF Slack `#in-toto-attestations`. Ask for a slot at the monthly community meeting (the agenda is on HackMD).
4. Read the replies for 2–4 weeks. Open the predicate PR only if the maintainers want a shared predicate. Sign off every commit with `git commit -s`.
5. Answer reviews. If the URI goes under `in-toto.io`, send the redirect PR.

### 7. Draft text
**#67 comment:**
> We maintain a small decision rule for DSSE-signed statements that have the in-toto Statement shape. It has a public conformance suite [link]. Here are our answers to the three questions in the comment of 2026-10-02:
> 1. **Authentic:** DSSE verification only. This gives no authority.
> 2. **Authorized:** this is a question of verifier policy, not a predicate field. A field that claims authority is self-asserted. A policy entry names a signer × predicateType × scope × action and has an expiry.
> 3. **Effect:** a revocation from a signer outside the policy does not change the verdict. The verifier shows it only as a "contested" notice. A revocation from an authorized signer removes the attestation from ordinary use. When two authorized signers disagree, the result is `escalate`, unless a local precedence rule decides. A timestamp never decides between signers.
>
> **Monotonic principle:** "deny if revoked" is not monotonic. We use freshness instead. An imported attestation keeps its full effect only while a signed status from its issuer is newer than a maximum age (default 30 days). This is near the short-lived VSA idea above.
>
> | Vector | Expected |
> |---|---|
> | A1 by B; revocation by B (B authorized) | rejected (`withdrawn`) |
> | revocation by X (valid signature, not in policy) | accepted, notice `contested-by:X` |
> | revocation by B, but B's policy entry has no expiry | accepted, notice `contested-by:B` |
> | B's policy entry covers another action only | the revocation has no effect |
> | revocation by C (authorized); B does not withdraw | `escalate`; with precedence [B, C]: accepted |
> | no status from B newer than 30 days | downgraded (`status-stale`) |
>
> Question: would you accept one generic lifecycle predicate in the vetted list?

**Predicate outline** (`lifecycle`, v0.1; the URI domain is not chosen yet):
```jsonc
{ "_type": "https://in-toto.io/Statement/v1",
  "subject": [{ "digest": { "sha256": "<digest of the target DSSE envelope>" } }],
  "predicateType": "https://<domain>/attestation/lifecycle/v0.1",
  "predicate": {
    "state": "withdrawn|superseded|suspended|contested",  // required
    "reason": "...",                                       // required
    "successor": { "digest": { "sha256": "..." } },        // required if superseded
    "owner": "...", "reviewBy": "2026-11-07T00:00:00Z",    // required if suspended
    "effectiveAt": "2026-10-20T00:00:00Z", "scope": "..." } }
// Parsing: the predicate has no authority field; verifier policy decides authority.
// An unknown state gives escalate (a proposal; not in kstd 0.2 cases).
```

---

## (b) MCP SEP-1913: Trust and Sensitivity Annotations

### 1. What the group wants
- **State of [PR #1913](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1913):**
  - It is open, with Status "Draft" and "review required". The sponsor is @dend.
  - A bot has reported sponsor inactivity since 2026-06-08. The last report was on 2026-10-12.
  - The PR description is older than the file. It still lists `sensitiveHint`/`privateHint`, which the file does not contain.
- **Where the work moved:**
  - On 2026-06-10 the author announced a split to the Extensions Track (SEP-2133). The work is now incubated in [`experimental-ext-tool-annotations`](https://github.com/modelcontextprotocol/experimental-ext-tool-annotations), run by the Tool Annotations IG.
  - #1913 is now the "umbrella" thread ([sep-disposition](https://github.com/modelcontextprotocol/experimental-ext-tool-annotations/blob/main/docs/sep-disposition.md)).
- **Current text ([trust-annotations.mdx](https://github.com/modelcontextprotocol/experimental-ext-tool-annotations/blob/main/specification/draft/trust-annotations.mdx)):**
  - It has two booleans, `sensitive` and `untrusted`, under `_meta["io.modelcontextprotocol/trust-annotations"]`, plus `evidenceRef` {`type`, `digest`, `canonicalization`, `schema`, `ref`}.
  - Absence *"MUST be treated as 'no claim made'"*.
  - A per-ContentBlock annotation MAY refine the result-level one but MUST NOT weaken it.
  - Propagation is not in this extension.
- **Open questions ([open-questions.md](https://github.com/modelcontextprotocol/experimental-ext-tool-annotations/blob/main/docs/open-questions.md)):**
  - "Enforcement vs. advisory": the sponsor fears a *"false sense of security"*.
  - Declassification and taint persistence.
  - Who keeps the `evidenceRef.type` registry. No registry file exists yet.
- **The bar for a scheme ([schemes/README](https://github.com/modelcontextprotocol/experimental-ext-tool-annotations/blob/main/schemes/README.md)):** identity, payload, graceful degradation, and a candidate producer and consumer.
- **Fixtures:** PR #5 was closed without merge. The facilitator's rule: *"we will only merge the actual extension and documentation"*.
- **SEP process ([guidelines](https://modelcontextprotocol.io/community/sep-guidelines)):**
  - A SEP needs prior group discussion and a sponsor.
  - A SEP with no sponsor after 6 months becomes dormant.
  - Core Maintainers review every two weeks.
- **No deadline is given.**

### 2. What we bring
- **Kütüphane MCP server (`src/kutuphane/server.py`):**
  - `_for_model` treats every MCP caller and every `agent:` principal as a model reader.
  - `_text` returns `text: null` with `withheld` for each passage, before delivery.
  - `op_file` first runs the ordinary read check, then refuses the whole file.
  - The rights stay in the result body as `item`. The server writes no `_meta` and no tool annotations.
- **Gap against D60:** `kstd.py:257` still writes `n` for an absent `ai_use` term. D60 is not implemented yet.
- **kstd:** rule 4 (declassification), `derive` + `inputs` (taint), and `cases.yaml`.

### 3. Comparison
| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| Absence = no claim | D60 three-state `ai_use` | partial | The code still writes `n` |
| `sensitive` floor | `personal_data` yes/unknown; `export: restricted` | partial | We need a mapping |
| `untrusted` | origin; trust per issuer | we differ | |
| Per-block refine, never weaken | per-passage `withheld` | match | |
| Enforcement or advisory (open) | server-side decision before delivery | we differ | We are stricter; this is our offer |
| Declassification (open) | rule 4 | match | |
| Taint persistence (open) | `derive` + `inputs`; strictest input wins | match | |
| `evidenceRef.canonicalization` required | DSSE raw bytes | partial | Propose the value `"none"` |
| Rights and AI use | `ai_use`, license | we lack (on their side) | Offer as a scheme |

### 4. Reason
- **For them:** they get a deterministic answer to their two hardest open questions, plus a producer for the bar.
- **For us:** MCP is our `deliver` channel. One shared key means that clients can show our decisions.

### 5. Consequences
- **IPR and licensing:**
  - No CLA or DCO is in [CONTRIBUTING](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/CONTRIBUTING.md).
  - Spec contributions go under Apache-2.0. SEP files are CC0. The extension repo is Apache-2.0.
  - The [AI policy](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/AI_POLICY.md) requires disclosure. An AI wrote this draft, so the operator must disclose that in the comment.
- **If they accept:**
  - Kütüphane writes `_meta` on each block: the floor booleans plus our key.
  - D60 export must come first.
- **If they reject (hints only):** our server-side enforcement does not change.
- **Effort (estimate):**
  - The comment takes about 3 hours.
  - The scheme issue takes about 1 day.
  - The Kütüphane emitter takes 1–2 days.
- **Risks:**
  - SEP-1913 can close and be replaced by extension SEPs.
  - The sponsor is not active.
  - The thread has many self-promoting comments.
  - Our fixtures will not be merged.
  - We must not use the reserved `io.modelcontextprotocol/` prefix for our own key. We must use our own reverse-DNS name.

### 6. Steps for the operator
1. Use a GitHub account. Join Discord `#tool-annotations-ig`.
2. Post the comment on #1913. Include the disclosure line.
3. In the extension repo, open an issue: "Candidate scheme: rights and AI use". Cover the four bar items, and name Kütüphane as the producer.
4. Implement D60 export and the `_meta` emitter. Then link them in the issue.
5. Follow the IG meetings (the schedule is "TBD") and the `type` registry question.

### 7. Draft text
> *Disclosure: AI assistance drafted this comment. I reviewed it and I take responsibility for it.*
>
> We run an MCP server for a document library (Kütüphane, Apache-2.0, [link]). It decides on the server, before delivery. When an item's rights do not permit AI input, the result keeps the citation and metadata, and the text is withheld with a reason. Three points for "Enforcement vs. advisory":
> 1. **Enforce where the policy is.** The party that holds the source policy decides before delivery, and the annotation reports that decision. For clients, we propose a normative check path with vectors: the same inputs give the same `permit`/`deny`/`escalate` and the same reason codes.
> 2. **Declassification:** a tightening applies at once, from any source. A loosening applies only from a source that the host policy names for that kind × scope × action, with an expiry.
> 3. **Rights are not sensitivity.** We propose a scheme behind `evidenceRef`. The records are DSSE raw bytes, so `canonicalization: "none"`.
> ```json
> "_meta": {
>   "io.modelcontextprotocol/trust-annotations": { "sensitive": true,
>     "evidenceRef": { "type": "kstd.decision.v0", "digest": "sha256:…", "canonicalization": "none" } },
>   "com.example/kstd": { "decision": "deny", "action": "infer",
>     "reasons": ["rights-reserved:ai_input"], "ai_use": { "search": "y" }, "personal_data": "unknown" } }
> ```
> Here `ai_input` is absent, so the record does not write it as `n`. The decision still fails closed.
>
> | Input | Expected |
> |---|---|
> | `ai_input: y`, model client | text delivered, `permit` |
> | `ai_input` absent | text withheld, `rights-reserved:ai_input` |
> | an untrusted source tightens | applies at once |
> | an untrusted source loosens | ignored |
> | trust for another action only | the loosening is ignored |
> | no confirmed label | the strictest value applies to the decision |

`com.example` and `<domain>` are placeholders. Replace them with the company's domain.