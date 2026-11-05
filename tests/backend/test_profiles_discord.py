"""Discord-keyed profiles (user, 2026-11-05): the Discord id comes from the Nakama match list or is a recent replay player's id."""

from sqlalchemy import select

from backend.api import profiles
from backend.models import ArenaPlayer, DiscordProfile, Player
from test_discord_preview import discord  # noqa: F401
from test_profiles import avatars  # noqa: F401


def test_known_ids_and_bio_cleaning(tmp_path):
    from backend.db import open_db
    _, sm = open_db(tmp_path / "t.db", 0)
    d = "1033759231184224368"
    with sm() as db:
        assert not profiles._known_discord(db, d)  # not a lookup for any account
        db.add(ArenaPlayer(user_id="u", username="x", display_name=None, discord_id=d, matches=1, last_match_at="t"))
        db.add(Player(user_id="1346263035425325078", name="N", first_seen_at="t", last_seen_at="t"))
        db.commit()
        assert profiles._known_discord(db, d) and profiles._known_discord(db, "1346263035425325078")
        db.add(DiscordProfile(discord_id=d, bio=profiles.clean_bio("hi\x00 there"), show_avatar=True, updated_at="t"))
        db.commit()
        assert db.scalar(select(DiscordProfile.bio)) == "hi there"


def test_my_profile_is_editable_only_by_the_logged_in_account(tmp_path, avatars):
    from app_helpers import app_client
    from test_discord_preview import MEMBER, NO_ROLE, login, settings
    from backend.models import NakamaAccount
    SITE = {"X-EchoVR": "1"}
    with app_client(settings(tmp_path)) as client:
        assert client.get("/api/profiles/me").status_code == 401  # not logged in
        assert client.post("/api/profiles/me", json={"bio": "x"}, headers=SITE).status_code == 401
        login(client, MEMBER)
        me = client.get("/api/profiles/me").json()
        assert me["known"] is False and me["editable"] is False  # never seen on the match list
        assert client.post("/api/profiles/me", json={"bio": "x"}, headers=SITE).status_code == 404
        with client.app.state.sessionmaker() as db:  # the tracker has now collected this account
            db.add(NakamaAccount(user_id="n1", discord_id=MEMBER, username="m", display_name=None, first_seen_at="t", last_seen_at="t"))
            db.commit()
        saved = client.post("/api/profiles/me", json={"bio": "Hello  there", "show_avatar": False}, headers=SITE).json()
        assert saved["bio"] == "Hello  there" and saved["editable"] and saved["avatar_url"] is None
        assert client.get("/api/profiles/me").json()["bio"] == "Hello  there"
        # public read of the same account works, editing someone else's does not
        assert client.get(f"/api/profiles/discord/{MEMBER}").json()["bio"] == "Hello  there"
        login(client, NO_ROLE)
        assert client.post(f"/api/profiles/discord/{MEMBER}", json={"bio": "mine now"}, headers=SITE).status_code == 403
        assert client.get(f"/api/profiles/discord/{MEMBER}").json()["editable"] is False
        assert client.get("/api/profiles/discord/12").status_code == 400  # not a Discord id


def test_player_profile_shows_the_linked_account_without_the_discord_id(tmp_path, avatars):
    import json
    from app_helpers import app_client
    from test_discord_preview import MEMBER, settings
    from backend.models import NakamaAccount, Player
    with app_client(settings(tmp_path)) as client:
        with client.app.state.sessionmaker() as db:
            db.add(Player(user_id=MEMBER, name="Recent", first_seen_at="t", last_seen_at="t"))
            db.commit()
        assert client.get(f"/api/profiles/{MEMBER}").json()["account"] is None  # nothing linked yet
        with client.app.state.sessionmaker() as db:
            db.add(NakamaAccount(user_id="n1", discord_id=MEMBER, username="m", display_name="Mighty", first_seen_at="t",
                                 last_seen_at="2026-11-05T10:00:00", replay_user_id=MEMBER, link="player_id"))
            db.commit()
        r = client.get(f"/api/profiles/{MEMBER}").json()
        assert r["linked"] and r["account"] == {"name": "Mighty", "last_seen": "2026-11-05T10:00:00"}
        assert MEMBER not in json.dumps(r["account"])  # the Discord id is not shown
