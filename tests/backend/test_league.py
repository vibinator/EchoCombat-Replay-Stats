"""Echo Combat George League rosters (league.py, user 2026-11-27): the Discord ids on the player list and on team rosters."""

from backend import league
from backend.db import open_db
from backend.models import LeagueMember

A, B, C, D = "111111111111111111", "222222222222222222", "333333333333333333", "444444444444444444"


def fake_site(players, teams):
    def get(path):
        if path == "/api/players":
            return [{"id": p, "username": "x", "display_name": "X", "role": "Player"} for p in players] + [{"id": "not-a-snowflake"}]
        if path == "/api/teams":
            return [{"id": i, "name": f"T{i}", "status": "Active"} for i in teams]
        tid = int(path.rsplit("/", 1)[1])
        roster, former = teams[tid]
        return {"id": tid, "roster": [{"id": m} for m in roster], "former_roster": [{"id": m, "season": "1"} for m in former]}
    return get


def test_reads_the_player_list_and_every_team_roster():
    pauses = []
    got = league.read_rosters(fake_site([A, B, C], {1: ([A], [D]), 2: ([], [])}), pauses.append)
    assert got == ({A, B, C}, {A, D})  # a former team member counts as having been on a team
    assert pauses == [league.PACE_S, league.PACE_S]  # one second between the team requests


def test_first_seen_dates_are_kept_and_never_taken_away(tmp_path):
    _, sm = open_db(tmp_path / "l.db", 0)
    assert league.store(sm, {A, B}, set(), now="2026-11-27T10:00:00") == 2
    assert league.store(sm, {A}, {A, D}, now="2026-11-28T10:00:00") == 1  # D: left the league, but was on a team
    with sm() as db:
        rows = {m.discord_id: m for m in db.query(LeagueMember)}
    assert (rows[A].joined_at, rows[A].team_at, rows[A].last_seen_at) == ("2026-11-27T10:00:00", "2026-11-28T10:00:00", "2026-11-28T10:00:00")
    assert (rows[B].joined_at, rows[B].team_at, rows[B].last_seen_at) == ("2026-11-27T10:00:00", None, "2026-11-27T10:00:00")  # B left: still joined
    assert (rows[D].joined_at, rows[D].team_at) == ("2026-11-28T10:00:00", "2026-11-28T10:00:00")


def test_the_league_table_survives_rebuilds():
    from backend.db import PRESERVED_TABLES
    assert "league_members" in PRESERVED_TABLES
