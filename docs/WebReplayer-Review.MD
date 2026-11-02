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
- **Status:** Done 2026-11-02 (meshes built and checked against replay data; not yet viewed in a browser, which is Phase 4). Details and rebuild steps: `app/tools/maps3d/README.md`.
- **Result:**
  - `app/frontend/public/maps3d/{surge,fission,dyson,combustion}.glb`, in replay coordinates (metres, x/y/z as `head.position`, Y up). The placement is baked in, so no offsets table is needed.
  - 15.3 MB of FBX became 2.96 MB of GLB (surge 1.05 MB, just over the 1 MB aim). This came from weld, light meshopt simplification (about 0.1 m) and `KHR_mesh_quantization`.
  - No Draco or meshopt decoder is needed: a WASM decoder would need a CSP change.
  - There are no normals; render with `flatShading`.
- **Provenance:**
  - The meshes were exported from Maya 2019 by the upstream author on 2021-12-26.
  - Their numeric part names suggest they were extracted from the game's hologram minimaps and re-coloured.
  - The repo's MIT license (inherited copyright lines from three-fbx-viewer) says nothing separately about the meshes.
  - The old replayviewer.ecranked.com served the same files. **Publishing them is the owner's decision** (Open questions).
- **Placement:**
  - Upstream `EC_MAPS` is kept for surge, dyson and fission. A fit found no worthwhile change for surge and dyson, and the change it wanted for fission put 23 % of heads under the floor.
  - Combustion gets a fitted correction on top of upstream's `rotation.y = 80` rad: x -1.25 m, z +2.06 m, yaw +2.8°, scale 0.990. Its median head-to-surface distance went from 1.20 to 0.75 m on held-out positions, and its capture point mesh is 0.7 m from the centre measured from replays.
  - The height is not fitted: a free height fit pulled floors up to head height (14–32 % of heads under the floor).
  - Team colour zones match the side each team starts on, so nothing is mirrored relative to the data.
- **Check (`app/tools/maps3d/check.mjs`, 10 other replays per map):** median head-to-surface distance surge 0.95 m, fission 1.04, dyson 1.21, combustion 0.83. Heads under the floor: 0–3.5 %.
- **Later (Phases 4 and 9):**
  - Handedness was settled from the data (right-handed, as in three.js: no mirror).
  - The backdrop plates and load-in rooms are cropped at build time: 2.47 MB in total now.
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
- **Status:** Done 2026-11-02.
  - The parser keeps `head.forward` and the hand positions (`PlayerFrame.head_forward`, `lhand`, `rhand`). `PARSER_VERSION` stays 3, so **nothing is reprocessed**.
  - `app/backend/tracks3d.py` writes `tracks3d.bin` next to `tracks.bin` from the same single pass over the frames (`Recorders`). It holds 5 Hz head x/y/z (int16 dm), yaw (uint8), pitch (int8 °), team, hands (format 2), and the payload cart position per sample in the header.
  - **Low CPU (user, 2026-11-02: "whatever is the most efficient / low CPU usage"):** matches processed before 3D playback get their file **on first view**. The build reads the replay once (no stats) in the worker's below-normal-priority processes, about 1 s per 10-minute match (0.6–1.0 s measured on 71–110 MB replays). There is one build per replay, however many visitors ask, and files in an older format are rebuilt the same way. Only matches someone opens cost anything, instead of a full-archive reprocess.
  - **Measured on 8 real replays:** 140–210 KB per 10-minute match with hands.
  - Tests in `tests/backend/test_tracks3d.py`.
- **Goal:** A derived per-match file with everything 3D needs and nothing more.
- **Tasks:**
  - Have `_player` also keep `head.forward` (yaw/pitch are enough). Bump `PARSER_VERSION` (`app/parser/__init__.py`).
  - Add a `tracks3d.bin` next to `tracks.bin`, at 5 Hz to start (configurable). Per sample, store x/y/z as int16 dm, yaw as uint8 (1.4° steps), pitch as int8, plus team.
  - Have gear stay in `tracks.bin`, and the 3D file take samples from the same frames as `TrackRecorder.add` (`app/backend/tracks.py:51`).
