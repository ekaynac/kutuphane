# Local CPU embedder and reranker (D61) behind the LLMDAP routes `emb` and `rerank`: BAAI/bge-m3 and
# BAAI/bge-reranker-v2-m3 at the commits pinned in server.py. Same pattern as deploy/laya: CPU torch, no weights in
# the image (the Hugging Face cache is mounted read-only), the container has no network out, non-root.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd -u 65532 -M models
COPY server.py /srv/server.py
USER 65532
ENV HF_HOME=/hf HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1
CMD ["python", "-I", "/srv/server.py"]
