// 3D playback stage (docs/WebReplayer-Review.MD, Phases 4-9). Loaded on demand (React.lazy): three.js stays out of the
// main bundle. PlaybackView keeps the clock, controls, roster and feed; this only draws the map, players and objectives
// at the clock's time, from GET /api/matches/{id}/playback3d (5 Hz, world space) and the 2D playback's events / series.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { getPlayback3d, type MatchEvent, type Playback, type Playback3D } from "../api";
import { useApi } from "../useApi";
import { Status } from "./common";
import { TEAM_COLORS, type Camera3D } from "./playback3d";

const JUMP_M = 3; // positions further apart than this between two samples are a respawn / teleport: no gliding
const SKULL_S = 5;
const DEATH_FLASH_S = 3;
const FOLLOW_BACK_M = 7; // chase camera: behind and above the picked player, looking down at them
const FOLLOW_UP_M = 4;
const RIDE_MAP_OPACITY = 0.28; // follow / first person: the map is a coarse hologram (~1 m), so see through it

export interface Map3DProps {
  id: number;
  playback: Playback;
  second: number;
  follow: string | null;
  onPick: (userId: string | null) => void;
  camera: Camera3D;
  names: boolean;
  trailSeconds: number;
  trailColor: "team" | "speed";
  deaths: MatchEvent[];
  swaps: Map<string, string>; // user id -> loadout swap text shown now
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

interface PlayerObj {
  track: Track;
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

  useEffect(() => {
    dirty.current = true; // any new props (time, toggles, picked player): draw again
  });

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    const data = props.data;
    const hz = data.hz;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    } catch (e) {
      setFailed(`3D could not start: ${(e as Error).message}`);
      return;
    }
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.domElement.className = "pb3d-labels";
    el.appendChild(labels.domElement);

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#101216");
    scene.add(new THREE.HemisphereLight(0xffffff, 0x2a3140, 2.2));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(0.6, 1, 0.4);
    scene.add(sun);

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

