# Labelling v5 — auto set results, and open points in draft 0.2

**Status:** RESULTS, 2026-10-27. Branch `feat/labelling-v5-eval`.
**Language:** ASD-STE100 Simplified Technical English.
**Basis:** `docs/20` (plan, D67), `docs/11` (draft 0.2, D68), `research/labelling-v5/auto/{docs,rights}.README.md`, `research/labelling-v5/scenario/core.README.md`, the research questions Q1–Q27 (`docs/research/2026-10-22-labelset-public.md` §4).

## 1. What we ran

- **Set:** the auto set only: 200 cases (`auto/docs` 115, `auto/rights` 85). The human proposals are frozen and did not change (`rules-v5.0`, `llm-v5.0`, `baseline-v5.1`).
- **Proposers (version 5.2):**
  - `rules-v5.2` (`experiments/labeling_v5/propose.py`): a source "Rejected" (also "REJECTED", "declined", "reddedildi") now gives `rejected`, not `withdrawn` (D68). It also gives `normative: history`.
  - `baseline-v5.2`: the same rules without the file bytes (path and `evidence` only).
  - `llm-v5.2` (`llm_propose.py`): Qwen3.8-27B-NVFP4 on the LLMDAP `chat` route, temperature 0. The prompt now has the acceptance choice `rejected`, defined as "a decision not to accept it, so it was never accepted".
- **Scorer:** `experiments/labeling_v5/eval_auto.py`. It reads the gold only after the proposers ran. The proposers never import it.
- **Before numbers:** the v5.1 files of 2026-10-26 20:12 came from the first `auto/docs` build. Their case bytes are not the current ones (for example, the 12 decision-time PEP copies said `Accepted` then). For a clean comparison, we ran the v5.1 code again on the current cases: the rules on all 200 cases, Qwen on the 19 cases that the change can affect.
- **Run facts:**
  - rules and baseline: 200 cases in about 3 s each.
  - Qwen: 200/200 valid proposals. One case (`auto-rfc-4214`) failed the schema check two times (`normative` missing) and passed on the third run. The median time was 22.7 s per case (maximum 56.4 s). The GPU was shared with the labelling page. The v5.1 prompt on the same day took about 21 s per case, so the prompt change did not cause the slower time (on 2026-10-26 the mean was 8.6 s).

Run it again:

```
python -I experiments/labeling_v5/propose.py research/labelling-v5 --set auto
python -I experiments/labeling_v5/propose.py research/labelling-v5 --set auto --baseline
KUTUPHANE_LLMDAP_URL=… KUTUPHANE_LLMDAP_KEY=… python -I experiments/labeling_v5/llm_propose.py research/labelling-v5 --set auto
python experiments/labeling_v5/eval_auto.py research/labelling-v5 --llm-version llm-v5.2 --details
```

## 2. How we score

- Each cell is **correct / abstained / wrong**. Accuracy = correct ÷ n. "Abstained" means no proposal: the rules give no value, or Qwen says `unknown`. For the licence, `unknown` is a value, not an abstention.
- **Acceptance:** the kstd value of the current source declaration (`gold.acceptance`).
  - A case with no declared status (5 ADRs) expects no claim. No claim and `pending` (the kstd default) are both correct.
  - Nanopubs: a retraction or a supersession by the same key expects `withdrawn`. A retraction by another key is only a contest mark (docs/11 §4 rule 8), so it expects no claim.
  - The 12 decision-time PEPs are scored separately (§3.2).
- **Dangerous errors:**
  - **false `accepted`:** the proposal is `accepted`, and the expected value is not;
  - **missed `withdrawn`/`rejected`:** the expected value is `withdrawn` or `rejected`, and the proposal is neither (52 cases);
  - **missed successor:** the gold has `superseded_by`, and the proposal names no successor (42 cases). A second count, "successor not flagged", counts the cases where the proposal does not even give `withdrawn` or `rejected` (39 cases; the 3 `other-scope` PEPs stay accepted, so they are not in this count);
  - **withdrawn by another key:** `withdrawn` or `rejected` for a nanopub that only another key retracted (5 cases);
  - **false licence:** a licence other than `unknown` that is not the gold licence;
  - **false `assisted`:** `assisted` where the gold origin is `model` (30 cases).
