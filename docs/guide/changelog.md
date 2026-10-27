# Changelog

This file lists the changes that users and operators can see.
The newest changes are first.
Each date has the pull requests (PRs) that were merged on that date.
Decision D75 is the rule for this file: each feature PR updates the related user documentation in the same PR, and it adds its entry here.
Internal work (decision records, research notes, labelling experiments) is in one "Design and research" line for each date.
For the terms, read [concepts.md](concepts.md).

## Unreleased

### Bulk import and private journals (#75)

- New command `kutuphane note import <journal> <file.jsonl> --by <principal>`: it imports the records of an orchestrator's local memory (for example nöbetçi-mcp) as `pending` notes, in one transaction. A record keeps its claimed Standing, origin and original timestamps as provenance only; origin follows D70 (`--by agent:` gives `model`, `--by user:` gives `unknown`). Links between records resolve by record id. The same record id again is a no-op. The format is in [agent-memory.md](agent-memory.md), section 11. Migration `027_note_import.sql`: after `migrate`, apply `deploy/db-roles.sql` again ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- The import is CLI only (no MCP tool or HTTP route). It does not count against the importer's daily write limit for MCP and HTTP ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- Private journals: a journal with `--sensitivity restricted --egress local_only` keeps customer-confidential project memory in the installation ([operations.md](operations.md), section 6) ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- Behavior change: `kutuphane export` now refuses every book with `sensitivity: restricted`, not only journals (docs/09: Sensitivity owns export). To move such a book, publish it with `--sensitivity normal` first ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- `ingest` and `approve-import` into a journal slug are refused. Before, they could give a journal a content version and another policy ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- The decision export leaves out each note with a `restricted` book in its sources; the summary counts them in `restricted` ([#112](https://github.com/ekaynac/kutuphane/pull/112)).
- `journal create --train y` is refused for a `restricted` journal ([#112](https://github.com/ekaynac/kutuphane/pull/112)).

### Light install (#76)

- New: `deploy/compose.light.yaml` starts Postgres, Core and the ingress proxy with no LLMDAP and no model server; only open source parts. Search is full text only. Steps and what is lost (answers, vectors, rerank, the model audit): [install.md](install.md#light-install) ([#111](https://github.com/ekaynac/kutuphane/pull/111)).
- Without LLMDAP, `ask_library` and `POST /v1/ask` give `503` `answers are not available: this install has no model gateway (LLMDAP); search is full text only` (before: `502` `model service unavailable or refused`). `background: true` makes no job ([#111](https://github.com/ekaynac/kutuphane/pull/111)).
- The server needs `KUTUPHANE_ANSWER_MODEL` only when `KUTUPHANE_LLMDAP_URL` is set. An embedding or rerank route without LLMDAP still stops the start: Core calls a model only through LLMDAP ([#111](https://github.com/ekaynac/kutuphane/pull/111)).
- `deploy/egress_probe.py --light` checks that Core reaches Postgres and nothing else ([#111](https://github.com/ekaynac/kutuphane/pull/111)).

### Security fixes (Astra review #15)

- A skill block now follows the skill's bytes: a new version of a book with the same skill files keeps every block that a curator did not clear, also when the new scan says `SAFE`, an earlier scan failed, or no scanner is configured now. `kutuphane skill show` shows the copy (`carried_from`), and one `skill clear` lifts all copies. Migration `022_skill_block_carry.sql`; after `migrate`, run `kutuphane skill rescan` once ([#110](https://github.com/ekaynac/kutuphane/pull/110)).
- A note that cites a passage of a blocked skill, or that is derived from such a note, is handled as `ai_input: n` for model readers: `query_notes`, `neighbours`, a note in `open_citation` and the `propose_note` candidates give `text: null` with `withheld`. The decision export withholds its text, options and choice for every reader ([#110](https://github.com/ekaynac/kutuphane/pull/110)).
- The last rights check before a delivery and the skill block check are one database statement for files, passages, answers and notes, so a concurrent change cannot give a delivery that no state permitted ([#110](https://github.com/ekaynac/kutuphane/pull/110)).
- A SkillSpector report that is larger than 8 MiB, nested deeper than 64 levels, or has a NUL, a lone surrogate, NaN or infinity is a failed scan that blocks; the ingest no longer stops ([#110](https://github.com/ekaynac/kutuphane/pull/110)).
- `deploy/skillspector/install.sh` installs the build backend (hatchling and its dependencies, `deploy/skillspector/build-requirements.txt`) with hash checks, installs wheels only, and builds SkillSpector without build isolation. `SKILLSPECTOR_WHEELS=<folder>` installs without network. It needs Python 3.12 or 3.13 ([#110](https://github.com/ekaynac/kutuphane/pull/110)).
- kstd rule 4: a later loosening from an issuer without trust for that kind, scope and action no longer replaces the same issuer's restriction; the restriction stays in force. Four conformance cases are added ([#110](https://github.com/ekaynac/kutuphane/pull/110)).

### Skill scan (SkillSpector, D71)

- Optional: `deploy/skillspector/install.sh` installs the pinned SkillSpector 2.13.1 (tag tarball sha256 checked) into its own environment. With `KUTUPHANE_SKILLSPECTOR_BIN`, `ingest`, `approve-import` and `skill rescan` scan each skill folder with `--no-llm` and record the result as a curator proposal; `receive` shows it as a finding ([#109](https://github.com/ekaynac/kutuphane/pull/109)).
- `DO_NOT_INSTALL`, a scan that does not cover the whole skill, or a failed scan blocks the skill for agents at once, also with `activate` (`read_document`, `open_citation`, search, answers). `SAFE` gives no right; `not_scanned` does not block ([#109](https://github.com/ekaynac/kutuphane/pull/109)).
- New commands: `kutuphane skill show`, `kutuphane skill rescan`, and `kutuphane skill clear` (a curator with `curate` and `KUTUPHANE_CURATOR_DSN`; recorded). A new SkillSpector version marks old results stale. Migration `021_skill_scan.sql`: after `migrate`, apply `deploy/db-roles.sql` again ([#109](https://github.com/ekaynac/kutuphane/pull/109)).

### kstd (draft 0.3, D74)

- `kutuphane kstd-init` states no `ai_use` term: until you state the terms, no file is indexed or sent to a model. It writes `standard: kstd/0.3`; a `kstd/0.2` manifest is still accepted, and `issued` is optional ([#108](https://github.com/ekaynac/kutuphane/pull/108)).
- An unknown field, `assisted` without `reviewed_by`, `tool` without a complete `software_agent`, and `reviewed_by` or `software_agent` for another origin no longer refuse the book. The claim is not trusted (the field is ignored, or the origin counts as `unknown`), `kstd-check` warns, and the item `notices` show the same text. The error for a wrong `ai_use` value is now "ai_use terms take y or n" ([#108](https://github.com/ekaynac/kutuphane/pull/108)).
- The standard has a minimal core (envelope, `ai_use.search` and `ai_use.ai_input`, origin with the default `unknown`), and the other fields are profiles. In the decision rule, a restriction from an issuer that is not trusted gives `escalate` (`restriction-untrusted`), not `deny`. See [kstd.md](kstd.md) ([#108](https://github.com/ekaynac/kutuphane/pull/108)).

### Documentation

- The user and operator guide is in `docs/guide/` (start at [index.md](index.md)), and `README.md` is a short overview with a tested quick start (D75).

## 2026-10-27

### Agent memory

- Agents can write notes to journals with `propose_note` and connect notes with `link_notes` ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- Agents can find notes with `query_notes` and `neighbours`, and `open_citation` also opens a note reference ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- A curator sets the Standing of a note with `kutuphane note standing` ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- Operators register code repositories for a journal with `kutuphane repo add` and `kutuphane repo remove`, and agents check code citations with `verify_citations` ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- `ask_library` can run as a background job, and `job_status`, `job_result` and `job_cancel` control the job ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- The MCP server supports two MCP protocol versions, and `deploy/mcp_probe.py` checks the MCP endpoint of an installation ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- `kutuphane note rollback` retires a note and each note derived from it, and it reports the deliveries, answers and exports that used them ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- Agents record how an item worked in a task with `record_outcome` or `POST /v1/outcomes`, and reads show the outcome counts ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- `kutuphane decisions export` writes the decision records of journals as JSONL, and it includes text only when `ai_input` and `train` permit it ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- Journals have a `train` right, `kutuphane journal restrict --no-train` removes it, and a restriction on a source journal also applies to the notes derived from it ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- After this upgrade, run `kutuphane migrate` and apply `deploy/db-roles.sql` again ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- A cancelled or expired background job does not store an answer, and note queries do not fail when many notes have code citations ([#102](https://github.com/ekaynac/kutuphane/pull/102)).
- `open_citation` checks the linked books again, collapsed note results keep contradicting notes, and `repo add` refuses a repository with git grafts ([#102](https://github.com/ekaynac/kutuphane/pull/102)).
- `decisions export` removes references and text when a right is lost before delivery ([#105](https://github.com/ekaynac/kutuphane/pull/105)).
- Rollback sets a note that was approved before to `retired`, and `note standing` refuses `rejected` for such a note ([#105](https://github.com/ekaynac/kutuphane/pull/105)).

### Security

- The server checks the exact token issuer (RFC 9207), and Kütüphane requires PyJWT 2.10.1 or later ([#104](https://github.com/ekaynac/kutuphane/pull/104)).

### Knowledge standard (kstd)

- The reference decision rule requires `ai_use.search: y` for search, checks personal data for `infer` to a cloud destination, and applies `local_only` to `cloud` and `cloud:*` destinations ([#103](https://github.com/ekaynac/kutuphane/pull/103)).

### Design and research

- Scope review, vision 1.0, the R1 agent memory design ([../24-r1-agent-memory-design.md](../24-r1-agent-memory-design.md)), decisions D69–D75 and shared internal contracts for feature modules ([#97](https://github.com/ekaynac/kutuphane/pull/97), [#98](https://github.com/ekaynac/kutuphane/pull/98), [#99](https://github.com/ekaynac/kutuphane/pull/99), [#100](https://github.com/ekaynac/kutuphane/pull/100), [#106](https://github.com/ekaynac/kutuphane/pull/106)).

## 2026-10-26

### Search and answers

- Answers accept grouped citations such as `[2,3,5]` and `[2-4]` ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- Search and ask accept scope filters (`--book`, `--path`, `--origin`, `--current-only` on the CLI, and the same filters on HTTP and MCP), and the filters only make the result smaller ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- The answer uses the language of the question ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- For a question in a different language, Kütüphane translates the question and reranks each passage in its own language ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- Questions about recent items rank by relevance and date ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- Answers are faster: on the 8 pilot questions, the mean time fell from 134 s to 63 s ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- A translated search checks the rights on all books again before a model call ([#96](https://github.com/ekaynac/kutuphane/pull/96)).
- Kütüphane checks the query length before the embedding call, and the query cache has a byte limit ([#96](https://github.com/ekaynac/kutuphane/pull/96)).
- An invalid citation group makes the answer fail, and recency ranking uses only validated dates ([#96](https://github.com/ekaynac/kutuphane/pull/96)).

### Indexing and ingest

- Wrong embedding settings stop `ingest` before publication, and an index failure after publication makes `ingest` exit with code 3 ([#92](https://github.com/ekaynac/kutuphane/pull/92)).
- Kütüphane tries a failed embedding batch again with backoff ([#92](https://github.com/ekaynac/kutuphane/pull/92)).
- `kutuphane index` uses the stored vector again when the text, model and width did not change ([#92](https://github.com/ekaynac/kutuphane/pull/92)).
- `kutuphane index` has `--batch`, `--batch-chars` and `--concurrency`, with lower defaults (8 passages, 8,000 characters) ([#92](https://github.com/ekaynac/kutuphane/pull/92)).
- Kütüphane embeds a passage that is longer than the embedding limit as a 24,000-character prefix and marks the vector as truncated ([#66](https://github.com/ekaynac/kutuphane/pull/66)).
- The number of characters in one embedding batch has a limit ([#65](https://github.com/ekaynac/kutuphane/pull/65)).

### Knowledge standard (kstd)

- kstd has a `rejected` acceptance state, and the reference rule shows rejected items only in the history view ([#90](https://github.com/ekaynac/kutuphane/pull/90)).
- `kstd-init` and `kstd-check` accept `--accept-finding` ([#65](https://github.com/ekaynac/kutuphane/pull/65)).
- A refused `kstd-init` does not leave an empty `kstd.yaml`, and `kstd-init` writes non-ASCII names as readable text ([#65](https://github.com/ekaynac/kutuphane/pull/65)).

### Design and research

- Pilot 1 report, labelling v5 pages, gold sets and proposers, labelling page access fixes, and decisions D64–D68 ([#60](https://github.com/ekaynac/kutuphane/pull/60), [#61](https://github.com/ekaynac/kutuphane/pull/61), [#62](https://github.com/ekaynac/kutuphane/pull/62), [#63](https://github.com/ekaynac/kutuphane/pull/63), [#64](https://github.com/ekaynac/kutuphane/pull/64), [#82](https://github.com/ekaynac/kutuphane/pull/82), [#83](https://github.com/ekaynac/kutuphane/pull/83), [#84](https://github.com/ekaynac/kutuphane/pull/84), [#85](https://github.com/ekaynac/kutuphane/pull/85), [#86](https://github.com/ekaynac/kutuphane/pull/86), [#87](https://github.com/ekaynac/kutuphane/pull/87), [#88](https://github.com/ekaynac/kutuphane/pull/88), [#89](https://github.com/ekaynac/kutuphane/pull/89), [#91](https://github.com/ekaynac/kutuphane/pull/91), [#95](https://github.com/ekaynac/kutuphane/pull/95)).

## 2026-10-23

### Knowledge standard (kstd)

- The origin `tool` needs a complete `software_agent`, and signed packages list tool-made files in `tool_made`, not in `ai_generated` ([#57](https://github.com/ekaynac/kutuphane/pull/57)).
- Validation of tool metadata is stricter ([#58](https://github.com/ekaynac/kutuphane/pull/58)).

### Design and research

- Program-output origin options (D62), the labelling v4 rule proposer and page, the Qwen proposer and its results ([#54](https://github.com/ekaynac/kutuphane/pull/54), [#55](https://github.com/ekaynac/kutuphane/pull/55), [#56](https://github.com/ekaynac/kutuphane/pull/56), [#59](https://github.com/ekaynac/kutuphane/pull/59)).

## 2026-10-22

### Ingest

- Search includes these formats: `.txt`, `.json`, `.jsonl`, `.ndjson`, `.yaml`, `.toml`, `.sh`, `.ts`, `.js`, `.py`, `.html`, `.xml`, `.csv` and `.mdc` ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- Kütüphane keeps a file that it cannot extract in quarantine: it stores and lists the file, but it does not index it ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- A credential scan refuses a book with credential-like file names or text ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- Ingest includes allowlisted agent folders (for example `.claude/`, `.cursor/rules`, `.agents/`, `.codex/`), and agents still need `activate` to receive instructions ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- You must publish your books again, because the reader and chunker versions changed ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- The credential scan also reads JSON keys, code literals and extracted text, and `ingest --accept-finding` accepts one reviewed finding and records it in the publication ([#53](https://github.com/ekaynac/kutuphane/pull/53)).
- Kütüphane splits JSONL records only at `\n` ([#53](https://github.com/ekaynac/kutuphane/pull/53)).

### Knowledge standard (kstd)

- A `kstd.yaml` file in a folder controls publication, search, AI input, export and the item information that results show ([#42](https://github.com/ekaynac/kutuphane/pull/42)).
- `kutuphane kstd-init` writes a starting manifest, and `kutuphane kstd-check` validates a manifest ([#42](https://github.com/ekaynac/kutuphane/pull/42)).
- `kutuphane export` needs `--legal-basis` when files contain personal data ([#42](https://github.com/ekaynac/kutuphane/pull/42)).
- kstd adds the origin `assisted` with `reviewed_by`, the personal data value `synthetic`, three-state `ai_use` values and DPV legal-basis codes on export ([#46](https://github.com/ekaynac/kutuphane/pull/46)).
- Signed packages list the `ai_generated` and `reviewed` files ([#46](https://github.com/ekaynac/kutuphane/pull/46)).
- MCP callers and agents do not receive the text of passages without `ai_input` ([#44](https://github.com/ekaynac/kutuphane/pull/44)).
- Kütüphane refuses duplicate YAML keys and merge keys, and it checks licenses with the SPDX expression grammar ([#44](https://github.com/ekaynac/kutuphane/pull/44)).
- The reference rule follows the full input lineage and denies when an input is missing ([#53](https://github.com/ekaynac/kutuphane/pull/53)).

### Deployment

- `deploy/compose.local-models.yaml` (profile `local-models`) runs a local CPU embedder and reranker and a chat proxy behind LLMDAP ([#49](https://github.com/ekaynac/kutuphane/pull/49)).
- The local model server limits request size, read time and concurrent requests ([#53](https://github.com/ekaynac/kutuphane/pull/53)).

### License

- The code license is Apache-2.0, and the specification text license is CC-BY-4.0 ([#41](https://github.com/ekaynac/kutuphane/pull/41)).

### Design and research

- Landscape study, contribution guide, real-use plan, labelling v4 dataset and decisions D59–D61 ([#45](https://github.com/ekaynac/kutuphane/pull/45), [#47](https://github.com/ekaynac/kutuphane/pull/47), [#48](https://github.com/ekaynac/kutuphane/pull/48), [#50](https://github.com/ekaynac/kutuphane/pull/50), [#52](https://github.com/ekaynac/kutuphane/pull/52)).

## 2026-10-21

### Knowledge standard (kstd)

- `kstd/reference/` has conformance cases for the decision rule and a reference evaluator ([#40](https://github.com/ekaynac/kutuphane/pull/40)).

## 2026-10-20

### Design and research

- Decision D55, the vision draft, the research map and the knowledge standard draft ([#36](https://github.com/ekaynac/kutuphane/pull/36), [#37](https://github.com/ekaynac/kutuphane/pull/37), [#38](https://github.com/ekaynac/kutuphane/pull/38), [#39](https://github.com/ekaynac/kutuphane/pull/39)).

## 2026-10-15

### Search and answers

- Search reranks the top 30 hits through the LLMDAP rerank route, and a failed rerank keeps the hybrid order ([#29](https://github.com/ekaynac/kutuphane/pull/29)).
- HTTP, MCP, the CLI and answers use the same retrieval path ([#29](https://github.com/ekaynac/kutuphane/pull/29)).
- A local-only book never goes to a cloud rerank route ([#29](https://github.com/ekaynac/kutuphane/pull/29)).
- Answers do not use a score threshold, because a reranker can give negative scores to useful passages ([#32](https://github.com/ekaynac/kutuphane/pull/32)).

### Deployment

- Compose runs LLMDAP, and each pair of services that must talk has its own internal network (`db`, `web`, `gateway`, `models`) ([#30](https://github.com/ekaynac/kutuphane/pull/30)).
- `deploy/llmdap/README.md` gives the LLMDAP setup steps ([#30](https://github.com/ekaynac/kutuphane/pull/30)).
- The compose profile `decision-models` runs the Laya service, and `deploy/compose.hosted.yaml` gives only LLMDAP an outbound network ([#34](https://github.com/ekaynac/kutuphane/pull/34)).

### Design and research

- Ontology v2 draft (D53), block rule, rule proposer, labelling v2 and shadow labelling fixes ([#27](https://github.com/ekaynac/kutuphane/pull/27), [#31](https://github.com/ekaynac/kutuphane/pull/31), [#33](https://github.com/ekaynac/kutuphane/pull/33), [#35](https://github.com/ekaynac/kutuphane/pull/35)).

## 2026-10-14

### Deployment

- `deploy/llmdap_contract.py` does not follow redirects, fails when the audit export fails, and tests the real shared secret when `LLMDAP_GATEWAY_TRUST_SECRET` is set ([#28](https://github.com/ekaynac/kutuphane/pull/28)).

### Design and research

- Labelling guide in STE English ([#26](https://github.com/ekaynac/kutuphane/pull/26)).

## 2026-10-13

### Search and answers

- Search combines full-text and vector ranking, with embeddings from LLMDAP ([#24](https://github.com/ekaynac/kutuphane/pull/24)).
- `ingest` and `approve-import` embed the new version, and `kutuphane index` adds missing vectors to a book ([#24](https://github.com/ekaynac/kutuphane/pull/24)).
- When the query embedding fails, search uses full text only ([#24](https://github.com/ekaynac/kutuphane/pull/24)).
- Core authenticates to LLMDAP with its own subject key ([#24](https://github.com/ekaynac/kutuphane/pull/24)).

### Deployment

- `deploy/llmdap_contract.py` checks Core against a real LLMDAP gateway; run it at install time and after each LLMDAP upgrade ([#25](https://github.com/ekaynac/kutuphane/pull/25)).

### Design and research

- M0 model measurement on GPU and CPU ([#23](https://github.com/ekaynac/kutuphane/pull/23)).

## 2026-10-12

### Catalog and access

- `kutuphane migrate`, `ingest` and `show` publish and list book versions with stable version ids ([#5](https://github.com/ekaynac/kutuphane/pull/5)).
- `kutuphane grant`, `revoke`, `delegate`, `undelegate` and `read` control and use access, and each decision goes to the access log ([#6](https://github.com/ekaynac/kutuphane/pull/6)).
- An agent needs `activate` to receive agent instruction files, and the file type and name checks ignore case and separators ([#6](https://github.com/ekaynac/kutuphane/pull/6), [#7](https://github.com/ekaynac/kutuphane/pull/7)).
- Kütüphane decides access in one statement, normalizes frontmatter before classification, and the CLI command `cat` is removed ([#8](https://github.com/ekaynac/kutuphane/pull/8)).
- A refused write does not stay in the database ([#18](https://github.com/ekaynac/kutuphane/pull/18)).

### Identity and audit

- Kütüphane verifies JWT access tokens against a JWKS file, and `kutuphane whoami` shows the verified identity ([#9](https://github.com/ekaynac/kutuphane/pull/9)).
- `kutuphane explain` shows the unified audit for a correlation id, and `explain --answer` does this for an answer id ([#9](https://github.com/ekaynac/kutuphane/pull/9), [#14](https://github.com/ekaynac/kutuphane/pull/14)).

### Search and answers

- `kutuphane search` searches the books that the caller can read, and results carry versioned citation handles ([#10](https://github.com/ekaynac/kutuphane/pull/10)).
- `kutuphane ask` answers with `[n]` citations, and `kutuphane reopen` shows a stored answer again without a model call ([#12](https://github.com/ekaynac/kutuphane/pull/12)).
- Only the same caller, or the user that the answer was made for, can reopen an answer ([#13](https://github.com/ekaynac/kutuphane/pull/13)).
- Kütüphane checks all source books again before it returns an answer, and one invalid citation rejects the answer ([#14](https://github.com/ekaynac/kutuphane/pull/14)).
- A search over many books checks all rights in one statement and runs again once when rights change ([#11](https://github.com/ekaynac/kutuphane/pull/11)).
- A model call to a cloud route needs `cloud_ok` on every source book ([#11](https://github.com/ekaynac/kutuphane/pull/11)).
- Full-text ranking is better: recall@10 rose from 0.245 to 0.563 on the test set ([#21](https://github.com/ekaynac/kutuphane/pull/21)).

### HTTP API, MCP and web UI

- Core serves an HTTP API under `/v1/` and an MCP endpoint at `/mcp`, with the same functions behind both ([#15](https://github.com/ekaynac/kutuphane/pull/15)).
- Core serves a reader UI at `/ui`, with a strict Content Security Policy on each response ([#16](https://github.com/ekaynac/kutuphane/pull/16)).
- Core does not start when database migrations are pending ([#16](https://github.com/ekaynac/kutuphane/pull/16)).
- `kutuphane dev-keys` and `kutuphane dev-token` make development tokens, and they work only with `KUTUPHANE_DEV=1` ([#16](https://github.com/ekaynac/kutuphane/pull/16)).
- `/v1/feedback` and the MCP tool `record_runbook_feedback` record runbook outcomes for one content version ([#17](https://github.com/ekaynac/kutuphane/pull/17)).
- MCP tool errors use the HTTP error mapping and do not show internal details ([#22](https://github.com/ekaynac/kutuphane/pull/22)).
- The web UI removes the data of the previous user after sign-out ([#22](https://github.com/ekaynac/kutuphane/pull/22)).

### Packages

- `kutuphane keygen`, `trust`, `untrust`, `export`, `receive`, `approve-import`, `reject-import` and `imports` move books between installations as signed packages ([#19](https://github.com/ekaynac/kutuphane/pull/19)).
- Package approval locks the trusted key, and Kütüphane records each failed or refused package ([#22](https://github.com/ekaynac/kutuphane/pull/22)).

### Deployment

- The repository has a Dockerfile and compose networks, and `deploy/egress_probe.py` checks that Core reaches only allowed services ([#15](https://github.com/ekaynac/kutuphane/pull/15), [#22](https://github.com/ekaynac/kutuphane/pull/22)).

### Design and research

- Direction decisions D1–D48, product brief, roadmap, M1 definition and status, and the first labelling page ([#1](https://github.com/ekaynac/kutuphane/pull/1), [#2](https://github.com/ekaynac/kutuphane/pull/2), [#3](https://github.com/ekaynac/kutuphane/pull/3), [#4](https://github.com/ekaynac/kutuphane/pull/4), [#20](https://github.com/ekaynac/kutuphane/pull/20)).
