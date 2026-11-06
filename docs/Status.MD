# Status

Last updated: 2026-10-30 — current release **Beta 2** (see Changelog.MD; every update gets the next beta number)

## Objective
Build a new, simplified web app that recreates the useful functionality of the old Echo VR replay app (upload → parse → stats → display). Reference material outside `EchoVR-Replay-Stats\` is read-only; it may be read directly (Decisions D6).

## Confirmed decisions
- Server-side parsing (D1)
- Python (FastAPI) backend + parser, React (Vite, TS) frontend, SQLite (D2, D3)
- Replays only from the read-only share `Z:\ECRanked\Replays`; no uploads (D25)
- No user accounts in v1 (D5)
- Echo Combat `.echoreplay` only, zip or plain text (D7); players keyed by userid as string (D8); no legacy `.ecrreplay` (D9)
- No dependency on the offline ECRanked API (D16)

## Completed
- Beta 1 — read-only website + admin console (`admin.bat`), achievements follow their text + 21 new ones, per-player and 0.1 m heatmaps, hex gear codes fixed, performance pass (Changelog.MD)
- Folder structure + initial docs
- Phase 1 — replay format decoded and documented (ReplayData.MD); old features classified (Decisions.MD)
- Phase 9 — all 20 GUI ideas, admin (challenge period, lossless merge + undo), heatmap v2 (0.25 m, gear / loadout / speed layers, high-res minimaps), repair damaged replays, home global stats + players seen + matches per map
- Phase 8 — achievements (75 rules, badges, leaderboard stat); detailed Import page (stages, live files, rate, ETA)
- Phase 7 — leaderboard, timeline, heatmaps (match + player; team / weapon / deaths), CSV/JSON export, capture time, packet loss, emotes; replay download removed (D28)
- Share import (D25): scanner (5 min), 8-process worker newest first, crash recovery, Import page; old-format fixes (D26). Smoke test on the share: 2.5 replays/s, 0 failures; 24 / 24 sampled 2021–2026 files parse
- Phase 6 — website: home, matches (filters, paging), match detail, players search, player profile (period/map), upload; `run.bat` launcher
- Phase 5 — stats + storage: all MVP stats, timeline events, payload winner/attacking team/push-block; verified against old `skims.py` on 4 samples
- Phase 4 — parser (`app/parser`, v1) + background worker; all 16 samples parse; bad files fail as unsupported/corrupt/incomplete
- Phase 3 — upload + storage: backend (12 tests), React upload page (drag/drop, progress, per-file results, uploads table with download/delete), FastAPI serves built frontend
- Phase 2 — API v1 and pipeline (Architecture.MD); 7-table schema (DataModel.MD); front-end extract reviewed (D14–D16); redone against old backend routes (D17, profile set, leaderboards, achievements, loadout names)

## In progress
- —

## Next
- You: run `run.bat`; let the import run (~3 h for 29k files, newest first); check pages + Import page; report anything wrong
- You: run `run.bat`, check the pages (none viewed in a browser yet) — especially match Timeline / Heatmap tabs, player heatmap + achievements, Leaderboard, Import page
- After that: all planned phases are done; next work comes from your feedback

## Blockers / risks
- Import needs the share online; replays before 2022 Q4 lack payload data (winner unknown) and before 2021 Q4 lack loadouts
- Reference `HeatMap.py` contains a Discord webhook URL with its token (commented out) — never copy it; revoke it if still live
- No kills/damage/stuns/possession in the Combat API; "core player stats" are movement/presence/loadout stats (old app's set)
- Deaths are an out-of-bounds heuristic (estimated) — also feeds profile "Total Deaths" / "Deaths/Game"
- Payload-map winner not directly available (ReplayData Q5)
- Timestamp timezone unknown (Q6)
- Front-end extract is saved as `docs/reference/echocombat-extract.md` (no `old-frontend-ecranked.md` exists)
- Friendly names unknown for newer loadout codes (rifle, smg, chain, magnum, loc, dot) → shown as raw codes
- Flaky test (2026-11-06): `tests/backend/test_remote.py::test_damaged_track_files_are_left_out_not_saved` failed once in five full runs, passes alone; ignore unless it reoccurs

## Awaiting your answer
- —

## MVP scope (Phases 3–6) — approved 2026-10-29
- Upload many `.echoreplay` files with per-file status; reject Arena/corrupt files clearly
- Match: map, mode, date, duration, rounds/capture/payload progress, winner (capture-point only), contested time
- Per player: team, play time, left early, ping, avg/top speed, % stopped / upside down / near mate / near enemy, dominant arm, est. deaths, loadout usage
- Pages: home (recent + search), match list, match detail, player profile (full old stat set, day/week/month/all)
- Phase 7 (done): timeline, heatmaps, leaderboard, exports; Phase 8: achievements

## Scope / architecture changes
- Possession and Arena stats (goals/saves/etc.) dropped: not present in Combat replays
- Input is `.echoreplay` (not `.replay`), read from the share; web upload removed (D25)
- Positions kept in per-replay tracks files, not the DB (D11)
- Worker queue moved Phase 3 → Phase 4
- Leaderboards moved Defer → Phase 7 (D15); Achievements Defer → Phase 8 (D17)

## Changelog
- 2026-10-29 — Project scaffolded; stack and v1 constraints decided
- 2026-10-29 — Phase 1 + 2 completed via direct inspection of reference code and samples
- 2026-10-29 — Front-end extract reviewed; D14–D16; home/leaderboard pages; profile stat set
- 2026-10-29 — Phase 2 redone against old backend routes; D17; profile/leaderboard/achievement/loadout-name findings
- 2026-10-29 — Achievement thresholds: use rule text (D17)
- 2026-10-29 — Flamingo Challenges = achievements (confirmed)
- 2026-10-29 — Graphs = heatmaps; `HeatMap.py` reviewed; D18; heatmap features classified
- 2026-10-29 — Minimaps found in old `htdocs/public/`, copied to `docs/reference/minimaps/`; aspect check done
- 2026-10-29 — MVP approved; Phase 3 step 1 (backend upload/storage) done
- 2026-10-29 — Phase 3 complete (upload page + static serving)
- 2026-10-29 — Phase 4 complete (parser v1 + worker, D19)
- 2026-10-29 — Phase 5 step 1 (tables + match/presence stats)
- 2026-10-29 — Phase 5 step 2 (all MVP stats + events); old map bounds found suspect
- 2026-10-29 — Old bounds kept (D20); full field survey of new plain-text replays; payload semantics + winner rule found
- 2026-10-29 — Phase 5 complete (payload stats D21, top speed D22, schema rebuild D23)
- 2026-10-30 — Reviewed 2 large replays (99/116 MB): new codes drone/buff, custom team labels, ping 999, payload overtime; all parse + stats in < 3 s
- 2026-10-30 — Gear table received (incl. cut gear): `docs/reference/gear-table.json`, `app/backend/gear.py`
- 2026-10-30 — Ping 999 excluded from average (D24, stats v4)
- 2026-10-30 — Phase 6 complete (pages + match/player API + run.bat)
- 2026-10-30 — Uploads replaced by read-only import from Z:\ECRanked\Replays (D25); mode from map (D26); stats v5
- 2026-10-30 — Old ecranked.com achievement images received (`app/images/`), noted as Phase 8 input
- 2026-10-30 — Restart persistence verified (test + real share: 95/95 untouched); D27
- 2026-10-30 — Phase 7 complete (D28 no download, D29 heatmap layouts, D30 binary tracks; stats v6, parser v3)
- 2026-10-30 — Achievement tier frames confirmed as progress levels (25/50/75/100 %)
- 2026-10-30 — Phase 8 complete (D31); Import page per-stage detail (D32)
- 2026-10-30 — Achievements moved to their own page `/achievements` (catalogue, search, top players, per-player view); player page keeps a summary
- 2026-10-30 — Phase 9: GUI round 2 (D37), admin D33, merges D34, heatmaps D35 (stats v7), repair D36
