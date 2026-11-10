import threading
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


BUSY_TIMEOUT_S = 30  # how long a write waits for another writer (SQLite has one at a time)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def open_db(db_path: Path, cache_mb: int = 0) -> tuple[Engine, sessionmaker]:
    """cache_mb > 0 keeps the database in RAM (D49): memory-mapped up to cache_mb (one copy in the OS page cache,
    shared by every connection) plus a 32 MB page cache per connection. Not temp_store=MEMORY: measured 60 %
    slower on the archive-wide GROUP BY queries."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Several threads write (worker results, combat reports, arena poll, scanner, console): a writer waits up to
    # BUSY_TIMEOUT_S for the others instead of failing with "database is locked" after Python's default 5 s (Review BUG-1)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_S})

    @event.listens_for(engine, "connect")
    def _pragmas(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_S * 1000}")
        if cache_mb > 0:
            cur.execute(f"PRAGMA mmap_size={cache_mb * 1024 * 1024}")
            cur.execute("PRAGMA cache_size=-32768")
        cur.close()

    from . import models  # noqa: F401  registers tables on Base

    _add_columns_in_place(engine)
    _rebuild_stale_tables(engine)
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    _add_missing_indexes(engine)
    _backfill_counted(engine)
    return engine, sessionmaker(engine, expire_on_commit=False)


_readers: dict[str, sessionmaker] = {}


def open_reader(db_path: str, cache_mb: int = 0) -> sessionmaker:
    """Read-only sessions for a helper process (the achievement calculations, api/achievements.py): no tables are created
    or changed here, the web server did that when it started. One engine per database per process."""
    sessions = _readers.get(db_path)
    if sessions is None:
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": BUSY_TIMEOUT_S})

        @event.listens_for(engine, "connect")
        def _pragmas(conn, _record):
            cur = conn.cursor()
            cur.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_S * 1000}")
            cur.execute("PRAGMA query_only=ON")
            if cache_mb > 0:
                cur.execute(f"PRAGMA mmap_size={cache_mb * 1024 * 1024}")
                cur.execute("PRAGMA cache_size=-32768")
            cur.close()

        from . import models  # noqa: F401  registers tables on Base

        sessions = _readers[db_path] = sessionmaker(engine, expire_on_commit=False)
    return sessions


def warm(db_path: Path, cache_mb: int) -> None:
    """Read the database file once in the background so the first visitors do not wait on the disk (D49)."""
    def _read():
        left = cache_mb * 1024 * 1024
        try:
            with open(db_path, "rb") as f:
                while left > 0 and (chunk := f.read(1 << 20)):
                    left -= len(chunk)
        except OSError:
            pass

    threading.Thread(target=_read, name="db-warm", daemon=True).start()


def _add_missing_columns(engine: Engine) -> None:
    """A table kept across rebuilds (PRESERVED_TABLES, e.g. arena_players) is never dropped, so a column added to its model
    later would be missing from an existing database (and an index on it would fail at startup). Nullable columns are
    added in place; the data stays."""
    inspector = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if table.name not in PRESERVED_TABLES or not inspector.has_table(table.name):
            continue
        have = {c["name"] for c in inspector.get_columns(table.name)}
        with engine.begin() as conn:
            for column in table.columns:
                if column.name not in have and column.nullable:
                    kind = column.type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))


def _add_missing_indexes(engine: Engine) -> None:
    """create_all skips tables that already exist, so an index added to a model later would never reach
    an existing database. Indexes are not data: adding one needs no rebuild."""
    for table in Base.metadata.sorted_tables:
        for index in table.indexes:
            index.create(engine, checkfirst=True)


# The database is a cache of the replay share (D25): every table can be rebuilt from it.
# Derived tables, children first: a change here keeps `replays` and only recomputes stats.
DERIVED_TABLES = ("duplicate_matches", "events", "match_player_loadouts", "match_players", "matches")
# Kept across every rebuild: admin settings are not derived from the share.
PRESERVED_TABLES = ("app_settings", "player_aliases", "repair_requests", "aggressive_repairs", "hidden_replays", "console_log", "cloud_log", "player_profiles", "arena_players", "arena_counted", "nakama_combat_players", "nakama_combat_counted", "discord_profiles", "nakama_accounts")


# Combat stats (combat.py): a cache of the recorder's match reports, kept apart from the replay data. Children first.
COMBAT_TABLES = ("combat_players", "combat_matches", "combat_files")


# Derived columns added without the usual drop + rebuild (D57, an exception to D23): the site keeps its match stats while
# a higher STATS_VERSION reads every replay again. Must be nullable: NULL = this replay has not been read again yet.
IN_PLACE_COLUMNS = {"match_players": ("frames_lone_wolf_near", "ping_capped_sum"), "matches": ("counted_for_stats",)}


def _backfill_counted(engine: Engine) -> None:
    """matches.counted_for_stats for rows saved before the column existed (stats/quality.py, one UPDATE, ~1 s for 30k)."""
    from .stats.quality import BACKFILL_SQL
    with engine.begin() as conn:
        conn.execute(text(BACKFILL_SQL))


def _add_columns_in_place(engine: Engine) -> None:
    inspector = inspect(engine)
    for name, columns in IN_PLACE_COLUMNS.items():
        if not inspector.has_table(name):
            continue
        have = {c["name"] for c in inspector.get_columns(name)}
        table = Base.metadata.tables[name]
        with engine.begin() as conn:
            for column in columns:
                if column not in have:
                    kind = table.columns[column].type.compile(engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{name}" ADD COLUMN "{column}" {kind}'))


def _stale(inspector, name: str) -> bool:
    if not inspector.has_table(name):
        return False  # created by create_all
    return {c["name"] for c in inspector.get_columns(name)} != set(Base.metadata.tables[name].columns.keys())


def _rebuild_stale_tables(engine: Engine) -> None:
    """Columns differ from the models -> drop and let create_all rebuild. A derived-table change
    clears stats_version (matches recomputed); a `replays`/`players` change drops everything
    (the scanner rediscovers every file)."""
    inspector = inspect(engine)
    if any(_stale(inspector, n) for n in COMBAT_TABLES):
        # the combat stats are separate from the replay data: a change there drops and re-reads only those tables
        with engine.begin() as conn:
            Base.metadata.drop_all(conn, tables=[Base.metadata.tables[n] for n in COMBAT_TABLES])
    core_stale = any(_stale(inspector, n) for n in Base.metadata.tables
                     if n not in DERIVED_TABLES + PRESERVED_TABLES + COMBAT_TABLES)
    derived_stale = any(_stale(inspector, n) for n in DERIVED_TABLES)
    if not core_stale and not derived_stale:
        return
    with engine.begin() as conn:
        if core_stale:
            keep = [t for n, t in Base.metadata.tables.items() if n not in PRESERVED_TABLES + COMBAT_TABLES]
            Base.metadata.drop_all(conn, tables=keep)
            return
        for name in DERIVED_TABLES:
            Base.metadata.tables[name].drop(conn, checkfirst=True)
        conn.execute(text("UPDATE replays SET stats_version = NULL"))
