-- D26: bind the three version ids of every publish together, and remember which profile a book is served with.

ALTER TABLE book ADD COLUMN current_profile text REFERENCES profile_version(id);

CREATE TABLE publication (
    id           bigserial PRIMARY KEY,
    book         text NOT NULL,
    content_id   text NOT NULL,
    profile_id   text NOT NULL REFERENCES profile_version(id),
    policy_id    text NOT NULL REFERENCES policy_version(id),
    published_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (book, content_id) REFERENCES content_version(book, id)
);
CREATE INDEX publication_book ON publication (book, id);
