from datetime import date

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend.achievements import rule_notes, RULES, Game, _all_time, _easier_platinum, _harder, _scaled, evaluate, icon_file, overall, tier

from backend.combat_achievements import COMBAT_RULES
from backend.profile_achievements import COUNTED_RULES, PROFILE_RULES

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
    removed = {91, 99, 80, 81, 82, 83, 84, 85, 113}  # Unstoppable, the first Showboat, and the duplicates removed on 2026-11-05
    # 75 original + 63 new + Switch Hitter + Attack Drone / Umbral Veil / Neutron (3 each, 2026-11-20); the 22 Test Drives (179-197,
    # 268, 272, 276) were retired on 2026-11-26 (D63); Combat has its own list (combat_achievements); the Mega Prize is not in RULES
    retired = {21, 22, 24, 87, 88, 89, 92, 109, 110, 111, 121, 139, 140, 142, 144, 145, 146, 149}  # Specials trimmed (2026-11-26, D64); 96, 97 back 2026-11-28
    expected = [i for i in range(5, 152) if i not in removed | retired] + [201, 279] + [i for i in range(265, 277) if (i - 265) % 4 != 3]
    assert ids == expected and len(set(ids)) == 131  # + Full Lobby on Kronos II (279, 2026-11-26); + 96, 97 (2026-11-28)
    assert next(r for r in RULES if r.id == 151).name == "Showbot" and sum(r.name == "Showbot" for r in RULES) == 1  # no "(Emotes)" tag (2026-11-26)
    assert [r.id for r in RULES if r.new] == [i for i in expected if i >= 80]
    assert all(r.counted for r in RULES)
    assert icon_file(next(r for r in RULES if r.id == 7)) == "comet_daily.png"
    assert icon_file(next(r for r in RULES if r.id == 32)) == "comet_weekly.png"
    assert icon_file(next(r for r in RULES if r.id == 57)) == "comet.png"
    # "colour_" art keeps its own colours, so no daily / weekly variant even in the old daily range (id 29)
    assert icon_file(next(r for r in RULES if r.id == 29)) == "colour_sweaty.png"
    assert icon_file(next(r for r in RULES if r.id == 23)) == "launch_daily.png"
    # every Dot Field challenge has the Dot Field art (user, 2026-11-20); so do the later gear sets
    assert {icon_file(r) for r in RULES if "Dot Field" in r.name or r.id in (136, 138)} == {"dot_field.png"}
    assert [icon_file(r) for r in RULES if r.id in (265, 270, 275)] == ["attack_drone.png", "umbral_veil.png", "neutron.png"]
    assert {icon_file(r) for r in RULES if "Overcharge" in r.name or r.id in (112, 131, 132)} == {"overcharge.png"}


def test_every_icon_file_exists():
    from pathlib import Path
    from backend.combat_achievements import COMBAT_RULES
    folder = Path(__file__).resolve().parents[2] / "app" / "frontend" / "public" / "achievements"
    missing = {r.id: icon_file(r) for r in RULES + COMBAT_RULES if r.icon and not (folder / icon_file(r)).is_file()}
    assert not missing


def test_tiers():
    assert [tier(p) for p in (0.1, 0.25, 0.5, 0.8, 1.0)] == [None, "white", "bronze", "silver", "gold"]


def test_daily_only_weapon_takes_best_day():
    games = [game("2026-10-27")] * 6 + [game("2026-10-28")] * 15 + [game("2026-10-28", loadout=("assault", "heal", "det"))]
    r = by_id(evaluate(games))
    # One with the Comet: ladder 3 / 9 / 17 / 22 games in one day (bronze, silver, gold, crown); the best day (15 Comet-only games) counts
    assert (r[7]["tier"], r[7]["count"], r[7]["progress"]) == ("crown", 15, 1.0)
    assert (r[5]["tier"], r[5]["count"]) == (None, 1)  # Pulsar only once: bronze needs 2 (2 / 6 / 8 / 10, 2026-11-26)


