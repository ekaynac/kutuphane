-- #75 (docs/24 §23): an operator moves an orchestrator's local memory into a journal with
-- `kutuphane note import`. The import writes notes as the CLI channel; D70 R2 still holds: an agent path stores
-- `model`; a user without `act` stores `unknown` over HTTP and over the CLI.
ALTER TABLE write_record DROP CONSTRAINT write_record_channel_check;
ALTER TABLE write_record ADD CONSTRAINT write_record_channel_check CHECK (channel IN ('mcp', 'http', 'cli'));
ALTER TABLE write_record DROP CONSTRAINT write_record_check2;
ALTER TABLE write_record ADD CONSTRAINT write_record_origin_path_check
    CHECK (origin = 'model' OR (principal LIKE 'user:%' AND on_behalf_of IS NULL AND channel IN ('http', 'cli')));

-- One row per imported record: the record id of the source system is the idempotency key in its journal. What the
-- record claims (Standing, timestamps) is provenance only: the note is `pending` until a curator acts (§8.2).
CREATE TABLE note_import (
    book             text NOT NULL REFERENCES journal(book),
    record           text NOT NULL CHECK (record ~ '^[A-Za-z0-9._:-]{1,128}$'),
    note_seq         bigint NOT NULL,
    write_seq        bigint NOT NULL REFERENCES write_record(seq),
    standing_claimed text CHECK (standing_claimed IN ('approved', 'pending', 'rejected', 'retired')),
    created_at       timestamptz,               -- the original timestamps, as the record states them
    updated_at       timestamptz,
    imported_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (book, record),
    FOREIGN KEY (note_seq, book) REFERENCES note (seq, book)
);
CREATE INDEX note_import_note ON note_import (note_seq);
