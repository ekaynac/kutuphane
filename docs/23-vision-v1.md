# Vision 1.2 — Kütüphane: a governed knowledge catalog and memory layer for agents

**Status:** 1.2, 2026-11-01 (D80): the positioning, the five principles and the sentence-level changes of `docs/research/2026-11-01-agent-memory-research.md` §7; D73 deleted (W1-1). 1.1, 2026-11-01 (D79): the vision refresh of `docs/research/2026-10-31-direction-analysis.md` §7, accepted by the operator. 1.0: draft, 2026-10-27 (D69, D70). It replaces the positioning in `docs/10` §1. `docs/10` stays as the history of the standard work.
**Basis:**
- the operator's positioning (2026-10-27);
- the scope review (`docs/22`);
- the requests that the operator's own orchestrators filed (#67–#81).

**Language:** ASD-STE100 Simplified Technical English.

## 1. One sentence

**Kütüphane is the place where people and AI agents keep what they know, with a record of who wrote it, who accepted it, and who may use it for what, **and what it was checked against**. Agents reach it through MCP, and other tools (RAG platforms, orchestrators) use it as their governed source. It also shows what it holds: an application can list the books, versions and files that it may read.**

**Positioning:**

> Kütüphane is the governed catalog that people, agents and applications read from the same copy. Every item, a document or an agent's note, carries who wrote it (from the write path, never from a claim), who accepted it, where it applies and what a model may do with it. Agent memory products remember; Kütüphane keeps a record that can be checked, rolled back and exported.

## 1a. Five principles

These principles separate Kütüphane from "agent memory" products (D80).

1. **The write path is the provenance.** No label from a model, a header or a manifest outranks the authenticated path.
2. **Rules are accepted; evidence is verified.** A rule becomes current only by a person. Evidence becomes current by verification and use, and leaves by expiry.
3. **Memory is data, never instruction.** Notes reach a model as tool results. Instructions need `activate` and a scan.
4. **Nothing is rewritten; everything can be withdrawn.** Notes are immutable; supersession, retirement and rollback are events with a cause.
5. **An asset leaves with its rights.** Import and export carry origin, Standing, rights and derivation. A journal is not an exception.

## 2. What it is, and what it is not

