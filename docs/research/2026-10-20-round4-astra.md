Keep artifacts, attributed statements, and local decisions. The [merged draft](/home/mega/kobra/docs/11-standard-draft.md) is larger than its tested behavior. Restore the reversal rules from [Astra](/home/mega/kobra/docs/research/2026-10-20-round3-astra.md) and the link between action and outcome from [Claude](/home/mega/kobra/docs/research/2026-10-20-round3-claude.md).

**1. D1–D6**

- **D1 — No universal origin gate.** Require the declared origin to appear in provenance views; let a training or legal profile add specific controls. Human origin does not prove quality, and model origin does not prove failure.
- **D2 — Permit automatic approval under bounded delegation.** Put independent human approval in risk profiles, including the current D54 product policy. Remove the universal author–approver separation and human package acceptance from the core.
- **D3 — Specify results, not storage.** Require enough audit evidence to explain each decision, with a declared retention period. Remove the mandatory Merkle log and event replay model.
- **D4 — Artifact and statement identities are separate; packages carry them.** An `item` is one statement type, not the universal identity unit. A package must declare its intended use and missing dependencies.
- **D5 — Keep separate rights meanings.** Use a versioned TDMRep mapping now and an optional AIPREF mapping; neither replaces licenses or access policy. [TDMRep](https://www.w3.org/community/reports/tdmrep/CG-FINAL-tdmrep-20240510/) is a Community Group report, while the cited [AIPREF draft-06](https://www.ietf.org/archive/id/draft-ietf-aipref-vocab-06.html) is work in progress.
- **D6 — Keep receipts, without new verbs.** A use receipt must identify the action and decision; an outcome receipt must refer to that use. The merge kept Claude’s outcome labels but lost this essential link.

**2. Canon check**

The following values have no distinct, testable effect, or have an incomplete effect:

| Element in §3–§6 | Gap and correction |
|---|---|
| Origin: `human`, `model`, `composite`, `external` | No rule maps each value to a result. `external` describes source location, not production method. Remove it from this axis; permit `unknown`. |
| Personal-data flag | Declared in §3, but absent from §5 behavior. Specify what `yes`, `no`, and `unknown` change, or move the flag into a privacy profile. |
| Export: `normal`, `restricted` | No destination rule defines the difference. Define the blocked destinations and authorized exceptions. |
| Route: `cloud_ok`, `local_only` | The route effect is clear, but “local” has no defined boundary. Define the permitted processing locations. |
| Outcome: success, failure, harm, correction | “Changes ranking and opens reviews” does not distinguish the four values. Define separate effects in an outcome profile. |
| `suspended` | Used in §6 but absent from the acceptance vocabulary. Specify which uses stop; keep suspension separate from historical acceptance. |
| Duty states | No required consequence follows `violated` or `escalated`. Name the blocked action or required review. |
| Open labels | “Can change display and search” permits labels with no effect. Require a display or search rule for each supported label. |
| `time`, `refs`, media type, format version | Their processing rules are incomplete. Distinguish time meanings and reference types; define decoder selection and unsupported-format behavior. |

Inputs, applicability, acceptance, and the four mandate values have stated effects. However, `executable` must not prevent inspection as evidence.

**No operation in §4 is behavior-free.** `register`, `derive`, `attest`, `decide`, `deliver`, `transfer`, and `erase` each change a record, decision, or retained copy. But the policy actions lack a complete mapping: define whether `train` also requires `derive`, what `infer` covers, and where `cite`, `activate`, and `execute` are checked.

The transition defects are:

| Transition | Missing part |
|---|---|
| New → pending | No reversal. Also, receiving a status statement must not turn that statement into a pending knowledge item. |
| Pending → accepted | No reversal; add withdrawal of approval. |
| Accepted → suspended | No reversal; require fresh authorization after the cause is resolved. |
| Accepted → withdrawn | No reversal; allow new approval while retaining the withdrawal record. |
| Any → contested mark | No authorized clearing actor, clearing trigger, or reversal. |
| Grant → suspended | Execution actor and restoration rule are absent. |
| Duty transitions | Issuing, checking, and escalation actors are absent. Split receipt acceptance, deadline failure, and escalation; specify correction or terminal status. |
| Package transitions | Arrival explains quarantine only. Validation and acceptance criteria, rejection actors, and retry rules are absent. |
| Retained → erased | Trigger, custodian, and lack of guaranteed reversal are stated. Keep this rule. |

Changes to mandates, scope, rights, handling, delegation, labels, and review status also lack transition rules. In particular, “before confirmation” has no confirmation actor or evidence requirement.

For every change, record the trigger, actor, scope, reason, policy version, and prior record. A generic append-only log does not define these fields.

**3. Errors**

- **Rights are not one “strictest combination.”** License conditions can conflict. CC BY-SA, for example, restricts additional downstream terms and specifies permitted adapter licenses. Keep input terms separate; check each proposed use and the output terms. Handling restrictions may use a separate conservative rule. [CC BY-SA legal code](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en)

- **Withdrawal does not suspend every kind of grant.** Suspend local permissions that explicitly depend on continued approval. Do not imply that withdrawal cancels an irrevocable copyright license. [CC BY-SA, §2](https://creativecommons.org/licenses/by-sa/4.0/legalcode.en#s2)

- **The origin vocabulary is misattributed.** IPTC does not define the draft’s four-value set; its `composite` term does not necessarily mean human-plus-model content. Also, Article 50 duties depend on the actor, output, and use, with exceptions. Put those mappings in a profile. [IPTC terms](https://cv.iptc.org/newscodes/digitalsourcetype/), [Commission guidance](https://digital-strategy.ec.europa.eu/en/faqs/transparency-obligations-under-article-50-ai-act)

- **ODRL is more than a serialization.** It defines constraints, duties, action relationships, and conflict rules. Specify a small ODRL profile or an explicit mapping; do not replace its meanings silently. [ODRL 2.2](https://www.w3.org/TR/odrl-model/)

- **Compatibility claims need exact formats.** A raw-byte multihash is not automatically SWHID-compatible: SWHID v1 content identifiers hash a specified header and content with SHA-1. The proposed statement fields also differ from in-toto’s schema. [SWHID](https://www.swhid.org/specification/v1.2/5.Core_identifiers/), [in-toto](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md)

- **References and salted commitments do not automatically remove personal data from logs.** Linkability and retained auxiliary data still matter. The cited EDPB consultation text expressly discusses this risk. [EDPB, §4.2](https://www.edpb.europa.eu/system/files/2025-04/edpb_guidelines_202502_blockchain_en.pdf)

- **“Finds every descendant” exceeds the available evidence.** The graph finds recorded descendants available to the node. Missing links and undisclosed copies remain unresolved; a receipt cannot prove future receiver compliance.

- **Certificate Transparency is not a revocation service.** Its specification points to separate certificate status mechanisms. Keep log proofs and current authorization status distinct. [RFC 9162, §3.2.1](https://www.rfc-editor.org/rfc/rfc9162.html#section-3.2.1)

- **L0 conflicts with the general signed-object requirements.** State which requirements start at each level. Reading file bytes while ignoring metadata must not count as permission to use them.

**4. Cuts**

- Remove mandatory Merkle storage, generic duties, outcome ranking, and SKOS mappings from the core. Put them in profiles.
- Make `transfer` a package workflow built from delivery, registration, and statements. Preserve its checks without another core verb.
- Remove `none` from mandate. Search exclusion belongs to indexing policy.
- Replace the exclusive role list with separate scoped grants for rule authority and activation.
- Delete claims that all successful standards followed one adoption path, or that a closed reference implementation guarantees failure. Require open specifications, tests, and interoperable implementations instead.
- Remove repeated agreement summaries from normative text.

**5. One missing piece**

The draft needs **one precise decision contract**. Given the same request, policy, trust configuration, statements, and evaluation time, two implementations must return the same result and reason.

Define precedence, unknown required terms, stale authorization, and action relationships. Bind a permit to exact artifact and policy versions, with an expiry. Publish small test cases before adding more concepts.

**6. Minimal L0**

Proposed syntax, not an existing schema. This example describes an unsigned file. The digest matches the UTF-8 text `Use the test room for demonstrations.` followed by one LF newline.

```yaml
format: knowledge-l0-proposal-1
issuer: "Example Lab"
artifacts:
  - path: demo.txt
    media_type: text/plain
    digest:
      sha256: 24f559eaaa5970eaea8b6d77f03beb2eda69a86d04fded763d7efbbbdaea9796
    origin: unknown
    applicability:
      purpose: demonstration
      authoritative_use: false
    rights:
      license: unknown
      holder: unknown
      tdm_reservation: unknown
    personal_data: "no"
    required_notices: []
```

Here, `unknown` supplies no permission. A consumer needs a recorded basis for the proposed use.