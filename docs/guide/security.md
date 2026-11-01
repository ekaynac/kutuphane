# Security model

This page describes what Kütüphane protects, against whom, and how. The design sources are `../07-m1-definition.md`
(the acceptance tests AT-01 to AT-15), `../24-r1-agent-memory-design.md` §5, §8, §10–§12 and the decisions in
`../01-direction-decisions.md`.

## Threat model

| Threat | Example | Control |
|---|---|---|
| An agent reads a book that it may not read | a search that returns passages, ranks or counts of other books | the gate decides `read` before the query and again before delivery |
| A right is revoked during a request | a delegation ends while an answer runs | the final decision runs again at the delivery point; a lost book refuses or reruns |
| An agent passes as a person | an agent writes "accepted by Ayşe" | origin from the write path (D70); Standing only by the curator credential or a person's passkey act |
| An agent approves its own notes | an agent calls a curation tool | no MCP tool and no HTTP route of Core changes Standing; curator web takes no token and needs a passkey with user verification for each act |
| A phishing page asks for a passkey signature | another tailnet node, another port, an iframe | the RP ID is the full host name, the origin is compared exactly, cross-origin and framed ceremonies are refused |
| Restricted text reaches a model | `ai_input: n` text in an embedding or an answer prompt | the `ai_input` gate before every embed, rerank and answer |
| Text leaves the machine | a `local_only` book on a cloud route | the egress check in Core, LLMDAP policy, internal networks |
| Prompt injection in sources | a document says "ignore your instructions" | the answer prompt treats passages as source text only; agent instructions need `activate`; a skill that SkillSpector blocks is refused to agents |
| A credential is indexed | an API key in an ingested file or a note | the secret scan refuses the book or the note |
| A poisoned note spreads | agents derive notes from a false finding | `kutuphane note rollback` retires the whole `derived_from` closure and reports every use |
| A git mirror is a trap | alternates, grafts or config that make git read other files or run commands | the repository confinement checks |
| A forged token | a token from another issuer | the issuer is compared exactly; the JWKS is pinned per issuer |
| A consumer's issuer names our people | an application IdP signs a token for `user:<curator>` | each extra issuer is bound to its principal prefixes, both ways; `curate` is refused to its principals by default |

Out of scope: the host and its administrators, the database owner credential, disk encryption (a deployment duty,
D48), and execution of agent instructions after `activate` (that belongs to the agent host).

## Identity

- The IdP issues every token. Kütüphane stores no client secret and accepts no static API key.
- The verifier checks the signature against the JWKS file (`KUTUPHANE_OIDC_JWKS`), the audience and the issuer.
  The issuer is compared as an exact string. The protected-resource metadata advertises the same string. The
  server refuses to start when the MCP SDK would rewrite the issuer.
