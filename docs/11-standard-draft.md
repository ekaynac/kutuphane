# Knowledge standard — draft 0.1 (merged from brainstorm round 3)

**Status:** DRAFT 0.1, 2026-10-20. It merges three independent round-3 proposals: Claude, Astra (GPT-6) and Mythos (Claude Mythos 5.1). All three did web research. Their texts are in `docs/research/2026-10-20-round3-*.md`.
- §8 lists the points where the three disagree.
- §9 lists the questions for the operator.
- Round 4 (critique) follows.

**Language:** ASD-STE100 Simplified Technical English.

## 1. Thesis

Knowledge is no longer scarce text. Models produce text without limit, but they cannot produce **accountability**:
- who stands behind a statement, on what evidence;
- what may be done with it, and with everything derived from it;
- how a correction or a withdrawal reaches the people and systems that use it.

The standard governs these things. It does not govern genres or storage formats. Its shape is an **hourglass**:
- **the narrow waist:** content-addressed artifacts and signed statements about them;
- **above it, free to change:** formats, models and languages;
- **below it, free to change:** storage and transport.

Each node decides locally, from attributed statements and its own trust policy. The main loop is: **capture → test → authorize use → observe results → correct or withdraw.** Consolidation by agents is one step in this loop.

## 2. What all three proposals agree on

1. **The waist is small:** bytes with a digest, and signed statements about them. Blocks, chunking and claim extraction are profiles, not core.
2. **Everything except the artifact digest is an attributed statement:** provenance, origin, rights, approvals, contests, withdrawals, policies and receipts. A signature binds a statement to a key; it does not make the statement true or authoritative. Disputed statements are kept, but they do not become effective policy.
3. **Derive is a first-class operation.** Summarizing, translating, embedding, consolidating and training all create a new artifact from recorded inputs. Rights and handling of the result are the **meet** (the strictest combination) of the inputs. A withdrawal of an input finds every descendant.
4. **Decisions have three outcomes:** `permit`, `deny`, `escalate` (needs review). Only `permit` allows the action.
5. **Reading, activation and execution are separate rights.** An instruction label cannot secure an agent: hostile instructions can be in any content. Content is always delivered as typed data. Only an item with role `executable` can be activated, and only with a grant, at the host and tool boundary.
6. **Time has more than one meaning:** observation time, applicability (valid) time, and approval or authorization expiry. `as_of(t) = window(t,t)` is wrong: a dated observation stays useful evidence.
7. **Withdrawal does not travel by itself.** The status of an imported item is checked at use time against its issuer's signed status stream, with a declared maximum age. If the status cannot be checked, the item keeps its content but loses rule authority. Evidence: retractions reach only a small share of later citations; Certificate Transparency and TUF show the working patterns.
8. **Erasure must be honest.** Encrypted or hashed personal data can still be personal data (EDPB). Personal data stays out of permanent logs: by reference, or by salted commitment. Erasure is a recorded disposition. It names its scope, its exceptions and the copies that were not resolved. It never claims universal removal.
9. **Rights use existing vocabularies, with separate meanings:** copyright license (SPDX), TDM reservation (TDMRep / IETF AIPREF), data-protection basis, and local access policy. Unknown or conflicting required terms block the affected action. ODRL is a serialization; our own small decision rule is normative.
10. **Trust is specific:** issuer × statement type × scope × action, with expiry and delegation limits. Trusting a node to transport a package does not mean trusting it to approve a procedure.
11. **Availability is protected:** an untrusted proposal can never hide accepted knowledge. An emergency hold needs an owner and a review deadline.
12. **Adoption needs a consumer on day one.**
    - Each standard that won had a party that read the data and rewarded the producer.
    - The core (specification, validator, package format, decision algorithm) must be open source.
    - At least two independent implementations must exist before v1 is frozen.

## 3. The narrow waist

| Element | Definition |
|---|---|
| **Artifact** | Exact bytes with a media type, a format version and an agile content digest (multihash; SWHID-compatible). Any format: text, table, code, vectors, a skill folder, a model checkpoint. The digest gives identity, not meaning or permission. |
| **Statement** | A signed, typed record by a named issuer about artifacts or other statements: `issuer, about[], kind, body, time, refs`. It uses the shape of an in-toto statement, with canonical JSON (JCS). |
| **Package** | A signed manifest plus artifacts and statements, as a plain directory or tar (BagIt-like). It contains what a receiver needs to assess *one proposed use*. Unresolved dependencies are explicit. It works over a network, USB or a data diode. |

