-- The curator web database role (docs/25 §3.1, §4.5). Curator web (the phone page, `kutuphane curator web`) connects
-- with KUTUPHANE_CURATOR_WEB_DSN as kutuphane_curator_web. Every Standing event it writes is an item of a signed act
-- statement (migration 023: keys, a trigger and the policy below); it cannot make a person or an enrollment (only
-- the owner, through `kutuphane curator enroll`), and it cannot revoke or un-revoke a passkey.
--
-- Once, as the owner:   CREATE ROLE kutuphane_curator_web LOGIN PASSWORD '<a new secret>';
-- After every `kutuphane migrate`, as the owner, after deploy/db-roles.sql:
--   psql "$KUTUPHANE_CURATOR_DSN" -v ON_ERROR_STOP=1 -f deploy/db-roles-curator.sql
GRANT USAGE ON SCHEMA public TO kutuphane_curator_web;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO kutuphane_curator_web;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kutuphane_curator_web;
GRANT INSERT ON passkey, curator_session, curator_challenge, curator_act, standing_event, access_event
    TO kutuphane_curator_web;
GRANT UPDATE (sign_count) ON passkey TO kutuphane_curator_web;
GRANT UPDATE (ended_at) ON curator_session TO kutuphane_curator_web;
DROP POLICY IF EXISTS standing_event_web ON standing_event;
CREATE POLICY standing_event_web ON standing_event FOR INSERT TO kutuphane_curator_web
    WITH CHECK (act IS NOT NULL
                OR (set_by = 'system' AND value = 'retired' AND EXISTS (  -- docs/24 §8.3: a retirement its act signs
                        SELECT 1 FROM standing_event c
                          JOIN note_link l ON l.src = c.note_seq AND l.type = 'supersedes' AND l.creation
                         WHERE c.seq = standing_event.cause_seq AND c.act IS NOT NULL AND c.value = 'approved'
                           AND l.dst_note = standing_event.note_seq)));
-- Migration 026 (trigger standing_event_retires_signed) adds: the target is in the `retires` list of the cause's act
-- statement, and the cause event is of this transaction.
