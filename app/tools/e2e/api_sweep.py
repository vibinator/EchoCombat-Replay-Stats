"""API end-to-end sweep against a running local server (docs/reference/E2E-TESTING.md).

    .venv\\Scripts\\python app/tools/e2e/api_sweep.py [--base http://127.0.0.1:8000] [--data data] [--no-writes]

Every route with real ids from the data, then guard / validation / abuse cases, the read-only console commands, a
Permissions add + remove, an icon set + reset, caching (ETag 304), cold vs warm heavy answers and 40 parallel requests.
Prints one line per request; exit code 1 when any status differs from the expected one. Needs the server started by
run_local.bat (login bypass, rate limit off): with the limit on, the sweep 429s half-way."""

import argparse
import concurrent.futures as cf
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_login import cookie  # noqa: E402

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
PAGE = {"X-EchoVR": "1", "User-Agent": UA}
failures: list[str] = []


def check(label: str, r: httpx.Response, expect, ms: float | None = None) -> httpx.Response:
    ok = r.status_code in (expect if isinstance(expect, tuple) else (expect,))
    cache = r.headers.get("x-echovr-cache", "-")
    timing = f"{ms:7.0f}ms" if ms is not None else " " * 9
    note = "" if ok else f"   <-- expected {expect}: {r.text[:120]!r}"
    print(f"{r.status_code} {timing} {len(r.content):9,d}B {cache:5} {label}{note}")
    if not ok:
        failures.append(label)
    return r


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--data", default=str(Path(__file__).resolve().parents[3] / "data"))
    p.add_argument("--no-writes", action="store_true", help="skip console commands, permissions and icon changes")
    a = p.parse_args()
    session = cookie(Path(a.data))
    c = httpx.Client(base_url=a.base, headers=PAGE, cookies={"echovr_session": session}, timeout=180)
    anon = httpx.Client(base_url=a.base, headers=PAGE, timeout=30)

    def get(path, expect=200, client=c):
        t = time.perf_counter()
        r = client.get(path)
        return check(f"GET {path}", r, expect, (time.perf_counter() - t) * 1000)

    # --- ids from the data -------------------------------------------------------------------------------------------
    for _ in range(60):
        try:
            if anon.get("/api/health").status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(1)
    me = get("/api/auth/me").json()
    if not (me.get("user") or {}).get("console"):
        print("The test login has no console access: start the server with run_local.bat", file=sys.stderr)
        return 1
    m = get("/api/matches?limit=3&min_players=6").json()["items"][0]
    mid = m["id"]
    det = get(f"/api/matches/{mid}").json()
    uid, uid2, mp = det["teams"]["blue"][0]["user_id"], det["teams"]["orange"][0]["user_id"], det["map"]
    combat = get("/api/combat/matches?limit=1").json().get("items") or []
    csid = combat[0]["session_id"] if combat else None
    old = get("/api/matches?limit=1&offset=20000").json()["items"]
    old_id = old[0]["id"] if old else mid
    top = get("/api/leaderboard?limit=1").json()["items"][0]["user_id"]

    # --- every public route ------------------------------------------------------------------------------------------
    print("--- routes ---")
    for path in [
        f"/api/matches/{mid}/events", f"/api/matches/{mid}/timeline", f"/api/matches/{mid}/heatmap",
        f"/api/matches/{mid}/heatmap?mode=weapons", f"/api/matches/{mid}/heatmap3d", f"/api/matches/{mid}/playback",
        f"/api/matches/{mid}/playback3d", f"/api/matches/{mid}/export?format=csv", f"/api/matches/{mid}/export?format=json",
        f"/api/matches/thumbnails?ids={mid}", "/api/matches?map=surge&mode=payload&result=attack_win&private=0&min_players=6",
        "/api/matches?player_name=a", "/api/matches?from=2026-01-01&to=2026-12-31", "/api/matches?limit=200&offset=20000",
        "/api/players?q=a", f"/api/players/{uid}", f"/api/players/{uid}?period=week", f"/api/players/{uid}?period=month&map={mp}",
        f"/api/players/{uid}/heatmap?map={mp}", f"/api/players/{uid}/heatmap?map={mp}&mode=deaths&period=month",
        f"/api/players/{uid}/heatmap3d?map={mp}", f"/api/players/{uid}/trends", f"/api/players/{uid}/companions",
        f"/api/players/compare/{uid},{uid2}", f"/api/players/{uid}/achievements", f"/api/players/{uid}/achievements?period=week",
        "/api/leaderboard", "/api/leaderboard?stat=top_speed&period=month", "/api/leaderboard?stat=achievements",
        "/api/leaderboard/stats", "/api/leaderboard/gear", "/api/leaderboard/achievers",
        "/api/achievements", f"/api/achievements?player={uid}", "/api/achievements/recent", "/api/challenges",
        "/api/overview", "/api/overview/activity?bucket=day", "/api/overview/activity?bucket=month", "/api/overview/players-seen",
        "/api/overview/processing", "/api/overview/last-match", "/api/overview/live", "/api/search?q=a", f"/api/search?q=%23{mid}",
        "/api/combat/summary", "/api/combat/stats", "/api/combat/stats?map=surge", "/api/combat/leaderboard",
        "/api/combat/leaderboard?stat=kills&period=month", "/api/combat/matches", f"/api/combat/players/{uid}",
        "/api/arena/visible", "/api/arena/progress", "/api/arena/search?q=a", f"/api/avatars?ids={uid}",
        "/api/profiles/me", f"/api/profiles/{uid}", "/api/health",
        "/api/admin/console/overview", "/api/admin/console/achievements", "/api/admin/console/merge-suggestions",
        "/api/admin/console/log", "/api/admin/console/players?q=a", "/api/admin/console/mega-prizes",
        "/api/admin/console/achievements.csv", "/api/admin/console/mega-prizes.csv", "/api/admin/permissions",
        "/api/admin/status", "/api/admin/icons",
    ] + ([f"/api/combat/matches/{csid}"] if csid else []):
        get(path)

    # --- refusals and validation ------------------------------------------------------------------------------------
    print("--- guard / validation ---")
    get("/api/matches/999999999", 404)
    get("/api/players/nobody", 404)
    check("no X-EchoVR header", httpx.get(a.base + "/api/overview", headers={"User-Agent": UA}), 403)
    check("no User-Agent", httpx.get(a.base + "/api/overview", headers={"X-EchoVR": "1"}), 403)
    check("script User-Agent", httpx.get(a.base + "/api/overview", headers={"X-EchoVR": "1", "User-Agent": "python-requests/2"}), 403)
    check("POST on a read-only path", c.post("/api/matches"), 405)
    check("replay file path", c.get("/surge/x.echoreplay"), 404)
    check("openapi hidden", c.get("/openapi.json"), 404)
    check("console without login", anon.get("/api/admin/console/overview"), 403)
    check("console command without login", anon.post("/api/admin/console/status", json={}), 403)
    check("profile edit without login", anon.post("/api/profiles/me", json={"bio": "x"}), 401)
    check("bot link without secret (422: body is validated before the secret, Review SEC-4)", anon.post("/api/bot/link", json={}), (401, 404, 422))
    check("worker claim without secret", anon.post("/api/worker/claim", json={"count": 1, "parser_version": "x", "stats_version": "y"}), (401, 404))
    check("limit above max", c.get("/api/matches?limit=1000"), 422)
    check("negative offset", c.get("/api/matches?offset=-1"), 422)
    check("unknown stat", c.get("/api/leaderboard?stat=__import__"), 400)
    check("bad period", c.get(f"/api/players/{uid}?period=century"), 422)
    check("bad date", c.get("/api/matches?from=notadate"), 422)
    check("search too long", c.get("/api/search?q=" + "a" * 5000), 422)
    check("quote in search", c.get("/api/players?q=%27%20OR%201%3D1--"), 200)
    check("custom icon traversal", c.get("/achievements/custom/..%2F..%2Fsession.key"), 404)
    check("static traversal", c.get("/assets/..%2F..%2F..%2Fbackend%2Fconfig.py"), 404)
    check("huge match id (known 500, Review BUG-4)", c.get("/api/matches/" + "9" * 30), (404, 422, 500))
    r = c.get("/api/auth/login?next=https://evil.example", follow_redirects=False)
    check("login next= outside site", r, 303)
    if "evil" in r.headers.get("location", "") and "next" in r.headers.get("location", ""):
        failures.append("open redirect in login next=")
    check("callback with bad state", c.get("/api/auth/callback?code=x&state=y", follow_redirects=False), 303)

    # --- writes (staff) -----------------------------------------------------------------------------------------------
    if not a.no_writes:
        print("--- console commands (read-only ones) ---")
        for name, args in [("status", {}), ("find", {"term": "a"}), ("merges", {}), ("profile-links", {}), ("hidden", {}),
                           ("remote", {}), ("cannot-repair", {}), ("challenge", {}), ("mega-period", {}), ("hide-stats", {}),
                           ("find", {"term": ""}), ("unmerge", {"alias": "nope"}), ("discord-check", {"user_id": "100000000000000001"})]:
            t = time.perf_counter()
            r = c.post(f"/api/admin/console/{name}", json=args)
            check(f"console/{name} {args or ''} ok={r.json().get('ok') if r.status_code == 200 else '?'}", r, 200, (time.perf_counter() - t) * 1000)
        check("unknown console command", c.post("/api/admin/console/rm-rf", json={}), 404)
        print("--- permissions add / remove ---")
        test_id = "100000000000000001"
        check("add admin user", c.post("/api/admin/permissions", json={"permission": "admin", "type": "user", "id": test_id}), 200)
        if not c.get("/api/auth/me").json()["user"]["admin"]:
            failures.append("admin permission did not apply")
        check("remove admin user", c.post("/api/admin/permissions", json={"permission": "admin", "type": "user", "id": test_id, "remove": True}), 200)
        check("bad permission id", c.post("/api/admin/permissions", json={"permission": "preview", "type": "role", "id": "abc"}), 400)
        check("fixed YAML id", c.post("/api/admin/permissions", json={"permission": "console", "type": "user", "id": test_id, "remove": True}), 400)
        print("--- icons set / reset ---")
        icons = c.get("/api/admin/icons").json()
        rule = c.get("/api/admin/console/achievements").json()[0]["id"]
        check("set icon", c.put(f"/api/admin/achievements/{rule}/icon", json={"icon": icons[1]}), 200)
        check("reset icon", c.put(f"/api/admin/achievements/{rule}/icon", json={"icon": None}), 200)
        check("bad icon name", c.put(f"/api/admin/achievements/{rule}/icon", json={"icon": "../../x.png"}), 400)
        check("upload not a PNG", c.post(f"/api/admin/achievements/{rule}/icon", content=b"GIF89a....", headers={"Content-Type": "image/png"}), 400)

    # --- caching and heavy answers -----------------------------------------------------------------------------------
    print("--- caching / heavy ---")
    r = c.get("/api/overview")
    check("If-None-Match -> 304", c.get("/api/overview", headers={"If-None-Match": r.headers.get("etag", "")}), 304)
    get(f"/api/matches/{old_id}/playback3d", (200, 404, 503))
    get(f"/api/matches/{old_id}/heatmap")
    get(f"/api/players/{top}/heatmap?map=dyson&last=5000")
    get(f"/api/players/{top}/heatmap?map=dyson&last=5000")
    get(f"/api/players/{top}")
    get(f"/api/players/{top}/achievements")
    get(f"/api/matches?player={top}&limit=200")

    def one(i):
        t = time.perf_counter()
        r = c.get(["/api/overview", "/api/leaderboard?stat=top_speed", "/api/achievements/recent", "/api/matches?limit=50&with_players=1"][i % 4])
        return r.status_code, round((time.perf_counter() - t) * 1000)

    with cf.ThreadPoolExecutor(20) as ex:
        res = list(ex.map(one, range(40)))
    print(f"40 parallel: statuses {sorted({s for s, _ in res})}, max {max(t for _, t in res)} ms, median {sorted(t for _, t in res)[20]} ms")
    if {s for s, _ in res} != {200}:
        failures.append("parallel requests")

    print(f"\n{'OK' if not failures else 'FAILED'}: {len(failures)} unexpected" + (": " + "; ".join(failures) if failures else ""))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
