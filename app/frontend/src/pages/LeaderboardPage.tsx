import { useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { CombatBoard } from "./CombatPage";
import {
  getGear, getLeaderboard, getLeaderboardOverview, getLeaderboardRecords, getLeaderboardStats,
  type LeaderboardRecords, type LeaderboardRow, type Period, type StatOption,
} from "../api";
import { ShareBar } from "../components/bars";
import { Status, TableWrap } from "../components/common";
import { EmptyState, FitText, Skeleton } from "../components/ui";
import { Avatar, useAvatars } from "../components/Avatar";
import { COMPARE_MAX, compareTabPath } from "../components/CompareView";
import { MAPS, MAP_MODE, dateTime, duration, int, num, pct, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const PAGE_SIZE = 50;
const PERIODS: [Period, string][] = [
  ["day", "Today"],
  ["week", "This week"],
  ["month", "This month"],
  ["all", "All time"],
];
const MODES: [string, string][] = [
  ["", "All"],
  ["capture_point", "Capture point"],
  ["payload", "Payload"],
];
/** Board-only parameters: dropped when switching to the stat cards or the records, so a shared link stays short. */
const BOARD_KEYS = ["stat", "sort", "offset", "weapon", "ordnance", "tacmod", "view"];

function formatValue(stat: string, value: number): string {
  if (stat.startsWith("pct_") || stat === "win_rate" || stat === "achievements") return pct(value);
  if (stat.startsWith("payload_push") || stat.startsWith("payload_block")) return duration(value);
  if (stat === "avg_speed" || stat === "top_speed") return `${num(value)} m/s`;
  if (stat === "distance_km" || stat === "distance_per_game") return `${num(value, stat === "distance_km" ? 1 : 2)} km`;
  if (stat === "avg_ping") return num(value, 0);
  if (stat === "deaths_per_game_est" || stat === "emotes_per_game") return num(value, 2);
  if (stat === "hours_played" || stat === "loadout") return `${num(value, stat === "loadout" ? 2 : 1)} h`;
  return value.toLocaleString();
}

function formatRecord(unit: LeaderboardRecords["records"][number]["unit"], value: number): string {
  if (unit === "speed") return `${num(value, 2)} m/s`;
  if (unit === "metres") return value >= 1000 ? `${num(value / 1000, 2)} km` : `${int(value)} m`;
  if (unit === "seconds") return duration(value);
  if (unit === "share") return pct(value);
  return int(value);
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

/** The stat groups in the order the server lists them (stats are already sorted by group there). */
function groupsOf(stats: StatOption[]): [string, StatOption[]][] {
  const groups = new Map<string, StatOption[]>();
  for (const s of stats) {
    const g = s.group ?? "Other";
    groups.set(g, [...(groups.get(g) ?? []), s]);
  }
  return [...groups];
}

type View = "overview" | "board" | "records";

/** Leaderboard navigation (C2, user 2026-11-16): the stat groups as chips, then the group's stats as chips, instead of
 *  one long dropdown. "All stats" (the stat cards) and "Records" sit at either end. */
function StatNav({ view, stat, stats, go }: { view: View; stat: string; stats: StatOption[]; go: (view: View, stat?: string) => void }) {
  const groups = groupsOf(stats);
  const current = stats.find((s) => s.key === stat)?.group;
  const inGroup = groups.find(([g]) => g === current)?.[1] ?? [];
  return (
    <nav className="lb-nav" aria-label="Leaderboard stats">
      <div className="lb-chips" role="tablist" aria-label="Stat groups">
        <button type="button" role="tab" aria-selected={view === "overview"} className={view === "overview" ? "lb-chip active" : "lb-chip"} onClick={() => go("overview")}>
          All stats
        </button>
        {groups.map(([g, items]) => (
          <button key={g} type="button" role="tab" aria-selected={view === "board" && g === current}
            className={view === "board" && g === current ? "lb-chip active" : "lb-chip"} onClick={() => go("board", items[0].key)}>
            {g}
          </button>
        ))}
        <button type="button" role="tab" aria-selected={view === "records"} className={view === "records" ? "lb-chip active" : "lb-chip"} onClick={() => go("records")}>
          Records
        </button>
      </div>
      {view === "board" && inGroup.length > 1 && (
        <div className="lb-chips lb-subchips" role="tablist" aria-label={`${current} stats`}>
          {inGroup.map((s) => (
            <button key={s.key} type="button" role="tab" aria-selected={s.key === stat} className={s.key === stat ? "lb-chip sub active" : "lb-chip sub"} onClick={() => go("board", s.key)}>
              {s.label}
            </button>
          ))}
        </div>
      )}
    </nav>
  );
}

interface CardRow {
  key: string;
  rank: number;
  userId: string;
  name: string;
  value: ReactNode;
  sub?: ReactNode;
}

/** One stat's top players (B4) or one record's best matches (B2); #1 gets the bigger picture and the gold rank. */
function StatCard({ heading, hint, rows, more, empty, avatars }: {
  heading: string; hint?: string; rows: CardRow[]; more?: string; empty: string; avatars: Record<string, string>;
}) {
  return (
    <article className="lb-card">
      <h3 title={hint || undefined}>{more ? <Link to={more}>{heading}</Link> : heading}</h3>
      {rows.length === 0 ? (
        <p className="muted lb-card-empty">{empty}</p>
      ) : (
        <ol className="lb-card-list">
          {rows.map((r) => (
            <li key={r.key} className={`place-${r.rank}`}>
              <span className="lb-card-rank">{r.rank}</span>
              <Avatar name={r.name} url={avatars[r.userId]} size={r.rank === 1 ? 32 : 22} />
              <span className="lb-card-who">
                <Link to={playerPath(r.userId, r.name)}><FitText title={r.name}>{r.name}</FitText></Link>
                {r.sub && <span className="muted lb-card-sub">{r.sub}</span>}
              </span>
              <span className="lb-card-value">{r.value}</span>
            </li>
          ))}
        </ol>
      )}
      {more && rows.length > 0 && <Link className="lb-card-more" to={more}>Full board →</Link>}
    </article>
  );
}

function Overview({ period, map, mode, minGames, boardLink }: { period: Period; map: string; mode: string; minGames: number; boardLink: (stat: string) => string }) {
  const overview = useApi(() => getLeaderboardOverview({ period, map: map || undefined, mode: mode || undefined, min_games: minGames }),
    `lb-overview|${period}|${map}|${mode}|${minGames}`);
  const avatars = useAvatars(overview.data?.boards.flatMap((b) => b.items.map((r) => r.user_id)) ?? []);
  if (overview.loading && !overview.data) return <Skeleton cards={8} />;
  if (!overview.data) return <Status loading={false} error={overview.error} />;
  const groups = new Map<string, typeof overview.data.boards>();
  for (const b of overview.data.boards) groups.set(b.group, [...(groups.get(b.group) ?? []), b]);
  return (
    <>
      <div className="lb-groups">
      {[...groups].map(([group, boards]) => (
        // a group of n cards asks for about n card widths and takes its share of the spare room by n too, so cards are
        // the same width across the groups of a row and every row ends at the page's right edge (a 420 px cap per card
        // left the three-card rows short of it, 2026-11-16)
        <section key={group} className="lb-group" style={{ flexBasis: boards.length * 260, flexGrow: boards.length, maxWidth: boards.length * 600 }}>
          <h2 className="lb-group-title">{group}</h2>
          <div className="lb-cards">
            {boards.map((b) => (
              <StatCard key={b.stat} heading={b.label} hint={b.hint} more={boardLink(b.stat)} avatars={avatars}
                empty={`No one with ${minGames}+ games yet`}
                rows={b.items.map((r) => ({ key: r.user_id, rank: r.rank, userId: r.user_id, name: r.name, value: formatValue(b.stat, r.value) }))} />
            ))}
          </div>
        </section>
      ))}
      </div>
      <p className="muted footnote">
        The top 5 of every stat for players with {minGames}+ games in this selection; open a card for the full board.
        Averages and rates count games of 2+ minutes with 2+ players per team; totals count everything.
      </p>
    </>
  );
}

function Records({ period, map, mode }: { period: Period; map: string; mode: string }) {
  const records = useApi(() => getLeaderboardRecords({ period, map: map || undefined, mode: mode || undefined }), `lb-records|${period}|${map}|${mode}`);
  const avatars = useAvatars(records.data?.records.flatMap((r) => r.items.map((i) => i.user_id)) ?? []);
  if (records.loading && !records.data) return <Skeleton cards={6} />;
  if (!records.data) return <Status loading={false} error={records.error} />;
  return (
    <>
      <div className="lb-cards wide">
        {records.data.records.map((rec) => (
          <StatCard key={rec.key} heading={rec.label} avatars={avatars} empty="No matches in this selection"
            rows={rec.items.map((i) => ({
              key: `${i.user_id}-${i.match_id}`, rank: i.rank, userId: i.user_id, name: i.name,
              value: <Link to={`/matches/${i.match_id}`} title="Open the match">{formatRecord(rec.unit, i.value)}</Link>,
              sub: `${title(i.map)} · ${dateTime(i.started_at)}`,
            }))} />
        ))}
      </div>
      <p className="muted footnote">
        Best single matches, each player&apos;s best one only; click a value to open the match. Counts games of 2+ minutes with
        2+ players per team; average speed and time inverted also need a minute in the play area.
      </p>
    </>
  );
}

function ReplayBoard() {
  const [params, setParams] = useSearchParams();
  const view: View = params.get("view") === "records" ? "records" : params.get("stat") ? "board" : "overview";
  const stat = params.get("stat") ?? "games";
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "";
  const mode = params.get("mode") ?? "";
  const minGames = Number(params.get("min_games") ?? 10);
  const stats = useApi(getLeaderboardStats, "stats");
  // players ticked for "Compare selected" (user, 2026-11-16: the Compare page moved to the player profile). Kept while
  // the stat, filters, view or page change, so players can be picked from different boards; the first ticked opens it.
  const [picked, setPicked] = useState<Pick[]>([]);

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    if (key === "stat") next.delete("sort");
    if (key === "mode" && value && map && MAP_MODE[map] !== value) next.delete("map"); // the map is not played in that mode
    setParams(next);
  }

  function go(to: View, toStat?: string) {
    const next = new URLSearchParams(params);
    for (const k of BOARD_KEYS) next.delete(k);
    if (to === "records") next.set("view", "records");
    if (to === "board" && toStat) next.set("stat", toStat);
    setParams(next);
  }

  /** Link to one stat's full board with the current period, mode, map and minimum. */
  function boardLink(s: string): string {
    const next = new URLSearchParams(params);
    for (const k of BOARD_KEYS) next.delete(k);
    next.set("stat", s);
    return `?${next.toString()}`;
  }

  return (
    <section>
      <StatNav view={view} stat={stat} stats={stats.data ?? []} go={go} />
      <div className="filters">
        <div className="tabs" role="tablist" aria-label="Period">
          {PERIODS.map(([value, label]) => (
            <button key={value} role="tab" aria-selected={period === value} className={period === value ? "tab active" : "tab"} onClick={() => set("period", value === "all" ? "" : value)}>
              {label}
            </button>
          ))}
        </div>
        <label>
          Mode
          <select value={mode} onChange={(e) => set("mode", e.target.value)}>
            {MODES.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Map
          <select value={map} onChange={(e) => set("map", e.target.value)}>
            <option value="">All</option>
            {MAPS.filter((m) => !mode || MAP_MODE[m] === mode).map((m) => (
              <option key={m} value={m}>
                {title(m)}
              </option>
            ))}
          </select>
        </label>
        {view !== "records" && (
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
        )}
      </div>
      {view === "overview" && <Overview period={period} map={map} mode={mode} minGames={minGames} boardLink={boardLink} />}
      {view === "records" && <Records period={period} map={map} mode={mode} />}
      {view === "board" && <StatBoard stat={stat} period={period} map={map} mode={mode} minGames={minGames} stats={stats.data ?? []} set={set} picked={picked} setPicked={setPicked} />}
    </section>
  );
}

type Pick = { user_id: string; name: string };

function StatBoard({ stat, period, map, mode, minGames, stats, set, picked, setPicked }: {
  stat: string; period: Period; map: string; mode: string; minGames: number; stats: StatOption[]; set: (key: string, value: string) => void;
  picked: Pick[]; setPicked: React.Dispatch<React.SetStateAction<Pick[]>>;
}) {
  const [params] = useSearchParams();
  const offset = Number(params.get("offset") ?? 0);
  const weapon = params.get("weapon") ?? "";
  const ordnance = params.get("ordnance") ?? "";
  const tacmod = params.get("tacmod") ?? "";
  const sortParam = params.get("sort") ?? "";
  const sort = sortParam && sortParam !== stat ? sortParam : "";

  const gear = useApi(getGear, "gear");
  const board = useApi(
    () =>
      getLeaderboard({
        stat, period, map: map || undefined, mode: mode || undefined, min_games: minGames, offset, limit: PAGE_SIZE,
        weapon: weapon || undefined, ordnance: ordnance || undefined, tacmod: tacmod || undefined,
        compare: stat !== "achievements",
        sort: sort || undefined,
      }),
    params.toString(),
  );

  const avatars = useAvatars(board.data?.items.map((r) => r.user_id) ?? []);
  const navigate = useNavigate();
  const isPicked = (id: string) => picked.some((x) => x.user_id === id);
  function togglePick(r: LeaderboardRow) {
    setPicked((now) => (now.some((x) => x.user_id === r.user_id) ? now.filter((x) => x.user_id !== r.user_id) : now.length < COMPARE_MAX ? [...now, { user_id: r.user_id, name: r.name }] : now));
  }
  function openCompare() {
    navigate(compareTabPath(playerPath(picked[0].user_id, picked[0].name), picked.map((x) => x.user_id), period));
  }
  const hint = stats.find((s) => s.key === stat)?.hint;

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
    <>
      {hint && <p className="muted footnote lb-hint">{hint}</p>}
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
                  const shown = sort ? (r[sort as keyof LeaderboardRow] as number | null) : r.value;
                  return (
                    <Link key={r.user_id} to={playerPath(r.user_id, r.name)} className={`podium-step place-${r.rank}`}>
                      <span className="podium-medal" aria-label={`Rank ${r.rank}`}>{r.rank}</span>
                      <Avatar name={r.name} url={avatars[r.user_id]} size={r.rank === 1 ? 64 : 52} />
                      <strong className="podium-name"><FitText title={r.name}>{r.name}</FitText></strong>
                      <span className="podium-value">{shown == null ? "–" : formatValue(sort || stat, shown)}</span>
                      <span className="podium-label">{sort ? sortLabel?.toLowerCase() : board.data!.label.toLowerCase()}</span>
                      <span className="muted podium-context">{podiumLine(stat, r)}</span>
                    </Link>
                  );
                })}
              </div>
            )}
            <div className="compare-pick" role="status">
              {picked.length === 0 ? (
                <span className="muted">Tick up to {COMPARE_MAX} players to compare them side by side.</span>
              ) : (
                <>
                  <span>
                    {picked.length < 2 ? "Tick one more player to compare: " : "Compare "}
                    {picked.map((x) => x.name).join(", ")}
                  </span>
                  <button type="button" disabled={picked.length < 2} onClick={openCompare}>Compare selected</button>
                  <button type="button" className="link" onClick={() => setPicked([])}>Clear</button>
                </>
              )}
            </div>
            <TableWrap>
              <table className="stack board">{/* board: on a phone one line per player, tap it for the other columns (Review GUI-5) */}
                <thead>
                  <tr>
                    <th className="pick"><span className="sr-only">Compare</span></th>
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
                      <td data-label="Compare" className="pick keep" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          aria-label={`Compare ${r.name}`}
                          checked={isPicked(r.user_id)}
                          disabled={!isPicked(r.user_id) && picked.length >= COMPARE_MAX}
                          onChange={() => togglePick(r)}
                        />
                      </td>
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
              (all time: with 7 days ago). Averages, rates and win rates count games of 2+ minutes with 2+ players per team;
              games without a recorded winner count for neither side. Games and hours count everything.
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
    </>
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
