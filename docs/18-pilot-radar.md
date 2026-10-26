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
| G12 | **Ingest reports failure after a successful publish.** When indexing fails, `ingest` exits 2 and does not print the publication result. One failed embedding call stops the whole `index` run. | The operator does not know that the book is live; the accepted findings are not printed. | small |
| G13 | **The host CLI needs settings that only `compose.yaml` sets** (`*_ROUTE_CLASS`, default `local`). | The first ingest failed. | small |
| G14 | **No evidence filter in `ask` and `search`** (book, path, origin). | Question 3 could not limit the evidence to classified news records. | medium |
| G15 | **Citations in `ask` have no `line` and no record id.** `search` gives the line; `ask` gives `path` and `ordinal` only. HTML passages have no line. | A reader cannot open news record 109 from the answer; the citation must be resolved in the database. | small |
| G16 | **Origin is per file, not per record.** One `kstd.yaml` item covers 2,533 records. Their `model` and `classified_at` fields are not shown or checked. A file with records from different models, or with some reviewed records, cannot be described. | Correct here only because one model wrote all records. | medium (G2 follow-up) |
| G17 | **Any change re-embeds the whole book.** Vectors are keyed by `content_id`; the radar bots append records every 2 hours. [INFERENCE from the key: one appended record re-embeds all 7,560 news passages, about 37 min on CPU.] | No incremental update for bot-written data. | medium (with G9) |
| G18 | **Indexing is slow on CPU and blocks queries.** About 1 passage/s. During indexing, query embedding failed with HTTP 504 and `ask` fell back to full text (question 2, first try). | A 10,000-passage pilot needs about 1.5 h; questions during that time are worse. | medium (queue or priority for query calls) |
| G19 | **A Turkish passage falls below the rerank cut for an English question.** Re-run of question 2 with the embedding route working (every `emb` call without error; no full-text fallback). English: full text has no passage of the rescue report or `docs/pulse.md` in its top 30; the hybrid list has the report at rank 7; the reranker moves it to rank 10 (score 0.005), outside the 8 passages that the answer model gets, so the answer is "not in library". Turkish ("Halkalar neden Pulse ile değiştirildi?"): the reranker puts the same passage first (score 0.52), and the answer is correct and cites the report. One question pair only: the language effect is shown for this pair, not measured. | False "not in library" for a question in the other language. | medium (measure on a bilingual question set) |
| G20 | **Answer language does not follow the question.** The system prompt is Turkish; all answers are Turkish. | English users get Turkish answers. | small |
| G21 | **A grouped reference is not read.** The stored answer to question 6 ends with `[2,3,5,6]`. `answers.CITE` reads only `[n]`, so 2, 3 and 5 are neither checked nor listed; the listed citations keep their own numbers (`n` 4, 6, 7, 8). An answer that cites only in grouped form becomes "not in library". (The first version of this row also said that a cited passage contradicted its sentence; the stored answer does not show that: passage 6 says `llama-3.1-8b` avoid → pilot.) | Part of the evidence is not shown and not checked. | small (read `[a,b]`, or ask for one number per bracket) |
| G22 | **Recency is not understood.** "Recent weeks" did not rank the newest brief first (question 6). | Old evidence wins. | medium (dates as a filter or ranking signal) |
| G23 | **Republished model text is not linked to its source.** Brief summaries are copies of `news-classified` summaries; `news-observations` repeats the titles. | Duplicate hits; question 3 cited the copy, not the record (with G11). | medium |
| G24 | **The `tool` boundary is not clear for third-party text and batch statistics.** Digests copy GitHub repository names and news titles (origin of the third party unknown), and ring calibration uses quartiles of the current batch. | `tool` is a judgement here; the input rule could make every digest `model`. | decision (D64 follow-up) |
| G25 | **`software_agent.version` is not known per file.** The briefs and digests were made by many commits of the radar; the pilot used the package version 0.1.0. | One generator version cannot be suspended exactly. | small (the generator must record it) |
| G26 | **Each answer takes 48–112 s** (CPU embedding, CPU rerank, 27B answer model). `search` alone took 45 s. | Usable for a pilot, slow for daily use. | measure first |

## 6. Recommendations

1. Fix G12, G13, G15 and G20 first. They are small and they affect every user.
2. Add an evidence filter (G14) and read grouped citations (G21) before the next pilot. Without the filter,
   answers about one source type cannot be trusted.
3. Use per-record provenance for JSONL (G16): read `model` and similar fields into the item information.
4. Make embedding incremental and give query calls priority over indexing (G17, G18).
5. Test a multilingual question set with working embeddings and keep the retrieval traces; then consider query
   translation, a bilingual query or a larger rerank cut for Turkish/English books (G19).
6. Decide G24 in the D64 follow-up: whether verbatim third-party text and batch statistics keep an output `tool`.
