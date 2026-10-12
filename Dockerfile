# Kütüphane Core: one Python app (API + MCP). Build once with network access, then ship the image offline.
FROM python:3.12-slim

RUN useradd --system --uid 10001 --home /app kutuphane
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && rm -rf /root/.cache

USER kutuphane
EXPOSE 8080
CMD ["uvicorn", "--factory", "kutuphane.server:app_from_env", "--host", "0.0.0.0", "--port", "8080", \
     "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
