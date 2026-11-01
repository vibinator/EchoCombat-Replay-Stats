import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { comparePlayers, getPlayerHeatmapBy, searchPlayers, type Period, type PlayerStats } from "../api";
import { Status, TableWrap } from "../components/common";
import { HeatmapView } from "../components/HeatmapView";
import { EmptyState, Skeleton, WhenVisible } from "../components/ui";
import { MAPS, duration, num, pct, title } from "../format";
import { useApi } from "../useApi";

const ROWS: [string, (s: PlayerStats) => string, (s: PlayerStats) => number | null, boolean][] = [
  // label, display, comparable value, higher is better
  ["Games", (s) => String(s.games), (s) => s.games, true],
  ["Wins – losses", (s) => `${s.wins} – ${s.losses}`, (s) => (s.wins + s.losses ? s.wins / (s.wins + s.losses) : null), true],
  ["Hours played", (s) => num(s.hours_played), (s) => s.hours_played, true],
  ["Deaths / game*", (s) => num(s.deaths_per_game_est, 2), (s) => s.deaths_per_game_est, false],
  ["Average speed", (s) => `${num(s.avg_speed, 2)} m/s`, (s) => s.avg_speed, true],
  ["Top speed", (s) => `${num(s.top_speed)} m/s`, (s) => s.top_speed, true],
  ["Time idle", (s) => pct(s.pct_stopped), (s) => s.pct_stopped, false],
  ["Inverted", (s) => pct(s.pct_upside_down), (s) => s.pct_upside_down, true],
  ["Near a teammate", (s) => pct(s.pct_near_mate), (s) => s.pct_near_mate, true],
  ["Near an enemy", (s) => pct(s.pct_near_enemy), (s) => s.pct_near_enemy, true],
  ["Average ping", (s) => num(s.avg_ping, 0), (s) => s.avg_ping, false],
  ["Payload push*", (s) => duration(s.payload_push_s), (s) => s.payload_push_s, true],
  ["Payload block*", (s) => duration(s.payload_block_s), (s) => s.payload_block_s, true],
  ["Emotes", (s) => String(s.emote_count), (s) => s.emote_count, true],
];

function AddPlayer({ onAdd }: { onAdd: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const found = useApi(() => (term ? searchPlayers(term, 8) : Promise.resolve(null)), term);
  return (
    <div>
      <form className="search" onSubmit={(e) => (e.preventDefault(), setTerm(q.trim()))}>
        <input type="search" placeholder="Add a player" aria-label="Add a player" value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="submit">Find</button>
      </form>
      {found.data && (
        <ul className="picker">
          {found.data.items.map((p) => (
            <li key={p.user_id}>
              <button className="link" onClick={() => (onAdd(p.user_id), setTerm(""), setQ(""))}>{p.name}</button> <span className="muted">{p.games} games</span>
            </li>
          ))}
          {found.data.items.length === 0 && <li className="muted">No players found.</li>}
        </ul>
      )}
    </div>
  );
}

export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const ids = (params.get("players") ?? "").split(",").filter(Boolean).slice(0, 4);
  const period = (params.get("period") as Period) || "all";
  const map = params.get("map") ?? "dyson";
  const data = useApi(() => (ids.length >= 2 ? comparePlayers(ids, period) : Promise.resolve(null)), `${ids.join(",")}|${period}`);

  function setIds(next: string[]) {
    const p = new URLSearchParams(params);
    if (next.length) p.set("players", next.join(","));
    else p.delete("players");
    setParams(p);
  }
  function set(key: string, value: string) {
    const p = new URLSearchParams(params);
    p.set(key, value);
    setParams(p);
  }

  const c = data.data;
  return (
    <section>
      <h1>Compare players</h1>
      <p className="muted">Up to four players side by side; head-to-head uses the first two.</p>
      <div className="filters">
        {ids.length < 4 && <AddPlayer onAdd={(id) => !ids.includes(id) && setIds([...ids, id])} />}
        <label>
          Period
          <select value={period} onChange={(e) => set("period", e.target.value)}>
            <option value="all">All time</option>
            <option value="month">This month</option>
            <option value="week">This week</option>
            <option value="day">Today</option>
          </select>
        </label>
      </div>

      {ids.length < 2 && <EmptyState title="Pick at least two players">Search above, or use "Compare" on a player page.</EmptyState>}
      {data.loading && <Skeleton lines={6} />}
      <Status loading={false} error={data.error} />
      {c && (
        <>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Stat</th>
                  {c.players.map((p) => (
                    <th key={p.user_id} className="num">
                      <Link to={`/players/${p.user_id}`}>{p.name}</Link>{" "}
                      <button className="link danger" aria-label={`Remove ${p.name}`} onClick={() => setIds(ids.filter((x) => x !== p.user_id))}>×</button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.map(([label, show, value, higher]) => {
                  const values = c.players.map((p) => value(p.stats));
                  const known = values.filter((v): v is number => v != null);
                  const best = known.length > 1 ? (higher ? Math.max(...known) : Math.min(...known)) : null;
                  return (
                    <tr key={label}>
                      <td>{label}</td>
                      {c.players.map((p, i) => (
                        <td key={p.user_id} className={`num${best != null && values[i] === best ? " best" : ""}`}>{show(p.stats)}</td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
          <p className="muted footnote">Best value per row is highlighted. * Estimated.</p>

          <h2>Head to head: {c.players[0].name} vs {c.players[1].name}</h2>
          <div className="cards">
            <div className="card">
              <span className="label">Same team</span>
              <strong>{c.head_to_head.together.games} games</strong>
              <span className="muted">record {c.head_to_head.together.wins} – {c.head_to_head.together.losses}</span>
            </div>
            <div className="card">
              <span className="label">Opposite teams</span>
              <strong>{c.head_to_head.against.games} games</strong>
              <span className="muted">
                {c.players[0].name} won {c.head_to_head.against.wins}, lost {c.head_to_head.against.losses}
              </span>
            </div>
          </div>

          <div className="section-head">
            <h2>Heatmaps</h2>
            <label>
              Map{" "}
              <select value={map} onChange={(e) => set("map", e.target.value)}>
                {MAPS.map((m) => <option key={m} value={m}>{title(m)}</option>)}
              </select>
            </label>
          </div>
          <WhenVisible minHeight={400}>
            <div className="heatmap-grid">
              {c.players.map((p) => (
                <CompareHeatmap key={p.user_id} userId={p.user_id} name={p.name} map={map} period={period} />
              ))}
            </div>
          </WhenVisible>
        </>
      )}
    </section>
  );
}

function CompareHeatmap({ userId, name, map, period }: { userId: string; name: string; map: string; period: Period }) {
  const h = useApi(() => getPlayerHeatmapBy(userId, map, "team", period, 200, 0.5), `${userId}|${map}|${period}`);
  return (
    <div>
      <h3>{name}</h3>
      {h.loading && <Skeleton lines={3} />}
      {h.data && <HeatmapView heatmap={h.data} caption={`${h.data.matches} matches.`} />}
    </div>
  );
}
