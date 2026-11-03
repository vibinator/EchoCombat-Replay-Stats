// 3D view of a heatmap (heatmaps3d.py): every layer's voxels as continuous ribbons inside the map model. Loaded on demand
// (React.lazy in HeatmapView): three.js stays out of the main bundle. Colours, layer visibility and brightness come from the
// 2D view's legend and sliders, so both views read the same way.
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { LineSegments2 } from "three/examples/jsm/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/examples/jsm/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import type { Heatmap3D, Heatmap3DLayer } from "../api";
import { useApi } from "../useApi";
import { useFullscreen } from "../useFullscreen";
import { Status } from "./common";
import { dressMapModel, type MapMaterial } from "./mapModel3d";

const BASE_FOV = 50;
const RIBBON_PX = 3.5; // ribbon thickness on screen, so far paths stay visible
const MANY_VOXELS = 120_000; // above this only the three axis neighbours are joined (fewer segments)
// neighbour offsets joined into ribbons: half of the 26 neighbours, so each pair is joined once
const LINKS: [number, number, number][] = [
  [1, 0, 0], [0, 1, 0], [0, 0, 1],
  [1, 1, 0], [1, -1, 0], [1, 0, 1], [1, 0, -1], [0, 1, 1], [0, 1, -1],
  [1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
];
const DENSE_FACES = 4; // a voxel with this many of its 6 face neighbours is in a busy spot: only axis links there, so no scribble
const DEFAULT_MAP_OPACITY = 0.2; // see-through: the heat sits inside the arena
const FALLBACK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];

export interface Heat3DSource {
  key: string;
  load: () => Promise<Heatmap3D>;
}

interface Props {
  source: Heat3DSource;
  colors: Map<string, string>;
  hidden: Set<string>;
  opacity: number;
  onUse2D: () => void;
}

