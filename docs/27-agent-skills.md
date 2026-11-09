# Agent skills for Kütüphane (D84, #202)

**Status:** decided 2026-11-09 by `agent:omp-kutuphane`; the operator delegated the decision in #202.
**Gate:** `kutuphane-vision-gate` Part A, run on `main` 62683bb. The triage comment on #202 has the full evidence.

## 1. The skills

| Skill | Audience | Invocation | Decision | Why |
|---|---|---|---|---|
| `kutuphane-vision-gate` | developers of Kütüphane | model, repo only | **kept, extended** with consumer compatibility (Part A step 10, a Part B check, `consumers.md`) | The consumer check has the same reader and the same moment (before a PR) as Part B. A second description would add context load to every session in this repository for a branch that the gate already reaches. |
| `ponytail-kutuphane` | developers of Kütüphane | model, repo only | **kept, unchanged** | Every symbol that it names exists on `main`. Every coding agent has used it since #168. |
| `kutuphane-memory` | any omp or Claude Code session with the `kutuphane` MCP | model, repo + user links | **new** | Five live harness principals. It is generalised from nöbetçi's `supervisor-memory` and corrects that skill's `search_library` advice: on a journal, `search_library` gives HTTP 400. |
| library research (`search_library` → `open_citation` → cite) | harness sessions | — | **deferred** | No harness principal can read a content book. On 2026-11-09, `list_books` for `omp-kutuphane`, `omp-adc`, `omp-default` and `nobetci-supervisor` gave journals only. The one fact that applies today ("search and ask do not read journals") is in `kutuphane-memory`. |
| `supervisor-memory` (nöbetçi) | the nöbetçi host | model | **points at `kutuphane-memory`** | It keeps only the host facts: the cwd → principal table, the `nobetci-memory` exclusion, the WORK_QUEUE ledger rule and the curator. |

**Reopen the research skill** when a harness principal gets `read` on a content book, or when a consumer files a
research use case.

## 2. Distribution

- **Developer skills** stay in `.claude/skills/` and load only in sessions inside this repository. Their triggers
  ("every coding task in this repository") would misfire in other projects.
- **`kutuphane-memory`** lives in `.claude/skills/` too, so it versions with the MCP surface. Other projects on the
  same machine get it through a link from `~/.omp/agent/skills/` (omp) and `~/.claude/skills/` (Claude Code) to a
  checkout that stays on `main` ([agent-memory.md](guide/agent-memory.md) §14).
- The skills do not set up identities or tokens: that is #200 (provisioning) and #201 (the identity guide).

## 3. Evidence that the skills change behaviour

Each run is `omp -p --mode json` with the default model (`gpt-6.1-sol`) in a fresh session. A baseline ran without the
skill (`--no-skills`), or with the skill as it was on `main`.

| Run | Without the change | With the change |
|---|---|---|
| **Memory, read:** "Is there an earlier decision on agent skills or MCP use?" | 9 calls: `search_library` 2× (it cannot read journals), `query_notes` 3× without `book`, budgets up to 10,000 tokens, `list_books` last | 6 calls: `list_books` first, then `query_notes` with `book: [own, shared]` and `sets: [current, open]`, then `history`; no `search_library` |
| **Memory, write:** "Operator ruling #202 … record it" | — | `decision_proposal` in the own journal, `pending`, origin `model`, dated, with `idempotency_key: 202-2026-11-09-skill-set-decision`. Second run: it read with `budget_tokens: 1500`, found the note, and wrote no copy (`status: existing`) |
| **Gate:** "Plan: change the MCP error text `forbidden` to `access denied: <reason>`" | Old gate on `main`, fresh session: 39 calls; it never opened nöbetçi and named **no** consumer | New gate: it read `consumers.md` and named `nobetci_mcp/memory.py:96-103` (prefix parse), the `kutuphane-memory` line that cites the text, and InfraMedic's HTTP 403 contract. It wrote a `Consumer compatibility` PR section, and gave the verdict "operator decision" with the option "keep the `forbidden` prefix" |

The first write run also called `confirm_origin` without a request, because of a loose line about dictated text. That
call only reads a state (it writes nothing). The line was narrowed before merge, and the second run did not call it.

One baseline was void and was run again: an `omp -p` started in `~/kobra` resumed the open operator session
(`parentSession`), so it saw this conversation. The reruns use an empty `--session-dir`.

## 4. Not done here

- **A consumer contract test** that pins the error prefixes and result keys that nöbetçi's `memory.py` parses. A skill
  reminds a developer; a test fails the build. nöbetçi's own tests use a fake Kütüphane and stay green after a
  change (`nobetci-mcp/README.md:137`). This needs its own issue.
- The research skill (§1).
