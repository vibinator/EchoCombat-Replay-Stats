import { useEffect, useRef, useState } from "react";
import type { Playback } from "../api";
import { duration } from "../format";

const TEAM_COLORS = ["", "#19d9fc", "#ea7924"];
const SPEEDS = [1, 2, 4, 8, 16];

/** Animated player dots over the minimap, driven by the 2 Hz position tracks. */
export function PlaybackView({ playback }: { playback: Playback }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [t, setT] = useState(0); // sample index (float)
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(4);
  const [names, setNames] = useState(true);
  const last = useRef<number | null>(null);
  const end = Math.max(0, playback.samples - 1);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = (now: number) => {
      if (last.current != null) {
        const dt = (now - last.current) / 1000;
        setT((v) => {
          const next = v + dt * playback.hz * speed;
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
  }, [playing, speed, end, playback.hz]);

  useEffect(() => {
    const el = canvas.current;
    if (!el) return;
    const box = el.getBoundingClientRect();
    el.width = box.width * devicePixelRatio;
    el.height = box.height * devicePixelRatio;
    const ctx = el.getContext("2d")!;
    ctx.scale(devicePixelRatio, devicePixelRatio);
    ctx.clearRect(0, 0, box.width, box.height);
    const i = Math.floor(t);
    const f = t - i;
    ctx.font = "11px system-ui, sans-serif";
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
      // trail: last 5 s
      ctx.strokeStyle = TEAM_COLORS[a[2]];
      ctx.globalAlpha = 0.35;
      ctx.lineWidth = 2;
      ctx.beginPath();
      let pen = false;
      for (let k = Math.max(0, i - 10); k <= i; k++) {
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
      ctx.globalAlpha = 1;
      ctx.fillStyle = TEAM_COLORS[a[2]];
      ctx.strokeStyle = "#16181c";
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      if (names) {
        ctx.fillStyle = "#fff";
        ctx.strokeStyle = "rgba(0,0,0,.7)";
        ctx.lineWidth = 3;
        ctx.strokeText(p.name, x + 7, y - 6);
        ctx.fillText(p.name, x + 7, y - 6);
      }
    }
  }, [t, playback, names]);

  return (
    <div className="playback">
      <div className="heatmap-tools">
        <button onClick={() => (t >= end ? (setT(0), setPlaying(true)) : setPlaying(!playing))}>{playing ? "Pause" : t >= end ? "Replay" : "Play"}</button>
        <label>
          Speed
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            {SPEEDS.map((s) => (
              <option key={s} value={s}>{s}×</option>
            ))}
          </select>
        </label>
        <label className="inline-check">
          <input type="checkbox" checked={names} onChange={(e) => setNames(e.target.checked)} /> Names
        </label>
        <span className="muted">
          {duration(t / playback.hz)} / {duration(end / playback.hz)}
        </span>
      </div>
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
      <div className="heatmap-stage">
        <div className="heatmap-inner">
          <img src={playback.image} alt={`${playback.map} minimap`} />
          <canvas ref={canvas} className="playback-canvas" />
        </div>
      </div>
      <p className="muted footnote">Positions are recorded twice per second; dots glide between them. Players off the map image (spawn rooms) are hidden.</p>
    </div>
  );
}
