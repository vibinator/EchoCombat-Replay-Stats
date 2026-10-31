import { useState } from "react";
import { Link, Navigate, useParams, useSearchParams } from "react-router";
import {
  getCompanions, getPlayer, getPlayerHeatmapBy, getTrends,
  type Companion, type CompanionWindow, type GearUse, type GearUseSet, type HeatmapLayerMode, type Period, type PlayerProfile, type PlayerStats,
} from "../api";
import { AchievementsSummary } from "../components/AchievementsView";
import { LineChart } from "../components/charts";
import { GearName, MatchTable, Status, TableWrap, TeamBadge } from "../components/common";
import { CELL_SIZES, HEATMAP_MODES, HeatmapView } from "../components/HeatmapView";
import { InfoTip, Skeleton } from "../components/ui";
import { MAPS, dateTime, duration, num, pct, periodLabel, title } from "../format";
import { useApi } from "../useApi";

const PERIODS: [Period, string][] = [
  ["day", "Today"],
  ["week", "This week"],
  ["month", "This month"],
  ["all", "All time"],
];

function cards(s: PlayerStats): [string, string, string?][] {
  const list: [string, string, string?][] = [
    ["Games", String(s.games)],
    ["Wins – losses", `${s.wins} – ${s.losses}`, "Matches without a known winner are not counted"],
    ["Hours played", num(s.hours_played)],
    ["Deaths*", String(s.deaths_est), "Estimated from leaving the map bounds"],
    ["Deaths / game*", num(s.deaths_per_game_est, 2)],
    ["Average speed", `${num(s.avg_speed, 2)} m/s`],
    ["Top speed", `${num(s.top_speed)} m/s`, "Fastest speed held for a full second"],
    ["Time idle", pct(s.pct_stopped), "Moving slower than 1 m/s"],
    ["Inverted", pct(s.pct_upside_down)],
    ["Near a teammate", pct(s.pct_near_mate)],
    ["Near an enemy", pct(s.pct_near_enemy)],
    ["Average ping", num(s.avg_ping, 0)],
    ["Packet loss", s.avg_packet_loss == null ? "–" : `${(s.avg_packet_loss * 100).toFixed(2)}%`],
    ["Emotes", String(s.emote_count)],
    ["Left early", pct(s.pct_left_early), "Last seen more than 45 s before the end"],
    ["Arm", s.dominant_arm ? `${s.dominant_arm} (${pct(s.dominant_arm === "Left" ? s.pct_left_arm : 1 - (s.pct_left_arm ?? 0))})` : "–"],
  ];
  if (s.games_by_mode.payload) {
    list.push(["Payload push*", duration(s.payload_push_s), "Estimated: within 3 m of the payload"]);
    list.push(["Payload block*", duration(s.payload_block_s), "Estimated: within 3 m of the payload"]);
  }
  return list;
}

function ProfileHeader({ p }: { p: PlayerProfile }) {
  const main = p.loadouts[0];
  const favourite = Object.entries(p.stats.games_by_map).sort((a, b) => b[1] - a[1])[0];
  const form = p.recent_matches.slice(0, 10);
  return (
    <div className="profile-header">
      <div>
        <h1>
          {p.name}
        </h1>
        <p className="muted">
          {p.level != null && `Level ${p.level} · `}First seen {dateTime(p.first_seen_at).slice(0, 10)} · last seen {dateTime(p.last_seen_at).slice(0, 10)}
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
  return (
    <TableWrap>
      <table className="stack">
        <thead>
          <tr><th>{heading}</th><th className="num">Picked</th><th className="num">Games</th><th className="num">Time held</th></tr>
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
              <td data-label="Time held" className="num">{pct(g.share)}</td>
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
          <LineChart title="Win rate" data={items.map((i) => ({ label: i.period, value: i.win_rate }))} format={(v) => pct(v)} min={0} />
          <LineChart title="Average speed (m/s)" data={items.map((i) => ({ label: i.period, value: i.avg_speed }))} format={(v) => num(v)} />
          <LineChart title="Deaths per game (est.)" data={items.map((i) => ({ label: i.period, value: i.deaths_per_game_est }))} format={(v) => num(v)} color="var(--chart-2)" />
          <LineChart title="Average ping" data={items.map((i) => ({ label: i.period, value: i.avg_ping }))} format={(v) => num(v, 0)} color="var(--chart-2)" />
          <LineChart title="Games" data={items.map((i) => ({ label: i.period, value: i.games }))} min={0} />
        </div>
      )}
    </>
  );
}

function CompanionTable({ title: heading, rows, together }: { title: string; rows: Companion[]; together: boolean }) {
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
                <th className="num">Games</th>
                <th className="num">{together ? "Won together" : "Won against"}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.user_id}>
                  <td data-label="Player"><Link to={`/players/${c.user_id}`}>{c.name}</Link></td>
                  <td data-label="Games" className="num">{c.games}</td>
                  <td data-label={together ? "Won together" : "Won against"} className="num">
                    {c.wins} – {c.losses}
                  </td>
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
  const cell = Number(params.get("hm_cell") ?? 0.25);
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
      {h.data && <HeatmapView heatmap={h.data} caption={`${h.data.matches} match${h.data.matches === 1 ? "" : "es"}.`} />}
    </>
  );
}

export function PlayerPage() {
  const userId = useParams().userId ?? "";
  const [params, setParams] = useSearchParams();
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "";
  const profile = useApi(() => getPlayer(userId, period, map || undefined), `${userId}|${period}|${map}`);
  const p = profile.data;

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value && !(key === "period" && value === "all")) next.set(key, value);
    else next.delete(key);
    setParams(next);
  }

  // a merged ID answers with its main player: show that player's own address (old links keep working)
  if (p && p.user_id !== userId) {
    const search = params.toString();
    return <Navigate replace to={`/players/${encodeURIComponent(p.user_id)}${search ? `?${search}` : ""}`} />;
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
                {cards(p.stats).map(([label, value, hint]) => (
                  <div className="card" key={label}>
                    <span className="label">
                      {label}
                      <InfoTip text={hint} />
                    </span>
                    <strong>{value}</strong>
                  </div>
                ))}
              </div>
              <p className="muted footnote">
                Games per map: {Object.entries(p.stats.games_by_map).map(([m, n]) => `${title(m)} ${n}`).join(" · ")}. * Estimated.
              </p>

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

          <Trends userId={p.user_id} />
          <Companions userId={p.user_id} />
          {p.stats.games > 0 && <PlayerHeatmap userId={p.user_id} period={period} maps={p.stats.games_by_map} />}
          <AchievementsSummary userId={p.user_id} />

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
