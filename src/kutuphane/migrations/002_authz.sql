-- M1b authorization core (D28, D37, D24). OpenFGA-shaped tuples kept in Postgres; revocation is soft so the
-- access log can always name the exact grant rows behind a decision.

-- (object, relation, subject): ('book:kvkk', 'read', 'user:ayse'), ('book:kvkk', 'read', 'role:hukuk#member'),
-- ('role:hukuk', 'member', 'user:ayse'). E9 modes are independent; nothing implies anything else.
CREATE TABLE grant_tuple (
    id         bigserial PRIMARY KEY,
    object     text NOT NULL,
    relation   text NOT NULL CHECK (relation IN ('discover', 'read', 'use', 'activate', 'member')),
    subject    text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz
);
CREATE UNIQUE INDEX grant_tuple_live ON grant_tuple (object, relation, subject) WHERE revoked_at IS NULL;
CREATE INDEX grant_tuple_subject ON grant_tuple (subject, relation) WHERE revoked_at IS NULL;

-- One level only: a user delegates to an agent; agents never delegate.
CREATE TABLE delegation (
    id         bigserial PRIMARY KEY,
    delegator  text NOT NULL CHECK (delegator LIKE 'user:%'),
    delegate   text NOT NULL CHECK (delegate LIKE 'agent:%'),
    object     text NOT NULL,
    mode       text NOT NULL CHECK (mode IN ('discover', 'read', 'use', 'activate')),
    purpose    text,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    CHECK (expires_at > created_at)
);
CREATE INDEX delegation_live ON delegation (delegate, delegator, mode) WHERE revoked_at IS NULL;

CREATE TABLE access_event (
    id             bigserial PRIMARY KEY,
    at             timestamptz NOT NULL DEFAULT now(),
    correlation_id text NOT NULL,
    principal      text NOT NULL,
    on_behalf_of   text,
    action         text NOT NULL,
    object         text NOT NULL,
    mode           text NOT NULL,
    allowed        boolean NOT NULL,
    reason         text NOT NULL,
    policy_id      text,
    grant_ids      bigint[] NOT NULL DEFAULT '{}',
    delegation_id  bigint,
    content_id     text,
    path           text
);
CREATE INDEX access_event_correlation ON access_event (correlation_id);
