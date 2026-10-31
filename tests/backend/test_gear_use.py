"""Gear use: times each weapon / ordnance / tac mod was picked (no shot counts exist in replays), games used, time share."""

import replay_factory as rf
from app_helpers import add, app_client, make_settings

from backend.gear_use import count_picks


def test_pick_rule():
    changes = [
        {"weapon": "assault", "tacmod": "heal", "ordnance": "det"},
        {"weapon": "", "tacmod": "heal", "ordnance": "det"},  # respawn gap: not a new pick
        {"weapon": "assault", "tacmod": "heal", "ordnance": "det"},
        {"weapon": "blaster", "tacmod": "heal", "ordnance": "stun"},
        {"weapon": "assault", "tacmod": "heal", "ordnance": "stun"},  # back to Pulsar: a second pick
    ]
    picks = count_picks(changes)
    assert picks["weapon"] == {"assault": 2, "blaster": 1}
    assert picks["ordnance"] == {"det": 1, "stun": 1}
    assert picks["tacmod"] == {"heal": 1}


def _frame(weapon: str, ordnance: str = "det") -> dict:
    blue = rf.player(100, "Main") | {"Weapon": weapon, "Ordnance": ordnance}
    return rf.frame(teams=[{"players": [blue]}, {"players": [rf.player(300, "Mate", 1)]}, {}])


def by_code(items):
    return {g["code"]: g for g in items}


def test_match_and_player_pages_show_gear_use(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        weapons = ["assault"] * 4 + [""] * 2 + ["assault"] * 2 + ["blaster"] * 2  # Pulsar 6 frames, Nova 2
        add(c, {"dyson/1.echoreplay": rf.plain(rf.lines_from([_frame(w) for w in weapons])),
                "dyson/2.echoreplay": rf.plain(rf.lines_from([_frame("blaster", "stun")] * 3))})

        matches = {m["replay_id"]: m["id"] for m in c.get("/api/matches").json()["items"]}
        first = c.get(f"/api/matches/{matches[1]}").json()
        main = next(p for p in first["teams"]["blue"] if p["user_id"] == "100")
        weapons_used = by_code(main["gear"]["weapons"])
        assert (weapons_used["assault"]["picks"], weapons_used["blaster"]["picks"]) == (1, 1)
        assert weapons_used["assault"]["share"] == 0.75 and weapons_used["assault"]["name"] == "Pulsar"
        assert "games" not in weapons_used["assault"]  # one match

        profile = c.get("/api/players/100").json()["gear"]
        weapons_all = by_code(profile["weapons"])
        assert (weapons_all["blaster"]["picks"], weapons_all["blaster"]["games"]) == (2, 2)
        assert (weapons_all["assault"]["picks"], weapons_all["assault"]["games"]) == (1, 1)
        assert profile["weapons"][0]["code"] == "assault"  # most time held first (6 frames vs 5)
        assert {g["code"]: g["games"] for g in profile["ordnances"]} == {"det": 1, "stun": 1}
        assert by_code(profile["tacmods"])["heal"]["picks"] == 2  # once per match
