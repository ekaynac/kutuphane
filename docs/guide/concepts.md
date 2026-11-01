# Concepts

This page defines the words that the rest of the guide uses. The design sources are `../09-ontology-v2.md`,
`../24-r1-agent-memory-design.md` and `../11-standard-draft.md`.

## Books and versions

A **book** is the unit of access. You give rights per book, and every search and read stays inside the books that
the caller may read now. A book slug is lowercase: `[a-z0-9][a-z0-9-]{0,62}`.

| Kind | Content | How content arrives |
|---|---|---|
| file book | files from a folder or one file | `kutuphane ingest`, or a signed package (`receive` + `approve-import`) |
| journal | notes that agents and people write | `propose_note` (MCP) or `POST /v1/notes` (HTTP) |

Each publication of a file book gets three content-addressed ids (SHA-256 over canonical JSON; `src/kutuphane/ids.py`):

| Id | Covers | Changes when |
|---|---|---|
| `ct_…` content version | the file paths and their bytes | a byte or a path changes |
| `pf_…` profile | how the content is cut and searched (reader, chunker, FTS configuration, settings) | the cutter or the search settings change |
| `pl_…` policy | `sensitivity`, `egress`, `protection` | the policy changes |

Versions never change. The same bytes give the same `ct_` id (`new_content: false`). Old versions stay, so an old
citation still opens its exact text.

**Profiles.** `chunked` (the default) cuts text into passages of about 1,200 characters at headings and blank
lines; a markdown heading or `---` line joins the next passage. HTML comment characters become spaces (line numbers
stay); a comment-only block is not a passage. A rule file's leading source comment
(`<!-- source: … | url: … -->`, first line, at most 500 characters) and comments in code fences stay. A `#` line in
a code fence, or `#41`, is not a heading. `whole` serves each file as one piece (at most 500,000 characters). A book
that an older reader published keeps its old index until you ingest it again.

**Passages and citation handles.** A passage is one cut piece of one file version, with the handle
`<book>@ct_<64 hex>/pf_<64 hex>/<path>#<ordinal>`. `open_citation` (MCP) and `GET /v1/citation?handle=…` open it.
Text passages carry the `line` where they start.

## Book policy

Every book has three mandatory axes (`src/kutuphane/policy.py`):

| Axis | Values | Effect |
|---|---|---|
| `sensitivity` | `normal`, `restricted` | `restricted` cannot be `cloud_ok`, is never in a package, cannot allow `train` (journals), and keeps its derived notes out of the decision export |
| `egress` | `local_only`, `cloud_ok` | content of a `local_only` book never goes to a `cloud` model route |
| `protection` | `standard` | the only value today |

## Rights of content (`ai_use`, licence, personal data)

