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
REVOKE UPDATE, DELETE ON note, write_record, note_link, note_citation, outcome FROM kutuphane_app;
-- docs/24 §22: the app records skill scans but can never remove one or its block. skill_block is an updatable view
-- (it would write skill_scan with the owner's rights), so it is read-only too.
REVOKE INSERT, UPDATE, DELETE ON skill_clearance, skill_block FROM kutuphane_app;
REVOKE UPDATE, DELETE ON skill_scan FROM kutuphane_app;
GRANT UPDATE (stale) ON skill_scan TO kutuphane_app;
