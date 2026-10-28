# Changelog

This file lists the changes that users and operators can see.
The newest changes are first.
Each date has the pull requests (PRs) that were merged on that date.
Decision D75 is the rule for this file: each feature PR updates the related user documentation in the same PR, and it adds its entry here.
Internal work (decision records, research notes, labelling experiments) is in one "Design and research" line for each date.
For the terms, read [concepts.md](concepts.md).

## Unreleased

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
- New MCP tool `confirm_origin` and route `GET /v1/notes/{book}/{id}/confirmation`: the state (`open`, `confirmed`, `expired`, `none`) and the URL. A 2026-07-28 client with the `elicitation.url` capability gets a URL-mode elicitation; the tool never uses a form, and an `accept` confirms nothing ([mcp.md](mcp.md#516-confirm_origin)). ([#117](https://github.com/ekaynac/kutuphane/pull/117))
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
