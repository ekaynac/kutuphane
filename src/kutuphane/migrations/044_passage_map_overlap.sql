-- Astra review #20: an `overlap` match across a changed content version could join a passage to a successor of
-- another meaning (`enable` to `disable` keeps most word pairs). The rule is now stricter (passagemap.choose): across
-- a changed content version, an overlap must hold the whole old text. The rows written by the old rule are removed;
-- a read computes the new answer, and `kutuphane reindex-map <book>` (or the next publication) writes it again.
DELETE FROM passage_map WHERE match = 'overlap' AND content_id <> to_content_id;
