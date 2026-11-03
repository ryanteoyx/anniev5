"""Shared test helper: run annie_core against a throwaway folder so tests never touch the real database or files."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import annie_core as annie  # noqa: E402

SAMPLES = ROOT / "samples"


def fresh():
    """A brand-new, empty Annie in a temporary folder. Returns (annie module, connection, temp path)."""
    tmp = Path(tempfile.mkdtemp(prefix="annie-test-"))
    annie.FILE_DIR = tmp / "files"
    annie.ARCHIVE_DIR = tmp / "archive"
    annie.REFERENCE_FOLDER = tmp / "reference_samples"
    annie._REFERENCE_PROFILE_CACHE.update(signature=None, profiles=[])
    return annie, annie.connect(tmp / "annie.db"), tmp


def load_samples(annie, con):
    """Ingest every sample PDF in file-name order, exactly like uploads. Returns the per-file results."""
    out = {}
    for p in sorted(SAMPLES.glob("*.pdf")):
        out[p.name] = annie.ingest_file(con, p.name, p.read_bytes(), channel="UPLOAD")
    return out
