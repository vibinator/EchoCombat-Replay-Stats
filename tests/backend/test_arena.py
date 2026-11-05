"""Arena match counting (app/backend/arena.py): public Arena only, 4 minutes in the match, once per match."""

from types import SimpleNamespace

import pytest
from app_helpers import app_client, make_settings
from sqlalchemy import select

from backend import admin_actions as actions
from backend.arena import MIN_PRESENT_S, Tracker, is_public_arena
from backend.db import open_db
from backend.models import ArenaPlayer


def label(match_id, users, mode="echo_arena", lobby="public"):
    return {"id": match_id, "mode": mode, "lobby_type": lobby,
            "players": [{"user_id": u, "username": u, "display_name": u.upper()} for u in users]}


def tracker(tmp_path, snapshots, period=True):
    _, sm = open_db(tmp_path / "t.db", 0)
    if period:
        with sm() as db:
            actions.set_challenge_window(db, "1970-01-01", None)
            db.commit()
    it = iter(snapshots)
    return Tracker(sm, SimpleNamespace(arena_poll_s=60.0), fetch=lambda: {"labels": next(it)}), sm


def test_status_for_the_console(tmp_path):
    six = list("abcdef")
    t, _ = tracker(tmp_path, [[label("m1", six)]] * 6)
    assert t.status(now=1000.0)["state"] == "off"  # not started
    t.start()
    try:
        assert t.status(now=1000.0)["state"] == "waiting"
        for i in range(6):
            t.poll(now=1000.0 + 60 * i)
        s = t.status(now=1300.0)
        assert (s["state"], s["matches_now"], s["players_now"], s["counted_since_start"]) == ("working", 1, 6, 6)
        assert s["last_ok_at"].endswith("+00:00") and s["last_counted_at"].endswith("+00:00")  # with a zone: shown in the viewer's time
        assert s["last_error"] is None
        assert t.status(now=1300.0 + 4 * 60)["state"] == "waiting"  # no answer for a while, no error recorded
        t._last_error = (1500.0, "ConnectError: down")
        s = t.status(now=1300.0 + 4 * 60)
        assert (s["state"], s["last_error"]) == ("failing", "ConnectError: down")
    finally:
        t.stop()


def test_overview_has_the_arena_status_for_console_users_only(tmp_path):
    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        assert client.get("/api/admin/console/overview").status_code in (401, 403, 404)  # not a console user


def test_status_outside_the_period(tmp_path):
    from backend.models import ArenaPlayer as _AP, NakamaAccount
    t, sm = tracker(tmp_path, [[label("m1", list("abcdef"))]], period=False)
    t.start()
    try:
        assert t.poll(now=1000.0) == 0  # no period set: nothing is counted, but the accounts on the list are collected
        assert t.status(now=1000.0)["state"] == "outside_period"
        with sm() as db:
            assert db.scalar(select(NakamaAccount.username).where(NakamaAccount.user_id == "a")) == "a"
            assert db.scalar(select(_AP.user_id)) is None
    finally:
        t.stop()


def test_only_public_arena():
    assert is_public_arena(label("m", [])) and not is_public_arena(label("m", [], mode="echo_arena_private", lobby="private"))
    assert not is_public_arena(label("m", [], mode="social_2.0")) and not is_public_arena(label("m", [], lobby="private"))


