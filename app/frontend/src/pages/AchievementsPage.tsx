import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router";
import { getAchievements, getLeaderboard, getRarity, getRecentUnlocks, searchPlayers } from "../api";
import { AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, JumpToNew, useAchievementsAccess } from "../components/AchievementsView";
import { Status, TableWrap } from "../components/common";
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
  const board = useApi(() => getLeaderboard({ stat: "achievements", period: "all", min_games: 10, limit: 10 }), "top");
  if (!board.data || board.data.items.length === 0) return null;
  return (
    <>
      <div className="section-head">
        <h2>Top players</h2>
        <Link to="/leaderboard?stat=achievements">Full leaderboard</Link>
      </div>
      <TableWrap>
        <table>
          <thead>
            <tr>
              <th className="num">#</th>
              <th>Player</th>
              <th className="num">Games</th>
              <th className="num">Overall</th>
            </tr>
          </thead>
          <tbody>
            {board.data.items.map((r) => (
              <tr key={r.user_id}>
                <td className="num">{r.rank}</td>
                <td>
                  <Link to={achievementsPath(r.user_id, r.name)}>{r.name}</Link>
                </td>
                <td className="num">{int(r.games)}</td>
                <td className="num">{pct(r.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableWrap>
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
