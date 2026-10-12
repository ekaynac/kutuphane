-- Astra review #2: the access log names exactly what was handed out (AT-09), and every model call has its own id
-- so one LLMDAP record can never stand in for two calls.
ALTER TABLE access_event ADD COLUMN profile_id text;
ALTER TABLE access_event ADD COLUMN items jsonb;  -- citation handles delivered (search, cite)

ALTER TABLE model_call ADD COLUMN call_id text;  -- the correlation id actually sent to LLMDAP for this call
UPDATE model_call SET call_id = correlation_id WHERE call_id IS NULL;
ALTER TABLE model_call ALTER COLUMN call_id SET NOT NULL;
CREATE UNIQUE INDEX model_call_call_id ON model_call (call_id);
ALTER TABLE model_call ADD COLUMN source_books text[] NOT NULL DEFAULT '{}';
