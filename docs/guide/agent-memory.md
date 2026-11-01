# Agent memory: a how-to for orchestrators

This page is for the builders of coding orchestrators (for example ADC and nöbetçi-mcp). It shows how an
orchestrator keeps its decisions, findings, lessons and conventions in Kütüphane, and how people accept them. The
contract is `../24-r1-agent-memory-design.md`. The tool reference is `mcp.md`.

Kütüphane holds knowledge. Run state (goals, jobs, costs) stays in the orchestrator's own event log.

## 1. Set up (operator)

```sh
# a journal for the orchestrator; search and AI input must be stated
kutuphane journal create adc-memory --search y --ai-input y \
  --sensitivity normal --egress local_only --protection standard --by user:admin
# the orchestrator writes and reads its notes
kutuphane grant book:adc-memory propose agent:adc
kutuphane grant book:adc-memory read agent:adc
# the orchestrator reads the project documents
kutuphane grant book:<docs-book> read agent:adc
# a person accepts notes (users only; never delegated)
kutuphane grant book:adc-memory curate user:ayse
# optional: code citations into a bare mirror that you keep current
kutuphane repo add adc-memory adc /srv/repos/adc.git --ref 'refs/heads/*' --by user:admin
```

Add `--train y` to `journal create` only if decision records may leave as training data (see step 8).

**Token.** The orchestrator gets an OAuth client-credentials token from the IdP. The IdP mapper sets
`kutuphane/principal_type: agent` and `sub: adc`, so the principal is `agent:adc`. For work on behalf of a person,
use an RFC 8693 token exchange and a delegation (`kutuphane delegate`). For development, use
`kutuphane dev-token adc --agent …` (see the `README.md` quick start).

## 2. Propose a note

```json
{"name": "propose_note", "arguments": {
  "book": "adc-memory",
  "kind": "finding",
  "text": "The retry loop in run.py does not stop after a 4xx response.",
  "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"],
  "scope": {"repo": "adc", "branch": "main", "paths": ["src/**"]},
  "commit": "3f2c…e1",
  "class_key": "retry-on-4xx",
  "idempotency_key": "adc:run-41:finding-1"}}
```

| Choose | When |
|---|---|
| `kind` | `finding`, `lesson`, `dead_end`, `test_result` (evidence); `convention`, `decision_proposal` (rules) |
| `citations` | up to 20: passage handles (`book@ct_…/pf_…/path#n`) or code citations (`repo@<full commit>:path:start-end[#symbol]`, at most 200 lines) |
| `scope` | the repo, branch and path globs where the note applies; a scoped `rule` needs a matching read context |
| `commit` | the commit you observed; needs `scope.repo` |
| `links` | creation links: `derived_from` and `supersedes` exist only here |
| `class_key` | a label for one class of problem; repeated classes set `guard_due` |
| `decision` | only for `decision_proposal`: `{"options": [2..20 strings], "choice": one of them}` |
| `idempotency_key` | always; 8–128 characters of `A-Z a-z 0-9 . _ : -` |

The receipt:

```json
{"ref": "adc-memory@nt_…", "status": "created", "standing": "pending", "origin": "model", "origin_notice": null,
 "candidates": [], "recurrence": 1, "class_count": 0, "guard_due": false, "vector": "stored"}
```

