"""D57: a derived column can be added without dropping the match tables, so the site keeps its stats during a re-read."""

import sqlite3

from sqlalchemy import select

from backend.db import IN_PLACE_COLUMNS, open_db
from backend.models import MatchPlayer, Replay


def _without_column(path) -> None:
    """A database as the previous version left it: the column is not there yet."""
    con = sqlite3.connect(path)
    con.execute('ALTER TABLE match_players DROP COLUMN "frames_lone_wolf_near"')
    con.commit()
    con.close()


def test_in_place_columns_are_nullable():
    assert MatchPlayer.__table__.columns["frames_lone_wolf_near"].nullable
    assert "frames_lone_wolf_near" in IN_PLACE_COLUMNS["match_players"]


def test_old_database_keeps_its_rows_and_gets_the_column(tmp_path):
    path = tmp_path / "t.db"
    engine, sessions = open_db(path, 0)
    with sessions() as db:
        db.add(Replay(source_path="a.echoreplay", size_bytes=1, source_mtime=1.0, discovered_at="2026-11-05T00:00:00", status="done", stats_version="9"))
        db.commit()
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=OFF")
    columns = [r[1] for r in con.execute("PRAGMA table_info(match_players)")]
    values = {c: 0 for c in columns if c not in ("id", "frames_lone_wolf_near")}
    con.execute(f"INSERT INTO match_players ({', '.join(values)}) VALUES ({', '.join('?' * len(values))})", list(values.values()))
    con.commit()
    con.close()
    engine.dispose()
    _without_column(path)

    engine, sessions = open_db(path, 0)  # the upgrade
    with sessions() as db:
        rows = db.scalars(select(MatchPlayer)).all()
        assert len(rows) == 1 and rows[0].frames_lone_wolf_near is None  # kept, no value yet
        replay = db.scalars(select(Replay)).one()
        assert replay.stats_version == "9"  # not cleared: the re-read comes from the version check, the old rows stay until then
    engine.dispose()


def test_lone_echo_counts_from_an_older_read_are_forgotten(tmp_path):
    """Lone Echo went from 3.5 m to 10 m (stats version 22; user, 2026-11-28): a row from an older read is set to NULL (no
    value yet, no false medal against the lower targets) until its replay is read again; a row read at 22 keeps its value."""
    path = tmp_path / "t.db"
    engine, sessions = open_db(path, 0)
    engine.dispose()
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys=OFF")
    for rid, version in ((1, "21"), (2, "22")):
        con.execute("INSERT INTO replays (id, source_path, size_bytes, source_mtime, discovered_at, status, stats_version) "
                    "VALUES (?, ?, 1, 1.0, 'x', 'done', ?)", (rid, f"{rid}.echoreplay", version))
        mcols = [r[1] for r in con.execute("PRAGMA table_info(matches)") if r[3] and r[1] != "id"]
        con.execute(f"INSERT INTO matches (id, {', '.join(mcols)}) VALUES (?, {', '.join('?' * len(mcols))})",
                    [rid, *(rid if c == "replay_id" else 0 for c in mcols)])
        pcols = [r[1] for r in con.execute("PRAGMA table_info(match_players)") if r[1] not in ("id", "match_id", "frames_lone_wolf_near")]
        con.execute(f"INSERT INTO match_players (match_id, frames_lone_wolf_near, {', '.join(pcols)}) VALUES (?, 50, {', '.join('?' * len(pcols))})",
                    [rid, *(0 for _ in pcols)])
    con.commit()
    con.close()

    engine, sessions = open_db(path, 0)  # the upgrade
    with sessions() as db:
        assert dict(db.execute(select(MatchPlayer.match_id, MatchPlayer.frames_lone_wolf_near)).all()) == {1: None, 2: 50}
    engine.dispose()
