# Knowledge standard — draft 0.2

**Status:** DRAFT 0.2, 2026-10-20. The working name is `kstd` (operator question Q5).
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
| `acceptance` | `accepted` or `withdrawn` for an item, in a scope; a withdrawal names a successor or a terminal reason | eligibility for ordinary use |
| `mandate` | rule authority for an item, in a scope | the item can impose a requirement |
| `contest` | a dispute of an item, with a reason | a visible mark and a review; removes nothing |
| `policy` | permissions and prohibitions on actions, with conditions; delegations | the input to the decision rule |
| `status` | a signed, sequenced status stream of an issuer: withdrawals, holds, supersessions, with an expiry | freshness across nodes |
| `receipt` | `use` (written by `deliver`) or `outcome` (signed by the actor; it references the `use` receipt) | audit; the trigger for reviews |
| `disposition` | an erasure: its scope, completion, exceptions and unresolved copies | honest erasure |

A field outside this standard MUST NOT change a decision.

## 3. Operations

| Operation | Effect |
|---|---|
| **register** | Admit an artifact or a received statement. Verify the format, the identity and the signature. Assign **no** authority. A received status or receipt statement does not become an item. |
| **derive** | Create an artifact from recorded inputs and a named process: summary, translation, embedding, consolidation, training. The new item lists its inputs. Its rights are checked per input for each proposed use (§5); its handling inherits the strictest input value. |
| **attest** | Add a statement. A statement MUST NOT give powers that its issuer does not have. |
| **decide** | Apply the decision rule (§4). Result: `permit`, `deny` or `escalate`, with a reason. |
| **deliver** | Release content or metadata to a person, a model, a tool or a node, as typed data, with the required notices. Write a `use` receipt. |
| **erase** | Execute a disposition. Remove the retained data and the recorded derivatives in its scope. Record completion, exceptions and unresolved copies. |

**Transfer between nodes** is a composition: `deliver` to a node → `register` at the receiver → a `receipt`. A package is in quarantine until it passes registration and the receiver's acceptance policy.

**Actions** in policies: `read`, `infer`, `derive`, `train` (a kind of `derive`), `forward`, `activate`.
- Reading an item never permits activating it.
- Execution after activation belongs to the host and the tool boundary, outside this standard.

## 4. The decision rule (normative)

Given the same request, policy, trust configuration, statements and evaluation time, two conforming implementations MUST return the same result and the same reason.

1. The result is the strictest of all applicable rules: `deny` > `escalate` > `permit`.
2. No applicable permission means `deny`.
3. An unknown *required rights* term means `deny`. Unknown required *applicability* context means `escalate`.
4. An imported statement that tightens applies at once. One that loosens applies only if the trust policy names its issuer for that **kind × scope × action**, with an expiry.
5. When two trusted issuers conflict, the local precedence rule decides; without one, the result is `escalate`. A timestamp never decides between issuers.
6. A status past its maximum age removes **rule authority** only. The content stays available as evidence.
7. A `permit` is bound to exact artifact, statement and policy versions, and it has an expiry.
8. No proposal from an issuer that is not trusted can remove an accepted item from use. A **hold** needs a named owner and a review deadline.

The conformance test suite (a set of request → result cases) is part of the standard.

## 5. Properties and their behaviors

| Property | Values | Behavior |
|---|---|---|
| **Origin** (`item`) | `human`, `model`, `unknown` (counts as `model`) | `deliver` shows it as a notice. Training or legal controls are profile policies, not core rules. |
| **Inputs** (`item`) | statement ids | Used for checking the rights of a derivative, the reach of a withdrawal and the reach of poisoning. Repeated copies of one source do not count as independent evidence. A withdrawal reaches every *recorded* descendant and every node that checks status. |
| **Rights** (`item`) | license (SPDX id or `unknown`); holder (a person or a collective); `ai_use`: `search`, `ai_input`, `train` = `y` / `n` (absent = `n`); a legal basis note | The license terms of each input are checked for each proposed use; they are not merged into one value. Licenses stay valid as granted; a withdrawal does not cancel an irrevocable license. `ai_use` maps to IETF AIPREF and TDMRep in a versioned mapping. |
| **Personal data** (`item`) | `yes`, `no`, `unknown` (counts as `yes`) | `yes`: `forward` needs a recorded legal basis; the data is stored encrypted and is in the scope of erasure. Logs at receivers hold no personal data; the origin's log holds pseudonymized data and is in the scope of erasure. |
| **Applicability** (`item`) | conditions, exclusions; observation time; valid time | Outside the conditions or the valid time: no rule authority, and `escalate` if the request needs authority. Dated evidence stays available with its date. |
| **Acceptance** | `pending` (default), `accepted`, `suspended`, `withdrawn` | Only `accepted` is eligible for ordinary use. `suspended` stops ordinary use until fresh authorization or a successful status check. `withdrawn` is history. |
| **Mandate** | present in a scope / absent | Only an accepted item with a mandate can be cited as a requirement. Without one, an accepted item is evidence. |
| **Handling** | export: `normal` / `restricted`; route: `cloud_ok` / `local_only` | `restricted`: never leaves the node. `local_only`: processed only in the locations that the node declares as under its control. Derivatives inherit the stricter value. Before an administrator confirms the value: `restricted` + `local_only`. |
| **Activation** (`policy`) | a permission for `activate`, in a scope | Only then can an agent run the item as an instruction or a skill. The item can still be read as evidence. |

