-- #140: a re-index (a new profile id, or a new content version) gives every passage of a book a new handle. Notes
-- cite passages and link to them (`about`, `derived_from`) by the exact handle, so after a re-index they stayed on the
-- old passages: `neighbours` from a new handle did not find them. The passage map records, for each referenced passage
-- of an earlier version, its successor in the version that a publication made current: the passage of the same path
-- with the same text (`exact`), else the passage that holds most of its text (`overlap`), else none (`none`: the
-- reads show the citation as `stale`). The citation keeps its handle (audit); the reads add the successor
-- (passagemap.py). The map is written once per (passage, target version) and never changed.
CREATE TABLE passage_map (
    book          text NOT NULL,
    content_id    text NOT NULL,
    profile_id    text NOT NULL,
    path          text NOT NULL,
    ordinal       integer NOT NULL,
    to_content_id text NOT NULL,
    to_profile_id text NOT NULL,
    to_ordinal    integer,                       -- NULL: no successor (match = 'none')
    match         text NOT NULL CHECK (match IN ('exact', 'overlap', 'none')),
    mapped_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (book, content_id, profile_id, path, ordinal, to_content_id, to_profile_id),
    FOREIGN KEY (book, content_id, profile_id, path, ordinal) REFERENCES chunk (book, content_id, profile_id, path, ordinal),
    FOREIGN KEY (book, to_content_id, to_profile_id, path, to_ordinal)
        REFERENCES chunk (book, content_id, profile_id, path, ordinal),
    CHECK ((match = 'none') = (to_ordinal IS NULL)),
    CHECK ((content_id, profile_id) <> (to_content_id, to_profile_id))
);
-- `neighbours` from a passage: the earlier passages that map to it
CREATE INDEX passage_map_to ON passage_map (book, to_content_id, to_profile_id, path, to_ordinal)
    WHERE to_ordinal IS NOT NULL;

-- D71 after a re-index: a note also depends on the successor of each passage it cites or derives from, in the
-- version that is current now, so a scan that blocks that skill withholds the note too (the gates apply to the new
-- passage). The block of the cited passage itself still applies.
CREATE FUNCTION passage_successor_blocked(p_book text, p_content text, p_profile text, p_path text,
                                          p_ordinal integer) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    SELECT EXISTS (SELECT 1 FROM public.passage_map m JOIN public.book b ON b.slug = m.book
                    WHERE m.book = p_book AND m.content_id = p_content AND m.profile_id = p_profile
                      AND m.path = p_path AND m.ordinal = p_ordinal AND m.to_ordinal IS NOT NULL
                      AND m.to_content_id = b.current_content AND m.to_profile_id = b.current_profile
                      AND public.skill_blocked(m.book, m.to_content_id, m.path))
$$;

CREATE OR REPLACE FUNCTION note_skill_blocked(p_seq bigint) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog, public, pg_temp AS $$
    WITH RECURSIVE dep(seq) AS (
        SELECT p_seq
        UNION
        SELECT l.dst_note FROM public.note_link l JOIN dep ON l.src = dep.seq
         WHERE l.type = 'derived_from' AND l.dst_note IS NOT NULL)
    SELECT EXISTS (SELECT 1 FROM dep JOIN public.note_citation c ON c.note_seq = dep.seq
                    WHERE c.kind = 'passage'
                      AND (public.skill_blocked(c.cite_book, c.content_id, c.path)
                           OR public.passage_successor_blocked(c.cite_book, c.content_id, c.profile_id, c.path,
                                                               c.ordinal)))
        OR EXISTS (SELECT 1 FROM dep JOIN public.note_link l ON l.src = dep.seq
                    WHERE l.type = 'derived_from' AND l.dst_book IS NOT NULL
                      AND (public.skill_blocked(l.dst_book, l.dst_content_id, l.dst_path)
                           OR public.passage_successor_blocked(l.dst_book, l.dst_content_id, l.dst_profile_id,
                                                               l.dst_path, l.dst_ordinal)))
$$;
