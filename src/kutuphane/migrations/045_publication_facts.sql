-- #160: who stood behind each publication. `approved_by`: the principal who ran `ingest` (channel `ingest`) or
-- decided `approve-import` (channel `import`, with the package_import row: its issuer key and sequence). Publications
-- before this migration recorded nobody: all three stay NULL.
ALTER TABLE publication
    ADD COLUMN approved_by text CHECK (approved_by ~ '^(user|agent|role):[a-z0-9][a-z0-9._@-]{0,121}$'),
    ADD COLUMN channel text CHECK (channel IN ('ingest', 'import')),
    ADD COLUMN package_import bigint REFERENCES package_import(id),
    ADD CONSTRAINT publication_approval CHECK ((approved_by IS NULL) = (channel IS NULL)
                                               AND (package_import IS NOT NULL) = (channel IS NOT DISTINCT FROM 'import'));
