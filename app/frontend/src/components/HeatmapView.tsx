import { lazy, Suspense, useEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent, type ReactNode } from "react";
import type { Heatmap, HeatmapLayer, HeatmapLayerMode } from "../api";
import { useFullscreen } from "../useFullscreen";
import type { Heat3DSource } from "./Heatmap3DView";

const Heatmap3DView = lazy(() => import("./Heatmap3DView")); // three.js loads when 3D is first asked for

// Layer colours. Teams use the game's colours (drawn over the minimap, not a chart surface). Gear uses the
// validated dark categorical order (dataviz), fixed per code so a colour never moves between views.
const CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const FIXED: Record<string, string> = {
  blue: "#56b4e9", orange: "#f0a030", deaths: "#e66767", other: "#8b919c",
  // weapons
  assault: CATEGORICAL[0], blaster: CATEGORICAL[1], scout: CATEGORICAL[2], rocket: CATEGORICAL[3],
  magnum: CATEGORICAL[4], smg: CATEGORICAL[5], chain: CATEGORICAL[6], rifle: CATEGORICAL[7],
  // ordnance
  det: CATEGORICAL[0], stun: CATEGORICAL[1], arc: CATEGORICAL[2], burst: CATEGORICAL[3],
  loc: CATEGORICAL[4], dot: CATEGORICAL[5], drone: CATEGORICAL[6],
  // tac mods
  heal: CATEGORICAL[0], sensor: CATEGORICAL[1], shield: CATEGORICAL[2], wraith: CATEGORICAL[3],
  buff: CATEGORICAL[4], smoke: CATEGORICAL[5], point: CATEGORICAL[6],
  // speed bands: one hue, light (slow) -> dark (fast)
  stopped: "#fde0c5", slow: "#f9a867", medium: "#e8742a", fast: "#b5470b",
  // pose
  upside: "#d55181", upright: "#3987e5",
};
/** "Compare": the two colours of the home page's compare (map_heat.COMPARE_RGB), first layer / second layer. */
const COMPARE_COLORS: [string, string] = ["#ff4fa3", "#2fd69b"];

export const HEATMAP_MODES: [HeatmapLayerMode, string][] = [
  ["team", "Team"],
  ["weapons", "Weapon"],
  ["ordnance", "Ordnance"],
  ["tacmod", "Tac mod"],
  ["loadout", "Full loadout"],
  ["speed", "Speed"],
  ["pose", "Upside down"],
];
export const HEATMAP_CELL_M = 0.1; // super fine; the only heatmap resolution offered

// Per-player layers: shades around the team colour, so the team still reads at a glance.
const TEAM_SHADES: Record<string, string[]> = {
  blue: ["#56b4e9", "#4a7fd0", "#9fd3f2", "#3a9bb0", "#a99be0"],
  orange: ["#f0a030", "#f5bd62", "#f7d9a0", "#d98512", "#f2ae72"],
};

function layerColors(layers: HeatmapLayer[]): Map<string, string> {
  const seen: Record<string, number> = {};
  return new Map(layers.map((l, i) => {
    const shades = l.team ? TEAM_SHADES[l.team] : undefined;
    if (shades) {
      const n = (seen[l.team!] = (seen[l.team!] ?? -1) + 1);
      return [l.key, shades[n % shades.length]];
    }
    return [l.key, FIXED[l.key] ?? CATEGORICAL[i % CATEGORICAL.length]];
  }));
}

function rgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** One canvas: sequential per layer (one hue, alpha rising with log(count)). Where layers overlap the colours are MIXED by how busy
 *  each layer is there (not painted over one another), so neither team hides the other; the peak is capped below solid so the
 *  busiest cells do not glare (user, 2026-11-06: it looked too blue). */
