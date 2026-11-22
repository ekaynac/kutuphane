-- D85 (#235): a use policy has an unattended form. It has no attesters: a package from the trusted key is published
-- with no person and no attestation, and the publication is recorded as acceptance `policy`, never as a person.
-- `attesters` is empty exactly when the policy is unattended; existing policies stay attested.
ALTER TABLE use_policy ADD COLUMN unattended boolean NOT NULL DEFAULT false;
ALTER TABLE use_policy DROP CONSTRAINT use_policy_attesters_check,
    ADD CONSTRAINT use_policy_unattended CHECK (unattended = (cardinality(attesters) = 0));
-- A publication under a use policy has the kind `consumer_attested` (an attester) or `policy` (unattended).
-- For `policy`, `approved_by` is `policy:<id>` of its use policy: not a principal, and no person.
ALTER TABLE publication DROP CONSTRAINT publication_approved_by_check,
    ADD CONSTRAINT publication_approved_by_check
        CHECK (approved_by ~ '^(user|agent|role):[a-z0-9][a-z0-9._@-]{0,121}$' OR approved_by ~ '^policy:[0-9]{1,18}$');
ALTER TABLE publication DROP CONSTRAINT publication_use_policy,
    ADD CONSTRAINT publication_use_policy CHECK ((acceptance IN ('consumer_attested', 'policy')) = (use_policy IS NOT NULL)),
    ADD CONSTRAINT publication_policy_kind CHECK ((acceptance = 'policy') = (approved_by ~ '^policy:')
                                                  AND (acceptance <> 'policy' OR approved_by = 'policy:' || use_policy));
