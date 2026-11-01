"""App version (user, 2026-11-01): calendar versioning, YYYY.MM.DD.N = release date + the Nth update that day, plus the
release time. Never edit by hand: `python app/bump_version.py` sets both and adds the heading to docs/Changelog.MD.
Shown in the website footer, /api/health and the admin console; tags the Docker image."""

VERSION = "2026.11.01.7"
RELEASED = "2026-11-01T17:01"  # local time of the release
APP_VERSION = f"{VERSION} (beta)"
