import { Component, lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router";
import type { MatchEvent, Playback } from "../api";
import { duration, num } from "../format";
import { GearLabel } from "./common";
import { CAMERAS, isCamera, TEAM_COLORS, type Camera3D } from "./playback3d";

const Map3D = lazy(() => import("./Map3D")); // three.js: only downloaded when someone opens the 3D view
const SPEEDS = [0.5, 1, 2, 4, 8, 16];
const TRAILS: [number, string][] = [[0, "Off"], [10, "5 s"], [30, "15 s"], [120, "1 min"]]; // in samples (2 Hz)
const DEATH_FLASH_S = 3; // red ring on the dead player's dot and name in the roster
const SKULL_S = 5; // skull marker left where someone died
const SWAP_S = 3; // "⇄ weapon" label after a loadout change
const FIGHT_GAP_S = 6; // deaths closer together than this belong to the same fight
const FIGHT_MIN_DEATHS = 3;
const BANNER_S = 3; // "Round won" / "Checkpoint" banner over the map
const CLIP_S = 10; // "Copy clip": the last 10 seconds
const SKULL = new Image();
SKULL.src = "/icons/death.png";

type Player = Playback["players"][number];

/** Playback clock: the time in seconds, whether it runs, and its speed. Shared between two views in compare mode. */
export interface Clock {
  t: number;
  playing: boolean;
  speed: number;
  setT: (seconds: number | ((v: number) => number)) => void;
  setPlaying: (playing: boolean | ((p: boolean) => boolean)) => void;
  setSpeed: (speed: number | ((s: number) => number)) => void;
}

/** A clock that runs from 0 to `max` seconds. */
export function useClock(max: number): Clock {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const last = useRef<number | null>(null);
  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = (now: number) => {
      if (last.current != null) {
        const dt = (now - last.current) / 1000;
        setT((v) => {
          const next = v + dt * speed;
          if (next >= max) {
            setPlaying(false);
            return max;
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
  }, [playing, speed, max]);
  return { t, playing, speed, setT, setPlaying, setSpeed };
}

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

/** Gear names of a loadout swap: weapon, ordnance, tac mod (empty slots left out). */
function swapParts(e: MatchEvent): string[] {
  return [e.data?.weapon, e.data?.ordnance, e.data?.tacmod].filter(Boolean).map(String);
}

function swapText(e: MatchEvent): string {
  return swapParts(e).join(" · ");
}

/** Feed line for a loadout swap, with gear icons next to the names. */
function SwapLabel({ e }: { e: MatchEvent }) {
  return (
    <>
      {e.name ?? "Player"} switched to{" "}
      {swapParts(e).map((g, k) => (
        <span key={k}>
          {k > 0 && " · "}
          <GearLabel name={g} />
        </span>
      ))}
    </>
  );
}

function eventLabel(e: MatchEvent): string {
  if (e.type === "round_won") return `Round won: Blue ${e.data?.blue} – ${e.data?.orange} Orange`;
  if (e.type === "payload_checkpoint") return `Checkpoint ${e.data?.checkpoint}`;
  if (e.type === "death_est") return `${e.name ?? "Player"} died (est.)`;
  if (e.type === "loadout_change") return `${e.name ?? "Player"} switched to ${swapText(e)}`;
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

/** Colour for a speed in m/s: slow blue, through green and yellow, to fast red. */
function speedColor(v: number | null): string {
  const s = Math.min(1, Math.max(0, (v ?? 0) / 12));
  return `hsl(${Math.round(220 - 220 * s)} 90% 55%)`;
}

interface Fight {
  start: number;
  end: number;
  deaths: number;
  blue: number;
  orange: number;
}

/** Runs of deaths close together: team fights. */
function findFights(deaths: MatchEvent[]): Fight[] {
  const fights: Fight[] = [];
  let cur: MatchEvent[] = [];
  const close = () => {
    if (cur.length >= FIGHT_MIN_DEATHS) {
      fights.push({
        start: cur[0].t_s,
        end: cur[cur.length - 1].t_s,
        deaths: cur.length,
        blue: cur.filter((d) => d.team === "blue").length,
        orange: cur.filter((d) => d.team === "orange").length,
      });
    }
    cur = [];
  };
  for (const d of [...deaths].sort((a, b) => a.t_s - b.t_s)) {
    if (cur.length && d.t_s - cur[cur.length - 1].t_s > FIGHT_GAP_S) close();
    cur.push(d);
  }
  close();
  return fights;
}

/** The 3D chunk failed to load or crashed: say so and offer the 2D map instead of breaking the page. */
class Stage3DBoundary extends Component<{ onUse2D: () => void; children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message || "unknown error" };
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="pb3d-message">
        <p>The 3D view could not start ({this.state.error}).</p>
        <button type="button" onClick={this.props.onUse2D}>Show the 2D map</button>
      </div>
    );
  }
}

/**
 * Animated player dots over the minimap, driven by the 2 Hz position tracks, with scoreboard, objective (payload route /
 * capture point), roster, fights, death summary, loadout changes and event markers.
 * `clock` = a shared clock (compare mode); `compact` = only scoreboard, map and feed. With `matchId` (single match, not
 * compare) the map can switch to 3D (Map3D) and the view is kept in the address: ?view=3d&cam=&player=&t=&until=.
 */
export function PlaybackView({ playback, clock, compact = false, label, matchId }: { playback: Playback; clock?: Clock; compact?: boolean; label?: string; matchId?: number }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const root = useRef<HTMLDivElement>(null);
  const hz = playback.hz;
  const end = Math.max(0, playback.samples - 1);
  const own = useClock(end / hz);
  const c = clock ?? own;
  const [names, setNames] = useState(true);
  const [trail, setTrail] = useState(10);
  const [trailColor, setTrailColor] = useState<"team" | "speed">("team");
  const [swaps, setSwaps] = useState(true);
  const [params, setParams] = useSearchParams();
  const linked = matchId != null && !compact && !clock; // this view owns the address (deep links)
  const [follow, setFollow] = useState<string | null>(() => (linked ? params.get("player") : null)); // highlighted player
  const view: "2d" | "3d" = linked && params.get("view") === "3d" ? "3d" : "2d";
  const camParam = params.get("cam");
  const camera: Camera3D = isCamera(camParam) ? camParam : "orbit";
  const cameraNow = useRef(camera);
  cameraNow.current = camera;
  const until = linked ? Number(params.get("until")) || 0 : 0; // a clip link: stop here
  const [copied, setCopied] = useState("");
  const setParam = useCallback((changes: Record<string, string | null>) => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      for (const [k, v] of Object.entries(changes)) {
        if (v == null) next.delete(k);
        else next.set(k, v);
      }
      return next;
    }, { replace: true });
  }, [setParams]);
  const pick = useCallback((userId: string | null) => setFollow((f) => (f === userId ? null : userId)), []);

  const second = Math.min(c.t, end / hz);
  const t = Math.min(end, second * hz); // sample index (float)
  const i = Math.floor(t);

  // deep link: start at ?t= (once), stop at ?until= (clip links)
  const startAt = useRef(linked ? Number(params.get("t")) || 0 : 0);
  useEffect(() => {
    if (startAt.current > 0) c.setT(Math.min(end / hz, startAt.current));
    startAt.current = 0;
  }, [c, end, hz]);
  useEffect(() => {
    if (until > 0 && c.playing && second >= until) c.setPlaying(false);
  }, [until, c, second]);

  const deaths = useMemo(() => playback.events.filter((e) => e.type === "death_est"), [playback.events]);
  const moments = useMemo(() => playback.events.filter((e) => e.type === "round_won" || e.type === "payload_checkpoint"), [playback.events]);
  const rounds = useMemo(() => playback.events.filter((e) => e.type === "round_won"), [playback.events]);
  const checkpoints = useMemo(() => playback.events.filter((e) => e.type === "payload_checkpoint"), [playback.events]);
  const fights = useMemo(() => findFights(deaths), [deaths]);
  // loadout changes after each player's first one (that is the starting pick)
  const changes = useMemo(() => {
    const seen = new Set<string>();
    return playback.events
      .filter((e) => e.type === "loadout_change")
      .sort((a, b) => a.t_s - b.t_s)
      .filter((e) => {
        const key = e.user_id ?? e.name ?? "";
        if (!seen.has(key)) {
          seen.add(key);
          return false;
        }
        return true;
      });
  }, [playback.events]);
  const checkpointDistances = useMemo(
    () => checkpoints.map((e) => seriesAt(playback.series.payload_distance, Math.round(e.t_s * hz))),
    [checkpoints, playback.series.payload_distance, hz],
  );

  const seek = useCallback((seconds: number) => c.setT((v) => Math.min(end / hz, Math.max(0, v + seconds))), [c, end, hz]);
  const jump = useCallback((seconds: number) => {
    c.setPlaying(false);
    c.setT(Math.min(end / hz, Math.max(0, seconds)));
  }, [c, end, hz]);
  const toggle = useCallback(() => {
    if (second >= end / hz) {
      c.setT(0);
      c.setPlaying(true);
    } else c.setPlaying((p) => !p);
  }, [c, second, end, hz]);
  const nextFight = () => {
    const f = fights.find((x) => x.start - 2 > second + 0.5);
    if (f) jump(Math.max(0, f.start - 2));
  };
  const prevFight = () => {
    const f = [...fights].reverse().find((x) => x.start - 2 < second - 2);
    if (f) jump(Math.max(0, f.start - 2));
  };

  // roster order (blue, then orange): keys 1-9, 0 pick a player
  const order = useMemo(() => [1, 2].flatMap((team) => playback.players.filter((p) => (p.points.find((q) => q)?.[2] ?? 0) === team)), [playback.players]);

  // keyboard: space play / pause, arrows ±5 s (shift ±30 s), [ ] speed, N / P next / previous fight, 1-0 pick a player,
  // Esc let go; in 3D also C next camera
  function onKey(e: React.KeyboardEvent) {
    const tag = (e.target as HTMLElement).tagName;
    if (tag === "SELECT" || tag === "INPUT" || compact) return;
    if (/^[0-9]$/.test(e.key) && !e.ctrlKey && !e.metaKey && !e.altKey) {
      const p = order[(Number(e.key) + 9) % 10];
      if (p) setFollow(p.user_id);
    } else if (e.key === "Escape") {
      setFollow(null);
      if (view === "3d" && (camera === "follow" || camera === "first")) setParam({ cam: null });
    } else if ((e.key === "c" || e.key === "C") && view === "3d") {
      // from a ref, not the render's value: quick presses (before the address updates) each move one camera on
      const k = CAMERAS.findIndex((x) => x.value === cameraNow.current);
      const next = CAMERAS[(k + 1) % CAMERAS.length].value;
      cameraNow.current = next;
      setParam({ cam: next === "orbit" ? null : next });
    } else if (e.key === " ") {
      e.preventDefault();
      toggle();
    } else if (e.key === "ArrowRight") seek(e.shiftKey ? 30 : 5);
    else if (e.key === "ArrowLeft") seek(e.shiftKey ? -30 : -5);
    else if (e.key === "]") c.setSpeed((s) => SPEEDS[Math.min(SPEEDS.length - 1, SPEEDS.indexOf(s) + 1)]);
    else if (e.key === "[") c.setSpeed((s) => SPEEDS[Math.max(0, SPEEDS.indexOf(s) - 1)]);
    else if (e.key === "n" || e.key === "N") nextFight();
    else if (e.key === "p" || e.key === "P") prevFight();
  }

  const attackerColor = playback.attacking_team === "blue" ? TEAM_COLORS[1] : playback.attacking_team === "orange" ? TEAM_COLORS[2] : "#ffffff";
  const payload = seriesAt(playback.series.payload_distance, i);
  const bluePts = seriesAt(playback.series.blue_points, i);
  const orangePts = seriesAt(playback.series.orange_points, i);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    el.width = box.width * devicePixelRatio;
    el.height = box.height * devicePixelRatio;
    const ctx = el.getContext("2d")!;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    ctx.clearRect(0, 0, box.width, box.height);
    const W = box.width;
    const H = box.height;
    const f = t - i;
    ctx.font = "11px system-ui, sans-serif";

    // --- objective: payload route and cart ---
    const route = playback.objects.route;
    if (route && route.some(Boolean)) {
      const draw = (from: number, to: number) => {
        ctx.beginPath();
        let pen = false;
        for (let k = from; k <= Math.min(to, route.length - 1); k++) {
          const q = route[k];
          if (!q) {
            pen = false;
            continue;
          }
          if (pen) ctx.lineTo(q[0] * W, q[1] * H);
          else ctx.moveTo(q[0] * W, q[1] * H);
          pen = true;
        }
        ctx.stroke();
      };
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = "rgba(255,255,255,.35)";
      ctx.lineWidth = 3;
      ctx.setLineDash([4, 5]);
      draw(0, route.length - 1);
      ctx.setLineDash([]);
      const dist = Math.max(0, Math.min(route.length - 1, payload ?? 0));
      ctx.strokeStyle = attackerColor;
      ctx.globalAlpha = 0.85;
      ctx.lineWidth = 4;
      draw(0, Math.floor(dist));
      ctx.globalAlpha = 1;
      checkpointDistances.forEach((d, k) => {
        const q = d != null ? route[Math.round(d)] : null;
        if (!q) return;
        ctx.fillStyle = second >= checkpoints[k].t_s ? attackerColor : "#fff";
        ctx.strokeStyle = "#16181c";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.rect(q[0] * W - 5, q[1] * H - 5, 10, 10);
        ctx.fill();
        ctx.stroke();
      });
      const endPoint = route[route.length - 1];
      if (endPoint) {
        ctx.font = "bold 12px system-ui, sans-serif";
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "rgba(0,0,0,.8)";
        ctx.lineWidth = 3;
        ctx.strokeText("⚑", endPoint[0] * W - 4, endPoint[1] * H - 8);
        ctx.fillText("⚑", endPoint[0] * W - 4, endPoint[1] * H - 8);
        ctx.font = "11px system-ui, sans-serif";
      }
      const cart = route[Math.round(dist)];
      if (cart) {
        ctx.fillStyle = attackerColor;
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 2;
        ctx.beginPath();
        if (ctx.roundRect) ctx.roundRect(cart[0] * W - 8, cart[1] * H - 8, 16, 16, 3);
        else ctx.rect(cart[0] * W - 8, cart[1] * H - 8, 16, 16); // older browsers
        ctx.fill();
        ctx.stroke();
      }
    }

    // --- objective: capture point ---
    const point = playback.objects.point;
    if (point) {
      const px = point.u * W;
      const py = point.v * H;
      const rad = point.r * W;
      const blue = bluePts ?? 0;
      const orange = orangePts ?? 0;
      const lead = blue === orange ? 0 : blue > orange ? 1 : 2;
      const share = Math.max(blue, orange) / 100;
      ctx.fillStyle = lead ? `${TEAM_COLORS[lead]}33` : "rgba(255,255,255,.08)";
      ctx.beginPath();
      ctx.arc(px, py, rad, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.4)";
      ctx.lineWidth = 2;
      ctx.stroke();
      if (lead && share > 0) {
        ctx.strokeStyle = TEAM_COLORS[lead];
        ctx.lineWidth = 5;
        ctx.beginPath();
        ctx.arc(px, py, rad, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, share));
        ctx.stroke();
      }
      ctx.font = "bold 12px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillStyle = "#fff";
      ctx.strokeStyle = "rgba(0,0,0,.8)";
      ctx.lineWidth = 3;
      const text = lead ? `${Math.round(Math.max(blue, orange))}%` : "point";
      ctx.strokeText(text, px, py + 4);
      ctx.fillText(text, px, py + 4);
      ctx.textAlign = "start";
      ctx.font = "11px system-ui, sans-serif";
    }

    // --- skulls where players died: pop in, then fade out ---
    for (const d of deaths) {
      const age = second - d.t_s;
      const u = d.data?.u as number | null | undefined;
      const w = d.data?.v as number | null | undefined;
      if (age < 0 || age > SKULL_S || u == null || w == null) continue;
      const pop = Math.min(1, age / 0.25);
      const size = (26 + 10 * (1 - pop)) * pop + 6;
      ctx.globalAlpha = age < SKULL_S - 1.5 ? 0.95 : Math.max(0, (SKULL_S - age) / 1.5) * 0.95;
      if (SKULL.complete) ctx.drawImage(SKULL, u * W - size / 2, w * H - size / 2, size, size);
      if (names && d.name) {
        ctx.font = "bold 11px system-ui, sans-serif";
        ctx.fillStyle = d.team === "blue" ? TEAM_COLORS[1] : TEAM_COLORS[2];
        ctx.strokeStyle = "rgba(0,0,0,.8)";
        ctx.lineWidth = 3;
        ctx.textAlign = "center";
        ctx.strokeText(d.name, u * W, w * H + size / 2 + 11);
        ctx.fillText(d.name, u * W, w * H + size / 2 + 11);
        ctx.textAlign = "start";
        ctx.font = "11px system-ui, sans-serif";
      }
      ctx.globalAlpha = 1;
    }

    // --- players ---
    const recentlyDied = new Set(deaths.filter((d) => second >= d.t_s && second - d.t_s < DEATH_FLASH_S).map((d) => d.user_id));
    const recentSwap = new Map(changes.filter((e) => second >= e.t_s && second - e.t_s < SWAP_S).map((e) => [e.user_id, e]));
    for (const p of playback.players) {
      const a = p.points[i];
      if (!a) continue;
      const b = p.points[i + 1];
      // interpolate between samples unless the player jumped (respawn)
      const lerp = b && Math.hypot(b[0] - a[0], b[1] - a[1]) < 0.08;
      const u = lerp ? a[0] + (b[0] - a[0]) * f : a[0];
      const v = lerp ? a[1] + (b[1] - a[1]) * f : a[1];
      const x = u * W;
      const y = v * H;
      const picked = follow === p.user_id;
      const dim = follow != null && !picked;
      const base = dim ? 0.4 : 1;
      if (trail > 0) {
        ctx.lineWidth = picked ? 3.5 : 2.5;
        ctx.lineCap = "round";
        ctx.globalAlpha = base * (picked ? 0.85 : 0.5);
        const from = Math.max(0, i - trail);
        for (let k = from + 1; k <= i; k++) {
          const q0 = p.points[k - 1];
          const q1 = p.points[k];
          if (!q0 || !q1) continue;
          ctx.strokeStyle = trailColor === "speed" ? speedColor(p.speed[k]) : TEAM_COLORS[a[2]];
          ctx.beginPath();
          ctx.moveTo(q0[0] * W, q0[1] * H);
          ctx.lineTo(q1[0] * W, q1[1] * H);
          ctx.stroke();
        }
      }
      ctx.globalAlpha = base;
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
      const swap = swaps ? recentSwap.get(p.user_id) : undefined;
      if (swap) {
        const text = `⇄ ${swapText(swap)}`;
        ctx.font = "bold 10px system-ui, sans-serif";
        ctx.fillStyle = "#ffe08a";
        ctx.strokeStyle = "rgba(0,0,0,.85)";
        ctx.lineWidth = 3;
        ctx.strokeText(text, x + 7, y + 14);
        ctx.fillText(text, x + 7, y + 14);
        ctx.font = "11px system-ui, sans-serif";
      }
      ctx.globalAlpha = 1;
    }
  }, [t, i, second, playback, names, trail, trailColor, follow, deaths, changes, swaps, payload, bluePts, orangePts, checkpoints, checkpointDistances, attackerColor, view]);

  // loadout swap labels shown now (3D labels; the 2D canvas works them out itself)
  const swapLabels = useMemo(
    () => new Map(swaps ? changes.filter((e) => second >= e.t_s && second - e.t_s < SWAP_S && e.user_id).map((e) => [e.user_id!, swapText(e)]) : []),
    [swaps, changes, second],
  );
  const banner = moments.filter((e) => second >= e.t_s && second - e.t_s < BANNER_S).pop();

  /** Copy a link to this moment (or to the last 10 s as a clip) with the view, camera and picked player. */
  function copyLink(clip: boolean) {
    const u = new URL(window.location.href);
    const from = clip ? Math.max(0, second - CLIP_S) : second;
    u.searchParams.set("t", String(Math.floor(from)));
    if (clip) u.searchParams.set("until", String(Math.ceil(second)));
    else u.searchParams.delete("until");
    if (follow) u.searchParams.set("player", follow);
    else u.searchParams.delete("player");
    const text = u.toString();
    const done = () => {
      setCopied(clip ? "Clip link copied" : "Link copied");
      setTimeout(() => setCopied(""), 2500);
    };
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(text).then(done, () => window.prompt("Copy this link:", text));
    else window.prompt("Copy this link:", text);
  }

  // scoreboard
  const roundsSoFar = rounds.filter((e) => e.t_s <= second);
  const lastRound = roundsSoFar[roundsSoFar.length - 1];
  const blueRounds = lastRound ? Number(lastRound.data?.blue ?? 0) : 0;
  const orangeRounds = lastRound ? Number(lastRound.data?.orange ?? 0) : 0;
  const checkpointsDone = checkpoints.filter((e) => e.t_s <= second).length;
  const deathsSoFar = (team: string) => deaths.filter((d) => d.team === team && d.t_s <= second).length;
  const inFight = fights.find((x) => second >= x.start - 2 && second <= x.end + 3);
  // big number beside each team: rounds won (capture point); in payload games, which team attacks / defends
  const side = (team: "blue" | "orange") =>
    playback.mode === "capture_point" ? (
      <strong>{team === "blue" ? blueRounds : orangeRounds}</strong>
    ) : (
      <span className="muted">{playback.attacking_team ? (playback.attacking_team === team ? "attack" : "defence") : ""}</span>
    );
  const recent = playback.events
    .filter((e) => e.t_s <= second && e.type !== "contest_end" && (e.type !== "loadout_change" || (swaps && changes.includes(e))))
    .slice(-6)
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

  // death summary (whole match)
  const summary = useMemo(() => {
    const rows = playback.players.map((p) => {
      const mine = deaths.filter((d) => d.user_id === p.user_id).sort((a, b) => a.t_s - b.t_s);
      const team = p.points.find((q) => q)?.[2] ?? 0;
      return { p, team, mine };
    });
    return rows.sort((a, b) => b.mine.length - a.mine.length);
  }, [playback.players, deaths]);
  const maxDeaths = Math.max(1, ...summary.map((r) => r.mine.length));
  const firstDeath = deaths.length ? [...deaths].sort((a, b) => a.t_s - b.t_s)[0] : null;
  const total = Math.max(1, end / hz);
  const pos = (s: number) => `${(s / total) * 100}%`;

  return (
    <div className="playback" ref={root} tabIndex={0} onKeyDown={onKey} aria-label="Match playback (space: play / pause, arrow keys: skip, [ ]: speed, N / P: next / previous fight)">
      {label && <h3 className="pb-label">{label}</h3>}
      <div className="pb-score">
        <div className="pb-team blue">
          <span>Blue</span>
          {side("blue")}
          <span className="pb-deaths" title="Estimated deaths so far">
            <img src="/icons/death.png" alt="" /> {deathsSoFar("blue")}
          </span>
        </div>
        <div className="pb-mid">
          <strong>{duration(second)}</strong>
          <span className="muted">
            {playback.mode === "payload"
              ? `Payload ${payload != null ? `${num(payload, 0)} m` : "–"} · checkpoint ${checkpointsDone}/${Math.max(3, checkpoints.length)}`
              : `Round ${Math.min(roundsSoFar.length + 1, 2)}${bluePts != null || orangePts != null ? ` · capture ${Math.round(bluePts ?? 0)}% – ${Math.round(orangePts ?? 0)}%` : ""}`}
          </span>
          {inFight && <span className="pb-fight">⚔ Fight · {inFight.deaths} deaths</span>}
        </div>
        <div className="pb-team orange">
          <span className="pb-deaths" title="Estimated deaths so far">
            <img src="/icons/death.png" alt="" /> {deathsSoFar("orange")}
          </span>
          {side("orange")}
          <span>Orange</span>
        </div>
      </div>

      {!clock && (
        <div className="heatmap-tools">
          <button onClick={toggle}>{c.playing ? "Pause" : second >= end / hz ? "Replay" : "Play"}</button>
          <span className="zoom-buttons">
            <button className="secondary" onClick={() => seek(-10)} title="Back 10 s">−10 s</button>
            <button className="secondary" onClick={() => seek(10)} title="Forward 10 s">+10 s</button>
            <button className="secondary" onClick={prevFight} disabled={fights.length === 0} title="Previous fight (P)">⏮ Fight</button>
            <button className="secondary" onClick={nextFight} disabled={fights.length === 0} title="Next fight (N)">Fight ⏭</button>
          </span>
          <label>
            Speed
            <select value={c.speed} onChange={(e) => c.setSpeed(Number(e.target.value))}>
              {SPEEDS.map((s) => (
                <option key={s} value={s}>{s}×</option>
              ))}
            </select>
          </label>
          <span className="muted">
            {duration(second)} / {duration(end / hz)}
          </span>
          {linked && (
            <span className="zoom-buttons">
              <button className="secondary" onClick={() => copyLink(false)} title="Copy a link that opens this match here, at this moment">Copy link</button>
              <button className="secondary" onClick={() => copyLink(true)} title={`Copy a link that plays the last ${CLIP_S} seconds`}>Copy clip</button>
            </span>
          )}
          {copied && <span className="muted" role="status">{copied}</span>}
        </div>
      )}

      <div className="heatmap-tools">
        {linked && (
          <span className="zoom-buttons" role="group" aria-label="Map view">
            <button className={view === "2d" ? "" : "secondary"} aria-pressed={view === "2d"} onClick={() => setParam({ view: null })}>2D map</button>
            <button className={view === "3d" ? "" : "secondary"} aria-pressed={view === "3d"} onClick={() => setParam({ view: "3d" })} title="3D map with heights and where players look">3D</button>
          </span>
        )}
        {view === "3d" && (
          <label title={CAMERAS.find((x) => x.value === camera)?.help}>
            Camera
            <select value={camera} onChange={(e) => setParam({ cam: e.target.value === "orbit" ? null : e.target.value })}>
              {CAMERAS.map((x) => (
                <option key={x.value} value={x.value}>{x.label}</option>
              ))}
            </select>
          </label>
        )}
        <label>
          Trails
          <select value={trail} onChange={(e) => setTrail(Number(e.target.value))}>
            {TRAILS.map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </label>
        <label>
          Trail colour
          <select value={trailColor} onChange={(e) => setTrailColor(e.target.value as "team" | "speed")}>
            <option value="team">Team</option>
            <option value="speed">Speed</option>
          </select>
        </label>
        {trailColor === "speed" && trail > 0 && (
          <span className="pb-legend" title="Trail colour = speed">
            0 <span className="pb-ramp" /> 12+ m/s
          </span>
        )}
        <label className="inline-check">
          <input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} /> Names
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={swaps} onChange={(e) => setSwaps(e.target.checked)} /> Loadout changes
        </label>
      </div>

      {!clock && (
        <div className="pb-track">
          <input
            className="scrubber"
            type="range"
            min={0}
            max={end}
            step={0.5}
            value={t}
            aria-label="Match time"
            onChange={(e) => jump(Number(e.target.value) / hz)}
          />
          <div className="pb-markers" aria-hidden="true">
            {fights.map((f, k) => (
              <span key={`f${k}`} className="pb-fightband" style={{ left: pos(f.start), width: `max(6px, ${((f.end - f.start) / total) * 100}%)` }} />
            ))}
            {deaths.map((e, k) => (
              <span key={`d${k}`} className={`pb-tick death ${e.team ?? ""}`} style={{ left: pos(e.t_s) }} />
            ))}
            {moments.map((e, k) => (
              <button key={`m${k}`} type="button" className="pb-tick moment" style={{ left: pos(e.t_s) }} title={`${duration(e.t_s)} · ${eventLabel(e)}`} onClick={() => jump(e.t_s)} />
            ))}
          </div>
        </div>
      )}

      <div className={compact ? "pb-main compact" : "pb-main"}>
        <div className="heatmap-stage">
          {view === "3d" && matchId != null ? (
            <Stage3DBoundary onUse2D={() => setParam({ view: null })}>
              <Suspense fallback={<div className="pb3d-message"><p className="muted">Loading 3D…</p></div>}>
                <Map3D id={matchId} playback={playback} second={second} follow={follow} onPick={pick} camera={camera} names={names}
                  trailSeconds={trail / hz} trailColor={trailColor} deaths={deaths} swaps={swapLabels} onUse2D={() => setParam({ view: null })} />
              </Suspense>
            </Stage3DBoundary>
          ) : (
            <div className="heatmap-inner">
              <img src={playback.image} alt={`${playback.map} minimap`} />
              <canvas ref={canvas} className="playback-canvas" />
            </div>
          )}
          {banner && <div className="pb-banner" aria-live="polite">{eventLabel(banner)}</div>}
        </div>

        {!compact && (
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
                    <span className="pb-name">{died && <img className="pb-skull" src="/icons/death.png" alt="died" />}{p.name}</span>
                    <span className="pb-gear">
                      {here ? (
                        <>
                          <GearLabel name={weapon} /> · <GearLabel name={ordnance} /> · <GearLabel name={tacmod} />
                        </>
                      ) : (
                        "off the map / left"
                      )}
                    </span>
                    <span className="pb-nums">
                      {here && sp != null ? `${num(sp, 1)} m/s` : "–"}
                      {killsDeaths > 0 && ` · ${killsDeaths} death${killsDeaths === 1 ? "" : "s"}*`}
                    </span>
                  </button>
                ))}
              </div>
            ))}
          </aside>
        )}
      </div>

      <ul className="pb-feed">
        {recent.length === 0 && <li className="muted">Nothing yet.</li>}
        {recent.map((e, k) => (
          <li key={`${e.frame}-${e.type}-${k}`} className={e.type === "death_est" ? "death" : e.type === "loadout_change" ? "swap" : ""}>
            <span className="muted">{duration(e.t_s)}</span>{" "}
            {e.type === "death_est" ? <img className="pb-skull" src="/icons/death.png" alt="" /> : e.type === "loadout_change" ? <span>⇄</span> : e.team && <span className={`dot ${e.team}`} />}{" "}
            {e.type === "loadout_change" ? <SwapLabel e={e} /> : eventLabel(e)}
          </li>
        ))}
      </ul>

      {!compact && (
        <>
          <h3 className="pb-sub">Deaths (estimated)</h3>
          <div className="pb-summary">
            <p className="muted">
              {deaths.length} deaths{firstDeath ? <> · first: <button type="button" className="link" onClick={() => jump(firstDeath.t_s - 2)}>{firstDeath.name} at {duration(firstDeath.t_s)}</button></> : ""}
              {fights.length > 0 && ` · ${fights.length} team fight${fights.length === 1 ? "" : "s"} (${FIGHT_MIN_DEATHS}+ deaths within ${FIGHT_GAP_S} s)`}
            </p>
            {summary.map(({ p, team, mine }) => (
              <div key={p.user_id} className={`pb-sumrow ${follow === p.user_id ? "picked" : ""}`}>
                <button type="button" className={`link pb-sumname ${team === 1 ? "blue" : "orange"}`} onClick={() => setFollow(follow === p.user_id ? null : p.user_id)}>
                  {p.name}
                </button>
                <span className="pb-sumbar">
                  <span className={team === 1 ? "bluefill" : "orangefill"} style={{ width: `${(mine.length / maxDeaths) * 100}%` }} />
                </span>
                <span className="pb-sumcount">{mine.length}</span>
                <span className="pb-sumtimes">
                  {mine.slice(0, 10).map((d, k) => (
                    <button key={k} type="button" className="chip" onClick={() => jump(d.t_s - 2)} title="Jump to this death">{duration(d.t_s)}</button>
                  ))}
                  {mine.length > 10 && <span className="muted">+{mine.length - 10}</span>}
                </span>
              </div>
            ))}
          </div>
          {fights.length > 0 && (
            <>
              <h3 className="pb-sub">Team fights</h3>
              <div className="pb-fights">
                {fights.map((f, k) => (
                  <button key={k} type="button" className="chip big" onClick={() => jump(Math.max(0, f.start - 2))}>
                    {duration(f.start)} · {f.deaths} deaths <span className="blue">{f.blue}</span>/<span className="orange">{f.orange}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </>
      )}

      <p className="muted footnote">
        {playback.objects.route ? "Payload route and cart are drawn from the recorded payload distance. " : ""}
        {playback.objects.point ? "The capture point is drawn where players stand while capture progress rises (size is approximate). " : ""}
        Positions are recorded twice per second; dots glide between them. Players off the map image (spawn rooms) are hidden. Click a player to
        highlight them; keys: space play / pause, ← → skip 5 s (shift 30 s), [ ] speed, N / P next / previous fight, 1–9 and 0 pick a player,
        Esc let go{view === "3d" ? ", C next camera" : ""}. Ticks under the slider are estimated deaths (small), round / checkpoint moments (dots,
        click to jump) and fights (red bands). * Estimated. Speed is measured between recorded positions.
        {view === "3d" && (
          <>
            {" "}3D: head positions and where each player looks, five times per second; the cone points where they look. Click a player to pick
            them; Follow and First person ride along with the picked player. 3D map models from{" "}
            <a href="https://github.com/duncancarroll/ec-web-replayer" target="_blank" rel="noreferrer">ec-web-replayer</a> (MIT).
          </>
        )}
      </p>
    </div>
  );
}

/** Two matches side by side on one shared clock (both start at 0:00). */
export function PlaybackCompare({ a, b }: { a: Playback; b: Playback }) {
  const longest = Math.max(a.samples / a.hz, b.samples / b.hz);
  const clock = useClock(longest);
  return (
    <div className="pb-compare">
      <div className="heatmap-tools">
        <button onClick={() => (clock.t >= longest ? (clock.setT(0), clock.setPlaying(true)) : clock.setPlaying((p) => !p))}>
          {clock.playing ? "Pause" : clock.t >= longest ? "Replay" : "Play"}
        </button>
        <span className="zoom-buttons">
          <button className="secondary" onClick={() => clock.setT((v) => Math.max(0, v - 10))}>−10 s</button>
          <button className="secondary" onClick={() => clock.setT((v) => Math.min(longest, v + 10))}>+10 s</button>
        </span>
        <label>
          Speed
          <select value={clock.speed} onChange={(e) => clock.setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{s}×</option>
            ))}
          </select>
        </label>
        <span className="muted">
          {duration(clock.t)} / {duration(longest)}
        </span>
      </div>
      <input className="scrubber" type="range" min={0} max={longest} step={0.5} value={clock.t} aria-label="Shared match time"
        onChange={(e) => { clock.setPlaying(false); clock.setT(Number(e.target.value)); }} />
      <div className="pb-compare-grid">
        <PlaybackView playback={a} clock={clock} compact label={`${a.map} (left)`} />
        <PlaybackView playback={b} clock={clock} compact label={`${b.map} (right)`} />
      </div>
    </div>
  );
}