- **Licence values:** deprecated GNU ids are compared in their current form (`GPL-2.0` = `GPL-2.0-only`, `GPL-2.0+` = `GPL-2.0-or-later`), as the gold does. Outer parentheses do not count.
- **Fields that a proposer does not have:** Qwen has no licence, successor, contest or validity field. The rules and the baseline have no successor field. These cells show "abstained" only.

## 3. Results

### 3.1 Acceptance

| Source | n | rules | baseline | Qwen |
|---|---|---|---|---|
| PEP (without the 12 decision-time PEPs) | 28 | 28 / 0 / 0 | 0 / 28 / 0 | 25 / 0 / 3 |
| RFC | 30 | 0 / 30 / 0 | 0 / 30 / 0 | 25 / 0 / 5 |
| KEP | 25 | 11 / 14 / 0 | 0 / 25 / 0 | 25 / 0 / 0 |
| ADR | 20 | 18 / 2 / 0 | 5 / 15 / 0 | 15 / 0 / 5 |
| nanopub | 15 | 5 / 10 / 0 | 5 / 10 / 0 | 9 / 1 / 5 |
| **Total** | **118** | **62 / 56 / 0 (53 %)** | **10 / 108 / 0 (8 %)** | **99 / 1 / 18 (84 %)** |

The baseline is correct only where no claim is correct (ADRs with no status, nanopubs retracted by another key).

**The D68 change, before and after** (v5.1 and v5.2 code on the same, current cases):

| Cases | Gold | rules v5.1 | rules v5.2 | Qwen v5.1 | Qwen v5.2 |
|---|---|---|---|---|---|
| PEP 601, 722, 736; ADR 0038 | `rejected` | `withdrawn` ×4 | **`rejected` ×4** | `withdrawn` ×4 | **`rejected` ×4** |
| PEP 426, 501, 759 (author-withdrawn, `prior_acceptance: false`) | `withdrawn` | `withdrawn` ×3 | `withdrawn` ×3 | `withdrawn` ×3 | `withdrawn` ×3 |
| 12 decision-time PEPs (text: `Draft`) | text: `pending` | `pending` ×12 | `pending` ×12 | `pending` ×12 | `pending` ×12 |

- **Rules:** the 4 values above are the only differences between v5.1 and v5.2 on all 200 cases. PEP acceptance goes from 25/28 to 28/28, ADR from 17/20 to 18/20.
- **Qwen:** the `rejected` choice did not move the author-withdrawn drafts to `rejected`. On all 200 cases, Qwen v5.2 gives `rejected` only for the 4 rejected cases.

### 3.2 The 12 decision-time PEPs

PEPs 649, 688, 700, 701, 703, 714, 735, 749, 752, 770, 772 and 794. The copy is the text at the last revision before the decision (`artifact_status: Draft`); the current state is `accepted`.

| Score | n | rules | baseline | Qwen |
|---|---|---|---|---|
| vs `artifact_status` (Draft → `pending`) | 12 | 12 / 0 / 0 | 0 / 12 / 0 | 12 / 0 / 0 |
| vs current `acceptance` (`accepted`) | 12 | 0 / 0 / 12 | 0 / 12 / 0 | 0 / 0 / 12 |

Both proposers answer for the text that they see, and neither one uses outside memory of the decision. That is the correct behavior for a proposer. The current state must come from a status source (a `status` statement or the PEP index), not from the text.

### 3.3 Licence, origin, personal data, contest mark, validity

