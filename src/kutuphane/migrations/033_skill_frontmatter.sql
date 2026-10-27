-- Security review #18, finding 7: the validated SKILL.md frontmatter of each content version, written once (at
-- publication, or at the first skills call for a version published before this migration), so `skills/list`,
-- `skills/get` and `resources/read` read this row and never parse SKILL.md blobs again.
-- `skills`: {folder: frontmatter as JSON} of every skill folder whose SKILL.md conforms to SEP-2640 (skills.py);
-- the folder is "." for the book root. A folder that does not conform is not in it.
CREATE TABLE skill_frontmatter (
    book       text NOT NULL,
    content_id text NOT NULL,
    skills     jsonb NOT NULL CHECK (jsonb_typeof(skills) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (book, content_id),
    FOREIGN KEY (book, content_id) REFERENCES content_version (book, id)
);
