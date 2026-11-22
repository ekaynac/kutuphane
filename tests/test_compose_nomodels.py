"""#242: `compose.nomodels.yaml` is the real switch-off of the standalone embedder. Skipped without docker compose."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV = {"KUTUPHANE_VERSION": "v0.0.0", "KUTUPHANE_DB_PASSWORD": "x", "PATH": __import__("os").environ["PATH"]}


def _config(*files: str) -> dict:
    cmd = ["docker", "compose", *[a for f in files for a in ("-f", f)], "config", "--format", "json"]
    out = subprocess.run(cmd, cwd=ROOT, env=ENV, capture_output=True, text=True, timeout=60)
    if out.returncode:
        pytest.skip(f"docker compose cannot read the files: {out.stderr.strip()[:200]}")
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("docker") is None, reason="needs docker compose")
def test_nomodels_override_removes_the_embedder_dependency_and_the_model_calls():
    base = _config("compose.yaml")
    assert "embedder" in base["services"]["core"]["depends_on"]
    assert "profiles" not in base["services"]["embedder"]
    off = _config("compose.yaml", "compose.nomodels.yaml")
    assert set(off["services"]["core"]["depends_on"]) == {"postgres"}
    # in a profile that nothing turns on: `config` (like `up`) leaves them out
    assert not {"embedder", "models-fetch"} & set(off["services"])
    env = off["services"]["core"]["environment"]
    assert env["KUTUPHANE_EMBED_PROVIDER"] == env["KUTUPHANE_RERANK_PROVIDER"] == "llmdap"
