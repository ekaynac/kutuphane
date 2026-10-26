-- G17 (pilot radar): incremental indexing. A vector records the sha256 of the text that was embedded (the passage,
-- or its first vectors.EMBED_CHARS characters when `truncated`). A new content version of the same book and profile
-- copies the vector of a passage whose embedded text, model and width are unchanged, and embeds only the rest.
-- Existing vectors get the hash of their chunk text: every stored vector was made from the first 24,000 characters
-- (013) or from the whole passage, which was shorter (an oversized passage failed the call before 013).
ALTER TABLE chunk_vector ADD COLUMN input_sha256 bytea;
UPDATE chunk_vector v SET input_sha256 = sha256(convert_to(left(c.text, 24000), 'UTF8'))
  FROM chunk c
 WHERE (c.book, c.content_id, c.profile_id, c.path, c.ordinal) = (v.book, v.content_id, v.profile_id, v.path, v.ordinal);
ALTER TABLE chunk_vector ALTER COLUMN input_sha256 SET NOT NULL;
CREATE INDEX chunk_vector_reuse ON chunk_vector (book, profile_id, model, input_sha256);
