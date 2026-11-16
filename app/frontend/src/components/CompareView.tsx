import { useState } from "react";
import { Link } from "react-router";
import { comparePlayers, getPlayerHeatmap3d, getPlayerHeatmapBy, searchPlayers, type Period, type PlayerStats } from "../api";
import { Status, TableWrap } from "./common";
import { HEATMAP_CELL_M, HeatmapView } from "./HeatmapView";
import { EmptyState, Skeleton, WhenVisible } from "./ui";
import { MAPS, duration, int, num, pct, playerPath, title } from "../format";
import { useApi } from "../useApi";

/** Players in one comparison, the profile's own player included. */
export const COMPARE_MAX = 4;

/** A player profile's Compare tab, with these players already in it: `ids[0]` is the profile's player, the rest the
 *  others (?vs=). Used by the old /compare address and the Leaderboard's "Compare selected". */
export function compareTabPath(path: string, ids: string[], period?: Period): string {
  const p = new URLSearchParams({ tab: "compare" });
  if (ids.length > 1) p.set("vs", ids.slice(1, COMPARE_MAX).join(","));
  if (period && period !== "all") p.set("period", period);
  return `${path}?${p.toString()}`;
}

/** A speed, or just "–" when the player has none in this period. */
const speed = (value: number | null, digits?: number) => (value == null ? "–" : `${num(value, digits)} m/s`);

const ROWS: [string, (s: PlayerStats) => string, (s: PlayerStats) => number | null, boolean, ((s: PlayerStats) => boolean)?][] = [
  // label, display, comparable value, higher is better
  ["Games", (s) => int(s.games), (s) => s.games, true],
  [
    "Wins – losses",
    (s) => `${int(s.wins)} – ${int(s.losses)}`,
    (s) => (s.wins != null && s.losses != null && s.wins + s.losses ? s.wins / (s.wins + s.losses) : null),
    true,
    (s) => s.wins != null, // hidden from players: left out of the answer
  ],
  ["Hours played", (s) => num(s.hours_played), (s) => s.hours_played, true],
  ["Deaths / game*", (s) => num(s.deaths_per_game_est, 2), (s) => s.deaths_per_game_est, false],
  ["Average speed", (s) => speed(s.avg_speed, 2), (s) => s.avg_speed, true],
  ["Top speed", (s) => speed(s.top_speed), (s) => s.top_speed, true],
  ["Time idle", (s) => pct(s.pct_stopped), (s) => s.pct_stopped, false],
  ["Inverted", (s) => pct(s.pct_upside_down), (s) => s.pct_upside_down, true],
  ["Near a teammate", (s) => pct(s.pct_near_mate), (s) => s.pct_near_mate, true],
  ["Near an enemy", (s) => pct(s.pct_near_enemy), (s) => s.pct_near_enemy, true],
  ["Average ping", (s) => num(s.avg_ping, 0), (s) => s.avg_ping, false],
  ["Payload push*", (s) => duration(s.payload_push_s), (s) => s.payload_push_s, true],
  ["Payload block*", (s) => duration(s.payload_block_s), (s) => s.payload_block_s, true],
  ["Emotes", (s) => int(s.emote_count), (s) => s.emote_count, true],
];

