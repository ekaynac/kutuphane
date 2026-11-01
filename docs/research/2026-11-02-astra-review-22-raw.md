Reviewed `ea9edb1..origin/main`; locations below refer to `origin/main`. No DB accessed or files changed. Reproductions used Python and mocks.

1. **High — #179 — [deploy/db-roles.sql:30](/home/mega/kobra/deploy/db-roles.sql:30): Existing decider privileges survive removal.** Deleting `db-roles-decider.sql` does not revoke its deployed grants. An existing `kutuphane_decider` credential can still insert suggestions and delegated uses; retained `SECURITY DEFINER` triggers can still create approvals under live delegations. **Fix:** explicitly revoke the retired role’s table/function privileges and disable new delegated uses while preserving historical rows.

2. **High — #183/#184 — [journalexport.py:98](/home/mega/kobra/src/kutuphane/journalexport.py:98): A concurrent sensitivity restriction can escape the export gate.** Restricted sources are filtered in `_records`, but `_finish` only refreshes AI-use flags and skill blocks. If a source becomes restricted between those steps, unchanged read grants allow its text through. Reproduced with a mocked interleaving. **Fix:** recheck current source sensitivity at the final decision, remove affected records and audit items, and synchronize with policy updates.

3. **Medium — #179 — [passkey.py:427](/home/mega/kobra/src/kutuphane/passkey.py:427): Historical delegation acts now fail verification.** Their stored rows remain, but their effect checkers were removed. A valid historical `delegate` act produces `no effect check for delegate`; `end_delegation` has the same problem. Reproduced with signature verification mocked successful. **Fix:** retain read-only historical effect verification without restoring those actions to `ACTIONS`.

4. **Medium — #185 — [server.py:74](/home/mega/kobra/src/kutuphane/server.py:74): The unified parser makes accepted content inaccessible.** `source.read_file` still accepts paths containing tabs/newlines, and chunks permit them. Their generated handles opened previously but now fail with `malformed passage handle`. Reproduced for both characters. **Fix:** align ingestion and handle validation, while preserving access to already-stored paths.

5. **Low — #179 — [curatorqueue.py:450](/home/mega/kobra/src/kutuphane/curatorqueue.py:450): Historical model approvals are misattributed.** Removing the `model:%` branch classifies retained delegated approvals as `system` decisions. **Fix:** preserve a historical model/delegation category in reports.

**No finding:**

- **#179:** active `passkey.ACTIONS` and curator receipts contain no remaining delegated-curation behavior.
- **#180:** migration 049’s tightening/D68 rules, documented expiry clock, curator locking, cron idempotency, and R2 outcome filtering.
- **#182:** default port bindings, internal `outbound`, project-name migration guidance, retained restart policies, and compose secret defaults.
- **#183/#184:** static restricted/unknown-licence exclusions, skill-text withholding, import rights intersection, `--by` read gate, and exclusive `0600` output creation. Operator-selected `--out` paths are not an untrusted traversal boundary.
- **#185:** origin loading through `origin.shown` and remaining callers of removed functions.