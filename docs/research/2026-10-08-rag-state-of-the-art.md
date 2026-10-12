# RAG / agent knowledge-access state of the art (Q4 2026) — brief for Kütüphane v1

Web research by a delegated agent (2026-10-08); model output, reviewed by the session. Scope: on-prem/air-gapped,
Postgres-centric, Qwen3-class ~27–32B generator, bge-m3 embedder, agents + humans. "Production" = multiple named
deployments or vendor-hosted at scale; "research" = papers/self-reported benchmarks only.

## 1. Retrieval

- **Hybrid BM25 + dense + cross-encoder rerank is the proven baseline.** Anthropic's Contextual Retrieval study
  (2024-09-19) measured BM25+embeddings cutting top-20 retrieval failures 49%, 67% with a reranker. VectorChord's BEIR
  runs show cross-encoder rerank beating both single methods on all four datasets while plain RRF *lowers* nDCG on
  FiQA/Quora vs dense alone — validate fusion before shipping. A 2026 Postgres measurement found BM25 vs pgvector a
  "dead heat" and hybrid "the only configuration with no bad shape."
- **Rerankers:** bge-reranker-v2-m3 (568M, XLM-R, 8k ctx) is the safe self-hosted default; Qwen3-Reranker 0.6B/4B/8B
  (Apache-2.0, 100+ langs, 32k ctx, instruction-aware, 2025-06-05) is the stronger open option. Both serve via TEI/vLLM.
- **Postgres stack (all production):** pgvector 0.8.0 (2024-10-30) added iterative index scans + better cost estimation
  so metadata-filtered ANN (tenant/ACL) no longer collapses recall; 0.8.2 current. BM25 in Postgres: ParadeDB
  pg_search (Tantivy, AGPL-3 community), VectorChord-BM25 (`vchord_bm25`), TigerData pg_textsearch 1.0 (2026-03-31;
  native C; 2.3x query speedup and 8.7x concurrency vs ParadeDB on MS MARCO v2, but 1.6–2x slower builds). VectorChord
  1.1.1 (2026-02-28) adds RaBitQ-quantized disk-friendly ANN and an exact `@#` MaxSim operator (ColBERT-style
  multi-vector). pgvectorscale (DiskANN + label filtering) for >10M vectors.
- **Late interaction / ColPali:** ColQwen2/2.5 are the only visual-document retrievers with real production traffic;
  patch-level multi-vectors cost ~100x storage; pooling papers still research. Research/early-adopter for v1.
- **Learned sparse (SPLADE):** production in OpenSearch/Elastic; bge-m3 emits a sparse head for free; Postgres has no
  inverted-index path for learned sparse.
- **When a dedicated store is needed:** >50–100M vectors, sub-50 ms p99 under heavy concurrency, learned-sparse or
  ColPali at scale, or cross-cluster sharding. Below that, Postgres + RLS + transactions wins on governance.

## 2. Chunking and parsing

- **Contextual retrieval beats late chunking on quality; late chunking wins on cost.** Controlled eval (arXiv
  2504.19754): 72.4 vs 61.0 nDCG@10 on ConTEB, 1891 ms vs 16 ms indexing per document. Late chunking alone ~3.6%
  relative nDCG gain (Jina). On-prem Qwen3 with vLLM prefix caching makes the context prefix cheap. Structure-aware
  (heading/section) chunking with a 50–100-token LLM context prefix is the mainstream choice.
- **Parsing stacks (production, GPU self-hostable):** Docling (RT-DETR layout >85% mAP DocLayNet, TableFormer >91% TEDS
  on FinTabNet, 4–6 GB VRAM/worker, ~2.4k pages/hr on L40S) for enterprise/financial/legal/PPTX; MinerU for formulas and
  CJK; Marker for speed (~3k pages/hr) with 75–80% TEDS on tables; PyMuPDF4LLM for native-text PDFs; unstructured for
  mixed Office/email; Nougat superseded. Route per document type; keep HTML tables; store figure crops with captions.

## 3. Beyond-chunk RAG

- Costs: Microsoft GraphRAG ≈ $50–200 and 45 min per 500 pages vs LightRAG ≈ $0.50/3 min vs plain embeddings <$5.
  GraphRAG-Bench (arXiv 2506.05690) finds GraphRAG "frequently underperforms vanilla RAG" except for
  hierarchical/global-summary queries; structure-based methods cost 5–10 F1 on simple QA.
- HippoRAG 2 (ICML 2025): best of the graph family but research-grade code.
- Graphiti/Zep (temporal KG) is for *agent memory*, not document corpora. Cognee's wins are self-reported.
- Verdict: only "Type 1" graph use (entity/relationship metadata as filters/expansions on vector hits) is cheap and
  proven. Full GraphRAG is research-adjacent for a governed library.

## 4. Agentic RAG and the grep counter-trend

