# Round 4 — Mythos critique of draft 0.1

## 1. Decisions D1–D6

**D1 Origin gate: keep origin, remove the fixed gate.** Origin is a signed declaration with two values, `human` and `model`, plus `unknown`, which counts as `model`. Its core behavior is one: deliver shows it as a notice. A training exclusion for `model` is a default policy in a profile, not a core rule. Reason: the canon needs a behavior per value, and `composite` and `external` have none that `model` and `human` do not already have. I argued for the gate in round 3. Astra was right that the authority gate is the signer.

**D2 Automatic approval: yes, under a signed delegation.** The delegation is a `policy` statement with scope, expiry and a named accountable human. The approver identity is never the author identity. Risk profiles can forbid it. Reason: my own 2027 test already assumed agent volume that a human-only rule cannot carry. Amend D54: the *delegation* is human-only, the act is not.

**D3 Log fold: not normative.** Make the test normative instead: given the same statements and the same trust policy, two implementations must return the same decision. Storage stays free. L2 needs an append-only, tamper-evident log; witnesses are L3. Reason: canon rule 3, and a signed-statement table with a hash chain is enough.

**D4 Travelling unit: keep the merge, in one sentence.** The `item` is the unit of identity, the package is the unit of transfer, and each statement is self-contained. Delete the "smallest claim" discussion.