**Statement kinds (closed):**

| Kind | Purpose |
|---|---|
| `item` | The claim envelope: it names artifacts and declares origin, rights, inputs, applicability and the personal-data flag. |
| `judgment` | Acceptance, mandate (role), scope, contest, label. |
| `policy` | Permission, prohibition, duty. |
| `status` | Withdrawal, supersession, hold, erasure disposition. |
| `receipt` | A use, a delivery, a transfer, or the outcome of a use. |

**The log** is the node's append-only, Merkle-chained sequence of statements. The standard specifies observable behavior; storage is free (disagreement D3 in §8).

## 4. Operations (closed set)

| Operation | Effect |
|---|---|
| **register** | Admit an artifact or a received statement; verify format and identity; assign **no** authority. |
| **derive** | Create an artifact from recorded inputs and a named process; the result is `pending`; the rights are the meet of the inputs. |
| **attest** | Add a statement of any kind. A statement cannot give powers that its issuer does not have. |
| **decide** | Evaluate action × actor × purpose × destination × context against the policy and the trust policy. Result: permit, deny or escalate. |
| **deliver** | Release content or metadata to a person, model, tool or node, as typed data. It keeps the required notices and records the decision. |
| **transfer** | Send or receive a package: verify, quarantine, compare, accept, receipt. A node never forwards what the receiver's rights do not allow. |
| **erase** | Execute a disposition: remove the retained data and its derivatives in scope; record completion, exceptions and unresolved copies. |

**Named actions** for policies: `read`, `cite`, `infer`, `derive`, `train`, `forward`, `activate`, `execute`. Reading a procedure gives no right to execute it.

## 5. Properties and their behaviors

| Property | Kind of statement | Behavior |
|---|---|---|
| **Origin** | `item` (declared by the accountable signer; IPTC digital source type: human, model, composite, external) | Training and consolidation input and transparency marking (AI Act Art. 50). Never the only basis of a mandate without review. A false origin is a signed lie with a name on it. |
| **Inputs** | `item` | The derivation graph: the meet of rights, the reach of a withdrawal, the blast radius of poisoning. It separates "used as input" from "supports this conclusion". Repeated copies of one source do not count as independent evidence. |
| **Rights** | `item` / `policy` | Gates derive, train, deliver and transfer. Unknown means no. |
| **Applicability** | `item` / `judgment` | Conditions, exclusions and valid time. Missing required context blocks authoritative use and escalates. Dated evidence stays available with its date. |
| **Acceptance** | `judgment` | `pending` (proposal view) → `accepted` (ordinary use) → `withdrawn` (history, with a reason and a successor or a terminal reason). It belongs to an issuer and a scope; it does not claim universal truth. |
| **Mandate** | `judgment` | Roles: `rule` (can impose a requirement), `evidence` (support only), `executable` (activation only), `none` (not indexed; handling controls still apply). |
| **Handling** | `policy` | Export: `normal` / `restricted`. Route: `cloud_ok` / `local_only`. The stricter value is inherited by derivatives. Before confirmation, the value is `local_only`. |
| **Review conditions** | `policy` | Expiry, changed dependencies, contradictions, failed tests or bad outcomes cause a review or a suspension, as the policy declares. A review warning and an authorization expiry have different effects. |
| **Outcome** | `receipt` | Task success, failure, harm, correction. It changes ranking and opens reviews; use counts alone never give authority. |

Descriptive labels (open, SKOS-mapped) can change display and search. They never change a gate.

## 6. State transitions (summary)

