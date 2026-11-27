"""deploy/nginx.conf (the release ingress): its body limits must never be lower than Core's own limits, or nginx
answers 413 with its own page and Core's limit and error text never apply."""
import re
from pathlib import Path

from kutuphane import packages

ROOT = Path(__file__).resolve().parents[1]
CONF = (ROOT / "deploy" / "nginx.conf").read_text()
UNITS = {"": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3}
ENVELOPE = 1024 * 1024  # margin for the JSON envelope around a base64 package


def _limit(block: str) -> int:
    m = re.search(r"^\s*client_max_body_size\s+(\d+)([kmg]?)\s*;", block, re.M | re.I)
    assert m, "client_max_body_size not set"
    return int(m.group(1)) * UNITS[m.group(2).lower()]


def _location_package_upload() -> str:
    m = re.search(r"location\s*=\s*/v1/packages\s*\{(.*?)\n    \}", CONF, re.S)
    assert m, "no `location = /v1/packages` block"
    return m.group(1)


def _server_level() -> str:
    return re.sub(r"location\s.*?\n    \}", "", CONF, flags=re.S)


def test_package_upload_limit_covers_max_package_bytes_as_base64():
    base64_size = (packages.MAX_PACKAGE_BYTES + 2) // 3 * 4
    assert _limit(_location_package_upload()) >= base64_size + ENVELOPE, (
        "nginx would refuse a package that Core accepts: raise client_max_body_size in the /v1/packages location")


def test_default_limit_covers_the_mcp_transport_limit():
    from mcp.server.sse import DEFAULT_MAX_REQUEST_BODY_SIZE
    assert _limit(_server_level()) >= DEFAULT_MAX_REQUEST_BODY_SIZE


def test_both_compose_files_mount_this_conf():
    assert "./deploy/nginx.conf:/etc/nginx/conf.d/default.conf" in (ROOT / "compose.yaml").read_text()
    assert "./nginx.conf:/etc/nginx/conf.d/default.conf" in (ROOT / "deploy" / "compose.full.yaml").read_text()
