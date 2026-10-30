import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  getMatch, getMatchHeatmapBy, getPlayback, getTimeline, matchExportUrl,
  type HeatmapLayerMode, type MatchDetail, type MatchPlayer, type Team,
} from "../api";
import { LoadoutText, Status, TableWrap } from "../components/common";
import { CELL_SIZES, HEATMAP_MODES, HeatmapView } from "../components/HeatmapView";
import { PlaybackView } from "../components/PlaybackView";
import { TimelineView } from "../components/TimelineView";
import { InfoTip, STAT_HELP, Skeleton } from "../components/ui";
import { dateTime, duration, modeLabel, num, pct, teamLabel, title } from "../format";
import { useApi } from "../useApi";

function resultText(m: MatchDetail): string {
  if (m.mode === "payload") {
    if (m.final_payload_checkpoint == null) return "Payload progress not recorded (older replay)";
    if (!m.winner) return "Winner unknown — recording ended early";
    return m.winner === m.attacking_team ? "Payload delivered" : "Defence held";
  }
  return m.winner ? `${teamLabel(m.winner)} wins` : "Draw / unfinished";
}

function TeamColumn({ team, m }: { team: Team; m: MatchDetail }) {
  const players = m.teams[team] ?? [];
  const won = m.winner === team;
  const score = m.mode === "capture_point" ? (team === "blue" ? m.blue_rounds : m.orange_rounds) : null;
  return (
    <div className={`team-col ${team}${won ? " won" : ""}`}>
      <div className="team-col-head">
        <span className={`team-text ${team}`}>{teamLabel(team)}</span>
        {score != null && <span className="team-score">{score}</span>}
        {m.mode === "payload" && m.attacking_team && <span className="tag">{m.attacking_team === team ? "attack" : "defence"}</span>}
        {won && <span className="tag win">winner</span>}
      </div>
      <ul>
        {players.map((p) => (
          <li key={p.user_id}>
            <Link to={`/players/${p.user_id}`}>{p.name}</Link>
            {p.level != null && <span className="muted"> lvl {p.level}</span>}
          </li>
        ))}
        {players.length === 0 && <li className="muted">No players</li>}
      </ul>
    </div>
  );
}

function Scoreboard({ m }: { m: MatchDetail }) {
  return (
    <div className="scoreboard-big">
      <TeamColumn team="blue" m={m} />
      <div className="score-center">
        {m.mode === "capture_point" ? (
          <strong className="score-big">
            <span className="team-text blue">{m.blue_rounds}</span> – <span className="team-text orange">{m.orange_rounds}</span>
          </strong>
        ) : (
          <strong className="score-big">{m.final_payload_checkpoint != null ? `CP ${m.final_payload_checkpoint}/3` : "–"}</strong>
        )}
        <span>{resultText(m)}</span>
        {m.mode === "payload" && m.final_game_timer != null && <span className="muted">{duration(m.final_game_timer)} left on the clock</span>}
        {m.mode === "capture_point" && (m.blue_capture_s > 0 || m.orange_capture_s > 0) && (
          <span className="muted">capturing: blue {duration(m.blue_capture_s)} · orange {duration(m.orange_capture_s)}</span>
        )}
      </div>
      <TeamColumn team="orange" m={m} />
    </div>
  );
}

type Highlight = { label: string; hint: string; player: MatchPlayer; value: string };

