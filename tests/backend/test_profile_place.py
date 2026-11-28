"""Flag and game region on a profile (user, 2026-11-28): picked by the player, or detected from their connection
(Cloudflare's CF-IPCountry) unless they picked one; shown at once, marked as detected."""

import pytest

from backend import guard, regions
from backend.api import profiles
from backend.models import NakamaAccount
from test_discord_preview import discord  # noqa: F401
from test_profiles import avatars  # noqa: F401

SITE = {"X-EchoVR": "1"}


def test_lists_and_region_for_a_country():
    assert {"gb", "us", "jp", "gb-eng"} <= regions.COUNTRIES and not {"xx", "eu", "t1"} & regions.COUNTRIES
    assert regions.clean_country(" GB ") == "gb" and regions.clean_country("") is None
    with pytest.raises(ValueError):
        regions.clean_country("zz")
    with pytest.raises(ValueError):
        regions.clean_region("mars")
    assert [regions.region_for(c, s) for c, s in [("de", None), ("gb-sct", None), ("au", None), ("kr", None), ("sg", None),
                                                   ("us", "TX"), ("us", "ny"), ("ca", "BC"), ("us", None), ("br", None)]] == [
        "europe", "europe", "australia", "japan", "singapore", "us-central", "us-east", "us-west", None, None]


def _client(tmp_path):
    from app_helpers import app_client
    from test_discord_preview import settings
    return app_client(settings(tmp_path))


def _known(client, discord_id):
    with client.app.state.sessionmaker() as db:
        db.add(NakamaAccount(user_id="n1", discord_id=discord_id, username="m", display_name=None, first_seen_at="t", last_seen_at="t"))
        db.commit()


def test_detected_unless_the_player_picked_one(tmp_path, avatars, monkeypatch):
    from test_discord_preview import MEMBER, login
    monkeypatch.setattr(guard, "_from_inside", lambda host: True)  # as through the Cloudflare tunnel
    with _client(tmp_path) as client:
        _known(client, MEMBER)
        login(client, MEMBER)
        client.get("/api/auth/me", headers={"cf-ipcountry": "DE"})
        me = client.get("/api/profiles/me").json()
        assert (me["country"], me["region"], me["place_detected"], me["place_auto"]) == ("de", "europe", True, True)
        assert me["bio"] is None  # detection writes no bio (and no bio date: Edit your Bio stays not done)

        # the player picks one: never overwritten by detection again
        saved = client.post("/api/profiles/me", json={"bio": "hi", "country": "gb-wls", "region": "us-east"}, headers=SITE).json()
        assert (saved["country"], saved["region"], saved["place_detected"], saved["place_auto"]) == ("gb-wls", "us-east", False, False)
        profiles._detected.clear()
        client.get("/api/auth/me", headers={"cf-ipcountry": "JP"})
        assert client.get("/api/profiles/me").json()["country"] == "gb-wls"

        # a save from a page opened before the fields existed changes neither
        client.post("/api/profiles/me", json={"bio": "hello"}, headers=SITE)
        assert client.get("/api/profiles/me").json()["region"] == "us-east"

        # back to automatic: detected again at once, from this request's connection
        auto = client.post("/api/profiles/me", json={"bio": "hello", "place_auto": True}, headers={**SITE, "cf-ipcountry": "AU"}).json()
        assert (auto["country"], auto["region"], auto["place_detected"]) == ("au", "australia", True)

        assert client.post("/api/profiles/me", json={"bio": "x", "country": "zz"}, headers=SITE).status_code == 400


def test_header_not_believed_outside_the_tunnel_or_unknown(tmp_path, avatars, monkeypatch):
    from test_discord_preview import MEMBER, login
    with _client(tmp_path) as client:
        _known(client, MEMBER)
        login(client, MEMBER)
        monkeypatch.setattr(guard, "_from_inside", lambda host: False)  # straight to the port: anyone could send the header
        client.get("/api/auth/me", headers={"cf-ipcountry": "DE"})
        assert client.get("/api/profiles/me").json()["country"] is None
        monkeypatch.setattr(guard, "_from_inside", lambda host: True)
        profiles._detected.clear()
        for unknown in ("XX", "T1"):  # unknown, Tor
            client.get("/api/auth/me", headers={"cf-ipcountry": unknown})
        assert client.get("/api/profiles/me").json()["country"] is None


def test_place_goes_with_the_discord_account_when_linked_and_unlinked(tmp_path):
    from backend import discord_links
    from backend.db import open_db
    from backend.models import DiscordProfile, Player, PlayerProfile
    d = "123456789012345678"
    _, sm = open_db(tmp_path / "p.db", 0)
    with sm() as db:
        db.add(Player(user_id="p1", name="p1", first_seen_at="t", last_seen_at="t"))
        db.add(DiscordProfile(discord_id=d, bio=None, show_avatar=True, updated_at="t", country="fr", region="europe", place_set_by="player"))
        db.commit()
        discord_links.link(db, "p1", d)
        db.commit()
        p = db.get(PlayerProfile, "p1")
        assert (p.country, p.region, p.place_set_by) == ("fr", "europe", "player")
        p.country = "be"
        discord_links.unlink(db, "p1", d, block=False)
        db.commit()
        kept = db.get(DiscordProfile, d)
        assert (kept.country, kept.region, kept.place_set_by) == ("be", "europe", "player")
