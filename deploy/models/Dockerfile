# Local CPU embedder and reranker (D61): BAAI/bge-m3 and BAAI/bge-reranker-v2-m3 at the commits pinned in
# server.py (the exact files and sizes: manifest.json), behind the LLMDAP routes `emb` and `rerank` (full stack) or
# called directly (compose.yaml). CPU torch, no weights in the image: /hf is the Hugging Face cache, a mounted volume.
# The server has no network out and runs non-root. `python /srv/server.py fetch` (the `models-fetch` service) fills
# the cache from the Hub.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd -u 65532 -M models \
 && mkdir /hf && chown 65532 /hf   # a new named volume at /hf takes this owner
COPY server.py manifest.json /srv/
USER 65532
ENV HF_HOME=/hf HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
CMD ["python", "-I", "/srv/server.py"]
