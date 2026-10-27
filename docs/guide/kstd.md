# kstd: the knowledge contract

kstd (working name) is the written contract for the rules that Kütüphane enforces: who stands behind a file, what
may be done with it and with what is derived from it, and how a withdrawal reaches its users. The specification is
`../11-standard-draft.md` (draft 0.3). The conformance cases and a small reference evaluator are in `kstd/`
(`kstd/README.md`).

Kütüphane implements level **L0 (Described)**: one manifest file, `kstd.yaml`, at the root of a folder.

## The manifest

```yaml
standard: kstd/0.3                       # the version; kstd/0.2 is still accepted
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this folder
issued: 2026-10-20                       # optional
rights:                                  # defaults for every item
  license: CC-BY-4.0                     # SPDX id, or unknown
  holder: "ACME GmbH"
  ai_use: {search: y, ai_input: y, train: n}   # absent = not stated; a decision treats it as n
  personal_data: no                      # yes | no | synthetic | unknown (= yes)
notices: ["Attribution: ACME GmbH, 2026"]
items:
  - path: procedures/pressure-test.md
    digest: sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
    origin: human                        # human | assisted | model | tool | unknown (= model)
    entered_by: "agent:kobra-7"          # optional for human: who entered the words
    confirmed_by: "user:ayse"            # optional for human: the person who confirmed them as their own
    valid_from: 2026-01-01
    applies_to: "Plant 3, line A"
  - path: notes/weekly-summary.md
    digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
    origin: assisted                     # a model wrote it; a named person reviewed it
    reviewed_by: "Ayşe Yılmaz <ayse@acme.example>"
    rights: {personal_data: unknown}     # overrides the default
  - path: reference/api/index.html
    digest: sha256:2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae
    origin: tool                         # written rules only; no learned model at any step
    software_agent: {name: typedoc, version: "0.26.11"}
```

Each item names one file by path and SHA-256 digest. An item can override the default rights.

## Workflow

```sh
kutuphane kstd-init <folder> --issuer "ACME <kb@acme.example>"   # writes kstd.yaml with every file and its digest
# state ai_use, and edit the license and personal_data
kutuphane kstd-check <folder>                                    # errors (exit 1) and warnings
kutuphane ingest <folder> --book <slug> --sensitivity normal --egress local_only --protection standard
```

`kstd-init` and `kstd-check` need no database. Both run the same secret scan and the same personal-data scan as
`ingest`, and take the same `--accept-finding` and `--deny-names` values.

`kstd-init` writes safe starting values: `license: unknown`, `personal_data: unknown`, and `origin: unknown` for
each file. It states **no `ai_use` term**: the line `# ai_use: {search: y|n, ai_input: y|n, train: y|n}` is only a
comment. Until you state the terms, no file is indexed and no file is sent to a model, and `kstd-check` warns
"no default ai_use". If you remove the `#` and keep `y|n`, `kstd-check` gives an error: select `y` or `n`. Change
the values to the true values before you ingest.

### Origin proposals from a source repository

Run `kstd-init` on a copy of the folder. A copy has no git history, so give the repository that it came from:

```sh
kutuphane kstd-init <copy> --issuer "ACME <kb@acme.example>" --source-repo <repo> [--commit <rev>]
```

- **Match.** A file of the copy matches a file in the tree of the commit (default `HEAD`): the same path, the
  same end of a path (a copy of a subfolder), or the same content at another path. If the path matches and the
  content is different, git has no evidence for the change: the file stays `unknown`. If the copy was taken at an
  older commit, give that commit with `--commit`.
- **History.** The commits that changed the matched path, back to the commit that added it. Renames are followed.
  Merge commits are not counted.
- **Proposal.** `model` when every one of these commits has a `Co-Authored-By` trailer with a known model agent
  (for example `Claude … <noreply@anthropic.com>`, GitHub Copilot, Cursor Agent, aider, Codex, Gemini). Else
  `unknown`. A person's name alone (`Claude Monet`) is not a model.
- **Never proposed:** `human`, because a person's commit does not prove that a person wrote the words; `assisted`,
  because it needs a named reviewer; `tool`, because it needs a `software_agent`. `model` and `unknown` are handled
  the same way, so a wrong proposal gives no permission.

The proposal is a value with a comment, and the evidence is comment lines of the item. `kstd-check` and ingest read
it as a normal value; the comments are for you:

```yaml
# proposals from git: /src/handbook at 1223ca71ff9c… (a proposal is not authority: check each origin before you publish)
items:
  - path: "rules/backup.md"
    digest: sha256:…
    origin: model                     # proposed from git: 2 of 2 commits name a model; rules/backup.md at 1223ca71ff9c (same path and content)
    #   e0d712a9591d Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
    #   cc290e35fe49 Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  - path: "notes/site.md"
    digest: sha256:…
    origin: unknown                   # git: 1 of 2 commits name a model; notes/site.md at 1223ca71ff9c (same path and content)
    #   5b1f0c2d9e8a no model trailer
    #   9a7e6d5c4b3a Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

`kstd-init` prints the counts (`origin proposals from git: model 30, unknown 3`). It reads only a local
repository and does not change it: no fetch (also not for a partial clone), no hooks, no signature check.

### Personal-data findings

`kstd-init` lists each personal-data or fleet-data finding on stderr (path, line and rule, never the matched
text), and writes `personal_data: unknown` for the item of that file, with the findings as a comment:

```yaml
  - path: "notes/site.md"
    …
    rights:
      personal_data: unknown            # proposed: personal-data findings: email (line 3); private-ipv4 (line 4); check them