| Transition | Trigger and actor | Automatic? |
|---|---|---|
| new → pending | register or derive; system | yes |
| pending → accepted | required evidence passes; an authorized approver (the author is never the approver) | only under explicit, bounded delegation (D2 in §8) |
| accepted → suspended | approval expiry, an authorized hold, a failed dependency, a stale status; policy engine | yes, if the policy declares it |
| accepted → withdrawn | correction, replacement or withdrawal; authorized issuer; supersession acts only in the shared scope and time | only under a prior replacement rule |
| any → contested mark | a contest from a trusted issuer | yes; marks only, removes nothing |
| grant → suspended | its source item is withdrawn | yes |
| duty: issued → discharged / violated → escalated | a signed receipt or a deadline | discharge needs a receipt |
| package: received → quarantined → accepted / rejected | transfer | acceptance by a human at L2+ |
| retained → erased | a valid disposition decision; custodian | execution can be automatic; no guaranteed reversal |

**Separate failure costs:**
- *access* (who may read);
- *availability* (accepted knowledge stays usable);
- *authority* (what may be imposed).

Each has its own rule. A single strictness order is not sufficient.

## 7. Conformance levels

| Level | Requires | Rights |
|---|---|---|
| **L0 Described** | Files plus a small manifest: digests, issuer, origin, applicability, rights or `unknown`, required notices. A validator. "Dumb-down": a tool that ignores every field still reads the files. **About one hour.** | **Declared:** SPDX, rights holder (a person or a collective), TDM reservation, personal data flag. Rights meaning starts here. |
| **L1 Verifiable** | Digests, signed statements and packages, agile signatures (post-quantum ready), revision checks, derive with inputs. | Bound to exact versions; travel inside the package. |
| **L2 Governed** | decide / deliver / derive gates, acceptance and mandates, delegation, review conditions, receipts, duties, honest erasure. | **Enforced.** ODRL serialization; unsupported duties block use. |
| **L3 Federated** | Capability negotiation, signed status streams with maximum age, withdrawal delivery, receipt tracking, trust policy per issuer × kind × scope × action. | Enforced across nodes. A controlled transfer needs an L2 receiver; a simple public release does not. |

**Compliance mappings** (GDPR, AI Act Art. 50/53, the DSM Directive) live in a separate, dated **compliance profile**, not in the core. Regulation moves, and a conformance badge must never claim general legal compliance.

## 8. Disagreements to resolve in round 4

| # | Question | Positions |
|---|---|---|
| D1 | Does origin (human vs model) have a gate? | **Mythos, Claude:** yes, for training and consolidation input and marking. **Astra:** no human premium; evaluate evidence and process. *Draft: the gate is on training input and marking, not on authority.* |
| D2 | Can approval be automatic? | **Astra:** yes, under bounded delegation; human-only in risk profiles. **Mythos, Claude:** a human approves, and the author is never the approver. Conflicts with D54 (`curate` is human-only). |
| D3 | Is "every state is a fold over the log" normative? | **Claude, Mythos:** yes. **Astra:** specify behavior only; allow simpler storage. |
| D4 | What is the travelling unit? | **Mythos, Claude:** the `item` statement (the claim). **Astra:** a package sufficient for one use; there is no universal smallest claim. *Draft: both: the `item` is the unit of identity, the package is the unit of transfer.* |
| D5 | Which rights vocabulary? | **Mythos:** IETF AIPREF (draft-06) now. **Astra, Claude:** TDMRep (W3C CG final) now, and track AIPREF. |
| D6 | Is reliance and outcome a core verb? | **Claude:** yes (rely/report). **Astra, Mythos:** receipts are statements. *Draft: `receipt` kind, no extra verb.* |

## 9. Questions for the operator (all three asked them)

1. **License (D10).** D10 makes Kütüphane proprietary. All three say that an open standard with a closed reference implementation fails. Proposal:
   - specification text CC-BY;
   - validator, package format, decision algorithm and conformance tests Apache-2.0;
   - the rest of Kütüphane can stay a separate decision.
2. **The first consumer.** Which workflow gives value on day one?
   - **Mythos:** LLMDAP and the agent runtime visibly behave better with a manifest.
   - **Astra:** reliable citations and controlled export.
3. **Automatic approval** (D2 above).
4. **Maximum offline age:** after how long without a status check must a node stop authoritative use of imported items?
5. **Standards home and second implementation:**
   - Join or map to the W3C AI Agent Memory Interoperability Community Group (chartered in 2026)?
   - Who builds the second independent implementation?
