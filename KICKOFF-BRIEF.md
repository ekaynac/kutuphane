# Kobra — kickoff brief for the new product session

Written 2026-10-07 by the nöbetçi/InfraMedic supervisor session, at the operator's request. It hands you the operator's
intent and the context you need. **You** own this product's direction from here on, together with the operator.
You may move this file into the repo (for example to `docs/00-kickoff-brief.md`) or keep it as the first commit.

## 1. The operator's intent (their words, translated faithfully)

- Start developing **Kobra as a completely separate product**. Product direction and decisions are made in **this
  session**, together with the operator. This session **initialises git** for the new repo (here: `/home/mega/kobra`).
- **InfraMedic keeps being developed separately** from the new Kobra repo. For now, **nothing changes** in InfraMedic or
  in the Kobra that lives inside InfraMedic.
- The new Kobra is, at its core, a platform for **controlling RAG and knowledge systems**: **like NotebookLM**. Evaluate
  which features should make Kobra **different from NotebookLM**.
- Kobra is planned as a platform strengthened by a **solid library system** and by **LLMDAP**.
- Think and brainstorm about whether Kobra can be planned **harness-agnostic**.
- If needed, **the code may be written from scratch**: reuse from InfraMedic is allowed, but it is not required.
- In particular, plan **what makes this platform different from any OpenWebUI- or LibreChat-like application**.
- The central question: **once it is independent of InfraMedic, what makes Kobra meaningful?**

The first job of this session is **brainstorming with the operator**, not code. Ask questions, offer options with a
recommendation, and record the decisions.

## 2. Ground rules for this session

- **Read-only** everywhere outside `/home/mega/kobra`:
  - `/home/mega/inframedic` is the product repo, developed by an unattended cycle;
  - `/home/mega/nobetci`, `/home/mega/nobetci-dev` and `/srv/nobetci` are the dev-cycle framework;
  - the edge host `192.168.20.36` is InfraMedic's live box.
  Do not edit, commit, push, deploy or restart anything there. Read as much as you like.
- `/home/mega/AGENTS.md` and the nöbetçi work queue are **not** for this session. They coordinate InfraMedic's dev cycle.
  Ignore their instructions and do not touch that queue.
- No secrets in the repo; never print credential files.
- This machine is a DGX Spark: one GPU, unified memory, shared with a vLLM server (`:8000`, Qwen3.8-27B), an Ollama
  embedder (`nb-embedder`, bge-m3) and InfraMedic's dev cycle. Do not start heavy local models or long GPU jobs without
  asking the operator.
- Agree on any GitHub remote with the operator first. Creating or pushing to a remote is an outward-facing act.
- The operator writes in Turkish, often from a phone. Keep answers short and scannable, and batch your questions.

## 3. What Kobra is today, inside InfraMedic (read these; do not change them)

Kobra is InfraMedic's **technician-facing agent: "the face of the system"**. In an ask session, a model investigates
devices through a confined sandbox toolkit and searches the knowledge sources.

Code, all in `/home/mega/inframedic`:
- `inframedic/sandbox/` holds Kobra's sessions, the guard, sources, private_mask and redaction.
- `inframedic/sandbox/toolkit.py` has the `search_sources` / `list_sources` vocabulary.
- `inframedic/kobra_contract.py` is the internal boundary that was approved on 2026-09-24 (option **B**: an internal
  boundary now, with the physical split to be decided later). It provides read ports and a single `AuthorityPort`. An
  import-rule test, `tests/test_kobra_contract.py`, enforces it.
- `inframedic/knowledge/` is the knowledge center (catalog, broker, corpus generations).
- `inframedic/llmdapclient/` is the LLMDAP client (RAG, gateway calls, composition roots).

Design and doctrine, in `inframedic/docs/notes/`:
- `2026-08-24-kobra-sandbox-design.md`: Kobra's product claim, "a mid-size on-prem model".
- `2026-08-27-saga-and-kobra-doctrine.md`: Kobra versus the Saga. Authority stays in InfraMedic: write gate, quorum,
  credential leases, and a device lock so that Saga and Kobra never write to the same device at once.
- `2026-08-28-knowledge-center-doctrine.md`, `2026-08-12-canonical-standards-and-knowledge-library.md`,
  `2026-08-13-knowledge-layer-backlog.md`: the library, catalog, canon and corpus ideas.
