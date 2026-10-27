# Scope review — similar systems, a minimal core, and human vs agent authorship

**Status:** 0.1, 2026-10-27. It is for the operator's decision (§7).
**Basis:** four research reports in `docs/research/`:
- `2026-10-27-oss-km-survey.md`: 16 open-source knowledge, RAG, agent-memory and data-governance projects;
- `2026-10-27-kompl.md`: an in-depth look at github.com/tuirk/Kompl;
- `2026-10-27-human-vs-agent-origin.md`: how a system can tell agent writes from human writes;
- `2026-10-27-astra-scope-raw.md`: Astra's critique of our scope.

**Language:** ASD-STE100 Simplified Technical English.

The operator asked:
1. Are there similar open-source systems, and what is our difference?
2. Did we add more detail than a standard needs, compared with OKF's minimal format? Can the required part be smaller?
3. How do we make sure that an AI agent can never record knowledge as human, and how do we support a human who tells an agent to record their own words?
4. Is this meaningful work?

## 1. Similar systems: where we are different

| Group | Examples | They have | They do not have |
|---|---|---|---|
| RAG / knowledge platforms | Onyx (33k★), RAGFlow (93k★), Dify (160k★), Open WebUI (157k★) | connectors, UI, chunking, access per dataset or group, MCP | rights per item, AI-use permission, personal data + legal basis, origin, a policy decision |
| Agent memory | mem0, Graphiti/Zep, Cognee, Letta, Basic Memory | memory scoped by user/agent; Graphiti: a strong bi-temporal model (`valid_at` / `invalid_at`) | origin from authentication (the writer declares it), rights, a decision rule |
| Data-governance catalogs | DataHub, OpenMetadata, Apache Atlas + Ranger | owners, glossary, lineage, PII tags, access policies, review; Atlas: **PII tags propagate through lineage**; DataHub: `actor` + `impersonator` | **use** rights (they control *access*, not *what a model may do*); licence per item; a three-result decision |
| Knowledge format | OKF (Google) | markdown + frontmatter; `generated.by`, `verified`, `status`, `stale_after`, `sources` | rights, PII, signatures; trust is "advisory, not access control" |
| Personal wiki | Kompl (81★) | an LLM compiles a wiki from saved sources; good MCP tools; an injection fence | rights, PII, multi-user, trust; cloud models only |

**What only kstd/Kütüphane does** (verified in the survey):
1. **Use rights per item that stop model input.** `ai_input: n` means no embedding, no reranking and no answer. The catalogs control access only.
2. **Personal data with a DPV legal basis at export.**
3. **A deterministic permit / deny / escalate rule with public conformance cases.**
4. **Agent instructions need `activate`.**

**What is not new:**
- restrictions that follow lineage (Atlas has done this since about 2018);
- supersession over time (Graphiti does it better);
- origin labels (OKF, mem0 and DataHub have them).

**Where we are behind:**
- the community: 0★ and 1 contributor;
- connectors: we read folders only;
- the user interface;
- tests at scale.

**The real competition** is DataHub and OpenMetadata. They already have most of the infrastructure and could add a licence or AI-use property in one release.

## 2. Kompl

Kompl answers a different question: "turn my saved material into a wiki with no work". We ask: "may this item be used, by whom, for what, and who accepted it?" It does not make our work redundant. It does show our weakness: Kompl gives visible value on the first day, and we give mostly refusals and metadata.

**Useful to us:**
- its MCP **injection fence** (a random tag around each result), Apache-2.0;
- `quote_verified` (a derived claim keeps its source sentence, and the sentence is checked);
- separate source dates;
- agent writes that are off by default, with limits per call and per day.

**Cooperation chance:** in issue #104 the maintainer says that the work "establishing what an item is, where it came from" happens *before* Kompl. That is exactly the kstd layer. Two concrete steps:
1. A Kompl source connector that reads `kstd.yaml`: it skips `ai_input: n`, carries the licence and origin, and blocks the cloud model for personal data.
2. An export of Kompl pages as kstd items with `origin: model` and their recorded inputs.

The maintainer lists Turkey as her location.

## 3. Too much detail? A minimal core

**Astra's verdict:** yes, but the problem is more in the normative scope and the strict validation than in the number of fields.
- L0 blocks publication for unknown fields or incomplete reviewer data. Such errors could instead make only that one claim untrusted.
- Draft 0.2 standardizes eight statement kinds, lifecycles, delegation, erasure and federation, before search and answers have shown enough value.

**Proposal: three levels.**

| Level | Fields | Who fills them | Missing → |
|---|---|---|---|
| **Core envelope (required)** | `version`; `subject` = the content digest; `issuer` = from the authenticated write path or a verified signature | the system, never the person | not registered |
| **Core permissions (required for search and model answers)** | `ai_use.search`, `ai_use.ai_input` | once per folder; a file only as an exception | **deny**: not indexed, never sent to a model |
| **Profiles (only when that operation is used)** | licence (derive/forward/train); personal data + legal basis (export, cloud processing); origin details (`reviewed_by`, `software_agent`, `entered_by`); acceptance, mandate, validity (rule authority); activate (agents); tags; federation, status, erasure | the operation that needs them | that operation is denied or escalated; other operations still work |

**Origin stays in the core as a field with a safe default** (`unknown` = treated as `model`). It is never required from a person, and the system fills it from the write path (§4).

