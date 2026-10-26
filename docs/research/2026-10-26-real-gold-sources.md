I checked 16 sources by the GitHub API or the web, with small samples only. The best automatic-gold sources are PEPs, IETF RFCs, KEP files with their production-readiness (PRR) approval files, the MADR-format ADRs in mozilla/fxa, and the `dotnet/docs` pages that Copilot wrote and named people approved. The plan at the end gives about 395 documents.

## 1. Source checks

| Source | Licence | Fetch | kstd fields (reliability) | Count | Trap |
|---|---|---|---|---|---|
| **PEPs** | Each file states its licence. 263 files say "public domain or CC0-1.0-Universal"; the others say only "public domain", which has no SPDX id. | `peps.python.org/api/peps.json`; raw `peps/pep-NNNN.rst`; `api/release-cycle.json` | acceptance and supersession (high); `Superseded-By`/`Replaces`; `Resolution:` link with a date; approver from `PEP-Delegate:`/`BDFL-Delegate:` (about 131 files, by code search), else the Steering Council; validity from `release-cycle.json` (`first_release`, `end_of_life`, `release_manager`); the header has real author e-mails, so personal data = `yes` | 746: 375 Final, 132 Rejected, 74 Withdrawn, 25 Superseded, 11 Accepted; 31 have `Superseded-By`; 260 have `Resolution` | `Superseded-By` can stand on a **Final** PEP (248→249, 333→3333, 409→415). That is a supersession in a different scope, not a withdrawal. Editors change Final PEPs after acceptance: take the git version at the Resolution date. `peps.json` is made by a tool. Future EOL dates are plans with month precision. |
| **KEPs** | Apache-2.0 (repository only) | git tree API, then raw `kep.yaml` and `keps/prod-readiness/<sig>/<n>.yaml` | status, authors, creation-date, latest-milestone (applicability). The `approver` in the PRR file is a real named approval (high). | 710 `kep.yaml`: 325 implemented, 294 implementable, 68 provisional, 11 withdrawn, 6 replaced; 483 PRR files | `reviewers:` and `approvers:` are **assigned** people, not proof of approval. `superseded-by:` is almost always empty; KEP 536 is `replaced` with no successor. The authors edit `status`. |
| **Rust RFCs** | README: "in the process of being licensed" MIT OR Apache-2.0; "some parts" already are | `text/*.md`; PR comments by `rfcbot` | accepted = merged into `text/`. The rfcbot FCP comment lists the team members who checked the box (named approvers, high). | 646 | Licence per file is **`unknown`** for old RFCs. The bot edits the checkbox comment, so it shows the last state. There is almost no supersession data (4 hits). |
| **IETF RFCs** | Text: BCP 78 + IETF Trust Legal Provisions 5.0, not SPDX; code parts BSD-3-Clause | `rfc-editor.org/rfc/rfcN.json`; datatracker `ballotpositiondocevent` API | `obsoletes`/`obsoleted_by`/`updates`, status, `pub_date` (high); IESG ballots: `yes`/`noobj`/`discuss` per person ID, then resolve to a name (high) | about 9,950 | RFC 2616 still shows "DRAFT STANDARD" after six RFCs obsoleted it. RFC 9110 obsoletes only "portions of 7230" (part of the scope). `updates` is not a supersession. Other streams (ISE, IRTF, IAB) have no IESG ballot. |
| **W3C TR** | W3C document licence (`W3C-20150513` and others) | `api.w3.org/specifications/{s}/versions`, `/supersedes` | status per version (Recommendation, Retired, Superseded…), editors, successor links (medium) | 1,721 specs | Supersession links are sparse (`rdf11-mt/supersedes` is empty). The approver is the W3C as a body, not a named person. |
| **ADRs** | fxa: MPL-2.0; ris-search: GPL-3.0 | raw `docs/adr/*.md` | MADR `Status: superseded by [ADR-0017]` plus `Deciders: Les Orchard, …` (high) | fxa 53 (about 51 with Deciders); ris-search 25 | **adr-tools writes `Accepted` by script** (`s|STATUS|Accepted|`), and `adr new -s` writes "Superseded by" into the old file. ris-search history is squashed ("Initial commit" by a machine account). Many 2025–26 ADR repositories were made by a model. |
| **REUSE / SPDX** | per file | REUSE API `api.reuse.software/status/github.com/<o>/<r>`; raw files; `REUSE.toml` | licence per file (high) | reuse-tool 185 files (CC-BY-SA-4.0 docs, GPL-3.0-or-later code, CC0-1.0 config); curl 910 doc `.md` files (`curl`); Linux `Documentation/*.rst`: 2,092 GPL-2.0 and 334 GFDL-1.1-no-invariants-or-later hits | nextcloud/server and syncthing are "non-compliant" now. `REUSE.toml` `[[annotations]]` is a folder-default assertion (docs/19 §3.1). reuse-tool development moved to Codeberg; GitHub is a mirror [INFERENCE from `.forgejo/`]. |
| **PostHog/posthog.com** | `/contents/` MIT; everything else "please do not duplicate" | as for PRs below | licence per folder; assisted | 586 Claude co-authored commits | Some PRs were merged without an approval (PR 21557). |
| **Assisted PRs** | dotnet/docs CC-BY-4.0; sentry-docs FSL-1.1-ALv2; Sentry/PostHog app repos are code | see the extraction steps below | `assisted` + `reviewed_by` (high when the filters pass) | dotnet/docs: 606 merged PRs by Copilot, 998 files with `ai-usage: ai-assisted`, 49 with `ai-usage: ai-generated`; sentry-docs 635; Sentry 2,849, PostHog 5,768 commits | Claude Code adds the trailer by default, and a person can remove it, so no trailer is not proof of `human`. **`ai-usage` is set by Copilot itself** (`.github/copilot-instructions.md`). An approval can apply to an older commit (Sentry PR 121673). Remove bot reviewers (`copilot-pull-request-reviewer[bot]`). An approval covers the diff, not the whole file. |
| **OKF bundles** | Apache-2.0 | git tree; raw `bundles/*` | `generated.by` (`human:jsmith@acme`, `reference_agent/gemini-2.5-flash`), `verified`, `status: deprecated`, `stale_after`, `sources` (medium) | 83 files in 4 bundles | acme_retail is an invented example. Its author and its verifier are the same person; kstd §6 needs a different approver. Supersession is only in prose. |
| **Nanopubs** | `dct:license` per nanopub; often absent | SPARQL `query.knowledgepixels.com/repo/full` | supersession, retraction, signer key, created (high) | 10,423 distinct superseding nanopubs; 95 retractions by another key | They are records, not documents. Many supersessions come in one batch in the same second (a script). |
| **C2PA test files** | CC-BY-SA-4.0 | `c2pa-org/public-testfiles` `legacy/1.4` | signer and ingredients (inputs) | 117 media files | They are test fixtures ("Adobe make_test"). My sample had no `digitalSourceType`. The test certificates are not on a trust list. The `2.2/` folders hold only READMEs. There are no text documents. |
| **Gretel synthetic PII** | Apache-2.0 | HF `gretelai/synthetic_pii_finance_multilingual` | personal data = `synthetic`; origin `model` (Navigator, Mixtral) | 10k–100k full documents | The claim is self-declared. kstd gives `synthetic` only when the issuer is trusted; otherwise it is `unknown`. |
| **Wikipedia, Category:Living people** | CC-BY-SA-4.0 | MediaWiki API | personal data = `yes` (high) | 1,156,395 | Old revisions are also under GFDL. |
| **PyPI attestations (PEP 740)** | per project (`sigstore`: Apache-2.0) | `pypi.org/integrity/<p>/<v>/<file>/provenance` | signer (publisher = GitHub repo + workflow); DSSE statement with a sha256 subject; origin `tool` (high) | not counted | The signature covers the whole sdist; the README is a member file. |
| **HF Croissant / RAI** | per card | `/api/datasets/<id>/croissant` | licence (low) | about 4,296 GitHub hits for `rai:personalSensitiveInformation` | HF Croissant is made by a tool and has no RAI fields (`common-pile/news`: no `license`). RAI fields are free text. **Do not use as gold.** |

