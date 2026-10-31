from datetime import date

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend.achievements import RULES, Game, evaluate, icon_file, overall, tier

BLUE = str(rf.BIG_USER_ID)


def game(day="2026-10-28", map_="dyson", mode="capture_point", deaths=5, loadout=("scout", "heal", "det"),
         play=400.0, private=False, top=10.0, upside=0, mate=0):
    return Game(started_at=f"{day}T20:00:00.000", map=map_, mode=mode, private=private, play_time_s=play,
                deaths=deaths, in_bounds=1000, near_mate=mate, near_enemy=0, upside=upside, speed_sum=3000.0,
                top_speed=top, frame_rate=20.0, loadouts={loadout: 1000} if loadout else {})


def by_id(results):
    return {r["id"]: r for r in results}


def test_catalogue():
    ids = [r.id for r in RULES]
    assert ids == list(range(5, 127)) and len(set(ids)) == 122  # 75 original + 47 new (80-126)
    assert [r.id for r in RULES if r.new] == list(range(80, 127))
    assert icon_file(next(r for r in RULES if r.id == 7)) == "comet_daily.png"
    assert icon_file(next(r for r in RULES if r.id == 32)) == "comet_weekly.png"
    assert icon_file(next(r for r in RULES if r.id == 57)) == "comet.png"


def test_tiers():
    assert [tier(p) for p in (0.1, 0.25, 0.5, 0.8, 1.0)] == [None, "white", "bronze", "silver", "gold"]


def test_daily_only_weapon_takes_best_day():
    games = [game("2026-10-27")] * 6 + [game("2026-10-28")] * 15 + [game("2026-10-28", loadout=("assault", "heal", "det"))]
    r = by_id(evaluate(games))
    # One with the Comet: ladder 3 / 6 / 10 / 15 / 20 games in one day; the best day (15 Comet-only games) counts
    assert (r[7]["tier"], r[7]["count"], r[7]["progress"]) == ("platinum", 15, pytest.approx(0.8))
    assert (r[5]["tier"], r[5]["count"], r[5]["progress"]) == (None, 1, pytest.approx(1 / 15, abs=1e-4))  # Pulsar only once


def test_weekly_groups_by_calendar_week():
    # Mon 26 Oct - Sun 1 Nov 2026 is one week; 2 Nov starts the next
    games = [game(d) for d in ("2026-10-26", "2026-11-01")] + [game("2026-11-02")]
    r = by_id(evaluate(games))
    # Frame-Drop Hell: the best week has 2 Dyson games, ladder 4 / 6 / 8 / 16 / 30
    assert (r[50]["count"], r[50]["progress"]) == (2, pytest.approx(0.1))


def test_per_game_rules_ignore_short_appearances():
    r = by_id(evaluate([game(deaths=0, play=30.0)]))
    assert r[18]["progress"] == 0.0
    r = by_id(evaluate([game(deaths=3)]))
    assert (r[18]["tier"], r[18]["count"]) == ("bronze", 1) and r[18]["estimated"]


def test_all_time_and_overall():
    games = [game(deaths=10) for _ in range(100)]
    r = by_id(evaluate(games))
    assert (r[68]["tier"], r[68]["count"]) == ("gold", 1000)  # 1000 deaths
    assert (r[59]["tier"], r[59]["count"]) == ("gold", 100)  # 100 games with Detonator (ordnance id 59)
    assert (r[67]["tier"], r[67]["count"]) == (None, 1)  # one loadout combination, ladder 8 / 16 / ...
    assert 0 < overall(list(r.values())) < 1


def test_old_replays_without_loadouts():
    r = by_id(evaluate([game(loadout=None)]))
    assert r[7]["progress"] == 0 and r[17]["progress"] == 0


def test_api_and_leaderboard(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        a = client.get(f"/api/players/{BLUE}/achievements").json()
        assert a["total"] == len(RULES) and len(a["items"]) == len(RULES) and 0 <= a["overall"] <= 1
        assert client.get("/api/players/nobody/achievements").status_code == 404
        assert len(client.get("/api/achievements").json()) == len(RULES)
        board = client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1}).json()
        assert {r["name"] for r in board["items"]} == {"Player", "Other"}
        assert board["label"] == "Achievements (overall %)"


