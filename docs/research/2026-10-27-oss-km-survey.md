## Survey: open-source knowledge, RAG and agent-memory systems compared with Kütüphane/kstd

**Data:** GitHub API and primary documents, checked 2026-10-27. ★ = stars. "?" = not verified.

### 1. Projects in detail

| Project | Licence | ★ / last release | Unit of knowledge | Governance facts (evidence) |
|---|---|---|---|---|
| **Onyx** | MIT, with `ee/` folders under an Enterprise licence | 33.0k / v5.0.1, 2026-10-26 | connector document → chunk | Connectors are Private, Public or Auto-Sync. Document RBAC and permission sync work only in EE ([access controls](https://docs.onyx.app/security/architecture/access_controls.md)). It has an MCP server with OAuth ([doc](https://docs.onyx.app/overview/onyx_anywhere/mcp_server)). |
| **RAGFlow** | Apache-2.0 | 92.9k / v1.0.0-rc2 | dataset → document → chunk | A dataset is "Only me" or "Team" ([doc](https://ragflow.io/docs/v1.0.0-rc2/guides/team/permission_system_overview/team_and_resource_permissions)). It has an MCP server and document metadata. |
| **Dify** | modified Apache-2.0 (no multi-tenant use, logo clause) | 159.7k / 1.18.0 | knowledge base → document → segment | `only_me` / `all_team_members` / `partial_members`, and a metadata filter ([API](https://docs.dify.ai/en/api-reference/knowledge-bases/get-knowledge-base)). Issue [#19249](https://github.com/langgenius/dify/issues/19249) reported a bypass through a direct URL. |
| **Open WebUI** | own licence (BSD-3 + a branding clause above 50 users) | 156.9k / v0.12.4 | knowledge base → file | Group read/write grants ([doc](https://docs.openwebui.com/features/authentication-access/rbac/permissions/)). |
| **DataHub** | Apache-2.0 | 12.9k / v1.8.0 | **Context Document** + data assets | It has owners, tags, glossary, domains, draft/published, version history and imports from Notion, Confluence and GitHub ([doc](https://docs.datahub.com/docs/features/feature-guides/context/context-documents)). Its MCP server is open source. `DocumentSource` is only NATIVE or EXTERNAL ([schema](https://github.com/datahub-project/datahub/blob/master/metadata-models/src/main/pegasus/com/linkedin/knowledge/DocumentSource.pdl)). `AuditStamp` has **`actor` + `impersonator`** ([schema](https://github.com/datahub-project/datahub/blob/master/li-utils/src/main/pegasus/com/linkedin/common/AuditStamp.pdl)). |
| **OpenMetadata** | Apache-2.0 | 15.6k / 2.0.6 | data asset, glossary term | Policy rules have conditions such as `matchAnyTag(PII.Sensitive)` ([doc](https://docs.open-metadata.org/v2.1.x-SNAPSHOT/how-to-guides/admin-guide/roles-policies/authorization)). It has glossary approval by reviewers ([doc](https://docs.open-metadata.org/v2.0.x/how-to-guides/data-governance/glossary/approval)), PII auto-classification, data contracts with "terms of use", and an MCP server. |
| **Apache Atlas + Ranger** | Apache-2.0 | 2.2k / no GitHub releases | data entity | A PII classification **propagates through lineage** ([doc](https://atlas.apache.org/2.0.0/ClassificationPropagation.html)). Ranger tag policies use it to control access. |
| **OKF v0.2** (Google) | Apache-2.0 | 1.1k / last push 2026-08-21 | markdown concept + YAML | It has `sources`, `generated{by,at}`, `verified[]`, `status`, `stale_after` and attested computations. An actor is written `human:<id>` or `agent/version`. The spec says: "Trust tiers are advisory signals, not access control" ([SPEC §5, §7](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)). It has no rights, PII or signature fields. |
| **mem0** | Apache-2.0 | 67.9k / ts-v3.3.1 | extracted memory fact | It scopes memories by `user_id` / `agent_id` / `run_id`. Its history table keeps `event`, `actor_id` and `role` ([storage.py](https://github.com/mem0ai/mem0/blob/main/mem0/memory/storage.py)). The writer declares these values itself. |
| **Graphiti / Zep** | Apache-2.0 | 32.3k / v0.31.2 | episode → entity/edge | It is bi-temporal: `valid_at`, `invalid_at`, `expired_at`. A new fact invalidates an old one, and each edge links to its episodes ([edges.py](https://github.com/getzep/graphiti/blob/main/graphiti_core/edges.py)). It has an MCP server. |
| **Cognee** | Apache-2.0 | 32.8k / v1.6.6rc1 | dataset → graph | It has tenants and roles, and read/write/delete/share rights on each dataset ([doc](https://docs.cognee.ai/core-concepts/multi-user-mode/permissions-system/datasets)). It has an MCP server (`cognee-mcp`). |
| **Letta** | Apache-2.0 | 25.3k / 0.16.8, 2026-05 | memory block | A block can be `read_only` ([doc](https://docs.letta.com/guides/agents/memory-blocks)). The `.af` file format makes an agent portable. |
| **Basic Memory** | AGPL-3.0 | 4.4k / v0.24.1 | markdown note | It is local-first and works through MCP. "AI and humans write to the same files" ([README](https://github.com/basicmachines-co/basic-memory)). It does not record who wrote what. |
| **TrustGraph** | Apache-2.0 | 2.8k / v2.8.17 | ontology graph | It calls itself an "agent governance platform": a policy runtime checks agent actions, and it keeps W3C PROV-O provenance ([README](https://github.com/trustgraph-ai/trustgraph)). We did not test these claims. |
| **Kompl** | Apache-2.0 | 81 / v0.4.0, 2026-10-26 | compiled wiki page | It shows citations and disputes. Its MCP tool `add_source` is off by default and allows at most 20 a day. It has one tenant and **no auth**. It compiles with cloud LLMs ([README](https://github.com/tuirk/Kompl)). |

**Other projects, one line each:**
- **Outline:** BSL-1.1, 41.1k★. It has an official MCP server and collection permissions.
- **Wiki.js:** AGPL, 29.1k★.
- **Logseq:** AGPL, 45.4k★.
- **AnythingLLM:** MIT, 67.6k★.
- **PrivateGPT:** Apache, 57.6k★.
- **SurfSense:** Apache, 16.6k★, with Owner/Admin/Editor/Viewer roles.
- **Khoj:** AGPL, 37.8k★. The last release is a beta from 2026-03.
- **Kotaemon:** Apache, 25.8k★.
- **R2R:** MIT, 8.0k★. No release after 2025-06, so it is not active.
- **Morphik:** BUSL-1.1, so it is not open source.
- **Quivr:** it has changed to monitoring of content streams.
- **LightRAG**, **GraphRAG**, **txtai**, **Haystack**, **LlamaIndex:** these are retrieval engines or frameworks. They have a free metadata dict and no governance.
- **MCP memory server:** entities, relations and observations only.
- **MemOS:** 12.1k★. Its paper says that it has ACL, TTL, provenance and audit. The open-source code is not verified.
- **OpenViking:** AGPL, 40.9k★.
- **Fides (Ethyca):** Apache-2.0, 482★. It has data-use, data-category and legal-basis policies for *systems*, not for texts.
- **Presidio:** MIT, 11.5k★. It is a PII detector, not a knowledge system.

### 2. Matrix

Y = yes, P = partial, N = no, ? = not verified. The evidence links are in §1.

| | ACL | Lineage | Human/AI origin | Rights per item | PII | Review | Versions/supersession | Audit | Policy decision | MCP | Local |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Kütüphane** | Y | Y | Y (declared) | **Y** | **Y + legal basis** | Y | Y | Y | **Y, 3 results + cases** | Y | Y |
| Onyx | P (EE) | P | N | N | N | N | ? | ? | N | Y | Y |
| RAGFlow | P | P | N | N | N | N | ? | ? | N | Y | Y |
| Dify | P | P | N | N | N | N | ? | ? | N | ? | Y |
| Open WebUI | P | N | N | N | N | N | ? | ? | N | ? | Y |
| DataHub | Y | Y | P (actor/impersonator) | N | P (tags) | P (draft) | Y | Y | P (access only) | Y | Y |
| OpenMetadata | Y | Y | ? | P (contract text) | Y | Y | Y | ? | P (access only) | Y | Y |
| Atlas + Ranger | Y | **Y + propagation** | N | N | Y | ? | ? | Y | Y (access) | N | Y |
| OKF | N | Y | P (self-asserted) | N | N | P (`verified`) | P (`status`) | N | N ("advisory") | — | — |
| mem0 | P | P | P (self-asserted) | N | N | N | Y | P | N | ? | Y |
| Graphiti | ? | Y | N | N | N | N | **Y (bi-temporal)** | N | N | Y | Y |
| Cognee | Y | ? | N | N | N | N | ? | ? | N | Y | Y |
| Letta | P | N | N | N | N | N | ? | ? | N | ? | Y |
| Basic Memory | N | P | N | N | N | N | P (files) | N | N | Y | Y |
| TrustGraph | P | Y | ? | N | ? | ? | ? | Y (claimed) | P (agent actions) | ? | Y |
| Kompl | N | Y | N | N | N | P | P | N | N | Y | P |

### 3. Where we are different, and where we are behind

**Real differences:**
1. **Use rights per item stop model input.** No other project has a licence or AI-use field that stops embedding, reranking or answers. DataHub, OpenMetadata and Atlas control **access**, not **use**. OpenMetadata "terms of use" is contract text and does not control a call.
2. **Legal basis at export.** We use DPV codes on knowledge text. Fides has this idea, but only for systems.
3. **Deterministic permit/deny/escalate with a public test set.** OPA and Cedar are policy engines, but they have no rule set for knowledge rights.
4. **Agent instructions need `activate`.** We did not find this in any other project.

**Not new:**
- **Restrictions that follow lineage.** Atlas propagates classifications through lineage since about 2018. Our rule for derived items is a version of that idea.
- **Supersession.** Graphiti's bi-temporal model is better developed than ours.
- **Origin labels.** OKF has `generated` / `verified`, mem0 has `actor_id`, and DataHub has `impersonator`.

**Where we are behind:**
- **Community:** 0★, 1 contributor, repo created 2026-10-07. The others have 1k–160k★.
- **Connectors:** we ingest folders only. Onyx has 40+ connectors (vendor figure), DataHub 150+. We have no permission sync.
- **UX:** the root README describes no web UI for search or reading. We have only a labelling page.
- **Scale:** not tested beyond our corpus.

**Origin, for the human/agent question:** every system that records origin takes it from the writer's claim (OKF `human:` prefix, mem0 `role`). Our `origin` in `kstd.yaml` is also an issuer's claim. DataHub shows a better pattern: `actor` (the credited person) and `impersonator` (the service that made the change). Our origin must come from the **authenticated principal of the write**, not from a field:
- an agent principal can never write `human`;
- if a person tells an agent to enter text, the record is actor = person, impersonator = agent, origin = `model`;
- the text becomes `assisted` only after a review in a session where the person authenticated.

### 4. Who could adopt kstd, and who competes

**Integration targets.** These projects have metadata slots but no rights fields:
- **OKF:** the same file shape. A `rights` + `personal_data` family is the whole difference.
- **DataHub:** kstd fields as structured properties, plus an ingestion source for `kstd.yaml`.
- **OpenMetadata:** custom properties and policy conditions.
- **Basic Memory / Obsidian vaults:** `kstd.yaml` next to the notes.
- **mem0 / Graphiti:** per-memory metadata, with origin taken from the principal.
- **Kompl:** compiled pages are `origin: model` with recorded `inputs`.
- **Onyx / RAGFlow / Dify:** they could filter on `ai_input`, but they enforce weakly.

**Competitors:**
- **DataHub** is the most direct competitor: it is open source and has governed Context Documents for agents through MCP.
- **OpenMetadata** calls itself "Open Context Layer for Data and AI".
- **TrustGraph** competes with our governance claim.
- **Onyx** competes with us as a product.

### 5. Does a project already do what kstd aims at?

**No.** No verified project combines per-item licence, AI use, personal data with a legal basis, origin and a deterministic three-result decision with conformance cases, for knowledge text.

But the gap is narrow and closing. DataHub and OpenMetadata already have most of the infrastructure: owners, tags, lineage, policies, versions, MCP and documents for agents. They could add a licence or AI-use property in one release. Their communities are much larger than ours.

**Is the work meaningful?**
- **Yes, for the specification:** the decision rule with its cases, and the rights/PII/origin profile. This part is new and portable.
- **Less, for Kütüphane as a product** competing with platforms that have 30k–160k★.

**Recommendations:**
- Keep Kütüphane as the reference implementation.
- Offer kstd as a profile that OKF, DataHub and OpenMetadata can carry.

**For the "minimal" question:** OKF is no longer minimal. v0.2 already has provenance, trust, lifecycle and attestation, and our `origin` maps to `generated` / `verified`. The minimal part that only kstd adds is:
- `license`;
- `ai_use`;
- `personal_data` + `legal_basis`;
- a digest and a signature;
- the decision rule.