def test_weekly_is_a_rolling_seven_days():
    # Sun 1 Nov and Mon 2 Nov are in different calendar weeks but within 7 days of each other
    games = [game(d) for d in ("2026-10-26", "2026-11-01")] + [game("2026-11-02")]
    r = by_id(evaluate(games))
    # Frame-Drop Hell: the best 7 days hold 2 Dyson games (26 Oct + 1 Nov, or 1 Nov + 2 Nov), ladder 4 / 8 / 12 / 18
    assert (r[50]["count"], r[50]["progress"]) == (2, pytest.approx(0.125))
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
    assert (r[68]["tier"], r[68]["count"]) == ("gold", 1000)  # 1000 deaths: 95 / 400 / 800 / 1,400 (halfway to November's pace, 2026-11-26)
    assert (r[59]["tier"], r[59]["count"]) == ("gold", 100)  # 100 games with Detonator (ordnance id 59): 20 / 50 / 80 / 120
    assert (r[67]["tier"], r[67]["count"]) == (None, 1)  # one loadout combination, ladder 6 / 12 / ...
    assert 0 < overall(list(r.values())) < 1


def test_old_replays_without_loadouts():
    r = by_id(evaluate([game(loadout=None)]))
    assert r[7]["progress"] == 0 and r[17]["progress"] == 0


def test_api_and_leaderboard(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two())) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        a = client.get(f"/api/players/{BLUE}/achievements").json()
        assert a["total"] == len(COUNTED_RULES) and len(a["items"]) == len(RULES) + len(COMBAT_RULES) + len(PROFILE_RULES) and 0 <= a["overall"] <= 1
        assert client.get("/api/players/nobody/achievements").status_code == 404
        assert len(client.get("/api/achievements").json()) == len(RULES) + len(COMBAT_RULES) + len(PROFILE_RULES)
        board = client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1}).json()
        assert {r["name"] for r in board["items"]} == {"Player", "Other", "Mate", "Rival"}
        assert board["label"] == "Challenges (overall %)"


