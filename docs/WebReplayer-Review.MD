# 3D replay viewer: review of ec-web-replayer and port plan

## Summary
- [duncancarroll/ec-web-replayer](https://github.com/duncancarroll/ec-web-replayer) (MIT; a fork of limitlesspro/three-fbx-viewer) is an "extremely alpha" Three.js viewer for Echo Combat `.echoreplay` files. Reviewed 2026-11-02 at `master` (41 commits).
- **It cannot run against anything live.**
  - It downloads replays from `https://ecranked.ddns.net/api/v1/replay/<uuid>/download`, which is offline.
  - Its demo (`ec-web-replayer-ycfsx.ondigitalocean.app`) no longer resolves in DNS.
  - Dropping a local file still works.
- **Worth keeping:** the four combat minimap meshes (`assets/models/maps/*.fbx`) and their placement offsets (`EC_MAPS`). Also the idea of a 3D view over replay positions.
- **Not worth keeping:** the playback engine, the build setup and the UI code (see the bugs below).
- **Decision (user, 2026-11-02):** port 3D playback into this site instead of fixing the upstream repo. The plan is the 10 phases below. None are built yet.

## Upstream review

### Architecture
- **Build:** browserify + budo, with esmify/glslify transforms. Three.js `^0.110` (2019). `electron/` has a desktop wrapper. `build/bundle.js` (2 MB) is committed.
- **`src/app.js`:**
  - It reads hash params (`#replay=<uuid>`, `#model=`, `#preset=`, `#cameraPosition=`) and accepts drag-and-drop through `simple-dropzone`.
  - For `replay` it does `fetch(ecRankedApi + uuid + "/download")`, wraps the blob in a `File` and hands it to the viewer.
  - It shows errors with `window.alert`.
- **`src/viewer.js` (35 KB):** a `Viewer` class, but playback state lives in module-level variables, so it is a singleton.
  - The zip goes through `unzip-stream` → `readline-browser`. Each line is split at the first tab into a timestamp and the `/session` JSON.
  - **Fields read:** `map_name`, `teams[0..1].players[]`, and per player only `userid`, `name` and `body.position`. Head, hands, facing, velocity, gear and payload are all ignored.
  - **Players:** a 0.4 m `SphereGeometry` in blue `0x0058cc` or orange `0xeb5e34`, with a `SpriteText2D` name 4 m above it. FBX player models are loaded in code that is commented out.
  - **Maps:** `FBXLoader` places the minimap with the offsets below. It uses `OrbitControls`, an HDR/cube environment map and a vignette background.
- **`src/playback_controls.js`:** a music-player-style bar (play, prev/next = slower/faster, a progress bar, a title). It was adapted from an audio-player template, and `songs`/`songIndex` are still left over.

### Map assets and offsets
| `map_name` | Name | File | Position | Rotation | Scale |
|---|---|---|---|---|---|
| `mpl_combat_gauss` | Surge | `surge_minimap.fbx` (5.4 MB) | (21.8, -1.37, 45.7) | 0 | 0.56 |
| `mpl_combat_fission` | Fission | `fission_minimap.fbx` (3.0 MB) | (-0.5, -12.43, 21) | 0 | 0.588 |
| `mpl_combat_dyson` | Dyson | `dyson_minimap.fbx` (3.7 MB) | (0, -3.95, 0) | 0 | 0.92377 |
| `mpl_combat_combustion` | Combustion | `combustion_minimap.fbx` (3.2 MB) | (0, -83.3, 26.2) | y = **80** | (-0.588, 0.588, -0.588) |

- Position is applied as `(z, y, x)`, so the axes are swapped, and scale as `(-x, y, -z)`, so the mesh is mirrored. The x/z swap matches what `ReplayData.MD` ("Map bounds") found for the old bounds and the minimap orientation.
- Combustion's `rotation.y = 80` is passed to Three.js, which takes radians. 80 rad ≈ 4584° ≈ 264°, so this is almost certainly a degrees/radians mistake that happened to look close to right.
- The license is MIT for the repo. Whether the meshes themselves came from Ready At Dawn (game assets) is unknown, so this has to be checked before shipping them (Phase 1).

### Bugs and limitations found
| # | Where | Problem |
|---|---|---|
| 1 | `app.js` | Its data source (`ecranked.ddns.net`) is offline. |
| 2 | `viewer.js onLineRead` | The pause check runs after the counter increments, so about two lines are processed per tick (off-by-one). |
| 3 | `viewer.js play/stepForward/stepBackward` | Speed comes from halving or doubling a `setInterval` (100 ms base), not from the frame timestamps. Since replays are about 15–20 Hz and not fixed, playback speed drifts. |
| 4 | `viewer.js play` | It is not idempotent: a second call leaks an interval. |
| 5 | `viewer.js setProgress / rewindToBeginning` | Seeking is a `// TODO` and rewind is a no-op. The stream is forward-only, so neither can work without buffering the frames. |
| 6 | `viewer.js load` | The returned Promise never resolves (the `resolve` calls are commented out). |
| 7 | `viewer.js setContent → updateGUI` | `addGUI()` is commented out, so the GUI folders are `null` and `updateGUI()` throws. The environment, encoding and display updates after it never run. |
| 8 | `viewer.js` | An unknown `map_name` throws on `EC_MAPS[map].name`. |
| 9 | `viewer.js updatePlayerPositions` | `.get(userid).position` has no null check. It crashes when a player is replaced by another (same count, new userid). |
| 10 | `viewer.js` | Players who leave are never removed. Their meshes and label textures are never disposed. |
| 11 | `viewer.js onLineRead` | The JSON is sliced from the tab itself, not after it. It works because `JSON.parse` skips whitespace, but it is off by one. |
| 12 | `viewer.js` | It uses `renderer.gammaOutput` and `physicallyCorrectLights`, both removed in current Three.js. It also sets globals `window.THREE/scene/renderer`. |
| 13 | `playback_controls.js setProgress` | It sets the bar width in px while `updateProgress` uses %, and `viewer.setProgress` is a stub. |
| 14 | `app.js` | It still calls `view()` after "no .echoreplay found"; uses the deprecated `keyCode`; leaves debug `console.log`s in. |
| 15 | `package.json` | Build tools are in `dependencies`. The `clean` script is broken (`rm bundle.js rm -Rf build/`). `deploy` uses the retired `now` CLI. |

## Gap analysis against this site
- **No raw replays are served, by design.**
  - `app/backend/middleware.py:34-35` returns 404 for any path matching `guard.REPLAY_FILE` (`app/backend/guard.py:36`).
  - `docs/Architecture.MD` ("API (v1)") states there are no replay-download endpoints (D25, D28).
  - So the upstream data path (download the whole `.echoreplay` and parse it in the browser) is **not an option**. The 3D view must use derived tracks, like the 2D view does.
- **What exists today:**
  - `GET /api/matches/{id}/playback` (`app/backend/api/matches.py:360-400`) returns 2 Hz `[u, v, team]` points in minimap image space, plus speed, loadout runs, events (`PLAYBACK_EVENTS`), map objects, gear names and series.
  - It is built from `data/processed/<replay_id>/tracks.bin` (`app/backend/tracks.py`, format v2: x/z as int16 dm, weapon/tacmod/ordnance/team as uint8, about 30 KB per match).
- **What 3D needs that is missing:**
  - **Height (y):** not stored in tracks; only x/z are kept.
  - **Facing:** `app/parser/frames.py:122-141` `_player` keeps `head.position`, `body.up` and `velocity`. It drops `head.forward`/`left`/`up`, `body.forward` and the hands.
  - **Smoothness:** at 2 Hz a 3D view looks jumpy even with interpolation. 5–10 Hz is a better target.
  - **World coordinates:** the existing endpoint returns minimap `u, v`, but 3D wants metres.
- **What can be reused as-is:**
  - Events, including `death_est` with an x/z position.
  - Gear tables, map objects (payload route, capture point), timeline series and duration.
  - Name and alias resolution from `_playback`.
  - On the frontend: `PlaybackView.tsx` (controls, trails, death skulls, fight detection), the `getPlayback` client and types in `src/api.ts`, and the Playback tab in `pages/MatchPage.tsx:307-334`.

## The 10 phases

### Phase 1 — Audit and map assets
- **Goal:** Map meshes the site is allowed to ship, that are light, and that are placed correctly in replay coordinates.
- **Tasks:**
  - Check where the upstream FBX meshes came from and their license. Credit duncancarroll (MIT).
  - Convert the FBX files to GLB with Draco/meshopt compression, aiming for under 1 MB each.
  - Re-derive the offsets in metres in a single coordinate convention, with no axis swap or mirror (bake them into the GLB).
  - Fix Combustion's rotation (degrees → radians, or bake it in).
- **Files:** `app/frontend/public/maps3d/<map>.glb` (new), a small offsets table in the frontend.
- **Reuse:** the extents and orientation notes in `docs/ReplayData.MD` ("Map bounds", "Heatmap image extents").
- **Done when:** sample head positions from 16 replays (the same check as the 2026-10-29 bounds study) land on the walkable mesh surfaces on all four maps.

### Phase 2 — 3D track data (backend)
- **Goal:** A derived per-match file with everything 3D needs and nothing more.
- **Tasks:**
  - Have `_player` also keep `head.forward` (yaw/pitch are enough). Bump `PARSER_VERSION` (`app/parser/__init__.py`).
  - Add a `tracks3d.bin` next to `tracks.bin`, at 5 Hz to start (configurable). Per sample, store x/y/z as int16 dm, yaw as uint8 (1.4° steps), pitch as int8, plus team.
  - Have gear stay in `tracks.bin`, and the 3D file take samples from the same frames as `TrackRecorder.add` (`app/backend/tracks.py:51`).
- **Budget:** about 9 bytes per player per sample. At 10 players, 5 Hz and 10 min that is about 270 KB raw, which is acceptable after zlib (to be measured).
- **Done when:** a full reprocess writes the file for every match, and round-trip tests show the quantisation error stays under 0.1 m and 2°.

### Phase 3 — API endpoint
- **Goal:** `GET /api/matches/{id}/playback3d`.
- **Tasks:**
  - Return world-space metres plus yaw/pitch, `hz`, `samples`, the map key and the player list (names and aliases as in `_playback`). Leave out events and gear, which the client already gets from `/playback`.
  - Use `cached_response` like the other match endpoints.
  - Consider a binary body (`application/octet-stream`, typed arrays) if JSON is too big.
- **Rules:** derived data only, with no frames or replay bytes. Read-only, so the existing middleware needs no change.
- **Done when:** the endpoint is documented in `docs/Architecture.MD`, tests in `tests/backend/` cover a fixture, and it returns 404 `no_tracks3d` for matches that have not been reprocessed.

### Phase 4 — Frontend scaffold
- **Goal:** A 3D toggle on the Playback tab that loads without slowing anything else.
- **Tasks:**
  - Add `three` (current release) to `app/frontend`.
  - Add a new `components/Playback3DView.tsx`, loaded with `React.lazy`, so three.js stays out of the main chunk.
  - Add a "2D / 3D" switch in `PlaybackTab` (`pages/MatchPage.tsx:307`), remembered in the URL as `?view=3d`.
  - Add `getPlayback3d` plus types to `src/api.ts`, which sends `X-EchoVR` like every request.
- **Done when:** the map mesh renders with orbit controls on all four maps, and the main bundle size is unchanged (compare the `vite build` output).

### Phase 5 — Playback engine
- **Goal:** Replace everything in upstream bugs 2–6 with one correct clock.
- **Tasks:**
  - Use a time-based clock (`requestAnimationFrame` plus elapsed time × speed).
  - Interpolate linearly between samples (slerp yaw).
  - Add seek, scrub, rewind and step, with speeds 0.25×–8×.
  - Move the clock out of `PlaybackView.tsx` into a shared hook (for example `usePlaybackClock`), so 2D and 3D use the same controls and event markers, and switching views keeps the time.
- **Done when:** seeking anywhere is instant, real-time playback lasts `duration_s` (±1 %), and toggling 2D↔3D keeps the time.

### Phase 6 — Player rendering
- **Goal:** Players that are easy to read in 3D.
- **Tasks:**
  - Draw team-coloured capsules (the site's team colours, not the upstream hex values) with a facing cone.
  - Add name labels that always face the camera (CSS2DRenderer or troika-three-text) and fade with distance.
  - Optionally add a weapon icon from the gear tables.
  - Show `death_est` events as skulls with the 2D view's icon, and hide players while they are absent.
  - Create players and remove them on join and leave, disposing of their resources (upstream bugs 9–10).
- **Done when:** a mid-match join or leave renders correctly, and the heap stays flat over a 10-minute replay (DevTools).

### Phase 7 — Cameras
- **Goal:** Ways of viewing that a 2D map cannot offer.
- **Tasks:**
  - **Orbit** (default).
  - **Top-down orthographic**, matching the 2D view.
  - **Follow player:** third person, smoothed.
  - **First person:** from the head position and yaw/pitch, which is only as good as 5–10 Hz allows.
  - **Selection:** click a player to focus them, use 1–0 to pick a player, Tab to cycle and Esc to go back to orbit.
- **Done when:** every camera works through a seek and through a death or respawn of the followed player.

### Phase 8 — Objective and event overlays
- **Goal:** Show the game state, not just dots.
- **Tasks:**
  - Draw the payload route as a 3D line, with the cart placed along it from the `payload_distance` series.
  - Show the capture point ring coloured by the points series.
  - Add round and checkpoint banners from `round_won` / `payload_checkpoint`.
  - Show contest highlights and the fight detection already in `PlaybackView.tsx`.
- **Reuse:** `objects` and `series` from `/playback` (`_map_objects` in `app/backend/api/matches.py`).
- **Done when:** overlays match the 2D view at the same time for a payload match and a capture-point match.

### Phase 9 — Performance and robustness
- **Goal:** Smooth on an ordinary laptop, and safe everywhere.
- **Tasks:**
  - Use instanced meshes for players and skulls, with one render loop and no `setInterval`.
  - Render on demand while paused and lower the pixel ratio on weak GPUs.
  - Fall back to the 2D view with a note when WebGL is unavailable.
  - Show a friendly message for unknown maps (upstream bug 8).
  - Support touch controls and a mobile layout.
  - Dispose of everything on unmount. Check the CSP (`app/backend/guard.py` `CONTENT_SECURITY_POLICY`) still allows workers or WASM if the Draco decoder needs them.
- **Done when:** 60 fps on a mid-range laptop at 4×, no console errors, and Lighthouse shows no regression on the match page.

### Phase 10 — Polish and sharing
- **Goal:** Make it worth sending to someone.
- **Tasks:**
  - Deep links `?view=3d&t=<s>&cam=<mode>&player=<id>`, plus a "copy link at this moment" button.
  - Shareable clips (a start and end time range).
  - A settings panel: labels, trails (3D ribbons), speed, camera smoothing.
  - Keyboard help (`?`) and reduced motion (no auto-orbit).
  - 3D compare (`?vs=`), as a stretch goal.
  - Credits for ec-web-replayer and the map mesh source on the About page.
- **Done when:** a pasted link opens at the same moment, camera and player.

## Open questions
- **Mesh provenance:** are the minimap FBXs made by the fan community or extracted from the game? This decides whether the site may host them (Phase 1).
- **Sample rate and storage:** is 5 Hz enough for first person, or should it be 10 Hz? Measure the `tracks3d.bin` size on real matches before choosing.
- **Pose:** should hands be added too (`lhand`/`rhand` position)? It roughly triples the storage but would show aiming and throwing.
- **Reprocessing:** a new parser version means one full reprocess of every replay.
