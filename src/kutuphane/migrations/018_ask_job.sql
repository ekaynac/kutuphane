-- docs/24 §4.4, §12.2: `ask_library` as a durable background job. A job runs once (a lease that ends makes it
-- `failed: interrupted`, never a second model call); its result is the stored answer, reopened with current rights.
CREATE TABLE ask_job (
    id                  text PRIMARY KEY CHECK (id ~ '^jb_[0-9a-f]{32}$'),
    principal           text NOT NULL,
    on_behalf_of        text,
    correlation_id      text NOT NULL,
    question            text NOT NULL,
    scope               jsonb NOT NULL,
    idempotency_key     text CHECK (idempotency_key ~ '^[A-Za-z0-9._:-]{8,128}$'),
    request_sha256      bytea,
    status              text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    started_at          timestamptz,
    lease_until         timestamptz,
    finished_at         timestamptz,
    cancel_requested_at timestamptz,
    answer_id           text REFERENCES answer(id),
    error               text CHECK (char_length(error) <= 500),
    CHECK (status <> 'succeeded' OR answer_id IS NOT NULL),
    CHECK ((idempotency_key IS NULL) = (request_sha256 IS NULL))
);
CREATE UNIQUE INDEX ask_job_idempotency ON ask_job (principal, coalesce(on_behalf_of, ''), idempotency_key)
    WHERE idempotency_key IS NOT NULL;
CREATE INDEX ask_job_owner ON ask_job (principal, created_at DESC);
CREATE INDEX ask_job_open  ON ask_job (created_at) WHERE status IN ('queued', 'running');
