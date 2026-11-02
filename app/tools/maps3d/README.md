# 3D map meshes (3D playback, Phase 1)

Builds `app/frontend/public/maps3d/<map>.glb` (surge, fission, dyson, combustion) for the planned 3D playback view.
Plan and findings: `docs/WebReplayer-Review.MD`. This tool is not part of the app build or the Docker image. The GLBs are
committed, so run it only to rebuild them.

## Source and credit
- **Meshes:** the `*_minimap.fbx` files from [duncancarroll/ec-web-replayer](https://github.com/duncancarroll/ec-web-replayer). These are the same files the old `replayviewer.ecranked.com` served; a copy is in the workspace at `www.ecranked.com/replayviewer.ecranked.com/assets/models/maps/`.
- **How they were made:** exported from Autodesk Maya 2019 on 2021-12-26 (FBX metadata, `C:\Users\dunca\Desktop\...`), with hand-named colour materials ("Light Orange", "Capture Point Transparent"...).
- **Likely origin:** the parts have numeric names ("100.001", "1005"), which suggests they were extracted from the game's holographic minimaps and then re-coloured. If so, the shapes come from Echo VR (Ready At Dawn / Meta), not from the repo author.
- **License:** the repository is MIT ("Copyright (c) 2019 Pavel Kuznetsov", "Copyright (c) 2017 Don McCurdy", inherited from three-fbx-viewer / three-gltf-viewer). It does not say anything separately about the meshes.
- **Hosting:** the site already serves map images from the old ECRanked site (`public/minimaps/`) on the same basis. Whether to publish the meshes is the owner's call; see Open questions in the review doc.

## Coordinates
- The GLBs are in **replay coordinates**: metres, x / y / z exactly as `head.position` / `body.position` in the replay, Y up. Place players with no offset.
- **Placement:** upstream `EC_MAPS` (position applied as (z, y, x), scale as (-x, y, -z)), baked in.
- **Combustion** keeps upstream's `rotation.y = 80` (radians, which was probably meant as degrees) plus a fitted correction: x -1.25 m, z +2.06 m, yaw +2.8°, scale 0.990. Fitted 2026-11-02 to in-play head positions with height locked, because a free height fit pulls floors up to head height and put 14–32 % of heads under the floor. The correction is checked on held-out positions: median head-to-surface distance 1.20 → 0.75 m. Its capture point mesh is 0.7 m from the centre measured from replays (`app/backend/stats/map_objects.py`).
- **Other maps:** the same fit found no worthwhile correction for surge or dyson (< 0.6 m, < 0.5°). For fission it wanted a 12 % shrink that put 23 % of heads under the floor, so the upstream placement is kept.
- **Team sides:** the mesh's blue and orange zones are on the side each team starts on (checked against first in-arena positions), so nothing is mirrored relative to the data.
- **Handedness:** the replay data is right-handed (`left = up × forward` for every head sample checked), like three.js, so the raw coordinates render the way players saw the map.

## Format
- **Materials:** one primitive per FBX material: base colour (linear), alpha blend for the capture point volumes, emissive kept, double-sided.
- **No normals:** render with `flatShading: true`, which is the look of the in-game hologram minimaps. This also lets vertices weld.
- **Processing:** weld → meshopt simplify (error 0.0005 of the mesh size, about 0.1 m; borders locked) → `KHR_mesh_quantization` (14-bit positions).
  - three.js `GLTFLoader` reads this natively. No Draco or meshopt **decoder** is needed, because a WASM decoder would need a CSP change (`script-src 'self'`).
- **Cropped:** triangles reaching more than 12 m outside the map's play extents are dropped. These are the large backdrop plates and most of the load-in rooms; the arena and every spawn tube stay.
- **Sizes:** 15.3 MB of FBX → 2.47 MB of GLB (surge 0.98 MB, combustion 0.59, dyson 0.48, fission 0.41).

## Rebuild and check
```
cd app/tools/maps3d
npm install
node build.mjs "../../../../www.ecranked.com/replayviewer.ecranked.com/assets/models/maps" ../../frontend/public/maps3d
python -I sample_heads.py "<folder with .echoreplay files>" heads.json 10
node check.mjs ../../frontend/public/maps3d heads.json
```
`check.mjs` exits non-zero when a map's median head-to-surface distance is more than 0.3 m worse than when it was built.

Result on 2026-11-02 (10 other replays per map from `ECRanked/Replays`):

| Map | Heads | Median distance | Within 2 m | Under floor |
|---|---|---|---|---|
| surge | 25,341 | 0.95 m | 84.9 % | 0.0 % |
| fission | 18,265 | 1.04 m | 82.0 % | 3.4 % |
| dyson | 13,140 | 1.14 m | 73.4 % | 0.0 % |
| combustion | 21,749 | 0.83 m | 86.7 % | 3.2 % |
