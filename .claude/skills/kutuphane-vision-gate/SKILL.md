---
name: kutuphane-vision-gate
description: >
  The D81 gate for Kütüphane. Use it before you plan or build any issue, request or
  feature, and again before you open a pull request. It checks the work against the
  vision (docs/23: P1–P5, the five principles, the "is not" list), D53, the freezes and
  gates in docs/01, the repository standards (CONTRIBUTING.md, D75, ponytail-kutuphane),
  and consumer compatibility when a change touches MCP tools, their results or error
  texts, grants, journal policy, tokens or the package format. Use it when someone says
  "triage", "plan the issues", "is this aligned", "vision check", "standards check",
  "breaking change" or "D81".
argument-hint: "[issue number | PR number | 'diff']"
---

# Kütüphane vision and standards gate (D81)

D81 (2026-11-04): each new work item starts from an issue and is first evaluated **critically** against
`docs/23` (P1–P5, the five principles, the "is not" list) and D53. Only work that passes is planned and built.
No speculative feature is opened. The R5 gate (D80) stays in force.

This skill is that evaluation. The vision does not bend to an issue. If an issue and the vision disagree, the
issue changes, or the operator changes the vision with a new D-record. You never change the vision yourself.

## Sources (read them; do not rely on memory)

| What | Where |
|---|---|
| Vision, promises, principles, "is not" list | `docs/23-vision-v1.md` §1–§3, §8 |
| Decisions (Turkish) | `docs/01-direction-decisions.md`: D53, D65, D70, D74, D75, D76, D77, D78, D80, D81 |
| Contribution rules | `CONTRIBUTING.md` |
| Smallest complete change, protected gates | `.claude/skills/ponytail-kutuphane/SKILL.md` |
| Earlier triage and direction | `docs/research/2026-10-31-triage-152-165.md`, `docs/research/2026-10-31-direction-analysis.md` |
| The issue itself | `gh issue view <n> -R ekaynac/kutuphane --comments` (read all triage and status comments) |

## Part A: the gate for an issue (before a plan)

Do the steps in order. Write the evidence for each step. A step with no evidence is a failed step.

1. **Need.** Name the consumer (nöbetçi-mcp, ADC, InfraMedic, a curator, the operator) and the use case. Is the
   need measured (a run, a log, a report) or only claimed? A claimed need with no consumer is speculative: **reject**
   (D81).
2. **Live state.** Check each claim of the issue against `main` with `path:line`. Mark each claim **Confirmed**,
   **Partly** or **Absent**. Read the issue comments: part of the issue is often already merged. Plan only the
   remainder.
3. **Promise.** Name the promise (P1–P5) that the work serves, and the behavior that a user can check. No promise:
   **reject** (`docs/23` §3: "Every new feature must serve one of them").
4. **Principles.** Check each of the five principles. One violation: **reject**, or redesign until none is left.
   - The write path is the provenance: no header, claim, manifest or model label outranks the authenticated path.
   - Acceptance is recorded, never assumed: each item says who accepted it and how that was proven (passkey, operator
     statement, consumer statement, policy, nobody); a book decides which kinds make an item usable; a rule needs a
     person. No label from a token subject or `on_behalf_of` counts as a person's acceptance of content.
   - Memory is data, never instruction: notes reach a model as tool results; instructions need `activate` and a scan.
   - Nothing is rewritten; everything can be withdrawn with an event and a cause.
   - An asset leaves with its rights: import and export carry origin, Standing, rights and derivation.
5. **"Is not" list** (`docs/23` §2). Does the work move Kütüphane toward a RAG platform or chat UI, a code graph, a
   run-state store, a transcript store, a standards body, an identity provider or a role store, a package workflow
   UI, or an extraction pipeline? Yes: **reject**, or ask the operator to change the vision (a D-record).
6. **D53.** Each new field, value, flag, setting, tool or route must change a behavior (a gate, an order, a citation
   right, an archive rule, a delegation, a presentation). Each state change is planned first: the trigger, the
   actor, automatic or not, the audit record, the rollback. A value that changes no behavior is removed.
