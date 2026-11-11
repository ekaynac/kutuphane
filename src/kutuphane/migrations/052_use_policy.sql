-- D85 (S2): a use policy is the curator's standing decision that a book may be published from a trusted key without a
-- per-package act, when the package carries a signed consumer attestation (`accepted_by`) from one of the named
-- attesters and has no findings. One active policy for a book and key. The policy is the book policy to apply.
CREATE TABLE use_policy (
    id         bigserial PRIMARY KEY,
    book       text NOT NULL,
    issuer     text NOT NULL REFERENCES trusted_key(fingerprint),
    attesters  text[] NOT NULL CHECK (cardinality(attesters) > 0),
    policy     jsonb NOT NULL,
    created_by text NOT NULL CHECK (created_by LIKE 'user:%'),
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    revoked_by text,
    CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);
CREATE UNIQUE INDEX use_policy_active ON use_policy (book, issuer) WHERE revoked_at IS NULL;
ALTER TABLE publication
    ADD COLUMN use_policy bigint REFERENCES use_policy(id),
    ADD CONSTRAINT publication_use_policy CHECK ((acceptance = 'consumer_attested') = (use_policy IS NOT NULL));