| Field: source | n | rules | baseline | Qwen |
|---|---|---|---|---|
| licence: PEP | 40 | 2 / 0 / 38 | 0 / 40 / 0 | no field |
| licence: RFC | 30 | 1 / 0 / 29 | 0 / 30 / 0 | no field |
| licence: KEP | 25 | 25 / 0 / 0 | 0 / 25 / 0 | no field |
| licence: ADR | 20 | 20 / 0 / 0 | 0 / 20 / 0 | no field |
| licence: REUSE/SPDX | 30 | 17 / 3 / 10 | 0 / 30 / 0 | no field |
| licence: nanopub | 15 | 1 / 1 / 13 | 0 / 15 / 0 | no field |
| **licence total** | **160** | **66 / 4 / 90 (41 %)** | 0 / 160 / 0 | — |
| origin: assisted-docs PRs (gold `model`) | 25 | 10 / 13 / 2 | 10 / 13 / 2 | 0 / 0 / 25 |
| origin: radar briefs (gold `model`) | 5 | 5 / 0 / 0 | 0 / 5 / 0 | 0 / 0 / 5 |
| personal data: PEP | 40 | 36 / 3 / 1 | 0 / 40 / 0 | 17 / 0 / 23 |
| personal data: RFC | 30 | 28 / 0 / 2 | 0 / 30 / 0 | 4 / 0 / 26 |
| personal data: KEP | 25 | 2 / 23 / 0 | 0 / 25 / 0 | 0 / 0 / 25 |
| personal data: ADR | 20 | 1 / 19 / 0 | 0 / 20 / 0 | 4 / 0 / 16 |
| personal data: TAB court texts | 10 | 0 / 10 / 0 | 0 / 10 / 0 | 10 / 0 / 0 |
| **personal data total** | **125** | **67 / 55 / 3 (54 %)** | 0 / 125 / 0 | **35 / 0 / 90 (28 %)** |
| contest mark found (nanopub, another key) | 5 | 0 / 5 / 0 | 0 / 5 / 0 | no field |
| `valid_to` (release PEPs) | 5 | 0 / 5 / 0 | 0 / 5 / 0 | no field |

- **Licence:** 88 of the 90 rule errors are `unknown` where the item declares a licence: the PEP Copyright section (public domain or CC0-1.0), the RFC copyright notice, the nanopub `dct:license`, and 8 REUSE files whose licence is in a sidecar or `REUSE.toml`. These errors are safe: `unknown` gives no permission. The 2 other errors are false licences (§3.4).
- **Personal data:** Qwen says `no` for 90 of the 115 documents. The gold says `yes`, because the Author headers name real persons and often give e-mail addresses. The rules find the e-mail addresses. 3 rule errors are a false `synthetic`: the word pattern matched "dummy data" (PEP 426) and "dummy change_cipher_spec record" (RFC 8446, 9846).

### 3.4 Dangerous errors

| Dangerous error | Cases | rules | baseline | Qwen |
|---|---|---|---|---|
| false `accepted` | 118 | **0** | **0** | **11** |
| missed `withdrawn`/`rejected` | 52 | 25 | 52 | **6** |
| missed successor (no successor named) | 42 | 42 | 42 | 42 |
| successor not flagged (not even `withdrawn`) | 39 | 22 | 39 | **6** |
| withdrawn by another key | 5 | 0 | 0 | **4** |
| false licence | 160 | 2 | 0 | no field |
| false `assisted` | 30 | 2 | 2 | **25** |

- **Qwen, false `accepted` (11):**
  - 5 ADRs with no status line (0000, 0008, 0009, 0016, 0025). Qwen reads the decision section as an acceptance. For example, ADR 0008: "ADR 'Decision Outcome' establishes a binding technical standard for the project."
  - 5 obsoleted RFCs (4330, 7158, 7230, 7234, 8446). `rfcN.json` lists `obsoleted_by`, and that file is in the prompt, but Qwen follows "Proposed Standard". RFC 7230 is the partial case.
  - 1 nanopub that another key retracted (`auto-np-ratscpscqneypdgz`).