- **Budget:** about 9 bytes per player per sample. At 10 players, 5 Hz and 10 min that is about 270 KB raw, which is acceptable after zlib (to be measured).
- **Done when:** a full reprocess writes the file for every match, and round-trip tests show the quantisation error stays under 0.1 m and 2°.

### Phase 3 — API endpoint
- **Status:** Done 2026-11-02.
  - `GET /api/matches/{id}/playback3d` returns: map, model URL, play extent, hz, samples, payload cart positions, route / capture point in metres, and per player x/y/z/yaw/pitch/team.
  - It is cached and gzipped like the other match endpoints: 137–159 KB for a 9–12 minute match with 10–12 players.
  - A match without a file gets one built while the request waits (up to 25 s, then 503 `tracks3d_building`). It answers 404 `no_tracks3d` only when the replay cannot be read.
  - The model URL carries `?v=<release>`, and `/maps3d/` is served `immutable`, so each visitor (and Cloudflare) fetches a map once per release.
  - Documented in `docs/Architecture.MD`; tested in `test_gui_api.py`.
- **Goal:** `GET /api/matches/{id}/playback3d`.
- **Tasks:**
  - Return world-space metres plus yaw/pitch, `hz`, `samples`, the map key and the player list (names and aliases as in `_playback`). Leave out events and gear, which the client already gets from `/playback`.
  - Use `cached_response` like the other match endpoints.
  - Consider a binary body (`application/octet-stream`, typed arrays) if JSON is too big.
- **Rules:** derived data only, with no frames or replay bytes. Read-only, so the existing middleware needs no change.
- **Done when:** the endpoint is documented in `docs/Architecture.MD`, tests in `tests/backend/` cover a fixture, and it returns 404 `no_tracks3d` for matches that have not been reprocessed.

### Phase 4 — Frontend scaffold
- **Status:** Done 2026-11-02.
  - `three` 0.181.0 (pinned) is added. `components/Map3D.tsx` is a lazy chunk (622 kB, 162 kB gzipped) that is downloaded only when someone opens 3D; the main bundle has no three.js.
  - A "2D map / 3D" switch on the Playback tab is kept in the address as `?view=3d`. The match id reaches `PlaybackView` as `matchId`.
  - **Handedness settled from the data:** in replays `left = up × forward` (138 of 138 head samples), which is the same right-handed convention as three.js, so the raw coordinates are drawn as they are, with no mirror.
- **Goal:** A 3D toggle on the Playback tab that loads without slowing anything else.
- **Tasks:**
  - Add `three` (current release) to `app/frontend`.
  - Add a new `components/Playback3DView.tsx`, loaded with `React.lazy`, so three.js stays out of the main chunk.
  - Add a "2D / 3D" switch in `PlaybackTab` (`pages/MatchPage.tsx:307`), remembered in the URL as `?view=3d`.
  - Add `getPlayback3d` plus types to `src/api.ts`, which sends `X-EchoVR` like every request.
- **Done when:** the map mesh renders with orbit controls on all four maps, and the main bundle size is unchanged (compare the `vite build` output).

### Phase 5 — Playback engine
- **Status:** Done 2026-11-02.
  - The existing time-based clock (`useClock` in `PlaybackView.tsx`) already did play, seek, step and speed. The 3D stage reads the same clock, so 2D and 3D share the controls, scrubber, event markers and time; switching views keeps the moment.
  - **3D interpolation:** samples glide at 5 Hz, except across jumps over 3 m (respawns). Yaw turns the short way round.
- **Goal:** Replace everything in upstream bugs 2–6 with one correct clock.
- **Tasks:**
  - Use a time-based clock (`requestAnimationFrame` plus elapsed time × speed).
  - Interpolate linearly between samples (slerp yaw).
  - Add seek, scrub, rewind and step, with speeds 0.25×–8×.
  - Move the clock out of `PlaybackView.tsx` into a shared hook (for example `usePlaybackClock`), so 2D and 3D use the same controls and event markers, and switching views keeps the time.
