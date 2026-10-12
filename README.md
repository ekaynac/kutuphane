# Kütüphane

Versioned, explainable knowledge access for people and LLM agents, on-prem and air-gapped.
Decisions: `docs/01-direction-decisions.md`. Product: `docs/05`–`07`. Proprietary, see `LICENSE`.

## Development (M1a)

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
printf 'KUTUPHANE_DB_PASSWORD=%s\n' "$(python3 -c 'import secrets;print(secrets.token_urlsafe(24))')" > .env
docker compose up -d --wait postgres
docker compose exec -T postgres psql -U kutuphane -c 'CREATE DATABASE kutuphane_test'

set -a; . ./.env; set +a
export KUTUPHANE_DSN="postgresql://kutuphane:${KUTUPHANE_DB_PASSWORD}@127.0.0.1:55432/kutuphane"
export KUTUPHANE_TEST_DSN="${KUTUPHANE_DSN}_test"
.venv/bin/python -m pytest -q

.venv/bin/kutuphane migrate
.venv/bin/kutuphane ingest tests/fixtures/okf-kitap --book ornek \
  --sensitivity normal --egress local_only --protection standard
.venv/bin/kutuphane show ornek
```

Disk encryption is a deployment requirement at the volume level (D48); the application does not encrypt.
