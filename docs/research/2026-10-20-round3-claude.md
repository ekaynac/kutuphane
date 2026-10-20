# Round 3 — Claude (independent proposal)

## 1. Thesis

In the AI age, knowledge is no longer scarce text. It is a **network of attributable claims, the judgments about those claims, and the reliance on them**.
- Models can produce text without limit. They cannot produce **accountability**: who asserted what, on which evidence, who accepted it for which use, who relied on it, and what happened then.
- A knowledge standard must therefore govern **claims, judgments, rights and reliance**. It must not govern genres or storage formats. Representations that are specific to one model (embeddings, summaries, fine-tunes) are **disposable caches** of claims, never the knowledge itself.
- A node's job is to **route** claims and judgments under rights and local trust, and to record reliance and its outcomes. The fitness of knowledge comes from **outcomes of use**, not from its age or its genre.

The core is small: five objects, nine verbs, three gates. It can survive changes in models, because it governs commitments, not representations.

## 2. Blind spots (ranked)

1. **We have no record of reliance or outcome.** We record who *read* a passage (the audit). We do not record who *acted* on a claim, and with what result. Without this:
   - fitness is unmeasurable;
   - a bad claim cannot be traced to its consequences;
   - consolidation has no signal.

   Our runbook feedback (AT-15) is a small, local case of the missing general mechanism. In safety-critical fields, *reliance* is the unit of accountability (for example, aviation and medical incident reporting).
