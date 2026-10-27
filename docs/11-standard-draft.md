# Knowledge standard — draft 0.2

**Status:** DRAFT 0.2, 2026-10-20. The working name is `kstd` (operator question Q5). **Since D59 (2026-10-22) this draft is a contribution and a test tool, not a standard proposed alone:** it is re-checked against the existing work in `docs/13-landscape.md` and brought to the matching communities.
- **History:** draft 0.1 merged three round-3 proposals (Claude, Astra, Mythos). Astra and Mythos critiqued it in round 4. The change log is in §10. The sources are in `docs/research/2026-10-20-round{3,4}-*`.
- **Language:** ASD-STE100 Simplified Technical English. **MUST**, **MUST NOT** and **MAY** are normative.

## 1. Scope and shape

This standard governs **accountability for knowledge**:
- who stands behind a statement;
- what may be done with it and with what is derived from it;
- how a correction or a withdrawal reaches the people and systems that check it.

It does not govern genres, storage or transport. The shape is an hourglass:
- formats, models and languages above the waist;
- storage and transport below it;
- in the waist, only **artifacts**, **statements** and one **decision rule**.

It serves an organization node (on-prem, air-gapped possible) and a network of nodes (routers of shared knowledge) with the same model.

## 2. The waist

| Element | Definition | Identity |
|---|---|---|
| **Artifact** | Exact bytes with a media type and a format version, in any format: text, table, code, vectors, a skill folder, a model checkpoint. The media type and format version select the decoder. An unsupported format MUST NOT get meaning from a guess. | multihash of the bytes |
| **Statement** | A signed record by a named **issuer** about artifacts or statements: `issuer, about[], kind, body, issued_at`. Signed as DSSE (raw bytes, no canonicalization). | digest of the signed bytes |
| **Package** | A manifest plus artifacts and statements, as a directory or a tar. It declares its **intended use** and its unresolved dependencies. It works over a network, USB or a data diode. | digest of the manifest |

An artifact identity and a statement identity are separate. A correction of rights changes a statement; the artifact keeps its identity.

**Statement kinds (closed):**

| Kind | Body | Effect |
|---|---|---|
| `item` | names artifacts; declares origin, rights, inputs, applicability, personal data | makes the artifacts knowledge that the node can evaluate |
| `acceptance` | `accepted`, `rejected` or `withdrawn` for an item, in a scope; a withdrawal names a successor or a terminal reason; a rejection names its reason. A body (a council, the IESG) can be recorded as the source's decision maker, but a local acceptance needs a named person or a delegated agent (D68). | eligibility for ordinary use |
| `mandate` | rule authority for an item, in a scope | the item can impose a requirement |
| `contest` | a dispute of an item, with a reason | a visible mark and a review; removes nothing |
| `policy` | permissions and prohibitions on actions, with conditions; delegations | the input to the decision rule |
| `status` | a signed, sequenced status stream of an issuer: withdrawals, holds, supersessions, with an expiry | freshness across nodes |
| `use_record` | `use` (written by `deliver`) or `outcome` (signed by the actor; it references the `use` record). Not called "receipt": in SCITT a receipt is a log inclusion proof, and in DPV/ISO 27560 a consent record. | audit; the trigger for reviews |
| `disposition` | an erasure: its scope, completion, exceptions and unresolved copies | honest erasure |

A field outside this standard MUST NOT change a decision.

## 3. Operations

| Operation | Effect |
|---|---|
| **register** | Admit an artifact or a received statement. Verify the format, the identity and the signature. Assign **no** authority. A received status or use record does not become an item. |
| **derive** | Create an artifact from recorded inputs and a named process: summary, translation, embedding, consolidation, training. The new item lists its inputs. Its rights are checked per input for each proposed use (§5); its handling inherits the strictest input value. |
| **attest** | Add a statement. A statement MUST NOT give powers that its issuer does not have. |
| **decide** | Apply the decision rule (§4). Result: `permit`, `deny` or `escalate`, with a reason. |
| **deliver** | Release content or metadata to a person, a model, a tool or a node, as typed data, with the required notices. Write a `use` record. |
| **erase** | Execute a disposition. Remove the retained data and the recorded derivatives in its scope. Record completion, exceptions and unresolved copies. |

**Transfer between nodes** is a composition: `deliver` to a node → `register` at the receiver → a `use_record`. A package is in quarantine until it passes registration and the receiver's acceptance policy.

**Actions** in policies: `read`, `infer`, `derive`, `train` (a kind of `derive`), `forward`, `activate`.
- Reading an item never permits activating it.
- Execution after activation belongs to the host and the tool boundary, outside this standard.

## 4. The decision rule (normative)

