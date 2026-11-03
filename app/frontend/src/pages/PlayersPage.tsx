import { Link, useSearchParams } from "react-router";
import { searchPlayers } from "../api";
import { Status, TableWrap } from "../components/common";
import { PlayerSearch } from "../components/PlayerSearch";
import { dateTime, int, playerPath } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

export function PlayersPage() {
  usePageTitle("Players");
  const [params] = useSearchParams();
  const q = params.get("q") ?? "";
  const result = useApi(() => searchPlayers(q), q);

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
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th className="num">Games</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {result.data.items.map((p) => (
                  <tr key={p.user_id}>
                    <td>
                      <Link to={playerPath(p.user_id, p.name)}>{p.name}</Link>
                    </td>
                    <td className="num">{int(p.games)}</td>
                    <td>{dateTime(p.last_seen_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        ))}
    </section>
  );
}
