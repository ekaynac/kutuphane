# kstd — knowledge standard (working name)

The specification draft is `docs/11-standard-draft.md`. This folder holds the parts that make the draft testable:

| Path | Purpose |
|---|---|
| `tests/decision/cases.yaml` | Conformance cases for the decision rule (§4): inputs and the expected `result`, `authority`, `reasons`, `notices`. A conforming implementation MUST give the same output for every case. |
| `reference/decide.py` | A small reference evaluator. It proves that the cases are consistent. It is not a product component. |
| `reference/test_cases.py` | Runs the cases: `cd kstd/reference && python -m pytest`. |

**Rule:** each new rule or value in the specification comes with at least one case that fails when the rule is removed.
