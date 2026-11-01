# kstd: the knowledge contract

kstd (working name) is the written contract for the rules that Kütüphane enforces: who stands behind a file, what
may be done with it and with what is derived from it, and how a withdrawal reaches its users. The specification is
`../11-standard-draft.md` (draft 0.3.1). The conformance cases and a small reference evaluator are in `kstd/`
(`kstd/README.md`).

Kütüphane implements level **L0 (Described)**: one manifest file, `kstd.yaml`, at the root of a folder.

## The manifest

```yaml
standard: kstd/0.3                       # kstd/0.2 is still accepted
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this folder
issued: 2026-10-20                       # optional
rights:                                  # defaults for every item
  license: CC-BY-4.0                     # SPDX id, or unknown
  holder: "ACME GmbH"
  ai_use: {search: y, ai_input: y, train: n}
  personal_data: no                      # yes | no | synthetic | unknown (= yes)
notices: ["Attribution: ACME GmbH, 2026"]
items:
  - path: procedures/pressure-test.md
    digest: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    origin: human                        # human | assisted | model | tool | unknown (= model)
    entered_by: "agent:kobra-7"          # optional: who entered the words
    confirmed_by: "user:ayse"            # optional: who confirmed them as their own
    valid_from: 2026-01-01
    applies_to: {platform: [vcenter], version: ">=7.0,<8"}   # or one string (= one platform)
  - path: notes/weekly-summary.md
    digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    origin: assisted                     # a named person reviewed it
    reviewed_by: "Ayşe Yılmaz <ayse@acme.example>"
    rights: {personal_data: unknown}     # overrides the default
  - path: reference/api/index.html
    digest: sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae
    origin: tool                         # no learned model at any step
    software_agent: {name: typedoc, version: "0.26.11"}
```

Each item names one file by path and SHA-256 digest, and can override the default rights.

## Workflow

```sh
kutuphane kstd-init <folder> --issuer "ACME <kb@acme.example>"   # every file and its digest
# state ai_use, license and personal_data
kutuphane kstd-check <folder>                                    # errors (exit 1) and warnings
kutuphane ingest <folder> --book <slug> --sensitivity normal --egress local_only --protection standard
```

`kstd-init` and `kstd-check` need no database. They run the secret and personal-data scans of `ingest`, with the
same `--accept-finding` and `--deny-names` values and the same findings. A finding does not make `kstd-check` fail.

`kstd-init` writes safe values: `license: unknown`, `personal_data: unknown`, `origin: unknown`, and **no `ai_use`
term** (`# ai_use: {search: y|n, ai_input: y|n, train: y|n}` is a comment). Until you state the terms, no file is
indexed or sent to a model, and `kstd-check` warns "no default ai_use". `y|n` without the `#` is an error.

### Origin proposals from a source repository

A copy of a folder has no git history, so give its source repository:

```sh
kutuphane kstd-init <copy> --issuer "ACME <kb@acme.example>" --source-repo <repo> [--commit <rev>]
```

- **Match.** A file matches a file in the tree of the commit (default `HEAD`; use `--commit` for an older copy) by
  path, by end of path, or by content. Same path with other content stays `unknown`.
- **History.** The commits that changed the matched path since it was added; renames followed, merges not counted.
- **Proposal.** `model` when every commit has a `Co-Authored-By` trailer with a known model agent (for example
  `Claude … <noreply@anthropic.com>`, GitHub Copilot, Cursor Agent, aider, Codex, Gemini); else `unknown`. A person's
  name alone (`Claude Monet`) is not a model.
- **Never proposed:** `human`, `assisted` (needs a reviewer) or `tool` (needs a `software_agent`). `model` and
  `unknown` are handled the same way, so a wrong proposal gives no permission.

The proposal is a normal value; the evidence is in comments:

```yaml
# proposals from git: /src/handbook at 1223ca71ff9c… (a proposal is not authority: check each origin before you publish)
items:
  - path: "rules/backup.md"
    digest: sha256:…
    origin: model                     # proposed from git: 2 of 2 commits name a model; rules/backup.md at 1223ca71ff9c (same path and content)
    #   e0d712a9591d Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
    #   cc290e35fe49 …
```

`kstd-init` prints the counts (`origin proposals from git: model 30, unknown 3`). It only reads the local
repository: no fetch (also not for a partial clone), no hooks, no signature check.

### Personal-data findings

`kstd-init` lists each personal-data or fleet-data finding on stderr (path, line and rule, never the text), and
writes `personal_data: unknown` with the findings as a comment for that item:

```yaml
    rights:
      personal_data: unknown            # proposed: personal-data findings: email (line 3); private-ipv4 (line 4); check them
```

