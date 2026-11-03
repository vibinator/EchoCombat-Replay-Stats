// How the map models (public/maps3d/*.glb) are dressed, shared by the 3D playback (Map3D.tsx) and the 3D heatmaps.
import * as THREE from "three";
import { TEAM_COLORS } from "./playback3d";

// The map files use the colours of the old hologram minimaps: their "Light Orange" is #ff3800, which reads as red next to the
// site's orange, and the dark parts are near black. Recoloured when loaded (user, 2026-11-02): the teams in the site's own
// colours, readable darks, a cleaner glow. Anything not listed keeps the colour it came with.
export const MAP_LOOK: Record<string, { color: string; emissive?: string; emissiveIntensity?: number }> = {
  "Light Orange": { color: TEAM_COLORS[2] },
  "Light Blue": { color: "#22b7ee" },
  "Dark Gray": { color: "#1a202b" },
  "Dark Blue": { color: "#122042" },
  "Light Gray": { color: "#4b5465" },
  "Light Light Gray": { color: "#a9b1bf" },
  Map: { color: "#d4dae5" },
  lambert1: { color: "#7b8393" },
  Pink: { color: "#c93f72" },
  "Glowing Blue": { color: "#1780d6", emissive: "#2fa4ff", emissiveIntensity: 0.85 },
};
// Layers of the map file that lie exactly on top of each other (a team zone on the floor it colours, trim on a wall): the
// depth buffer cannot tell them apart, so they flicker. The higher the layer, the nearer it is drawn (polygon offset).
export const MAP_LAYER: Record<string, number> = {
  "Dark Gray": 0, "Map": 1, lambert1: 1, Watery: 1, "Dark Blue": 2, "Light Gray": 2, "Light Light Gray": 3,
  "Light Blue": 4, "Light Orange": 4, Pink: 5, "Glowing Blue": 5, "Capture Point Transparent": 6,
};

export interface MapMaterial {
  m: THREE.MeshStandardMaterial;
  opacity: number;
  transparent: boolean;
}

/** Recolour a loaded map model, keep its layers apart and make it unpickable. Returns its materials (for see-through). */
export function dressMapModel(root: THREE.Object3D): MapMaterial[] {
  const materials: MapMaterial[] = [];
  root.traverse((o) => {
    const mesh = o as THREE.Mesh;
    if (!mesh.isMesh) return;
    for (const m of ([] as THREE.Material[]).concat(mesh.material)) {
      const std = m as THREE.MeshStandardMaterial;
      const look = MAP_LOOK[std.name];
      if (look) {
        std.color.set(look.color);
        if (look.emissive) { std.emissive.set(look.emissive); std.emissiveIntensity = look.emissiveIntensity ?? 1; }
      }
      std.flatShading = true; // the files have no normals (app/tools/maps3d)
      const layer = MAP_LAYER[std.name] ?? 1;
      std.polygonOffset = true;
      std.polygonOffsetFactor = -layer;
      std.polygonOffsetUnits = -layer;
      materials.push({ m: std, opacity: std.opacity, transparent: std.transparent });
    }
    mesh.raycast = () => {}; // clicks pick players only
  });
  return materials;
}
