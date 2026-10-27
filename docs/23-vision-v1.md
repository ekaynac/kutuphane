# Vision 1.0 — Kütüphane: a governed knowledge catalog and memory layer for agents

**Status:** 1.0 draft, 2026-10-27 (D69, D70). It replaces the positioning in `docs/10` §1. `docs/10` stays as the history of the standard work.
**Basis:**
- the operator's positioning (2026-10-27);
- the scope review (`docs/22`);
- the requests that the operator's own orchestrators filed (#67–#81).

**Language:** ASD-STE100 Simplified Technical English.

## 1. One sentence

**Kütüphane is the place where people and AI agents keep what they know, with a record of who wrote it, who accepted it, and who may use it for what. Agents reach it through MCP, and other tools (RAG platforms, orchestrators) use it as their governed source.**

## 2. What it is, and what it is not

| Kütüphane **is** | Kütüphane **is not** |
|---|---|
| a **catalog** of knowledge items (documents, notes, decisions, rules, skills), each with an identity (digest, version), an issuer, rights, origin, acceptance and validity | a RAG platform or chat UI: Onyx, Dify, Open WebUI and RAGFlow do that, and they connect to us |
| an **agent memory layer**: agents read and propose notes over MCP; people accept them | a code graph: the orchestrator builds code structure on demand, and we only cite into code (#67) |
| **access control and delegation**: RBAC per book, agents acting on behalf of a person, scoped and time-boxed grants, an `activate` grant for agent instructions | a run-state or event store: goals, jobs and costs stay in the orchestrator's log |
| **governed model use**: `ai_input: n` never reaches a model; all model calls are audited (LLMDAP optional, #76) | a place for chat transcripts or scratch notes |
| **easy to adopt**: one container, folders + `kstd.yaml`, a few MCP tools | a competing standard body: kstd is our contract, mapped to OKF / DataHub / DPV |

## 3. The value we offer — five promises

Each promise is a behavior that a user can check. Every new feature must serve one of them.

| # | Promise | What the user sees | Evidence today / gap |
|---|---|---|---|
| P1 | **Knowledge with an owner.** Each item shows who issued it, who accepted it, and whether it is current. | An answer cites "accepted rule, v3, accepted by Ayşe on 2026-10-01", not just a passage. | Standing, rule/evidence and validity exist (ontology v2). Pilot 1 showed it works on radar. |
| P2 | **An agent can never pass as a person.** Origin comes from the write path, not from the writer's claim (D70; `docs/22` §4 R1–R7). | An agent-written note is `model` and `pending` until a person accepts it. | Gap: there is no agent write path yet (#68). |
| P3 | **A model never sees what it may not see.** Rights and personal data are checked before every embedding, rerank and answer, also for agents. | `ai_input: n` content is listed but never sent to a model; an export without a legal basis is refused. | Built and tested. Astra review #12 closed the merged-search gap. |
| P4 | **Memory that does not rot.** Duplicates are merged and contradictions kept; stale citations are flagged; a poisoned note is rolled back with everything derived from it. | An agent gets "stale: the cited code moved", or "retired: derived from a rejected note". | Gaps: #70, #72, #79. |
| P5 | **Cheap and fast for agent loops.** Deterministic, filtered reads with no model call; a model answer only when it is asked for. | A filtered read in milliseconds; stable output that keeps prompt caches valid. | Gap: #71 (today `search_library` is the only read; answers take ~63 s). |

## 4. Who uses it

1. **Coding orchestrators** (ADC, nöbetçi-mcp): shared memory for decisions, findings, lessons, conventions and skills (#67). **This is the first real customer**, and it sets the first roadmap.
2. **Organizations with a RAG platform:** Kütüphane is the governed source. The platform asks through MCP or HTTP, and gets only the passages the caller and the model may use, with the rights attached.
3. **Curators (people):** they accept or reject what agents propose, through a fast queue (#77).

## 5. Import, export and integration

kstd is our internal contract. To the outside, Kütüphane maps it to what others use:

| Direction | Target | What moves |
|---|---|---|
| import | folders + `kstd.yaml`; OKF bundles; an orchestrator's local memory (#75) | items with origin, dates, citations, rights |
| export | OKF bundles; kstd signed packages; JSONL decision records (#74) | items + rights + origin + acceptance |
| sync (later) | DataHub / OpenMetadata | catalog entries and governance properties |
| serve | MCP (tools, Skills #80, `_meta` handling labels); HTTP | governed results |

## 6. The standard (kstd)

- **kstd stays the written contract** for the rules that Kütüphane enforces.
- **Its size:** the operator is not sure about the minimal core (`docs/22` §3); it stays open. Until a decision, no new statement kinds or categories are added. A field is added only when a customer request (an issue) needs a behavior from it (D53).
- **Contributions to standards groups:** still on hold (D61).

## 7. Roadmap from the customer requests

| Phase | Issues | Promise |
|---|---|---|
| **R1: agent memory, first slice** | #68 the agent write path `propose_note` (with D70 origin), #69 the journal profile, #71 the structured fast query + `neighbours`, #72 merging equal concerns, #73 MCP 2026-07-28 + headless auth, #70 code citations + a verifier | P2, P4, P5 |
| **R2: curation at volume** | #77 the curator queue, #79 rollback along `derived_from`, #74 outcome feedback + decision export | P1, P4 |
| **R3: adoption** | #76 the light install, #75 bulk import + private books, #80 MCP Skills + handling labels | P3, P5 |
| **Decision needed** | #78 delegated curate for narrow note classes | P1 |
| **Low priority** | #81 the tree-sitter code profile | — |

Labelling v5 continues in parallel: it measures the judgments that the curator queue (#77) and a future delegated curate (#78) need.

## 8. How we know that it works

- The orchestrators use Kütüphane for their real goals. We measure:
  - the curator's seconds per accepted note;
  - the share of notes still `pending` after 7 days;
  - the stale-citation rate;
  - the fast-read latency.
- **Zero incidents** of the following kinds:
  - an agent recorded as a person;
  - `ai_input: n` text in a model call;
  - a rejected or retired note served as current.
