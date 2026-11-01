"""Is Cloudflare caching the public site the way it should (D53)? Run it after updating the server and after changing
the Cloudflare Cache Rule (docs/Setup.MD, "Cloudflare cache"). It asks the public site about 20 small questions and
reads Cloudflare's answer headers; nothing is changed anywhere.

  Windows:  check_cloudflare.bat                       (or: check_cloudflare.bat https://echocombat.com)
  NAS:      docker exec -it echovr-replay-stats python app/cloudflare_check.py https://echocombat.com

Exit code 1 when something is wrong (FAIL)."""

import os
import sys
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36"
SCRIPT = "python-requests/2.32"
KEPT = ("HIT", "REVALIDATED", "UPDATING", "STALE")  # cf-cache-status values meaning Cloudflare answered from its cache


@dataclass
class Probe:
    path: str
    status: int
    headers: dict[str, str]  # names in lower case

    def header(self, name: str) -> str:
        return self.headers.get(name.lower(), "")

    @property
    def cache(self) -> str:
        return self.header("cf-cache-status").upper()


def ask(base: str, path: str, *, site: bool = True, agent: str = BROWSER, etag: str | None = None,
        body: bool = False) -> tuple[Probe, bytes]:
    headers = {"User-Agent": agent}
    if site:
        headers["X-EchoVR"] = "1"  # what the site's own pages send (scraper protection, D48)
    if etag:
        headers["If-None-Match"] = etag
    if not body:
        headers["Accept-Encoding"] = "gzip"  # as browsers ask (the body is not read)
    request = urllib.request.Request(base.rstrip("/") + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as r:
            return Probe(path, r.status, {k.lower(): v for k, v in r.headers.items()}), (r.read() if body else b"")
    except urllib.error.HTTPError as e:  # 304, 403, ... are answers too
        return Probe(path, e.code, {k.lower(): v for k, v in e.headers.items()}), b""


def collect(base: str) -> dict[str, Probe]:
    """Every question, in order. The API one carries a never-used query string, so its first answer cannot have
    been cached by anyone else yet (the server ignores the extra parameter)."""
    p: dict[str, Probe] = {}
    p["index"], html = ask(base, "/", site=False, body=True)
    asset = next((part.split('"')[0] for part in html.decode("utf-8", "replace").split('src="')[1:]
                  if part.startswith("/assets/")), None)
    if asset:
        p["asset1"], _ = ask(base, asset, site=False)
        p["asset2"], _ = ask(base, asset, site=False)
    p["image1"], _ = ask(base, "/minimaps/dyson_small.png", site=False)
    p["image2"], _ = ask(base, "/minimaps/dyson_small.png", site=False)
    api = f"/api/overview/activity?bucket=year&cfcheck={uuid.uuid4().hex[:12]}"
    for i in (1, 2, 3):
        p[f"api{i}"], _ = ask(base, api)
    p["revalidate"], _ = ask(base, api, etag=p["api1"].header("etag") or '"none"')
    p["no_header"], _ = ask(base, api, site=False)
    p["script"], _ = ask(base, api, agent=SCRIPT)
    p["me1"], _ = ask(base, "/api/auth/me")
    p["me2"], _ = ask(base, "/api/auth/me")
    return p


def _max_age(cache_control: str) -> int:
    for part in cache_control.replace(" ", "").split(","):
        if part.startswith("max-age="):
            try:
                return int(part.split("=", 1)[1])
            except ValueError:
                return 0
    return 0


def assess(p: dict[str, Probe]) -> list[tuple[str, str]]:
    """(PASS | WARN | FAIL | INFO, what it means and what to do)."""
    out: list[tuple[str, str]] = []
    api1, api2, api3 = p["api1"], p["api2"], p["api3"]
    if not (api1.header("cf-ray") and api1.header("server").lower() == "cloudflare"):
        return [("FAIL", "These answers did not come through Cloudflare (no cf-ray header). Use the public address "
                         "(https://echocombat.com), not the NAS's own one.")]
    if any(x.header("cf-mitigated") for x in p.values()):
        return [("FAIL", "Cloudflare challenged this check (Bot Fight Mode or a WAF rule), so it cannot see the cache. "
                         "Check in a browser instead: Setup.MD, Cloudflare cache, 'Check in a browser'.")]

    if api1.status != 200:
        out.append(("FAIL", f"The data answer came back {api1.status} instead of 200: is the app running? (tunnel healthy?)"))
        return out
    if api1.header("etag") and api1.header("x-echovr-cache"):
        out.append(("PASS", "The server is the new version: answers carry an ETag and cache headers."))
    else:
        out.append(("FAIL", "The server does not send the new cache headers yet: upload the new version, wait for the "
                            "GitHub Actions build, then Recreate the container (Setup.MD, Updating)."))

    statuses = [a.cache or "NONE" for a in (api1, api2, api3)]
    seen = " -> ".join(statuses)
    if any(s in KEPT for s in statuses[1:]):
        out.append(("PASS", f"Cloudflare keeps public data answers ({seen}): repeats never reach the NAS."))
    elif all(s == "DYNAMIC" for s in statuses):
        out.append(("FAIL", f"No Cache Rule applies to /api/ ({seen}): every request goes to the NAS. Add the rule "
                            "(Setup.MD, Cloudflare cache, steps 1-3)."))
    elif "BYPASS" in statuses:
        out.append(("FAIL", f"The Cache Rule applies but Cloudflare was told not to keep the answer ({seen}). Check that "
                            "ECHOVR_EDGE_CACHE_S is above 0 in docker-compose.yml and the rule's Edge TTL is 'Use "
                            "cache-control header if present, bypass cache if not'."))
    else:
        out.append(("WARN", f"Cloudflare looked in its cache but did not keep the answer ({seen}). Check the rule's Edge "
                            "TTL ('Use cache-control header if present, bypass cache if not') and run the check again."))

    browser = api1.header("cache-control")
    if _max_age(browser) > 0:
        out.append(("WARN", f"Browsers are told to keep answers {_max_age(browser)} s without asking ('{browser}'): set "
                            "the rule's Browser TTL to 'Respect origin'."))
    elif "no-cache" in browser:
        out.append(("PASS", "Browsers check every answer with the server (no-cache + ETag), as chosen."))
    if not api1.header("etag"):
        out.append(("INFO", "The 304 Not Modified check runs once the server sends ETags (the new version)."))
    elif p["revalidate"].status == 304:
        out.append(("PASS", "An unchanged answer is a 304 Not Modified: almost nothing is sent or rebuilt."))
    else:
        out.append(("WARN", f"Asking with the ETag gave {p['revalidate'].status}, not 304: something changes the ETag on "
                            "the way (a Transform Rule, or a feature that rewrites responses)."))

    for me in (p["me1"], p["me2"]):
        if me.cache in KEPT:
            out.append(("FAIL", "DANGER: a login answer (/api/auth/me) came from Cloudflare's cache, so visitors could "
                                "see each other's login state. Set the rule's Edge TTL to 'Use cache-control header if "
                                "present, bypass cache if not' (never 'Ignore cache-control header')."))
            break
    else:
        if "no-store" in p["me2"].header("cache-control"):
            out.append(("PASS", "Login answers are never kept by Cloudflare (private, no-store)."))

    if p["no_header"].status == 403:
        out.append(("PASS", "Cached answers still need the site's own X-EchoVR header: scrapers without it are refused."))
    elif p["no_header"].status == 200:
        out.append(("WARN", "A cached answer was served without the X-EchoVR header, so scrapers can read cached pages "
                            "without it. Add the header condition to the Cache Rule (Setup.MD, Cloudflare cache, step 2) "
                            "if your plan allows it, and keep the rate limiting rule (step 4)."))
    if p["script"].status == 200:
        out.append(("INFO", "A script that copies the header and gets a cached answer is not stopped by the app; "
                            "Cloudflare's rate limiting rule (step 4) bounds how fast it can go."))

    index = p["index"]
    if index.cache in KEPT and _max_age(index.header("cache-control")) > 0:
        out.append(("WARN", "The page itself (index.html) is cached with a lifetime: after an update visitors could get "
                            "the old page. Only /api/ should be in the Cache Rule."))
    elif "no-cache" in index.header("cache-control"):
        out.append(("PASS", "Pages (index.html) are always checked, so a new version shows at once."))
    else:
        out.append(("WARN", "Pages (index.html) are sent without 'no-cache' (the old server version): after an update "
                            "some browsers keep the old page for a while. Fixed by the new version."))
    if "asset2" in p:
        if p["asset2"].cache in KEPT and "immutable" in p["asset2"].header("cache-control"):
            out.append(("PASS", "Scripts and styles (/assets) are kept by Cloudflare and browsers for a year."))
        else:
            out.append(("WARN", f"Scripts (/assets) were not served from Cloudflare's cache ({p['asset2'].cache or 'none'})."))
    if p["image2"].cache in KEPT:
        out.append(("PASS", "Images are kept by Cloudflare."))
    else:
        out.append(("WARN", f"Images were not served from Cloudflare's cache ({p['image2'].cache or 'none'})."))
    return out


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else os.environ.get("ECHOVR_PUBLIC_URL", "https://echocombat.com")
    if not base.startswith("https://"):
        print(f"Checking {base}: only the public https address goes through Cloudflare.")
    print(f"Checking how Cloudflare caches {base} ...\n")
    try:
        results = assess(collect(base))
    except OSError as e:  # includes time-outs (30 s per question)
        print(f"FAIL  {base} did not answer in time or could not be reached ({e}). If the site works in a browser the "
              "server was just busy: run the check again in a minute.")
        return 1
    for level, message in results:
        print(f"{level:<5} {message}")
    failed = any(level == "FAIL" for level, _ in results)
    print("\nSomething needs fixing (FAIL above)." if failed else "\nCloudflare is set up as intended.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
