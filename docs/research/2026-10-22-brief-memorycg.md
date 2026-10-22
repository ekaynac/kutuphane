The brief follows. I checked all sources on 2026-10-22. I did not post anything and I did not edit any repo files.

# Brief: W3C AI Agent Memory Interoperability CG

## 1. What the group wants

**Corrections to `docs/13` and to the slice report:**
- Message [0022](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0022.html) is Matthew Hinkle's use case. It is not the citation thread.
- The citation fields are in [0003](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0003.html), [0005](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0005.html), [0006](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0006.html), [0008](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0008.html), [0009](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0009.html) and [0011](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0011.html).
- Message [0035](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0035.html) is the status of the catalogue.
- **The catalogue already has entries on both of our topics:** entry 4 (Hinkle, authority) and entry 5 (Jeongho Song, how far an erasure reaches). So we add to those two entries. We do not send new, separate entries.

**Use-case catalogue** (charter §5 item 1, a Community Group Report):
- **Format:** a short note on the list. The chair: "in the shape the entries already share: setting, actors, what moves or must remain, and what has to be verified."
- **Date:** the chair will post the working draft "by 30 October". "Corrections and new entries are welcome at any time."
- Each entry records a need that revision -03 does not meet "as a gap against that revision". Such a gap is not a failure for any implementation ([0034](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0034.html)).

**Hinkle (0022):**
- Check 4: "imported memory is evidence, not an automatic grant of authority."
- Test vector: an authorization, its revocation and an unresolved conflict.
- He asks how to express the checks "as testable acceptance criteria".
- Yasha Khandelwal (0023) says that provenance and reconciliation are not measured by agmi, "and I do not know of anything that does yet".

**derived-from (Jeongho Song, [0017](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0017.html)):**
- The open question: should a cell "carry a field that says a cell was derived from another cell … so that an erasure can follow that link?"
- Point 5 was added in 0018, 0021, 0024, 0025 and 0029: restoring an old copy must not bring the erased data back without a warning. A derived-from field does not solve point 5.

**Citation form:**
- Six proposed fields: item IRI, unit identifier, digest (algorithm, value and the bytes it covers), licence, retrieval time (UTC), source version.
- The citation goes inside the encrypted content.
- The digest covers only the source's own bytes. This is the view of three participants, and the baseline profile will decide.
- The chair asks for more views: "whether the profile should have a citation form at all."

**Charter v1.1 call for consensus ([0014](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0014.html)):**
- It closes on 2026-11-02.
- Option 1 keeps the reference to the chair's draft-saihm-memory-protocol and names the revision for each deliverable. Option 2 holds the reference open.
- Proposals for an independent assessor are due by 27 October.
- At present, three replies support option 1 and there are no objections.
- A reply is not required from us.

## 2. What we bring

- The decision rule, rules 4, 5 and 8: `docs/11-standard-draft.md` §4.
- The matching cases in `kstd/tests/decision/cases.yaml` (rule 4: lines 136–181; rule 5: lines 184–201; rule 8: line 265). The reference rule is `kstd/reference/decide.py`.
- `inputs`, `derive`, `erase` and `disposition`: `docs/11` §2, §3 and §5.
- Digest and licence handling: `src/kutuphane/kstd.py`, lines 34, 87 and 328 (`sha256:` over the raw file bytes; an SPDX expression or `unknown`).

## 3. Comparison

| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| Entry shape: setting, actors, moves/remains, verify | the drafts in §7 | match | — |
| Hinkle check 4 and his test vector | rules 4, 5 and 8, with 8 cases | match | Ours is asymmetric: a restriction counts from anyone, a loosening only from a trusted issuer. |
| Hinkle checks 2–3 (provenance, reconciliation) | origin, acceptance | partial | — |
| Testable acceptance criteria | result plus reason codes, deterministic | match | Yasha's served/reported/refused is for the storage layer. Our cases are for the decision layer. |
| derived-from field | `inputs` (§5), erasure of recorded derivatives (§3) | partial | Only spec text. There is no erasure case in `cases.yaml` and no erasure code in `decide.py` or in Kütüphane. |
| Point 5: no restore after erasure | — | we lack | — |
| An erasure record without the content | `disposition` | match | We adopt their erasure classes (`docs/13` §3.1). |
| The six citation fields | `kstd.yaml` path, digest, license | partial | We have no IRI, no retrieval time and no source version. |
| The digest covers the source bytes | sha256 of the file bytes | match | — |

## 4. Reason

- **For them:**
  - Our cases are the testable criteria that Hinkle asks for.
  - They also answer Jeongho's open question with a worked vector.
  - No one in the thread has yet defined what a missing or `unknown` licence means.
- **For us:**
  - Rules 4 and 8 and `inputs` get outside review before the conformance pack starts.
  - kstd takes the group's terms (D60).
  - The work prepares the ODRL contribution in 2027.

## 5. Consequences