function HeatCanvas({ heatmap, layers, colors, opacity }: { heatmap: Heatmap; layers: HeatmapLayer[]; colors: Map<string, string>; opacity: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    el.width = heatmap.cols;
    el.height = heatmap.rows;
    const ctx = el.getContext("2d")!;
    const img = ctx.createImageData(heatmap.cols, heatmap.rows);
    const cells = heatmap.cols * heatmap.rows;
    const wr = new Float32Array(cells), wg = new Float32Array(cells), wb = new Float32Array(cells), wsum = new Float32Array(cells);
    const clear = new Float32Array(cells).fill(1); // share of the minimap left showing through
    for (const layer of layers) {
      if (layer.max === 0) continue;
      const [r, g, b] = rgb(colors.get(layer.key) ?? "#c3c2b7");
      const scale = Math.log1p(layer.max);
      for (const [c, row, n] of layer.cells) {
        const a = (0.2 + 0.7 * Math.pow(Math.log1p(n) / scale, 1.3)) * opacity;
        const i = row * heatmap.cols + c;
        wr[i] += r * a;
        wg[i] += g * a;
        wb[i] += b * a;
        wsum[i] += a;
        clear[i] *= 1 - a;
      }
    }
    for (let i = 0; i < cells; i++) {
      if (!wsum[i]) continue;
      img.data[i * 4] = wr[i] / wsum[i];
      img.data[i * 4 + 1] = wg[i] / wsum[i];
      img.data[i * 4 + 2] = wb[i] / wsum[i];
      img.data[i * 4 + 3] = (1 - clear[i]) * 255;
    }
    ctx.putImageData(img, 0, 0);
  }, [heatmap, layers, colors, opacity]);
  return <canvas ref={canvas} aria-label={`Heatmap over the ${heatmap.map} minimap`} />;
}

// "Compare" (user, 2026-11-10; the home page's compare for one heatmap's own layers). Each layer is taken as a share
// of its own total and smoothed over COMPARE_BLUR_M (paths are thin lines at this cell size: cell by cell two layers
// hardly ever meet); a spot is drawn in the colour of the layer that is relatively more often there, from
// COMPARE_FROM (1.2 times as often) to COMPARE_TOP (3 times), and left clear where the two together are thin.
const COMPARE_BLUR_M = 0.6;
const COMPARE_FROM = 0.045;
const COMPARE_TOP = 0.25;
const COMPARE_MIN = 0.35; // of the average density (both layers together) where either was: thinner spots stay clear

function smoothed(layer: HeatmapLayer, cols: number, rows: number, radius: number): { grid: Float32Array; total: number } {
  let grid = new Float32Array(cols * rows);
  let total = 0;
  for (const [c, r, n] of layer.cells) {
    grid[r * cols + c] = n;
    total += n;
  }
  const width = 2 * radius + 1;
  for (let pass = 0; pass < 2; pass++) {
    for (const [step, line, count] of [[1, cols, rows], [cols, rows, cols]] as const) {
      // a running sum along each row (step 1) and then each column (step cols)
      const out = new Float32Array(cols * rows);
      for (let k = 0; k < count; k++) {
        const base = step === 1 ? k * cols : k;
        let sum = 0;
        for (let i = 0; i < line + radius; i++) {
          if (i < line) sum += grid[base + i * step];
          if (i - width >= 0) sum -= grid[base + (i - width) * step];
          if (i - radius >= 0 && i - radius < line) out[base + (i - radius) * step] = sum / width;
        }
      }
      grid = out;
    }
  }
  return { grid, total };
}

