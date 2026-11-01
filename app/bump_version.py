"""Next app version: python app/bump_version.py

Calendar versioning (user, 2026-11-01): YYYY.MM.DD.N, N = the Nth update that day (1 on a new day). Sets VERSION and
RELEASED (now, local time) in app/backend/version.py and adds an empty "## <version> — HH:MM" entry at the top of
docs/Changelog.MD for the notes. Prints the new version."""

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "app" / "backend" / "version.py"
CHANGELOG = ROOT / "docs" / "Changelog.MD"
SEPARATOR = "\n---\n\n"  # end of the changelog's intro; entries follow, newest first


def next_version(current: str, now: datetime) -> str:
    today = now.strftime("%Y.%m.%d")
    day, _, n = current.rpartition(".")
    return f"{today}.{int(n) + 1 if day == today else 1}"


def _newline(path: Path) -> str:
    """Keep each file's line endings (read_text turns them into \\n)."""
    return "\r\n" if b"\r\n" in path.read_bytes() else "\n"


def main() -> None:
    now = datetime.now()
    source = VERSION_FILE.read_text(encoding="utf-8")
    current = re.search(r'^VERSION = "([^"]+)"', source, re.M).group(1)
    version = next_version(current, now)
    source = re.sub(r'^VERSION = "[^"]+"', f'VERSION = "{version}"', source, flags=re.M)
    source = re.sub(r'^RELEASED = "[^"]+"', f'RELEASED = "{now:%Y-%m-%dT%H:%M}"', source, flags=re.M)
    VERSION_FILE.write_text(source, encoding="utf-8", newline=_newline(VERSION_FILE))

    newline = _newline(CHANGELOG)
    log = CHANGELOG.read_text(encoding="utf-8")
    head, sep, rest = log.partition(SEPARATOR)
    if not sep:
        sys.exit(f"{CHANGELOG}: intro separator '---' not found")
    CHANGELOG.write_text(f"{head}{sep}## {version} — {now:%H:%M}\n\n{rest}", encoding="utf-8", newline=newline)
    print(version)


if __name__ == "__main__":
    main()
