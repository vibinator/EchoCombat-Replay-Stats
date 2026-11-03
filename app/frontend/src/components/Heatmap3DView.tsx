// 3D view of a heatmap (heatmaps3d.py): every layer's voxels as soft additive glows inside the map model. Loaded on demand
// (React.lazy in HeatmapView): three.js stays out of the main bundle. Colours, layer visibility and brightness come from the
// 2D view's legend and sliders, so both views read the same way.
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Heatmap3D, Heatmap3DLayer } from "../api";
import { useApi } from "../useApi";
import { useFullscreen } from "../useFullscreen";
import { Status } from "./common";
import { dressMapModel, type MapMaterial } from "./mapModel3d";

const BASE_FOV = 50;
const GLOW_SIZE = 1.15; // a voxel's dot is this many voxels wide: just overlapping neighbours, so a path reads as a thin line
const GAIN = 0.8; // brightness at slider 1 (crisp dots need more than soft glows to stay bright)
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

const VERTEX = `
uniform float uSize;
uniform float uScale;
attribute vec3 heat;
varying vec3 vHeat;
void main() {
  vHeat = heat;
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_PointSize = max(3.0, uSize * uScale / -mv.z);
  gl_Position = projectionMatrix * mv;
}`;
const FRAGMENT = `
uniform float uGain;
varying vec3 vHeat;
void main() {
  float r = length(gl_PointCoord - 0.5) * 2.0;
  float f = 1.0 - smoothstep(0.7, 1.0, r); // a solid dot with a short soft edge (not a glow)
  if (f <= 0.0) discard;
  gl_FragColor = vec4(vHeat * f * uGain, 1.0);
}`;

interface LayerObj {
  layer: Heatmap3DLayer;
  points: THREE.Points;
  heat: Float32Array;
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

    // --- the heat: one Points object per layer ---
    const material = new THREE.ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: { uSize: { value: vox * GLOW_SIZE }, uScale: { value: 1 }, uGain: { value: GAIN } },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const rgb = new THREE.Color();
    const objs: LayerObj[] = data.layers.map((layer) => {
      const position = new Float32Array(layer.count * 3);
      for (let i = 0; i < layer.count; i++) {
        position[i * 3] = ox + (layer.ix[i] + 0.5) * vox;
        position[i * 3 + 1] = oy + (layer.iy[i] + 0.5) * vox;
        position[i * 3 + 2] = oz + (layer.iz[i] + 0.5) * vox;
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute("position", new THREE.BufferAttribute(position, 3));
      const heat = new Float32Array(layer.count * 3);
      geo.setAttribute("heat", new THREE.BufferAttribute(heat, 3));
      geo.boundingSphere = new THREE.Sphere(center, span * 2); // never culled: the layers span the whole arena
      const points = new THREE.Points(geo, material);
      points.frustumCulled = false;
      points.renderOrder = 5; // after the (see-through) map
      scene.add(points);
      return { layer, points, heat };
    });
    // like the 2D heatmap's alpha curve, with a higher floor so rarely used paths stay visible: 0.4 .. 1 with log(count)
    function apply() {
      const { colors: palette, hidden: off, opacity: gain } = latest.current;
      objs.forEach(({ layer, points, heat }, k) => {
        rgb.set(palette.get(layer.key) ?? FALLBACK[k % FALLBACK.length]);
        const scale = Math.log1p(layer.max) || 1;
        for (let i = 0; i < layer.count; i++) {
          const a = 0.4 + 0.6 * (Math.log1p(layer.n[i]) / scale);
          heat[i * 3] = rgb.r * a;
          heat[i * 3 + 1] = rgb.g * a;
          heat[i * 3 + 2] = rgb.b * a;
        }
        points.geometry.attributes.heat.needsUpdate = true;
        points.visible = !off.has(layer.key);
      });
      material.uniforms.uGain.value = GAIN * gain;
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
      material.uniforms.uScale.value = buffer.y / (2 * Math.tan((camera.fov * Math.PI) / 360));
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
      material.dispose();
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        if ((o as THREE.Points).isPoints) return; // the heat's one shared material is disposed above
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
