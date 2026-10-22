# Contributions — a guide for the operator

**Status:** 0.1, 2026-10-22 (D60). The facts were checked on 2026-10-22.
**Basis:** the briefs in `docs/research/2026-10-22-brief-*.md`. Each brief has:
- the links and the quotes;
- the full comparison table;
- the ready-to-adapt **draft text** in its §7.

This guide gives the result and the order of work.
**Language:** ASD-STE100 Simplified Technical English.

## 0. Rules for every contribution

1. **Accounts (2026-10-22):** the GitHub account is linked to the W3C account, and a datatracker account exists. The Google CCLA for OKF is still open.
1. **Make the text public first.** Make the repo public (§9), or put the test vectors directly in the post. Do not link to a private repo.
2. **Small and concrete.** Give one problem, one proposal and test vectors (input → expected result). Do not ask a group to adopt kstd. Use the group's own terms, not ours.
3. **Invented examples only.** Never put text, file names or numbers from our corpus in a post.
4. **Disclose AI help.** MCP requires a disclosure line by policy. The AIPREF chair asks for short posts and makes the author responsible. Use this line: *"Drafted with AI assistance; I reviewed it and take responsibility."*
5. **Patents:** the operator confirmed on 2026-10-22 that the company has no patents in this area. The W3C CLA §3.1, IETF BCP 79, the Google CCLA and Apache-2.0 PRs need no further patent disclosure.
6. **Replace the placeholders** `<Company>`, `<Name>`, `[REPO-URL]` and `com.example` with real values.
7. **Do not overclaim (§8).** Kütüphane implements L0 only. The reference rules are in `kstd/reference/`, not in the product.

## 1. Calendar

| Date (2026) | Group | Action | Required? |
|---|---|---|---|
| by **10-26** | W3C Agent Memory CG | Post drafts A, B and C (§2) | yes: the working draft is due 10-30 |
| by **10-26** | W3C ODRL CG | Open the charter issue (§3) | yes: the breakout is on 10-28 |
| by **10-27** | W3C Web & AI IG | Comment on #22 (§7) | optional |
| **10-28** 11:45–12:45 GMT | ODRL | TPAC breakout "Proposed Digital Policy WG Charter" | attend, or ask the chair to mention our issue |
| **10-29** 09:00 GMT | Web & AI IG | TPAC session (18 seats; observers only if you are eligible) | optional |
| by **10-30** | IETF AIPREF | Comment on #246, link it in #253, mail to the list (§4) | yes: before IETF 127 |
| **11-02** | IETF 127 | Registration cut-off | only if you go to San Francisco |
| **11-02** 12:00 UTC | ODRL CG | CG call: ask for an agenda item | recommended |
| **11-16 / 11-19** | AIPREF | Sessions at IETF 127 (times not final) | in person or by Meetecho |
| November | DPV, OKF, in-toto, MCP, AI Content Disclosure | Post the comments (§5–§7) | no deadline |
| Q1 2027 | ODRL 3.0 WG, Agent Conformance CG | Our cases in their formats | — |

## 2. W3C AI Agent Memory Interoperability CG — **first priority**

- **What they want:**
  - The chair collects a **use-case catalogue** in this shape: "setting, actors, what moves or must remain, and what has to be verified". The working draft is due on 2026-10-30, so post before 10-26.
  - Entry 4 (Hinkle) asks for **"imported memory is evidence, not an automatic grant of authority"** as *testable acceptance criteria*. Nobody has given test vectors for it yet.
  - Entry 5 (Jeongho Song) asks whether a `derived-from` field lets an erasure follow derived notes.
  - A thread proposes six citation fields: IRI, unit id, digest, licence, retrieval time and source version.
- **What we bring:**
  - rules 4, 5 and 8 with their cases (`kstd/tests/decision/cases.yaml`);
  - the **erasure reach** cases (`kstd/tests/erasure/cases.yaml`, new; they match draft B exactly);
  - the licence rule "unknown gives nothing".
- **Fit:**
  - Authority and erasure reach: they match.
  - Citation: partial, because we have no IRI, retrieval time or source version.
  - "No restore after erasure" (their point 5): we lack it.