**IPR and licensing ([CLA](https://www.w3.org/community/about/process/cla/)):**
- §2.1: we give a free copyright licence for each Contribution, and it cannot be taken back.
- §3.1: we give royalty-free patent licences for our Essential Claims, but only for text that actually goes into a Report.
- §5: we can withdraw a Contribution within 45 days. A Contribution becomes void if it is not in a Report within 150 days.
- §10: we must disclose our interest.
- §1: source code outside the Specification is not covered by the CLA. Our Apache-2.0 code stays as it is.
- **Before you post:** confirm that the company has no patents in this area (not verified).

**What changes in kstd:**
- **If they accept:**
  - `inputs` maps to their `derived-from`.
  - The citation fields `retrieved_at`, `source_version` and the IRI go into the item.
  - Erasure cases go into `cases.yaml`. This is necessary in all cases, by the rule in `kstd/README.md`.
- **If they reject:**
  - kstd keeps `inputs` and rules 4, 5 and 8 as its own terms, as an external statement layer.
  - The decision rule does not change.

**Time:**
- About 3–4 hours to adapt the drafts and post them.
- About 1 day to add the erasure vector to `cases.yaml` and `decide.py`.
- About 1 hour each week to read the list.
- About 2 hours to review the working draft.

**Risks:**
- The group is small (about 36 participants).
- The chair is the only author of the referenced draft.
- Our fields can become only "gaps against -03".
- In the custodial profile, the operator can read the `inputs` that are inside the encrypted content.
- If we use kstd words instead of their words, they can see our posts as promotion of kstd.

## 6. Steps for the operator

1. Use your own W3C account, with your company as the affiliation. Join the group at https://www.w3.org/community/ai-agent-memory-interop/join. Not verified: how W3C links the company's CLA acceptance to your account, and whether you can post to the list without a subscription.
2. Do this before 26 October, so that the chair can include our text in the working draft:
   - Post Draft A as a reply to 0022.
   - Post Draft B as a reply to 0029 (the thread that starts at 0017).
   - Post Draft C as a reply to 0008.
3. Optional: reply to the call for consensus by 2 November.
4. After 30 October: check the working draft, correct our text, and answer questions.
5. When the conformance pack starts, offer the cases in machine-readable form.

## 7. Draft text

Replace `<Company>` and `<Name>` before you post.

**A. Re: entry 4. Imported entries that loosen permission**

> Matthew, all — an addition to entry 4. Interest: I work for `<Company>`; we build an on-prem knowledge library and a draft decision rule with test cases. AI disclosure: drafted with AI assistance; I reviewed it and take responsibility.
>
> **Setting:** a receiver imports entries from several sources. Some restrict what the agent may do (a revocation, "process locally only"). Some loosen it (a grant, "may go to a cloud model").
> **Actors:** user; receiver and operator; two or more sources; a person who resolves conflicts.
> **Must remain:** every entry, ignored ones too, as evidence with its issuer.
> **Verify:**
> 1. A restricting entry applies at once, from any source.
> 2. A loosening entry applies only if the receiver's own policy names its issuer for that kind of entry, scope and action, with an expiry. Otherwise the receiver declines.
> 3. Trust for one action does not extend to another; trust with no expiry is not trust.
> 4. Two trusted sources in conflict, no precedence rule: ask a person. A timestamp never decides between sources.
> 5. A removal from an untrusted source does not remove; it shows as a dispute.
>
> **Vector** (entry D is "local only"):
> V1 untrusted S: "D may go to cloud" → request cloud → decline.
> V2 untrusted S: "D must not leave" → request forward → decline.
> V3 P trusted to loosen only for read; P: "cloud OK" → request cloud → decline.
> V4 P trusted, no expiry → treated as untrusted.
> V5 trusted P "accepted", trusted T "withdrawn", no precedence → escalate; with precedence [P, T] → act on P, whichever is newer.
>
> Gap against -03: the cell has no issuer or kind for an entry about another cell.

**B. Re: entry 5. derived-from as recorded inputs**

> Jeongho, all — a worked answer to your open question, and it leaves point 5 untouched.
> A derived note records, when written, the ids of the cells it came from.
> - Erasure covers every note whose inputs reach an erased cell, transitively.
> - A note is removed whole, never edited. A replacement is a new note with a new id.
> - A note with no recorded inputs is reported as "scope unknown", not as clean.
> - Copies already shared are listed as unresolved.
>
> **Vector:** cells A (user U), B (user V). N1←[A], N2←[A,B], N3←[B], index entry X1←[N1]; N1 shared to provider Q.
> Request: erase A (request R1).
> **Expected:** erased {A, N1, N2, X1}; kept {B, N3}. The record holds R1, time, rule "recorded inputs", the erased ids and "unresolved: N1 at Q", with no content. No live cell lists an erased id. A new N4←[B] is allowed.
> Placement: the inputs list can sit in the encrypted content, as the citation does. Then only key holders can follow it, which matters for a profile where the holder keeps the keys.

**C. Re: citation form**

> Russell, all — yes to a citation form with the six fields. Three points from implementation:
> 1. Licence is an SPDX expression or the explicit value `unknown`. A missing or `unknown` licence gives no permission. A collection licence does not replace the licence of a unit that has none.
> 2. Do not write a default for a value that the source did not state.
> 3. We agree that the digest covers the source's own bytes. We pin sha-256 over the raw bytes.
>
> A note derived from a cited cell should list that cell as an input, so that a withdrawal reaches it.