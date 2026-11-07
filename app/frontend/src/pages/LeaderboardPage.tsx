import { Link, useSearchParams } from "react-router";
import { CombatBoard } from "./CombatPage";
import { getGear, getLeaderboard, getLeaderboardStats, type LeaderboardRow, type Period } from "../api";
import { ShareBar } from "../components/bars";
import { Status, TableWrap } from "../components/common";
import { EmptyState, FitText, Skeleton } from "../components/ui";
import { Avatar, useAvatars } from "../components/Avatar";
import { MAPS, duration, int, num, pct, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

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

/** Context columns shown on every board; the one matching the ranked stat is left out (it is the value column). */
const SUMMARY: [keyof LeaderboardRow & string, string][] = [
  ["games", "Games"],
  ["wins", "Wins"],
  ["losses", "Losses"],
  ["win_rate", "Win rate"],
  ["hours_played", "Hours played"],
];

function podiumLine(stat: string, r: LeaderboardRow): string {
  const parts: string[] = [];
  if (stat !== "games") parts.push(`${r.games.toLocaleString()} games`);
  if (stat !== "wins" && r.wins != null) parts.push(`${r.wins.toLocaleString()} wins`);
  if (stat !== "win_rate" && r.win_rate != null) parts.push(`${pct(r.win_rate)} win rate`);
  return parts.join(" · ");
}

function ReplayBoard() {
  const [params, setParams] = useSearchParams();
  const stat = params.get("stat") ?? "games";
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "";
  const minGames = Number(params.get("min_games") ?? 10);
  const offset = Number(params.get("offset") ?? 0);
  const weapon = params.get("weapon") ?? "";
  const ordnance = params.get("ordnance") ?? "";
  const tacmod = params.get("tacmod") ?? "";
  const sortParam = params.get("sort") ?? "";
  const sort = sortParam && sortParam !== stat ? sortParam : "";

  const stats = useApi(getLeaderboardStats, "stats");
  const gear = useApi(getGear, "gear");
  const board = useApi(
    () =>
      getLeaderboard({
        stat, period, map: map || undefined, min_games: minGames, offset, limit: PAGE_SIZE,
        weapon: weapon || undefined, ordnance: ordnance || undefined, tacmod: tacmod || undefined,
        compare: stat !== "achievements",
        sort: sort || undefined,
      }),
    params.toString(),
  );

  const avatars = useAvatars(board.data?.items.map((r) => r.user_id) ?? []);

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    if (key === "stat") next.delete("sort");
    setParams(next);
  }

  const total = board.data?.total ?? 0;
  // win-loss columns are left out of the answer while they are hidden from players
  const columns = SUMMARY.filter(([key]) => key !== stat && (!board.data || board.data.items.some((r) => key in r)));
  const sortLabel = SUMMARY.find(([key]) => key === sort)?.[1];

  /** Clickable header: ranks the # column by this column; the ranked stat's own column (key "") restores the default. */
  function sortHeader(k: string, label: string, isNum = true) {
    const active = sort === k;
    return (
      <th key={k} className={isNum ? "num" : undefined} aria-sort={active ? "descending" : undefined}>
        <button type="button" className={active ? "th-sort active" : "th-sort"} onClick={() => set("sort", k)} title={`Rank by ${label}`}>
          {label}
          {active && " ▼"}
        </button>
      </th>
    );
  }

  return (
    <section>
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
                    <Link key={r.user_id} to={playerPath(r.user_id, r.name)} className={`podium-step place-${r.rank}`}>
                      <span className="podium-rank">{r.rank}</span>
                      <Avatar name={r.name} url={avatars[r.user_id]} size={44} />
                      <strong><FitText title={r.name}>{r.name}</FitText></strong>
                      <span>
                        {sort
                          ? `${(r[sort as keyof LeaderboardRow] as number | null) == null ? "–" : formatValue(sort, r[sort as keyof LeaderboardRow] as number)} ${sortLabel?.toLowerCase()}`
                          : formatValue(stat, r.value)}
                      </span>
                      <span className="muted">{podiumLine(stat, r)}</span>
                    </Link>
                  );
                })}
              </div>
            )}
            <TableWrap>
              <table className="stack board">{/* board: on a phone one line per player, tap it for the other columns (Review GUI-5) */}
                <thead>
                  <tr>
                    <th className="num">#</th>
                    <th>Player</th>
                    {columns.map(([key, label]) => sortHeader(key, label))}
                    <th aria-sort={sort ? undefined : board.data.higher_is_better ? "descending" : "ascending"}>
                      <button type="button" className={sort ? "th-sort" : "th-sort active"} onClick={() => set("sort", "")} title={`Rank by ${board.data.label}`}>
                        {board.data.label}
                        {!sort && (board.data.higher_is_better ? " ▼" : " ▲")}
                      </button>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {board.data.items.map((r) => (
                    // the class toggle only matters under 760 px (styles.css, table.board): it opens the hidden columns
                    <tr key={r.user_id} onClick={(e) => e.currentTarget.classList.toggle("open")}>
                      <td data-label="#" className="num keep rank">
                        {r.rank} <RankChange r={r} />
                      </td>
                      <td data-label="Player" className="keep">
                        <span className="who"><Avatar name={r.name} url={avatars[r.user_id]} /><Link to={playerPath(r.user_id, r.name)}>{r.name}</Link></span>
                      </td>
                      {columns.map(([key, label]) => {
                        const v = r[key] as number | null;
                        return <td key={key} data-label={label} className="num">{v == null ? "–" : formatValue(key, v)}</td>;
                      })}
                      <td data-label={board.data!.label} className="keep value">
                        <ShareBar value={r.value} max={board.data!.max_value ?? board.data!.items[0]?.value ?? 0}>{formatValue(stat, r.value)}</ShareBar>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
            <p className="muted footnote">
              {sort ? `Ranked by ${sortLabel?.toLowerCase()}, highest first` : board.data.higher_is_better ? "Highest first" : "Lowest first"} · Click a column header to re-rank ·{" "}
              {int(total)} ranked players · Arrows compare with one period earlier
              (all time: with 7 days ago).
            </p>
            {total > PAGE_SIZE && (
              <div className="pager">
                <button className="secondary" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - PAGE_SIZE)))}>
                  Previous
                </button>
                <span className="muted">
                  {int(offset + 1)}–{int(Math.min(offset + PAGE_SIZE, total))} of {int(total)}
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

/** Leaderboard with two boards (user, 2026-11-06): the replay stats and, moved here from the main menu, the Combat stats from the
 *  recorder's match reports. They are separate data sources, so the tab says so. ?board=combat opens the second one. */
export function LeaderboardPage() {
  usePageTitle("Leaderboard");
  const [params, setParams] = useSearchParams();
  const board = params.get("board") === "combat" ? "combat" : "replay";
  function pick(next: "replay" | "combat") {
    // each board has its own stat, period and map filters: start the other one clean
    setParams(next === "combat" ? { board: "combat" } : {});
  }
  return (
    <section>
      <h1>Leaderboard</h1>
      <div className="tabs section-tabs" role="tablist" aria-label="Leaderboard">
        <button role="tab" aria-selected={board === "replay"} className={board === "replay" ? "tab active" : "tab"} onClick={() => pick("replay")}>
          <span className="tab-label">Replay stats</span>
          <span className="tab-hint">from the replay files</span>
        </button>
        <button role="tab" aria-selected={board === "combat"} className={board === "combat" ? "tab active" : "tab"} onClick={() => pick("combat")}>
          <span className="tab-label">Combat stats</span>
          <span className="tab-hint">separate data: the game&apos;s own counters</span>
        </button>
      </div>
      {board === "combat" ? <CombatBoard /> : <ReplayBoard />}
    </section>
  );
}
