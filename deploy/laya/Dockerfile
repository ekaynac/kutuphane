# Laya (Convai, Apache-2.0 open weights) as an on-prem typed-decision server behind LLMDAP (`systemone` route, #225).
# The weights are not in the image: the Hugging Face cache is mounted read-only and the container has no network out.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch==2.14.1 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd -u 65532 -M laya
USER 65532
ENV HF_HOME=/hf HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 LAYA_HOST=0.0.0.0 LAYA_PORT=8000
CMD ["laya-serve"]
