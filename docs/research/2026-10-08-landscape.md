# Kütüphane competitive landscape brief (research as of 2026-10-08)

Web research by a delegated agent; model output, reviewed by the session. Vendor "roundup" blogs used only where a
primary source corroborated them. Caveats at the end.

## 1. Landscape summary by segment

**Developer-docs-for-agents.** Context7 (Upstash) indexes 9,000+ public libraries by parsing `.md/.mdx/.rst/.txt/.ipynb`
from source repos (falls back to generating from code), serves two tools (`resolve-library-id`, `get-library-docs`) over
MCP with topic filter and token budget; versions come from git tags/branches declared in `context7.json`
(`previousVersions`, `branchVersions`). Private sources need Pro/Enterprise and there is no self-host option documented.
llms.txt/llms-full.txt is now default on Mintlify and GitBook; GitBook exposes an MCP server per published space;
Mintlify reports ~half of docs traffic is agents. DeepWiki MCP is free for public repos; private repos go through the
authenticated Devin MCP server. Ref.tools is a token-efficient docs-search MCP (public + private repos + web).
Exa/Tavily are web-search MCPs, not knowledge stores. None of these do per-entity ACL, delegation or audit; all are SaaS.

**Enterprise knowledge/search for AI.** Glean: SaaS or "customer hosted" single tenant in your GCP/AWS project,
permission inheritance from 100+ sources, MCP directory (Sept 2026 release); air-gap is only mentioned in job postings.
Onyx (ex-Danswer, MIT): self-host/on-prem/air-gapped, 45+ connectors with real-time permission sync, "full audit trail
on every query and response", MCP tools. Microsoft 365 Copilot: Graph connectors with ACL security-trimming; on-prem
sources via Graph Connector Agent (v3.1.16, Jan 2026) but the index/Copilot are cloud-only. Google NotebookLM
Enterprise (renamed "Gemini Notebook Enterprise") and Gemini Enterprise (ex-Agentspace): cloud-only with regional
residency (EU/JP/UK/IN/SG, mid-2026), notebook sharing with Okta SCIM autocomplete (Aug 20 2026), resource-level IAM
(Sept 28 2026), usage audit logs into Cloud Logging via `ObservabilityConfig`, official Discovery Engine REST API; agent
sharing with admin approval (Feb 23 2026). Elastic Agent Builder exposes an MCP server where tool/data access follows
Elastic user permissions (document-level security). Vectara: SaaS/VPC/on-prem, "air-gapped supported", OIDC/SAML.
RAGFlow: single Docker deployable RAG+agents (April 2026 release). Dify: Community Edition self-host; Enterprise adds
RBAC/audit logs. AnythingLLM: multi-user roles Docker-only, MCP agent builder. Khoj: cloud deprecated April 2026,
self-host only. LlamaCloud: BYOC via Helm on K8s. deepset Haystack Enterprise: VPC/on-prem/air-gapped. Cohere North 2:
on-prem/air-gapped agent platform with memory. Writer: Knowledge Graph (enterprise tier), SaaS.

**Agent memory layers.** Mem0 scopes memory by `user_id/agent_id/app_id/run_id`; no cross-entity sharing, no documented
ACL or history; cloud platform. Zep: Graphiti bi-temporal graph (valid_at/invalid_at edge invalidation, history
preserved); Zep CE deprecated mid-2026, Graphiti stays OSS with an MCP server (needs Neo4j/FalkorDB/Kuzu). Letta: shared
memory blocks attached to multiple agents (read/write), self-hostable. Cognee (Apache-2.0): 100% local with Ollama,
graph + vector, MCP; air-gap capable. Supermemory: closed managed service, MCP-native. Honcho (OSS): Workspaces → Peers
(humans and agents are both peers) and Sessions. None has delegation, signed provenance or explainable access.

