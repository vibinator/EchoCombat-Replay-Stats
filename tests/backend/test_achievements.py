from datetime import date

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend.achievements import medal_times, rule_notes, RULES, Game, _all_time, _easier_platinum, _harder, _scaled, evaluate, icon_file, overall, tier

from backend.combat_achievements import COMBAT_RULES

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
    expected = [i for i in range(5, 152) if i not in (91, 99)] + list(range(179, 198))  # 75 original + 70 new (80-151 without 91, Unstoppable, and 99, the first Showboat) + 19 Test Drive; Combat has its own list (combat_achievements); the Mega Prize is not in RULES
    assert ids == expected and len(set(ids)) == 164
    assert next(r for r in RULES if r.id == 151).name == "Showboat" and sum(r.name == "Showboat" for r in RULES) == 1
    assert [r.id for r in RULES if r.new] == [i for i in expected if i >= 80]
    assert all(r.counted for r in RULES)
    assert icon_file(next(r for r in RULES if r.id == 7)) == "comet_daily.png"
    assert icon_file(next(r for r in RULES if r.id == 32)) == "comet_weekly.png"
    assert icon_file(next(r for r in RULES if r.id == 57)) == "comet.png"


def test_tiers():
    assert [tier(p) for p in (0.1, 0.25, 0.5, 0.8, 1.0)] == [None, "white", "bronze", "silver", "gold"]


def test_daily_only_weapon_takes_best_day():
    games = [game("2026-10-27")] * 6 + [game("2026-10-28")] * 15 + [game("2026-10-28", loadout=("assault", "heal", "det"))]
    r = by_id(evaluate(games))
    # One with the Comet: ladder 3 / 6 / 9 / 17 / 22 games in one day (diamond and platinum are 30 % harder than 13 / 17); the best day (15 Comet-only games) counts
    assert (r[7]["tier"], r[7]["count"], r[7]["progress"]) == ("platinum", 15, 1.0)
    assert (r[5]["tier"], r[5]["count"]) == ("bronze", 1)  # Pulsar only once: the first step


def test_weekly_is_a_rolling_seven_days():
    # Sun 1 Nov and Mon 2 Nov are in different calendar weeks but within 7 days of each other
    games = [game(d) for d in ("2026-10-26", "2026-11-01")] + [game("2026-11-02")]
    r = by_id(evaluate(games))
    # Frame-Drop Hell: the best 7 days hold 2 Dyson games (26 Oct + 1 Nov, or 1 Nov + 2 Nov), ladder 4 / 6 / 8 / 16 / 30
    assert (r[50]["count"], r[50]["progress"]) == (2, pytest.approx(0.1))
    games = [game(d) for d in ("2026-10-30", "2026-11-01", "2026-11-03")]  # all three across a calendar week boundary
    assert by_id(evaluate(games))[50]["count"] == 3
    games = [game(d) for d in ("2026-10-26", "2026-11-02")]  # exactly 7 days apart: not the same window
    assert by_id(evaluate(games))[50]["count"] == 1


def test_phasers_switching_weapons_keeps_progress():
    # 5 Pulsar-only games over 6 days, with Nova games in between: they do not break or reset the count
    days = ["2026-10-28", "2026-10-29", "2026-10-30", "2026-10-31", "2026-11-01"]
    games = []
    for d in days:
        games += [game(d, loadout=("assault", "heal", "det")), game(d, loadout=("blaster", "heal", "det"))]
    r = by_id(evaluate(games))
    assert r[30]["count"] == 5 and r[31]["count"] == 5  # Pulse Check and Eat My Nova!
    assert "in any 7 days" in r[30]["description"]


def test_per_game_rules_ignore_short_appearances():
    r = by_id(evaluate([game(deaths=0, play=30.0)]))
    assert r[18]["progress"] == 0.0
    r = by_id(evaluate([game(deaths=3)]))
    assert (r[18]["tier"], r[18]["count"]) == (None, 1) and r[18]["estimated"]


