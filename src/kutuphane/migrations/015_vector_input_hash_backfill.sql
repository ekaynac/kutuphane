-- Astra review #12: 014 gave every existing vector the hash of its chunk's first 24,000 characters. A vector made
-- before 013 from a whole passage longer than that (a capable embedding backend could embed it) then carried the
-- key of its prefix, and a later passage with the same prefix but another suffix could copy it.
-- The key is recomputed from the text that was actually embedded: the prefix for a `truncated` vector, the whole
-- text otherwise (before 013 nothing was cut). A key that is not certain becomes NULL, which never matches, so that
-- vector is never copied again: a truncated vector whose prefix key equals the prefix of an untruncated longer
-- passage of the same book, profile and model may itself be such a copy (014 gave both the same key).
ALTER TABLE chunk_vector ALTER COLUMN input_sha256 DROP NOT NULL;
UPDATE chunk_vector v
   SET input_sha256 = CASE WHEN v.truncated THEN sha256(convert_to(left(c.text, 24000), 'UTF8'))
                           ELSE sha256(convert_to(c.text, 'UTF8')) END
  FROM chunk c
 WHERE (c.book, c.content_id, c.profile_id, c.path, c.ordinal) = (v.book, v.content_id, v.profile_id, v.path, v.ordinal);
UPDATE chunk_vector v SET input_sha256 = NULL
 WHERE v.truncated AND EXISTS (
       SELECT 1 FROM chunk_vector w
         JOIN chunk c ON (c.book, c.content_id, c.profile_id, c.path, c.ordinal)
                       = (w.book, w.content_id, w.profile_id, w.path, w.ordinal)
        WHERE (w.book, w.profile_id, w.model) = (v.book, v.profile_id, v.model) AND NOT w.truncated
          AND length(c.text) > 24000 AND sha256(convert_to(left(c.text, 24000), 'UTF8')) = v.input_sha256);
