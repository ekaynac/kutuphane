"""#242: `deploy/models/server.py fetch` (compose service `models-fetch`). A commit counts as present only when every
file of manifest.json is in the snapshot with its size (an interrupted download leaves a partial folder); a complete
one needs no network. Real Hugging Face cache layout on disk (snapshots/<commit>/<file> -> ../../blobs/<blob>); torch,
transformers and the Hub client are stubbed, so nothing reaches the network."""
import importlib.util
import json
import logging
import os
import sys
import types
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy" / "models"
SMALL = {"config.json": b"{}", "weights.bin": b"w" * 40}


def _layout(cache: Path, repo: str, revision: str, files: dict[str, bytes]) -> None:
    root = cache / f"models--{repo.replace('/', '--')}"
    (root / "snapshots" / revision).mkdir(parents=True, exist_ok=True)
    (root / "blobs").mkdir(exist_ok=True)
    for name, data in files.items():
        (root / "blobs" / f"blob-{name}").write_bytes(data)
        link = root / "snapshots" / revision / name
        if not link.is_symlink():
            link.symlink_to(f"../../blobs/blob-{name}")


@pytest.fixture
def server(monkeypatch, tmp_path):
    """The Hub client as it behaves: a file that is in the snapshot is trusted (no size check, never rewritten) unless
    `force_download=True`; a missing file is downloaded (complete and linked) when the network answers."""
    cache, calls = tmp_path / "hub", []
    state = {"network": True}

    def hf_hub_download(repo, filename, revision=None, force_download=False):
        calls.append({"repo": repo, "file": filename, "revision": revision, "force": force_download})
        root = cache / f"models--{repo.replace('/', '--')}"
        link = root / "snapshots" / revision / filename
        if link.exists() and not force_download:
            return str(link)  # present: trusted, whatever its size
        if not state["network"]:
            raise ConnectionError("Temporary failure in name resolution")
        (root / "snapshots" / revision).mkdir(parents=True, exist_ok=True)
        (root / "blobs").mkdir(exist_ok=True)
        (root / "blobs" / f"blob-{filename}").write_bytes(SMALL[filename])
        if not link.is_symlink():
            link.symlink_to(f"../../blobs/blob-{filename}")
        return str(link)

    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    stubs = {"torch": types.ModuleType("torch"), "transformers": types.ModuleType("transformers"),
             "huggingface_hub": types.ModuleType("huggingface_hub")}
    stubs["torch"].inference_mode = lambda: (lambda fn: fn)  # a decorator at import
    stubs["huggingface_hub"].hf_hub_download = hf_hub_download
    stubs["huggingface_hub"].snapshot_download = lambda *a, **k: pytest.fail("fetch must not use snapshot_download")
    for name in ("AutoModel", "AutoModelForSequenceClassification", "AutoTokenizer"):
        setattr(stubs["transformers"], name, object)
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("models_server_under_test", DEPLOY / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MANIFEST = {repo: {"revision": rev, "files": {n: {"size": len(d)} for n, d in SMALL.items()}}
                       for repo, rev in module.PINNED.items()}
    module.calls, module.state, module.cache, module.download = calls, state, cache, hf_hub_download
    return module


def _seed(server, *, only=None) -> None:
    for repo, revision in server.PINNED.items():
        if only is None or repo == only:
            _layout(server.cache, repo, revision, SMALL)


def test_the_manifest_matches_the_pinned_commits_and_the_files_the_server_needs():
    manifest = json.loads((DEPLOY / "manifest.json").read_text(encoding="utf-8"))
    source = (DEPLOY / "server.py").read_text(encoding="utf-8")
    for repo, entry in manifest.items():
        assert f'"{entry["revision"]}"' in source, repo
        assert {"config.json", "tokenizer.json", "tokenizer_config.json", "sentencepiece.bpe.model"} <= set(entry["files"])
        assert all(isinstance(m["size"], int) and m["size"] > 0 and len(m["blob"]) in (40, 64) for m in entry["files"].values())
    assert "pytorch_model.bin" in manifest["BAAI/bge-m3"]["files"]
    assert "model.safetensors" in manifest["BAAI/bge-reranker-v2-m3"]["files"]


def test_a_complete_cache_is_not_downloaded_and_needs_no_network(server, caplog):
    _seed(server)
    server.state["network"] = False  # a download would raise
    with caplog.at_level(logging.INFO, logger="models"):
        server.fetch()
    assert server.calls == []  # the Hub client is not called at all
    assert caplog.text.count("in the cache and complete; no download") == 2


def test_an_empty_cache_is_downloaded_file_by_file_then_verified(server):
    server.fetch()
    assert {c["file"] for c in server.calls} == set(SMALL) and not any(c["force"] for c in server.calls)
    server.calls.clear()
    server.fetch()
    assert server.calls == []


def _break(server, how: str) -> str:
    repo, revision = next(iter(server.PINNED.items()))
    snap = server.cache / f"models--{repo.replace('/', '--')}"
    if how == "missing":
        (snap / "snapshots" / revision / "weights.bin").unlink()
    elif how == "dangling":
        (snap / "blobs" / "blob-weights.bin").unlink()
    elif how == "truncated":
        (snap / "blobs" / "blob-weights.bin").write_bytes(b"w" * 7)
    return repo


def test_the_hub_client_stub_keeps_a_truncated_file_unless_forced(server):
    """Why the first fix looped: the client trusts a file that is there, so only force_download repairs it."""
    _seed(server)
    repo = _break(server, "truncated")
    revision = server.PINNED[repo]
    server.download(repo, "weights.bin", revision=revision)
    assert server.snapshot_problems(repo) == {"weights.bin": "size 7, expected 40"}
    server.download(repo, "weights.bin", revision=revision, force_download=True)
    assert server.snapshot_problems(repo) == {}


@pytest.mark.parametrize("how", ["missing", "dangling", "truncated"])
def test_an_incomplete_snapshot_is_repaired_file_by_file_when_the_hub_answers(server, how):
    _seed(server)
    repo = _break(server, how)
    server.fetch()
    assert [(c["file"], c["force"]) for c in server.calls] == [("weights.bin", how == "truncated")]
    assert server.snapshot_problems(repo) == {}  # verified again after the download


@pytest.mark.parametrize("how", ["missing", "dangling", "truncated"])
def test_an_incomplete_snapshot_without_network_fails_and_names_the_files(server, caplog, how):
    _seed(server)
    repo = _break(server, how)
    server.state["network"] = False
    with caplog.at_level(logging.INFO, logger="models"), pytest.raises(ConnectionError):
        server.fetch()
    expected = {"missing": "weights.bin (missing)", "dangling": "weights.bin (missing)",
                "truncated": "weights.bin (size 7, expected 40)"}[how]
    assert f"cannot fetch {repo}@{server.PINNED[repo]}: the cache lacks {expected}" in caplog.text


def test_a_download_that_leaves_a_file_wrong_is_an_error(server, caplog):
    _seed(server)
    _break(server, "truncated")
    server.MANIFEST = {r: {**e, "files": {**e["files"], "weights.bin": {"size": 999}}} for r, e in server.MANIFEST.items()}
    with caplog.at_level(logging.INFO, logger="models"), pytest.raises(SystemExit):
        server.fetch()
    assert "still wrong after the download: weights.bin (size 40, expected 999)" in caplog.text


def test_an_empty_cache_without_network_names_every_file(server, caplog):
    server.state["network"] = False
    with caplog.at_level(logging.INFO, logger="models"), pytest.raises(ConnectionError):
        server.fetch()
    repo, revision = next(iter(server.PINNED.items()))
    assert f"cannot fetch {repo}@{revision}: the cache lacks config.json (missing), weights.bin (missing)" in caplog.text
