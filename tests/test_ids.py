import pytest

from kutuphane import ids


def test_content_id_ignores_order():
    a = ids.content_id({"a.md": "1" * 64, "b/c.md": "2" * 64})
    b = ids.content_id({"b/c.md": "2" * 64, "a.md": "1" * 64})
    assert a == b and a.startswith("ct_")


def test_content_id_tracks_bytes_and_paths():
    base = ids.content_id({"a.md": "1" * 64})
    assert ids.content_id({"a.md": "3" * 64}) != base
    assert ids.content_id({"z.md": "1" * 64}) != base


def test_kinds_never_collide():
    body = {"x": 1}
    assert len({ids.profile_id(body)[3:], ids.policy_id(body)[3:]}) == 2


def test_paths_are_normalized_nfc():
    decomposed = "ş"  # s + combining cedilla
    assert ids.normalize_path(f"{decomposed}.md") == "ş.md"


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x.md", "a/../b.md", "a//b.md", "./a.md", ""])
def test_unsafe_paths_rejected(bad):
    with pytest.raises(ValueError):
        ids.normalize_path(bad)