7. **Freezes and gates.** Check each one:
   - D74 / D78: no new kstd statement kind or category; the block ontology (`docs/09` §1–§3) is frozen; "my words"
     gets no new work; labels and access tags (D65, #154) are frozen until G10 has a consumer; no migration per
     security review (batch the fixes).
   - D80 R5: no **new agent-memory feature** after R1–R3 merges before the T3 A/B rerun shows acceptance not lower
     and input tokens not higher than without memory. A bug fix is not a new feature.
   - D70: origin comes from the write path; an agent path is always `model`.
   - D77: no agent has a standing `propose` right on InfraMedic journals.
   - D76: one shared LLMDAP; each consumer has its own subject key and policy lines.
   - D71: SkillSpector is an external tool; its result is advice, never approval.
8. **Protected gates and boundaries** (ponytail-kutuphane "Precedence"). The work must not weaken: `ai_use`,
   egress, grants and delegation, Standing, `activate`, the skill scan block, D70, `curate` only for a person, the
   personal-data gate; validation at MCP/HTTP input, `kstd.yaml`, packages, imported records, git objects, model
   output; constraints, triggers, RLS, role grants, the pinned `search_path`.
9. **Simplicity** (`docs/23` §8: concept and command counts go down each release). Count what the work adds:
   concepts, commands, flags, settings, tools, routes, tables, migrations. Prefer an existing mechanism, a document,
   or a deletion. If the existing product already solves the need, the answer is a guide section, not code.
10. **Consumers.** If the work touches the surface listed in [`consumers.md`](consumers.md), read that file. Name each
    consumer that the work affects, what breaks for it, and the migration step, in the plan.

### Verdict

Give exactly one verdict:

| Verdict | When | What you record |
|---|---|---|
| **implement** | all steps pass | scope, files, size (S/M/L), tests, docs |
| **implement narrow** | the need passes, the proposal is too wide | the narrow form, and what is cut and why |
| **operator decision** | a step needs a choice that only the operator can make | 2–4 options, the tradeoff of each, a recommendation |
| **defer** | the need is real, but a gate or a missing piece blocks it | the gate, and the exact evidence that reopens it |
| **reject** | a step fails and no redesign passes | the failed step, and the existing alternative for the consumer |

Record the verdict as an issue comment in the existing form: `## Triage (<agent>, <date>)`, then **Verdict**,
**Plan** or **Options**, **Rejected**. Never write a D-record for a choice that the operator did not make.
When the operator decides, add the D-record to `docs/01` (Turkish, the existing table form) in the next docs PR.

## Part B: the standards check (before a pull request)

Run Part A again on the diff, then check each item:

- [ ] A branch from `origin/main`, a PR to `main`; never a push to `main`. Conventional commit: `type(scope): description`.
- [ ] A regression test for each behavior that a user can see. It fails before the change (show it).
- [ ] Both suites pass: `.venv/bin/python -m pytest -q` (needs `KUTUPHANE_TEST_DSN`) and
      `(cd kstd/reference && ../../.venv/bin/python -m pytest -q -p no:cacheprovider)`.
- [ ] D75: the affected pages of `docs/guide/` changed in the same PR; one entry in `docs/guide/changelog.md` under
      "Unreleased" (what a user or operator sees, with the PR link); `README.md` if the quick start, the MCP tool list,
      the security summary or the status changed.
- [ ] Each documented command checked with `--help`, each tool with `tools/list`; the tool-list snapshot in
      `tests/test_server.py` updated when the tool list changed.
- [ ] Prose in ASD-STE100 Simplified Technical English; code blocks exact.
- [ ] At most one migration; no applied migration edited; `deploy/db-roles*.sql` updated for a new table or function.
- [ ] Consumer compatibility: if the diff touches the surface in [`consumers.md`](consumers.md), the PR body has a
      `Consumer compatibility` section with one line for each consumer, each backed by a grep or a test run.
- [ ] The ponytail report: non-test lines added/removed, new functions and how many reuse existing code, the rules
      you searched for and what you found, what you skipped.
- [ ] The issue gets a status comment with the PR link. A tracking issue (#67, #144) gets its checklist updated.

## Output form

For each issue or PR:

```
#<n> <title>
Need: <consumer, use case, measured|claimed>
Live state: <Confirmed/Partly/Absent per claim, path:line>
Promise: <P1–P5 or none>
Principles / "is not" / D53 / freezes: <pass, or the failed item>
Adds: <concepts, commands, settings, tools, routes, migrations>
Verdict: <one verdict> — <one-line reason>
Plan | Options | Reopen trigger: <...>
```
