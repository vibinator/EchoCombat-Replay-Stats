import { Link } from "react-router";
import { getMatchThumbnails, type MatchSummary } from "../api";
import { duration, modeLabel, scoreText, title } from "../format";
import { useApi } from "../useApi";
import { LocalTime, TeamBadge } from "./common";
import { EmptyState } from "./ui";

/** Team heat of every listed match, fetched in one request; empty until it arrives (or if it fails). */
function useThumbnails(matches: MatchSummary[]): Record<string, string> {
  const ids = matches.map((m) => m.id);
  const key = [...ids].sort((a, b) => a - b).join(",");
  const heat = useApi(() => (ids.length ? getMatchThumbnails(ids) : Promise.resolve({ thumbnails: {} })), `thumbnails:${key}`);
  return heat.data?.thumbnails ?? {};
}

/** Minimap thumbnail with the players' heat on top; both images fill the same box with object-fit: contain, and the
 * heat PNG covers the whole minimap, so they line up at any card size. */
function MatchThumb({ map, heat }: { map: string; heat: string | undefined }) {
  return (
    <div className={heat ? "match-card-thumb has-heat" : "match-card-thumb"}>
      <img src={`/minimaps/${map}_small.png`} alt="" loading="lazy" />
      {heat && <img className="match-card-heat" src={heat} alt="" />}
    </div>
  );
}

/** Visual match list: minimap thumbnail with team heat, score, winner and (when loaded) the players' names.
 * `compact`: one short row per match, small thumbnail on the left (home page, beside the live video). */
export function MatchCards({ matches, compact = false }: { matches: MatchSummary[]; compact?: boolean }) {
  const thumbnails = useThumbnails(matches);
  if (matches.length === 0) return <EmptyState title="No matches match these filters" />;
  return (
    <div className={compact ? "match-cards compact" : "match-cards"}>
      {matches.map((m) => (
        <Link key={m.id} to={`/matches/${m.id}`} className="match-card">
          <MatchThumb map={m.map} heat={thumbnails[m.id]} />
          <div className="match-card-body">
            <div className="match-card-head">
              <strong>{title(m.map)}</strong>
              <span className="muted">
                {modeLabel(m.mode)} · <span className="match-id">#{m.id}</span>
              </span>
            </div>
            <div className="match-card-score">
              <span>{scoreText(m)}</span>
              <TeamBadge team={m.winner} />
            </div>
            <span className="muted">
              <LocalTime iso={m.started_at} /> · {duration(m.duration_s)}
              {m.player_count != null && ` · ${m.player_count} players`}
            </span>
            {m.players && m.players.length > 0 && (
              <div className="match-card-players">
                {m.players.slice(0, 10).map((p) => (
                  <span key={p.user_id} className={`name-chip ${p.team}`}>
                    {p.name}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}
