-- docs/24 §4.3, §10: code repositories that an administrator registers per journal (`kutuphane repo add`).
-- Code citations and note scopes name a repository by (book, slug). Kütüphane never fetches: the verifier reads
-- only commits that the registered `refs` reach, through a confined git process (coderepo.py).
CREATE TABLE code_repo (
    book          text NOT NULL REFERENCES journal(book),
    slug          text NOT NULL CHECK (slug ~ '^[a-z0-9][a-z0-9._-]{0,62}$'),
    git_dir       text NOT NULL CHECK (git_dir LIKE '/%' AND git_dir !~ '[[:cntrl:]]'),
    object_format text NOT NULL CHECK (object_format IN ('sha1', 'sha256')),
    refs          text[] NOT NULL CHECK (cardinality(refs) BETWEEN 1 AND 10),
    added_by      text NOT NULL,
    added_at      timestamptz NOT NULL DEFAULT now(),
    removed_at    timestamptz,
    PRIMARY KEY (book, slug)
);
ALTER TABLE note ADD FOREIGN KEY (book, scope_repo) REFERENCES code_repo (book, slug);
ALTER TABLE note_citation ADD FOREIGN KEY (book, repo) REFERENCES code_repo (book, slug);
