-- #156: a consumer's own correlation id (HTTP `X-Correlation-Id`, MCP `_meta["kutuphane/correlation-id"]`), stored
-- next to ours. It is a label only: never a right, never an idempotency key. NULL when the caller sent none. The
-- pattern is LLMDAP's correlation id pattern with a shorter limit, so `<caller>.<ours>.<n>` still fits LLMDAP.
ALTER TABLE access_event ADD COLUMN caller_correlation_id text
    CHECK (caller_correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$');
ALTER TABLE model_call ADD COLUMN caller_correlation_id text
    CHECK (caller_correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$');
ALTER TABLE write_record ADD COLUMN caller_correlation_id text
    CHECK (caller_correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$');
-- A background ask runs later, in a worker: its model calls carry the id of the request that submitted it.
ALTER TABLE ask_job ADD COLUMN caller_correlation_id text
    CHECK (caller_correlation_id ~ '^[A-Za-z0-9][A-Za-z0-9._:-]{7,63}$');
-- `kutuphane explain` accepts either id.
CREATE INDEX access_event_caller_correlation ON access_event (caller_correlation_id)
    WHERE caller_correlation_id IS NOT NULL;
CREATE INDEX model_call_caller_correlation ON model_call (caller_correlation_id)
    WHERE caller_correlation_id IS NOT NULL;