- **Why:**
  - For them: we give the test vectors that they ask for.
  - For us: rules 4, 5 and 8 and `inputs` get outside review before their conformance pack starts.
- **Consequences:**
  - IPR: the W3C CLA gives a royalty-free copyright licence. The patent commitment covers only the text that goes into a Report. You can withdraw a contribution within 45 days.
  - If they accept: `inputs` maps to their `derived-from`, and the citation fields go into the item.
  - If they reject: nothing in kstd changes.
  - Effort: 3–4 h to post, then about 1 h per week.
  - Risks: a small group, and the chair is the only author of the referenced draft. Write in their words, so that the post does not look like promotion.
- **Steps:**
  1. Join the group at `w3.org/community/ai-agent-memory-interop/join` with the company affiliation.
  2. Post **A** as a reply to message 0022, **B** as a reply to 0029 and **C** as a reply to 0008.
  3. After 10-30, check the working draft and correct our text.
  4. Drafts: `docs/research/2026-10-22-brief-memorycg.md` §7.

## 3. W3C ODRL CG → proposed Digital Policy WG (ODRL 3.0)

- **What they want:**
  - The CG approved the WG charter draft on 2026-10-05. It plans a **Conformance Evaluation** deliverable (Q2 2028), but no draft exists yet.
  - The July workshop asked that "different implementations reach compatible conclusions" and for "test cases with inputs and expected outputs".
  - The current evaluation reports give results **per rule**, not **per request**.
  - ODRL 2.2 §3.2 says "MUST stop processing" and defines no result for that case.
- **What we bring:**
  - the decision rule with three results (deny > escalate > permit);
  - fail-closed handling of unknown terms;
  - reason codes;
  - 38 cases, two of them converted to their odrl-force Turtle format (in the brief).
- **Fit:**
  - Deterministic tests and multi-level conformance: they match.
  - A third result and a result per request: we differ. This is our main input.
  - We have no ODRL processor.
- **Why:** this is the only group that will write a policy-evaluation conformance suite. Our input can still change its scope.
- **Consequences:**
  - The CLA applies now. The WG (2027) needs W3C Membership or Invited Expert status.
  - If they accept: we use their name for `escalate` and their reason-code registry.
  - If they reject: we publish a crosswalk (escalate ↔ XACML `Indeterminate` ↔ AuthZEN `decision:false` + context).
  - Kütüphane does not change in either case.
  - Effort: about 2 h for the issue, and 1–2 days to convert the cases.
  - Risk: the charter is already approved, so a late scope change can meet resistance. Explain that `escalate` is an evaluation result, not enforcement.
- **Steps:**
  1. Join the ODRL CG.
  2. Open the charter issue on `w3c/odrl` before 10-26 and ask for the `W3C Charter` label.
  3. On 10-28, attend the breakout, or ask chair Víctor Rodríguez-Doncel to mention the issue.
  4. Mail `public-odrl@w3.org` for the 11-02 call.
  5. When the repo is public, ask odrl-force whether they accept a result per request, then send the PR.
  6. Drafts: `brief-odrl.md` §7.

## 4. IETF AIPREF (`ai-control`)

