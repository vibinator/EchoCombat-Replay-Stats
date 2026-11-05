"""The Combat achievements (combat_achievements.py): only the recorder's reports, apart from the replay rules, on the same page."""

import ast
from pathlib import Path

import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import achievement_sheet, admin_actions as actions, combat_achievements as ca, icons
from backend.achievements import RULES, evaluate, medal_times, rule_notes
from backend.models import CombatFile, CombatMatch, CombatPlayer, PlayerAlias

RULES_HERE = ca.COMBAT_RULES
STARTED = "2026-11-05T20:00:00"


def game(kills=0, assists=0, deaths=5, damage=0.0, objective=0, time_s=0.0, top=False, started=STARTED):
    return ca.CombatGame(started, kills, assists, deaths, damage, objective, time_s, top)


def results(games):
    return {r["id"]: r for r in evaluate(games, RULES_HERE)}


def test_kept_apart_from_the_replay_rules():
    ids = {r.id for r in RULES_HERE}
    assert ids == set(range(164, 179)) | {198, 199, 200} and not ids & {r.id for r in RULES}
    assert all(r.group == "Combat" and r.new and not r.counted for r in RULES_HERE)
    # the module cannot read a replay table: it imports only the combat ones
    tree = ast.parse(Path(ca.__file__).read_text(encoding="utf-8"))
    models = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "models" for a in n.names}
    assert models == {"CombatFile", "CombatMatch", "CombatPlayer"}


def test_one_game_ladders():
    r = results([game(kills=12, assists=4, deaths=2, damage=1500.5, objective=9, time_s=120.0)])
    assert r[164]["count"] == 12 and r[164]["tier"] == "silver" and r[165]["count"] == 4 and r[165]["tier"] is None
    assert r[166]["count"] == 1500.5 and r[167]["count"] == 10 and r[168]["count"] == 9 and r[169]["count"] == 120
    assert results([game(kills=1, deaths=9)])[167]["count"] == 0  # never below 0
    assert results([game(kills=10, deaths=0)])[170]["progress"] == 1
    assert results([game(kills=10, deaths=1)])[170]["progress"] == 0 and results([game(kills=9, deaths=0)])[170]["progress"] == 0
    assert rule_notes(next(x for x in RULES_HERE if x.id == 164)) == ["Best game", "4+ min games", "3+ players per team"]


def test_days_and_all_time():
    games = [game(kills=6, assists=8, damage=100.0, objective=5, top=True, started="2026-11-04T20:00:00"),
             game(kills=7, assists=5, damage=200.0, objective=5), game(kills=3, assists=8, damage=300.0)]
    r = results(games)
    assert r[171]["count"] == 10 and r[172]["count"] == 13  # the best day: 7 + 3 kills, 5 + 8 assists
    assert r[173]["count"] == 16 and r[174]["count"] == 21 and r[175]["count"] == 600
    assert r[176]["count"] == 1 and r[177]["count"] == 2 and r[178]["count"] == 1


def test_assists_are_above_kills_at_every_medal():
    levels = {r.id: r.levels for r in RULES_HERE}
    for kills, assists in ((164, 165), (171, 172), (173, 174)):
        assert all(a > k for k, a in zip(levels[kills], levels[assists]))


def test_medal_dates():
    times = medal_times([game(kills=8, started="2026-11-04T20:00:00"), game(kills=13)], RULES_HERE)
    assert times[164]["bronze"].startswith("2026-11-04") and times[164]["gold"].startswith("2026-11-05")


def _report(db, session, started=STARTED, duration=400.0, players=()):
    """players: (user id, team, present seconds, kills, assists)"""
    f = CombatFile(source_path=f"matches/{session}.json", size_bytes=1, source_mtime=1.0, status="done", processed_at=started)
    db.add(f)
    db.flush()
    m = CombatMatch(file_id=f.id, session_id=session, map="dyson", started_at=started, ended_at=started, duration_s=duration,
                    has_events=False, events_complete=None, teams="{}")
    db.add(m)
    db.flush()
    db.add_all(CombatPlayer(match_id=m.id, user_id=u, name=f"name{u}", team=t, present_s=s, kills=k, assists=a, deaths=1, eliminations=k + a, damage=0.0,
                            objective_eliminations=0, objective_damage=0.0, objective_time=0.0, hill_captures=0, hill_defends=0)
               for u, t, s, k, a in players)


FULL = [("1", "blue", 400.0, 9, 2), ("2", "blue", 400.0, 3, 11), ("3", "blue", 400.0, 0, 0),
        ("4", "orange", 400.0, 12, 0), ("5", "orange", 400.0, 0, 0), ("6", "orange", 400.0, 0, 0)]


