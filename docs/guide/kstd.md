# kstd: the knowledge contract

kstd (working name) is the written contract for the rules that Kütüphane enforces: who stands behind a file, what
may be done with it and with what is derived from it, and how a withdrawal reaches its users. The specification is
`../11-standard-draft.md` (draft 0.2). The conformance cases and a small reference evaluator are in `kstd/`
(`kstd/README.md`).

Kütüphane implements level **L0 (Described)**: one manifest file, `kstd.yaml`, at the root of a folder.

## The manifest

```yaml
standard: kstd/0.2
issuer: "ACME GmbH <knowledge@acme.example>"   # who answers for this folder
issued: 2026-10-20
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
# edit the license, ai_use and personal_data
kutuphane kstd-check <folder>                                    # digests, SPDX ids, terms; exit 1 on errors
kutuphane ingest <folder> --book <slug> --sensitivity normal --egress local_only --protection standard
```

`kstd-init` and `kstd-check` need no database. Both run the same secret scan as `ingest` and take the same
`--accept-finding` values.

`kstd-init` writes safe starting values: `license: unknown`, `ai_use: {search: y, ai_input: n, train: n}`,
`personal_data: unknown`, and `origin: unknown` for each file. Change them to the true values before you ingest.

## What Kütüphane does with each field

| Field | Effect |
|---|---|
| invalid manifest | `ingest` and `approve-import` refuse the book |
| `ai_use.search` not `y` | the file is not indexed |
| `ai_use.ai_input` not `y` | no embedding, no rerank, not in an answer; model readers get `text: null` and `withheld`; `read_document` refuses it |
| `ai_use.train` | notes derived from the file inherit it; a decision export needs it for text |
| `personal_data` not `no` or `synthetic` | `export` needs `--legal-basis` with DPV codes (for example `eu-gdpr:A6-1-b`); the codes go into the signed package |
| `origin` | shown with every result; the search filter `--origin`; the signed package lists `model`/`unknown` files as AI-generated, `assisted` files as reviewed (`reviewed_by` required), `tool` files as tool-made (`software_agent` required) |
| `license`, `valid_from`, `valid_to`, `applies_to`, `notices` | shown with search results, citations and answers (`item`) |
| `valid_from`, `valid_to` | the `--current-only` filter; `valid_from` dates a file for "recent" questions |
| absent `ai_use` term | shown as "not stated"; treated as `n` |

`kstd.yaml` itself is metadata. It is stored and checked, never indexed. A file with no manifest follows its book
policy only: it is searched and it can go to a model (the book's egress still applies). Its origin is `unknown`.

Validity keeps its time: `2026-10-27T23:59:00Z` is not current at noon that day. A date alone means 00:00 UTC.

## The decision rule

`../11-standard-draft.md` §4 is the normative decision rule. In short: the strictest applicable rule wins (`deny` >
`escalate` > `permit`); no applicable permission means `deny`; an unknown required rights term means `deny`; a
statement that tightens applies at once, one that loosens needs a trusted issuer. `kstd/tests/decision/cases.yaml`
holds the cases. Run them:

```sh
cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider
```

## Notes and kstd

Notes in journals do not use `kstd.yaml`. The journal states `search`, `ai_input` and `train`, and the server
computes origin from the write path (see `concepts.md`). The rollback closure of a note is the "reach of a
withdrawal" of the specification.

## The minimal core (D74)

The operator accepted the minimal core in D74. The envelope (`version`, `subject`, `issuer`) is required; for search
and model answers `ai_use.search` and `ai_use.ai_input` are required; everything else is a profile that only the
operation that needs it requires. `../11-standard-draft.md` is the reference for the current state of this work.