**D5 Rights vocabulary: AIPREF terms as values, TDMRep as an output.** The manifest carries the AIPREF categories. The validator emits a TDMRep file for the web. Reason: AIPREF is at [draft-08 with a standards-track status](https://datatracker.ietf.org/doc/draft-ietf-aipref-vocab/), TDMRep is a frozen community report with one bit, and the [OLG Hamburg](https://www.technologyslegaledge.com/2025/12/robert-kneschke-v-laion-judgment-of-10-december-2025-ref-5-u-104-24/) requires a reservation that an automated process can act on. Both proposals express the same bit, so the mapping is lossless.

**D6 Reliance: a `receipt`, no verb.** Keep two closed receipt subtypes: `use`, which deliver writes automatically, and `outcome`, which the actor signs and which references the `use` receipt. Reason: Claude's substance survives, and a verb adds nothing that a statement kind does not already do.

## 2. Canon check

**Values and operations with no behavior change:**
- `origin`: `composite` behaves as `model`; `external` behaves as `human`. Collapse to two values.
- `item.refs` (§3): undefined and unused. `about[]` already names the subjects.
- `artifact.format version` and `media type`: no behavior is stated. State it: they select the decoder, and an unsupported format cannot acquire meaning (Astra).
- `judgment` subtype `label`: by §5 it never changes a gate. It is a profile, not a core kind.
- Action `cite`: no gate in §4–§5 uses it. Either define it as "present as authoritative" under the mandate, or cut it.
- Action `execute`: the standard ends at activation. Execution belongs to the host and tool boundary (§2.5).
- Operation `transfer`: it is deliver to a node, register from a node, plus a `receipt`. Quarantine is a package state. It is a composition, not a primitive.
- "Three failure costs" (§6 end): it says "each has its own rule" and gives no rule. Either write the rules or cut the paragraph.

**State changes without trigger, actor or reversal.** The merge lost Astra's reversal column, and no transition has an audit column. Add both. Specific gaps:
- `accepted → suspended`: no reversal. Astra had "fresh authorization" or a successful status check.
- `accepted → withdrawn`: no reversal. Mythos had `retired → pending` (reopen, curator).
- `any → contested`: no reversal. The contest issuer withdraws it, or the review closes it.
- `grant → suspended`: no reversal when the source item is reinstated.
- `duty: violated → escalated`: no actor. Claude's `dispensed` exit is lost.
- `package: rejected`: no reversal, no actor for `rejected`.
- `new → pending`: no reversal. Astra had removal under retention.
- `suspended` is a state in §6 and not a value of Acceptance in §5.

## 3. Errors

1. **"multihash; SWHID-compatible" is a contradiction.** SWHID v1, now [ISO/IEC 18670:2025](https://www.iso.org/es/contents/data/standard/08/99/89985.html), uses SHA-1 only. A v2 with SHA-256 is in an [exploration phase with no timeline](https://groups.google.com/g/swhid-discuss/c/G4lKMtr-iLA/m/76__j-ZWBgAJ). Say "multihash; SWHID is an optional mapping".
2. **in-toto statement plus canonical JSON (JCS) mixes two incompatible designs.** in-toto signs through DSSE, which ["avoids canonicalization to reduce attack surface"](https://github.com/secure-systems-lab/dsse/blob/master/README.md) and signs the [raw serialized bytes](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md). Pick DSSE: the statement digest is the digest of the signed bytes, and no canonicalizer exists to attack.
3. **The origin values are not IPTC terms.** The [IPTC Digital Source Type vocabulary](https://cv.iptc.org/newscodes/digitalsourcetype/) has twenty terms such as `trainedAlgorithmicMedia` and `compositeWithTrainedAlgorithmicMedia`. It has no `human`, `model` or `external`. Drop the IPTC claim, or give the exact mapping in a profile.
4. **Certificate Transparency is not a status mechanism.** [RFC 9162](https://www.rfc-editor.org/rfc/rfc9162) gives public, auditable issuance logs for monitors. Use-time status with a maximum age is the pattern of the [TUF timestamp and snapshot roles](https://theupdateframework.github.io/specification/latest/index.html) and of [OCSP must-staple](https://www.rfc-editor.org/rfc/rfc7633). §2.7 must cite those.
5. **"A withdrawal of an input finds every descendant" overclaims.** The origin node does not know the descendants that other nodes derive. The correct statement, consistent with §2.7, is: every descendant that checks status finds the withdrawal.
6. **"Personal data stays out of permanent logs" is wrong for the origin node.** A salted commitment is pseudonymised data, and it stays personal data for the holder of the salt ([EDPB Guidelines 02/2025](https://www.edpb.europa.eu/our-work-tools/documents/public-consultations/2025/guidelines-022025-processing-personal-data-through_en)). The receiver side is settled by the CJEU in [EDPS v SRB, C-413/23 P](https://curia.europa.eu/juris/liste.jsf?num=C-413/23). Correct text: receivers' logs hold no personal data; the origin's log holds pseudonymised data and is in scope of erasure.
7. **§5 puts AI Act Art. 50 inside the core table.** §7 says that all compliance mappings live in a dated profile. Move the reference.

## 4. Cuts

- **§2 (twelve agreements) and §8:** a standard has no history section. Fold the normative sentences into §3–§7 and move the rest to a change log. This is about one third of the text.
- **`transfer`, `cite`, `execute`, `label`, `refs`:** see §2 above.
- **Origin: four values to two.**
- **"Descriptive labels (open, SKOS-mapped)":** replace with one sentence: "A field outside this standard never changes a decision."
- **SWHID, IPTC, PROV-O, Web Annotation, ODRL, Croissant, Agent Skills:** out of the core text, into one "mappings" profile. The core names only multihash, DSSE, SPDX and AIPREF.
- **L1 "post-quantum ready":** say "agile", which is testable, and nothing more.
- **§9 questions 1, 2 and 5:** they are operator decisions, not draft content.

## 5. One missing piece

**The decision rule.** §2.9 says "our own small decision rule is normative", and no section writes it. Without it, two implementations cannot pass the same conformance test, so the "two implementations before v1" condition cannot be met. The rule fits in six lines:

1. The result is the strictest of all applicable statements: `deny` > `escalate` > `permit`.
2. No applicable `permit` means `deny`.
3. An `unknown` required term means `deny` for rights and `escalate` for applicability.
4. An imported statement that tightens applies at once; one that loosens applies only if the trust policy names its issuer for that kind, scope and action.
5. Two trusted issuers in conflict: the local precedence rule decides, or `escalate`. Time never decides between issuers.
6. A stale status, past its maximum age, removes `rule` authority and nothing else.

This also replaces the "three failure costs" paragraph.

## 6. The minimal L0

```yaml
# kstd.yaml — one file at the root of the folder
standard: kstd/0.1
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this file
issued: 2026-10-20
rights:                       # default for every item
  license: CC-BY-4.0          # SPDX id, or unknown
  holder: "ACME GmbH"
  ai_use: {train-ai: n, ai-input: y, search: y}   # AIPREF terms; absent = n
  personal_data: no           # yes | no | unknown (unknown counts as yes)
notices: ["Attribution: ACME GmbH, 2026"]
items:
  - path: procedures/pressure-test.md
    digest: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    origin: human             # human | model | unknown (unknown counts as model)
    valid_from: 2026-01-01    # no valid_to = open
    applies_to: "Plant 3, line A"
  - path: notes/weekly-summary.md
    digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    origin: model
    rights: {personal_data: unknown}   # overrides the default
```

A tool that ignores every field still reads the files. A validator checks digests, SPDX ids, AIPREF terms and dates, and nothing else.