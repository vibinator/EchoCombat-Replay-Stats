import { Link, useSearchParams } from "react-router";
import { searchPlayers } from "../api";
import { LocalTime, Status, TableWrap } from "../components/common";
import { Avatar, useAvatars } from "../components/Avatar";
import { PlayerSearch } from "../components/PlayerSearch";
import { int, num, playerPath, title } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

export function PlayersPage() {
  usePageTitle("Players");
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const result = useApi(() => searchPlayers(q), q);
  const avatars = useAvatars(result.data?.items.map((p) => p.user_id) ?? []);

  return (
    <section>
      <h1>Players</h1>
      <PlayerSearch key={q} initial={q} />
      <Status loading={result.loading} error={result.error} />
      {result.data &&
        (result.data.items.length === 0 ? (
          <p className="muted">No players found{q && ` for "${q}"`}.</p>
        ) : (
          <TableWrap>
            <table className="stack">
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="num">Games</th>
                  <th className="num">Hours played</th>
                  <th>Favourite map</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((p) => (
                  <tr key={p.user_id}>
                    <td data-label="Name">
                      <span className="who"><Avatar name={p.name} url={avatars[p.user_id]} /><Link to={playerPath(p.user_id, p.name)}>{p.name}</Link></span>
                    </td>
                    <td data-label="Games" className="num">{int(p.games)}</td>
                    <td data-label="Hours played" className="num">{p.hours_played != null ? num(p.hours_played, 1) : "–"}</td>
                    <td data-label="Favourite map">{p.favourite_map ? title(p.favourite_map) : "–"}</td>
                    <td data-label="Last seen"><LocalTime iso={p.last_seen_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        ))}
    </section>
  );
}
