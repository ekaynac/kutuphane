# Kütüphane Core: one Python app (API + MCP + UI). Build once with network access, then ship the image offline.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
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
