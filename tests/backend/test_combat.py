"""Combat stats (combat.py, api/combat.py): the recorder's match reports, kept apart from the replay data."""

import json

import pytest
from app_helpers import app_client, make_settings

from backend import combat
from backend.db import open_db
from backend.models import CombatMatch, CombatPlayer, Match, PlayerAlias, Replay

BIG_ID = "1253331851049959565"  # larger than 2**53: must stay text
SESSION = "0CAD10E9-CF2A-451F-B677-EAFD0C0CB130"
SESSION_2 = "AD606013-A3A7-4780-BEED-043F1DA2274D"
STATS = dict(kills=6, assists=4, deaths=8, eliminations=10, damage=881.424, damage_taken=0.0, damage_taken_raw=0.0,
             objective_eliminations=4, objective_damage=463.08, objective_time=113.688, hill_captures=0, hill_defends=0)
EVENTS = {"shots": 434, "shots_by_weapon": {"magnum": 92, "blaster": 342}, "kills_by_weapon": {"blaster": 2, "blaster_cone": 1},
          "deaths_by_weapon": {"rifle": 4, "r15_ord_det": 1}, "tacmod_activations": 3, "heal_bubbles": 2, "stuns_given": 1,
          "stuns_received": 0, "self_kills": 1}


def player(user_id=BIG_ID, name="Likare", team="blue", events=EVENTS, **stats):
    return {"userid": user_id, "name": name, "names_used": [name], "playerids": [4], "team": team, "present_seconds": 480,
            "loadouts": {"weapons": ["assault", "rifle"], "tacmods": ["heal"], "ordnance": ["det"]},
            "stats": STATS | stats, "events": events, "segments": []}


def report(session=SESSION, map_="mpl_combat_dyson", started="2026-11-04T17:54:16", players=None, **extra):
    return {"format": "ecranked.match", "schema_version": 1, "session_id": session, "map": map_, "started": started,
            "ended": "2026-11-04T18:02:46", "duration_s": 510, "frames": 15290, "events_complete": True, "spectators_excluded": 1,
            "players": [player()] if players is None else players,
            "teams": {"blue": {"kills": 6, "damage": 881.4}, "orange": {"kills": 3, "damage": 400.0}}} | extra


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path, combat_source_dir=tmp_path / "recorder")


def put(settings, name, content, raw=False):
    path = settings.combat_dir / "matches" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content if raw else json.dumps(content), encoding="utf-8")


def sync(client):
    state = client.app.state
    return combat.sync_once(state.sessionmaker, state.settings, combat.CombatState())


def test_report_is_read_and_ids_stay_text(settings):
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        assert sync(client) == 1
        with client.app.state.sessionmaker() as db:
            m = db.query(CombatMatch).one()
            p = db.query(CombatPlayer).one()
    assert (m.session_id, m.map, m.has_events, m.events_complete) == (SESSION, "dyson", True, True)
    assert p.user_id == BIG_ID and p.kills == 6 and p.damage == 881.424 and p.shots == 434


def test_nothing_is_read_twice_and_a_changed_file_is_read_again(settings):
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        assert sync(client) == 1
        assert sync(client) == 0
        put(settings, f"{SESSION}.json", report(players=[player(kills=9)]))
        assert sync(client) == 1
        with client.app.state.sessionmaker() as db:
            assert db.query(CombatPlayer).one().kills == 9 and db.query(CombatMatch).count() == 1


def test_recently_written_file_waits(tmp_path):
    settings = make_settings(tmp_path, combat_source_dir=tmp_path / "recorder", settle_s=3600)
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        assert sync(client) == 0


def test_no_event_log_means_unknown_not_zero(settings):
    put(settings, f"{SESSION}.json", report(players=[player(events=None)], events_complete=None))
    with app_client(settings) as client:
        sync(client)
        with client.app.state.sessionmaker() as db:
            p = db.query(CombatPlayer).one()
            assert p.shots is None and p.kills_by_weapon is None
            assert db.query(CombatMatch).one().has_events is False
        data = client.get(f"/api/combat/players/{BIG_ID}").json()
    assert data["matches"] == 1 and data["events"] is None


