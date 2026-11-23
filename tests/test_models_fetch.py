"""#242: `deploy/models/server.py fetch` (compose service `models-fetch`) never contacts the Hub for a commit that is in
the cache, so a volume that was filled by hand works with no network. torch, transformers and the Hub client are stubbed."""
import importlib.util
import logging
import sys
import types
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parent.parent / "deploy" / "models" / "server.py"


class LocalEntryNotFoundError(Exception):
    pass


@pytest.fixture
def server(monkeypatch):
    calls: list[dict] = []
    state = {"cached": set(), "network": True}

    def snapshot_download(repo, revision=None, allow_patterns=None, local_files_only=False):
        calls.append({"repo": repo, "revision": revision, "local_files_only": local_files_only})
        if local_files_only:
            if (repo, revision) not in state["cached"]:
                raise LocalEntryNotFoundError(repo)
        elif not state["network"]:
            raise ConnectionError("Temporary failure in name resolution")
        else:
            state["cached"].add((repo, revision))
        return "/hf/x"

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
    spec = importlib.util.spec_from_file_location("models_server_under_test", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.calls, module.state = calls, state
    return module


def test_a_cached_commit_is_not_looked_up_on_the_hub(server, caplog):
    server.state["cached"] = set(server.PINNED.items())
    server.state["network"] = False  # any call without local_files_only would raise
    with caplog.at_level(logging.INFO, logger="models"):
        server.fetch()
    assert [c["local_files_only"] for c in server.calls] == [True, True]
    assert [(c["repo"], c["revision"]) for c in server.calls] == list(server.PINNED.items())
    assert caplog.text.count("is in the cache; no download") == 2


def test_a_missing_commit_is_downloaded_and_the_next_run_downloads_nothing(server, caplog):
    with caplog.at_level(logging.INFO, logger="models"):
        server.fetch()
    assert [c["local_files_only"] for c in server.calls] == [True, False, True, False]
    assert caplog.text.count("downloading from the Hub") == 2
    server.calls.clear()
    server.fetch()
    assert all(c["local_files_only"] for c in server.calls)


def test_an_empty_cache_and_no_network_fail_and_name_the_revision(server, caplog):
    server.state["network"] = False
    with caplog.at_level(logging.INFO, logger="models"), pytest.raises(ConnectionError):
        server.fetch()
    repo, revision = next(iter(server.PINNED.items()))
    assert f"cannot fetch {repo}@{revision}: not in the cache" in caplog.text
