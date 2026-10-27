-- Security review #16 (docs/25 §4.6): sessions know their passkey or their enrollment, an enrollment can be
-- cancelled, and a system event caused by an act event is one of the retirements that the act's statement signs.

-- An enrollment the owner cancelled (`kutuphane curator cancel-enrollment`) registers nothing.
ALTER TABLE curator_enrollment ADD COLUMN cancelled_at timestamptz;

CREATE OR REPLACE FUNCTION passkey_enrollment_live() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM curator_enrollment WHERE id = NEW.enrollment AND clock_timestamp() < expires_at
                                                      AND cancelled_at IS NULL) THEN
        RAISE EXCEPTION 'enrollment % is not live', NEW.enrollment;
    END IF;
    RETURN NEW;
END $$;

-- A passkey session names the passkey of its login (revoking it ends the session); an enrollment session names its
-- enrollment (it registers for that code only). The sessions made before this migration end now; the checks are
-- NOT VALID only for these ended rows.
UPDATE curator_session SET ended_at = clock_timestamp() WHERE ended_at IS NULL;
ALTER TABLE curator_session
    ADD COLUMN credential_id bytea,
    ADD COLUMN enrollment text,
    ADD FOREIGN KEY (credential_id, principal) REFERENCES passkey (credential_id, principal),
    ADD FOREIGN KEY (enrollment, principal) REFERENCES curator_enrollment (id, principal),
    ADD CONSTRAINT curator_session_credential CHECK ((login = 'passkey') = (credential_id IS NOT NULL)) NOT VALID,
    ADD CONSTRAINT curator_session_enrollment CHECK ((login = 'enrollment') = (enrollment IS NOT NULL)) NOT VALID;
CREATE INDEX curator_session_credential ON curator_session (credential_id) WHERE ended_at IS NULL;

-- A system event whose cause is an act event is a retirement that the act's statement lists (`retires`), written in
-- the transaction of the act (docs/24 §8.3, docs/25 §5.2).
CREATE FUNCTION standing_event_retires_signed() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cause_act bigint;
BEGIN
    SELECT act INTO cause_act FROM standing_event WHERE seq = NEW.cause_seq;
    IF cause_act IS NULL THEN
        RETURN NEW;
    END IF;
    IF NEW.set_by <> 'system' OR NEW.value <> 'retired' OR NEW.act IS NOT NULL
       OR NOT EXISTS (SELECT 1 FROM standing_event c WHERE c.seq = NEW.cause_seq AND c.xmin = pg_current_xact_id()::xid)
       OR NOT EXISTS (
            SELECT 1 FROM curator_act a
              JOIN curator_challenge ch ON ch.id = a.challenge
              JOIN note n ON n.seq = NEW.note_seq
             CROSS JOIN jsonb_array_elements(coalesce(ch.payload -> 'retires', '[]'::jsonb)) r
             WHERE a.seq = cause_act AND r ->> 'ref' = n.book || '@' || n.id AND r ->> 'id' = n.id) THEN
        RAISE EXCEPTION 'system event is not a retirement signed by act %', cause_act;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER standing_event_retires_signed BEFORE INSERT ON standing_event
    FOR EACH ROW WHEN (NEW.cause_seq IS NOT NULL) EXECUTE FUNCTION standing_event_retires_signed();
