"""Pinned challenges (user, 2026-11-27): up to 3, set by the player's own Discord account, seen by everyone, removed by
themselves once completed (api/pins.py)."""

from app_helpers import app_client
from test_discord_preview import MEMBER, NO_ROLE, discord, login, settings  # noqa: F401 (fixture)
from test_profiles import avatars  # noqa: F401 (fixture)

from backend import profile_achievements as pa
from backend.achievements import RULES
from backend.models import ChallengePin, NakamaAccount, Player, PlayerProfile

SITE = {"X-EchoVR": "1"}
REPLAY_ID = "OVR-ORG-123456"
A, B, C, D = (r.id for r in RULES[:4])


def setup(client):
    with client.app.state.sessionmaker() as db:
        db.add(Player(user_id=REPLAY_ID, name="Mighty", first_seen_at="t", last_seen_at="t"))
        db.add(NakamaAccount(user_id="n1", discord_id=MEMBER, username="mighty", display_name="Mighty", first_seen_at="t",
                             last_seen_at="t", replay_user_id=REPLAY_ID))
        db.commit()


def pin(client, rule_id, pinned=True, headers=SITE):
    return client.post(f"/api/profiles/{REPLAY_ID}/pins", json={"id": rule_id, "pinned": pinned}, headers=headers)


def test_the_owner_pins_up_to_three_and_everyone_sees_them(tmp_path, discord, avatars):
    with app_client(settings(tmp_path)) as client:
        setup(client)
        login(client, MEMBER)
        assert client.get(f"/api/profiles/{REPLAY_ID}/pins").json() == {"pins": [], "max": 3, "editable": True}
        for rule_id in (A, B, C):
            assert pin(client, rule_id).status_code == 200
        assert pin(client, A).json()["pins"] == [A, B, C]  # pinning again changes nothing
        r = pin(client, D)
        assert r.status_code == 409 and r.json()["error_code"] == "pins_full"
        assert pin(client, B, pinned=False).json()["pins"] == [A, C]
        assert pin(client, 999999).status_code == 404
        assert pin(client, D, headers={}).status_code == 405  # no X-EchoVR header: the read-only rule
        r = client.get(f"/api/profiles/{REPLAY_ID}/pins")
        assert "no-store" in r.headers["cache-control"]  # editable is per visitor

        client.cookies.clear()
        login(client, NO_ROLE)  # someone else: may not change them
        assert pin(client, D).status_code in (403, 404)  # 404 coming_soon: without the preview role challenges stay hidden


def test_another_discord_account_cannot_pin(tmp_path, discord, avatars):
    with app_client(settings(tmp_path)) as client:
        setup(client)
        with client.app.state.sessionmaker() as db:
            db.add(PlayerProfile(user_id="p2", discord_id="555555555555555555", bio=None, show_avatar=True, linked_at="t", updated_at="t"))
            db.add(Player(user_id="p2", name="Other", first_seen_at="t", last_seen_at="t"))
            db.commit()
        login(client, MEMBER)
        r = client.post("/api/profiles/p2/pins", json={"id": A, "pinned": True}, headers=SITE)
        assert r.status_code == 403 and r.json()["error_code"] == "not_your_profile"
        assert client.get("/api/profiles/p2/pins").json() == {"pins": [], "max": 3, "editable": False}


def test_a_completed_pin_removes_itself(tmp_path, discord, avatars):
    with app_client(settings(tmp_path)) as client:
        setup(client)
        login(client, MEMBER)
        pin(client, A)
        pin(client, pa.BIO_RULE.id)
        with client.app.state.sessionmaker() as db:  # the bio Special is complete once the page has a bio
            assert [p.achievement_id for p in db.query(ChallengePin)] == [A, pa.BIO_RULE.id]
        assert client.post("/api/profiles/me", json={"bio": "Pinning things", "show_avatar": True}, headers=SITE).status_code == 200
        assert client.get(f"/api/players/{REPLAY_ID}/achievements").status_code == 200  # working them out unpins it
        assert client.get(f"/api/profiles/{REPLAY_ID}/pins").json()["pins"] == [A]