- **Qwen, withdrawn by another key (4 of 5):** for example `auto-np-ramlct-vjkaz_1zm`: "The target nanopublication is explicitly retracted by the later one." Qwen does not compare the two signing keys, which are in `evidence`.
- **Qwen, false `assisted` (25 of 25):** for example dotnet PR 49512: "Copilot bot authored; … made substantive edits and reviews." An approval or a co-author trailer is not proof of a review in substance.
- **Qwen, radar briefs (`tool` ×5):** "Generated by deterministic rules in src/radar/reports/brief.py". The inputs are model output, so the input rule gives `model` (docs/17 §4; G24, G25).
- **Rules, missed `withdrawn` (25):** 14 RFCs, 10 nanopubs and KEP 5339. The rules read only a `status:` line. They do not read `obsoleted_by` in `rfcN.json`, or the nanopub `target`/`later` evidence. In KEP 5339 the first `status`-like line that the rules find is not the KEP status.
- **Rules, false licence (2):** `src/reuse/licenses.py` has two SPDX header lines, and the rules read only the first (`Apache-2.0`; gold `Apache-2.0 AND GPL-3.0-or-later`). A jinja2 template has an SPDX example line with a template variable, and the rules propose `{{`.
- **Rules, false `assisted` (2):** dotnet PRs 55749 and 56390. Each one has one non-trivial remark by a reviewer, and the rules call that a substantive review.

## 4. Findings by research question

| Q | Finding |
|---|---|
| Q13 (superseded vs retracted: different states?) | `rejected` is now a separate value, and both proposers find it: 4/4 after the change, 0/4 before. Neither proposer gives the reason (`superseded`, `obsoleted`, `replaced`, `withdrawn`) or the successor: 42/42 successors are missed. A successor relation needs its own field and an adapter per source. |
| Q12 (a revocation by another signer: only a notice?) | Qwen makes 4 of 5 retractions by another key into `withdrawn`. Rule 8 forbids this. A model proposer must not decide trust; the key comparison belongs to code. |
| Q16 (false authority signals) | Qwen's 11 false `accepted` come from two signals: a template heading ("Decision Outcome") and a document class ("Proposed Standard"). The rules make no false `accepted`, because they need an explicit status word. |
| Q17 (scope of a successor) | PEPs 248, 333 and 409 are `Final` with `Superseded-By` (`other-scope`). Qwen says `withdrawn` for all 3; the rules say `accepted`. RFC 7230 (partial obsoletion) gets `accepted` from Qwen. The partial case needs the rule in §6.3. |
| Q21 (the exact text served) | For the 12 decision-time PEPs both proposers answer for the served text (`pending`), not for the current state (`accepted`). An answer must name the text version and get the current state from a status source. |
| Q4 (assisted vs model) | Qwen gives `assisted` for 25/25 model PRs. The rules give it for 2/25. The PR record alone cannot show a review in substance; the human set must judge it. |
| Q6, Q24 (tool output; machine signals) | Qwen calls the radar briefs `tool` (5/5) because a script assembled them. The rules get `model` (5/5) from the record field `model`. The origin of a tool output must follow its inputs (docs/17 §4). |
| Q10 (collection licence vs item licence) | The rules never use a repository licence: all 45 KEP and ADR files are correctly `unknown`. But the rules do not read item-level declarations other than SPDX and front matter, so 88 items get a safe `unknown`. |
| Q7, Q24 (personal data from machine signals) | Qwen does not count author names and e-mail addresses in a document header as personal data (90 `no`). The rules find e-mail addresses, but a word list for "synthetic" gives 3 false `synthetic`. The trust rule for `synthetic` (docs/11 §5) makes these errors safe in a decision. |
| Q15 (validity vs other dates) | No proposer gives `valid_to` for the 5 release PEPs. The dates are in `release-cycle.json`, which is a reference only, not a file copy. |

