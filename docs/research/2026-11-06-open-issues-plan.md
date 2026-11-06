# Plan: the open issues on 2026-11-06 (D81 gate)

**Status:** decided. The operator answered the questions of §3 on 2026-11-06 (D82). Each verdict comes from the
`kutuphane-vision-gate` skill (`.claude/skills/kutuphane-vision-gate/SKILL.md`).
**Base:** `main` 1e9747c (#191). Open issues: #67, #73, #138, #141, #144, #158, #162, #163. Open PRs: none.
**Notation:** `[INFERENCE]` = not verified. Live facts were read on the Spark host on 2026-11-06.

## 1. Summary

| # | Title (short) | Verdict | Promise | Size | Blocked by |
|---|---|---|---|---|---|
| #141 | Unattended operation | **implement narrow** (a gap in the shipped policy + a host recipe); the policy form is an operator choice | P5 | S | operator: Q1 (policy form, live kill test, D76) |
| #73 | MCP migration, headless auth | **implement narrow** (a guide recipe, no code) | P2, P5 | S | the live TLS probe needs the operator |
| #144 | InfraMedic tracking | **update** the checklist; re-run the P0 shadow after #141 | — | — | #141 |
| #67 | Orchestrator tracking | **close** when #73 closes | — | — | #73 |
| #162 | Curator web: approve a package | **reject** ("is not" list) | — | — | operator may change the vision |
| #158 | Roles from a token claim | **operator decision**; recommended: defer | P3 | M | the InfraMedic issuer does not exist yet |
| #163 | Approved notes in search and ask | **defer** | P1 | L | R5 gate (D80); no measured need |
| #138 | G10 item-level access | **defer** (keep open) | P3 | L | D78 freeze; D81 (InfraMedic P0 count) |

Work order: #141 → #73 → #144 and #67 status → the comments for #162, #158, #163, #138.

## 2. Per issue

### #141 Unattended operation

- **Need:** InfraMedic 2.9 (a 30-day unattended run on the same host) and nöbetçi-mcp. **Measured.**
- **Live state:**
  - Restart policies and `GET /v1/health`: **Confirmed** merged (#147).
  - **New defect, measured on 2026-11-06.** `kutuphane-reranker-gpu-1` is `Exited (0)` since
    2026-11-04T14:01:21Z, `RestartCount=0`, policy `on-failure:5`. Its log ends with vLLM
    `EngineDeadError`, then a clean shutdown with exit code 0. `on-failure` never restarts an exit code 0.
    Two minutes later the InfraMedic P0 shadow run (`/home/mega/nobetci-dev/docs/research/2026-11-04-kutuphane-p0-shadow/`)
    reports `rerank: failed × 12` and `× 15`. So the reranker was down for 42 hours with no person told.
  - Host Core unit: **Absent** from the guide. The live Core is the user unit `kutuphane-core.service`
    (#141 comment, 2026-10-29). Its `WorkingDirectory` is `/home/mega/kobra` and it runs that checkout's
    editable `.venv`. A restart runs whatever branch is checked out there. `[INFERENCE]` no other process
    pins the deployed version.
  - The live reboot and `docker kill` test: **Absent**. D76 says: not now.
- **Gate:** P5; no principle touched; no "is not" item; adds no concept.
- **Verdict: implement narrow.**
  1. `reranker-gpu` must come back after an engine death. The `on-failure:5` cap is deliberate
     (`deploy/compose.full.yaml:177–179`: a crash loop competes with the chat model for the shared GPU memory),
     so the form is **operator question Q1**:
     - (a) `restart: unless-stopped`: the simplest; no cap, Docker's delay doubles to a limit;
     - (b) **recommended:** keep `on-failure:5`, and make an engine death exit non-zero
       (`entrypoint: ["sh", "-c", "vllm serve …; exit 1"]` or the equivalent). The cap stays; `docker stop` still
       stops it (Docker never restarts a container that a person stopped);
     - (c) no change; the operator watches `GET /v1/health`.
     Update `install.md` "Reboot and restart", the comment at `compose.full.yaml:177`, and the changelog. No test
     pins the compose policy text (a source-text test); the proof is the live check in Q1.
  2. `install.md`: a "Core as a host user service" recipe. It runs from a separate, pinned checkout (a tag or a
     merged commit), never from a development tree. `EnvironmentFile` mode 0600, `Restart=always`.
  3. Operator action (no code): start the reranker now, and run the kill test when the operator allows it.
- **Not in scope:** the host-specific free-memory wrapper (rejected in the 2026-10-29 triage); alerting.

### #73 MCP 2026-07-28, long operations, headless auth

- **Need:** nöbetçi-mcp runs jobs up to 12 h with an 8 h development token (`devauth.TTL_SECONDS`,
  `src/kutuphane/devauth.py:18`); a timer re-mints it, so the dev signing key stays next to the orchestrator.
  **Measured** (#73 comment, 2026-10-29).
- **Live state:** the protocol work, background jobs, issuer pinning and the scoped T3 client: **Confirmed**
  merged (#100–#105). Several issuers bound to principal prefixes: **Confirmed** merged (#172,
  `KUTUPHANE_OIDC_ISSUERS`, `src/kutuphane/identity.py:36`, `curate` refused by default).
- **Gate:** P2, P5. "Is not an identity provider": Kütüphane must not mint tokens. The #157 issuer entry already
  lets a consumer sign its own short-lived tokens, with its public JWKS on the host. That is the contract that
  InfraMedic got (#144 comment, 2026-11-01).
- **Verdict: implement narrow, documentation only.** A section in `docs/guide/agent-memory.md` (or
  `operations.md`): "A single-host orchestrator without an IdP". It names the issuer entry
  (`principal_prefixes: ["agent:nobetci-"]`, `curate` absent), the token shape (EdDSA, 5 min, `kid`,
  `aud: kutuphane`, `kutuphane/principal_type: agent`), and the JWKS rotation rule. Check each claim against
  `identity.py` and with `kutuphane whoami`. No `--ttl` flag on `dev-token`: `KUTUPHANE_DEV=1` is for
  development machines only (`operations.md`).
- **Outside this repository:** the token signer in nöbetçi-mcp. File it there.
- **Close #73** after the operator runs the live probe (TLS, a real token), or after the operator says that the
  probe is not needed.

### #144 InfraMedic tracking

- **Verdict: update.** Tick the merged items: #136, #137, #139, #140, #142, #143 (issue body) and #156, #157,
  #159, #160, #161, #164, #165 (W4 comment). Pilot 2 step 6 (the shadow comparison) ran twice on 2026-11-04:
  `p0shadow1` top-1 agreement 8 of 12 (0.67), recall@8 canon 0.8 against 1.0, losses `edge-runner-why`,
  `rbac-gate-map`; `p0shadow2` top-1 13 of 15 (0.87), recall@8 canon 0.9 against 1.0, loss
  `g4-canon-05-continuous-deployment`. Both runs report `rerank: failed` for every question: the reranker was down
  (see #141), so these numbers do not measure the product. Ask the InfraMedic side to re-run both after the #141
  fix. Open a retrieval issue only if the losses stay.

### #67 Orchestrator tracking

- **Verdict: close** when #73 closes. Every other child is closed. Further memory work is behind the R5 gate (D80).

### #162 Curator web: approve or reject a received package

- **Need:** on a customer appliance the approver is the InfraMedic approver, not a shell user (Faz 2→3 rule
  "30 days without vendor intervention"). **Claimed**, not measured.
- **Live state:** **Confirmed** absent (`src/kutuphane/curatorweb.py:269–282`: no package routes).
- **Gate:** fails step 5. `docs/23` §2 says that Kütüphane is **not** "a package workflow UI: a package is approved
  once, on the CLI". The direction analysis (§3, §9) calls it drift toward a CMS workflow.
- **Verdict: reject**, with the existing alternative: `submit_package` + `approve-import` on the CLI.
  The operator can change this only with a D-record that changes `docs/23` §2.

### #158 Role membership from a token claim

- **Need:** InfraMedic scoped roles without a sync job. **Claimed.** The InfraMedic token signer does not exist
  yet (#144 comment, 2026-11-01).
- **Live state:** **Confirmed** absent (no `role_claim` in `src/kutuphane/identity.py`; membership is DB-only).
- **Gate:** step 5 is at risk ("not a role store: tokens come from the IdP, grants live here"); step 4, principle 1
  holds only if the claim is from a pinned issuer. The direction analysis: "accept only read-only, `curate`
  refused, or reject".
- **Verdict: operator decision.** Options:
  - (a) **defer** until the InfraMedic issuer is live and InfraMedic shows a sync cost (recommended: no consumer can
    send the claim today);
  - (b) the narrow form: per request, `read` only, only roles under the issuer's `role_prefix`, never `curate` or
    `propose`, the claimed roles in `access_event`;
  - (c) reject, and keep `kutuphane grant` + an InfraMedic sync job.

### #163 Approved notes as evidence in search and ask

- **Need:** InfraMedic wants one call instead of `search_library` + `query_notes`. **Claimed.** D77 makes
  approved InfraMedic notes rare (agents write only on the operator's request).
- **Live state:** **Confirmed** absent (`search.py`, `answers.py` read passages only).
- **Gate:** step 7 fails. It is a new agent-memory feature after R1–R3, so the R5 gate (D80) blocks it until the
  T3 A/B rerun. Step 6 is open: it adds a citation kind `note` to search results (D53).
- **Verdict: defer.** Reopen when both are true: the T3 rerun passes R5, and an InfraMedic P1 read path shows the
  second `query_notes` call as a measured cost. The workaround is one `query_notes` call (40 ms).

### #138 G10 item-level access

- **Live state:** option 2 (one book per scope) is **Confirmed** merged with an isolation test (#148).
- **Gate:** D78 freezes access tags until G10 has a consumer; D81 keeps G10 waiting for the InfraMedic P0 count.
- **Verdict: defer**, keep open. Reopen trigger: the InfraMedic P0 count shows that one book per scope does not
  work (the number of scopes, or the shared content that must be copied).

## 3. Operator questions

1. **#141:** the reranker policy form: (a), (b) recommended, or (c)? May the agent start `reranker-gpu` now,
   and when may it run the `docker kill` / engine-death / reboot test (D76 deferred it)?
2. **#73:** run the live probe (TLS, a real token), or close #73 without it?
3. **#158:** (a) defer, (b) narrow form, or (c) reject?
4. **#162:** confirm the reject, or change `docs/23` §2 with a new D-record.

**Answers (operator, 2026-11-06, D82):** Q1: first (b), then (a) `restart: unless-stopped` on new evidence: Docker
counts the `on-failure` restarts from the last start by a person, not per crash (moby `restartmanager.go`), and the
first start on this host failed 5 times with `CUDA error: out of memory`. Start `reranker-gpu` now and run the
engine-death and `docker kill` test now, also below the 15 GB floor (no reboot test). Q2: close #73 without the
live probe. Q3: (a) defer. Q4: the reject is confirmed.

## 4. Working rules for the development session

- Work in the worktree `/home/mega/kutuphane-dev` with its own `.venv` (editable install of this tree).
  **Never** check out a branch in `/home/mega/kobra`: the live `kutuphane-core.service` runs that tree.
- One branch per issue from `origin/main`: `fix/ops/reranker-restart`, `docs/guide/host-core-unit`,
  `docs/guide/local-issuer`. PR to `main`; the operator merges.
- Tests: `KUTUPHANE_TEST_DSN` points at the database `kutuphane_test` in `kutuphane-postgres-1`
  (127.0.0.1:55432, owner `kutuphane`, password `KUTUPHANE_DB_PASSWORD` in `/home/mega/kobra/.env`).
  Do not print the password.
- Before each PR: Part B of `kutuphane-vision-gate`.