def test_coming_soon_until_the_start_date(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        paths = [f"/api/players/{BLUE}/achievements", "/api/achievements", "/api/achievements/recent",
                 "/api/leaderboard?stat=achievements"]

        def hidden():
            stats = {s["key"] for s in client.get("/api/leaderboard/stats").json()}
            codes = {client.get(p).status_code for p in paths}
            return not client.get("/api/challenges").json()["launched"] and "achievements" not in stats and codes == {403}

        assert hidden()  # no start date
        act(client, actions.set_challenge_window, "2999-01-01", None)
        assert hidden()  # start date still to come
        act(client, actions.set_challenge_window, "2026-01-01", None)
        assert client.get("/api/challenges").json()["launched"]
        assert {client.get(p).status_code for p in paths} == {200}


def test_logic_follows_the_text():
    """Every condition is in the description (user, 2026-10-30)."""
    text = {r.id: r.description for r in RULES}
    assert "(3+ minutes)" in text[18] and "3+ minutes" in text[21] and "50+ games" in text[73]
    # 3+ minutes: a short game does not count, even with 0 deaths
    assert by_id(evaluate([game(deaths=0, play=60.0)]))[18]["progress"] == 0
    assert by_id(evaluate([game(deaths=3)]))[18]["tier"] == "bronze"
    # Pew Pew Proof: "fewer than 5" -> an average of exactly 5 is not enough
    week = [game(f"2026-10-{d:02d}", deaths=5) for d in (26, 27, 28) for _ in range(9)]
    assert by_id(evaluate(week))[43]["progress"] < 1
    week[0] = game("2026-10-26", deaths=4)
    assert by_id(evaluate(week))[43]["progress"] == 1.0


def test_average_unlock_date_is_when_first_reached():
    from backend.achievements import unlock_dates

    # Inverted 60%+ (diamond) over 50+ games: reached on day 2 (games 1-50 are 90 % inverted), then diluted, still above 60%
    games = [game("2026-10-01", upside=900)] * 25 + [game("2026-10-02", upside=900)] * 25 + [game("2026-10-20")] * 20
    assert by_id(evaluate(games))[74]["progress"] == 1.0
    assert unlock_dates(games)[74] == "2026-10-02"


def test_teammate_proximity_targets():
    """Tech Support: ladder 25 / 30 / 35 / 45 / 60 % over a week; Robot Wrecking Squad: 14 / 16 / 19 / 22 / 25 % all-time
    over 50+ games."""
    r = by_id(evaluate([game(mate=250)] * 5))
    assert (r[46]["tier"], r[46]["count"]) == ("bronze", 25) and r[71]["count"] == 0  # 5 games: the all-time one needs 50
    assert by_id(evaluate([game(mate=240)] * 5))[46]["tier"] is None
    assert by_id(evaluate([game(mate=140)] * 50))[71]["tier"] == "bronze"
    assert by_id(evaluate([game(mate=130)] * 50))[71]["tier"] is None


def test_new_gear_challenges():
    starburst = [game(loadout=("rifle", "heal", "loc"))] * 25
    r = by_id(evaluate(starburst))
    assert r[80]["tier"] == "gold" and r[84]["tier"] == "gold" and r[80]["new"]  # 25 games: gold on both ladders
    assert r[86]["progress"] == 0.25  # 1 of the 4 unreleased weapons
    one_game = Game(**{**game().__dict__, "loadouts": {("assault", "heal", "det"): 250, ("blaster", "sensor", "stun"): 250,
                                                      ("scout", "shield", "arc"): 250, ("rocket", "wraith", "burst"): 250}})
    r = by_id(evaluate([one_game]))
    assert r[87]["progress"] == r[88]["progress"] == r[89]["progress"] == 1.0
    assert r[110]["progress"] == pytest.approx(4 / 6, abs=1e-4) and r[111]["progress"] == 4 / 5


def test_now_public_gear_challenges():
    """101-112 (user, 2026-10-31): the unreleased gear now seen in everyday games."""
    quark_day = [game("2026-10-31", loadout=("smg", "buff", "loc"))] * 10
    r = by_id(evaluate(quark_day))
    assert r[103]["tier"] == "gold" and r[104]["tier"] == "gold"  # only Quark / only Translocator, 10 in one day
    assert r[107]["tier"] == "bronze" and r[112]["tier"] == "platinum"  # 10 Quark games; 10 Overcharge games (1/3/5/10/25)
    assert r[101]["progress"] == 0.0 and r[109]["progress"] == 0.5  # no Starburst; Translocator without Dot Field
    both = Game(**{**game().__dict__, "loadouts": {("assault", "heal", "loc"): 500, ("assault", "heal", "dot"): 500}})
    assert by_id(evaluate([both]))[109]["progress"] == 1.0


def test_new_result_challenges():
    def played(day, won, **kw):
        return Game(**{**game(day).__dict__, "team": "blue", "winner": "blue" if won else "orange", **kw})

    streak = [played(f"2026-10-{d:02d}", True) for d in range(1, 5)]
    streak.insert(2, Game(**{**game("2026-10-02").__dict__, "team": "blue", "winner": None}))  # no result: skipped
    r = by_id(evaluate(streak))
    assert (r[90]["count"], r[90]["tier"], r[91]["tier"]) == (4, "silver", "bronze")  # On a Roll 2/3/5/8/12, Unstoppable 4/6/10/14/18
    streak.append(played("2026-10-05", True))
    r = by_id(evaluate(streak))
    assert (r[90]["tier"], r[91]["tier"]) == ("gold", "bronze")
    assert by_id(evaluate(streak + [played("2026-10-06", False)]))[90]["count"] == 5  # best run kept

    sweep = by_id(evaluate([played("2026-10-01", True, rounds_lost=0)]))[93]  # tiered: 1 game = bronze
    assert (sweep["tier"], sweep["count"], sweep["progress"]) == ("bronze", 1, 0.2)
    assert by_id(evaluate([played("2026-10-01", True, rounds_lost=1)]))[93]["progress"] == 0
    attack = played("2026-10-01", True, mode="payload", map="fission", attacking_team="blue", push_s=200.0)
    defend = played("2026-10-01", True, mode="payload", map="fission", attacking_team="orange", block_s=30.0)
    r = by_id(evaluate([attack, defend]))
    assert (r[94]["tier"], r[94]["count"], r[95]["tier"], r[96]["tier"]) == ("bronze", 1, "bronze", "gold")  # push 3.3 min
    assert (r[97]["tier"], r[97]["unit"]) == ("bronze", " min") and r[96]["estimated"]  # block 30 s = first medal


def test_tiered_achievements():
    """Clean Sweep / Special Delivery (user, 2026-10-31): bronze 1, silver 5, gold 10, platinum 25, diamond 100
    games; progress 20 % per medal, partial in between; the text lists every target (website text is the spec)."""
    from backend.achievements import unlock_threshold

    def sweeps(n):
        return [Game(**{**game(f"2026-10-{1 + i % 28:02d}").__dict__, "team": "blue", "winner": "blue", "rounds_lost": 0})
                for i in range(n)]

    expected = {0: (None, 0.0), 1: ("bronze", 0.2), 3: ("bronze", 0.3), 5: ("silver", 0.4), 10: ("gold", 0.6),
                25: ("platinum", 0.8), 50: ("platinum", 0.8 + 25 / 75 / 5), 100: ("diamond", 1.0), 120: ("diamond", 1.0)}
    for n, (medal, progress) in expected.items():
        r = by_id(evaluate(sweeps(n)))[93]
        assert (r["tier"], r["count"], r["levels"]) == (medal, n, [1, 5, 10, 25, 100]), n
        assert r["progress"] == pytest.approx(progress, abs=1e-4), n
    rule = next(r for r in RULES if r.id == 93)
    assert "1 bronze, 5 silver, 10 gold, 25 platinum, 100 diamond" in rule.description
    assert unlock_threshold(rule) == 0.2 and unlock_threshold(next(r for r in RULES if r.id == 43)) == 0.25
    delivery = next(r for r in RULES if r.id == 94)
    assert "Deliver the payload to the end" in delivery.description and delivery.levels == (1, 5, 10, 25, 100)
    assert "count" not in by_id(evaluate(sweeps(1)))[43]  # single-step rules unchanged


def test_ladders_with_units_and_periods():
    """Per-game ladders count the best game, units are in the text, short games do not count."""
    r = by_id(evaluate([game(top=20.0), game(top=9.0)]))
    assert (r[23]["tier"], r[23]["count"], r[23]["unit"]) == ("silver", 20.0, " m/s")  # 14 / 18 / 22 / 26 / 32
    assert "14 m/s bronze, 18 m/s silver" in next(x for x in RULES if x.id == 23).description
    r = by_id(evaluate([game(upside=600)]))
    assert (r[24]["tier"], r[24]["count"]) == ("gold", 60.0)  # 60 % inverted in one 3+ min game: 10 / 25 / 50 / 75 / 90
    assert by_id(evaluate([game(upside=900, play=60.0)]))[24]["count"] == 0


def test_new_activity_challenges():
    days = [game(f"2026-10-{d:02d}") for d in (1, 2, 3, 4, 10)]
    r = by_id(evaluate(days))
    assert r[113]["count"] == 5 and r[114]["count"] == 5 and r[115]["count"] == 2  # games, days, weeks
    assert r[116]["count"] == 4 and r[116]["tier"] == "bronze"  # four days in a row: 3 / 5 / 7 / 14 / 30
    assert r[17]["count"] == 0 and r[124]["count"] == 0  # one loadout only


def test_versatile_bot_counts_days():
    every = [game("2026-10-28", loadout=(w, t, o)) for w, t, o in
             (("assault", "heal", "det"), ("blaster", "sensor", "stun"), ("scout", "shield", "arc"), ("rocket", "wraith", "burst"))]
    r = by_id(evaluate(every))
    assert r[17]["count"] == 1 and r[17]["tier"] == "bronze"  # all 12 equipables in one day = 1 day
    assert by_id(evaluate(every + [game("2026-10-29")]))[17]["count"] == 1


def test_grand_tour_and_medal_collector():
    def won(map_, day="2026-10-01"):
        return Game(**{**game(day, map_=map_).__dict__, "team": "blue", "winner": "blue"})

    r = by_id(evaluate([won(m) for m in ("dyson", "combustion", "fission", "surge")]))
    assert r[122]["count"] == 1 and r[122]["tier"] == "bronze"
    assert r[126]["count"] == 0 and r[126]["levels"] == [5, 10, 25, 50, 75]  # nothing at gold yet
    r = by_id(evaluate([won("dyson", f"2026-10-{1 + i % 28:02d}") for i in range(120)]))
    golds = sum(1 for x in r.values() if x["id"] != 126 and (x["count"] >= x["levels"][2] if "levels" in x else x["progress"] >= 1))
    assert golds > 0 and r[126]["count"] == golds  # Medal Collector counts gold-or-better medals of the others


def test_hex_gear_codes_are_normalised():
    from parser.frames import gear_code

    assert gear_code("0xE32DC7C9DA8051A4") == "scout" and gear_code("0xe32dc7c9da8051a4") == "scout"
    assert gear_code("rifle") == "rifle" and gear_code(None) == "" and gear_code("0xDEADBEEF") == "0xDEADBEEF"


def test_ranking_only_re_evaluates_changed_players(tmp_path, monkeypatch):
    """The everyone-ranking keeps each player's results while their games are unchanged (a new replay changes
    ~8 players of 8k); the result must equal a full evaluation."""
    from backend.api import achievements as api

    with app_client(make_settings(tmp_path)) as client:
        sessions = client.app.state.sessionmaker
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        first = api._compute(sessions, (None, None))
        evaluated = []
        real = api.evaluate
        monkeypatch.setattr(api, "evaluate", lambda games: evaluated.append(len(games)) or real(games))
        assert api._compute(sessions, (None, None)) == first and evaluated == []  # nothing changed
        assert api._compute(sessions, ("2030-01-01", None))["rows"] == [] and evaluated == []  # no games in window
        add(client, {"dyson/1.echoreplay": rf.plain(rf.lines(20))})
        again = api._compute(sessions, (None, None))
        assert evaluated == [2, 2]  # both players gained a game
        api._evaluated.clear()
        assert api._compute(sessions, (None, None)) == again
