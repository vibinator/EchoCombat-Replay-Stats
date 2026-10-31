import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router";
import { getAchievements, getLeaderboard, getRarity, getRecentUnlocks, searchPlayers } from "../api";
import { AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, JumpToNew, useAchievementsAccess } from "../components/AchievementsView";
import { Status, TableWrap } from "../components/common";
import { pct } from "../format";
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
        <input type="search" placeholder="Find a player" aria-label="Find a player" value={q} onChange={(e) => setQ(e.target.value)} />
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
                <Link to={`/achievements?player=${encodeURIComponent(p.user_id)}`}>{p.name}</Link>{" "}
                <span className="muted">{p.games} games</span>
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
                  <Link to={`/achievements?player=${encodeURIComponent(r.user_id)}`}>{r.name}</Link>
                </td>
                <td className="num">{r.games}</td>
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
      <ul className="recent-unlocks">
        {recent.data.map((e, i) => (
          <li key={`${e.user_id}-${e.id}-${i}`}>
            <img src={`/achievements/${e.icon ?? "happy_cubesat.png"}`} alt="" />
            <span>
              <Link to={`/achievements?player=${encodeURIComponent(e.user_id)}`}>{e.name}</Link> completed <strong>{e.achievement}</strong>
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
  const player = params.get("player");
  const name = useApi(() => (player ? getAchievements(player) : Promise.resolve(null)), player ?? "");

  return (
    <section>
      <div className="section-head">
        <h1>Achievements{player && name.data && <span className="muted"> · {name.data.name}</span>}</h1>
        {player && (
          <span>
            <Link to={`/players/${encodeURIComponent(player)}`}>Player profile</Link> · <Link to="/achievements">All achievements</Link>
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
            The 75 achievements from the original ECRanked site, plus new ones (marked "new") built on data it never used:
            unreleased gear, wins, payload push / block time and emotes. Pick a player to see their progress. Tiers: white 25%, bronze 50%,
            silver 75%, gold 100%. "Use only" an item = 95%+ of that game's loadout time; "use" = 5%+. Days are calendar days,
            weeks start on Monday.
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
