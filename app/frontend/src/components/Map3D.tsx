// 3D playback stage (docs/WebReplayer-Review.MD, Phases 4-9). Loaded on demand (React.lazy): three.js stays out of the
// main bundle. PlaybackView keeps the clock, controls, roster and feed; this only draws the map, players and objectives
// at the clock's time, from GET /api/matches/{id}/playback3d (5 Hz, world space) and the 2D playback's events / series.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { getPlayback3d, type MatchEvent, type Playback, type Playback3D } from "../api";
import { useApi } from "../useApi";
import { gearIconUrl, Status } from "./common";
import { CAMERAS, CONTROL_HELP, isFreeCamera, TEAM_COLORS, type Camera3D } from "./playback3d";

const JUMP_M = 3; // positions further apart than this between two samples are a respawn / teleport: no gliding
const SKULL_S = 5;
const DEATH_FLASH_S = 3;
const HAND_STEP_M = 0.02; // hands are sent relative to the head in 2 cm steps
const SHOULDER_DROP_M = 0.3; // arms are drawn from just below the head
const FOLLOW_BACK_M = 7; // chase camera: behind and above the picked player, looking down at them
const FOLLOW_UP_M = 4;
// The map files use the colours of the old hologram minimaps: their "Light Orange" is #ff3800, which reads as red next to the
// site's orange, and the dark parts are near black. Recoloured when loaded (user, 2026-11-02): the teams in the site's own
// colours, readable darks, a cleaner glow. Anything not listed keeps the colour it came with.
const MAP_LOOK: Record<string, { color: string; emissive?: string; emissiveIntensity?: number }> = {
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
const MAP_LAYER: Record<string, number> = {
  "Dark Gray": 0, "Map": 1, lambert1: 1, Watery: 1, "Dark Blue": 2, "Light Gray": 2, "Light Light Gray": 3,
  "Light Blue": 4, "Light Orange": 4, Pink: 5, "Glowing Blue": 5, "Capture Point Transparent": 6,
};
const OVERLAY_LAYER = 8; // the capture point ring and arc on the floor
const RIDE_MAP_OPACITY = 0.28; // follow / first person: the map is a coarse hologram (~1 m), so see through it
const BASE_FOV = 55;
const MOVE_MS = 450; // eased camera moves (picking a camera, R)
const DRAG_RAD_PER_PX = 0.006; // follow / first person: dragging turns the view this much per pixel
const HINT_MS = 8000;
const HINTS_KEY = "pb3d.hints"; // which cameras already showed their one-line "how to"
const SHORT_LABEL: Record<Camera3D, string> = { orbit: "Orbit", top: "Top", blue: "Blue end", orange: "Orange end", objective: "Objective", follow: "Follow", first: "First person" };
const HINT: Record<"free" | "follow" | "first", string> = {
  free: "Drag to slide · right-drag to turn · wheel to zoom · W A S D to fly · ? for all controls",
  follow: "Drag to swing round the player · wheel for distance · double-click to reset",
  first: "Drag to look around · wheel to zoom · double-click to look where they look",
};
const LEGEND_KEY = "pb3d.legend"; // "0" = the PC controls card was folded away
const LEGEND: Record<"free" | "follow" | "first", [string, string][]> = {
  free: [["Left-drag", "Slide"], ["Right-drag", "Turn"], ["Wheel", "Zoom"], ["W A S D", "Fly"], ["Q / E", "Down / up"], ["Shift", "Faster"], ["R", "Reset view"], ["?", "All controls"]],
  follow: [["Drag", "Swing round"], ["Wheel", "Distance"], ["Double-click / R", "Reset"], ["1 – 9", "Pick player"], ["?", "All controls"]],
  first: [["Drag", "Look around"], ["Wheel", "Zoom"], ["Double-click / R", "Reset"], ["1 – 9", "Pick player"], ["?", "All controls"]],
};
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

export interface Map3DProps {
  id: number;
  playback: Playback;
  second: number;
  follow: string | null;
  onPick: (userId: string | null) => void;
  camera: Camera3D;
  onCamera: (c: Camera3D) => void;
  names: boolean;
  trailSeconds: number;
  trailColor: "team" | "speed";
  deaths: MatchEvent[];
  swaps: Map<string, string>; // user id -> loadout swap text shown now
  weapons: Map<string, string>; // user id -> weapon held now (icon in the label)
  hands: boolean; // draw hands and arms
  onUse2D: () => void;
}

/** Latest value of a 2 Hz objective series at a sample. */
function seriesAt(series: (number | null)[] | undefined, i: number): number | null {
  if (!series) return null;
  for (let k = Math.min(i, series.length - 1); k >= 0; k--) if (series[k] != null) return series[k];
  return null;
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function Map3D(props: Map3DProps) {
  const data = useApi(() => getPlayback3d(props.id), `p3d${props.id}`);
  const [webgl] = useState(webglAvailable);
  if (!webgl) {
    return (
      <div className="pb3d-message">
        <p>3D playback needs WebGL, which this browser or device does not offer.</p>
        <button type="button" onClick={props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
  if (data.loading && !data.data) return <div className="pb3d-message"><p className="muted">Loading 3D positions…</p></div>;
  if (!data.data) {
    return (
      <div className="pb3d-message">
        <Status loading={false} error={data.error} />
        <button type="button" onClick={props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
  return <Stage {...props} data={data.data} />;
}

interface Pose {
  x: number;
  y: number;
  z: number;
  yaw: number; // radians, 0 = facing +z
  pitch: number; // radians, + = up
}

type Track = Playback3D["players"][number];

function present(p: Track, k: number): boolean {
  return k >= 0 && k < p.team.length && p.team[k] !== 0;
}

/** Pose at a fractional sample, gliding between samples unless the player jumped. */
function poseAt(p: Track, s: number): Pose | null {
  const i = Math.floor(s);
  if (!present(p, i)) return null;
  const a: Pose = { x: p.x[i] / 10, y: p.y[i] / 10, z: p.z[i] / 10, yaw: (p.yaw[i] / 256) * Math.PI * 2, pitch: (p.pitch[i] * Math.PI) / 180 };
  const f = s - i;
  if (f <= 0 || !present(p, i + 1)) return a;
  const bx = p.x[i + 1] / 10, by = p.y[i + 1] / 10, bz = p.z[i + 1] / 10;
  if (Math.hypot(bx - a.x, by - a.y, bz - a.z) > JUMP_M) return a;
  let dyaw = (p.yaw[i + 1] - p.yaw[i]) % 256;
  if (dyaw > 128) dyaw -= 256;
  if (dyaw < -128) dyaw += 256;
  return {
    x: a.x + (bx - a.x) * f, y: a.y + (by - a.y) * f, z: a.z + (bz - a.z) * f,
    yaw: a.yaw + ((dyaw / 256) * Math.PI * 2) * f,
    pitch: a.pitch + (((p.pitch[i + 1] - p.pitch[i]) * Math.PI) / 180) * f,
  };
}

function speedColor(v: number, out: THREE.Color): THREE.Color {
  const s = Math.min(1, Math.max(0, v / 12));
  return out.setHSL((220 - 220 * s) / 360, 0.9, 0.55); // same ramp as the 2D trails
}

/** Hand offsets (metres, relative to the head) at a fractional sample: [lx, ly, lz, rx, ry, rz]. */
function handsAt(p: Track, s: number, out: number[]): boolean {
  const h = p.hands;
  if (!h || h.length < 6) return false;
  const i = Math.floor(s), f = s - i;
  const glide = f > 0 && present(p, i + 1) && Math.hypot(p.x[i + 1] - p.x[i], p.y[i + 1] - p.y[i], p.z[i + 1] - p.z[i]) / 10 <= JUMP_M;
  for (let k = 0; k < 6; k++) out[k] = (glide ? h[k][i] + (h[k][i + 1] - h[k][i]) * f : h[k][i]) * HAND_STEP_M;
  return true;
}

interface PlayerObj {
  track: Track;
  hands: THREE.Mesh[];
  arms: THREE.LineSegments;
  group: THREE.Group;
  head: THREE.Group;
  ring: THREE.Mesh;
  label: CSS2DObject;
  labelEl: HTMLDivElement;
  labelText: string;
  trail: THREE.LineSegments;
  trailPos: Float32Array;
  trailCol: Float32Array;
}

function Stage(props: Map3DProps & { data: Playback3D }) {
  const mount = useRef<HTMLDivElement>(null);
  const latest = useRef(props);
  latest.current = props;
  const dirty = useRef(true);
  const engine = useRef<{ setCamera: (c: Camera3D) => void } | null>(null);
  const [mapState, setMapState] = useState<"loading" | "ok" | "none" | "failed">(props.data.model ? "loading" : "none");
  const [failed, setFailed] = useState<string | null>(null);
  const [help, setHelp] = useState(false); // the "?" list of controls
  const [legend, setLegend] = useState(() => { try { return localStorage.getItem(LEGEND_KEY) !== "0"; } catch { return true; } }); // PC controls card, always on view
  const toggleLegend = () => setLegend((v) => { try { localStorage.setItem(LEGEND_KEY, v ? "0" : "1"); } catch { /* ignore */ } return !v; });
  const legendKind = isFreeCamera(props.camera) ? "free" : props.camera === "follow" ? "follow" : "first";
  const [hint, setHint] = useState<string | null>(null); // one line of "how to" the first time a camera is used
  const hasObjective = !!(props.data.objects.route?.length || props.data.objects.point);

  useEffect(() => {
    dirty.current = true; // any new props (time, toggles, picked player): draw again
  });

  // the first time a camera is used (per browser), say in one line how to move it; goes away by itself or at the first touch
  useEffect(() => {
    const kind = isFreeCamera(props.camera) ? "free" : props.camera === "follow" ? "follow" : "first";
    let seen: string[] = [];
    try { seen = JSON.parse(localStorage.getItem(HINTS_KEY) || "[]"); } catch { /* private window: shown every time */ }
    if (seen.includes(kind)) { setHint(null); return; }
    try { localStorage.setItem(HINTS_KEY, JSON.stringify([...seen, kind])); } catch { /* ignore */ }
    setHint(HINT[kind]);
    const t = window.setTimeout(() => setHint(null), HINT_MS);
    return () => window.clearTimeout(t);
  }, [props.camera]);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    const data = props.data;
    const hz = data.hz;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch (e) {
      setFailed(`3D could not start: ${(e as Error).message}`);
      return;
    }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0); // see-through: the gradient behind the canvas (styles.css .pb3d) is the sky
    renderer.toneMapping = THREE.NeutralToneMapping; // bright surfaces keep their hue instead of clipping to flat colour
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.domElement.className = "pb3d-labels";
    el.appendChild(labels.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xdbe8ff, 0x2a3140, 1.5));
    const sun = new THREE.DirectionalLight(0xfff1dc, 1.9); // warm key from above
    sun.position.set(0.5, 1, 0.35);
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0x8fb4ff, 0.7); // cool fill from the other side: shaded faces keep some shape
    fill.position.set(-0.7, 0.35, -0.6);
    scene.add(fill);

    // --- where the action is (5th-95th percentiles, so the load-in rooms far around the arena do not count) ---
    const xs: number[] = [], zs: number[] = [], ys: number[] = [];
    for (const p of data.players)
      for (let k = 0; k < p.team.length; k += 5)
        if (p.team[k]) { xs.push(p.x[k] / 10); zs.push(p.z[k] / 10); ys.push(p.y[k] / 10); }
    if (!xs.length) { xs.push(-50, 50); zs.push(-50, 50); ys.push(0); }
    for (const a of [xs, zs, ys]) a.sort((u, v) => u - v);
    const q = (a: number[], f: number) => a[Math.floor(f * (a.length - 1))];
    // the map's play area when known; otherwise where players spent most of their time
    const [x0, x1, z0, z1] = data.extent ?? [q(xs, 0.05), q(xs, 0.95), q(zs, 0.05), q(zs, 0.95)];
    const center = new THREE.Vector3((x0 + x1) / 2, ys[Math.floor(ys.length / 2)], (z0 + z1) / 2);
    const span = Math.max(40, x1 - x0, z1 - z0);
    scene.fog = new THREE.Fog("#0d1118", span * 1.15, span * 3.6); // far parts fade into the sky

    const camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.05, span * 12);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.screenSpacePanning = true;
    controls.maxDistance = span * 3;
    controls.minDistance = 0.1; // close enough to read a player's hands
    controls.enableDamping = true; // glides to a stop instead of halting dead
    controls.dampingFactor = 0.12;
    controls.zoomToCursor = true; // the wheel zooms towards what the pointer is over, not the middle of the map
    controls.zoomSpeed = 1.4;
    controls.rotateSpeed = 0.8;
    controls.panSpeed = 1.2;
    // left drag moves sideways, right drag (or Shift + left drag) turns, wheel zooms, middle drag zooms
    controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
    controls.addEventListener("change", () => { dirty.current = true; });

    // --- map model ---
    let disposed = false;
    const mapMaterials: { m: THREE.MeshStandardMaterial; opacity: number; transparent: boolean }[] = [];
    const mapSeeThrough = (on: boolean) => {
      for (const x of mapMaterials) {
        x.m.transparent = on || x.transparent;
        x.m.opacity = on ? Math.min(x.opacity, RIDE_MAP_OPACITY) : x.opacity;
        x.m.depthWrite = !x.m.transparent;
        x.m.needsUpdate = true;
      }
    };
    if (data.model) {
      new GLTFLoader().load(
        data.model,
        (gltf) => {
          if (disposed) return;
          gltf.scene.traverse((o) => {
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
              mapMaterials.push({ m: std, opacity: std.opacity, transparent: std.transparent });
            }
            mesh.raycast = () => {}; // clicks pick players only
          });
          scene.add(gltf.scene);
          // a faint grid under the arena, fading out with the fog: gives the floating map a place to sit
          const floor = new THREE.Box3().setFromObject(gltf.scene).min.y - 0.6;
          const size = Math.ceil((span * 1.7) / 10) * 10;
          const grid = new THREE.GridHelper(size, size / 10, 0x34496a, 0x1d2940);
          (grid.material as THREE.Material).transparent = true;
          (grid.material as THREE.Material).opacity = 0.55;
          grid.position.set(center.x, floor, center.z);
          grid.raycast = () => {};
          scene.add(grid);
          mapSeeThrough(!isFreeCamera(mode));
          setMapState("ok");
          dirty.current = true;
        },
        undefined,
        () => !disposed && setMapState("failed"),
      );
    } else {
      const grid = new THREE.GridHelper(Math.ceil(span / 10) * 10, Math.ceil(span / 10), 0x3a4150, 0x262b35);
      grid.position.set(center.x, ys[0] - 1.5, center.z);
      scene.add(grid);
    }

    // --- players ---
    const teamMats = [1, 2].map((t) => new THREE.MeshStandardMaterial({ color: TEAM_COLORS[t], roughness: 0.6, emissive: TEAM_COLORS[t], emissiveIntensity: 0.25 }));
    const noseMat = new THREE.MeshStandardMaterial({ color: "#ffffff", roughness: 0.5 });
    const ringMat = new THREE.MeshBasicMaterial({ color: "#ffffff" });
    const headGeo = new THREE.SphereGeometry(0.28, 20, 14);
    const noseGeo = new THREE.ConeGeometry(0.11, 0.42, 12).rotateX(Math.PI / 2).translate(0, 0, 0.42);
    const bodyGeo = new THREE.CapsuleGeometry(0.26, 0.75, 4, 12).translate(0, -0.85, 0);
    const ringGeo = new THREE.TorusGeometry(0.5, 0.04, 8, 32).rotateX(Math.PI / 2);
    const handGeo = new THREE.SphereGeometry(0.09, 12, 8);
    const trailMax = Math.ceil(120 * hz) + 2; // longest trail: 1 min (2D: 120 samples at 2 Hz)
    const pickable: THREE.Object3D[] = [];
    const players: PlayerObj[] = data.players.map((track) => {
      const firstTeam = track.team.find((t) => t) ?? 1;
      const group = new THREE.Group();
      const head = new THREE.Group();
      const headMesh = new THREE.Mesh(headGeo, teamMats[firstTeam - 1]);
      const nose = new THREE.Mesh(noseGeo, noseMat);
      head.add(headMesh, nose);
      const body = new THREE.Mesh(bodyGeo, teamMats[firstTeam - 1]);
      const ring = new THREE.Mesh(ringGeo, ringMat);
      ring.position.y = -0.2;
      group.add(head, body, ring);
      headMesh.userData.uid = body.userData.uid = track.user_id;
      pickable.push(headMesh, body);
      const labelEl = document.createElement("div");
      labelEl.className = "pb3d-label";
      const label = new CSS2DObject(labelEl);
      label.position.set(0, 0.55, 0);
      group.add(label);
      group.visible = false;
      scene.add(group);
      const trailPos = new Float32Array(trailMax * 6);
      const trailCol = new Float32Array(trailMax * 6);
      const tg = new THREE.BufferGeometry();
      tg.setAttribute("position", new THREE.BufferAttribute(trailPos, 3).setUsage(THREE.DynamicDrawUsage));
      tg.setAttribute("color", new THREE.BufferAttribute(trailCol, 3).setUsage(THREE.DynamicDrawUsage));
      const trail = new THREE.LineSegments(tg, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.7 }));
      trail.frustumCulled = false;
      trail.raycast = () => {};
      scene.add(trail);
      // hands are placed in world space (offsets from the head are not turned with the head)
      const hands = [0, 1].map(() => {
        const m = new THREE.Mesh(handGeo, teamMats[firstTeam - 1]);
        m.visible = false;
        m.raycast = () => {};
        scene.add(m);
        return m;
      });
      const armGeo = new THREE.BufferGeometry();
      armGeo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(12), 3).setUsage(THREE.DynamicDrawUsage));
      const arms = new THREE.LineSegments(armGeo, new THREE.LineBasicMaterial({ color: TEAM_COLORS[firstTeam], transparent: true, opacity: 0.8 }));
      arms.frustumCulled = false;
      arms.visible = false;
      arms.raycast = () => {};
      scene.add(arms);
      return { track, hands, arms, group, head, ring, label, labelEl, labelText: "", trail, trailPos, trailCol };
    });
    const byId = new Map(players.map((p) => [p.track.user_id, p]));

    // --- skulls where players died (at their last 3D position before the death) ---
    const skullTex = new THREE.TextureLoader().load("/icons/death.png", () => { dirty.current = true; });
    skullTex.colorSpace = THREE.SRGBColorSpace;
    const skulls = props.deaths.flatMap((d) => {
      const p = d.user_id ? byId.get(d.user_id) : undefined;
      if (!p) return [];
      let k = Math.min(p.track.team.length - 1, Math.floor(d.t_s * hz));
      while (k >= 0 && !present(p.track, k)) k--;
      if (k < 0) return [];
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: skullTex, transparent: true, depthTest: false }));
      sprite.position.set(p.track.x[k] / 10, p.track.y[k] / 10 + 0.4, p.track.z[k] / 10);
      sprite.visible = false;
      sprite.renderOrder = 10;
      scene.add(sprite);
      return [{ t: d.t_s, sprite }];
    });

    // --- payload route and cart ---
    const pb = latest.current.playback;
    const attacker = pb.attacking_team === "blue" ? TEAM_COLORS[1] : pb.attacking_team === "orange" ? TEAM_COLORS[2] : "#ffffff";
    const payloadSamples = (data.payload ?? []).flatMap((q, k) => (q ? [{ k, q }] : []));
    let cart: THREE.Group | null = null;
    let travelled: Line2 | null = null;
    let routeLen = 0;
    const routePts: THREE.Vector3[] = [];
    const lineMats: LineMaterial[] = [];
    if (payloadSamples.length) {
      // the flamingo (its own model, taken out of the map file so it can move); a box stands in until it has loaded
      cart = new THREE.Group();
      const stand = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.0, 1.4), new THREE.MeshStandardMaterial({ color: attacker, emissive: attacker, emissiveIntensity: 0.35 }));
      stand.raycast = () => {};
      cart.add(stand);
      // a ring under it in the attacking team's colour (the flamingo itself is pink for both teams)
      const base = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.09, 8, 40).rotateX(Math.PI / 2), new THREE.MeshBasicMaterial({ color: attacker }));
      base.position.y = -0.7;
      base.raycast = () => {};
      cart.add(base);
      scene.add(cart);
      const group = cart;
      if (data.payload_model)
        new GLTFLoader().load(data.payload_model, (gltf) => {
          if (disposed) return;
          gltf.scene.traverse((o) => {
            const mesh = o as THREE.Mesh;
            if (!mesh.isMesh) return;
            for (const m of ([] as THREE.Material[]).concat(mesh.material)) (m as THREE.MeshStandardMaterial).flatShading = true;
            mesh.raycast = () => {};
          });
          group.remove(stand);
          group.add(gltf.scene);
          dirty.current = true;
        });
    }
    if (data.objects.route?.length) {
      // the route is (x, z) per metre of payload distance; its height comes from the nearest recorded cart position
      let y = payloadSamples[0]?.q[1] ?? center.y - 1.5;
      for (const [x, z] of data.objects.route) {
        let best = 16;
        for (const { q } of payloadSamples) {
          const d = (q[0] - x) ** 2 + (q[2] - z) ** 2;
          if (d < best) { best = d; y = q[1]; }
        }
        routePts.push(new THREE.Vector3(x, y + 0.15, z));
      }
      routeLen = routePts.length;
      // thick lines (a plain WebGL line is always 1 px): the whole route faint and dashed, what the payload has covered
      // solid in the attacking team's colour and drawn over the map, so progress reads at a glance from any camera
      const flat = routePts.flatMap((v) => [v.x, v.y, v.z]);
      const faint = new LineMaterial({ color: 0xffffff, linewidth: 3, dashed: true, dashSize: 1.2, gapSize: 1, transparent: true, opacity: 0.55 });
      const full = new Line2(new LineGeometry().setPositions(flat), faint);
      full.computeLineDistances();
      const done = new LineMaterial({ color: new THREE.Color(attacker).getHex(), linewidth: 7, depthTest: false, transparent: true });
      travelled = new Line2(new LineGeometry().setPositions(flat.map((v, k) => (k % 3 === 1 ? v + 0.05 : v))), done);
      travelled.renderOrder = 10;
      lineMats.push(faint, done);
      for (const l of [full, travelled]) { l.raycast = () => {}; scene.add(l); }
    }

    // --- capture point: a ring on the floor, filled by the leading team's progress ---
    let pointRing: THREE.Mesh | null = null;
    let pointArc: THREE.Mesh | null = null;
    let arcKey = "";
    const point = data.objects.point;
    let pointY = center.y;
    if (point) {
      const near: number[] = [];
      for (const p of data.players)
        for (let k = 0; k < p.team.length; k += 2)
          if (p.team[k] && Math.hypot(p.x[k] / 10 - point[0], p.z[k] / 10 - point[1]) < point[2]) near.push(p.y[k] / 10);
      near.sort((a, b) => a - b);
      if (near.length) pointY = near[Math.floor(near.length * 0.25)] - 1.1; // heads stand ~1.1 m above the floor
      pointRing = new THREE.Mesh(new THREE.RingGeometry(point[2] - 0.2, point[2], 64).rotateX(-Math.PI / 2),
        new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.45, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -OVERLAY_LAYER, polygonOffsetUnits: -OVERLAY_LAYER }));
      pointRing.position.set(point[0], pointY + 0.05, point[1]);
      pointRing.raycast = () => {};
      scene.add(pointRing);
    }

    // --- cameras ---
    let mode: Camera3D = latest.current.camera;
    const look = new THREE.Vector3();

    // where each team starts: the first moment a team has two players out of the load-in room (players load in at the origin)
    const anchor: (THREE.Vector3 | null)[] = [null, null, null];
    for (let k = 0; k < data.samples && !(anchor[1] && anchor[2]); k++) {
      for (const t of [1, 2]) {
        if (anchor[t]) continue;
        const here = data.players.filter((pl) => pl.team[k] === t && Math.hypot(pl.x[k], pl.z[k]) > 100);
        if (here.length < 2) continue;
        const mean = (f: (pl: (typeof here)[number]) => number) => here.reduce((a, pl) => a + f(pl), 0) / here.length / 10;
        anchor[t] = new THREE.Vector3(mean((pl) => pl.x[k]), mean((pl) => pl.y[k]), mean((pl) => pl.z[k]));
      }
    }
    // the ready-made viewpoints of the camera list: where the camera stands and what it looks at
    function presetPose(m: Camera3D, pos: THREE.Vector3, target: THREE.Vector3) {
      target.copy(center);
      if (m === "top") {
        pos.set(center.x, center.y + span * 0.95, center.z + 0.01);
        return;
      }
      if (m === "blue" || m === "orange") {
        const a = anchor[m === "blue" ? 1 : 2];
        if (a) { // behind the team's start, looking across the arena
          const dx = center.x - a.x, dz = center.z - a.z, len = Math.hypot(dx, dz) || 1;
          pos.set(a.x - (dx / len) * span * 0.12, a.y + span * 0.14, a.z - (dz / len) * span * 0.12);
          return;
        }
      } else if (m === "objective") {
        if (routePts.length) target.copy(routePts[Math.floor(routePts.length / 2)]);
        else if (point) target.set(point[0], pointY, point[1]);
        pos.set(target.x + span * 0.12, target.y + span * 0.16, target.z + span * 0.2);
        return;
      }
      pos.set(center.x + span * 0.27, center.y + span * 0.38, center.z + span * 0.43);
    }

    // eased moves: between the steerable cameras (position + the point looked at), and into a ride (blend from where the camera was)
    const tw = { on: false, t0: 0, fromP: new THREE.Vector3(), fromT: new THREE.Vector3(), toP: new THREE.Vector3(), toT: new THREE.Vector3() };
    const blend = { on: false, t0: 0, fromP: new THREE.Vector3(), fromQ: new THREE.Quaternion() };
    const tmpP = new THREE.Vector3(), tmpQ = new THREE.Quaternion();
    const ease = (now: number, t0: number) => { const k = clamp((now - t0) / MOVE_MS, 0, 1); return [k, k * k * (3 - 2 * k)] as const; };
    controls.addEventListener("start", () => { tw.on = false; }); // grabbing the view ends the glide
    // dragging / wheel offsets while riding a player (follow: swing round and distance; first person: look around and zoom)
    const drag = { yaw: 0, pitch: 0, dist: 1 };
    const resetRide = () => {
      drag.yaw = drag.pitch = 0;
      drag.dist = 1;
      camera.fov = BASE_FOV;
      camera.updateProjectionMatrix();
      dirty.current = true;
    };

    let started = false;
    function setCamera(next: Camera3D) {
      const wasFree = isFreeCamera(mode);
      mode = next;
      resetRide();
      controls.enabled = isFreeCamera(next);
      controls.enableRotate = next !== "top";
      camera.up.set(0, 1, 0);
      if (!isFreeCamera(next)) { camera.near = 0.05; camera.updateProjectionMatrix(); } // riding: close to the player's head
      mapSeeThrough(!isFreeCamera(next));
      const glide = started && !reducedMotion;
      started = true;
      tw.on = blend.on = false;
      if (controls.enabled) {
        presetPose(next, tw.toP, tw.toT);
        if (glide) {
          if (!wasFree) { // leaving a ride: start from the camera's own view, looking ahead
            camera.getWorldDirection(look);
            controls.target.copy(camera.position).addScaledVector(look, 10);
          }
          tw.fromP.copy(camera.position);
          tw.fromT.copy(controls.target);
          tw.t0 = performance.now();
          tw.on = true;
        } else {
          camera.position.copy(tw.toP);
          controls.target.copy(tw.toT);
        }
        controls.update();
      } else if (glide) {
        blend.fromP.copy(camera.position);
        blend.fromQ.copy(camera.quaternion);
        blend.t0 = performance.now();
        blend.on = true;
      }
      dirty.current = true;
    }
    engine.current = { setCamera };
    setCamera(mode);

    // --- keyboard: W A S D move (Shift = faster), Q / E down / up, R puts the camera back (orbit and top-down only) ---
    const held = new Set<string>();
    let fast = false;
    const typing = (t: EventTarget | null) => t instanceof HTMLElement && /^(input|textarea|select)$/i.test(t.tagName);
    const onKeyDown = (e: KeyboardEvent) => {
      fast = e.shiftKey;
      if (e.ctrlKey || e.metaKey || e.altKey || typing(e.target)) return;
      if (e.key === "?") { setHelp((h) => !h); return; }
      const k = e.key.toLowerCase();
      if (k === "r") { if (controls.enabled) setCamera(mode); else resetRide(); return; } // free: back to the camera's own spot; riding: look where the player looks
      if (!controls.enabled) return;
      if (k.length === 1 && "wasdqe".includes(k)) { held.add(k); tw.on = false; e.preventDefault(); dirty.current = true; }
    };
    const onKeyUp = (e: KeyboardEvent) => { fast = e.shiftKey; held.delete(e.key.toLowerCase()); };
    const onBlur = () => { held.clear(); fast = false; };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    window.addEventListener("blur", onBlur);
    const fwd = new THREE.Vector3(), side = new THREE.Vector3(), step = new THREE.Vector3();
    let lastFly = performance.now();
    function fly(now: number) {
      const dt = Math.min(0.1, (now - lastFly) / 1000);
      lastFly = now;
      if (!held.size || !controls.enabled) return;
      // speed grows with the distance to what is being looked at: slow close up, quick from far away
      const speed = Math.max(4, camera.position.distanceTo(controls.target) * 0.9) * (fast ? 3 : 1);
      camera.getWorldDirection(fwd);
      if (mode === "top") fwd.set(0, 0, -1); else fwd.y = 0;
      fwd.normalize();
      side.crossVectors(fwd, camera.up).normalize();
      step.set(0, 0, 0);
      if (held.has("w")) step.add(fwd);
      if (held.has("s")) step.sub(fwd);
      if (held.has("d")) step.add(side);
      if (held.has("a")) step.sub(side);
      if (held.has("e")) step.y += 1;
      if (held.has("q")) step.y -= 1;
      if (!step.lengthSq()) return;
      step.normalize().multiplyScalar(speed * dt);
      camera.position.add(step); // the target moves with the camera, so turning still works from the new spot
      controls.target.add(step);
      dirty.current = true;
    }

    // --- right and middle buttons move the view: no browser menu (in any camera, also over the name labels and on touch
    // screens' long press), no middle-click autoscroll, no text selected by dragging ---
    const noDefault = (e: Event) => e.preventDefault();
    const noAutoscroll = (e: MouseEvent) => { if (e.button === 1 || e.button === 2) e.preventDefault(); };
    el.addEventListener("contextmenu", noDefault);
    el.addEventListener("auxclick", noDefault);
    el.addEventListener("mousedown", noAutoscroll);

    // --- picking: a click (not a drag) with the main button on a player picks them ---
    const ray = new THREE.Raycaster();
    let down: [number, number] | null = null;
    // riding a player: a drag (any button) turns the view round / around, a wheel changes distance / zoom, a double click resets
    let ride: [number, number] | null = null;
    const onDown = (e: PointerEvent) => {
      down = e.button === 0 ? [e.clientX, e.clientY] : null; // right / middle never pick
      if (!isFreeCamera(mode)) {
        ride = [e.clientX, e.clientY];
        try { renderer.domElement.setPointerCapture(e.pointerId); } catch { /* a drag that leaves the canvas just stops */ }
      }
    };
    const onMove = (e: PointerEvent) => {
      if (!ride || isFreeCamera(mode)) return;
      drag.yaw += (e.clientX - ride[0]) * DRAG_RAD_PER_PX;
      drag.pitch = clamp(drag.pitch + (e.clientY - ride[1]) * DRAG_RAD_PER_PX, -1.4, 1.4);
      ride = [e.clientX, e.clientY];
      dirty.current = true;
    };
    const onWheel = (e: WheelEvent) => {
      if (isFreeCamera(mode)) return; // OrbitControls zooms
      e.preventDefault();
      const f = Math.exp(clamp(e.deltaY, -200, 200) * 0.0012);
      if (mode === "follow") drag.dist = clamp(drag.dist * f, 0.1, 5);
      else { camera.fov = clamp(camera.fov * f, 8, 100); camera.updateProjectionMatrix(); }
      dirty.current = true;
    };
    const onDouble = () => { if (!isFreeCamera(mode)) resetRide(); };
    const onUp = (e: PointerEvent) => {
      ride = null;
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
      const box = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - box.left) / box.width) * 2 - 1, -((e.clientY - box.top) / box.height) * 2 + 1), camera);
      const hit = ray.intersectObjects(pickable.filter((o) => o.parent?.visible !== false && o.parent?.parent?.visible !== false), false)[0];
      if (hit) latest.current.onPick(hit.object.userData.uid as string);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointercancel", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("wheel", onWheel, { passive: false });
    renderer.domElement.addEventListener("dblclick", onDouble);

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      labels.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      for (const m of lineMats) m.resolution.set(w, h);
      dirty.current = true;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    // --- one frame ---
    const color = new THREE.Color();
    const offs = [0, 0, 0, 0, 0, 0];
    const desired = new THREE.Vector3();
    let settling = 0; // follow camera still gliding towards its spot
    function update() {
      const p = latest.current;
      const s = Math.min(data.samples - 1, Math.max(0, p.second * hz));
      const i = Math.floor(s);
      const sample2d = Math.floor(p.second * p.playback.hz);
      const died = new Set(p.deaths.filter((d) => p.second >= d.t_s && p.second - d.t_s < DEATH_FLASH_S).map((d) => d.user_id));
      const trailN = Math.round(p.trailSeconds * hz);
      for (const o of players) {
        const pose = poseAt(o.track, s);
        o.group.visible = !!pose && !(mode === "first" && p.follow === o.track.user_id); // first person: not your own head
        const team = o.track.team[i] || o.track.team.find((t) => t) || 1;
        if (pose) {
          o.group.position.set(pose.x, pose.y, pose.z);
          o.group.rotation.y = pose.yaw;
          o.head.rotation.x = -pose.pitch;
          const picked = p.follow === o.track.user_id;
          o.ring.visible = picked;
          const hideLabel = (mode === "first" || mode === "follow") && picked;
          o.label.visible = (p.names || picked) && !hideLabel;
          const swap = p.swaps.get(o.track.user_id);
          const weapon = p.weapons.get(o.track.user_id) ?? "";
          const text = `${o.track.name}|${weapon}|${swap ?? ""}`;
          if (text !== o.labelText) {
            o.labelText = text;
            const parts: (Node | string)[] = [];
            const icon = gearIconUrl(weapon);
            if (icon) {
              const img = document.createElement("img");
              img.src = icon;
              img.alt = "";
              img.title = weapon;
              parts.push(img);
            }
            parts.push(o.track.name);
            if (swap) {
              const line = document.createElement("div");
              line.className = "pb3d-swap";
              line.textContent = `⇄ ${swap}`;
              parts.push(line);
            }
            o.labelEl.replaceChildren(...parts);
          }
          o.labelEl.className = `pb3d-label ${team === 1 ? "blue" : "orange"}${picked ? " picked" : ""}${died.has(o.track.user_id) ? " died" : ""}`;
        }
        // hands and arms
        const showHands = !!pose && p.hands && o.group.visible && handsAt(o.track, s, offs);
        o.hands[0].visible = o.hands[1].visible = o.arms.visible = !!showHands;
        if (showHands && pose) {
          const arm = o.arms.geometry.attributes.position as THREE.BufferAttribute;
          for (let k = 0; k < 2; k++) {
            const hx = pose.x + offs[k * 3], hy = pose.y + offs[k * 3 + 1], hz = pose.z + offs[k * 3 + 2];
            o.hands[k].position.set(hx, hy, hz);
            arm.setXYZ(k * 2, pose.x, pose.y - SHOULDER_DROP_M, pose.z);
            arm.setXYZ(k * 2 + 1, hx, hy, hz);
          }
          arm.needsUpdate = true;
        }
        // trail: segments between recent samples (gaps and respawn jumps left out)
        let n = 0;
        if (trailN > 0) {
          for (let k = Math.max(1, i - trailN + 1); k <= i; k++) {
            const t = o.track;
            if (!present(t, k) || !present(t, k - 1)) continue;
            const ax = t.x[k - 1] / 10, ay = t.y[k - 1] / 10, az = t.z[k - 1] / 10, bx = t.x[k] / 10, by = t.y[k] / 10, bz = t.z[k] / 10;
            const d = Math.hypot(bx - ax, by - ay, bz - az);
            if (d > JUMP_M) continue;
            if (p.trailColor === "speed") speedColor(d * hz, color);
            else color.set(TEAM_COLORS[t.team[k]] || "#ffffff");
            o.trailPos.set([ax, ay - 0.3, az, bx, by - 0.3, bz], n * 6);
            o.trailCol.set([color.r, color.g, color.b, color.r, color.g, color.b], n * 6);
            n++;
          }
        }
        o.trail.geometry.setDrawRange(0, n * 2);
        o.trail.geometry.attributes.position.needsUpdate = true;
        o.trail.geometry.attributes.color.needsUpdate = true;
        o.trail.visible = n > 0;
        (o.trail.material as THREE.LineBasicMaterial).opacity = p.follow && p.follow !== o.track.user_id ? 0.25 : 0.7;
      }
      for (const sk of skulls) {
        const age = p.second - sk.t;
        sk.sprite.visible = age >= 0 && age <= SKULL_S;
        if (!sk.sprite.visible) continue;
        const pop = Math.min(1, age / 0.25);
        sk.sprite.scale.setScalar(0.4 + 0.9 * pop);
        sk.sprite.material.opacity = age < SKULL_S - 1.5 ? 0.95 : Math.max(0, (SKULL_S - age) / 1.5) * 0.95;
      }
      if (cart) {
        let k = i;
        while (k >= 0 && !data.payload?.[k]) k--;
        const q = k >= 0 ? data.payload![k]! : null;
        cart.visible = !!q;
        if (q) cart.position.set(q[0], q[1], q[2]);
      }
      const dist = Math.max(0, Math.min(routeLen - 1, seriesAt(p.playback.series.payload_distance, sample2d) ?? 0));
      if (travelled) (travelled.geometry as LineGeometry).instanceCount = Math.max(0, Math.floor(dist));
      if (cart && routePts.length > 6) {
        // turn it with the route: the model was built facing along the start of the route
        const last = routePts.length - 1;
        const heading = (d: number) => {
          const a = routePts[Math.max(0, Math.min(last, Math.floor(d) - 2))], b = routePts[Math.max(0, Math.min(last, Math.floor(d) + 3))];
          return Math.atan2(b.x - a.x, b.z - a.z);
        };
        cart.rotation.y = heading(dist) - heading(0);
      }
      if (point && pointRing) {
        const blue = seriesAt(p.playback.series.blue_points, sample2d) ?? 0;
        const orange = seriesAt(p.playback.series.orange_points, sample2d) ?? 0;
        const lead = blue === orange ? 0 : blue > orange ? 1 : 2;
        const share = Math.min(1, Math.max(blue, orange) / 100);
        const key = lead ? `${lead}:${Math.round(share * 100)}` : "";
        if (key !== arcKey) {
          arcKey = key;
          if (pointArc) { scene.remove(pointArc); pointArc.geometry.dispose(); (pointArc.material as THREE.Material).dispose(); pointArc = null; }
          if (lead && share > 0) {
            // starts at "north" (-z) and runs clockwise seen from above, like the 2D ring
            const geo = new THREE.RingGeometry(point[2] - 0.7, point[2] - 0.2, 64, 1, Math.PI / 2 - share * Math.PI * 2, share * Math.PI * 2).rotateX(-Math.PI / 2);
            pointArc = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: TEAM_COLORS[lead], transparent: true, opacity: 0.85, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -OVERLAY_LAYER - 1, polygonOffsetUnits: -OVERLAY_LAYER - 1 }));
            pointArc.position.set(point[0], pointY + 0.08, point[1]);
            pointArc.raycast = () => {};
            scene.add(pointArc);
          }
          (pointRing.material as THREE.MeshBasicMaterial).color.set(lead ? TEAM_COLORS[lead] : "#ffffff");
        }
      }
      // follow / first-person cameras ride along with the picked player
      if (mode === "follow" || mode === "first") {
        const o = p.follow ? byId.get(p.follow) : undefined;
        const pose = o ? poseAt(o.track, s) : null;
        if (pose) {
          const fx = Math.sin(pose.yaw), fz = Math.cos(pose.yaw);
          if (mode === "first") {
            camera.position.set(pose.x + fx * 0.15, pose.y, pose.z + fz * 0.15);
            // a camera looks down -z; the drag turns the view away from where the player looks
            camera.rotation.set(clamp(pose.pitch + drag.pitch, -1.5, 1.5), pose.yaw + Math.PI + drag.yaw, 0, "YXZ");
            settling = 0;
          } else {
            // swing round the player by the drag: the (back, up) offset is turned about the player, up / down in its own plane
            const a = pose.yaw - drag.yaw, sa = Math.sin(a), ca = Math.cos(a);
            const back = FOLLOW_BACK_M * drag.dist, up = FOLLOW_UP_M * drag.dist;
            const r = Math.hypot(back, up), lift = clamp(Math.atan2(up, back) + drag.pitch, -0.2, 1.45);
            desired.set(pose.x - sa * Math.cos(lift) * r, pose.y + Math.sin(lift) * r, pose.z - ca * Math.cos(lift) * r);
            const gap = camera.position.distanceTo(desired);
            if (reducedMotion || gap > 25) camera.position.copy(desired);
            else camera.position.lerp(desired, 0.18);
            settling = camera.position.distanceTo(desired) > 0.02 ? 1 : 0;
            const ahead = 2 * Math.max(0, Math.cos(drag.yaw)); // looking ahead of the player only while behind them
            look.set(pose.x + fx * ahead, pose.y, pose.z + fz * ahead);
            camera.lookAt(look);
          }
          if (blend.on) { // eased in from wherever the camera was (the chase camera already glides to its spot)
            const [k, e] = ease(performance.now(), blend.t0);
            tmpQ.copy(camera.quaternion);
            camera.quaternion.copy(blend.fromQ).slerp(tmpQ, e);
            if (mode === "first") {
              tmpP.copy(camera.position);
              camera.position.lerpVectors(blend.fromP, tmpP, e);
            }
            if (k >= 1) blend.on = false;
            settling = 1;
          }
        }
      }
    }

    let raf = 0;
    const loop = (now: number) => {
      raf = requestAnimationFrame(loop);
      if (controls.enabled) {
        if (tw.on) {
          const [k, e] = ease(now, tw.t0);
          camera.position.lerpVectors(tw.fromP, tw.toP, e);
          controls.target.lerpVectors(tw.fromT, tw.toT, e);
          if (k >= 1) tw.on = false;
          dirty.current = true;
        }
        fly(now);
        controls.update(); // damping: carries on gliding after the mouse is released (marks the frame dirty while it moves)
        // depth precision: a near plane that grows with the distance keeps surfaces centimetres apart (floor / ring / route)
        // from flickering when the camera is far away, and still lets you get close
        const near = clamp(camera.position.distanceTo(controls.target) * 0.01, 0.05, 2);
        if (Math.abs(near - camera.near) > camera.near * 0.1) { camera.near = near; camera.updateProjectionMatrix(); dirty.current = true; }
      }
      if (!dirty.current && !settling) return; // paused and nothing moved: no work (render on demand)
      dirty.current = false;
      update();
      renderer.render(scene, camera);
      labels.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      el.removeEventListener("contextmenu", noDefault);
      el.removeEventListener("auxclick", noDefault);
      el.removeEventListener("mousedown", noAutoscroll);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("blur", onBlur);
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      renderer.domElement.removeEventListener("pointercancel", onUp);
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("wheel", onWheel);
      renderer.domElement.removeEventListener("dblclick", onDouble);
      controls.dispose();
      engine.current = null;
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        for (const mat of ([] as (THREE.Material | undefined)[]).concat(m.material)) {
          if (!mat) continue;
          for (const v of Object.values(mat)) if (v instanceof THREE.Texture) v.dispose();
          mat.dispose();
        }
      });
      skullTex.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
      labels.domElement.remove();
    };
    // the scene is built once per answer; everything else reaches the frame loop through `latest`
  }, [props.data]);

  useEffect(() => {
    engine.current?.setCamera(props.camera);
  }, [props.camera]);

  // follow / first person need someone to look from: the first player on the map
  useEffect(() => {
    if ((props.camera === "follow" || props.camera === "first") && !props.follow) {
      const s = Math.floor(props.second * props.data.hz);
      const p = props.data.players.find((q) => q.team[s]) ?? props.data.players[0];
      if (p) props.onPick(p.user_id);
    }
  }, [props.camera, props.follow, props.data, props.second, props.onPick]);

  return (
    <div className="pb3d" ref={mount} onPointerDown={() => setHint(null)}>
      <div className="pb3d-bar" role="toolbar" aria-label="Camera">
        {CAMERAS.filter((c) => c.value !== "objective" || hasObjective).map((c) => (
          <button key={c.value} type="button" className={c.value === props.camera ? "active" : ""} aria-pressed={c.value === props.camera}
            title={c.help} onClick={() => props.onCamera(c.value)}>{SHORT_LABEL[c.value]}</button>
        ))}
        <button type="button" className={`pb3d-help-btn${help ? " active" : ""}`} aria-expanded={help} aria-label="Show the controls" title="How to move around (?)"
          onClick={() => setHelp((h) => !h)}>?</button>
      </div>
      <div className={`pb3d-keys${legend ? "" : " folded"}`}>
        <button type="button" aria-expanded={legend} onClick={toggleLegend} title={legend ? "Fold the controls away" : "Show the controls"}>Controls {legend ? "▾" : "▸"}</button>
        {legend && (
          <dl>
            {LEGEND[legendKind].map(([k, v]) => (
              <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
        )}
      </div>
      {help && (
        <div className="pb3d-help" role="dialog" aria-label="3D controls">
          <div className="pb3d-help-head"><strong>Moving around</strong><button type="button" aria-label="Close" onClick={() => setHelp(false)}>×</button></div>
          <dl>
            {CONTROL_HELP.filter((r) => !r.only || r.only === (isFreeCamera(props.camera) ? "free" : props.camera) || (r.only === "ride" && !isFreeCamera(props.camera))).map((r) => (
              <div key={`${r.only}${r.keys}`}><dt>{r.keys}</dt><dd>{r.does}</dd></div>
            ))}
          </dl>
        </div>
      )}
      {hint && !help && <div className="pb3d-hint" role="status">{hint}</div>}
      {failed && <div className="pb3d-message overlay"><p>{failed}</p><button type="button" onClick={props.onUse2D}>Show the 2D map</button></div>}
      {mapState === "loading" && <div className="pb3d-note">Loading the map…</div>}
      {mapState === "failed" && <div className="pb3d-note">The map model could not be loaded: players only.</div>}
      {mapState === "none" && <div className="pb3d-note">No 3D model for this map yet: players only.</div>}
    </div>
  );
}
