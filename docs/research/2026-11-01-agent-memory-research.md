# Agent memory in open source (late 2026), and where Kütüphane is different

**Status:** research note, 2026-11-01. Read-only. Sources checked today; links at the end. `[INFERENCE]` = no direct evidence. "not verified" = not checked at the source.
**Scope:** deeper than `docs/research/2026-10-27-oss-km-survey.md` on agent memory only. §2.4 lists where that survey is stale.
**Language:** ASD-STE100.

## 1. The short answer

1. Two fields share one name. **Chat memory** (mem0, Zep, MemoryOS, MIRIX) extracts facts from conversations with an LLM and searches them. **Coding-agent memory** (Copilot, Claude Code, Letta, Codex, deepagents) stores small notes or files that the agent writes through a tool call, reads into the prompt and checks against the code. Kütüphane is in the second field.
2. The second field converged on three rules in 2026: (a) **human-written instructions and agent-written learnings are separate**; (b) **a memory is evidence, not an instruction** (Zep's security page; Claude Code v2.1.50 removed memories from the system prompt after MemoryTrap); (c) **verify at read time, do not curate offline** (Copilot: +7 points PR merge rate in an A/B).
3. Kütüphane has (a) and (b) as database guarantees (D70 origin, `activate`, Standing by a person only). The field has them as prompts and settings.
4. Kütüphane does (c) more strictly than Copilot (server-side git check, byte exact), but adds a step nobody else has: **a person must accept a note before an agent gets it as current**. That step is unproven and scales worst.
5. Our two biggest gaps are not extraction or graphs. They are **no expiry** (nothing in a journal ages out) and **no export of notes** (`export` refuses a journal; the field moved memory into git).

## 2. How agent memory works today

### 2.1 Memory systems

| System | Unit | Who writes | Read | Update / forget | Provenance, trust | Sharing |
|---|---|---|---|---|---|---|
| **mem0 OSS v3** | extracted fact | one LLM pass, **ADD only** | vector + BM25 + entity, top 20 | none in OSS; #4956 open since April: contradictions accumulate, ranking has no time term | ids declared by the caller | per id |
| **Zep / Graphiti** | fact on an edge + source episode | LLM extraction; invalidates old edges | graph search; context block | `created_at`, `valid_at`, `invalid_at`, `expired_at`; "fields do not establish that the fact is true" | episode metadata (`source`, `review_state`) projected onto facts; **"customer-writable; do not accept a security label from a model"**; access policies per key | user graph + shared graphs |
| **Letta** | Markdown file in **MemFS** (a git repo per agent) | the agent with file tools; `/remember` | root files in the system prompt each turn; `MEMORY.md` index; no vector index by default | agent edits; **dreaming** consolidates in background, "does not ask you for approval"; git history | git commits | shared repos (cloud) |
| **deepagents** (LangGraph) | file in a namespace | agent `edit_file`; optional consolidation agent on cron | prompt or on demand | last-write-wins | org memory **read-only** "to prevent prompt injection via shared state"; human interrupt for shared writes | user / agent / org |
| **Cognee** | graph | pipeline | graph + vector | 1–5 feedback → `improve()` reweights the graph | tenants, roles, dataset rights | yes |
| **Basic Memory** | Markdown note | person and AI, same files | MCP | file edits | none per entry | local-first |
| **MCP memory server** | entity, relation, observation | the model | `search_nodes`, whole graph | delete tools | no author, no time in the README | one JSONL file, lock file |
| **A-MEM** | Zettelkasten note | LLM writes tags, links; "evolution" rewrites old notes | vector | update, delete | none | — |
| **MemoryOS** | dialogue page → segment → profile | pipeline | heat score moves pages short → mid → long term | heat decay | none | per user |
| **MIRIX 0.1.6** | 6 memory types | 8 agents | Postgres BM25 + vector | retention and decay policies | none visible | — |

Evaluation claims: mem0 vendor numbers LoCoMo 91.6, LongMemEval 93.4; A-MEM and MemoryOS paper claims only; the others publish none.

### 2.2 Coding-agent memory

| Tool | Human part | Agent part | Trust rules |
|---|---|---|---|
| **Claude Code** | `CLAUDE.md`, path-scoped `.claude/rules/`, `AGENTS.md`; "context, not enforced configuration" | **auto memory**: 4 note types (`user`, `feedback`, `project`, `reference`); `MEMORY.md` first 200 lines / 25 KB loaded each session; per repo, machine-local; skips what the code shows | v2.1.50 removed memories from the system prompt after Cisco's **MemoryTrap** (an npm postinstall rewrote every `MEMORY.md` and the global hooks). `/doctor prompt-audit` finds stale and conflicting instructions. |
| **Copilot Memory** | custom instructions | `store_memory` tool; **repository facts** (write access to create, read access to use) and **user preferences** (owned by the billing entity); every fact has **citations** into code; the agent checks them before use, "a judgment, not a guarantee"; hidden votes; **expiry 90 days** (7–180), reset only by an upvote; secrets and model-control tokens rejected; subagents read only | A/B: PR merge 90 % vs 83 %, review approval 77 % vs 75 %, p < 0.00001. Seeded adversarial memories "self-healed" through citation checks. |
| **Cursor** | Rules, Team Rules, `AGENTS.md`, Skills | **Memories removed in 2.1** (2025-11-21), no changelog entry (forum, staff) | "memory you do not own disappears" |
| **Codex** | `AGENTS.md` chain, `AGENTS.override.md`, 32 KiB cap | none | — |
| **OpenHands** | — | **condensers**: `LLMSummarizingCondenser` replaces old events with a summary; up to 2× lower cost per turn | run-state compression, not memory |
| **Skills** | `SKILL.md` folders (Anthropic, Cursor 2.4, deepagents) | MCP **SEP-2640** (Final): skills as `skill://` resources; `skills/list` carries sha256 digest + size per file; "digests are unsigned … MUST NOT treat a digest match as a security boundary"; nested skills need fresh consent | Kütüphane serves this (#80, D71 scan). |

### 2.3 Research, 2026

- **Poisoning.** MINJA (NeurIPS 2025): > 95 % injection, 70 % attack success, query-only, idealized. A 2026 EHR study: pre-existing legitimate memories cut attack success; trust thresholds are hard to calibrate. **SAFE-Mem** (Oct 2026): three labels per claim (`kind`, `authority`, `scope`), filtered at retrieval; ≥ 77 % lower attack success than defenses that keep utility. OWASP **ASI06** names memory and context poisoning; its lead uses MemoryTrap as the example.
- **Evaluation.** "Is complex agentic memory always needed?" (Oct 2026): naive RAG over **raw history** ranks first in 6 of 7 settings against agentic memory systems; transformed memory loses evidence. **LongMemEval-V2** (451 questions, web-agent experience): a file-based coding-agent memory scores 74.9 % at 108 s per query; plain RAG 51 % at 0.2 s; the leaderboard scores the accuracy–latency frontier.
- **Consolidation.** deepagents and Letta run it as a background agent. **RecMem**: consolidate only when similar interactions recur; up to 87 % fewer tokens (the idea behind our `recurrence` and `guard_due`). "Epistemics of agent memory": ConsolidationBench; "governed consolidation" = poison-resistance, reversibility, auditability; its quality score did not predict transfer.
- **Temporal.** Zep's four timestamps are the reference. mem0's #4956 thread converges on write-time supersession (`valid_from/valid_to`), not read-time recency; one commenter measured recency demotion at −0.012 nDCG on named lookups.
- **Provenance.** Zep: episode → fact projection, caller-written labels. Copilot: citations, checked by the model. SAFE-Mem: authority label per claim. None derives the label from the authenticated write path.

### 2.4 Updates to the 2026-10-27 survey

| Survey said | Now |
|---|---|
| mem0 keeps ADD/UPDATE/DELETE events; graph memory in OSS | v3 OSS is ADD-only; graph memory is Platform only |
| Letta: memory blocks with `read_only` | MemFS git files, dreaming, shared repos |
| Graphiti: bi-temporal edges | Zep v4 adds metadata projection, access policies, a memory-security page |
| Claude Code, Cursor: not covered | auto memory exists, removed from the system prompt; Cursor Memories removed |

## 3. Map of design choices

K = Kütüphane.

| Dimension | Choices in the field | K |
|---|---|---|
| Unit | extracted fact · graph edge · file · note · summary · skill | content-addressed note, kind, scope, citations |
| Writer | LLM pipeline · agent tool call · person | agent tool call (`propose_note`); person via CLI import |
| Accepted before use | never · "approve to store" dialog (Copilot app) | **yes: Standing by a person; pending is never current** |
| Read | prompt at start · hybrid search · graph · file read | SQL filters + FTS, 40 ms; no vector on reads |
| Staleness | none (mem0) · invalidation (Zep) · expiry + votes (Copilot) · agent edits (Letta) | immutable note, `supersedes`, Standing events, verifier, `as_of`; **no expiry** |
| Provenance source | caller-declared · citations checked by the model | **write path, DB check**; citations checked by the server |
| Instruction vs evidence | file type · read-only namespace | Role `rule`/`evidence`; `activate`; skill scan |
| Sharing | per user · per repo · org read-only | per book grants; delegation; rights follow derivation |
| Portability | git (Letta, Archcore) · import tool (Copilot CLI) · none (Cursor) | import JSONL yes; **export of a journal: refused** |

## 4. What the field does well that we lack

| Field feature | Fits D69 / D53? | Verdict |
|---|---|---|
| LLM extraction from conversations | No. Our unit is a cited note. D77 calls copied knowledge duplication. Raw-RAG shows transformed memory loses evidence. | **Do not copy.** |
| Agent decides what to store, by tool call | Yes. We have it: `propose_note`. | The gap is acceptance, not capture (§6). |
| Consolidation agent (dreaming) | No. It writes `model` text with no person; our A/B shows +50 % tokens, no gain. | **Do not copy.** |
| **Expiry with reinforcement** (Copilot) | Yes. P4. D53: a note leaves a set. | **Adapt** (R1). |
| Temporal knowledge graph | Partly. We have two timelines (`written_at`/`observed_commit`; Standing `seq`, `as_of`). We lack entity edges. | **Do not build.** Our scope is code paths. |
| Procedural memory as skills | Yes. Built: Skills over MCP, `activate`, SkillSpector. No consumer. | Keep; no new work. |
| Working / episodic split (condensers) | No. Run state stays in the orchestrator. | Keep the line. |
| Memory scoring (votes) | Partly. `record_outcome` counts change nothing. Hidden votes break deterministic output (P5). | **Adapt** as a filter (R2). |
| Memory in git | Yes for portability; no for the store (constraints, RLS, audit). | Export in the import shape (R3). |

## 5. What only a governed knowledge-artifact system can do

| Capability | Real need or theory? | Evidence and verdict |
|---|---|---|
| **Origin an agent cannot forge** (D70) | Real. MemoryTrap worked because models "assume [memory files] were written by the user". Zep tells customers not to trust model labels; we enforce it in a `write_record` CHECK. | Unique. Keep; add nothing. |
| **Accepted vs proposed** | Real for `rule` notes: every tool keeps rules human-written. **Theory at volume for `evidence`**: the field serves evidence with no person and verifies at read. 9 notes waited for the operator (D77). | Keep for rules. Rethink for evidence (R1). |
| **Rights follow derivation** | Real for InfraMedic (`restricted`, `ai_input`, `train`). No memory system has it for model use. | Keep. Built. |
| **Rollback along `derived_from`** | Real in design, untested by an incident. Zep traces facts to episodes but does not list who read them; our report lists deliveries, answers, exports. | Keep. Do not extend. |
| **Citation verification** | Real. Copilot's A/B is the field's best proof that cited memory pays. Ours is server-side, byte exact, and removes the note from `current` on `stale`. Cost: a bare mirror per repo. | Keep. This is the P4 engine. |
| **One artifact for people, agents, apps** | Real: InfraMedic shows Standing in its screens; nöbetçi reads notes; the operator curates on the phone. No memory product serves three readers with one rights model. | **This is the positioning** (§7). |
| **Signed packages between installations** | Real for books. **Theory for notes**: a journal has no export. | Fix the export (R3). |
| **Memory as a reviewed, versioned asset** | Real; the field agrees (git everywhere). An asset that cannot leave the DB is a cache with a longer life. | R3. |

## 6. Weak points, honestly

| Risk | Evidence | Weight |
|---|---|---|
| **Curation bottleneck.** One curator; every note waits; the field needs zero. If pending stays pending, agents stop proposing. | 9 pending (D77); D73 decider built then frozen; the "pending after 7 days" metric has no target | high |
| **No expiry.** An approved `finding` is current forever unless a citation goes stale or a curator acts. Copilot drops a memory after 90 unused days. | design §8.2 | high |
| **No export of notes.** Lock-in; backup only by DB dump. Cursor's lesson: "memory you do not own disappears". | `packages.py` L61; only decisions export | high |
| **Write friction.** `propose_note` 1.3 s vs reads 40 ms; key, kind, scope, full commit, registered mirror. Claude auto memory needs nothing. | #67 comment; guide §2 | medium |
| **Recall.** Filters + FTS; no semantic recall; the agent must know `repo/path/kind`. Path scope is strong for code (Claude rules, Copilot citations), weak for "seen this before?". | `notesquery.py` L3; vectors only for duplicates | medium |
| **No measured benefit.** One A/B: 8/9 vs 9/9, +50 % tokens. Copilot's bar: a lift at p < 0.00001. | #121 T3 | medium |
| **Duplicates left to the agent.** Candidates shown, never merged. | design §7 | low |

## 7. A sharper vision

**Positioning (proposed):**

> Kütüphane is the governed catalog that people, agents and applications read from the same copy. Every item, a document or an agent's note, carries who wrote it (from the write path, never from a claim), who accepted it, where it applies and what a model may do with it. Agent memory products remember; Kütüphane keeps a record that can be checked, rolled back and exported.

**Principles that separate us from "agent memory":**

1. **The write path is the provenance.** No label from a model, a header or a manifest outranks the authenticated path.
2. **Rules are accepted; evidence is verified.** A rule becomes current only by a person. Evidence becomes current by verification and use, and leaves by expiry.
3. **Memory is data, never instruction.** Notes reach a model as tool results. Instructions need `activate` and a scan.
4. **Nothing is rewritten; everything can be withdrawn.** Notes are immutable; supersession, retirement and rollback are events with a cause.
5. **An asset leaves with its rights.** Import and export carry origin, Standing, rights and derivation. A journal is not an exception.

**Sentence-level changes to `docs/23`** (within A/B/C and the freeze list):

- §1: after "who may use it for what" add "**and what it was checked against**".
- §2 "is not": add "**an extraction pipeline**: Kütüphane never writes a note from a conversation; an agent proposes, a person or a verifier decides."
- §3 P4: replace "stale citations are flagged" with "a note with a stale citation is not current; **evidence that nobody uses expires**".
- §3 P5 evidence: "Built: `query_notes` 40 ms. Open: no semantic recall on notes, by design until a consumer measures a miss."
- §4 item 1: add "Copilot Memory's A/B shows cited, verified memories lift PR merge rate; our A/B (#121) does not yet. **The next A/B gates further memory work.**"
- §5 export row: add "**journal records (JSONL, the import shape)**".
- §8: add "a journal round-trips through export and import with no loss" and "the 7-day pending share has a target" (`[INFERENCE]` 20 % is a proposal).

## 8. Recommendations, ranked by value per effort

| # | Recommendation | Area | Effort | Why |
|---|---|---|---|---|
| **R1** | **Expiry for evidence.** A `pending` evidence note with no outcome and no curator event for T days (default 90) gets a system event `rejected`, reason `expired`; an `approved` evidence note with no outcome for T days gets `retired`, reason `expired`. `record_outcome: passed` resets the clock. Rules never expire. One CLI command on cron; one CHECK change (`set_by = system` must allow `rejected`); no new table. | B | small | Copilot's rule in our event model. Bounds the backlog with no model decider (D73 stays frozen). "System only tightens" holds. |
| **R2** | **Outcomes as a filter.** `query_notes` gets `min_passed: n` and `exclude_failed: true`. Deterministic; caches stay valid; no hidden votes. | B | small | Makes `record_outcome` change a behavior (D53). |
| **R3** | **`kutuphane journal export <book> --out FILE`** in the `note import` JSONL shape, plus Standing events, origin, writers, link refs; refused for `restricted`, as packages are. Round-trip test: export → import gives the same note ids. | A | small–medium | Closes lock-in; gives backup and a git path. Reuses `noteimport` rules. |
| **R4** | **"Memory is data" section** in `docs/guide/agent-memory.md`: notes go into tool results, never system prompts; instructions need `activate`; cite Zep's placement table and MemoryTrap. No code. | C | tiny | The field learned this in 2026; we already enforce the server side. |
| **R5** | **Rerun the A/B before any new memory feature.** Gate: acceptance not lower, input tokens not higher (`2026-10-31` §8 B). If it fails twice, cut `propose_note` to `kind`, `text`, `scope`, `citations` and let the server fill the rest. | B | small | Copilot proved value; we have a 1-of-9 loss. Measure first. |

**Do not copy:** LLM extraction from chat; consolidation agents; entity graphs; hidden votes; memory in the system prompt; caller-declared trust labels; a model decider for Standing; recency re-ranking.

**Do less here, more there:** less curator web and decider; more expiry, export and one honest A/B.

**Not checked:** star counts and dates of every system; Cognee's and MIRIX's rights at code level; whether `open` notes carry citation statuses in `query_notes` output (`[INFERENCE]` yes: `_verify` runs for placed notes).

## Links

- mem0 v3 migration: <https://docs.mem0.ai/migration/oss-v2-to-v3> · #4956: <https://github.com/mem0ai/mem0/issues/4956>
- Zep facts: <https://help.getzep.com/v4/facts> · security: <https://help.getzep.com/v4/memory-security>
- Letta MemFS: <https://docs.letta.com/concepts/memfs/> · dreaming: <https://docs.letta.com/configuration/memory>
- deepagents memory: <https://docs.langchain.com/oss/python/deepagents/memory>
- Cognee: <https://docs.cognee.ai/changelog> · <https://docs.cognee.ai/guides/feedback-system>
- Basic Memory v0.23.0: <https://github.com/basicmachines-co/basic-memory/releases/tag/v0.23.0>
- MCP memory server: <https://github.com/modelcontextprotocol/servers/blob/main/src/memory/README.md>
- A-MEM: <https://github.com/agiresearch/A-mem> · MemoryOS: <https://github.com/BAI-LAB/MemoryOS> · MIRIX: <https://docs.mirix.io/>
- Claude Code memory: <https://code.claude.com/docs/en/memory>
- Copilot Memory: <https://docs.github.com/en/copilot/concepts/agents/copilot-memory> · A/B blog: <https://github.blog/ai-and-ml/github-copilot/building-an-agentic-memory-system-for-github-copilot>
- Cursor Memories removed: <https://forum.cursor.com/t/are-my-memories-gone/144057> · secondary: <https://archcore.ai/blog/cursor-memories-removed>
- Codex AGENTS.md: <https://developers.openai.com/codex/guides/agents-md/>
- OpenHands condenser: <https://docs.openhands.dev/sdk/guides/context-condenser>
- SEP-2640: <https://modelcontextprotocol.io/seps/2640-skills-extension>
- MINJA: <https://arxiv.org/abs/2503.03704> · EHR study: <https://arxiv.org/abs/2601.05504> · SAFE-Mem: <https://arxiv.org/abs/2610.22959>
- MemoryTrap: <https://blogs.cisco.com/ai/identifying-and-remediating-a-persistent-memory-compromise-in-claude-code> · OWASP ASI06: <https://genai.owasp.org/2026/05/13/memory-is-a-feature-it-is-also-an-attack-surface>
- Raw-RAG: <https://arxiv.org/abs/2610.30755> · LongMemEval-V2: <https://xiaowu0162.github.io/longmemeval-v2> · MemoryAgentBench: <https://github.com/HUST-AI-HYZ/MemoryAgentBench>
- RecMem: <https://arxiv.org/abs/2605.16045> · Epistemics: <https://arxiv.org/abs/2609.33013>
