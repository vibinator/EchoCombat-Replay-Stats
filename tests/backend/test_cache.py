"""Answer caches and who may keep a copy (D53): ETag / 304, stale-while-revalidate, cache headers per kind of answer."""

import time
from types import SimpleNamespace

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings
from starlette.datastructures import MutableHeaders

from backend import admin_actions as actions
from backend import cache
from backend.middleware import _static_cache

BLUE = str(rf.BIG_USER_ID)


def match_file(n: int = 20) -> dict[str, bytes]:
    return {f"dyson/{time.monotonic_ns()}.echoreplay": rf.plain(rf.lines(n, blue_round_score=1))}


def test_answers_carry_an_etag_and_repeat_as_304(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, match_file())
        first = client.get("/api/overview")
        assert first.status_code == 200 and first.json()["matches"] == 1
        etag = first.headers["etag"]
        assert etag.startswith('W/"') and first.headers["x-echovr-cache"] == "MISS"
        assert client.get("/api/overview").headers["x-echovr-cache"] == "HIT"
        for sent in (etag, etag.removeprefix("W/"), f'"other", {etag}', "*"):  # weak comparison, lists, any
            again = client.get("/api/overview", headers={"If-None-Match": sent})
            assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag, sent
        assert client.get("/api/overview", headers={"If-None-Match": '"other"'}).status_code == 200
        plain = client.get("/api/overview", headers={"Accept-Encoding": "identity"})
        assert "content-encoding" not in plain.headers and plain.json() == first.json()
        add(client, match_file())  # new data: a new answer, a new tag (always fresh in the tests)
        changed = client.get("/api/overview", headers={"If-None-Match": etag})
        assert changed.status_code == 200 and changed.json()["matches"] == 2 and changed.headers["etag"] != etag


def test_out_of_date_answer_is_sent_at_once_and_rebuilt_in_the_background(tmp_path):
    with app_client(make_settings(tmp_path, cache_refresh_s=0.3)) as client:
        add(client, match_file())
        assert client.get("/api/overview").json()["matches"] == 1
        add(client, match_file())
        young = client.get("/api/overview")  # younger than the refresh interval: kept as it is
        assert young.json()["matches"] == 1 and young.headers["x-echovr-cache"] == "HIT"
        time.sleep(0.35)
        stale = client.get("/api/overview")  # old enough: still sent at once, a rebuild starts
        assert stale.json()["matches"] == 1 and stale.headers["x-echovr-cache"] == "STALE"
        assert stale.headers["cloudflare-cdn-cache-control"] == "no-store"  # no shared cache keeps a stale answer
        deadline = time.monotonic() + 10
        while (r := client.get("/api/overview")).json()["matches"] != 2:
            assert time.monotonic() < deadline, "the background rebuild never landed"
            time.sleep(0.05)
        assert r.headers["x-echovr-cache"] == "HIT"


def test_a_page_nobody_asked_for_yet_is_built_for_the_visitor(tmp_path):
    with app_client(make_settings(tmp_path, cache_refresh_s=300)) as client:
        add(client, match_file())
        r = client.get(f"/api/players/{BLUE}")
        assert r.status_code == 200 and r.headers["x-echovr-cache"] == "MISS" and r.json()["stats"]["games"] == 1
        missing = client.get("/api/players/nobody")
        assert missing.status_code == 404 and missing.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("edge", [60, 0])
def test_cache_headers(tmp_path, edge):
    with app_client(make_settings(tmp_path, edge_cache_s=edge)) as client:
        add(client, match_file())
        public = client.get("/api/overview").headers
        if edge:
            assert public["cache-control"] == "no-cache"  # browsers ask every time (ETag), Cloudflare keeps it 60 s
            assert public["cloudflare-cdn-cache-control"] == "max-age=60, stale-if-error=600"
        else:
            assert public["cache-control"] == "private, no-cache"
            assert public["cloudflare-cdn-cache-control"] == "no-store"
        assert client.get("/api/leaderboard/gear").headers["cache-control"] == public["cache-control"]  # uncached ones too
        for url in ("/api/auth/me", "/api/admin/status"):  # logins: never shared
            h = client.get(url).headers
            assert h["cache-control"] == "private, no-store" and h["cloudflare-cdn-cache-control"] == "no-store", url
        error = client.get("/api/matches/999999").headers
        assert error["cache-control"] == "no-store" and error["cloudflare-cdn-cache-control"] == "no-store"