## 6. State transitions

Each change records: trigger, actor, scope, reason, policy version, prior statement.

| Transition | Trigger | Actor | Automatic? | Reversal |
|---|---|---|---|---|
| new → `pending` | register or derive | system | yes | removal under the retention policy |
| `pending` → `accepted` | the required evidence passes | an approver whose identity is not the author's: a person, or an agent under a signed **delegation** (scope, expiry, a named accountable person) | only under delegation | withdrawal of acceptance |
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
| **L2 Governed** | The decision rule with its test suite, acceptance, mandates, delegation, activation, handling, receipts, honest erasure, a tamper-evident append-only audit. Storage is free. | Enforced. |
| **L3 Federated** | Signed status streams with a maximum age (as in TUF timestamps and OCSP stapling), withdrawal delivery, trust policy per issuer × kind × scope × action, receipt tracking. | Enforced across nodes. A controlled transfer needs an L2 receiver; a public release does not. |

**Profiles** (outside the core, versioned): mappings (SWHID, IPTC, PROV-O, Web Annotation, ODRL, Croissant, Agent Skills, AIPREF/TDMRep), compliance (GDPR, AI Act Art. 50/53, DSM Directive), obligations, outcome ranking, labels, block and claim extraction, transparency witnesses. A conformance badge never claims legal compliance.

## 8. L0 example (`kstd.yaml`)

```yaml
standard: kstd/0.2
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this file
issued: 2026-10-20
rights:                                  # default for every item
  license: CC-BY-4.0                     # SPDX id, or unknown
  holder: "ACME GmbH"
  ai_use: {search: y, ai_input: y, train: n}   # absent = n
  personal_data: no                      # yes | no | unknown (= yes)
notices: ["Attribution: ACME GmbH, 2026"]
items:
  - path: procedures/pressure-test.md
    digest: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    origin: human                        # human | model | unknown (= model)
    valid_from: 2026-01-01
    applies_to: "Plant 3, line A"
  - path: notes/weekly-summary.md
    digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    origin: model
    rights: {personal_data: unknown}     # overrides the default
```

## 9. Questions for the operator

| # | Question | Proposal |
|---|---|---|
| Q1 | License: D10 makes Kütüphane proprietary. | Specification CC-BY-4.0. Validator, decision rule, test suite and package tools Apache-2.0. The rest of Kütüphane: a separate decision. |
| Q2 | The first consumer (day-one value). | LLMDAP and Kütüphane read `kstd.yaml`: answers show origin and rights, and egress follows `ai_use` and handling with no extra work. |
| Q3 | Automatic approval under a signed delegation (§6). | Yes in the core; risk profiles can forbid it. D54 changes: the *delegation* is human-only. |
| Q4 | Maximum status age at L3. | A default of 7 days, per node policy. |
| Q5 | Standards home and name. | Map to the W3C AI Agent Memory community group and stay the layer below it. Find a second implementer before v1. Choose the final name. |

## 10. Change log (0.1 → 0.2)

- **Decisions:**
  - D1: no core origin gate; three values.
  - D2: delegated approval.
  - D3: storage is free; decision determinism is normative.
  - D4: artifact and statement identities, package for transfer.
  - D5: own `ai_use` terms, mapped to AIPREF and TDMRep.
  - D6: `use` and `outcome` receipts.
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
