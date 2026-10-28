# Concepts

This page explains the words that the rest of the guide uses. The design sources are `../09-ontology-v2.md` (the
ontology), `../24-r1-agent-memory-design.md` (agent memory) and `../11-standard-draft.md` (kstd).

## Books and versions

A **book** is the unit of access. You give rights per book, and every search and every read stays inside the books
that the caller may read now. A book slug is lowercase: `[a-z0-9][a-z0-9-]{0,62}`.

There are two kinds of book:

| Kind | Content | How content arrives |
|---|---|---|
| file book | files from a folder or one file | `kutuphane ingest`, or a signed package (`receive` + `approve-import`) |
| journal | notes that agents and people write | `propose_note` (MCP) or `POST /v1/notes` (HTTP) |

Each publication of a file book gets three content-addressed ids (SHA-256 over canonical JSON; `src/kutuphane/ids.py`):

| Id | Covers | Changes when |
|---|---|---|
| `ct_…` content version | the file paths and their bytes | a byte or a path changes |
| `pf_…` profile | how the content is cut and searched (reader, chunker, FTS configuration, settings) | the cutter or the search settings change |
| `pl_…` policy | the book policy: `sensitivity`, `egress`, `protection` | the policy changes |

Versions never change. A new ingest of the same bytes gives the same `ct_` id (`new_content: false`). The book points
to its current content, profile and policy. Old versions stay, so an old citation still opens the exact text that it
named.

**Profiles.** `chunked` (the default) cuts text into passages of about 1,200 characters at headings and blank
lines. In markdown, a heading or a `---` line alone is not a passage: it joins the passage after it, so a passage
starts with its heading. HTML comments are hidden in a rendered file, so no passage holds one: the server replaces
each comment character with a space (the offsets and line numbers stay), and a block of comments only is not a
passage. One exception: a rule file's leading source comment (`<!-- source: … | url: … -->`, the first line of the
file, at most 500 characters) is a citation of the vendor document, not an instruction. It stays in the passage of
the rule. A comment in a code fence is code and stays. A `#` line in a code fence, or `#41` without a space,
is not a heading. `whole` serves each file as one piece (at most 500,000 characters). A book that an older reader
published keeps its old index until you ingest it again.

**Passages and citation handles.** A passage is one cut piece of one file version. Its handle names the exact
version:

```
<book>@ct_<64 hex>/pf_<64 hex>/<path>#<ordinal>
```

`open_citation` (MCP) and `GET /v1/citation?handle=…` open a handle. Text passages carry the `line` where they start.

## Book policy

Every book has a policy with three mandatory axes (`src/kutuphane/policy.py`):

| Axis | Values | Effect |
|---|---|---|
| `sensitivity` | `normal`, `restricted` | `restricted` cannot be `cloud_ok`. A `restricted` book is never in a package. A note with a `restricted` book in its sources is never in the decision export. A `restricted` journal cannot allow `train`. |
| `egress` | `local_only`, `cloud_ok` | content of a `local_only` book never goes to a `cloud` model route |
| `protection` | `standard` | the only value today |

## Rights of content (`ai_use`, licence, personal data)

A folder can carry a `kstd.yaml` manifest (see `kstd.md`). It states, per file:

| Right | Values | Effect |
|---|---|---|
| `ai_use.search` | `y`, `n`, absent | not `y`: the file is not indexed |
| `ai_use.ai_input` | `y`, `n`, absent | not `y`: the text never reaches a model (no embedding, no rerank, no answer); model readers get `text: null` and `withheld` |
| `ai_use.train` | `y`, `n`, absent | for journals: controls the text in decision exports |
| `license` | SPDX id or `unknown` | shown with results; `unknown` gives no permission |
| `personal_data` | `yes`, `no`, `synthetic`, `unknown` | not `no` or `synthetic`: `export` needs `--legal-basis` |

