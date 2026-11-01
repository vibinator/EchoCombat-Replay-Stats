import { lazy, Suspense, useEffect, useState, useSyncExternalStore } from "react";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router";
import { connection, getHealth, getMe, getProcessing, loginUrl, LOGOUT_URL } from "./api";
import { GlobalSearch } from "./components/GlobalSearch";
import { HomePage } from "./pages/HomePage";
import { useAchievementsAccess } from "./components/AchievementsView";
import { ErrorBoundary, Skeleton } from "./components/ui";
import { useApi, useWhileVisible } from "./useApi";

// Pages other than home load on first visit: the first page view downloads less.
const AchievementsPage = lazy(() => import("./pages/AchievementsPage").then((m) => ({ default: m.AchievementsPage })));
const ComparePage = lazy(() => import("./pages/ComparePage").then((m) => ({ default: m.ComparePage })));
const ConsolePage = lazy(() => import("./pages/ConsolePage").then((m) => ({ default: m.ConsolePage })));
const LeaderboardPage = lazy(() => import("./pages/LeaderboardPage").then((m) => ({ default: m.LeaderboardPage })));
const MatchPage = lazy(() => import("./pages/MatchPage").then((m) => ({ default: m.MatchPage })));
const MatchesPage = lazy(() => import("./pages/MatchesPage").then((m) => ({ default: m.MatchesPage })));
const PermissionsPage = lazy(() => import("./pages/PermissionsPage").then((m) => ({ default: m.PermissionsPage })));
const PlayerPage = lazy(() => import("./pages/PlayerPage").then((m) => ({ default: m.PlayerPage })));
const PlayersPage = lazy(() => import("./pages/PlayersPage").then((m) => ({ default: m.PlayersPage })));
const StatusPage = lazy(() => import("./pages/StatusPage").then((m) => ({ default: m.StatusPage })));

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
  return (
    <section>
      <h1>Page not found</h1>
      <Link to="/">Go to the home page</Link>
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

const NAV = [
  ["/", "Home"],
  ["/matches", "Matches"],
  ["/players", "Players"],
  ["/leaderboard", "Leaderboard"],
  ["/achievements", "Achievements"],
  ["/compare", "Compare"],
] as const;

function Layout() {
  const [theme, toggleTheme] = useTheme();
  const version = useApi(getHealth, "health").data?.version;
  const pending = usePendingReplays();
  const achievements = useAchievementsAccess();
  const me = useApi(getMe, "me").data;
  const user = me?.user;
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMenuOpen(false), [location.pathname]);

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          EchoVR Replay Stats
        </Link>
        <ProcessingIndicator pending={pending} />
        <ConnectionNote />
        <button className="menu-toggle secondary" aria-expanded={menuOpen} aria-controls="main-nav" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? "Close" : "Menu"}
        </button>
        <nav id="main-nav" className={menuOpen ? "open" : ""}>
          {[
            ...NAV,
            ...(user?.admin || user?.console ? ([["/status", "Status"]] as const) : []),
            ...(user?.console
              ? ([
                  ["/console", "Console"],
                  ["/permissions", "Permissions"],
                ] as const)
              : []),
          ].map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
              {to === "/achievements" && achievements.visible === false && (
                <span className="tag" title={achievements.total ? `${achievements.total} achievements available` : undefined}>
                  Coming soon{achievements.total ? ` · ${achievements.total}` : ""}
                </span>
              )}
              {to === "/achievements" && achievements.preview && <span className="tag">preview</span>}
            </NavLink>
          ))}
        </nav>
        <GlobalSearch />
        <button className="theme-toggle secondary" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
        {user ? (
          <span className="account muted">
            {user.name} · <a href={LOGOUT_URL}>Log out</a>
          </span>
        ) : (
          me?.enabled && (
            <a className="button discord-login" href={loginUrl(location.pathname + location.search)}>
              Log in with Discord
            </a>
          )
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
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/achievements" element={<AchievementsPage />} />
          <Route path="/console" element={<ConsolePage />} />
          <Route path="/permissions" element={<PermissionsPage />} />
          <Route path="/status" element={<StatusPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        </Suspense>
        </ErrorBoundary>
      </main>
      <footer>
        Inspired by ECRanked, the original Echo Combat stats site. · Press <kbd>/</kbd> to search
        {version && <> · {version}</>}
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
