# Kütüphane guide

This guide is the user and operator documentation of Kütüphane. It describes the code on `main`. The design
documents (`docs/01`–`docs/24`) explain why; this guide explains how.

## Reading order

| If you are | Read |
|---|---|
| new to Kütüphane | the `README.md` quick start, then `concepts.md` |
| an operator | `install.md`, `operations.md`, `security.md`, `troubleshooting.md` |
| an orchestrator builder | `concepts.md`, `agent-memory.md`, `mcp.md` |
| an integrator (RAG platform, scripts) | `concepts.md`, `http-api.md` or `mcp.md` |
| a content owner | `kstd.md`, then the ingest section of `operations.md` |
| a curator | the curation sections of `agent-memory.md` and `operations.md` |

## Pages

| Page | Content |
|---|---|
| [concepts.md](concepts.md) | books, content versions, profiles, passages, journals, notes, links, Standing, origin, rights, grants, delegation, `activate` |
| [install.md](install.md) | development install, light install (no LLMDAP), full stack, local models overlay, database roles, reboot, upgrade |
| [operations.md](operations.md) | the CLI: ingest, index, search and ask, grants, journals, curation, outcomes, decision export, code repositories, packages, audit, backups |
| [mcp.md](mcp.md) | the MCP endpoint, protocol versions, authentication, every tool, background jobs, idempotency |
| [http-api.md](http-api.md) | every HTTP route |
| [security.md](security.md) | threat model, gates, origin rules, curation boundary, git confinement, LLMDAP, egress, audit records |
| [kstd.md](kstd.md) | the `kstd.yaml` manifest and its effects; the decision rule |
| [agent-memory.md](agent-memory.md) | a how-to for orchestrators: propose, query, neighbours, code citations, outcomes, rollback |
| [troubleshooting.md](troubleshooting.md) | messages and their fixes |
| [changelog.md](changelog.md) | user-facing changes, newest first |

## Design sources

| Document | Content |
|---|---|
| `../01-direction-decisions.md` | the operator decisions (D1–D75) |
| `../23-vision-v1.md` | the vision and the five promises |
| `../24-r1-agent-memory-design.md` | the agent memory contract (R1, R2) |
| `../09-ontology-v2.md` | the ontology: blocks, facets, Standing |
| `../11-standard-draft.md` | the kstd specification draft |
| `../07-m1-definition.md` | the acceptance tests AT-01 to AT-15 |

## Keep the guide current

Each feature PR updates the pages that it changes and adds an entry to `changelog.md` (D75). See
`CONTRIBUTING.md`.
