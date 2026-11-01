import { useEffect, useMemo, useRef, useState, type MouseEvent, type PointerEvent, type WheelEvent } from "react";
import type { Heatmap, HeatmapLayer, HeatmapLayerMode } from "../api";

// Layer colours. Teams use the game's colours (drawn over the minimap, not a chart surface). Gear uses the
// validated dark categorical order (dataviz), fixed per code so a colour never moves between views.
const CATEGORICAL = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];
const FIXED: Record<string, string> = {
  blue: "#19d9fc", orange: "#ea7924", deaths: "#e66767", other: "#8b919c",
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
};

export const HEATMAP_MODES: [HeatmapLayerMode, string][] = [
  ["team", "Team"],
  ["weapons", "Weapon"],
  ["ordnance", "Ordnance"],
  ["tacmod", "Tac mod"],
  ["loadout", "Full loadout"],
  ["speed", "Speed"],
];
export const HEATMAP_CELL_M = 0.1; // super fine; the only heatmap resolution offered

// Per-player layers: shades around the team colour, so the team still reads at a glance.
const TEAM_SHADES: Record<string, string[]> = {
  blue: ["#19d9fc", "#3b6fe0", "#8ff0ff", "#0f9a9a", "#a69cff"],
  orange: ["#ea7924", "#d1342a", "#ffc46b", "#b0611a", "#ff8fa0"],
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

/** One canvas: sequential per layer (one hue, alpha rising with log(count)); layers composited "over". */
function HeatCanvas({ heatmap, layers, colors, opacity }: { heatmap: Heatmap; layers: HeatmapLayer[]; colors: Map<string, string>; opacity: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    el.width = heatmap.cols;
    el.height = heatmap.rows;
    const ctx = el.getContext("2d")!;
    const img = ctx.createImageData(heatmap.cols, heatmap.rows);
    for (const layer of layers) {
      if (layer.max === 0) continue;
      const [r, g, b] = rgb(colors.get(layer.key) ?? "#c3c2b7");
      const scale = Math.log1p(layer.max);
      for (const [c, row, n] of layer.cells) {
        const a = (0.25 + 0.75 * (Math.log1p(n) / scale)) * opacity;
        const i = (row * heatmap.cols + c) * 4;
        const prev = img.data[i + 3] / 255;
        const out = a + prev * (1 - a);
        img.data[i] = (r * a + img.data[i] * prev * (1 - a)) / out;
        img.data[i + 1] = (g * a + img.data[i + 1] * prev * (1 - a)) / out;
        img.data[i + 2] = (b * a + img.data[i + 2] * prev * (1 - a)) / out;
        img.data[i + 3] = out * 255;
      }
    }
    ctx.putImageData(img, 0, 0);
  }, [heatmap, layers, colors, opacity]);
  return <canvas ref={canvas} aria-label={`Heatmap over the ${heatmap.map} minimap`} />;
}

function Stage({ heatmap, layers, colors, opacity, lookup, zoom, pan, onPan, onZoom, label }: {
  heatmap: Heatmap; layers: HeatmapLayer[]; colors: Map<string, string>; opacity: number;
  lookup: Map<number, [string, number][]>; zoom: number; pan: [number, number];
  onPan: (p: [number, number]) => void; onZoom: (z: number, at?: [number, number]) => void; label?: string;
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
  function onWheel(e: WheelEvent<HTMLDivElement>) {
    if (!e.ctrlKey && !e.altKey && zoom === 1 && e.deltaY > 0) return; // let the page scroll
    e.preventDefault();
    onZoom(zoom * (e.deltaY < 0 ? 1.25 : 0.8));
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
        onWheel={onWheel}
      >
        <div className="heatmap-inner" style={{ transform: `translate(${pan[0] * 100}%, ${pan[1] * 100}%) scale(${zoom})` }}>
          <img src={heatmap.image} alt={`${heatmap.map} minimap`} />
          <HeatCanvas heatmap={heatmap} layers={layers} colors={colors} opacity={opacity} />
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

export function HeatmapView({ heatmap, caption }: { heatmap: Heatmap; caption?: string }) {
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [showTable, setShowTable] = useState(false);
  const [opacity, setOpacity] = useState(1);
  const [split, setSplit] = useState(heatmap.mode === "player");
  const [zoom, setZoomState] = useState(1);
  const [pan, setPan] = useState<[number, number]>([0, 0]);

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
    const next = Math.min(8, Math.max(1, z));
    setZoomState(next);
    if (next === 1) setPan([0, 0]);
  }

  if (heatmap.layers.length === 0) return <p className="muted">No position data for this selection.</p>;
  const visible = heatmap.layers.filter((l) => !hidden.has(l.key));
  const totals = heatmap.layers.map((l) => ({ ...l, total: l.cells.reduce((s, [, , n]) => s + n, 0) }));
  const stageProps = { heatmap, colors, opacity, lookup, zoom, pan, onPan: setPan, onZoom: setZoom };

  return (
    <div className="heatmap">
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
        <span className="zoom-buttons">
          <button className="secondary" onClick={() => setZoom(zoom * 1.5)} aria-label="Zoom in">+</button>
          <button className="secondary" onClick={() => setZoom(zoom / 1.5)} aria-label="Zoom out">−</button>
          <button className="secondary" onClick={() => setZoom(1)} disabled={zoom === 1}>Reset</button>
        </span>
        {heatmap.layers.length > 1 && (
          <label className="inline-check">
            <input type="checkbox" checked={split} onChange={(e) => setSplit(e.target.checked)} /> Side by side
          </label>
        )}
        <button className="link" onClick={() => setShowTable(!showTable)}>
          {showTable ? "Hide table" : "Show as table"}
        </button>
      </div>

      {split ? (
        <div className="heatmap-grid">
          {visible.map((l) => (
            <Stage key={l.key} {...stageProps} layers={[l]} label={l.label} />
          ))}
        </div>
      ) : (
        <Stage {...stageProps} layers={visible} />
      )}
      <p className="muted footnote">
        {caption ?? ""} Brighter = more time spent there (log scale, {heatmap.cell_m} m cells). Scroll with Ctrl/Alt or use +/− to zoom, drag to
        pan. Hover for sample counts (2 per second).
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