def test_all_time_and_overall():
    games = [game(deaths=10) for _ in range(100)]
    r = by_id(evaluate(games))
    assert (r[68]["tier"], r[68]["count"]) == ("gold", 1000)  # 1000 deaths
    assert (r[59]["tier"], r[59]["count"]) == ("platinum", 100)  # 100 games with Detonator (ordnance id 59)
    assert (r[67]["tier"], r[67]["count"]) == (None, 1)  # one loadout combination, ladder 6 / 12 / ...
    assert 0 < overall(list(r.values())) < 1


def test_old_replays_without_loadouts():
    r = by_id(evaluate([game(loadout=None)]))
    assert r[7]["progress"] == 0 and r[17]["progress"] == 0


def test_api_and_leaderboard(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        a = client.get(f"/api/players/{BLUE}/achievements").json()
        assert a["total"] == len(RULES) and len(a["items"]) == len(RULES) + len(COMBAT_RULES) and 0 <= a["overall"] <= 1
        assert client.get("/api/players/nobody/achievements").status_code == 404
        assert len(client.get("/api/achievements").json()) == len(RULES) + len(COMBAT_RULES)
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
    assert "25+ games" in text[73] and "25+ games" in text[43]
    # the counting rules are listed per achievement, not repeated in the description
    notes = {r.id: rule_notes(r) for r in RULES}
    assert "4+ min games" in notes[18] and "4+ min games" in notes[21]
    assert "Best game" in notes[21] and "Best 7 days" in notes[43]
    assert "3+ players per team" in notes[139] and "3+ players per team" not in notes[23]
    assert not any("4+ minutes" in d or "best game" in d for d in text.values())
    # 4+ minutes: a short game does not count, even with 0 deaths
    assert by_id(evaluate([game(deaths=0, play=60.0)]))[18]["progress"] == 0
    assert by_id(evaluate([game(deaths=3)]))[18]["count"] == 1
    # Pew Pew Proof: "fewer than 5" -> an average of exactly 5 is not enough
    week = [game(f"2026-10-{d:02d}", deaths=5) for d in (26, 27, 28) for _ in range(9)]
    assert by_id(evaluate(week))[43]["progress"] < 1
    week[0] = game("2026-10-26", deaths=4)
    assert by_id(evaluate(week))[43]["progress"] == 1.0


def test_average_unlock_date_is_when_first_reached():
    from backend.achievements import unlock_dates

    # Inverted 40%+ (platinum) over 50+ games: reached on day 2 (games 1-50 are 90 % inverted), then diluted, still above 40%
    games = [game("2026-10-01", upside=900)] * 25 + [game("2026-10-02", upside=900)] * 25 + [game("2026-10-20")] * 20
    assert by_id(evaluate(games))[74]["progress"] == 1.0
    assert unlock_dates(games)[74] == "2026-10-02"


def test_teammate_proximity_targets():
    """Tech Support: ladder 16 / 20 / 24 / 26 / 28 % over a week on 3+ days with 10+ minutes in bounds (these games have 50 s each);
    Robot Wrecking Squad: 14 / 15.5 / 17 / 19.5 / 22.5 % all-time over 50+ games."""
    def over_days(mate, *per_day):
        return [g for i, n in enumerate(per_day) for g in [game(f"2026-10-0{i + 1}", mate=mate)] * n]
    r = by_id(evaluate(over_days(170, 4, 4, 4)))
    assert (r[46]["tier"], r[46]["count"]) == ("bronze", 17) and r[71]["count"] == 0  # 12 games: the all-time one needs 50
    assert by_id(evaluate(over_days(170, 4, 4, 3)))[46]["tier"] is None  # under 10 minutes in bounds
    assert by_id(evaluate(over_days(150, 4, 4, 4)))[46]["tier"] is None
    assert by_id(evaluate(over_days(170, 6, 6)))[46]["tier"] is None  # two days only
    assert by_id(evaluate([game(mate=140)] * 50))[71]["tier"] == "bronze"
    assert by_id(evaluate([game(mate=130)] * 50))[71]["tier"] is None


def test_new_gear_challenges():
    starburst = [game(loadout=("rifle", "heal", "loc"))] * 30
    r = by_id(evaluate(starburst))
    assert r[80]["tier"] == "gold" and r[84]["tier"] == "gold" and r[80]["new"]  # 30 games: gold on both ladders (1 / 6 / 30 / ...: all-time ladders are raised 20 %)
    assert r[86]["progress"] == 0.25  # 1 of the 4 unreleased weapons
    one_game = Game(**{**game().__dict__, "loadouts": {("assault", "heal", "det"): 250, ("blaster", "sensor", "stun"): 250,
                                                      ("scout", "shield", "arc"): 250, ("rocket", "wraith", "burst"): 250}})
    r = by_id(evaluate([one_game]))
    assert r[87]["progress"] == r[88]["progress"] == r[89]["progress"] == 1.0
    assert r[110]["progress"] == 4 / 5 and r[111]["progress"] == 4 / 5


def test_now_public_gear_challenges():
    """101-112 (user, 2026-10-31): the unreleased gear now seen in everyday games."""
    quark_day = [game("2026-10-31", loadout=("smg", "buff", "loc"))] * 10
    r = by_id(evaluate(quark_day))
    assert r[103]["tier"] == "platinum" and r[104]["tier"] == "platinum"  # only Quark / only Translocator, 10 in one day
    assert r[107]["tier"] == "bronze" and r[112]["tier"] == "bronze"  # 10 Quark / Overcharge games on the veteran ladder 5/15/50/150/500
    assert r[101]["progress"] == 0.0 and r[109]["progress"] == 0.5  # no Starburst; Translocator without Dot Field
    both = Game(**{**game().__dict__, "loadouts": {("assault", "heal", "loc"): 500, ("assault", "heal", "dot"): 500}})
    assert by_id(evaluate([both]))[109]["progress"] == 1.0


def test_new_result_challenges():
    def played(day, won, **kw):
        return Game(**{**game(day).__dict__, "team": "blue", "winner": "blue" if won else "orange", **kw})

    streak = [played(f"2026-10-{d:02d}", True) for d in range(1, 5)]
    streak.insert(2, Game(**{**game("2026-10-02").__dict__, "team": "blue", "winner": None}))  # no result: skipped
    r = by_id(evaluate(streak))
    assert (r[90]["count"], r[90]["tier"]) == (4, "silver")  # On a Roll 2/3/4/7/8 (eased 2026-11-04; was 2/4/6/13/18)
    streak.append(played("2026-10-05", True))
    r = by_id(evaluate(streak))
    assert r[90]["tier"] == "gold" and by_id(evaluate(streak + [played("2026-10-06", True)]))[90]["tier"] == "diamond"
    assert by_id(evaluate(streak + [played("2026-10-06", False)]))[90]["count"] == 5  # best run kept

    sweep = by_id(evaluate([played("2026-10-01", True, rounds_lost=0)]))[93]  # tiered: 1 game = bronze
    assert (sweep["tier"], sweep["count"], sweep["progress"]) == ("bronze", 1, 0.2)
    assert by_id(evaluate([played("2026-10-01", True, rounds_lost=1)]))[93]["progress"] == 0
    attack = played("2026-10-01", True, mode="payload", map="fission", attacking_team="blue", push_s=120.0)
    defend = played("2026-10-01", True, mode="payload", map="fission", attacking_team="orange", block_s=30.0)
    r = by_id(evaluate([attack, defend]))
    assert (r[94]["tier"], r[94]["count"], r[95]["tier"], r[96]["tier"]) == ("bronze", 1, "bronze", "bronze")  # push 120 s: bronze at 112 s
    assert (r[97]["tier"], r[97]["unit"]) == ("bronze", " s") and r[96]["estimated"]  # block 30 s = silver (15 / 30 / 45 / 62 / 81 s)


def test_tiered_achievements():
    """Clean Sweep / Special Delivery (user, 2026-10-31): bronze 1, silver 5, gold 10, diamond 25, platinum 100
    games (diamond and platinum 30 % harder, 2026-11-03: 33 and 130); progress 20 % per medal, partial in between; the text
    lists every target (website text is the spec)."""
    from backend.achievements import unlock_threshold

    def sweeps(n):
        return [Game(**{**game(f"2026-10-{1 + i % 28:02d}").__dict__, "team": "blue", "winner": "blue", "rounds_lost": 0})
                for i in range(n)]

    expected = {0: (None, 0.0), 1: ("bronze", 0.2), 3: ("bronze", 0.28), 6: ("silver", 0.4), 12: ("gold", 0.6),
                39: ("diamond", 0.8), 50: ("diamond", 0.8 + 11 / 117 / 5), 156: ("platinum", 1.0), 180: ("platinum", 1.0)}
    for n, (medal, progress) in expected.items():
        r = by_id(evaluate(sweeps(n)))[93]
        assert (r["tier"], r["count"], r["levels"]) == (medal, n, [1, 6, 12, 39, 156]), n
        assert r["progress"] == pytest.approx(progress, abs=1e-4), n
    rule = next(r for r in RULES if r.id == 93)
    assert "1 bronze, 6 silver, 12 gold, 39 diamond, 156 platinum" in rule.description
    assert unlock_threshold(rule) == 0.2 and unlock_threshold(next(r for r in RULES if r.id == 43)) == 0.25
    delivery = next(r for r in RULES if r.id == 94)
    assert "Deliver the payload to the end" in delivery.description and delivery.levels == (1, 6, 12, 39, 94)
    assert "count" not in by_id(evaluate(sweeps(1)))[43]  # single-step rules unchanged


def test_ladders_with_units_and_periods():
    """Per-game ladders count the best game, units are in the text, short games do not count."""
    r = by_id(evaluate([game(top=20.0), game(top=9.0)]))
    assert (r[23]["tier"], r[23]["count"], r[23]["unit"]) == ("gold", 20.0, " m/s")  # 14 / 17 / 20 / 26 / 30
    assert "14 m/s bronze, 17 m/s silver" in next(x for x in RULES if x.id == 23).description
    r = by_id(evaluate([game(upside=600)]))
    assert (r[24]["tier"], r[24]["count"]) == ("gold", 60.0)  # 60 % inverted in one 3+ min game: 15 / 35 / 52 / 66 / 78 (TUNED_LEVELS)
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
        return Game(**{**game(day, map_=map_).__dict__, "team": "blue", "winner": "blue", "near_mate": 200})

    r = by_id(evaluate([won(m) for m in ("dyson", "combustion", "fission", "surge")]))
    assert r[122]["count"] == 1 and r[122]["tier"] == "bronze"
    # Medal Collector counts every challenge at gold or better (more of them since the ladders were retuned on 2026-11-04)
    assert r[126]["count"] >= 1 and r[126]["levels"] == [5, 10, 25, 65, 98]
    r = by_id(evaluate([won("dyson", f"2026-10-{1 + i % 28:02d}") for i in range(120)]))
    golds = sum(1 for x in r.values() if x["id"] != 126 and x["group"] != "Gear in one game" and (x["count"] >= x["levels"][2] if "levels" in x else x["progress"] >= 1))
    assert golds > 0 and r[126]["count"] == golds  # Medal Collector counts gold-or-better medals of the others
    assert any(x["group"] == "Gear in one game" and x["progress"] >= 1 for x in r.values())  # Test Drives were completed, and are not counted


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


def test_new_gear_matches_the_older_gear():
    """Every weapon, ordnance and tac mod has the same ladders, new gear included (user, 2026-10-31 and 2026-11-03)."""
    by = {r.id: r for r in RULES}
    old_vet, old_day, old_week = by[55].levels, by[5].levels, by[30].levels
    assert all(by[i].levels == old_vet for i in (105, 106, 107, 108, 112, 133, 134))  # veterans (+ Overcharge, Blazar, Dot Field)
    assert all(by[i].levels == old_day for i in (101, 102, 103, 104, 131, 135, 136))  # only X in one day
    assert all(by[i].levels == old_week for i in (127, 128, 129, 130, 132, 137, 138))  # only X in one week
    week = [game(f"2026-10-{d:02d}", loadout=("smg", "buff", "loc")) for d in (26, 27, 28) for _ in range(6)]
    r = by_id(evaluate(week))
    assert (r[129]["tier"], r[129]["count"]) == ("platinum", 18) and r[132]["count"] == 18  # 18 Quark-only games in a week


def test_one_game_challenges_need_enough_players():
    base = game("2026-10-01")
    long_game = {**base.__dict__, "play_time_s": 1200.0}
    r = by_id(evaluate([Game(**{**long_game, "enough_players": False})]))
    assert r[140]["count"] == 0  # Marathon Bot: fewer than 3 per team
    r = by_id(evaluate([Game(**long_game)]))
    assert r[140]["count"] == 20


def test_lone_wolf_uses_its_own_distance():
    base = game("2026-10-01", mate=0).__dict__
    far_from_2_6m_only = Game(**{**base, "in_bounds": 2000, "lone_wolf_near": 400})  # always over 2.6 m, within 3.5 m for 20 %
    assert by_id(evaluate([far_from_2_6m_only]))[143]["count"] == pytest.approx(80)
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1200})]))[143]["tier"] == "platinum"  # exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1199})]))[143]["count"] == 0  # just under: a few seconds of play do not count
    assert "3.5 m" in next(rule for rule in RULES if rule.id == 143).description


