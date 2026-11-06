import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router";
import { getAchievements, getAchievers, getRarity, getRecentUnlocks, searchPlayers } from "../api";
import { AchievementRules, AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, JumpToNew, MegaPrizesSection, useAchievementsAccess } from "../components/AchievementsView";
import { Avatar, useAvatars } from "../components/Avatar";
import { Status } from "../components/common";
import { achievementsPath, dateTime, int, medalRuleText, nameSlug, pct, playerPath } from "../format";
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

/** The ranking behind "Top players" and "Recent medals" is calculated for everyone, which takes minutes after the server
 *  starts (it answers empty or late meanwhile). Ask again every 10 seconds, up to 5 minutes, until there is something. */
function useRanking<T extends unknown[]>(load: () => Promise<T>, key: string) {
  const [round, setRound] = useState(0);
  const result = useApi(load, `${key}|${round}`);
  const waiting = !result.loading && (result.error !== null || !result.data || result.data.length === 0);
  useEffect(() => {
    if (!waiting || round >= 30) return;
    const t = setTimeout(() => setRound(round + 1), 10_000);
    return () => clearTimeout(t);
  }, [waiting, round]);
  return result;
}

function TopPlayers() {
  const top = useRanking(() => getAchievers(10), "top");
  const avatars = useAvatars(top.data?.map((p) => p.user_id) ?? []);
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
            <span className="who"><Avatar name={p.name} url={avatars[p.user_id]} size={32} /><Link to={achievementsPath(p.user_id, p.name)} className="name">{p.name}</Link></span>
            <strong className="big">
              {int(p.completed)} <span className="muted">/ {int(p.total)} completed</span>
            </strong>
            <span className="muted" title="Gold or better = challenges where the player reached the gold, platinum or crown medal">{int(p.gold_plus)} challenges at gold or better</span>
            <span className="muted" title="Every medal step reached, added up across all challenges (a challenge can give up to 4)">{int(p.medals)} medals earned in total</span>
            {p.best_section && <span className="muted">Best category: {p.best_section} ({pct(p.best_section_share)} done)</span>}
            <span className="muted">Avg progress {pct(p.overall)}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

/** The medal's icon in the colour of the tier earned (like the badge cards); uploaded art keeps its own colours. */
function RecentIcon({ icon, medal }: { icon: string | null; medal: string | null }) {
  const src = `/achievements/${icon ?? "happy_cubesat.png"}`;
  if (icon?.startsWith("custom/")) return <img src={src} alt="" />;
  return <span className={`recent-glyph t-${medal ?? "crown"}`} style={{ WebkitMaskImage: `url(${src})`, maskImage: `url(${src})` }} aria-hidden="true" />;
}

function RecentUnlocks() {
  const recent = useRanking(getRecentUnlocks, "recent");
  const avatars = useAvatars(recent.data?.map((e) => e.user_id) ?? []);
  if (!recent.data || recent.data.length === 0) return null;
  return (
    <>
      <h2>Recent medals</h2>
      <ul className="recent-unlocks" tabIndex={0} aria-label="Recent medals, scroll sideways">
        {recent.data.map((e, i) => (
          <li key={`${e.user_id}-${e.id}-${i}`}>
            <RecentIcon icon={e.icon} medal={e.medal} />
            <span>
              <span className="who"><Avatar name={e.name} url={avatars[e.user_id]} size={20} /><Link to={achievementsPath(e.user_id, e.name)}>{e.name}</Link></span> earned{" "}
              <span className={`medal-chip ${e.medal ?? "gold"}`}>{e.medal ?? "completed"}</span> in <strong>{e.achievement}</strong>
            </span>
            <span className="desc">{medalRuleText(e.description, e.medal)}</span>
            <span className="muted">{dateTime(e.at)}</span>
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
            <ChallengeBanner />
            <PlayerPicker />
          </div>
          <TopPlayers />
          <RecentUnlocks />
          <Catalogue />
          <AchievementRules />
        </>
      )}
    </section>
  );
}
