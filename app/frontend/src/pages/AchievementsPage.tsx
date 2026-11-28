import { useEffect, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useParams, useSearchParams } from "react-router";
import { getAchievements, getAchievers, getChallenges, getMe, getMyProfile, getRarity, getRecentUnlocks, loginUrl, searchPlayers } from "../api";
import { AchievementRules, AchievementsView, ChallengeBanner, ComingSoon, GroupedBadges, keepsColours, MegaPrizesSection, ScrollToNew, useAchievementsAccess } from "../components/AchievementsView";
import { Avatar, useAvatars } from "../components/Avatar";
import { Status } from "../components/common";
import { achievementsPath, dateTime, int, medalRuleText, nameSlug, pct, playerPath } from "../format";
import { useApi } from "../useApi";
import { usePageTitle } from "../usePageTitle";

/** An obvious way to one's own challenges (user, 2026-11-28: "on the challenges page, put a button (obvious) to let the
 *  user view their own profile"): logged in, their own challenges and player page; logged out, the Discord login; not
 *  on their own page already. */
function MyChallengesButton({ viewing }: { viewing: string | null }) {
  const me = useApi(getMe, "me");
  const loggedIn = !!me.data?.user;
  const mine = useApi(() => (loggedIn ? getMyProfile() : Promise.resolve(null)), `my-profile|${loggedIn}`);
  const { pathname } = useLocation();
  if (!me.data?.enabled) return null; // no Discord login on this server
  if (!loggedIn) {
    return (
      <div className="my-challenges">
        <a className="ach-all-big my-challenges-button" href={loginUrl(pathname)}>
          See your own challenges: log in with Discord <span aria-hidden="true">→</span>
        </a>
      </div>
    );
  }
  const p = mine.data;
  if (!p) return null;
  if (!p.user_id) {
    return (
      <div className="my-challenges">
        <Link className="ach-all-big my-challenges-button" to="/profile">My profile <span aria-hidden="true">→</span></Link>
        <span className="muted">Your Discord account is not linked to a player yet: play a match, or ask an admin to link it.</span>
      </div>
    );
  }
  if (viewing === p.user_id) return null;
  return (
    <div className="my-challenges">
      <Link className="ach-all-big my-challenges-button" to={achievementsPath(p.user_id, p.name)}>
        View my challenges <span aria-hidden="true">→</span>
      </Link>
      <Link to={playerPath(p.user_id, p.name)}>My player page</Link>
    </div>
  );
}

/** Find a player's challenges: top right of the page, beside the title, the matches in a list that drops down under it
 *  (user, 2026-11-28: it sat in a weird spot under the period banner). */