def test_untouchable_is_one_medal_and_needs_a_minute_in_bounds():
    base = {**game("2026-10-01", deaths=0).__dict__, "team": "blue", "winner": "blue"}
    assert next(rule for rule in RULES if rule.id == 139).levels == ()  # one win is the whole challenge
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1200})]))[139]["progress"] == 1.0  # exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1199})]))[139]["progress"] == 0
    assert by_id(evaluate([Game(**{**base, "in_bounds": 0})]))[139]["progress"] == 0  # never on the map: could not die
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1200, "deaths": 1})]))[139]["progress"] == 0
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1200, "winner": "orange"})]))[139]["progress"] == 0


def test_lone_wolf_has_no_value_before_the_replay_is_read_again():
    base = game("2026-10-01", mate=0).__dict__
    assert by_id(evaluate([Game(**{**base, "in_bounds": 2000, "lone_wolf_near": None})]))[143]["count"] == 0  # not a false 100 %


def test_seven_day_upside_down_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 49).levels == (9.3, 22, 36, 47, 57)
    def flipped(day, frames=4000):
        return Game(**{**game(day).__dict__, "upside": frames * 3 // 5, "in_bounds": frames})
    assert by_id(evaluate([flipped("2026-10-01"), flipped("2026-10-02"), flipped("2026-10-03")]))[49]["tier"] == "platinum"
    assert by_id(evaluate([flipped("2026-10-01"), flipped("2026-10-02"), flipped("2026-10-03", 3995)]))[49]["count"] == 0
    assert by_id(evaluate([flipped("2026-10-01", 12000), flipped("2026-10-02", 12000)]))[49]["count"] == 0  # two days


def test_speed_demon_needs_a_minute_in_bounds():
    base = game("2026-10-01").__dict__
    rule = next(rule for rule in RULES if rule.id == 145)
    assert rule.levels == (3.5, 4, 4.5, 5.25, 6)
    fast = {**base, "speed_sum": 6.0 * 1200}
    assert by_id(evaluate([Game(**{**fast, "in_bounds": 1200})]))[145]["tier"] == "platinum"  # 6 m/s for exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**fast, "in_bounds": 1199})]))[145]["count"] == 0


def test_seven_day_speed_needs_three_days_and_ten_minutes_in_bounds():
    base = game("2026-10-01").__dict__  # 20 Hz, 4 m/s below
    def fast(frames, day="2026-10-01"):
        return Game(**{**base, "started_at": f"{day}T20:00:00.000", "in_bounds": frames, "speed_sum": 4.0 * frames})
    assert next(rule for rule in RULES if rule.id == 48).levels == (2.75, 3, 3.25, 3.5, 3.75)
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(4000, "2026-10-07")]))[48]["tier"] == "platinum"  # exactly 10 minutes, any 3 days of the 7
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(3999, "2026-10-07")]))[48]["count"] == 0
    assert by_id(evaluate([fast(24000)]))[48]["count"] == 0  # one long game
    assert by_id(evaluate([fast(6000), fast(6000)]))[48]["count"] == 0  # several games on one day
    assert by_id(evaluate([fast(6000), fast(6000, "2026-10-03")]))[48]["count"] == 0  # two days
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(4000, "2026-10-20")]))[48]["count"] == 0  # not in the same 7 days


