"""Echo Combat George League, Rookie League only (league.py, user 2026-11-27): the Discord ids on its team rosters and
leaderboard, its League Subs, and the matches played / won."""

from backend import league
from backend.db import open_db
from backend.models import LeagueMember

A, B, C, D, E, F = (str(n) * 18 for n in range(1, 7))


def fake_site(players, leaderboard, teams, archives=None):
    """players: (id, role, veteran, override); leaderboard: (id, matches, wins); teams: id -> (roster, former)."""
    asked = []

    def get(path):
        asked.append(path)
        if path == "/api/players":
            return [{"id": p, "role": role, "is_veteran": vet, "play_override": ov} for p, role, vet, ov in players] + [{"id": "not-a-snowflake"}]
        if path == "/api/leaderboard/players":
            return [{"id": p, "matches": m, "wins": w} for p, m, w in leaderboard]
        if path == "/api/teams":
            return [{"id": i, "league": "rookie", "status": "Active"} for i in teams]
        if path.startswith("/api/player/"):
            seasons = (archives or {}).get(path.rsplit("/", 1)[1], [])
            return {"archived_stats": [{"season": "1", "archive_matches": m, "archive_wins": w} for m, w in seasons]}
        roster, former = teams[int(path.rsplit("/", 1)[1])]
        return {"roster": [{"id": m} for m in roster], "former_roster": [{"id": m, "season": "1"} for m in former]}

    get.asked = asked
    return get


SITE = dict(
    players=[(A, "Player", False, False), (C, "League Sub", False, False), (E, "League Sub", True, False), (F, "League Sub", True, True)],
    leaderboard=[(A, 2, 1), (B, 1, 0), (D, 0, 0)],
    teams={1: ([A], [B]), 2: ([], [])},
)


def test_reads_the_rookie_league_only():
    pauses = []
    r = league.read_rosters(fake_site(**SITE), pauses.append)
    assert r.on_team == {A, B}  # a former team member counts as having been on a team
    assert r.league == {A, B, D}  # on a Rookie team or its leaderboard; a sub alone has not joined
    assert (r.played, r.won) == ({A, B}, {A})
    assert r.subs == {C, F}  # a veteran sub cannot play in Rookie, unless given an override
    assert len(pauses) == 4  # one second between the requests


def test_every_request_asks_for_the_rookie_league(monkeypatch):
    sent = []

    class Reply:
        content = b"[]"

        def raise_for_status(self):
            pass

        def json(self):
            return []

    monkeypatch.setattr(league.httpx, "get", lambda url, **kw: sent.append(kw["headers"]) or Reply())
    league.read_rosters(pause=lambda s: None)
    assert sent and all(h["X-ECGL-League"] == "rookie" for h in sent)


def test_first_seen_dates_are_kept_and_never_taken_away(tmp_path):
    _, sm = open_db(tmp_path / "l.db", 0)
    first = league.read_rosters(fake_site(**SITE), lambda s: None)
    assert league.store(sm, first, now="2026-11-27T10:00:00") == 5  # A, B, D joined; subs C and F
    later = league.Rosters(league={A}, on_team={A}, played={A}, won={A, B})
    assert league.store(sm, later, now="2026-11-28T10:00:00") == 0
    with sm() as db:
        rows = {m.discord_id: m for m in db.query(LeagueMember)}
    a, b, c, d = rows[A], rows[B], rows[C], rows[D]
    assert (a.joined_at, a.team_at, a.played_at, a.won_at) == ("2026-11-27T10:00:00",) * 4
    assert (b.won_at, b.team_at) == ("2026-11-28T10:00:00", "2026-11-27T10:00:00")  # B left the team: still counted
    assert (c.joined_at, c.sub_at) == (None, "2026-11-27T10:00:00")  # a sub has not joined the Rookie League by that alone
    assert (d.joined_at, d.played_at) == ("2026-11-27T10:00:00", None)  # on the leaderboard, no match yet


def test_earlier_rookie_seasons_are_read_once_per_player(tmp_path):
    _, sm = open_db(tmp_path / "a.db", 0)
    get = fake_site(**SITE, archives={D: [(3, 2)]})
    league.store(sm, league.read_rosters(get, lambda s: None), now="2026-11-27T10:00:00")
    ranked = {A, B, D}
    assert league.store_archives(sm, get, ranked, lambda s: None, now="2026-11-27T11:00:00") == 3
    assert league.store_archives(sm, get, ranked, lambda s: None) == 0  # never asked twice
    with sm() as db:
        d = db.get(LeagueMember, D)
    assert (d.played_at, d.won_at) == ("2026-11-27T11:00:00", "2026-11-27T11:00:00")
    assert sum(1 for p in get.asked if p.startswith("/api/player/")) == 3


def test_the_league_table_survives_rebuilds():
    from backend.db import PRESERVED_TABLES
    assert "league_members" in PRESERVED_TABLES
