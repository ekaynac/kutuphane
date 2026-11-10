-- D85 (S1): each publication records HOW it was accepted, apart from who. `acceptance` is the kind of evidence:
-- curator_passkey, operator_cli, consumer_attested, policy or none (kinds never merge, no order between them).
-- Today a new publication is operator_cli, or none for the internal path without `approved_by`; the other kinds are
-- for later slices. Publications before this migration are marked `acceptance_legacy` and are never upgraded: a
-- person's name there was a statement checked only for its form.
ALTER TABLE publication
    ADD COLUMN acceptance text CHECK (acceptance IN ('curator_passkey', 'operator_cli', 'consumer_attested', 'policy',
                                                     'none')),
    ADD COLUMN acceptance_legacy boolean NOT NULL DEFAULT false;
UPDATE publication SET acceptance = CASE WHEN approved_by IS NULL THEN 'none' ELSE 'operator_cli' END,
                       acceptance_legacy = true;
ALTER TABLE publication
    ALTER COLUMN acceptance SET NOT NULL,
    ADD CONSTRAINT publication_acceptance CHECK ((acceptance = 'none') = (approved_by IS NULL));