- Claude Code retrieves with grep/glob + a compact tree and curated descriptions, no vector DB. Context7 exposes two
  MCP tools over a private index; llms.txt is a curated map. PageIndex's "vectorless" tree navigation reports 98.7%
  FinanceBench (self-reported).
- Counter-evidence: Chroma "Context Rot" (2025-07-14, 18 models incl. Qwen3-32B/235B) shows non-uniform degradation
  with input length; multi-hop accuracy drops between 32k–128k on every 1M-window model. Prompt caching makes "load
  whole document" cheap only when queries share a prefix.
- Agentic loops (query decomposition, iterative retrieval, rerank, synthesis) are proven even with local 7B models
  (arXiv 2606.21553); hierarchical retrieval interfaces (A-RAG, arXiv 2602.03442) and the SoK (arXiv 2603.07379) are
  the current research framing.
- Practical synthesis: agents want *both* — a `search` tool (hybrid+rerank) and `grep`/`read_section`/`list_tree`
  tools over full parsed documents; humans want ranked passages with citations.

## 5. Evaluation

Ragas (offline tuning), DeepEval (CI gate on golden set), TruLens (production drift) is the standard trio. Metrics:
context precision/recall, nDCG@k/MRR for retrieval; faithfulness, answer relevancy, correctness for generation. Teams
version: prompt-template hash, embedding model + revision, chunker version, top-k, index snapshot ID, doc count,
eval-model; re-embeds go to a parallel table/collection for A/B against the frozen golden set before cut-over.
Golden-set generation pipelines (rag-gs, TRIAD arXiv 2608.21558) are usable but need human review.

## 6. Citations and grounding

Character-span citations are production: Anthropic Citations API (2025-01) returns char ranges per claim; NotebookLM
shows numbered inline citations with hover-preview and says "not in sources" when unsupported. For Qwen3 on-prem: pass
each chunk as a numbered document, require `[n]` per sentence, then verify with an NLI/reranker pass that the cited
span entails the sentence (AtomCite arXiv 2609.05802; "Cited but Not Verified" arXiv 2605.06635). Pleias-RAG (arXiv
2504.18225) demonstrates small models trained to quote.

## 7. Security and governance

OWASP LLM Top 10 (2025): prompt injection (LLM01), vector/embedding weaknesses (LLM08). Proven controls: metadata
(source, revision, classification, ACL) on every chunk; **pre-filter** by identity inside the query (RLS or WHERE +
pgvector 0.8 iterative scans), not post-filter — arXiv 2608.11730 shows post-filtering leaks plaintext via
near-duplicate probes. Treat retrieved text as data, strip/flag instruction-like spans at ingest, sign ingestion
provenance, re-scan indexes on model changes. Embedding inversion is real (vec2text, ZSINVERT arXiv 2504.00147) so
vectors are confidential; encrypted-query vector search remains academic — rely on disk encryption + RLS + audit.
Index poisoning defenses (RAGuard, InceptionRAG) are research; the practical control is curated ingestion with human
approval.

## 8. Embedders for on-prem

- bge-m3 (2024-02, MIT): dense+sparse+multi-vector, 8k ctx, 1024-d, 100+ langs incl. Turkish. Most flexible free model.
- Qwen3-Embedding 0.6B/4B/8B (2025-06-05, Apache-2.0): MMTEB 64.3/69.5/70.6, Matryoshka 32–4096-d, 32k ctx,
  instruction-aware; TR-TEB Turkish retrieval 76.3 (8B)/75.5 (4B). Biggest recent change for Turkish.
- jina-embeddings-v4 (Qwen research license) and v5-text (CC-BY-NC) are **not commercially usable** on-prem without a
  license. nomic-embed-text v2 (Apache-2.0) trails bge-m3/Qwen3 on multilingual.
- Turkish benchmarks: TR-MTEB (EMNLP 2025 Findings), TR-TEB.

## Recommendations for Kütüphane v1 (ranked)

1. Postgres-only retrieval core: pgvector 0.8.x HNSW + a BM25 extension + bge-reranker-v2-m3 or Qwen3-Reranker-0.6B.
   Spike pg_textsearch vs ParadeDB on our corpus. Fuse by rerank, not RRF alone. Scale ceiling ~50M vectors; accept.
2. Keep bge-m3 as v1 embedder; run Qwen3-Embedding-4B in a parallel column as a measured A/B. Store embedding
   model+revision per row; never mix in one index.
3. Parse with Docling by default, MinerU for formula-heavy, PyMuPDF4LLM fast path; structure-aware chunking +
   LLM-generated 50–100 token context prefix. Skip late chunking in v1.
4. Dual access surface for agents: MCP tools `search` (hybrid+rerank, ACL-filtered), `read_section`/`grep`/`tree` over
   parsed Markdown/HTML, plus a per-document llms.txt-style map. Humans get the same search with span citations.
5. Span-level citations + verification pass ("not in library" fallback). ~1 extra model call per answer.
6. Governance baked into the schema: RLS pre-filtering, classification + provenance per chunk, ingestion approval
   workflow, instruction-pattern scanner, audit log of retrieved chunk IDs per answer; vectors treated as confidential.