def test_counts_after_three_minutes_once(tmp_path):
    steps = int(MIN_PRESENT_S // 60) + 3
    six = list("abcdef")  # 6 players seen = big enough (3v3 or a min of 6, user 2026-11-04)
    t, sm = tracker(tmp_path, [[label("m1", six)]] * steps + [[label("m1", ["a"])]])
    counted = [t.poll(now=1000.0 + 60 * i) for i in range(steps)]
    assert sum(counted) == 6 and counted[:4] == [0, 0, 0, 0]  # 0-180 s in: not yet; 240 s: counted
    assert t.poll(now=1000.0 + 60 * steps) == 0  # already counted, never twice
    with sm() as db:
        assert {p.user_id: p.matches for p in db.scalars(select(ArenaPlayer))} == {u: 1 for u in six}


def test_spectators_and_moderators_are_not_counted_and_lose_their_record(tmp_path):
    steps = int(MIN_PRESENT_S // 60) + 1
    watching = label("m2", ["s", "m"])
    watching["players"][0]["team"], watching["players"][1]["team"] = "spectator", "moderator"
    t, sm = tracker(tmp_path, [[label("m1", ["a", "s", "m", "b", "c", "d", "e"])]] * steps + [[watching]] * steps)
    for i in range(steps):
        t.poll(now=1000.0 + 60 * i)
    with sm() as db:
        assert {p.user_id for p in db.scalars(select(ArenaPlayer))} == set("asmbcde")  # counted while playing
    for i in range(steps, 2 * steps):
        t.poll(now=1000.0 + 60 * i)
    with sm() as db:
        assert {p.user_id for p in db.scalars(select(ArenaPlayer))} == set("abcde")  # seen as spectator/moderator: record gone


def test_short_stays_and_other_modes_do_not_count(tmp_path):
    t, sm = tracker(tmp_path, [[label("m1", ["a"])], [label("m1", ["a"])], [], [label("m2", ["a"], lobby="private")]])
    assert [t.poll(now=1000.0 + 60 * i) for i in range(4)] == [0, 0, 0, 0]
    with sm() as db:
        assert db.scalars(select(ArenaPlayer)).all() == []


def test_nothing_counts_before_the_challenge_period(tmp_path):
    t, sm = tracker(tmp_path, [[label("m1", ["a"])]] * 7, period=False)
    assert [t.poll(now=1000.0 + 60 * i) for i in range(6)] == [0] * 6
    with sm() as db:
        actions.set_challenge_window(db, "2999-01-01", None)  # starts in the future: still nothing
        db.commit()
    t._window = (0.0, False)
    assert t.poll(now=2000.0) == 0


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        yield c


def test_progress_is_for_the_preview_role_only(client):
    r = client.get("/api/arena/progress")
    assert r.status_code == 403 and r.headers["cache-control"] == "private, no-store"


def test_winners_report_needs_console_and_lists_nobody_without_a_period(client):
    assert client.get("/api/admin/console/mega-prizes").status_code in (401, 403, 404)  # not a console user
    from backend import mega_prizes
    with client.app.state.sessionmaker() as db:
        db.add(ArenaPlayer(user_id="u", username="u", display_name="U", discord_id=None, matches=1000, last_match_at="x"))
        db.commit()
        none = mega_prizes.report(db)
        assert [len(p["winners"]) for p in none["prizes"]] == [0, 0]  # no start date set: nobody has won yet
        actions.set_challenge_window(db, "2020-01-01", None)
        db.commit()
        data = mega_prizes.report(db)
    assert [len(p["winners"]) for p in data["prizes"]] == [0, 1] and data["prizes"][1]["winners"][0]["name"] == "U"
    assert b"Jack Series 11 from Lone Echo 1/2" in mega_prizes.csv_bytes(data)


def test_opens_a_database_made_before_discord_id_existed(tmp_path):
    """The Docker crash: arena_players already existed without discord_id and is kept across rebuilds."""
    import sqlite3
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE arena_players (user_id VARCHAR NOT NULL PRIMARY KEY, username VARCHAR NOT NULL, "
                "display_name VARCHAR, matches INTEGER NOT NULL, last_match_at VARCHAR NOT NULL)")
    con.execute("INSERT INTO arena_players VALUES ('u', 'u', 'U', 12, 'x')")
    con.commit()
    con.close()
    _, sm = open_db(path, 0)
    with sm() as db:
        row = db.get(ArenaPlayer, "u")
        assert row.matches == 12 and row.discord_id is None  # data kept, column added


def test_search_is_for_the_preview_role_only(client):
    assert client.get("/api/arena/search", params={"q": "ab"}).status_code == 403


def test_search_finds_arena_players_by_name(tmp_path, monkeypatch):
    from backend.api import arena as api
    _, sm = open_db(tmp_path / "s.db", 0)
    with sm() as db:
        db.add(ArenaPlayer(user_id="u1", username="zed", display_name="Zed The Great", discord_id=None, matches=40, last_match_at="x"))
        db.commit()
    from types import SimpleNamespace
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(sessionmaker=sm)))
    monkeypatch.setattr(api.auth, "has_preview", lambda r: True)  # the role check is covered above
    found = api.search(request, q="the gre")
    assert found["results"] == [{"kind": "arena", "name": "Zed The Great", "user_id": "u1", "matches": 40}]
    assert api.search(request, q="z")["results"] == []  # one letter: too broad


def test_combat_prize_counts_only_games_of_four_minutes_inside_the_period():
    from backend.achievements import mega_combat_games
    g = lambda day, secs: SimpleNamespace(started_at=f"{day}T10:00:00", play_time_s=secs, enough_players=True)  # noqa: E731
    games = [g("2026-11-01", 239), g("2026-11-01", 240), g("2026-11-02", 900), g("2026-10-31", 900), g("2026-11-09", 900)]
    assert mega_combat_games(games, "2026-11-01", "2026-11-05") == 2  # under 4 minutes, before the start and after the end: out
    assert mega_combat_games(games, "2026-11-01", None) == 3


