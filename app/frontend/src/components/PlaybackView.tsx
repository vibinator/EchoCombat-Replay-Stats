import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MatchEvent, Playback } from "../api";
import { duration, num } from "../format";

const TEAM_COLORS = ["", "#19d9fc", "#ea7924"];
const SPEEDS = [0.5, 1, 2, 4, 8, 16];
const TRAILS: [number, string][] = [[0, "Off"], [10, "5 s"], [30, "15 s"], [120, "1 min"]]; // in samples (2 Hz)
const DEATH_FLASH_S = 3;

type Player = Playback["players"][number];

/** Current weapon / ordnance / tac mod names of a player at a sample (run-length list, binary search). */
function loadoutAt(p: Player, gear: Playback["gear"], i: number): [string, string, string] {
  let lo = 0;
  let hi = p.loadout.length - 1;
  let at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (p.loadout[mid][0] <= i) {
      at = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  if (at < 0) return ["–", "–", "–"];
  const [, w, o, t] = p.loadout[at];
  return [gear.weapon[w]?.name ?? "–", gear.ordnance[o]?.name ?? "–", gear.tacmod[t]?.name ?? "–"];
}

function eventLabel(e: MatchEvent): string {
  if (e.type === "round_won") return `Round won: Blue ${e.data?.blue} – ${e.data?.orange} Orange`;
  if (e.type === "payload_checkpoint") return `Checkpoint ${e.data?.checkpoint}`;
  if (e.type === "death_est") return `${e.name ?? "Player"} died (est.)`;
  if (e.type === "contest_start") return "Contest start";
  if (e.type === "contest_end") return "Contest end";
  return e.type;
}

/** Latest value of an objective series at a sample. */
function seriesAt(series: (number | null)[] | undefined, i: number): number | null {
  if (!series) return null;
  for (let k = Math.min(i, series.length - 1); k >= 0; k--) if (series[k] != null) return series[k];
  return null;
}

/** Animated player dots over the minimap, driven by the 2 Hz position tracks, with scoreboard, roster and event markers. */
export function PlaybackView({ playback }: { playback: Playback }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(0); // sample index (float)
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [names, setNames] = useState(true);
  const [trail, setTrail] = useState(10);
  const [follow, setFollow] = useState<string | null>(null); // highlighted player
  const last = useRef<number | null>(null);
  const end = Math.max(0, playback.samples - 1);
  const hz = playback.hz;

  const deaths = useMemo(() => playback.events.filter((e) => e.type === "death_est"), [playback.events]);
  const markers = useMemo(() => playback.events.filter((e) => e.type === "round_won" || e.type === "payload_checkpoint"), [playback.events]);
  const rounds = useMemo(() => playback.events.filter((e) => e.type === "round_won"), [playback.events]);
  const checkpoints = useMemo(() => playback.events.filter((e) => e.type === "payload_checkpoint"), [playback.events]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = (now: number) => {
      if (last.current != null) {
        const dt = (now - last.current) / 1000;
        setT((v) => {
          const next = v + dt * hz * speed;
          if (next >= end) {
            setPlaying(false);
            return end;
          }
          return next;
        });
      }
      last.current = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      last.current = null;
    };
  }, [playing, speed, end, hz]);

  const seek = useCallback((seconds: number) => setT((v) => Math.min(end, Math.max(0, v + seconds * hz))), [end, hz]);
  const toggle = useCallback(() => {
    if (t >= end) {
      setT(0);
      setPlaying(true);
    } else setPlaying((p) => !p);
  }, [t, end]);

  // keyboard: space play / pause, arrows ±5 s (shift ±30 s), [ ] speed — only while the player has focus
  function onKey(e: React.KeyboardEvent) {
    if ((e.target as HTMLElement).tagName === "SELECT") return;
    if (e.key === " ") {
      e.preventDefault();
      toggle();
    } else if (e.key === "ArrowRight") seek(e.shiftKey ? 30 : 5);
    else if (e.key === "ArrowLeft") seek(e.shiftKey ? -30 : -5);
    else if (e.key === "]") setSpeed((s) => SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(s) + 1)]);
    else if (e.key === "[") setSpeed((s) => SPEEDS[Math.max(0, SPEEDS.indexOf(s) - 1)]);
    else return;
  }

  const second = t / hz;
  const i = Math.floor(t);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    el.width = box.width * devicePixelRatio;
    el.height = box.height * devicePixelRatio;
    const ctx = el.getContext("2d")!;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    ctx.clearRect(0, 0, box.width, box.height);
    const f = t - i;
    ctx.font = "11px system-ui, sans-serif";
    const recentlyDied = new Set(deaths.filter((d) => second >= d.t_s && second - d.t_s < DEATH_FLASH_S).map((d) => d.user_id));
    for (const p of playback.players) {
      const a = p.points[i];
      if (!a) continue;
      const b = p.points[i + 1];
      // interpolate between samples unless the player jumped (respawn)
      const lerp = b && Math.hypot(b[0] - a[0], b[1] - a[1]) < 0.08;
      const u = lerp ? a[0] + (b[0] - a[0]) * f : a[0];
      const v = lerp ? a[1] + (b[1] - a[1]) * f : a[1];
      const x = u * box.width;
      const y = v * box.height;
      const picked = follow === p.user_id;
      const dim = follow != null && !picked;
      ctx.globalAlpha = dim ? 0.4 : 1;
      if (trail > 0) {
        ctx.strokeStyle = TEAM_COLORS[a[2]];
        ctx.globalAlpha = (dim ? 0.4 : 1) * (picked ? 0.7 : 0.35);
        ctx.lineWidth = picked ? 3 : 2;
        ctx.beginPath();
        let pen = false;
        for (let k = Math.max(0, i - trail); k <= i; k++) {
          const q = p.points[k];
          if (!q) {
            pen = false;
            continue;
          }
          if (pen) ctx.lineTo(q[0] * box.width, q[1] * box.height);
          else ctx.moveTo(q[0] * box.width, q[1] * box.height);
          pen = true;
        }
        ctx.stroke();
        ctx.globalAlpha = dim ? 0.4 : 1;
      }
      if (recentlyDied.has(p.user_id)) {
        ctx.strokeStyle = "#ff4d5e";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 11, 0, Math.PI * 2);
        ctx.stroke();
      }
      if (picked) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = TEAM_COLORS[a[2]];
      ctx.strokeStyle = "#16181c";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (names || picked) {
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "rgba(0,0,0,.7)";
        ctx.lineWidth = 3;
        ctx.strokeText(p.name, x + 7, y - 6);
        ctx.fillText(p.name, x + 7, y - 6);
      }
      ctx.globalAlpha = 1;
    }
  }, [t, i, second, playback, names, trail, follow, deaths]);

  // scoreboard
  const roundsSoFar = rounds.filter((e) => e.t_s <= second);
  const lastRound = roundsSoFar[roundsSoFar.length - 1];
  const blueRounds = lastRound ? Number(lastRound.data?.blue ?? 0) : 0;
  const orangeRounds = lastRound ? Number(lastRound.data?.orange ?? 0) : 0;
  const payload = seriesAt(playback.series.payload_distance, i);
  const checkpointsDone = checkpoints.filter((e) => e.t_s <= second).length;
  const bluePts = seriesAt(playback.series.blue_points, i);
  const orangePts = seriesAt(playback.series.orange_points, i);
  // big number beside each team: rounds won (capture point); in payload games, which team attacks / defends
  const side = (team: "blue" | "orange") =>
    playback.mode === "capture_point" ? (
      <strong>{team === "blue" ? blueRounds : orangeRounds}</strong>
    ) : (
      <span className="muted">{playback.attacking_team ? (playback.attacking_team === team ? "attack" : "defence") : ""}</span>
    );
  const recent = playback.events
    .filter((e) => e.t_s <= second && e.type !== "contest_end")
    .slice(-5)
    .reverse();

  const roster = (team: number) =>
    playback.players
      .filter((p) => (p.points.find((q) => q)?.[2] ?? 0) === team)
      .map((p) => {
        const here = p.points[i];
        const [weapon, ordnance, tacmod] = loadoutAt(p, playback.gear, i);
        const died = deaths.some((d) => d.user_id === p.user_id && second >= d.t_s && second - d.t_s < DEATH_FLASH_S);
        const killsDeaths = deaths.filter((d) => d.user_id === p.user_id && d.t_s <= second).length;
        return { p, here, weapon, ordnance, tacmod, died, killsDeaths, speed: p.speed[i] };
      });

  return (
    <div className="playback" ref={root} tabIndex={0} onKeyDown={onKey} aria-label="Match playback (space: play / pause, arrow keys: skip, [ ]: speed)">
      <div className="pb-score">
        <div className="pb-team blue">
          <span>Blue</span>
          {side("blue")}
        </div>
        <div className="pb-mid">
          <strong>{duration(second)}</strong>
          <span className="muted">
            {playback.mode === "payload"
              ? `Payload ${payload != null ? `${num(payload, 0)} m` : "–"} · checkpoint ${checkpointsDone}/${Math.max(3, checkpoints.length)}`
              : `Round ${Math.min(roundsSoFar.length + 1, 2)}${bluePts != null || orangePts != null ? ` · points ${Math.round(bluePts ?? 0)} – ${Math.round(orangePts ?? 0)}` : ""}`}
          </span>
        </div>
        <div className="pb-team orange">
          {side("orange")}
          <span>Orange</span>
        </div>
      </div>

      <div className="heatmap-tools">
        <button onClick={toggle}>{playing ? "Pause" : t >= end ? "Replay" : "Play"}</button>
        <span className="zoom-buttons">
          <button className="secondary" onClick={() => seek(-10)} title="Back 10 s">−10 s</button>
          <button className="secondary" onClick={() => seek(10)} title="Forward 10 s">+10 s</button>
        </span>
        <label>
          Speed
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{s}×</option>
            ))}
          </select>
        </label>
        <label>
          Trails
          <select value={trail} onChange={(e) => setTrail(Number(e.target.value))}>
            {TRAILS.map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} /> Names
        </label>
        <span className="muted">
          {duration(second)} / {duration(end / hz)}
        </span>
      </div>

      <div className="pb-track">
        <input
          className="scrubber"
          type="range"
          min={0}
          max={end}
          step={0.5}
          value={t}
          aria-label="Match time"
          onChange={(e) => {
            setPlaying(false);
            setT(Number(e.target.value));
          }}
        />
        <div className="pb-markers" aria-hidden="true">
          {deaths.map((e, k) => (
            <span key={`d${k}`} className={`pb-tick death ${e.team ?? ""}`} style={{ left: `${(e.t_s * hz / Math.max(1, end)) * 100}%` }} />
          ))}
          {markers.map((e, k) => (
            <button
              key={`m${k}`}
              type="button"
              className="pb-tick moment"
              style={{ left: `${(e.t_s * hz / Math.max(1, end)) * 100}%` }}
              title={`${duration(e.t_s)} · ${eventLabel(e)}`}
              onClick={() => {
                setPlaying(false);
                setT(Math.min(end, e.t_s * hz));
              }}
            />
          ))}
        </div>
      </div>

      <div className="pb-main">
        <div className="heatmap-stage">
          <div className="heatmap-inner">
            <img src={playback.image} alt={`${playback.map} minimap`} />
            <canvas ref={canvas} className="playback-canvas" />
          </div>
        </div>

        <aside className="pb-side">
          {[1, 2].map((team) => (
            <div key={team} className="pb-roster">
              <h3 className={team === 1 ? "blue" : "orange"}>{team === 1 ? "Blue" : "Orange"}</h3>
              {roster(team).map(({ p, here, weapon, ordnance, tacmod, died, killsDeaths, speed: sp }) => (
                <button
                  key={p.user_id}
                  type="button"
                  className={`pb-player ${follow === p.user_id ? "picked" : ""} ${here ? "" : "gone"} ${died ? "died" : ""}`}
                  onClick={() => setFollow(follow === p.user_id ? null : p.user_id)}
                  title="Click to highlight this player"
                >
                  <span className="pb-name">{p.name}</span>
                  <span className="pb-gear">{here ? `${weapon} · ${ordnance} · ${tacmod}` : "off the map / left"}</span>
                  <span className="pb-nums">
                    {here && sp != null ? `${num(sp, 1)} m/s` : "–"}
                    {killsDeaths > 0 && ` · ${killsDeaths} death${killsDeaths === 1 ? "" : "s"}*`}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </aside>
      </div>

      <ul className="pb-feed">
        {recent.length === 0 && <li className="muted">Nothing yet.</li>}
        {recent.map((e, k) => (
          <li key={`${e.frame}-${k}`}>
            <span className="muted">{duration(e.t_s)}</span> {e.team && <span className={`dot ${e.team}`} />} {eventLabel(e)}
          </li>
        ))}
      </ul>

      <p className="muted footnote">
        Positions are recorded twice per second; dots glide between them. Players off the map image (spawn rooms) are hidden. Click a player to
        highlight them; keys: space play / pause, ← → skip 5 s (shift 30 s), [ ] speed. Ticks under the slider are estimated deaths (small) and
        round / checkpoint moments (click to jump). * Estimated. Speed is measured between recorded positions.
      </p>
    </div>
  );
}