function CompareCanvas({ heatmap, layers, opacity }: { heatmap: Heatmap; layers: [HeatmapLayer, HeatmapLayer]; opacity: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const { cols, rows } = heatmap;
    el.width = cols;
    el.height = rows;
    const ctx = el.getContext("2d")!;
    const img = ctx.createImageData(cols, rows);
    const radius = Math.max(1, Math.round(COMPARE_BLUR_M / heatmap.cell_m));
    const a = smoothed(layers[0], cols, rows, radius);
    const b = smoothed(layers[1], cols, rows, radius);
    if (a.total && b.total) {
      let sum = 0;
      let reached = 0;
      for (let i = 0; i < cols * rows; i++) {
        const both = a.grid[i] / a.total + b.grid[i] / b.total;
        if (both > 0) {
          sum += both;
          reached++;
        }
      }
      const floor = (COMPARE_MIN * sum) / Math.max(1, reached); // against the average of everywhere the smoothing reaches
      const tints = COMPARE_COLORS.map(rgb);
      for (let i = 0; i < cols * rows; i++) {
        const pa = a.grid[i] / a.total;
        const pb = b.grid[i] / b.total;
        if (pa + pb < floor) continue;
        const lean = pa / (pa + pb) - 0.5;
        const strength = (Math.abs(lean) - COMPARE_FROM) / (COMPARE_TOP - COMPARE_FROM);
        if (strength <= 0) continue;
        const [r, g, bl] = tints[lean > 0 ? 0 : 1];
        img.data[i * 4] = r;
        img.data[i * 4 + 1] = g;
        img.data[i * 4 + 2] = bl;
        img.data[i * 4 + 3] = (0.3 + 0.65 * Math.min(1, strength)) * opacity * 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [heatmap, layers, opacity]);
  return <canvas ref={canvas} aria-label={`${layers[0].label} compared with ${layers[1].label} over the ${heatmap.map} minimap`} />;
}

function Stage({ heatmap, layers, colors, opacity, lookup, zoom, pan, onPan, label, compare }: {
  heatmap: Heatmap; layers: HeatmapLayer[]; colors: Map<string, string>; opacity: number;
  lookup: Map<number, [string, number][]>; zoom: number; pan: [number, number];
  onPan: (p: [number, number]) => void; label?: string; compare?: [HeatmapLayer, HeatmapLayer];
}) {
  const [hover, setHover] = useState<{ x: number; y: number; lines: string[] } | null>(null);
  const drag = useRef<{ x: number; y: number; pan: [number, number] } | null>(null);

  function onMove(e: MouseEvent<HTMLDivElement>) {
    const inner = (e.currentTarget.firstElementChild as HTMLElement).getBoundingClientRect();
    const box = e.currentTarget.getBoundingClientRect();
    const c = Math.floor(((e.clientX - inner.left) / inner.width) * heatmap.cols);
    const r = Math.floor(((e.clientY - inner.top) / inner.height) * heatmap.rows);
    const totals = new Map<string, number>();
    for (let dr = -1; dr <= 1; dr++)
      for (let dc = -1; dc <= 1; dc++)
        for (const [l, n] of lookup.get((r + dr) * heatmap.cols + c + dc) ?? []) totals.set(l, (totals.get(l) ?? 0) + n);
    const lines = [...totals].map(([l, n]) => `${l}: ${n}`);
    setHover(lines.length ? { x: e.clientX - box.left, y: e.clientY - box.top, lines } : null);
  }
  function onPointerDown(e: PointerEvent<HTMLDivElement>) {
    if (zoom <= 1) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, pan };
  }
  function onPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    const box = e.currentTarget.getBoundingClientRect();
    onPan([drag.current.pan[0] + (e.clientX - drag.current.x) / box.width, drag.current.pan[1] + (e.clientY - drag.current.y) / box.height]);
  }

  return (
    <div className="heatmap-frame">
      {label && <div className="heatmap-label">{label}</div>}
      <div
        className={`heatmap-stage${zoom > 1 ? " zoomed" : ""}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => (drag.current = null)}
      >
        <div className="heatmap-inner" style={{ transform: `translate(${pan[0] * 100}%, ${pan[1] * 100}%) scale(${zoom})` }}>
          <img src={heatmap.image} alt={`${heatmap.map} minimap`} />
          {compare ? <CompareCanvas heatmap={heatmap} layers={compare} opacity={opacity} /> : <HeatCanvas heatmap={heatmap} layers={layers} colors={colors} opacity={opacity} />}
        </div>
        {hover && (
          <div className="tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
            {hover.lines.map((line) => <div key={line}>{line}</div>)}
          </div>
        )}
      </div>
    </div>
  );
}

/** `view3d` = where the same heatmap can be had in 3D (absent: 2D only, e.g. the deaths layer has no height).
 *  `controls` = the page's own selectors, shown again in the 3D view's full screen (where the page is hidden). */
export function HeatmapView({ heatmap, caption, view3d, controls }: { heatmap: Heatmap; caption?: string; view3d?: Heat3DSource; controls?: ReactNode }) {
  const [wants3d, setWants3d] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const screen = useFullscreen(root); // the 2D view's full screen: legend, sliders and the page's selectors come along
  const is3d = wants3d && !!view3d;
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showTable, setShowTable] = useState(false);
  const [opacity, setOpacity] = useState(1);
  const [split, setSplit] = useState(heatmap.mode === "player");
  const [zoom, setZoomState] = useState(1);
  const [pan, setPan] = useState<[number, number]>([0, 0]);
  const [versus, setVersus] = useState<[string, string] | null>(null); // "Compare": two layer keys

  const colors = useMemo(() => layerColors(heatmap.layers), [heatmap]);
  useEffect(() => setSplit(heatmap.mode === "player"), [heatmap.mode]); // one small map per player by default
  const lookup = useMemo(() => {
    const m = new Map<number, [string, number][]>();
    for (const layer of heatmap.layers)
      for (const [c, r, n] of layer.cells) {
        const key = r * heatmap.cols + c;
        m.set(key, [...(m.get(key) ?? []), [layer.label, n]]);
      }
    return m;
  }, [heatmap]);
  useEffect(() => {
    setZoomState(1);
    setPan([0, 0]);
  }, [heatmap.map]);

  function setZoom(z: number) {
    const next = Math.min(24, Math.max(1, z));
    setZoomState(next);
    if (next === 1) setPan([0, 0]);
  }

  if (heatmap.layers.length === 0)
    return (
      <p className="muted">
        {heatmap.mode === "pose"
          ? "No upside-down data for these matches yet: it is kept for matches processed since the 2026-11-10 update; older ones get it when the archive is read again."
          : "No position data for this selection."}
      </p>
    );
  const visible = heatmap.layers.filter((l) => !hidden.has(l.key));
  const byKey = new Map(heatmap.layers.map((l) => [l.key, l]));
  // the two layers compared, while both are still in this answer (another mode or map: back to the plain heat)
  const compare = !is3d && versus && versus[0] !== versus[1] && byKey.has(versus[0]) && byKey.has(versus[1])
    ? ([byKey.get(versus[0])!, byKey.get(versus[1])!] as [HeatmapLayer, HeatmapLayer]) : undefined;
  const totals = heatmap.layers.map((l) => ({ ...l, total: l.cells.reduce((s, [, , n]) => s + n, 0) }));
  const stageProps = { heatmap, colors, opacity, lookup, zoom, pan, onPan: setPan };

  return (
    <div className={`heatmap pb-fs${screen.fakeClass}${screen.full ? " is-full" : ""}`} ref={root}>
      {screen.full && controls && <div className="filters">{controls}</div>}
      <div className="legend" role="group" aria-label="Layers (key)">
        {totals.map((l) => (
          <label key={l.key} className="legend-item">
            <input
              type="checkbox"
              checked={!hidden.has(l.key)}
              onChange={() => {
                const next = new Set(hidden);
                if (next.has(l.key)) next.delete(l.key);
                else next.add(l.key);
                setHidden(next);
              }}
            />
            <span className="swatch" style={{ background: colors.get(l.key) }} />
            {l.label}
          </label>
        ))}
      </div>
      <div className="heatmap-tools">
        <label>
          Opacity
          <input type="range" min={0.2} max={1} step={0.05} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} />
        </label>
        {view3d && (
          <span className="zoom-buttons" role="group" aria-label="Flat or 3D">
            <button className={is3d ? "secondary" : ""} aria-pressed={!is3d} onClick={() => setWants3d(false)}>2D</button>
            <button className={is3d ? "" : "secondary"} aria-pressed={is3d} onClick={() => setWants3d(true)}>3D</button>
          </span>
        )}
        {!is3d && (
          <button type="button" className="secondary pb-fs-btn" aria-pressed={screen.full} title={screen.full ? "Leave full screen (Esc)" : "Full screen: the map as big as the screen, with all the controls"} onClick={screen.toggle}>{screen.full ? "✕ Exit full screen" : "⛶ Full screen"}</button>
        )}
        {!is3d && (
          <span className="zoom-buttons">
            <button className="secondary" onClick={() => setZoom(zoom * 1.5)} aria-label="Zoom in">+</button>
            <button className="secondary" onClick={() => setZoom(zoom / 1.5)} aria-label="Zoom out">−</button>
            <button className="secondary" onClick={() => setZoom(1)} disabled={zoom === 1}>Reset</button>
          </span>
        )}
        {!is3d && heatmap.layers.length > 1 && !compare && (
          <label className="inline-check">
            <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} /> Side by side
          </label>
        )}
        {!is3d && heatmap.layers.length > 1 && (
          <span className="heatmap-compare" title="Lay one layer against another: each in its own colour where it is relatively more often than the other">
            <label className="inline-check">
              <input type="checkbox" checked={!!compare} onChange={(e) => setVersus(e.target.checked ? [heatmap.layers[0].key, heatmap.layers[1].key] : null)} /> Compare
            </label>
            {compare && (
              <>
                <select aria-label="First layer" value={compare[0].key} onChange={(e) => setVersus([e.target.value, e.target.value === compare[1].key ? compare[0].key : compare[1].key])}>
                  {heatmap.layers.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
                <button type="button" className="secondary" aria-label="Swap the two layers" title="Swap" onClick={() => setVersus([compare[1].key, compare[0].key])}>⇄</button>
                <select aria-label="Second layer" value={compare[1].key} onChange={(e) => setVersus([e.target.value === compare[0].key ? compare[1].key : compare[0].key, e.target.value])}>
                  {heatmap.layers.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              </>
            )}
          </span>
        )}
        <button className="link" onClick={() => setShowTable(!showTable)}>
          {showTable ? "Hide table" : "Show as table"}
        </button>
      </div>

      {is3d && view3d ? (
        <Suspense fallback={<div className="pb3d-message"><p className="muted">Loading 3D…</p></div>}>
          <Heatmap3DView source={view3d} colors={colors} hidden={hidden} opacity={opacity} onUse2D={() => setWants3d(false)} onHidden={setHidden} onOpacity={setOpacity} controls={controls} />
        </Suspense>
      ) : compare ? (
        <Stage {...stageProps} layers={compare} compare={compare} />
      ) : split ? (
        <div className="heatmap-grid">
          {visible.map((l) => (
            <Stage key={l.key} {...stageProps} layers={[l]} label={l.label} />
          ))}
        </div>
      ) : (
        <Stage {...stageProps} layers={visible} />
      )}
      {compare && (
        <p className="muted footnote">
          <span className="swatch" style={{ background: COMPARE_COLORS[0] }} /> where {compare[0].label} is relatively more often,{" "}
          <span className="swatch" style={{ background: COMPARE_COLORS[1] }} /> where {compare[1].label} is; each measured against its own total, smoothed over about half a metre. Clear = about as often, or too little of either.
        </p>
      )}
      <p className="muted footnote">
        {caption ?? ""} {compare ? "" : "Brighter = more time spent there (log scale). "}
        {heatmap.mode === "pose" && "Upside down is kept for matches processed since the 2026-11-10 update; older matches are left out of this colouring. "}
        {is3d
          ? "In 3D each glow is a 0.5 m cube of space; the map is drawn see-through so the heat shows inside it. Drag to turn, right-drag to move, wheel to zoom."
          : `${heatmap.cell_m} m cells. Use the + / − buttons to zoom in up to 24×, drag to pan. Hover for sample counts (2 per second).`}
      </p>

      {showTable && (
        <table>
          <thead>
            <tr>
              <th>Layer</th>
              <th className="num">Cells visited</th>
              <th className="num">Samples</th>
              <th className="num">Busiest cell</th>
            </tr>
          </thead>
          <tbody>
            {totals.map((l) => (
              <tr key={l.key}>
                <td><span className="swatch" style={{ background: colors.get(l.key) }} /> {l.label}</td>
                <td className="num">{l.cells.length.toLocaleString()}</td>
                <td className="num">{l.total.toLocaleString()}</td>
                <td className="num">{l.max}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
