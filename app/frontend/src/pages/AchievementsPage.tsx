import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router";
import { getAchievements, getAchievers, getRarity, getRecentUnlocks, searchPlayers } from "../api";
import { AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, JumpToNew, useAchievementsAccess } from "../components/AchievementsView";
import { Status } from "../components/common";
import { achievementsPath, int, nameSlug, pct, playerPath } from "../format";
import { useApi } from "../useApi";

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
            <span className="muted">{int(p.medals)} medals · {int(p.gold_plus)} gold or better</span>
            {p.best_section && <span className="muted">Strongest: {p.best_section} ({pct(p.best_section_share)})</span>}
            <span className="muted">Overall {pct(p.overall)}</span>
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
      <h2>Recently completed</h2>
      <ul className="recent-unlocks" tabIndex={0} aria-label="Recently completed, scroll sideways">
        {recent.data.map((e, i) => (
          <li key={`${e.user_id}-${e.id}-${i}`}>
            <img src={`/achievements/${e.icon ?? "happy_cubesat.png"}`} alt="" />
            <span>
              <Link to={achievementsPath(e.user_id, e.name)}>{e.name}</Link> completed <strong>{e.achievement}</strong>
            </span>
            <span className="muted">{e.date}</span>
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
          <p className="muted">
            The achievements from the original ECRanked site, plus new ones (marked "new") built on data it never used:
            unreleased gear, wins, payload push / block time, emotes and how often you play. Almost every challenge is a ladder of medals
            (bronze, silver, gold, diamond, platinum); pick a player to see their progress to each medal. A few single-step challenges keep
            white 25%, bronze 50%, silver 75%, gold 100%. "Use only" an item = 95%+ of that game's loadout time; "use" = 5%+. Days are calendar days;
            "7 days" is any 7-day window, not a calendar week.
          </p>
          <ChallengeBanner />
          <PlayerPicker />
          <TopPlayers />
          <RecentUnlocks />
          <Catalogue />
        </>
      )}
    </section>
  );
}