def test_seven_day_enemy_share_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 47).levels == (12, 14, 16, 18, 20)
    def close(day, frames=4000):
        return Game(**{**game(day).__dict__, "near_enemy": frames // 5, "in_bounds": frames})
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03")]))[47]["tier"] == "platinum"  # 20 % for exactly 10 minutes at 20 Hz
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03", 3995)]))[47]["count"] == 0
    assert by_id(evaluate([close("2026-10-01", 12000), close("2026-10-02", 12000)]))[47]["count"] == 0  # two days


def test_can_we_talk_needs_a_minute_in_bounds():
    base = game("2026-10-01").__dict__
    assert next(rule for rule in RULES if rule.id == 22).levels == (25, 30, 35, 40, 50)
    close = {**base, "near_enemy": 600}
    assert by_id(evaluate([Game(**{**close, "in_bounds": 1200})]))[22]["tier"] == "platinum"  # 50 % for exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**close, "in_bounds": 1199})]))[22]["count"] == 0


def test_seven_day_teammate_share_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 46).levels == (16, 20, 24, 26, 28)
    def close(day, frames=4000):
        return Game(**{**game(day).__dict__, "near_mate": frames * 7 // 25, "in_bounds": frames})
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03")]))[46]["tier"] == "platinum"  # 28 % for exactly 10 minutes at 20 Hz
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03", 3975)]))[46]["count"] == 0
    assert by_id(evaluate([close("2026-10-01", 12000), close("2026-10-02", 12000)]))[46]["count"] == 0  # two days


def test_statue_needs_a_minute_in_bounds():
    base = game("2026-10-01").__dict__
    assert next(rule for rule in RULES if rule.id == 142).levels == (54, 61, 67, 73, 80)
    still = {**base, "stopped": 960}
    assert by_id(evaluate([Game(**{**still, "in_bounds": 1200})]))[142]["tier"] == "platinum"  # 80 % for exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**still, "in_bounds": 1199})]))[142]["count"] == 0


def test_full_team_salvo_needs_a_minute_in_bounds():
    base = game("2026-10-01").__dict__
    close = {**base, "near_mate": 972}  # 81 % of 1200
    assert by_id(evaluate([Game(**{**close, "in_bounds": 1200})]))[21]["tier"] == "platinum"  # exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**close, "in_bounds": 1199})]))[21]["count"] == 0


def test_all_gear_shares_one_ladder_per_kind():
    veteran = {r.levels for r in RULES if r.name.endswith(" Veteran") and r.period == "all"}
    assert len(veteran) == 1  # one ladder for every weapon, ordnance and tac mod (set in TUNED_LEVELS on 2026-11-04)
    for period in ("day", "week"):  # one ladder for "only X" in a day / in 7 days (42: Gearhead is about loadouts, not one gear)
        assert len({r.levels for r in RULES if "using only" in r.description and r.period == period and r.id != 42}) == 1
    assert next(r for r in RULES if r.id == 112).levels in veteran  # Overclocked is a veteran ladder too


def test_victory_lap_needs_a_win():
    won = Game(**{**game("2026-10-01").__dict__, "team": "blue", "winner": "blue", "emotes": 30})
    lost = Game(**{**won.__dict__, "winner": "orange"})
    assert by_id(evaluate([won]))[151]["count"] == 30 and by_id(evaluate([lost]))[151]["count"] == 0


def test_achiever_facts_and_endpoint(tmp_path):
    from backend.achievements import achiever_facts

    none = achiever_facts([0.0] * len(RULES))
    assert none["completed"] == 0 and none["medals"] == 0 and none["best_section"] is None
    full = achiever_facts([1.0] * len(RULES))
    assert full["completed"] == len(RULES) == full["total"] and full["gold_plus"] == len(RULES) and full["best_section_share"] == 1.0
    # one ladder at 3 of 5 medals (progress 0.6): gold, 3 medals, nothing completed
    one = [0.0] * len(RULES)
    index = next(i for i, r in enumerate(RULES) if r.id == 7)
    one[index] = 0.6
    facts = achiever_facts(one)
    assert (facts["completed"], facts["medals"], facts["gold_plus"]) == (0, 3, 1) and facts["best_section"] == "In one day"
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        top = client.get("/api/leaderboard/achievers", params={"min_games": 1}).json()
        assert {r["name"] for r in top} == {"Player", "Other"}
        assert all(r["total"] == len(RULES) and 0 <= r["completed"] <= len(RULES) and "medals" in r for r in top)


def test_test_drive_one_challenge_per_released_item():
    from backend.achievements import _released_gear, section_of

    drives = {r.name: r for r in RULES if r.name.startswith("Test Drive: ")}
    assert len(drives) == sum(len(x) for x in _released_gear()) == 19
    assert {"Test Drive: Pulsar", "Test Drive: Overcharge", "Test Drive: Dot Field", "Test Drive: Blazar"} <= set(drives)
    assert all(r.counted and r.period == "game" and section_of(r) == "In one game" for r in drives.values())
    pulsar = next(r for r in drives.values() if r.name.endswith("Pulsar"))
    assert pulsar.description == "Use Pulsar for at least 3 minutes in one game"
    assert rule_notes(pulsar) == ["Best game", "3+ players per team"]


def test_test_drive_counts_the_time_in_one_game():
    pulsar = next(r.id for r in RULES if r.name == "Test Drive: Pulsar")
    nova = next(r.id for r in RULES if r.name == "Test Drive: Nova")
    heal = next(r.id for r in RULES if r.name == "Test Drive: Repair Matrix")

    def swapped(pulsar_frames, nova_frames, play=400.0):
        g = game(play=play)
        g.loadouts = {("assault", "heal", "det"): pulsar_frames, ("blaster", "heal", "det"): nova_frames}
        return g

    r = by_id(evaluate([swapped(600, 400)]))  # 60 % and 40 % of a 400 s game: 240 s and 160 s
    assert r[pulsar]["progress"] == 1 and r[nova]["progress"] == round(160 / 180, 4) and r[heal]["progress"] == 1
    r = by_id(evaluate([swapped(600, 400)] * 3))
    assert r[nova]["progress"] == round(160 / 180, 4)  # one game, not added up over games
    assert by_id(evaluate([game(play=179.0, loadout=("assault", "heal", "det"))]))[pulsar]["progress"] < 1
    assert by_id(evaluate([game(play=180.0, loadout=("assault", "heal", "det"))]))[pulsar]["progress"] == 1
    small = game(loadout=("assault", "heal", "det"))
    small.enough_players = False
    assert by_id(evaluate([small]))[pulsar]["progress"] == 0  # a game under 3v3 does not count
    assert medal_times([game("2026-11-05", loadout=("assault", "heal", "det"))])[pulsar][None].startswith("2026-11-05")
