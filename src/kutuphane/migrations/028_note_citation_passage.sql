-- G32 (docs/26): `neighbours` from a passage follows the notes that cite it, so the passage citations are looked up
-- by the cited passage, as note_link_dst_passage does for the `about` and `derived_from` links.
CREATE INDEX note_citation_passage ON note_citation (cite_book, content_id, profile_id, path, ordinal)
    WHERE kind = 'passage';