- More issuers (`KUTUPHANE_OIDC_ISSUERS`, #157) each have their own exact issuer, audience and JWKS, and principal
  prefixes. A token may name only the principals of its own issuer: those under its prefixes for an extra issuer,
  and those under no extra issuer's prefix for the primary one. `kutuphane grant … curate` refuses a principal of an
  extra issuer unless its entry says `"curate": true` ([operations.md](operations.md#more-than-one-token-issuer)).
- A caller's correlation id (`X-Correlation-Id`, #156) is a label in the audit records only. It never decides a
  right or an idempotency key.
- The principal is `user:<sub>`. A token with `kutuphane/principal_type: agent` gives `agent:<sub>`. A token with
  `act.sub` is that agent acting for the user `sub`.
- `client_id` (else `azp`) is recorded with each write. It never changes rights or origin.
- `_meta.clientInfo` of an MCP request is not authenticated. It is never used.

## The gate

Every path that gives out content goes through one gate (`src/kutuphane/gate.py`):

1. **Before the work:** one decision for every book that the request needs.
2. **At delivery:** the same decision again. A book that the caller lost meanwhile drops out. A read runs once
   more; if the rights change again, it refuses (HTTP 409 "authorization changed during the request; retry").
3. **Logging:** every decision, allowed or refused, is an `access_event` row with the policy, the grants, the
   delegation and the items delivered.

Rights are decided per call. A grant is expired at its expiry instant. An agent that acts for a person needs a live
delegation and the person's own current right; losing either one refuses the next call.

A book that the caller cannot read gives the same empty result as a book that does not exist. A scope filter never
adds a book.

## Text gates

| Gate | Rule |
|---|---|
| `ai_use.search` | not `y`: the file or note is not indexed and not in text filters |
| `ai_use.ai_input` | not `y`: no embedding, no rerank, not in an answer prompt; model readers get `text: null` and `withheld` |
| `ai_use.train` | not `y`: a decision export has only hashes |
| `activate` | an agent gets agent-instruction passages only with `activate` on the book; each delivery is logged. A skill that a scan blocks is refused to agents even with `activate` (see below). MCP Skills (`skills/list`, `skills/get`, `skill://` reads) need `read` and `activate` for every principal, people too |
| personal data | `export` of a file with `personal_data` not `no`/`synthetic` needs `--legal-basis` (DPV codes) |

In a manifest, an absent term is "not stated" and counts as `n`. A file with no manifest follows its book policy
only. Note rights follow derivation and the current state of every journal in the closure.

## Origin rules (D70)

The server computes the origin of a note from the authenticated write path:

| Path | Origin |
|---|---|
| `agent:` principal, an agent acting for a user, or the MCP channel | `model` |
| a `user:` principal, no `act`, over HTTP | `unknown` (handled as `model`) |

A writer can ask for a lower value. A claim of `human`, `assisted` or `tool` is refused with
`origin_notice: origin-claim-refused`, and the computed value is stored. No write path stores `human`: only a person
gives it, with a passkey `confirm` act in curator web bound to the note digest (D70 R3). The confirm page and its act
options check the person's direct `read` on the book of the reference before they look up the note, so a person
without it gets one refusal whatever the note's state. A live confirmation is replaced only by its confirmer: another
person (also through a new request for the same bytes) is refused until the confirmer withdraws it (R7; a trigger of
migration 029).

## Curation boundary

- Only the database owner role, and the curator web role for a signed act, can insert Standing events. The app role
  (`kutuphane_app`, used by the server) cannot (`deploy/db-roles.sql`).
- `kutuphane note standing`, `kutuphane note rollback`, `kutuphane skill clear`, `kutuphane curator …` and
  `kutuphane grant … curate …` need `KUTUPHANE_CURATOR_DSN`. The named curator must hold `curate` on the book now.
  `curate` is for users only, granted directly, never delegated.
- The database enforces this too: a row-level security policy on `grant_tuple` (`deploy/db-roles.sql`) refuses a
  live `curate` row from the app role. The app role can still revoke or delete one.
- The CLI trusts its operator. So the curator credential is the boundary. An agent that can read it can curate as
  any user. Keep it out of every environment that an agent can read.
- `kutuphane note expire` writes system events with no curator, also with `KUTUPHANE_CURATOR_DSN`. The database
  accepts a system event without a cause only with the reason `expired`, on an `evidence` note, and only as
  `pending` → `rejected` (never approved) or `approved` (or `pending` after an approval) → `retired` (migration
  049). The system only tightens.
- Memory rows (`note`, `write_record`, `note_link`, `note_citation`, `outcome`) are append-only for the app role.
  The citations and the creation links of a note are part of its id: the database writes them only in the
  transaction that writes the note (migration 039). So a later insert cannot change a note that a person confirmed
  or approved. Readers and `curator verify-acts` also compare the parts with the signed id.
- Skill scan records are append-only for the app role (it can only mark a record `stale`). The app role cannot
  write a skill clearance, so it cannot lift a block.
- Every database function and trigger fixes its search path to `pg_catalog, public, pg_temp` and names its tables
  with their schema (migration 038). The role scripts take the right to make temporary tables (`TEMP`) from
  `PUBLIC` and from the app and curator web roles. So a role cannot hide a table or a sequence that a check
  reads behind a temporary one.

## Curator web and passkeys (D72)

Curator web (`kutuphane curator web`) is the phone page of the curator. Design: `../25-curator-queue-passkey-design.md`.

- **Its own process, role and host.** It runs as `kutuphane_curator_web` (`deploy/db-roles-curator.sql`), in its own
  container on its own internal networks; Core cannot reach it. It has no MCP, takes no bearer token and serves no
  book file. A Tailscale sidecar gives it its own host name with HTTPS; Funnel stays off.
- **Enrollment.** Only the owner credential makes a curator and a one-time code (`kutuphane curator enroll`, 15
  minutes, one passkey). Registration needs user verification. The curator web role cannot make a person or an
  enrollment, and cannot revoke or un-revoke a passkey. An enrollment session registers only for its own code; the
  owner can cancel an unused code (`curator cancel-enrollment`).
- **The act.** Each decision is a WebAuthn assertion with user verification over a stored statement: the challenge
  is `SHA-256("kutuphane/curator-act/v1\n" ‖ canonical JSON)` of the action, the note references and digests, the
  Standing in force, the new values, the reason, a fresh 32-byte nonce and the expiry (5 minutes). One act per
  challenge, in the same session. The database accepts a Standing event of the web role only as an item of its
  act's statement, with `set_by` = the signer (migration 023: keys, a trigger and row-level security). When the
  approval of a rule retires the rules that it supersedes, the statement lists them (`retires`); the act writes
  exactly those, and the database accepts a system event caused by an act only as a `retired` event of a listed
  note, in the same transaction (migration 026).
- **Checks of every ceremony.** The exact origin and the full-host RP ID; user verification; no `crossOrigin` and no
  `topOrigin`; the signature counter must increase when it is not 0. The note digest is computed again from all its
  stored parts before a person sees or signs it. Rights and the Standing in force are decided again in the act
  transaction.
- **Session.** A passkey login gives a `__Host-` cookie (`Secure`, `HttpOnly`, `SameSite=Strict`), 8 hours, no
  renewal. A session shows the pending notes; only an act changes anything. A session names the passkey of its
  login: when that passkey is revoked, the session ends (`curator end-sessions` ends all sessions of a person). Every state-changing request needs this
  origin and JSON.
- **Trusted base and limits.** Curator web is in the trusted base, as the CLI host is: the authenticator does not
  show the statement, so the page that shows it also chooses what the person signs. `kutuphane curator verify-acts`
  finds rows that no stored passkey signed; it cannot find a signature given over a misleading page. A passkey
  proves who confirmed, not that the person read the text.

## Delegated curate (D73), removed

Delegated curate and the decider runner are removed (2026-11-01). Only a person approves a note: on the phone with a
passkey act, or with the owner credential. The tables of migration 025 stay as history; no Kütüphane role writes
them (`deploy/db-roles.sql` and `deploy/db-roles-curator.sql` revoke the writes), and curator web refuses the
`delegate` and `end_delegation` actions.

## Skill scan (SkillSpector)

SkillSpector (D71) is an optional, external static scanner of skill folders. Kütüphane runs it as a subprocess
from its own environment. It never imports, copies or ships it. Install and commands: [operations.md](operations.md).

**What blocks `activate`.** For an agent, every file of a skill folder is refused when a scan of that folder:
- recommends `DO_NOT_INSTALL`;
- did not cover the whole skill (completeness is not `complete`);
- failed (a crash, a timeout, output that is not a valid report, or a report of another version). A failed scan
  blocks, so a skill cannot escape the scan when it breaks the scanner. A report is untrusted input: a report
  larger than 8 MiB, nested deeper than 64 levels, or with a value that cannot be stored (a NUL character, a lone
  surrogate, NaN or infinity) is a failed scan too, and the ingest continues.

The block applies to `read_document`, `kutuphane read`, `open_citation`, agent search (the passages are left out
before ranking), `ask_library`/`reopen_answer` for agents, and MCP Skills: a skill with a blocked file is not in
`skills/list`, and `skills/get` and `resources/read` refuse it, also a skill that holds a blocked skill in a
subfolder ([mcp.md](mcp.md#10-skills-sep-2640)). It is in force in the same transaction that publishes the version.
Each refusal is an `access_event` (`activate`, refused, "skill blocked by a scan"). The last rights check before a
delivery and the block check are one database statement, so a change between them (for example, a right revoked and
a block cleared in one transaction) cannot give a delivery.

**The block follows the bytes.** A block belongs to the skill's files (the input digest), not to one version of
the book. When a new version of the book has the same skill files, every block that is not cleared is copied
to the new version (`carried_from` in `kutuphane skill show`), also when the new scan says `SAFE`, the scan
failed before, or no scanner is configured now.

**Notes derived from a blocked skill.** A note that cites a passage of a blocked skill, or that is derived
(`derived_from`, at any depth) from such a note, is handled as a note with `ai_input: n` for model readers (agents
and MCP callers): `query_notes`, `neighbours`, a note in `open_citation`, and the candidates of `propose_note`
give `text: null` and `withheld: "derived from a skill blocked by a scan …"`; the note itself stays listed. The
decision export withholds the text, the options and the choice for every reader. People who read over HTTP still
get the text, as for `ai_input`. When a curator clears the block, the text is shown again.

**What does not block.** `SAFE` and `CAUTION` give no right: an agent still needs `activate`. `not_scanned` (no
SkillSpector configured, or a version that is not allowed) does not block; the operator can still decide otherwise.

**Only a person lifts a block.** A scan is a proposal (origin `tool`), never an approval. A later scan never lifts a
block, also when it says `SAFE`. A curator with `curate` lifts it with `kutuphane skill clear`; the clearance is
recorded and covers only those bytes and that report.

**Environment and egress.** SkillSpector runs with `--no-llm` and only `PATH`, `HOME` (an empty temporary folder)
and `LANG`: no provider keys, no `LANGSMITH_*`, no Kütüphane variables. Its supply-chain check (SC4) sends the
dependency names that a skill declares to `api.osv.dev`, also with `--no-llm`. To block this, set
`KUTUPHANE_SKILLSPECTOR_PROXY=http://127.0.0.1:9` (a dead port); SC4 then uses its bundled list. To allow it, give a
proxy that permits only `api.osv.dev`. Without the variable, the egress follows the network of the host that runs
the scan.

**Supply chain.** `deploy/skillspector/install.sh` installs only the pinned version, from the tag tarball with a
known sha256. It installs the dependencies from the upstream lock and the build backend (hatchling and its
dependencies, `deploy/skillspector/build-requirements.txt`) as wheels only, with hash checks, and then builds
SkillSpector with that backend, without build isolation. No step gets a package that has no hash. Use Python 3.12
or 3.13: a pinned dependency (yara-python) has no wheel for 3.14, and the installer builds nothing from source.
SkillSpector is one layer, not proof: it does not read images or binaries, and attacks against it are researched.

## MCP Skills and handling labels (#80)

- **Skills over MCP (SEP-2640).** Skill folders reach a model through `skills/list`, `skills/get` and
  `resources/read` of `skill://` URIs with the same whole-skill gate as `read_document`: `read` and `activate` for
  every principal, `ai_input` for every file of the skill, and no blocked file in the skill, a blocked skill in a
  subfolder included. `read_document` applies the same rule to a file in a skill folder (security review #18). The
  list and the entries hold the frontmatter and the digests only; a file goes out only on its own `resources/read`.
  A refusal inside the fetch (`ai_input`, not found) is in `access_event` too. HTML, JavaScript, SVG and XML go out
  as `text/plain` (or `application/octet-stream`), so a host does not render or run them; the digest does not
  change. The digests are the SHA-256 of the stored bytes (the content manifest), but the same server gives the
  digests and the bytes: a host must not take a digest match as proof of trust (SEP-2640). Treat skill content as
  untrusted model input. Details: [mcp.md](mcp.md#10-skills-sep-2640).
- **Handling labels.** `search_library`, `open_citation`, `read_document`, `query_notes` and the skill reads give
  the Sensitivity and Egress of each book in the result, the strictest of them, and the skill-scan records that
  apply, in `_meta["kutuphane/handling"]` ([mcp.md](mcp.md#44-handling-labels-in-_meta)). A note's label names
  only the source books that the caller may read; the others count only in `unnamed_sources` and in the strictest
  values. The labels inform the client; the server still enforces Egress itself (LLMDAP, `local_only`) and
  Sensitivity (export). They are not a right and not a proof.
- **Hidden markdown comments.** No passage holds an HTML comment of a markdown file (a reader of the rendered file
  never sees it), except the leading one-line source comment of a rule file, which is a citation
  ([concepts.md](concepts.md)). The cut is linear in the file size: a file of many comments cannot stall an ingest.

## Secret scan

`ingest`, `kstd-init`, `kstd-check`, package receipt and `propose_note` scan the text:

- credential-like file names (`credentials.json`, `*.env`, `id_rsa`, key stores, `settings.local.json`);
- credential-like text (keys, tokens, passwords, private key blocks), also in extracted HTML and PDF text, JSON
  values and quoted literals.

A finding refuses the whole book or the note. The error names the path, the line and the rule, never the matched
text. Placeholders (`${PASSWORD}`, `<your-key>`, `changeme`) are not credentials. A reviewed false positive in a file
can be accepted with `--accept-finding <path>@sha256:<digest>:<rule>`. The acceptance covers exactly that file
content and is recorded in the publication. Package receipt accepts nothing.

`ingest`, `kstd-init` and `kstd-check` also look for personal data and fleet data: private IP addresses, e-mail
addresses, phone numbers and the names of a `--deny-names` file. These findings never show the matched text and do
not refuse a `local_only` book: they are recorded in the publication, and `kstd-init` proposes
`personal_data: unknown`. A `cloud_ok` book refuses an open finding in a file that can go to a model
([operations.md](operations.md#personal-data-and-fleet-data-findings)).

`kstd-init --source-repo` runs git read-only on a local repository: no transport (`protocol.allow=never`), no lazy
fetch of a partial clone, no replace refs, no fsmonitor, no signature check, and no search above the given folder.

## Git confinement

Code citations read bare mirrors that an administrator registers (`kutuphane repo add`). Kütüphane never fetches.

- The mirror is inside `KUTUPHANE_REPO_ROOTS`, with no symlink in its path. Compose mounts it read-only.
- The repository is bare and has no `commondir`, no `info/grafts`, no alternates and no promisor pack.
- Its `config` has only allowed keys: plain `core.*` keys, `extensions.objectformat`, and `remote.<name>.url`,
  `.fetch`, `.mirror`. Any other key (`include.*`, `core.alternateRefsCommand`, …) refuses the repository.
- git runs with no shell, an empty environment, no system or global config, no replace objects, no grafts, no lazy
  fetch and no protocols, with a 5 s limit per command.
- Only commits that a registered ref pattern reaches can be cited. An object in the store that no ref reaches (for
  example a force-pushed secret) is `unverifiable: commit_not_published`.
- No result contains code text. Files over 2 MiB and binary files are `unverifiable`.

## Model calls (LLMDAP)

- Core reaches a model only through the LLMDAP bridge. Core authenticates with its own subject key
  (`KUTUPHANE_LLMDAP_KEY`); no header can claim another subject.
- The person served travels as the `x-llmdap-for-subject` label. Each call has a call id that joins Core's
  `model_call` row and LLMDAP's signed audit chain.
- Every attempt is a `model_call` row, also a call that the egress check stopped before it was sent.
- Before a call, Core checks the egress of every source book now. A `local_only` book never goes to a route whose
  class is `cloud` (`KUTUPHANE_LLMDAP_ROUTE_CLASS`, `_EMBED_ROUTE_CLASS`, `_RERANK_ROUTE_CLASS`).

## Egress (network)

- `db`, `web`, `gateway`, `models`, `curator-db` and `curator` are internal compose networks with no route out. Core
  is on `db`, `web` and `gateway` only.
- Only the ingress publishes a port. Only LLMDAP reaches the model servers. LLMDAP's network `outbound` is internal
  too; `KUTUPHANE_LLMDAP_OFFLINE=false` (a hosted decision model) gives it a way out, and each hosted call still
  needs an `llm:egress` grant.
- `deploy/egress_probe.py` proves it from inside Core: no default route, outside names do not resolve, forbidden
  addresses refuse a connection.
- SkillSpector sends dependency names to `api.osv.dev` unless you block it (see "Skill scan" above).

## Web and HTTP

- Every response has a strict Content Security Policy (`default-src 'none'`, only this origin), `nosniff`,
  `no-referrer` and `X-Frame-Options: DENY`.
- The UI shows model output as plain text. Only `[n]` becomes a button.
- The ingress terminates TLS in a real installation and limits a request body to 1 MiB.

## Signed packages

Packages move a book between installations. A package is a tar with a canonical manifest and an Ed25519
signature. The receiver keeps it in quarantine, checks the key (trusted and not revoked), the signature, every
digest, the content id and the sequence, and scans it again. Nothing is published until a person runs
`approve-import`, and the receiver's own policy applies.

## Audit records

| Record | Where | Content |
|---|---|---|
| `access_event` | Postgres | every gate decision: who, for whom, action, book, mode, allowed, reason, policy, grants, delegation, content version, items |
| `model_call` | Postgres | every model call attempt: call id, principal, route, model, source books, status, error |
| `write_record` | Postgres | every note write and link: principal, on behalf of, client id, channel, origin |
| `standing_event` | Postgres | every Standing change: curator or system, reason, cause |
| LLMDAP audit | the `llmdap-audit` volume | the signed chain on the gateway side; back it up |

`kutuphane explain <correlation-id> --llmdap-export <file.jsonl>` joins Core's records with the LLMDAP export. A
model call that Core made and LLMDAP did not record is reported as missing. See `operations.md`.
