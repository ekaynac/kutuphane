import os
import shutil
from pathlib import Path

import pytest

from kutuphane import db

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DSN_ENV = "KUTUPHANE_TEST_DSN"
# Migrations that add a column which today's write path fills, and that do not depend on the migrations after the
# step under test: a test that writes with today's code into an old schema applies them first.
WRITE_PATH_COLUMNS = ("047_note_applies_to.sql",)


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF with a text layer (ASCII text, Helvetica). Deterministic bytes."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


@pytest.fixture(autouse=True)
def _no_skillspector(monkeypatch):
    """Every test starts without a configured SkillSpector (D71): a scan runs only where a test sets one up. The
    contract test reads KUTUPHANE_SKILLSPECTOR_BIN when it is collected, before this runs."""
    for name in ("KUTUPHANE_SKILLSPECTOR_BIN", "KUTUPHANE_SKILLSPECTOR_ALLOW_VERSION", "KUTUPHANE_SKILLSPECTOR_TIMEOUT",
                 "KUTUPHANE_SKILLSPECTOR_PROXY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def okf_dir(tmp_path) -> Path:
    dest = tmp_path / "okf-kitap"
    shutil.copytree(FIXTURES / "okf-kitap", dest)
    return dest


@pytest.fixture
def conn():
    dsn = os.environ.get(TEST_DSN_ENV)
    if not dsn:
        pytest.skip(f"{TEST_DSN_ENV} not set (see README: docker compose up -d postgres)")
    with db.connect(dsn) as c:
        name = c.execute("SELECT current_database()").fetchone()[0]
        if not name.endswith("_test"):
            pytest.fail(f"refusing to reset non-test database {name!r}")
        c.execute("DROP SCHEMA public CASCADE")
        c.execute("CREATE SCHEMA public")
        db.migrate(c)
        yield c


@pytest.fixture
def conn2(conn):
    """A second, independent session on the same test database (for race tests)."""
    with db.connect(os.environ[TEST_DSN_ENV]) as c:
        yield c


@pytest.fixture
def conn_b(conn):
    """A second installation: its own schema in the test database, fully migrated."""
    conn.execute("DROP SCHEMA IF EXISTS install_b CASCADE")
    conn.execute("CREATE SCHEMA install_b")
    with db.connect(os.environ[TEST_DSN_ENV] + "?options=-csearch_path%3Dinstall_b,public") as c:
        db.migrate(c)
        yield c
    conn.execute("DROP SCHEMA IF EXISTS install_b CASCADE")