def test_answers_that_depend_on_the_visitor_are_never_shared(tmp_path):
    """Before the launch the challenges and stat list depend on the visitor's Discord preview: private. After it
    they are the same for everyone, so they may be shared."""
    with app_client(make_settings(tmp_path, edge_cache_s=60)) as client:
        add(client, match_file())
        for url in ("/api/challenges", "/api/leaderboard/stats"):
            assert client.get(url).headers["cache-control"] == "private, no-store", url
        assert client.get("/api/achievements").headers["cache-control"] == "private, no-store"  # 403 coming soon
        act(client, actions.set_challenge_window, "2026-01-01", None)
        for url in ("/api/challenges", "/api/leaderboard/stats", "/api/achievements"):
            r = client.get(url)
            assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", url


def test_guard_refusals_are_never_kept(tmp_path):
    with app_client(make_settings(tmp_path, scraper_guard=True, edge_cache_s=60)) as client:
        refused = client.get("/api/overview", headers={"User-Agent": "Mozilla/5.0"})  # no X-EchoVR header
        assert refused.status_code == 403 and refused.headers["cache-control"] == "no-store"
        assert refused.headers["cloudflare-cdn-cache-control"] == "no-store"
        assert client.post("/api/overview").headers["cache-control"] == "no-store"  # read-only site: 405


@pytest.mark.parametrize("path, content_type, expected", [
    ("/", "text/html; charset=utf-8", "no-cache"),
    ("/players/123", "text/html; charset=utf-8", "no-cache"),
    ("/players/123", None, "no-cache"),  # a 304 carries no content type: page addresses are known by their path
    ("/assets/index-abc123.js", "text/javascript", "public, max-age=31536000, immutable"),
    ("/minimaps/dyson.png", "image/png", "public, max-age=14400"),
])
def test_static_cache_headers(path, content_type, expected):
    message = {"type": "http.response.start", "status": 200, "headers": []}
    headers = MutableHeaders(scope=message)
    if content_type:
        headers["content-type"] = content_type
    _static_cache(headers, path, 200)
    assert headers["cache-control"] == expected


def test_stamp_is_read_at_most_every_couple_of_seconds(tmp_path, monkeypatch):
    with app_client(make_settings(tmp_path)) as client:
        sessions = client.app.state.sessionmaker
        reads = []
        real = cache.data_stamp
        monkeypatch.setattr(cache, "data_stamp", lambda db: reads.append(1) or real(db))
        first = cache.current_stamp(sessions)
        assert cache.current_stamp(sessions) == first and len(reads) == 1  # remembered
        cache.bump_generation()  # a replay saved by this process: seen at once
        assert cache.current_stamp(sessions) != first and len(reads) == 2
        monkeypatch.setattr(cache, "STAMP_TTL_S", 0)  # the admin console's changes: seen after the TTL
        cache.current_stamp(sessions)
        assert len(reads) == 3


def test_store_keeps_the_most_recent_within_its_limits():
    store = cache.Store(max_entries=3, max_bytes=100)
    for key in "abc":
        store.put(key, cache.Entry((), 0.0, size=30))
    store.get("a")  # used: kept
    store.put("d", cache.Entry((), 0.0, size=30))  # over 100 bytes: the least recently used one goes
    assert list(store.entries) == ["c", "a", "d"] and store.bytes == 90
    store.put("e", cache.Entry((), 0.0, size=500))  # bigger than the whole store: not kept, nothing else lost either
    assert "e" not in store.entries and store.bytes <= 100


def test_answer_built_from_an_older_cached_answer_is_as_old_as_it(tmp_path):
    """The leaderboard page is built from the all-stats aggregate: when that one is stale the page must not pass for
    fresh, or it would never be rebuilt."""
    with app_client(make_settings(tmp_path, cache_refresh_s=300)) as client:
        add(client, match_file())
        request = SimpleNamespace(app=client.app, headers={})
        cache.cached(request, "inner", (), lambda: "old")
        inner_key = ("inner", (), next(iter(client.app.state.value_cache.entries))[2])
        inner = client.app.state.value_cache.entries[inner_key]
        add(client, match_file())  # the stamp moves on; the inner answer is young, so it is reused as it is
        outer = cache.cached(request, "outer", (), lambda: cache.cached(request, "inner", (), lambda: "new") + "+page")
        assert outer == "old+page"
        built = client.app.state.value_cache.entries[("outer", (), inner_key[2])]
        assert built.stamp == inner.stamp and built.built_at == inner.built_at
