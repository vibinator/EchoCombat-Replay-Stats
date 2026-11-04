import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router";
import { getAchievements, getAchievers, getRarity, getRecentUnlocks, searchPlayers } from "../api";
import { AchievementRules, AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, JumpToNew, MegaPrizesSection, useAchievementsAccess } from "../components/AchievementsView";
import { Status } from "../components/common";
import { achievementsPath, int, nameSlug, pct, playerPath } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

function PlayerPicker() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const found = useApi(() => (search ? searchPlayers(search, 10) : Promise.resolve(null)), search);

  function submit(e: FormEvent) {
    e.preventDefault();
    setSearch(q.trim());
  }

  return (
    <>
      <form className="search" onSubmit={submit} role="search">
        <input type="search" maxLength={64} placeholder="Find a player" aria-label="Find a player" value={q} onChange={(e) => setQ(e.target.value)} />
        <button type="submit">Search</button>
      </form>
      {search && <Status loading={found.loading} error={found.error} />}
      {found.data &&
        (found.data.items.length === 0 ? (
          <p className="muted">No players found for "{search}".</p>
        ) : (
          <ul className="picker">
            {found.data.items.map((p) => (
              <li key={p.user_id}>
                <Link to={achievementsPath(p.user_id, p.name)}>{p.name}</Link>{" "}
                <span className="muted">{int(p.games)} games</span>
              </li>
            ))}
          </ul>
        ))}
    </>
  );
}

function TopPlayers() {
  const top = useApi(() => getAchievers(10), "top");
  if (!top.data || top.data.length === 0) return null;
  return (
    <>
      <div className="section-head">
        <h2>Top players</h2>
        <Link to="/leaderboard?stat=achievements">Full leaderboard</Link>
      </div>
      <ol className="top-players" tabIndex={0} aria-label="Top players, scroll sideways">
        {top.data.map((p) => (
          <li key={p.user_id}>
            <span className="rank">#{p.rank}</span>
            <Link to={achievementsPath(p.user_id, p.name)} className="name">{p.name}</Link>
            <strong className="big">
              {int(p.completed)} <span className="muted">/ {int(p.total)} completed</span>
            </strong>
            <span className="muted" title="Gold or better = challenges where the player reached the gold, diamond or platinum medal">{int(p.gold_plus)} challenges at gold or better</span>
            <span className="muted" title="Every medal step reached, added up across all challenges (a challenge can give up to 5)">{int(p.medals)} medals earned in total</span>
            {p.best_section && <span className="muted">Best category: {p.best_section} ({pct(p.best_section_share)} done)</span>}
            <span className="muted">Avg progress {pct(p.overall)}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

function RecentUnlocks() {
  const recent = useApi(getRecentUnlocks, "recent");
  if (!recent.data || recent.data.length === 0) return null;
  return (
    <>
      <h2>Recent medals</h2>
      <ul className="recent-unlocks" tabIndex={0} aria-label="Recent medals, scroll sideways">
        {recent.data.map((e, i) => (
          <li key={`${e.user_id}-${e.id}-${i}`}>
            <img src={`/achievements/${e.icon ?? "happy_cubesat.png"}`} alt="" />
            <span>
              <Link to={achievementsPath(e.user_id, e.name)}>{e.name}</Link> earned{" "}
              <span className={`medal-chip ${e.medal ?? "gold"}`}>{e.medal ?? "completed"}</span> in <strong>{e.achievement}</strong>
            </span>
            <span className="muted">{e.at.slice(0, 10)} {e.at.slice(11, 16)}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Catalogue() {
  const rules = useApi(getRarity, "catalogue");
  return (
    <>
      <div className="section-head">
        <h2>All achievements</h2>
        <JumpToNew ready={!!rules.data} />
      </div>
      <Status loading={rules.loading} error={rules.error} />
      {rules.data && <GroupedBadges items={rules.data} />}
    </>
  );
}

export function AchievementsPage() {
  usePageTitle("Achievements");
  const { visible, start, total, peek } = useAchievementsAccess();
  if (visible === null) return null;
  if (!visible)
    return (
      <section>
        <h1>Achievements</h1>
        <ComingSoon start={start} total={total} peek={peek} />
      </section>
    );
  return <LaunchedAchievementsPage />;
}

function LaunchedAchievementsPage() {
  const [params] = useSearchParams();
  const { userId, name: nameInUrl = "" } = useParams();
  const { hash } = useLocation();
  const player = userId ?? params.get("player");
  const name = useApi(() => (player ? getAchievements(player) : Promise.resolve(null)), player ?? "");
  const d = name.data;
  usePageTitle(d ? `Achievements · ${d.name}` : "Achievements");

  // show the player's own address, /achievements/<name>/<id>: old ?player= links, an outdated name and a merged ID all
  // move to it (as profiles do)
  if (d && (!userId || d.user_id !== userId || nameInUrl !== nameSlug(d.name))) {
    const rest = new URLSearchParams(params);
    rest.delete("player");
    const search = rest.toString();
    return <Navigate replace to={`${achievementsPath(d.user_id, d.name)}${search ? `?${search}` : ""}${hash}`} />;
  }

  return (
    <section>
      <div className="section-head">
        <h1>Achievements{player && name.data && <span className="muted"> · {name.data.name}</span>}</h1>
        {player && (
          <span>
            <Link to={d ? playerPath(d.user_id, d.name) : `/players/${encodeURIComponent(player)}`}>Player profile</Link> · <Link to="/achievements">All achievements</Link>
          </span>
        )}
      </div>
      {player ? (
        <>
          <ChallengeBanner />
          <AchievementsView userId={player} />
        </>
      ) : (
        <>
          <MegaPrizesSection />
          <div className="ach-intro">
            <p className="muted">
              The original ECRanked achievements plus new ones (marked "new"). Most are medal ladders, bronze to platinum; pick a player to see
              their progress.
            </p>
            <AchievementRules open />
            <ChallengeBanner />
            <PlayerPicker />
          </div>
          <TopPlayers />
          <RecentUnlocks />
          <Catalogue />
        </>
      )}
    </section>
  );
}