Given the same request, policy, trust configuration, statements and evaluation time, two conforming implementations MUST return the same result and the same reason.

1. The result is the strictest of all applicable rules: `deny` > `escalate` > `permit`.
2. No applicable permission means `deny`.
3. An unknown *required rights* term means `deny`. Unknown required *applicability* context means `escalate`.
4. An imported statement that **tightens access** (rights, handling, a prohibition) applies at once, from any issuer. A statement that loosens applies only if the trust policy names its issuer for that **kind × scope × action**, with an expiry. A withdrawal or a hold affects **availability**, not access, so rule 8 applies to it: from an issuer that is not trusted, it is only a visible contest mark.
5. When two trusted issuers conflict, the local precedence rule decides; without one, the result is `escalate`. A timestamp never decides between issuers.
6. A status of an imported item that is past its maximum age removes **rule authority** only. The content stays available as evidence, and rule authority comes back when a current status arrives (over the network or in a package). The maximum age is set **per trusted source**; the default is 30 days. An administrator can set "never" for a source; when the last status is older than the default age, each use then shows the notice "status not checked". A node's own items need no status check.
7. A `permit` is bound to exact artifact, statement and policy versions, and it has an expiry.
8. No proposal from an issuer that is not trusted can remove an accepted item from use. A **hold** needs a named owner and a review deadline.

The conformance test suite (a set of request → result cases) is part of the standard.

## 5. Properties and their behaviors

| Property | Values | Behavior |
|---|---|---|
| **Origin** (`item`) | `human`, `assisted`, `model`, `tool`, `unknown` (counts as `model`). `assisted` = model output that a named person (`reviewed_by`) reviewed in substance (not only for spelling or grammar) and took editorial responsibility for. `model` = a **learned model** (parameters fitted to data: generative or not, e.g. LLMs, classifiers, embeddings, neural OCR, machine translation) produced or changed any part of the content. `tool` = software made the content by running **written rules** (code, templates, queries, configuration, rule sets that people wrote) on recorded inputs, or recorded events of the world; **no learned model at any step**; it needs `software_agent: {name, version}` (docs/17). If any input is `model` or `unknown` the output is `model`; an `assisted` input makes it `assisted`; a change of form only (format conversion, formatter) keeps the input origin. A rule engine (thresholds, decision tables, policy or inference engines) is `tool` when people wrote every rule, threshold and weight; any part fitted to data makes it `model` (D64, docs/17 §8). Mapping: IPTC Digital Source Type (`tool`: `dataDrivenMedia`, recordings `digitalCapture`); W3C AI Content Disclosure `human-only` / `ai-assisted` / `ai-autonomous` (`tool` → `human-only`, `unknown` → no key); C2PA `softwareAgent`. | `deliver` shows it as a notice. On export, `model` and `unknown` items are marked as AI-generated; `assisted` items are not marked and carry `reviewed_by` (EU AI Act Art. 50(4)); `tool` items are not marked and carry their `software_agent`, so all output of one generator version can be trusted or suspended together. An `assisted` item gets authority only through acceptance, the same as a `model` item. Training or legal controls are profile policies, not core rules. |
| **Inputs** (`item`) | statement ids | Used for checking the rights of a derivative, the reach of a withdrawal and the reach of poisoning. The check covers the whole recorded lineage: inputs of inputs, transitively, each once (a cycle ends); a recorded ancestor that is not known denies (`input-unknown`). Rights, `ai_use` and personal data (with the synthetic trust rule) are checked per input; handling is inherited, the strictest value of the lineage wins. An empty input list is not proof that an item has no inputs. Repeated copies of one source do not count as independent evidence. A withdrawal or an erasure reaches every *recorded* descendant, also of a source that is not held locally, and every node that checks status. |
| **Rights** (`item`) | license (SPDX id or `unknown`); holder (a person or a collective); `ai_use`: `search`, `ai_input`, `train` = `y` / `n` / absent | The license terms of each input are checked for each proposed use; they are not merged into one value. A package license does not replace an item license: an item with no license of its own stays `unknown`. Licenses stay valid as granted; a withdrawal does not cancel an irrevocable license. `ai_use` is stored with three states: an absent term is "not stated". **The decision treats an absent term as `n`**; an export writes it as absent, never as `n`. A search (a `read` request with `operation: search`) needs `search: y`; a search that computes embeddings in the node only to select items and link to them does not need `ai_input` (AIPREF: an embedding model is not generative). Sending content to a model (`infer`) needs `ai_input: y`. `ai_use` maps to IETF AIPREF, the ODRL AI profile and TDMRep in a versioned mapping (`train` covers generative and non-generative training). |
| **Personal data** (`item`) | `yes`, `no`, `synthetic`, `unknown` (counts as `yes`); legal basis: one or more DPV codes (`eu-gdpr:A6-1-a`…`f`, `eu-gdpr:A9-2-a`…`j`) | `yes`: `forward`, and `infer` with a `destination` outside the node (a model at a processor), need a recorded legal basis; an `infer` without a `destination` stays in the node and needs none. The licence check of `forward` does not apply to `infer` (`ai_input` covers the use). The data is stored encrypted and is in the scope of erasure. `synthetic` (looks like personal data, describes no real person): no legal basis is needed, but only when the item issuer is trusted for `item` statements in the scope; from any other issuer it counts as `unknown`. Logs at receivers hold no personal data; the origin's log holds pseudonymized data and is in the scope of erasure. Categories use DPV PD. |
| **Applicability** (`item`) | conditions, exclusions; observation time; valid time | Outside the conditions or the valid time: no rule authority, and `escalate` if the request needs authority. Dated evidence stays available with its date. |
| **Acceptance** | `pending` (default), `accepted`, `rejected`, `suspended`, `withdrawn` | Only `accepted` is eligible for ordinary use. `suspended` stops ordinary use until fresh authorization or a successful status check. `withdrawn` is history: it was accepted once. `rejected` is history too, but it was **never** accepted (D68). |
| **Mandate** | present in a scope / absent | Only an accepted item with a mandate can be cited as a requirement. Without one, an accepted item is evidence. |
| **Handling** | export: `normal` / `restricted`; route: `cloud_ok` / `local_only` | `restricted`: never leaves the node. `local_only`: processed only in the locations that the node declares as under its control. Derivatives inherit the stricter value. Before an administrator confirms the value: `restricted` + `local_only`. |
| **Activation** (`policy`) | a permission for `activate`, in a scope | Only then can an agent run the item as an instruction or a skill. The item can still be read as evidence. |

