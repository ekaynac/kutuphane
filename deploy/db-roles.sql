-- The application database role (docs/24 §4.1, §8.2). The server, and every process that an agent can reach,
-- connects with KUTUPHANE_DSN as kutuphane_app. Only the owner role (KUTUPHANE_CURATOR_DSN: `kutuphane migrate`,
-- `kutuphane note standing`, `kutuphane note rollback`, `kutuphane skill clear`) writes Standing and skill
-- clearances; memory rows and skill scan records are append-only for the app (a scan record may only become stale).
--
-- Once, as the owner:   CREATE ROLE kutuphane_app LOGIN PASSWORD '<a new secret>';
-- After every `kutuphane migrate` (new tables need their grants), as the owner:
--   psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles.sql
GRANT USAGE ON SCHEMA public TO kutuphane_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kutuphane_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kutuphane_app;
REVOKE INSERT, UPDATE, DELETE ON standing_event FROM kutuphane_app;
REVOKE UPDATE, DELETE ON note, write_record, note_link, note_citation, outcome, note_import FROM kutuphane_app;
-- docs/24 §22: the app records skill scans but can never remove one or its block. skill_block is an updatable view
-- (it would write skill_scan with the owner's rights), so it is read-only too.
REVOKE INSERT, UPDATE, DELETE ON skill_clearance, skill_block FROM kutuphane_app;
REVOKE UPDATE, DELETE ON skill_scan FROM kutuphane_app;
GRANT UPDATE (stale) ON skill_scan TO kutuphane_app;
-- Review #18: the stored SKILL.md frontmatter of a content version is written once and never changed.
REVOKE UPDATE, DELETE ON skill_frontmatter FROM kutuphane_app;
-- docs/25 §4.5: no write on any curation table; no read of persons, enrollments, sessions or challenges.
REVOKE INSERT, UPDATE, DELETE ON curator_person, curator_enrollment, passkey, curator_session, curator_challenge,
    curator_act FROM kutuphane_app;
REVOKE SELECT ON curator_person, curator_enrollment, curator_session, curator_challenge FROM kutuphane_app;
-- docs/25 §4.5 (024): the R3 confirmations and R7 withdrawals are written only by curator web; the app reads them.
REVOKE INSERT, UPDATE, DELETE ON origin_confirmation, origin_withdrawal FROM kutuphane_app;
-- docs/25 §4.5 (025): no write on the decider and delegation tables (the decider role and curator web write them).
REVOKE INSERT, UPDATE, DELETE ON note_suggestion, curate_delegation, delegation_use, delegation_end FROM kutuphane_app;
-- Security review #17 (029): the key of the sample draw is the owner's only.
REVOKE ALL ON delegation_sample_key FROM kutuphane_app;