function PlayerPicker() {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const found = useApi(() => (search ? searchPlayers(search, 10) : Promise.resolve(null)), search);

  function submit(e: FormEvent) {
    e.preventDefault();
    setSearch(q.trim());
  }

  return (
    <div className="ch-find">
      <form className="search" onSubmit={submit} role="search">
        <input type="search" maxLength={64} placeholder="Find a player" aria-label="Find a player" value={q}
          onChange={(e) => { setQ(e.target.value); if (!e.target.value) setSearch(""); }} />
        <button type="submit">Search</button>
      </form>
      {search && (found.loading || found.error || found.data) && (
      <div className="ch-find-results">
      <Status loading={found.loading} error={found.error} />
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
      <button type="button" className="ch-find-close" aria-label="Close" onClick={() => { setSearch(""); setQ(""); }}>×</button>
      </div>
      )}
    </div>
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
    <div className="ach-pane">
      <div className="section-head">
        {/* no "Full leaderboard" link (user, 2026-11-27) */}
        <h2>Top players <span className="muted hint">· most challenges fully complete</span></h2>
      </div>
      <ol className="top-players" tabIndex={0} aria-label="Top players, scroll sideways">
        {/* shorter cards (user, 2026-11-27): the full-complete count and the tiers reached; the rest is hover text */}
        {top.data.map((p) => (
          <li key={p.user_id} title={[
            `${int(p.gold_plus)} challenges at silver or better (silver, gold or crown tier)`,
            p.best_section ? `Best category: ${p.best_section} (${pct(p.best_section_share)} done)` : null,
            `Avg progress ${pct(p.overall)}`,
          ].filter(Boolean).join("\n")}>
            <span className="rank">#{p.rank}</span>
            <span className="who"><Avatar name={p.name} url={avatars[p.user_id]} size={32} /><Link to={achievementsPath(p.user_id, p.name)} className="name">{p.name}</Link></span>
            {/* fewer words (user, 2026-11-27): the heading already says "most challenges fully complete" */}
            <strong className="big" title={`${int(p.completed)} of ${int(p.total)} challenges fully complete`}>
              <img className="medal-crown" src="/achievements/crown.png" alt="" />{int(p.completed)} <span className="muted">/ {int(p.total)}</span>
            </strong>
            <span className="muted" title="Every tier reached, added up across all challenges (a challenge can give up to 4)">{int(p.medals)} tiers</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The medal's icon in the colour of the tier earned (like the badge cards); uploaded and "colour_" art keep their own colours. */
function RecentIcon({ icon, medal }: { icon: string | null; medal: string | null }) {
  const src = `/achievements/${icon ?? "happy_cubesat.png"}`;
  if (keepsColours(icon)) return <img src={src} alt="" />;
  // an <i>, not a <span>: the card's text column is styled as its first span (styles.css .recent-unlocks li > span:first-of-type)
  return <i className={`recent-glyph t-${medal ?? "crown"}`} style={{ WebkitMaskImage: `url(${src})`, maskImage: `url(${src})` }} aria-hidden="true" />;
}

function RecentUnlocks() {
  const recent = useRanking(getRecentUnlocks, "recent");
  const avatars = useAvatars(recent.data?.map((e) => e.user_id) ?? []);
  if (!recent.data || recent.data.length === 0) return null;
  return (
    <div className="ach-pane">
      <div className="section-head"><h2>Recent tiers reached</h2></div>
      <ul className="recent-unlocks" tabIndex={0} aria-label="Recent tiers reached, scroll sideways">
        {recent.data.map((e, i) => (
          // fewer words (user, 2026-11-27): the tier chip alone, the rule is hover text
          <li key={`${e.user_id}-${e.id}-${i}`} title={medalRuleText(e.description, e.medal)}>
            <span className="rank">{dateTime(e.at)}</span>
            <span className="who"><Avatar name={e.name} url={avatars[e.user_id]} size={32} /><Link to={achievementsPath(e.user_id, e.name)} className="name">{e.name}</Link></span>
            <strong className="big"><RecentIcon icon={e.icon} medal={e.medal} />{e.achievement}</strong>
            <span><span className={`medal-chip ${e.medal ?? "gold"}`}>{e.medal ?? "completed"}</span></span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Catalogue() {
  const rules = useApi(getRarity, "catalogue");
  const w = useApi(getChallenges, "challenge").data;
  return (
    <>
      <div className="section-head">
        {/* the challenge period in small text by the heading (user, 2026-11-27) */}
        <h2>
          All challenges
          {w?.start && (
            <small className="muted period-note" title="Only matches played inside this period count for challenges">
              {dateTime(w.start)} → {w.end ? dateTime(w.end) : "open-ended"}
            </small>
          )}
        </h2>
        <ScrollToNew ready={!!rules.data} />
      </div>
      <Status loading={rules.loading} error={rules.error} />
      {rules.data && <GroupedBadges items={rules.data} />}
    </>
  );
}

export function AchievementsPage() {
  usePageTitle("Challenges");
  const { visible, start, total, peek } = useAchievementsAccess();
  if (visible === null) return null;
  if (!visible)
    return (
      <section>
        <h1>Flamingo Challenges &amp; Mega Prizes</h1>
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
  usePageTitle(d ? `Challenges · ${d.name}` : "Challenges");

  // show the player's own address, /challenges/<name>/<id>: old ?player= links, an outdated name and a merged ID all
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
        <h1>Flamingo Challenges &amp; Mega Prizes{player && name.data && <span className="muted"> · {name.data.name}</span>}</h1>
        {/* one link back (user, 2026-11-27): "All challenges" is already in the site menu */}
        {player && (
          <Link to={d ? playerPath(d.user_id, d.name) : `/players/${encodeURIComponent(player)}`}>← Player profile</Link>
        )}
        {!player && <PlayerPicker />}
      </div>
      <MyChallengesButton viewing={d?.user_id ?? null} />
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
          </div>
          <div className="ach-duo">
            <TopPlayers />
            <RecentUnlocks />
          </div>
          <Catalogue />
          <AchievementRules />
        </>
      )}
    </section>
  );
}
