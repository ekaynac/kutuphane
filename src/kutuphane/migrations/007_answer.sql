-- M1d: stored answers (D36). An old answer and its evidence are SHOWN again, never regenerated; opening one needs
-- current read rights on every book whose passages went into it (AT-07).
CREATE TABLE answer (
    id             text PRIMARY KEY,
    created_at     timestamptz NOT NULL DEFAULT now(),
    correlation_id text NOT NULL,
    principal      text NOT NULL,
    on_behalf_of   text,
    question       text NOT NULL,
    status         text NOT NULL CHECK (status IN ('answered', 'not_in_library')),
    body           text,
    citations      jsonb NOT NULL DEFAULT '[]',  -- [{n, book, content_id, profile_id, path, ordinal}] actually cited
    sources        jsonb NOT NULL DEFAULT '[]',  -- every passage given to the model (same shape)
    source_books   text[] NOT NULL DEFAULT '{}',
    model          text
);
CREATE INDEX answer_correlation ON answer (correlation_id);
