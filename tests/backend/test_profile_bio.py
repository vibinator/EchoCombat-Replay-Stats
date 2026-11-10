"""A bio written on My profile shows on the player's own page (user, 2026-11-10: "it doesn't show up on their profile page").
The Discord account is known only through the Echo account seen on the match list (no bot link, player id is not the
Discord id): the bio was saved under the Discord id, but the player page only looked at bot links."""

from app_helpers import app_client
from test_discord_preview import MEMBER, NO_ROLE, discord, login, settings  # noqa: F401 (fixture)
from test_profiles import avatars  # noqa: F401 (fixture)

from backend.models import NakamaAccount, Player

SITE = {"X-EchoVR": "1"}
REPLAY_ID = "OVR-ORG-123456"  # an older replay player id: not the Discord id


def setup(client):
    with client.app.state.sessionmaker() as db:
        db.add(Player(user_id=REPLAY_ID, name="Mighty", first_seen_at="t", last_seen_at="t"))
        db.add(NakamaAccount(user_id="n1", discord_id=MEMBER, username="mighty", display_name="Mighty", first_seen_at="t",
                             last_seen_at="t", replay_user_id=REPLAY_ID))
        db.commit()


def test_bio_from_my_profile_shows_on_the_player_page(tmp_path, avatars):
    with app_client(settings(tmp_path)) as client:
        setup(client)
        login(client, MEMBER)
        assert client.post("/api/profiles/me", json={"bio": "I play support", "show_avatar": True}, headers=SITE).status_code == 200
        assert client.get("/api/profiles/me").json()["user_id"] == REPLAY_ID  # My profile knows its player page

        client.cookies.clear()  # anybody looking at the player page
        page = client.get(f"/api/profiles/{REPLAY_ID}").json()
        assert page["bio"] == "I play support" and page["linked"] is True and page["editable"] is False


def test_the_owner_can_edit_the_bio_on_the_player_page(tmp_path, avatars):
    with app_client(settings(tmp_path)) as client:
        setup(client)
        login(client, MEMBER)
        page = client.get(f"/api/profiles/{REPLAY_ID}").json()
        assert page["editable"] is True  # the owner sees the editor on their player page
        r = client.post(f"/api/profiles/{REPLAY_ID}", json={"bio": "Edited here", "show_avatar": True}, headers=SITE)
        assert r.status_code == 200 and r.json()["bio"] == "Edited here"
        assert client.get("/api/profiles/me").json()["bio"] == "Edited here"  # one bio, both pages

        client.cookies.clear()
        login(client, NO_ROLE)  # someone else: refused
        assert client.post(f"/api/profiles/{REPLAY_ID}", json={"bio": "hacked"}, headers=SITE).status_code == 403
        assert client.get(f"/api/profiles/{REPLAY_ID}").json()["bio"] == "Edited here"