**Compared with OKF:** OKF v0.2 is no longer minimal either. It has provenance, trust, lifecycle and attestation. **What only kstd adds** is small:
- licence;
- `ai_use`;
- personal data + legal basis;
- a digest + a signature;
- the decision rule.

So kstd can be offered as **a small profile that OKF, DataHub and OpenMetadata can carry**, not as a competing format.

**Stop:**
- adding categories that have no shown operational benefit;
- guessing origin from prose: the measurement showed that nobody can do it;
- asking people again for facts that a machine already knows;
- counting agreement with our own reference engine as independent validation.

**Fix:**
- `kstd-init` grants `search: y` by default. It must start from "not stated", that is, deny.
- Rule 4 lets **any** issuer impose a restriction, so an attacker could deny access to everything. A restrictive statement also needs an admissibility rule, for example a trusted issuer or a limited scope.

## 4. Agent vs human authorship

**What a system can prove:** which credential wrote the bytes, and which verified person confirmed those exact bytes. **No system can prove that a human wrote a text.** A person can paste chatbot text.

**Rules (proposal R1–R7):**

| # | Rule |
|---|---|
| R1 | **Origin is computed by the server** from the write path (principal, on-behalf-of, channel, client, authentication strength). A requested origin is only a request. A lower value is always allowed; a higher value needs R3. |
| R2 | **An agent path always gives `model`:** an `agent:` principal, any MCP write, or a token with an `act` claim (RFC 8693). If an agent requests `human`, the item is stored as `model` with the notice `origin-claim-refused`, and a confirmation request is opened. |
| R3 | **Upgrade only by a confirmation in the person's own session.** The agent opens Kütüphane's own page by MCP URL-mode elicitation. The person sees the full text, chooses "these are my words, verbatim" → `human` (with `entered_by: agent:…`), or "a model wrote it, I checked it in substance" → `assisted`. Then the person signs with a passkey (WebAuthn with user verification). The challenge contains the digest of the exact bytes. **An answer in an MCP form is refused**, because the agent host could answer it. One changed byte → `model` again. |
| R4 | A direct write by a person counts as `human` only from the registered UI with fresh, user-verified login. Otherwise `unknown`, because a script can hold a person's token. |
| R5 | A `human` declared in `kstd.yaml` counts only from a trusted issuer. Otherwise `unknown`. |
| R6 | No proof → `model`, if we know that an agent wrote it; `unknown`, if we do not know the path. Both are handled as `model`. |
| R7 | The confirming person can withdraw the confirmation. Others use `contest`. |

**Your example:** you tell an agent "write this down, it is my decision". The agent writes it, and it is stored as `model`. A confirmation request goes to your page. You check the text and confirm with a passkey: "my words, verbatim". Then it becomes `human`, `entered_by: agent:claude`, confirmed by you. If you do not confirm, it stays `model`.

**Honest limits:**
- **It proves who confirmed, not who wrote.** A false claim then has a named, verified owner. That is accountability, not truth.
- **A person can confirm without reading.**
- **An agent that has a person's raw token** (browser automation, no `act` claim) looks like that person. The identity provider must forbid this, and token binding (DPoP) helps.

**In the core:** no new required field. The core needs only rule R5 and two optional fields, `entered_by` and a wider `reviewed_by`. The proof method (passkey, CIBA) is a Kütüphane profile.

## 5. Is this meaningful work?

**Yes, in a narrow form. Not yet in the broad form.**
- **Meaningful:**
  - a portable, enforceable contract for "may a model use this item, and who said so";
  - the decision rule and its conformance cases;
  - origin derived from authentication.

  The survey found no project that does this. Our own measurement supports it: Qwen gave 11 false `accepted` and 25 false `assisted`, so inference must stay apart from authorization.
- **Not proven:**
  - the broad standard: 8 statement kinds, lifecycles, federation;
  - Kütüphane as a product that competes with platforms of 30k–160k★.
- **Clear proof of value would be:**
  1. two independent consumers (for example Kütüphane and a Kompl or OKF connector) give the same decisions on independently judged cases;
  2. real users get useful answers with fewer wrong disclosures and fewer stale rules;
  3. a body or project that adopts the profile (OKF, DataHub, the ODRL work).

## 6. Proposed direction

1. **Shrink the normative core** to §3: the envelope + `ai_use` + the decision rule. Everything else becomes a profile that is required only by its operation.
2. **Origin from the write path** (§4 R1–R7). Kütüphane gets a write API with confirmation (G9).
3. **kstd as a profile for others.** First OKF (a rights family; the planned contribution, `docs/14` §6), then a DataHub/OpenMetadata mapping, then a Kompl connector.
4. **Keep Kütüphane as the reference implementation and the test bench.** Do not try to beat Onyx or Dify as a product.
5. **Measure value on real tasks** (radar, inframedic): fewer wrong disclosures, correct current rules, and the cost of labelling.
6. **Continue labelling v5.** The 120 human cases test exactly the judgments that cannot be automated: review, harmful agent files, binding rules, real persons.

## 7. Questions for the operator

1. **Minimal core:** do you accept the three levels in §3? The normative core would be envelope + `ai_use` + decision rule; everything else becomes a profile.
2. **Origin from the write path:** do you accept rules R1–R7? Then Kütüphane needs a write API with passkey confirmation.
3. **Position:** kstd as a small profile that other formats (OKF, DataHub, OpenMetadata) carry, with Kütüphane as the reference, rather than our own complete format and product?
4. **Kompl:** may we contact the maintainer and propose a `kstd.yaml` connector?
