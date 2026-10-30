import { useState, type MouseEvent } from "react";

/* Small SVG charts. Colours come from CSS variables validated per theme (dataviz validator):
   --chart-1 (blue) / --chart-2 (orange). One series per chart (no dual axes); hover tooltip on every mark. */

export interface BarDatum {
  label: string; // shown on the axis (sparse) and in the tooltip
  value: number;
  tooltip?: string;
}

const W = 800;

export function BarChart({ data, title, unit = "", height = 180, color = "var(--chart-1)" }: {
  data: BarDatum[];
  title: string;
  unit?: string;
  height?: number;
  color?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const pad = { left: 40, right: 8, top: 8, bottom: 24 };
  const max = Math.max(1, ...data.map((d) => d.value));
  const innerW = W - pad.left - pad.right;
  const slot = innerW / Math.max(1, data.length);
  const gap = Math.min(2, slot * 0.2);
  const y = (v: number) => height - pad.bottom - (v / max) * (height - pad.top - pad.bottom);
  const labelEvery = Math.max(1, Math.ceil(data.length / 8));

  function onMove(e: MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const i = Math.floor((((e.clientX - box.left) / box.width) * W - pad.left) / slot);
    setHover(i >= 0 && i < data.length ? i : null);
  }

  return (
    <figure className="chart">
      <figcaption className="chart-title">{title}</figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={title} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {[0, 0.5, 1].map((f) => (
            <g key={f}>
              <line className="grid" x1={pad.left} x2={W - pad.right} y1={y(max * f)} y2={y(max * f)} />
              <text className="axis" x={pad.left - 6} y={y(max * f) + 4} textAnchor="end">
                {Math.round(max * f).toLocaleString()}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = pad.left + i * slot + gap / 2;
            const h = height - pad.bottom - y(d.value);
            return (
              <g key={d.label}>
                {d.value > 0 && (
                  <path
                    d={roundedTop(x, y(d.value), Math.max(1, slot - gap), h, Math.min(4, (slot - gap) / 2))}
                    fill={color}
                    opacity={hover == null || hover === i ? 1 : 0.55}
                  />
                )}
                {i % labelEvery === 0 && (
                  <text className="axis" x={x + (slot - gap) / 2} y={height - 6} textAnchor="middle">
                    {d.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {hover != null && (
          <div className="tooltip chart-tooltip" style={{ left: `${((pad.left + hover * slot) / W) * 100}%` }}>
            <strong>{data[hover].tooltip ?? data[hover].label}</strong>
            <div>
              {data[hover].value.toLocaleString()}
              {unit}
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}

function roundedTop(x: number, y: number, w: number, h: number, r: number): string {
  if (h <= r) return `M${x},${y + h}V${y}H${x + w}V${y + h}Z`;
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export interface LinePoint {
  label: string;
  value: number | null;
}

/** Single-series line chart (use several for small multiples). */
export function LineChart({ data, title, format = (v: number) => v.toLocaleString(), height = 140, color = "var(--chart-1)", min }: {
  data: LinePoint[];
  title: string;
  format?: (v: number) => string;
  height?: number;
  color?: string;
  min?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const pad = { left: 44, right: 10, top: 10, bottom: 22 };
  const values = data.map((d) => d.value).filter((v): v is number => v != null);
  if (values.length === 0) return null;
  const lo = min ?? Math.min(...values);
  const hi = Math.max(...values, lo + 1e-9);
  const span = hi - lo || 1;
  const x = (i: number) => pad.left + (data.length === 1 ? 0.5 : i / (data.length - 1)) * (W - pad.left - pad.right);
  const y = (v: number) => height - pad.bottom - ((v - lo) / span) * (height - pad.top - pad.bottom);
  let d = "";
  let pen = false;
  data.forEach((p, i) => {
    if (p.value == null) {
      pen = false;
      return;
    }
    d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`;
    pen = true;
  });

  function onMove(e: MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const t = (((e.clientX - box.left) / box.width) * W - pad.left) / (W - pad.left - pad.right);
    const i = Math.round(t * (data.length - 1));
    setHover(i >= 0 && i < data.length ? i : null);
  }

  const labelEvery = Math.max(1, Math.ceil(data.length / 6));
  return (
    <figure className="chart">
      <figcaption className="chart-title">{title}</figcaption>
      <div className="chart-wrap">
        <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={title} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
          {[0, 1].map((f) => (
            <g key={f}>
              <line className="grid" x1={pad.left} x2={W - pad.right} y1={y(lo + span * f)} y2={y(lo + span * f)} />
              <text className="axis" x={pad.left - 6} y={y(lo + span * f) + 4} textAnchor="end">
                {format(lo + span * f)}
              </text>
            </g>
          ))}
          {data.map((p, i) =>
            i % labelEvery === 0 ? (
              <text key={p.label} className="axis" x={x(i)} y={height - 5} textAnchor="middle">
                {p.label}
              </text>
            ) : null,
          )}
          <path d={d} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
          {hover != null && data[hover].value != null && (
            <>
              <line className="crosshair" x1={x(hover)} x2={x(hover)} y1={pad.top} y2={height - pad.bottom} />
              <circle cx={x(hover)} cy={y(data[hover].value!)} r={4} fill={color} stroke="var(--panel)" strokeWidth={2} />
            </>
          )}
        </svg>
        {hover != null && data[hover].value != null && (
          <div className="tooltip chart-tooltip" style={{ left: `${(x(hover) / W) * 100}%` }}>
            <strong>{data[hover].label}</strong>
            <div>{format(data[hover].value!)}</div>
          </div>
        )}
      </div>
    </figure>
  );
}
