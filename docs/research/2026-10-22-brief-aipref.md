# Brief: IETF AIPREF WG (ai-control)

## 1. What the group wants

- **Charter.** The charter asks for a vocabulary, the ways to attach it, and one way to reconcile several preferences. Enforcement, registries and auditing are out of scope. [charter-ietf-aipref-01](https://datatracker.ietf.org/doc/charter-ietf-aipref/)
- **Current text.** [draft-ietf-aipref-vocab-08](https://www.ietf.org/archive/id/draft-ietf-aipref-vocab-08.txt) is dated 2026-09-14. The draft says it does "NOT REFLECT CONSENSUS".
  - The categories are `train-ai` (generative models only), `ai-use` and `search`. The values are `y` and `n`.
  - An absent value is "unknown". About defaults, §5 says: "This document takes no position".
  - In §5.1, disallow wins over allow, and allow wins over unknown.
  - In §4.3, `search` "overrides" the other categories, but only while the outputs stay in the search application.
- **#246 (derived forms).** [Issue](https://github.com/ietf-wg-aipref/drafts/issues/246): "an index is a black hole for preferences". Two pull requests compete:
  - [PR #240](https://github.com/ietf-wg-aipref/drafts/pull/240) (Rosenthol) changes the definitions so that they also cover derivations.
  - [PR #253](https://github.com/ietf-wg-aipref/drafts/pull/253) (Thomson) builds on [#252](https://github.com/ietf-wg-aipref/drafts/pull/252). It adds: "Retaining preferences with assets that are transformed into an alternative format … including the creation of embeddings".
  - On 2026-10-22, Thomson wrote that a many-to-one transformation is "nebulous": "If you have something better to suggest, please do so".
  - B. Quinn (IPTC) asked for generic text.
- **#245 (preferences that go with models).** [Issue](https://github.com/ietf-wg-aipref/drafts/issues/245): vocab-08 §3.3 tells trainers to give the preferences with a distributed model, "or [indicate] what sorts of uses are consistent". EKR said that the rule puts obligations only on trainers, and #252/#253 extend it.
- **#153 and #154 (unknown, defaults).** Both are "deferred". In the interim chat, Thomson said "not urgent to answer those" ([chat log](https://datatracker.ietf.org/meeting/interim-2026-aipref-15/materials/chatlog-interim-2026-aipref-15-202610212000-00)).
- **Interim of 2026-10-21.** The [agenda](https://github.com/ietf-wg-aipref/wg-materials/blob/main/interim-26-10/agenda.md) had one item: review the issues and prepare for San Francisco. The minutes are not published (not verified).
- **IETF 127, San Francisco, 14–20 Nov.** Datatracker shows two AIPREF sessions, at 2026-11-16 19:30 UTC and 2026-11-19 19:00 UTC. They are still "waiting for scheduling", so the times are not final.
  - The agenda is not published. Draft WG agendas are due on 2026-11-04.
  - The I-D cut-off and the early-registration cut-off are both 2026-11-02. [Dates](https://datatracker.ietf.org/meeting/127/important-dates/)
- **Format.** Use GitHub comments and short plain-text mail. On 2026-10-13 the chair [wrote](https://mailarchive.ietf.org/arch/msg/ai-control/cQjT0yBfUkJFx2WxB2JJfNCuQDk/): "keep them short… AI-generated text is often verbose… you're responsible for it".

## 2. What we bring

- **`derive` and `inputs`:** a derived item lists its inputs. Its rights are checked per input for each use. See `docs/11-standard-draft.md` §3 and the Inputs row in §5.
  - **Status:** this is only in the spec. `kstd/reference/decide.py` does not read `inputs`, and none of the 35 cases in `kstd/tests/decision/cases.yaml` is about it.
- **The gate in Kütüphane, which is implemented:** if `ai_use.ai_input` is not `y`, Kütüphane makes no embedding and does no reranking, and the passage is not used in answers. If `search` is not `y`, the file is not indexed. See `src/kutuphane/kstd.py` and `kstd/README.md`.
- **Three-state storage and a fail-closed decision (D60):** the decision treats absent as `n`. Export does not write `n` for an absent value.

## 3. Comparison

| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| Absent = unknown | three-state storage (D60) | match | Draft 0.2 still says "absent = n" in storage. Change it first. |
| Default "no position" (§5) | absent → deny, only in the decision | partial | A local default, which §5 allows. |
| Most restrictive wins (§5.1) | rule 1, rule 4 | partial | We also need a trusted issuer for a loosening. |
| `search` overrides | flags are independent | we differ | `search: y, ai_input: n` → no embedding. AIPREF allows an embedding for search. |
| `ai-use` | `ai_input` | partial | Ours also covers embedding and reranking models. |
| `train-ai` (generative only) | `train` (all training) | partial | Note it in the mapping table. |
| #246/#253: preferences stay with derived forms | `derive` + `inputs` | partial | Spec only. No test case yet. |
| #245 §3.3: uses that are consistent | per-input check | partial | Not implemented. |

## 4. Reason

- **For them:** #253 has no rule for a derived form made from several assets. If you apply §5.1 across the inputs, "allow" plus "unknown" gives "allow". But §5.1 combines statements about one asset, so this result turns silence into permission. We bring a rule and test vectors, which is what Thomson asked for. The text needs no new category.
- **For us:** AIPREF is the normative source of `ai_use`. When the text is fixed, our mapping table and our export become stable. It also makes our `inputs` model public with the WG's terms.

## 5. Consequences

- **IPR and licensing:**
  - The [Note Well](https://www.ietf.org/about/note-well/) covers each comment, mail and remark at the mic.
  - Under BCP 78 (RFC 5378), the company gives the IETF Trust a non-exclusive, royalty-free, perpetual right to copy and change the text for IETF work. The company keeps its copyright. Our text is already CC-BY-4.0, so we give away nothing new. Do not paste text from third parties.
  - Under BCP 79 (RFC 8179): if you know of a patent or a patent application that the company owns or controls and that covers the contribution, disclose it on datatracker or do not take part. It is not verified that the company has no patent here.
  - IETF meetings are recorded and published. The W3C CLA does not apply here.
- **If they accept:** cite the vocab revision in the mapping profile (`docs/11` §7). Add two cases. Make export write the per-input preferences for derived items.
- **If they reject:** keep the rule in the kstd profile and write in the mapping "AIPREF does not define derived forms". If the WG adds a new "retain/index" category, add a fourth flag or map it.
- **Effort:**
  - Reading and drafting: about 4 hours.
  - Two cases plus the `inputs` check in `decide.py`: about half a day.
  - IETF 127 in person: one week. The registration fee is not verified.
- **Risks:**
  - The WG is split between publishers and AI firms. Call our default "local", and do not propose it as the default.
  - Do not overclaim. Kütüphane implements the gate, not the propagation.
  - Do not link to the repo before it is public.
  - The §4.3 override means that our export `search=y, ai-use=n` lets an AIPREF reader make an embedding for search.

## 6. Steps for the operator

1. Ask company legal to do the BCP 79 patent check.
2. Make the accounts: a GitHub account with the company in the profile, and a free datatracker account. Subscribe to the list at https://www.ietf.org/mailman/listinfo/ai-control/ with the same email address.
3. Optional, but best: add the two vectors below as kstd cases before you post.
4. By 2026-10-30, post the comment on #246 and give a link to it in #253. The same day, send the mail.
5. Register for IETF 127 before 2026-11-02. When #246/#253 come up, queue at the mic with the Meetecho onsite tool.
6. Follow up: watch #246, #253, #252 and #245, and answer within two working days. Keep #153/#154 until the WG opens them again. Our data point for them: keep "unknown" in storage and apply the default only at the decision.

## 7. Draft text

**GitHub comment (#246; give a link to it in #253):**

> #253 covers one asset → one derived form. Many derived forms (summaries, index entries, training sets) come from **several** assets. If a recipient applies Section 5.1 across those inputs, `ai-use=y` on A plus no statement on B gives "allow". But B's declaring party allowed nothing.
>
> Suggestion, with no new category: a use of a derived form is consistent with preferences only if it is consistent with the preferences of **each** input asset. For each category: if any input disallows → disallow; otherwise, if any input is unknown → unknown; otherwise → allow. "Unknown" then goes to the local default (Section 5).
>
> Test vectors (category `ai-use`):
>
> | Inputs | §5.1 across inputs | Suggested |
> |---|---|---|
> | A `ai-use=y`, B `ai-use=n` | disallow | disallow |
> | A `ai-use=y`, B none | allow | unknown |
> | A `search=y, ai-use=n`; an embedding is made for search, and a generative feature later reads it | — | disallow (the §4.3 override ends outside search) |
>
> This needs a record of the inputs for each derived form. Our data model keeps one. Today our tool makes no embedding unless AI input is allowed.

**Mail to `ai-control@ietf.org`:**

> Subject: Derived forms from several assets (#246, #253)
>
> Hi all,
>
> I am <name>, <company>. We build an on-premises knowledge base that reads usage preferences per file.
>
> #253 keeps preferences with transformed assets. Many derived forms come from several assets. If Section 5.1 is applied across the inputs, "allow" from one asset and "unknown" from another gives "allow", but the second declaring party said nothing.
>
> Proposal: a use of a derived form is consistent only if it is consistent with each input's preferences. Disallow if any input disallows; unknown if any input is unknown; else allow. This could also give the "uses consistent with those preferences" in Section 3.3 (#245).
>
> Test vectors: <link to the #246 comment>. I will be in San Francisco.
>
> <name>