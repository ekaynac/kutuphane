-- docs/25 §4.1: passkeys, sessions, signed curator acts. Standing events of the web path name their act.

-- One WebAuthn user handle per person, made by the owner role (the CLI) at the first enrollment: every passkey of a
-- person carries the same handle, so a passkey login names exactly one person.
CREATE TABLE curator_person (
    principal   text PRIMARY KEY CHECK (principal ~ '^user:[a-z0-9][a-z0-9._@-]{0,121}$'),
    user_handle bytea NOT NULL UNIQUE CHECK (octet_length(user_handle) = 32),
    UNIQUE (principal, user_handle)
);

-- One-time enrollment codes. Only the owner role (the CLI, KUTUPHANE_CURATOR_DSN) inserts them.
CREATE TABLE curator_enrollment (
    id          text PRIMARY KEY CHECK (id ~ '^en_[0-9a-f]{32}$'),
    principal   text NOT NULL REFERENCES curator_person (principal),
    code_sha256 bytea NOT NULL CHECK (octet_length(code_sha256) = 32),
    created_by  text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '1 hour'),
    UNIQUE (id, principal)
);

-- One row per registered credential. An enrollment registers at most one credential, for its own person, while live.
CREATE TABLE passkey (
    credential_id   bytea PRIMARY KEY CHECK (octet_length(credential_id) BETWEEN 16 AND 1023),
    principal       text NOT NULL,
    user_handle     bytea NOT NULL,
    enrollment      text NOT NULL UNIQUE,
    public_key      bytea NOT NULL,                     -- COSE_Key
    sign_count      bigint NOT NULL CHECK (sign_count >= 0),   -- the last counter of any assertion (login or act)
    backup_eligible boolean NOT NULL,                   -- BE flag at registration
    created_at      timestamptz NOT NULL DEFAULT now(),
    revoked_at      timestamptz,                        -- set only by the owner role (CLI)
    FOREIGN KEY (enrollment, principal) REFERENCES curator_enrollment (id, principal),
    FOREIGN KEY (principal, user_handle) REFERENCES curator_person (principal, user_handle),
    UNIQUE (credential_id, principal)
);
CREATE INDEX passkey_principal ON passkey (principal) WHERE revoked_at IS NULL;

CREATE FUNCTION passkey_enrollment_live() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM curator_enrollment WHERE id = NEW.enrollment AND clock_timestamp() < expires_at) THEN
        RAISE EXCEPTION 'enrollment % is not live', NEW.enrollment;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER passkey_enrollment_live BEFORE INSERT ON passkey
    FOR EACH ROW EXECUTE FUNCTION passkey_enrollment_live();

CREATE TABLE curator_session (
    id_sha256  bytea PRIMARY KEY CHECK (octet_length(id_sha256) = 32),   -- SHA-256 of the cookie value
    principal  text NOT NULL REFERENCES curator_person (principal),
    login      text NOT NULL CHECK (login IN ('passkey', 'enrollment')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    ended_at   timestamptz,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '8 hours'),
    UNIQUE (id_sha256, principal)
);

-- The statement that one WebAuthn ceremony signs. challenge = SHA-256(domain || canonical(payload)) (§5.2).
-- A `login` challenge has no session and no principal yet: the assertion names the person.
CREATE TABLE curator_challenge (
    id         text PRIMARY KEY CHECK (id ~ '^ch_[0-9a-f]{32}$'),
    session    bytea,
    principal  text,
    action     text NOT NULL CHECK (action IN ('register', 'login', 'standing', 'confirm', 'withdraw', 'delegate',
                                               'end_delegation')),
    payload    jsonb NOT NULL,
    challenge  bytea NOT NULL UNIQUE CHECK (octet_length(challenge) = 32),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > created_at AND expires_at <= created_at + interval '5 minutes'),
    CHECK ((action = 'login') = (session IS NULL) AND (session IS NULL) = (principal IS NULL)),
    FOREIGN KEY (session, principal) REFERENCES curator_session (id_sha256, principal),
    UNIQUE (id, principal, action),
    UNIQUE (id, action)
);
-- A passkey login uses its own login challenge once.
ALTER TABLE curator_session
    ADD COLUMN login_challenge text UNIQUE,
    ADD COLUMN login_action text GENERATED ALWAYS AS (CASE WHEN login_challenge IS NOT NULL THEN 'login' END) STORED,
    ADD FOREIGN KEY (login_challenge, login_action) REFERENCES curator_challenge (id, action),
    ADD CHECK ((login = 'passkey') = (login_challenge IS NOT NULL));

-- A verified assertion. UNIQUE (challenge): a challenge is used once (replay = unique violation, nothing written).
CREATE TABLE curator_act (
    seq                bigint PRIMARY KEY DEFAULT nextval('memory_seq'),
    challenge          text NOT NULL UNIQUE,
    principal          text NOT NULL,
    action             text NOT NULL CHECK (action IN ('standing', 'confirm', 'withdraw', 'delegate', 'end_delegation')),
    credential_id      bytea NOT NULL,
    authenticator_data bytea NOT NULL,
    client_data_json   bytea NOT NULL,
    signature          bytea NOT NULL,
    backup_state       boolean NOT NULL,                -- BS flag of this assertion (a synced passkey)
    shown_ms           integer CHECK (shown_ms BETWEEN 0 AND 3600000),
    at                 timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (challenge, principal, action) REFERENCES curator_challenge (id, principal, action),
    FOREIGN KEY (credential_id, principal) REFERENCES passkey (credential_id, principal),
    UNIQUE (seq, principal),
    UNIQUE (seq, action)
);
CREATE INDEX curator_act_principal ON curator_act (principal, at);

ALTER TABLE standing_event ADD COLUMN act bigint,
    ADD COLUMN act_action text GENERATED ALWAYS AS (CASE WHEN act IS NOT NULL THEN 'standing' END) STORED,
    ADD FOREIGN KEY (act, set_by) REFERENCES curator_act (seq, principal),     -- set_by = the signer
    ADD FOREIGN KEY (act, act_action) REFERENCES curator_act (seq, action);   -- only a standing act
CREATE UNIQUE INDEX standing_event_act ON standing_event (act, note_seq) WHERE act IS NOT NULL;

-- An act event is exactly one item of its signed statement: this note, this value, this reason.
CREATE FUNCTION standing_event_in_statement() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.act IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM curator_act a
          JOIN curator_challenge c ON c.id = a.challenge
          JOIN note n ON n.seq = NEW.note_seq
         CROSS JOIN jsonb_array_elements(c.payload -> 'items') i
         WHERE a.seq = NEW.act AND i ->> 'ref' = n.book || '@' || n.id AND i ->> 'to' = NEW.value
           AND c.payload ->> 'reason' = NEW.reason) THEN
        RAISE EXCEPTION 'event is not in the statement of act %', NEW.act;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER standing_event_in_statement BEFORE INSERT ON standing_event
    FOR EACH ROW EXECUTE FUNCTION standing_event_in_statement();

-- Row-level security: SELECT stays open to every role that has the privilege. INSERT policies per role are in
-- deploy/db-roles.sql (roles are made by the deployment, not by migrations). The owner (CLI) bypasses RLS.
ALTER TABLE standing_event ENABLE ROW LEVEL SECURITY;
CREATE POLICY standing_event_select ON standing_event FOR SELECT USING (true);
