-- #164: a note's Scope also has the kstd bound `applies_to` {platform?, version?} (docs/09 §2, #137). NULL is
-- unbounded; the canonical body has the key only when it is set, so the ids of the older notes do not change.
ALTER TABLE note ADD COLUMN applies_to jsonb
    CHECK (applies_to IS NULL OR (jsonb_typeof(applies_to) = 'object' AND applies_to <> '{}'::jsonb
                                  AND applies_to - 'platform' - 'version' = '{}'::jsonb));

-- D78: `record_outcome` replaces runbook feedback. The table goes only when it is empty: feedback data is kept.
-- Astra review #21: lock first, so a feedback row that an old server commits during the upgrade is seen, not dropped.
LOCK TABLE runbook_feedback IN ACCESS EXCLUSIVE MODE;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM runbook_feedback) THEN
        DROP TABLE runbook_feedback;
    END IF;
END $$;