**Knowledge packaging.** Agent Skills (SKILL.md, open standard since Dec 18 2025, 25+ implementations by March 2026):
frontmatter `name/description/license/compatibility/metadata/allowed-tools`, progressive disclosure, no signing or ACL
in spec. AGENTS.md: donated to Linux Foundation AAIF (Dec 9 2025), 60k+ repos. MCP resources/prompts: read-only URIs +
templates, no versioning semantics. A2A v1.0 Agent Card at `/.well-known/agent-card.json` describes capabilities/auth,
not knowledge. OpenAI: File Search vector stores (4.2B queries/month, June 2026), "company knowledge" in ChatGPT with
citations and user-scoped access; Agent Builder sunset Nov 30 2026. Google OKF v0.1 (June 12 2026): portable directory
of Markdown+YAML frontmatter (only `type` required), cross-links form a graph; no ACL/versioning/provenance fields.
This is the closest thing to a "knowledge bundle" standard and Kütüphane should import/export it.

**Versioning and provenance.** lakeFS positions itself as "git for agent knowledge" (OKF post, July 13 2026):
branches/commits/tags/rollback, immutable release tags for agents; Summer 2026 release (July 28) adds Iceberg-queryable
audit log, object-level ABAC, multi-tenant "mini-lakeFS" for agents — Mount/RBAC/SSO/audit are Enterprise-only. Dolt:
version-controlled SQL for agent data, with MCP plugins. W3C PROV remains the lineage vocabulary (Git2PROV). C2PA 2.4
(April 2026) signs media manifests; EU AI Act labeling (Aug 2026) drives adoption. Sigstore/OpenSSF Model Signing is the
de facto signing bundle format. "Explainable access" products exist only as adjacent niches: TrustGraph (two-layer
provenance), Sourcegraph (which files an agent read, for regulated teams), Provena (OSS evidence-backed memory),
Gravitee/Saviynt (runtime authorization decision logs).

**Access control and agent identity.** OpenFGA and SpiceDB document RAG patterns: post-filter (BatchCheck) vs
pre-filter (ListObjects then restrict vector search); LangChain ships a SpiceDBRetriever. MCP spec 2026-07-28 hardened
OAuth 2.1 (issuer validation, CIMD instead of DCR, `Mcp-Method`/`Mcp-Name` headers) but agent identity, per-request
authorization, delegation chains and audit are explicitly out of scope. IETF: draft-klrc-aiagent-auth (-03, July 2026),
19 WIMSE drafts (Aug 2026), SPIFFE WIT-SVID, AIMS composing WIMSE+SPIFFE+OAuth; AIP (arXiv 2603.24775, March 2026)
proposes invocation-bound capability token chains (Biscuit) for MCP+A2A delegation. No product ships all of this.

## 2. Comparison table

| Product | Self-host | Air-gap | Agent-facing (MCP/API) | Human-facing UI | Versioning | Sharing/ACL | Provenance/audit |
|---|---|---|---|---|---|---|---|
| Context7 | No | No | MCP | Minimal | Git tags/branches of libs | Private sources (Pro/Ent), team-level | No |
| Mintlify / GitBook | No | No | llms.txt, MCP | Yes | Via git | Site-level | No |
| DeepWiki / Ref.tools | No | No | MCP | Yes/No | No | Private via Devin key | No |
| NotebookLM Ent. | No (cloud, residency) | No | Discovery Engine API; no official MCP | Yes (strong) | No | Per-notebook share, IAM | Cloud Logging usage audit |
| Gemini Enterprise | No | No | Agents, connectors | Yes | No | Source ACL inheritance, agent sharing | Cloud audit logs |
| Glean | Customer-hosted (GCP/AWS) | Unclear | MCP directory, API | Yes | No | Source ACL inheritance | Analytics |
| Onyx | Yes (MIT) | Yes | MCP, API | Yes | No | Permission sync, groups | Query/response audit trail |
| M365 Copilot | No | No | Graph API, agents | Yes | No | ACL trimming | Purview |
| Elastic Agent Builder | Yes | Yes | MCP | Kibana | No | Doc-level security | ES audit |
| Vectara | Yes | Yes | API | Minimal | No | Corpus-level, IdP | Limited |
| RAGFlow / Dify / AnythingLLM | Yes | Yes | API, MCP agents | Yes | No | Workspace/RBAC (Dify Ent. audit) | Weak |
| LlamaCloud / deepset / Cohere North | BYOC / on-prem | deepset, Cohere yes | API | Partial | No | Tenant/RBAC | Limited |
| Mem0 | Cloud (OSS core) | OSS only | API, MCP | No | No | Entity scoping only | No |
| Zep/Graphiti | Graphiti OSS | Yes | MCP | No | Bi-temporal facts | None | History preserved |
| Letta | Yes | Yes | API | Dev UI | No | Shared blocks | No |
| Cognee | Yes | Yes | MCP | No | No | None | No |
| Honcho | Yes | Yes | API | No | No | Workspace/peer | No |
| lakeFS | Yes | Yes | S3/Mount, API | Yes | Git-like commits/tags | ABAC (Enterprise) | Iceberg audit table (Enterprise) |
| OKF / Agent Skills / AGENTS.md | Format only | n/a | Yes | Yes | None in spec | None | None |

