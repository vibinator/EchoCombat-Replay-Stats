"""Test app wired to a temporary replay "share"; scans run only when a test calls sync()."""

from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.scanner import scan_once


def make_settings(tmp_path: Path, **overrides) -> Settings:
    share = tmp_path / "share"
    share.mkdir(exist_ok=True)
    values = dict(data_dir=tmp_path / "data", source_dir=share, workers=0, settle_s=0, auto_scan=False, import_api=True,
                  scraper_guard=False, counted_stats=False)  # synthetic matches are seconds long: every game counts in averages
    return Settings(**(values | overrides))


@contextmanager
def app_client(settings: Settings):
    with TestClient(create_app(settings), client=("127.0.0.1", 50000)) as client:  # a private peer, like cloudflared
        yield client


def write(settings: Settings, files: dict[str, bytes]) -> None:
    for rel, content in files.items():
        path = settings.source_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def sync(client: TestClient) -> int:
    """Scan the share and wait until every queued replay is processed. Returns replays queued."""
    state = client.app.state
    queued = scan_once(state.sessionmaker, state.settings, state.scanner.state)
    state.worker.notify()
    state.worker.wait_idle()
    return queued


def add(client: TestClient, files: dict[str, bytes]) -> None:
    write(client.app.state.settings, files)
    sync(client)


def replay_by_path(client: TestClient, rel: str) -> dict:
    items = client.get("/api/replays", params={"limit": 200}).json()["items"]
    return next(r for r in items if r["source_path"] == rel)


def act(client: TestClient, action, *args):
    """Run an admin console action (backend.admin_actions) against the test app's database."""
    with client.app.state.sessionmaker() as db:
        return action(db, *args)