- **What they want:**
  - #246 says that "an index is a black hole for preferences". PR #253 keeps preferences with **one** transformed asset.
  - The editor (Thomson) wrote on 2026-10-22 that the many-to-one case is "nebulous": "If you have something better to suggest, please do so".
  - The defaults questions (#153/#154) are deferred.
- **What we bring:** a derived item is checked against **each** input. This is now executable: `kstd/reference/decide.py`, cases "an embedding or summary of an input that reserves AI input…" and "…input is not known…".
- **Fit:**
  - "Absent = unknown": it matches our three-state storage (D60).
  - Most-restrictive merge: partial.
  - `search` overrides the other categories (§4.3) in AIPREF, but our flags are independent. We differ: with `search=y, ai-use=n`, an AIPREF reader can make an embedding for search, and Kütüphane does not.
- **Why:**
  - For them: the editor asked for exactly this, and our text gives a concrete rule with vectors.
  - For us: `ai_use` maps to the normative vocabulary.
- **Consequences:**
  - IPR: the Note Well applies. BCP 78 gives the IETF Trust a right to use the text, and the company keeps the copyright. BCP 79 makes you disclose any company patent that you know of.
  - If they accept: we cite the vocab revision in the mapping.
  - If they reject: we write "AIPREF does not define derived forms" in the mapping.
  - Effort: about 4 h. IETF 127 in person takes one week.
  - Risk: the WG is split between publishers and AI firms. Call our default "local". Do not propose it as everyone's default.
- **Steps:**
  1. Do the patent check.
  2. The datatracker account exists (2026-10-22). Subscribe to `ai-control` with the same e-mail.
  3. Post the #246 comment and link it in #253.
  4. Send the mail by 10-30.
  5. Drafts: `brief-aipref.md` §7.

## 5. W3C DPV CG

- **What they want:**
  - #221 asks for a flat subset without RDF, "much like SPDX". The use case there is ours: *"this document contains that kind of PII, can't be used for AI training"*.
  - A member will add a CSV/JSON example by 2026-11-30.
  - New concepts are filed with the `[NEW]:` template and decided in the Wednesday calls.
- **Correction to our plan:**
  - `dpv:SyntheticData` already exists.
  - "Presence unknown" is already possible as `hasPersonalData UnknownApplicability`.
  - So we file **no** new concept. We file only a usage note: `SyntheticData` does not by itself mean "no personal data".
- **What we bring:** L0 with DPV legal-basis codes (D60, now implemented: `kstd.py` `LEGAL_BASES`, `export --legal-basis eu-gdpr:A6-1-b`), a validator and test cases. We are a real adopter of the flat form.
- **Fit:**
  - The flat use and the legal-basis codes: they match.
  - `synthetic`: we differ. Ours means "no legal basis is needed, from a trusted issuer only", and DPV does not say this.
  - We do not pin the vocabulary version yet (#492).
- **Consequences:**
  - The CLA applies. Examples are informative, so the patent risk is very low.
  - If they accept: we validate against their published, versioned list, not a hard-coded set.
  - If they reject: we pin `https://w3id.org/dpv/2.3/legal/eu/gdpr`.
  - Effort: about 5 h, plus 1–2 calls.
- **Steps:**
  1. Join the group and link your GitHub account.
  2. Comment on #221.
  3. Ask the chairs for an AOB item in a Wednesday call.
  4. Then file the usage note.
  5. Drafts: `brief-dpv.md` §7.

## 6. Open Knowledge Format (OKF, Google)

- **What they want:**
  - The spec is "minimally opinionated": only optional keys, and consumers **must not reject** a concept with unknown or missing fields.
  - CONTRIBUTING says: open an issue before a PR.
  - kc#52 asks for an SPDX `license`, but it sits in a **frozen** copy, so open a new issue in `open-knowledge-format`.
  - #15 asks that imported trust is "reportable, not inherited".
  - Maintainers have been quiet since 2026-08.
- **What we bring:**
  - a `rights` family (SPDX license, `ai_use` with three states, `personal_data`, DPV `legal_basis`) and `sources[].digest`;
  - the rule that **restrictions are inherited** even when trust is not.
- **Fit:**
  - License and "not inherited": they match.
  - Our manifest is strict and their frontmatter is tolerant: we differ. The draft respects their rule: an invalid value counts as "not stated".
- **Why:**
  - OKF has our L0 shape. If OKF takes these names, a plain bundle carries kstd rights without `kstd.yaml`.
- **Consequences:**
  - A **Google CCLA** is needed, and issue text also counts as a contribution. One company signer does this; it takes 1–3 days.
  - If they accept: Kütüphane reads `rights` from frontmatter, and the stricter value wins against `kstd.yaml`.
  - If they do not reply in 6 weeks: we keep an extension key with the same names.
  - Risks: Google controls the format, and more than 20 proposals compete.
- **Steps:**
  1. Get the CCLA signed.
  2. Post the #15 comment first; it is cheap.
  3. Then open the new issue and link kc#52, #15 and #32.
  4. Drafts: `brief-okf.md` §7.

## 7. Smaller items (November, no deadline)

| Group | They want | We bring | Consequence | Draft |
|---|---|---|---|---|
| **in-toto #67** (CNCF) | Revocation without revoking the key. The 2026-10-02 comment separates "authentic" from "authorized". The spec says that an ignored attestation must never turn deny into allow. | Authority comes from verifier policy (rule 4). An unauthorized revocation is only a notice (rule 8). Freshness instead of "deny if revoked" (rule 6). Six vectors. | A comment needs no CLA. A PR needs a DCO sign-off (Apache-2.0). If they accept, our field names become lowerCamelCase in the in-toto binding. | `brief-intotomcp.md` §(a)7 |
| **MCP SEP-1913** → Tool Annotations IG | Open questions: "enforcement vs. advisory", declassification, taint. Absence = "no claim made". | Kütüphane decides on the server before delivery (`server.py`, `withheld`), and rule 4 handles declassification. | No CLA. The AI disclosure line is **required**. Use our own reverse-DNS key, never `io.modelcontextprotocol/`. If they accept, Kütüphane writes `_meta` (1–2 days). | `brief-intotomcp.md` §(b)7 |
| **W3C AI Content Disclosure CG** #48 | Pointers for formats that are not HTML. The CG finished its report, and a next version is not planned. | YAML front-matter keys with the report's values. Our `assisted` → their `ai-assisted`, with a separate review record. | The CLA applies. A low response is likely. | `brief-disclosurewebai.md` §(a)7 |
| **W3C Web & AI IG** #22 | "Identify missing or evolving specifications". The issue has no comments yet. | `docs/13` and the three gaps: absent ≠ no, reviewed AI text, fragment level. | Non-members can comment under the Patent Policy. Do not promise the test set before it exists. | `brief-disclosurewebai.md` §(b)7 |
| **W3C Agent Conformance CG** | Runnable suites and versioned fixtures | `cases.yaml` as a fixture set | Low priority; its activity is not verified | `brief-odrl.md` §6.7 |

## 8. What we have and what we do not have (do not overclaim)

**Done for these contributions (D60, PR "feat(kstd): D60 fields"):**
- `assisted` + `reviewed_by`;
- `synthetic`;
- three-state `ai_use`;
- DPV legal-basis codes on export;
- `ai_generated` / `reviewed` in signed packages;
- `use_record`;
- input rights in the reference rule;
- erasure reach cases.

The reference suite has 38 decision cases and 4 erasure cases.

**Not in Kütüphane (spec or reference rule only):**
- the decision rule with `escalate`, trust, status and acceptance (Kütüphane is L0);
- the propagation of rights through `inputs`;
- the erasure operation;
- an ODRL processor;
- the MCP `_meta` emitter;
- metadata for fragments of a file (only per file);
- the public test set (planned, not built).

**For your decision:**
1. On export to disclosure keys:
   - `model` → `ai-autonomous`;
   - `unknown` → no key.

   Today the signed package lists `unknown` together with `model` as `ai_generated`, because it fails closed.

## 9. Before the repo becomes public (audit of 2026-10-22)

**Checks:** all 112 commits and all 152 file paths in the history were checked. The scripts print only paths and counts.

- **Secrets:** no secret value is in any commit. The values checked come from `.env`, `bridge.env`, `core.key` and the labelling token. The matches were only config names (`GATEWAY_AUTH_MODE`) and the fake keys in `test_secret_scan.py`.
- **Corpus text:** the corpus has 163 files. No run of 12 or more words from any corpus file is in any commit.
- **Corpus file names:**
  - `docs/00-kickoff-brief.md` names 3 of your private documents (`…knowledge-layer-backlog`, `…saga-and-kobra-doctrine`, `…llmdap-mcp-doctrine`).
  - The old `KICKOFF-BRIEF.md` is still in the history.
  - **Operator decision (2026-10-22): these names may be public.** No history rewrite.
- **Read once before you publish:**
  - `docs/00`, `docs/01` and `docs/08`, which are internal decisions in Turkish;
  - the raw review files in `docs/research/`;
  - `docs/13` §4–§6 and this file, which contain our plan and our questions to the groups.

  None of them has secrets or corpus text.
