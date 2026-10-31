# Direction analysis — Kütüphane, 2026-10-31

Read-only analysis of `main`, issues #67–#165 and the docs. `[INFERENCE]` marks a claim with no direct evidence.

## 1. Where we are

Kütüphane today is a Postgres note store for coding agents plus a kstd-aware file catalog with hybrid search, both served over MCP and HTTP, with a large curation apparatus on top (passkey web, "my words" confirmation, a model decider with delegated approval, SkillSpector blocks). The code is 14,491 lines in 51 modules, 38 migrations, 18 MCP tools plus the Skills methods, about 60 CLI commands, 5 compose files, 4 database roles and 52 `KUTUPHANE_*` settings. Real traffic is narrow: one live journal (`nobetci-memory`; #67 comment 2026-10-29: `propose_note` 1.3 s, `query_notes` 40 ms), one canon book (`inframedic-canon`, `docs/26`), and the operator as the only curator. ADC's one measured A/B (#121, T3) cost +50 % input tokens with acceptance 8/9 vs 9/9; the rerun waits for a model. InfraMedic consumes nothing in production yet: its W4 design (#144, 2026-10-31) is at phase P0 and filed ten issues. So: the governed catalog and memory layer of D69 exists and works. The proven value sits in the catalog side (origin, rights, packages, scope) and in cheap deterministic note reads. The value of the heavy curation stack is not yet shown by use.

## 2. The surface map

| Surface | State | Who uses it | Evidence |
|---|---|---|---|
| `query_notes`, `neighbours`, `propose_note`, `link_notes`, `record_outcome` | solid; thin edges | nöbetçi-mcp (live), ADC (tests) | 40 ms reads; #152 bug; #153, #155, #154 |
| `search_library`, `open_citation`, `read_document`, `max_chars` | solid | ADC T3, InfraMedic pilot | #121: −76 % result size; `docs/26` |
| `ask_library`, jobs, `reopen_answer` | solid; slow without GPU | pilots only | 30 s mean (`docs/26` §5.1); 8–10 s with #131 |
| Catalog read: list books, versions, files | **missing** | InfraMedic | #159; `server.py` has no list route |
| Publication facts: who approved a version | missing | InfraMedic | #160; only `package_import` has `decided_by` |
| Packages (`export`, `receive`, `approve-import`, `submit_package`) | solid | InfraMedic (planned) | #139 merged; #161, #162 asked |
| Identity: one issuer, dev tokens | thin | every consumer | #73 open (8 h token, timer workaround); #157 |
| Audit for consumers (correlation id) | thin | InfraMedic | #156 |
| Curator web (queue, acts, My words, delegations) | **over-built for its use** | the operator alone | 5 review rounds → migrations 026, 029, 038, 039, 044; 1 curator; [INFERENCE] 0 live delegations, 0 confirmations |
| Decider + delegated curate (D73) | over-built; unused | nobody | own DB role, 2 CLI groups; D77 forbids standing `propose` on InfraMedic journals |
| `record_runbook_feedback` | dead weight | nobody known | `feedback.py`; duplicates `record_outcome` |
| kstd manifest and loader | solid core; wide spec | both pilots | D74 works; `docs/11` has 8 statement kinds, code and cases use 4 |
| Install and operations | thin for unattended use | operator | #141 open; Core ran as a hand-started `uvicorn`; 5 compose files |
| `docs/guide` | complete; heavy | all | 52,721 words |
| Standard text (`docs/11`) | over-built vs code | nobody outside | `contest`, `use_record`, `disposition`, federation, erasure: no code, no cases |
| MCP Skills + SkillSpector | solid; no consumer | none | #80, D71 |

## 3. Gaps against the plan

**Planned:** #73 live probe and client credentials; #138 G10 (D65: after decision cases); #141 reboot test; #121 rerun; #81 (low); labelling v5 human set (`docs/20`); `docs/21` §5 successor field and §6 spec points; `docs/09` blocks and annotation events (approved, never built); Pilot 2 step 6 (`docs/26` §7.6).

**Not planned before 2026-10-29/31:** all of #152–#165. The roadmap (`docs/23` §7) ends at R3 and has no consumer-contract work: no catalog listing (#159), publication facts (#160), correlation id (#156), second issuer (#157), note scope by platform (#164), notes as evidence (#163), DB-free `pack` (#161). Also unplanned: `curate` grants written with the app-role DSN (#67 comment), against `security.md`.

## 4. New surfaces from real use

| Surface | From | Fits D69? |
|---|---|---|
| Consumer read contract: list books and files, item information, who approved, correlation id (#156, #159, #160) | InfraMedic | **Yes.** A catalog that cannot list itself is not a catalog. Core gap. |
| Package submission, DB-free `pack`, package approval on the phone (#139, #161, #162) | InfraMedic | #139, #161 yes. #162 is drift toward a CMS workflow; `approve-import` already does it. |
| Multi-issuer auth; roles from token claims (#157, #158) | InfraMedic | #157 yes. #158 moves the grant truth out (`docs/09` §4.3): accept only read-only, `curate` refused, or reject. |
| Notes as evidence in search and ask (#163, G33) | InfraMedic | Half. Memory feeding the governed source is D69; but it merges two retrieval paths and adds a citation kind (D53). Decide after B. |
| Labels on notes (#154) | nöbetçi-mcp | Drift: D65 tags again. `class_key` + scope exist. Narrow or reject. |
| Shared external LLMDAP with purposes (#165, D76) | both products | Yes, operations. |
| The operator's daily use: phone curation, hand units, timer-minted tokens | operator | Yes. It shows install and identity are the weak surfaces, not curation. |

## 5. Facets

**Develop:**
- **Standing on book versions.** Files have no Standing; a version is "accepted" by whoever ran `ingest` or `approve-import`, and nothing shows it (#160). `approved_by` + channel on `publication` closes P1 for files.
- **Scope.** Notes use `repo/branch/paths`; files use `applies_to {platform, version}` (#137); #164 wants both. Make one Scope facet with one context object on every read.
- **Origin.** Keep; strongest facet (D70, DB check in `write_record`). Add nothing.

**Keep:** Sensitivity, Egress, `ai_use.search`/`ai_input`/`train`, `personal_data` + legal basis, `license` (#143), Agent instruction (`agentfiles.py`), note `kind`.

**Freeze or remove (D53/D74):**
- **Role and Time basis as facets.** On notes they are derived from `kind` (`KIND_ROLE`, `KIND_TIME`); on files they do not exist. Two names for `kind`. Remove from the guide; keep `kind`.
- `holder`, `issued`: no behavior.
- `valid_from`/`valid_to`: act only when the caller sends `current_only` or asks for "latest" (`search.Scope.admits`). Either make an expired file `history` by default, as notes are, or call validity advisory in `kstd.md`.
- `review_by`, split marks, continuity links, annotation events (`docs/09` §1–§3): never built. Freeze.
- Tags and access tags (D65, #154): freeze until G10 has a consumer.
- kstd kinds `contest`, `use_record`, `disposition`, `policy`, federation, erasure: an appendix "not in the reference".

**Two mechanisms, one job:**
1. `record_runbook_feedback` vs `record_outcome`.
2. Note scope vs `applies_to`.
3. Passage citation vs `about` link (both feed `neighbours` since G32).
4. Three acceptance paths: Standing event, `approve-import`, silent `ingest`.
5. Two "delegation" words: grant delegation and curate delegation.
6. `read_document` vs `GET /v1/files` vs `resources/read skill://`.
7. `reopen_answer` vs `job_result`.
8. `class_key` vs labels (#154).

## 6. The complexity budget

Signs:
- 38 migrations in 10 days; five are review patches to one stack, each with "re-apply three role scripts".
- A new user meets about 30 concepts: book, version, profile, passage, journal, note, 6 kinds, 8 link types, 4 Standings, 5 origins, 3 `ai_use` terms, sensitivity, egress, protection, 7 grant modes, delegation, curate delegation, decider spec, act, confirmation, package, trusted key, skill scan, watermark, `class_key`, scope, `applies_to`, handling labels.
- 60 CLI commands, 52 settings, 5 compose files, 4 DB roles, 3 probe scripts, 52,721 guide words for one operator.
- The D73 stack is about 2,000 lines, 3 migrations, 1 DB role, 2 CLI groups, with no live use.

Reductions:
1. Delete `record_runbook_feedback` and `feedback.py`.
2. Put the decider and delegated curate behind one off-by-default setting, or remove them until `curator report` shows more than one curator and a backlog. [INFERENCE] the backlog is 9 notes (D77).
3. Two compose files (light, full) with profiles.
4. One migration per release; batch review fixes; a baseline migration for new installs.
5. Cut the guide: one page per role; design history out.
6. `docs/11` normative text = what `decide.py` and the cases test.
7. One Scope object on every read.

## 7. Vision refresh (`docs/23`)

- §1 sentence: add "…and **shows what it holds**: an application can list the books, versions and files that it may read."
- §2 "is not": add "an identity provider or a role store: tokens come from the IdP, grants live here" and "a package workflow UI: a package is approved once, on the CLI".
- §3 evidence column: P2 "Gap: no agent write path (#68)" → "Built (D70; DB check `write_record.origin`)"; P4 → "Built (#72, #79, passage map); not measured in use"; P5 → "Built: `query_notes` 40 ms, `max_chars` −76 %; open: T3 rerun".
- §4 users: add "4. **Consumer applications** (InfraMedic): they submit signed packages, read the catalog with a scope context, and show Standing and citations in their own screens." Replace "through a fast queue (#77)" with "on the phone (D72) or the CLI".
- §5: add a row "serve | consumer contract | the book list, item information, publication facts, the caller's correlation id".
- §6: replace "it stays open" with "Decided (D74). The reference implements `item`, `acceptance`, `handling`, `mandate`; other kinds are an appendix until a consumer needs them."
- §7: replace R1–R3 (done) with the three areas below; D73 marked frozen.
- §8: add "a second consumer reads from Kütüphane in production" and "concept and command counts go down each release".

## 8. Three areas to continue in

### A — The catalog contract for consumers
- **Goal:** an application can list what it may read, see who approved each version, and trace every call.
- **Why now:** InfraMedic P1 is blocked on #159, #160, #156, #157; it is the only external consumer with a dated plan (#144).
- **Includes:** `GET /v1/books` + `list_books` (with `kind: book|journal`); the files of a version with kstd item information; `approved_by` and channel on `publication`; a caller correlation id echoed on every response; a second issuer bound to a principal prefix (#157); #165 purpose names.
- **Excludes:** #158 (decision), #138 G10, #162, #163, anything in `notes*.py`.
- **Files:** `server.py` routes, `catalog.py`, `identity.py`, `gate.py`, `packages.py`, `llmdap.py`.
- **First step:** `GET /v1/books` and `list_books`, gated on `read` per book; hidden books never named.
- **Signal:** InfraMedic's knowledge screen shows Kütüphane items with Standing and citations with no direct DB access; every InfraMedic request is in `access_event` under its own correlation id.
- **Decisions:** the InfraMedic issuer and JWKS; #158 narrow or reject; `kind` on the list.

### B — Agent memory precision
- **Goal:** an orchestrator can scope, find and follow its own proposals with no workaround and no extra calls.
- **Why now:** nöbetçi-mcp runs `memory.mode = ab` and filed #152–#155 from one evening; #164 asks for the file scope shape on notes.
- **Includes:** #152; `refs` on `query_notes` (#155); `paths` list (#153); one Scope object with `platform`/`version` on notes (#164); `record_outcome` absorbs runbook feedback (delete `feedback.py`); a decision on #154 (prefer `class_key` + scope).
- **Excludes:** #163 (decide after B), curator web, decider, any new link type or kind.
- **Files:** `notes.py`, `notesquery.py`, `noteimport.py`, `outcomes.py`, `feedback.py`, one migration.
- **First step:** fix `_glob_prefix_ok` (#152) and add `refs`; both small, both unblock nöbetçi.
- **Signal:** nöbetçi runs `memory.mode = on`; an A/B shows acceptance not lower and input tokens not higher than without memory; `curator report` shows the 7-day pending share under a value the operator sets.
- **Decisions:** one scope shape; #154 yes/no; #163 go/no-go after B.

### C — Simplify the operator surface and the standard
- **Goal:** fewer concepts, commands, files and words, with no loss that a user can see.
- **Why now:** 150 PRs in 10 days; five review-patch migrations on one stack; Core and curator web run from hand units (#141 comment); `curate` grants bypass the curator DSN (#67 comment).
- **Includes:** the `curate` grant DSN fix; #141 reboot test and a host unit recipe; #73 single-host client-credentials recipe; two compose files; decider and delegated curate off by default; `docs/11` appendix; Role/Time removed as facets from the guide; a baseline migration for new installs; the guide cut.
- **Excludes:** any new tool, route, facet or behavior; `notes*.py`; `catalog.py`.
- **Files:** `cli.py`, `authz.py`, `deploy/*`, `compose.yaml`, `docs/guide/*`, `docs/11`, `docs/09` status note, `migrations/` baseline.
- **First step:** record the frozen list as one decision (D78) in `docs/01`, and make `grant … curate` refuse the app role.
- **Signal:** after one release, modules, migrations on a new install, CLI commands, settings, compose files and guide words are all lower; the quick start fits one screen.
- **Decisions:** delete runbook feedback; freeze D73; the `docs/11` appendix; two compose files; the guide cut.

A, B and C touch different files (server/catalog/identity; notes/outcomes; cli/deploy/docs/kstd), serve different users (InfraMedic; nöbetçi/ADC; the operator) and need different decisions.

## 9. Stop or defer

- **Stop:** `record_runbook_feedback`; new kstd statement kinds; block-level ontology (`docs/09` §1–§3); a migration per security review; #81 (close).
- **Freeze:** decider and delegated curate (D73) until a second curator or a backlog exists; "my words" gets no new work; labelling v5 only as measurement.
- **Defer:** #163 (after B); #162 (the CLI does it); #138 G10 (no second consumer); #158 (narrow or reject); #121 rerun only if a model is cheap.
