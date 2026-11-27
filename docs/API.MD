# Public player-stats API (v1)

Profile stats of Echo Combat players, for people and bots an admin gave a key (user, 2026-11-27). Everything else on
`/api/` stays for the site's own pages only (guard.py). Code: `app/backend/api/public.py`, keys: `app/backend/api_keys.py`.

## Getting a key (admins)
- **Console page > API tab > New API key**: give it a name (who or what uses it). The key and ready-to-use URLs are shown
  **once**; the audit log keeps the output with the key blacked out. Only admins can make, list or revoke keys.
- Or `admin.bat api-key-add <name>`, `admin.bat api-keys`, `admin.bat api-key-revoke <id>`.
- A revoked key stops working within 10 seconds. Only a SHA-256 of each key is stored (app_settings `api_key:<id>`).

## Calling it
Send the key in one of: `Authorization: Bearer <key>` (best for scripts), `X-API-Key: <key>`, or `?key=<key>` (a URL
that works on its own, but it ends up in browser histories and logs).

| Endpoint | What |
|---|---|
| `GET /api/v1/players?q=<name>&limit=20&offset=0` | players whose name contains `q`, most recently seen first: `user_id`, `name`, `games`, `hours_played`, `last_seen_at` |
| `GET /api/v1/players/{user_id}?period=all&map=` | one player's profile stats; `period` and `map` as on the player page |
| `GET /api/v1/openapi.json` | the API listed as JSON (OpenAPI 3), no key needed |

The player answer: `user_id`, `name`, `level`, `first_seen_at`, `last_seen_at`, `period`, `map` and `stats` (games,
wins, losses, games by map and mode, hours, estimated deaths, speeds, time stopped / upside down / near teammates and
enemies, left early, arm, payload push / block, emotes). Not shared: heatmaps, bios, Discord ids, pings, loadouts and
match-by-match data. Stats hidden from players (admin.bat hide-stats) stay hidden. A merged id answers with its main
player. Errors are `{"error_code", "message"}`: 401 `api_key_missing` / `bad_api_key`, 404 `not_found`, 429
`rate_limited` (with `Retry-After`).

## Limits
Per key 30 requests a minute (bursts up to 60) and 1,000 an hour, plus the site's own limit per address. Answers are
`private, no-store`: Cloudflare never keeps them.

## Cloudflare
Bot Fight Mode (Setup.MD) may challenge scripts before they reach the server. Test a key from a script after the
update; if it gets a Cloudflare challenge page instead of JSON, Bot Fight Mode has to be turned off (on the free plan it
cannot skip one path), leaving the app's own guard, the per-key limits and the WAF rate-limiting rule.
