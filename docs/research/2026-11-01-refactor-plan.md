# Refactor plan — Kütüphane, 2026-11-01

Read-only analysis of `main` with static tools; no test run. `[INFERENCE]` marks a claim with no direct evidence. Each slice follows `ponytail-kutuphane` at level **ultra**.

## 1. Complexity facts

**Size.** 14,552 lines in 50 modules, 963 functions, 88 classes. Tests: 48 files, 13,892 lines, 1,047 tests. 38 migrations (`001`–`044`; gaps at 030, 031, 034–036, 043). 53 CLI leaf commands in 8 groups (`cli.py:654-947`). 51 `KUTUPHANE_*` names (40 read by code, 11 compose-only). 5 compose files, 398 lines. Guide: 53,083 words.

| Module | Lines | Module | Lines |
|---|---|---|---|
| notesquery | 1,154 | curatorqueue | 542 |
| notes | 1,074 | packages | 511 |
| cli | 969 | skillscan | 458 |
| server | 800 | passkey | 441 |
| kstd | 559 | decider | 391 |
| coderepo | 559 | delegation | 360 |

**Import hubs.** Fan-in: `gate` 28, `authz` 17, `ids` 16, `kstd` 14, `notes` 12, `search` 10, `db` 10. Fan-out: `cli` 31, `server` 24, `notes` 17, `packages` 12, `notesquery` 11. Two late imports break cycles: `notes.py:767` imports `confirm` inside `propose`; `passkey.py:439` imports `delegation` at the end of the file.

**Duplicated rules.**

| Rule | Copies | Area |
|---|---|---|
| Curator check: `user:` principal + reason 1..500 | `curation.py:25-29`, `notes.py:856-860`, `skillscan.py:437-440`, `delegation.py:164-166`, `passkey.py:153` | C / B |
| Book slug regex `^[a-z0-9][a-z0-9-]{0,62}` | `search.py:99`, `notesquery.py:44`, `notes.py:56`, `authz.py:20` (with `book:`), `001_catalog.sql:21` | free / B |
| `REPO`, `CLASS_KEY` regex; `LINK_TYPES` | `notes.py:38,58-59`, `notesquery.py:31,45-46` | B |
| Passage handle parser | `server.py:68-76` ("malformed citation handle", `BadRequest`), `notes.py:77-88` ("malformed passage handle", `ValueError`, adds a control-char check) | A + B |
| Write-path origin SQL (`bool_or(wr.origin = 'model')`) | `origin.py:47-48`, `notesquery.py:246-247` | B |
| `skill_block` rule in Python | `skillscan.py:79-82` repeats the view `021_skill_scan.sql:46-53` | keep (§4) |
| Current-version join | `search.py:64`, `vectors.py:97`, `quotes.py:118` | keep (§4) |
| `curate`+`read` rights read | `curatorqueue.py:43`, `curatorweb.py:274` | C |
| `set_by LIKE 'model:%'` aggregate | `curatorqueue.py:502`, `delegation.py:278` | D73 |

**Dead code.** `source.SEARCHED_TYPES` (`source.py:58`, 0 references). `catalog.whole_profile` (`catalog.py:29-30`, tests only). `notes.item_info` (`notes.py:400-410`; its docstring names `server._text`, which does not call it; tests only). `health.py:7` unused `annotations` import. `feedback.py`, table `runbook_feedback`, tool `record_runbook_feedback`, route `/v1/feedback`: no known consumer.

**Settings.** Every name that code reads is used. Frozen or redundant: `KUTUPHANE_DECIDER_DSN`, `_DECIDER_LLMDAP_KEY`, `_DECIDER_BOOKS`, `_DELEGATION_MIN_SHADOW` (D73); `_CURATOR_URL`, `_CONFIRM_HOURS` ("my words"); `_DB_PORT`, `_PORT` (only `compose.light.yaml:24,57`, not in `operations.md`).