function AddPlayer({ onAdd }: { onAdd: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const found = useApi(() => (term ? searchPlayers(term, 8) : Promise.resolve(null)), term);
  return (
    <div>
      <form className="search" onSubmit={(e) => (e.preventDefault(), setTerm(q.trim()))}>
        <input type="search" maxLength={64} placeholder="Add a player" aria-label="Add a player to compare" value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="submit">Find</button>
      </form>
      {found.data && (
        <ul className="picker">
          {found.data.items.map((p) => (
            <li key={p.user_id}>
              <button className="link" onClick={() => (onAdd(p.user_id), setTerm(""), setQ(""))}>{p.name}</button> <span className="muted">{int(p.games)} games</span>
            </li>
          ))}
          {found.data.items.length === 0 && <li className="muted">No players found.</li>}
        </ul>
      )}
    </div>
  );
}

/** Compare tab of a player profile (user, 2026-11-16: the Compare page moved here). The profile's player is always the
 *  first column and the first side of the head-to-head; up to three others are added by search or from the Leaderboard. */
export function CompareView({ userId, name, others, setOthers, period, map, setMap }: {
  userId: string; name: string; others: string[]; setOthers: (ids: string[]) => void;
  period: Period; map: string; setMap: (map: string) => void;
}) {
  const ids = [userId, ...others.filter((id) => id !== userId)].slice(0, COMPARE_MAX);
  const data = useApi(() => (ids.length >= 2 ? comparePlayers(ids, period) : Promise.resolve(null)), `${ids.join(",")}|${period}`);
  const c = data.data;
  const remove = (id: string) => setOthers(ids.slice(1).filter((x) => x !== id));

  return (
    <section>
      <h2>Compare</h2>
      <p className="muted">{name} side by side with up to three other players; head-to-head is {name} against the first one added.</p>
      {ids.length < COMPARE_MAX && (
        <div className="filters">
          <AddPlayer onAdd={(id) => !ids.includes(id) && setOthers([...ids.slice(1), id])} />
        </div>
      )}

      {ids.length === 1 && (
        <EmptyState title="Add a player to compare with">
          Search above, or tick players on the <Link to="/leaderboard">Leaderboard</Link> and use "Compare selected".
        </EmptyState>
      )}
      {data.loading && <Skeleton lines={6} />}
      <Status loading={false} error={data.error} />
      {c && (
        <>
          <TableWrap>
            <table>
              <thead>
                <tr>
                  <th>Stat</th>
                  {c.players.map((p, i) => (
                    <th key={p.user_id} className="num">
                      {i === 0 ? p.name : <Link to={playerPath(p.user_id, p.name)}>{p.name}</Link>}
                      {i > 0 && (
                        <>
                          {" "}
                          <button className="link danger" aria-label={`Remove ${p.name}`} onClick={() => remove(p.user_id)}>×</button>
                        </>
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ROWS.filter(([, , , , shown]) => !shown || c.players.every((p) => shown(p.stats))).map(([label, show, value, higher]) => {
                  const values = c.players.map((p) => value(p.stats));
                  const known = values.filter((v): v is number => v != null);
                  const best = known.length > 1 ? (higher ? Math.max(...known) : Math.min(...known)) : null;
                  const most = Math.max(0, ...known);
                  return (
                    <tr key={label}>
                      <td>{label}</td>
                      {c.players.map((p, i) => (
                        <td key={p.user_id} className={`num${best != null && values[i] === best ? " best" : ""}`}>
                          {show(p.stats)}
                          {values[i] != null && most > 0 && (
                            <span className="mini-track" aria-hidden="true">
                              <span className="mini-fill" style={{ width: `${Math.max(2, (values[i]! / most) * 100)}%` }} />
                            </span>
                          )}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </TableWrap>
          <p className="muted footnote">
            Best value per row is highlighted. * Estimated. Averages and win rates count games of 2+ minutes with 2+ players per team;
            games without a recorded winner count for neither side.
          </p>

          <h2>Head to head: {c.players[0].name} vs {c.players[1].name}</h2>
          <div className="cards">
            <div className="card">
              <span className="label">Same team</span>
              <strong>{int(c.head_to_head.together.games)} games</strong>
              {c.head_to_head.together.wins != null && (
                <span className="muted">record {c.head_to_head.together.wins} – {c.head_to_head.together.losses}</span>
              )}
            </div>
            <div className="card">
              <span className="label">Opposite teams</span>
              <strong>{int(c.head_to_head.against.games)} games</strong>
              {c.head_to_head.against.wins != null && (
                <span className="muted">
                  {c.players[0].name} won {c.head_to_head.against.wins}, lost {c.head_to_head.against.losses}
                </span>
              )}
            </div>
          </div>

          <div className="section-head">
            <h2>Heatmaps</h2>
            <label>
              Map{" "}
              <select value={map} onChange={(e) => setMap(e.target.value)}>
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
  const h = useApi(() => getPlayerHeatmapBy(userId, map, "team", period, 200, HEATMAP_CELL_M), `${userId}|${map}|${period}`);
  return (
    <div>
      <h3>{name}</h3>
      {h.loading && <Skeleton lines={3} />}
      {h.data && (
        <HeatmapView
          heatmap={h.data}
          caption={`${int(h.data.matches)} matches.`}
          view3d={{ key: `h3|${userId}|${map}|${period}`, load: () => getPlayerHeatmap3d(userId, map, "team", period, 200) }}
        />
      )}
      <Status loading={false} error={h.error} />
    </div>
  );
}
