-- docs/15 §3 G1, G3, G5.

-- G1: text passages carry the line they start on (JSONL: the record's line). PDFs and HTML keep it null.
ALTER TABLE chunk ADD COLUMN line integer CHECK (line >= 1);

-- G3: a file that cannot be extracted is stored and listed, but not indexed. Like chunks, quarantine belongs to
-- one (content version, profile): a version that fixes the file, or a reader that can extract it, has none.
CREATE TABLE quarantine (
    book       text NOT NULL,
    content_id text NOT NULL,
    profile_id text NOT NULL REFERENCES profile_version(id),
    path       text NOT NULL,
    reason     text NOT NULL,
    PRIMARY KEY (book, content_id, profile_id, path),
    FOREIGN KEY (book, content_id) REFERENCES content_version(book, id)
);

-- G5: the K3 rule (agentfiles.is_instruction) now also marks agent folders, instruction file name prefixes and
-- suffixes, and skill folders. Chunks stored under older profiles keep being served until a book is published
-- again, so mark them now: the same rule, written once more in SQL for the rows that exist. Fail closed: this only
-- ever turns the flag on.
UPDATE chunk c SET instruction = true
 WHERE NOT c.instruction
   AND (c.path ~* '(^|/)(agents\.md|agents\.override\.md|claude\.md|claude\.local\.md|gemini\.md|skill\.md|copilot-instructions\.md)[^/]*$'
        OR c.path ~* '(\.mdc|\.instructions\.md|\.prompt\.md|\.agent\.md|\.chatmode\.md)$'
        OR c.path ~ '(^|/)\.(claude|cursor|github|agents|codex)/'
        OR EXISTS (
            SELECT 1 FROM content_version v CROSS JOIN LATERAL jsonb_array_elements(v.manifest) AS m(entry)
             WHERE v.book = c.book AND v.id = c.content_id
               AND m.entry->>'path' ~* '(^|/)skill\.md$'
               AND starts_with(c.path, regexp_replace(m.entry->>'path', '[^/]*$', ''))));
