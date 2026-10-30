import { Link } from "react-router";
import type { MatchSummary } from "../api";
import { dateTime, duration, modeLabel, scoreText, title } from "../format";
import { TeamBadge } from "./common";
import { EmptyState } from "./ui";

/** Visual match list: minimap thumbnail, score, winner and (when loaded) the players' names. */
export function MatchCards({ matches }: { matches: MatchSummary[] }) {
  if (matches.length === 0) return <EmptyState title="No matches match these filters" />;
  return (
    <div className="match-cards">
      {matches.map((m) => (
        <Link key={m.id} to={`/matches/${m.id}`} className="match-card">
          <img src={`/minimaps/${m.map}_small.png`} alt="" loading="lazy" />
          <div className="match-card-body">
            <div className="match-card-head">
              <strong>{title(m.map)}</strong>
              <span className="muted">{modeLabel(m.mode)}</span>
            </div>
            <div className="match-card-score">
              <span>{scoreText(m)}</span>
              <TeamBadge team={m.winner} />
            </div>
            <span className="muted">
              {dateTime(m.started_at)} · {duration(m.duration_s)}
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
