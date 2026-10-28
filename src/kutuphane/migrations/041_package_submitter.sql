-- #139: a signed package can arrive over HTTP (`POST /v1/packages`) or MCP (`submit_package`), not only from the
-- CLI (`receive`). The origin of its files stays what the issuer signed (D74: the issuer comes from the verified
-- signature, the origins from the enclosed kstd.yaml); the caller that submitted it is recorded here, from the
-- verified token (D70), so the import status can be read by that caller only. A CLI receipt has none (NULL).
ALTER TABLE package_import
    ADD COLUMN submitted_by text,
    ADD COLUMN submitted_for text,
    ADD COLUMN submitted_channel text CHECK (submitted_channel IN ('http', 'mcp')),
    ADD COLUMN submitted_client_id text,
    ADD CONSTRAINT package_import_submitter CHECK ((submitted_by IS NULL) = (submitted_channel IS NULL));
