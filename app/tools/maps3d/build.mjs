// Builds the 3D map meshes for 3D playback (docs/WebReplayer-Review.MD, Phase 1).
//
//   node build.mjs <dir with *_minimap.fbx> <output dir>
//   e.g. node build.mjs "../../../../www.ecranked.com/replayviewer.ecranked.com/assets/models/maps" ../../frontend/public/maps3d
//
// Source: the minimap FBX files of duncancarroll/ec-web-replayer (MIT; same files as the old replayviewer.ecranked.com).
// Output: one GLB per map, in replay coordinates (metres, x / y / z exactly as head.position in the replay, Y up), so the
// viewer places players with no offset. Placement (upstream EC_MAPS, plus a fitted correction for combustion), welded,
// lightly simplified (meshopt, ~0.1 m error), positions quantised (KHR_mesh_quantization: three.js reads it natively,
// no WASM decoder, so the site's CSP needs no change). No normals: render with flatShading. One primitive per material.
// Cropped to the play area: triangles reaching more than CROP_MARGIN_M outside the map's extents (the backdrop plates and
// the load-in rooms far around the arena) are dropped.
globalThis.self = globalThis;
globalThis.window = { innerWidth: 1, innerHeight: 1 }; // FBXLoader reads the window size for cameras in the file
import fs from "node:fs";
import path from "node:path";
import * as THREE from "three";
import { FBXLoader } from "three/examples/jsm/loaders/FBXLoader.js";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { Document, NodeIO } from "@gltf-transform/core";
import { KHRMeshQuantization } from "@gltf-transform/extensions";
import { weld, dedup, prune, quantize, simplify } from "@gltf-transform/functions";
import { MeshoptSimplifier } from "meshoptimizer";

// Upstream EC_MAPS (src/viewer.js), applied the way upstream does: position (z, y, x), scale (-x, y, -z), rotation as-is.
// combustion rotation.y = 80 is radians in three.js (= 263.7 degrees); kept, because the fitted correction is relative to it.
const MAPS = {
  surge: { file: "surge_minimap.fbx", p: [21.8, -1.37, 45.7], r: [0, 0, 0], s: [0.56, 0.56, 0.56] },
  fission: { file: "fission_minimap.fbx", p: [-0.5, -12.43, 21], r: [0, 0, 0], s: [0.588, 0.588, 0.588] },
  dyson: { file: "dyson_minimap.fbx", p: [0, -3.95, 0], r: [0, 0, 0], s: [0.92377, 0.92377, 0.92377] },
  combustion: { file: "combustion_minimap.fbx", p: [0, -83.3, 26.2], r: [0, 80, 0], s: [-0.588, 0.588, -0.588],
    // 2026-11-02 fit (horizontal shift, yaw, scale; height locked) to ~22k in-play head positions from 10 replays, checked
    // on held-out positions: median head-to-surface 1.20 -> 0.75 m, capture point mesh 0.7 m from the measured centre.
    fix: { dx: -1.25, dz: 2.0625, yaw: 0.0484375, scale: 0.9896875 } },
};

// Play extents per map (x min, x max, z min, z max; docs/ReplayData.MD "Heatmap image extents", stats/maps.py HEATMAP_LAYOUTS).
const EXTENTS = { dyson: [-54.625, 54.625, -41.125, 28.375], combustion: [-18.25, 55.625, -87.625, 86.625],
  surge: [-55.625, 149.5, -47, 62.625], fission: [-74.125, 124.5, -23.125, 34.125] };
const CROP_MARGIN_M = 12;

function crop(pos, [x0, x1, z0, z1]) {
  const m = CROP_MARGIN_M, keep = [];
  const inside = (i) => pos[i] >= x0 - m && pos[i] <= x1 + m && pos[i + 2] >= z0 - m && pos[i + 2] <= z1 + m;
  for (let i = 0; i < pos.length; i += 9) if (inside(i) && inside(i + 3) && inside(i + 6)) for (let k = 0; k < 9; k++) keep.push(pos[i + k]);
  return new Float32Array(keep);
}

function placement(m) {
  const o = new THREE.Object3D();
  o.position.set(m.p[2], m.p[1], m.p[0]);
  o.scale.set(-m.s[0], m.s[1], -m.s[2]);
  o.rotation.set(m.r[0], m.r[1], m.r[2]);
  o.updateMatrix();
  if (!m.fix) return o.matrix;
  const f = m.fix;
  return new THREE.Matrix4().makeTranslation(f.dx, 0, f.dz).multiply(new THREE.Matrix4().makeRotationY(f.yaw))
    .multiply(new THREE.Matrix4().makeScale(f.scale, f.scale, f.scale)).multiply(o.matrix);
}

function loadFbx(file) {
  const buf = fs.readFileSync(file);
  const warn = console.warn; console.warn = () => {}; // FBXLoader warns about unused Maya properties
  const obj = new FBXLoader().parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), "");
  console.warn = warn;
  obj.updateMatrixWorld(true);
  return obj;
}

/** <map>_payload.glb: the payload model on its own, centred on its own middle (x, y, z) so the viewer can put it at the
 *  cart's recorded position. It keeps the orientation it was baked with, at the start of the route. */