**CLI.** `grant`/`revoke` (`cli.py:688-693`) run on the app DSN, so a `curate` grant bypasses the curator credential (C's first step; a behavior change, not a refactor). Groups `decider` (2) and `delegation` (4) serve D73 only. `curator queue`/`report` and the curator-web pages share one implementation (`curatorqueue`): fine.

**Migrations.** `db.migrate` (`db.py:31-43`) applies every `.sql` in name order. `tests/test_migrations.py:11,30,58` rebuild from 005, 011, 012 and replay forward, so old files must stay. Baseline option: a generated `migrations/baseline/schema.sql` (`pg_dump --schema-only`) that `migrate` applies when `schema_migration` does not exist, then marks every file applied. Cost: about 15 lines in `db.py`, one dump per release, one test that baseline equals replay (W2-6).

**Tests that pin wiring.** `test_server.py:417-420` (`TOOLS` order: a deliberate contract, keep). `test_settings.py:17,73` (the compose file list and its variables; changes with W1-4). `test_skillspector_contract.py` (the external binary). Tests of dead functions: `item_info` in `test_notes.py:126,132,134,512,553`, `test_confirm.py:103,140`, `test_rollback.py`; `whole_profile` in `test_authz.py`, `test_ingest.py`, `test_search.py`, `test_egress_audit.py`.

## 2. Refactor slices

One PR per slice. Behavior-preserving unless the row says "test change". Proof = the existing tests unchanged, plus the smoke check named.

### Wave 1 — now, no file of area A or B

| # | Slice | Files owned | Deletes / merges | Net lines | Risk | Proof | Decision |
|---|---|---|---|---|---|---|---|
| W1-1 | **Remove D73** (§3 option B) | `decider.py`, `delegation.py`, `curatorweb.py`, `passkey.py:437-441`, `curatorqueue.py:395-412,475-530`, `curator_ui/delegation.js`, `curator_ui/index.html`, `cli.py` (groups `decider`, `delegation`), `deploy/db-roles-decider.sql`, `deploy/deciders/`, guide | 2 modules, 6 commands, 4 settings, 1 role script, 1 UI tab; tests `test_decider.py`, `test_delegation.py`, D73 parts of `test_curator_review17.py`, `test_curator_queue.py`, `test_astra_review19.py` | about −1,300 src, −1,100 tests | Stored `delegate` acts would fail `verify-acts`: run `SELECT kind, count(*) FROM curator_act GROUP BY kind` first (`[INFERENCE]` 0). The queue receipt loses `suggestions`/`sample`: a response-shape change | `test_curatorweb.py`, `test_curator_e2e.py`, `test_curator_review16.py` unchanged; `kutuphane curator verify-acts` = 0 problems | **Yes**: remove or flag |
| W1-2 | **One curator check** `authz.curator(principal, reason)` | `authz.py`, `curation.py:25-29`, `skillscan.py:437-440` | merges 3 copies; error texts stay byte-equal | about −8 | `authz` must not import `notes`; the check uses `authz.PRINCIPAL` only | `test_skillscan.py`, `test_curation_db.py` | No |
| W1-3 | **One slug regex** `ids.SLUG` | `ids.py`, `search.py:99`, `authz.py:20` | merges 2 of 5 copies (rest in W2-2) | about −2 | None: same pattern string | `test_search.py`, `test_authz.py` | No |
| W1-4 | **Two compose files** | `compose.yaml`, `deploy/compose.*.yaml`, `tests/test_settings.py:17`, `install.md` | light becomes `compose.yaml`; curator, GPU and hosted become profiles of `deploy/compose.full.yaml`; drops `_DB_PORT`, `_PORT` | −398, +about 250 | **Test change**: `test_settings.py:17` lists the files. `[INFERENCE]` the host runs `compose.yaml` + local-models; #141 reboot test must follow | `docker compose config` per profile equals the old merged config (normalized diff) | **Yes**: layout |
| W1-5 | **Dead names** | `source.py:58`, `health.py:7` | `SEARCHED_TYPES`, the import | −2 | None | full suite | No |
| W1-6 | **Guide and standard cut** (area C text) | `docs/guide/*`, `docs/11`, `docs/09` status note, `docs/01` (D78) | Role/Time out as facets; `docs/11` appendix for `contest`, `use_record`, `disposition`, `policy`, federation, erasure; design history out of the guide | about −15,000 words | A rule that code enforces drops out of the text: after the cut, `grep` each command, setting and tool name; each appears once | the grep list | **Yes**: the cut list |

Run W1-1 before W1-2; W1-1 removes the `delegation.py:164-166` copy.

### Wave 2 — after A and B merge

| # | Slice | Files owned | Deletes / merges | Net lines | Risk | Proof | Decision |
|---|---|---|---|---|---|---|---|
| W2-1 | **Runbook feedback out** (if B did not; B's list names `feedback.py`) | `feedback.py`, `server.py:246-261,440-449,492,740-747`, `test_feedback.py`, `test_server.py:263-273,418`, `mcp.md §5.6`, `http-api.md §8`, `concepts.md:228-232`, changelog | 1 module, 1 tool, 1 route, 5 tests; **test change**: `TOOLS` loses one name | about −70 src, −80 tests | `SELECT count(*) FROM runbook_feedback` first; keep the table, or drop it in one migration when 0 | `test_server.py`; `deploy/mcp_probe.py` | **Yes**: drop table or keep |
| W2-2 | **Shared note constants** | `notesquery.py:31,44-46`, `notes.py:38,56,58-59` | `notesquery` imports `LINK_TYPES`, `REPO`, `CLASS_KEY` from `notes`; `notes.BOOK` becomes `ids.SLUG` | about −6 | None | `test_notes_query.py`, `test_notes.py` | No |
| W2-3 | **One passage-handle parser** | `server.py:68-76`, `notes.py:77-88` | `server.parse_citation` calls `notes.parse_passage`, maps `ValueError` to `BadRequest`; the HTTP text becomes "malformed passage handle" | about −8 | One error text changes: **not byte-equal**; grep the old text in tests and the guide first | `test_server.py`, `test_passage_map.py` | No; name the text change |
| W2-4 | **One write-path-origin SQL** | `origin.py:47-48`, `notesquery.py:246-247` | `notesquery` reads origin only through `origins.shown` (already called at `:274`) | about −3 | One extra query per read: measure `query_notes` (40 ms today) | `test_notes_query.py`, `test_confirm.py` | No |
| W2-5 | **Dead functions with tests** | `catalog.py:29-30`, `notes.py:400-410,856-860`, tests in §1 | `whole_profile` (tests call `profiles.spec("whole")`), `item_info` (tests read `origins.shown` and the journal rights), `_curation` → `authz.curator` | about −20 src | **Test change**: the tests used dead functions as probes; the asserted facts stay | the same assertions on public reads | No |
| W2-6 | **Baseline migration** | `db.py`, `migrations/baseline/schema.sql` (generated), `test_migrations.py` | adds a new-install fast path; deletes nothing | +15 src, +about 2,500 generated | A second schema source: regenerate per release or the test fails. Only after A's and B's migrations exist | new test: baseline schema == replayed schema (`pg_dump` diff of two `_test` DBs) | **Yes**: do it, or stop at "one migration per release" |

## 3. The frozen stack

**Size.** D73: `decider.py` 391, `delegation.py` 360, `delegation.js` 165, `cli.py` about 80, `curatorweb.py` about 30, `curatorqueue.py` about 70, `passkey.py` 5, `db-roles-decider.sql` 25, 2 spec files; migrations 025, 029 (+038 re-creations); 4 settings; about 1,100 test lines. "My words": `confirm.py` 346, `confirm.js` 176, `notes.py:767-768`, the confirmation branch of `origin.shown` (`origin.py:47-85`), 2 curator-web routes, 1 MCP tool, 1 HTTP route, migration 024, 2 settings; tests 698 lines.

**Option A — one setting, off by default: `KUTUPHANE_CURATION_EXTRAS=1`.** When off: `server.FEATURES` drops `confirm` (no `confirm_origin`, no `/confirmation` route); `notes.propose` skips `confirm.receipt`; `curatorweb` does not register the `confirm`, `withdraw`, `delegate`, `end_delegation` handlers, fields, routes and tabs; `cli.parser` omits `decider` and `delegation`. Never gated: `passkey.EFFECTS` for the two act kinds (stored acts must verify), `origins.shown` (a stored confirmation stays visible), the triggers of 024/025/029, the role scripts. Cost: about +40 lines, two configurations in the suite (`conftest` sets the flag; `TOOLS` needs a run with and without). No data loss; reversible at once.

**Option B — remove D73; keep "my words" as it is.** Delete the W1-1 files. Keep every table (no `DROP`, no data loss). Keep the `passkey.EFFECTS` entries only if stored `delegate` acts exist. "My words" stays: it is the only path to `origin: human` (D70 R3), part of the Origin facet that the analysis keeps, and it needs no new work. Cost: about −1,300 src, −1,100 tests, −6 commands, −4 settings, −1 role script. Re-adding is one `git revert`.

**Recommendation: B.** A flag is a third mechanism around two unused ones; it adds code and a dormant configuration that the suite must cover. D73 has no user and no live delegation `[INFERENCE]`; D77 forbids its standing `propose` on the InfraMedic journals. "My words" is small and woven into every read through `origins.shown`; removing it changes `query_notes` output for any confirmed note. If the operator wants one switch over both, take option A under the name above.

## 4. Things NOT to refactor

| Item | Reason |
|---|---|
| `authz._DECIDE`, `gate.guard_many` (`authz.py:119-160`) | Fail-closed; Astra #15 made the right and the block one snapshot. A split re-opens that window. |
| SQL `skill_blocked`, `note_skill_blocked`, `passage_successor_blocked`, view `skill_block` | The one rule copy every reader uses. `skillscan.blocking()` is a Python copy that runs before rows exist (`receive` findings); leave it. |
| Current-version join (3 copies) | A plain join, not a gate; a shared constant saves 0 lines and hides the query. |
| `passkey.py`, `canonical.py`, `curation.py` | Signed statements and byte-exact canonical forms: a change is a security review. |
| The three `*_ROUTE_CLASS` settings | An egress gate per route with no default (`test_settings.py:96`). One setting loosens it. |
| Applied migrations; `test_migrations.py` replays | Never edit an applied migration; the replays prove the upgrade path. |
| `test_server.py` `TOOLS` snapshot | A contract with cache hints (#121). Update only when a tool goes (W2-1). |
| `kstd.py`, `catalog.py`, `identity.py`, `gate.py`, `packages.py`, `llmdap.py`, `notes*.py`, `outcomes.py` beyond W2 | Areas A and B own them. |
| `cli.py` as one module | A split by group gives no fewer lines and a second import graph; the parser is the documentation. |

## 5. The measurement

Report before and after each wave; all commands are read-only.

| Number | Before | Target after W1 + W2 | Command |
|---|---|---|---|
| Source lines | 14,552 | about 13,150 | `wc -l src/kutuphane/*.py` |
| Modules | 50 | 47 | `ls src/kutuphane/*.py` |
| Functions / classes | 963 / 88 | about 880 / 80 | the AST count script |
| `KUTUPHANE_*` settings | 51 | 45 | the regex count script over `src/`, compose, `operations.md` |
| CLI leaf commands | 53 | 47 | `grep -c 'set_defaults(fn=' cli.py` + 1 |
| MCP tools | 18 | 17 | `test_server.py` `TOOLS` |
| Compose files / lines | 5 / 398 | 2 / about 250 | `wc -l compose.yaml deploy/compose.*.yaml` |
| Migrations on a new install | 38 | 1 baseline + new (W2-6), else 40 | `kutuphane migrate` on an empty `_test` DB |
| DB role scripts | 3 | 2 | `ls deploy/db-roles*.sql` |
| Test files / tests | 48 / 1,047 | about 44 / 980 | `pytest --collect-only -q` |
| Guide words | 53,083 | under 35,000 | `wc -w docs/guide/*.md` |
| Concepts (analysis §6 list) | 30 | 24 (−decider spec, −curate delegation, −suggestion, −runbook feedback, −Role, −Time) | count the `concepts.md` list |
| Duplicated rules (§1) | 9 | 2 kept on purpose | the duplicate-line script |

**Skipped or not checked:** no test run and no database query; the row counts of acts, delegations, confirmations and feedback are `[INFERENCE]` 0. `vulture` is not installed; the dead-code list comes from a name-reference scan over `src/` and `tests/`. **Risk:** W1-1 and W2-1 delete code with tests behind it; run the row counts first and keep the tables in every case.
