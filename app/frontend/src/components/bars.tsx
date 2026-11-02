/** Small bars and lines that sit inside cards and table cells: share bars, split bars, a value against the site
 * average, sparklines. Every one also shows its numbers as text, so the colours are never needed to read them. */
import type { ReactNode } from "react";
import { pct } from "../format";

/** A bar for `value` out of `max` (the biggest in the table), with the text beside it. The Loadouts table's style. */
export function ShareBar({ value, max, children }: { value: number | null; max: number; children: ReactNode }) {
  const width = value != null && max > 0 ? Math.max(2, (value / max) * 100) : 0;
  return (
    <span className="share-cell">
      <span className="share-track"><span className="share-fill" style={{ width: `${width}%` }} /></span>
      <span className="share-pct">{children}</span>
    </span>
  );
}

export interface Part {
  label: string;
  value: number;
  color: string;
  /** shown in the legend after the percentage, e.g. a count or a time */
  detail?: string;
}

/** Parts of one whole as one bar, with a legend (the colours alone are not enough in the light theme). */
export function SplitBar({ parts, percentages = true }: { parts: Part[]; percentages?: boolean }) {
  const total = parts.reduce((sum, x) => sum + x.value, 0);
  if (!total) return null;
  const share = (x: Part) => x.value / total;
  return (
    <>
      <div className="split-bar" role="img" aria-label={parts.map((x) => `${x.label} ${x.detail ?? pct(share(x))}`).join(", ")}>
        {parts.filter((x) => x.value > 0).map((x) => (
          <div key={x.label} style={{ width: `${share(x) * 100}%`, background: x.color }} title={`${x.label}: ${x.detail ?? pct(share(x))}`} />
        ))}
      </div>
      <span className="split-legend muted">
        {parts.map((x) => (
          <span key={x.label}>
            <span className="split-key" style={{ background: x.color }} aria-hidden="true" />
            {x.label}
            {percentages && ` ${pct(share(x))}`}
            {x.detail && `${percentages ? " ·" : ""} ${x.detail}`}
          </span>
        ))}
      </span>
    </>
  );
}

/** A share (0-1) as a bar with a tick at the site average. The bar is scaled so both stay visible (most of these
 * are a few percent); the numbers say the exact values. */
export function VsAverage({ value, average }: { value: number | null; average: number | null | undefined }) {
  if (value == null) return <strong>–</strong>;
  if (average == null) return <strong>{pct(value)}</strong>;
  const scale = Math.max(value, average) * 1.25 || 1;
  const diff = value - average;
  const compare = Math.abs(diff) < Math.max(0.005, average * 0.1) ? "about average" : diff > 0 ? "above average" : "below average";
  return (
    <>
      <strong>{pct(value)}</strong>
      <span className="avg-track" role="img" aria-label={`${pct(value)}, site average ${pct(average)}`}>
        <span className="avg-fill" style={{ width: `${(value / scale) * 100}%` }} />
        <span className="avg-tick" style={{ left: `${(average / scale) * 100}%` }} />
      </span>
      <span className="muted">
        {compare} · site {pct(average)}
      </span>
    </>
  );
}

/** A line with no axes, for the trend under a card. Needs two or more known values. */
export function Sparkline({ values, label }: { values: (number | null)[]; label: string }) {
  const known = values.map((v, i) => [i, v] as const).filter((p): p is readonly [number, number] => p[1] != null);
  if (known.length < 2) return null;
  const ys = known.map((p) => p[1]);
  const lo = Math.min(...ys);
  const hi = Math.max(...ys);
  const w = 100;
  const h = 24;
  const x = (i: number) => (i / (values.length - 1)) * w;
  const y = (v: number) => (hi === lo ? h / 2 : h - 2 - ((v - lo) / (hi - lo)) * (h - 4));
  const points = known.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  return (
    <svg className="sparkline" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <polyline points={points} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
