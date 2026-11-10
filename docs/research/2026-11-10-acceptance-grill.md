# Acceptance and use: the decision tree (grill, 2026-11-10)

**Status:** decided by the operator on 2026-11-10 (D85). The vision text is `docs/23` version 1.3.
**Trigger:** #207 (InfraMedic: the same person approves the same content twice, in InfraMedic and in Kütüphane;
the live P2 test needed 4 host-side acts for 3 documents and 1 note).
**Scope:** #207 and its branches #196, #208 items 4 and 5, and #201. Out of scope: #163 (R5 gate), #138 (G10, D78),
#208 items 1, 2, 3 and 6 (done in #210 and the #208 comment).

## 1. The facts that shaped the tree

- A note is current only when its Standing is `approved` (`src/kutuphane/notesquery.py:188`), for rules and for
  evidence. `pending` notes are only in the `open` set. Standing is written only by the owner role
  (`deploy/db-roles.sql:12`); a phone approval is a passkey act over the note digest (D72); the CLI trusts the
  operator (`src/kutuphane/curation.py:3-4`, `docs/guide/security.md:74-75`). No MCP tool or HTTP route changes
  Standing (`tests/test_notes.py:603-615`).
- A book version is published by `ingest` or `approve-import`. Both run on the app role, and `--by` is free text
  checked only against the principal pattern (`src/kutuphane/cli.py:687,815`, `src/kutuphane/catalog.py:86-87`).
  So `publication.approved_by` is a statement today, not a verified acceptance.
- A token's `on_behalf_of` names who the write is for (`src/kutuphane/identity.py:169-176`). It does not prove that
  this person accepted this content: one token can write many contents. The only content-bound acceptance today is
  the passkey act over the exact digest (D70, D72; `src/kutuphane/confirm.py:7-12`).
- The issuer entry flag `"curate": true` only permits a `curate` grant for that issuer's principals
  (`src/kutuphane/identity.py:145-150`); it opens no approval path.

## 2. Decisions

| # | Decision |
|---|---|
| Q1 | Scope as above. |
| Q2 | Separate **who accepted an item** (always recorded, always true) from **whether it may be used** (a policy of the book). The default policy stays strict: a person in Kütüphane. A looser policy is an explicit choice for one book. |
| Q3' | Acceptance kinds never merge into one label. A person's acceptance counts only with evidence bound to the exact content. A token subject or `on_behalf_of` alone never gives "human-approved". |
| Q5'' | Two Kütüphane-side levels: **(i-a) curator passkey act** (person and content bound, verified); **(i-b) operator statement** on the CLI (content bound; the person is stated). `ingest` and `approve-import` need the owner credential and `curate` for the `--by` person. In a strict book, missing evidence refuses the command (the package stays `received`); the record is never weakened to publish. |
| Q6 | **(ii) consumer statement** for packages: an optional `accepted_by` in the signed manifest (person, time, the consumer's approval record id). A key may state acceptance only for the principal prefixes bound to it, as issuers do. |
| Q7 | A use policy is set only by a Kütüphane curator (CLI or passkey act), for one book and one signing key or issuer; it is recorded, shown in `explain`, and revocable. Revocation affects the next writes only. |
| Q8 | Never under a looser policy: `restricted` books, `cloud_ok` egress, packages with agent instruction files (K3). A package with a finding (personal data, secret, SkillSpector, `license: unknown`) goes to the normal queue. |
| Q9 | Notes stay as they are in this change. Making notes current by a policy or a consumer statement is a new agent-memory feature: it waits for the R5 gate (D80, the T3 rerun). Principle 2's sentence "evidence becomes current by verification and use" is removed until that decision; the code needs acceptance for evidence too. |
| Q10 | #201: without an IdP, the consumer signs its own short-lived tokens; Kütüphane keeps only the public JWKS (#195). `dev-token` stays for development machines. A token says for whom a write is made, never that content was accepted. |
| Q11 | #208 item 5 (InfraMedic annexes): they stay local in InfraMedic. Reopen when InfraMedic measures that annexes are cited again outside their run. |
| Q12 | Readers get `acceptance: {kind, by, at}` with `kind` one of `curator_passkey`, `operator_cli`, `consumer_attested`, `policy`, `none`, on book versions (search, `list_books`, `list_files`) and notes (`query_notes`). The filter takes a set of kinds; there is no order between kinds. It replaces `publication.approved_by` (one field per fact, D53). |
| Q13 | #196 opens, as the second slice: curator web lists received packages and approves or rejects them with a passkey act bound to the manifest digest and `content_id`. `docs/23` §2: "a package is approved once, by a person with `curate`, on the phone or the CLI". |
| Q14 | #208 item 4: one passkey act for 1–50 packages, each digest in the signed statement; `approve-import` takes several ids in one transaction, each recorded as `operator_cli`. No "approve everything in a range". |
| Q15 | Past publications show `operator_cli` with `legacy: true` and are never upgraded. Past note approvals keep what is recorded: an act gives `curator_passkey`, the CLI gives `operator_cli`. |
| Q16 | Slices: **S1** the acceptance record, the strict gate of Q5'' and the reader field and filter (one migration; notes: display only); **S2** the use policy and the consumer statement (package format change: `consumers.md` and an announcement on #144); **S3** passkey approval of packages, single and bulk (#196, #208 item 4). Notes after R5. Each slice is its own PR and passes the D81 gate. |
| Q17 | Vision 1.3: principle 2, P1 and the §2 package line as in `docs/23`; this file; D85. |

## 3. Rejected

- Auto-approving notes from a consumer (#207 rule 5) now: it breaks principle 2 for rules, T17 and the issuer
  contract `curate: false`, and it is a new memory feature before R5.
- Dropping the label and publishing anyway when evidence is missing (it bypasses the strict default).
- One "approved" yes/no for readers (it hides how acceptance was proven), and an order between kinds (which is
  stronger depends on the consumer).
- Treating the owner credential on the CLI as verified human acceptance (`docs/guide/security.md:74-75`).