7. Eval from day one: 150–300 question golden set per domain, Ragas offline + CI gate, versioned index snapshots,
   parallel-table re-embed A/B.
8. Defer: ColPali/ColQwen, GraphRAG/LightRAG/HippoRAG (only Type-1 entity metadata now), Graphiti-style memory.

## Sources

- pgvector 0.8.0: https://www.postgresql.org/about/news/pgvector-080-released-2952
- VectorChord hybrid: https://blog.vectorchord.ai/hybrid-search-with-postgres-native-bm25-and-vectorchord ;
  MaxSim: https://blog.vectorchord.ai/vectorchord-03-bringing-efficient-multi-vector-contextual-late-interaction-in-postgresql ;
  1.1.1: https://pgxn.org/dist/vchord
- pg_textsearch 1.0: https://www.tigerdata.com/blog/pg-textsearch-bm25-full-text-search-postgres
- ParadeDB: https://www.paradedb.com/ ; comparison: https://www.web3aiblog.com/blog/postgres-vector-search-compared-pgvector-pgvectorscale-paradedb-lantern-2026
- Hybrid measured in Postgres: https://dev.to/devopsdaily/full-text-vs-pgvector-vs-hybrid-search-measured-50jj
- Rerankers: https://futureagi.com/blog/best-rerankers-for-rag-2026/ ; https://aimultiple.com/rerankers
- Qwen3-Embedding: https://github.com/QwenLM/Qwen3-Embedding ; https://huggingface.co/Qwen/Qwen3-Embedding-8B ; https://arxiv.org/abs/2506.05176
- TR-MTEB: https://aclanthology.org/2025.findings-emnlp.471.pdf ; TR-TEB: https://www.researchgate.net/publication/407438143_TR-TEB_Turkish_Text_Embedding_Benchmark
- jina v4: https://huggingface.co/jinaai/jina-embeddings-v4 ; v5-text: https://www.elastic.co/search-labs/blog/jina-embeddings-v5-text
- MILCO (ICLR 2026): https://proceedings.iclr.cc/paper_files/paper/2026/file/4d803b886406e5ad11a7b5c1776b859b-Paper-Conference.pdf
- ColPali: https://mixpeek.com/curated-lists/best-visual-document-retrieval-models ; https://arxiv.org/abs/2506.04997
- Contextual Retrieval: https://www.anthropic.com/news/contextual-retrieval ; chunking eval: https://arxiv.org/abs/2504.19754 ;
  https://www.splunk.com/en_us/blog/artificial-intelligence/chunking-techniques.html
- Parsing: https://www.spheron.network/blog/self-host-document-intelligence-docling-marker-mineru-rag-guide/ ;
  https://themenonlab.blog/blog/best-open-source-pdf-to-markdown-tools-2026 ; OmniDocBench https://arxiv.org/abs/2412.07626 ;
  Docling https://arxiv.org/abs/2501.17887
- Graph RAG: https://www.paperclipped.de/en/blog/graph-rag-production/ ; https://arxiv.org/abs/2506.05690 ;
  https://arxiv.org/abs/2502.14802 ; https://arxiv.org/abs/2502.11371
- Memory: https://vectorize.io/articles/mem0-vs-zep ; https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026
- Agentic/grep: https://pageindex.ai/blog/claude-code-agentic-rag ; https://akitaonrails.com/en/2026/04/06/rag-is-dead-long-context/ ;
  https://github.com/upstash/context7 ; https://www.trychroma.com/research/context-rot ;
  https://www.sitepoint.com/long-context-vs-rag-1m-token-windows/
- Agentic RAG research: https://arxiv.org/abs/2606.21553 ; https://arxiv.org/abs/2602.03442 ; https://arxiv.org/abs/2603.07379 ;
  https://github.com/yoloshii/gigaxity-deep-research
- Evaluation: https://www.premai.io/blog/rag-evaluation-metrics-frameworks-testing-2026/ ; https://qaskills.sh/blog/rag-regression-testing-guide ;
  https://arxiv.org/abs/2311.09476 ; https://arxiv.org/abs/2608.21558
- Citations: https://claude.com/blog/introducing-citations-api ; https://freeacademy.ai/lessons/notebooklm-grounded-qa-citations ;
  https://arxiv.org/abs/2609.05802 ; https://arxiv.org/abs/2605.06635 ; https://arxiv.org/abs/2504.18225
- Security: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html ;
  https://predictionguard.com/blog/rag-security-indirect-prompt-injection-and-knowledge-base-poisoning ;
  https://arxiv.org/abs/2608.11730 ; https://arxiv.org/abs/2504.00147 ; https://arxiv.org/abs/2607.26339 ;
  https://medium.com/@michael.hannecke/implementing-row-level-security-in-vector-dbs-for-rag-applications-fdbccb63d464
