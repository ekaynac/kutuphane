-- Astra review #9: a reviewed credential finding (`ingest --accept-finding <path>@sha256:<digest>:<rule>`) is part
-- of the publication record: [{path, sha256, rule}], never the matched text. Older publications accepted nothing.
ALTER TABLE publication ADD COLUMN accepted_findings jsonb NOT NULL DEFAULT '[]'::jsonb;