async function writePayload(io, name, parts, mirrored, outDir) {
  const merged = mergeGeometries(parts.map((p) => p.g));
  merged.computeBoundingBox();
  const centre = merged.boundingBox.getCenter(new THREE.Vector3());
  const pos = new Float32Array(merged.attributes.position.array);
  for (let i = 0; i < pos.length; i += 3) { pos[i] -= centre.x; pos[i + 1] -= centre.y; pos[i + 2] -= centre.z; }
  if (mirrored) for (let i = 0; i < pos.length; i += 9) for (let k = 0; k < 3; k++) [pos[i + 3 + k], pos[i + 6 + k]] = [pos[i + 6 + k], pos[i + 3 + k]];
  const { mat } = parts[0];
  const doc = new Document();
  doc.getRoot().getAsset().generator = "EchoVR-Replay-Stats app/tools/maps3d (ec-web-replayer minimap FBX, MIT)";
  const buffer = doc.createBuffer();
  const material = doc.createMaterial("payload").setBaseColorFactor([mat.color.r, mat.color.g, mat.color.b, 1])
    .setMetallicFactor(0).setRoughnessFactor(1).setDoubleSided(true);
  const accessor = doc.createAccessor().setType("VEC3").setArray(pos).setBuffer(buffer);
  const mesh = doc.createMesh("payload").addPrimitive(doc.createPrimitive().setMaterial(material).setAttribute("POSITION", accessor));
  doc.createScene("payload").addChild(doc.createNode("payload").setMesh(mesh));
  await doc.transform(weld(), dedup(), prune(), quantize({ quantizePosition: 14 }));
  const out = path.join(outDir, `${name}_payload.glb`);
  await io.write(out, doc);
  const size = merged.boundingBox.getSize(new THREE.Vector3());
  console.log(`${name}_payload: ${fs.statSync(out).size} B, ${pos.length / 9} triangles, size ${size.toArray().map((v) => v.toFixed(2)).join(" x ")} m, `
    + `was at (${centre.x.toFixed(1)}, ${centre.y.toFixed(1)}, ${centre.z.toFixed(1)})`);
}

async function build(srcDir, outDir) {
  await MeshoptSimplifier.ready;
  const io = new NodeIO().registerExtensions([KHRMeshQuantization]);
  fs.mkdirSync(outDir, { recursive: true });
  for (const [name, m] of Object.entries(MAPS)) {
    const src = path.join(srcDir, m.file);
    const place = placement(m);
    const mirrored = place.determinant() < 0;
    const byMaterial = new Map();
    const payloadParts = []; // the flamingo: a part named "payload", baked at the start of the route (surge, fission)
    loadFbx(src).traverse((o) => {
      if (!o.isMesh) return;
      const mat = [].concat(o.material)[0];
      if (o.name === "payload") {
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", o.geometry.attributes.position.clone());
        if (o.geometry.index) g.setIndex(o.geometry.index.clone());
        g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(place, o.matrixWorld));
        payloadParts.push({ mat, g: g.index ? g.toNonIndexed() : g });
        return; // not part of the map: the viewer moves it along the route (it would stand at the start otherwise)
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute("position", o.geometry.attributes.position.clone());
      if (o.geometry.index) g.setIndex(o.geometry.index.clone());
      g.applyMatrix4(new THREE.Matrix4().multiplyMatrices(place, o.matrixWorld));
      if (!byMaterial.has(mat.name)) byMaterial.set(mat.name, { mat, parts: [] });
      byMaterial.get(mat.name).parts.push(g.index ? g.toNonIndexed() : g);
    });
    const doc = new Document();
    doc.getRoot().getAsset().generator = "EchoVR-Replay-Stats app/tools/maps3d (ec-web-replayer minimap FBX, MIT)";
    const buffer = doc.createBuffer();
    const mesh = doc.createMesh(name);
    for (const [matName, { mat, parts }] of byMaterial) {
      const pos = crop(mergeGeometries(parts).attributes.position.array, EXTENTS[name]);
      if (!pos.length) continue;
      if (mirrored) // a mirrored placement flips the winding: swap two corners so front faces stay front
        for (let i = 0; i < pos.length; i += 9) for (let k = 0; k < 3; k++) [pos[i + 3 + k], pos[i + 6 + k]] = [pos[i + 6 + k], pos[i + 3 + k]];
      const material = doc.createMaterial(matName)
        .setBaseColorFactor([mat.color.r, mat.color.g, mat.color.b, mat.transparent ? mat.opacity : 1]) // linear, as glTF wants
        .setMetallicFactor(0).setRoughnessFactor(1).setDoubleSided(true)
        .setAlphaMode(mat.transparent ? "BLEND" : "OPAQUE");
      if (mat.emissive && mat.emissive.getHex()) material.setEmissiveFactor([mat.emissive.r, mat.emissive.g, mat.emissive.b]);
      const accessor = doc.createAccessor().setType("VEC3").setArray(new Float32Array(pos)).setBuffer(buffer);
      mesh.addPrimitive(doc.createPrimitive().setMaterial(material).setAttribute("POSITION", accessor));
    }
    doc.createScene(name).addChild(doc.createNode(name).setMesh(mesh));
    await doc.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: 0, error: 0.0005, lockBorder: true }),
      dedup(), prune(), quantize({ quantizePosition: 14 }));
    const out = path.join(outDir, `${name}.glb`);
    await io.write(out, doc);
    if (payloadParts.length) await writePayload(io, name, payloadParts, mirrored, outDir);
    const tris = mesh.listPrimitives().reduce((n, p) => n + p.getIndices().getCount() / 3, 0);
    console.log(`${name}: ${fs.statSync(src).size} B fbx -> ${fs.statSync(out).size} B glb, ${tris} triangles, ${byMaterial.size} materials`);
  }
}

const [srcDir, outDir] = process.argv.slice(2);
if (!srcDir || !outDir) { console.error("usage: node build.mjs <fbx dir> <output dir>"); process.exit(2); }
await build(srcDir, outDir);