So a folder default `personal_data: no` does not cover that file; a finding never proposes `no`. Rules and the
`--deny-names` file: [operations.md](operations.md#personal-data-and-fleet-data-findings).

## Validation

`kstd-check` and `ingest` keep three results apart:

| Result | Cause | Effect |
|---|---|---|
| error | a YAML alias, merge key or duplicate key; a wrong type; no `issuer`; an unknown `standard`; a digest that does not match; an invalid SPDX expression; an `ai_use` value that is not `y` or `n` ("ai_use terms take y or n"); an invalid `personal_data` or `origin` value; an invalid date or path | `ingest` and `approve-import` refuse the book |
| warning: the claim is not trusted | an unknown field that does not start with `x-` (also an unknown `ai_use` term); `origin: assisted` without `reviewed_by`; `origin: tool` without `software_agent: {name, version}` as strings; `reviewed_by` without `assisted`; `software_agent` without `tool`; `entered_by` or `confirmed_by` without `human`, or not a non-empty string | publication continues. The field is ignored, or the origin counts as `unknown` (handled as `model`). The item `notices` in results show the same text, for example `kstd.yaml politika/x.md: origin 'assisted' not trusted: …; handled as unknown` |
| authorized | the fields in the next table | each operation reads only the fields that it needs |

## What Kütüphane does with each field

| Field | Effect |
|---|---|
| `ai_use.search` not `y` | the file is not indexed |
| `ai_use.ai_input` not `y` | no embedding, no rerank, not in an answer; model readers get `text: null` and `withheld`; `read_document` refuses it |
| `ai_use.train` | derived notes inherit it; a decision export needs it for text |
| absent `ai_use` term | "not stated"; treated as `n` |
| `license: unknown` (also when no license is stated) | a note that cites the file or derives from it (also through other notes) is written, with `licence_notice` in its receipt. `export` refuses the book and names the files; the decision export leaves out every derived note (`licence_unknown` in the summary). `kstd-check` warns "no default license: a file without its own license may be derived from in this installation (with a notice), but it and every note derived from it are never exported or forwarded". For internal content, state an internal license, for example `LicenseRef-InfraMedic-Internal` (#143). |
| `personal_data` not `no` or `synthetic` | `export` needs `--legal-basis` with DPV codes (for example `eu-gdpr:A6-1-b`), stored in the signed package |
| `origin` | shown with every result; the search filter `--origin`; the signed package lists `model`/`unknown` files as AI-generated, `assisted` as reviewed (`reviewed_by`), `tool` as tool-made (`software_agent`), and `human` files with `entered_by` or `confirmed_by` in `human_confirmed`. An `assisted` or `tool` claim without its evidence counts as `unknown`; `entered_by` and `confirmed_by` are optional for `human`. |
| `license`, `valid_from`, `valid_to`, `applies_to`, `notices` | shown with search results, citations and answers (`item`) |
| `valid_from`, `valid_to` | the `--current-only` filter; `valid_from` dates a file for "recent" questions. A date alone means 00:00 UTC, so `2026-10-27T23:59:00Z` is not current at noon that day. |
| `applies_to` | the request context (`--platform`, `--version`; `context` on HTTP and MCP): a file whose `applies_to` the context contradicts is left out before ranking; `item.scope` is `unbounded`, `match` or `needs_context` ([operations.md](operations.md#scope-filters-g14)). Keys: `platform` (a list of strings) and `version` (comma-separated clauses with `>=`, `>`, `<=`, `<`, `==`, for example `>=2.1,<3`; a version is numbers with dots). One string means `platform: [<string>]`. A malformed `platform` or `version` refuses the book; an unknown key is ignored with a notice. `item.applies_to` shows the mapping form. |

`kstd.yaml` itself is stored and checked, never indexed. A file with no manifest: see
[concepts.md](concepts.md#rights-of-content-ai_use-licence-personal-data).

## The decision rule

`../11-standard-draft.md` §4 is the normative rule: the strictest rule wins (`deny` > `escalate` > `permit`), and
no permission means `deny`. A tightening from an untrusted issuer gives `escalate` (reason `restriction-untrusted`,
notice `restricted-by:<issuer>`). In Kütüphane every restriction comes from an admissible issuer, so this does not
change its behavior. Run the cases in `kstd/tests/decision/cases.yaml`:

```sh
cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider
```

## Notes and kstd

Notes do not use `kstd.yaml` ([concepts.md](concepts.md#origin)). A note that a person confirmed has kstd item
information of the same shape (`human` with `entered_by` and `confirmed_by`, or `assisted` with `reviewed_by`). The
rollback closure of a note is the "reach of a withdrawal" of the specification.

## The minimal core (D74)

| Level | Fields | Missing → |
|---|---|---|
| Core envelope (required to register) | `standard`, `digest`, `issuer` | the book is refused |
| Core permissions (required for search and model answers) | `ai_use.search`, `ai_use.ai_input` | not indexed, never sent to a model |
| Origin (safe default) | `origin` | `unknown`, handled as `model` |
| Profiles | license, personal data, handling, inputs, origin details, acceptance, mandate and validity, activation, tags, federation | only the operation that needs the field is denied or escalated |

Details: `../11-standard-draft.md` §5 and §11.
