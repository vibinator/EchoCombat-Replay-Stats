import { useEffect, useState } from "react";
import { BrowserRouter, Link, NavLink, Route, Routes, useLocation } from "react-router";
import { getHealth, getProcessing } from "./api";
import { GlobalSearch } from "./components/GlobalSearch";
import { AchievementsPage } from "./pages/AchievementsPage";
import { ComparePage } from "./pages/ComparePage";
import { HomePage } from "./pages/HomePage";
import { LeaderboardPage } from "./pages/LeaderboardPage";
import { MatchPage } from "./pages/MatchPage";
import { MatchesPage } from "./pages/MatchesPage";
import { PlayerPage } from "./pages/PlayerPage";
import { PlayersPage } from "./pages/PlayersPage";
import { useApi } from "./useApi";

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

const PROCESSING_POLL_MS = 15_000;

/** Number of replays still waiting to be read; polled so the top bar shows when new data is on its way. */
function usePendingReplays(): number {
  const [pending, setPending] = useState(0);
  useEffect(() => {
    let current = true;
    const poll = () =>
      getProcessing()
        .then((d) => current && setPending(d.pending))
        .catch(() => current && setPending(0));
    poll();
    const timer = setInterval(poll, PROCESSING_POLL_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, []);
  return pending;
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
        <button className="menu-toggle secondary" aria-expanded={menuOpen} aria-controls="main-nav" onClick={() => setMenuOpen(!menuOpen)}>
          {menuOpen ? "Close" : "Menu"}
        </button>
        <nav id="main-nav" className={menuOpen ? "open" : ""}>
          {NAV.map(([to, label]) => (
            <NavLink key={to} to={to} end={to === "/"}>
              {label}
            </NavLink>
          ))}
        </nav>
        <GlobalSearch />
        <button className="theme-toggle secondary" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
          {theme === "dark" ? "Light" : "Dark"}
        </button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/matches" element={<MatchesPage />} />
          <Route path="/matches/:id" element={<MatchPage />} />
          <Route path="/players" element={<PlayersPage />} />
          <Route path="/players/:userId" element={<PlayerPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/leaderboard" element={<LeaderboardPage />} />
          <Route path="/achievements" element={<AchievementsPage />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
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
