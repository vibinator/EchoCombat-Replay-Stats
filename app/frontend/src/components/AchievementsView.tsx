import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";
import { LEVELS, getAchievements, getArenaProgress, getChallenges, searchMegaPrizes, type MegaPrizeSearch as SearchResult, getMe, getRarity, loginUrl, type Achievement, type AchievementPeek, type AchievementRarity, type AchievementRule } from "../api";
import { achievementsPath, pct, ruleText } from "../format";
import { useApi } from "../useApi";
import { Status } from "./common";
import { EmptyState } from "./ui";

// Old ecranked.com badge art (app/images -> public/achievements). Tier frames = progress levels
// 25 / 50 / 75 / 100 % (white / bronze / silver / gold); the lock emblem = below 25 %.
const IMG = "/achievements/";
const GENERIC_ICON = "happy_cubesat.png";
export const GROUPS: [Achievement["period"], string][] = [
  ["game", "In one game"],
  ["day", "In one day"],
  ["week", "In any 7 days"],
  ["all", "All time"],
];

// New achievements (not on the original site) get their own sections, in this order. Merged (user, 2026-11-04): each section lists
// the themes it holds (a challenge's `group`).
export const NEW_GROUPS: [name: string, hint: string, groups: string[]][] = [
  ["Gear", "Experimental weapons and ordnances (never released), and using all four weapons, ordnances or tac mods in one game", ["Experimental gear", "Gear mastery"]],
  ["Modes & wins", "Winning, streaks, and Payload and Capture Point play", ["Wins", "Payload", "Capture Point"]],
  ["Combat", "Kills, assists, damage and objective play, from the game's own counters in the recorder's match reports, from 4 November 2026 on, apart from the replay stats. Targets are provisional. These do not count toward your average progress, totals or Medal Collector.", ["Combat"]],
];

// Survival, Movement, Emotes and Activity are not themes any more (user, 2026-11-04): their challenges sit with the others of the same
// period (mostly "In one game"; the all-time ones, Activity included, under "All time").
const BY_PERIOD = new Set(["Survival", "Movement", "Emotes", "Activity", "Gear in one game"]);
const GEAR_GROUPS = new Set(["Experimental gear", "Gear mastery"]);
/** Shown under its period (in one game / day / any 7 days / all time) rather than a theme: the old rules, a few themes, and the
 *  "any 7 days" gear challenges (user, 2026-11-04). */
const inPeriodSection = (a: { new: boolean; group: string | null; period: string }) =>
  !a.new || BY_PERIOD.has(a.group ?? "") || (a.period === "week" && GEAR_GROUPS.has(a.group ?? ""));

type AnyBadge = Parameters<typeof Badge>[0]["a"];

/** Which section (tab) a challenge sits in: its period, or the theme section of a new one. */
export function sectionId(a: { new: boolean; group: string | null; period: string }): string {
  return `p-${a.period}`; // one page per period (user, 2026-11-06); the theme is a filter inside it, see themeOf
}

/** Theme chip of a challenge inside its period page (user, 2026-11-06: themes are filters now, not tabs). */
export function themeOf(a: { new: boolean; group: string | null; period: string }): string {
  if (!inPeriodSection(a)) return NEW_GROUPS.find(([, , gs]) => gs.includes(a.group ?? ""))?.[0] ?? "More";
  return a.new ? "Other new" : "Original";
}

/** The four pages (user, 2026-11-06): game, day, week, cumulative (= all time). */
const PAGE_LABELS: Record<string, string> = { game: "Game", day: "Day", week: "Week", all: "Cumulative" };
const NEW_CHIP = "__new";

type Filter = "done" | "open" | "new";
const FILTERS: [Filter, string][] = [["open", "In progress"], ["new", "Not started"], ["done", "Completed"]];

/** Where a player stands: completed (100 %), in progress, or not started. Catalogue entries (no progress) have none. */
function status(a: AnyBadge): Filter | null {
  if (a.progress === undefined) return null;
  return a.progress >= 1 ? "done" : a.progress > 0 ? "open" : "new";
}

type SortBy = "default" | "closest" | "complete" | "rarest" | "name";
type Shares = Map<number, number | null>;

/** Order of the cards in a section. Default: a player's list is closest-to-the-next-medal first, a catalogue keeps the rule order. */
function sortItems<T extends AnyBadge>(list: T[], by: SortBy, tracked: boolean, shares: Shares): T[] {
  const out = [...list];
  const closest = (x: T) => nextMedalFraction(x as unknown as Achievement) ?? 0;
  if (by === "complete") return out.sort((x, y) => (y.progress ?? 0) - (x.progress ?? 0)); // overall progress over all tiers
  if (by === "name") return out.sort((x, y) => x.name.localeCompare(y.name));
  if (by === "rarest") return out.sort((x, y) => (shares.get(x.id) ?? 1) - (shares.get(y.id) ?? 1));
  if (by === "closest" || (by === "default" && tracked)) return out.sort((x, y) => closest(y) - closest(x));
  return out;
}

/** The challenges of one tab, and (for a player) filters Completed / In progress / Not started. Completed achievements are
 *  hidden until you pick Completed; the view opens on the first filter that has something. `only` is the status picked for
 *  the whole page (it replaces the pills). */