## 3. The wedge: features no current product combines

1. Humans and agents as first-class, equal principals in one knowledge store, with per-entity (user, agent, role)
   grants and a UI as good as NotebookLM for the humans.
2. Delegation as a modeled object: user-to-agent grants with scope, TTL and depth, so an agent reads only what its
   delegating human could, and the chain is stored.
3. Content-addressed versioning of knowledge (commits, tags, diffs, pinned releases for agents) merged with retrieval:
   every answer cites doc@commit.
4. Explainable access log: per-read record of who/which agent, under whose delegation, which chunk/version, in which
   query, with the authorization decision and policy; exportable as W3C PROV.
5. Signed, portable knowledge bundles (OKF + Agent Skills layout, Sigstore/C2PA-style manifests) for air-gap
   import/export with provenance intact.
6. Air-gapped, encrypted-at-rest deployment with the MCP server as a separable product.
7. Bi-temporal knowledge semantics on documents and facts ("what did agent X know on date D").

## 4. Risks: who could move in

- Google: OKF + Gemini Notebook Enterprise + Google Distributed Cloud could become on-prem NotebookLM with IAM and
  audit. Highest risk.
- Onyx: already self-host/air-gap with permission sync, audit trail and MCP; adding versioning and delegation is
  incremental. Direct OSS competitor.
- lakeFS (now owns DVC): "agent knowledge versioning" plus ABAC and audit tables; could add a retrieval/UI layer.
- Microsoft: Copilot connectors, Purview audit and Entra Agent ID; on-prem index is the gap.
- Cohere North / deepset: sovereign on-prem agent platforms with memory could add shared KB semantics.
- Standards drift: MCP auth, WIMSE/SPIFFE agent identity and A2A move fast; the delegation model must track them.
- Commoditization: "docs over MCP" is free; the wedge must be governance, not retrieval.

## 5. Sources (accessed 2026-10-08)

- Context7: https://context7.com/docs/library-owners.md ; https://context7.com/docs/adding-libraries ;
  https://www.mintlify.com/upstash/context7/mcp/overview ; https://docs.stacklok.com/toolhive/guides-mcp/context7
- Mintlify llms.txt: https://index.mintlify.com/library/best-llms-txt-platforms ; GitBook: https://gitbook.com/docs/llm-ready-docs
- DeepWiki MCP: https://cognition.ai/blog/deepwiki-mcp-server ; https://docs.devin.ai/de/work-with-devin/deepwiki-mcp ;
  Ref: https://glama.ai/mcp/servers/ref-tools/ref-tools-mcp ; Exa/Tavily: https://parallel.ai/articles/best-web-search-mcp.md
- Glean: https://docs.glean.com/get-started/prepare/about-deployment ; https://docs.glean.com/release-notes/releases/2026-09-08-september-release
- Onyx: https://onyx.app/solutions/secure-ai ; https://onyx.app/insights/glean-alternatives
- Microsoft Graph connectors: https://learn.microsoft.com/graph/custom-connector-sdk-overview ;
  https://learn.microsoft.com/en-us/microsoftsearch/on-prem-agent ; https://www.microsoft.com/download/details.aspx?id=104045
- Google: https://docs.cloud.google.com/agentspace/docs/release-notes ; https://docs.cloud.google.com/gemini/enterprise/docs/choose-product ;
  https://docs.cloud.google.com/gemini/enterprise/notebooklm-enterprise/docs/set-up-usage-audit-logs-for-nblme ;
  https://workspaceupdates.googleblog.com/2026/03/new-ways-to-customize-and-interact-with-your-content-in-NotebookLM.html ;
  https://elephas.app/blog/notebooklm-source-limits.md ; https://pasqualepillitteri.it/en/news/3874/notebooklm-canvas-personal-preferences-connectors-coming-2026
