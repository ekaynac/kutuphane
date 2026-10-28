# Pilot 1 — the radar repository as books

Real-use pilot 1 (`docs/15` §4, D61). Date: 2026-10-26. Branch: `fix/pilot-radar`.

## 1. Setup

- **Source:** the public repository `ekaynac/onprem-ai-adoption-radar` (MIT), pinned at commit
  `b8321066765ff2237433ceeeccc5c0e47e15b7f9`. The commit history with trailers comes from the labelling v4 cache.
- **Kütüphane:** this repository, CLI on the host. Postgres (main database `kutuphane`; migrations 010–012 were
  applied first).
- **Models (all local):** LLMDAP routes `chat` (RadixArk/Qwen3.8-27B-NVFP4 on the host vLLM), `emb` (BAAI/bge-m3,
  1024 dimensions, CPU), `rerank` (BAAI/bge-reranker-v2-m3, CPU). Core settings as in
  `deploy/compose.local-models.yaml`.
- **Principal:** `user:pilot` with `discover`, `read` and `use` on the three books.
- The book folders are in `research/pilots/radar/` (git ignores them).

## 2. Books and kstd values

| Book | Files | Content |
|---|---|---|
| `radar-docs` | 83 | `README.md`, `CHANGELOG.md`, `docs/**` (68 markdown, 1 YAML), `config/*.yaml` (12) |
| `radar-news` | 2 | `data/news-classified.jsonl` (2,533 records, 1.4 MB), `data/news-observations.jsonl` (5,027 records, 1.7 MB) |
| `radar-briefs` | 24 | `data/briefs/brief-2026-W*.json` (8), `digests/digest_2026-W*.html` (16) |

Not loaded: telemetry JSONL files (`calls-ledger`, `autopilot-log`, history and metric files), code, images.

**Rights (all books):** license `MIT`, holder "Enes Kaynakcı" (from `LICENSE`). `ai_use`: `search: y`,
`ai_input: y` (the repository is public), `train` not stated (absent; decisions treat it as `n`). Notice: the source
URL and the commit.

**Personal data:**

- `radar-docs`: default `no`. 12 files are `unknown`, because they contain the owner's name, the GitHub user name or
  a mailbox address.
- `radar-news` and `radar-briefs`: `unknown`. News titles name people; briefs and digests contain GitHub user names
  in repository slugs.

**Origin:**

| Files | Origin | Evidence |
|---|---|---|
| 19 docs/config files with a `Co-Authored-By: Claude` trailer in their history | `model` | commit trailers; no named reviewer is recorded |
| `docs/superpowers/plans/*`, `docs/superpowers/specs/*` | `model` | written by the superpowers skill (header "For agentic workers…"); "Approved" lines name no reviewer, so they stay `model` |
| 9 other docs and config files (for example `CHANGELOG.md`, `docs/persistence.md`) | `unknown` | no trailer and no other statement |
| `news-classified.jsonl` | `model` | every record has `"model": "claude-opus-5"` |
| `news-observations.jsonl` | `tool` (`onprem-ai-adoption-radar` 0.1.0) | collector records: titles, URLs and times as fetched |
| briefs W32, W35–W38, W40 | `model` | they contain news summaries that are identical to `news-classified` summaries (input rule) |
| briefs W33, W39 | `tool` | no model text inside: ring moves, benchmark moves and new repositories only |
| 16 digests | `tool` | templates over trending numbers and ring changes; no news text |

`kstd-check`: PASS for all three books (`radar-docs` needs the accepted finding, see §3).

## 3. Load results

| Book | Passages | Publish | Indexing (bge-m3, CPU) | Notes |
|---|---|---|---|---|
| `radar-docs` | 2,601 (mean 812 characters) | about 1 s | 2,578 s (about 1 passage/s) | 1 accepted finding |
| `radar-news` | 7,560 (one per JSONL record, mean 427 characters) | — | 2,200 s for publish and index together | — |
| `radar-briefs` | 45 (mean 2,666 characters) | about 1 s | failed twice (HTTP 504 after 120 s); 148 s after the fix in §5 | — |

- **Secret scan:** `README.md` line 276, rule `authorization-header`. The text is the documentation example
  `Authorization: Bearer your-secret`. This is a clear false positive. It was accepted for this rule and this
  file digest only (`--accept-finding README.md@sha256:<digest>:authorization-header`).
