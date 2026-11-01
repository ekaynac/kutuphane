# Security model

Design and threat analysis: `../07-m1-definition.md` (AT-01 to AT-15), `../24-r1-agent-memory-design.md` §5, §8,
§10–§12, `../25-curator-queue-passkey-design.md`, `../01-direction-decisions.md`.

## Threat model

Threats: unauthorized reads, rights revoked mid-request, agents that pass as a person or approve their own notes,
passkey phishing, restricted text that reaches a model or leaves the machine, prompt injection, indexed
credentials, poisoned notes (`kutuphane note rollback` retires the `derived_from` closure and reports every use),
trap git mirrors, forged tokens, a consumer's IdP that names our people.

Out of scope: the host and its administrators, the database owner credential, disk encryption (D48), and execution
of agent instructions after `activate` (the agent host's duty).

## Identity

- The IdP issues every token; no client secret or static API key exists. The verifier checks the signature
  (`KUTUPHANE_OIDC_JWKS`), the audience and the exact issuer string (also advertised in the protected-resource
  metadata); the server refuses to start if the MCP SDK would rewrite it.
- Extra issuers (`KUTUPHANE_OIDC_ISSUERS`, #157) each have an exact issuer, audience, JWKS and principal prefixes.
  Their tokens may name only principals under their prefixes; primary tokens only principals under no extra prefix.
  `kutuphane grant … curate` refuses an extra issuer's principal unless its entry says `"curate": true`
  ([operations.md](operations.md#more-than-one-token-issuer)).
- `X-Correlation-Id` (#156) is an audit label only, never a right or an idempotency key.
- Principal: `user:<sub>`; `kutuphane/principal_type: agent` gives `agent:<sub>`; `act.sub` means the agent acts
  for that user.
- `client_id` (else `azp`) is recorded per write and never changes rights or origin. `_meta.clientInfo` is not
  authenticated and never used.

## The gate

One gate (`src/kutuphane/gate.py`) decides every content path: per needed book before the work, and again at
delivery. A lost book drops out; a read reruns once, and if rights change again it refuses (HTTP 409
"authorization changed during the request; retry"). Every decision is an `access_event` row.

Rights are decided per call; a grant expires at its expiry instant. An agent acting for a person needs a live
delegation and the person's current right. An unreadable book looks missing. Scope filters never add books.

## Text gates

- `ai_use.search` not `y`: the file or note is not indexed and not in text filters.
- `ai_use.ai_input` not `y`: no embedding, no rerank, not in an answer prompt; model readers get `text: null` and
  `withheld`. People on HTTP see the text of passages that they may read.
- `ai_use.train` not `y`: a decision export has only hashes.
- `activate`: an agent gets agent-instruction passages only with `activate` on the book; each delivery is logged.
  A scan-blocked skill is refused to agents even with `activate`. MCP Skills (`skills/list`, `skills/get`,
  `skill://` reads) need `read` and `activate` for every principal, people too.
- Personal data: `export` of a file with `personal_data` not `no`/`synthetic` needs `--legal-basis` (DPV codes).

An absent manifest term is "not stated" and counts as `n`. A file with no manifest follows its book policy only.
Note rights follow derivation and the current state of every journal in the closure. The answer prompt treats
passages as source text only.

## Origin rules (D70)

Origin comes from the authenticated write path: an `agent:` principal, an agent acting for a user, or the MCP
channel gives `model`; a `user:` principal without `act` over HTTP gives `unknown` (handled as `model`). A writer
can ask for a lower value; a claim of `human`, `assisted` or `tool` is refused with
`origin_notice: origin-claim-refused` and the computed value is stored. Only a person gives `human`, with a passkey
`confirm` act in curator web bound to the note digest (R3). The confirm page and act options first check the
person's direct `read` on the reference's book: without it, one refusal whatever the note's state. Only its
confirmer replaces a live confirmation; another person (also by a new request for the same bytes) is refused until
the confirmer withdraws it (R7).

## Curation boundary

- No MCP tool and no HTTP route of Core changes Standing. Only the owner role, and the curator web role for a signed
  act, insert Standing events; the app role (`kutuphane_app`) cannot (`deploy/db-roles.sql`).
- `kutuphane note standing`, `kutuphane note rollback`, `kutuphane skill clear`, `kutuphane curator …` and
  `kutuphane grant … curate …` need `KUTUPHANE_CURATOR_DSN`; the named curator must hold `curate` on the book now.
  `curate` is for users only, granted directly, never delegated. Row-level security on `grant_tuple` refuses a live
  `curate` row from the app role (it can still revoke or delete one).
- The CLI trusts its operator, so the curator credential is the boundary: an agent that reads it can curate as any
  user. Keep it out of every environment that an agent can read.
- `kutuphane note expire` writes curator-less system events (also with `KUTUPHANE_CURATOR_DSN`). The database
  accepts a causeless system event only with reason `expired`, on an `evidence` note, and only `pending` →
  `rejected` or `approved` (or `pending` after an approval) → `retired`. The system only tightens.
- For the app role, memory rows (`note`, `write_record`, `note_link`, `note_citation`, `outcome`) and skill scan
  records are append-only (a scan record can only be marked `stale`); it cannot write a skill clearance. A note's
  citations and creation links are part of its id and written only in its transaction; readers and
  `curator verify-acts` compare them with the signed id.
- Database functions and triggers use the search path `pg_catalog, public, pg_temp` and schema-qualified tables;
  the role scripts take `TEMP` from `PUBLIC`, the app and curator web roles.

## Curator web and passkeys (D72)

Curator web (`kutuphane curator web`, [install.md](install.md#curator-web)) runs as `kutuphane_curator_web`
(`deploy/db-roles-curator.sql`) on its own internal networks; Core cannot reach it. No MCP, no bearer token, no book
files; Funnel stays off.

- **Enrollment.** Only the owner credential makes a curator and a one-time code (`kutuphane curator enroll`, 15
  minutes, one passkey; cancel with `curator cancel-enrollment`). Registration needs user verification and
  registers only for its own code. The web role cannot make a person or enrollment, or (un-)revoke a passkey.
- **The act.** Each decision is a WebAuthn assertion with user verification over
  `SHA-256("kutuphane/curator-act/v1\n" ‖ canonical JSON)` of the action, note references and digests, the Standing
  in force, the new values, the reason, a fresh 32-byte nonce and the expiry (5 minutes); one act per challenge, in
  the same session. The database accepts a web-role Standing event only as an item of its act, with `set_by` = the
  signer; superseded rules are listed (`retires`) and only those are retired, in the same transaction.
- **Ceremony checks.** Exact origin, full-host RP ID, user verification, no `crossOrigin` or `topOrigin`, an
  increasing signature counter (when not 0). The note digest is recomputed before display; rights and Standing are
  decided again in the act transaction.
- **Session.** `__Host-` cookie (`Secure`, `HttpOnly`, `SameSite=Strict`), 8 hours, no renewal. Revoking the login
  passkey ends the session; `curator end-sessions` ends all of a person's sessions. State-changing requests need
  this origin and JSON.
- **Limits.** The authenticator does not show the statement, so curator web is in the trusted base, like the CLI
  host. `kutuphane curator verify-acts` finds rows no stored passkey signed, not a misleading page. A passkey proves
  who confirmed, not that the person read the text.

## Delegated curate (D73), removed

Delegated curate and the decider runner are removed (2026-11-01): only a person approves a note, by passkey act or
owner credential. The migration 025 tables stay as history: migration 050 refuses any write to them, drops the
decider read functions and revokes all rights of an existing `kutuphane_decider` role. Curator web refuses the
`delegate` and `end_delegation` actions; `verify-acts` still checks the stored ones.

## Skill scan (SkillSpector)

SkillSpector (D71) is an optional external scanner run as a subprocess; Kütüphane never imports or ships it
([install.md](install.md#optional-skillspector), [operations.md](operations.md)).

**What blocks `activate`.** For an agent, every file of a skill folder is refused when its scan recommends
`DO_NOT_INSTALL`, did not cover the whole skill (completeness not `complete`), or failed. Failed means a crash, a
timeout, an invalid or other-version report, a report over 8 MiB or nested deeper than 64 levels, or a value that
cannot be stored (NUL, lone surrogate, NaN, infinity); the ingest continues.

The block covers `read_document`, `kutuphane read`, `open_citation`, agent search (passages left out before
ranking), `ask_library`/`reopen_answer` for agents, and MCP Skills, from the transaction that publishes the version.
Each refusal is an `access_event` (`activate`, refused, "skill blocked by a scan"); the last rights check and block
check are one statement.

**The block follows the bytes.** A block belongs to the skill files (input digest), not a book version: a new
version with the same files gets every uncleared block copied (`carried_from` in `kutuphane skill show`), even if
the new scan says `SAFE`, failed before, or no scanner is configured now.

**Derived notes.** A note citing a blocked skill, or derived from one (`derived_from`, any depth), is
`ai_input: n` for model readers: `query_notes`, `neighbours`, `open_citation` and `propose_note` candidates give
`text: null` and `withheld: "derived from a skill blocked by a scan …"` (the note stays listed); the decision export
withholds text, options and choice for every reader. People on HTTP still get the text. Clearing the block restores
it.

**What does not block.** `SAFE` and `CAUTION` give no right (`activate` is still needed); `not_scanned` (no scanner
or a version not allowed) does not block. **Only a person lifts a block:** a scan is a proposal (origin `tool`);
no later scan lifts it, even `SAFE`. `kutuphane skill clear` by a curator with `curate` does, for those bytes and
that report only.

**Environment and egress.** It runs with `--no-llm` and only `PATH`, `HOME` (empty temporary folder) and `LANG`
(no provider keys, `LANGSMITH_*` or Kütüphane variables). Its SC4 check sends dependency names to `api.osv.dev`:
`KUTUPHANE_SKILLSPECTOR_PROXY=http://127.0.0.1:9` blocks this (SC4 uses its bundled list); an `api.osv.dev`-only
proxy allows it; unset follows the host network.

**Supply chain.** `deploy/skillspector/install.sh` installs only hash-checked inputs (pinned tarball, wheels from
the upstream lock and `deploy/skillspector/build-requirements.txt`) and builds nothing from source; use Python 3.12
or 3.13 (yara-python has no 3.14 wheel). SkillSpector is one layer, not proof: it skips images and binaries.

## MCP Skills and handling labels (#80)

- **Skills over MCP (SEP-2640).** `skills/list`, `skills/get` and `resources/read` of `skill://` URIs need `read`
  and `activate` for every principal, `ai_input` for every file, and no blocked file (subfolder skills included);
  a blocked skill is not listed and is refused. `read_document` applies the same rule to a skill file. Digests come
  from the same server as the bytes, so they are no proof of trust; treat skill content as untrusted. Media types
  and fetch rules: [mcp.md](mcp.md#10-skills-sep-2640).
- **Handling labels.** `search_library`, `open_citation`, `read_document`, `query_notes` and the skill reads give
  each book's Sensitivity and Egress, the strictest values and the skill-scan records in
  `_meta["kutuphane/handling"]` ([mcp.md](mcp.md#44-handling-labels-in-_meta)); unreadable source books are not
  named. Labels inform; they are not a right or a proof. The server still enforces Egress and Sensitivity.
- **Hidden markdown comments.** No passage holds a markdown HTML comment, except a rule file's leading one-line
  source comment ([concepts.md](concepts.md)). The cut is linear in file size.

## Secret scan

`ingest`, `kstd-init`, `kstd-check`, package receipt and `propose_note` scan for credential-like file names and
text, also in extracted HTML and PDF text, JSON values and quoted literals. A finding refuses the whole book or
note; the error names path, line and rule, never the matched text. `--accept-finding` accepts one reviewed false
positive for exactly that content; package receipt accepts nothing. Rules and placeholders:
[operations.md](operations.md).

Personal and fleet data findings (private IPs, e-mail addresses, phone numbers, `--deny-names`) never show the
matched text and do not refuse a `local_only` book: they are recorded, and `kstd-init` proposes
`personal_data: unknown`. A `cloud_ok` book refuses an open finding in a file that can go to a model
([operations.md](operations.md#personal-data-and-fleet-data-findings)).

`kstd-init --source-repo` runs git read-only: no transport (`protocol.allow=never`), no lazy fetch, no replace refs,
no fsmonitor, no signature check, no search above the given folder.

## Git confinement

Code citations read bare mirrors that an administrator registers (`kutuphane repo add`); Kütüphane never fetches.
A mirror must be inside `KUTUPHANE_REPO_ROOTS` (no symlink in the path; mounted read-only), bare, with no
`commondir`, `info/grafts`, alternates or promisor pack, and a `config` of only plain `core.*` keys,
`extensions.objectformat` and `remote.<name>.url`, `.fetch`, `.mirror` (any other key, such as `include.*` or
`core.alternateRefsCommand`, refuses it). git runs with no shell, an empty environment, no system or global config,
no replace objects, grafts, lazy fetch or protocols, and 5 s per command. Only commits a registered ref pattern
reaches can be cited; others (for example a force-pushed secret) are `unverifiable: commit_not_published`. No result
contains code text; files over 2 MiB and binary files are `unverifiable`.

## Model calls (LLMDAP)

- Core reaches a model only through LLMDAP with its own subject key (`KUTUPHANE_LLMDAP_KEY`); no header can claim
  another subject. The person served travels as the `x-llmdap-for-subject` label; a call id joins Core's
  `model_call` row and LLMDAP's signed audit chain.
- Every attempt is a `model_call` row, also one that the egress check stopped. Before a call, Core checks every
  source book's egress now: a `local_only` book never goes to a `cloud` route (`KUTUPHANE_LLMDAP_ROUTE_CLASS`,
  `_EMBED_ROUTE_CLASS`, `_RERANK_ROUTE_CLASS`).

## Egress (network)

- `db`, `web`, `gateway`, `models`, `curator-db` and `curator` are internal networks; Core is on `db`, `web` and
  `gateway` only. Only the ingress publishes a port; only LLMDAP reaches the model servers. LLMDAP's `outbound` is
  internal unless `KUTUPHANE_LLMDAP_OFFLINE=false` (hosted decision model); each hosted call needs `llm:egress`.
- `deploy/egress_probe.py` proves it from inside Core: no default route, no outside name resolution, forbidden
  addresses refuse. SkillSpector egress: see "Skill scan".

## Web and HTTP

- Every response has a strict Content Security Policy (`default-src 'none'`, only this origin), `nosniff`,
  `no-referrer` and `X-Frame-Options: DENY`.
- The UI shows model output as plain text; only `[n]` becomes a button.
- The ingress terminates TLS in a real installation and limits a request body to 1 MiB.

## Signed packages

A package (tar, canonical manifest, Ed25519 signature) moves a book between installations. The receiver
quarantines it, checks the key (trusted, not revoked), signature, every digest, content id and sequence, and scans
it again. Nothing is published until a person runs `approve-import`; the receiver's policy applies.

## Audit records

In Postgres: `access_event` (every gate decision: who, for whom, action, book, mode, allowed, reason, policy,
grants, delegation, content version, items), `model_call` (every attempt: call id, principal, route, model, source
books, status, error), `write_record` (every note write and link: principal, on behalf of, client id, channel,
origin), `standing_event` (every Standing change: curator or system, reason, cause). The LLMDAP audit is the signed
gateway-side chain in the `llmdap-audit` volume; back it up. `kutuphane explain <correlation-id> --llmdap-export
<file.jsonl>` joins both and reports a model call that LLMDAP did not record as missing
([operations.md](operations.md)).
