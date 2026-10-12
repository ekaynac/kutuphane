-- M1f (D23, D29, AT-13, AT-14): signed packages between installations, over network or physical media alike.

-- Trust root: a key is trusted only after an administrator confirmed its fingerprint out of band.
CREATE TABLE trusted_key (
    fingerprint text PRIMARY KEY,
    public_key  bytea NOT NULL,
    name        text NOT NULL,
    added_by    text NOT NULL,
    added_at    timestamptz NOT NULL DEFAULT now(),
    revoked_at  timestamptz
);

-- Replay protection on the receiving side: highest sequence accepted per (signing key, book).
CREATE TABLE package_sequence (
    issuer        text NOT NULL,
    book          text NOT NULL,
    last_sequence bigint NOT NULL,
    PRIMARY KEY (issuer, book)
);

-- The sending side's counter per (own signing key, book).
CREATE TABLE export_sequence (
    issuer        text NOT NULL,
    book          text NOT NULL,
    last_sequence bigint NOT NULL,
    PRIMARY KEY (issuer, book)
);

-- Every received package is kept with its verdict: quarantined → verified | rejected → published | rejected.
CREATE TABLE package_import (
    id           bigserial PRIMARY KEY,
    received_at  timestamptz NOT NULL DEFAULT now(),
    status       text NOT NULL CHECK (status IN ('verified', 'rejected', 'published')),
    issuer       text,
    book         text,
    sequence     bigint,
    content_id   text,
    manifest     jsonb,
    package      bytea NOT NULL,
    reasons      jsonb NOT NULL DEFAULT '[]',
    findings     jsonb NOT NULL DEFAULT '[]',
    diff         jsonb,
    decided_by   text,
    decided_at   timestamptz
);