- No file was quarantined. No size limit was reached.
- The first ingest of `radar-docs` stopped with `LLMDAP not configured: set KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS`.
  The book was published, but the command exited with code 2 and printed no publication result.

## 4. Questions

All answers came through `kutuphane ask`. Each citation shows the item information (origin, license MIT, holder,
personal data, notices). No passage was withheld.

| # | Question | Answer quality | Citations OK? | Time |
|---|---|---|---|---|
| 1 | Which on-prem serving engines support NVFP4 on Blackwell? | Partly correct. vLLM evidence is correct (3 news records). The claim that the sources have nothing for the other engines is not shown; `config/platform-matrix.yaml` was not retrieved. | 3 of 4. Citation [2] (README, technique radar) does not support the claim. | 102 s |
| 2 | Why were rings replaced with Pulse? | "Not in library". Wrong: the rescue report (Turkish) gives the reason (rings, calls ledger and lineage produced noise, ring flapping KN-4), and `docs/pulse.md` lists the frozen parts. Re-run with working embeddings: the same; asked in Turkish: answered correctly (G19). | — | 58 s |
| 3 | Security news about vLLM and llama.cpp, classified records only | Correct content (engine as attack surface; isolate, patch). | No. The only citation is brief W35, not a `news-classified` record. Kütüphane cannot limit the evidence to one file or book. | 93 s |
| 4 | How do Jev and Claude disagree on news relevance? | Good. Different product question; F1 0.83, agreement 79.3%, event-type 63.9%; `other` vs `community`. | Yes (`docs/jev.md`, rescue report). | 104 s |
| 5 | What did the weekly brief of 2026-W40 recommend? | Good. Two ring moves to pilot, one benchmark move, new repositories ignored below 200 stars/day. | Yes (brief W40, digest W40). | 112 s |
| 6 | Hangi modeller son haftalarda pilot halkasına girdi ve neden? | Partly wrong. It omits `hf-qwen3-8-27b-nvfp4` (W40, the most recent). The last sentence cites `[2,3,5,6]`; passages 2, 3 and 5 are not in the citation list (G21). | Partly. The cited claims match their passages (checked against the stored answer, Astra review #11). | 98 s |
| 7 | Boiling point of liquid nitrogen at sea level (not in library) | "Not in library" — correct | — | 80 s |
| 8 | Winner of the 2018 FIFA World Cup final (not in library) | "Not in library" — correct | — | 48 s |

All answers are in Turkish, also for the English questions. `kutuphane search` for question 2 took 45 s.

**v2 (`fix/answers-quality`, 2026-10-26/27).** The same questions through `answers.ask` (as `kutuphane ask`) on the
same books, before (main at `929d4a9`) and after the branch. The answer model was shared with the operator's
labelling work in both runs, so the times vary; the token counts do not. 2en/2tr are question 2 in English and in
Turkish; 3s is question 3 with `--book radar-news --path data/news-classified.jsonl` (G14).

| # | Before (re-run) | v2 | Time before → v2 |
|---|---|---|---|
| 1 | Turkish; vLLM evidence correct (3 news records); README cited for the engine matrix | English; vLLM evidence correct (5 news records); also names Diffusers (a library, not a serving engine); `platform-matrix.yaml` still not retrieved | 166 s → 89 s |
| 2en | "Not in library" | "Not in library"; the report §41 and KN-4 §7 are now passages 1 and 3 (G19 open at the answer step) | 67 s → 72 s |
| 2tr | Correct (KN-4 ring flapping, Kapsam B) | Correct (KN-4, Kapsam B, rings frozen), cites §41, §7, README | 152 s → 100 s |
| 3 | "Not in library" (8 passages, 7 classified records) | Correct content; cites brief W35 only (the copy, G23) | 116 s → 54 s |
| 3s | — | Correct; cites classified records only (the security advisory record and 7 others) | — → 43 s |
| 4 | Good (Turkish) | Good (English): different questions, 79.3 % / 20.7 %, `other` vs `community` | 235 s → 66 s |
| 5 | Good (Turkish) | Good (English): 2 ring moves to pilot, aider-polyglot +8.4, repositories ignored below 200/day | 173 s → 65 s |
| 6 | Partly wrong: W35, W39, W32; omits W40 | Correct for the newest weeks: W40 `hf-qwen3-8-27b-nvfp4`, W39 `hf-minicpm5-2b`; brief W40 is passage 1 (G22) | 141 s → 82 s |
| 7 | "Not in library" — correct | "Not in library" — correct | 111 s → 49 s |
| 8 | "Not in library" — correct | "Not in library" — correct | 65 s → 23 s |

### 4.1 Time per stage (G26)

Seconds: query embedding / hybrid search / translation / rerank / answer model; then characters sent to the
reranker, and prompt / answer tokens.

| # | Before | v2 |
|---|---|---|
| 1 | 1.1 / 1.4 / – / 48 / 115; 67,353 ch; 3,878 / 694 tok | 0.3 / 0.4 / – / 26 / 62; 27,891 ch; 2,591 / 273 tok |
| 2en | 0.3 / 0.1 / – / 49 / 18; 57,930 ch; 12,147 / 10 tok | 0.6 / 0.5 / 3.6 / 42 / 26; 26,526 ch; 5,079 / 86 tok |
| 2tr | 0.3 / 0.2 / – / 44 / 108; 31,113 ch; 3,413 / 206 tok | 0.2 / 0.2 / 2.5 / 31 / 66; 26,140 ch; 3,101 / 184 tok |
| 3 | 21.4 / 0.3 / – / 87 / 7; 56,124 ch; 3,246 / 10 tok | 0.6 / 0.4 / – / 29 / 24; 24,425 ch; 2,239 / 173 tok |
| 4 | 77.1 / 2.2 / – / 77 / 78; 44,533 ch; 4,099 / 309 tok | 0.6 / 0.3 / 5.1 / 34 / 26; 23,970 ch; 2,401 / 128 tok |
| 5 | 5.6 / 0.2 / – / 77 / 90; 79,087 ch; 11,040 / 328 tok | 0.2 / 0.2 / – / 40 / 25; 33,619 ch; 6,040 / 150 tok |
| 6 | 0.2 / 0.2 / – / 62 / 79; 58,932 ch; 7,715 / 604 tok | 0.5 / 0.3 / 2.4 / 34 / 45; 32,872 ch; 6,156 / 204 tok |
| 7 | 0.2 / 0.2 / – / 93 / 18; 75,274 ch; 12,877 / 10 tok | 0.2 / 0.2 / – / 36 / 12; 27,200 ch; 6,826 / 10 tok |
| 8 | 0.3 / 0.3 / – / 54 / 11; 40,396 ch; 7,027 / 10 tok | 0.2 / 0.1 / – / 17 / 5; 21,969 ch; 2,634 / 10 tok |

Questions 1–8 (2en for 2): mean 134 s → 63 s. The before-run query embeddings of 21 s and 77 s (questions 3, 4)
waited for other calls on the shared embedder (G18). Prompt building takes less than 0.1 s. In v2, question 3s
used the cached vector of question 3 (no embedding call). Rerank cap, measured offline on the same hybrid pools
(full / 1,500 / 1,200 / 800 characters): the top 8 at 1,200 had 6–8 of 8 passages in common with the full rerank
on questions 1–6, kept every evidence passage, and brought the report into the top 8 for question 2en; at 800,
digest W40 fell from rank 8 to rank 25 for question 6.

### 4.2 Re-check after chunker 5 (2026-10-27)

After the re-ingest with chunker 5 (#118), question 3 seemed to lose the security advisory record, and question 2en
still did not give the reason. The retrieval stages of `fd28bce` (v2), #96, #110 and #118 ran against the same
database (read-only, with the old and the new `radar-docs` profile).

- **Question 3 is not a regression.** With the three radar books, the advisory record has hybrid rank 34 at every
  commit and with both profiles (full-text rank 17, no vector rank in the top 60). The rerank pool is 30, so the
  reranker never sees it. The 8 passages are the same as in the v2 run of question 3. The record that the check
  expected came from the v2 run of 3s (`--book radar-news --path data/news-classified.jsonl`), where it has hybrid
  rank 1 and rerank rank 2. Question 3 has no translation step: its pool has no Turkish passage.
- **Question 2en: the translation was sampled.** In 8 samples, the answer model wrote the literal Turkish word for
  "rings" 3 times. The other samples used other words ("bracelets", "wristbands", "circles", one wrong word) or
  answered the question. With another word, the second search does not find the KN-4 passage. In 3 runs before the
  fix, 2 translations used "wristbands". **Fixed:** the translation uses greedy decoding (`temperature` 0); the 8
  greedy translations (5 samples, 3 runs) were all literal.

3 runs of each question, before → after the fix (user `pilot`, the three radar books; 3s as in v2):

| # | Answered | Evidence | Answer |
|---|---|---|---|
| 1 | 3/3 → 3/3 | the same 8 passages in all 6 runs (no translation) | vLLM in every answer |
| 2tr | 3/3 → 3/3 | KN-4 in 3/3 → 3/3 | gives the reason (ring flapping) in 2/3 → 1/3 |
| 2en | 2/3 → 2/3 | literal translation 1/3 → 3/3; KN-4 in 1/3 → 3/3 | gives the reason in 1/3 → 1/3 |
| 3 | 3/3 → 2/3 | the same 8 passages in all 6 runs; advisory record in 0/6 | advisory content (from the brief copy, G23) in 3/3 → 2/3 |
| 3s | 3/3 → 3/3 | advisory record in 6/6 | cites the advisory record in 6/6 |

Retrieval of questions 1, 3 and 3s does not change; their answer differences come from the answer model. Open
(G19): the passage with the report's diagnosis is at rank 24–28 of the second search; the merge keeps 15 passages of
each list, so it does not reach the reranker. In a test pool that keeps it, the reranker puts it at rank 21–29,
outside the top 8. With KN-4 in the evidence, the English answer gives the reason in 1 of 3 runs: the answer step
is still the limit.

## 5. Problems found

### Fixed on this branch (with regression tests)

1. **`kstd-init` and `kstd-check` could not accept a reviewed finding.** They run the same credential scan as
   `ingest`, and the error told the operator to use `--accept-finding`, but these commands did not have the option.
   Now they take the same `--accept-finding` values.
2. **A refused `kstd-init` left an empty `kstd.yaml`.** The file was created before the scan. The next run then
   failed with "file exists". Now the scan runs first.
3. **`kstd-init` wrote non-ASCII text as escapes** (`"K\xFCt\xFCphane"`), and a long path could wrap onto two
   lines. Now names stay readable and each value stays on one line.
4. **Indexing long passages failed with HTTP 504.** A batch of 32 passages of JSON or HTML took more than the
   120 s gateway time on CPU. Batches now also have a character limit (24,000 characters). A longer single passage
   is embedded by its first 24,000 characters, and its vector is marked `truncated` (Astra review #11).

### New gaps (continuing `docs/15` §3)

| # | Gap | Effect in the pilot | Size |
|---|---|---|---|
| G12 | **Ingest reports failure after a successful publish.** When indexing fails, `ingest` exits 2 and does not print the publication result. One failed embedding call stops the whole `index` run. **Closed (`fix/indexing`):** an embedding settings error stops `ingest` before the publication; an index failure after the publication prints the publication result with `index_error` or `failed`/`not_attempted` and exits with code 3. A failed call is tried 2 more times (5 s, 10 s backoff); a batch that still fails is reported and `index` continues; after 3 failed batches in a row the rest is not attempted. Scratch database, all 45 brief passages: with the old batching, one call of 12 passages failed with HTTP 504 (the old code stops at the first failed call); with the new defaults, no call failed. | The operator does not know that the book is live; the accepted findings are not printed. | small |
| G13 | **The host CLI needs settings that only `compose.yaml` sets** (`*_ROUTE_CLASS`, default `local`). **Closed (`fix/pilot1-small`):** every `KUTUPHANE_*` value of `compose.yaml`, `compose.light.yaml` and `compose.curator.yaml` was checked (a test reads the files). `KUTUPHANE_OIDC_AUDIENCE` (`kutuphane`) and `KUTUPHANE_CONFIRM_HOURS` (`24`) now have the compose default in the code, and an empty value counts as not set. The others are container addresses and paths, or route classes: the CLI stops and names the setting. A route class gets no default, because `local` skips the egress check; the message now gives the two values and says that compose sets `local`, and a bad value names its setting. Scratch database: `ingest` without `KUTUPHANE_LLMDAP_EMBED_ROUTE_CLASS` exits 2 with that message and publishes nothing; with it, `ingest`, `search` and `ask` run. | The first ingest failed. | small |
| G14 | **No evidence filter in `ask` and `search`** (book, path, origin). **Closed (`fix/answers-quality`):** `book` (one or more), `path` prefix, `origin` (kstd values) and `current_only` on the CLI, the HTTP API and MCP `search_library`/`ask_library`. The filters are in the pre-filter of the ranking statement, so they act before ranking and `k`. A book filter is an intersection with the readable books; tests show that a filter never shows an unreadable book. Question 3 with `--book radar-news --path data/news-classified.jsonl` cites 8 classified records only (§4, 3s). | Question 3 could not limit the evidence to classified news records. | medium |
| G15 | **Citations in `ask` have no `line` and no record id.** `search` gives the line; `ask` gives `path` and `ordinal` only. HTML passages have no line. **Closed (`fix/pilot1-small`):** each `ask` citation (also in a grouped reference, G21) has `line`, as in `search`, and `record`: the number of the JSONL record in its file, from 1, when the passage is inside one record (`null` otherwise, for example with the `whole` profile). Blank lines are not records; both pieces of a cut long record have its number. `reopen` and a background job's result give both, read from the passage, so old answers have them too. HTML and PDF have no line. Scratch database, fixture book with a blank line in its JSONL file: `ask` cites `haberler.jsonl` with `line` 2, `record` 2 and `line` 4, `record` 3; `reopen` gives the same. | A reader cannot open news record 109 from the answer; the citation must be resolved in the database. | small |
| G16 | **Origin is per file, not per record.** One `kstd.yaml` item covers 2,533 records. Their `model` and `classified_at` fields are not shown or checked. A file with records from different models, or with some reviewed records, cannot be described. **Decided, not built (`feat/record-origin`, §7.2):** the smallest profile (a record field that can only make the origin stricter or more specific) changes no decision and no shown origin on the pilot data (one `model` value in 2,533 records, no review field), a per-file `model` is already safe for a mixed file, and a record field can never express "reviewed" (R1). Reopen with a file that mixes producers, or with suspension per generator version. | Correct here only because one model wrote all records. | medium (G2 follow-up) |
| G17 | **Any change re-embeds the whole book.** Vectors are keyed by `content_id`; the radar bots append records every 2 hours. [INFERENCE from the key: one appended record re-embeds all 7,560 news passages, about 37 min on CPU.] **Closed (`fix/indexing`):** a vector records the sha256 of its embedded text (migration 014, existing vectors filled in); a new version copies the vector of each passage with the same embedded text, model and width in the same book and profile. Scratch database, `radar-briefs` with one brief changed (1 of 24 files, 2 of 45 passages): the old code embeds 45 passages; the new code made 2 embedding calls for the 2 changed passages and copied 43 vectors (51 s). | No incremental update for bot-written data. | medium (with G9) |
| G18 | **Indexing is slow on CPU and blocks queries.** About 1 passage/s. During indexing, query embedding failed with HTTP 504 and `ask` fell back to full text (question 2, first try). **Partly closed (`fix/indexing`):** `KUTUPHANE_INDEX_BATCH`, `_BATCH_CHARS` and `_CONCURRENCY` (or `index` options) set the load; the defaults are 8 passages, 8,000 characters, 1 call in flight (before: 32 passages, 24,000 characters, 1 call). README tells how to publish first and index later with smaller calls. Scratch database, all 45 brief passages, one query embedding every 3 s during indexing (idle: 0.2 s): old batching 268 s, query median 52 s, max 85 s; new defaults 234 s, query median 2.5 s, max 75 s (one outlier; [INFERENCE] other calls on the shared embedder, which reranks under the same lock). Open: the embedder has no priority for query calls; a query still waits for the call in front of it. | A 10,000-passage pilot needs about 1.5 h; questions during that time are worse. | medium (queue or priority for query calls) |
| G19 | **A Turkish passage falls below the rerank cut for an English question.** Re-run of question 2 with the embedding route working (every `emb` call without error; no full-text fallback). English: full text has no passage of the rescue report or `docs/pulse.md` in its top 30; the hybrid list has the report at rank 7; the reranker moves it to rank 10 (score 0.005), outside the 8 passages that the answer model gets, so the answer is "not in library". Turkish ("Halkalar neden Pulse ile değiştirildi?"): the reranker puts the same passage first (score 0.52), and the answer is correct and cites the report. One question pair only: the language effect is shown for this pair, not measured. **Partly closed (`fix/answers-quality`):** measured on the 7 pilot questions with traces: question 2 in English has 6 Turkish passages in its hybrid top 30, with rerank scores 0.0002–0.005; with the Turkish question, the reranker gives the same report passage 0.52. In question 4 (English) Turkish passages score up to 0.31, so the effect depends on the question. Now, when the pool has Turkish and English passages, the answer model translates the question (2.4–5.1 s; only the question is sent), a second hybrid search runs with the translation, and each passage is reranked against the question in its own language. Without a translation, up to 2 other-language passages from the hybrid top 8 keep a place. Question 2 in English now gets the evidence of the Turkish question (report §41 first, KN-4 §7 third). The answer model still writes "not in library": its raw text names the deletion (§41) and the ring flapping (§7), but says that no passage connects them to the decision. Open: the answer step, not retrieval. **Re-check 2026-10-27 (§4.2, `fix/retrieval-regression`):** the translation was sampled and was not the literal one in 5 of 8 samples; it now uses greedy decoding, and question 2en has KN-4 in its evidence in 3 of 3 runs (before: 1 of 3). Open: the diagnosis passage does not reach the reranker (merge cut), and the answer step. | False "not in library" for a question in the other language. | medium (measure on a bilingual question set) |
| G20 | **Answer language does not follow the question.** The system prompt is Turkish; all answers are Turkish. **Closed (`fix/answers-quality`):** the question language (Turkish/English from function words and Turkish letters) selects the system prompt and the labels; another language gets the English prompt and "answer in the language of the question". v2: the English questions 1, 3, 4, 5 get English answers; questions 2 (tr) and 6 get Turkish answers. | English users get Turkish answers. | small |
| G21 | **A grouped reference is not read.** The stored answer to question 6 ends with `[2,3,5,6]`. `answers.CITE` reads only `[n]`, so 2, 3 and 5 are neither checked nor listed; the listed citations keep their own numbers (`n` 4, 6, 7, 8). An answer that cites only in grouped form becomes "not in library". (The first version of this row also said that a cited passage contradicted its sentence; the stored answer does not show that: passage 6 says `llama-3.1-8b` avoid → pilot.) **Closed (`fix/answers-quality`):** `[2,3,5]`, `[2, 3]` and `[2-4]` (also with an en dash) are read; every number is checked; an unknown number or a reversed range refuses the answer as before. | Part of the evidence is not shown and not checked. | small (read `[a,b]`, or ask for one number per bracket) |
| G22 | **Recency is not understood.** "Recent weeks" did not rank the newest brief first (question 6). **Closed (`fix/answers-quality`):** a question with "recent", "latest", "son", "en yeni" and similar words ranks the top 2k passages by relevance rank + date rank. The date is the kstd `valid_from`, else the first date or ISO week in the path, else the first date in the text (a record date). v2 question 6: brief W40 is passage 1 and the answer names `hf-qwen3-8-27b-nvfp4` (W40) and `hf-minicpm5-2b` (W39). | Old evidence wins. | medium (dates as a filter or ranking signal) |
| G23 | **Republished model text is not linked to its source.** Brief summaries are copies of `news-classified` summaries; `news-observations` repeats the titles. **Closed (`feat/record-origin`, §7.4):** no brief passage is a whole copy of a news passage (0 exact, 0 normalized); the copies are whole field values inside longer passages. A passage that repeats a whole string value (40 characters or more, white space folded) of a JSONL record now points to the record (`quoted_records` in search and ask), and `ask` puts the record into the evidence right before the copy. Pilot data: 7 of 45 brief passages point to 29 records; the passage of brief W35 that question 3 cited points to the advisory record. Copies are not collapsed (they hold other text). | Duplicate hits; question 3 cited the copy, not the record (with G11). | medium |
| G24 | **The `tool` boundary is not clear for third-party text and batch statistics.** Digests copy GitHub repository names and news titles (origin of the third party unknown), and ring calibration uses quartiles of the current batch. | `tool` is a judgement here; the input rule could make every digest `model`. | decision (D64 follow-up) |
| G25 | **`software_agent.version` is not known per file.** The briefs and digests were made by many commits of the radar; the pilot used the package version 0.1.0. **Decided: no Kütüphane change (`feat/record-origin`, §7.3).** kstd already takes an exact `software_agent.version` per file; the files do not record one (the `version` field of the 8 briefs is one schema value; the digests have none), and no Kütüphane behavior suspends by version yet. The generator must write its version (for example its commit) into each output. | One generator version cannot be suspended exactly. | small (the generator must record it) |
| G26 | **Each answer takes 48–112 s** (CPU embedding, CPU rerank, 27B answer model). `search` alone took 45 s. **Mostly closed (`fix/answers-quality`):** profile per stage in §4.1. The reranker (CPU) and the answer model (shared GPU, 2–6 tokens/s during the operator's labelling) take nearly all of the time; query embedding (0.2–1 s when the embedder is free) and hybrid search (0.1–2 s) are small. Changes: the reranker reads the first 1,200 characters of a passage (36–58 % fewer characters; the top 8 kept the evidence passages on 7 questions); query vectors are cached per process; each passage goes to the answer model by its first 2,400 characters, and the answer is asked to be short (about 150 words). Questions 1–8: mean 134 s → 63 s. Open: the reranker still takes 17–42 s on CPU. | Usable for a pilot, slow for daily use. | measure first |

## 6. Recommendations

1. Fix G12, G13, G15 and G20 first. They are small and they affect every user.
2. Add an evidence filter (G14) and read grouped citations (G21) before the next pilot. Without the filter,
   answers about one source type cannot be trusted.
3. Use per-record provenance for JSONL (G16): read `model` and similar fields into the item information.
   (Decided on 2026-10-28, §7.2: not now; the pilot data gives it no behavior.)
4. Make embedding incremental and give query calls priority over indexing (G17, G18).
5. Test a multilingual question set with working embeddings and keep the retrieval traces; then consider query
   translation, a bilingual query or a larger rerank cut for Turkish/English books (G19).
6. Decide G24 in the D64 follow-up: whether verbatim third-party text and batch statistics keep an output `tool`.

## 7. Record origin and republished text (G16, G23, G25)

Analysis of 2026-10-28, branch `feat/record-origin`. Language: ASD-STE100 Simplified Technical English. The numbers
come from read-only queries on the pilot database (current versions only; aggregates only, no passage text).

### 7.1 What the data shows

| Measure | Value |
|---|---|
| `news-classified.jsonl` records / distinct `model` values / records with a field that names a reviewer | 2,533 / 1 / 0 |
| `news-observations.jsonl` records with a field that names a producer or a version | 0 of 5,027 |
| Briefs with a generator version | 0 of 8 (their `version` field has one schema value in all 8); digests: 0 of 16 |
| Code that reads `software_agent.version` | the package export (`tool_made`) and the item information only; no suspension by version exists |
| Current passages, all books / whole-passage duplicate groups (exact) / of them across books / more with case and white-space folding | 10,514 / 9 (9 extra copies, all inside one book) / 0 / 0 |
| `radar-briefs` passages that are a whole copy of a `radar-news` passage: exact / normalized | 0 / 0 of 45 |
| `radar-briefs` passages that hold a whole record value (the §7.4 rule) | 7 of 45 (6 of 24 files) |
| Records that they repeat | 29 (15 classified, 14 observations); at most 7 per passage |
| Pointers from the briefs labelled `tool` (W33, W39) and from the digests | 0 |
| Question 3: the cited passage of brief W35 | repeats exactly 2 records: the advisory record that question 3s cites, and its observation record |

### 7.2 G16: per-record origin — not built

**The smallest mechanism.** An operation profile, not a core field (D74): the kstd item of a JSONL file names the
record fields, for example `record_origin: {field: model, version_field: generator_version, allowed: [...]}`. Each
record value is checked against the allow-list. Rule R1: a record field can only make the origin stricter (`tool` →
`model`) or more specific inside `model` or `tool` (a model name, a generator version). It can never give `human`
or `assisted`.

**What it would change:** the shown origin per passage; the origin filter per passage (today it is a file list in
the search pre-filter); the export marking stays per file and takes the strictest record; suspension per version
(G25), if it existed.

**Why it is not worth it now (D53, D74):**
1. On the pilot data it changes nothing. One model wrote all 2,533 records, and the per-file `model` is exact. The
   observations have no producer field.
2. A mixed file is already safe. docs/17 §5 makes mixed content `model`. Per-record origin only adds precision to
   the filter and the shown value, for a case that no pilot has shown.
3. It cannot close the second case of G16. "Some records are reviewed" means `assisted`, and R1 forbids a record
   field to raise the origin. A review needs a person's statement: a separate file with its own item, or notes with
   an origin confirmation (docs/25 §7).
4. A model name per record is a new field with no behavior: kstd has no model identity in the origin details, and
   no rule reads one.
5. Cost: a per-passage origin in the ranking pre-filter, a strictest-record rule in the export, a new manifest key
   with its validation, and the documentation.

**Reopen when** a book has a file whose records come from different producers (the `needs_split` rate of the
labelling data is the measure), or when suspension per generator version exists (§7.3). Then build the profile
above, with R1.

### 7.3 G25: generator version — no Kütüphane change

kstd already takes `software_agent: {name, version}` per item, as an exact string. The radar outputs do not record
the version that made them (§7.1). A `version_field` would read the schema version, which is the same for every
brief. No Kütüphane behavior suspends by version, so a per-record version would also change nothing. The fix is at
the generator: it writes its version (for example its commit) into each output, and `kstd-init` can then propose
it.

### 7.4 G23: records that a passage repeats — built

**The proposal was a `same_as` between whole passages** (by `input_sha256`, plus a normalized hash), with the copies
collapsed. The data refutes it: no brief passage is a whole copy of a news passage, and across books there is no
whole-passage duplicate at all. The copies are **whole field values inside longer passages**: the same brief
passage also holds ring moves and other text. A collapse would remove that text from the evidence. (A normalized
match is also only a candidate, never an automatic identity, docs/24 §7.) So there is no `same_as` and no collapse.
The 9 exact duplicates inside one book (0.09 % of the passages) do not justify a collapse either.

**What "source" means (the minimal rule):** the JSONL record. A record is one line and one passage, with an id and
a line (G15). A longer text that repeats one of its whole field values was assembled from it; a record field is not
cut out of a brief. The older publication is not the rule: the content version of a book changes at each
publication, and the radar bots publish the news every 2 hours (G17), so the news would become newer than the
briefs that copy it. A record never counts as a copy, so two records with the same value are not linked.

**Identity is text, never a vector:** the sha256 of a string value of a record, at any depth, after white space
(`[ \t\n\r\f\v]+`) is folded to one space; only values of 40 characters or more (shorter values are labels such as
`event_type`). A passage repeats the value when the same digest comes from one of its units: a JSON string literal,
a line, or a line without its markdown list, quote or heading mark. The values are stored at publication
(`record_value`, migration 037; the migration fills the versions published before it, with the same folding). The
lookup runs at read time against the current version of each book, so a new publication never leaves a stale link.

**Behavior:**
- `search` (CLI, HTTP, MCP): each hit has `quoted_records`, the handles of the records it repeats. Only records in
  books that the caller may read now and that pass the same filters (book, path, origin, validity); never an
  instruction passage. The order of the hits does not change: the copy usually has other text.
- `ask`: each record is put into the evidence right before its first copy (at most 4; only with AI input in its
  rights). The copy is marked `repeats [n]` in the prompt, with one note that tells the model to cite record `[n]`
  for that text. A citation has `quoted_records` (the records in the evidence), also when the answer is opened
  again. The record's book is a source book of the answer, so the final gate decides it with the others.

**Limits:** a value inside a longer line, a paraphrase, and a translation are not found. Record-to-record copies
are not linked (none in the pilot: no classified summary equals an observation summary).

**Effect on question 3 [INFERENCE]:** the cited W35 passage brings the advisory record into the evidence before it,
so the answer can cite the record. The answer was not run again: this work does not write to the pilot database.