function Highlights({ m }: { m: MatchDetail }) {
  const all = [...(m.teams.blue ?? []), ...(m.teams.orange ?? [])];
  const full = all.filter((p) => p.play_time_s >= 180);
  function best(list: MatchPlayer[], key: (p: MatchPlayer) => number | null, low = false): MatchPlayer | undefined {
    return list.filter((p) => key(p) != null).sort((a, b) => (low ? key(a)! - key(b)! : key(b)! - key(a)!))[0];
  }
  const items: (Highlight | null)[] = [];
  const add = (label: string, hint: string, p: MatchPlayer | undefined, value: (p: MatchPlayer) => string) =>
    items.push(p ? { label, hint, player: p, value: value(p) } : null);
  add("Fastest", "Top speed held for a second", best(all, (p) => p.top_speed), (p) => `${num(p.top_speed)} m/s`);
  add("Most mobile", "Average speed, 3+ min played", best(full, (p) => p.avg_speed), (p) => `${num(p.avg_speed)} m/s`);
  add("Fewest deaths*", "Estimated deaths, 3+ min played", best(full, (p) => p.deaths_est, true), (p) => String(p.deaths_est));
  add("In the thick of it", "Most time near enemies", best(full, (p) => p.pct_near_enemy), (p) => pct(p.pct_near_enemy));
  if (m.mode === "payload") {
    add("Top pusher*", "Time on the payload as attacker", best(all, (p) => p.payload_push_s || null), (p) => duration(p.payload_push_s));
    add("Top blocker*", "Time on the payload as defender", best(all, (p) => p.payload_block_s || null), (p) => duration(p.payload_block_s));
  }
  const shown = items.filter((h): h is Highlight => h !== null);
  if (shown.length === 0) return null;
  return (
    <div className="cards highlights">
      {shown.map((h) => (
        <div key={h.label} className={`card team-${h.player.team}`} title={h.hint}>
          <span className="label">{h.label}</span>
          <strong><Link to={`/players/${h.player.user_id}`}>{h.player.name}</Link></strong>
          <span className="muted">{h.value}</span>
        </div>
      ))}
    </div>
  );
}

const COLUMNS = ["Play time", "Deaths*", "Ping", "Avg speed", "Top speed", "Stopped", "Inverted", "Near mate", "Near enemy", "Loss", "Emotes"];

