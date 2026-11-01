import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "app"))

from bump_version import next_version  # noqa: E402

from backend.version import APP_VERSION, RELEASED, VERSION  # noqa: E402


def test_next_version_counts_per_day():
    assert next_version("2026.11.01.6", datetime(2026, 11, 1, 18)) == "2026.11.01.7"
    assert next_version("2026.11.01.6", datetime(2026, 11, 2, 9)) == "2026.11.02.1"
    assert next_version("2026.12.31.9", datetime(2027, 1, 1)) == "2027.01.01.1"


def test_version_matches_release_and_changelog():
    assert re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.\d+", VERSION) and APP_VERSION == f"{VERSION} (beta)"
    date, time = RELEASED.split("T")
    assert VERSION.startswith(date.replace("-", ".") + ".") and re.fullmatch(r"\d{2}:\d{2}", time)
    first = next(line for line in (ROOT / "docs" / "Changelog.MD").read_text(encoding="utf-8").splitlines()
                 if line.startswith("## ") and not line.startswith("## Versioning"))
    assert first == f"## {VERSION} — {time}"  # newest entry = the current version