## 6. State transitions

Each change records: trigger, actor, scope, reason, policy version, prior statement.

| Transition | Trigger | Actor | Automatic? | Reversal |
|---|---|---|---|---|
| new → `pending` | register or derive | system | yes | removal under the retention policy |
| `pending` → `accepted` | the required evidence passes | an approver whose identity is not the author's: a person, or an agent under a signed **delegation** (scope, expiry, a named accountable person) | only under delegation | withdrawal of acceptance |
| `pending` → `rejected` | a decision not to accept, with a reason | the same approvers as for acceptance | only under delegation | a new proposal (a new item); the rejection stays in history |
| `accepted` → `suspended` | approval expiry, a hold, a failed dependency, a stale status | policy engine, or a hold owner | yes, if the policy declares it | fresh authorization, or a successful status check |
| `accepted` → `withdrawn` | correction, replacement, withdrawal; supersession only in the shared scope and time | the issuer, or a prior replacement rule | only under a replacement rule | a new acceptance; the withdrawal stays in history |
| contest mark set | a contest from a trusted issuer | the contest issuer | yes (mark only) | the issuer withdraws it, or a reviewer closes it |
| local permission → suspended | its source item is withdrawn, and the permission depends on continued acceptance | system | yes | the source is accepted again, and the grant holder confirms |
| package: quarantined → registered / rejected | registration checks and the acceptance policy | the receiving node; a person or a delegated agent | as the policy declares | a resubmitted package |
| retained → erased | a valid disposition | the custodian | execution can be automatic | none |
| mandate, handling, rights, delegation changed | a new statement | an issuer with that power | tightening: yes; loosening: rule 4 of §4 | a new statement |

## 7. Conformance levels

| Level | Requires | Rights |
|---|---|---|
| **L0 Described** | One manifest file (§8). Unsigned. A tool that ignores every field still reads the files. **Reading the bytes is not permission to use them.** A validator checks digests, SPDX ids, `ai_use` terms and dates. | Declared. `unknown` gives no permission. |
| **L1 Verifiable** | Signed statements (DSSE) and packages, multihash, agile algorithms, revision checks, derive with inputs. | Bound to exact versions. |
| **L2 Governed** | The decision rule with its test suite, acceptance, mandates, delegation, activation, handling, use records, honest erasure, a tamper-evident append-only audit. Storage is free. | Enforced. |
| **L3 Federated** | Signed status streams with a maximum age per source (as in TUF timestamps and OCSP stapling; the stream can travel in packages, so air-gapped nodes conform), withdrawal delivery, trust policy per issuer × kind × scope × action, use-record tracking. | Enforced across nodes. A controlled transfer needs an L2 receiver; a public release does not. |

**Profiles** (outside the core, versioned): mappings (SWHID, IPTC, PROV-O, Web Annotation, ODRL, Croissant, Agent Skills, AIPREF/TDMRep), compliance (GDPR, AI Act Art. 50/53, DSM Directive), obligations, outcome ranking, labels, block and claim extraction, transparency witnesses. A conformance badge never claims legal compliance.

