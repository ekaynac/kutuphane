-- Astra review #21: across a changed content version, the overlap rule (passagemap.choose) ignored operators and case,
-- so `retries >= 3` could map to `retries <= 3`. The rule now keeps them. The rows written by the old rule are removed;
-- a read computes the new answer, and `kutuphane reindex-map <book>` (or the next publication) writes it again.
DELETE FROM passage_map WHERE match = 'overlap' AND content_id <> to_content_id;