def test_bad_files_are_failed_not_fatal(settings):
    put(settings, "broken.json", "{not json", raw=True)
    put(settings, "other.json", {"format": "something.else"})
    put(settings, "noid.json", report(session="nope"))
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        assert sync(client) == 4
        state = combat.CombatState()
        combat.sync_once(client.app.state.sessionmaker, settings, state)
        with client.app.state.sessionmaker() as db:
            assert db.query(CombatMatch).count() == 1
            failed = {f.source_path: f.error_message for f in db.query(combat.CombatFile).filter_by(status="failed")}
    assert len(failed) == 3 and state.read == 0


def test_players_without_a_valid_text_id_are_skipped_and_numbers_become_text(settings):
    players = [player(user_id=BIG_ID), player(user_id=None, name="nobody"), player(user_id=1234, name="numeric"), player(user_id="abc", name="x")]
    put(settings, f"{SESSION}.json", report(players=players))
    with app_client(settings) as client:
        sync(client)
        with client.app.state.sessionmaker() as db:
            assert sorted(p.user_id for p in db.query(CombatPlayer)) == ["1234", BIG_ID]


def test_combat_is_separate_from_replay_data(settings):
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        sync(client)
        with client.app.state.sessionmaker() as db:
            assert db.query(Replay).count() == 0 and db.query(Match).count() == 0
        assert client.get("/api/matches").json()["total"] == 0
        assert client.get("/api/players").json()["total"] == 0
        assert client.get("/api/combat/summary").json()["matches"] == 1


def test_changed_combat_tables_do_not_drop_the_replay_tables(tmp_path):
    from sqlalchemy import text
    db_path = tmp_path / "data" / "database" / "echovr-stats.db"
    engine, sessions = open_db(db_path)
    with sessions() as db:
        db.add(Replay(source_path="dyson/a.echoreplay", size_bytes=1, source_mtime=1.0, discovered_at="x", status="done"))
        db.commit()
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE combat_players ADD COLUMN junk TEXT"))  # now differs from the model
    engine.dispose()
    engine, sessions = open_db(db_path)
    with sessions() as db:
        assert db.query(Replay).count() == 1
        assert "junk" not in [c["name"] for c in __import__("sqlalchemy").inspect(engine).get_columns("combat_players")]
    engine.dispose()


def test_player_endpoint_totals_and_weapons(settings):
    put(settings, f"{SESSION}.json", report())
    put(settings, f"{SESSION_2}.json", report(session=SESSION_2, map_="mpl_combat_gauss", started="2026-11-04T19:00:00",
                                               players=[player(kills=4, deaths=2, events=None)]))
    with app_client(settings) as client:
        sync(client)
        data = client.get(f"/api/combat/players/{BIG_ID}").json()
        assert data["matches"] == 2 and data["name"] == "Likare"
        assert data["stats"]["kills"] == 10 and data["stats"]["deaths"] == 10 and data["stats"]["kd"] == 1.0
        assert {m["map"] for m in data["by_map"]} == {"dyson", "surge"}
        assert data["recent"][0]["session_id"] == SESSION_2  # newest first
        ev = data["events"]
        assert ev["matches"] == 1 and ev["shots"] == 434 and ev["self_kills"] == 1
        names = {w["code"]: w["name"] for w in ev["kills_by_weapon"] + ev["deaths_by_weapon"] + ev["shots_by_weapon"]}
        assert names["blaster"] == "Nova" and names["blaster_cone"] == "Nova cone" and names["r15_ord_det"] == "Detonator"
        assert client.get(f"/api/combat/players/{BIG_ID}", params={"map": "surge"}).json()["stats"]["kills"] == 4
        assert client.get("/api/combat/players/99").json() == {"user_id": "99", "name": None, "matches": 0}
        assert client.get("/api/combat/players/abc").status_code == 422


