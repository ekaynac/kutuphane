-- The application database role (docs/24 §4.1, §8.2). The server, and every process that an agent can reach,
-- connects with KUTUPHANE_DSN as kutuphane_app. Only the owner role (KUTUPHANE_CURATOR_DSN: `kutuphane migrate`,
-- `kutuphane note standing`) writes Standing; memory rows are append-only for the app.
--
-- Once, as the owner:   CREATE ROLE kutuphane_app LOGIN PASSWORD '<a new secret>';
-- After every `kutuphane migrate` (new tables need their grants), as the owner:
--   psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles.sql
GRANT USAGE ON SCHEMA public TO kutuphane_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO kutuphane_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kutuphane_app;
REVOKE INSERT, UPDATE, DELETE ON standing_event FROM kutuphane_app;
REVOKE UPDATE, DELETE ON note, write_record, note_link, note_citation, outcome FROM kutuphane_app;
