-- G23 (docs/18 §7, quotes.py): the string values of JSONL record passages, so that a passage that repeats a whole
-- value can point to its record. One row per (record passage, sha256 of a value after white-space folding), only for
-- values of at least 40 characters. Written at publication; derived data, never a kstd field.
CREATE TABLE record_value (
    book       text    NOT NULL,
    content_id text    NOT NULL,
    profile_id text    NOT NULL,
    path       text    NOT NULL,
    ordinal    integer NOT NULL,
    sha256     bytea   NOT NULL CHECK (length(sha256) = 32),
    PRIMARY KEY (book, content_id, profile_id, path, ordinal, sha256),
    FOREIGN KEY (book, content_id, profile_id, path, ordinal) REFERENCES chunk (book, content_id, profile_id, path, ordinal)
);
CREATE INDEX record_value_sha ON record_value (sha256);

-- backfill: the record passages of versions published before this migration, with the folding of quotes.py
-- ([ \t\n\r\f\v]+ → one space, then trim spaces). A passage that is not one JSON object (a cut record, the `whole`
-- profile) has no values; jsonb also refuses what quotes.record_values refuses (NaN, NUL, lone surrogates).
INSERT INTO record_value (book, content_id, profile_id, path, ordinal, sha256)
SELECT DISTINCT c.book, c.content_id, c.profile_id, c.path, c.ordinal, sha256(convert_to(v.folded, 'UTF8'))
  FROM chunk c
  JOIN content_version cv ON cv.book = c.book AND cv.id = c.content_id
 CROSS JOIN LATERAL (SELECT c.text::jsonb AS j WHERE pg_input_is_valid(c.text, 'jsonb')) r
 CROSS JOIN LATERAL jsonb_path_query(r.j, 'strict $.**') AS s(x)
 CROSS JOIN LATERAL (SELECT btrim(regexp_replace(s.x #>> '{}', '[ \t\n\r\f\v]+', ' ', 'g'), ' ') AS folded) v
 WHERE jsonb_typeof(r.j) = 'object' AND jsonb_typeof(s.x) = 'string' AND length(v.folded) >= 40
   AND EXISTS (SELECT 1 FROM jsonb_array_elements(cv.manifest) f
                WHERE f->>'path' = c.path AND f->>'media_type' = 'application/jsonl')
ON CONFLICT DO NOTHING;
