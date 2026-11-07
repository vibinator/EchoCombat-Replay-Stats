# End-to-end testing locally (hand-written, 2026-11-07)

What the 2026-11-07 review ran, packaged so it can be repeated in minutes. Everything lives in `app/tools/e2e/`.
Nothing here touches the replay share; it writes only to the data folder you point it at and to the audit log.

## 1. Unit / integration tests (1 min)
```
.venv\Scripts\python -m pytest -q
```
≈ 414 tests. Known flaky: `tests/backend/test_remote.py::test_damaged_track_files_are_left_out_not_saved` (race between the
in-process worker thread and the test switching remote mode; see Review, BUG-5). Frontend: `cd app\frontend && npm run build`
(type-check + bundle; there are no frontend unit tests).

## 2. Start the site with the Discord login bypassed
`auth.enabled()` only needs *any* client secret and bot token to be set; access is decided by ids, and ids in
`ECHOVR_DISCORD_PREVIEW_ROLES` always get the Console (and so the Preview). A fake 18-digit user id therefore gives a
full staff login without Discord. Discord calls fail harmlessly (401 warnings in the log: avatars, member list, role names).

```
app\tools\e2e\run_local.bat                      (defaults: data\ and the source from settings.local.bat, rate limit off, 4 workers)
app\tools\e2e\run_local.bat --data C:\tmp\e2e    (a throw-away data folder: empty database, re-import from the share)
```
Then mint the session cookie (signed with `<data>/session.key`, created on first use):
```
.venv\Scripts\python app\tools\e2e\local_login.py            → prints the cookie value and a ready-made curl header
```
Paste it into the browser as cookie `echovr_session` for `127.0.0.1` (DevTools > Application > Cookies), reload: the top
bar shows "E2E Tester · Console". Admin (Status page) is granted on the Permissions page as a *user* id (and removed again
there). The sweeps below do this automatically.

Guard reminder: `/api/*` answers only to a browser User-Agent **plus** `X-EchoVR: 1`; `curl -A Mozilla/5.0 -H "X-EchoVR: 1"`.
Headless Chrome is refused by UA (`HeadlessChrome`): the browser sweep sets a normal UA.

## 3. API sweep (30 s)
```
.venv\Scripts\python app\tools\e2e\api_sweep.py [--base http://127.0.0.1:8000] [--data data]
```
Hits every route in `API-ROUTES.md` with real ids discovered from the data (newest match, two of its players, a combat
session), prints `status  ms  bytes  cache  path`, then the negative cases (guard refusals, read-only 405, validation,
path traversal, open-redirect, console without login), console commands (read-only ones: status, find, merges …),
Permissions add + remove, icon set + reset, ETag 304, cold vs warm heatmaps, 40 parallel requests. Exit code 1 when a
status differs from the expected one. Run it with the rate limit off (`run_local.bat` does) or it will 429 half-way.

## 4. Browser sweep (3–4 min)
Needs Playwright in the **global** Python (`pip install playwright && playwright install chromium`; the venv does not have it).
```
python app\tools\e2e\browser_sweep.py [--base …] [--data data] [--out C:\tmp\e2e-shots]
```
Visits every page at 1400 px and the main ones at 390 px, in light and dark, with the staff cookie: full-page screenshots,
console errors (Twitch embed noise filtered), failed requests, horizontal-overflow check, slowest API call per page,
and a `report.json`. Read the screenshots with the image viewer; grep the JSON for `"errors": [` that are not empty.

## 5. What to look at by hand afterwards
- `docs/Review-2026-11-07.MD` for the open findings and whether they still reproduce.
- Server log: `database is locked`, `Saving replay … failed`, `Exception in ASGI application`.
- Console > Dashboard: failed count, "Arena counter" error text, import speed (≈ 200 replays/min at 4 workers on the PC).