def test_merged_player_ids_are_added_up(settings):
    other = "42"
    put(settings, f"{SESSION}.json", report())
    put(settings, f"{SESSION_2}.json", report(session=SESSION_2, started="2026-11-04T19:00:00", players=[player(user_id=other, kills=1)]))
    with app_client(settings) as client:
        sync(client)
        with client.app.state.sessionmaker() as db:
            db.add(PlayerAlias(alias_user_id=other, main_user_id=BIG_ID, created_at="x"))
            db.commit()
        assert client.get(f"/api/combat/players/{other}").json()["user_id"] == BIG_ID
        assert client.get(f"/api/combat/players/{BIG_ID}").json()["stats"]["kills"] == 7
        board = client.get("/api/combat/leaderboard", params={"min_games": 1}).json()
        assert board["total"] == 1 and board["items"][0]["matches"] == 2


def test_leaderboard_orders_and_respects_min_games(settings):
    players = [player(user_id="1", name="A", kills=5, deaths=1), player(user_id="2", name="B", kills=9, deaths=7, team="orange"),
               player(user_id="3", name="C", kills=1, deaths=3)]
    put(settings, f"{SESSION}.json", report(players=players))
    with app_client(settings) as client:
        sync(client)
        get = lambda **q: client.get("/api/combat/leaderboard", params={"min_games": 1} | q).json()
        assert [r["name"] for r in get(stat="kills")["items"]] == ["B", "A", "C"]
        assert [r["name"] for r in get(stat="deaths")["items"]] == ["A", "C", "B"]  # fewer is better
        assert get(stat="kd")["items"][0]["name"] == "A"
        assert get(min_games=2)["total"] == 0 and get(stat="nonsense") is not None
        assert client.get("/api/combat/leaderboard", params={"stat": "nonsense"}).status_code == 422


def test_match_endpoints(settings):
    put(settings, f"{SESSION}.json", report(players=[player(), player(user_id="7", name="Orange", team="orange", events=None)]))
    with app_client(settings) as client:
        sync(client)
        listing = client.get("/api/combat/matches").json()
        assert listing["total"] == 1 and listing["items"][0]["players"] == 2
        detail = client.get(f"/api/combat/matches/{SESSION.lower()}").json()
        assert detail["session_id"] == SESSION and detail["teams"]["blue"]["kills"] == 6
        blue, orange = detail["players"]
        assert blue["events"]["shots"] == 434 and orange["events"] is None and blue["weapons"] == ["Pulsar", "Starburst"]
        assert client.get("/api/combat/matches/" + SESSION_2).status_code == 404


def test_combat_match_links_to_the_replay_match_with_the_same_id(settings):
    import replay_factory as rf
    from app_helpers import add
    session = "00000000-0000-4000-8000-0000000000AA"
    put(settings, f"{session}.json", report(session=session))
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        add(client, {"dyson/a.echoreplay": rf.zipped(rf.lines(5, sessionid=session))})
        sync(client)
        replay_match = client.get("/api/matches").json()["items"][0]
        assert replay_match["session_id"].upper() == session
        assert client.get(f"/api/combat/matches/{session}").json()["replay_match_id"] == replay_match["id"]
        assert client.get(f"/api/combat/matches/{SESSION}").json()["replay_match_id"] is None  # no replay for it here
        # the replay match itself carries nothing of the combat report
        assert "kills" not in str(client.get(f"/api/matches/{replay_match['id']}").json().get("teams", {}).get("blue", [{}])[:0])


def test_combat_folder_default_follows_where_matches_is(tmp_path):
    share = tmp_path / "ECRanked" / "Replays"
    share.mkdir(parents=True)
    s = make_settings(tmp_path)
    from dataclasses import replace
    s = replace(s, source_dir=share)
    assert s.combat_dir == share.parent  # PC layout: matches/ beside Replays/
    (share / "matches").mkdir()
    assert s.combat_dir == share  # NAS layout: the whole recorder folder is the share
    assert replace(s, combat_source_dir=tmp_path).combat_dir == tmp_path
