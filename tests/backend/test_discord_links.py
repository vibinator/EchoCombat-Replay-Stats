"""Unlink / link Discord accounts by hand (user, 2026-11-25): an admin's correction overrules every automatic link."""

import admin_console as console
import pytest
from app_helpers import app_client
from sqlalchemy import select
from test_discord_preview import MEMBER, NO_ROLE, login, settings
from test_profiles import BOT, SECRET, avatars, discord  # noqa: F401 (fixtures)

from backend import discord_links, discord_names
from backend.arena import Tracker
from backend.db import PRESERVED_TABLES
from backend.models import DiscordLinkBlock, NakamaAccount, Player, PlayerAlias, PlayerProfile

SITE = {"X-EchoVR": "1"}
OTHER = "987654321098765432"


@pytest.fixture
def client(tmp_path, avatars):  # noqa: F811
    with app_client(settings(tmp_path, bot_link_secret=SECRET)) as c:
        yield c


def players(client, *ids, **names):
    with client.app.state.sessionmaker() as db:
        for u in ids:
            db.add(Player(user_id=u, name=names.get(u, f"name-{u}"), first_seen_at="2026-11-01T00:00:00", last_seen_at="2026-11-01T00:00:00"))
        db.commit()


def seen(client, uid, discord_id, replay=None, link=None):
    with client.app.state.sessionmaker() as db:
        db.add(NakamaAccount(user_id=uid, discord_id=discord_id, username=f"echo-{uid}", first_seen_at="t", last_seen_at="t",
                             replay_user_id=replay, link=link))
        db.commit()


def account_of(client, uid):
    with client.app.state.sessionmaker() as db:
        a = db.get(NakamaAccount, uid)
        return a.replay_user_id, a.link


def test_unlink_holds_when_the_player_id_is_the_discord_id(client, monkeypatch):
    monkeypatch.setattr(discord_names, "_by_id", {MEMBER: "aaa"})
    sm = client.app.state.sessionmaker
    players(client, MEMBER)
    seen(client, "n1", MEMBER, MEMBER, "player_id")
    login(client, MEMBER)
    assert client.get(f"/api/profiles/{MEMBER}").json()["editable"]
    assert MEMBER in client.get("/api/avatars", params={"ids": MEMBER}).json()
    console.cmd_unlink_profile(sm, MEMBER, yes=True)
    p = client.get(f"/api/profiles/{MEMBER}").json()
    assert not p["linked"] and not p["editable"] and p["account"] is None and p["avatar_url"] is None
    assert client.get("/api/avatars", params={"ids": MEMBER}).json() == {}
    assert client.post(f"/api/profiles/{MEMBER}", json={"bio": "x"}, headers=SITE).status_code == 403
    assert account_of(client, "n1") == (None, None)
    with sm() as db:  # the match list does not bring it back
        acc = db.get(NakamaAccount, "n1")
        Tracker._link(db, acc)
        assert acc.replay_user_id is None
    assert client.get("/api/profiles/me").json()["user_id"] is None
    # nor does the bot, until an admin links them again
    body = {"discord_id": MEMBER, "user_id": MEMBER}
    r = client.post("/api/bot/link", json=body, headers=BOT)
    assert r.status_code == 409 and "link_blocked" in r.text
    console.cmd_link_profile(sm, MEMBER, MEMBER, yes=True)
    assert client.get(f"/api/profiles/{MEMBER}").json()["editable"]
    assert account_of(client, "n1") == (MEMBER, "profile")
    assert client.post("/api/bot/link", json=body, headers=BOT).json()["changed"] is False


def test_moving_an_account_to_the_right_player(client):
    """The account's own-id player and its Echo account both follow the hand-made link; the bio moves along."""
    sm = client.app.state.sessionmaker
    players(client, MEMBER, "wrong", "right")
    seen(client, "n1", MEMBER)
    console.cmd_link_profile(sm, "wrong", MEMBER, yes=True)
    login(client, MEMBER)
    client.post("/api/profiles/wrong", json={"bio": "mine", "show_avatar": False}, headers=SITE)
    console.cmd_link_profile(sm, "right", MEMBER, yes=True)
    right = client.get("/api/profiles/right").json()
    assert right["editable"] and right["bio"] == "mine" and right["show_avatar"] is False
    for other in ("wrong", MEMBER):  # only one player shows it, also not the player with this very id
        p = client.get(f"/api/profiles/{other}").json()
        assert not p["linked"] and not p["editable"] and p["bio"] is None and p["account"] is None, other
    assert account_of(client, "n1") == ("right", "profile")
    assert client.get("/api/profiles/me").json()["user_id"] == "right"
    console.cmd_unlink_profile(sm, "right", yes=True)
    assert client.get("/api/profiles/me").json()["bio"] == "mine"  # stays with the account ...
    assert client.get("/api/profiles/right").json()["bio"] is None  # ... not with the player
    assert account_of(client, "n1") == (MEMBER, "player_id")  # its own id takes over again


