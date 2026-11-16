"""Load-time work of 2026-11-16: combat answers kept like the replay ones, the quick JSON reply, the start-up warm-up of
the Matches / Leaderboard first screens, and the files the pages now load from the site itself."""

import json

import pytest
from app_helpers import app_client, make_settings

from backend import cache, combat, guard
from backend.api import overview
from backend.stats.maps import minimap_url
from test_combat import SESSION, SESSION_2, player, put, report


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path, combat_source_dir=tmp_path / "recorder")


def sync(client):
    state = client.app.state
    return combat.sync_once(state.sessionmaker, state.settings, combat.CombatState())


def test_combat_answers_are_kept_and_follow_new_reports(settings):
    put(settings, f"{SESSION}.json", report())
    with app_client(settings) as client:
        sync(client)
        first = client.get("/api/combat/leaderboard", params={"min_games": 1})
        again = client.get("/api/combat/leaderboard", params={"min_games": 1})
        assert (first.headers["x-echovr-cache"], again.headers["x-echovr-cache"]) == ("MISS", "HIT")
        assert first.json()["total"] == 1 and first.headers["etag"] == again.headers["etag"]
        unchanged = client.get("/api/combat/leaderboard", params={"min_games": 1}, headers={"If-None-Match": first.headers["etag"]})
        assert unchanged.status_code == 304
        # another report: the kept answers are out of date at once (tests rebuild before answering)
        put(settings, f"{SESSION_2}.json", report(session=SESSION_2, started="2026-11-05T17:54:16",
                                                   players=[player(user_id="77", name="Other", kills=9)]))
        sync(client)
        cache._stamps.clear()
        from backend.api import combat as combat_api
        combat_api._stamps.clear()  # the stamp is re-read at most every 2 s
        assert client.get("/api/combat/leaderboard", params={"min_games": 1}).json()["total"] == 2
        assert client.get("/api/combat/summary").json()["matches"] == 2
        assert client.get("/api/combat/matches/" + "0" * 8 + "-0000-0000-0000-" + "0" * 12).status_code == 404  # never kept


def test_json_reply_has_an_etag_and_answers_304():
    from starlette.requests import Request

    def ask(headers=()):
        return cache.json_reply(Request({"type": "http", "headers": list(headers)}), {"a": [1, 2], 3: "x"})

    first = ask()
    assert json.loads(first.body) == {"a": [1, 2], "3": "x"} and first.headers["etag"].startswith('W/"')
    assert ask([(b"if-none-match", first.headers["etag"].encode())]).status_code == 304


def test_warm_fills_the_first_screens(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        overview.warm(client.app)
        kept = {key[0] for key in client.app.state.response_cache.entries}
        assert {"overview", "matches", "matches-summary", "leaderboard-overview"} <= kept
        hit = client.get("/api/matches", params={"with_players": "true", "limit": 24, "offset": 0})
        assert hit.headers["x-echovr-cache"] == "HIT" and json.loads(hit.content)["total"] == 0


def test_fonts_and_pictures_come_from_the_site_itself():
    assert "googleapis" not in guard.CONTENT_SECURITY_POLICY and "gstatic" not in guard.CONTENT_SECURITY_POLICY
    assert "font-src 'self'" in guard.CONTENT_SECURITY_POLICY
    assert minimap_url("dyson") == "/minimaps/dyson.webp" and minimap_url("fission") == "/minimaps/fission.webp?v=2"


def test_response_cache_size_is_a_setting(tmp_path):
    with app_client(make_settings(tmp_path, response_cache_mb=3)) as client:
        client.get("/api/overview")
        assert client.app.state.response_cache.max_bytes == 3 * 1024 * 1024
