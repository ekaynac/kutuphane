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


class LocalEntryNotFoundError(Exception):
    pass


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
    cache, calls = tmp_path / "hub", []
    state = {"network": True, "interrupt": False}

    def snapshot_download(repo, revision=None, allow_patterns=None, local_files_only=False):
        calls.append({"repo": repo, "revision": revision, "local_files_only": local_files_only})
        snap = cache / f"models--{repo.replace('/', '--')}" / "snapshots" / revision
        if local_files_only:
            if not snap.is_dir():
                raise LocalEntryNotFoundError(repo)
            return str(snap)
        if not state["network"]:
            raise ConnectionError("Temporary failure in name resolution")
        _layout(cache, repo, revision, SMALL)  # a download completes the whole snapshot (and repairs links)
        for name, data in SMALL.items():
            (cache / f"models--{repo.replace('/', '--')}" / "blobs" / f"blob-{name}").write_bytes(data)
        return str(snap)

    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    stubs = {"torch": types.ModuleType("torch"), "transformers": types.ModuleType("transformers"),
             "huggingface_hub": types.ModuleType("huggingface_hub"),
             "huggingface_hub.errors": types.ModuleType("huggingface_hub.errors")}
    stubs["torch"].inference_mode = lambda: (lambda fn: fn)  # a decorator at import
    stubs["huggingface_hub"].snapshot_download = snapshot_download
    stubs["huggingface_hub.errors"].LocalEntryNotFoundError = LocalEntryNotFoundError
    for name in ("AutoModel", "AutoModelForSequenceClassification", "AutoTokenizer"):
        setattr(stubs["transformers"], name, object)
    for name, module in stubs.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("models_server_under_test", DEPLOY / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.MANIFEST = {repo: {"revision": rev, "files": {n: {"size": len(d)} for n, d in SMALL.items()}}
                       for repo, rev in module.PINNED.items()}
    module.calls, module.state, module.cache = calls, state, cache
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


def test_an_empty_cache_is_downloaded_then_verified(server):
    server.fetch()
    assert [c["local_files_only"] for c in server.calls] == [False, False]
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


@pytest.mark.parametrize("how", ["missing", "dangling", "truncated"])
def test_an_incomplete_snapshot_is_downloaded_again_when_the_hub_answers(server, how):
    _seed(server)
    repo = _break(server, how)
    server.fetch()
    assert {"repo": repo, "revision": server.PINNED[repo], "local_files_only": False} in server.calls
    assert server.snapshot_problems(repo) == []  # verified again after the download


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
