// Lists the mesh parts of a minimap FBX (name, material, triangles, centre in replay coordinates).
globalThis.self = globalThis; globalThis.window = { innerWidth: 1, innerHeight: 1 };
import fs from "node:fs";
import * as THREE from "three";
import { FBXLoader } from "three/examples/jsm/loaders/FBXLoader.js";
const [file, ...near] = process.argv.slice(2);
const buf = fs.readFileSync(file);
const warn = console.warn; console.warn = () => {};
const obj = new FBXLoader().parse(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength), "");
console.warn = warn; obj.updateMatrixWorld(true);
const rows = [];
obj.traverse((o) => {
  if (!o.isMesh) return;
  const g = o.geometry.clone().applyMatrix4(o.matrixWorld); g.computeBoundingBox();
  const c = g.boundingBox.getCenter(new THREE.Vector3()), s = g.boundingBox.getSize(new THREE.Vector3());
  rows.push({ name: o.name, parent: o.parent?.name, mat: [].concat(o.material)[0].name, tris: (o.geometry.index?.count ?? o.geometry.attributes.position.count) / 3,
    c: c.toArray().map((v) => +v.toFixed(1)), s: s.toArray().map((v) => +v.toFixed(1)) });
});
console.log(rows.length, "parts");
for (const r of rows) if (r.mat === "Pink" || /flam|pay|cart|bird/i.test(r.name + r.parent)) console.log(JSON.stringify(r));
