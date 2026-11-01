# Changelog

This file lists the changes that users and operators can see.
The newest changes are first.
Each date has the pull requests (PRs) that were merged on that date.
Decision D75 is the rule for this file: each feature PR updates the related user documentation in the same PR, and it adds its entry here.
Internal work (decision records, research notes, labelling experiments) is in one "Design and research" line for each date.
For the terms, read [concepts.md](concepts.md).

## Unreleased

### Vision 1.2 and "memory is data" (D80)

- `docs/01` D80 records the nine operator decisions of 2026-11-01. R5: no new agent-memory feature merges before the T3 A/B (#121) rerun.
- `docs/23` is version 1.2: the positioning, five principles, and the research §7 sentence changes. D73 is deleted, not frozen.
- `agent-memory.md` §13: notes reach a model only as tool results; instructions need `activate` and the scan.

### Astra review #21 fixes

- Fixed: across a new content version, an `overlap` successor now must hold the whole old passage text with its operators and case. Before, `retries >= 3` could map to `retries <= 3`; such a citation is now `stale` ([operations.md](operations.md#re-index-and-note-citations)).
- Fixed: the curator queue and the origin confirmation showed "Applies everywhere (no scope)" on a rule that had only an `applies_to` bound. The card now shows the bound ("Applies to vcenter; version >=7,<8") and says "everywhere" only when the note has neither a scope nor `applies_to` ([operations.md](operations.md)).
- Fixed: migration `047_note_applies_to.sql` now locks `runbook_feedback` before it checks that the table is empty, so a feedback row that an old server commits during the upgrade is kept.
- Migration `048_passage_map_operators.sql` removes the `overlap` rows of a changed content version. After `migrate`, run `kutuphane reindex-map <book>` for each book whose passages notes cite. No role script changes. On the main database, a read-only count gives the same `overlap` answer for all 6 such rows.

### `curate` grant in the database; small refactor (wave 1)

- Fixed: the app database role could insert a `curate` row into `grant_tuple` directly, past the CLI check. A row-level security policy in `deploy/db-roles.sql` now refuses it; run the script again after you upgrade ([security.md](security.md#curation-boundary)).
- Changed: a curator act with a malformed principal now gives `a curator is a user:` (before: `invalid curator: …`). One check, `authz.curator`, serves curation and `kutuphane skill clear`.
- Design and research: refactor wave 1 (W1-2, W1-3, W1-5): one slug pattern `ids.SLUG`, dead names removed.

### Catalog read and publication facts (#159, #160)

- New: `GET /v1/books` and the MCP tool `list_books`: the books and journals that you may read now, with `kind` (`book` or `journal`), the current `content_id` and `profile_id`, and `publication`. A book that you may not read is not in the list ([http-api.md](http-api.md#72-get-v1books), [mcp.md](mcp.md#518-list_books)) ([#159](https://github.com/ekaynac/kutuphane/issues/159)).
- New: `GET /v1/books/{book}/files` and the MCP tool `list_files`: the files of a book's current version, a page at a time (`cursor`, `limit` 1–500), with digest, size, passage count and the kstd item information (licence, `ai_use`, `personal_data`, origin, validity, `applies_to`). It needs `read` on the book; a book that you may not read gives the same `403` as a book that does not exist ([http-api.md](http-api.md#73-get-v1booksbookfiles), [mcp.md](mcp.md#519-list_files)) ([#159](https://github.com/ekaynac/kutuphane/issues/159)).
- New: each publication records `approved_by` and `channel`: `ingest` (the new `--by` option, default `user:<the CLI user>`) or `import` (the `approve-import --by` decider, with the package's signing key and sequence). The book list, the file list, `open_citation` and `kutuphane show` show them; older publications show `null` ([operations.md](operations.md#2-ingest-a-folder-into-a-book)) ([#160](https://github.com/ekaynac/kutuphane/issues/160)).
- Migration `045_publication_facts.sql` adds `approved_by`, `channel` and `package_import` to `publication`. No role script changes.

### Identity and trace: caller correlation id, more issuers, LLMDAP purposes (#156, #157, #165)

- New: send your own correlation id in `X-Correlation-Id` (MCP: `_meta["kutuphane/correlation-id"]`). Kütüphane stores it next to its own id as `caller_correlation_id` in `access_event`, `model_call`, `write_record` and a background job, puts it at the start of the LLMDAP correlation id, and returns both ids on every response (`X-Correlation-Id` + `X-Caller-Correlation-Id`; MCP result `_meta`). A malformed id is `400` (MCP `-32602`). It never decides a right or an idempotency key. `kutuphane explain` accepts either id ([http-api.md](http-api.md#15-correlation-id), [mcp.md](mcp.md#46-correlation-id)) ([#156](https://github.com/ekaynac/kutuphane/issues/156)).
- New: `KUTUPHANE_OIDC_ISSUERS`, a JSON file of more token issuers, each with its exact issuer, audience, JWKS and principal prefixes. Its tokens may name only its own principals, and no other issuer may name them. `grant … curate` refuses its principals unless the entry says `"curate": true` ([operations.md](operations.md#more-than-one-token-issuer)) ([#157](https://github.com/ekaynac/kutuphane/issues/157)).
- Changed: every model call sends `x-llmdap-purpose`, one of `answer`, `search`, `index`, `translate`, `rerank`, `note`, `decide`, `health`. The decider's purpose was `curator-decider`; it is now `decide`. The guide tells how to run Core against a shared LLMDAP (D76) ([operations.md](operations.md#a-shared-llmdap-d76)) ([#165](https://github.com/ekaynac/kutuphane/issues/165)).
- Migration `046_caller_correlation.sql` adds `caller_correlation_id` to `access_event`, `model_call`, `write_record` and `ask_job`. After `migrate`, apply `deploy/db-roles.sql` as usual.

### Agent memory: one Scope context; runbook feedback removed (#164, D78)

- New: `propose_note` and `POST /v1/notes` accept `applies_to` (`{platform, version}`, the shape of the kstd `applies_to` of files). It is part of the note id; a note without it keeps its id ([mcp.md](mcp.md#59-propose_note)) ([#164](https://github.com/ekaynac/kutuphane/issues/164)).
- New: `platform` and `version` in the context of `query_notes`, `neighbours`, `open_citation` and their HTTP routes, next to `repo`, `branch`, `path(s)` and `commit`. The verdict is the one of files (`kstd.scope_verdict`): a contradicted bound leaves the note out; a missing context value keeps evidence current and makes a bounded rule `needs_context`. A note without `applies_to` gives the same result as before; an item has `applies_to` only when the note has one ([mcp.md](mcp.md#512-query_notes)).
- Changed: a rule approval retires a superseded note, and the curator queue gives tier 1, only when `applies_to` is also the same. Curator web and the confirmation page show `applies_to`.
- Removed: `record_runbook_feedback`, `POST /v1/feedback` and `GET /v1/feedback` (D78). Use `record_outcome` on the passage handle of the runbook. Migration `047_note_applies_to.sql` adds `note.applies_to` and drops the table `runbook_feedback` only when it has no rows (the main database had 0).
- The MCP tool sections from `job_status` on move up one number in [mcp.md](mcp.md); the HTTP sections from Notes on move up one number in [http-api.md](http-api.md).

### Frozen list and `curate` grant credential (D78, D79)

- Changed: `kutuphane grant … curate …` needs `KUTUPHANE_CURATOR_DSN`. Without it the CLI refuses with exit code 2. Before, the app credential could make a curator ([security.md](security.md#curation-boundary)).
- Changed: the guide no longer names Role and Time basis as facets; they follow from the note kind ([concepts.md](concepts.md#kinds)). The decider, delegated curate and "my words" are frozen: they work, with no new work ([operations.md](operations.md)).
- Design and research: D78 (the frozen list) and D79 (areas A/B/C, vision 1.1) in `docs/01`; `docs/23` vision 1.1; `docs/11` draft 0.3.1 moves the kinds that the reference does not implement to an appendix; `docs/09` status note.

### Note query: folder scope, `refs` and `paths` (#152, #155, #153)

- Fixed: a folder prefix in `path` (it ends with `/`) matched every note whose scope glob has no literal head, for example `*.log` matched `src/`. Now a folder matches a glob only when a file below the folder can match it, with the glob rules of the write path (`*` and `?` do not match `/`) ([mcp.md](mcp.md#512-query_notes)) ([#152](https://github.com/ekaynac/kutuphane/issues/152)).
- New: `refs` on `query_notes` and `GET /v1/notes` (1–50 note references): only these notes, with `standing` and the new item key `standing_seq` (the event of the effective Standing). Notes that you may not read are left out without an error; the other filters still apply. The `propose_note` receipt does not change ([mcp.md](mcp.md#512-query_notes)) ([#155](https://github.com/ekaynac/kutuphane/issues/155)).
- New: `paths` on `query_notes` and `GET /v1/notes` (1–20 context paths, with `path`): one query, one budget, one order. The scope rule for each path does not change. Each item has `paths`, the context paths that put it in the sets ([mcp.md](mcp.md#512-query_notes)) ([#153](https://github.com/ekaynac/kutuphane/issues/153)).

### Astra review #20 fixes

- Changed: the package status (`POST /v1/packages`, `GET /v1/packages/{id}`, `submit_package`, `package_status`) gives `diff` only with a current `read` on the book; else `diff` is `null`. Before, `propose` alone listed the files of the receiving catalog ([http-api.md](http-api.md#122-get-v1packagesid)).
- Changed: the note receipt's `licence_notice` names no path in a book that you may not read; `unreadable` gives their number. The note is still never exported ([mcp.md](mcp.md)).
- Changed: across a new content version, an `overlap` successor must hold the whole old passage text. One changed word (`enable` to `disable`) no longer joins a note to a passage of another meaning; such a citation is `stale`. A re-index with the same content is not changed ([operations.md](operations.md#re-index-and-note-citations)).
- Fixed: a publication during a read could give a `moved_to` handle that mixed two versions.
- Migration `044_passage_map_overlap.sql` removes the `overlap` rows of a changed content version. After `migrate`, run `kutuphane reindex-map <book>` for each book whose passages notes cite. On the main database, a read-only count gives the same `overlap` answer for all 6 such rows.

### Scope: `applies_to` and the request context (#137, #142, #138)

- New: kstd `applies_to` has a mapping form: `{platform: [<names>], version: "<range>"}`, for example `{platform: [vcenter], version: ">=7.0,<8"}`. The string form stays valid and means `platform: [<string>]`. A malformed `platform` or `version` refuses the book; an unknown key is ignored with a notice (D74). `item.applies_to` now always shows the mapping form ([kstd.md](kstd.md#what-kütüphane-does-with-each-field)) ([#137](https://github.com/ekaynac/kutuphane/issues/137)).
- New: a request context on search and ask: `--platform` and `--version` on the CLI, `platform` and `version` on `GET /v1/search`, `context: {platform, version}` on `POST /v1/ask`, `search_library` and `ask_library` (also for a background job). A file whose `applies_to` the context contradicts is left out before ranking. A file without `applies_to` always matches. A bounded file without a matching context value stays in the evidence with `item.scope: needs_context`. Each `item` has `scope`: `unbounded`, `match` or `needs_context` ([operations.md](operations.md#scope-filters-g14), [mcp.md](mcp.md#51-search_library)) ([#137](https://github.com/ekaynac/kutuphane/issues/137)).
- New: the guide tells how to give roles one scope each with whole-book grants: one book per scope and one shared book; a test shows that a scope-A role gets no scope-B passage or note from search, ask evidence, `open_citation`, `neighbours` or `query_notes` ([operations.md](operations.md#one-book-per-scope-138)) ([#138](https://github.com/ekaynac/kutuphane/issues/138)).
- Design and research: Pilot 2 question 6 is in the measured answer set (`docs/26` §8), not a CI gate ([#142](https://github.com/ekaynac/kutuphane/issues/142)).

### Restart policies and the dependency check (#141)

- New: `postgres`, `core`, `ingress` and `llmdap` (and `embedder` and `spark-chat` in the local-models overlay; the three services of the light install) have `restart: unless-stopped`: they come back after a crash or a host reboot without a person. `reranker-gpu` has `restart: on-failure:5`, so a start that fails with a CUDA out-of-memory error is tried again ([install.md](install.md#reboot-and-restart)) ([#141](https://github.com/ekaynac/kutuphane/issues/141)).
- New: `GET /v1/health` (a token is necessary) gives one boolean for each dependency: `db`, `llmdap`, `embedding`, `rerank`, `chat`, and `ok`. It names no route, model or address. A dependency that the install does not configure is `null`. `/healthz` does not change ([http-api.md](http-api.md#33-get-v1health)) ([#141](https://github.com/ekaynac/kutuphane/issues/141)).

### Retrieval status: a degraded search shows (#136)

- New: each search and answer tells what each model stage did: `retrieval: {embedding, translation, rerank}`, each `ok`, `failed` or `skipped`. Before, a failed query embedding (full text only), a failed query translation (the question only) and a failed rerank (the hybrid order) gave the same result shape as a full search and only wrote a log line. `GET /v1/search` and `POST /v1/ask` have the `retrieval` key; `search_library` has it in `_meta["kutuphane/retrieval"]`; `ask_library`, `reopen_answer`, `job_result` and `GET /v1/answers/{id}` have it in the answer. It is stored with the answer (migration 042; older answers show `null`) ([http-api.md](http-api.md#51-get-v1search), [mcp.md](mcp.md#45-retrieval-status)) ([#136](https://github.com/ekaynac/kutuphane/issues/136)).
- New: the guide gives the `model_call` queries that count the failed model calls per route and the degraded answers per stage ([operations.md](operations.md#degraded-searches-and-failed-model-calls-136)) ([#136](https://github.com/ekaynac/kutuphane/issues/136)).

### Notes follow a re-index (#140)

- Fixed: after a re-index (a new profile id, for example a new chunker, or a new content version), note citations and `about` and `derived_from` links stayed on the old passages, so `neighbours` from a new handle did not find the notes. Now each publication maps every cited or linked passage of an earlier version to the passage of the same path in the new version: the same text (`exact`), else the passage that holds at least half of its word pairs (`overlap`), else none. The notes keep their handles, and the old passages still open ([operations.md](operations.md#re-index-and-note-citations)) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- New: a passage citation in `query_notes`, `neighbours` and a note in `open_citation`, and a passage in `open_citation` (MCP and HTTP), have `status`: `current`, `moved` with `moved_to` and `match`, or `stale` (no successor; the citation stays). `neighbours` from a passage also gives the notes on the passages that the map joins to it; such an edge has `original`, the handle that the note stores ([agent-memory.md](agent-memory.md#5-follow-links), [mcp.md](mcp.md#52-open_citation)) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- New: the curator queue gives a passage citation and a passage link the same `status` keys, and the card says "re-indexed" or "not in the current version". The decision export has `context.passages` {handle: state} ([operations.md](operations.md#8-outcomes-and-decision-export)) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- New: `ingest` and `approve-import` give the counts in `passage_map` and warn on stderr when a cited passage has no successor. `kutuphane reindex-map <book> [--dry-run]` maps a book that was published before this change (idempotent) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- Changed: a model reader gets the text of a note withheld also when the skill of the successor passage is blocked (D71: the gates apply to the new passage) ([#146](https://github.com/ekaynac/kutuphane/pull/146)).
- Migration `040_passage_map.sql`. After `migrate`, apply `deploy/db-roles.sql`, `deploy/db-roles-curator.sql` and `deploy/db-roles-decider.sql` again, then run `kutuphane reindex-map <book>` for each book whose passages notes cite. On `inframedic-canon` (the chunker 5 re-index and the next content version), a read-only count of the 12 journal citations gives 1 `exact`, 11 `overlap` and 0 `none`; the one `derived_from` link gives `overlap` ([#146](https://github.com/ekaynac/kutuphane/pull/146)).

### Packages over HTTP and MCP; license unknown (#139, #143)

- New: `POST /v1/packages` and the MCP tool `submit_package` receive a signed package from an application, with the same checks as `kutuphane receive` and a size limit (`413`). `GET /v1/packages/{id}` and the MCP tool `package_status` give the import status to the caller that submitted it: `received`, `findings`, `approved` or `refused`. The caller needs `propose` on the book that the manifest names (no new grant mode); without it, nothing is stored. Nothing is published until a person runs `approve-import`; then only the changed passages embed again. The issuer is the signing key (D74); the caller is recorded in `submitted_by`, `submitted_for`, `submitted_channel` (D70, migration 041; `kutuphane imports` shows them) ([http-api.md](http-api.md#12-packages), [mcp.md](mcp.md#516-submit_package), [operations.md](operations.md#packages-from-an-application-http-and-mcp-139)) ([#139](https://github.com/ekaynac/kutuphane/issues/139)).
- Changed: `license: unknown` permits derivation in this installation with a notice: the note receipt has `licence_notice` with the files. `export` refuses a book with a `license: unknown` file, and the decision export leaves out every note derived from one (`licence_unknown` in the summary). The `kstd-check` warning says this. The kstd reference rule permits `derive` with the notice `rights-unknown` and denies `forward` of the derived item (`input-rights-unknown`); docs/11 §4 rule 3 and §5.2 are updated. For internal content, state a license such as `LicenseRef-InfraMedic-Internal` ([kstd.md](kstd.md#what-kütüphane-does-with-each-field), [operations.md](operations.md#10-packages)) ([#143](https://github.com/ekaynac/kutuphane/issues/143)).

### Curator web in plain words (#135)

- Changed: the phone page of curator web has three tabs: **To review** (the queue), **My words** (the "my words" requests) and **Auto-approval** (the delegations, now also at `/delegations`). Each tab has one line that tells what it is for. A card shows the note text first, then the kind in plain words ("Finding: something an agent observed"), who proposed it for whom and the date; the evidence as file names with the first two lines and **Show passage**; the options of a decision with the **Proposed choice** marked; the replaced rule; and a warning line instead of the tier ("Approving this replaces an approved rule."). Where a note applies (its scope) stays on the card; the ids, the class key and the writer ids are under **Details**. A group card says "3 notes say the same thing" and has **Approve all** and **Reject all**. The reason is a tap on a chip (**Correct and useful**, **Wrong**, **Duplicate**, **Not useful now**) or free text; the bottom bar says "Sign 3 decisions"; the sign sheet says "You approve 2 notes and reject 1" from the stored statement; the receipt says "Done. 2 approved, 1 rejected." Large buttons, 17 px text, and dark colours when the phone uses a dark theme ([operations.md](operations.md#on-the-phone-curator-web-d72)) ([#135](https://github.com/ekaynac/kutuphane/pull/135)).
- Changed: the queue gives a readable passage citation its `path` and an `excerpt` (the first 240 characters), and a passage link its `path` ([operations.md](operations.md#the-queue-77)) ([#135](https://github.com/ekaynac/kutuphane/pull/135)).

### kstd-check findings and vector counters (#134)

- Fixed: `kstd-check --deny-names <file>` did the personal-data scan but did not show its findings. In Pilot 2, `kstd-init` and `ingest` gave 45 findings with the same deny-list, and `kstd-check` gave none. Now `ingest`, `kstd-init` and `kstd-check` list each finding (`personal-data finding (labelling, not refused): <path> line <n> (<rule>)`) and one count line (`personal-data findings: <rule> <n>, … (<files> files)`) from the same scan. A finding does not make `kstd-check` fail ([operations.md](operations.md#personal-data-and-fleet-data-findings), [kstd.md](kstd.md#workflow)) ([#134](https://github.com/ekaynac/kutuphane/pull/134)).
- Changed: the index result field `vectors_added` is now `vectors_embedded`, and it counts only the new vectors from the embedder. Before, `vectors_added` also counted the copied vectors: a re-ingest that copied all 585 vectors showed `vectors_added 585` and `vectors_reused 585`. Now it shows `vectors_embedded 0` and `vectors_reused 585`. A script that reads `vectors_added` must read `vectors_embedded` + `vectors_reused` ([operations.md](operations.md#3-indexing)) ([#134](https://github.com/ekaynac/kutuphane/pull/134)).

### Curator web on the host with tailscale serve (#132)

- New: an install variant without a sidecar: curator web runs on the host as a systemd user service bound to 127.0.0.1, and `tailscale serve` on the host gives it HTTPS 443 (tailnet only, Funnel off). It needs no tagged auth key ([install.md](install.md#host-install-with-tailscale-serve)) ([#132](https://github.com/ekaynac/kutuphane/pull/132)).

### GPU reranker (#131; G26)

- New: the compose profile `gpu-rerank` runs `bge-reranker-v2-m3` (the same pinned commit) on the GPU, with the host vLLM's image and 0.04 of the GPU memory (about 1.9 GB used), behind the new LLMDAP route `rerank-gpu`. Set `KUTUPHANE_LLMDAP_RERANK_ROUTE=rerank-gpu` to use it; `rerank` (the CPU embedder) stays the fallback. On the pilot questions the rerank stage went from 11–25 s to 0.2–0.3 s with the same top 8, and `ask` from 22–31 s to 8–10 s on average ([install.md](install.md#gpu-reranker), [operations.md](operations.md#reranking), [troubleshooting.md](troubleshooting.md#ingest-and-index)) ([#131](https://github.com/ekaynac/kutuphane/pull/131)).
- Changed: the local-models overlay takes `KUTUPHANE_LLMDAP_RERANK_ROUTE` from `.env` (default `rerank`). After an upgrade, restart LLMDAP once to load the new route. After a reboot, start the GPU reranker again ([install.md](install.md#reboot-and-restart)) ([#131](https://github.com/ekaynac/kutuphane/pull/131)).
- Design and research: `docs/26` §10 and `docs/18` §4.1 (method, memory, order agreement, time before and after) ([#131](https://github.com/ekaynac/kutuphane/pull/131)).

### Astra review #19 fixes

- Fixed: a database function without a fixed search path could read a temporary table or sequence of the caller. The decider role could hide `standing_event` and `memory_seq` and so make a late suggestion count as earlier shadow evidence for a delegation. Every function and trigger now uses `pg_catalog, public, pg_temp` and names its tables with their schema, and the role scripts take the `TEMP` right from `PUBLIC` and from the three login roles ([security.md](security.md#curation-boundary), [install.md](install.md)) ([#130](https://github.com/ekaynac/kutuphane/pull/130)).
- Fixed: the app role could add a citation or a creation link to a note after a person confirmed or approved it, and the note kept `human`. The database now writes these parts only in the transaction of the note. A confirmation, and an approval on the phone, count only while the note's stored parts give the signed id; else the note shows `model` and `pending`. `curator verify-acts` reports such an act with the problem `contents` ([operations.md](operations.md#on-the-phone-curator-web-d72), [troubleshooting.md](troubleshooting.md#notes-and-curation)) ([#130](https://github.com/ekaynac/kutuphane/pull/130)).
- Fixed: `quoted_records` was decided apart from the hits. A grant change between the two reads could give a passage of one book with a record of another book, with no moment when you could read both. Search and ask now decide the passages and the records in one final step: a lost book drops its passages and the handles into it. Each book whose records a search names gets an `access_event` with the action `quote` ([concepts.md](concepts.md#records-that-a-passage-repeats)) ([#130](https://github.com/ekaynac/kutuphane/pull/130)).
- Fixed: `approve-import` published a package with personal data into a `cloud_ok` book without a review. The cloud gate is now part of every publication, as for `ingest`. `receive` lists each personal-data finding (`personal_data`: path, digest, rule, lines), and `approve-import` takes `--accept-finding` ([operations.md](operations.md#10-packages)) ([#130](https://github.com/ekaynac/kutuphane/pull/130)).
- Migrations `038_function_search_path.sql` and `039_note_parts_at_creation.sql`. After `migrate`, apply `deploy/db-roles.sql`, `deploy/db-roles-curator.sql` and `deploy/db-roles-decider.sql` again ([#130](https://github.com/ekaynac/kutuphane/pull/130)).
- Design and research: `docs/08` (Astra incelemesi #19), the raw review in `docs/research/2026-10-28-astra-review-19-raw.md` ([#130](https://github.com/ekaynac/kutuphane/pull/130)).

### Pilot 1 gaps G13, G15 (host CLI settings, citation lines)

- Changed: each `ask` citation has `line` (the line where the passage starts, as in `search`; `null` for HTML and PDF) and `record` (for a JSONL passage inside one record: the number of the record in the file, from 1; else `null`). The evidence of `reopen`, `reopen_answer` and a background job's result has both too, also for old answers (G15) ([operations.md](operations.md#answers), [mcp.md](mcp.md), [http-api.md](http-api.md)) ([#129](https://github.com/ekaynac/kutuphane/pull/129)).
- Changed: `KUTUPHANE_OIDC_AUDIENCE` is `kutuphane` when it is not set, as in compose. An empty `KUTUPHANE_CONFIRM_HOURS` is 24, as in compose (G13) ([operations.md](operations.md#variables)) ([#129](https://github.com/ekaynac/kutuphane/pull/129)).
- Changed: a route class (`KUTUPHANE_LLMDAP_ROUTE_CLASS`, `_EMBED_ROUTE_CLASS`, `_RERANK_ROUTE_CLASS`) still has no default outside compose, because `local` skips the egress check. The message now gives the two values and tells that compose sets `local`; a bad value names its setting (G13) ([troubleshooting.md](troubleshooting.md)) ([#129](https://github.com/ekaynac/kutuphane/pull/129)).

### Records that a passage repeats (#128; pilot 1 gaps G23, G16, G25)

- New: a passage that repeats a whole string value of a JSONL record (40 characters or more, white space folded; a JSON string, a line, or a line without its markdown mark) points to that record. `search_library`, `GET /v1/search` and `kutuphane search` give each hit `quoted_records`: the handles of those records, only from books that you may read now and that pass the filters. The order of the hits does not change ([concepts.md](concepts.md#records-that-a-passage-repeats), [mcp.md](mcp.md#51-search_library), [http-api.md](http-api.md)) ([#128](https://github.com/ekaynac/kutuphane/pull/128)).
- Changed: `ask_library`, `POST /v1/ask` and `kutuphane ask` put each such record into the evidence right before its first copy (at most 4 records; only with AI input in their rights) and tell the model to cite the record for the repeated text. Each citation, and each evidence entry of `reopen_answer`, has `quoted_records` ([#128](https://github.com/ekaynac/kutuphane/pull/128)).
- Migration `037_record_value.sql`: it stores the values of the record passages of every current and earlier version. After `migrate`, apply `deploy/db-roles.sql` again ([#128](https://github.com/ekaynac/kutuphane/pull/128)).
- Design and research: `docs/18` §7. Per-record origin (G16) is not built: on the pilot data it changes no decision, and a record field can never show a review. G25 needs the generator to record its version; Kütüphane needs no change ([#128](https://github.com/ekaynac/kutuphane/pull/128)).

### A size budget for agent search results (#121)

- New: `search_library` takes `max_chars` (80–4800), and `GET /v1/search` takes `max_chars` too. Each `text` becomes a deterministic snippet around the words that match the query (the search's text search configuration; the passage start when no word matches), cut at white space, with `…` on each cut side, and each result has `truncated`. The hits, their order, their scores and the gates do not change: a withheld text stays `null`. The `citation` stays, so `open_citation` gives the full passage. Without `max_chars` the result does not change. On this repository's user guide as a book, `max_chars: 300` made the median result of 8 queries 65% smaller (12,959 to 4,578 characters for 8 hits) ([mcp.md](mcp.md#51-search_library), [http-api.md](http-api.md#51-get-v1search), [agent-memory.md](agent-memory.md#4-read-memory-fast-no-model-call)) ([#127](https://github.com/ekaynac/kutuphane/pull/127)).
- Changed: a server without LLMDAP does not list `ask_library`, `job_status`, `job_result` and `job_cancel` in `tools/list`. The list depends on the deployment only, never on the caller. `POST /v1/ask` still gives `503` there ([mcp.md](mcp.md#5-tools), [install.md](install.md#light-install)) ([#127](https://github.com/ekaynac/kutuphane/pull/127)).
- Changed: each MCP tool description names the grant that the tool needs (for example `needs read on the book`), so an agent does not spend a turn to find it out ([mcp.md](mcp.md#5-tools)) ([#127](https://github.com/ekaynac/kutuphane/pull/127)).

### Security review #18 fixes (#118, #122, #123)

- Fixed: the handling labels of a note named every book that its text came from, with its Sensitivity and Egress, also a book that the caller may not read. `books` now names only the books of the caller's read set; the others count in `unnamed_sources` and still make `sensitivity` and `egress` stricter ([mcp.md](mcp.md#44-handling-labels-in-_meta)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Fixed: a markdown file with many adjacent HTML comments (`"<!---->" * 40 + "x"`, 280 bytes) could stop an ingest, a package approval or a reindex (exponential regex backtracking). The cut is now linear ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Changed: no passage holds a markdown HTML comment, which a reader of the rendered file never sees. Each comment character becomes a space, so offsets and line numbers stay. A rule file's leading one-line `<!-- source: … -->` comment is a citation and stays in the rule passage (G28). No passage of the current books changes (2,787 checked), so the chunker version stays 5 and no ingest is needed ([concepts.md](concepts.md)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Fixed: `skills/get` and `resources/read` took the content id before the read, so a version published between the two could give the labels and the `access_event` row of the old version with the new bytes. They now use the version served ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Fixed: a refusal inside a skills read (the kstd rights do not allow AI input; not found) left no `access_event` row. It is now logged with its reason, for every mode ([mcp.md](mcp.md#103-gate)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Changed: `resources/read` of a `skill://` HTML, JavaScript, SVG or XML file gives `text/plain` (`application/octet-stream` when not UTF-8). The bytes and the digest do not change ([mcp.md](mcp.md#107-resourcesread)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Changed: the server stores the checked `SKILL.md` frontmatter at publication; skills calls no longer parse every `SKILL.md` of a book, and `skills/get` and `resources/read` look only at the skills above the path. Migration `033_skill_frontmatter.sql`: after `migrate`, apply `deploy/db-roles.sql` again ([#125](https://github.com/ekaynac/kutuphane/pull/125)).
- Fixed: `read_document` served a file of a skill that holds a blocked skill in a subfolder, and checked AI input for that one file only. A file in a skill folder now stands for its whole skill, as in `skills/get` ([mcp.md](mcp.md#55-read_document)) ([#125](https://github.com/ekaynac/kutuphane/pull/125)).

### Pilot 2 gaps G34, G35 (kstd-init evidence)

- `kutuphane kstd-init <copy> --source-repo <repo> [--commit <rev>]` proposes the origin of each file from the commit history of a local repository (G34). A file matches by path (also the end of a path, for a copy of a subfolder) or by content at the commit (default `HEAD`). It gets `origin: model` with a `# proposed from git` comment when every commit of the file has a `Co-Authored-By` trailer with a known model agent, else `origin: unknown`. The commit ids and the trailer lines are comment lines of the item. `human` and `assisted` are never proposed: a person's commit is not proof of human authorship, and `assisted` needs a named reviewer. Git runs read-only, with no network ([kstd.md](kstd.md#origin-proposals-from-a-source-repository)) ([#124](https://github.com/ekaynac/kutuphane/pull/124)).
- `ingest`, `kstd-init` and `kstd-check` find personal data and fleet data (G35): private IPv4 and IPv6 addresses, e-mail addresses, phone numbers, and the names of a deny-list file (`--deny-names <file>`: customers, sites). Each finding gives the path, the line and the rule, never the matched text. `kstd-init` writes `personal_data: unknown` for the item of each file with a finding (never `no`). `ingest` records the findings in the publication (`data_findings` in the result and in `show`) and lists them on stderr. A `local_only` book is not refused. A `cloud_ok` book refuses a file with a finding that can go to a model, until you accept each reviewed finding with `--accept-finding <path>@sha256:<digest>:<rule>` ([operations.md](operations.md#personal-data-and-fleet-data-findings)) ([#124](https://github.com/ekaynac/kutuphane/pull/124)).
- Migration `032_data_findings.sql` adds `data_findings` to the publication record: run `kutuphane migrate` ([#124](https://github.com/ekaynac/kutuphane/pull/124)).

### MCP Skills (SEP-2640) and handling labels (#80)

- New: the MCP server serves the skill folders of the current book versions with the Skills extension `io.modelcontextprotocol/skills` (SEP-2640, Final): `skills/list`, `skills/get`, and `resources/read` of `skill://<book>/<folder>/<file>`. A skill is served only to a principal with `read` and `activate` on the book (people too), when kstd allows AI input for all its files and a scan blocks none of them. Each file has its SHA-256 (`sha256:` + the digest in the content manifest) and size; the bytes go out only on `resources/read`. On 2026-07-28 the client must declare the extension (else `-32021`). `read_document` stays the path for other clients ([mcp.md](mcp.md#10-skills-sep-2640)) ([#123](https://github.com/ekaynac/kutuphane/pull/123)).
- New: `search_library`, `open_citation`, `read_document` and `query_notes` give the Sensitivity and Egress of each book in the result, the strictest of them, and the skill-scan records that apply, in `_meta["kutuphane/handling"]`. The guide records how these map to the experimental trust-annotations extension (SEP-1913) when it is stable ([mcp.md](mcp.md#44-handling-labels-in-_meta)) ([#123](https://github.com/ekaynac/kutuphane/pull/123)).
- `deploy/mcp_probe.py --skill <SKILL.md URI>` checks the Skills extension and the digests through the proxy; the probe also checks the handling labels of `search_library` ([mcp.md](mcp.md#9-check-the-server-with-deploymcp_probepy)) ([#123](https://github.com/ekaynac/kutuphane/pull/123)).

### Retrieval re-check (Pilot 1 questions 1–3)

- Fixed: for a question with passages in Turkish and in English, the question translation was sampled. An English question could get a Turkish word of another sense, or an answer in place of a translation, and the second search then missed the passage with the answer (G19). The translation now uses greedy decoding (`temperature` 0). Pilot 1 question 2 in English: the literal translation in 3 of 3 runs, before 1 of 3 ([operations.md](operations.md), section 4; results in [../18-pilot-radar.md](../18-pilot-radar.md), section 4.2) ([#122](https://github.com/ekaynac/kutuphane/pull/122)).

### Security review #17 fixes (curator slices R, D, Q)

- Fixed: the decider runner role could choose its own sample. It could roll back a sampled use and try again, pick the note for a forced sample, and set the `seq` of a use or a suggestion. The database now sets `seq`, the time and `sampled` (column grants and triggers), draws the sample as an HMAC of the delegation and the note under a key that only the owner reads (a retry draws the same), accepts a use only for the oldest eligible note of the class with a suggestion committed before it, and checks the creator's `curate` right and the runner's authorship in the trigger. A suggestion after a Standing event is refused, so it cannot count as shadow evidence ([security.md](security.md#delegated-curate-d73)) ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Fixed: another person could confirm over a live origin confirmation and so remove it without the confirmer's withdrawal (R7), also through a new request for the same bytes. A live confirmation now stays until its confirmer withdraws it (page, act and database) ([operations.md](operations.md), section 7) ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Fixed: the confirm page and its act options told a person without `read` on the book whether a note existed, had a request or had a confirmation. They now check `read` first and give one refusal ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Fixed: the decider runner sent the text of a note whose journal closed `ai_input` or whose skill a scan blocked during the run. It now reads each note again through the text gate just before the model call (`closed_meanwhile` in the run output) ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Changed: the decider role has no `SELECT` on `note`; it reads note text only through `decider_notes()`. **Action:** for each journal in `KUTUPHANE_DECIDER_BOOKS`, run `kutuphane grant book:<journal> read agent:kutuphane-decider`; the books of live delegations need nothing ([install.md](install.md#decider-runner)) ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Changed: `spec_sha256` now also covers the runner's prompt and answer code (`runner_code`, printed by `kutuphane decider spec`). Every spec digest changes with this release: suggestions and delegations of the old digests no longer match, and shadow agreement starts again ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Changed: `KUTUPHANE_DELEGATION_MIN_SHADOW` must be a whole number of at least 1; curator web does not start with another value. The confirm sign sheet shows the claim and the writer of the stored statement. A delegation end by an act is bound to its `end_delegation` act ([#120](https://github.com/ekaynac/kutuphane/pull/120)).
- Migration `029_curator_review17.sql` (needs the `pgcrypto` extension, part of PostgreSQL). After `migrate`, apply `deploy/db-roles.sql`, `deploy/db-roles-curator.sql` and `deploy/db-roles-decider.sql` again ([#120](https://github.com/ekaynac/kutuphane/pull/120)).

### Pilot 2 gaps (G27–G33)

- Markdown passages: a heading, a `---` line or an HTML comment alone is no longer a passage. It joins the passage after it, so each passage starts with its heading, and a rule file's leading source comment (`<!-- source: … -->`) is in the passage of the rule (G27, G28). A `#` line in a code fence, or `#41` with no space, is not a heading. The chunker version is now 5: ingest your markdown books again to get the new passages. Old passage handles still open ([concepts.md](concepts.md)) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).
- A vector is copied from any profile of the same book when the embedded text is the same, so the new ingest embeds only the passages whose text changed ([operations.md](operations.md), section 3) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).
- `class_count` and `guard_due` count only clusters of evidence notes (`finding`, `lesson`, `dead_end`, `test_result`). The `convention` that answers a class no longer sets `guard_due` (G31) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).
- `neighbours` from a passage also gives the notes that cite the passage, with the edge type `cites` and the same gates as links (G32). Migration `028_note_citation_passage.sql` adds the index for it: run `kutuphane migrate` ([#118](https://github.com/ekaynac/kutuphane/pull/118)).
- `search_library`, `ask_library` and `GET /v1/search` refuse a journal that you may read in the `book` filter with `journal: use query_notes …`, not with an empty list. The guide says that notes are not in search or answers (G33) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).
- Answers: the model is told to base the answer on passage `[1]` when it answers the question, to put each `[n]` after its claim, and to answer the part of a question that the passages answer (G30). A document or section that the question names and that the passages do not hold is named in the prompt, so the answer is `not_in_library` or says that the passages only refer to it (G29). The results before and after are in [../26-pilot-2.md](../26-pilot-2.md), section 8 ([mcp.md](mcp.md), section 5.3) ([#118](https://github.com/ekaynac/kutuphane/pull/118)).

### Security review #16 fixes (curator web)

- Fixed: approving a rule on the phone retired the rules that it supersedes without showing them. The signed statement now lists them (`retires`), the act retires exactly those or is refused (409), and `curator verify-acts` also checks the retirements ([#116](https://github.com/ekaynac/kutuphane/pull/116)).
- Fixed: the database role of curator web could write any system Standing value. It can now write only a `retired` event that the act's statement lists, in the act's transaction ([#116](https://github.com/ekaynac/kutuphane/pull/116)).
- Fixed: a session stayed open after its passkey was revoked. `revoke-passkey` now ends its sessions; new commands `kutuphane curator end-sessions <user>` and `kutuphane curator cancel-enrollment <id>`. An enrollment session registers only for its own code ([#116](https://github.com/ekaynac/kutuphane/pull/116)).
- Fixed: `deploy/curator_probe.py` reported PASS when docker failed or could not see the containers ([#116](https://github.com/ekaynac/kutuphane/pull/116)).
- Migration `026_curator_review16.sql`. Open curator sessions end when it runs. After `migrate`, apply `deploy/db-roles-curator.sql` again ([#116](https://github.com/ekaynac/kutuphane/pull/116)).

### "My words" origin confirmation (D70 R3, R7; docs/25 slice R)

- New: a person confirms that a note holds their words. When an agent (or a person over HTTP) proposes with `origin: human` or `assisted`, the receipt gets `confirmation: {url, expires_at}`. The person opens the URL in curator web, reads the full text, picks "These are my words, verbatim" (`human`, only the person the words were entered for) or "A model wrote or reworded this. I reviewed it in substance." (`assisted`, also a curator), and signs with a passkey. A request is open 24 hours (`KUTUPHANE_CONFIRM_HOURS`). One changed byte is another note, with the write-path origin. Use: [operations.md](operations.md), section 7. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New MCP tool `confirm_origin` and route `GET /v1/notes/{book}/{id}/confirmation`: the state (`open`, `confirmed`, `expired`, `none`) and the URL. A 2026-07-28 client with the `elicitation.url` capability gets a URL-mode elicitation; the tool never uses a form, and an `accept` confirms nothing ([mcp.md](mcp.md#515-confirm_origin)). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- Behavior change: `query_notes`, `neighbours`, `open_citation` and the decision export give the shown origin: a live confirmation, else the write-path value. With a confirmation, the item also has `entered_by` and `confirmed_by`. The `origin` filter of `query_notes` and `GET /v1/notes` now takes `human` and `assisted` too. The decision export `actor.origin` is now the shown origin of the note (before: the origin of its first write). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- R7: only the person who confirmed withdraws the confirmation, with a passkey act on the same page. A query with `as_of` before the withdrawal still shows it. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- kstd: the origin-details profile gets two optional fields for `human`, `entered_by` and `confirmed_by` (docs/11 0.3). A signed package lists such files in a new list `human_confirmed` (only when there is one, so other packages are unchanged). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- Migration `024_origin_confirmation.sql` (`origin_confirmation`, `origin_withdrawal`; `write_record.person` and `confirmable`). After `migrate`, apply `deploy/db-roles.sql` and, with curator web, `deploy/db-roles-curator.sql` again. New setting for Core: `KUTUPHANE_CURATOR_URL` ([install.md](install.md#curator-web)). ([#117](https://github.com/ekaynac/kutuphane/pull/117))

### Model suggestions and delegated curate (D73, #78, docs/25 slice D)

- New: the decider runner. `kutuphane decider run --spec FILE` asks a local model through LLMDAP for a suggestion (`approved`, `rejected` or `abstain`, and a confidence) on each undecided note. The first decider is the local Qwen (`deploy/deciders/qwen-notes.json`) in shadow mode (`--shadow`: suggestions only). A suggestion never changes Standing and is never shown before a person decides. Install: [install.md](install.md#decider-runner); use: [operations.md](operations.md), section 7. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New: delegated curate. A curator signs a `delegate` act on the phone: one decider spec may approve fresh notes of one evidence kind in one journal for at most 30 days, after at least 30 shadow decisions at the chosen threshold. The database checks each use, holds 1 in N uses (and always one after 2N) for a person, pauses at 3 open samples, writes the approval with `set_by: model:<name>@<version>`, and ends the delegation when a person rejects a sample on any path (phone, `note standing`, `note rollback`). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New item key `approved_by` in `query_notes`, `neighbours` and `open_citation` (MCP and HTTP): `user:…` or `model:…` for an approved note, else `null`. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New commands: `kutuphane decider run|spec`, `kutuphane delegation list|report|agreement|end`. Curator web: the **Delegations** view, the `delegate` and `end_delegation` acts, and `GET /api/delegations`, `GET /api/delegations/{id}`. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- Migration `025_curate_delegation.sql` (suggestions, delegations, ends, uses; `standing_event.delegation_use`; `set_by` may be `model:…` only for a delegated approval). After `migrate`, apply `deploy/db-roles.sql` and `deploy/db-roles-curator.sql` again; with the runner, also the new `deploy/db-roles-decider.sql` (the role `kutuphane_decider`). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- `llmdap.chat` takes request options (the runner sends `temperature: 0`); new `llmdap.systemone` for typed-decision routes (Laya, `deploy/deciders/laya-notes.json`). ([#117](https://github.com/ekaynac/kutuphane/pull/117))

### The curator queue and its measures (#77, docs/25 slice Q)

- New: the curator queue. The pending notes of the books where the curator holds `curate` and `read`, in risk order (tier 1: an approval that changes what is current; then decision proposals, conventions, findings, lessons and dead ends, test results), as `same_as` groups, at a watermark: the same watermark gives the same queue. Read [operations.md](operations.md), section 7, "The queue". ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- Curator web: the page shows the queue. One passkey act decides a batch or a whole group (1–50 notes, one reason, one Standing event per note); **Select group** selects a group. The routes `GET /api/queue` and `GET /api/note/{book}/{id}` replace `GET /api/pending`. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- Each card shows every part of the note that its id covers: the text, the scope, the class key, the commit, the decision options and choice, the citations, and the links with the target text. A note with a citation or a creation link into a book that the curator cannot read cannot be approved on the phone (security review #16, finding 1). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- A model suggestion and a delegation sample are never in the queue and never change its order (D67). The act receipt shows them after the decision. ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New command `kutuphane curator queue --curator user:<name>`: the same queue on the command line (Pilot 2 G36). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
- New command `kutuphane curator report --from D1 --to D2`: curator seconds per approved note, the share still pending after 7 days (by tier and by book), who decided, and the delegations. ([#117](https://github.com/ekaynac/kutuphane/pull/117))

### Curator web with passkeys (D72, docs/25 slice P)

- New: curator web, the phone page of the curator. A curator approves or rejects pending notes and signs each decision with a passkey (WebAuthn, user verification required). The passkey signs the exact statement: the notes and their digests, the Standing in force, the new values and the reason. Install: [install.md](install.md#curator-web); use: [operations.md](operations.md), section 7. The CLI path (`note standing`) stays and works as before ([#115](https://github.com/ekaynac/kutuphane/pull/115)).
- New commands: `kutuphane curator enroll|passkeys|revoke-passkey|verify-acts|web` ([#115](https://github.com/ekaynac/kutuphane/pull/115)).
- Migration `023_curator_passkey.sql` (persons, enrollments, passkeys, sessions, challenges, acts; `standing_event.act`). After `migrate`, apply `deploy/db-roles.sql` again; with curator web, also the new `deploy/db-roles-curator.sql` (the role `kutuphane_curator_web`) ([#115](https://github.com/ekaynac/kutuphane/pull/115)).
- New overlay `deploy/compose.curator.yaml`: the curator container and a Tailscale sidecar with its own tailnet host name (HTTPS, never Funnel). `deploy/curator_probe.py` checks a deployment ([#115](https://github.com/ekaynac/kutuphane/pull/115)).
- New dependency: `webauthn` 3.0.1 (py_webauthn, BSD-3-Clause) ([#115](https://github.com/ekaynac/kutuphane/pull/115)).
- Design: `docs/25-curator-queue-passkey-design.md`, the curator queue, passkey acts, the "my words" confirmation and delegated curate ([#113](https://github.com/ekaynac/kutuphane/pull/113)).

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

### Design and research

- Labelling v5: Astra read the 60 second-reader cases blind, and `experiments/labeling_v5/compare_second.py` compares its answers with the operator's labels (agreement, Cohen's kappa, disagreements) ([../20-labelling-curation-v5.md](../20-labelling-curation-v5.md) §8) ([#126](https://github.com/ekaynac/kutuphane/pull/126)).

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