def test_a_player_linked_to_another_account_is_no_longer_its_own_id(client):
    sm = client.app.state.sessionmaker
    players(client, MEMBER)
    seen(client, "n1", MEMBER, MEMBER, "player_id")
    seen(client, "n2", OTHER)
    console.cmd_link_profile(sm, MEMBER, OTHER, yes=True)
    assert account_of(client, "n1") == (None, None) and account_of(client, "n2") == (MEMBER, "profile")
    login(client, MEMBER)
    assert not client.get(f"/api/profiles/{MEMBER}").json()["editable"]
    assert client.get("/api/profiles/me").json()["user_id"] is None


def test_unlink_a_seen_account_and_a_merged_players_link(client):
    sm = client.app.state.sessionmaker
    players(client, "seen", "main", "alt")
    seen(client, "n1", OTHER, "seen")
    console.cmd_unlink_profile(sm, OTHER, yes=True)
    assert account_of(client, "n1") == (None, None)
    with pytest.raises(console.ConsoleError):
        console.cmd_unlink_profile(sm, "seen", yes=True)  # nothing left
    # linked first, merged later: the link counts for the main player and can be taken off there
    console.cmd_link_profile(sm, "alt", NO_ROLE, yes=True)
    with sm() as db:
        db.add(PlayerAlias(alias_user_id="alt", main_user_id="main", created_at="t"))
        db.commit()
    assert client.get("/api/profiles/main").json()["linked"]
    assert client.post("/api/bot/lookup", json={"user_id": "main"}, headers=BOT).json()["discord_id"] == NO_ROLE
    console.cmd_unlink_profile(sm, "main", yes=True)
    assert not client.get("/api/profiles/main").json()["linked"]
    with sm() as db:
        assert db.scalar(select(PlayerProfile)) is None and discord_links.blocks_of(db, "main") == [NO_ROLE]


def test_the_bots_unlink_blocks_nothing(client):
    players(client, "p")
    client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": "p"}, headers=BOT)
    assert client.post("/api/bot/unlink", json={"discord_id": MEMBER}, headers=BOT).json() == {"removed": True}
    assert client.post("/api/bot/unlink", json={"discord_id": MEMBER}, headers=BOT).json() == {"removed": False}
    assert client.post("/api/bot/link", json={"discord_id": MEMBER, "user_id": "p"}, headers=BOT).json()["changed"]


def test_console_page_shows_unlinks_and_links(client, monkeypatch):
    players(client, "p1", "p2", p1="Alpha", p2="Beta")
    monkeypatch.setattr(discord_names, "_by_name", {"beta": (OTHER, "bbb")})
    monkeypatch.setattr(discord_names, "_by_id", {OTHER: "bbb"})
    monkeypatch.setattr(discord_names, "refresh_soon", lambda s: None)
    url = "/api/admin/console"
    login(client, NO_ROLE)
    assert client.get(f"{url}/players", params={"q": "Alpha"}).status_code == 403
    assert client.post(f"{url}/link-profile", json={"player": "p1", "discord_id": OTHER}, headers=SITE).status_code == 403
    login(client, MEMBER)

    def find(q):
        return client.get(f"{url}/players", params={"q": q}).json()

    def run(command, **args):
        r = client.post(f"{url}/{command}", json=args, headers=SITE).json()
        assert r["ok"], r
        return r["output"]

    assert find("Alpha")[0]["discord"] is None
    beta = find("Beta")[0]["discord"]
    assert (beta["id"], beta["how"]) == (OTHER, "name")
    assert client.get("/api/profiles/p2").json()["avatar_url"]
    assert "p2" in client.get("/api/avatars", params={"ids": "p2"}).json()
    run("unlink-profile", player="p2", discord_id=OTHER)  # a wrong picture by name
    assert client.get("/api/profiles/p2").json()["avatar_url"] is None
    assert "p2" not in client.get("/api/avatars", params={"ids": "p2"}).json()
    row = find("Beta")[0]
    assert row["discord"] is None and [d["id"] for d in row["discord_unlinked"]] == [OTHER]
    assert "Linked" in run("link-profile", player="p1", discord_id=OTHER)
    assert [p["user_id"] for p in find(OTHER)] == ["p1"]  # found by the Discord id
    assert find("Alpha")[0]["discord"]["how"] == "profile"
    run("unlink-profile", player="p1")
    assert find("Alpha")[0]["discord"] is None
    run("link-profile", player="p1", discord_id=OTHER)  # "Link again"
    assert find("Alpha")[0]["discord_unlinked"] == [] and find("Alpha")[0]["discord"]["id"] == OTHER
    report = run("profile-links")
    assert "Unlinked by hand: 1" in report and "Beta" in report
    log = client.get(f"{url}/log", params={"q": "unlink-profile"}).json()
    assert len(log) == 2 and log[0]["who_id"] == MEMBER
    assert not client.post(f"{url}/unlink-profile", json={"player": "p1", "discord_id": "12"}, headers=SITE).json()["ok"]


def test_blocks_survive_a_rebuild():
    assert DiscordLinkBlock.__tablename__ in PRESERVED_TABLES