| Kütüphane **is** | Kütüphane **is not** |
|---|---|
| a **catalog** of knowledge items (documents, notes, decisions, rules, skills), each with an identity (digest, version), an issuer, rights, origin, acceptance and validity | a RAG platform or chat UI: Onyx, Dify, Open WebUI and RAGFlow do that, and they connect to us |
| an **agent memory layer**: agents read and propose notes over MCP; people accept them | a code graph: the orchestrator builds code structure on demand, and we only cite into code (#67) |
| **access control and delegation**: RBAC per book, agents acting on behalf of a person, scoped and time-boxed grants, an `activate` grant for agent instructions | a run-state or event store: goals, jobs and costs stay in the orchestrator's log |
| **governed model use**: `ai_input: n` never reaches a model; all model calls are audited (LLMDAP optional, #76) | a place for chat transcripts or scratch notes |
| **easy to adopt**: one container, folders + `kstd.yaml`, a few MCP tools | a competing standard body: kstd is our contract, mapped to OKF / DataHub / DPV |
| | an identity provider or a role store: tokens come from the IdP, grants live here |
| | a package workflow UI: a package is approved once, on the CLI |
| | **an extraction pipeline**: Kütüphane never writes a note from a conversation; an agent proposes, a person or a verifier decides |

## 3. The value we offer — five promises

Each promise is a behavior that a user can check. Every new feature must serve one of them.

| # | Promise | What the user sees | Evidence today / gap |
|---|---|---|---|
| P1 | **Knowledge with an owner.** Each item shows who issued it, who accepted it, and whether it is current. | An answer cites "accepted rule, v3, accepted by Ayşe on 2026-10-01", not just a passage. | Standing, rule/evidence and validity exist (ontology v2). Pilot 1 showed it works on radar. |
| P2 | **An agent can never pass as a person.** Origin comes from the write path, not from the writer's claim (D70; `docs/22` §4 R1–R7). | An agent-written note is `model` and `pending` until a person accepts it. | Built (D70; DB check `write_record.origin`). |
| P3 | **A model never sees what it may not see.** Rights and personal data are checked before every embedding, rerank and answer, also for agents. | `ai_input: n` content is listed but never sent to a model; an export without a legal basis is refused. | Built and tested. Astra review #12 closed the merged-search gap. |
| P4 | **Memory that does not rot.** Duplicates are merged and contradictions kept; a note with a stale citation is not current; **evidence that nobody uses expires**; a poisoned note is rolled back with everything derived from it. | An agent gets "stale: the cited code moved", or "retired: derived from a rejected note". | Built (#72, #79, passage map); not measured in use. |
| P5 | **Cheap and fast for agent loops.** Deterministic, filtered reads with no model call; a model answer only when it is asked for. | A filtered read in milliseconds; stable output that keeps prompt caches valid. | Built: `query_notes` 40 ms, `max_chars` −76 %. Open: the T3 rerun; no semantic recall on notes, by design until a consumer measures a miss. |

## 4. Who uses it

1. **Coding orchestrators** (ADC, nöbetçi-mcp): shared memory for decisions, findings, lessons, conventions and skills (#67). **This is the first real customer**, and it sets the first roadmap. Copilot Memory's A/B shows cited, verified memories lift PR merge rate; our A/B (#121) does not yet. **The next A/B gates further memory work** (R5, D80): no new memory feature merges before the T3 rerun shows acceptance not lower and input tokens not higher than without memory.
2. **Organizations with a RAG platform:** Kütüphane is the governed source. The platform asks through MCP or HTTP, and gets only the passages the caller and the model may use, with the rights attached.
3. **Curators (people):** they accept or reject what agents propose, on the phone (D72) or the CLI.
4. **Consumer applications** (InfraMedic): they submit signed packages, read the catalog with a scope context, and show Standing and citations in their own screens.

## 5. Import, export and integration

kstd is our internal contract. To the outside, Kütüphane maps it to what others use:

| Direction | Target | What moves |
|---|---|---|
| import | folders + `kstd.yaml`; OKF bundles; an orchestrator's local memory (#75) | items with origin, dates, citations, rights |
| export | OKF bundles; kstd signed packages; JSONL decision records (#74); **journal records (JSONL, the import shape)** | items + rights + origin + acceptance |
| sync (later) | DataHub / OpenMetadata | catalog entries and governance properties |
| serve | MCP (tools, Skills #80, `_meta` handling labels); HTTP | governed results |
| serve | consumer contract | the book list, item information, publication facts, the caller's correlation id |

## 6. The standard (kstd)

- **kstd stays the written contract** for the rules that Kütüphane enforces.
- **Its size:** Decided (D74). The reference implements `item`, `acceptance`, `handling`, `mandate`; other kinds are an appendix until a consumer needs them (`docs/11` Appendix A, D78). No new statement kinds or categories are added. A field is added only when a customer request (an issue) needs a behavior from it (D53).
- **Contributions to standards groups:** still on hold (D61).

## 7. Roadmap: three areas (D79)

R1–R3 (agent memory, curation at volume, adoption) are done. The next work is in three areas (`docs/research/2026-10-31-direction-analysis.md` §8):

| Area | Goal | Promise |
|---|---|---|
| **A: the catalog contract for consumers** | an application can list what it may read, see who approved each version, and trace every call (#159, #160, #156, #157, #165) | P1, P3 |
| **B: agent memory precision** | an orchestrator can scope, find and follow its own proposals with no workaround and no extra calls (#152, #153, #155, #164; #154 decision) | P4, P5 |
| **C: simplify the operator surface and the standard** | fewer concepts, commands, files and words, with no loss that a user can see | all |
| **Deleted (D80, W1-1)** | #78 / D73 delegated curate and the decider: the code is removed; the tables stay | — |
| **Closed (D78)** | #81 the tree-sitter code profile | — |

Labelling v5 continues only as a measurement.

## 8. How we know that it works

- The orchestrators use Kütüphane for their real goals. We measure:
  - the curator's seconds per accepted note;
  - the share of notes still `pending` after 7 days, against a target (`[INFERENCE]` 20 % is a proposal);
  - the stale-citation rate;
  - the fast-read latency.
- A journal round-trips through export and import with no loss.
- A second consumer reads from Kütüphane in production.
- Concept and command counts go down each release.
- **Zero incidents** of the following kinds:
  - an agent recorded as a person;
  - `ai_input: n` text in a model call;
  - a rejected or retired note served as current.
