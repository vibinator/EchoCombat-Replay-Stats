"""check_cloudflare.bat's verdicts (app/cloudflare_check.py), from made-up Cloudflare answers: no network."""

from cloudflare_check import Probe, assess

CF = {"server": "cloudflare", "cf-ray": "8f00-AMS"}


def api(cache: str, **headers) -> Probe:
    return Probe("/api/overview/activity", 200, CF | {"cf-cache-status": cache, "etag": 'W/"abc"', "x-echovr-cache": "HIT",
                                                      "cache-control": "no-cache"} | headers)


def site(**changes) -> dict[str, Probe]:
    """A correctly set up site; `changes` replaces probes."""
    p = {
        "index": Probe("/", 200, CF | {"cf-cache-status": "DYNAMIC", "cache-control": "no-cache"}),
        "asset1": Probe("/assets/a.js", 200, CF | {"cf-cache-status": "MISS", "cache-control": "public, max-age=31536000, immutable"}),
        "asset2": Probe("/assets/a.js", 200, CF | {"cf-cache-status": "HIT", "cache-control": "public, max-age=31536000, immutable"}),
        "image1": Probe("/minimaps/dyson_small.png", 200, CF | {"cf-cache-status": "HIT"}),
        "image2": Probe("/minimaps/dyson_small.png", 200, CF | {"cf-cache-status": "HIT"}),
        "api1": api("MISS"), "api2": api("HIT"), "api3": api("HIT"),
        "revalidate": Probe("/api/overview/activity", 304, CF | {"cf-cache-status": "HIT"}),
        "no_header": Probe("/api/overview/activity", 403, CF | {"cf-cache-status": "DYNAMIC"}),
        "script": Probe("/api/overview/activity", 403, CF | {"cf-cache-status": "DYNAMIC"}),
        "me1": Probe("/api/auth/me", 200, CF | {"cf-cache-status": "BYPASS", "cache-control": "private, no-store"}),
        "me2": Probe("/api/auth/me", 200, CF | {"cf-cache-status": "BYPASS", "cache-control": "private, no-store"}),
    }
    return p | changes


def levels(results) -> set[str]:
    return {level for level, _ in results}


def test_a_correct_setup_passes():
    results = assess(site())
    assert levels(results) == {"PASS"}, results


def test_no_cache_rule_yet():
    results = assess(site(api1=api("DYNAMIC"), api2=api("DYNAMIC"), api3=api("DYNAMIC")))
    assert any(level == "FAIL" and "No Cache Rule" in text for level, text in results)


def test_login_answer_from_the_cache_is_flagged_as_dangerous():
    leaked = Probe("/api/auth/me", 200, CF | {"cf-cache-status": "HIT", "cache-control": "private, no-store"})
    results = assess(site(me2=leaked))
    assert any(level == "FAIL" and "DANGER" in text for level, text in results)


def test_old_server_and_browser_ttl_override():
    old = {"server": "cloudflare", "cf-ray": "1", "cf-cache-status": "DYNAMIC"}
    results = assess(site(api1=Probe("/api/x", 200, old), api2=Probe("/api/x", 200, old), api3=Probe("/api/x", 200, old)))
    assert any(level == "FAIL" and "new cache headers" in text for level, text in results)
    assert not any("304" in text and level == "WARN" for level, text in results)  # no ETag yet: not blamed on Cloudflare
    results = assess(site(api1=api("MISS", **{"cache-control": "max-age=14400"})))
    assert any(level == "WARN" and "Browser TTL" in text for level, text in results)


def test_cached_answers_without_the_site_header():
    results = assess(site(no_header=Probe("/api/x", 200, CF | {"cf-cache-status": "HIT"})))
    assert any(level == "WARN" and "X-EchoVR" in text for level, text in results)


def test_not_through_cloudflare_or_challenged():
    lan = {k: Probe(v.path, v.status, {"cf-cache-status": ""}) for k, v in site().items()}
    assert assess(lan)[0][0] == "FAIL" and "Cloudflare" in assess(lan)[0][1]
    challenged = site(api2=api("DYNAMIC", **{"cf-mitigated": "challenge"}))
    assert assess(challenged) == [assess(challenged)[0]] and "challenged" in assess(challenged)[0][1]
