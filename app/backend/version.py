"""App version (user, 2026-11-01): calendar versioning, YYYY.MM.DD.N = release date + the Nth update that day, plus the
release time. Never edit by hand: `python app/bump_version.py` sets both and adds the heading to docs/Changelog.MD.
VERSION (full) tags the Docker image, GitHub commits and changelog entries; people see the short form (user,
2026-11-01): "Beta v26.11.1-7" in the website footer, /api/health and the admin console."""

VERSION = "2026.11.06.11"
RELEASED = "2026-11-06T15:21"  # local time of the release


def short(version: str) -> str:
    """2026.11.01.7 -> v26.11.1-7 (two-digit year, no leading zeros, update of the day after the dash)."""
    y, m, d, n = version.split(".")
    return f"v{y[2:]}.{int(m)}.{int(d)}-{n}"


APP_VERSION = f"Beta {short(VERSION)}"