- `2026-08-28-llmdap-mcp-doctrine.md`: LLMDAP and MCP. Key line: "MCP is vocabulary, not a product mode."
- `2026-08-19-llmdap-ops.md`: how the LLMDAP gateway runs.

Family brainstorm and decisions: `/home/mega/nobetci-dev/docs/2026-09-24-inframedic-family-brainstorm.md`, §4 and §5b.
- In 2026-09-24's options, a separate repo with a separate cycle was option A; it was rejected *then* because it would
  have stopped InfraMedic's plan.
- The operator is now choosing a separate product deliberately. InfraMedic's in-repo Kobra stays as it is.
- The family idea still stands: InfraMedic is the producer, Kobra serves the technician or knowledge worker, and MCP
  handles distribution as a separate repo. The default export carries only abstract layers with no fleet or company
  data; anything more is opt-in.

## 4. LLMDAP, in one paragraph (verify against the sources)

LLMDAP is a **governed LLM/data gateway**. InfraMedic runs it as `llmdap-gateway.service` (gateway 0.8.0, Docker,
loopback `127.0.0.1:8790` on the edge).

It provides:
- **subject-literal policy grants**, from a managed policy file;
- **routes** to model providers;
- **RAG collections** and memory/evidence;
- a **queryable signed audit**;
- **composition roots**: every call must sit under a governed correlation root, which writes an audit row, or it is
  refused before egress;
- **per-service subjects**.

InfraMedic generates and applies its gateway policy through a human-approved path ("D-021"); the current corpus
generation is "gen-3". The LLMDAP upstream source is **not** checked out on this machine. Learn it from InfraMedic's
client code and the notes above, and ask the operator where the upstream lives if you need it.

## 5. Questions to open the brainstorm with (a starting set, not a script)

1. **Positioning:** who is Kobra for once it is outside InfraMedic? IT/infra technicians, any knowledge team, regulated
   or air-gapped organisations?
2. **Versus NotebookLM:**
   - what does Kobra keep (sources-grounded notebooks, citations, audio/briefs);
   - what does it add (on-prem/sovereign, governed egress, audited answers, a versioned canonical library,
     corpus generations with cutover/retire, evidence and redaction classes, multi-tenant policy);
   - what does it drop?
3. **Versus OpenWebUI / LibreChat:** those are chat front-ends over model providers. Kobra's possible differentiators:
   - the **library** as the primary object, not the chat;
   - **governance** through LLMDAP: policy, audit, egress classes;
   - **provenance** on every answer;
   - knowledge **lifecycle**: ingest, review, canon, supersede, retire;
   - **evaluation** of retrieval quality.
4. **Library system:**
   - what is a source, a collection, a canon entry, a version or a generation;
   - who approves what;
   - how sensitivity is represented (`restricted` / `normal`);
   - import and export formats.
5. **Harness-agnostic:**
   - Can Kobra's agent loop run on any harness (Claude Code, OpenAI Agents, LangGraph, a plain tool loop) and any model
     route through LLMDAP?
   - Should it expose MCP?
   - What is the minimal contract?
6. **LLMDAP relationship:** is LLMDAP a hard dependency, the default backend or one of several backends? And what does
   that mean for a solo or self-hosted install?
7. **Reuse vs rewrite:** what is worth lifting from InfraMedic (redaction, broker, catalog, cassettes, sandbox toolkit),
   and what should start clean?
8. **Relationship to InfraMedic later:**
   - Does InfraMedic one day consume Kobra as a library or service, or do they stay siblings that exchange export
     bundles over MCP?
   - Who owns the shared contract?
9. **First milestone:** the smallest end-to-end demo that proves "Kobra is meaningful on its own".

## 6. Suggested first steps

1. `git init` in `/home/mega/kobra` and commit this brief.
2. Read the files in §3 and §4. Summarise for the operator, in Turkish and briefly, what Kobra-in-InfraMedic already
   does well and what it lacks for the new goal.
3. Run the brainstorm (§5) and record the decisions in `docs/` with dates, including rejected options and why.
4. Only after the operator approves a direction: a product brief, a roadmap and the first milestone.
