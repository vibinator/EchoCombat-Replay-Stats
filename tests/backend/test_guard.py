"""Scraper protection (D48): the site's own pages get the data, scripts, bots and floods do not."""

import replay_factory as rf
from app_helpers import add, app_client, make_settings

from backend.guard import RateLimiter

BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/140.0 Safari/537.36", "X-EchoVR": "1"}


def guarded(tmp_path, **overrides):
    return app_client(make_settings(tmp_path, scraper_guard=True, **overrides))


def test_site_pages_get_data_scripts_do_not(tmp_path):
    with guarded(tmp_path) as client:
        assert client.get("/api/matches", headers=BROWSER).status_code == 200
        no_header = client.get("/api/matches", headers={"User-Agent": BROWSER["User-Agent"]})
        assert no_header.status_code == 403 and no_header.json()["error_code"] == "automated"
        for agent in ("python-requests/2.32", "curl/8.5.0", "Scrapy/2.11", "Mozilla/5.0 HeadlessChrome/120.0", ""):
            assert client.get("/api/matches", headers=BROWSER | {"User-Agent": agent}).status_code == 403, agent
        assert client.get("/api/matches").headers["x-robots-tag"] == "noindex, nofollow"


def test_browser_opened_links_and_health_need_no_header(tmp_path):
    with guarded(tmp_path) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
        page = {"User-Agent": BROWSER["User-Agent"]}
        match_id = client.get("/api/matches", headers=BROWSER).json()["items"][0]["id"]
        assert client.get(f"/api/matches/{match_id}/export", headers=page).status_code == 200  # <a href> download
        assert client.get("/api/auth/me", headers=page).status_code == 200
        assert client.get("/api/health", headers={"User-Agent": "Python-urllib/3.12"}).status_code == 200  # Docker


def test_ai_crawlers_refused_everywhere(tmp_path):
    with guarded(tmp_path) as client:
        bot = {"User-Agent": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2)"}
        assert client.get("/matches", headers=bot).status_code == 403
        assert client.get("/api/matches", headers=BROWSER | bot).json()["error_code"] == "crawler"


def test_rate_limit_per_visitor(tmp_path):
    with guarded(tmp_path, rate_limit_per_min=3) as client:  # bursts up to 6
        ok = [client.get("/api/leaderboard/stats", headers=BROWSER | {"CF-Connecting-IP": "1.1.1.1"}).status_code
              for _ in range(6)]
        assert ok == [200] * 6
        r = client.get("/api/leaderboard/stats", headers=BROWSER | {"CF-Connecting-IP": "1.1.1.1"})
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        # someone else behind the same tunnel is not affected
        assert client.get("/api/leaderboard/stats", headers=BROWSER | {"CF-Connecting-IP": "2.2.2.2"}).status_code == 200


def test_token_bucket():
    limiter = RateLimiter(per_minute=60, burst=10)
    assert all(limiter.take("a", now=0.0) == 0 for _ in range(10))
    assert limiter.take("a", now=0.0) > 0
    assert limiter.take("a", now=1.0) == 0  # one per second refills
    assert limiter.take("a", 5, now=2.0) > 0  # heavy request needs 5 tokens
    assert limiter.take("a", 5, now=7.0) == 0


def test_hourly_limit_bounds_a_slow_scraper(tmp_path):
    with guarded(tmp_path, rate_limit_per_min=100, rate_limit_per_hour=4) as client:  # minute bucket never trips
        ip = BROWSER | {"CF-Connecting-IP": "3.3.3.3"}
        assert [client.get("/api/leaderboard/stats", headers=ip).status_code for _ in range(4)] == [200] * 4
        r = client.get("/api/leaderboard/stats", headers=ip)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_forged_visitor_address_ignored_from_public_peer():
    from types import SimpleNamespace

    from backend.guard import client_ip

    def req(peer):
        return SimpleNamespace(client=SimpleNamespace(host=peer), headers={"cf-connecting-ip": "9.9.9.9"})

    assert client_ip(req("172.18.0.3")) == "9.9.9.9"  # cloudflared in the Docker network
    assert client_ip(req("8.8.8.8")) == "8.8.8.8"  # reached the port directly: header is not believed


def test_replay_files_and_internals_not_served(tmp_path):
    with guarded(tmp_path, import_api=False) as client:  # as on the public site
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
        for path in ("/replays/dyson/a.echoreplay", "/dyson/a.echoreplay", "/api/matches/1/a.echoreplay", "/x/a.ECHOREPLAY",
                     "/a%252eechoreplay", "/api/replays/1", "/api/import", "/openapi.json", "/secret.txt"):
            assert client.get(path, headers=BROWSER).status_code == 404, path
        assert "source_dir" not in client.get("/api/health").json()
        csp = client.get("/", headers=BROWSER).headers["content-security-policy"]
        assert "script-src 'self'" in csp and "object-src 'none'" in csp