function TeamTable({ team, players, payload }: { team: Team; players: MatchPlayer[]; payload: boolean }) {
  if (players.length === 0) return null;
  const cols = [...COLUMNS, ...(payload ? ["Push / block*"] : []), "Arm", "Main loadout"];
  return (
    <>
      <h2 className={`team-text ${team}`}>{teamLabel(team)} team</h2>
      <TableWrap>
        <table className="stack">
          <thead>
            <tr>
              <th>Player</th>
              {cols.map((c) => (
                <th key={c} className={c === "Arm" || c === "Main loadout" ? "" : "num"}>
                  {c}
                  <InfoTip text={STAT_HELP[c]} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.user_id}>
                <td data-label="Player">
                  <Link to={`/players/${p.user_id}`}>{p.name}</Link>
                  {p.left_early && <span className="tag" title="Last seen more than 45 s before the end">left early</span>}
                </td>
                <td data-label="Play time" className="num">{duration(p.play_time_s)}</td>
                <td data-label="Deaths*" className="num">{p.deaths_est}</td>
                <td data-label="Ping" className="num">{num(p.avg_ping, 0)}</td>
                <td data-label="Avg speed" className="num">{num(p.avg_speed)} m/s</td>
                <td data-label="Top speed" className="num">{num(p.top_speed)} m/s</td>
                <td data-label="Stopped" className="num">{pct(p.pct_stopped)}</td>
                <td data-label="Inverted" className="num">{pct(p.pct_upside_down)}</td>
                <td data-label="Near mate" className="num">{pct(p.pct_near_mate)}</td>
                <td data-label="Near enemy" className="num">{pct(p.pct_near_enemy)}</td>
                <td data-label="Loss" className="num">{p.avg_packet_loss == null ? "–" : `${(p.avg_packet_loss * 100).toFixed(1)}%`}</td>
                <td data-label="Emotes" className="num">{p.emote_count}</td>
                {payload && (
                  <td data-label="Push / block*" className="num">
                    {duration(p.payload_push_s)} / {duration(p.payload_block_s)}
                  </td>
                )}
                <td data-label="Arm">{p.dominant_arm ?? "–"}</td>
                <td data-label="Main loadout">
                  <LoadoutText loadout={p.loadouts[0]} />
                  {p.loadouts.length > 1 && <span className="muted"> +{p.loadouts.length - 1}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </>
  );
}

type Tab = "players" | "timeline" | "heatmap" | "playback";
const TABS: [Tab, string][] = [
  ["players", "Stats per player"],
  ["timeline", "Score and events over time"],
  ["heatmap", "Where everyone went"],
  ["playback", "Watch the positions move"],
];

function TimelineTab({ id }: { id: number }) {
  const t = useApi(() => getTimeline(id), `t${id}`);
  return (
    <>
      {t.loading && <Skeleton lines={4} />}
      <Status loading={false} error={t.error} />
      {t.data && <TimelineView timeline={t.data} />}
    </>
  );
}

function HeatmapTab({ m }: { m: MatchDetail }) {
  const [params, setParams] = useSearchParams();
  const player = params.get("hm_player") ?? "";
  const mode = (params.get("hm_mode") as HeatmapLayerMode | "player") || "team";
  const cell = Number(params.get("hm_cell") ?? 0.25);
  const h = useApi(() => getMatchHeatmapBy(m.id, mode, cell, player || undefined), `${m.id}|${mode}|${cell}|${player}`);
  const everyone = [...(m.teams.blue ?? []), ...(m.teams.orange ?? [])];
  function set(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }
  return (
    <>
      <div className="filters">
        <label>
          Colour by
          <select value={mode} onChange={(e) => set("hm_mode", e.target.value, "team")}>
            {HEATMAP_MODES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            <option value="player">Player</option>
          </select>
        </label>
        <label>
          Show
          <select value={player} onChange={(e) => set("hm_player", e.target.value, "")}>
            <option value="">All players</option>
            {everyone.map((p) => <option key={p.user_id} value={p.user_id}>{p.name} ({p.team})</option>)}
          </select>
        </label>
        <label>
          Detail
          <select value={cell} onChange={(e) => set("hm_cell", e.target.value, "0.25")}>
            {CELL_SIZES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
      </div>
      {h.loading && <Skeleton lines={5} />}
      <Status loading={false} error={h.error} />
      {h.data && <HeatmapView heatmap={h.data} />}
    </>
  );
}

function PlaybackTab({ id }: { id: number }) {
  const p = useApi(() => getPlayback(id), `p${id}`);
  return (
    <>
      {p.loading && <Skeleton lines={5} />}
      <Status loading={false} error={p.error} />
      {p.data && <PlaybackView playback={p.data} />}
    </>
  );
}

export function MatchPage() {
  const id = Number(useParams().id);
  const match = useApi(() => getMatch(id), String(id));
  const m = match.data;
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "players";
  const setTab = (t: Tab) => setParams(t === "players" ? {} : { tab: t }, { replace: true });
  const [exportOpen, setExportOpen] = useState(false);

  return (
    <section>
      {match.loading && <Skeleton cards={3} lines={4} />}
      <Status loading={false} error={match.error} />
      {m && (
        <>
          <div className="section-head">
            <h1>
              {title(m.map)} <span className="muted">· {modeLabel(m.mode)} · #{m.id}</span>
            </h1>
            <span className="muted">
              <button className="link" onClick={() => setExportOpen(!exportOpen)}>Export</button>
              {exportOpen && (
                <>
                  {" "}<a href={matchExportUrl(m.id, "csv")}>CSV</a> · <a href={matchExportUrl(m.id, "json")}>JSON</a>
                </>
              )}
            </span>
          </div>
          <p className="muted">
            {dateTime(m.started_at)} · {duration(m.duration_s)} · {m.player_count} players · contested {duration(m.contested_s)}
            {m.private_match && " · private"}
            {m.recorded_by && <> · recorded by {m.recorded_by}</>}
          </p>
          {m.also_recorded_in.length > 0 && (
            <p className="note">
              Also recorded in:{" "}
              {m.also_recorded_in.map((other, i) => (
                <span key={other}>
                  {i > 0 && ", "}
                  <Link to={`/matches/${other}`}>match #{other}</Link>
                </span>
              ))}
            </p>
          )}

          <Scoreboard m={m} />
          <Highlights m={m} />

          <div className="tabs section-tabs" role="tablist" aria-label="Match views">
            {TABS.map(([t, hint]) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
                <span className="tab-label">{title(t)}</span>
                <span className="tab-hint">{hint}</span>
              </button>
            ))}
          </div>

          {tab === "players" && (
            <>
              <TeamTable team="blue" players={m.teams.blue ?? []} payload={m.mode === "payload"} />
              <TeamTable team="orange" players={m.teams.orange ?? []} payload={m.mode === "payload"} />
              <p className="muted footnote">
                * Estimated. Percentages count time inside the map bounds only. Hover ⓘ for what each column means.
              </p>
            </>
          )}
          {tab === "timeline" && <TimelineTab id={m.id} />}
          {tab === "heatmap" && <HeatmapTab m={m} />}
          {tab === "playback" && <PlaybackTab id={m.id} />}
        </>
      )}
    </section>
  );
}
