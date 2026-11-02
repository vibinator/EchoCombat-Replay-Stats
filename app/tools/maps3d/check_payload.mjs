// Sanity check of <map>_payload.glb: loads, one mesh, small, centred on itself.
import { NodeIO } from "@gltf-transform/core";
import { KHRMeshQuantization } from "@gltf-transform/extensions";
const io = new NodeIO().registerExtensions([KHRMeshQuantization]);
for (const m of ["surge", "fission"]) {
  const doc = await io.read(`../../frontend/public/maps3d/${m}_payload.glb`);
  const prim = doc.getRoot().listMeshes()[0].listPrimitives()[0];
  const pos = prim.getAttribute("POSITION");
  const min = [], max = [];
  pos.getMinNormalized?.(min); pos.getMaxNormalized?.(max);
  const lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9], v = [0, 0, 0];
  for (let i = 0; i < pos.getCount(); i++) { pos.getElement(i, v); for (let k = 0; k < 3; k++) { lo[k] = Math.min(lo[k], v[k]); hi[k] = Math.max(hi[k], v[k]); } }
  console.log(m, "vertices", pos.getCount(), "bbox", lo.map((x) => x.toFixed(2)), hi.map((x) => x.toFixed(2)));
}