    const camera = new THREE.PerspectiveCamera(55, 1, 0.05, span * 12);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.screenSpacePanning = true;
    controls.maxDistance = span * 3;
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
              std.flatShading = true; // the files have no normals (app/tools/maps3d)
              mapMaterials.push({ m: std, opacity: std.opacity, transparent: std.transparent });
            }
            mesh.raycast = () => {}; // clicks pick players only
          });
          scene.add(gltf.scene);
          mapSeeThrough(mode === "follow" || mode === "first");
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
      return { track, group, head, ring, label, labelEl, labelText: "", trail, trailPos, trailCol };
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
    let cart: THREE.Mesh | null = null;
    let travelled: THREE.Line | null = null;
    let routeLen = 0;
    if (payloadSamples.length) {
      cart = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.0, 1.4), new THREE.MeshStandardMaterial({ color: attacker, emissive: attacker, emissiveIntensity: 0.35 }));
      cart.raycast = () => {};
      scene.add(cart);
    }
    if (data.objects.route?.length) {
      // the route is (x, z) per metre of payload distance; its height comes from the nearest recorded cart position
      let y = payloadSamples[0]?.q[1] ?? center.y - 1.5;
      const pts = data.objects.route.map(([x, z]) => {
        let best = 16;
        for (const { q } of payloadSamples) {
          const d = (q[0] - x) ** 2 + (q[2] - z) ** 2;
          if (d < best) { best = d; y = q[1]; }
        }
        return new THREE.Vector3(x, y + 0.1, z);
      });
      routeLen = pts.length;
      const full = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineDashedMaterial({ color: "#ffffff", dashSize: 1, gapSize: 1, transparent: true, opacity: 0.45 }));
      full.computeLineDistances();
      travelled = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts.map((v) => v.clone().setY(v.y + 0.05))), new THREE.LineBasicMaterial({ color: attacker }));
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
        new THREE.MeshBasicMaterial({ color: "#ffffff", transparent: true, opacity: 0.45, side: THREE.DoubleSide }));
      pointRing.position.set(point[0], pointY + 0.05, point[1]);
      pointRing.raycast = () => {};
      scene.add(pointRing);
    }

    // --- cameras ---
    let mode: Camera3D = latest.current.camera;
    const look = new THREE.Vector3();
    function setCamera(next: Camera3D) {
      mode = next;
      controls.enabled = next === "orbit" || next === "top";
      controls.enableRotate = next === "orbit";
      if (next === "orbit") {
        controls.target.copy(center);
        camera.position.set(center.x + span * 0.35, center.y + span * 0.5, center.z + span * 0.55);
      } else if (next === "top") {
        controls.target.copy(center);
        camera.position.set(center.x, center.y + span * 0.95, center.z + 0.01);
      }
      camera.up.set(0, 1, 0);
      mapSeeThrough(next === "follow" || next === "first");
      if (controls.enabled) controls.update();
      dirty.current = true;
    }
    engine.current = { setCamera };
    setCamera(mode);

    // --- picking: a click (not a drag) on a player picks them ---
    const ray = new THREE.Raycaster();
    let down: [number, number] | null = null;
    const onDown = (e: PointerEvent) => { down = [e.clientX, e.clientY]; };
    const onUp = (e: PointerEvent) => {
      if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 5) return;
      const box = renderer.domElement.getBoundingClientRect();
      ray.setFromCamera(new THREE.Vector2(((e.clientX - box.left) / box.width) * 2 - 1, -((e.clientY - box.top) / box.height) * 2 + 1), camera);
      const hit = ray.intersectObjects(pickable.filter((o) => o.parent?.visible !== false && o.parent?.parent?.visible !== false), false)[0];
      if (hit) latest.current.onPick(hit.object.userData.uid as string);
    };
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      labels.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      dirty.current = true;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    // --- one frame ---
    const color = new THREE.Color();
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
          const text = `${o.track.name}${swap ? `\n⇄ ${swap}` : ""}`;
          if (text !== o.labelText) { o.labelText = text; o.labelEl.textContent = text; }
          o.labelEl.className = `pb3d-label ${team === 1 ? "blue" : "orange"}${picked ? " picked" : ""}${died.has(o.track.user_id) ? " died" : ""}`;
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
      if (travelled) {
        const dist = Math.max(0, Math.min(routeLen - 1, seriesAt(p.playback.series.payload_distance, sample2d) ?? 0));
        travelled.geometry.setDrawRange(0, Math.floor(dist) + 1);
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
            pointArc = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: TEAM_COLORS[lead], transparent: true, opacity: 0.85, side: THREE.DoubleSide }));
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
            camera.rotation.set(pose.pitch, pose.yaw + Math.PI, 0, "YXZ"); // a camera looks down -z
            settling = 0;
          } else {
            desired.set(pose.x - fx * FOLLOW_BACK_M, pose.y + FOLLOW_UP_M, pose.z - fz * FOLLOW_BACK_M);
            const gap = camera.position.distanceTo(desired);
            if (reducedMotion || gap > 25) camera.position.copy(desired);
            else camera.position.lerp(desired, 0.18);
            settling = camera.position.distanceTo(desired) > 0.02 ? 1 : 0;
            look.set(pose.x + fx * 2, pose.y, pose.z + fz * 2);
            camera.lookAt(look);
          }
        }
      }
    }

    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
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
      observer.disconnect();
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
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
    <div className="pb3d" ref={mount}>
      {failed && <div className="pb3d-message overlay"><p>{failed}</p><button type="button" onClick={props.onUse2D}>Show the 2D map</button></div>}
      {mapState === "loading" && <div className="pb3d-note">Loading the map…</div>}
      {mapState === "failed" && <div className="pb3d-note">The map model could not be loaded: players only.</div>}
      {mapState === "none" && <div className="pb3d-note">No 3D model for this map yet: players only.</div>}
    </div>
  );
}
