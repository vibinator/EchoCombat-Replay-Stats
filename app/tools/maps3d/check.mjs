// Checks the built map meshes against real head positions (docs/WebReplayer-Review.MD, Phase 1).
//
//   python -I sample_heads.py <replay folder> heads.json     (head positions every 20th frame, per map)
//   node check.mjs <glb dir> heads.json
//
// Per map, for in-play positions (inside the heatmap extents, docs/ReplayData.MD): distance from each head to the nearest
// opaque surface, and the share of heads with a surface above but none below ("under the floor": should stay near 0).
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { NodeIO } from "@gltf-transform/core";
import { KHRMeshQuantization } from "@gltf-transform/extensions";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { MeshBVH } from "three-mesh-bvh";

const KEYS = { surge: "mpl_combat_gauss", fission: "mpl_combat_fission", dyson: "mpl_combat_dyson", combustion: "mpl_combat_combustion" };
const EXTENTS = { dyson: [-54.625, 54.625, -41.125, 28.375], combustion: [-18.25, 55.625, -87.625, 86.625],
  surge: [-55.625, 149.5, -47, 62.625], fission: [-74.125, 124.5, -23.125, 34.125] }; // x min, x max, z min, z max
// Results when the meshes were built (2026-11-02, 10 replays per map): a later rebuild should not be clearly worse.
const BASELINE_MEDIAN_M = { surge: 1.03, fission: 1.11, dyson: 1.12, combustion: 0.81 };

const [glbDir, headsFile] = process.argv.slice(2);
if (!glbDir || !headsFile) { console.error("usage: node check.mjs <glb dir> <heads.json>"); process.exit(2); }
const heads = JSON.parse(fs.readFileSync(headsFile, "utf8"));
const io = new NodeIO().registerExtensions([KHRMeshQuantization]);
let failed = false;
for (const [map, key] of Object.entries(KEYS)) {
  const doc = await io.read(path.join(glbDir, `${map}.glb`));
  const parts = [];
  for (const node of doc.getRoot().listNodes()) {
    const mesh = node.getMesh(); if (!mesh) continue;
    const world = new THREE.Matrix4().fromArray(node.getWorldMatrix());
    for (const prim of mesh.listPrimitives()) {
      if (prim.getMaterial().getAlphaMode() === "BLEND") continue; // see-through capture point volumes
      const a = prim.getAttribute("POSITION"), n = a.getCount(), arr = new Float32Array(n * 3), t = [];
      for (let i = 0; i < n; i++) { a.getElement(i, t); arr.set(t, i * 3); } // getElement undoes the quantisation
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.BufferAttribute(arr, 3));
      g.setIndex(new THREE.BufferAttribute(new Uint32Array(prim.getIndices().getArray()), 1));
      parts.push(g.applyMatrix4(world));
    }
  }
  const bvh = new MeshBVH(mergeGeometries(parts));
  const e = EXTENTS[map];
  const pts = (heads[key] || []).filter((h) => h[0] >= e[0] && h[0] <= e[1] && h[2] >= e[2] && h[2] <= e[3]);
  if (!pts.length) { console.log(`${map}: no sample positions`); continue; }
  const v = new THREE.Vector3(), hit = {}, ray = new THREE.Ray();
  let under = 0;
  const d = pts.map((h) => {
    v.set(h[0], h[1], h[2]);
    ray.origin.copy(v); ray.direction.set(0, -1, 0); const down = bvh.raycastFirst(ray, THREE.DoubleSide);
    ray.direction.set(0, 1, 0); const up = bvh.raycastFirst(ray, THREE.DoubleSide);
    if (!down && up) under++;
    bvh.closestPointToPoint(v, hit, 0, 1e9); return hit.distance;
  }).sort((a, b) => a - b);
  const q = (x) => d[Math.floor(x * (d.length - 1))];
  const med = q(0.5), ok = med <= BASELINE_MEDIAN_M[map] + 0.3;
  failed ||= !ok;
  console.log(`${ok ? "ok  " : "FAIL"} ${map}: ${d.length} heads, median ${med.toFixed(2)} m (built ${BASELINE_MEDIAN_M[map]}), p90 ${q(0.9).toFixed(2)} m, `
    + `within 2 m ${(100 * d.filter((x) => x < 2).length / d.length).toFixed(1)} %, under the floor ${(100 * under / d.length).toFixed(1)} %`);
}
process.exit(failed ? 1 : 0);
