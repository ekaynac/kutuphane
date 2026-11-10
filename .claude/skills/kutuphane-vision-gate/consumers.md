# Consumers of the Kütüphane surface

Read this when a change touches the **surface**. The change is done when the PR body has a `Consumer compatibility`
section with one line for each consumer below, and each "unchanged" line has a grep or a test run behind it.

## What counts as the surface

- **MCP:** tool names, arguments, result keys, error texts, and the protocol envelope (2026-07-28: stateless, with the
  `Mcp-Method` and `Mcp-Name` headers; the result is JSON text in `content[0].text`).
- **HTTP:** routes, parameters, bodies and status codes.
- **Authorization:** grant modes and what each one permits; the defaults of `journal create`.
- **Identity:** token claims, issuers, principal prefixes, and the `kutuphane dev-token` flags.
- **Packages:** the format (`kutuphane-package/1`, `docs/guide/operations.md` "Package format") and the behaviour of
  `receive` and `approve-import`.
- **CLI:** the commands and flags that a consumer runs: `dev-token`, `journal create`, `agent add`, `grant`, `pack`,
  `receive`.

## The consumers

### 1. nöbetçi-mcp memory client (`~/nobetci-mcp/nobetci_mcp/memory.py`)

- **Uses:**
  - `query_notes`, `propose_note`, `link_notes`, `record_outcome` over MCP 2026-07-28, with one `tools/call` per
    request (`:54-65`).
  - The result keys `items`, `standing`, `text`, `scope.paths`, `ref`, `status`, `recurrence`, and
    `candidates[].ref/standing/match/similarity` (`:289-361`).
- **Error texts:** it classifies errors by **text prefix** (`:96-103`). These strings are a contract: `Error executing
  tool`, `forbidden`, `not found`, `limit reached`, `at most 3 open jobs`, `reused with another request`,
  `authorization changed`, `internal error`, `model service`.
- **How it breaks:** silently. A failed call turns memory off for that job, and the job runs on (`:7-9`). Its own
  tests use a fake Kütüphane, so they stay green.
- **Check:** grep Kütüphane's `src/` for each changed string or key, and compare it with the lines above.
- **Announce:** an issue in `ekaynac/nobetci-mcp` that names the PR.

### 2. Coding-harness sessions (omp, Claude Code, Codex)

- **Uses:**
  - the `kutuphane` MCP, with the skill `.claude/skills/kutuphane-memory` from this repository;
  - one principal per project (`~/nobetci-mcp/ops/README.md` "Kütüphane identities");
  - tokens from `~/nobetci-mcp/ops/kutuphane-agent-tokens:20-21`
    (`KUTUPHANE_DEV=1 kutuphane dev-token <p> --agent --client-id <p> --private-key … --issuer …/dev`, every 4 h).
- **How it breaks:**
  - A renamed tool, argument or result field makes the skill wrong: agents waste turns, or write notes in the wrong
    shape.
  - A changed `dev-token` flag stops the minter: every session loses memory within 4 h.
- **Check:** grep `.claude/skills/kutuphane-memory/SKILL.md` for each changed name. Run the minter once:
  `systemctl --user start omp-kutuphane-tokens`.
- **Announce:** change the skill **in the same PR**, and change the README recipe in `ekaynac/nobetci-mcp`.

### 3. InfraMedic (#144)

- **Uses:** it has no client code yet. Its build follows a written contract:
  - the issuer contract on #144: EdDSA, `aud: kutuphane`, prefixes `user:im.` and `agent:inframedic-`;
  - the W4 design `~/nobetci-dev/docs/research/2026-10-31-kutuphane-integration-design.md`:
    - `/v1/books`, `/v1/books/{book}/files`;
    - `/v1/search` with `platform`, `version` and `max_chars`;
    - `/v1/citation`, `/v1/files/…`, `/v1/notes` (GET and POST);
    - `/v1/packages`, and `X-Correlation-Id`;
  - the package format.
- **How it breaks:** its P1 and P2 code is built against the old contract.
- **Check:** compare the change with the routes and fields above.
- **Announce:** a comment on #144 that gives the change, the PR and the migration step.

## The PR section

```
## Consumer compatibility
- nöbetçi-mcp memory.py: unchanged (grep: …) | breaks: … → nobetci-mcp#…
- harness sessions / kutuphane-memory: unchanged | skill updated in this PR | minter: …
- InfraMedic (#144): unchanged | breaks: … → comment on #144
```

A new consumer (a new client, a new skill, a new identity recipe) gets its own section in this file, in the PR that
adds it.
