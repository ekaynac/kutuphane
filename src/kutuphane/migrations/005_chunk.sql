-- M1d: what a presentation profile serves (D26). Chunks are immutable per (content version, profile); a citation
-- names book, content id, profile id, path and ordinal, so an old answer reopens the exact passage (AT-07).
CREATE TABLE chunk (
    book        text NOT NULL,
    content_id  text NOT NULL,
    profile_id  text NOT NULL REFERENCES profile_version(id),
    path        text NOT NULL,
    ordinal     integer NOT NULL,
    page        integer,              -- PDFs: 1-based page of the chunk start
    start_char  integer NOT NULL,     -- offsets into the profile's extracted text of the file
    end_char    integer NOT NULL,
    text        text NOT NULL,
    instruction boolean NOT NULL,     -- K3: agents also need `activate` (D37)
    tsv         tsvector NOT NULL,
    PRIMARY KEY (book, content_id, profile_id, path, ordinal),
    FOREIGN KEY (book, content_id) REFERENCES content_version(book, id)
);
CREATE INDEX chunk_tsv ON chunk USING gin (tsv);
