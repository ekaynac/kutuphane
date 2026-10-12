-- AT-15 (D13): runbooks evolve through outcome feedback. Feedback belongs to the exact content version it was
-- given on; a new version starts clean and never inherits it.
CREATE TABLE runbook_feedback (
    id             bigserial PRIMARY KEY,
    at             timestamptz NOT NULL DEFAULT now(),
    correlation_id text NOT NULL,
    book           text NOT NULL,
    content_id     text NOT NULL,
    path           text NOT NULL,
    outcome        text NOT NULL CHECK (outcome IN ('worked', 'failed', 'changed')),
    principal      text NOT NULL,
    on_behalf_of   text,
    tested_on      text,
    note           text CHECK (length(note) <= 2000),
    FOREIGN KEY (book, content_id) REFERENCES content_version(book, id)
);
CREATE INDEX runbook_feedback_target ON runbook_feedback (book, content_id, path);
