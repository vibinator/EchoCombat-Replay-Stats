from datetime import date

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings

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
    assert ids == list(range(5, 101)) and len(set(ids)) == 96  # 75 original + 21 new (80-100)
    assert [r.id for r in RULES if r.new] == list(range(80, 101))
    assert icon_file(next(r for r in RULES if r.id == 7)) == "comet_daily.png"
    assert icon_file(next(r for r in RULES if r.id == 32)) == "comet_weekly.png"
    assert icon_file(next(r for r in RULES if r.id == 57)) == "comet.png"


def test_tiers():
    assert [tier(p) for p in (0.1, 0.25, 0.5, 0.8, 1.0)] == [None, "white", "bronze", "silver", "gold"]


def test_daily_only_weapon_takes_best_day():
    games = [game("2026-10-27")] * 6 + [game("2026-10-28")] * 15 + [game("2026-10-28", loadout=("assault", "heal", "det"))]
    r = by_id(evaluate(games))
    assert r[7]["progress"] == 1.0 and r[7]["tier"] == "gold"  # One with the Comet: 15 Comet-only games on the 28th
    assert r[5]["progress"] == pytest.approx(1 / 15, abs=1e-4)  # Pulsar only once


def test_weekly_groups_by_calendar_week():
    # Mon 26 Oct - Sun 1 Nov 2026 is one week; 2 Nov starts the next
    games = [game(d) for d in ("2026-10-26", "2026-11-01")] + [game("2026-11-02")]
    r = by_id(evaluate(games))
    assert r[50]["progress"] == pytest.approx(2 / 8)  # Frame-Drop Hell: 8 Dyson games in a week


def test_per_game_rules_ignore_short_appearances():
    r = by_id(evaluate([game(deaths=0, play=30.0)]))
    assert r[18]["progress"] == 0.0
    r = by_id(evaluate([game(deaths=3)]))
    assert r[18]["progress"] == 1.0 and r[18]["estimated"]


def test_all_time_and_overall():
    games = [game(deaths=10) for _ in range(100)]
    r = by_id(evaluate(games))
    assert r[68]["progress"] == pytest.approx(1.0)  # 1000 deaths
    assert r[59]["progress"] == 1.0  # 100 games with Detonator (ordnance id 59)
    assert r[67]["progress"] == pytest.approx(1 / 64, abs=1e-4)  # one loadout combination
    assert 0 < overall(list(r.values())) < 1


def test_old_replays_without_loadouts():
    r = by_id(evaluate([game(loadout=None)]))
    assert r[7]["progress"] == 0 and r[17]["progress"] == 0


def test_api_and_leaderboard(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        a = client.get(f"/api/players/{BLUE}/achievements").json()
        assert a["total"] == 96 and len(a["items"]) == 96 and 0 <= a["overall"] <= 1
        assert client.get("/api/players/nobody/achievements").status_code == 404
        assert len(client.get("/api/achievements").json()) == 96
        board = client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1}).json()
        assert {r["name"] for r in board["items"]} == {"Player", "Other"}
        assert board["label"] == "Achievements (overall %)"


def test_logic_follows_the_text():
    """Every condition is in the description (user, 2026-10-30)."""
    text = {r.id: r.description for r in RULES}
    assert "(3+ minutes)" in text[18] and "(3+ minutes)" in text[21] and "50+ games" in text[73]
    # 3+ minutes: a short game does not count, even with 0 deaths
    assert by_id(evaluate([game(deaths=0, play=60.0)]))[18]["progress"] == 0
    assert by_id(evaluate([game(deaths=3)]))[18]["progress"] == 1.0
    # Pew Pew Proof: "fewer than 5" -> an average of exactly 5 is not enough
    week = [game(f"2026-10-{d:02d}", deaths=5) for d in (26, 27, 28) for _ in range(9)]
    assert by_id(evaluate(week))[43]["progress"] < 1
    week[0] = game("2026-10-26", deaths=4)
    assert by_id(evaluate(week))[43]["progress"] == 1.0


def test_average_unlock_date_is_when_first_reached():
    from backend.achievements import unlock_dates

    # Inverted 4%+ over 50+ games: reached on day 2 (games 1-50 all inverted), then diluted but still above 4%
    games = [game("2026-10-01", upside=500)] * 25 + [game("2026-10-02", upside=500)] * 25 + [game("2026-10-20")] * 100
    assert by_id(evaluate(games))[74]["progress"] == 1.0
    assert unlock_dates(games)[74] == "2026-10-02"


def test_teammate_proximity_targets():
    """Tech Support: 22% over a week; Robot Wrecking Squad: 13% all-time over 50+ games (user, 2026-10-30)."""
    r = by_id(evaluate([game(mate=220)] * 5))
    assert r[46]["progress"] == 1.0 and r[71]["progress"] < 1  # 5 games: the all-time one needs 50
    r = by_id(evaluate([game(mate=210)] * 5))
    assert r[46]["progress"] < 1
    assert by_id(evaluate([game(mate=130)] * 50))[71]["progress"] == 1.0
    assert by_id(evaluate([game(mate=120)] * 50))[71]["progress"] < 1


def test_new_gear_challenges():
    starburst = [game(loadout=("rifle", "heal", "loc"))] * 25
    r = by_id(evaluate(starburst))
    assert r[80]["progress"] == 1.0 and r[84]["progress"] == 1.0 and r[80]["new"]
    assert r[86]["progress"] == 0.25  # 1 of the 4 unreleased weapons
    one_game = Game(**{**game().__dict__, "loadouts": {("assault", "heal", "det"): 250, ("blaster", "sensor", "stun"): 250,
                                                      ("scout", "shield", "arc"): 250, ("rocket", "wraith", "burst"): 250}})
    r = by_id(evaluate([one_game]))
    assert r[87]["progress"] == r[88]["progress"] == r[89]["progress"] == 1.0


def test_new_result_challenges():
    def played(day, won, **kw):
        return Game(**{**game(day).__dict__, "team": "blue", "winner": "blue" if won else "orange", **kw})

    streak = [played(f"2026-10-{d:02d}", True) for d in range(1, 5)]
    streak.insert(2, Game(**{**game("2026-10-02").__dict__, "team": "blue", "winner": None}))  # no result: skipped
    assert by_id(evaluate(streak))[90]["progress"] == pytest.approx(4 / 5)
    streak.append(played("2026-10-05", True))
    assert by_id(evaluate(streak))[90]["progress"] == 1.0
    assert by_id(evaluate(streak + [played("2026-10-06", False)]))[90]["progress"] == 1.0  # best run kept

    assert by_id(evaluate([played("2026-10-01", True, rounds_lost=0)]))[93]["progress"] == 1.0
    assert by_id(evaluate([played("2026-10-01", True, rounds_lost=1)]))[93]["progress"] == 0
    attack = played("2026-10-01", True, mode="payload", map="fission", attacking_team="blue", push_s=200.0)
    defend = played("2026-10-01", True, mode="payload", map="fission", attacking_team="orange", block_s=30.0)
    r = by_id(evaluate([attack, defend]))
    assert (r[94]["progress"], r[95]["progress"], r[96]["progress"]) == (1.0, 1.0, 1.0)
    assert r[97]["progress"] == 0.5 and r[96]["estimated"]


def test_hex_gear_codes_are_normalised():
    from parser.frames import gear_code

    assert gear_code("0xE32DC7C9DA8051A4") == "scout" and gear_code("0xe32dc7c9da8051a4") == "scout"
    assert gear_code("rifle") == "rifle" and gear_code(None) == "" and gear_code("0xDEADBEEF") == "0xDEADBEEF"