def test_coming_soon_until_the_start_date(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        paths = [f"/api/players/{BLUE}/achievements", "/api/achievements", "/api/achievements/recent",
                 "/api/leaderboard?stat=achievements"]

        def hidden():
            # before the launch the stat is only listed marked "preview" (the page shows it to the preview role only)
            stats = {s["key"] for s in client.get("/api/leaderboard/stats").json() if not s.get("preview")}
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
    assert "25+ games" in text[73] and "dying fewer than 5 times a game" in text[43]
    # the counting rules are listed per achievement, not repeated in the description
    notes = {r.id: rule_notes(r) for r in RULES}
    assert "4+ min games" in notes[18] and "4+ min games" in notes[43] and "4+ min games" in notes[42]
    assert "Best game" in notes[23] and "Best 7 days" in notes[43]
    # every challenge says 2+ players per team (user, 2026-11-28), Full Lobby its own 5v5
    assert all("2+ players per team" in n for i, n in notes.items() if i not in (279, 126))  # 126: Medal Collector counts medals, not games and "2+ players per team" not in notes[279]
    assert {"4+ min games", "2+ players per team"} <= set(notes[23])  # top speed: full-size games only (user, 2026-11-26)
    assert by_id(evaluate([game(top=30.0, play=200.0)]))[23]["count"] == 0  # under 4 minutes
    small = game(top=30.0)
    small.enough_players = False
    assert by_id(evaluate([small]))[23]["count"] == 0  # under 2 per team
    assert not any("4+ minutes" in d or "best game" in d for d in text.values())
    # 4+ minutes: a short game does not count, even with 0 deaths
    assert by_id(evaluate([game(deaths=0, play=60.0)]))[18]["progress"] == 0
    assert by_id(evaluate([game(deaths=3)]))[18]["count"] == 1
    # Pew Pew Proof: "fewer than 5" -> an average of exactly 5 is not enough, and it needs 3 different days
    week = [game(f"2026-10-{d:02d}", deaths=5) for d in (26, 27, 28) for _ in range(12)]  # 36: a crown since 2026-11-28 (35)
    assert by_id(evaluate(week))[43]["count"] == 0
    week[0] = game("2026-10-26", deaths=4)
    assert by_id(evaluate(week))[43]["count"] == 36 and by_id(evaluate(week))[43]["tier"] == "crown"
    one_evening = [game("2026-10-26", deaths=0)] * 30
    assert by_id(evaluate(one_evening))[43]["count"] == 0  # all on one day
    assert by_id(evaluate([game("2026-10-26", deaths=0, play=60.0)] * 30))[43]["count"] == 0  # short games do not count


def test_gearhead_counts_long_full_games_only():
    from backend.achievements import _gearhead_run

    a, b = ("scout", "heal", "det"), ("assault", "stun", "rocket")
    run = [game(f"2026-10-2{i}", loadout=a) for i in range(1, 5)]
    assert _gearhead_run(run) == 4
    assert _gearhead_run(run[:2] + [game("2026-10-23", loadout=b)] + run[2:]) == 2  # another loadout ends the run
    assert _gearhead_run(run[:2] + [game("2026-10-23", loadout=b, play=60.0)] + run[2:]) == 4  # a short game is ignored


def test_average_unlock_date_is_when_first_reached():
    from backend.achievements import unlock_dates

    # Inverted 40%+ (gold) over 50+ games: reached on day 2 (games 1-50 are 90 % inverted), then diluted, still above 40%
    games = [game("2026-10-01", upside=900)] * 25 + [game("2026-10-02", upside=900)] * 25 + [game("2026-10-20")] * 20
    assert by_id(evaluate(games))[74]["progress"] == 1.0
    assert unlock_dates(games)[74] == "2026-10-02"


def test_teammate_proximity_targets():
    """Tech Support: ladder 16 / 20 / 24 / 26 / 28 % over a week on 3+ days with 10+ minutes in bounds (these games have 50 s each);
    Robot Wrecking Squad: 14 / 15.5 / 17 / 19.5 / 22.5 % all-time over 50+ games."""
    def over_days(mate, *per_day):
        return [g for i, n in enumerate(per_day) for g in [game(f"2026-10-0{i + 1}", mate=mate)] * n]
    r = by_id(evaluate(over_days(180, 4, 4, 4)))
    assert (r[46]["tier"], r[46]["count"]) == ("bronze", 18) and r[71]["count"] == 0  # 12 games: the all-time one needs 50
    assert by_id(evaluate(over_days(180, 4, 4, 3)))[46]["tier"] is None  # under 10 minutes in bounds
    assert by_id(evaluate(over_days(150, 4, 4, 4)))[46]["tier"] is None
    assert by_id(evaluate(over_days(180, 6, 6)))[46]["tier"] is None  # two days only
    assert by_id(evaluate([game(mate=120)] * 50))[71]["tier"] == "bronze"  # 12 / 14 / 16 / 18 % (2026-11-11)
    assert by_id(evaluate([game(mate=140)] * 50))[71]["tier"] == "silver"
    assert by_id(evaluate([game(mate=110)] * 50))[71]["tier"] is None


def test_new_gear_challenges():
    starburst = [game(loadout=("rifle", "heal", "loc"))] * 30
    r = by_id(evaluate(starburst))
    assert r[105]["tier"] == "bronze" and r[108]["tier"] == "bronze" and r[105]["new"]  # 30 games on the Veteran ladder: 20 / 50 / 80 / 120 (2026-11-26)
    assert r[86]["count"] == 0  # Forbidden Arsenal: the least-used experimental weapon (only Starburst played here)
    four = [game(loadout=(w, "heal", "loc")) for w in ("rifle", "magnum", "smg", "chain")] * 2
    assert (by_id(evaluate(four))[86]["count"], by_id(evaluate(four))[86]["levels"]) == (2, list(next(x for x in RULES if x.id == 123).levels))  # the No Gun Left Behind ladder



def test_now_public_gear_challenges():
    """101-112 (user, 2026-10-31): the unreleased gear now seen in everyday games."""
    quark_day = [game("2026-10-31", loadout=("smg", "buff", "loc"))] * 10
    r = by_id(evaluate(quark_day))
    assert r[103]["tier"] == "crown" and r[104]["tier"] == "crown"  # only Quark / only Translocator, 10 in one day
    assert r[107]["tier"] is None and r[112]["tier"] is None and r[107]["count"] == 10  # 10 Quark / Overcharge games: the veteran ladder starts at 20
    assert r[101]["progress"] == 0.0  # no Starburst (Beam Me Up, Translocator, 109, retired 2026-11-26)


def test_new_result_challenges():
    def played(day, won, **kw):
        return Game(**{**game(day).__dict__, "team": "blue", "winner": "blue" if won else "orange", **kw})

    streak = [played(f"2026-10-{d:02d}", True) for d in range(1, 5)]
    streak.insert(2, Game(**{**game("2026-10-02").__dict__, "team": "blue", "winner": None}))  # no result: skipped
    r = by_id(evaluate(streak))
    assert (r[90]["count"], r[90]["tier"]) == (4, "bronze")  # On a Roll 3/5/6/7 (was 2/3/4/7/8 (eased 2026-11-04; was 2/4/6/13/18)
    streak.append(played("2026-10-05", True))
    r = by_id(evaluate(streak))
    assert r[90]["tier"] == "silver" and by_id(evaluate(streak + [played("2026-10-06", True), played("2026-10-07", True)]))[90]["tier"] == "gold"  # 3/5/7/9 (2026-11-26)
    assert by_id(evaluate(streak + [played("2026-10-06", False)]))[90]["count"] == 5  # best run kept

    sweep = by_id(evaluate([played("2026-10-01", True, rounds_lost=0)]))[93]  # tiered: bronze is 2 games (2026-11-26)
    assert (sweep["tier"], sweep["count"], sweep["progress"]) == (None, 1, 0.125)
    assert by_id(evaluate([played("2026-10-01", True, rounds_lost=1)]))[93]["progress"] == 0
    attack = played("2026-10-01", True, mode="payload", map="fission", attacking_team="blue", push_s=120.0)
    defend = played("2026-10-01", True, mode="payload", map="fission", attacking_team="orange", block_s=30.0)
    r = by_id(evaluate([attack, defend]))
    assert (r[94]["tier"], r[94]["count"], r[95]["tier"], r[95]["count"]) == ("bronze", 1, None, 1)  # Shutout bronze is 2 wins now (2026-11-26)


def test_tiered_achievements():
    """Clean Sweep / Special Delivery (user, 2026-10-31): 1 / 5 / 10 / 25 / 100 games, 2026-11-03: 1 / 6 / 12 / 39 / 156; 2026-11-06:
    four medals (silver dropped): bronze 1, silver 12, gold 39, crown 156; progress 25 % per medal, partial in between; the text
    lists every target (website text is the spec)."""
    from backend.achievements import unlock_threshold

    def sweeps(n):
        return [Game(**{**game(f"2026-10-{1 + i % 28:02d}").__dict__, "team": "blue", "winner": "blue", "rounds_lost": 0})
                for i in range(n)]

    expected = {0: (None, 0.0), 1: (None, 0.125), 2: ("bronze", 0.25), 10: ("bronze", 0.25 + 8 / 18 / 4), 20: ("silver", 0.5),
                25: ("gold", 0.75), 28: ("gold", 0.75 + 3 / 5 / 4), 30: ("crown", 1.0), 40: ("crown", 1.0)}  # 2 / 20 / 25 / 30 (2026-11-27)
    for n, (medal, progress) in expected.items():
        r = by_id(evaluate(sweeps(n)))[93]
        assert (r["tier"], r["count"], r["levels"]) == (medal, n, [2, 20, 25, 30]), n
        assert r["progress"] == pytest.approx(progress, abs=1e-4), n
    rule = next(r for r in RULES if r.id == 93)
    assert "2 bronze, 20 silver, 25 gold, 30 crown" in rule.description
    assert unlock_threshold(rule) == 0.25 and unlock_threshold(next(r for r in RULES if r.id == 69)) == 0.25
    delivery = next(r for r in RULES if r.id == 94)
    assert "Deliver the payload to the end" in delivery.description and delivery.levels == (1, 10, 15, 20)


def test_ladders_with_units_and_periods():
    """Per-game ladders count the best game, units are in the text, short games do not count."""
    r = by_id(evaluate([game(top=24.0), game(top=9.0)]))
    assert (r[23]["tier"], r[23]["count"], r[23]["unit"]) == ("silver", 24.0, " m/s")  # 19 / 24 / 29 / 35 (2026-11-26)
    assert next(rule for rule in RULES if rule.id == 23).levels == (19, 24, 29, 35)
    assert "19 m/s bronze, 24 m/s silver" in next(x for x in RULES if x.id == 23).description


def test_new_activity_challenges():
    days = [game(f"2026-10-{d:02d}") for d in (1, 2, 3, 4, 10)]
    r = by_id(evaluate(days))
    assert r[114]["count"] == 5 and r[115]["count"] == 2  # days, weeks
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
    # Medal Collector counts every challenge at silver or better (more of them since the ladders were retuned on 2026-11-04)
    assert r[126]["levels"] == [5, 25, 65, 98]
    r = by_id(evaluate([won("dyson", f"2026-10-{1 + i % 28:02d}") for i in range(120)]))
    golds = sum(1 for x in r.values() if x["id"] != 126 and (x["count"] >= x["levels"][1] if "levels" in x else x["progress"] >= 1))
    assert golds > 0 and r[126]["count"] == golds  # Medal Collector counts silver-or-better medals of the others
    assert not any(x["group"] == "Gear in one game" for x in r.values())  # the Test Drives are retired (2026-11-26)


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
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        first = api._compute(sessions, (None, None))
        evaluated = []
        real = api.evaluate
        monkeypatch.setattr(api, "evaluate", lambda games: evaluated.append(len(games)) or real(games))
        assert api._compute(sessions, (None, None)) == first and evaluated == []  # nothing changed
        assert api._compute(sessions, ("2030-01-01", None))["rows"] == [] and evaluated == []  # no games in window
        add(client, {"dyson/1.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        again = api._compute(sessions, (None, None))
        assert evaluated == [2, 2, 2, 2]  # all four players (2v2) gained a game
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
    assert (r[129]["tier"], r[129]["count"]) == ("gold", 18) and r[132]["count"] == 18  # 18 Quark-only games in a week (crown is 20)


def test_one_game_challenges_need_enough_players():
    far = {**game("2026-10-01").__dict__, "in_bounds": 1200}  # Lone Echo, never near a teammate (Marathon Bot, Space Statue retired)
    assert by_id(evaluate([Game(**{**far, "enough_players": False})]))[143]["count"] == 0  # fewer than 2 per team
    assert by_id(evaluate([Game(**far)]))[143]["tier"] == "crown"


def test_lone_wolf_uses_its_own_distance():
    base = game("2026-10-01", mate=0).__dict__
    far_from_2_6m_only = Game(**{**base, "in_bounds": 2000, "lone_wolf_near": 400})  # always over 2.6 m, within 10 m for 20 %
    assert by_id(evaluate([far_from_2_6m_only]))[143]["count"] == pytest.approx(80)
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1200})]))[143]["tier"] == "crown"  # exactly 1 minute at 20 Hz
    assert by_id(evaluate([Game(**{**base, "in_bounds": 1199})]))[143]["count"] == 0  # just under: a few seconds of play do not count
    assert "10 m" in next(rule for rule in RULES if rule.id == 143).description  # 3.5 m until 2026-11-28 (user)



