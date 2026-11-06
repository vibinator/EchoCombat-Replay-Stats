"""Small Discord pictures for the name lists (user, 2026-11-06): GET /api/avatars and the extra Players-list fields."""

from app_helpers import app_client, make_settings

from backend import discord_names
from backend.models import DiscordProfile, NakamaAccount, Player, PlayerAlias, PlayerProfile

SITE = {"X-EchoVR": "1"}
DISCORD_A = "111111111111111111"
DISCORD_B = "222222222222222222"
DISCORD_C = "333333333333333333"
DISCORD_D = "444444444444444444"


def _setup(client, monkeypatch):
    monkeypatch.setattr(discord_names, "_by_id", {DISCORD_A: "aaa", DISCORD_B: "bbb", DISCORD_C: "ccc", DISCORD_D: "ddd"})
    monkeypatch.setattr(discord_names, "refresh_soon", lambda settings: None)
    with client.app.state.sessionmaker() as db:
        for uid in ("plain", "linked", "hidden", "seen", "merged", "nodiscord", DISCORD_A):
            db.add(Player(user_id=uid, name=uid, first_seen_at="2026-11-01T00:00:00", last_seen_at="2026-11-01T00:00:00"))
        db.add(PlayerProfile(user_id="linked", discord_id=DISCORD_B, show_avatar=True, linked_at="t", updated_at="t"))
        db.add(PlayerProfile(user_id="hidden", discord_id=DISCORD_C, show_avatar=False, linked_at="t", updated_at="t"))
        db.add(NakamaAccount(user_id="n1", discord_id=DISCORD_D, username="d", first_seen_at="t", last_seen_at="t", replay_user_id="seen"))
        db.add(PlayerAlias(alias_user_id="merged", main_user_id="linked", created_at="t"))
        db.commit()


def test_avatars_follow_the_players_own_choice(tmp_path, monkeypatch):
    with app_client(make_settings(tmp_path)) as client:
        _setup(client, monkeypatch)
        ids = ["plain", "linked", "hidden", "seen", "merged", "nodiscord", DISCORD_A, "unknown"]
        r = client.get("/api/avatars", params={"ids": ",".join(ids)}, headers=SITE)
        assert r.status_code == 200 and "private" in r.headers["cache-control"]
        got = r.json()
        assert got["linked"] == f"https://cdn.discordapp.com/avatars/{DISCORD_B}/bbb.png?size=64"  # the bot link
        assert got["seen"].startswith(f"https://cdn.discordapp.com/avatars/{DISCORD_D}/")  # an Echo account seen on the match list
        assert got[DISCORD_A].startswith(f"https://cdn.discordapp.com/avatars/{DISCORD_A}/")  # the player id IS the Discord id
        assert got["merged"] == got["linked"]  # a merged id shows its main player's picture
        assert "hidden" not in got  # show_avatar off: never listed
        assert not {"plain", "nodiscord", "unknown"} & set(got)  # nobody to ask / not on the server


def test_discord_profile_choice_hides_the_picture_at_once(tmp_path, monkeypatch):
    with app_client(make_settings(tmp_path)) as client:
        _setup(client, monkeypatch)
        assert DISCORD_A in client.get("/api/avatars", params={"ids": DISCORD_A}, headers=SITE).json()
        with client.app.state.sessionmaker() as db:
            db.add(DiscordProfile(discord_id=DISCORD_A, show_avatar=False, updated_at="t"))
            db.commit()
        assert client.get("/api/avatars", params={"ids": DISCORD_A}, headers=SITE).json() == {}  # not kept in any shared cache


def test_avatars_limits_and_no_member_list(tmp_path, monkeypatch):
    with app_client(make_settings(tmp_path)) as client:
        _setup(client, monkeypatch)
        many = ",".join(f"x{i}" for i in range(500)) + f",{DISCORD_A}"
        assert client.get("/api/avatars", params={"ids": many}, headers=SITE).json() == {}  # only the first 100 ids are looked at
        assert client.get("/api/avatars", headers=SITE).json() == {}
        monkeypatch.setattr(discord_names, "_by_id", {})  # member list not read yet / no bot token: no pictures, no error
        assert client.get("/api/avatars", params={"ids": DISCORD_A}, headers=SITE).json() == {}


def test_players_list_has_hours_and_favourite_map(tmp_path):
    import replay_factory as rf
    from app_helpers import add

    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        items = client.get("/api/players", headers=SITE).json()["items"]
        assert items and all("hours_played" in p and "favourite_map" in p for p in items)
        top = max(items, key=lambda p: p["games"])
        assert top["favourite_map"] == "dyson" and top["hours_played"] >= 0
        assert not any("wins" in p or "win_rate" in p for p in items)  # win / loss can be hidden by the site: not in this list