function Section<T extends AnyBadge>({ label, items, only, sort, shares }: { label: string; items: T[]; only: Filter | ""; sort: SortBy; shares: Shares }) {
  const [picked, setPicked] = useState<Filter | null>(null);
  const tracked = items.every((a) => status(a) !== null);
  const counts = { done: 0, open: 0, new: 0 };
  if (tracked) for (const a of items) counts[status(a)!]++;
  const filter = only || picked || FILTERS.find(([f]) => counts[f] > 0)?.[0] || "open";
  const shown = sortItems(tracked ? items.filter((a) => status(a) === filter) : items, sort, tracked, shares);
  const overall = tracked ? items.reduce((sum, a) => sum + (a.progress ?? 0), 0) / items.length : 0;
  return (
    <div className="ach-panel">
      {tracked && (
        <div className="section-progress" title={`${counts.done} of ${items.length} completed, ${pct(overall)} overall`}>
          <div className="bar" style={{ "--sec": `var(--tier-${sectionMedal(overall) ?? "bar-default"})` } as React.CSSProperties} role="progressbar" aria-label={`${label} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(overall * 100)}>
            <div style={{ width: `${overall * 100}%` }} />
          </div>
          <span className="muted">{counts.done}/{items.length} completed · {pct(overall)}</span>
        </div>
      )}
      {tracked && !only && (
        <div className="tabs" role="tablist">
          {FILTERS.map(([f, text]) => (
            <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "tab active" : "tab"} onClick={() => setPicked(f)}>
              {text} ({counts[f]})
            </button>
          ))}
        </div>
      )}
      <div className="tiles" aria-label={label}>
        {shown.map((a) => <Tile key={a.id} a={a} />)}
      </div>
    </div>
  );
}

/** Original achievements by period, then the new ones by theme, in one flat list of sections. A sticky bar jumps to a
 *  section; the controls above filter (text, status, new only) and sort every section at once (user, 2026-11-04). */
export function GroupedBadges<T extends AnyBadge>({ items: all }: { items: T[] }) {
  // Mega Prize challenges are never in this list (they are not in the public rules at all, see achievements.py)
  const items = all.filter((a) => !a.prize);
  const rarity = useApi(getRarity, "rarity").data;
  const shares: Shares = new Map((rarity ?? []).map((r) => [r.id, r.unlocked_share]));
  const [q, setQ] = useState("");
  const [only, setOnly] = useState<Filter | "">("");
  const [newOnly, setNewOnly] = useState(false);
  const [sort, setSort] = useState<SortBy>("default");
  const [params, setParams] = useSearchParams();
  const { hash } = useLocation();
  const tracked = items.length > 0 && items.every((a) => status(a) !== null);
  const term = q.trim().toLowerCase();
  const visible = items.filter((a) => (!newOnly || a.new) && (!term || `${a.name} ${ruleText(a.description)}`.toLowerCase().includes(term))
    && (!tracked || !only || status(a) === only));
  const sections: { id: string; label: string; items: T[] }[] = GROUPS.map(([period]) => ({ id: `p-${period}`, label: PAGE_LABELS[period], items: [] as T[] }));
  for (const a of visible) sections.find((x) => x.id === sectionId(a))?.items.push(a);
  const shownSections = sections.filter((x) => x.items.length > 0);
  // the page comes from the address (?section=), so a link can open one; "Jump to new challenges" (#new) picks the New chip
  const wanted = params.get("section");
  const active = shownSections.find((x) => x.id === wanted) ?? shownSections[0];
  const [theme, setTheme] = useState(hash === "#new" ? NEW_CHIP : "");
  const themes = new Map<string, number>();
  for (const a of active?.items ?? []) themes.set(themeOf(a), (themes.get(themeOf(a)) ?? 0) + 1);
  const newCount = (active?.items ?? []).filter((a) => a.new).length;
  const chip = theme === NEW_CHIP ? (newCount ? NEW_CHIP : "") : themes.has(theme) ? theme : "";
  const pageItems = !active ? [] : chip === NEW_CHIP ? active.items.filter((a) => a.new) : chip ? active.items.filter((a) => themeOf(a) === chip) : active.items;
  const themeHint = (name: string) => NEW_GROUPS.find(([n]) => n === name)?.[1] ?? (name === "Original" ? "Challenges from the original ECRanked site" : "");
  function pick(id: string) {
    const next = new URLSearchParams(params);
    if (id === shownSections[0]?.id) next.delete("section");
    else next.set("section", id);
    setParams(next, { replace: true, preventScrollReset: true });
  }
  return (
    <>
      <div className="ach-toolbar">
        <input type="search" placeholder="Filter challenges" aria-label="Filter challenges" value={q} onChange={(e) => setQ(e.target.value)} />
        {tracked && (
          <select aria-label="Status" value={only} onChange={(e) => setOnly(e.target.value as Filter | "")}>
            <option value="">All statuses</option>
            {FILTERS.map(([f, text]) => (
              <option key={f} value={f}>{text}</option>
            ))}
          </select>
        )}
        <label className="inline-check">
          <input type="checkbox" checked={newOnly} onChange={(e) => setNewOnly(e.target.checked)} /> New only
        </label>
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as SortBy)}>
          <option value="default">{tracked ? "Closest to next medal" : "Original order"}</option>
          {tracked && <option value="closest">Closest to next medal (all)</option>}
          {tracked && <option value="complete">Closest to fully completed (all tiers)</option>}
          <option value="rarest">Rarest first</option>
          <option value="name">A to Z</option>
        </select>
      </div>
      {shownSections.length === 0 && <p className="muted">No challenge matches.</p>}
      {active && (
        <>
          <div className="tabs section-tabs ach-tabs" id="new" role="tablist" aria-label="Achievement groups">
            {shownSections.map((x) => (
              <button key={x.id} role="tab" aria-selected={active.id === x.id} className={active.id === x.id ? "tab active" : "tab"} onClick={() => pick(x.id)}>
                <span className="tab-label">{x.label}</span>
                <span className="tab-hint">{x.items.length}</span>
              </button>
            ))}
          </div>
          {(themes.size > 1 || newCount > 0) && (
            <div className="theme-chips" role="group" aria-label="Theme">
              <button className={chip === "" ? "chip active" : "chip"} onClick={() => setTheme("")}>All {active.items.length}</button>
              {newCount > 0 && <button className={chip === NEW_CHIP ? "chip active" : "chip"} title="Not on the original ECRanked site" onClick={() => setTheme(NEW_CHIP)}>New {newCount}</button>}
              {[...themes].map(([name, n]) => (
                <button key={name} className={chip === name ? "chip active" : "chip"} title={themeHint(name)} onClick={() => setTheme(name)}>{name} {n}</button>
              ))}
            </div>
          )}
          {tracked && <NotYetStarted items={pageItems as unknown as Achievement[]} />}
          <Section key={active.id + chip} label={active.label} items={pageItems} only={only} sort={sort} shares={shares} />
        </>
      )}
    </>
  );
}

/** The Mega Prizes section of the Achievements page: only for the Preview role (the server checks it too, so nobody else
 * even asks for the data). */
export function MegaPrizesSection() {
  const me = useApi(getMe, "me").data?.user;
  return me?.preview || me?.console ? <MegaPrizes /> : null;
}

type PrizeRow = SearchResult["results"][number];

/** Every player who reaches the target wins the prize: there can be many winners (user, 2026-11-05). */
const winnersText = (n: number, target: number) =>
  `${n === 0 ? "No winners yet" : `${n} ${n === 1 ? "winner" : "winners"} so far`}: everyone who reaches ${target} wins the prize.`;

/** Change over the last day: an arrow for the rank (up / down) and the matches gained, shown next to a player's name. */
function Move({ r }: { r: { rank_change?: number | null; gained?: number } }) {
  if (r.rank_change === undefined) return null;
  const up = (r.rank_change ?? 0) > 0;
  const down = (r.rank_change ?? 0) < 0;
  const gained = r.gained ? `+${r.gained.toLocaleString()} in the last 24 h` : "no matches in the last 24 h";
  const title = r.rank_change === null ? `New in the list, ${gained}` : up ? `Up ${r.rank_change} place${r.rank_change > 1 ? "s" : ""}, ${gained}` : down ? `Down ${-r.rank_change} place${r.rank_change < -1 ? "s" : ""}, ${gained}` : `Same place, ${gained}`;
  return (
    <span className={`move ${up ? "up" : down ? "down" : "same"}`} title={title}>
      {up ? "▲" : down ? "▼" : "–"}{r.rank_change ? Math.abs(r.rank_change) : ""}{r.gained ? <small> +{r.gained}</small> : null}
    </span>
  );
}

/** One player's progress inside a prize card: name, a bar and the count. */
function PlayerBar({ r, target }: { r: { name: string; user_id: string; matches: number; rank?: number; rank_change?: number | null; gained?: number }; target: number }) {
  return (
    <li>
      <span className="mega-who"><span className="mega-name" title={`${r.name} (${r.user_id})`}>{r.rank ? `${r.rank}. ` : ""}{r.name}</span><Move r={r} /></span>
      <span className="bar" role="progressbar" aria-label={`${r.name} ${r.matches} of ${target}`} aria-valuemin={0} aria-valuemax={target} aria-valuenow={r.matches}>
        <span style={{ width: `${Math.min(100, (r.matches / target) * 100)}%` }} />
      </span>
      <span className="mega-count">{r.matches} / {target}</span>
    </li>
  );
}

/** A player search of its own for one prize card (user, 2026-11-06: no shared search box at the top any more). */
function useMegaSearch(kind: PrizeRow["kind"]) {
  const [q, setQ] = useState("");
  const [found, setFound] = useState<PrizeRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setFound(null);
      return;
    }
    let live = true;
    const t = setTimeout(() => searchMegaPrizes(term).then((r: SearchResult) => live && (setFound(r.results.filter((x) => x.kind === kind).sort((x, y) => y.matches - x.matches)), setError(null)), (e: Error) => live && setError(e.message)), 300);
    return () => {
      live = false;
      clearTimeout(t);
    };
  }, [q, kind]);
  return { q, setQ, found, error };
}

/** The two prize cards, each with its own player search: the players found show inside that card with their progress bar.
 *  Public Arena is counted from the live match list, separately from Combat. */
function MegaPrizes() {
  const result = useApi(getArenaProgress, "arena-progress");
  const arena = result.data;
  const combatSearch = useMegaSearch("combat");
  const arenaSearch = useMegaSearch("arena");
  if (!arena) return null; // no Preview role (403) or still loading: the section stays hidden
  const combat = arena.combat[0];
  const combatTarget = combat?.levels?.[combat.levels.length - 1] ?? 1000;
  return (
    <div className="section mega" id="mega-prizes">
      <h2>
        Mega Prizes <span className="tag">draft</span>
      </h2>
      {arena.period.start && (
        <div className={`rec-window${arena.period.active ? "" : " ended"}`} role="note">
          <span className="rec-dates">
            {arena.period.start} → {arena.period.end ?? "open-ended"}
          </span>
          <span className="muted">Only matches played inside this period count for Mega Prizes.</span>
        </div>
      )}
      <div className="mega-cards">
        <article className="mega-card">
          <PrizePhotos prefix="d13" alt="Delta-13 from Lone Echo 2" />
          <div className="mega-body">
            <strong>Play {combatTarget} Echo Combat Matches</strong>
            <span className="tag mega-prize">Mega Prize: {combat?.prize ?? "Delta-13 from Lone Echo 2"}</span>
            {arena.period.active && <span className="live-text" title="Matches are being recorded right now">Recording live data</span>}
            <span className="muted">Only counts games of 4+ minutes with at least 3v3. Matches from the replay files before the live count started are included, linked by Discord ID.</span>
            <span className="muted">{winnersText(arena.winners_combat, combatTarget)}</span>
            <PrizeSearch s={combatSearch} />
            {combatSearch.found !== null ? (combatSearch.found.length > 0 ? (
              <ul className="mega-results scroll">{combatSearch.found.map((r) => <PlayerBar key={r.user_id} r={r} target={combatTarget} />)}</ul>
            ) : (
              <span className="muted">Nobody found.</span>
            )) : (
              arena.top_combat.length > 0 && (
                <>
                  <span className="muted">Top {arena.top_combat.length} (▲▼ = places gained or lost in the last 24 h)</span>
                  <ul className="mega-results scroll">{arena.top_combat.map((r) => <PlayerBar key={r.user_id} r={r} target={combatTarget} />)}</ul>
                </>
              )
            )}
          </div>
        </article>
        <article className="mega-card">
          <PrizePhotos prefix="jack" alt="Jack, Lone Echo" />
          <div className="mega-body">
            <strong>Play {arena.target} Public Arena Matches</strong>
            <span className="tag mega-prize">Mega Prize: Jack Series 11 from Lone Echo 1/2</span>
            {arena.period.active && <span className="live-text" title="Matches are being recorded right now">Recording live data</span>}
            <span className="muted">Only counts public matches of 4+ minutes with at least 3v3 (or 6+ players).</span>
            <span className="muted">Arena history only starts on 2026-11-04, so totals are lower than Combat.</span>
            <span className="muted">{winnersText(arena.winners_arena, arena.target)}</span>
            <PrizeSearch s={arenaSearch} />
            {arenaSearch.found !== null ? (
              arenaSearch.found.length > 0 ? (
                <ul className="mega-results scroll">{arenaSearch.found.map((r) => <PlayerBar key={r.user_id} r={r} target={arena.target} />)}</ul>
              ) : (
                <span className="muted">Nobody found.</span>
              )
            ) : (
              <>
                {arena.top_arena.length > 0 && (
                  <>
                    <span className="muted">Top {arena.top_arena.length} (▲▼ = places gained or lost in the last 24 h)</span>
                    <ul className="mega-results scroll">{arena.top_arena.map((p) => <PlayerBar key={p.user_id} r={p} target={arena.target} />)}</ul>
                  </>
                )}
              </>

            )}
          </div>
        </article>
      </div>
    </div>
  );
}

function PrizeSearch({ s }: { s: ReturnType<typeof useMegaSearch> }) {
  return (
    <div className="mega-search">
      <input type="search" placeholder="Search a player" aria-label="Search a player for this prize" value={s.q} onChange={(e) => s.setQ(e.target.value)} />
      {s.error && <p className="error">{s.error}</p>}
    </div>
  );
}

/** Front and back of a prize, side by side and zoomed in (user, 2026-11-06). The window shows part of the pictures: drag them (mouse
 *  or finger) or scroll the wheel to move up and down; both move together. Arrow keys work when it is focused. */
function PrizePhotos({ prefix, alt }: { prefix: string; alt: string }) {
  const drag = useRef<{ y: number; top: number } | null>(null);
  return (
    <div className="mega-photos" tabIndex={0} role="group" aria-label={`${alt}: drag or scroll to move up and down`}
      title="Drag or scroll to move up and down"
      onPointerDown={(e) => {
        drag.current = { y: e.clientY, top: e.currentTarget.scrollTop };
        e.currentTarget.setPointerCapture(e.pointerId);
        e.currentTarget.classList.add("dragging");
      }}
      onPointerMove={(e) => {
        if (drag.current) e.currentTarget.scrollTop = drag.current.top - (e.clientY - drag.current.y);
      }}
      onPointerUp={(e) => {
        drag.current = null;
        e.currentTarget.classList.remove("dragging");
      }}
      onPointerCancel={(e) => {
        drag.current = null;
        e.currentTarget.classList.remove("dragging");
      }}>
      <div className="mega-photos-row">
        <PrizeImage name={`${prefix}_front.png`} alt={`${alt}, front`} />
        <PrizeImage name={`${prefix}_back.png`} alt={`${alt}, back`} />
      </div>
    </div>
  );
}

/** A prize picture. It is behind the Preview role and /api answers only requests that carry X-EchoVR (scraper protection), which an
 *  <img> tag cannot send: so it is fetched with the header and shown from memory. */
function PrizeImage({ name, alt }: { name: string; alt: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    let live = true;
    fetch(`/api/arena/image/${name}`, { headers: { "X-EchoVR": "1" } })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((b) => {
        url = URL.createObjectURL(b);
        if (live) setSrc(url);
      })
      .catch(() => undefined);
    return () => {
      live = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [name]);
  return src ? <img src={src} alt={alt} /> : <div className="mega-img-placeholder" role="img" aria-label={alt} />;
}

/** Link to the new-challenges tabs; also opens and scrolls there when the page is opened with #new (data loads late). */
export function JumpToNew({ ready }: { ready: boolean }) {
  const { hash } = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    if (ready && hash === "#new") document.getElementById("new")?.scrollIntoView();
  }, [ready, hash]);
  return (
    <a className="jump-new" href="#new" onClick={(e) => {
      e.preventDefault();
      navigate({ hash: "#new" }, { replace: true });
      setTimeout(() => document.getElementById("new")?.scrollIntoView({ behavior: "smooth" }), 50);
    }}>
      Jump to new challenges ↓
    </a>
  );
}

/** Percentage-tiered rules: medals at 25 / 50 / 75 / 100 % of the way. */
const PERCENT_STEPS = [{ medal: "white", at: 0.25 }, { medal: "bronze", at: 0.5 }, { medal: "silver", at: 0.75 }, { medal: "gold", at: 1 }];

/** One segment per medal, each filled in its own colour with the target underneath, so the progress to every
 *  tier is visible (user, 2026-10-31). Tiered rules segment by count, the others by percentage. */
function TierSteps({ a }: { a: Achievement & AchievementRule }) {
  const steps =
    a.levels && a.count != null
      ? a.levels.map((need, i) => {
          const prev = i ? a.levels![i - 1] : 0;
          return { medal: LEVELS[i], label: `${need.toLocaleString()}${a.unit ?? ""}`, fill: Math.max(0, Math.min(1, (a.count! - prev) / (need - prev))) };
        })
      : PERCENT_STEPS.map((s, i) => {
          const prev = i ? PERCENT_STEPS[i - 1].at : 0;
          return { medal: s.medal, label: `${Math.round(s.at * 100)}%`, fill: Math.max(0, Math.min(1, (a.progress - prev) / (s.at - prev))) };
        });
  return (
    <div className="tier-steps" role="progressbar" aria-valuenow={Math.round(a.progress * 100)} aria-label={a.name}>
      {steps.map((s) => (
        <div key={s.medal} className={`step t-${s.medal}${s.fill >= 1 ? " done" : ""}`} title={`${s.medal}: ${s.label}`}>
          <div className="seg"><div style={{ width: `${s.fill * 100}%` }} /></div>
          <span>{s.label}</span>
        </div>
      ))}
    </div>
  );
}

/** The next medal a player is heading for and how far along it is (0..1); null = every medal reached, or not started.
 *  Ladders: between the previous target and the next one; single-step rules: between the percentage steps. */
function nextMedal(a: Achievement): { fraction: number; medal: string } | null {
  let fraction: number;
  let medal: string;
  if (a.levels && a.count != null) {
    const next = a.levels.findIndex((need) => a.count! < need);
    if (next < 0) return null;
    const prev = next ? a.levels[next - 1] : 0;
    fraction = (a.count - prev) / (a.levels[next] - prev);
    medal = LEVELS[next];
  } else {
    const next = PERCENT_STEPS.findIndex((s) => a.progress < s.at);
    if (next < 0) return null;
    const prev = next ? PERCENT_STEPS[next - 1].at : 0;
    fraction = (a.progress - prev) / (PERCENT_STEPS[next].at - prev);
    medal = PERCENT_STEPS[next].medal;
  }
  return fraction > 0 ? { fraction, medal } : null;
}

function nextMedalFraction(a: Achievement): number | null {
  return nextMedal(a)?.fraction ?? null;
}

/** Medal colour of a section's overall progress (ladders give 25 % per medal: bronze 25 ... crown 100 %). */
function sectionMedal(progress: number): string | null {
  return progress >= 1 ? "crown" : progress >= 0.75 ? "platinum" : progress >= 0.5 ? "gold" : progress >= 0.25 ? "bronze" : null;
}

const EASY_SHOWN = 12;
const MIN_SHARE = 0.05; // at least 5% of players

/** First thing a player sees: challenges they have not started yet that most players unlock first (the highest share of
 *  players with a medal), in a row that scrolls sideways (user, 2026-11-03; it replaced "Closest to your next medal").
 *  Hidden until that share is loaded; only challenges with a medal for at least 5% of players are offered. */
function NotYetStarted({ items }: { items: Achievement[] }) {
  const rarity = useApi(getRarity, "rarity").data;
  if (!rarity) return null; // without the share of players per challenge, near-impossible ones could be offered
  const share = new Map(rarity.map((r) => [r.id, r.unlocked_share]));
  // only challenges a real share of players has a medal for (GUI test 2026-11-03: Overcharge, Dot Field... were offered)
  const easy = items
    .filter((a) => a.progress === 0 && (share.get(a.id) ?? 0) >= MIN_SHARE)
    .sort((x, y) => (share.get(y.id) ?? 0) - (share.get(x.id) ?? 0) || (x.levels?.[0] ?? 1) - (y.levels?.[0] ?? 1))
    .slice(0, EASY_SHOWN);
  if (easy.length === 0) return null;
  return (
    <section className="closest">
      <h3>Not yet started <span className="muted hint">· the easiest ones to begin with</span></h3>
      <div className="badges scroll-row" tabIndex={0} aria-label="Not yet started, scroll sideways">
        {easy.map((a) => (
          <div key={a.id} className="next-card" style={{ "--next": "var(--tier-bronze)" } as React.CSSProperties} title="First medal: bronze">
            <Badge a={a} />
          </div>
        ))}
      </div>
    </section>
  );
}

const CLOSE_FROM = 0.5; // half or more of all tiers done counts as close to fully completed
const CLOSE_HUE_FAR = 50; // yellow
const CLOSE_HUE_NEAR = 130; // green

/** A card close to its next medal is highlighted in its own list, yellow to green as it nears the medal (user, 2026-11-05;
 *  it replaced the "Close to a medal" row). Null = not close, or a catalogue entry without progress. */
function closeness(a: Parameters<typeof Badge>[0]["a"]): { hue: number; label: string } | null {
  if (a.progress === undefined || a.progress >= 1) return null;
  // shaded by overall progress over all tiers (user, 2026-11-05): green = nearly fully completed
  if (a.progress < CLOSE_FROM) return null;
  const nearness = (a.progress - CLOSE_FROM) / (1 - CLOSE_FROM);
  return {
    hue: Math.round(CLOSE_HUE_FAR + nearness * (CLOSE_HUE_NEAR - CLOSE_HUE_FAR)),
    label: `${Math.floor(a.progress * 100)}% of the way to fully completed (all tiers)`,
  };
}

/** A rule with a player's progress, or just the catalogue entry when `progress` is absent. */
/** Tiered achievements: "13 more to reach diamond", or the top medal once every target is reached. */
function levelText(count: number, levels: number[], unit = ""): string {
  const next = levels.findIndex((need) => count < need);
  if (next < 0) return `${count.toLocaleString()}${unit} · ${LEVELS[levels.length - 1]} (max)`;
  const left = Math.round(Math.max(levels[next] - count, 0) * 100) / 100; // count arrives rounded to 2 decimals
  const shown = Number.isInteger(left) ? left : Math.ceil(left * 10) / 10; // round up: "0.0 more" would be wrong
  return `${shown.toLocaleString()}${unit} more to reach ${LEVELS[next]}`;
}

export function Badge({ a, compact = false }: { a: AchievementRule & Partial<Pick<Achievement, "progress" | "tier" | "unlocked_at" | "count" | "try_next">> & Partial<Pick<AchievementRarity, "unlocked_share" | "completed_share">>; compact?: boolean }) {
  const tier = a.tier ?? null;
  const catalogue = a.progress === undefined;
  const frame = tier ? `${tier}.png` : "white_lock.png";
  const src = IMG + (a.icon ?? GENERIC_ICON);
  // The glyph takes the colour of the tier reached; grey = not started, plain = started, no tier yet (user,
  // 2026-11-02). Built-in art is one colour on transparent, so it is used as a mask; uploads keep their own colours.
  const state = catalogue ? "" : tier ? " tinted" : a.progress! > 0 ? " tinted started" : " not-started";
  const tinted = state.includes("tinted") && a.icon != null && !a.icon.startsWith("custom/");
  const close = closeness(a);
  return (
    <div className={`badge-card${compact ? " compact" : ""}${tier || catalogue ? "" : " locked"}${tier ? ` t-${tier}` : ""}${tinted ? state : state.replace(" tinted", "")}${close ? " close" : ""}`}
      style={close ? ({ "--close-hue": close.hue } as React.CSSProperties) : undefined}
      title={`${ruleText(a.description)}${a.estimated ? " (estimated)" : ""}${close ? ` · ${close.label}` : ""}`}>
      <div className="badge-art">
        {tinted ? (
          <span className="icon glyph" style={{ WebkitMaskImage: `url(${src})`, maskImage: `url(${src})` }} aria-hidden="true" />
        ) : (
          <img className="icon" src={src} alt="" />
        )}
        {!catalogue && <img className="tier" src={IMG + frame} alt={tier ?? "locked"} />}
      </div>
      <div className="badge-text">
        <strong>
          {a.name}
          {a.new && <span className="tag" title="Not on the original ECRanked site: uses data it never read">new</span>}
        </strong>
        <span className="muted rule-text">
          {ruleText(a.description)}
          {a.estimated && " *"}
        </span>
        {compact && (
          <span className="tile-pct" title={catalogue ? "Share of players who have unlocked it" : "Overall progress, counting every medal"}>
            {catalogue ? (a.unlocked_share != null ? `${pct(a.unlocked_share)} of players` : "") : pct(a.progress)}
          </span>
        )}
        {catalogue && <TierSteps a={{ ...a, progress: 0, count: 0, tier: null } as unknown as Achievement & AchievementRule} />}
        {a.prize && <span className="tag mega-prize" title="Mega Prize for completing this challenge">Mega Prize: {a.prize}</span>}
        {!catalogue && (
          <>
            <TierSteps a={a as Achievement & AchievementRule} />
            <span className="muted">
              {a.levels && a.count != null ? (
                <>
                  {levelText(a.count, a.levels, a.unit)}
                  {tier && a.progress! < 1 && <b className="tier-name"> · {tier}</b>}
                </>
              ) : (
                <>
                  {pct(a.progress)}
                  {tier && <b className="tier-name"> · {tier}</b>}
                </>
              )}
              {a.unlocked_at && ` · completed ${a.unlocked_at}`}
            </span>
          </>
        )}
        {close && (
          <span className="close-reason" title="Shaded yellow to green by how close this challenge is to being fully completed (every tier)">
            Highlighted: {close.label}
          </span>
        )}
        {!catalogue && a.try_next && a.try_next.length > 0 && a.progress! < 1 && (
          <span className="muted try-next">
            Try next:{" "}
            {a.try_next.map((l, i) => (
              <span key={l.label}>
                {i > 0 && " · "}
                <Link to={`/leaderboard?stat=loadout&weapon=${l.weapon}&ordnance=${l.ordnance}&tacmod=${l.tacmod}`} title="Who plays this loadout most">{l.label}</Link>
              </span>
            ))}
          </span>
        )}
        {a.rules && a.rules.length > 0 && <span className="muted rule-notes">{a.rules.join(" · ")}</span>}
        {a.unlocked_share != null && (
          <details className="card-more">
            <summary>Rarity</summary>
            <span className="muted rarity" title="Share of players with 10+ games">
              {pct(a.unlocked_share)} unlocked · {pct(a.completed_share)} completed
            </span>
          </details>
        )}
      </div>
    </div>
  );
}

/** A compact tile (user, 2026-11-06): art, name and the medal bar. Everything else (description, rules, targets, rarity) is in a
 *  popover: it shows on hover or keyboard focus, and a tap on a touch screen opens / closes it. */
function Tile({ a }: { a: AnyBadge }) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false); // closed with the cross while the mouse is still over the tile: stays shut until it leaves
  const [side, setSide] = useState("mid");
  function place(el: HTMLElement) {
    const r = el.getBoundingClientRect();
    setSide(r.left < 170 ? "left" : window.innerWidth - r.right < 170 ? "right" : "mid");
  }
  function close() {
    setOpen(false);
    setDismissed(true);
  }
  return (
    <div className={`tile${open ? " open" : ""}${dismissed ? " dismissed" : ""}`} tabIndex={0} role="button" aria-expanded={open}
      onMouseEnter={(e) => place(e.currentTarget)} onFocus={(e) => place(e.currentTarget)}
      onMouseLeave={() => setDismissed(false)}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest(".tile-pop")) return; // clicks inside the card (links, text) leave it open
        place(e.currentTarget);
        setDismissed(false);
        setOpen((v) => !v);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if ((e.target as HTMLElement).closest(".tile-pop")) return;
          e.preventDefault();
          setDismissed(false);
          setOpen((v) => !v);
        } else if (e.key === "Escape") close();
      }}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) {
          setOpen(false);
          setDismissed(false);
        }
      }}>
      {/* pointing at the tile again (after closing with the cross) shows the card on hover once more */}
      <div className="tile-face" onMouseEnter={() => setDismissed(false)}>
        <Badge a={a} compact />
      </div>
      <div className={`tile-pop ${side}`} role="tooltip">
        {open && <button type="button" className="tile-close" aria-label="Close" title="Close" onClick={(e) => { e.stopPropagation(); close(); }}>×</button>}
        <Badge a={a} />
      </div>
    </div>
  );
}

/** Small summary for the player page; the full list lives on /achievements. */
export interface AchievementsAccess {
  /** this visitor sees achievements: launched, or a Discord preview (null while loading) */
  visible: boolean | null;
  launched: boolean;
  preview: boolean;
  start: string | null;
  /** number of achievements available (null while loading) */
  total: number | null;
  peek: AchievementPeek | null;
}

export function useAchievementsAccess(): AchievementsAccess {
  const d = useApi(getChallenges, "challenge").data;
  return {
    visible: d ? d.launched || d.preview : null,
    launched: !!d?.launched,
    preview: !!d?.preview,
    start: d?.start ?? null,
    total: d?.total ?? null,
    peek: d?.peek ?? null,
  };
}

/** Before the launch: how many achievements per section, a few shown in full and a few more as hidden badges. */
function SneakPeek({ peek }: { peek: AchievementPeek }) {
  const newTotal = Object.values(peek.new).reduce((a, b) => a + b, 0);
  return (
    <section className="sneak-peek">
      <div className="section-head">
        <h2>Sneak peek</h2>
      </div>
      {peek.revealed.length > 0 && (
        <>
          <p className="muted">{peek.revealed.length} of them, revealed early:</p>
          <div className="badges">{peek.revealed.map((a) => <Badge key={a.id} a={a} />)}</div>
          <p className="muted">…and the rest stay secret until the start:</p>
        </>
      )}
      <div className="badges mystery">
        {peek.icons.map((icon) => (
          <div key={icon} className="badge-card locked">
            <div className="badge-art">
              <img className="icon" src={IMG + icon} alt="" />
              <img className="tier" src={IMG + "white_lock.png"} alt="locked" />
            </div>
            <div className="badge-text">
              <strong>???</strong>
              <span className="muted">Revealed at the start</span>
            </div>
          </div>
        ))}
      </div>
      {peek.one_game > 0 && (
        <p className="muted">
          <strong>{peek.one_game}</strong> “In one game” challenges — every one needs at least 3 players on each team.
        </p>
      )}
      <h3>From the original ECRanked site</h3>
      <div className="cards">
        {GROUPS.filter(([period]) => peek.periods[period]).map(([period, label]) => (
          <div key={period} className="card">
            <span className="label">{label}</span>
            <strong>{peek.periods[period]}</strong>
          </div>
        ))}
      </div>
      {newTotal > 0 && (
        <>
          <h3>
            New challenges <span className="tag">new</span> <span className="muted hint">· {newTotal}, built on replay data the original site never read</span>
          </h3>
          <p className="muted">More being developed.</p>
          <div className="cards">
            {Object.entries(peek.new).map(([theme, count]) => (
              <div key={theme} className="card">
                <span className="label">{theme}</span>
                <strong>{count}</strong>
                {theme === "Experimental gear" && <span className="muted">Now public</span>}
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  );
}

function PreviewLogin() {
  const me = useApi(getMe, "me").data;
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const failed = params.get("login") === "failed";
  const why = params.get("why");
  if (!me?.enabled) return null;
  if (me.user)
    return (
      <p className="muted">
        Logged in as <strong>{me.user.name}</strong>, but your Discord account does not have the preview role.
      </p>
    );
  return (
    <p className="muted">
      {failed && <>The Discord login did not work{why ? ` (${why})` : ""}, please try again. </>}
      Have preview access? <a href={loginUrl("/achievements")}>Log in with Discord</a>
    </p>
  );
}

export function ComingSoon({ start, total, peek }: { start: string | null; total: number | null; peek: AchievementPeek | null }) {
  return (
    <>
      <EmptyState title="Coming soon">
        {total ? <><strong>{total}</strong> achievements</> : "Achievements"} and Flamingo Challenges are on their way
        {start && start > new Date().toISOString().slice(0, 10) ? (
          <>
            {" "}
            — they start on <strong>{start}</strong>. Only matches from that day on count.
          </>
        ) : (
          ". Only matches played after they start will count."
        )}
      </EmptyState>
      <PreviewLogin />
      {peek && <SneakPeek peek={peek} />}
    </>
  );
}

/** Progress at the top of the player page (user, 2026-11-06): overall bar, crowns and medals, and the three challenges closest to
 *  their next medal. Clicking the header opens the Achievements tab. Hidden until achievements are visible to this visitor. */
export function AchievementsStrip({ userId, onOpen }: { userId: string; onOpen: () => void }) {
  const { visible } = useAchievementsAccess();
  if (!visible) return null;
  return <StripBody userId={userId} onOpen={onOpen} />;
}

function StripBody({ userId, onOpen }: { userId: string; onOpen: () => void }) {
  const d = useApi(() => getAchievements(userId), userId).data;
  if (!d) return null;
  const counted = d.items.filter((a) => a.counted && !a.prize);
  const crowns = counted.filter((a) => a.progress >= 1).length;
  const medals = LEVELS.map((m) => [m, counted.filter((a) => a.levels && a.tier === m).length] as const);
  const next = counted
    .filter((a) => a.progress < 1 && a.levels && a.count != null)
    .map((a) => [a, nextMedal(a)] as const)
    .filter((x): x is readonly [Achievement, { fraction: number; medal: string }] => x[1] !== null)
    .sort((x, y) => y[1].fraction - x[1].fraction)
    .slice(0, 3);
  return (
    <section className="ach-strip" aria-label="Achievements">
      <button className="ach-strip-head" onClick={onOpen} title="Open the Achievements tab">
        <strong>Achievements</strong>
        <div className="bar" style={{ "--sec": `var(--tier-${sectionMedal(d.overall) ?? "bar-default"})` } as React.CSSProperties} role="progressbar" aria-label="Average progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(d.overall * 100)}>
          <div style={{ width: `${d.overall * 100}%` }} />
        </div>
        <span className="muted">{pct(d.overall)} · {crowns} / {counted.length} crowns</span>
        <span className="strip-medals">
          {medals.map(([m, n]) => (
            <span key={m} className={`t-${m}`} title={`Challenges where ${m} is the best medal`}><i />{n}</span>
          ))}
        </span>
      </button>
      {next.length > 0 && (
        <div className="ach-strip-next" aria-label="Closest to the next medal">
          {next.map(([a, nm]) => (
            <div key={a.id} className="strip-next">
              <Tile a={a} />
              <span className="muted">{levelText(a.count ?? 0, a.levels ?? [], a.unit)} · {pct(nm.fraction)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export function AchievementsSummary({ userId }: { userId: string }) {
  const { visible, start, total } = useAchievementsAccess();
  if (visible) return <LaunchedSummary userId={userId} />;
  if (visible === null) return null;
  // Before the Flamingo Challenge start date set in the console: the section, but no personal progress (previewers excepted)
  return (
    <>
      <div className="section-head">
        <h2>
          Achievements <span className="tag">Coming soon</span>
        </h2>
        <Link to="/achievements">Sneak peek</Link>
      </div>
      <p className="muted">
        {total ? `${total} achievements` : "Achievements"} and Flamingo Challenges.{" "}
        {start ? (
          <>
            This player's progress shows from <strong>{start}</strong>, counting matches from that day on.
          </>
        ) : (
          "This player's progress shows once the challenges start."
        )}
      </p>
    </>
  );
}

function LaunchedSummary({ userId }: { userId: string }) {
  const result = useApi(() => getAchievements(userId), userId);
  const d = result.data;
  if (!d) return null;
  const counted = d.items.filter((a) => a.counted); // the Combat section is left out of the totals for now
  const gold = counted.filter((a) => a.progress >= 1).length; // crown for ladders, 100 % for single-step ones
  const unlocked = counted.filter((a) => a.tier).length;
  const added = d.items.filter((a) => a.new);
  return (
    <>
      <div className="section-head">
        <h2>Achievements</h2>
        <Link to={achievementsPath(d.user_id, d.name)}>View all achievements</Link>
      </div>
      <div className="cards">
        <div className="card">
          <span className="label" title="Average progress across every achievement, counting partial progress toward each one">Average progress</span>
          <strong>{pct(d.overall)}</strong>
        </div>
        <div className="card">
          <span className="label">Completed (crown)</span>
          <strong>
            {gold} / {d.total}
          </strong>
        </div>
        <div className="card">
          <span className="label">Unlocked (25%+)</span>
          <strong>
            {unlocked} / {d.total}
          </strong>
        </div>
        {added.length > 0 && (
          <Link className="card link-card" to={`${achievementsPath(d.user_id, d.name)}#new`}>
            <span className="label">New challenges</span>
            <strong>
              {added.filter((a) => a.progress >= 1).length} / {added.length}
            </strong>
            <span className="muted">gear, modes and wins</span>
          </Link>
        )}
      </div>
      <div className="ach-summary-tabs">
        {GROUPS.map(([period]) => [`p-${period}`, PAGE_LABELS[period]] as const).map(([id, label]) => {
          const list = d.items.filter((a) => !a.prize && sectionId(a) === id);
          if (list.length === 0) return null;
          const done = list.filter((a) => a.progress >= 1).length;
          const avg = list.reduce((t, a) => t + a.progress, 0) / list.length;
          return (
            <Link key={id} className="card link-card" to={`${achievementsPath(d.user_id, d.name)}?section=${id}`}>
              <span className="label">{label}</span>
              <strong>{done} / {list.length}</strong>
              <div className="bar" style={{ "--sec": `var(--tier-${sectionMedal(avg) ?? "bar-default"})` } as React.CSSProperties}><div style={{ width: `${avg * 100}%` }} /></div>
            </Link>
          );
        })}
      </div>
    </>
  );
}

/** The admin-set Flamingo Challenge period (only matches inside it count). */
export function ChallengeBanner() {
  const w = useApi(getChallenges, "challenge");
  const d = w.data;
  if (!d) return null;
  if (d.preview)
    return (
      <p className="note">
        <strong>Preview</strong> — only people with the Discord preview role see this.
        {d.visibility === "preview" && d.start && d.start <= new Date().toISOString().slice(0, 10) ? (
          <> It counts matches from <strong>{d.start}</strong>; it is not public yet.</>
        ) : d.start ? (
          <>
            {" "}
            It counts every match in the archive; from the launch on <strong>{d.start}</strong> only matches from that day count.
          </>
        ) : (
          " It counts every match in the archive; after the launch only matches from its start date count."
        )}
      </p>
    );
  if (!d.launched) return null;
  return <RecordingWindow what="achievements" />;
}

/** A clear box with the set period in which matches are recorded; used for achievements and for Mega Prizes. */
export function RecordingWindow({ what }: { what: "achievements" | "Mega Prizes" }) {
  const d = useApi(getChallenges, "challenge").data;
  if (!d || !d.start) return null;
  return (
    <div className={`rec-window${d.active ? "" : " ended"}`} role="note">
      <span className="rec-dates">
        {d.start} → {d.end ?? "open-ended"}
      </span>
      <span className="muted">
        Only matches played inside this period count for {what}
        {what === "achievements" ? "; the player stats pages count every match" : ""}.
      </span>
    </div>
  );
}

/** The counting rules in plain words, on the overview and on every player's page. */
export function AchievementRules({ open = false }: { open?: boolean }) {
  return (
    <details className="rules-help" open={open}>
      <summary>Rules</summary>
      <ul>
        <li>
          <strong>Medals.</strong> Almost every challenge is a ladder: bronze, gold, platinum and a gold crown with a pink diamond for completing it. The bar has one step per medal, the
          colour of a name is the medal reached and the number under each step is its target. A few single-step challenges keep white 25%, bronze
          50%, silver 75%, gold 100%.
        </li>
        <li>
          <strong>Completed</strong> means the crown (or 100% for a single-step challenge). <strong>Average progress</strong> counts partial progress
          toward every challenge, so it is always higher than the share completed.
        </li>
        <li>
          <strong>Progress is your best ever</strong>: your best game, best calendar day, best rolling 7 days, or the all-time total. A "7 days" window
          is any 7 days in a row, not a calendar week.
        </li>
        <li>
          <strong>Nothing is locked.</strong> Every challenge is open from your first game, in any order. Daily challenges suit a short session,
          "any 7 days" ones sit in between, and the all-time ones count every game you have played, so daily and weekly play always adds to them.
          Medal Collector counts the gold (or better) medals you hold on all the others.
        </li>
        <li>
          <strong>Each achievement lists its own rules</strong> under its description: whether the best game, day or 7 days counts, whether games
          under 4 minutes are ignored, whether it needs 3+ players per team and how "only" is judged. <strong>"3+ players per team"</strong> = both teams had at least 3 players for at least half of the match (3v3, 3v4, 4v4, 5v5 and so on all count); smaller games do not count towards it. Recordings that cover less than half a match are ignored
          everywhere.
        </li>
        <li>
          <strong>Using an item.</strong> In every game you carry a weapon, an ordnance and a tac mod, and you can change them. For each of those
          three slots the site measures how long each item was equipped during the game. <strong>"Use"</strong> an item = it was equipped for at least
          10% of the game, so trying it out for a moment does not count. <strong>"Use only"</strong> an item = it was equipped for at least 90% of
          the game in its slot, so a short switch is fine: in a 10-minute game up to 1 minute of something else is allowed.
        </li>
        <li>
          <strong>Days are UK days</strong>, midnight to midnight UK time, so everyone is counted on the same clock. That covers "in one day", "any 7 days" and the challenge dates. Match times on the site are shown in your own timezone.
        </li>
        <li>
          <strong>Highlighted cards</strong> are close to their next medal: at least a quarter of the way there, from yellow to green as you get closer.
        </li>
        <li>
          <strong>Combat section.</strong> These use the game's own counters from the recorder's match reports, from 4 November 2026 on, apart from the
          replay stats. You earn medals as usual, but their targets are provisional and they do not count toward average progress, totals, rankings or Medal Collector.
        </li>
        <li>* Deaths are estimated from the recording.</li>
      </ul>
    </details>
  );
}

export function AchievementsView({ userId }: { userId: string }) {
  const result = useApi(() => getAchievements(userId), userId);
  const [sort, setSort] = useState<"group" | "closest">("group");
  const data = result.data;

  return (
    <>
      <Status loading={result.loading} error={result.error} />
      {data && (
        <>
          <div className="filters">
            <div className="card">
              <span className="label" title="Average progress across every achievement, counting partial progress toward each one">Average progress</span>
              <strong>{pct(data.overall)}</strong>
            </div>
            <div className="card">
              <span className="label">Completed</span>
              <strong>
                {data.completed} / {data.total}
              </strong>
            </div>
            {LEVELS.map((medal, i) => (
              <div className={`card t-${medal}`} key={medal} title={`Challenges where the ${medal} medal (or better) is earned`}>
                <span className="label" style={{ color: "var(--tier)" }}>{medal}</span>
                <strong>{data.items.filter((a) => a.counted && a.levels && a.tier && LEVELS.indexOf(a.tier as (typeof LEVELS)[number]) >= i).length}</strong>
              </div>
            ))}
          </div>
          {sort === "group" && <JumpToNew ready />}
          <label className="inline-check">
            <input type="checkbox" checked={sort === "closest"} onChange={(e) => setSort(e.target.checked ? "closest" : "group")} /> Sort by closest
            to the next medal
          </label>
          {sort === "closest" && (
            <div className="badges">
              {data.items
                .filter((a) => a.progress < 1)
                .sort((a, b) => (nextMedalFraction(b) ?? 0) - (nextMedalFraction(a) ?? 0))
                .map((a) => <Badge key={a.id} a={a} />)}
            </div>
          )}
          {sort === "group" && (
            <GroupedBadges items={data.items} />
          )}
          <AchievementRules />
        </>
      )}
    </>
  );
}
