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
-- #140 (040): a passage map row is written once (publication, note write, `kutuphane reindex-map`) and never changed.
REVOKE UPDATE, DELETE ON passage_map FROM kutuphane_app;
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
-- docs/25 §4.5 (025): no write on the tables of the removed D73 (delegated curate); they stay as history.
REVOKE INSERT, UPDATE, DELETE ON note_suggestion, curate_delegation, delegation_use, delegation_end FROM kutuphane_app;
-- Security review #17 (029): the key of the sample draw is the owner's only.
REVOKE ALL ON delegation_sample_key FROM kutuphane_app;
-- D79: only the owner makes a curator. The app writes every other grant row, and may revoke or delete a curate row
-- (that only takes a right away). Every other role reads grant_tuple as before; the owner bypasses RLS.
ALTER TABLE grant_tuple ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS grant_tuple_select ON grant_tuple;
CREATE POLICY grant_tuple_select ON grant_tuple FOR SELECT USING (true);
DROP POLICY IF EXISTS grant_tuple_app ON grant_tuple;
CREATE POLICY grant_tuple_app ON grant_tuple FOR ALL TO kutuphane_app
    USING (true) WITH CHECK (relation <> 'curate' OR revoked_at IS NOT NULL);
-- Astra review #19 (038): no login role makes temporary tables or sequences, which PostgreSQL would search before
-- `public` in a function without a pinned search path. TEMP is a right of PUBLIC by default, so it goes from PUBLIC
-- (the owner of the database keeps it); defense in depth next to the pinned paths of migration 038.
DO $$ BEGIN
    EXECUTE format('REVOKE TEMPORARY ON DATABASE %I FROM PUBLIC, kutuphane_app', current_database());
END $$;
