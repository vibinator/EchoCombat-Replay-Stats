import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = r"Z:\ECRanked\Replays"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    source_dir: Path  # read-only replay share (D25); never written to
    workers: int = 8  # parallel processes for parsing; 0 = run in a thread (tests)
    scan_interval_s: float = 300.0
    settle_s: float = 120.0  # skip files modified more recently (may still be recording / copying)
    auto_scan: bool = True  # tests turn this off and call scan_once() themselves
    # /api/import and /api/replays: off on the website, import progress is only in the admin console (user,
    # 2026-10-30); tests turn it on to inspect replays
    import_api: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            data_dir=Path(env("ECHOVR_DATA_DIR", PROJECT_ROOT / "data")),
            source_dir=Path(env("ECHOVR_REPLAY_SOURCE", DEFAULT_SOURCE)),
            workers=int(env("ECHOVR_WORKERS", 8)),
            scan_interval_s=float(env("ECHOVR_SCAN_INTERVAL_S", 300)),
        )

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "database" / "echovr-stats.db"
