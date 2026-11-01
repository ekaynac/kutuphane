# Changelog

This file lists the changes that users and operators can see, newest first.
Each date has the pull requests (PRs) that were merged on that date.
Rule D75: each feature PR updates the user documentation and adds its entry here.
Internal work (decisions, research, labelling) is in one "Design and research" line for each date.
For the terms, read [concepts.md](concepts.md).

## Unreleased

### Guide cut (W1-6, D80)

- Changed (documentation): the guide is about 31,000 words (before: 57,000). Each page is for one role. Design history now links to `docs/24`, `docs/25`, `docs/research` and `docs/08`. Old changelog entries are one line each, with the PR link. No command, setting, MCP tool, HTTP route or error text was removed.
- Fixed (README quick start): `kutuphane grant … curate user:ayse` now has `KUTUPHANE_CURATOR_DSN`. Without it, the command stops with `KUTUPHANE_CURATOR_DSN is not set (the curator credential)`.

### Refactor wave 2 (W2-2 to W2-5)

- Changed: `open_citation` and `GET /v1/citation` check a passage handle as the note tools do. A malformed handle gets `400` `malformed passage handle` (before: `malformed citation handle`) ([http-api.md](http-api.md)).
- Changed: `kutuphane note rollback` with a malformed `--curator` gives `a curator is a user:` (before: `invalid curator: …`).
- Removed (internal): `llmdap.systemone`, `SYSTEMONE_PATH`, `catalog.whole_profile`, `notes.item_info`. The LLMDAP `systemone` routes stay.

### Two compose files (W1-4)

