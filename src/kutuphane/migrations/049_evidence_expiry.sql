-- R1 (docs/24 §8.4): evidence that nobody uses expires (`kutuphane note expire`). An expiry is a system event with
-- the reason `expired` and no cause event. It has exactly two moves, and both tighten (docs/09 §3.2): a pending
-- evidence note that was never approved gets `rejected` (D68), and an approved one, or one approved once, `retired`.
ALTER TABLE standing_event
    DROP CONSTRAINT standing_event_check,
    DROP CONSTRAINT standing_event_check1,
    ADD CONSTRAINT standing_event_system_cause
        CHECK ((set_by = 'system' AND reason <> 'expired') = (cause_seq IS NOT NULL)),
    ADD CONSTRAINT standing_event_system_tightens CHECK (set_by <> 'system' OR value = 'retired'
                                                         OR (value = 'rejected' AND reason = 'expired'));

CREATE FUNCTION standing_event_expiry() RETURNS trigger LANGUAGE plpgsql
SET search_path = pg_catalog, public, pg_temp AS $$
DECLARE
    allowed text;  -- NULL: no expiry move (a rule note, or a note that is out)
BEGIN
    SELECT CASE WHEN e.value = 'approved' THEN 'retired'
                WHEN coalesce(e.value, 'pending') <> 'pending' THEN NULL
                WHEN EXISTS (SELECT 1 FROM public.standing_event a WHERE a.note_seq = n.seq AND a.value = 'approved')
                    THEN 'retired'
                ELSE 'rejected' END
      INTO allowed
      FROM public.note n
      LEFT JOIN LATERAL (SELECT value FROM public.standing_event WHERE note_seq = n.seq ORDER BY seq DESC LIMIT 1) e
        ON true
     WHERE n.seq = NEW.note_seq AND n.kind IN ('finding', 'dead_end', 'lesson', 'test_result');  -- role evidence
    IF NEW.act IS NOT NULL OR NEW.value IS DISTINCT FROM allowed THEN
        RAISE EXCEPTION 'an expiry moves pending evidence to rejected (retired if ever approved) and approved to retired';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER standing_event_expiry BEFORE INSERT ON standing_event
    FOR EACH ROW WHEN (NEW.set_by = 'system' AND NEW.reason = 'expired') EXECUTE FUNCTION standing_event_expiry();