function webglAvailable(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function Heatmap3DView(props: Props) {
  const [webgl] = useState(webglAvailable);
  const data = useApi(props.source.load, props.source.key);
  if (!webgl) {
    return (
      <div className="pb3d-message">
        <p>3D needs WebGL, which this browser or device does not offer.</p>
        <button type="button" onClick={props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
  if (data.loading && !data.data) return <div className="pb3d-message"><p className="muted">Loading the 3D heat…</p></div>;
  if (!data.data) {
    return (
      <div className="pb3d-message">
        <Status loading={false} error={data.error} />
        <button type="button" onClick={props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
  if (data.data.layers.length === 0) {
    return (
      <div className="pb3d-message">
        <p className="muted">
          {data.data.matches_3d < data.data.matches
            ? `No 3D positions yet for ${data.data.matches === 1 ? "this match" : "these matches"}: they are recorded for matches imported since 3D playback arrived.`
            : "No position data for this selection."}
        </p>
        <button type="button" onClick={props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
  return <Scene {...props} data={data.data} />;
}

interface LayerObj {
  layer: Heatmap3DLayer;
  line: LineSegments2;
  color: Float32Array; // the line geometry's colour buffer: 3 floats per end, 2 ends per segment
  segA: Uint32Array; // voxel index at each segment's start / end
  segB: Uint32Array;
  alpha: Float32Array; // per voxel
}

function Scene({ data, colors, hidden, opacity, onUse2D }: Props & { data: Heatmap3D }) {
  const mount = useRef<HTMLDivElement>(null);
  const dirty = useRef(true);
  const screen = useFullscreen(mount);
  const latest = useRef({ colors, hidden, opacity });
  latest.current = { colors, hidden, opacity };
  const engine = useRef<{ apply: () => void; view: (v: "orbit" | "top") => void; mapOpacity: (o: number) => void } | null>(null);
  const [mapState, setMapState] = useState<"loading" | "ok" | "none" | "failed">(data.model ? "loading" : "none");
  const [failed, setFailed] = useState<string | null>(null);
  const [mapOpacity, setMapOpacity] = useState(DEFAULT_MAP_OPACITY);
  const [view, setView] = useState<"orbit" | "top">("orbit");
  const latestMapOpacity = useRef(mapOpacity); // read when the map model arrives
  latestMapOpacity.current = mapOpacity;
  const voxels = useMemo(() => data.layers.reduce((s, l) => s + l.count, 0), [data]);

  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch (e) {
      setFailed(`3D could not start: ${(e as Error).message}`);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0); // the gradient behind the canvas (styles.css .pb3d) is the sky
    renderer.toneMapping = THREE.NeutralToneMapping;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xdbe8ff, 0x2a3140, 1.5));
    const sun = new THREE.DirectionalLight(0xfff1dc, 1.9);
    sun.position.set(0.5, 1, 0.35);
    scene.add(sun);
    const fill = new THREE.DirectionalLight(0x8fb4ff, 0.7);
    fill.position.set(-0.7, 0.35, -0.6);
    scene.add(fill);

    const vox = data.vox_m;
    const [ox, oy, oz] = data.origin;
    // the arena's box: the map's play area sideways, the heat's height up
    const x0 = ox, x1 = ox + data.nx * vox, z0 = oz, z1 = oz + data.nz * vox;
    const y0 = oy, y1 = oy + data.ny * vox;
    const center = new THREE.Vector3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2);
    const span = Math.max(30, x1 - x0, z1 - z0, y1 - y0);

    const camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.1, span * 12);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.screenSpacePanning = true;
    controls.zoomToCursor = true;
    controls.maxDistance = span * 3;
    controls.minDistance = 1;
    controls.addEventListener("change", () => { dirty.current = true; });
    const place = (v: "orbit" | "top") => {
      controls.target.copy(center);
      if (v === "top") camera.position.set(center.x, center.y + span * 1.05, center.z + 0.01);
      else camera.position.set(center.x + span * 0.55, center.y + span * 0.55, center.z + span * 0.8);
      controls.enableRotate = v !== "top";
      controls.update();
      dirty.current = true;
    };
    place("orbit");

    // --- the map ---
    let disposed = false;
    let mapMaterials: MapMaterial[] = [];
    const setMapOpacity = (o: number) => {
      for (const x of mapMaterials) {
        x.m.transparent = o < 1 || x.transparent;
        x.m.opacity = Math.min(x.opacity, o);
        x.m.depthWrite = !x.m.transparent;
        x.m.needsUpdate = true;
      }
      dirty.current = true;
    };
    if (data.model) {
      new GLTFLoader().load(
        data.model,
        (gltf) => {
          if (disposed) return;
          mapMaterials = dressMapModel(gltf.scene);
          scene.add(gltf.scene);
          const floor = new THREE.Box3().setFromObject(gltf.scene).min.y - 0.6;
          const size = Math.ceil((span * 1.7) / 10) * 10;
          const grid = new THREE.GridHelper(size, size / 10, 0x34496a, 0x1d2940);
          (grid.material as THREE.Material).transparent = true;
          (grid.material as THREE.Material).opacity = 0.55;
          grid.position.set(center.x, floor, center.z);
          scene.add(grid);
          setMapOpacity(latestMapOpacity.current);
          setMapState("ok");
        },
        undefined,
        () => !disposed && setMapState("failed"),
      );
    } else {
      const size = Math.ceil(span / 10) * 10;
      const grid = new THREE.GridHelper(size, size / 10, 0x3a4150, 0x262b35);
      grid.position.set(center.x, y0 - 0.6, center.z);
      scene.add(grid);
    }

    // --- the heat: one ribbon object per layer; neighbouring voxels are joined by line segments ---
    const rgb = new THREE.Color();
    const t0 = performance.now();
    const lineMats: LineMaterial[] = [];
    const nbMax = data.layers.reduce((m, l) => Math.max(m, l.count), 0) > MANY_VOXELS ? 3 : LINKS.length;
    const objs: LayerObj[] = data.layers.map((layer) => {
      const at = new Map<number, number>();
      for (let i = 0; i < layer.count; i++) at.set((layer.iy[i] * data.nz + layer.iz[i]) * data.nx + layer.ix[i], i);
      const pos: number[] = [];
      const a: number[] = [];
      const b: number[] = [];
      const linked = new Uint8Array(layer.count);
      const dense = new Uint8Array(layer.count);
      for (let i = 0; i < layer.count; i++) {
        let faces = 0;
        for (let k = 0; k < 3; k++) {
          const [dx, dy, dz] = LINKS[k];
          for (const sg of [1, -1]) {
            const nx = layer.ix[i] + sg * dx, ny = layer.iy[i] + sg * dy, nz = layer.iz[i] + sg * dz;
            if (nx < 0 || nx >= data.nx || ny < 0 || ny >= data.ny || nz < 0 || nz >= data.nz) continue;
            if (at.has((ny * data.nz + nz) * data.nx + nx)) faces++;
          }
        }
        if (faces >= DENSE_FACES) dense[i] = 1;
      }
      const cx = (i: number) => ox + (layer.ix[i] + 0.5) * vox;
      const cy = (i: number) => oy + (layer.iy[i] + 0.5) * vox;
      const cz = (i: number) => oz + (layer.iz[i] + 0.5) * vox;
      for (let i = 0; i < layer.count; i++) {
        const x = layer.ix[i], y = layer.iy[i], z = layer.iz[i];
        for (let k = 0; k < nbMax; k++) {
          const [dx, dy, dz] = LINKS[k];
          const nx = x + dx, ny = y + dy, nz = z + dz;
          if (nx < 0 || nx >= data.nx || ny < 0 || ny >= data.ny || nz < 0 || nz >= data.nz) continue;
          const j = at.get((ny * data.nz + nz) * data.nx + nx);
          if (j === undefined) continue;
          if (k >= 3 && (dense[i] || dense[j])) continue; // diagonals only along sparse paths
          linked[i] = linked[j] = 1;
          pos.push(cx(i), cy(i), cz(i), cx(j), cy(j), cz(j));
          a.push(i);
          b.push(j);
        }
      }
      for (let i = 0; i < layer.count; i++) {
        if (linked[i]) continue; // a lone voxel: a short stub, so it still shows
        pos.push(cx(i) - vox * 0.3, cy(i), cz(i), cx(i) + vox * 0.3, cy(i), cz(i));
        a.push(i);
        b.push(i);
      }
      const geo = new LineSegmentsGeometry();
      geo.setPositions(new Float32Array(pos));
      geo.setColors(new Float32Array(a.length * 6));
      const color = (geo.attributes.instanceColorStart as THREE.InterleavedBufferAttribute).data.array as Float32Array;
      const mat = new LineMaterial({ vertexColors: true, linewidth: RIBBON_PX, transparent: true, depthWrite: false });
      lineMats.push(mat);
      const line = new LineSegments2(geo, mat);
      line.frustumCulled = false;
      line.renderOrder = 5; // after the (see-through) map
      line.raycast = () => {};
      scene.add(line);
      return { layer, line, color, segA: Uint32Array.from(a), segB: Uint32Array.from(b), alpha: new Float32Array(layer.count) };
    });
    console.info(`heatmap3d: ${data.layers.reduce((n, l) => n + l.count, 0)} voxels -> ${objs.reduce((n, o) => n + o.segA.length, 0)} ribbon segments, built in ${Math.round(performance.now() - t0)} ms`);
    // like the 2D heatmap's alpha curve, with a higher floor so rarely used paths stay visible: 0.4 .. 1 with log(count)
    function apply() {
      const { colors: palette, hidden: off, opacity: gain } = latest.current;
      const solid = Math.min(1, Math.max(0.2, gain)); // the brightness slider (0.2 .. 1, default 1): how solid the ribbons are
      objs.forEach(({ layer, line, color, segA, segB, alpha }, k) => {
        rgb.set(palette.get(layer.key) ?? FALLBACK[k % FALLBACK.length]);
        const scale = Math.log1p(layer.max) || 1;
        for (let i = 0; i < layer.count; i++) alpha[i] = 0.55 + 0.45 * (Math.log1p(layer.n[i]) / scale);
        for (let s = 0; s < segA.length; s++) {
          const p = alpha[segA[s]], q = alpha[segB[s]];
          color[s * 6] = rgb.r * p; color[s * 6 + 1] = rgb.g * p; color[s * 6 + 2] = rgb.b * p;
          color[s * 6 + 3] = rgb.r * q; color[s * 6 + 4] = rgb.g * q; color[s * 6 + 5] = rgb.b * q;
        }
        (line.geometry.attributes.instanceColorStart as THREE.InterleavedBufferAttribute).data.needsUpdate = true;
        (line.material as LineMaterial).opacity = solid;
        line.visible = !off.has(layer.key);
      });
      dirty.current = true;
    }
    apply();
    engine.current = { apply, view: place, mapOpacity: setMapOpacity };

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      const buffer = renderer.getDrawingBufferSize(new THREE.Vector2());
      for (const m of lineMats) m.resolution.set(buffer.x, buffer.y);
      dirty.current = true;
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    const noMenu = (e: Event) => e.preventDefault();
    el.addEventListener("contextmenu", noMenu);
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (controls.update()) dirty.current = true; // damping keeps gliding after the pointer is released
      if (!dirty.current) return;
      dirty.current = false;
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      disposed = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      el.removeEventListener("contextmenu", noMenu);
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
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [data]);

  useEffect(() => engine.current?.apply(), [colors, hidden, opacity, data]);
  useEffect(() => engine.current?.mapOpacity(mapOpacity), [mapOpacity]);

  return (
    <div className={`pb3d${screen.fakeClass}`} ref={mount}>
      <div className="pb3d-bar" role="toolbar" aria-label="Camera">
        {(["orbit", "top"] as const).map((v) => (
          <button key={v} type="button" className={v === view ? "active" : ""} aria-pressed={v === view}
            onClick={() => { setView(v); engine.current?.view(v); }}>{v === "orbit" ? "Orbit" : "Top"}</button>
        ))}
        <button type="button" onClick={() => engine.current?.view(view)} title="Put the camera back">Reset</button>
        <label className="pb3d-slider" title="How solid the map is drawn: lower to see the heat inside it">
          Map
          <input type="range" min={0.05} max={1} step={0.05} value={mapOpacity} onChange={(e) => setMapOpacity(Number(e.target.value))} />
        </label>
        <button type="button" className="pb3d-full" aria-pressed={screen.full} aria-label={screen.full ? "Leave full screen" : "Full screen"}
          title={screen.full ? "Leave full screen (Esc)" : "Full screen"} onClick={screen.toggle}>{screen.full ? "✕" : "⛶"}</button>
        <button type="button" className="pb3d-help-btn" onClick={onUse2D} title="Back to the flat map" aria-label="Show the 2D map">2D</button>
      </div>
      {failed && <div className="pb3d-message overlay"><p>{failed}</p><button type="button" onClick={onUse2D}>Show the 2D map</button></div>}
      {mapState === "loading" && <div className="pb3d-note">Loading the map…</div>}
      {mapState === "failed" && <div className="pb3d-note">The map model could not be loaded: heat only.</div>}
      {mapState === "none" && <div className="pb3d-note">No 3D model for this map yet: heat only.</div>}
      {data.matches_3d < data.matches && mapState !== "loading" && (
        <div className="pb3d-note" style={{ top: 36 }}>
          3D heat from {data.matches_3d.toLocaleString()} of {data.matches.toLocaleString()} matches (the others have no height recorded). {voxels.toLocaleString()} voxels.
        </div>
      )}
    </div>
  );
}