- Changed: `compose.yaml` is the light install (Postgres, Core, ingress). `deploy/compose.full.yaml` is the full stack, with the profiles `app`, `dev-models`, `decision-models`, `local-models`, `gpu-rerank` and `curator`. `deploy/compose.light.yaml`, `deploy/compose.local-models.yaml`, `deploy/compose.curator.yaml` and `deploy/compose.hosted.yaml` are removed. Container, volume and network names stay ([install.md](install.md#full-stack)).
- **Action, full stack:** put `COMPOSE_FILE=deploy/compose.full.yaml` in `.env`. Give absolute paths in `KUTUPHANE_OIDC_JWKS_FILE` and `KUTUPHANE_REPO_DIR` (a relative path is read from `deploy/`). The defaults are the local models (`routes.local.json`); for other models set the route settings and the new `KUTUPHANE_LLMDAP_ROUTES` (`routes.json` for stub models) in `.env`. `BRIDGE_ROUTES_FILE` has no effect now. Hosted decision model: `KUTUPHANE_LLMDAP_OFFLINE=false` and `KUTUPHANE_LLMDAP_ROUTES=routes.hosted.json`.
- **Action, light install:** put `COMPOSE_PROJECT_NAME=kutuphane-light` in `.env` to keep the volume. `KUTUPHANE_DB_PORT` and `KUTUPHANE_PORT` are removed (ports `55432` and `8080`). A relative JWKS or repo path is read from the repository root.
- Changed: Postgres is always on the internal network `curator-db`, LLMDAP on `outbound`. The next `up` recreates the two containers once; data stays. A missing curator web setting stops only curator web.

### Journal export (R3)

- New: `kutuphane journal export <journal> --out FILE --by <principal>` writes a journal as JSONL for `note import`, with Standing history, writers, outcomes and `ai_use`. A `restricted` journal is refused ([operations.md](operations.md#export-a-journal), [agent-memory.md](agent-memory.md#export-a-journal-backup-git)).
- Changed: `note import` accepts `standing_history`, `writers`, `outcomes`, `ai_use` and `withheld`; `ai_use` only narrows rights; a `withheld` record is refused.

### Expiry of unused evidence and outcome filters (R1, R2)

- New: `kutuphane note expire [--days N] [--dry-run]` (`KUTUPHANE_EVIDENCE_EXPIRY_DAYS`, default 90) expires old `evidence` notes (reason `expired`). Run it from a timer ([operations.md](operations.md#expiry-of-unused-evidence-r1)).
- New: `min_passed` and `exclude_failed` on `query_notes` and `GET /v1/notes` ([mcp.md](mcp.md#512-query_notes)). Migration `049_evidence_expiry.sql`.

### Remove the decider and delegated curate (D73)

- Removed: `kutuphane decider …`, `kutuphane delegation …`, the curator web **Auto-approval** tab (`/delegations`, `GET /api/delegations`, `GET /api/delegations/{id}`), the `delegate` and `end_delegation` acts, `deploy/db-roles-decider.sql`, `deploy/deciders/`, `KUTUPHANE_DECIDER_DSN`, `KUTUPHANE_DECIDER_LLMDAP_KEY`, `KUTUPHANE_DECIDER_BOOKS`, `KUTUPHANE_DELEGATION_MIN_SHADOW`. Only a person approves a note ([security.md](security.md#delegated-curate-d73-removed)).
- Changed: act receipts have no `suggestions` or `sample`; `kutuphane curator report` has no `delegations`.
- **Action:** run `deploy/db-roles-curator.sql` again; stop any `kutuphane decider run` timer; drop the role: `DROP OWNED BY kutuphane_decider; DROP ROLE kutuphane_decider;`.

### Vision 1.2 and "memory is data" (D80)

- Design and research: D80 in `docs/01`, vision 1.2 in `docs/23`; [agent-memory.md](agent-memory.md) §13: notes reach a model only as tool results.

### Astra review #21 fixes

- Fixed: an `overlap` successor must hold the whole old passage text with operators and case; else the citation is `stale`. Curator cards show an `applies_to` bound. Migration `047_note_applies_to.sql` keeps late feedback rows.
- **Action:** migration `048_passage_map_operators.sql`; after `migrate`, run `kutuphane reindex-map <book>` for each book whose passages notes cite.

### `curate` grant in the database; small refactor (wave 1)

- Fixed: the app role cannot insert a `curate` row into `grant_tuple`. **Action:** run `deploy/db-roles.sql` again ([security.md](security.md#curation-boundary)).
- Changed: a malformed curator principal gives `a curator is a user:` (also `kutuphane skill clear`).

### Catalog read and publication facts (#159, #160)

- New: `GET /v1/books` and `list_books`; `GET /v1/books/{book}/files` and `list_files` ([http-api.md](http-api.md#72-get-v1books), [mcp.md](mcp.md#518-list_books)) ([#159](https://github.com/ekaynac/kutuphane/issues/159)).
- New: each publication records `approved_by` and `channel` (`ingest --by`, or `import`). Migration `045_publication_facts.sql` ([#160](https://github.com/ekaynac/kutuphane/issues/160)).

### Identity and trace (#156, #157, #165)

- New: a caller correlation id in `X-Correlation-Id` (MCP `_meta["kutuphane/correlation-id"]`), returned with `X-Caller-Correlation-Id`; malformed is `400` (MCP `-32602`) ([http-api.md](http-api.md#15-correlation-id)).
- New: `KUTUPHANE_OIDC_ISSUERS` for more token issuers ([operations.md](operations.md#more-than-one-token-issuer)).
- Changed: each model call sends `x-llmdap-purpose` ([operations.md](operations.md#a-shared-llmdap-d76)). Migration `046_caller_correlation.sql`; then apply `deploy/db-roles.sql`.

### Agent memory: one Scope context; runbook feedback removed (#164, D78)

- New: `applies_to` on `propose_note` and `POST /v1/notes`; `platform` and `version` in the note query context ([mcp.md](mcp.md#59-propose_note)).
- Removed: `record_runbook_feedback`, `POST /v1/feedback` and `GET /v1/feedback`; use `record_outcome`. MCP and HTTP section numbers moved up one.

### Frozen list and `curate` grant credential (D78, D79)

- Changed: `kutuphane grant … curate …` needs `KUTUPHANE_CURATOR_DSN`; else exit code 2 ([security.md](security.md#curation-boundary)). Role and Time basis are no longer facets ([concepts.md](concepts.md#kinds)).
- Design and research: D78, D79, vision 1.1, kstd draft 0.3.1.

### Note query: folder scope, `refs` and `paths` (#152, #155, #153)

- Fixed: a folder `path` matches a scope glob only when a file below it can match ([#152](https://github.com/ekaynac/kutuphane/issues/152)).
- New: `refs` (1–50 note references, item key `standing_seq`) and `paths` (1–20 context paths) on `query_notes` and `GET /v1/notes` ([mcp.md](mcp.md#512-query_notes)) ([#155](https://github.com/ekaynac/kutuphane/issues/155), [#153](https://github.com/ekaynac/kutuphane/issues/153)).

### Astra review #20 fixes

- Changed: package status gives `diff` only with `read` on the book; `licence_notice` hides unreadable paths (`unreadable`); an `overlap` successor must hold the whole old text.
- **Action:** migration `044_passage_map_overlap.sql`; after `migrate`, run `kutuphane reindex-map <book>`.

### Scope: `applies_to` and the request context (#137, #142, #138)

- New: kstd `applies_to` mapping form `{platform: [...], version: "<range>"}` ([kstd.md](kstd.md#what-kütüphane-does-with-each-field)) ([#137](https://github.com/ekaynac/kutuphane/issues/137)).
- New: `--platform` and `--version` on search and ask (HTTP `platform`, `version`; `context: {platform, version}`); each `item` has `scope`: `unbounded`, `match` or `needs_context` ([operations.md](operations.md#scope-filters-g14)).
- New: one book per scope ([operations.md](operations.md#one-book-per-scope-138)) ([#138](https://github.com/ekaynac/kutuphane/issues/138)). Pilot 2 question 6 measured ([#142](https://github.com/ekaynac/kutuphane/issues/142)).

### Restart policies and the dependency check (#141)

- New: `restart: unless-stopped` on the main services, `restart: on-failure:5` on `reranker-gpu` ([install.md](install.md#reboot-and-restart)). `GET /v1/health` gives `db`, `llmdap`, `embedding`, `rerank`, `chat`, `ok` ([http-api.md](http-api.md#33-get-v1health)) ([#141](https://github.com/ekaynac/kutuphane/issues/141)).

### Retrieval status (#136)

- New: each search and answer has `retrieval: {embedding, translation, rerank}` (`ok`, `failed`, `skipped`); MCP `_meta["kutuphane/retrieval"]`; also in `GET /v1/answers/{id}`. Migration 042 ([mcp.md](mcp.md#45-retrieval-status), [operations.md](operations.md#degraded-searches-and-failed-model-calls-136)) ([#136](https://github.com/ekaynac/kutuphane/issues/136)).

### Notes follow a re-index (#140)

- Fixed: note citations and links follow a re-index through `passage_map` (`exact`, `overlap`, none). Citations have `status`: `current`, `moved` (`moved_to`, `match`) or `stale`; `neighbours` edges have `original` ([operations.md](operations.md#re-index-and-note-citations)) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- New: `kutuphane reindex-map <book> [--dry-run]`. **Action:** migration `040_passage_map.sql`; apply the role scripts again, then run `reindex-map` for each book whose passages notes cite.

### Packages over HTTP and MCP; license unknown (#139, #143)

- New: `POST /v1/packages`, `submit_package`, `GET /v1/packages/{id}`, `package_status` (needs `propose`; `413` over the size limit). Migration 041 ([http-api.md](http-api.md#12-packages), [operations.md](operations.md#packages-from-an-application-http-and-mcp-139)) ([#139](https://github.com/ekaynac/kutuphane/issues/139)).
- Changed: `license: unknown` permits derivation with `licence_notice`; `export` refuses such a book ([kstd.md](kstd.md#what-kütüphane-does-with-each-field)) ([#143](https://github.com/ekaynac/kutuphane/issues/143)).

### Curator web in plain words (#135)

- Changed: plain-word tabs, cards, chips and receipts on the phone page; the queue gives `path` and `excerpt` ([operations.md](operations.md#on-the-phone-curator-web-d72)) ([#135](https://github.com/ekaynac/kutuphane/pull/135)).

### kstd-check findings and vector counters (#134)

- Fixed: `kstd-check --deny-names <file>` lists personal-data findings and a count line `personal-data findings: <rule> <n>, … (<files> files)`.
- Changed: `vectors_added` is now `vectors_embedded`; a script must read `vectors_embedded` + `vectors_reused` ([operations.md](operations.md#3-indexing)) ([#134](https://github.com/ekaynac/kutuphane/pull/134)).

### Curator web on the host (#132)

- New: curator web as a host systemd user service behind `tailscale serve` ([install.md](install.md#host-install-with-tailscale-serve)) ([#132](https://github.com/ekaynac/kutuphane/pull/132)).

### GPU reranker (#131; G26)

- New: profile `gpu-rerank`, route `rerank-gpu`; set `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu`. Restart LLMDAP once after the upgrade ([install.md](install.md#gpu-reranker)) ([#131](https://github.com/ekaynac/kutuphane/pull/131)).

### Astra review #19 fixes

- Fixed: fixed function search paths; note parts are written only at creation; `quoted_records` are decided with the hits; `approve-import` applies the cloud gate (`--accept-finding`) ([security.md](security.md#curation-boundary)).
- **Action:** migrations `038_function_search_path.sql`, `039_note_parts_at_creation.sql`; apply the role scripts again. Review: [../08-m1-notes.md](../08-m1-notes.md) ([#130](https://github.com/ekaynac/kutuphane/pull/130)).

### Pilot 1 gaps G13, G15 (#129)

- Changed: `ask` citations have `line` and `record`. `KUTUPHANE_OIDC_AUDIENCE` defaults to `kutuphane`; an empty `KUTUPHANE_CONFIRM_HOURS` is 24. `KUTUPHANE_LLMDAP_ROUTE_CLASS` has no default outside compose ([#129](https://github.com/ekaynac/kutuphane/pull/129)).

### Records that a passage repeats (#128)

- New: search hits have `quoted_records`; answers add the record to the evidence ([concepts.md](concepts.md#records-that-a-passage-repeats)). Migration `037_record_value.sql`; apply `deploy/db-roles.sql` ([#128](https://github.com/ekaynac/kutuphane/pull/128)).

### A size budget for agent search results (#121)

- New: `max_chars` (80–4800) on `search_library` and `GET /v1/search`; results have `truncated`. Without LLMDAP, `tools/list` leaves out the ask and job tools. Tool descriptions name the grant ([mcp.md](mcp.md#51-search_library)) ([#127](https://github.com/ekaynac/kutuphane/pull/127)).

### Security review #18 fixes (#125)

- Fixed: handling labels name only readable books (`unnamed_sources`); linear HTML comment cut; skills reads use the served version and log refusals; `skill://` HTML gives `text/plain`; `read_document` checks the whole skill. Migration `033_skill_frontmatter.sql`; apply `deploy/db-roles.sql` ([mcp.md](mcp.md#44-handling-labels-in-_meta)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).

### Pilot 2 gaps G34, G35 (#124)

- New: `kutuphane kstd-init <copy> --source-repo <repo> [--commit <rev>]` proposes origin from git ([kstd.md](kstd.md#origin-proposals-from-a-source-repository)). Personal-data and fleet-data findings (`--deny-names <file>`, `--accept-finding <path>@sha256:<digest>:<rule>`) ([operations.md](operations.md#personal-data-and-fleet-data-findings)). Migration `032_data_findings.sql` ([#124](https://github.com/ekaynac/kutuphane/pull/124)).

### MCP Skills (SEP-2640) and handling labels (#123)

- New: `skills/list`, `skills/get`, `resources/read` of `skill://…` ([mcp.md](mcp.md#10-skills-sep-2640)); `_meta["kutuphane/handling"]`; `deploy/mcp_probe.py --skill` ([#123](https://github.com/ekaynac/kutuphane/pull/123)).

### Retrieval re-check (#122)

- Fixed: the question translation uses `temperature` 0 (G19) ([../18-pilot-radar.md](../18-pilot-radar.md)) ([#122](https://github.com/ekaynac/kutuphane/pull/122)).

### Security review #17 fixes (#120)

- Fixed: decider sampling is set by the database; a live origin confirmation stays until its confirmer withdraws it; the confirm page checks `read` first. The decider read journals after `kutuphane grant book:<journal> read agent:kutuphane-decider`. Migration `029_curator_review17.sql` (needs `pgcrypto`) ([#120](https://github.com/ekaynac/kutuphane/pull/120)).

### Pilot 2 gaps G27–G33 (#118)

- Changed: markdown chunker version 5 (ingest markdown books again); vectors are copied across profiles; `neighbours` gives `cites` edges (migration `028_note_citation_passage.sql`); a journal in the `book` filter gives `journal: use query_notes …`; answer prompt fixes ([../26-pilot-2.md](../26-pilot-2.md)) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).

### Security review #16 fixes (#116)

- Fixed: a phone rule approval lists `retires`; a revoked passkey ends its sessions. New: `kutuphane curator end-sessions <user>`, `kutuphane curator cancel-enrollment <id>`. Migration `026_curator_review16.sql`; apply `deploy/db-roles-curator.sql` ([#116](https://github.com/ekaynac/kutuphane/pull/116)).

### Origin confirmation, model suggestions and the curator queue (#117)

- New: "my words" confirmation (`confirm_origin`, `GET /v1/notes/{book}/{id}/confirmation`, `KUTUPHANE_CURATOR_URL`) ([mcp.md](mcp.md#515-confirm_origin)). New: the curator queue (`GET /api/queue`, `GET /api/note/{book}/{id}` replace `GET /api/pending`), `kutuphane curator queue --curator user:<name>`, `kutuphane curator report --from D1 --to D2`; item key `approved_by`. New then (removed later, D73): `kutuphane decider run --spec FILE`, `kutuphane decider run|spec`, `kutuphane decider spec`, `kutuphane delegation list|report|agreement|end`. Migrations `024_origin_confirmation.sql`, `025_curate_delegation.sql` ([#117](https://github.com/ekaynac/kutuphane/pull/117)).

### Curator web with passkeys (#115, #113)

- New: curator web; `kutuphane curator enroll|passkeys|revoke-passkey|verify-acts|web`; `deploy/curator_probe.py`; dependency `webauthn` 3.0.1. Migration `023_curator_passkey.sql`; apply `deploy/db-roles.sql` and `deploy/db-roles-curator.sql` ([install.md](install.md#curator-web)) ([#115](https://github.com/ekaynac/kutuphane/pull/115)). Design: [../25-curator-queue-passkey-design.md](../25-curator-queue-passkey-design.md) ([#113](https://github.com/ekaynac/kutuphane/pull/113)).

### Bulk import and private journals (#112)

- New: `kutuphane note import <journal> <file.jsonl> --by <principal>` (CLI only; migration `027_note_import.sql`). Private journals: `--sensitivity restricted --egress local_only`. `kutuphane export` refuses every `restricted` book; `journal create --train y` is refused for one ([#112](https://github.com/ekaynac/kutuphane/pull/112)).

### Light install (#111)

- New: light install without LLMDAP ([install.md](install.md#light-install)). `ask_library` and `POST /v1/ask` give `503` `answers are not available: this install has no model gateway (LLMDAP); search is full text only`. `KUTUPHANE_ANSWER_MODEL` is needed only with `KUTUPHANE_LLMDAP_URL`. `deploy/egress_probe.py --light` ([#111](https://github.com/ekaynac/kutuphane/pull/111)).

### Security fixes, Astra review #15 (#110)

- Fixed: a skill block follows the skill bytes (`carried_from`); notes on a blocked skill are withheld; SkillSpector reports have size limits; `deploy/skillspector/install.sh` uses hash checks (`SKILLSPECTOR_WHEELS=<folder>`). **Action:** migration `022_skill_block_carry.sql`, then run `kutuphane skill rescan` once ([#110](https://github.com/ekaynac/kutuphane/pull/110)).

### Skill scan, SkillSpector (#109)

- New: optional SkillSpector 2.13.1 scan with `KUTUPHANE_SKILLSPECTOR_BIN`; `kutuphane skill show`, `skill rescan`, `skill clear`. Migration `021_skill_scan.sql` ([#109](https://github.com/ekaynac/kutuphane/pull/109)).

### kstd draft 0.3 (#108)

- Changed: `kstd-init` states no `ai_use` term and writes `standard: kstd/0.3`. Untrusted claims warn, not refuse. Error: "ai_use terms take y or n" ([kstd.md](kstd.md)) ([#108](https://github.com/ekaynac/kutuphane/pull/108)).

### Documentation and design

- The guide is in `docs/guide/` ([index.md](index.md)); `README.md` is a short overview (D75). Labelling v5 second reader ([../20-labelling-curation-v5.md](../20-labelling-curation-v5.md)) ([#126](https://github.com/ekaynac/kutuphane/pull/126)).

## 2026-10-27

- Agent memory: `propose_note`, `link_notes`, `query_notes`, `neighbours`, `kutuphane note standing`, `kutuphane repo add`/`repo remove`, `verify_citations`, background `ask_library` with `job_status`, `job_result`, `job_cancel`; two MCP protocol versions; `deploy/mcp_probe.py` ([#101](https://github.com/ekaynac/kutuphane/pull/101)).
- Fixes: cancelled jobs store no answer; `repo add` refuses git grafts ([#102](https://github.com/ekaynac/kutuphane/pull/102)).
- kstd reference rule: `ai_use.search: y` for search; `local_only` covers `cloud:*` ([#103](https://github.com/ekaynac/kutuphane/pull/103)).
- `kutuphane note rollback`, `record_outcome` and `POST /v1/outcomes`, `kutuphane decisions export`, journal `train` right (`kutuphane journal restrict --no-train`), exact issuer check (RFC 9207, PyJWT 2.10.1). Run `kutuphane migrate` and `deploy/db-roles.sql` ([#104](https://github.com/ekaynac/kutuphane/pull/104)).
- `decisions export` drops lost rights; rollback sets a once-approved note to `retired` ([#105](https://github.com/ekaynac/kutuphane/pull/105)).
- Design and research: scope review, vision 1.0, [../24-r1-agent-memory-design.md](../24-r1-agent-memory-design.md), D69–D75 ([#97](https://github.com/ekaynac/kutuphane/pull/97), [#98](https://github.com/ekaynac/kutuphane/pull/98), [#99](https://github.com/ekaynac/kutuphane/pull/99), [#100](https://github.com/ekaynac/kutuphane/pull/100), [#106](https://github.com/ekaynac/kutuphane/pull/106)).

## 2026-10-26

- Indexing: embedding settings checked before publication; exit code 3 on index failure; retry with backoff; vector reuse; `kutuphane index --batch`, `--batch-chars`, `--concurrency` ([#92](https://github.com/ekaynac/kutuphane/pull/92)).
- Search and answers: grouped citations (`[2,3,5]`, `[2-4]`); filters `--book`, `--path`, `--origin`, `--current-only`; answer in the question's language; cross-language rerank; recency ranking; mean answer time 134 s to 63 s ([#94](https://github.com/ekaynac/kutuphane/pull/94)).
- Translated search re-checks rights; query length check; cache byte limit ([#96](https://github.com/ekaynac/kutuphane/pull/96)).
- kstd `rejected` acceptance state ([#90](https://github.com/ekaynac/kutuphane/pull/90)).
- Long passages embed as a 24,000-character prefix ([#66](https://github.com/ekaynac/kutuphane/pull/66)).
- Embedding batch character limit; `kstd-init` and `kstd-check` accept `--accept-finding` ([#65](https://github.com/ekaynac/kutuphane/pull/65)).
- Design and research: Pilot 1 report, labelling v5, D64–D68 ([#60](https://github.com/ekaynac/kutuphane/pull/60), [#61](https://github.com/ekaynac/kutuphane/pull/61), [#62](https://github.com/ekaynac/kutuphane/pull/62), [#63](https://github.com/ekaynac/kutuphane/pull/63), [#64](https://github.com/ekaynac/kutuphane/pull/64), [#82](https://github.com/ekaynac/kutuphane/pull/82), [#83](https://github.com/ekaynac/kutuphane/pull/83), [#84](https://github.com/ekaynac/kutuphane/pull/84), [#85](https://github.com/ekaynac/kutuphane/pull/85), [#86](https://github.com/ekaynac/kutuphane/pull/86), [#87](https://github.com/ekaynac/kutuphane/pull/87), [#88](https://github.com/ekaynac/kutuphane/pull/88), [#89](https://github.com/ekaynac/kutuphane/pull/89), [#91](https://github.com/ekaynac/kutuphane/pull/91), [#95](https://github.com/ekaynac/kutuphane/pull/95)).

## 2026-10-23

- kstd origin `tool` needs `software_agent`; packages list `tool_made` ([#57](https://github.com/ekaynac/kutuphane/pull/57)).
- Stricter tool metadata validation ([#58](https://github.com/ekaynac/kutuphane/pull/58)).
- Design and research: D62, labelling v4 proposers ([#54](https://github.com/ekaynac/kutuphane/pull/54), [#55](https://github.com/ekaynac/kutuphane/pull/55), [#56](https://github.com/ekaynac/kutuphane/pull/56), [#59](https://github.com/ekaynac/kutuphane/pull/59)).

## 2026-10-22

- Code license Apache-2.0, specification CC-BY-4.0 ([#41](https://github.com/ekaynac/kutuphane/pull/41)).
- kstd: `kstd.yaml`, `kutuphane kstd-init`, `kutuphane kstd-check`; `kutuphane export --legal-basis` ([#42](https://github.com/ekaynac/kutuphane/pull/42)).
- No passage text without `ai_input` to MCP callers; duplicate YAML keys refused; SPDX license check ([#44](https://github.com/ekaynac/kutuphane/pull/44)).
- kstd origin `assisted` with `reviewed_by`, `synthetic`, three-state `ai_use`, DPV legal basis; packages list `ai_generated` and `reviewed` ([#46](https://github.com/ekaynac/kutuphane/pull/46)).
- Profile `local-models`: local CPU embedder, reranker and chat proxy ([#49](https://github.com/ekaynac/kutuphane/pull/49)).
- More formats (`.txt`, `.json`, `.jsonl`, `.ndjson`, `.yaml`, `.toml`, `.sh`, `.ts`, `.js`, `.py`, `.html`, `.xml`, `.csv`, `.mdc`); quarantine; credential scan; allowlisted agent folders (`.claude/`, `.cursor/rules`, `.agents/`, `.codex/`). Publish your books again ([#51](https://github.com/ekaynac/kutuphane/pull/51)).
- Wider credential scan; `ingest --accept-finding`; JSONL split only at `\n`; full input lineage; local model server limits ([#53](https://github.com/ekaynac/kutuphane/pull/53)).
- Design and research: landscape, contribution guide, real-use plan, labelling v4, D59–D61 ([#45](https://github.com/ekaynac/kutuphane/pull/45), [#47](https://github.com/ekaynac/kutuphane/pull/47), [#48](https://github.com/ekaynac/kutuphane/pull/48), [#50](https://github.com/ekaynac/kutuphane/pull/50), [#52](https://github.com/ekaynac/kutuphane/pull/52)).

## 2026-10-21

- `kstd/reference/` conformance cases and evaluator ([#40](https://github.com/ekaynac/kutuphane/pull/40)).

## 2026-10-20

- Design and research: D55, vision draft, research map, kstd draft ([#36](https://github.com/ekaynac/kutuphane/pull/36), [#37](https://github.com/ekaynac/kutuphane/pull/37), [#38](https://github.com/ekaynac/kutuphane/pull/38), [#39](https://github.com/ekaynac/kutuphane/pull/39)).

## 2026-10-15

- Rerank of the top 30 hits through LLMDAP; one retrieval path; local-only books never go to a cloud rerank route ([#29](https://github.com/ekaynac/kutuphane/pull/29)).
- Compose runs LLMDAP with internal networks `db`, `web`, `gateway`, `models`; `deploy/llmdap/README.md` ([#30](https://github.com/ekaynac/kutuphane/pull/30)).
- No score threshold for answers ([#32](https://github.com/ekaynac/kutuphane/pull/32)).
- Profile `decision-models` (Laya); outbound network only for LLMDAP ([#34](https://github.com/ekaynac/kutuphane/pull/34)).
- Design and research: ontology v2 (D53), labelling v2 ([#27](https://github.com/ekaynac/kutuphane/pull/27), [#31](https://github.com/ekaynac/kutuphane/pull/31), [#33](https://github.com/ekaynac/kutuphane/pull/33), [#35](https://github.com/ekaynac/kutuphane/pull/35)).

## 2026-10-14

- `deploy/llmdap_contract.py` follows no redirects and tests `LLMDAP_GATEWAY_TRUST_SECRET` ([#28](https://github.com/ekaynac/kutuphane/pull/28)).
- Design and research: STE labelling guide ([#26](https://github.com/ekaynac/kutuphane/pull/26)).

## 2026-10-13

- Hybrid full-text and vector search; `kutuphane index`; full text when the query embedding fails; Core subject key for LLMDAP ([#24](https://github.com/ekaynac/kutuphane/pull/24)).
- `deploy/llmdap_contract.py`: run at install and after each LLMDAP upgrade ([#25](https://github.com/ekaynac/kutuphane/pull/25)).
- Design and research: M0 model measurement ([#23](https://github.com/ekaynac/kutuphane/pull/23)).

## 2026-10-12

- `kutuphane migrate`, `ingest`, `show` ([#5](https://github.com/ekaynac/kutuphane/pull/5)).
- `kutuphane grant`, `revoke`, `delegate`, `undelegate`, `read`; `activate` for agent instruction files ([#6](https://github.com/ekaynac/kutuphane/pull/6)).
- Case-insensitive file type checks ([#7](https://github.com/ekaynac/kutuphane/pull/7)).
- One-statement access decision; `cat` removed ([#8](https://github.com/ekaynac/kutuphane/pull/8)).
- JWT verification against JWKS; `kutuphane whoami`; `kutuphane explain` ([#9](https://github.com/ekaynac/kutuphane/pull/9)).
- `kutuphane search` with versioned citation handles ([#10](https://github.com/ekaynac/kutuphane/pull/10)).
- Multi-book rights in one statement; cloud routes need `cloud_ok` ([#11](https://github.com/ekaynac/kutuphane/pull/11)).
- `kutuphane ask` with `[n]` citations; `kutuphane reopen` ([#12](https://github.com/ekaynac/kutuphane/pull/12)).
- Reopen only by the same caller or user ([#13](https://github.com/ekaynac/kutuphane/pull/13)).
- Answer re-check of source books; `explain --answer` ([#14](https://github.com/ekaynac/kutuphane/pull/14)).
- HTTP API under `/v1/`, MCP at `/mcp`; Dockerfile and `deploy/egress_probe.py` ([#15](https://github.com/ekaynac/kutuphane/pull/15)).
- Reader UI at `/ui` with strict CSP; no start with pending migrations; `kutuphane dev-keys`, `dev-token` (`KUTUPHANE_DEV=1`) ([#16](https://github.com/ekaynac/kutuphane/pull/16)).
- `/v1/feedback` and `record_runbook_feedback` (removed later) ([#17](https://github.com/ekaynac/kutuphane/pull/17)).
- A refused write does not stay ([#18](https://github.com/ekaynac/kutuphane/pull/18)).
- Signed packages: `kutuphane keygen`, `trust`, `untrust`, `export`, `receive`, `approve-import`, `reject-import`, `imports` ([#19](https://github.com/ekaynac/kutuphane/pull/19)).
- Full-text recall@10 0.245 to 0.563 ([#21](https://github.com/ekaynac/kutuphane/pull/21)).
- Safe MCP errors; UI sign-out clears data; package key lock ([#22](https://github.com/ekaynac/kutuphane/pull/22)).
- Design and research: D1–D48, product brief, roadmap, M1 ([#1](https://github.com/ekaynac/kutuphane/pull/1), [#2](https://github.com/ekaynac/kutuphane/pull/2), [#3](https://github.com/ekaynac/kutuphane/pull/3), [#4](https://github.com/ekaynac/kutuphane/pull/4), [#20](https://github.com/ekaynac/kutuphane/pull/20)).
