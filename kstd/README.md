# kstd — knowledge standard (working name)

The specification draft is `docs/11-standard-draft.md`. This folder holds the parts that make the draft testable:

| Path | Purpose |
|---|---|
| `tests/decision/cases.yaml` | Conformance cases for the decision rule (§4): inputs and the expected `result`, `authority`, `reasons`, `notices`. A conforming implementation MUST give the same output for every case. A derived item is checked against its whole recorded lineage (inputs of inputs, transitively, cycle-safe; a missing ancestor gives `input-unknown`): rights, `ai_use` and personal data (with the synthetic trust rule) per input, and it inherits the strictest `export` and `route` handling of the lineage. |
| `tests/erasure/cases.yaml`, `reference/erase.py` | Conformance cases for the reach of an erasure (§3 `erase`, §5 Inputs): erased, kept, unresolved copies at other nodes, derived items with unknown scope. The reach starts from every requested id, also one that is not held locally; only local items are reported as erased, and deliveries of any reached item stay unresolved. `inputs: []` counts as no recorded inputs (scope unknown). |
| `reference/decide.py` | A small reference evaluator. It proves that the cases are consistent. It is not a product component. |
| `reference/test_cases.py` | Runs the cases: `cd kstd/reference && python -m pytest`. |

**Rule:** each new rule or value in the specification comes with at least one case that fails when the rule is removed.

## L0 in Kütüphane

```sh
kutuphane kstd-init <folder> --issuer "ACME <kb@acme.example>"   # writes kstd.yaml: every file with its digest
# edit license, ai_use and personal_data
kutuphane kstd-check <folder>                                    # digests, SPDX ids, terms; exit 1 on errors
kutuphane ingest <folder> --book … --sensitivity … --egress … --protection …
# a reviewed credential-scan false positive (see the root README): one rule, one exact file content, recorded
kutuphane ingest <folder> … --accept-finding docs/ornek.md@sha256:<sha256sum of the file>:aws-access-key
```

A book with `kstd.yaml` follows it (`src/kutuphane/kstd.py`):

| Field | Effect in Kütüphane |
|---|---|
| invalid manifest | publication (ingest and approve-import) is refused |
| `ai_use.search` not `y` | the file is not indexed (every searched format: markdown, PDF, text formats, JSONL records, HTML) |
| `ai_use.ai_input` not `y` | its passages never reach a model: no embedding, no reranking, not in answer passages (the answer reports `withheld`); MCP callers and agent principals get no text (`text: null`, `withheld`) and `read_document` is refused |
| `personal_data` not `no` or `synthetic` | `export` needs `--legal-basis` with DPV codes (e.g. `eu-gdpr:A6-1-b`); the codes are recorded in the signed package |
| `origin` `model` or `unknown` / `assisted` | the signed package lists the file in `ai_generated` / in `reviewed` with its `reviewed_by` (EU AI Act Art. 50(4)); `assisted` needs `reviewed_by` |
| `ai_use` term absent | reported as absent ("not stated"); every decision treats it as `n` |
| origin, license, validity, applies_to, notices | shown with search results, citations and answers (`item`) |

A book without `kstd.yaml` behaves as before. Absent `ai_use` terms mean `n`; an unknown license gives no permission.
`kstd.yaml` itself is metadata: it is stored and checked, never indexed. A quarantined file (Kütüphane stores it
but cannot extract it, see the root README) keeps its kstd rights; it is not searched until a version fixes it.
