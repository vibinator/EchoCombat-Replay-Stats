# Phases

Last updated: 2026-10-29 (Phase 2 complete)

## Phase 1 — Discovery and reference extraction
- **Status:** Done (MVP scope awaiting user confirmation)
- **Goal:** Know the replay format, available data, and old-app features.
- **Inputs:** Direct read-only inspection of reference code + 16 sample replays (D6).
- **Tasks:** Record format + fields in ReplayData.MD; classify old features (Retain/Simplify/Defer/Remove) in Decisions.MD; define MVP scope.
- **Done when:** Format decodable on paper; field→stat mapping filled; MVP scope confirmed by user.
- **Depends on:** —
- **Notes:** Combat-only API: no kills/goals/possession. Payload winner derivation open (ReplayData Q5).

## Phase 2 — Architecture and data model
- **Status:** Done (pending user sign-off) — 2026-10-29
- **Goal:** Final pipeline design and DB schema.
- **Tasks:** Finalise Architecture.MD endpoints; finalise DataModel.MD tables from confirmed fields.
- **Done when:** Schema and API agreed.
- **Depends on:** 1
- **Notes:** Architecture.MD (API v1, validation, worker) and DataModel.MD (7 tables) finalised; Decisions D6–D13. Front-end extract (`reference/echocombat-extract.md`) reviewed → D14–D16. Redone 2026-10-29 against old backend routes (`htdocs/src/routes`): full profile stat set, period switch, leaderboard stats, per-player heatmaps, achievement rules (D17), loadout names.

## Phase 3 — Replay upload and storage
- **Status:** Complete 2026-10-29 (UI not yet checked in a browser by the user)
- **Goal:** Upload one or many `.echoreplay` files; validate; store file + metadata.
- **Tasks:** FastAPI upload/list/status/download/delete endpoints; size/extension/signature checks; hash-based dedupe; `replays` table; minimal React upload page with per-file status.
- **Done when:** Files land in `data/uploads`, rows in DB, status shown in UI; tests pass.
- **Depends on:** 2
- **Notes:** Upload was later replaced by import from the read-only share (D25, 2026-10-30): scanner + parallel worker + Import status page.

## Phase 4 — Replay parsing
- **Status:** Complete 2026-10-29
- **Goal:** Decode confirmed structure into in-memory frames/events.
- **Tasks:** Worker queue (moved from Phase 3; nothing to run before the parser exists); versioned parser module; error types (unsupported/corrupt/incomplete); tests with sample replays.
- **Done when:** Sample replays parse; bad files fail with clear errors.
- **Depends on:** 1, 3
- **Notes:** All 16 reference samples parse (≤ 2 s each). Two small samples copied to `tests/sample-replays/`. 35 tests. Delete refused (409) while a replay is processing (Windows file lock).

## Phase 5 — Conversion and statistics
- **Status:** Complete 2026-10-29 — step 3 (sample checks, payload winner Q5)
- **Goal:** Frames → match/player stats; persist.
- **Tasks:** Stats calculators for MVP set; store derived data; processing status.
- **Done when:** Stats for samples match expected values.
- **Depends on:** 4
- **Notes:** Matches the old app's own code exactly on 16 sample players (except D22 top-speed rule). Added payload winner / attacking team / push-block (D21). Stats v3, parser v2, 55 tests.

## Phase 6 — Website display
- **Status:** Complete 2026-10-30 (pending your browser check)
- **Goal:** Home, match list, match detail, player views.
- **Tasks:** Home (recent matches + player search); match list/detail; player page with profile stat set (DataModel) + match history; footer credit.
- **Done when:** User can upload and browse results end-to-end.
- **Depends on:** 5
- **Notes:** Verified via API/route checks with all 8 reference replays (temp data dir); not yet viewed in a browser. Added wins/losses and a Players search page.

## Phase 7 — Feature recreation and improvements
- **Status:** Complete 2026-10-30 (pages not yet viewed in a browser)
- **Goal:** Timeline, heatmaps (match + player), leaderboard (D15), filters, CSV/JSON export, capture-point progress per team, avg packet loss + emote count per player, remaining retained features.
- **Tasks (heatmaps, D18):** tracks file with weapon; `death_est` x/z; grid endpoint + cache; canvas renderer (team / weapons / deaths; all / team / player); verify map extents vs sample positions; minimap backgrounds.
- **Depends on:** 6
- **Notes:** Delivered: leaderboard (15 stats + loadout, period/map/min games), match timeline (objective chart + events), match + player heatmaps on minimaps (layout verified per map, D29), CSV/JSON export (match, player), capture time per team, packet loss, emotes. Tracks as binary (D30). Replay download removed (D28). Stats v6, parser v3 → full reprocess. 81 tests. Heatmap geometry checked by rendering API output over the minimaps; the React pages themselves not yet viewed (no browser tool in session).

## Phase 8 — Achievements
- **Status:** Complete 2026-10-30 (pages not yet viewed in a browser)
- **Goal:** Achievements (D17).
- **Inputs:** Rule list in old `stat.js` (found); thresholds = rule text (D17); old ecranked.com badge images in `app/images/` (76 files, user-supplied 2026-10-30): 23 subject icons (4 maps, capture_point, payload, deaths, 12 gear items) each in 3 variants (base, `_daily`, `_weekly`; A: = cumulative / 24-hour / 1-week groups), tier frames `white|bronze|silver|gold` = progress levels 25 / 50 / 75 / 100 % (user, 2026-10-30; `_lock` = level not reached), misc icons (checkmark, x, verified, moderator, crown, `combat_background.jpg`).
- **Tasks:** Rule table in code; achievements endpoint + profile tab; achievement leaderboard.
- **Done when:** Achievement progress matches rules for sample data.
- **Notes:** 75 rules (D31); player-page section with old badge icons + tier emblems (icon overlay on the emblem did not fit, so the emblem sits in the corner); `stat=achievements` leaderboard; 9 tests. Also: detailed Import page (D32).
- **Depends on:** 7

## Phase 9 — GUI improvements, admin, repair
- **Status:** Complete 2026-10-30 (pages not yet viewed in a browser)
- **Goal:** All 20 GUI ideas (D37); admin challenge period (D33); lossless player merge (D34); heatmap resolution + gear / loadout / speed layers (D35); repair damaged replays (D36); home global stats, players-seen graph, matches per map.
- **Done when:** Features built, tested, end-to-end checked on real replays.
- **Notes:** 120 tests. Merge round-trip test proves merge → undo restores every player's stats exactly. High-res minimaps re-oriented per map by data. Stats v7 / tracks v2 → one more full reprocess.
- **Depends on:** 8

## Future — 3D playback
- **Status:** All 10 phases built 2026-11-02 (3D view on the Playback tab: `components/Map3D.tsx`, `GET /api/matches/{id}/playback3d`, `tracks3d.bin`, meshes from `app/tools/maps3d/`). Optional improvements also done (3D compare, gear icons, hands, 3D tracks built on first view: no reprocess). Not yet seen on a real GPU or phone.
- **Plan:** [WebReplayer-Review.MD](WebReplayer-Review.MD): review of duncancarroll/ec-web-replayer and a 10-phase port of 3D playback into the Playback tab (derived 3D tracks only; no raw replay downloads).
