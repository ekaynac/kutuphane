# Kütüphane Core: one Python app (API + MCP + UI). Build once with network access, then ship the image offline.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# Debian 13 (trixie): its git is 2.47. The code citation verifier needs git >= 2.45 (docs/24 §10.2:
# GIT_NO_LAZY_FETCH, cat-file -z); Debian 12 has 2.39, so the base is pinned to trixie and the build checks it.
FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/* \
    && python -c "import subprocess, sys; v = subprocess.check_output(['git', '--version'], text=True).split()[2]; \
sys.exit(f'git {v} < 2.45' if tuple(map(int, v.split('.')[:2])) < (2, 45) else 0)"
RUN useradd --system --uid 10001 --home /app kutuphane
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache
COPY --from=web /web/dist /app/ui
ENV KUTUPHANE_UI_DIR=/app/ui

USER kutuphane
EXPOSE 8080
CMD ["uvicorn", "--factory", "kutuphane.server:app_from_env", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