```

So a folder default `personal_data: no` does not cover that file. Set the true value after you check the file. A
finding never proposes `no`. The rules and the `--deny-names` file are in
[operations.md](operations.md#personal-data-and-fleet-data-findings).

## Validation

`kstd-check` and `ingest` keep three results apart:

| Result | Cause | Effect |
|---|---|---|
| error | a YAML alias, merge key or duplicate key; a wrong type; no `issuer`; an unknown `standard`; a digest that does not match; an invalid SPDX expression; an `ai_use` value that is not `y` or `n` ("ai_use terms take y or n"); an invalid `personal_data` or `origin` value; an invalid date or path | `ingest` and `approve-import` refuse the book |
| warning: the claim is not trusted | an unknown field that does not start with `x-` (also an unknown `ai_use` term); `origin: assisted` without `reviewed_by`; `origin: tool` without `software_agent: {name, version}` as strings; `reviewed_by` without `assisted`; `software_agent` without `tool`; `entered_by` or `confirmed_by` without `human`, or not a non-empty string | publication continues. The field is ignored, or the origin counts as `unknown` (handled as `model`). The item `notices` in search results, citations and answers show the same text, for example `kstd.yaml politika/x.md: origin 'assisted' not trusted: …; handled as unknown` |
| authorized | the fields in the next table | each operation reads only the fields that it needs |

## What Kütüphane does with each field

| Field | Effect |
|---|---|
| manifest with an error (see Validation) | `ingest` and `approve-import` refuse the book |
| `ai_use.search` not `y` | the file is not indexed |
| `ai_use.ai_input` not `y` | no embedding, no rerank, not in an answer; model readers get `text: null` and `withheld`; `read_document` refuses it |
| `ai_use.train` | notes derived from the file inherit it; a decision export needs it for text |
| `personal_data` not `no` or `synthetic` | `export` needs `--legal-basis` with DPV codes (for example `eu-gdpr:A6-1-b`); the codes go into the signed package |
| `origin` | shown with every result; the search filter `--origin`; the signed package lists `model`/`unknown` files as AI-generated, `assisted` files as reviewed (with `reviewed_by`), `tool` files as tool-made (with `software_agent`), and `human` files that carry `entered_by` or `confirmed_by` in `human_confirmed`. An `assisted` or `tool` claim without its evidence counts as `unknown`, so the file is listed as AI-generated. `human` stays `human` without `entered_by` and `confirmed_by`: they are optional. |
| `license`, `valid_from`, `valid_to`, `applies_to`, `notices` | shown with search results, citations and answers (`item`) |
| `valid_from`, `valid_to` | the `--current-only` filter; `valid_from` dates a file for "recent" questions |
| absent `ai_use` term | shown as "not stated"; treated as `n` |

`kstd.yaml` itself is metadata. It is stored and checked, never indexed. A file with no manifest follows its book
policy only: it is searched and it can go to a model (the book's egress still applies). Its origin is `unknown`.

Validity keeps its time: `2026-10-27T23:59:00Z` is not current at noon that day. A date alone means 00:00 UTC.

## The decision rule

`../11-standard-draft.md` §4 is the normative decision rule. In short: the strictest applicable rule wins (`deny` >
`escalate` > `permit`); no applicable permission means `deny`; an unknown required rights term means `deny`; a
statement that loosens needs a trusted issuer. A statement that tightens applies at once only from the node, the
item's own issuer, or an issuer trusted for that kind and scope. From any other issuer, it gives `escalate`
(reason `restriction-untrusted`, notice `restricted-by:<issuer>`), never `deny`. A later statement of an issuer
replaces its earlier one, but a loosening replaces a restriction that applies only when the issuer is trusted for
that kind, scope and action. So an unauthorized loosening cannot turn a `deny` into a `permit`; the restriction
stays in force. An issuer without trust can still withdraw its own tightening that never applied. In
Kütüphane, every restriction comes from an admissible issuer (the `kstd.yaml` issuer, an administrator, or an
authorized curator), so this rule does not change its behavior. `kstd/tests/decision/cases.yaml` holds the cases.
Run them:

```sh
cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider
```

## Notes and kstd

Notes in journals do not use `kstd.yaml`. The journal states `search`, `ai_input` and `train`, and the server
computes origin from the write path (see `concepts.md`). A person can confirm a note's words with a passkey in
curator web ([operations.md](operations.md), section 7). The note then shows `human` or `assisted` with
`entered_by` and `confirmed_by`. Its kstd item information has the shape of these fields: `human` with
`entered_by` and `confirmed_by`, or `assisted` with `reviewed_by` (the person who confirmed). The rollback closure
of a note is the "reach of a withdrawal" of the specification.

## The minimal core (D74)

Draft 0.3 has a minimal core:

| Level | Fields | Missing → |
|---|---|---|
| Core envelope (required to register) | `standard` (the version), `digest` (the subject), `issuer` | the book is refused |
| Core permissions (required for search and model answers) | `ai_use.search`, `ai_use.ai_input` | not indexed, never sent to a model |
| Origin (safe default) | `origin` | `unknown`, handled as `model` |
| Profiles | license, personal data, handling, inputs, origin details, acceptance, mandate and validity, activation, tags, federation | only the operation that needs the field is denied or escalated |

`../11-standard-draft.md` §5 and §11 give the details and the changes from draft 0.2.
