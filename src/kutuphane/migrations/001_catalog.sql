-- M1a catalog (D26, D48). Versions are immutable and content-addressed; a book points at its current ones.

CREATE TABLE blob (
    sha256 text PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    data   bytea NOT NULL
);

CREATE TABLE profile_version (
    id         text PRIMARY KEY,
    spec       jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE policy_version (
    id         text PRIMARY KEY,
    doc        jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE book (
    slug            text PRIMARY KEY CHECK (slug ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    title           text NOT NULL,
    current_content text,
    current_policy  text REFERENCES policy_version(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE content_version (
    book       text NOT NULL REFERENCES book(slug),
    id         text NOT NULL,
    manifest   jsonb NOT NULL,  -- [{path, sha256, size, media_type, okf_type}]
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (book, id)
);

ALTER TABLE book
    ADD FOREIGN KEY (slug, current_content) REFERENCES content_version(book, id);
