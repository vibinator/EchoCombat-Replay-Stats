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
const H = 270;
const PAD = { left: 44, right: 16, top: 30, bottom: 50 };
const STRIP_Y = H - 40; // row of death ticks under the plot
const TEAM_COLOR = { blue: "#12a6c4", orange: "#d96a1a" } as const;
const EVENT_ICONS: Record<string, string> = {
  death_est: "☠",
  respawn: "↺",
  loadout_change: "⚙",
  round_won: "🏆",
  payload_checkpoint: "⚑",
  contest_start: "▶",
  contest_end: "■",
  player_join: "→",
  player_leave: "←",
};

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
        let area = "";
        let pen = false;
        let runStart = 0;
        let last = 0;
        const closeRun = () => {
          if (pen) area += `L${x(last / timeline.hz).toFixed(1)},${y(0).toFixed(1)}L${x(runStart / timeline.hz).toFixed(1)},${y(0).toFixed(1)}Z`;
        };
        timeline.series[k]!.forEach((v, i) => {
          if (v == null) {
            closeRun();
            pen = false;
            return;
          }
          const seg = `${pen ? "L" : "M"}${x(i / timeline.hz).toFixed(1)},${y(v).toFixed(1)}`;
          if (!pen) runStart = i;
          d += seg;
          area += seg;
          pen = true;
          last = i;
        });
        closeRun();
        return { key: k, d, area };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [timeline],
  );

  // Capture-point mode resets progress after each round, so split the chart into labelled round bands.
  const rounds = useMemo(() => {
    const won = timeline.events.filter((e) => e.type === "round_won").sort((a, b) => a.t_s - b.t_s);
    let prevB = 0;
    let prevO = 0;
    let start = 0;
    return won.map((e, i) => {
      const b = Number(e.data?.blue ?? prevB);
      const o = Number(e.data?.orange ?? prevO);
      const winner: "blue" | "orange" | null = b > prevB ? "blue" : o > prevO ? "orange" : e.team;
      const r = { n: i + 1, start, end: e.t_s, winner, blue: b, orange: o };
      prevB = b;
      prevO = o;
      start = e.t_s;
      return r;
    });
  }, [timeline]);

  const deaths = timeline.events.filter((e) => e.type === "death_est");
  const deathCount = { blue: deaths.filter((e) => e.team === "blue").length, orange: deaths.filter((e) => e.team === "orange").length };
  const checkpoints = timeline.events.filter((e) => e.type === "payload_checkpoint");
  const lead = useMemo(() => {
    const b = timeline.series.blue_points;
    const o = timeline.series.orange_points;
    if (!b || !o) return null;
    let bl = 0;
    let ol = 0;
    for (let i = 0; i < Math.min(b.length, o.length); i++) {
      const bv = b[i] ?? 0;
      const ov = o[i] ?? 0;
      if (bv > ov) bl++;
      else if (ov > bv) ol++;
    }
    const tot = bl + ol;
    return tot ? { blue: Math.round((bl / tot) * 100), orange: Math.round((ol / tot) * 100) } : null;
  }, [timeline]);
  const peak = (k: SeriesKey) => Math.round(Math.max(0, ...(timeline.series[k] ?? []).map((v) => v ?? 0)));

  function hoverAt(t: number) {
    const i = Math.round(t * timeline.hz);
    setHoverIndex(i >= 0 && i < n ? i : null);
  }

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
          <div className="tl-stats">
            <div className="tl-stat">
              <span className="tl-stat-label">Length</span>
              <strong>{duration(tMax)}</strong>
            </div>
            {rounds.length > 0 && (
              <div className="tl-stat">
                <span className="tl-stat-label">Rounds</span>
                <strong>
                  <span className="team-text blue">{rounds[rounds.length - 1].blue}</span> – <span className="team-text orange">{rounds[rounds.length - 1].orange}</span>
                </strong>
              </div>
            )}
            {checkpoints.length > 0 && (
              <div className="tl-stat">
                <span className="tl-stat-label">Checkpoints</span>
                <strong>{checkpoints.length}</strong>
              </div>
            )}
            {lead && (
              <div className="tl-stat">
                <span className="tl-stat-label">Time in the lead</span>
                <strong>
                  <span className="team-text blue">{lead.blue}%</span> / <span className="team-text orange">{lead.orange}%</span>
                </strong>
              </div>
            )}
            {keys.includes("blue_points") && keys.includes("orange_points") && (
              <div className="tl-stat">
                <span className="tl-stat-label">Peak capture</span>
                <strong>
                  <span className="team-text blue">{peak("blue_points")}%</span> / <span className="team-text orange">{peak("orange_points")}%</span>
                </strong>
              </div>
            )}
            {deaths.length > 0 && (
              <div className="tl-stat">
                <span className="tl-stat-label">Deaths (est.)</span>
                <strong>
                  <span className="team-text blue">{deathCount.blue}</span> / <span className="team-text orange">{deathCount.orange}</span>
                </strong>
              </div>
            )}
          </div>
          <div className="tl-card">
            <div className="tl-head">
              <h3 className="chart-title">{keys.length === 1 ? SERIES[keys[0]].label : "Capture progress (%)"} over time</h3>
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
            </div>
            <div className="chart-wrap">
              <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Objective progress over time" onMouseMove={onMove} onMouseLeave={() => setHoverIndex(null)}>
                <defs>
                  {keys.map((k) => (
                    <linearGradient key={k} id={`tl-fill-${k}`} x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={SERIES[k].color} stopOpacity={0.45} />
                      <stop offset="100%" stopColor={SERIES[k].color} stopOpacity={0.02} />
                    </linearGradient>
                  ))}
                </defs>
                {rounds.map((r) => (
                  <g key={r.n}>
                    {r.n % 2 === 1 && <rect className="round-band" x={x(r.start)} y={PAD.top} width={x(r.end) - x(r.start)} height={H - PAD.bottom - PAD.top} />}
                    <text className="round-label" x={(x(r.start) + x(r.end)) / 2} y={PAD.top - 14} textAnchor="middle">
                      Round {r.n}
                    </text>
                  </g>
                ))}
                {[0, 0.5, 1].map((f) => (
                  <g key={f}>
                    <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={y(yMax * f)} y2={y(yMax * f)} />
                    <text className="axis" x={PAD.left - 6} y={y(yMax * f) + 4} textAnchor="end">
                      {Math.round(yMax * f)}
                    </text>
                  </g>
                ))}
                {ticks.map((t) => (
                  <text key={t} className="axis" x={x(t)} y={H - 6} textAnchor="middle">
                    {duration(t)}
                  </text>
                ))}
                {paths.map((p) => (
                  <path key={`a-${p.key}`} d={p.area} fill={`url(#tl-fill-${p.key})`} stroke="none" />
                ))}
                {moments.map((e, i) => {
                  const round = e.type === "round_won" ? rounds.find((r) => r.end === e.t_s) : null;
                  const color = round?.winner ? TEAM_COLOR[round.winner] : "var(--muted)";
                  const label = round ? `${round.blue}–${round.orange}` : `CP${e.data?.checkpoint ?? ""}`;
                  const w = label.length * 6.5 + 12;
                  return (
                    <g key={`${e.frame}-${i}`}>
                      <line className="moment" x1={x(e.t_s)} x2={x(e.t_s)} y1={PAD.top} y2={H - PAD.bottom} style={{ stroke: color }} />
                      <rect x={x(e.t_s) - w / 2} y={PAD.top - 11} width={w} height={16} rx={8} fill={color} opacity={0.9} />
                      <text className="flag" x={x(e.t_s)} y={PAD.top} textAnchor="middle">
                        {label}
                      </text>
                    </g>
                  );
                })}
                {paths.map((p) => (
                  <path key={p.key} d={p.d} fill="none" stroke={SERIES[p.key].color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />
                ))}
                {deaths.length > 0 && (
                  <g>
                    <text className="axis strip-label" x={PAD.left - 6} y={STRIP_Y + 4} textAnchor="end">
                      ☠
                    </text>
                    {deaths.map((e, i) => (
                      <line
                        key={`${e.frame}-${i}`}
                        x1={x(e.t_s)}
                        x2={x(e.t_s)}
                        y1={STRIP_Y - 5}
                        y2={STRIP_Y + 5}
                        stroke={e.team ? TEAM_COLOR[e.team] : "var(--muted)"}
                        strokeWidth={1.5}
                        opacity={0.8}
                      >
                        <title>{`${duration(e.t_s)} · ${e.name ?? "Death"}`}</title>
                      </line>
                    ))}
                  </g>
                )}
                {hoverIndex != null && (
                  <g>
                    <line className="crosshair" x1={x(hoverIndex / timeline.hz)} x2={x(hoverIndex / timeline.hz)} y1={PAD.top} y2={H - PAD.bottom} />
                    {keys.map((k) => {
                      const v = timeline.series[k]![hoverIndex];
                      return v == null ? null : (
                        <circle key={k} cx={x(hoverIndex / timeline.hz)} cy={y(v)} r={4.5} fill={SERIES[k].color} stroke="var(--panel)" strokeWidth={2} />
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
            <p className="muted footnote">
              Flags mark rounds won (with the score) and payload checkpoints. Ticks along the bottom are estimated deaths, coloured by team. Hover the chart or an event row to compare.
            </p>
          </div>
        </>
      )}

      <h3 className="tl-events-title">Events</h3>
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
                <tr key={`${e.frame}-${e.type}-${i}`} onMouseEnter={() => hoverAt(e.t_s)} onMouseLeave={() => setHoverIndex(null)}>
                  <td className="num">{duration(e.t_s)}</td>
                  <td>
                    <span className={e.team ? `dot ${e.team}` : "dot none"} /> {EVENT_ICONS[e.type] ?? ""} {EVENT_LABELS[e.type] ?? e.type}
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
