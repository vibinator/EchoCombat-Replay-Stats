import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = r"Z:\ECRanked\Replays"
# Discord login for achievement previews (D41): the bot's application and the EchoVR Combat server (user, 2026-10-30)
DISCORD_CLIENT_ID = "1214456381466222683"
DISCORD_GUILD_ID = "779349159852769310"


def _secret(value: str | None) -> str:
    """docker-compose.yml placeholders (YOUR_...) count as not set: the Discord login stays off."""
    return "" if not value or value.startswith("YOUR_") else value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    source_dir: Path  # read-only replay share (D25); never written to
    workers: int = 8  # parallel processes for parsing; 0 = run in a thread (tests)
    scan_interval_s: float = 300.0  # full scan (lists every file)
    quick_check_s: float = 15.0  # between full scans: stat only the folders, full scan when one changed; 0 = off
    settle_s: float = 120.0  # skip files modified more recently (may still be recording / copying)
    auto_scan: bool = True  # tests turn this off and call scan_once() themselves
    # /api/import and /api/replays: off on the website, import progress is only in the admin console (user,
    # 2026-10-30); tests turn it on to inspect replays
    import_api: bool = False
    # Discord login (D41): on only when the secret, bot token and preview role(s) are all set
    public_url: str = "http://127.0.0.1:8000"  # Discord sends people back to <public_url>/api/auth/callback
    discord_client_id: str = DISCORD_CLIENT_ID
    discord_client_secret: str = ""
    discord_bot_token: str = ""
    discord_guild_id: str = DISCORD_GUILD_ID
    discord_preview_roles: tuple[str, ...] = ()  # role ids; any one of them gives preview access
    # Scraper protection (D48, guard.py): /api only for the site's own pages, no bots; tests turn it off
    scraper_guard: bool = True
    rate_limit_per_min: int = 30  # /api requests per visitor per minute (bursts up to 2x); 0 = no limit
    rate_limit_per_hour: int = 1500  # ... and per hour (no burst above it); 0 = no hourly limit
    # RAM caches (D49): database memory-mapped up to db_cache_mb, decoded tracks.bin files up to track_cache_mb; 0 = off
    db_cache_mb: int = 0
    track_cache_mb: int = 0
    # Answer caches (D53, cache.py): an out-of-date answer is sent at once and rebuilt in the background once it is
    # this many seconds old (0 = rebuilt before answering, the tests); Cloudflare may keep public API answers this
    # many seconds (Cloudflare-CDN-Cache-Control; 0 = no shared cache keeps them, browsers still revalidate by ETag)
    cache_refresh_s: float = 0.0
    edge_cache_s: int = 0
    # Twitch channel of the spectator bot: live = a game is being played now (twitch.py); "" = not checked (the tests)
    twitch_channel: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            data_dir=Path(env("ECHOVR_DATA_DIR", PROJECT_ROOT / "data")),
            source_dir=Path(env("ECHOVR_REPLAY_SOURCE", DEFAULT_SOURCE)),
            workers=int(env("ECHOVR_WORKERS", 8)),
            scan_interval_s=float(env("ECHOVR_SCAN_INTERVAL_S", 300)),
            quick_check_s=float(env("ECHOVR_QUICK_CHECK_S", 15)),
            public_url=env("ECHOVR_PUBLIC_URL", "http://127.0.0.1:8000"),
            discord_client_id=env("ECHOVR_DISCORD_CLIENT_ID", DISCORD_CLIENT_ID),
            discord_client_secret=_secret(env("ECHOVR_DISCORD_CLIENT_SECRET")),
            discord_bot_token=_secret(env("ECHOVR_DISCORD_BOT_TOKEN")),
            discord_guild_id=env("ECHOVR_DISCORD_GUILD_ID", DISCORD_GUILD_ID),
            rate_limit_per_min=int(env("ECHOVR_RATE_LIMIT_PER_MIN", 60)),
            rate_limit_per_hour=int(env("ECHOVR_RATE_LIMIT_PER_HOUR", 1500)),
            db_cache_mb=int(env("ECHOVR_DB_CACHE_MB", 1024)),
            track_cache_mb=int(env("ECHOVR_TRACK_CACHE_MB", 512)),
            cache_refresh_s=float(env("ECHOVR_CACHE_REFRESH_S", 300)),
            edge_cache_s=int(env("ECHOVR_EDGE_CACHE_S", 60)),
            twitch_channel=env("ECHOVR_TWITCH_CHANNEL", "combat_stream_bot"),
            discord_preview_roles=tuple(r.strip() for r in _secret(env("ECHOVR_DISCORD_PREVIEW_ROLES")).split(",") if r.strip()),
        )

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "database" / "echovr-stats.db"
