import type { MatchDetail, MatchPlayer, StoryStep, Team } from "../api";
import { duration, num, pct, teamLabel } from "../format";

/** The match on one line: where each round was won (capture point) or each checkpoint reached (payload), placed by
 * match time, with the result at the end. Hidden when the replay has no such events (older files, unchanged score). */
export function MatchStory({ m }: { m: MatchDetail }) {
  const steps = m.story ?? [];
  if (steps.length === 0 || m.duration_s <= 0) return null;
  const at = (t: number) => `${Math.min(100, Math.max(0, (t / m.duration_s) * 100))}%`;
  const payload = m.mode === "payload";
  const attack = m.attacking_team;
  const end = payload
    ? m.winner == null ? "Result unknown" : m.winner === attack ? "Payload delivered" : `Held at checkpoint ${m.final_payload_checkpoint ?? 0}`
    : m.winner ? `${teamLabel(m.winner)} wins ${m.blue_rounds}–${m.orange_rounds}` : "No winner";

  // capture point: the stretch before each round's end belongs to that round's winner
  const segments = payload ? [] : steps.map((s, i) => ({ from: i ? steps[i - 1].t_s : 0, to: s.t_s, team: s.type === "round" ? s.team : null }));

  return (
    <div className="match-story" aria-label="How the match went">
      <div className="story-track">
        {segments.map((g, i) => (
          <span key={i} className={`story-seg ${g.team ?? ""}`} style={{ left: at(g.from), width: `calc(${at(g.to)} - ${at(g.from)})` }} />
        ))}
        {payload && attack && (() => {
          const last = steps.at(-1)!;
          return <span className={`story-seg ${attack}`} style={{ left: 0, width: at(last.t_s) }} />;
        })()}
        {steps.map((s, i) => (
          <span key={i} className={`story-mark ${markTeam(s, attack) ?? ""}`} style={{ left: at(s.t_s) }} title={stepText(s, i)} />
        ))}
      </div>
      <ol className="story-steps">
        {steps.map((s, i) => (
          <li key={i}>
            <span className={`story-dot ${markTeam(s, attack) ?? ""}`} aria-hidden />
            {stepText(s, i)}
          </li>
        ))}
        <li className="story-end"><strong>{end}</strong> <span className="muted">{duration(m.duration_s)}</span></li>
      </ol>
    </div>
  );
}

const markTeam = (s: StoryStep, attack: Team | null): Team | null => (s.type === "round" ? s.team : attack);

function stepText(s: StoryStep, i: number): string {
  if (s.type === "round") {
    const score = s.blue != null && s.orange != null ? ` (${s.blue}–${s.orange})` : "";
    return `Round ${i + 1}: ${s.team ? teamLabel(s.team) : "?"}${score} at ${duration(s.t_s)}`;
  }
  const left = s.time_left_s != null ? `, ${duration(s.time_left_s)} left` : "";
  return `Checkpoint ${s.checkpoint ?? "?"} at ${duration(s.t_s)}${left}`;
}

type Row = { label: string; hint: string; blue: number | null; orange: number | null; show: (v: number) => string };

/** Play-time weighted mean of a per-player rate, so a 30-second sub does not count as much as a full match. */
function weighted(players: MatchPlayer[], key: (p: MatchPlayer) => number | null): number | null {
  let sum = 0;
  let w = 0;
  for (const p of players) {
    const v = key(p);
    if (v == null || p.play_time_s <= 0) continue;
    sum += v * p.play_time_s;
    w += p.play_time_s;
  }
  return w > 0 ? sum / w : null;
}

function mean(values: (number | null)[]): number | null {
  const v = values.filter((x): x is number => x != null);
  return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
}

/** Blue and orange side by side, each measure as two bars growing out from the middle (longer = more, not better). */
export function TeamComparison({ m }: { m: MatchDetail }) {
  const blue = m.teams.blue ?? [];
  const orange = m.teams.orange ?? [];
  if (blue.length === 0 || orange.length === 0) return null;
  const both = (key: (p: MatchPlayer) => number | null, how: "weighted" | "sum" | "mean") => {
    const f = (ps: MatchPlayer[]) =>
      how === "weighted" ? weighted(ps, key) : how === "mean" ? mean(ps.map(key)) : ps.reduce((a, p) => a + (key(p) ?? 0), 0);
    return { blue: f(blue), orange: f(orange) };
  };
  const rows: Row[] = [
    { label: "Avg speed", hint: "Average speed, weighted by play time", ...both((p) => p.avg_speed, "weighted"), show: (v) => `${num(v)} m/s` },
    { label: "Near enemy", hint: "Share of time near an enemy, weighted by play time", ...both((p) => p.pct_near_enemy, "weighted"), show: pct },
    { label: "Near mate", hint: "Share of time near a teammate, weighted by play time", ...both((p) => p.pct_near_mate, "weighted"), show: pct },
    { label: "Deaths*", hint: "Team total (estimated in older matches)", ...both((p) => p.deaths_est, "sum"), show: (v) => String(Math.round(v)) },
  ];
  if (m.mode === "payload") {
    rows.push({ label: "On payload*", hint: "Team total: time pushing (attack) or blocking (defence)", ...both((p) => p.payload_push_s + p.payload_block_s, "sum"), show: duration });
  }
  rows.push(
    { label: "Ping", hint: "Average ping, weighted by play time", ...both((p) => p.avg_ping, "weighted"), show: (v) => `${Math.round(v)} ms` },
    { label: "Level", hint: "Average player level", ...both((p) => p.level, "mean"), show: (v) => String(Math.round(v)) },
  );
  return (
    <div className="team-compare">
      <div className="tc-head">
        <span className="team-text blue">{teamLabel("blue")}</span>
        <span className="label">Team comparison</span>
        <span className="team-text orange">{teamLabel("orange")}</span>
      </div>
      {rows.filter((r) => r.blue != null || r.orange != null).map((r) => {
        const max = Math.max(r.blue ?? 0, r.orange ?? 0) || 1;
        return (
          <div key={r.label} className="tc-row" title={r.hint}>
            <span className="tc-val">{r.blue == null ? "–" : r.show(r.blue)}</span>
            <span className="tc-bar left"><span className="blue" style={{ width: `${((r.blue ?? 0) / max) * 100}%` }} /></span>
            <span className="tc-label">{r.label}</span>
            <span className="tc-bar"><span className="orange" style={{ width: `${((r.orange ?? 0) / max) * 100}%` }} /></span>
            <span className="tc-val right">{r.orange == null ? "–" : r.show(r.orange)}</span>
          </div>
        );
      })}
    </div>
  );
}