**Summary:** Qwen is right more often on acceptance (84 % vs 53 %), but it makes the dangerous errors: 11 false `accepted`, 4 withdrawals by another key, 25 false `assisted`. The rules abstain where they do not know, and they make 0 false `accepted`. For search and model answers (D67), a false `accepted` and a false `assisted` are the errors that give authority to the wrong text. A proposal from Qwen therefore needs a person or a code check before it counts.

## 5. Open points for the proposers

These are not fixed in v5.2. They are for v5.3, after the human set:

1. **Successor field:** neither proposer gives `superseded_by`. Sources declare it in `Superseded-By:` (PEP), `obsoleted_by` (`rfcN.json`), `replaces` in the successor (KEP), "superseded by [ADR-…]" (ADR), and `later` + same key (nanopub).
2. **RFC and KEP status:** the rules do not read `rfcN.json` (`status`, `obsoleted_by`) and do not know the KEP words `implemented` and `implementable`.
3. **Nanopub evidence:** the rules expect `retracted_by` records with `same_key`; the auto set gives `target`, `later` and two key hashes. The rules therefore find no contest mark (0/5).
4. **Item licence declarations:** the PEP Copyright section, the RFC notices and `dct:license` are item-level declarations (`auto/docs` README §3). The rules do not read them.
5. **SPDX:** read all header lines (`AND`), skip SPDX lines inside templates, and write current ids (`GPL-2.0-only`, not `GPL-2.0`).
6. **"Substantive" review in the rules:** one non-trivial remark is not enough. The rule must stay `low` confidence, or it must need more than one remark on the content.
7. **Qwen prompt:** state that a document class ("Proposed Standard") is not an acceptance, that an ADR without a status line declares no state, and that a retraction counts only from the same key. Measure again after the change.
8. **Gold definition of personal data:** decide whether public author attribution in a standards document is "personal data: yes" for kstd. Qwen and the gold disagree on 90 cases.

## 6. Open points in draft 0.2

These are proposals only. `docs/11` and `kstd/reference/decide.py` do not change: the operator answers the scenario forms first (`research/labelling-v5/scenario/core/sc-core-NN.desired.md`). Each point gives the proposed rule, the reason, and the scenario that tests it. The points come from `scenario/core.README.md` ("Points that the specification may not decide") and from the auto set. **Exception (2026-10-27):** §6.5 and §6.6 close known gaps of `decide.py`; they are now in `docs/11` §5, `decide.py` and the conformance cases (`docs/24` §19).

### 6.1 Statement kinds: `handling` and `tag`

- **Gap:** docs/11 §2 has a closed list of statement kinds. `handling` is not in the list, but §5 defines the handling property, and `decide.py` and `kstd/tests/decision/cases.yaml` use `kind: handling`. The scenarios also use `kind: tag` (docs/19 §5.1).
- **Proposal:**
  1. Add `handling` to the closed list. Body: `export`, `route`. Effect: rule 4 (a tightening applies from any issuer; a loosening only from a trusted issuer).
  2. Do not add a general `tag` kind. A **discovery tag** stays outside the core (a profile). It cannot change a decision ("A field outside this standard MUST NOT change a decision").
  3. An **access tag** is a governed facet, the same as handling (docs/19 §5.1). Put it in the `handling` body as `access: [concept]`. The same rule 4 applies: adding a restrictive tag is a tightening; a removal is a loosening.
  4. A statement with `state: proposed` (an agent proposal) has no effect until a trusted issuer confirms it.
- **Why:** one kind and one rule for every governed facet. The engine needs no second path for tags.
- **Scenario:** sc-core-04. Base: the tagger agent proposes to remove `customer:acme`; the tag stays. Consequential: Selin (trusted for the `customer` namespace) issues the removal; it applies. Irrelevant: an added discovery tag `topic:rollout` changes nothing.

### 6.2 Key rotation

