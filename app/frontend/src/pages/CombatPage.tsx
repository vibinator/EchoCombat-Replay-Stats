import { Link, useParams, useSearchParams } from "react-router";
import { getCombatBoard, getCombatMatch, getCombatStats, getCombatSummary, listCombatMatches, type Period } from "../api";
import { CombatMatchBody } from "../components/CombatView";
import { Status, TableWrap } from "../components/common";
import { Skeleton } from "../components/ui";
import { MAPS, dateTime, duration, int, num, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

const PERIODS: [Period, string][] = [["day", "Today"], ["week", "This week"], ["month", "This month"], ["all", "All time"]];
const PAGE_SIZE = 25;

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
      <p className="muted">
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
      {hint && <p className="muted footnote">{hint}</p>}
      {board.loading && !board.data && <Skeleton lines={6} />}
      <Status loading={false} error={board.error} />
      {board.data && (board.data.items.length === 0 ? (
        <p className="muted">No players with {minGames}+ combat matches here yet.</p>
      ) : (
        <TableWrap>
          <table className="stack">
            <thead>
              <tr><th className="num">#</th><th>Player</th><th className="num">{board.data.label}</th><th className="num">Matches</th><th className="num">Kills</th><th className="num">Deaths</th><th className="num">K/D</th><th className="num">Assists</th><th className="num">Damage</th></tr>
            </thead>
            <tbody>
              {board.data.items.map((r) => (
                <tr key={r.user_id}>
                  <td data-label="#" className="num rank">{r.rank}</td>
                  <td data-label="Player"><Link to={playerPath(r.user_id, r.name)}>{r.name}</Link></td>
                  <td data-label={board.data!.label} className="num"><strong>{Number.isInteger(r.value) ? int(r.value) : num(r.value, 2)}</strong></td>
                  <td data-label="Matches" className="num">{r.matches}</td>
                  <td data-label="Kills" className="num">{int(r.kills)}</td>
                  <td data-label="Deaths" className="num">{int(r.deaths)}</td>
                  <td data-label="K/D" className="num">{r.kd == null ? "–" : num(r.kd, 2)}</td>
                  <td data-label="Assists" className="num">{int(r.assists)}</td>
                  <td data-label="Damage" className="num">{int(r.damage)}</td>
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
      <p><Link to="/combat">← Combat stats</Link></p>
      {match.loading && !m && <Skeleton lines={6} />}
      <Status loading={false} error={match.error} />
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