2. **Our time model is too poor.** "Durable / window" mixes two different times:
   - *valid time:* when a claim is true in the world;
   - *record time:* when the system knew or accepted it.

   Bitemporal data models solve this ([SQL:2011 temporal tables](https://en.wikipedia.org/wiki/SQL:2011); Jev-Mem also separates observation time from event time). Without both times, a node cannot answer "what did we believe on date D, and was it true then?". That question decides audits, liability and AI Act record keeping.
3. **We treat machine representations as knowledge.** Vectors, summaries and model memory become stale when the model changes. The durable object is the claim, plus a **derivation recipe**: the source ids, the model id and the parameters. Any cache can be rebuilt or discarded. This answers "knowledge beyond human language" safely:
   - machine content is allowed;
   - but **authority attaches only to content that a stated verifier can check** (a person, a test, a schema, a proof).
4. **Executable knowledge is a supply chain.** Skills, prompts and procedures are code that agents execute. The software supply chain already solved signing, provenance and review attestations ([SLSA](https://slsa.dev), [Sigstore](https://www.sigstore.dev), [in-toto](https://in-toto.io)). We built `activate`, but we have no attestation of review and no pinning across nodes.
5. **We need tamper evidence, not a blockchain.** Append-only Merkle logs with independent witnesses give cheap, verifiable history across organizations ([Certificate Transparency, RFC 9162](https://www.rfc-editor.org/rfc/rfc9162); [Sigstore Rekor](https://docs.sigstore.dev/logging/overview/)). The research papers that use ledgers reach for blockchains where a transparency log is sufficient.
6. **Adoption needs immediate value at L0.** The standards that won (robots.txt, RSS, SPDX ids, schema.org, MCP) were tiny, gave value on day one, had a reference implementation, and degraded gracefully. The standards that lost demanded global agreement on an ontology first (OWL-heavy Semantic Web projects). L0 must be a file convention that gives better answers and citations on the first day.
7. **Rights must use the formats that the law already reads.** The TDM opt-out (EU DSM Directive Art. 4(3)) has a machine-readable W3C community protocol ([TDMRep](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/)). Providers of general-purpose models must respect such reservations ([AI Act Art. 53(1)(c)](https://eur-lex.europa.eu/eli/reg/2024/1689/oj)). If our L0 rights fields map 1:1 to TDMRep and SPDX, they work in court and in crawlers on day one.
8. **Incentives are missing.** A node shares when sharing returns value. We need reciprocity:
   - routed answers come back;
   - labelers build reputation;
   - reliance outcomes show which sources are reliable.

   Without this, the "router of humanity's knowledge" stays an idea.

## 3. The core

### 3.1 Five objects (the narrow waist)

| Object | Definition | Identity |
|---|---|---|
| **Content** | Bytes of any media type: text, table, image, code, or a machine format. | hash of the bytes |
| **Claim** | A statement that can be relied on. It has a pointer into the content (a span or a selector, as in [W3C Web Annotation](https://www.w3.org/TR/annotation-model/)), its **origin**, its **valid time** and its **rights**. A whole document can be one claim. | hash of the claim envelope (content ref + origin + valid time + rights) |
| **Judgment** | A signed opinion about a claim, made by a named author: a standing, a role, a scope, a contest, an endorsement, a label. | hash + signature; never inside the claim's hash |
| **Policy** | Permissions, prohibitions, obligations, dispensations (an [ODRL](https://www.w3.org/TR/odrl-model/) profile) on objects, actions and purposes. | versioned |
| **Event** | One entry in an append-only, Merkle-chained log. Every state is a fold over events. | log position + hash |

**Two notes:**
- The **block** stays the deterministic local anchor *inside* a node. Claims point to blocks; blocks never travel alone.
- **Personal data** is never in the immutable log. The log holds references, and the referenced data is encrypted under keys that can be destroyed.

### 3.2 Nine verbs (closed)

| Verb | Effect | Main behavior |
|---|---|---|
| **assert** | creates a claim | starts its record time; the author is fixed |
| **derive** | creates a claim from other claims (summary, inference, consolidation, embedding) | origin `derived`, a derivation recipe, and links to the sources; never edits its sources |
| **judge** | adds a judgment (standing, role, scope, label, endorsement) | changes authority and ranking at the nodes that trust the judge |
| **contest** | a judgment that disputes a claim | answers show "disputed"; the claim goes to a review queue; nothing is hidden |
| **supersede** | links a new claim to an old one | the old claim leaves current answers *in the successor's scope and time* |
| **revoke** | the issuer withdraws a claim or a judgment | the revocation travels to every receiver; a successor or a terminal reason is required |
| **rely** | a person or an agent acts on a claim | records the purpose, the action and the policy in force; opens an outcome slot |
| **report** | an outcome of a reliance (worked, failed, harmed, changed) | the fitness input; a "failed" or "harmed" report contests the claim |
| **erase** | destroys the keys of personal or confidential data | the content becomes unreadable everywhere; the log keeps the fact of erasure |

**Grant, prohibit and oblige are policy operations, not knowledge verbs.** They use the existing authorization layer (Zanzibar-style grants plus the ODRL profile).

### 3.3 Properties and their behaviors

**Intrinsic properties** (inside the claim envelope; they travel; nobody can change them without a new claim):

| Property | Values | Behavior |
|---|---|---|
| **origin** | `human`, `agent`, `model`, `external`, `derived` (with a recipe) | **Evidence bar:** a non-human origin cannot reach authority without a human judgment, and the judge must not be its author. Answers always show the origin. |
| **valid time** | an interval, or open; `as_of(t)` = observed at *t* | A claim is current only inside its valid time. Outside it, the claim is history. |
| **rights** | SPDX license, rights holder (a person or a collective), TDM reservation (TDMRep), personal data `yes / no / unknown` | An unknown value means no sharing and no training. Rights decide routing (L3). |

**Judgments** (opinions; local; a node computes the *effective* value from the judges that it trusts):

| Judgment | Values | Behavior |
|---|---|---|
| **standing** | `accepted`, `pending`, `retired` | Only `accepted` claims answer with authority. |
| **role** | `rule`, `evidence`, `none` | A `rule` gives requirements and checks for conflicts; `none` is not indexed. |
| **scope** | conditions *and exclusions* (typed context) | Outside the scope: `escalate`, not an answer. |
| **endorsement** / **label** | open vocabulary from a named labeler (SKOS-mapped) | Ranking and filtering only; never a gate. |

**Gates** (local and closed; they never travel as permissions; an incoming value can only tighten):

| Gate | Values | Behavior |
|---|---|---|
| **sensitivity** | `normal`, `restricted` | `restricted` is never exported. |
| **egress** | `local_only`, `cloud_ok` | controls the model route |
| **instruction** | `no`, `yes` | `yes` needs `activate` and a signed review attestation; it is pinned by hash |

**Decisions** have three outcomes: `permit`, `deny`, `escalate`.

### 3.4 State transitions (the rules that apply to all)

1. **Strictness order** for every gate and judgment. A move to a stricter value can be automatic. A move to a looser value needs the named human role, and it is audited.
2. **Availability limit.** An automatic or model-proposed change can tighten *access* at once. It cannot remove an `accepted` claim from answers. It can only mark the claim "disputed" and queue it.
3. **Author ≠ judge** for `accepted` and for `rule`. A quorum (k-of-n) is a policy option for commons.
4. **Imported judgments are proposals,** unless the local trust policy names the judge as trusted *for that judgment type and scope*. Gates are never imported loosely.
5. **Revocation and supersession are scoped:** they act only in the successor's scope and valid time. A cycle is refused.
6. **Obligations** have their own state machine: `issued → pending → discharged | dispensed | violated → escalated`. Discharge evidence is a signed receipt.

### 3.5 Conformance levels and rights

| Level | Objects and verbs | Rights | Standards |
|---|---|---|---|
| **L0 Described** | content + frontmatter; implicit claims (a file is a claim) | **declared:** SPDX, rights holder, TDMRep, personal data | OKF, SPDX, TDMRep |
| **L1 Attested** | claims with hashes, signatures, origin, valid time; assert, derive, supersede, revoke | inside the signed envelope | content addressing, [C2PA](https://c2pa.org/specifications/) for media, Ed25519 / [VC 2.0](https://www.w3.org/TR/vc-data-model-2.0/) |
| **L2 Governed** | judgments, gates, policy, rely and report, erase; Merkle-chained log | **enforced:** ODRL profile, purpose, obligations, erasure by key destruction | Zanzibar, [PROV-O](https://www.w3.org/TR/prov-o/) (minimal profile), ODRL |
| **L3 Federated** | routing, trust policies, revocations and judgments that travel, witnessed logs | **routing precondition:** the receiver is at least L2 and enforces | [nanopublication-style](https://nanopub.net) journal sync, [Dataspace Protocol](https://docs.internationaldataspaces.org/ids-knowledgebase/dataspace-protocol), CT-style witnesses, MCP/A2A |

**The rights declaration is core** (L0) because it costs nothing and it is necessary for any sharing. **Enforcement is not core** (L2+).

## 4. Reuse and avoid

**Reuse:**
- OKF (files);
- SPDX (licenses);
- TDMRep (TDM opt-out);
- W3C Web Annotation (selectors, judgments as annotations);
- PROV-O (derivation, minimal profile);
- ODRL (policy profile with closed gate terms);
- SKOS (open labels);
- VC 2.0 / C2PA (signatures, media provenance);
- Merkle transparency logs (RFC 9162 pattern);
- the nanopublication journal sync;
- AT Protocol labelers (the composable-moderation pattern);
- Zanzibar / OpenFGA;
- MCP for agent access;
- SLSA / in-toto for executable knowledge.

**Avoid:**
- mandatory RDF or OWL reasoning (it makes gates fragile and adoption slow);
- blockchains, DAOs and votes about truth;
- global ontologies;
- confidence values without calibration;
- any model-specific representation as authority.

## 5. Durability tests (2027–2032)

1. **2027 — contexts of 10 M tokens.** Retrieval becomes less important; whole libraries fit in a prompt. **The core holds:** authority, rights and gates still decide *which* claims may enter the context. Value moves from search to governance, which is exactly our core.
2. **2028 — agents write most new knowledge.** **The core holds:**
   - origin + the evidence bar + author ≠ judge stop laundering;
   - rely/report gives the fitness signal that separates useful agent output from noise.
3. **2029 — model-native memory and fine-tuning on organizational knowledge.** **The core holds:**
   - models are derivations with a recipe;
   - the `train` right and TDMRep decide what may enter them;
   - revocation and erasure mark which models must be retrained or discarded.

   **Must change:** a "model as derived object" profile.
4. **2030 — agent-to-agent formats that no human reads.** **The core holds:** content may be any media type. **The limit:** authority needs a stated verifier, so opaque content stays `evidence` at most. This is a deliberate brake.
5. **2032 — a commons of thousands of nodes.** **The core holds:**
   - journal sync + witnessed logs + labelers + local trust scale without consensus;
   - rely/report outcomes become reputation.

   **Must change:** a discovery layer, which is a separate profile.

## 6. Kill list

- **K1–K8 presets as a concept in the standard:** keep them only as UI shortcuts.
- **"Block" as a standard concept:** it is an implementation detail of the claim selector.
- **Origin as "metadata, no gate":** it becomes intrinsic and gated.
- **Time basis `durable` / `window`:** replaced by bitemporal valid time + record time.
- **`retired` as a local-only state:** revocation and supersession are events that travel.
- **Book-level policy as the only policy unit:** policy applies to any object set.
- **The two fixed prohibitions as special cases:** they become ODRL prohibitions with closed terms.

## 7. Failure modes and counter-measures

| Failure | Counter-measure |
|---|---|
| Nobody adopts L0 | L0 must improve answers on day one (citations, rights) with zero infrastructure; reference tooling; permissive license |
| Complexity creep | every new value needs a named behavior and a conformance test; a yearly removal review |
| Poisoning through federation | gates never loosen on import; the evidence bar; contest; rely/report reputation; witnessed logs |
| Laundering of model text as human text | origin inside the signed envelope; C2PA for media; author ≠ judge |
| Legal conflict (erasure vs logs) | personal data only by reference; crypto-shredding; logs keep the fact, not the data |
| Denial of knowledge through automatic tightening | the availability limit (3.4 rule 2) |
| Vendor capture | no mandatory model; caches are disposable; the open specification comes first |

## 8. Questions for the operator

1. Do you accept **reliance and outcome** (rely/report) as a core verb? It is new, and it is the fitness signal.
2. Do you accept **bitemporal time** instead of durable/window?
3. May **opaque machine content** carry authority if a verifier exists, or is it always `evidence` at most?
4. Is the **commons** governed by quorum judgments only, or do you also want reputation from outcomes?
5. Must L1 signatures use one format (VC 2.0), or may an L1 node choose?