In a manifest, an absent `ai_use` term is shown as "not stated", and every decision treats it as `n`. A file with no
manifest follows its book policy only: it is searched and it can go to a model (the book's egress still applies).
Its origin is `unknown`.

A **model reader** is an MCP caller or an `agent:` principal. The `ai_input` gate applies to every model call
(embedding, rerank, answer) and to the text that a model reader gets. People on HTTP see the text of passages that
they may read.

## Journals and notes

A **journal** is a book whose items are **notes**. An administrator creates it with `kutuphane journal create`
and states two rights: `--search` and `--ai-input` (both required), and `--train` (default `n`).

A **note** is one entry that an agent or a person writes. Its id is `nt_` + SHA-256 of its canonical body (kind,
text, class key, scope, commit, citations, creation links, decision). So:

- a note never changes. A correction is a new note with a `supersedes` link;
- the same bytes again are the same note: `status: existing` and `recurrence` + 1;
- a note reference is `<book>@nt_<64 hex>`. The same text in two journals is two notes.

A note is at most 8,000 characters. A secret scan reads every note before it is stored.

### Kinds, roles and time

| Kind | Role | Time |
|---|---|---|
| `decision_proposal` | `rule` | durable |
| `convention` | `rule` | durable |
| `finding` | `evidence` | durable |
| `lesson` | `evidence` | durable |
| `dead_end` | `evidence` | durable |
| `test_result` | `evidence` | as of its write time: always history |

A `rule` note with a scope needs a matching request context to be current. An `evidence` note is shown with its
scope.

### Links

| Type | When | Effect |
|---|---|---|
| `derived_from` | creation only | rights follow derivation; rollback follows it |
| `supersedes` | creation only | approving a `rule` successor retires the predecessor with the same scope |
| `same_as` | creation or later; same book | duplicate clusters, `collapse`, recurrence |
| `contradicts` | creation or later | never collapsed together |
| `about` | creation or later | `neighbours` from a passage; a citation of the passage is an edge there too (`cites`) |
| `fixed_by` | creation or later | the `unfixed` filter |
| `violates` | creation or later | `neighbours`, counts on the rule |
| `decided_by` | creation or later | `neighbours` |

Creation links are part of the note id. `link_notes` adds the later links.

**Rights follow derivation.** A note's `search`, `ai_input` and `train` are the AND of its journal and every
passage or note that it cites or derives from. Every read also ANDs the current values of every journal in the
note's closure. So `kutuphane journal restrict` on one journal also restricts the notes derived from it in other
journals.

## Standing

Standing is the acceptance state of a note. Only a curator changes it, and only on the command line
(`kutuphane note standing`, `kutuphane note rollback`). No MCP tool and no HTTP route changes Standing.

| Value | Meaning |
|---|---|
| `pending` | new; not accepted. Every note starts here |
| `approved` | a curator accepted it |
| `rejected` | never accepted (D68). A re-proposal gets `standing: rejected` in its receipt |
| `retired` | accepted before; withdrawn, replaced or rolled back |

Transitions: `pending` → `approved` or `rejected`; `approved` → `retired`; `rejected` or `retired` → `pending`
(reopen). A note that was ever approved cannot become `rejected`: use `retired`.

**Current.** One predicate decides "current" for every read (`query_notes`, `neighbours`, `open_citation`). A
note is current when all of these are true:

1. its Standing is `approved`;
2. it is not a `test_result`;
3. its scope matches the request context (`repo`, `branch`, `path`), and a scoped `rule` note has that context;
4. each code citation into a repository with a target in the request is `verified`.

| Set | Contains |
|---|---|
| `current` | the notes above |
| `open` | `pending` notes |
| `history` | `rejected`, `retired` and `test_result` notes |

A pending note is never current. Outcomes never change Standing.

**Facets of file books.** The ontology (`../09-ontology-v2.md`) also defines blocks, Role, Time and Standing for
the content of file books. That part is approved but not built. Today Standing exists for notes only. For file
books, kstd gives origin, validity (`valid_from`, `valid_to`) and applicability.

## Origin

Origin says who or what made the text: `human`, `assisted`, `model`, `tool` or `unknown` (handled as `model`).

- **File books:** origin comes from `kstd.yaml`. A book without a manifest is `unknown`.
- **Notes (D70):** the server computes origin from the authenticated write path. The writer's claim does not
  count.

| Write path | Stored origin |
|---|---|
| an `agent:` principal, an agent that acts for a person, or any MCP call | `model` |
| a `user:` principal, no `act`, over HTTP | `unknown` |

A writer can ask for a lower value (`origin: model`). A request for `human`, `assisted` or `tool` stores the
computed value and returns `origin_notice: origin-claim-refused`. No path stores `human` today. A later passkey
confirmation by the person on the exact note digest will give `human` (D70, D72).

## Principals, modes and grants

A **principal** is `user:<name>`, `agent:<name>` or `role:<name>`. The token from the identity provider (IdP) gives
the principal. Rights are decided per call, so a revoke applies to the next call.

| Mode | Gives |
|---|---|
| `read` | search, open and read the book; read notes |
| `activate` | an agent may receive agent instructions (see below) |
| `propose` | write notes, links and outcomes into a journal |
| `curate` | the user can be named as curator by the CLI. Users only, granted directly, never delegated |
| `discover`, `use` | reserved: you can grant them, but no code path checks them today |
| `member` | on `role:<name>`: puts a subject in the role |

```sh
kutuphane grant book:<slug> read agent:<name>
kutuphane grant role:<name> member user:<name>
kutuphane grant book:<slug> read 'role:<name>#member'
```

Modes are independent: one mode never implies another. Only `read` gives text; `propose` without `read` gives a
minimal receipt.

## Delegation

An agent can act for a person. The token then has `sub` = the person and `act.sub` = the agent. The agent needs:

1. a live delegation from the person for that book and mode (`kutuphane delegate`, time-boxed, one level);
2. the person's own current right.

When either one ends, the next call is refused. A delegation cannot give more than the person has. `curate` is
never delegated.

## Agent instructions and `activate`

Some files are instructions for agents (rule K3): files in `.claude/`, `.cursor/rules/`, `.github/` agent folders,
`.agents/`, `.codex/`; files in a skill folder (next to `SKILL.md`); `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`,
`SKILL.md`, `copilot-instructions.md`; Cursor `.mdc` rules; Copilot `.instructions.md`, `.prompt.md`, `.agent.md`,
`.chatmode.md`; and frontmatter types such as `skill`.

A person reads them with `read`. An agent also needs `activate` on the book. Without it, search does not return
those passages to the agent, and `read_document` refuses them. Each delivery is logged. A note is never an agent
instruction.

**Skill scan (D71).** When SkillSpector is installed, each skill folder is scanned at ingest. The scan result is a
proposal to the curator (origin `tool`), never an approval. A `DO_NOT_INSTALL` result, a scan that did not cover the
whole skill, or a failed scan blocks the skill for agents, also with `activate`. Only a curator lifts the block
(`kutuphane skill clear`). `SAFE` gives no right. See [security.md](security.md#skill-scan-skillspector).

## Outcomes and feedback

- **Outcomes** (`record_outcome`): `passed`, `failed`, `reverted` or `reopened` for a task, on one exact note or
  passage version. Reads show the counts. They never change Standing.
- **Runbook feedback** (`record_runbook_feedback`): `worked`, `failed` or `changed` for one exact file version.

## Answers and jobs

`ask_library` writes a short answer with `[n]` citations through the answer model, or `not_in_library`. The answer
and its evidence are stored. `reopen_answer` shows them again with no model call, under current rights. A long
answer can run as a background **job** (`background: true`). See `mcp.md`.

### Records that a passage repeats

A report often repeats text from data records: for example a weekly brief that copies the summary of a news record.
Kütüphane links the copy to the record, so that the answer can cite the record and not only the copy.

- **A record** is one passage of a JSONL file (one line). Each string value of a record with 40 characters or more
  (after white space is folded to one space) is stored as a sha256 at publication.
- **A passage repeats a record** when one of its JSON string values, one of its lines, or one of its lines without
  a markdown list, quote or heading mark has the same folded text. A value inside a longer line is not found. A
  record never counts as a copy, and similar text (vectors) never counts.
- **The record is the source.** Publication time does not decide, because a book that a program publishes again
  every few hours would become newer than its own copies.
- **Search** gives each passage `quoted_records`: the handles of the records that it repeats, from books that you
  may read now and that pass the search filters. The copy stays in the results with its rank, because it usually
  holds other text too.
- **Ask** puts each such record into the evidence right before its first copy (at most 4 records; only when their
  rights allow AI input). The copy is marked `repeats [n]` for the model, and the model is told to cite record
  `[n]` for that text. Each citation and evidence entry has `quoted_records`: the repeated records in the evidence.

## Audit

Every gate decision, allowed or refused, is an `access_event` row with the policy, the grants and the delegation
behind it. Every model call is a `model_call` row. `kutuphane explain <correlation-id>` joins them with the LLMDAP
audit export. See `security.md`.