def test_lone_wolf_has_no_value_before_the_replay_is_read_again():
    base = game("2026-10-01", mate=0).__dict__
    assert by_id(evaluate([Game(**{**base, "in_bounds": 2000, "lone_wolf_near": None})]))[143]["count"] == 0  # not a false 100 %


def test_seven_day_upside_down_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 49).levels == (9, 12, 20, 27)
    def flipped(day, frames=4000):
        return Game(**{**game(day).__dict__, "upside": frames * 3 // 5, "in_bounds": frames})
    assert by_id(evaluate([flipped("2026-10-01"), flipped("2026-10-02"), flipped("2026-10-03")]))[49]["tier"] == "crown"
    assert by_id(evaluate([flipped("2026-10-01"), flipped("2026-10-02"), flipped("2026-10-03", 3995)]))[49]["count"] == 0
    assert by_id(evaluate([flipped("2026-10-01", 12000), flipped("2026-10-02", 12000)]))[49]["count"] == 0  # two days



def test_seven_day_speed_needs_three_days_and_ten_minutes_in_bounds():
    base = game("2026-10-01").__dict__  # 20 Hz, 4 m/s below
    def fast(frames, day="2026-10-01"):
        return Game(**{**base, "started_at": f"{day}T20:00:00.000", "in_bounds": frames, "speed_sum": 4.0 * frames})
    assert next(rule for rule in RULES if rule.id == 48).levels == (2.25, 2.75, 3.25, 3.65)
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(4000, "2026-10-07")]))[48]["tier"] == "crown"  # exactly 10 minutes, any 3 days of the 7
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(3999, "2026-10-07")]))[48]["count"] == 0
    assert by_id(evaluate([fast(24000)]))[48]["count"] == 0  # one long game
    assert by_id(evaluate([fast(6000), fast(6000)]))[48]["count"] == 0  # several games on one day
    assert by_id(evaluate([fast(6000), fast(6000, "2026-10-03")]))[48]["count"] == 0  # two days
    assert by_id(evaluate([fast(4000), fast(4000, "2026-10-03"), fast(4000, "2026-10-20")]))[48]["count"] == 0  # not in the same 7 days


