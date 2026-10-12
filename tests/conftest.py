import os
import shutil
from pathlib import Path

import pytest

from kutuphane import db

FIXTURES = Path(__file__).parent / "fixtures"
TEST_DSN_ENV = "KUTUPHANE_TEST_DSN"


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
