import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  getCombatMatch, getMatch, getMatchHeatmap3d, getMatchHeatmapBy, getPlayback, getTimeline,
  type GearUse, type HeatmapLayerMode, type MatchDetail, type MatchPlayer, type Team,
} from "../api";
import { MatchCombatSection } from "../components/CombatView";
import { GearName, LoadoutText, LocalTime, NotFoundBox, Status, TableWrap, isNotFound } from "../components/common";
import { HEATMAP_CELL_M, HEATMAP_MODES, HeatmapView } from "../components/HeatmapView";
import { PlaybackCompare, PlaybackView } from "../components/PlaybackView";
import { TimelineView } from "../components/TimelineView";
import { FitText, InfoTip, STAT_HELP, Skeleton, useActiveTabInView } from "../components/ui";
import { duration, int, modeLabel, num, pct, playerPath, teamLabel, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

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
            <Link to={playerPath(p.user_id, p.name)}>{p.name}</Link>
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
  const full = all.filter((p) => p.play_time_s >= 240);
  function best(list: MatchPlayer[], key: (p: MatchPlayer) => number | null, low = false): MatchPlayer | undefined {
    return list.filter((p) => key(p) != null).sort((a, b) => (low ? key(a)! - key(b)! : key(b)! - key(a)!))[0];
  }
  const items: (Highlight | null)[] = [];
  const add = (label: string, hint: string, p: MatchPlayer | undefined, value: (p: MatchPlayer) => string) =>
    items.push(p ? { label, hint, player: p, value: value(p) } : null);
  add("Fastest", "Top speed held for a second", best(all, (p) => p.top_speed), (p) => `${num(p.top_speed)} m/s`);
  add("Most mobile", "Average speed, 4+ min played", best(full, (p) => p.avg_speed), (p) => `${num(p.avg_speed)} m/s`);
  add("Fewest deaths*", "Estimated deaths, 4+ min played", best(full, (p) => p.deaths_est, true), (p) => String(p.deaths_est));
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
          <strong><FitText title={h.player.name}><Link to={playerPath(h.player.user_id, h.player.name)}>{h.player.name}</Link></FitText></strong>
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
                  <Link to={playerPath(p.user_id, p.name)}>{p.name}</Link>
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
                <td data-label="Emotes" className="num">{int(p.emote_count)}</td>
                {payload && (
                  <td data-label="Push / block*" className="num">
                    {duration(p.payload_push_s)} / {duration(p.payload_block_s)}
                  </td>
                )}
                <td data-label="Arm">{p.dominant_arm ?? "–"}</td>
                <td data-label="Main loadout">
                  <LoadoutText loadout={p.loadouts[0]} stacked />
                  {p.loadouts.length > 1 && (
                    <span className="muted" title="Other loadouts: see Gear use below">+{p.loadouts.length - 1} more</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
    </>
  );
}

/** "Pulsar ×2 75% · Nova ×1 25%": times picked and share of time held, most held first. */
function GearList({ items }: { items: GearUse[] }) {
  if (items.length === 0) return <span className="muted">–</span>;
  return (
    <span className="gear-list">
      {items.map((g, i) => (
        <span key={g.code} className="nowrap">
          {i > 0 && " · "}
          <GearName item={g} /> <span title="Times picked">×{g.picks}</span> <span className="muted">{pct(g.share)}</span>
        </span>
      ))}
    </span>
  );
}

/** Every player's weapons, ordnance and tac mods in this match (replays have no shot counts, only what is held). */
const hasGearData = (m: MatchDetail) =>
  [...(m.teams.blue ?? []), ...(m.teams.orange ?? [])].some((p) => p.gear && (p.gear.weapons.length || p.gear.ordnances.length || p.gear.tacmods.length));

function GearUseTable({ m }: { m: MatchDetail }) {
  const players = [...(m.teams.blue ?? []), ...(m.teams.orange ?? [])];
  if (!hasGearData(m)) return null;
  return (
    <>
      <TableWrap>
        <table className="stack">
          <thead>
            <tr><th>Player</th><th>Weapons</th><th>Ordnance</th><th>Tac mods</th></tr>
          </thead>
          <tbody>
            {players.map((p) => (
              <tr key={p.user_id}>
                <td data-label="Player"><Link to={playerPath(p.user_id, p.name)} className={`team-text ${p.team}`}>{p.name}</Link></td>
                <td data-label="Weapons"><GearList items={p.gear.weapons} /></td>
                <td data-label="Ordnance"><GearList items={p.gear.ordnances} /></td>
                <td data-label="Tac mods"><GearList items={p.gear.tacmods} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
      <p className="muted footnote">
        ×N = times picked (switched to it, including the first one held); % = share of the time held. Replays do not
        record shots or ordnance / tac mod uses, so those cannot be counted.
      </p>
    </>
  );
}

type Tab = "players" | "combat" | "gear" | "timeline" | "heatmap" | "playback";
const TABS: [Tab, string][] = [
  ["players", "Stats per player"],
  ["combat", "Kills, damage, weapons"],
  ["gear", "Weapons, ordnance, tac mods"],
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
  const cell = HEATMAP_CELL_M;
  const h = useApi(() => getMatchHeatmapBy(m.id, mode, cell, player || undefined), `${m.id}|${mode}|${cell}|${player}`);
  const everyone = [...(m.teams.blue ?? []), ...(m.teams.orange ?? [])];
  function set(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }
  const filters = (
    <>
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
    </>
  );
  return (
    <>
      <div className="filters">{filters}</div>
      {h.loading && <Skeleton lines={5} />}
      <Status loading={false} error={h.error} />
      {h.data && <HeatmapView heatmap={h.data} controls={filters} view3d={{ key: `h3|${m.id}|${mode}|${player}`, load: () => getMatchHeatmap3d(m.id, mode, player || undefined) }} />}
    </>
  );
}

function PlaybackTab({ id }: { id: number }) {
  const [params, setParams] = useSearchParams();
  const other = Number(params.get("vs")) || 0; // ?vs=<match id>: play a second match next to this one
  const [draft, setDraft] = useState(other ? String(other) : "");
  const p = useApi(() => getPlayback(id), `p${id}`);
  const q = useApi(() => (other ? getPlayback(other) : Promise.resolve(null)), `q${other}`);
  function compare(value: number) {
    const next = new URLSearchParams(params);
    if (value > 0 && value !== id) next.set("vs", String(value));
    else next.delete("vs");
    setParams(next, { replace: true });
  }
  return (
    <>
      <form className="filters" onSubmit={(e) => { e.preventDefault(); compare(Number(draft.replace("#", "")) || 0); }}>
        <label>
          Compare with match #
          <input value={draft} onChange={(e) => setDraft(e.target.value)} inputMode="numeric" placeholder="match number" size={12} />
        </label>
        <button type="submit" className="secondary">Compare</button>
        {other > 0 && <button type="button" className="secondary" onClick={() => { setDraft(""); compare(0); }}>Stop comparing</button>}
      </form>
      {(p.loading || (other > 0 && q.loading)) && <Skeleton lines={5} />}
      <Status loading={false} error={p.error ?? q.error} />
      {p.data && other > 0 && q.data ? <PlaybackCompare a={p.data} b={q.data} aId={id} bId={other} /> : p.data && other === 0 ? <PlaybackView playback={p.data} matchId={id} /> : null}
    </>
  );
}

const MATCH_LINKS: [string, string][] = [["/matches", "All matches"], ["/", "Home"]];

export function MatchPage() {
  const id = useParams().id ?? "";
  // match numbers only: anything else (/matches/abc, a number too long to be one) cannot exist, so the server is not asked
  return /^\d{1,15}$/.test(id) ? <MatchContent id={Number(id)} /> : <BadMatchAddress />;
}

function BadMatchAddress() {
  usePageTitle("Match not found");
  return <NotFoundBox heading="Match not found" links={MATCH_LINKS}>That is not a match number.</NotFoundBox>;
}

function MatchContent({ id }: { id: number }) {
  const match = useApi(() => getMatch(id), String(id));
  const m = match.data;
  usePageTitle(m ? `${title(m.map)} #${m.id}` : `Match #${id}`);
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "players";
  const setTab = (t: Tab) => setParams(t === "players" ? {} : { tab: t }, { replace: true });
  // the Combat tab only exists for matches the recorder sent a report for (same cached request as the tab's own content)
  const sessionId = m?.session_id;
  const combat = useApi(() => (sessionId ? getCombatMatch(sessionId) : Promise.resolve(null)), `combat-match|${sessionId ?? ""}`);
  const hasCombat = !!combat.data;
  const tabs = TABS.filter(([t]) => (t !== "combat" || hasCombat) && (t !== "gear" || (!!m && hasGearData(m))));
  const tabStrip = useActiveTabInView(`${tab}|${tabs.length}|${!!m}`);

  return (
    <section>
      {match.loading && <Skeleton cards={3} lines={4} />}
      {match.error && !m && (isNotFound(match.error) ? (
        <NotFoundBox heading={`Match #${id} not found`} links={MATCH_LINKS}>
          This match is not in the archive (yet). It may still be waiting to be read, or the number is wrong.
        </NotFoundBox>
      ) : (
        <Status loading={false} error={match.error} />
      ))}
      {m && (
        <>
          <div className="section-head">
            <h1>
              {title(m.map)} <span className="muted">· {modeLabel(m.mode)} · #{m.id}</span>
            </h1>
          </div>
          <p className="muted">
            <LocalTime iso={m.started_at} /> · {duration(m.duration_s)} · {m.player_count} players · contested {duration(m.contested_s)}
            {m.private_match && " · private"}
            {m.recorded_by && <> · recorded by {m.recorded_by}</>}
          </p>
          {m.duplicate_of != null ? (
            <p className="note">
              Duplicate recording: this match was also saved as{" "}
              <Link to={`/matches/${m.duplicate_of}`}>match #{m.duplicate_of}</Link>, which is the one counted in stats,
              leaderboards and achievements. This copy is not counted.
            </p>
          ) : m.also_recorded_in.length > 0 && (
            <p className="note">
              Also recorded in (not counted again):{" "}
              {m.also_recorded_in.map((other, i) => (
                <span key={other}>
                  {i > 0 && ", "}
                  <Link to={`/matches/${other}`}>match #{other}</Link>
                </span>
              ))}
            </p>
          )}

          {m.repaired && (
            <p className="note">
              Repaired replay: the file was damaged and was recovered
              {m.repaired.aggressive ? " with aggressive repair" : " in repair mode"}
              {m.repaired.frames != null && <> ({m.repaired.frames.toLocaleString()} frames read correctly)</>}. Parts of
              the match may be missing, so its stats can be incomplete; nothing was guessed.
            </p>
          )}

          <Scoreboard m={m} />
          <Highlights m={m} />

          <div className="tabs section-tabs" role="tablist" aria-label="Match views" ref={tabStrip}>
            {tabs.map(([t, hint]) => (
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
          {tab === "combat" && hasCombat && <div className="tab-narrow"><MatchCombatSection sessionId={m.session_id} /></div>}
          {tab === "gear" && <div className="tab-narrow"><GearUseTable m={m} /></div>}
          {tab === "timeline" && <TimelineTab id={m.id} />}
          {tab === "heatmap" && <HeatmapTab m={m} />}
          {tab === "playback" && <PlaybackTab id={m.id} />}
        </>
      )}
    </section>
  );
}
