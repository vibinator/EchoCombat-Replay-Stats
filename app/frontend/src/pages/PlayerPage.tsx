import { type ReactNode, useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";
import {
  getCompanions, getPlayer, getPlayerHeatmapBy, getTrends,
  type Companion, type CompanionWindow, type GearUse, type GearUseSet, type HeatmapLayerMode, type Period, type PlayerProfile, type PlayerStats, type TrendPoint,
} from "../api";
import { AchievementsSummary } from "../components/AchievementsView";
import { ShareBar, Sparkline, SplitBar, VsAverage } from "../components/bars";
import { LineChart } from "../components/charts";
import { GearName, MatchTable, Status, TableWrap, TeamBadge } from "../components/common";
import { HEATMAP_CELL_M, HEATMAP_MODES, HeatmapView } from "../components/HeatmapView";
import { InfoTip, Skeleton, WhenVisible } from "../components/ui";
import { MAPS, dateTime, hoursMinutes, int, nameSlug, num, pct, periodLabel, playerPath, title } from "../format";
import { useApi } from "../useApi";

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

/** Games per map (all four, in the site's map colours). */
function MapBar({ games }: { games: Record<string, number> }) {
  return (
    <SplitBar parts={MAPS.map((m) => ({ label: title(m), value: games[m] ?? 0, color: `var(--map-${m})`, detail: int(games[m] ?? 0) }))} />
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

/** Per month, all time: the line under a card. */
function trend(items: TrendPoint[] | undefined, key: "games" | "avg_speed" | "deaths_per_game_est" | "avg_ping", label: string): ReactNode {
  if (!items || items.length < 2) return undefined;
  return <Sparkline values={items.map((i) => i[key])} label={`${label} per month, all time`} />;
}

function cards(s: PlayerStats, avg: Averages = {}, months?: TrendPoint[]): CardRow[] {
  const list: CardRow[] = [
    ["Games", int(s.games), "The line: games per month, all time", trend(months, "games", "Games")],
    // left out of the answer while win-loss stats are hidden from players
    ...(s.wins != null && s.losses != null
      ? ([
          ["Wins – losses", `${int(s.wins)} – ${int(s.losses)}`, "Matches without a known winner are not counted"],
          ["Win rate", s.wins + s.losses ? pct(s.wins / (s.wins + s.losses)) : "–", "Wins out of the games with a known winner"],
        ] as CardRow[])
      : []),
    ["Hours played", num(s.hours_played)],
    ["Deaths*", int(s.deaths_est), "Estimated from leaving the map bounds"],
    ["Deaths / game*", num(s.deaths_per_game_est, 2), "The line: per month, all time", trend(months, "deaths_per_game_est", "Deaths per game")],
    ["Average speed", `${num(s.avg_speed, 2)} m/s`, "The line: per month, all time", trend(months, "avg_speed", "Average speed")],
    ["Top speed", `${num(s.top_speed)} m/s`, "Fastest speed held for a full second"],
    ["Time idle", <VsAverage value={s.pct_stopped} average={avg.pct_stopped} />, "Moving slower than 1 m/s. The tick: every player's average"],
    ["Inverted", <VsAverage value={s.pct_upside_down} average={avg.pct_upside_down} />, "The tick: every player's average"],
    ["Near a teammate", <VsAverage value={s.pct_near_mate} average={avg.pct_near_mate} />, "The tick: every player's average"],
    ["Near an enemy", <VsAverage value={s.pct_near_enemy} average={avg.pct_near_enemy} />, "The tick: every player's average"],
    ["Average ping", num(s.avg_ping, 0), "The line: per month, all time", trend(months, "avg_ping", "Average ping")],
    ["Packet loss", s.avg_packet_loss == null ? "–" : `${(s.avg_packet_loss * 100).toFixed(2)}%`],
    ["Emotes", int(s.emote_count)],
    ["Left early", <VsAverage value={s.pct_left_early} average={avg.pct_left_early} />, "Last seen more than 45 s before the end. The tick: every player's average"],
    ["Arm", <ArmBar left={s.pct_left_arm} />, "Share of play time with the in-game dominant arm set to right / left"],
  ];
  if (s.games) list.push(["Modes", <ModeBar games={s.games_by_mode} />]);
  if (s.games_by_mode.payload) {
    list.push(["Payload push / block*", <PayloadBar push={s.payload_push_s} block={s.payload_block_s} />,
      "Estimated: within 3 m of the payload, attacking (push) or defending (block)"]);
  }
  return list;
}

function ProfileHeader({ p }: { p: PlayerProfile }) {
  const main = p.loadouts[0];
  const favourite = Object.entries(p.stats.games_by_map).sort((a, b) => b[1] - a[1])[0];
  // no `result` while win-loss stats are hidden from players: no form strip then
  const form = p.recent_matches.slice(0, 10).filter((m) => m.result !== undefined);
  return (
    <div className="profile-header">
      <div>
        <h1>
          {p.name}
        </h1>
        <p className="muted">
          {p.level != null && `Level ${p.level} · `}First seen {dateTime(p.first_seen_at).slice(0, 10)} · Last seen {dateTime(p.last_seen_at).slice(0, 10)}
          {p.merged_ids.length > 0 && ` · merged with ${p.merged_ids.length} other ID${p.merged_ids.length > 1 ? "s" : ""}`}
        </p>
        <div className="profile-facts">
          {main && (
            <span>
              Main loadout: <GearName item={main.weapon} /> · <GearName item={main.ordnance} /> · <GearName item={main.tacmod} />
            </span>
          )}
          {favourite && (
            <span>
              Favourite map: <Link to={`/matches?map=${favourite[0]}&player=${p.user_id}`}>{title(favourite[0])}</Link> ({favourite[1]} games)
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
  return (
    <>
      <h2>Heatmap</h2>
      <div className="filters">
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
        </label>      </div>
      {h.loading && <Skeleton lines={5} />}
      <Status loading={false} error={h.error} />
      {h.data && <HeatmapView heatmap={h.data} caption={`${int(h.data.matches)} match${h.data.matches === 1 ? "" : "es"}.`} />}
    </>
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
      <Status loading={false} error={profile.error} />
      {p && (
        <>
          <ProfileHeader p={p} />

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

          {p.stats.games === 0 ? (
            <p className="muted">No matches in this period.</p>
          ) : (
            <>
              <div className="cards">
                {cards(p.stats, p.site_avg, months.data?.items).map(([label, value, hint, under]) => (
                  <div className="card" key={label}>
                    <span className="label">
                      {label}
                      <InfoTip text={hint} />
                    </span>
                    {typeof value === "string" ? <strong>{value}</strong> : value}
                    {under}
                  </div>
                ))}
                {p.stats.games > 0 && (
                  <div className="card wide">
                    <span className="label">Games per map</span>
                    <MapBar games={p.stats.games_by_map} />
                  </div>
                )}
              </div>
              <p className="muted footnote">* Estimated.</p>

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

          {/* further down: asked for only when scrolled near (the heatmap is the heaviest request on the site) */}
          <WhenVisible><Trends userId={p.user_id} /></WhenVisible>
          <WhenVisible><Companions userId={p.user_id} /></WhenVisible>
          {p.stats.games > 0 && (
            <WhenVisible minHeight={400}><PlayerHeatmap userId={p.user_id} period={period} maps={p.stats.games_by_map} /></WhenVisible>
          )}
          <WhenVisible><AchievementsSummary userId={p.user_id} /></WhenVisible>

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
    </section>
  );
}