def test_small_matches_do_not_count_until_big_enough(tmp_path):
    steps = int(MIN_PRESENT_S // 60) + 2
    small = label("m1", ["a", "b", "c", "d"])
    for i, p in enumerate(small["players"]):
        p["team"] = "blue" if i < 2 else "orange"  # 2v2
    t, sm = tracker(tmp_path, [[small]] * steps)
    assert sum(t.poll(now=1000.0 + 60 * i) for i in range(steps)) == 0
    for i, p in enumerate(small["players"]):
        p["team"] = "blue" if i % 2 else "orange"
    big = label("m1", list("abcdef"))
    for i, p in enumerate(big["players"]):
        p["team"] = "blue" if i < 3 else "orange"  # 3v3
    t, _ = tracker(tmp_path / "x" if False else tmp_path, [[big]] * steps)


def combat_label(match_id, users):
    return {"id": match_id, "mode": "echo_combat", "lobby_type": "public",
            "players": [{"user_id": u, "username": u, "display_name": u.upper(), "discord_id": "d" + u,
                         "team": "blue" if i % 2 else "orange"} for i, u in enumerate(users)]}


def test_combat_counted_from_the_list_once_per_match_and_kept(tmp_path):
    from backend.models import NakamaCombatCounted, NakamaCombatPlayer
    six = list("abcdef")
    t, sm = tracker(tmp_path, [[combat_label("S1.node", six), label("m1", six)]] * 7)
    for i in range(6):
        t.poll(now=1000.0 + 60 * i)
    with sm() as db:
        assert db.scalar(select(NakamaCombatPlayer.matches).where(NakamaCombatPlayer.user_id == "a")) == 1
        assert db.scalar(select(ArenaPlayer.matches).where(ArenaPlayer.user_id == "a")) == 1  # Arena separate
    t._pruned = 0.0
    t.combat.pruned = 0.0
    t.poll(now=1000.0 + 3 * 86400)  # far later: Arena rows are pruned, Combat history stays
    with sm() as db:
        assert db.scalar(select(NakamaCombatCounted.match_id).where(NakamaCombatCounted.user_id == "a")) == "S1.node"


def test_combat_totals_from_nakama_only(tmp_path):
    from backend.api.arena import combat_totals
    from backend.models import NakamaCombatCounted, NakamaCombatPlayer
    _, sm = open_db(tmp_path / "t.db", 0)
    with sm() as db:
        db.add(NakamaCombatPlayer(user_id="u1", username="x", display_name="X", discord_id=None, matches=2, last_match_at="t"))
        db.add_all([NakamaCombatCounted(match_id=m, user_id="u1", counted_at=2e9) for m in ("S1.n", "S2.n")])
        db.commit()
        assert combat_totals(db, None, None) == []  # no period: nothing counts
        assert [(w["name"], w["count"]) for w in combat_totals(db, "2000-01-01", None)] == [("X", 2)]
        assert combat_totals(db, "2000-01-01", "2000-01-02") == []  # counted after the period


def test_combat_audit_columns(tmp_path):
    from backend.models import NakamaCombatCounted
    six = list("abcdef")
    t, sm = tracker(tmp_path, [[combat_label("S1.node", six)]] * 6)
    for i in range(6):
        t.poll(now=2e9 + 60 * i)
    with sm() as db:
        row = db.scalars(select(NakamaCombatCounted).where(NakamaCombatCounted.user_id == "a")).one()
        assert (row.blue, row.orange, row.spectators) == (3, 3, 0) and row.present_s >= MIN_PRESENT_S


def test_accounts_are_collected_and_linked_every_poll(tmp_path):
    from backend.models import NakamaAccount, Player, PlayerProfile
    d_recent, d_bot = "1346263035425325078", "1033759231184224368"
    def lab(uid, discord):
        return {"id": "m1", "mode": "social_2.0", "lobby_type": "public",
                "players": [{"user_id": uid, "username": uid, "display_name": uid.upper(), "discord_id": discord, "team": "blue"}]}
    snaps = [[lab("n1", d_recent), lab("n2", d_bot), lab("n3", None)]] * 3
    t, sm = tracker(tmp_path, snaps)
    with sm() as db:
        db.add(Player(user_id=d_recent, name="Recent", first_seen_at="t", last_seen_at="t"))  # replay id IS the Discord id
        db.add(Player(user_id="oculus-1", name="Old", first_seen_at="t", last_seen_at="t"))
        db.add(PlayerProfile(user_id="oculus-1", discord_id=d_bot, bio=None, show_avatar=True, linked_at="t", updated_at="t"))  # bot / admin
        db.commit()
    t.poll(now=2e9)
    with sm() as db:
        rows = {a.user_id: (a.replay_user_id, a.link) for a in db.scalars(select(NakamaAccount))}
        assert rows == {"n1": (d_recent, "player_id"), "n2": ("oculus-1", "profile"), "n3": (None, None)}
        db.scalar(select(NakamaAccount).where(NakamaAccount.user_id == "n3")).discord_id = None
        db.commit()
    t.poll(now=2e9 + 10)  # unchanged: nothing is written again before ACCOUNT_REFRESH_S
    assert t.accounts_seen == 3
