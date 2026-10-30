import type { ReactNode } from "react";
import { Link } from "react-router";
import type { GearItem, Loadout, MatchSummary, Team } from "../api";
import { dateTime, duration, modeLabel, scoreText, teamLabel, title } from "../format";

export function Status({ loading, error }: { loading: boolean; error: string | null }) {
  if (error) return <p className="error">{error}</p>;
  if (loading) return <p className="muted">Loading…</p>;
  return null;
}

export function TeamBadge({ team }: { team: Team | null }) {
  return team ? <span className={`team-badge ${team}`}>{teamLabel(team)}</span> : <span className="muted">–</span>;
}

export function GearName({ item }: { item: GearItem }) {
  return (
    <span title={item.cut ? `${item.code} — cut / unreleased gear` : item.code}>
      {item.name}
      {item.cut && <sup className="cut">cut</sup>}
    </span>
  );
}

export function LoadoutText({ loadout }: { loadout: Loadout | undefined }) {
  if (!loadout) return <span className="muted">–</span>;
  return (
    <span className="loadout">
      <GearName item={loadout.weapon} /> · <GearName item={loadout.ordnance} /> · <GearName item={loadout.tacmod} />
    </span>
  );
}

export function TableWrap({ children }: { children: ReactNode }) {
  return <div className="table-wrap">{children}</div>;
}

export function MatchTable({ matches, extra }: { matches: MatchSummary[]; extra?: (m: MatchSummary) => ReactNode }) {
  if (matches.length === 0) return <p className="muted">No matches yet. Replays are still being imported — see Import.</p>;
  return (
    <TableWrap>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Map</th>
            <th>Mode</th>
            <th>Score</th>
            <th>Winner</th>
            <th className="num">Length</th>
            {extra && <th />}
          </tr>
        </thead>
        <tbody>
          {matches.map((m) => (
            <tr key={m.id}>
              <td>
                <Link to={`/matches/${m.id}`}>{dateTime(m.started_at)}</Link>
              </td>
              <td>{title(m.map)}</td>
              <td>{modeLabel(m.mode)}</td>
              <td>{scoreText(m)}</td>
              <td>
                <TeamBadge team={m.winner} />
              </td>
              <td className="num">{duration(m.duration_s)}</td>
              {extra && <td>{extra(m)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </TableWrap>
  );
}
