-- Astra review #15 (D71, docs/24 §22). A block belongs to the skill's bytes: skillscan.store copies every uncleared
-- block of the same input digest into a new content version; carried_from names the record it was copied from. A
-- clearance has the key (book, input_digest, tool_version, report_digest), so one clearance lifts every copy.
ALTER TABLE skill_scan ADD COLUMN carried_from bigint REFERENCES skill_scan (id);

-- A note delivers content derived from a blocked skill when one of its passage dependencies, or one of a note it
-- is derived from (transitively), is inside a skill folder that a scan blocks now. The dependencies are the ones
-- that rights follow (notes._derive): passage citations and `derived_from` links (creation links only, so the
-- closure never changes after the note is written; the walk is cycle-safe anyway). Readers that put text into a
-- model get the text withheld, as for ai_input = false (notesquery, notes, decisions).
CREATE FUNCTION note_skill_blocked(p_seq bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE dep(seq) AS (
        SELECT p_seq
        UNION
        SELECT l.dst_note FROM note_link l JOIN dep ON l.src = dep.seq
         WHERE l.type = 'derived_from' AND l.dst_note IS NOT NULL)
    SELECT EXISTS (SELECT 1 FROM dep JOIN note_citation c ON c.note_seq = dep.seq
                    WHERE c.kind = 'passage' AND skill_blocked(c.cite_book, c.content_id, c.path))
        OR EXISTS (SELECT 1 FROM dep JOIN note_link l ON l.src = dep.seq
                    WHERE l.type = 'derived_from' AND l.dst_book IS NOT NULL
                      AND skill_blocked(l.dst_book, l.dst_content_id, l.dst_path))
$$;
