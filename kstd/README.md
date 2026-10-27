# kstd — knowledge standard (working name)

The specification draft is `docs/11-standard-draft.md` (draft 0.3). This folder holds the parts that make the draft testable:

| Path | Purpose |
|---|---|
| `tests/decision/cases.yaml` | Conformance cases for the decision rule (§4): inputs and the expected `result`, `authority`, `reasons`, `notices`. A conforming implementation MUST give the same output for every case. A derived item is checked against its whole recorded lineage (inputs of inputs, transitively, cycle-safe; a missing ancestor gives `input-unknown`): rights, `ai_use` and personal data (with the synthetic trust rule) per input, and it inherits the strictest `export` and `route` handling of the lineage. Rule 4 (restriction admissibility): a tightening counts only from the node, the item's own issuer, or an issuer trusted for that kind × scope; from any other issuer it gives `escalate` (`restriction-untrusted`, notice `restricted-by:<issuer>`), never `deny`. |
| `tests/erasure/cases.yaml`, `reference/erase.py` | Conformance cases for the reach of an erasure (§3 `erase`, §5 Inputs): erased, kept, unresolved copies at other nodes, derived items with unknown scope. The reach starts from every requested id, also one that is not held locally; only local items are reported as erased, and deliveries of any reached item stay unresolved. `inputs: []` counts as no recorded inputs (scope unknown). |
| `reference/decide.py` | A small reference evaluator. It proves that the cases are consistent. It is not a product component. |
| `reference/test_cases.py` | Runs the cases: `cd kstd/reference && python -m pytest`. |

**Rule:** each new rule or value in the specification comes with at least one case that fails when the rule is removed.

## The minimal core (D74)

| Level | Fields | Missing → |
|---|---|---|
| Core envelope (registration) | `standard` (version), `digest` (subject), `issuer` | not registered: publication is refused |
| Core permissions (search, model answers) | `ai_use.search`, `ai_use.ai_input` | `deny`: not indexed, never sent to a model |
| Origin (safe default) | `origin` | `unknown`, handled as `model` |
| Operation profiles | license, personal data, handling, inputs, origin details, acceptance/mandate/validity, activation, tags, federation | only the operation that needs the field is denied or escalated |

## L0 in Kütüphane

```sh
kutuphane kstd-init <folder> --issuer "ACME <kb@acme.example>"   # writes kstd.yaml: every file with its digest
# state ai_use (init writes no term: nothing is indexed or sent to a model), license and personal_data
kutuphane kstd-check <folder>                                    # errors (exit 1) and warnings (untrusted claims)
kutuphane ingest <folder> --book … --sensitivity … --egress … --protection …
# a reviewed credential-scan false positive (see docs/guide/operations.md §2): one rule, one exact file content, recorded;
# kstd-init and kstd-check take the same --accept-finding values
kutuphane ingest <folder> … --accept-finding docs/ornek.md@sha256:<sha256sum of the file>:aws-access-key
```

`kstd-init` writes `standard: kstd/0.3`. A manifest with `standard: kstd/0.2` is still read; the fields are the same. `issued` is optional.

A book with `kstd.yaml` follows it (`src/kutuphane/kstd.py`). Validation has three separate results (docs/11 §7):

| Result | Cause | Effect in Kütüphane |
|---|---|---|
| not readable | YAML aliases, merge keys or duplicate keys; a wrong type; no `issuer`; an unknown `standard`; a digest that does not match; a wrong value (SPDX expression, `ai_use` term not `y`/`n`, `personal_data`, `origin`, a date, a path) | publication (ingest and approve-import) is refused |
| claim not trusted | an unknown field (not `x-`); `assisted` without `reviewed_by`; `tool` without `software_agent: {name, version}` as strings; `reviewed_by` or `software_agent` for another origin | publication goes on; the field is ignored, or the origin counts as `unknown`; `kstd-check` warns, and the item `notices` carry the same text |
| authorized | the fields below | each operation reads only what it needs |

| Field | Effect in Kütüphane |
|---|---|
| `ai_use.search` not `y` | the file is not indexed (every searched format: markdown, PDF, text formats, JSONL records, HTML) |
| `ai_use.ai_input` not `y` | its passages never reach a model: no embedding, no reranking, not in answer passages (the answer reports `withheld`); MCP callers and agent principals get no text (`text: null`, `withheld`) and `read_document` is refused |
| `personal_data` not `no` or `synthetic` | `export` needs `--legal-basis` with DPV codes (e.g. `eu-gdpr:A6-1-b`); the codes are recorded in the signed package |
| `origin` `model` or `unknown` / `assisted` / `tool` | the signed package lists the file in `ai_generated` / in `reviewed` with its `reviewed_by` (EU AI Act Art. 50(4)) / in `tool_made` with its `software_agent`, and gives it no AI mark; an `assisted` or `tool` claim without its evidence counts as `unknown`, so the file is in `ai_generated` |
| `ai_use` term absent | reported as absent ("not stated"); every decision treats it as `n` |
| origin, license, validity, applies_to, notices | shown with search results, citations and answers (`item`) |

A book without `kstd.yaml` behaves as before. Absent `ai_use` terms mean `n`; an unknown license gives no permission.
`kstd.yaml` itself is metadata: it is stored and checked, never indexed. A quarantined file (Kütüphane stores it
but cannot extract it, see `docs/guide/operations.md` §2) keeps its kstd rights; it is not searched until a version
fixes it.

Kütüphane has no third-party restriction statements at L0. A tightening comes only from the `kstd.yaml` issuer
(also the enclosed manifest of a received package), an administrator (`journal restrict`) or the system cascade of
an authorized curator. Each one is an admissible issuer under rule 4.