A folder can carry a `kstd.yaml` manifest that states per file `ai_use` (`search`, `ai_input`, `train`), `license`
and `personal_data` ([kstd.md](kstd.md#what-kütüphane-does-with-each-field)). An absent `ai_use` term is treated as
`n`. A file with no manifest follows its book policy only, and its origin is `unknown`.

A **model reader** is an MCP caller or an `agent:` principal. The `ai_input` gate applies to every model call
(embedding, rerank, answer) and to the text that a model reader gets (`text: null` and `withheld`).

## Journals and notes

A **journal** is a book whose items are **notes**. An administrator creates it with `kutuphane journal create` and
states `--search` and `--ai-input` (both required), and `--train` (default `n`).

A **note** is one entry that an agent or a person writes, at most 8,000 characters. A secret scan reads it before
it is stored. Its id is `nt_` + SHA-256 of its canonical body (kind, text, class key, scope, commit, citations,
creation links, decision). So a note never changes (a correction is a new note with a `supersedes` link), the same
bytes again are the same note (`status: existing`, `recurrence` + 1), and the same text in two journals is two
notes. A note reference is `<book>@nt_<64 hex>`.

### Kinds

The kind sets how a note acts and how long it is current (D78).

| Kind | Acts as | Current |
|---|---|---|
| `decision_proposal`, `convention` | a rule | durable |
| `finding`, `lesson`, `dead_end` | evidence | durable |
| `test_result` | evidence | as of its write time: always history |

A rule note with a scope needs a matching request context to be current. An evidence note is shown with its scope.

### Links

Creation links are part of the note id; `link_notes` adds the later links.

| Type | Effect |
|---|---|
| `derived_from` (creation only) | rights follow derivation; rollback follows it |
| `supersedes` (creation only) | approving a `rule` successor retires the predecessor with the same scope |
| `same_as` (same book) | duplicate clusters, `collapse`, recurrence |
| `contradicts` | never collapsed together |
| `about` | `neighbours` from a passage; a citation of the passage is an edge there too (`cites`) |
| `fixed_by` | the `unfixed` filter |
| `violates`, `decided_by` | `neighbours`; `violates` counts on the rule |

**Rights follow derivation.** A note's `search`, `ai_input` and `train` are the AND of its journal and every passage
or note that it cites or derives from. Every read also ANDs the current values of every journal in the note's
closure, so `kutuphane journal restrict` on one journal also restricts the notes derived from it.

## Standing

Standing is the acceptance state of a note. Only a curator changes it, on the command line
(`kutuphane note standing`, `kutuphane note rollback`). No MCP tool and no HTTP route changes Standing.

| Value | Meaning |
|---|---|
| `pending` | new; not accepted. Every note starts here |
| `approved` | a curator accepted it |
| `rejected` | never accepted (D68). A re-proposal gets `standing: rejected` in its receipt |
| `retired` | accepted before; withdrawn, replaced or rolled back |

A note that was ever approved cannot become `rejected` (transitions: [operations.md](operations.md#7-curation)).

**Current.** One predicate decides "current" for every read (`query_notes`, `neighbours`, `open_citation`). A note
is current when:

1. its Standing is `approved`;
2. it is not a `test_result`;
3. its scope matches the request context (`repo`, `branch`, `path`), and a scoped `rule` note has that context; the
   same holds for its kstd Scope bound `applies_to` (`platform`, `version`; #164), with the rule of files;
4. each code citation into a repository with a target in the request is `verified`.

The sets are `current` (the notes above), `open` (`pending` notes) and `history` (`rejected`, `retired` and
`test_result` notes).

Outcomes never change Standing. An `evidence` note that nobody used for 90 days expires; `rule` notes never expire
([operations.md](operations.md#expiry-of-unused-evidence-r1)).

**File books** have no Standing: kstd gives origin, validity and applicability.

## Origin

Origin says who or what made the text: `human`, `assisted`, `model`, `tool` or `unknown` (handled as `model`). For
file books it comes from `kstd.yaml` (no manifest: `unknown`). For notes (D70) the server computes it from the
authenticated write path; the writer's claim does not count.

| Write path | Stored origin |
|---|---|
| an `agent:` principal, an agent that acts for a person, or any MCP call | `model` |
| a `user:` principal, no `act`, over HTTP | `unknown` |

A writer can ask for a lower value (`origin: model`). A request for `human`, `assisted` or `tool` stores the
computed value and returns `origin_notice: origin-claim-refused`. Only the person's passkey confirmation of the
exact note gives `human` (D70, D72; [agent-memory.md](agent-memory.md#2-propose-a-note)).

## Principals, modes and grants

A **principal** is `user:<name>`, `agent:<name>` or `role:<name>`. The IdP token gives the principal. Rights are
decided per call, so a revoke applies to the next call.

| Mode | Gives |
|---|---|
| `read` | search, open and read the book; read notes |
| `activate` | an agent may receive agent instructions (see below) |
| `propose` | write notes, links and outcomes into a journal; on a content book: submit a signed package for a person to approve (`POST /v1/packages`, `submit_package`) |
| `curate` | the user can be named as curator by the CLI. Users only, granted directly, never delegated. `kutuphane grant … curate …` needs `KUTUPHANE_CURATOR_DSN` |
| `discover`, `use` | reserved: you can grant them, but no code path checks them today |
| `member` | on `role:<name>`: puts a subject in the role |

Modes are independent. Only `read` gives text; `propose` without `read` gives a minimal receipt. Grant commands:
[operations.md](operations.md#grants).

## Delegation

An agent can act for a person: the token has `sub` = the person and `act.sub` = the agent. The agent needs a live
delegation from the person for that book and mode (`kutuphane delegate`, time-boxed, one level) and the person's own
current right. When either one ends, the next call is refused. `curate` is never delegated.

## Agent instructions and `activate`

Some files are instructions for agents (rule K3), for example `AGENTS.md`, `CLAUDE.md`, skill folders and
`.claude/` ([full list](operations.md#agent-instructions-k3)). An agent needs `activate` on the book to get them in
search and `read_document`; each delivery is logged. A note is never an agent instruction. A skill that the skill
scan blocks stays blocked, also with `activate`, until `kutuphane skill clear`
([security.md](security.md#skill-scan-skillspector)).

## Outcomes

`record_outcome` records `passed`, `failed`, `reverted` or `reopened` for a task, on one exact note or passage
version (for a runbook, its passage handle; `record_runbook_feedback` was removed, D78).

## Answers and jobs

`ask_library` writes a short answer with `[n]` citations through the answer model, or `not_in_library`. The answer
and its evidence are stored. `reopen_answer` shows them again with no model call, under current rights. A long
answer can run as a background **job** (`background: true`). See `mcp.md`.

### Records that a passage repeats

A report often repeats text from data records. Kütüphane links the copy to the record, so an answer can cite it.

- **A record** is one line of a JSONL file. Each string value of 40 characters or more (white space folded) is
  stored as a sha256 at publication.
- **A passage repeats a record** when a JSON string value or a line (also without a markdown list, quote or heading
  mark) has the same folded text. A value inside a longer line, similar text and records themselves never count.
  The record is the source, whatever the publication time.
- **Search** gives each passage `quoted_records`: handles of the repeated records that you may read now and that
  pass the filters. The copy keeps its rank. Each named book gets an `access_event` with the action `quote`.
- **Ask** puts each record into the evidence before its first copy (at most 4, when rights allow AI input), marks
  the copy `repeats [n]`, and tells the model to cite record `[n]`. Citations and evidence carry `quoted_records`.

## Audit

Every gate decision, allowed or refused, is an `access_event` row with the policy, grants and delegation behind it.
Every model call is a `model_call` row. `kutuphane explain <correlation-id>` joins them with the LLMDAP audit export.
See `security.md`.