def test_objective_damage_heals_and_stuns(tmp_path):
    """Siege Breaker reads every report; Field Medic and Shock Trooper only a complete event log, whose counts can be trusted."""
    from backend.db import open_db

    engine, sessions = open_db(tmp_path / "t.db", 0)
    def report(session, has_events, complete):
        with sessions() as db:
            _report(db, session, players=FULL)
            db.flush()
            m = db.query(CombatMatch).filter_by(session_id=session).one()
            m.has_events, m.events_complete = has_events, complete
            p = db.query(CombatPlayer).filter_by(match_id=m.id, user_id="1").one()
            p.objective_damage, p.heal_bubbles, p.stuns_given = 950.0, 6, 3
            db.commit()
    report("complete", True, True)
    with sessions() as db:
        g = ca.load_games(db, {})[0]["1"][0]
    assert (g.objective_damage, g.heal_bubbles, g.stuns_given) == (950.0, 6, 3)
    r = results([g])
    assert (r[198]["tier"], r[199]["tier"], r[200]["tier"]) == ("silver", "gold", "gold")
    report("cut short", True, False)
    report("no log", False, None)
    with sessions() as db:
        later = ca.load_games(db, {})[0]["1"][1:]
    assert [(x.objective_damage, x.heal_bubbles, x.stuns_given) for x in later] == [(950.0, 0, 0), (950.0, 0, 0)]
    engine.dispose()


def _body(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.text
    return response.json()


def test_reports_alone_count_on_the_same_page(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(20))})  # a replay, unrelated to the reports
        act(client, actions.set_challenge_window, "2026-01-01", None)
        sessions = client.app.state.sessionmaker
        blue = str(rf.BIG_USER_ID)
        before = _body(client, f"/api/players/{blue}/achievements")
        assert {r["progress"] for r in before["items"] if r["group"] == "Combat"} == {0}
        with sessions() as db:
            _report(db, "A0000000-0000-0000-0000-000000000001", players=FULL)  # no replay has this session id
            _report(db, "A0000000-0000-0000-0000-000000000002", players=FULL[:3] + FULL[3:5])  # 3v2: too small
            # player 1 is there for 100 s only: not counted for them, but their 30 kills still top the match
            _report(db, "A0000000-0000-0000-0000-000000000003", players=[("1", "blue", 100.0, 30, 0), ("8", "blue", 400.0, 0, 0)] + FULL[1:])
            db.add(PlayerAlias(alias_user_id="77", main_user_id="2", created_at="x"))
            _report(db, "A0000000-0000-0000-0000-000000000004", started="2026-11-05T21:00:00", players=FULL + [("77", "blue", 400.0, 5, 1)])
            db.commit()

        def page(uid):
            answer = _body(client, f"/api/players/{uid}/achievements")
            return answer, {r["id"]: r for r in answer["items"]}

        answer, one = page("1")  # a player the replays never saw has a page
        assert answer["name"] == "name1" and answer["games"] == 0 and answer["total"] == len(RULES) and len(answer["items"]) == len(RULES) + len(RULES_HERE)
        assert one[173]["count"] == 18  # 2 counted matches: the 3v2 and the 100 s one do not count
        _, two = page("2")
        assert two[173]["count"] == 14  # 3 + 3 + (3 + 5 from the merged id)
        assert two[174]["count"] == 34  # 11 + 11 + (11 + 1 from the merged id)
        assert page("77")[1][173]["count"] == two[173]["count"]  # the merged id shows its main player's cards
        assert page("4")[1][176]["count"] == 2 and page("1")[1][176]["count"] == 0  # Top Fragger: not in the match player 1 topped

        # the replay page's totals do not move
        after = _body(client, f"/api/players/{blue}/achievements")
        assert after["overall"] == before["overall"] and after["completed"] == before["completed"] and after["total"] == before["total"]

        catalogue = {r["id"]: r for r in _body(client, "/api/achievements")}
        assert catalogue[173]["counted"] is False and catalogue[7]["counted"] is True and catalogue[173]["unlocked_share"] is None  # nobody has 10+ games yet
        assert any(e["id"] == 164 and e["user_id"] == "4" for e in _body(client, "/api/achievements/recent"))
        assert client.get("/api/players/nobody/achievements").status_code == 404


def test_challenge_period_applies(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        act(client, actions.set_challenge_window, "2026-11-05", None)
        with client.app.state.sessionmaker() as db:
            _report(db, "B0000000-0000-0000-0000-000000000001", started="2026-11-04T20:00:00", players=FULL)
            _report(db, "B0000000-0000-0000-0000-000000000002", players=FULL)
            db.commit()
        items = {r["id"]: r for r in _body(client, "/api/players/1/achievements")["items"]}
        assert items[173]["count"] == 9


def test_icons_and_sheet_know_them():
    assert ca.COMBAT_RULES[0].id in icons.RULE_IDS and icons.default(164) == "deaths.png"
    assert any(row["id"] == 164 for row in achievement_sheet.name_and_rule())
