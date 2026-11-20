import { lazy, Suspense, useEffect, useRef, useState, useSyncExternalStore, type ComponentType } from "react";
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes, useLocation } from "react-router";
import { connection, getHealth, getMe, getProcessing, loginUrl, LOGOUT_URL, reloadOnce, siteUpdate } from "./api";
import { dateTime, viewerZone } from "./format";
import { GlobalSearch } from "./components/GlobalSearch";
import { HomePage } from "./pages/HomePage";
import { useAchievementsAccess } from "./achievementsAccess";
import { ErrorBoundary, Skeleton } from "./components/ui";
import { useApi, useWhileVisible } from "./useApi";
import { usePageTitle } from "./usePageTitle";

const PAGE_RETRY_MS = 1_500;

/** A page loaded on first visit (the first page view downloads less). Its file can fail to load: the server was busy
 *  or restarting for a moment (asked once more), or the site was updated since this tab opened and the file is gone
 *  (the tab is reloaded, which loads the current site: the skeleton stays until then). Before 2026-11-10 either one
 *  ended in "Something went wrong showing this page" until the visitor reloaded by hand. */
/** `route`: the addresses this page answers to. A page whose file is already here is shown at once, without the loading
 *  skeleton: React holds a page back until 300 ms after its skeleton appeared, however quickly the file arrives
 *  (measured 2026-11-16: every first visit and every first click on a menu item waited for that). So the file of the
 *  page being opened is fetched before the first render (preloadPage, main.tsx), and the main pages' files once the
 *  browser is idle (preloadMainPages). */
const pageFiles: { route: RegExp; main: boolean; fetch: () => Promise<unknown> }[] = [];

function page<M>(load: () => Promise<M>, pick: (m: M) => ComponentType, route: RegExp, main = false) {
  let ready: ComponentType | null = null;
  let asked: Promise<M> | null = null;
  const once = () =>
    (asked ??= load().then(
      (m) => {
        ready = pick(m);
        return m;
      },
      (e: unknown) => {
        asked = null; // asked again next time
        throw e;
      },
    ));
  const Lazy = lazy(() =>
    once()
      .catch(() => new Promise<M>((done, fail) => setTimeout(() => once().then(done, fail), PAGE_RETRY_MS)))
      .catch((e: unknown) => {
        if (reloadOnce()) return new Promise<M>(() => undefined);
        throw e;
      })
      .then((m) => ({ default: pick(m) })),
  );
  pageFiles.push({ route, main, fetch: once });
  return function Page() {
    const Ready = ready;
    return Ready ? <Ready /> : <Lazy />;
  };
}

const AchievementsPage = page(() => import("./pages/AchievementsPage"), (m) => m.AchievementsPage, /^\/(challenges?|achievements)(\/|$)/, true);
const CombatMatchPage = page(() => import("./pages/CombatPage"), (m) => m.CombatMatchPage, /^\/combat\/./);
const ConsolePage = page(() => import("./pages/ConsolePage"), (m) => m.ConsolePage, /^\/console$/);
const ProfilePage = page(() => import("./pages/ProfilePage"), (m) => m.ProfilePage, /^\/profile$/);
const LeaderboardPage = page(() => import("./pages/LeaderboardPage"), (m) => m.LeaderboardPage, /^\/leaderboard$/, true);
const MatchPage = page(() => import("./pages/MatchPage"), (m) => m.MatchPage, /^\/matches\/./, true);
const MatchesPage = page(() => import("./pages/MatchesPage"), (m) => m.MatchesPage, /^\/matches$/, true);
const PermissionsPage = page(() => import("./pages/PermissionsPage"), (m) => m.PermissionsPage, /^\/permissions$/);
const PlayerPage = page(() => import("./pages/PlayerPage"), (m) => m.PlayerPage, /^\/players\/./, true);
const CloudPage = page(() => import("./pages/CloudPage"), (m) => m.CloudPage, /^\/cloud$/);
const PlayersPage = page(() => import("./pages/PlayersPage"), (m) => m.PlayersPage, /^\/players$/);

const PRELOAD_WAIT_MS = 3_000;

/** Resolves once the file of the page at `pathname` is here (or failed, or took too long: the page then loads the
 *  usual way, behind its skeleton). */
export function preloadPage(pathname: string): Promise<void> {
  const file = pageFiles.find((f) => f.route.test(pathname));
  if (!file) return Promise.resolve();
  return Promise.race([file.fetch().then(() => undefined, () => undefined), new Promise<void>((done) => setTimeout(done, PRELOAD_WAIT_MS))]);
}

