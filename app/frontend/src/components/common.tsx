import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import { Link } from "react-router";
import { rateLimit, type GearItem, type Loadout, type MatchSummary, type Team } from "../api";
import { dateTime, duration, modeLabel, scoreText, teamLabel, title } from "../format";

/** Seconds until the rate limit lifts (0 when it is not active); ticks once a second while counting down. */
function useRateLimitCountdown(): number {
  const until = useSyncExternalStore(rateLimit.subscribe, rateLimit.until);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until <= Date.now()) return;
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [until]);
  return Math.max(0, Math.ceil((until - now) / 1000));
}

export function Status({ loading, error }: { loading: boolean; error: string | null }) {
  const wait = useRateLimitCountdown();
  if (error && wait > 0 && /too many requests/i.test(error)) {
    return (
      <p className="error rate-limit" role="status">
        {error} Trying again in <strong>{wait}s</strong>…
      </p>
    );
  }
  if (error) return <p className="error">{error}</p>;
  if (loading) return <p className="muted">Loading…</p>;
  return null;
}

export function TeamBadge({ team }: { team: Team | null }) {
  return team ? <span className={`team-badge ${team}`}>{teamLabel(team)}</span> : <span className="muted">–</span>;
}

/** In-game gear name -> small inline icon (public/icons). Add more names here as icons arrive. */
const GEAR_ICONS: Record<string, string> = {
  Comet: "/icons/comet.webp",
};

/** Decorative icon shown before a gear name; renders nothing for gear without an icon. */
export function GearIcon({ name }: { name: string }) {
  const src = GEAR_ICONS[name];
  return src ? <img className="gear-icon" src={src} alt="" aria-hidden="true" width={96} height={96} loading="lazy" decoding="async" /> : null;
}

/** Gear name with its icon (if any), kept on one line. */
export function GearLabel({ name }: { name: string }) {
  return GEAR_ICONS[name] ? (
    <span className="gear-label">
      <GearIcon name={name} />
      {name}
    </span>
  ) : (
    <>{name}</>
  );
}

export function GearName({ item }: { item: GearItem }) {
  return (
    <span title={item.cut ? `${item.code} — cut / unreleased gear` : item.code}>
      <GearLabel name={item.name} />
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