- Every note starts `pending`. Origin is `model` on every agent path. You cannot claim `human`: a token is not a
  person's act. When the person dictated the words, propose with `origin: "human"` (or `"assisted"` when you
  reworded them). The receipt then has `origin_notice: "origin-claim-refused"` and
  `confirmation: {"url", "expires_at"}`. Give the URL to the person, or call `confirm_origin` (a 2026-07-28 client
  shows the URL itself). Only the person can confirm, in curator web with a passkey, within 24 hours. Then the note
  shows `origin: human` with `entered_by` (you) and `confirmed_by` (the person). Change one byte and it is another
  note with origin `model` ([mcp.md](mcp.md#515-confirm_origin)).
- `status: existing` means the same bytes were already there. Its `standing` is the real value. If it is
  `rejected`, stop proposing it.
- `candidates` lists similar notes (`normalized`, `vector`, `class`). The server never merges them. Decide, and link
  with `link_notes` (`same_as` or `contradicts`).
- `guard_due: true`: this class occurs in 2 or more clusters of evidence notes (`finding`, `lesson`, `dead_end`,
  `test_result`) and no approved `convention` covers it. Build the test or lint in your orchestrator, then propose
  the convention with that `class_key`. The convention and a `decision_proposal` with the key do not count in
  `class_count`.
- A retry with the same key returns the first receipt. The same key with another request is refused.
- Your writes (notes, links, outcomes) count against `KUTUPHANE_NOTE_WRITES_PER_DAY` (default 500).
- A secret in the text refuses the note. The error names the rule, never the text.

## 3. Link notes later

```json
{"name": "link_notes", "arguments": {"src": "adc-memory@nt_…", "type": "fixed_by", "dst": "adc-memory@nt_…"}}
```

Later links: `same_as` (same book), `contradicts`, `about`, `fixed_by`, `violates`, `decided_by`. You need `propose`
on the book of `src` and `read` on the book of `dst`.

## 4. Read memory fast (no model call)

`query_notes` is the main read. It is SQL only, deterministic, and has a size limit. Notes are not in
`search_library` or `ask_library`: those search the passages of file books only. A journal in their `book` filter
gives the error `journal: use query_notes …`.

```json
{"name": "query_notes", "arguments": {
  "book": ["adc-memory"], "repo": "adc", "branch": "main", "path": "src/run.py",
  "kind": ["convention", "decision_proposal", "finding"], "collapse": true, "budget_tokens": 2000}}
```

- **Sets:** `current` (default; approved and valid in your context), `open` (pending), `history` (rejected,
  retired, test results).
- **Context:** give `repo`, `branch` (or `commit`) and `path`. A scoped `rule` note without a context is left out
  and counted in `excluded.needs_context`. With a `branch` or `commit`, code citations are verified against that
  target; a note with a `stale`, `missing` or `unverifiable` citation is not current (`excluded.code`).
  `include_unverified: true` shows them with their statuses.
- **Filters:** `kind`, `role`, `origin`, `class_key`, `written_after`, `written_before`, `commits` (`A..B`), `text`
  (full text), `unfixed` (findings with no `fixed_by`), and the outcome filters `min_passed` (at least n `passed`
  outcomes) and `exclude_failed` (no note whose latest outcome is `failed` or `reverted`), section 7.
- **Size:** `budget_tokens` (200–16,000, an estimate) and `max_bytes` (8,192–131,072, hard). Follow `next_cursor`
  until it is null.
- **Incremental reads:** keep the `watermark`. Next time, send `since: <watermark>`. You get changed `items` and
  `left` tombstones for notes that left the set (retired, rejected, reopened). Drop cached items of books that are
  not in `books`. If a branch head in `targets` moved, query again without `since`.
- The same request on the same data gives the same bytes, so the result can stay in a prompt cache.

HTTP: `GET /v1/notes?book=adc-memory&repo=adc&branch=main&kind=finding` (list parameters repeat).

**The documents (passages) in an agent loop.** Each tool result stays in the agent's context for all later turns.
A full `search_library` result is large (8 passages of up to 4,800 characters each). In a loop, search with
`max_chars` and open only the passages that you need:

```json
{"name": "search_library", "arguments": {"query": "retry backoff for failed jobs", "max_chars": 300}}
```

- Each `text` is a snippet of at most 300 characters around the words that match the query, with
  `truncated: true` when it is cut. The ranking and the gates are the same as without `max_chars`.
- The same request gives the same bytes, so the result can stay in a prompt cache.
- Call `open_citation` with the `citation` of a hit to get its full passage.
- On the user guide of this repository as a book, `max_chars: 300` made the median result of 8 queries 65%
  smaller: 12,959 to 4,578 characters for 8 hits ([#121](https://github.com/ekaynac/kutuphane/issues/121)).
  The rules are in [mcp.md](mcp.md#51-search_library).

## 5. Follow links

```json
{"name": "neighbours", "arguments": {"ref": "adc-memory@nt_…", "depth": 2, "direction": "both",
                                     "types": ["derived_from", "contradicts", "fixed_by"]}}
```

`ref` can also be a passage handle: then `root` is null and the nodes are the notes linked to that passage
(`about`, `derived_from`) and the notes that cite it (edge type `cites`). You do not need an `about` link next to a
citation.
`open_citation` opens one note (or passage) with its full text, Standing and `current` flag.

**After a re-index.** A new profile (for example a new chunker) or a new content version gives every passage of the
book a new handle. A note keeps the handle that it cites or links to, and that passage still opens. The reads add
where the passage is now, in the book's current version, for the same path:

| `status` | Meaning |
|---|---|
| `current` | the passage is in the current version |
| `moved` | `moved_to` is the passage that replaces it; `match` is `exact` (the same text) or `overlap` (the new passage holds at least half of its word pairs when only the profile changed, or the whole old text when the content changed) |
| `stale` | no passage of the current version replaces it; the citation stays |

Each passage citation of `query_notes`, `neighbours` and a note in `open_citation` has these keys, and so does a
passage in `open_citation`. `neighbours` from a passage also finds the notes on the passages that it replaces, and
from an old passage the notes on its successor. Such an edge keeps `dst` = the handle that you asked for and adds
`original`: the handle that the note stores. A model reader gets the text of a note withheld when the skill of the
successor passage is blocked (D71). The map is written when a version is published and when a note references an
older passage. For a book published before migration 040, run `kutuphane reindex-map <book>` once
([operations.md](operations.md#re-index-and-note-citations)).

## 6. Check code citations

```json
{"name": "verify_citations", "arguments": {"book": "adc-memory", "at": "main",
  "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"]}}
```

| Status | Meaning |
|---|---|
| `verified` | the same lines are at the same place in `at` |
| `stale` | the file is there, the lines changed; `moved_to` gives the new start line when the excerpt occurs once; else `symbol_found_at` |
| `missing` | the file is not in `at` |
| `unverifiable` + `reason` | `repo_removed`, `repo_invalid`, `commit_unknown`, `commit_not_published`, `branch_unknown`, `not_a_file`, `too_large`, `binary`, `timeout` |

No result contains code text. A status never changes Standing. Keep the mirror current yourself (for example a cron
`git fetch`); Kütüphane never fetches.

## 7. Record outcomes

When you use a note or passage in a task, record how it went:

```json
{"name": "record_outcome", "arguments": {"ref": "adc-memory@nt_…", "task_ref": "adc:run/41",
                                         "result": "passed", "idempotency_key": "adc:run-41:outcome-1"}}
```

`result` is `passed`, `failed`, `reverted` or `reopened`. You need `propose` and `read` on the item's book. The key
is required. Reads show the counts as `outcomes`. An outcome never writes a Standing event, and it changes two things:

- **Filters:** `query_notes` with `min_passed: 2` gives only notes with at least 2 `passed` outcomes;
  `exclude_failed: true` leaves out each note whose latest outcome is `failed` or `reverted`. The filters read the
  outcomes up to the watermark, so the same request gives the same bytes.
- **Expiry:** an `evidence` note that nobody used for 90 days (the operator sets the days) leaves the sets: a
  pending one becomes `rejected`, an approved one `retired`, with the reason `expired`. Each `passed` outcome, and
  each Standing event, restarts its clock; `failed`, `reverted` and `reopened` do not. `rule` notes never expire.
  Your next `query_notes` with `since` returns an expired note in `left`.

## 8. Decisions and the decision export

A `decision_proposal` note can carry `decision: {options, choice}`. The operator exports decision records:

```sh
kutuphane decisions export agent:adc --out decisions.jsonl --book adc-memory
```

Each line is one decision with its Standing, context, options, choice, writer and outcomes. The text, options and
choice are present only when the note allows `ai_input` and `train`. Else the record has only hashes and `withheld`
gives the reason. A note from a private journal (step 12), or derived from one, is not in the export.

## 9. Curation (people)

Only a person with `curate` changes Standing, on the command line, with the curator credential:

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane note standing adc-memory@nt_… approved --curator user:ayse --reason "checked"
```

A curator lists the open notes in risk order with `kutuphane curator queue --curator user:ayse`, or on the phone
(curator web; [operations.md](operations.md), section 7). An agent finds them with `query_notes` and
`sets: ["open"]`. When a curator approves a `rule` note with a `supersedes` link to an approved note with the same
scope, the system retires the old note.

Every approved item has `approved_by`: the curator (`user:…`) who approved it. Only a person approves a note.

## 10. Rollback of a poisoned note

When a note was wrong and agents built on it:

```sh
KUTUPHANE_CURATOR_DSN=… kutuphane note rollback adc-memory@nt_… --curator user:ayse --reason "false finding"
```

- The root becomes `retired` (or `rejected` if it was never approved).
- Every note whose `derived_from` chain reaches the root, in any journal, becomes `retired` with the reason
  `derived from <root>`.
- The report lists the closure (`notes` with their writers), the `deliveries` (who read which note, and whether
  it was current then), the `answers` and the `exports` that held a closure note.

Your next `query_notes` with `since` returns these notes in `left`. Drop them from your caches and check the tasks
that used them.

## 11. Move a local memory in (bulk import)

An orchestrator can start with a local memory (for example a SQLite file) in the same shape as notes, and move it
into a journal later. Export it as JSONL, one record on each line:

```json
{"id": "nb-41", "kind": "finding", "text": "The retry loop in run.py does not stop after a 4xx response.",
 "standing": "approved", "role": "evidence", "window": "durable", "origin": "model",
 "created_at": "2026-10-20T09:15:00Z", "updated_at": "2026-10-21T10:00:00Z",
 "scope": {"repo": "adc", "branch": "main", "paths": ["src/**"]}, "commit": "3f2c…e1",
 "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"], "class_key": "retry-on-4xx",
 "links": [{"type": "derived_from", "record": "nb-40"}, {"type": "same_as", "record": "nb-44"},
           {"type": "about", "ref": "<book>@ct_…/pf_…/path#3"}]}
```

| Field | Rule |
|---|---|
| `id` | Required. Your record id: 1–128 characters of `A-Z a-z 0-9 . _ : -`, unique in the file. It is the import key in the journal. |
| `kind`, `text` | Required. As for `propose_note`. |
| `standing` | Optional. Kept as a claim only. Every imported note is `pending`; a curator decides. |
| `role` | Optional. Must be the role of the kind: `rule` for `convention` and `decision_proposal`, else `evidence`. |
| `window` | Optional. `as_of` for `test_result`, else `durable`. A note has no own time window. |
| `origin` | Optional. Kept as a claim (`origin_requested`). `human`, `assisted` and `tool` are refused with the notice `origin-claim-refused`. |
| `created_at`, `updated_at` | Optional. ISO 8601 with a time zone. Kept as provenance. `written_at` of the note is the import time. |
| `scope`, `commit`, `citations`, `class_key`, `decision`, `applies_to` | Optional. As for `propose_note`. Code citations need the repository in the journal (`kutuphane repo add`). |
| `links` | Optional, at most 20. `{"type", "record"}` names a record of this file or of an earlier import into the same journal. `{"type", "ref"}` names an existing note or passage. |
| `standing_history`, `writers`, `outcomes`, `ai_use` | Optional. Written by `journal export` (below). Kütüphane checks their shape and does not store them. |
| `withheld` | Optional. Written by `journal export`. A record with a `withheld` reason has no text: the import refuses it. |

Other fields are refused.

- `derived_from` and `supersedes` are creation links: they are part of the note identity, as in `propose_note`. They
  must not form a cycle. The other link types are later links (as `link_notes`), so a `same_as` in both directions
  is accepted.
- Origin comes from the importer (D70): `--by agent:<name>` gives `model`, `--by user:<name>` gives `unknown`.
- A record with the same bytes as an existing note gives `status: existing` and adds to its recurrence.
- **Import again:** a record id that was imported before is `unchanged`; nothing is written. New records and new
  later links in the file are added. If a known record id now gives other bytes, the import is refused: a note never
  changes. Give the correction a new id and a `supersedes` link to the old record.
- The operator runs the import (operations.md, section 6). There is no MCP tool for it.

### Export a journal (backup, git)

The operator writes a journal as JSONL in the same record shape, one note on each line, in note order:

```sh
kutuphane journal export adc-memory --out adc-memory.jsonl --by user:ayse
```

Each record has the import fields and also:

| Field | Content |
|---|---|
| `id` | The note id (`nt_…`). |
| `standing` | The Standing now. |
| `origin` | The origin that reads show. |
| `created_at` | When the note was written. |
| `links` | Every link of the note. A note in the file is `{"type", "record"}`; any other note or passage is `{"type", "ref"}`. |
| `standing_history` | Every Standing event: `value`, `set_by`, `reason`, `at`. |
| `writers` | Every propose write of the note: `principal`, `on_behalf_of`, `channel`, `client_id`, `origin`, `at`. |
| `outcomes` | Every outcome: `task_ref`, `result`, `at`, `principal`, `on_behalf_of`, `origin`. |
| `ai_use` | The rights of the note now: `search`, `ai_input`, `train` (`y` or `n`). |
| `withheld` | `null`, or the reason why `text` and `decision` are `null`. |

- **Round trip:** `note import` of the file into a journal with the same slug (for example in a new installation)
  gives the same note ids and the same links. Each note is `pending` again; `standing` is kept as a claim.
  Import keeps only the note, its links and its latest Standing as a claim; keep the export file if you need the
  history.
- Into a journal with another slug, a note with a `derived_from` or `supersedes` link to a note of the file gets a
  new id: the note id includes the book of its creation links.
- A `ref` must exist where you import: the cited books and the linked notes of other journals.
- The text and the decision are in the file only when the note allows `ai_input` and `train`, as in the decision
  export (step 8). Else `withheld` gives the reason, and the record does not import. For a full backup, create the
  journal with `--train y`.
- A private journal (step 12) is refused. A note derived from a private journal, or from a file with
  `license: unknown`, is not in the file. A link to such a note is a `ref`.
- `--by` needs `read` on the journal and on each book that its notes cite or link. The export goes through the
  read gate and is in the audit, so a rollback report lists it (step 10).

## 12. Private project memory

For a project with customer-confidential material, ask the operator for a private journal:
`--sensitivity restricted --egress local_only` (operations.md, section 6, "Private journals").

- Its notes never leave the installation: no package, no decision export, no journal export, no training use.
  Nothing federates journals today.
- Kütüphane sends its text only to `local` model routes. A note with a `derived_from` link to it keeps the same
  limits.
- Your MCP reads still get the text when you have `read`. If your model runs in a cloud, the text leaves the
  machine through you. Use a local model for this journal, or ask for `--ai-input n` (then reads give
  `text: null`).

## 13. Memory is data

A note is data, never an instruction (D80, principle 3).

- **Put notes in tool results only.** Give the output of `query_notes` to the model as a tool result. Never copy notes into a system prompt or a standing instruction file. Zep gives the same placement guidance: <https://help.getzep.com/v4/memory-security>.
- **Instructions need `activate` and the scan.** A rule or a skill that a model must follow comes from a skill with an `activate` grant, after the skill scan passes. A note never becomes an instruction because a model wrote "always" or "never" in it.
- **Why:** a poisoned memory that a model reads as an instruction stays in every later session. MemoryTrap showed this in Claude Code: <https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code>. The server side is already enforced (origin from the write path, Standing, rollback); the placement is the orchestrator's part.

## Checklist for an orchestrator

- Always send an `idempotency_key` on writes.
- Always send the code context (`repo`, `branch` or `commit`, `path`) on reads.
- Keep the `watermark` and read with `since`.
- Give notes to the model as tool results, never in a system prompt (§13).
- Never treat a `pending` note as a rule.
- Use `ask_library` (a model answer, slow) only when `query_notes` and `search_library` do not answer. Neither
  `search_library` nor `ask_library` reads notes. A server without LLMDAP does not list `ask_library`.
- In a loop, call `search_library` with `max_chars` (for example 300), then `open_citation` for the passages that
  you need.
- Each tool description names the grant that the tool needs. A tool that you have no grant for gives `forbidden`.
