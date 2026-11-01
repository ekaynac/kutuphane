# Agent memory: a how-to for orchestrators

This page is for the builders of coding orchestrators (for example ADC and nöbetçi-mcp). It shows how an
orchestrator keeps its decisions, findings, lessons and conventions in Kütüphane, and how people accept them. The
terms are in [concepts.md](concepts.md#journals-and-notes). The tool parameters are in [mcp.md](mcp.md). The design
is `../24-r1-agent-memory-design.md`.

Kütüphane holds knowledge. Run state (goals, jobs, costs) stays in the orchestrator's own event log.

## 1. Set up (operator)

```sh
# a journal for the orchestrator; search and AI input must be stated
kutuphane journal create adc-memory --search y --ai-input y \
  --sensitivity normal --egress local_only --protection standard --by user:admin
kutuphane grant book:adc-memory propose agent:adc      # write notes
kutuphane grant book:adc-memory read agent:adc         # read notes
kutuphane grant book:<docs-book> read agent:adc        # read the project documents
KUTUPHANE_CURATOR_DSN=… kutuphane grant book:adc-memory curate user:ayse   # a person accepts notes (users only)
# optional: code citations into a bare mirror that you keep current
kutuphane repo add adc-memory adc /srv/repos/adc.git --ref 'refs/heads/*' --by user:admin
```

Add `--train y` to `journal create` only if decision records may leave as training data (step 8).

**Token.** The orchestrator gets an OAuth client-credentials token from the IdP. The IdP mapper sets
`kutuphane/principal_type: agent` and `sub: adc`, so the principal is `agent:adc`. For work on behalf of a person,
use an RFC 8693 token exchange and a delegation (`kutuphane delegate`). For development, use
`kutuphane dev-token adc --agent …` (see the `README.md` quick start).

## 2. Propose a note

```json
{"name": "propose_note", "arguments": {
  "book": "adc-memory", "kind": "finding",
  "text": "The retry loop in run.py does not stop after a 4xx response.",
  "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"],
  "scope": {"repo": "adc", "branch": "main", "paths": ["src/**"]},
  "commit": "3f2c…e1", "class_key": "retry-on-4xx",
  "idempotency_key": "adc:run-41:finding-1"}}
```

Select `kind` (evidence: `finding`, `lesson`, `dead_end`, `test_result`; rules: `convention`,
`decision_proposal`), up to 20 `citations` (passage handles or code citations of at most 200 lines), the `scope`
where the note applies, the `commit` that you observed, and a `class_key` for one class of problem. Creation
`links` (`derived_from`, `supersedes`) exist only here. `decision` (`{"options", "choice"}`) is only for a
`decision_proposal`. Always send an `idempotency_key`. All parameters: [mcp.md](mcp.md#59-propose_note).

The receipt:

```json
{"ref": "adc-memory@nt_…", "status": "created", "standing": "pending", "origin": "model", "origin_notice": null,
 "candidates": [], "recurrence": 1, "class_count": 0, "guard_due": false, "vector": "stored"}
```

- Every note starts `pending`. Origin is `model` on every agent path. When the person dictated the words, propose
  with `origin: "human"` (or `"assisted"`). The receipt then has `origin_notice: "origin-claim-refused"` and a
  `confirmation` URL. Give it to the person, or call `confirm_origin`; only the person can confirm, with a passkey,
  within 24 hours ([mcp.md](mcp.md#515-confirm_origin)).
- `status: existing`: the same bytes were already there, and `standing` is the real value. If it is `rejected`,
  stop proposing it.
- `candidates` lists similar notes. The server never merges them: decide, and link with `link_notes` (`same_as` or
  `contradicts`).
- `guard_due: true`: this class recurs in evidence and no approved `convention` covers it. Build the test or lint
  in your orchestrator, then propose the convention with that `class_key`.
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

`query_notes` is the main read: SQL only, deterministic, with a size limit. `search_library` and `ask_library`
search the passages of file books only; a journal in their `book` filter gives the error
`journal: use query_notes …`.

```json
{"name": "query_notes", "arguments": {
  "book": ["adc-memory"], "repo": "adc", "branch": "main", "path": "src/run.py",
  "kind": ["convention", "decision_proposal", "finding"], "collapse": true, "budget_tokens": 2000}}
```

- **Sets:** `current` (default), `open` (pending), `history` ([concepts.md](concepts.md#standing)).
- **Context:** always give `repo`, `branch` (or `commit`) and `path`. A scoped `rule` note without a context is
  left out (`excluded.needs_context`). A note with a `stale`, `missing` or `unverifiable` code citation is not
  current (`excluded.code`); `include_unverified: true` shows them.
- **Filters and size:** `kind`, `role`, `origin`, `class_key`, `written_after`, `written_before`, `commits`,
  `text`, `unfixed`, `min_passed`, `exclude_failed`; `budget_tokens` and `max_bytes`. Follow `next_cursor` until
  it is null. Details: [mcp.md](mcp.md#512-query_notes).
- **Incremental reads:** keep the `watermark` and send `since: <watermark>` next time. You get changed `items` and
  `left` tombstones for notes that left the set. Drop cached items of books that are not in `books`. If a branch
  head in `targets` moved, query again without `since`.
- The same request on the same data gives the same bytes, so the result can stay in a prompt cache.

HTTP: `GET /v1/notes?book=adc-memory&repo=adc&branch=main&kind=finding` (list parameters repeat).

**The documents in an agent loop.** Each tool result stays in the agent's context for all later turns. In a loop,
call `search_library` with `max_chars` (for example 300) to get snippets, and open only the passages that you need
with `open_citation` ([mcp.md](mcp.md#51-search_library); 65% smaller results in
[#121](https://github.com/ekaynac/kutuphane/issues/121)).

## 5. Follow links

```json
{"name": "neighbours", "arguments": {"ref": "adc-memory@nt_…", "depth": 2, "direction": "both",
                                     "types": ["derived_from", "contradicts", "fixed_by"]}}
```

`ref` can also be a passage handle: then `root` is null and the nodes are the notes linked to that passage
(`about`, `derived_from`) and the notes that cite it (edge type `cites`). You do not need an `about` link next to a
citation. `open_citation` opens one note (or passage) with its full text, Standing and `current` flag.

**After a re-index.** A note keeps the passage handle that it cites, and that passage still opens. Each passage
citation gets a `status` (`current`, `moved` with `moved_to`, or `stale`; [mcp.md](mcp.md#513-neighbours)). For a
book published before migration 040, run `kutuphane reindex-map <book>` once
([operations.md](operations.md#re-index-and-note-citations)).

## 6. Check code citations

```json
{"name": "verify_citations", "arguments": {"book": "adc-memory", "at": "main",
  "citations": ["adc@3f2c…e1:src/run.py:40-52#retry_job"]}}
```

The status is `verified`, `stale`, `missing` or `unverifiable` with a `reason`
([mcp.md](mcp.md#511-verify_citations)). No result contains code text. A status never changes Standing. Keep the
mirror current yourself (for example a cron `git fetch`); Kütüphane never fetches.

## 7. Record outcomes

When you use a note or passage in a task, record how it went:

```json
{"name": "record_outcome", "arguments": {"ref": "adc-memory@nt_…", "task_ref": "adc:run/41",
                                         "result": "passed", "idempotency_key": "adc:run-41:outcome-1"}}
```

`result` is `passed`, `failed`, `reverted` or `reopened`. You need `propose` and `read` on the item's book. An
outcome never changes Standing. `query_notes` filters on outcomes (`min_passed`, `exclude_failed`), and a `passed`
outcome restarts the 90-day expiry clock of an `evidence` note. An expired note comes back in `left`
([operations.md](operations.md#expiry-of-unused-evidence-r1)).

## 8. Decisions and the decision export

A `decision_proposal` note can carry `decision: {options, choice}`. The operator exports decision records:

```sh
kutuphane decisions export agent:adc --out decisions.jsonl --book adc-memory
```

Each line is one decision with its Standing, context, options, choice, writer and outcomes. The text, options and
choice are present only when the note allows `ai_input` and `train`; else `withheld` gives the reason. Private
journal notes (step 12) are not in the export ([operations.md](operations.md), section 8).

## 9. Curation and rollback (people)

Only a person with `curate` changes Standing, on the command line (`kutuphane note standing`,
`kutuphane note rollback`, with `KUTUPHANE_CURATOR_DSN`), or in curator web. A curator lists the open notes in
risk order with `kutuphane curator queue --curator user:ayse` ([operations.md](operations.md), section 7). An agent
finds them with `query_notes` and `sets: ["open"]`. Every approved item has `approved_by`: the curator (`user:…`).

## 10. Rollback of a poisoned note

A rollback retires the root note and every note whose `derived_from` chain reaches it, in any journal (reason
`derived from <root>`). The report lists the `deliveries`, `answers` and `exports` of these notes. Your next
`query_notes` with `since` returns them in `left`. Drop them from your caches and check the tasks that used them.

## 11. Move a local memory in (bulk import)

An orchestrator can start with a local memory (for example a SQLite file) and move it into a journal later. Export
it as JSONL, one record on each line, with the fields of `propose_note` and these:

| Field | Rule |
|---|---|
| `id` | Required. 1–128 characters of `A-Z a-z 0-9 . _ : -`, unique in the file. The import key in the journal. |
| `kind`, `text` | Required. As for `propose_note`. |
| `standing` | Kept as a claim only. Every imported note is `pending`; a curator decides. |
| `role` | Must be the role of the kind: `rule` for `convention` and `decision_proposal`, else `evidence`. |
| `window` | `as_of` for `test_result`, else `durable`. |
| `origin` | Kept as a claim (`origin_requested`). `human`, `assisted` and `tool` are refused with the notice `origin-claim-refused`. |
| `created_at`, `updated_at` | ISO 8601 with a time zone. Kept as provenance. `written_at` is the import time. |
| `scope`, `commit`, `citations`, `class_key`, `decision`, `applies_to` | As for `propose_note`. Code citations need the repository in the journal (`kutuphane repo add`). |
| `links` | At most 20. `{"type", "record"}` names a record of this file or of an earlier import into the same journal. `{"type", "ref"}` names an existing note or passage. |
| `standing_history`, `writers`, `outcomes` | Written by `journal export`. Checked for shape, not stored. |
| `ai_use` | Written by `journal export`: `{"search", "ai_input", "train"}`, each `y` or `n`. An `n` closes that right of a new note; a `y` never opens a right that the journal or a source closes. An existing note keeps its rights. |
| `withheld` | Written by `journal export`. A record with a `withheld` reason has no text: the import refuses it. |

All fields except `id`, `kind` and `text` are optional. Other fields are refused.

- `derived_from` and `supersedes` are creation links (part of the note identity) and must not form a cycle. Other
  link types are later links, so a `same_as` in both directions is accepted.
- Origin comes from the importer (D70): `--by agent:<name>` gives `model`, `--by user:<name>` gives `unknown`.
- A record with the same bytes as an existing note gives `status: existing` and adds to its recurrence.
- **Import again:** a record id that was imported before is `unchanged`. New records and new later links are added.
  If a known record id now gives other bytes, the import is refused: a note never changes. Give the correction a
  new id and a `supersedes` link to the old record.
- The operator runs the import (`kutuphane note import`, operations.md, section 6). There is no MCP tool for it.

### Export a journal (backup, git)

The operator writes a journal as JSONL in the same record shape, one note on each line, in note order:

```sh
kutuphane journal export adc-memory --out adc-memory.jsonl --by user:ayse
```

| Field | Content |
|---|---|
| `id` | The note id (`nt_…`). |
| `standing`, `origin` | The Standing now; the origin that reads show. |
| `created_at` | When the note was written. |
| `links` | Every link. A note in the file is `{"type", "record"}`; any other note or passage is `{"type", "ref"}`. |
| `standing_history` | Every Standing event: `value`, `set_by`, `reason`, `at`. |
| `writers` | Every propose write: `principal`, `on_behalf_of`, `channel`, `client_id`, `origin`, `at`. |
| `outcomes` | Every outcome: `task_ref`, `result`, `at`, `principal`, `on_behalf_of`, `origin`. |
| `ai_use` | The rights of the note now: `search`, `ai_input`, `train` (`y` or `n`). |
| `withheld` | `null`, or the reason why `text` and `decision` are `null`: the note depends on a skill that a scan blocks. The import refuses that record. |

The rules for `--by`, private journals and the round trip are in
[operations.md](operations.md#export-a-journal). Into a journal with another slug, a note with a creation link to
a note of the file gets a new id. A `ref` must exist where you import.

## 12. Private project memory

For customer-confidential material, ask the operator for a private journal
(`--sensitivity restricted --egress local_only`; [operations.md](operations.md#private-journals-customer-confidential-project-memory)).
Its notes never leave the installation, and Kütüphane sends their text only to `local` model routes. Your MCP reads
still get the text when you have `read`: if your model runs in a cloud, the text leaves the machine through you.
Use a local model for this journal, or ask for `--ai-input n` (then reads give `text: null`).

## 13. Memory is data

A note is data, never an instruction (D80, principle 3).

- Give the output of `query_notes` to the model as a tool result. Never copy notes into a system prompt or a
  standing instruction file (Zep gives the same guidance: <https://help.getzep.com/v4/memory-security>).
- A rule that a model must follow comes from a skill with an `activate` grant, after the skill scan passes. A note
  never becomes an instruction because a model wrote "always" or "never" in it.
- A poisoned memory that a model reads as an instruction stays in every later session
  (<https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code>).

## Checklist for an orchestrator

- Send an `idempotency_key` on writes and the code context on reads; read with `since`. A `pending` note is no rule.
- Use `ask_library` (a model answer, slow) only when `query_notes` and `search_library` do not answer. A server
  without LLMDAP does not list `ask_library`.
- A tool that you have no grant for gives `forbidden`.