def test_seven_day_enemy_share_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 47).levels == (9, 11, 13, 15)
    def close(day, frames=4000):
        return Game(**{**game(day).__dict__, "near_enemy": frames // 5, "in_bounds": frames})
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03")]))[47]["tier"] == "crown"  # 20 % for exactly 10 minutes at 20 Hz
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03", 3995)]))[47]["count"] == 0
    assert by_id(evaluate([close("2026-10-01", 12000), close("2026-10-02", 12000)]))[47]["count"] == 0  # two days



def test_seven_day_teammate_share_needs_three_days_and_ten_minutes_in_bounds():
    assert next(rule for rule in RULES if rule.id == 46).levels == (18, 21, 23, 25)
    def close(day, frames=4000):
        return Game(**{**game(day).__dict__, "near_mate": frames * 7 // 25, "in_bounds": frames})
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03")]))[46]["tier"] == "crown"  # 28 % for exactly 10 minutes at 20 Hz
    assert by_id(evaluate([close("2026-10-01"), close("2026-10-02"), close("2026-10-03", 3975)]))[46]["count"] == 0
    assert by_id(evaluate([close("2026-10-01", 12000), close("2026-10-02", 12000)]))[46]["count"] == 0  # two days


def test_one_day_targets():
    levels = {rule.id: rule.levels for rule in RULES}
    assert levels[25] == levels[26] == levels[27] == levels[28] == (3, 5, 7, 9)  # the four maps stay equal
    assert levels[19] == levels[20] == (5, 9, 12, 16) and levels[29] == (10, 20, 25, 30)
    r = by_id(evaluate([game("2026-10-01", map_="surge")] * 9))
    assert r[28]["tier"] == "crown" and "9 crown" in next(rule for rule in RULES if rule.id == 28).description
    assert by_id(evaluate([game("2026-10-01", map_="surge")] * 8))[28]["tier"] == "gold"


def test_impossible_top_medals_were_lowered():
    levels = {rule.id: rule.levels for rule in RULES}
    assert levels[72] == (6, 9, 10, 11) and levels[73] == (2.6, 2.85, 3.1, 3.4) and levels[100] == (40, 125, 150, 225)
    assert levels[150] == (8, 24, 32, 40) and levels[151] == (16, 24, 28, 32)  # doubled again (user, 2026-11-27)


def test_seven_day_map_and_mode_targets():
    levels = {rule.id: rule.levels for rule in RULES}
    assert levels[50] == levels[51] == levels[52] == levels[53] == (4, 8, 12, 18)  # the four maps stay equal
    assert levels[44] == levels[45] == (10, 25, 35, 40)  # the two modes stay equal
    assert levels[54] == (15, 50, 65, 80)
    days = [game(f"2026-10-0{i + 1}", map_="surge") for i in range(6)]
    assert by_id(evaluate(days * 3))[53]["tier"] == "crown"  # 18 games over 6 days
    assert by_id(evaluate(days * 2 + days[:5]))[53]["tier"] == "gold"  # 17
    spread = [game("2026-10-01", map_="surge")] * 9 + [game("2026-10-20", map_="surge")] * 9
    assert by_id(evaluate(spread))[53]["tier"] == "silver"  # 18 games, but only 9 in any 7 days


def test_seven_day_gear_needs_three_days_from_silver():
    assert next(r for r in RULES if r.id == 34).levels == (5, 10, 15, 20)  # 2026-11-26 (was 1 / 6 / 9 / 13)
    one_evening = [game("2026-10-01")] * 20  # 20 Detonator-only games, all on one day
    assert by_id(evaluate(one_evening))[34]["tier"] == "bronze"  # silver and up need games on 3+ days
    two_days = [game("2026-10-01")] * 10 + [game("2026-10-02")] * 10
    assert by_id(evaluate(two_days))[34]["tier"] == "bronze"
    three_days = [game("2026-10-01")] * 10 + [game("2026-10-02")] * 9 + [game("2026-10-07")]  # 3 days, all inside 7 days
    assert by_id(evaluate(three_days))[34]["tier"] == "crown"
    too_wide = [game("2026-10-01")] * 10 + [game("2026-10-02")] * 9 + [game("2026-10-09")]  # the 3rd day is outside the window
    assert by_id(evaluate(too_wide))[34]["tier"] == "bronze"
    assert "Silver+: 3+ different days" in rule_notes(next(r for r in RULES if r.id == 34))


def test_all_gear_shares_one_ladder_per_kind():
    veteran = {r.levels for r in RULES if r.name.endswith(" Veteran") and r.period == "all"}
    assert len(veteran) == 1  # one ladder for every weapon, ordnance and tac mod (set in TUNED_LEVELS on 2026-11-04)
    for period in ("day", "week"):  # one ladder for "only X" in a day / in 7 days (42: Gearhead is about loadouts, not one gear)
        assert len({r.levels for r in RULES if "using only" in r.description and r.period == period and r.id != 42}) == 1
    assert next(r for r in RULES if r.id == 112).levels in veteran  # Overcharged (was Overclocked) is a veteran ladder too


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
    # one ladder at 2 of 4 medals (progress 0.5): silver, 2 medals, nothing completed
    one = [0.0] * len(RULES)
    index = next(i for i, r in enumerate(RULES) if r.id == 7)
    one[index] = 0.5
    facts = achiever_facts(one)
    assert (facts["completed"], facts["medals"], facts["gold_plus"]) == (0, 2, 1) and facts["best_section"] == "In any 24 hours"
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two())) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        top = client.get("/api/leaderboard/achievers").json()  # no minimum of games (user, 2026-11-27)
        assert {r["name"] for r in top} == {"Player", "Other", "Mate", "Rival"}
        assert all(r["total"] == len(COUNTED_RULES) and 0 <= r["completed"] <= len(RULES) and "medals" in r for r in top)  # + George League (user, 2026-11-27)


def test_day_challenges_count_any_24_hours():
    """One Day became any 24 hours (user, 2026-11-28): a session across midnight counts together, two sessions a day apart do not."""
    late = [Game(**{**game().__dict__, "started_at": f"2026-10-28T{h}:00:00.000", "mode": "payload"}) for h in (22, 23)]
    early = [Game(**{**game().__dict__, "started_at": f"2026-10-29T0{h}:00:00.000", "mode": "payload"}) for h in (0, 1, 2)]
    assert by_id(evaluate(late + early))[20]["count"] == 5  # Checkpoint Reached: 22:00 to 02:00 is one stretch
    apart = late + [Game(**{**game().__dict__, "started_at": "2026-10-29T22:00:00.000", "mode": "payload"})]
    assert by_id(evaluate(apart))[20]["count"] == 2  # exactly 24 hours after the first game: a new window
    assert "Best 24 hours" in rule_notes(next(r for r in RULES if r.id == 20)) and "any 24 hours" in next(r for r in RULES if r.id == 20).description


def test_test_drives_are_retired():
    """The 22 "use <item> for 3 minutes in one game" rules were retired (user, 2026-11-26, D63); their ids are never reused."""
    assert not any(r.group == "Gear in one game" for r in RULES)
    assert not {r.id for r in RULES} & (set(range(179, 198)) | {268, 272, 276})



def test_top_players_rank_by_challenges_fully_complete():
    """Top players (user, 2026-11-26): most challenges fully complete first, average progress only breaks ties."""
    from backend.api.leaderboard import _by_complete
    ranking = [(1, 50, 0.9), (2, 40, 0.5), (3, 30, 0.6)]  # (player, games, average progress), as the ranking sorts them
    progress = {1: [1.0, 0.8, 0.9], 2: [1.0, 1.0, 0.0], 3: [1.0, 1.0, 0.2]}
    assert [pid for pid, _, _ in _by_complete(ranking, progress)] == [3, 2, 1]  # 2 complete each: the higher average first


def test_full_lobby_is_a_full_five_a_side_match():
    """Full Lobby on Kronos II (user, 2026-11-26): 5 players on each team for half the match, 4+ minutes; won or not."""
    full = Game(**{**game().__dict__, "full_lobby": True})
    r = by_id(evaluate([full]))[279]
    assert (r["progress"], r["tier"], r["binary"]) == (1.0, "crown", True)
    assert by_id(evaluate([game()]))[279]["tier"] is None  # 3v3 is not full
    assert by_id(evaluate([Game(**{**game(play=200.0).__dict__, "full_lobby": True})]))[279]["progress"] == 0  # under 4 minutes


def test_names_carry_no_category_tag():
    """User, 2026-11-26: the tabs and topic boxes say what kind a challenge is, so no "(Weapon)" / "(Award card)" in names."""
    from backend.combat_achievements import COMBAT_RULES
    names = [r.name for r in RULES + COMBAT_RULES]
    assert not [n for n in names if n.endswith(")")] and len(set(names)) == len(names)
    assert sum(r.award for r in COMBAT_RULES) == 25 and not any(r.award for r in RULES)


def test_period_start_time():
    """A challenge / Mega Prize start can carry a UK time (user, 2026-11-27): games before that minute on the start day
    do not count; a date alone still starts at 00:00, and the end day stays a whole day."""
    from datetime import datetime
    from backend.achievements import in_window
    assert actions.parse_start("2027-01-01") == "2027-01-01"
    assert actions.parse_start(" 2027-01-01 18:00 ") == actions.parse_start("2027-01-01T18:00") == "2027-01-01T18:00"
    for bad in ("18:00", "2027-13-01", "2027-01-01 25:00", "2027-01-01T18:00+01:00"):
        with pytest.raises(actions.AdminError):
            actions.parse_start(bad)
    with pytest.raises(actions.AdminError):
        actions.parse_end("2027-01-01 18:00")  # the end is a whole day
    games = [game("2026-10-28"), game("2026-10-29")]  # both 20:00
    assert len(in_window(games, "2026-10-28", None)) == 2
    assert len(in_window(games, "2026-10-28T19:59", None)) == 2
    assert len(in_window(games, "2026-10-28T20:01", None)) == 1
    assert len(in_window(games, "2026-10-28T20:01", "2026-10-28")) == 0
    at = datetime(2027, 1, 1, 17, 59, 30)
    assert not actions.has_started("2027-01-01T18:00", at) and actions.has_started("2027-01-01", at)
    assert actions.has_started("2027-01-01T18:00", datetime(2027, 1, 1, 18, 0))
    assert actions.window_active(("2027-01-01T18:00", "2027-01-01"), datetime(2027, 1, 1, 23, 59))
    assert not actions.window_active(("2027-01-01T18:00", "2027-01-01"), datetime(2027, 1, 2, 0, 0))


def test_loadouts_not_used_yet_are_listed():
    """I Use All the Loadouts (67, renamed from "5th Loadout when?" by the user, 2026-11-27) lists every loadout not used
    yet (user, same day): per weapon + ordnance pair, the tac mods still to use with it, by display name."""
    from backend.achievements import LOADOUT_RULE_ID, loadout_hints
    games = [game(loadout=("assault", "heal", "det")), game(loadout=("assault", "heal", "det"))]  # 2 x 50 s: used (1 min+)
    games.append(game(loadout=("scout", "heal", "det")))  # 50 s only: not used yet
    hints = loadout_hints(games)
    assert sum(len(x["tacmods"]) for x in hints["untried"]) == 240 - 1
    first = hints["untried"][0]
    assert (first["weapon"], first["ordnance"]) == ("Pulsar", "Detonator") and "Repair Matrix" not in first["tacmods"]
    assert len(first["tacmods"]) == 4 and len(hints["untried"]) == 48  # every pair still has something left
    card = next(r for r in evaluate(games) if r["id"] == LOADOUT_RULE_ID)
    assert card["name"] == "I Use All the Loadouts" and card["untried"] == hints["untried"] and len(card["try_next"]) == 3
