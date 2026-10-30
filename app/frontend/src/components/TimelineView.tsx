import { useMemo, useState, type MouseEvent } from "react";
import { Link } from "react-router";
import type { Timeline } from "../api";
import { duration } from "../format";

// Chart-mark versions of the team colours, validated for the dark chart surface (dataviz validator).
const SERIES = {
  blue_points: { label: "Blue capture", color: "#12a6c4" },
  orange_points: { label: "Orange capture", color: "#d96a1a" },
  payload_distance: { label: "Payload distance (m)", color: "#12a6c4" },
} as const;
type SeriesKey = keyof typeof SERIES;

const W = 800;
const H = 220;
const PAD = { left: 44, right: 16, top: 12, bottom: 28 };

const EVENT_LABELS: Record<string, string> = {
  death_est: "Death (est.)",
  respawn: "Respawn",
  loadout_change: "Loadout",
  round_won: "Round won",
  payload_checkpoint: "Checkpoint",
  contest_start: "Contest start",
  contest_end: "Contest end",
  player_join: "Joined",
  player_leave: "Left",
};
const KEY_MOMENTS = new Set(["round_won", "payload_checkpoint"]);

function niceMax(v: number): number {
  if (v <= 100) return 100;
  const step = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / step) * step;
}

export function TimelineView({ timeline }: { timeline: Timeline }) {
  const keys = (Object.keys(timeline.series) as SeriesKey[]).filter((k) => k in SERIES);
  const n = Math.max(0, ...keys.map((k) => timeline.series[k]!.length));
  const yMax = niceMax(Math.max(1, ...keys.flatMap((k) => timeline.series[k]!.map((v) => v ?? 0))));
  const tMax = Math.max(timeline.duration_s, n / timeline.hz, 1);
  const x = (t: number) => PAD.left + (t / tMax) * (W - PAD.left - PAD.right);
  const y = (v: number) => H - PAD.bottom - (v / yMax) * (H - PAD.top - PAD.bottom);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [types, setTypes] = useState<Set<string>>(new Set(["round_won", "payload_checkpoint", "death_est", "player_join", "player_leave"]));

  const paths = useMemo(
    () =>
      keys.map((k) => {
        let d = "";
        let pen = false;
        timeline.series[k]!.forEach((v, i) => {
          if (v == null) {
            pen = false;
            return;
          }
          d += `${pen ? "L" : "M"}${x(i / timeline.hz).toFixed(1)},${y(v).toFixed(1)}`;
          pen = true;
        });
        return { key: k, d };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timeline],
  );

  const ticks = Array.from({ length: 6 }, (_, i) => (tMax / 5) * i);
  const moments = timeline.events.filter((e) => KEY_MOMENTS.has(e.type));
  const eventTypes = [...new Set(timeline.events.map((e) => e.type))];
  const listed = timeline.events.filter((e) => types.has(e.type));

  function onMove(e: MouseEvent<SVGSVGElement>) {
    const box = e.currentTarget.getBoundingClientRect();
    const t = (((e.clientX - box.left) / box.width) * W - PAD.left) / (W - PAD.left - PAD.right) * tMax;
    const i = Math.round(t * timeline.hz);
    setHoverIndex(i >= 0 && i < n ? i : null);
  }

  return (
    <div className="timeline">
      {keys.length === 0 ? (
        <p className="muted">Objective progress was not recorded in this replay (older format).</p>
      ) : (
        <>
          {keys.length > 1 && (
            <div className="legend">
              {keys.map((k) => (
                <span key={k} className="legend-item">
                  <span className="swatch line" style={{ background: SERIES[k].color }} />
                  {SERIES[k].label}
                </span>
              ))}
            </div>
          )}
          <h3 className="chart-title">{keys.length === 1 ? SERIES[keys[0]].label : "Capture progress (%)"} over time</h3>
          <div className="chart-wrap">
            <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Objective progress over time" onMouseMove={onMove} onMouseLeave={() => setHoverIndex(null)}>
              {[0, 0.5, 1].map((f) => (
                <g key={f}>
                  <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(yMax * f)} y2={y(yMax * f)} />
                  <text className="axis" x={PAD.left - 6} y={y(yMax * f) + 4} textAnchor="end">
                    {Math.round(yMax * f)}
                  </text>
                </g>
              ))}
              {ticks.map((t) => (
                <text key={t} className="axis" x={x(t)} y={H - 8} textAnchor="middle">
                  {duration(t)}
                </text>
              ))}
              {moments.map((e, i) => (
                <g key={`${e.frame}-${i}`}>
                  <line className="moment" x1={x(e.t_s)} x2={x(e.t_s)} y1={PAD.top} y2={H - PAD.bottom} />
                </g>
              ))}
              {paths.map((p) => (
                <path key={p.key} d={p.d} fill="none" stroke={SERIES[p.key].color} strokeWidth={2} strokeLinejoin="round" />
              ))}
              {hoverIndex != null && (
                <g>
                  <line className="crosshair" x1={x(hoverIndex / timeline.hz)} x2={x(hoverIndex / timeline.hz)} y1={PAD.top} y2={H - PAD.bottom} />
                  {keys.map((k) => {
                    const v = timeline.series[k]![hoverIndex];
                    return v == null ? null : (
                      <circle key={k} cx={x(hoverIndex / timeline.hz)} cy={y(v)} r={4} fill={SERIES[k].color} stroke="var(--panel)" strokeWidth={2} />
                    );
                  })}
                </g>
              )}
            </svg>
            {hoverIndex != null && (
              <div className="tooltip chart-tooltip" style={{ left: `${(x(hoverIndex / timeline.hz) / W) * 100}%` }}>
                <strong>{duration(hoverIndex / timeline.hz)}</strong>
                {keys.map((k) => (
                  <div key={k}>
                    <span className="swatch line" style={{ background: SERIES[k].color }} /> {SERIES[k].label}:{" "}
                    {timeline.series[k]![hoverIndex] == null ? "–" : Math.round(timeline.series[k]![hoverIndex]!)}
                  </div>
                ))}
              </div>
            )}
          </div>
          <p className="muted footnote">Vertical lines mark rounds won / payload checkpoints.</p>
        </>
      )}

      <h3>Events</h3>
      <div className="chips" role="group" aria-label="Event types">
        {eventTypes.map((t) => (
          <button
            key={t}
            className={types.has(t) ? "chip active" : "chip"}
            aria-pressed={types.has(t)}
            onClick={() => {
              const next = new Set(types);
              if (next.has(t)) next.delete(t);
              else next.add(t);
              setTypes(next);
            }}
          >
            {EVENT_LABELS[t] ?? t}
          </button>
        ))}
      </div>
      {listed.length === 0 ? (
        <p className="muted">No events of the selected types.</p>
      ) : (
        <div className="table-wrap event-list">
          <table>
            <thead>
              <tr>
                <th className="num">Time</th>
                <th>Event</th>
                <th>Player</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {listed.map((e, i) => (
                <tr key={`${e.frame}-${e.type}-${i}`}>
                  <td className="num">{duration(e.t_s)}</td>
                  <td>
                    {e.team && <span className={`dot ${e.team}`} />} {EVENT_LABELS[e.type] ?? e.type}
                  </td>
                  <td>{e.user_id ? <Link to={`/players/${e.user_id}`}>{e.name}</Link> : e.team ? `${e.team} team` : "–"}</td>
                  <td className="muted">{describe(e.type, e.data)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function describe(type: string, data: Record<string, unknown> | null): string {
  if (!data) return "";
  if (type === "round_won") return `Blue ${data.blue} – ${data.orange} Orange`;
  if (type === "payload_checkpoint") return `Checkpoint ${data.checkpoint}${data.time_left_s != null ? `, ${duration(Number(data.time_left_s))} left` : ""}`;
  if (type === "loadout_change") return [data.weapon, data.ordnance, data.tacmod].filter(Boolean).join(" · ");
  if (type === "death_est") return `near x ${data.x}, z ${data.z}`;
  return "";
}
