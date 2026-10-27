-- docs/24 §22 (D71): SkillSpector scan records of skill folders, and the curator act that lifts their block.
-- A record is a curator proposal (origin `tool`, software_agent {skillspector, tool_version}), never an approval.
-- The app role inserts records and may only set `stale` (deploy/db-roles.sql); it cannot remove a record or a block.
CREATE TABLE skill_scan (
    id             bigserial PRIMARY KEY,
    book           text NOT NULL,
    content_id     text NOT NULL,
    skill_path     text NOT NULL,                       -- the folder that holds SKILL.md; '.' is the book root
    status         text NOT NULL CHECK (status IN ('scanned', 'failed', 'not_scanned')),
    input_digest   text NOT NULL CHECK (input_digest ~ '^[0-9a-f]{64}$'),  -- the skill's files: relative path + sha256
    tool_version   text,                                -- the version that ran (null: no tool ran)
    mode           text CHECK (mode IN ('no-llm')),     -- static rules only: origin `tool`
    report_digest  text CHECK (report_digest ~ '^[0-9a-f]{64}$'),  -- the normalized report (no finding_id, scanned_at)
    recommendation text CHECK (recommendation IN ('SAFE', 'CAUTION', 'DO_NOT_INSTALL')),
    score          integer CHECK (score BETWEEN 0 AND 100),
    completeness   text,                                -- analysis_completeness.status; anything but 'complete' blocks
    findings       jsonb,                               -- the normalized issues
    reason         text,                                -- why a scan failed or did not run
    stale          boolean NOT NULL DEFAULT false,      -- made by another tool version than the latest scan: rescan
    scanned_at     timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (book, content_id) REFERENCES content_version (book, id),
    CHECK ((status = 'not_scanned') = (tool_version IS NULL)),
    CHECK ((status = 'not_scanned') = (mode IS NULL)),
    CHECK ((status = 'scanned') = (report_digest IS NOT NULL AND recommendation IS NOT NULL AND score IS NOT NULL
                                   AND completeness IS NOT NULL AND findings IS NOT NULL)),
    CHECK ((status = 'scanned') = (reason IS NULL))
);
CREATE INDEX skill_scan_version ON skill_scan (book, content_id, skill_path);
CREATE INDEX skill_scan_input ON skill_scan (book, input_digest);

-- A person with `curate` lifts the block of exactly these bytes and this report (owner credential only).
CREATE TABLE skill_clearance (
    id            bigserial PRIMARY KEY,
    book          text NOT NULL REFERENCES book (slug),
    input_digest  text NOT NULL,
    tool_version  text NOT NULL,
    report_digest text,                                 -- null: a failed scan of these bytes by this version
    scan_id       bigint NOT NULL REFERENCES skill_scan (id),  -- the record the curator decided on
    curator       text NOT NULL CHECK (curator LIKE 'user:%'),
    reason        text NOT NULL CHECK (length(reason) BETWEEN 1 AND 500),
    at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX skill_clearance_input ON skill_clearance (book, input_digest);

-- R1: every blocking record blocks until a curator clears it; a later, looser scan never lifts it. Stale records too.
CREATE VIEW skill_block AS
SELECT s.*
  FROM skill_scan s
 WHERE (s.status = 'failed' OR (s.status = 'scanned' AND (s.recommendation = 'DO_NOT_INSTALL'
                                                           OR s.completeness <> 'complete')))
   AND NOT EXISTS (SELECT 1 FROM skill_clearance k
                    WHERE k.book = s.book AND k.input_digest = s.input_digest AND k.tool_version = s.tool_version
                      AND k.report_digest IS NOT DISTINCT FROM s.report_digest);

-- The gate's rule: may `activate` deliver this file of this version to an agent? No, when it is inside a blocked
-- skill folder.
CREATE FUNCTION skill_blocked(p_book text, p_content text, p_path text) RETURNS boolean
LANGUAGE sql STABLE AS $$
    SELECT EXISTS (SELECT 1 FROM skill_block b
                    WHERE b.book = p_book AND b.content_id = p_content
                      AND (b.skill_path = '.' OR starts_with(p_path, b.skill_path || '/')))
$$;
