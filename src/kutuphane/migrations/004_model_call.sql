-- M1c: Core's own record of every call it sent through LLMDAP, joinable with LLMDAP's audit (D35, AT-09).
CREATE TABLE model_call (
    id                     bigserial PRIMARY KEY,
    at                     timestamptz NOT NULL DEFAULT now(),
    correlation_id         text NOT NULL,
    derived_correlation_id text,          -- what LLMDAP stored (x-llmdap-correlation-id-derived); null if no answer
    principal              text NOT NULL,
    on_behalf_of           text,
    route                  text NOT NULL,
    model                  text NOT NULL,
    http_status            integer,
    error                  text
);
CREATE INDEX model_call_correlation ON model_call (correlation_id);
