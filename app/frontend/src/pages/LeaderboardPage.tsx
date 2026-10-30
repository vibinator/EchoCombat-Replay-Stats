import { Link, useSearchParams } from "react-router";
import { getGear, getLeaderboard, getLeaderboardStats, type LeaderboardRow, type Period } from "../api";
import { Status, TableWrap } from "../components/common";
import { EmptyState, FitText, Skeleton } from "../components/ui";
import { MAPS, duration, num, pct, title } from "../format";
import { useApi } from "../useApi";

const PAGE_SIZE = 50;
const PERIODS: [Period, string][] = [
  ["day", "Today"],
  ["week", "This week"],
  ["month", "This month"],
  ["all", "All time"],
];

function formatValue(stat: string, value: number): string {
  if (stat.startsWith("pct_") || stat === "win_rate" || stat === "achievements") return pct(value);
  if (stat === "payload_push_s" || stat === "payload_block_s") return duration(value);
  if (stat === "avg_speed" || stat === "top_speed") return `${num(value)} m/s`;
  if (stat === "avg_ping") return num(value, 0);
  if (stat === "deaths_per_game_est") return num(value, 2);
  if (stat === "hours_played" || stat === "loadout") return `${num(value, stat === "loadout" ? 2 : 1)} h`;
  return value.toLocaleString();
}

export function LeaderboardPage() {
  const [params, setParams] = useSearchParams();
  const stat = params.get("stat") ?? "games";
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "";
  const minGames = Number(params.get("min_games") ?? 10);
  const offset = Number(params.get("offset") ?? 0);
  const weapon = params.get("weapon") ?? "";
  const ordnance = params.get("ordnance") ?? "";
  const tacmod = params.get("tacmod") ?? "";

  const stats = useApi(getLeaderboardStats, "stats");
  const gear = useApi(getGear, "gear");
  const board = useApi(
    () =>
      getLeaderboard({
        stat, period, map: map || undefined, min_games: minGames, offset, limit: PAGE_SIZE,
        weapon: weapon || undefined, ordnance: ordnance || undefined, tacmod: tacmod || undefined,
        compare: stat !== "achievements",
      }),
    params.toString(),
  );

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  }

  const total = board.data?.total ?? 0;

  return (
    <section>
      <h1>Leaderboard</h1>
      <div className="filters">
        <label>
          Stat
          <select value={stat} onChange={(e) => set("stat", e.target.value)}>
            {(stats.data ?? []).map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <div className="tabs" role="tablist">
          {PERIODS.map(([value, label]) => (
            <button key={value} role="tab" aria-selected={period === value} className={period === value ? "tab active" : "tab"} onClick={() => set("period", value === "all" ? "" : value)}>
              {label}
            </button>
          ))}
        </div>
        <label>
          Map
          <select value={map} onChange={(e) => set("map", e.target.value)}>
            <option value="">All</option>
            {MAPS.map((m) => (
              <option key={m} value={m}>
                {title(m)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Min. games
          <select value={minGames} onChange={(e) => set("min_games", e.target.value === "10" ? "" : e.target.value)}>
            {[1, 5, 10, 25, 50, 100].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      </div>

      {stat === "loadout" && gear.data && (
        <div className="filters">
          {(
            [
              ["weapon", "Weapon", gear.data.weapons, weapon],
              ["ordnance", "Ordnance", gear.data.ordnances, ordnance],
              ["tacmod", "Tac mod", gear.data.tacmods, tacmod],
            ] as const
          ).map(([key, label, items, value]) => (
            <label key={key}>
              {label}
              <select value={value} onChange={(e) => set(key, e.target.value)}>
                <option value="">Any</option>
                {items.map((g) => (
                  <option key={g.code} value={g.code}>
                    {g.name}
                    {g.cut ? " (cut)" : ""}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}

      {board.loading && !board.data && <Skeleton lines={8} />}
      <Status loading={false} error={board.error} />
      {board.data &&
        (board.data.items.length === 0 ? (
          <EmptyState title={`No players with at least ${minGames} games in this selection`}>Try a lower minimum or a longer period.</EmptyState>
        ) : (
          <>
            {offset === 0 && board.data.items.length >= 3 && (
              <div className="podium">
                {[1, 0, 2].map((i) => {
                  const r = board.data!.items[i];
                  return (
                    <Link key={r.user_id} to={`/players/${r.user_id}`} className={`podium-step place-${r.rank}`}>
                      <span className="podium-rank">{r.rank}</span>
                      <strong><FitText title={r.name}>{r.name}</FitText></strong>
                      <span>{formatValue(stat, r.value)}</span>
                      <span className="muted">{r.games} games</span>
                    </Link>
                  );
                })}
              </div>
            )}
            <TableWrap>
              <table className="stack">
                <thead>
                  <tr>
                    <th className="num">#</th>
                    <th>Player</th>
                    <th className="num">Games</th>
                    <th className="num">{board.data.label}</th>
                  </tr>
                </thead>
                <tbody>
                  {board.data.items.map((r) => (
                    <tr key={r.user_id}>
                      <td data-label="#" className="num">
                        {r.rank} <RankChange r={r} />
                      </td>
                      <td data-label="Player">
                        <Link to={`/players/${r.user_id}`}>{r.name}</Link>
                      </td>
                      <td data-label="Games" className="num">{r.games}</td>
                      <td data-label={board.data!.label} className="num">{formatValue(stat, r.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <p className="muted footnote">
              {board.data.higher_is_better ? "Highest first" : "Lowest first"} · {total} ranked players · Arrows compare with one period earlier
              (all time: with 7 days ago).
            </p>
            {total > PAGE_SIZE && (
              <div className="pager">
                <button className="secondary" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - PAGE_SIZE)))}>
                  Previous
                </button>
                <span className="muted">
                  {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
                </span>
                <button className="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => set("offset", String(offset + PAGE_SIZE))}>
                  Next
                </button>
              </div>
            )}
          </>
        ))}
    </section>
  );
}

function RankChange({ r }: { r: LeaderboardRow }) {
  if (r.previous_rank == null) return r.rank ? <span className="rank-new" title="Not ranked in the previous period">new</span> : null;
  const delta = r.previous_rank - r.rank;
  if (delta === 0) return <span className="rank-same" title="Same rank as the previous period">=</span>;
  return (
    <span className={delta > 0 ? "rank-up" : "rank-down"} title={`Was #${r.previous_rank}`}>
      {delta > 0 ? "▲" : "▼"}
      {Math.abs(delta)}
    </span>
  );
}