## 8. L0 example (`kstd.yaml`)

```yaml
standard: kstd/0.2
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this file
issued: 2026-10-20
rights:                                  # default for every item
  license: CC-BY-4.0                     # SPDX id, or unknown
  holder: "ACME GmbH"
  ai_use: {search: y, ai_input: y, train: n}   # absent = not stated; a decision treats it as n
  personal_data: no                      # yes | no | synthetic | unknown (= yes)
notices: ["Attribution: ACME GmbH, 2026"]
items:
  - path: procedures/pressure-test.md
    digest: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    origin: human                        # human | assisted | model | tool | unknown (= model)
    valid_from: 2026-01-01
    applies_to: "Plant 3, line A"
  - path: notes/weekly-summary.md
    digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    origin: assisted                     # a model wrote it; a named person reviewed it
    reviewed_by: "Ayşe Yılmaz <ayse@acme.example>"
    rights: {personal_data: unknown}     # overrides the default
  - path: reference/api/index.html
    digest: sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae
    origin: tool                         # written rules only; no learned model at any step
    software_agent: {name: typedoc, version: "0.26.11"}   # strings; quote numeric-looking versions
```

## 9. Licenses

Five different things have different licenses:

| What | License | Why |
|---|---|---|
| The specification text | CC-BY-4.0 | Anyone can copy and implement it, with attribution. |
| The code (Kütüphane, validator, decision rule, test suite, package tools) | an open-source license; proposal: Apache-2.0 | Permissive, with a patent grant, as used by MCP and OpenFGA. |
| **Knowledge content** (artifacts) | **chosen by each issuer**, declared in `rights.license` | The standard never imposes a license on content. `unknown` gives no permission. |
| **Statements and manifests** (metadata) | recommended default: CC0-1.0, unless the issuer declares otherwise | Metadata must flow freely, so that receivers can check rights and status (as Wikidata and Europeana do for metadata). A statement contains no content. |
| Use records and audit logs | not shared by default | They are local records, and they can contain personal data. |

## 10. Operator decisions (2026-10-20)

| # | Question | Decision |
|---|---|---|
| Q1 | License | **The standard and Kütüphane are fully open source** (D10 was a misunderstanding; corrected by D56). Code license proposal: Apache-2.0. **The licenses of knowledge content and metadata (§9) are approved** (2026-10-21). |
| Q2 | Day-one value | Proposal: Kütüphane itself. A folder with `kstd.yaml` gives answers with origin, validity and license at once, and the handling rules are enforced by Kütüphane and LLMDAP with no extra work. Waiting for confirmation. |
| Q3 | Automatic approval under a signed delegation | **Yes.** D54 changes: the delegation is human-only; the approval can be automatic. |
| Q4 | Maximum status age | **Option c** (2026-10-21): a maximum age per source, default 30 days; "never" is allowed for air-gapped sources, with a visible warning (§4 rule 6). |
| Q5 | Name | **`kstd` is the temporary name.** |

## 11. Change log (0.1 → 0.2)

- **Decisions:**
  - D1: no core origin gate; three values.
  - D2: delegated approval.
  - D3: storage is free; decision determinism is normative.
  - D4: artifact and statement identities, package for transfer.
  - D5: own `ai_use` terms, mapped to AIPREF and TDMRep.
  - D6: `use` and `outcome` receipts.
  - D60 (2026-10-22, after the landscape study `docs/13`): origin `assisted` with `reviewed_by`; personal data `synthetic`; three-state `ai_use`; legal basis as DPV codes; `receipt` renamed to `use_record`.
  - D63 (2026-10-23): origin `tool` with `software_agent` (option B of docs/17, for now; the two-axis option is decided after labelling v4); a learned model that is not generative still counts as `model`.
- **Added:** the decision rule (§4) and its test suite, reversals for every transition, behaviors for personal data and handling, the L0 example.
- **Corrected:**
  - rights are not merged into one value;
  - withdrawal does not cancel irrevocable licenses;
  - DSSE instead of JCS;
  - SWHID and IPTC only as mappings;
  - status freshness follows TUF and OCSP, not Certificate Transparency;
  - "every descendant" became "recorded descendants and nodes that check";
  - personal data in the origin's log is pseudonymized and in the scope of erasure.
- **Removed from the core:**
  - `transfer` (now a composition);
  - `cite`, `execute`, `label`, `refs`;
  - the mandate value `none` (it is indexing policy);
  - the role list (replaced by mandate and activation);
  - the Merkle log as storage;
  - generic duties;
  - outcome ranking;
  - SKOS labels;
  - the agreement history.