- **Gap:** no statement kind carries a key rotation. sc-core-17 puts it in a `status` statement (`body.key_rotation`: old key, new key, effective time, retirement time of the old key).
- **Proposal:**
  1. Keep the rotation in the issuer's `status` stream. The stream is signed and sequenced, and it travels in packages (L3), so air-gapped nodes get it.
  2. A rotation is valid only when the **old** key signs it, and the old key is in `known_keys` and not retired at `effective`. A second signature by the new key is recommended (it shows that the issuer holds the new key).
  3. A valid rotation gives the new key the **same** trust entries as the old key: the same kinds × scopes × actions and the same expiry. It never adds a kind, a scope or an action.
  4. A rotation that only the new key signs gives no trust. It is a claim from an unknown key: a visible notice, as for an untrusted withdrawal (rule 8).
  5. After the old key's retirement time, statements signed with the old key count as from an unknown key.
- **Why:** this follows the TUF root rotation: a new root file must carry signatures of the old root keys (TUF also asks for the new keys). Trust then never comes from the new key alone. The auto set has the real case: two nanopub retractions by another key that claims the same ORCID (`auto/rights` README, "possible key rotation"). Without a signed rotation, the gold is a contest mark only.
- **Scenario:** sc-core-17. Base: the old 2025 key signs the rotation; the acceptance and the mandate that the new 2026 key signs count. Consequential: only the new key signs the rotation; the acceptance and the mandate do not count. Irrelevant: the statement order changes nothing. Also Q25 and Q12.

### 6.3 Partial withdrawal

- **Gap:** sc-core-23 withdraws only `part: section 3` of SEC-4, with the successor SEC-11. docs/11 has no `part` field. The auto set has the same case: RFC 9110 and RFC 9112 obsolete only "portions of" RFC 7230 (`supersession_scope: partial`).
- **Proposal:**
  1. Add an optional `part` (free text, or a fragment id) to an `acceptance: withdrawn` statement.
  2. A partial withdrawal does **not** change the acceptance state. The item stays `accepted`.
  3. Each use of the item shows the notice `partly-withdrawn: <part> → <successor>`.
  4. The item loses `rule` authority, and keeps `evidence` authority. A request with `want: rule` gives `escalate`: the engine cannot know whether the rule that the request needs is in the withdrawn part.
- **Why:** a full withdrawal removes the sections that are still in force. A full `rule` authority cites a section that is no longer in force. Both errors are worse than an escalation to a person.
- **Scenario:** sc-core-23. Base (partial): `escalate`, authority `evidence`, the notice. Consequential (no `part`): SEC-4 is `withdrawn`; `deny` in the ordinary view. Irrelevant: the renamed SEC-11 file changes nothing.

### 6.4 `updates`, `obsoletes` and `replaces`

- **Gap:** docs/11 does not define these relations. sc-core-07 uses `relations: {updates: [i-net7]}` in the NET-9 item. The auto set keeps them apart: an RFC `Updates:` is not a supersession; KEPs use `replaces` in the successor, and the KEP `superseded-by` field is empty in all 7 replaced or superseded KEPs (`auto/docs` README §4.3).
- **Proposal:**
  1. Define `relations` in the `item` body: `obsoletes`, `replaces` (the same meaning as `obsoletes`) and `updates`. Each one names item ids.
  2. `obsoletes`/`replaces` is a supersession. It moves the target to `withdrawn` (reason `superseded`, the successor named) only when the target's issuer, or a prior replacement rule, has the authority (docs/11 §6). It applies only in the shared scope and time.
  3. `updates` is an amendment. The target stays `accepted`. Each use of the target shows the notice `updated-by: <id>`, and a model answer gets both items.
  4. A relation is read from both sides: a successor's `obsoletes` and a target's `obsoleted_by` give the same edge.
- **Why:** the false `withdrawn` of an updated document removes a rule that is still in force. The auto set shows that sources declare the relation mostly on the successor side.
- **Scenario:** sc-core-07. Base (`Updates: NET-7`): NET-7 stays accepted, with the notice. Consequential (`Obsoletes: NET-7`): NET-7 is withdrawn. Irrelevant: the renamed NET-9 file changes nothing. Also Q13, Q16, Q17.