- **Done when:** seeking anywhere is instant, real-time playback lasts `duration_s` (±1 %), and toggling 2D↔3D keeps the time.

### Phase 6 — Player rendering
- **Status:** Done 2026-11-02.
  - **Player model:** head, body and a white facing cone (yaw and pitch) in the site's team colours. The picked player gets a white ring.
  - **Labels:** CSS2D name labels show the loadout swap for 3 s and turn red for 3 s after a death.
  - **Skulls** appear for 5 s at the player's last 3D position.
  - **Trails** are 3D segments in team or speed colour; respawn jumps are left out.
  - Absent players are hidden, and everything is disposed on unmount.
  - Labels show the icon of the weapon held now.
  - **Hands** (a toggle, on by default): small spheres in team colour with arms from the shoulders, which show aiming and throwing.
- **Goal:** Players that are easy to read in 3D.
- **Tasks:**
  - Draw team-coloured capsules (the site's team colours, not the upstream hex values) with a facing cone.
  - Add name labels that always face the camera (CSS2DRenderer or troika-three-text) and fade with distance.
  - Optionally add a weapon icon from the gear tables.
  - Show `death_est` events as skulls with the 2D view's icon, and hide players while they are absent.
  - Create players and remove them on join and leave, disposing of their resources (upstream bugs 9–10).
- **Done when:** a mid-match join or leave renders correctly, and the heap stays flat over a 10-minute replay (DevTools).

### Phase 7 — Cameras
- **Status:** Done 2026-11-02.
  - **Modes:** orbit, top-down, follow (a chase camera 7 m behind and 4 m above, looking down at the player) and first person (from head position + yaw / pitch).
  - **Keys and clicks:** C cycles the camera, 1–9 / 0 pick a player in roster order, Esc lets go; clicking a player in 3D picks them.
  - **See-through map:** in follow and first person the map turns see-through (28 %). The mesh is a coarse hologram (about 1 m), so a head-height camera often sits inside a slab and showed only grey.
  - The picked player's own model is hidden in first person.
- **Goal:** Ways of viewing that a 2D map cannot offer.
- **Tasks:**
  - **Orbit** (default).
  - **Top-down orthographic**, matching the 2D view.
  - **Follow player:** third person, smoothed.
  - **First person:** from the head position and yaw/pitch, which is only as good as 5–10 Hz allows.
  - **Selection:** click a player to focus them, use 1–0 to pick a player, Tab to cycle and Esc to go back to orbit.
- **Done when:** every camera works through a seek and through a death or respawn of the followed player.

### Phase 8 — Objective and event overlays
- **Status:** Done 2026-11-02.
  - **Payload:** the route is drawn at the height of the nearest recorded cart position, with the travelled part in the attacker's colour. The cart sits at its recorded 3D position.
  - **Capture point:** a ring at floor height (from heads standing on the point), with a progress arc in the leading team's colour.
  - **Banners:** "Round won" / "Checkpoint" banners appear for 3 s over the map, in both views.
  - Fights stay in the shared scoreboard ("⚔ Fight") and scrubber bands.
- **Goal:** Show the game state, not just dots.
- **Tasks:**
  - Draw the payload route as a 3D line, with the cart placed along it from the `payload_distance` series.
  - Show the capture point ring coloured by the points series.
  - Add round and checkpoint banners from `round_won` / `payload_checkpoint`.
  - Show contest highlights and the fight detection already in `PlaybackView.tsx`.
- **Reuse:** `objects` and `series` from `/playback` (`_map_objects` in `app/backend/api/matches.py`).
- **Done when:** overlays match the 2D view at the same time for a payload match and a capture-point match.

### Phase 9 — Performance and robustness
- **Status:** Done 2026-11-02, apart from what is listed below.
  - **Rendering:** a single `requestAnimationFrame` loop that draws only when something changed (a paused view does no GPU work), with the pixel ratio capped at 2.
  - **Fallbacks:** if WebGL is missing, or the chunk fails or crashes (error boundary), the view says so and offers the 2D map. A map without a model shows the players over a grid.
  - **Phones:** on narrow screens the stage is 4:5, and touch orbit / pinch works.
  - **Smaller meshes:** cropped to the play area at build time, now 2.47 MB in total.
  - **Not done:** instanced meshes (at most 14 players, so they are not needed). Frame rate was checked only in headless Chrome with software WebGL, not on a real GPU.
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
- **Status:** Done 2026-11-02, apart from what is listed below.
  - **Deep links:** `?tab=playback&view=3d&cam=<orbit|top|follow|first>&player=<user id>&t=<s>&until=<s>`.
  - **Copy link / Copy clip:** "Copy link" copies the current moment; "Copy clip" copies the last 10 s. A clip link stops playback at `until`.
  - **Reduced motion:** the chase camera jumps instead of gliding, and the banner does not animate.
  - **Credit:** ec-web-replayer (MIT) is credited in the 3D footnote.
  - **3D compare:** `?vs=<match>&view=3d&cam=` shows both matches in 3D on the shared clock, with one camera picker for both.
  - A separate settings panel was not added: the existing trail / label / swap / hands toggles and the camera picker cover it.
- **Goal:** Make it worth sending to someone.
- **Tasks:**
  - Deep links `?view=3d&t=<s>&cam=<mode>&player=<id>`, plus a "copy link at this moment" button.
  - Shareable clips (a start and end time range).
  - A settings panel: labels, trails (3D ribbons), speed, camera smoothing.
  - Keyboard help (`?`) and reduced motion (no auto-orbit).
  - 3D compare (`?vs=`), as a stretch goal.
  - Credits for ec-web-replayer and the map mesh source on the About page.
- **Done when:** a pasted link opens at the same moment, camera and player.

## Optional improvements (2026-11-02, after the 10 phases)
- **Done:**
  - 3D compare.
  - Gear icons in the 3D labels.
  - Hands and arms (tracks format 2).
  - 3D tracks built on first view instead of a full reprocess.
  - Map models cached for good.
- **Not possible yet: better map models.**
  - The only meshes available are the ec-web-replayer hologram minimaps, which are accurate to about 1 m.
  - Better geometry needs a new source, for example models exported from the game files, if that were allowed.
  - Until then, follow and first person keep the see-through map.

## Open questions
- **Mesh provenance (Phase 1 finding):** the FBXs were built in Maya by the upstream author, most likely from meshes extracted from the game's hologram minimaps.
  - **User, 2026-11-02:** "whatever is the most efficient / low CPU usage". So they are kept: they are static files the browser draws, cost the server almost nothing, and are cached for good.
  - Whether publishing them is acceptable remains the owner's call. Deleting `app/frontend/public/maps3d/` makes the view show players over a grid.

## Verification (2026-11-02)
- **Backend:** 279 tests pass (new: `test_tracks3d.py`, `test_playback3d`, `test_playback3d_built_on_first_view`).
- **Map meshes:** `app/tools/maps3d/check.mjs` passes on 10 replays per map.
- **Test site:** a local copy on 4 real replays (one per map, temporary data folder) answered `/playback3d` on every map.
- **Headless Chrome** (software WebGL), with no console errors:
  - orbit (surge), top-down (dyson), follow (combustion: capture ring, trails, picked ring) and first person (fission: cart, route, players) all render;
  - 2D → 3D → 2D switching works (the 2D canvas redraws);
  - C / 1–0 / Esc and play / pause work;
  - `?t=` and clip `?until=` work.
- **Optional improvements**, checked on the test site with no console errors:
  - a missing file was built on first view in 3.5 s, while the import queue was busy;
  - outdated files were rebuilt;
  - the model is served with `Cache-Control: immutable`;
  - hands and weapon icons render, and 3D compare renders both maps.
- **Not checked:** a real GPU and a phone.
- **Sample rate and storage:** is 5 Hz enough for first person, or should it be 10 Hz? Measure the `tracks3d.bin` size on real matches before choosing.
- **Pose:** should hands be added too (`lhand`/`rhand` position)? It roughly triples the storage but would show aiming and throwing.
- **Reprocessing:** a new parser version means one full reprocess of every replay.
