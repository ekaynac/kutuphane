"""#242: the standalone compose pairs its embedder URL with the class `local` (C3), and `compose.nomodels.yaml` is the
switch-off and the way to another embedder. `docker compose config` level; skipped only without docker compose."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV = {"KUTUPHANE_VERSION": "v0.0.0", "KUTUPHANE_DB_PASSWORD": "x", "PATH": os.environ["PATH"]}


def _compose_available() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=60).returncode == 0


pytestmark = pytest.mark.skipif(not _compose_available(), reason="needs docker compose")
STAGES = ("EMBED", "RERANK")


def _config(*files: str, cwd: Path = ROOT, env: dict | None = None) -> dict:
    """A `config` error with compose available is a failure of the test, never a skip."""
    cmd = ["docker", "compose", *[a for f in files for a in ("-f", f)], "config", "--format", "json"]
    out = subprocess.run(cmd, cwd=cwd, env={**ENV, **(env or {})}, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _core_env(config: dict) -> dict:
    return config["services"]["core"]["environment"]


def test_default_pairs_the_internal_url_with_class_local():
    env = _core_env(_config("compose.yaml"))
    for stage in STAGES:
        assert env[f"KUTUPHANE_{stage}_PROVIDER"] == "openai"
        assert env[f"KUTUPHANE_{stage}_OPENAI_URL"] == "http://embedder:8000"
        assert env[f"KUTUPHANE_{stage}_OPENAI_CLASS"] == "local"


def test_a_url_or_class_of_the_operator_cannot_change_the_bundled_pair():
    env = _core_env(_config("compose.yaml", env={"KUTUPHANE_EMBED_OPENAI_URL": "https://models.example",
                                                  "KUTUPHANE_RERANK_OPENAI_CLASS": "cloud"}))
    assert env["KUTUPHANE_EMBED_OPENAI_URL"] == "http://embedder:8000" and env["KUTUPHANE_EMBED_OPENAI_CLASS"] == "local"
    assert env["KUTUPHANE_RERANK_OPENAI_CLASS"] == "local"  # with its own URL; no operator value is read


def test_nomodels_gives_no_class_for_a_url_of_the_operator():
    env = _core_env(_config("compose.yaml", "compose.nomodels.yaml",
                            env={"KUTUPHANE_EMBED_PROVIDER": "openai", "KUTUPHANE_EMBED_OPENAI_URL": "http://other:9"}))
    assert env["KUTUPHANE_EMBED_OPENAI_URL"] == "http://other:9"
    assert env["KUTUPHANE_EMBED_OPENAI_CLASS"] == ""  # Core refuses to start: tests/test_openai_provider.py
    assert env["KUTUPHANE_RERANK_OPENAI_CLASS"] == "" and env["KUTUPHANE_RERANK_OPENAI_URL"] == ""
    assert _core_env(_config("compose.yaml", "compose.nomodels.yaml",
                             env={"KUTUPHANE_EMBED_OPENAI_CLASS": "cloud"}))["KUTUPHANE_EMBED_OPENAI_CLASS"] == "cloud"


def test_nomodels_override_removes_the_embedder_dependency_and_the_model_calls():
    base = _config("compose.yaml")
    assert "embedder" in base["services"]["core"]["depends_on"]
    assert "profiles" not in base["services"]["embedder"]
    off = _config("compose.yaml", "compose.nomodels.yaml")
    assert set(off["services"]["core"]["depends_on"]) == {"postgres"}
    # in a profile that nothing turns on: `config` (like `up`) leaves them out
    assert not {"embedder", "models-fetch"} & set(off["services"])
    env = _core_env(off)
    assert env["KUTUPHANE_EMBED_PROVIDER"] == env["KUTUPHANE_RERANK_PROVIDER"] == "llmdap"


def test_a_config_error_fails_the_test(tmp_path):
    (tmp_path / "broken.yaml").write_text("services:\n  core: [not, a, mapping\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        _config(str(ROOT / "compose.yaml"), str(tmp_path / "broken.yaml"), cwd=tmp_path)
