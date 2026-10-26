-- Astra review #11: a passage longer than the embedding budget (vectors.EMBED_CHARS) is embedded by its prefix only.
-- The vector says so; the chunk text and its full text index are unchanged. Older vectors were made from whole
-- passages (an oversized one failed the call rather than being cut).
ALTER TABLE chunk_vector ADD COLUMN truncated boolean NOT NULL DEFAULT false;
