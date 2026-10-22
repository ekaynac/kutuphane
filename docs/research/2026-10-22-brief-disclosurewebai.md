# W3C briefs: (a) AI Content Disclosure CG, (b) Web & AI IG

I checked all sources on 2026-10-22. Links that say `[REPO-URL]` need a public repo first. At the moment, `docs/13` and `kstd/tests/decision/cases.yaml` are not public.

---

## (a) W3C AI Content Disclosure CG

### 1. What the group wants

- **Final Report, 2026-10-09:** [AI Content Disclosure for HTML](https://www.w3.org/community/reports/ai-content-disclosure/CG-FINAL-ai-content-disclosure-20261009/).
  - It covers HTML text only. It has three values: `human-only`, `ai-assisted` and `ai-autonomous`.
  - A missing declaration means "unknown". It is not `human-only` (§5.2).
  - `ai-assisted` "does not identify the reviewer, record sign-off or editorial responsibility". The report says that "such records can be maintained separately" (§1.4, §3.2).
  - Feedback: "GitHub Issues are preferred".
- **Charter scope** ([charter.md](https://github.com/w3c-cg/ai-content-disclosure/blob/main/charter.md)):
  - The charter covers an HTML mechanism only.
  - New normative work needs a charter amendment: a 30-day vote with two-thirds approval.
  - A non-normative "Cross-Standard Alignment Guide" is in scope.
- **Open issues.** All are open and have no maintainer reply.
  - [#48](https://github.com/w3c-cg/ai-content-disclosure/issues/48) (2026-09-22) asks for "a non-normative note pointing to XMP with IPTC Digital Source Type, and to C2PA" for PDF, DOCX and EPUB. It also links [publ-a11y#814](https://github.com/w3c-cg/publ-a11y/issues/814).
  - [#49](https://github.com/w3c-cg/ai-content-disclosure/issues/49) asks that consumers do not rank or flag content lower only because it has no declaration.
  - [#47](https://github.com/w3c-cg/ai-content-disclosure/issues/47) asks for an optional contribution type (editing, translation, drafting). It has two supporting comments.
  - [#51](https://github.com/w3c-cg/ai-content-disclosure/issues/51) offers the AI Usage Scale. It asks for comparison cases.
- **Status after the report.**
  - The [publication record](https://github.com/w3c-cg/ai-content-disclosure/blob/main/reports/README.md) says: "Close the Community Group only after the report is listed". It also says: "Handle later substantive changes, including issues #46 to #49, as a new version."
  - On 2026-10-13, at the [Web & AI IG](https://www.w3.org/2026/10/13-webai-minutes.html), Weekly said that the CG "has completed its work… The repository will remain open". Cohen said that `ai-assisted` "is the category most likely to be refined further".
  - The last list message is from 2026-10-05. The last commit is from 2026-10-09.
  - **No next version has a date or a work plan. It is not verified that one will start.**

### 2. What we bring

- The `origin` values `human`, `model` and `unknown` (`docs/11-standard-draft.md` §5, line 82), plus `assisted` (D60).
  - `src/kutuphane/kstd.py:29` does not have `assisted` yet.
- The L0 manifest `kstd.yaml` (`docs/11` §8, `kstd/README.md`). It allows `x-` extension keys (`kstd.py:83`).
- The D60 export rule: do not write an absent value as a negative value.
- The C2PA 2.4 Annex A.9 front-matter embedding. I checked it against the spec.

### 3. Comparison

| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| #48: pointers for non-HTML formats | front-matter keys; `kstd.yaml` sidecar | partial | They ask for pointers, not for a new binding. We have nothing for PDF, DOCX or EPUB. |
| `ai-assisted` = AI involved, a person reviewed it | `assisted` (D60) | partial | Ours is narrower: a named person with editorial responsibility. `assisted` → `ai-assisted` loses no information. The reverse direction does. |
| No declaration = unknown (§5.2, #49) | `unknown` counts as `model` | we differ | This is correct inside the decision, because it fails closed. On export we must omit the key. |
| `ai-model`, `ai-provider`, `ai-prompt-url` | none | we lack | We could add them as `x-` keys. No decision yet. |
| Reviewer record "maintained separately" | `assisted` review record; DSSE statements | match | This is our main input. |
| #47 contribution type; #51 comparison | none | we lack | The planned Beemo items (`docs/13` §5) could give #51 cases later. |
| Element-level granularity | per file only | we lack | — |

### 4. Reasons

- **For them:** #48 is unanswered. Agents and many authors use Markdown and YAML, which have no XMP. In the IG meeting, Chris Needham asked who checks that a declaration is true. A separate, signed review record is a partial answer.
- **For us:** We get a public record that `assisted` maps to `ai-assisted`. We get front-matter names that we do not have to invent. This follows the "profile, not own terms" rule.

### 5. Consequences

- **IPR.**
  - The CLA applies per group, when you join.
  - A comment counts as a "Contribution" only if the group puts it into the Specification. You can also mark it in writing as "not a Contribution".
  - If the group includes it, you give a perpetual, royalty-free copyright license (§2.1). You also give a royalty-free license for any Essential Claims, for the life of the patents (§3.1).
  - You can withdraw a contribution within 45 days (§5). A contribution becomes void if the group does not include it within 150 days.
  - If a Working Group later takes the spec onto the Recommendation track, the royalty-free commitment continues even if you do not join that group (§9.2).
  - The report uses the W3C Software and Document License. Our CC-BY-4.0 text stays ours, because the grant is non-exclusive.
- **If they accept:**
  - Add a versioned mapping table to `docs/11`: `assisted`→`ai-assisted`, `unknown`→no key.
  - Define `human` with their §3.3 boundary (no generative AI). Without that, `human`→`human-only` is not exact.
  - Proposal, needs your decision: export `model`→`ai-autonomous`.
  - Proposal, needs your decision: apply the D60 export rule to `origin` too.
- **If they reject:** The binding stays as kstd profile text. The decision rule and the 33 cases do not change, because origin is not a gate (D1).
- **In both cases:** The report quotes the Commission FAQ: review must be "substantive", not "spelling or grammatical correction". Add this to the `assisted` definition before we skip the AI-generated marking.
- **Effort:** 2–3 h to post, then about 1 h per month. A PR, if they ask for one: about 1 day.
- **Risks:**
  - The CG can close, and the issue can stay without action.
  - Readers can think that `assisted` and `ai-assisted` mean the same. Do not write that they are equal.

### 6. Steps

1. Make the kstd draft public: the repo, or the draft on its own.
2. Sign in at w3.org. Join the CG at https://www.w3.org/groups/cg/ai-content-disclosure/ (this is where you accept the CLA). Link your GitHub account at https://www.w3.org/users/myprofile/connectedaccounts.
3. Post the #48 comment.
4. Optional: post a one-line +1 on #49 that links to #48.
5. Watch the issue. If the editors ask, open a PR against `index.html`, which is the editor's draft.

### 7. Draft: comment on #48

> +1 to the note. One addition for plain-text formats.
>
> Markdown, AsciiDoc, static-site sources and knowledge files read by AI agents often carry a YAML front-matter block and no XMP. C2PA 2.4 Annex A.9 can embed a *signed* manifest there. For an unsigned author declaration, the report's own names work as keys:
>
> ```yaml
> ---
> title: Pump maintenance checklist
> ai-disclosure: ai-assisted
> ai-model: Example Model
> ai-provider: Example Provider
> ai-prompt-url: https://example.com/ai-methodology
> ---
> ```
>
> The report's rules carry over unchanged. The declaration applies to the whole file, like the page-level `<meta>`.
>
> | Front matter | Effective value |
> |---|---|
> | `ai-disclosure: ai-assisted` | `ai-assisted` |
> | `ai-disclosure: AI-Assisted` | `ai-assisted` (ASCII case-insensitive) |
> | no `ai-disclosure` key | unknown (§5.2; see #49) |
> | `ai-disclosure: mixed` or `""` | unknown (no declaration) |
>
> Suggested note text: *"For text formats with YAML front matter (for example Markdown), authors can use the keys `ai-disclosure`, `ai-model`, `ai-provider` and `ai-prompt-url` with the values and parsing rules of this report. The declaration applies to the whole file. For signed declarations, see C2PA 2.4 Annex A.9."*
>
> We use this in an open folder-manifest profile ([REPO-URL]). It has a narrower level: model output that a named person reviewed and took editorial responsibility for. It exports as `ai-assisted`. The review record stays in the manifest, as §1.4 allows. Items with no stated origin export with no key. I can open a PR for a next version.

---

## (b) W3C Web & AI Interest Group

### 1. What the group wants

- **Scope** ([charter](https://www.w3.org/2025/10/webai-ig-charter.html), 2025-11-27 to 2027-11-27):
  - a landscape overview, coordination, gap finding and reports;
  - no Recommendations.
- **Issue [#22](https://github.com/w3c/webai/issues/22)** (chair, 2026-03-03): "Identify missing or evolving specifications required for AI–Web interoperability. Coordinate work with IETF, ISO, Linux Foundation, and others". It has **no comments**.
- **Issue [#19](https://github.com/w3c/webai/issues/19):** "techniques and metadata schemas for detecting, labelling, and validating AI-created content". The comments discuss PROV-O, "bounded authority", policy decisions and digest canonicalization.
- **[The paper](https://www.w3.org/2026/10/w3c-and-state-of-web-in-ai-era.html)** (finalized 2026-10-20):
  - Recommendation 5: "Clarify provenance: separate disclosure, provenance evidence and training preferences, at resource and fragment level."
  - The paper also says: "agents currently prefer text (lightly formatted with markdown) and structured data (json, yaml, csv)".
  - Feedback goes to public-webai@w3.org and to [w3c/webai-roadmap](https://github.com/w3c/webai-roadmap/issues). No deadline.
  - The roadmap issues are mostly a survey of 48 groups. Issue #51 there (2026-10-21) is strongly against AI.
- **[TPAC session](https://www.w3.org/events/meetings/f002d43a-d39c-447b-bf85-e99d87a11cfa/):** 2026-10-29, 09:00–12:30 GMT, Dublin, Room 18.
  - The room has 18 seats. IG participants get priority. There are few seats for observers.
  - Registration is closed and opens again on 26 October.
  - Who can [attend](https://www.w3.org/news-events/tpac/2026/participation/): Member employees, participants of groups that meet at TPAC, and invited guests. **I did not verify that you are eligible.**
- **Can non-members comment? Yes.** The charter says: "The group also welcomes non-Members to make technical contributions… provided they agree to the terms of the W3C Patent Policy". It also says: "The public is invited to review, discuss and contribute". Meetings are not public. A non-member can apply to be an Invited Expert.

### 2. What we bring

- `docs/13-landscape.md`: the groups (§2), the reuse table (§3.1) and the gaps (§3.2).
- 33 decision cases: `kstd/tests/decision/cases.yaml`, run by `kstd/reference/decide.py`.
- The public test set: only planned, 40–60 items (`docs/13` §5). **It is not built yet.**

### 3. Comparison

| Their requirement | Our element | Fit | Note |
|---|---|---|---|
| #22 missing specs; IETF, ISO, LF | `docs/13` §2–§3 | match | It includes AIPREF, JTC 21/SC 42 and MCP (AAIF). |
| Rec. 5: keep disclosure, evidence and preferences apart | `origin` / DSSE statements + `inputs` / `ai_use` | match | — |
| Rec. 5: fragment level | per file | we lack | — |
| #19 labelling and validation; policy decisions | decide.py with reasons; signed statements | partial | No detection. No PROV-O serialization. |
| Test material | 33 cases; test set planned | partial | — |

### 4. Reasons

- **For them:** #22 is empty. Recommendation 5 names the gap that we work on, and we can show three concrete problems.
- **For us:** Other groups review our landscape and correct it. We become visible before TPAC. We get a route to the proposed Digital Policy WG (ODRL) and to the Agent Conformance CG.

### 5. Consequences

- **IPR:**
  - Non-member contributions fall under the W3C Patent Policy.
  - An IG makes no Recommendations, so patent disclosure applies only when you review Recommendation-track specs.
  - Commits to webai-roadmap use the W3C Software and Document License (its `CONTRIBUTING.md`).
  - A comment that only links to our CC-BY-4.0 text transfers nothing more.
- **kstd:**
  - Nothing changes if they ignore the comment.
  - If they take up fragment-level metadata, kstd will need a fragment selector later.
- **Effort:**
  - About 1 h to post.
  - 1–2 h to check `docs/13` for internal content before you publish it. §4–§6 contain our plan and our questions to the groups.
  - TPAC: one morning, only if you are eligible.
- **Risks:**
  - Little response.
  - People can read the comment as vendor promotion. Some readers on the list are hostile to AI.
  - Links that do not work if we post before the repo is public.
  - We must not promise the test set before it exists.

### 6. Steps

1. Publish `docs/13` and the cases, after you check them.
2. Link your GitHub and W3C accounts. The IG README asks for this.
3. Post the #22 comment before 27 October.
4. Post a two-line pointer in #19 that links to #22.
5. Send one short mail to public-webai@w3.org with the link.
6. If you are eligible, register on 26 October and attend on 29 October as an observer. If not, read the minutes.
7. Follow-up:
   - Read the weekly GitHub digest.
   - The next IG call is on 10 November, 16:00 UTC (marked "tentative").
   - Add the test set to #22 when it is public.

### 7. Draft: comment on #22

> **Input for the landscape: rights, origin and use preferences for knowledge files**
>
> We build Kütüphane, an open-source (Apache-2.0) knowledge server. We mapped the groups that answer one question: what may an AI system do with a file, and who says so? Map: [REPO-URL]/docs/13-landscape.md.
>
> - Use preferences: IETF AIPREF, W3C TDMRep, ODRL (proposed Digital Policy WG), CAWG training-mining.
> - Disclosure: AI Content Disclosure CG, IPTC Digital Source Type, C2PA `c2pa.ai-disclosure`.
> - Personal data and legal basis: DPV. Status and trust: VC Bitstring Status List, in-toto/DSSE.
> - Agent channels: MCP (AAIF), Agent Skills.
>
> Three gaps, relevant to recommendation 5 of *W3C and the State of the Web in the AI Era*:
> 1. **Absent is not "no".** AIPREF and the Disclosure CG read a missing value as unknown. Access control must still fail closed. A profile should store three states, deny on absent, and never export absent as "no".
> 2. **Reviewed AI text.** `ai-assisted` says that a review occurred. It does not say who took editorial responsibility (EU AI Act Art. 50(4)). A separate signed review record can carry that.
> 3. **Fragment level.** Our profile works per file. We have no fragment answer yet.
>
> We keep disclosure, evidence and use preferences in separate fields. We publish 33 decision test cases (inputs → permit/deny/escalate with reasons): [REPO-URL]/kstd/tests/decision/cases.yaml. A small public test set with known origin and license is in preparation. We will add it here when it is public. We do not ask anyone to adopt our format. Corrections are welcome.
>
> *AI-assisted text; reviewed and posted by [name], who takes responsibility for it.*