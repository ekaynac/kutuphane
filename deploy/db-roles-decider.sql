-- The decider runner database role (docs/25 §3.1, §4.5, §8.3; D73). `kutuphane decider run` connects with
-- KUTUPHANE_DECIDER_DSN as kutuphane_decider. It writes suggestions, model call records, uses and one access record per
-- run, and nothing else: it holds no INSERT on standing_event. The database decides each use, sets its seq, time and
-- sample, and writes the approval of an unsampled use (migrations 025, 029: SECURITY DEFINER triggers). It reads note
-- text only through decider_notes() (the gated books, the text gate) and the next note of a delegation only through
-- delegation_next() (security review #17).
--
-- Once, as the owner:   CREATE ROLE kutuphane_decider LOGIN PASSWORD '<a new secret>';
-- After every `kutuphane migrate`, as the owner, after deploy/db-roles.sql:
--   psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles-decider.sql
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM kutuphane_decider;   -- also the grants of an older version of this file
GRANT USAGE ON SCHEMA public TO kutuphane_decider;
GRANT SELECT ON book, policy_version, curate_delegation, delegation_end, note_suggestion, delegation_use,
    standing_event, model_call TO kutuphane_decider;   -- book, policy_version: the egress check of llmdap
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kutuphane_decider;
GRANT INSERT (note_seq, decider, spec_sha256, value, confidence, model_call) ON note_suggestion TO kutuphane_decider;
GRANT INSERT (delegation, book, kind, decider, spec_sha256, approver, note_seq, suggestion, correlation_id)
    ON delegation_use TO kutuphane_decider;
GRANT INSERT ON model_call, access_event TO kutuphane_decider;
GRANT EXECUTE ON FUNCTION decider_notes(text[], text, bytea, integer, integer, bigint), delegation_next(text)
    TO kutuphane_decider;