/** The main pages' files, fetched when the browser has nothing else to do: the first click on Matches, Leaderboard,
 *  a player or a match then shows the page at once. Not on a connection that asks to save data. */
function preloadMainPages(): void {
  const saveData = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection?.saveData;
  if (saveData) return;
  for (const file of pageFiles) if (file.main) file.fetch().catch(() => undefined);
}

type Theme = "dark" | "light";
const THEME_KEY = "echovr-theme";

function storedTheme(): Theme | null {
  try {
    const t = localStorage.getItem(THEME_KEY);
    return t === "light" || t === "dark" ? t : null;
  } catch {
    return null;
  }
}

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(
    () => storedTheme() ?? (window.matchMedia?.("(prefers-color-scheme: light)").matches ? "light" : "dark"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch {
      /* storage unavailable */
    }
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

function NotFound() {
  usePageTitle("Page not found");
  return (
    <section className="not-found">
      <h1>Page not found</h1>
      <p className="links"><Link to="/">Go to the home page</Link><Link to="/matches">All matches</Link></p>
    </section>
  );
}

const PROCESSING_POLL_MS = 60_000; // the count changes slowly; a hidden tab does not ask at all

/** Number of replays still waiting to be read; polled so the top bar shows when new data is on its way. */
function usePendingReplays(): number {
  const [pending, setPending] = useState(0);
  useWhileVisible(() => {
    getProcessing()
      .then((d) => setPending(d.pending))
      .catch(() => setPending(0));
  }, PROCESSING_POLL_MS);
  return pending;
}

/** The server did not answer (busy or offline): pages keep showing what they have. */
function ConnectionNote() {
  const unreachable = useSyncExternalStore(connection.subscribe, connection.unreachable);
  if (!unreachable) return null;
  return (
    <span className="processing unreachable" role="status" title="The server is busy or out of reach. Pages show the data they already have and refresh by themselves once it answers again.">
      <span className="processing-text">Server busy · showing saved data</span>
    </span>
  );
}

function ProcessingIndicator({ pending }: { pending: number }) {
  if (pending === 0) return null;
  const text = `Processing ${pending.toLocaleString()} replay${pending === 1 ? "" : "s"}`;
  return (
    <span className="processing" role="status" title={`${text} in the background. New matches and stats appear as they finish.`}>
      <span className="spinner" aria-hidden="true" />
      <span className="processing-text">{text}</span>
    </span>
  );
}

/** The old Compare page (user, 2026-11-16: moved to the Compare tab of a player profile). Bookmarks and shared links
 *  open the first player's Compare tab with the others, period and heatmap map kept; without a player, the Leaderboard
 *  (where players are ticked for "Compare selected"). */
function CompareRedirect() {
  const { search } = useLocation();
  const old = new URLSearchParams(search);
  const ids = (old.get("players") ?? "").split(",").filter(Boolean).slice(0, 4);
  if (!ids.length) return <Navigate replace to="/leaderboard" />;
  const next = new URLSearchParams({ tab: "compare" });
  if (ids.length > 1) next.set("vs", ids.slice(1).join(","));
  const period = old.get("period");
  if (period && period !== "all") next.set("period", period);
  const map = old.get("map");
  if (map) next.set("cmp_map", map);
  return <Navigate replace to={`/players/${encodeURIComponent(ids[0])}?${next.toString()}`} />;
}

/** The old /combat address (bookmarks, shared links) opens the Combat tab of the Leaderboard, filters kept. */
function CombatRedirect() {
  const { search } = useLocation();
  const params = new URLSearchParams(search);
  params.set("board", "combat");
  return <Navigate replace to={`/leaderboard?${params.toString()}`} />;
}

/** Achievements were renamed Challenges (user, 2026-11-20): /achievements/... and /challenge/... links (shared, bookmarked,
 *  or a Discord login's return address) open the same page under /challenges, keeping the player, query and anchor. */
function ChallengesRedirect() {
  const { pathname, search, hash } = useLocation();
  return <Navigate replace to={`${pathname.replace(/^\/(achievements|challenge)(?=\/|$)/, "/challenges")}${search}${hash}`} />;
}

const NAV = [
  ["/", "Home"],
  ["/matches", "Matches"],
  ["/leaderboard", "Leaderboard"],
  ["/challenges", "Challenges"],
] as const;

/** "2026-11-01T17:05" (UK time, bump_version.py) -> "1 Nov 2026, 17:05" on the viewer's clock */
function released(iso: string): string {
  const [date, time] = dateTime(iso).split(" ");
  const [y, m, d] = date.split("-").map(Number);
  const month = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1];
  return `${d} ${month} ${y}, ${time}`;
}

function Layout() {
  const [theme, toggleTheme] = useTheme();
  const health = useApi(getHealth, "health").data;
  const pending = usePendingReplays();
  const achievements = useAchievementsAccess();
  const me = useApi(getMe, "me").data;
  const user = me?.user;
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);
  // The site was updated while this tab was open (api.ts, site updates): the next page change loads the new version,
  // instead of old pages meeting new answers and page files that no longer exist
  useEffect(() => {
    const idle = window.requestIdleCallback ?? ((fn: () => void) => window.setTimeout(fn, 1));
    const timer = window.setTimeout(() => idle(preloadMainPages), 1_500); // after the page's own data and pictures
    return () => window.clearTimeout(timer);
  }, []);
  const opened = useRef(location.pathname);
  useEffect(() => {
    if (location.pathname !== opened.current && siteUpdate.available()) reloadOnce();
    opened.current = location.pathname;
  }, [location.pathname]);

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          Echo Combat Stats
        </Link>
        <ProcessingIndicator pending={pending} />
        <ConnectionNote />
        <button className="menu-toggle secondary" aria-expanded={menuOpen} aria-controls="main-nav" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? "Close" : "Menu"}
        </button>
        <nav id="main-nav" className={menuOpen ? "open" : ""}>
          {[
            ...NAV,
            ...(user?.cloud ? ([["/cloud", "Cloud"]] as const) : []),
            ...(user?.console
              ? ([
                  ["/console", "Console"],
                ] as const)
              : []),
          ].map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
              {to === "/challenges" && achievements.visible === false && (
                <span className="tag" title={achievements.total ? `${achievements.total} challenges available` : undefined}>
                  Coming soon{achievements.total ? ` · ${achievements.total}` : ""}
                </span>
              )}
              {to === "/challenges" && achievements.preview && <span className="tag">preview</span>}
            </NavLink>
          ))}
        </nav>
        <GlobalSearch />
        <button className="theme-toggle secondary" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        {user ? (
          <span className="account muted">{/* the name opens the profile: short enough for the top bar's one row (Review GUI-1, approved 2026-11-07) */}
            <NavLink to="/profile" title="My profile">{user.name}</NavLink> · <a href={LOGOUT_URL}>Log out</a>
          </span>
        ) : me ? (
          me.enabled && (
            <a className="button discord-login" href={loginUrl(location.pathname + location.search)}>
              Log in with Discord
            </a>
          )
        ) : (
          // holds the button's place until the server answers, so the header and page do not jump when it appears
          <a className="button discord-login login-slot" aria-hidden="true">
            Log in with Discord
          </a>
        )}
      </header>
      <main>
        <ErrorBoundary key={location.pathname}>
        <Suspense fallback={<Skeleton lines={4} />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/matches" element={<MatchesPage />} />
          <Route path="/matches/:id" element={<MatchPage />} />
          <Route path="/players" element={<PlayersPage />} />
          <Route path="/players/:userId" element={<PlayerPage />} />
          <Route path="/players/:name/:userId" element={<PlayerPage />} />
          <Route path="/compare" element={<CompareRedirect />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/combat" element={<CombatRedirect />} />
          <Route path="/combat/:id" element={<CombatMatchPage />} />
          <Route path="/challenges" element={<AchievementsPage />} />
          <Route path="/challenges/:userId" element={<AchievementsPage />} />
          <Route path="/challenges/:name/:userId" element={<AchievementsPage />} />
          <Route path="/achievements/*" element={<ChallengesRedirect />} />
          <Route path="/challenge/*" element={<ChallengesRedirect />} />
          <Route path="/mega-prizes" element={<Navigate to="/challenges" replace />} />
          <Route path="/profile"element={<ProfilePage />} />
          <Route path="/console" element={<ConsolePage />} />
          <Route path="/cloud" element={<CloudPage />} />
          <Route path="/permissions" element={<PermissionsPage />} />
          <Route path="/status" element={<Navigate to="/console" replace />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        </Suspense>
        </ErrorBoundary>
      </main>
      <footer>
        {health && <span title={`Version ${health.build}`}>{health.version} · {released(health.released)}</span>}
        <div className="muted footer-time">Times are in your timezone ({viewerZone()}). "Today", "This week", charts and challenge days use UK time.</div>
      </footer>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}