CITATION.cff and CODEOWNERS were not sampled. CODEOWNERS names who *may* approve, not who did, so it is not gold.

**Microsoft states** that authors review all AI-generated content before publication ([principles](https://learn.microsoft.com/en-us/principles-for-ai-generated-content)). Thus a Microsoft `ai-generated` file that a named human approved maps to kstd `assisted`, not to `model`. Cases where the two labels disagree are useful test cases.

**Nanopub query example** (tested; it returned rows from 2026-10-25, CC-BY-4.0, same key):
```sparql
PREFIX npx: <http://purl.org/nanopub/x/> PREFIX npa: <http://purl.org/nanopub/admin/>
PREFIX dct: <http://purl.org/dc/terms/>
SELECT DISTINCT ?new ?old (?kn = ?ko AS ?sameKey) ?created ?license WHERE {
 GRAPH npa:graph { ?new npa:hasValidSignatureForPublicKeyHash ?kn .
                   ?old npa:hasValidSignatureForPublicKeyHash ?ko . }
 GRAPH ?g { ?new npx:supersedes ?old . ?new dct:created ?created . }
 OPTIONAL { GRAPH ?g { ?new dct:license ?license } } }
ORDER BY DESC(?created) LIMIT 100
```
For a retraction by another signer, use `npx:retracts` with `FILTER(?kn != ?ko)`. That gives 95 cases.

**How to extract an `assisted` document from a PR:**
1. Find the commits. Use `search/commits` with `q=repo:R "Co-Authored-By: Claude"`, or for Copilot use `search/issues` with `q=repo:R is:pr is:merged author:app/copilot-swe-agent`.
2. Find the PR of each commit: `repos/R/commits/SHA/pulls`.
3. Read `pulls/N/reviews`. Keep a PR only if it has `state=APPROVED`, the reviewer has `user.type=User`, the reviewer is not the PR author, and the review `commit_id` is the last model commit or a later one.
4. Read `pulls/N/files` and keep only files with `status=added` and a `.md` or `.mdx` name.
5. Read the file bytes at `merge_commit_sha`.

Search limits: about 30 requests per minute, and there is also a secondary limit. I hit that limit once in this work.

## 2. Extraction plan (about 395 documents)

| Slice | Docs | Item | Statements (auto-gold) |
|---|---|---|---|
| PEPs | 70: 25 Superseded + successors, 30 Final or Accepted with a Resolution (15 with a Delegate), 10 Withdrawn or Rejected, 5 release PEPs | the file at the Resolution-date commit; licence `CC0-1.0` or `unknown` (public domain only); personal data `yes` | `acceptance accepted` by the Delegate or the Steering Council, dated from the Resolution link; Superseded → `withdrawn` + successor; a Final with Superseded-By → stays accepted, with a successor in another scope; release PEPs: valid time = `first_release`…`end_of_life` |
| IETF RFCs | 50: 20 obsolete chains, 10 partial obsoletes, 10 `updates` only, 10 ISE without a ballot | the RFC text; licence `unknown` (TLP is not SPDX) | `accepted` with the IESG names who voted Yes; `obsoleted_by` → `withdrawn` + successor; valid time from `pub_date` to the successor's `pub_date`; an `updates` link is not a withdrawal |
| KEPs | 35: 6 replaced, 11 withdrawn, 18 implemented with a PRR file | README.md + kep.yaml; Apache-2.0; GitHub handles = personal data `yes` | acceptance from the status; approver from the PRR file only; applicability from the milestone |
| Rust RFCs | 20 | `text/N.md`; licence `unknown` before RFC 2044 (2017), `MIT OR Apache-2.0` after it [INFERENCE] | `accepted`; approvers = the names checked in the rfcbot comment |
| W3C TR | 20 | the TR snapshot; licence by date | status per version; successor link; editors; the approver is the W3C as a body |
| ADRs | 30: 25 fxa, 5 ris-search | the ADR file | fxa: Deciders = approvers; superseded → `withdrawn` + successor. ris-search: the `Accepted` line is written by a script, so gold acceptance = `pending` |
| REUSE / SPDX | 45: reuse-tool 10, Linux docs 15 (including files with no header → `unknown`), curl 10, posthog.com 10 (inside and outside `/contents/`) | the file | licence per file, and folder defaults from `REUSE.toml` |
| Assisted PRs | 50: dotnet/docs 25, sentry-docs 10, posthog.com 10, 5 negatives (no approval, bot reviewer only) | an added doc file at the merge commit | `assisted` + `reviewed_by`; keep the `ai-usage` value as a separate claim |
| OKF | 20 | the concept file | `generated.by` gives `model` or `human`; `deprecated` → `withdrawn`; `stale_after` = review date; self-verification is not acceptance |
| Personal data | 30: Gretel 15, Wikipedia living people 10, Synthea 5 (made locally with a pinned version) | the document | Gretel: `synthetic` from an untrusted issuer, so `unknown`; Wikipedia: `yes`; Synthea: `tool` + software_agent + `synthetic` |
| Trust / signer | 25: PyPI READMEs 10, nanopubs 10 (including cross-key retractions), C2PA 5 | the README, the nanopub, the image | signer identity; a cross-key retraction → a contest mark only; a bad C2PA signature → origin `unknown` |

**Notes for the build:**
- Store the source URL and the commit SHA for each statement.
- Write each statement with the real issuer, for example `issuer: python-steering-council`.

**What I did not verify:**
- the Linux files that have no SPDX header;
- the PyPI attestation count;
- the Rust RFC 2044 cut-off date;
- a real C2PA file that has `digitalSourceType`.

The small samples I used are in `/tmp/rgs`.