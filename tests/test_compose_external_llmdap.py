"""#242: deploy/compose.external-llmdap.yaml puts the four model servers on the external LLMDAP network and keeps
their other networks. Skipped only if `docker compose version` fails; a config error fails the test."""
import json
import os
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def _compose_ok() -> bool:
    try:
        return subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _compose_ok(), reason="docker compose is missing")

EXPECTED = {
    "embedder": {"models"},
    "spark-chat": {"models", "spark"},
    "reranker-gpu": {"models"},
    "model-stub": {"models"},
}


def test_model_servers_join_the_external_network():
    env = {**os.environ, "LLMDAP_NETWORK": "x", "KUTUPHANE_VERSION": "v0", "KUTUPHANE_DB_PASSWORD": "x"}
    r = subprocess.run(
        ["docker", "compose", "-f", str(DEPLOY / "compose.full.yaml"), "-f", str(DEPLOY / "compose.external-llmdap.yaml"),
         "--profile", "local-models", "--profile", "gpu-rerank", "--profile", "dev-models", "config", "--format", "json"],
        capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    cfg = json.loads(r.stdout)
    assert cfg["networks"]["llmdap"]["name"] == "x" and cfg["networks"]["llmdap"]["external"] is True
    for name, others in EXPECTED.items():
        assert set(cfg["services"][name]["networks"]) == others | {"llmdap"}, name
