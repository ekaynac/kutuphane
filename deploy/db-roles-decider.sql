-- The decider runner database role (docs/25 §3.1, §4.5, §8.3; D73). `kutuphane decider run` connects with
-- KUTUPHANE_DECIDER_DSN as kutuphane_decider. It writes suggestions, model call records, uses and one access record per
-- run, and nothing else: it holds no INSERT on standing_event. The database decides each use and writes the approval
-- of an unsampled use (migration 025, SECURITY DEFINER triggers).
--
-- Once, as the owner:   CREATE ROLE kutuphane_decider LOGIN PASSWORD '<a new secret>';
-- After every `kutuphane migrate`, as the owner, after deploy/db-roles.sql:
--   psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles-decider.sql
GRANT USAGE ON SCHEMA public TO kutuphane_decider;
GRANT SELECT ON note, note_journal, journal, note_link, note_citation, write_record, standing_event, book,
    policy_version, skill_scan, skill_clearance, skill_block, curate_delegation, delegation_end, note_suggestion,
    delegation_use, model_call, grant_tuple, delegation TO kutuphane_decider;   -- the last two: authz.direct
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kutuphane_decider;
GRANT INSERT ON note_suggestion, delegation_use, model_call, access_event TO kutuphane_decider;
