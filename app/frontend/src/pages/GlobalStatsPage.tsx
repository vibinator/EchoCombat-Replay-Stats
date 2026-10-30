import { Link } from "react-router";
import { getOverview } from "../api";
import { Status } from "../components/common";
import { EmptyState, Skeleton } from "../components/ui";
import { duration, num, pct } from "../format";
import { useApi } from "../useApi";

export function GlobalStatsPage() {
  const overview = useApi(getOverview, "overview");
  const o = overview.data;
  const g = o?.global;

  return (
    <section>
      <h1>Global stats</h1>
      <p className="muted">Records and averages across every match in the archive.</p>

      {!o && !overview.error && <Skeleton cards={9} lines={0} />}
      <Status loading={false} error={overview.error} />

      {o && g && (o.matches === 0 ? (
        <EmptyState title="No matches yet">Replays are still being imported.</EmptyState>
      ) : (
        <div className="cards">
          <div className="card"><span className="label">Average match</span><strong>{duration(g.avg_match_s)}</strong></div>
          <div className="card">
            <span className="label">Longest match</span>
            <strong>{g.longest_match ? <Link to={`/matches/${g.longest_match.id}`}>{duration(g.longest_match.duration_s)}</Link> : "–"}</strong>
          </div>
          <div className="card"><span className="label">Players per match</span><strong>{num(g.avg_players_per_match)}</strong></div>
          <div className="card" title="Estimated from players leaving the play area"><span className="label">Deaths (est.)</span><strong>{g.deaths_est.toLocaleString()}</strong></div>
          <div className="card">
            <span className="label">Fastest player</span>
            <strong>{g.fastest ? <Link to={`/players/${g.fastest.user_id}`}>{g.fastest.name}</Link> : "–"}</strong>
            {g.fastest && <span className="muted">{num(g.fastest.top_speed)} m/s</span>}
          </div>
          <div className="card">
            <span className="label">Most matches</span>
            <strong>{g.most_active ? <Link to={`/players/${g.most_active.user_id}`}>{g.most_active.name}</Link> : "–"}</strong>
            {g.most_active && <span className="muted">{g.most_active.games.toLocaleString()} matches</span>}
          </div>
          <div className="card">
            <span className="label">Busiest day</span>
            <strong>{g.busiest_day?.day ?? "–"}</strong>
            {g.busiest_day && <span className="muted">{g.busiest_day.matches} matches</span>}
          </div>
          <div className="card" title="Payload matches with a known result">
            <span className="label">Payload attack wins</span>
            <strong>{pct(g.payload_attack_win_rate)}</strong>
            <span className="muted">of {g.payload_decided.toLocaleString()} decided</span>
          </div>
          <div className="card">
            <span className="label">Capture point wins</span>
            <strong>
              <span className="team-text blue">{g.capture_wins.blue}</span> – <span className="team-text orange">{g.capture_wins.orange}</span>
            </strong>
            <span className="muted">blue – orange</span>
          </div>
        </div>
      ))}
    </section>
  );
}
