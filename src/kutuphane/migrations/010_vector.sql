-- M1d (D16, D31): chunk embeddings for hybrid search. Vectors come only through LLMDAP (D17, #222).
-- One row per chunk and embedding model; a query vector is only ever compared with vectors of the same model.
-- No ANN index in M1: search scans the vectors of the books the caller may read (exact, and few enough).
-- Needs the right to create the extension (or an administrator who created it beforehand).
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunk_vector (
    book       text NOT NULL,
    content_id text NOT NULL,
    profile_id text NOT NULL,
    path       text NOT NULL,
    ordinal    integer NOT NULL,
    model      text NOT NULL,       -- the embedding model as the LLMDAP route serves it
    embedding  vector NOT NULL,
    PRIMARY KEY (book, content_id, profile_id, path, ordinal, model),
    FOREIGN KEY (book, content_id, profile_id, path, ordinal)
        REFERENCES chunk (book, content_id, profile_id, path, ordinal)
);
