"""Browser end-to-end sweep: every page, headless Chromium, staff login (docs/reference/E2E-TESTING.md).

    python app/tools/e2e/browser_sweep.py [--base http://127.0.0.1:8000] [--data data] [--out <folder>] [--phone] [--dark]

Needs Playwright in the Python that runs it (pip install playwright; playwright install chromium) - the project venv does
not have it. Writes <out>/<theme>-<view>-<page>.png (full page) and <out>/report.json with, per page: load seconds, title,
first heading, console errors (Twitch embed noise filtered out), failed / 4xx-5xx requests, empty-state / alert texts,
horizontal overflow, the three slowest API calls. The guard refuses "HeadlessChrome": a normal user agent is set."""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_login import cookie  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
NOISE = ("twitch", "live-video.net", "amazon-adsystem", "Permissions policy", "getLayoutMap", "discord")
PHONE_PAGES = {"home", "matches", "match", "player", "leaderboard", "achievements", "console"}


def pages(base: str) -> list[tuple[str, str]]:
    h = {"X-EchoVR": "1", "User-Agent": UA}
    m = httpx.get(f"{base}/api/matches?limit=3&min_players=6", headers=h).json()["items"][0]
    det = httpx.get(f"{base}/api/matches/{m['id']}", headers=h).json()
    uid, uid2 = det["teams"]["blue"][0]["user_id"], det["teams"]["orange"][0]["user_id"]
    combat = httpx.get(f"{base}/api/combat/matches?limit=1", headers=h).json().get("items") or []
    mid = m["id"]
    return [
        ("home", "/"), ("matches", "/matches"), ("matches-list", "/matches?view=list&map=surge&mode=payload"),
        ("match", f"/matches/{mid}"), ("match-gear", f"/matches/{mid}?tab=gear"), ("match-timeline", f"/matches/{mid}?tab=timeline"),
        ("match-heatmap", f"/matches/{mid}?tab=heatmap"), ("match-playback", f"/matches/{mid}?tab=playback"),
        ("players", "/players"), ("players-search", "/players?q=a"), ("player", f"/players/{uid}"), ("player-week", f"/players/{uid}?period=week"),
        ("compare", f"/compare?players={uid},{uid2}"), ("leaderboard", "/leaderboard"), ("leaderboard-combat", "/leaderboard?board=combat"),
        ("leaderboard-ach", "/leaderboard?stat=achievements"), ("achievements", "/achievements"), ("achievements-player", f"/achievements/{uid}"),
        ("combat-match", f"/combat/{combat[0]['session_id']}" if combat else "/combat"), ("profile", "/profile"),
        ("console", "/console"), ("console-players", "/console?tab=players"), ("console-replays", "/console?tab=replays"),
        ("console-audit", "/console?tab=log"), ("permissions", "/permissions"), ("notfound", "/this-page-does-not-exist"),
    ]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--data", default=str(Path(__file__).resolve().parents[3] / "data"))
    p.add_argument("--out", default=str(Path(__file__).resolve().parents[3] / "data" / "e2e-shots"))
    p.add_argument("--phone", action="store_true", help="also the main pages at 390 px")
    p.add_argument("--dark", action="store_true", help="also the dark theme")
    a = p.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    session = cookie(Path(a.data))
    todo = pages(a.base)
    report = []
    views = [(1400, "desktop")] + ([(390, "phone")] if a.phone else [])
    themes = ["light"] + (["dark"] if a.dark else [])
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for theme in themes:
            for width, view in views:
                ctx = browser.new_context(user_agent=UA, viewport={"width": width, "height": 900}, color_scheme=theme)
                ctx.add_cookies([{"name": "echovr_session", "value": session, "domain": "127.0.0.1", "path": "/"}])
                page = ctx.new_page()
                errors, failed, timings = [], [], {}
                page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text[:300]}") if msg.type == "error" and not any(n in msg.text for n in NOISE) else None)
                page.on("pageerror", lambda e: errors.append(f"pageerror: {str(e)[:300]}") if not any(n in str(e) for n in NOISE) else None)
                page.on("requestfailed", lambda r: failed.append(f"{r.url[:120]} {r.failure}") if not any(n in r.url for n in NOISE) else None)
                page.on("response", lambda r: (failed.append(f"HTTP {r.status} {r.url[:140]}") if r.status >= 400 and not any(n in r.url for n in NOISE) else None,
                                               timings.__setitem__(r.url, (r.request.timing or {}).get("responseEnd", 0)) if "/api/" in r.url else None))
                for name, path in todo:
                    if view == "phone" and name not in PHONE_PAGES:
                        continue
                    errors.clear(); failed.clear(); timings.clear()
                    t0 = time.time()
                    try:
                        page.goto(a.base + path, wait_until="networkidle", timeout=90000)
                        page.wait_for_timeout(1500)
                        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                        page.wait_for_timeout(1200)
                        page.evaluate("window.scrollTo(0, 0)")
                        page.wait_for_load_state("networkidle", timeout=20000)
                    except Exception as e:  # noqa: BLE001 - recorded, the sweep goes on
                        errors.append(f"navigation: {str(e)[:200]}")
                    rec = {
                        "theme": theme, "view": view, "page": name, "path": path, "s": round(time.time() - t0, 1), "title": page.title(),
                        "h1": page.evaluate("document.querySelector('h1,h2')?.innerText || ''")[:80],
                        "text_chars": page.evaluate("document.body.innerText.length"),
                        "errors": errors[:8], "failed": failed[:8],
                        "alerts": page.evaluate("[...document.querySelectorAll('.error, [role=alert], .empty')].map(e => e.innerText.slice(0, 120)).filter(Boolean)")[:5],
                        "hscroll": page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"),
                        "slowest_api_ms": sorted(((round(v), u.replace(a.base, "")) for u, v in timings.items()), reverse=True)[:3],
                    }
                    page.screenshot(path=str(out / f"{theme}-{view}-{name}.png"), full_page=True)
                    report.append(rec)
                    flags = [f for f, on in (("ERR", rec["errors"]), ("FAIL", rec["failed"]), ("HSCROLL", rec["hscroll"]), ("ALERT", rec["alerts"])) if on]
                    print(f"{theme:5} {view:7} {name:20} {rec['s']:5}s {'/'.join(flags):18} {rec['h1'][:40]!r}", flush=True)
                ctx.close()
        browser.close()
    (out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    bad = [r for r in report if r["errors"] or r["hscroll"]]
    print(f"\n{len(report)} page views, {len(bad)} with console errors or horizontal overflow -> {out / 'report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