### 6.5 Is a search with a local embedding model an `ai_input` use?

- **Gap:** sc-core-05: the node's search is hybrid (lexical + a local embedding model). The item says `search: y`, `ai_input: n`.
- **Proposal:** **No.** A search that computes embeddings in a node-controlled location, only to select items and to show them to a person with a link, needs `ai_use.search` only. It does not need `ai_input`.
  - The vectors are a derivative (§3 derive). They inherit the handling of the item, and they never leave the node.
  - When the search result goes to a generative model (a model answer, RAG), the action is `infer`. Then `ai_input` is necessary.
  - Applied (2026-10-27): `decide.py` checks `ai_use.search` for a request with `operation: search`; absent = `n` (conformance cases "§5 search terms").
- **Why:** the AIPREF vocabulary (`draft-ietf-aipref-vocab-08` §4.2–4.3, https://datatracker.ietf.org/doc/html/draft-ietf-aipref-vocab-08) defines "AI Use" as input to a **generative** AI model, and "Search" as the selection of assets that directs users to their location. An embedding model such as bge-m3 is not generative. Also, a lexical search and a vector search are the same user action. The decision must not change with an implementation detail.
- **Scenario:** sc-core-05. Base (`search: y`, `ai_input: n`): `permit`. Consequential (`search` absent): `deny`, because an absent term counts as `n`. Irrelevant: the renamed file changes nothing. Also Q19 and Q3.

### 6.6 Is a model answer through a cloud processor a `forward` of personal data?

- **Gap:** sc-core-10: synthetic support tickets from a trusted vendor go to `cloud:llm.example.net`. docs/11 §5 required a legal basis for personal data only for `forward`. `decide.py` checked personal data only for `forward`, so the base and the consequential variant gave the same result. Applied (2026-10-27): an `infer` with a `destination` gets the personal-data check (conformance cases "§5 personal data in a model answer").
- **Proposal:** **Yes, for personal data.** An `infer` whose `destination` is outside the node-controlled locations also gets the personal-data check of `forward`:
  - `yes` or `unknown` needs a recorded legal basis;
  - `synthetic` counts only from an issuer that is trusted for `item` statements in the scope; from any other issuer it counts as `unknown`.
  - The licence check of `forward` does not apply: `ai_input` already covers the use of the content.
  - The `route` handling check stays as it is (`local_only` → `deny`).
- **Why:** a disclosure to a processor is processing of the data. The result must not depend on the action name that the request uses. Without this rule, the consequential variant (the trust entry for DataForge removed) does not change the result.
- **Scenario:** sc-core-10. Base (trusted vendor): `permit`. Consequential (no trust entry): `deny`, `personal-data-basis-missing`. Irrelevant: the statement order changes nothing. Also Q7 and Q11.

### 6.7 Item `ai_use`: merge with the folder default, or replace it?

- **Gap:** sc-core-13: the folder default is `{search: y, ai_input: y, train: n}`. The template item says only `ai_use: {search: y}`.
- **Proposal:** **merge per term.** An item value replaces only the terms that it names. The terms that it does not name come from the folder default. To reserve a term, the item writes `n`.
- **Why:**
  - The L0 example in docs/11 §8 already merges: `rights: {personal_data: unknown}` "overrides the default", and the licence still comes from the folder default. A merge per term is the same rule one level lower.
  - With "replace", the base gives `deny` (`ai_input` absent = `n`), and the consequential variant (`ai_input: n`) gives `deny` too. Then the consequential variant cannot change the result, as the scenario intends.
  - An explicit `n` is always stricter, so a merge never loosens what the item writes.
- **Scenario:** sc-core-13 (held-out). Base: `permit` for `infer`. Consequential (`ai_input: n`): `deny`, `rights-reserved:ai_input`. Irrelevant: the key order in the signed bytes changes nothing. Also Q3, Q18 and Q10.

### 6.8 Untrusted origin claims

- **Gap:** sc-core-15: Northwind's item says `origin: human` and "no LLM used (self-declared)". docs/11 §5 has a trust rule only for `synthetic`.
- **Proposal:** use the same rule as for `synthetic`. An origin value other than `model` or `unknown` counts only when the item issuer is trusted for `item` statements in the scope. From any other issuer, the origin counts as `unknown` (= `model`).
  - The claim stays visible, with its issuer: the notice `origin-claim-untrusted`.
  - In sc-core-15 the node policy has no origin condition. The result stays `permit`; the served origin and the notice change.
- **Why:** a self-declared origin is the cheapest false-authority signal (Q16, Q23). The auto set shows the risk: Qwen took the review record of 25 model PRs as `assisted` (§3). An approval in a PR record is not proof of a review in substance.
- **Scenario:** sc-core-15. Base (Northwind trusted for `item` in `book:customs`): origin `human`. Consequential (trusted only in `book:partners`): origin `unknown`, with the notice. Irrelevant: the renamed file changes nothing. Also Q4.

### 6.9 Content labels: a quoted attack vs an instruction

- **Gap:** sc-core-11 and sc-core-12. Do content labels change a decision, or only the activation-risk annotation?
- **Proposal:**
  1. A content label is a statement about one exact digest. A label from any issuer that **tightens** (`hostile`) applies at once (rule 4). Only a trusted issuer can remove it.
  2. A `hostile` label gives `deny` for `activate`, and `escalate` for `infer` when the actor is an agent. For a person who reads the item, it is a notice only.
  3. A `quoted-attack` label (text that quotes an attack to warn against it) changes no decision. It is a notice.
  4. Delivery to a model always passes the content as typed data (docs/11 §3 deliver), with or without a label.
- **Why:** sc-core-11 consequential (the same line as a hidden HTML comment to the assistant) keeps the same acceptance statement. Only a content label can change its result. In sc-core-12, the consequential change already fails on the digest: Selin's acceptance names the old SKILL.md digest. So a label rule is not necessary there, but it gives the same answer.
- **Scenario:** sc-core-11. Base (a quoted warning): `permit`, notice. Consequential (a hidden instruction): `escalate` for the helpdesk agent. sc-core-12: base `permit` for `activate`; consequential `deny` (digest and label). Also Q22 and Q5.

### 6.10 Author-withdrawn drafts that were never accepted (PEPs 426, 501, 759)

- **Gap:** D68 added `pending → rejected` (a decision not to accept, by an approver). docs/11 §5 says "`withdrawn` is history: it was accepted once". But PEPs 426, 501 and 759 are `Withdrawn` by their authors, and their git history has no accepted revision (`prior_acceptance: false`). docs/11 §6 has no `pending → withdrawn` transition. The `auto/docs` gold keeps them `withdrawn`.
- **Proposal:**
  1. Add the transition `pending → withdrawn`. Trigger: the issuer ends its own proposal, with a reason. Actor: the item issuer. Automatic: no. Reversal: a new proposal (a new item); the withdrawal stays in history.
  2. Change the §5 text: "`withdrawn` is history: its issuer ended it. `prior_acceptance` tells whether it was accepted before." `rejected` stays the decision of an approver.
  3. Do not map an author withdrawal to `rejected`. A rejection is a judgement by an approver. An author withdrawal says nothing about the content.
- **Why:** the source declares "Withdrawn", and the author, not an approver, made the change. A `rejected` label would put a decision into the record that nobody made. Both states are history, so the decision result is the same (`deny` in the ordinary view, visible in the history view). Only the reason differs.
- **Scenario:** none in `scenario/core`. A new base is necessary: an author withdraws a pending item; base = author withdrawal, consequential = an approver's rejection, irrelevant = a reworded reason. The auto set already scores the label: PEPs 426, 501 and 759 (§3.1).
