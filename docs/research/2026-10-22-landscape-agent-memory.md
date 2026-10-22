# Agent memory and agent knowledge: landscape report

I checked these sources on 2026-10-22. Participant counts come from the W3C API.

## 1. W3C AI Agent Memory Interoperability CG, with `draft-saihm-memory-protocol`

1. **Type and status:** This is a W3C Community Group. It was proposed on 2026-05-18 and launched on 2026-06-03. Charter v1.0 was adopted on 2026-06-19. The chair is Russell Jackson, who also writes the draft and maintains the SAIHM implementation. The group has about 36 participants, and its mailing list is very active in October 2026. A call for consensus on charter v1.1 closes on 2026-11-02. [Group page](https://www.w3.org/groups/cg/ai-agent-memory-interop/) · [Charter](https://www.w3.org/community/ai-agent-memory-interop/2026/07/16/charter-ai-agent-memory-interoperability-community-group-v1-0/) · [List](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/)
   - The group references the draft but does not write it. [`draft-saihm-memory-protocol-03`](https://datatracker.ietf.org/doc/draft-saihm-memory-protocol/) was posted on 2026-10-11 as an individual I-D with no stream. The Independent Submission stream stopped its review on 2026-07-25 ([chair's note](https://www.w3.org/community/ai-agent-memory-interop/2026/07/29/status-ietf-independent-submission-concluded-charter-2-1-de-confliction-lifts/)).
2. **Scope:** The group works one layer above the draft. It will make interoperability profiles, a use-case catalogue, test vectors and a regulatory crosswalk (GDPR Art. 17, AI Act, NIST, ISO 42001). The draft defines these parts:
   - a **cell**: `<cellId, holderId, kekVersion, tier, cellNonce, ciphertext, signature, timestamp>`, signed with ML-DSA-65;
   - a public audit log of receipts;
   - sharing contracts (TEMPORARY, PERMANENT, SYNDICATE). Revocation applies to future reads only;
   - two erasure classes, cryptographic and access-control;
   - eight MCP tools.
   - The cell has **no** fields for origin, license, inputs or personal data. Its "governance" tools are for votes on token parameters, not for knowledge policy.
3. **Open questions:**
   - A `derived-from` field, so that erasure reaches the agent's own notes ([0017](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0017.html)).
   - Retention in the cell or in policy, revision identity, and immutability.
   - A citation form for external sources. The chair proposes the minimum fields id, digest, IRI and licence ([0022](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0022.html)).
   - **"Imported memory is evidence, not an automatic grant of authority."** This comes from Matthew Hinkle's case, and it includes a test vector: an authorization, its revocation and a conflict.
   - Which bytes the citation digest covers ([0035](https://lists.w3.org/Archives/Public/public-ai-agent-memory-interop/2026Oct/0035.html)).
4. **Tests and data:**
   - Six use cases. A working draft is due on 2026-10-30.
   - [agmi](https://github.com/tech4biz-yasha/agent-memory-integrity) (MIT) applies 9 tamper attacks to 18 stores. Its draft is [`draft-khandelwal-bmwg-agent-memory-integrity-02`](https://datatracker.ietf.org/doc/draft-khandelwal-bmwg-agent-memory-integrity/).
   - [saihm-mcp](https://github.com/SAIHM-Admin/saihm-mcp) (Apache-2.0).
   - A related draft is [`draft-besleaga-agentic-knowledge-wellknown-01`](https://datatracker.ietf.org/doc/draft-besleaga-agentic-knowledge-wellknown/). It defines `/.well-known/knowledge-linkset`, digest-pinned artefacts and deterministic chunk IDs. It grants no rights.
5. **Overlap with kstd:**
   - *Covered:* the content-addressed unit, the signed receipt, erasure classes and the reach of a revocation. Our `disposition` should reuse their erasure-class vocabulary.
   - *Conflict:* their unit is one encrypted, opaque cell held by a custodial operator. Our unit is an artifact plus separate statements. Their revocation does not reach copies that a grantee already received. We record unresolved copies.
   - *Gap:* rights, `ai_use`, origin, legal basis, acceptance, contest, a decision rule and status freshness. The threads ask for many of these.
6. **How to take part:** You need a free W3C account and the W3C CLA. The IPR mode is royalty-free.
   - **First contribution:** two use-case entries before 2026-10-30, written as kstd decision-rule cases:
     - an imported loosening statement from an untrusted issuer → `escalate` or `deny`;
     - the reach of a derived-from erasure.
   - Also reply to the citation-fields thread.

## 2. IETF Agent Communication Protocols WG (agentproto)

1. **Type and status:** IETF Working Group. The [charter](https://datatracker.ietf.org/doc/charter-ietf-agentproto/) was approved on 2026-10-08, and the responsible AD is Charles Eckel.
2. **Scope:** dialog identifiers, lifecycle and context propagation, a reference architecture, and use cases. Dialog context explicitly **excludes** "conversation memory, retrieved documents, or prompts". Audit data structures are also out of scope.
3. **Our areas:** agent identity separate from user identity, revocation of an agent's access, and personal data in the dialog context.
4. **Tests and data:** none yet.
5. **Overlap with kstd:** none on knowledge. A kstd `use` receipt could carry a dialog ID.
6. **How to take part:** The mailing list is open. **First contribution:** a use case that shows a receipt correlated with a dialog ID.

## 3. W3C AI Agent Protocol CG and other W3C agent groups

1. **Type and status:** W3C Community Group with about 231 participants. The chairs are Gaowei Chang and Song Xu. Meetings are bi-weekly; the latest was on 2026-10-21. [Repo](https://github.com/w3c-cg/ai-agent-protocol) · [Spec draft](https://w3c-cg.github.io/ai-agent-protocol/protocol.html)
2. **Scope:** discovery, identity (`did:wba`), description, and security and privacy. The current work is an authorization proposal ([PR #46](https://github.com/w3c-cg/ai-agent-protocol/pull/46)) that combines DIDs, Verifiable Credentials and OAuth. The minutes say that a W3C "Agentic Web Working Group" charter is in drafting and that the group is not established.
3. **Our areas:**
   - [Issue #36](https://github.com/w3c-cg/ai-agent-protocol/issues/36) (memory, provenance, contested claims) is open. On 2026-09-10, user `chgaowei` (I think this is the co-chair) answered that this is an "application-level protocol".
   - [Issue #34](https://github.com/w3c-cg/ai-agent-protocol/issues/34) (evidentiary provenance gap) is open.
4. **Tests and data:** `tests/test_identity_documents.py`. I did not verify the license.
5. **Overlap with kstd:** identity of issuers and agents can be reused for kstd signers. Knowledge governance is a gap there.
6. **How to take part:** W3C account and CLA, then GitHub issues. **First contribution:** in #36, propose kstd statements as a candidate application-level profile.

**Other W3C groups** (all exist and are open):
- [Cognitive AI CG](https://www.w3.org/groups/cg/cogai): chairs Dave Raggett and Ronald Reck. The list had 9 messages in October 2026. Low relevance.
- [Procedural Memory KR CG](https://www.w3.org/community/pm-kr/): launched 2026-02-23, about 27 participants. I did not verify its chair or any output.
- Semantic Agent Communication, Autonomous Agents on the Web, Agent Identity Registry, Agent Trust Protocol, and Agent Conformance and Benchmarking. These belong to the slices of other peers.

## 4. Model Context Protocol (MCP), at the Agentic AI Foundation

1. **Type and status:** MCP is a project of the Agentic AI Foundation (AAIF), which is part of the Linux Foundation. It was donated on 2025-12-09 ([LF press](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)). The latest spec is [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28). Other AAIF projects: goose, AGENTS.md, agentgateway, A2A and Agent Router.
2. **Scope:** host, client and server roles, with Resources, Prompts and Tools, plus extensions (Tasks, Skills, Apps).
   - Resource annotations are only `audience`, `priority` and `lastModified`.
   - MCP has **no memory primitive**. The proposals for one were closed: SEP-2072 "Memory Portals", the MIF SEP ([#2342](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/2342)), [#2681](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2681) and #2043.
3. **Open questions:** [SEP-1913 "Trust and Sensitivity Annotations"](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1913), from [#711](https://github.com/modelcontextprotocol/modelcontextprotocol/issues/711), is **open**. It proposes:
   - `sensitiveHint`, `privateHint`, `openWorldHint` and `attribution`;
   - deterministic propagation;
   - block, escalate or confirm. This is near our handling values and our `escalate`.
4. **Tests and data:** [modelcontextprotocol/conformance](https://github.com/modelcontextprotocol/conformance). GitHub lists its license as "Other"; I did not verify the terms.
5. **Overlap with kstd:**
   - MCP is the transport for `deliver`.
   - *Gap:* rights, origin and status on Resources.
   - *Possible conflict:* labels that are hints only, against our deterministic rule.
6. **How to take part:** GitHub, the SEP process, Working Groups and Discord. No membership is needed. **First contribution:** comment on SEP-1913 with the kstd handling values and `ai_use` as a structured `_meta` profile, and give test cases.

## 5. Agent2Agent (A2A)

1. **Type and status:** A2A became an AAIF Growth Stage project on 2026-08-17 ([AAIF blog](https://aaif.io/blog/a2a-joins-aaif)). The latest spec is [1.0.0](https://a2a-protocol.org/latest/specification/).
2. **Scope:** Agent Card discovery, Tasks, Messages, Artifacts made of Parts, and Extensions. The agents stay opaque: they do not share internal memory.
3. **Our areas:** Artifact version lineage is **explicitly outside the protocol**. It is a client task, and the docs suggest an `artifactId` in Part metadata.
4. **Tests and data:** [a2a-tck](https://github.com/a2aproject/a2a-tck) (Apache-2.0).
5. **Overlap with kstd:** none on knowledge governance. An A2A Extension could carry kstd statements with Artifacts.
6. **How to take part:** GitHub. **First contribution:** an A2A Extension draft for "kstd statements on Artifacts".

## 6. Agent Skills (agentskills.io) and the MCP Skills extension

1. **Type and status:** an open format, first developed by Anthropic. [Repo](https://github.com/agentskills/agentskills) (Apache-2.0). It is **not** an AAIF project. The MCP side is the [Skills extension, SEP-2640](https://modelcontextprotocol.io/community/working-groups/skills-over-mcp), which became Final on 2026-09-13. Its conformance scenarios were merged on 2026-09-11.
2. **Scope:** `SKILL.md` frontmatter (`name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`) and progressive disclosure.
3. **Open questions:**
   - Provenance and signature RFCs were closed (#358, #247). A contributor wrote in [#418](https://github.com/agentskills/agentskills/issues/418) that attestation belongs at the **distribution layer**.
   - Still open: `.well-known` with `digest` ([PR #254](https://github.com/agentskills/agentskills/pull/254)), versioning (#46) and the metadata type mismatch (#514).
4. **Tests and data:** the `skills-ref` validator.
5. **Overlap with kstd:**
   - kstd's activation permission and skill-folder artifact fit here directly, as an external attestation layer.
   - `license` is free text, not SPDX.
6. **How to take part:** GitHub and Discord. **First contribution:** on PR #254 and #46, propose kstd `item` and `acceptance` statements next to the digest.

## 7. AGENTS.md

1. **Type and status:** an AAIF project. [agents.md](https://agents.md/) says it is used by more than 60k repositories.
2. **Scope:** plain Markdown with no required fields. The nearest file wins, and the user's prompt overrides it.
3. **Our areas:** none (no provenance or trust fields).
4. **Tests and data:** the public AGENTS.md files on GitHub could be a corpus for tests. Their licenses vary per repository.
5. **Overlap with kstd:** the closest analogue to our L0 (`kstd.yaml` per folder), but it gives instructions, not rights.
6. **How to take part:** GitHub. **First contribution:** an issue that proposes to link a sibling `kstd.yaml` for rights and authority.

## Most important for us (ranked)

1. **W3C AI Agent Memory Interoperability CG.** Its open questions (derived-from, citation fields, revoked authority) are kstd rules.
2. **MCP, through SEP-1913 and Resources `_meta`.** MCP is the main delivery channel.
3. **Agent Skills.** Attestation was moved to the distribution layer, which is where kstd fits.
4. **W3C AI Agent Protocol CG.** It has the identity basis, and issue #36 is open.
5. A2A. 6. IETF agentproto. 7. AGENTS.md.

## Questions to ask them

1. Memory CG: Will the baseline profile carry rights (SPDX, `ai_use`), origin and personal-data or legal-basis fields per cell, or does it delegate them to an external statement layer that we could provide?
2. Memory CG: Will "imported memory is evidence, not authority" become a conformance rule with deterministic test vectors? Can our `permit`/`deny`/`escalate` cases serve as those vectors?
3. MCP maintainers: Should SEP-1913 labels be machine-enforceable (`escalate`/`deny`) or only hints? Would a typed `_meta` profile for rights and handling be accepted as an extension?
4. Agent Skills: Which distribution-layer mechanism is preferred for attestation (PR #254 digest, ai-catalog)? Could signed `acceptance` and activation statements attach to it?
5. AI Agent Protocol CG: If knowledge provenance is "application-level", will the CG host or reference an application profile for signed knowledge statements?