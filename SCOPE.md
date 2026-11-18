# Kütüphane · Kapsam sözleşmesi (SCOPE.md)

## Kimlik
- **Bu repo:** the governed knowledge catalog and persistent agent memory where people and agents record what they know: who wrote it, who accepted it, and who may use it for what (`docs/23` §1; PORTFOLIO §1).
- **Bu repo değildir:** a RAG or chat platform, an identity provider, or an agentic AI governance gateway.
- **Neden ayrı bir proje:** it owns persistent memory, the RAG corpus, acceptance, links, sharing and the use rights of each item; LLMDAP, the governance gateway, owns the per-identity policy, encryption and audit chain of each call (PORTFOLIO §2). Exception: InfraMedic may carry its own knowledge center for on-prem installs without Kütüphane (D4).

## Çekirdek (değişmezler)
- **C1** The write path is the provenance: an agent is never recorded as a person (principle 1, P2, D70).
- **C2** Acceptance is recorded, never assumed: each item shows who accepted it and how (a person's passkey or statement, a consumer's signed statement, a standing policy, or nobody); a rule becomes current only by a person; a book is strict by default and a looser policy is an explicit, revocable choice for one book. `acceptance: none` marks versions published before D85 (`legacy`) (principle 2, D85).
- **C3** Rights decide before use, inside Kütüphane: `ai_input: n` never reaches a model, `restricted` never leaves in a package, a reader learns nothing about what it may not read; every check fails closed (P3). Search and ask can select by acceptance kind and the catalog paths show it; this is the reader's selection, not a server gate (D85 Q12, #235).
- **C4** Memory is data, never instruction: notes reach a model only as tool results; agent instructions need `activate` and a scan (principle 3).
- **C5** Nothing is rewritten and everything can be withdrawn; an asset leaves with its rights, origin and acceptance (principles 4, 5).

## Kapsam içi (yetenekler)
- **K1** The catalog: books, versions, files, publication facts, kstd item information (D69, #159, #160).
- **K2** The RAG corpus: search and cited answers over books (D16). Item rights are applied before each model call. On Spark, Kütüphane's model calls go through LLMDAP (D52, D76); Kütüphane stays decoupled from it: the light install makes no model call, and a customer may use another gateway. `model_call` is a usage record, never an audit chain.
- **K3** Persistent agent memory: journals, notes, Standing, links, outcomes, expiry, sharing, journal export and import (D69, D80).
- **K4** Acceptance and curation: curator web passkey acts (D72), CLI curation, use policies and the publish timer (D85). A passkey is only for curator acts and gives no session or token to another system.
- **K5** Packages: `pack`, `export`, `receive`, `submit_package`, signing keys, `trust` (D29, D51, D83).
- **K6** Rights and access: grants, delegation, `activate`, the skill scan (advice only, D71), handling labels, token checks for configured issuers.
- **K7** The kstd standard and its reference validator, inside D7.
- **K8** The existing MCP tools, HTTP routes and curator web pages. A new tool, route or page is always bucket B.
- **K9** (maintenance) Tests, `docs/guide/`, the changelog and install recipes. It never carries new behaviour.

## Kapsam dışı
- **D1** A RAG platform, a chat UI, conversation state, connectors to outside sources, a code graph → yapılmaz; those tools connect to Kütüphane (`docs/23` §2).
- **D2** The per-call policy, encryption and audit chain of an LLM call; model pinning, digests and attestation → LLMDAP. Model choice → each consumer; model serving → spark-inference.
- **D3** Issuing tokens: production → the deployment's IdP or the consumer's own issuer (#195). Development tokens (`dev-token`) are for development only; Kütüphane checks every issuer that its deployment configures.
- **D4** Consumer-specific logic (the InfraMedic appliance, runbooks, the InfraMedic site documents UI, and InfraMedic's own on-prem knowledge center for installs without Kütüphane, designed to work with Kütüphane) → InfraMedic; the coding loop and its profiles → nöbetçi-mcp; the Pulse pipeline → Radar.
- **D5** Run state, job logs, costs, chat transcripts → the orchestrator that runs the work.
- **D6** Notes extracted from a conversation by the server → yapılmaz; an agent proposes, a person decides.
- **D7** Frozen or removed: new kstd statement kinds or categories (D74); new work on "my words", labels and access tags (D78); the decider and delegated curate (D73) → yapılmaz. Lifting a freeze is a change of this page.
- **D8** Telegram, cards, the approval and issue flow, host tools and guards → spark-hub.

## Sınırlar ve arayüzler
- **Bu projenin sunduğu sözleşmeler:** the MCP tools with their results and error texts; the HTTP API `/v1/*`; `kutuphane-package/1`; `kstd.yaml`; the journal export (JSONL); the curator web pages. New memory needs of other projects (also of LLMDAP's frozen memory surface) come here as `[istek]` issues. A change always needs Enes's approval.
- **Radar → Kütüphane (official integration, PORTFOLIO §2/§3, #234):** the source is Radar's published `pulse.v1.json`; the target is `radar-*` books only. Radar writes through the existing package path; a write or a token is never human acceptance. Unattended publication is allowed (Enes, 2026-11-18) when it is documented and the read paths filter it: it uses a standing use policy on the Radar book and key, recorded as acceptance kind `policy`; search and ask can exclude it, and the catalog paths show it (the reader's selection, not a server gate; matrix in #235). Until that path exists (#235), a Radar version waits for a Kütüphane person. The old pilot books `radar-docs`, `radar-news`, `radar-briefs` are not this contract. **Open until Enes fixes them (#234):** the collection list, the Pulse → kstd mapping, the writer principal and target item identity, and the write frequency. A change on either side is bucket B.
- **Kullandığı dış sözleşmeler:** a model gateway: on Spark the LLMDAP bridge (chat, embeddings, rerank) with Kütüphane's own subject key; the code speaks the bridge API today, so another gateway needs the same API or a new adapter (bucket B). OIDC/JWKS issuers, among them the agent tokens of spark-hub/host; WebAuthn; SkillSpector (advice only); PostgreSQL with pgvector.
- **Ajanın dokunabildiği yerler:** this repository, its branches and worktrees, `*_test` databases, and the upgrade scripts that the agent keeps outside this repository (prepared and reviewed; pinned to a SHA; one command that Enes runs). **Dokunmadığı yerler:** the live trees, the live database, its grants and settings, the guardrails (spark-hub and its host tools, `spark-inceleme`, guards, CI definitions, harness hooks), other repositories.
- **Merge = canlı yayın mı?** No. The live install moves only by a pinned one-command upgrade script that Enes runs.

## Kanon
| Konu | Esas belge |
|---|---|
| Decisions (win over every repo document; PORTFOLIO wins over them) | `docs/01-direction-decisions.md` |
| Principles, promises, "is / is not" | `docs/23-vision-v1.md` |
| kstd | `docs/11-standard-draft.md`, `docs/guide/kstd.md` |
| Behaviour that exists | `docs/guide/` |
| Work rules | `CONTRIBUTING.md`; skills `kutuphane-vision-gate` (+ `consumers.md`), `ponytail-kutuphane` |

Tarihsel/bayat: `docs/05`, `docs/06`, `docs/10`, `docs/research/`. Gerekçe olarak kullanılmaz.

## Değişiklik kaydı
- 2026-11-18 · v1 · Enes onayı (spark-kart, `scope-onay`) · this PR
