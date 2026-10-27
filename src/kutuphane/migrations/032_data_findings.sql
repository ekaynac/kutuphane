-- G35: personal-data and fleet-data findings (datascan.py) that no acceptance covers are part of the publication
-- record: [{path, sha256, rule, lines}], never the matched text. Older publications recorded none.
ALTER TABLE publication ADD COLUMN data_findings jsonb NOT NULL DEFAULT '[]'::jsonb;