- Elastic: https://www.elastic.co/search-labs/blog/agent-builder-mcp-reference-architecture-elasticsearch
- Vectara: https://docs.vectara.com/docs/deployments ; https://www.vectara.com/business/solutions/use-cases/vectara-for-on-prem-ai
- RAGFlow/Dify/others: https://dupple.com/learn/best-rag-tools ; https://aicybr.com/blog/dify-self-hosting-deployment-guide ;
  https://docs.anythingllm.com/features/security-and-access ; https://docs.khoj.dev/get-started/setup ;
  https://developers.llamaindex.ai/llamaparse/self_hosting/ ; https://www.toolradar.com/tools/haystack-deepset ;
  https://www.techzine.eu/news/applications/144756/cohere-north-2-sovereign-agents-and-control-over-token-costs/ ;
  https://writer.com/blog/enterprise-ai-features/
- Memory: https://docs.mem0.ai/platform/features/entity-scoped-memory ; https://blog.getzep.com/beyond-static-knowledge-graphs/ ;
  https://www.agenticwire.news/article/zep-ce-deprecated-migrate-mem0-graphiti-letta ;
  https://docs.letta.com/guides/agents/multi-agent-shared-memory ; https://cognee.ai/product ;
  https://supermemory.ai/docs/overview/what-is-supermemory ; https://docs.honcho.dev/v2/documentation/core-concepts/architecture ;
  https://www.sentra.app/articles/mem0-alternatives ; https://mcp.directory/blog/mem0-vs-letta-vs-zep-vs-cognee-2026
- Packaging: https://agentskills.io/specification ; https://parallel.ai/articles/what-are-agent-skills ;
  https://codex.danielvaughan.com/2026/04/07/agents-md-open-standard-cross-tool-portability ;
  https://archestra.ai/blog/mcp-tools-resources-prompts ; https://aaif.io/blog/a2a-v1-0-a-builder-s-guide-part-1-discovery-tasks-and-clients ;
  https://developers.openai.com/api/docs/guides/tools-file-search ;
  https://venturebeat.com/ai/openai-launches-company-knowledge-in-chatgpt-letting-you-access-your-firms ;
  https://osher.com.au/blog/openai-agentkit/ ;
  https://the-decoder.com/google-clouds-open-knowledge-format-turns-scattered-docs-into-markdown-files-for-ai-agents/ ;
  https://www.gitbook.com/blog/what-is-okf-open-knowledge-format
- Versioning/provenance: https://lakefs.io/blog/okf-lakefs-agent-knowledge-versioning/ ;
  https://lakefs.io/blog/lakefs-summer-2026-release-ai-governance/ ; https://dev.co/databases/open-source/dolt ;
  https://researchcollaborations.elsevier.com/en/publications/git2prov-exposing-version-control-system-content-as-w3c-prov/ ;
  https://c2pa.org/?p=259 ; https://rywalker.com/research/sigstore ; https://docs.trustgraph.ai/learn/explainability ;
  https://sourcegraph.com/blog/compliance-first-ai-proving-agent-provenance ; https://mcpservers.org/servers/admiralpunk/provena
- Access control/identity: https://openfga.dev/docs/modeling/agents/rag-authorization ;
  https://docs.langchain.com/oss/python/integrations/retrievers/spicedb.md ;
  https://www.permit.io/blog/mcp-auth-vs-tool-call-authorization-2026-07-28 ;
  https://dev.to/tigeraio/mcps-auth-hardening-what-the-six-new-oauth-seps-fix-and-what-they-still-dont-2g0c ;
  https://ftp.kaist.ac.kr/ietf/draft-klrc-aiagent-auth-03.html ;
  https://labs.cloudsecurityalliance.org/research/csa-research-note-ietf-agent-identity-standards-20260902-csa/ ;
  https://mojoauth.com/blog/workload-identity-for-agents-spiffe-spire-vs-oauth-client-credentials ; https://arxiv.org/abs/2603.24775

Caveats: Glean air-gap support is inferred from a job posting; NotebookLM Enterprise has an official Discovery Engine
API but no official MCP server; lakeFS audit/ABAC/mount features are Enterprise-only; Mem0 and Supermemory self-hosting
claims rest on OSS cores, not the documented platforms.
