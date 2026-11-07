"""Mint a staff session cookie for local end-to-end testing (docs/reference/E2E-TESTING.md).

    python app/tools/e2e/local_login.py [--data data] [--id 100000000000000001] [--name "E2E Tester"] [--days 1]

The cookie is signed with <data>/session.key exactly as a real Discord login would be (backend/auth.py). Who it is lets in
depends on the server's settings: run_local.bat puts the same id in ECHOVR_DISCORD_PREVIEW_ROLES, which gives the
Console and the Preview. It only works against a server using that data folder; it is useless anywhere else."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))

from backend import auth  # noqa: E402
from backend.config import Settings  # noqa: E402

TEST_ID = "100000000000000001"


def cookie(data_dir: Path, user_id: str = TEST_ID, name: str = "E2E Tester", days: int = 1) -> str:
    settings = Settings(data_dir=data_dir, source_dir=data_dir)
    return auth.sign(settings, {"id": user_id, "name": name}, days * 86400)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data", default=str(ROOT / "data"))
    p.add_argument("--id", default=TEST_ID)
    p.add_argument("--name", default="E2E Tester")
    p.add_argument("--days", type=int, default=1)
    a = p.parse_args()
    value = cookie(Path(a.data), a.id, a.name, a.days)
    print(value)
    print(f'\ncurl -A "Mozilla/5.0" -H "X-EchoVR: 1" -b "{auth.SESSION_COOKIE}={value}" http://127.0.0.1:8000/api/auth/me', file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
