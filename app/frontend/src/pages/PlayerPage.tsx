import { type ReactNode, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";
import {
  getCombatPlayer, getCompanions, getPlayer, getPlayerHeatmap3d, getPlayerHeatmapBy, getTrends,
  type CombatPlayerStats, type Companion, type CompanionWindow, type GearUse, type GearUseSet, type HeatmapLayerMode, type Period, type PlayerProfile, type PlayerStats, type TrendPoint,
} from "../api";
import { AchievementsStrip, AchievementsSummary } from "../components/AchievementsView";
import { CombatSection } from "../components/CombatView";
import { ShareBar, Sparkline, SplitBar, VsAverage } from "../components/bars";
import { LineChart } from "../components/charts";
import { GearName, MatchTable, NotFoundBox, Status, TableWrap, TeamBadge, isNotFound } from "../components/common";
import { HEATMAP_CELL_M, HEATMAP_MODES, HeatmapView } from "../components/HeatmapView";
import { PlayerAvatar, PlayerBio, usePlayerBio } from "../components/PlayerBio";
import { InfoTip, MoreCard, Skeleton, useActiveTabInView } from "../components/ui";
import { MAPS, dateTime, hoursMinutes, int, nameSlug, num, pct, periodLabel, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const PERIODS: [Period, string][] = [
  ["day", "Today"],
  ["week", "This week"],
  ["month", "This month"],
  ["all", "All time"],
];

/** "Mostly right", "Even split"…: which of two parts is bigger, in a word or two. `strong` = label at 90 %+. */
function leaning(first: number, names: [string, string], strong?: [string, string]): string {
  const i = first >= 0.5 ? 0 : 1;
  const share = Math.max(first, 1 - first);
  if (strong && share >= 0.9) return strong[i];
  if (share >= 0.6) return `Mostly ${names[i]}`;
  return "Even split";
}

/** Right / left split of the in-game dominant arm, with the ratio underneath. */
function ArmBar({ left }: { left: number | null }) {
  if (left == null) return <strong>–</strong>;
  const right = 1 - left;
  const ratio = left === 0 ? "right only" : right === 0 ? "left only" : `${num(right / left, 1)} : 1`;
  return (
    <>
      <strong className="lean">{leaning(right, ["right", "left"], ["Right-handed", "Left-handed"])}</strong>
      <SplitBar parts={[
        { label: "R", value: right, color: "var(--chart-1)" },
        { label: "L", value: left, color: "var(--chart-2)" },
      ]} />
      <span className="muted">Right : left {ratio}</span>
    </>
  );
}

/** Games per mode. */
function ModeBar({ games }: { games: Record<string, number> }) {
  const payload = games.payload ?? 0;
  const capture = games.capture_point ?? 0;
  if (!(payload + capture)) return <strong>–</strong>;
  return (
    <>
      <strong className="lean">{leaning(payload / (payload + capture), ["payload", "capture"])}</strong>
      <SplitBar parts={[
        { label: "Payload", value: payload, color: "var(--chart-1)", detail: int(payload) },
        { label: "Capture", value: capture, color: "var(--chart-2)", detail: int(capture) },
      ]} />
    </>
  );
}

/** Time near the payload pushing vs blocking it. */
function PayloadBar({ push, block }: { push: number; block: number }) {
  if (!(push + block)) return <strong>–</strong>;
  return (
    <>
      <strong className="lean">{leaning(push / (push + block), ["pushing", "blocking"])}</strong>
      <SplitBar parts={[
        { label: "Push", value: push, color: "var(--chart-1)", detail: hoursMinutes(push) },
        { label: "Block", value: block, color: "var(--chart-2)", detail: hoursMinutes(block) },
      ]} />
    </>
  );
}

/** label, value, hint, something under the value (a sparkline) */
type CardRow = [string, ReactNode, string?, ReactNode?];

type Averages = NonNullable<PlayerProfile["site_avg"]>;

// the cards always shown at the top (the first HEADLINE_SIZE of these that exist); every other card is under "More stats"
const HEADLINE = ["Games", "Win rate", "Hours played", "Top speed", "Average speed", "Wins – losses", "Deaths / game*"];
const HEADLINE_SIZE = 6;

function StatCard({ row: [label, value, hint, under] }: { row: CardRow }) {
  return (
    <div className="card">
      <span className="label">
        {label}
        <InfoTip text={hint} />
      </span>
      {typeof value === "string" ? <strong>{value}</strong> : value}
      {under}
    </div>
  );
}

/**
 * A handful of headline cards; the rest open from a "More stats" card in the same grid (user, 2026-11-09: a pane, not a
 * dropdown under the cards), so the tabs are not pushed far down the page. The same card closes them again.
 */
function ProfileCards({ rows }: { rows: CardRow[] }) {
  const [open, setOpen] = useState(false);
  const headline = HEADLINE.map((label) => rows.find(([l]) => l === label)).filter((r): r is CardRow => !!r).slice(0, HEADLINE_SIZE);
  const rest = rows.filter((r) => !headline.includes(r));
  const shown = open ? [...headline, ...rest] : headline;
  return (
    <>
      <div className="cards">
        {shown.map((row) => <StatCard key={row[0]} row={row} />)}
        {rest.length > 0 && (
          <MoreCard open={open} count={rest.length} onToggle={() => setOpen(!open)}
            detail={open ? `Back to the top ${headline.length}` : "Movement, positioning, connection…"} />
        )}
      </div>
      {shown.some(([label]) => label.endsWith("*")) && <p className="muted footnote">* Estimated.</p>}
    </>
  );
}

/** Per month, all time: the line under a card. */
function trend(items: TrendPoint[] | undefined, key: "games" | "avg_speed" | "deaths_per_game_est" | "avg_ping", label: string): ReactNode {
  if (!items || items.length < 2) return undefined;
  return <Sparkline values={items.map((i) => i[key])} label={`${label} per month, all time`} />;
}

function cards(s: PlayerStats, avg: Averages = {}, months?: TrendPoint[]): CardRow[] {
  // averages and rates count only games of 2+ minutes with 2+ players per team (user, 2026-11-07, Review DATA-3);
  // the win rate counts games with a recorded winner (DATA-2). Each ⓘ says so with the numbers behind it.
  const counted = s.counted_games === s.games ? "" : ` Counts ${int(s.counted_games)} of ${int(s.games)} games: 2+ minutes with 2+ players per team.`;
  const decided = s.decided_games == null ? "" : ` ${int(s.decided_games)} of ${int(s.games)} games have a recorded winner.`;
  const list: CardRow[] = [
    ["Games", int(s.games), "The line: games per month, all time", trend(months, "games", "Games")],
    // left out of the answer while win-loss stats are hidden from players
    ...(s.wins != null && s.losses != null
      ? ([
          ["Wins – losses", `${int(s.wins)} – ${int(s.losses)}`, `Matches without a known winner are not counted.${decided}${counted}`],
          ["Win rate", s.wins + s.losses ? pct(s.wins / (s.wins + s.losses)) : "–", `Wins out of the games with a known winner.${decided}${counted}`],
        ] as CardRow[])
      : []),
    ["Hours played", num(s.hours_played)],
    ["Deaths*", int(s.deaths_est), `Estimated from leaving the map bounds.${counted}`],
    ["Deaths / game*", num(s.deaths_per_game_est, 2), `The line: per month, all time.${counted}`, trend(months, "deaths_per_game_est", "Deaths per game")],
    ["Average speed", `${num(s.avg_speed, 2)} m/s`, `The line: per month, all time.${counted}`, trend(months, "avg_speed", "Average speed")],
    ["Top speed", `${num(s.top_speed)} m/s`, `Fastest speed held for a full second.${counted}`],
    ["Time idle", <VsAverage value={s.pct_stopped} average={avg.pct_stopped} />, `Moving slower than 1 m/s. The tick: every player's average.${counted}`],
    ["Inverted", <VsAverage value={s.pct_upside_down} average={avg.pct_upside_down} />, `The tick: every player's average.${counted}`],
    ["Near a teammate", <VsAverage value={s.pct_near_mate} average={avg.pct_near_mate} />, `The tick: every player's average.${counted}`],
    ["Near an enemy", <VsAverage value={s.pct_near_enemy} average={avg.pct_near_enemy} />, `The tick: every player's average.${counted}`],
    ["Average ping", num(s.avg_ping, 0), `Readings above 400 ms count as 400. The line: per month, all time.${counted}`, trend(months, "avg_ping", "Average ping")],
    ["Packet loss", s.avg_packet_loss == null ? "–" : `${(s.avg_packet_loss * 100).toFixed(2)}%`],
    ["Emotes", int(s.emote_count)],
    ["Left early", <VsAverage value={s.pct_left_early} average={avg.pct_left_early} />, `Last seen more than 45 s before the end. The tick: every player's average.${counted}`],
    ["Arm", <ArmBar left={s.pct_left_arm} />, "Share of play time with the in-game dominant arm set to right / left"],
  ];
  if (s.games) list.push(["Modes", <ModeBar games={s.games_by_mode} />]);
  if (s.games_by_mode.payload) {
    list.push(["Payload push / block*", <PayloadBar push={s.payload_push_s} block={s.payload_block_s} />,
      "Estimated: within 3 m of the payload, attacking (push) or defending (block)"]);
  }
  return list;
}

/**
 * The game's own numbers in the header (all time), from the recorder's match reports: a separate source from the replay
 * stats, labelled as such. Opens the Combat tab. Nothing when the player has no reports.
 */
function GameFacts({ c, onOpen }: { c: CombatPlayerStats | null; onOpen: () => void }) {
  if (!c?.matches || !c.stats) return null;
  const mvp = c.awards?.items.find((a) => a.key === "mvp")?.count ?? 0;
  const parts = [
    `K/D ${c.stats.kd == null ? "–" : num(c.stats.kd, 2)}`,
    `${int(c.stats.kills)} kills`,
    ...(c.awards ? [`${int(mvp)} MVP${mvp === 1 ? "" : "s"}`, `${int(c.awards.total)} award${c.awards.total === 1 ? "" : "s"}`] : []),
  ];
  return (
    <span className="game-facts">
      <span className="muted">From the game</span>
      <InfoTip text={`The game's own counters from ${int(c.matches)} recorded match${c.matches === 1 ? "" : "es"}, all time. A separate source from the replay stats on this page, so numbers can differ.`} />
      {": "}
      <button type="button" className="link-button" onClick={onOpen}>{parts.join(" · ")}</button>
    </span>
  );
}

function ProfileHeader({ p, combat, onOpenCombat }: { p: PlayerProfile; combat: CombatPlayerStats | null; onOpenCombat: () => void }) {
  const main = p.loadouts[0];
  // no `result` while win-loss stats are hidden from players: no form strip then
  const form = p.recent_matches.slice(0, 10).filter((m) => m.result !== undefined);
  const bio = usePlayerBio(p.user_id);
  usePageTitle(p.name);
  return (
    <div className="profile-header">
      <div className="profile-identity">
        <PlayerAvatar profile={bio.profile} />
        <div>
          <h1>
            {p.name}
          </h1>
        <p className="muted">
          {p.level != null && `Level ${p.level} · `}First seen {dateTime(p.first_seen_at).slice(0, 10)} · Last seen {dateTime(p.last_seen_at).slice(0, 10)}
          {p.merged_ids.length > 0 && ` · merged with ${p.merged_ids.length} other ID${p.merged_ids.length > 1 ? "s" : ""}`}
        </p>
        <div className="profile-facts">
          <GameFacts c={combat} onOpen={onOpenCombat} />
          {main && (
            <span>
              Main loadout: <GearName item={main.weapon} /> · <GearName item={main.ordnance} /> · <GearName item={main.tacmod} />
            </span>
          )}
          {form.length > 0 && (
            <span className="form" title="Last 10 matches, newest first (W win, L loss, – unknown)">
              Form:{" "}
              {form.map((m) => (
                <Link key={m.id} to={`/matches/${m.id}`} className={`form-dot ${m.result ?? "none"}`} aria-label={m.result ?? "unknown"}>
                  {m.result === "win" ? "W" : m.result === "loss" ? "L" : "–"}
                </Link>
              ))}
            </span>
          )}
        </div>
          <PlayerBio userId={p.user_id} profile={bio.profile} onSaved={bio.set} />
        </div>
      </div>
      <div className="profile-actions">
        <Link className="button secondary" to={`/compare?players=${p.user_id}`}>
          Compare
        </Link>
      </div>
    </div>
  );
}

function GearUseTable({ heading, items }: { heading: string; items: GearUse[] }) {
  const top = Math.max(0, ...items.map((g) => g.share ?? 0));
  return (
    <TableWrap>
      <table className="stack">
        <thead>
          <tr><th>{heading}</th><th className="num">Picked</th><th className="num">Games</th><th>Time held</th></tr>
        </thead>
        <tbody>
          {items.length === 0 && (
            <tr><td colSpan={4} className="muted">–</td></tr>
          )}
          {items.map((g) => (
            <tr key={g.code}>
              <td data-label={heading}><GearName item={g} /></td>
              <td data-label="Picked" className="num">{g.picks.toLocaleString()}</td>
              <td data-label="Games" className="num">{(g.games ?? 0).toLocaleString()}</td>
              <td data-label="Time held"><ShareBar value={g.share} max={top}>{pct(g.share)}</ShareBar></td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}

/** Per weapon / ordnance / tac mod: times picked, games used, share of time held (no shot counts exist). */
function GearUseSection({ gear }: { gear: GearUseSet }) {
  return (
    <>
      <h2>Gear use</h2>
      <div className="gear-use">
        <GearUseTable heading="Weapon" items={gear.weapons} />
        <GearUseTable heading="Ordnance" items={gear.ordnances} />
        <GearUseTable heading="Tac mod" items={gear.tacmods} />
      </div>
      <p className="muted footnote">
        Picked = times switched to it (including the first one held in a match); Games = matches it was used in. Replays
        do not record shots or ordnance / tac mod uses, so those cannot be counted.
      </p>
    </>
  );
}

function Trends({ userId }: { userId: string }) {
  const [bucket, setBucket] = useState<"week" | "month" | "year">("month");
  const t = useApi(() => getTrends(userId, bucket), `${userId}|${bucket}`);
  // labelled by the bucket the data was fetched for (the tabs switch before the new data arrives)
  const items = (t.data?.items ?? []).map((i) => ({ ...i, period: periodLabel(i.period, t.data!.bucket) }));
  return (
    <>
      <div className="section-head">
        <h2>Trends</h2>
        <div className="tabs" role="tablist">
          {(["week", "month", "year"] as const).map((b) => (
            <button key={b} role="tab" aria-selected={bucket === b} className={bucket === b ? "tab active" : "tab"} onClick={() => setBucket(b)}>
              Per {b}
            </button>
          ))}
        </div>
      </div>
      {t.loading && <Skeleton lines={3} />}
      {items.length < 2 ? (
        !t.loading && <p className="muted">Not enough periods for a trend yet.</p>
      ) : (
        <div className="small-multiples">
          {items.some((i) => i.win_rate !== undefined) && (
            <LineChart title="Win rate" data={items.map((i) => ({ label: i.period, value: i.win_rate ?? null }))} format={(v) => pct(v)} min={0} />
          )}
          <LineChart title="Average speed (m/s)" data={items.map((i) => ({ label: i.period, value: i.avg_speed }))} format={(v) => num(v)} />
          <LineChart title="Deaths per game (est.)" data={items.map((i) => ({ label: i.period, value: i.deaths_per_game_est }))} format={(v) => num(v)} color="var(--chart-2)" />
          <LineChart title="Average ping" data={items.map((i) => ({ label: i.period, value: i.avg_ping }))} format={(v) => num(v, 0)} color="var(--chart-2)" />
          <LineChart title="Games" data={items.map((i) => ({ label: i.period, value: i.games }))} min={0} />
        </div>
      )}
    </>
  );
}

/** Wins vs losses as a split bar with the record as text. */
function RecordBar({ wins, losses }: { wins: number; losses: number }) {
  if (!wins && !losses) return <span className="muted">–</span>;
  return (
    <span className="record-cell">
      <SplitBar percentages={false} parts={[
        { label: "W", value: wins, color: "var(--ok)", detail: String(wins) },
        { label: "L", value: losses, color: "var(--bad)", detail: String(losses) },
      ]} />
    </span>
  );
}

function CompanionTable({ title: heading, rows, together }: { title: string; rows: Companion[]; together: boolean }) {
  const showRecord = rows.some((c) => c.wins !== undefined); // hidden from players: left out of the answer
  const most = Math.max(0, ...rows.map((c) => c.games));
  return (
    <div>
      <h3>{heading}</h3>
      {rows.length === 0 ? (
        <p className="muted">None yet.</p>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr>
                <th>Player</th>
                <th>Games</th>
                {showRecord && <th>{together ? "Won together" : "Won against"}</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.user_id}>
                  <td data-label="Player"><Link to={playerPath(c.user_id, c.name)}>{c.name}</Link></td>
                  <td data-label="Games"><ShareBar value={c.games} max={most}>{int(c.games)}</ShareBar></td>
                  {showRecord && (
                    <td data-label={together ? "Won together" : "Won against"}>
                      <RecordBar wins={c.wins ?? 0} losses={c.losses ?? 0} />
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </div>
  );
}

const COMPANION_WINDOWS: [CompanionWindow, string][] = [
  ["24h", "24 hours"], ["7d", "7 days"], ["1m", "1 month"], ["3m", "3 months"], ["6m", "6 months"], ["12m", "12 months"], ["all", "All time"],
];

function Companions({ userId }: { userId: string }) {
  const [window, setWindow] = useState<CompanionWindow>("all");
  const c = useApi(() => getCompanions(userId, window), `${userId}|${window}`);
  if (!c.data) return null;
  return (
    <>
      <div className="section-head">
        <h2>Teammates and opponents</h2>
        <label>
          Time frame
          <select value={window} onChange={(e) => setWindow(e.target.value as CompanionWindow)}>
            {COMPANION_WINDOWS.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
          </select>
        </label>
      </div>
      <div className="two-col">
        <CompanionTable title="Most played with" rows={c.data.teammates} together />
        <CompanionTable title="Most played against" rows={c.data.opponents} together={false} />
      </div>
    </>
  );
}

function PlayerHeatmap({ userId, period, maps }: { userId: string; period: Period; maps: Record<string, number> }) {
  const [params, setParams] = useSearchParams();
  const played = MAPS.filter((m) => maps[m]).sort((a, b) => (maps[b] ?? 0) - (maps[a] ?? 0));
  const map = played.includes(params.get("hm_map") ?? "") ? params.get("hm_map")! : played[0] ?? "dyson";
  const mode = (params.get("hm_mode") as HeatmapLayerMode | "deaths") || "team";
  const last = Number(params.get("hm_last") ?? 200);
  const cell = HEATMAP_CELL_M;
  const h = useApi(() => getPlayerHeatmapBy(userId, map, mode, period, last, cell), `${userId}|${map}|${mode}|${period}|${last}|${cell}`);
  function set(key: string, value: string, fallback: string) {
    const next = new URLSearchParams(params);
    if (value && value !== fallback) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }
  if (played.length === 0) return null;
  const filters = (
    <>
        <label>
          Map
          <select value={map} onChange={(e) => set("hm_map", e.target.value, played[0])}>
            {played.map((m) => <option key={m} value={m}>{title(m)} ({maps[m]})</option>)}
          </select>
        </label>
        <label>
          Colour by
          <select value={mode} onChange={(e) => set("hm_mode", e.target.value, "team")}>
            {HEATMAP_MODES.map(([v, label]) => <option key={v} value={v}>{label}</option>)}
            <option value="deaths">Deaths (est.)</option>
          </select>
        </label>
        <label>
          Matches
          <select value={last} onChange={(e) => set("hm_last", e.target.value, "200")}>
            {[20, 50, 200, 1000, 5000].map((n) => <option key={n} value={n}>{n === 5000 ? "All" : `Last ${n}`}</option>)}
          </select>
        </label>
    </>
  );
  return (
    <>
      <h2>Heatmap</h2>
      <div className="filters">{filters}</div>
      {h.loading && <Skeleton lines={5} />}
      <Status loading={false} error={h.error} />
      {h.data && (
        <HeatmapView
          heatmap={h.data}
          controls={filters}
          caption={`${int(h.data.matches)} match${h.data.matches === 1 ? "" : "es"}.`}
          view3d={mode === "deaths" ? undefined : { key: `h3|${userId}|${map}|${mode}|${period}|${last}`, load: () => getPlayerHeatmap3d(userId, map, mode, period, last) }}
        />
      )}
    </>
  );
}

type PlayerTab = "overview" | "combat" | "achievements" | "gear" | "trends" | "companions" | "heatmap";
const PLAYER_TABS: [PlayerTab, string, string][] = [
  ["overview", "Overview", "Recent matches"],
  ["combat", "Recorder stats", "Separate data: kills, damage"],
  ["achievements", "Achievements", "Medals and progress"],
  ["gear", "Loadouts & gear use", "What they play with"],
  ["trends", "Trends", "How they change over time"],
  ["companions", "Played with", "Teammates and opponents"],
  ["heatmap", "Heatmap", "Where they spend the match"],
];

/** Which parts of the page the period / map filter changes, for the line under it (it used to look like it set every tab). */
function filterScope(tab: PlayerTab): string {
  const base = "The period and map apply to the stats below";
  switch (tab) {
    case "overview": return `${base} and the recent matches.`;
    case "combat": return `${base} and the combat stats in this tab.`;
    case "gear": return `${base} and the loadouts in this tab.`;
    case "heatmap": return `${base}. The heatmap follows the period; choose its map in the heatmap itself.`;
    case "trends": return `${base} only. Trends always cover all time, by week, month or year.`;
    case "companions": return `${base} only. Played with has its own time window.`;
    case "achievements": return `${base} only. Achievements always count all time.`;
  }
}

function PlayerNotFound() {
  usePageTitle("Player not found");
  return (
    <NotFoundBox heading="Player not found" links={[["/players", "All players"], ["/", "Home"]]}>
      This player is not in the archive (yet), or the link is wrong.
    </NotFoundBox>
  );
}

export function PlayerPage() {
  const { userId = "", name: nameInUrl = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "";
  const profile = useApi(() => getPlayer(userId, period, map || undefined), `${userId}|${period}|${map}`);
  const p = profile.data;
  // the same answer the Trends section asks for (shared, cached): the lines under the cards
  const months = useApi(() => getTrends(userId, "month"), `${userId}|month`);

  const hasGames = (p?.stats.games ?? 0) > 0;
  // the combat tab only exists when there is combat data for this player (the same cached request the tab itself makes)
  const combat = useApi(() => getCombatPlayer(userId, period, map || undefined), `combat|${userId}|${period}|${map}`);
  const hasCombat = !!combat.data?.matches && !!combat.data.stats;
  // the header's "From the game" line is all time: the same cached request as the tab when no filter is set
  const combatAll = useApi(() => getCombatPlayer(userId, "all"), `combat|${userId}|all|`);
  const tabs = PLAYER_TABS.filter(([t]) => (t !== "combat" || hasCombat) && (hasGames || t === "overview" || t === "achievements" || t === "combat"));
  const asked = params.get("tab") === "beta" ? "combat" : params.get("tab"); // ?tab=beta: older links to this tab
  const tab = tabs.some(([t]) => t === asked) ? (asked as PlayerTab) : "overview";
  const tabStrip = useActiveTabInView(`${tab}|${tabs.length}|${!!p}`);
  const setTab = (t: PlayerTab) => {
    const next = new URLSearchParams(params);
    if (t === "overview") next.delete("tab");
    else next.set("tab", t);
    setParams(next, { replace: true });
  };

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value && !(key === "period" && value === "all")) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  // show the player's own address, /players/<name>/<id>: old links without the name, an outdated name and a merged ID
  // (answers with its main player) all keep working and move to it
  if (p && (p.user_id !== userId || nameInUrl !== nameSlug(p.name))) {
    const search = params.toString();
    return <Navigate replace to={`${playerPath(p.user_id, p.name)}${search ? `?${search}` : ""}`} />;
  }

  return (
    <section>
      {profile.loading && !p && <Skeleton cards={8} lines={2} />}
      {isNotFound(profile.error) ? <PlayerNotFound /> : <Status loading={false} error={profile.error} />}
      {p && (
        <>
          <ProfileHeader p={p} combat={combatAll.data} onOpenCombat={() => setTab("combat")} />

          {tab !== "achievements" && <AchievementsStrip userId={p.user_id} onOpen={() => setTab("achievements")} />}

          <div className="filters">
            <div className="tabs" role="tablist">
              {PERIODS.map(([value, label]) => (
                <button key={value} role="tab" aria-selected={period === value} className={period === value ? "tab active" : "tab"} onClick={() => set("period", value)}>
                  {label}
                </button>
              ))}
            </div>
            <label>
              Map
              <select value={map} onChange={(e) => set("map", e.target.value)}>
                <option value="">All</option>
                {MAPS.map((m) => <option key={m} value={m}>{title(m)}</option>)}
              </select>
            </label>
          </div>
          <p className="muted footnote filter-scope">{filterScope(tab)}</p>

          {p.stats.games === 0 ? (
            <p className="muted">No matches in this period.</p>
          ) : (
            <>
              <ProfileCards rows={cards(p.stats, p.site_avg, months.data?.items)} />
            </>
          )}

          <div className="tabs section-tabs" role="tablist" aria-label="Player views" ref={tabStrip}>
            {tabs.map(([t, label, hint]) => (
              <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "tab active" : "tab"} onClick={() => setTab(t)}>
                <span className="tab-label">{label}</span>
                <span className="tab-hint">{hint}</span>
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <>
              <h2>Recent matches</h2>
              <MatchTable
                matches={p.recent_matches}
                extra={(m) => {
                  const pm = p.recent_matches.find((x) => x.id === m.id)!;
                  return (
                    <span className="nowrap">
                      <TeamBadge team={pm.team} /> {pm.result && <span className={`result ${pm.result}`}>{pm.result}</span>}
                    </span>
                  );
                }}
              />
              {p.recent_matches.length >= 20 && (
                <p>
                  <Link to={`/matches?player=${p.user_id}`}>All matches with {p.name}</Link>
                </p>
              )}
            </>
          )}

          {tab === "combat" && <CombatSection userId={p.user_id} period={period} map={map} />}

          {/* achievements do not follow the period filter */}
          {tab === "achievements" && <AchievementsSummary userId={p.user_id} />}

          {tab === "gear" && p.stats.games > 0 && (
            <>
              <h2>Loadouts</h2>
              <TableWrap>
                <table className="stack loadouts">
                  <thead>
                    <tr><th className="num">#</th><th>Weapon</th><th>Ordnance</th><th>Tac mod</th><th>Time used</th></tr>
                  </thead>
                  <tbody>
                    {p.loadouts.slice(0, 10).map((lo, i) => {
                      const top = p.loadouts[0]?.share || 1;
                      return (
                        <tr key={`${lo.weapon.code}|${lo.ordnance.code}|${lo.tacmod.code}`}>
                          <td data-label="#" className="num rank">{i + 1}</td>
                          <td data-label="Weapon"><GearName item={lo.weapon} /></td>
                          <td data-label="Ordnance"><GearName item={lo.ordnance} /></td>
                          <td data-label="Tac mod"><GearName item={lo.tacmod} /></td>
                          <td data-label="Time used">
                            <span className="share-cell">
                              <span className="share-track"><span className="share-fill" style={{ width: `${Math.max(2, ((lo.share ?? 0) / top) * 100)}%` }} /></span>
                              <span className="share-pct">{pct(lo.share)}</span>
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </TableWrap>
              {p.gear && <GearUseSection gear={p.gear} />}
            </>
          )}

          {tab === "trends" && <Trends userId={p.user_id} />}
          {tab === "companions" && <Companions userId={p.user_id} />}
          {tab === "heatmap" && p.stats.games > 0 && <PlayerHeatmap userId={p.user_id} period={period} maps={p.stats.games_by_map} />}
        </>
      )}
    </section>
  );
}
