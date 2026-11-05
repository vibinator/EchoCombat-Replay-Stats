import { Link, useParams, useSearchParams } from "react-router";
import { getCombatBoard, getCombatMatch, getCombatStats, getCombatSummary, listCombatMatches, type CombatBoardRow, type Period } from "../api";
import { CombatMatchBody } from "../components/CombatView";
import { NotFoundBox, Status, TableWrap, isNotFound } from "../components/common";
import { Skeleton } from "../components/ui";
import { MAPS, dateTime, duration, int, num, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const PERIODS: [Period, string][] = [["day", "Today"], ["week", "This week"], ["month", "This month"], ["all", "All time"]];
const PAGE_SIZE = 25;
// stat key, heading, value. The column of the chosen stat is left out: that stat already has the bold column.
const COLUMNS: [string, string, (r: CombatBoardRow) => string][] = [
  ["matches", "Matches", (r) => int(r.matches)],
  ["kills", "Kills", (r) => int(r.kills)],
  ["deaths", "Deaths", (r) => int(r.deaths)],
  ["kd", "K/D", (r) => num(r.kd, 2)],
  ["assists", "Assists", (r) => int(r.assists)],
  ["damage", "Damage", (r) => int(r.damage)],
];

/** Combat stats: the game's own counters from the recorder's match reports. Separate from the replay-derived stats. */
export function CombatPage() {
  usePageTitle("Combat stats");
  const [params, setParams] = useSearchParams();
  const stat = params.get("stat") || "kills";
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") || "";
  const minGames = Number(params.get("min_games")) || 3;
  const offset = Number(params.get("offset")) || 0;

  const summary = useApi(getCombatSummary, "combat-summary").data;
  const stats = useApi(getCombatStats, "combat-stats");
  const board = useApi(() => getCombatBoard({ stat, period, map: map || undefined, min_games: minGames, offset, limit: PAGE_SIZE }), `combat-board|${params.toString()}`);
  const matches = useApi(() => listCombatMatches(15), "combat-matches");

  function set(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") next.delete("offset");
    setParams(next);
  }

  const total = board.data?.total ?? 0;
  const hint = stats.data?.find((s) => s.key === stat)?.hint;
  return (
    <section>
      <h1>Combat stats</h1>
      <p className="muted combat-intro">
        The game&apos;s own counters, collected from recorded matches
        {summary && summary.matches > 0 && ` (${int(summary.matches)} matches, ${int(summary.players)} players${summary.last_match_at ? `, latest ${dateTime(summary.last_match_at)}` : ""})`}.
        This is a separate source from the replay stats, so numbers can differ from the Leaderboard.
      </p>
      <div className="filters">
        <label>
          Stat
          <select value={stat} onChange={(e) => set("stat", e.target.value === "kills" ? "" : e.target.value)}>
            {(stats.data ?? []).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
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
            {MAPS.map((m) => <option key={m} value={m}>{title(m)}</option>)}
          </select>
        </label>
        <label>
          Min matches
          <select value={minGames} onChange={(e) => set("min_games", e.target.value === "3" ? "" : e.target.value)}>
            {[1, 3, 5, 10].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <p className="muted footnote combat-hint">{hint}</p>
      {board.loading && !board.data && <Skeleton lines={6} />}
      <Status loading={false} error={board.error} />
      {board.data && (board.data.items.length === 0 ? (
        <p className="muted">No players with {minGames}+ combat matches here yet.</p>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr>
                <th className="num">#</th><th>Player</th><th className="num">{board.data.label}</th>
                {COLUMNS.filter(([key]) => key !== board.data!.stat).map(([key, heading]) => <th key={key} className="num">{heading}</th>)}
              </tr>
            </thead>
            <tbody>
              {board.data.items.map((r) => (
                <tr key={r.user_id}>
                  <td data-label="#" className="num rank">{r.rank}</td>
                  <td data-label="Player"><Link to={playerPath(r.user_id, r.name)}>{r.name}</Link></td>
                  <td data-label={board.data!.label} className="num"><strong>{Number.isInteger(r.value) ? int(r.value) : num(r.value, 2)}</strong></td>
                  {COLUMNS.filter(([key]) => key !== board.data!.stat).map(([key, heading, value]) => (
                    <td key={key} data-label={heading} className="num">{value(r)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ))}
      {total > PAGE_SIZE && (
        <p className="pager">
          <button className="secondary" disabled={offset === 0} onClick={() => set("offset", String(Math.max(0, offset - PAGE_SIZE) || ""))}>Previous</button>
          <span className="muted"> {offset + 1}–{Math.min(total, offset + PAGE_SIZE)} of {total} </span>
          <button className="secondary" disabled={offset + PAGE_SIZE >= total} onClick={() => set("offset", String(offset + PAGE_SIZE))}>Next</button>
        </p>
      )}

      <h2>Latest combat matches</h2>
      {matches.data && matches.data.items.length === 0 && <p className="muted">No combat matches yet.</p>}
      {matches.data && matches.data.items.length > 0 && (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr><th>Played</th><th>Map</th><th className="num">Players</th><th className="num">Kills</th><th className="num">Damage</th><th className="num">Length</th></tr>
            </thead>
            <tbody>
              {matches.data.items.map((m) => (
                <tr key={m.session_id}>
                  <td data-label="Played"><Link to={`/combat/${m.session_id}`}>{dateTime(m.started_at)}</Link></td>
                  <td data-label="Map">{title(m.map)}</td>
                  <td data-label="Players" className="num">{m.players}</td>
                  <td data-label="Kills" className="num">{int(m.kills)}</td>
                  <td data-label="Damage" className="num">{int(m.damage)}</td>
                  <td data-label="Length" className="num">{duration(m.duration_s)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </TableWrap>
      )}
    </section>
  );
}

export function CombatMatchPage() {
  const { id = "" } = useParams();
  const match = useApi(() => getCombatMatch(id), `combat-match|${id}`);
  const m = match.data;
  usePageTitle(m ? `Combat stats · ${title(m.map)}` : "Combat match");
  return (
    <section>
      {match.loading && !m && <Skeleton lines={6} />}
      {isNotFound(match.error) ? (
        <NotFoundBox heading="Combat match not found" links={[["/combat", "Combat stats"], ["/", "Home"]]}>
          This match has no combat report (yet), or the link is wrong.
        </NotFoundBox>
      ) : (
        <>
          <p><Link to="/combat">← Combat stats</Link></p>
          <Status loading={false} error={match.error} />
        </>
      )}
      {m && (
        <>
          <h1>{title(m.map)} · {dateTime(m.started_at)}</h1>
          {m.replay_match_id != null && <p><Link to={`/matches/${m.replay_match_id}`}>Open the replay match</Link></p>}
          <CombatMatchBody m={m} />
        </>
      )}
    </section>
  );
}
