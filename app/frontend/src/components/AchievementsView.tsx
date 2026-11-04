import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { LEVELS, getAchievements, getArenaProgress, getChallenges, getMe, getRarity, loginUrl, type Achievement, type AchievementPeek, type AchievementRarity, type AchievementRule } from "../api";
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

// New achievements (not on the original site) get their own sections, in this order.
export const NEW_GROUPS: [string, string][] = [
  ["Experimental gear", "Weapons and ordnances that were never released, seen in recent replays (now public)"],
  ["Gear mastery", "All four weapons, ordnances or tac mods in one game"],
  ["Wins", "Results: streaks and totals"],
  ["Payload", "Winning, pushing and blocking the payload"],
  ["Capture Point", "Winning and sweeping Capture Point"],
  ["Activity", "How often and how long you play"],
  ["Survival", "Deaths in one game and flawless wins"],
  ["Movement", "How you move in a single game"],
  ["Emotes", ""],
];

type AnyBadge = Parameters<typeof Badge>[0]["a"];

const COLLAPSED_KEY = "achievements-collapsed";

/** Which sections are folded away; remembered in this browser (localStorage may be unavailable: then it just is not kept). */
function useCollapsed(foldByDefault: string[] = []) {
  const [folded, setFolded] = useState<Set<string>>(() => {
    try {
      const saved = localStorage.getItem(COLLAPSED_KEY);
      return new Set<string>(saved === null ? foldByDefault : JSON.parse(saved));
    } catch {
      return new Set<string>(foldByDefault);
    }
  });
  const save = (next: Set<string>) => {
    setFolded(next);
    try {
      localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next]));
    } catch {
      /* not remembered */
    }
  };
  return {
    folded,
    toggle: (id: string) => save(new Set(folded.has(id) ? [...folded].filter((x) => x !== id) : [...folded, id])),
    setAll: (ids: string[], collapsed: boolean) => save(new Set(collapsed ? ids : [])),
  };
}

type Collapse = ReturnType<typeof useCollapsed>;

type Filter = "done" | "open" | "new";
const FILTERS: [Filter, string][] = [["open", "In progress"], ["new", "Not started"], ["done", "Completed"]];

/** Where a player stands: completed (100 %), in progress, or not started. Catalogue entries (no progress) have none. */
function status(a: AnyBadge): Filter | null {
  if (a.progress === undefined) return null;
  return a.progress >= 1 ? "done" : a.progress > 0 ? "open" : "new";
}

/** A section: a heading that folds it away, and (for a player) filters Completed / In progress / Not started. Completed
 *  achievements are hidden until you pick Completed; the view opens on the first filter that has something. */
function Section<T extends AnyBadge>({ id, c, level = 3, title, items, anchor }: { id: string; c: Collapse; level?: 2 | 3; title: React.ReactNode; items: T[]; anchor?: string }) {
  const [picked, setPicked] = useState<Filter | null>(null);
  const open = !c.folded.has(id);
  const Heading = `h${level}` as "h2" | "h3";
  const tracked = items.every((a) => status(a) !== null);
  const counts = { done: 0, open: 0, new: 0 };
  if (tracked) for (const a of items) counts[status(a)!]++;
  const filter = picked ?? FILTERS.find(([f]) => counts[f] > 0)?.[0] ?? "open";
  // closest to the next medal first, like the row at the top; not started / completed ones keep the rule order (stable sort)
  const shown = tracked
    ? items.filter((a) => status(a) === filter).sort((a, b) => (nextMedalFraction(b as Achievement) ?? 0) - (nextMedalFraction(a as Achievement) ?? 0))
    : items;
  const overall = tracked ? items.reduce((sum, a) => sum + (a.progress ?? 0), 0) / items.length : 0;
  return (
    <div className="fold" id={anchor}>
      <Heading className="fold-head">
        <button type="button" aria-expanded={open} onClick={() => c.toggle(id)}>
          <span className="chevron" aria-hidden="true">{open ? "▾" : "▸"}</span> {title} <span className="muted hint">({items.length})</span>
        </button>
      </Heading>
      {tracked && (
        <div className="section-progress" title={`${counts.done} of ${items.length} completed, ${pct(overall)} overall`}>
          <div className="bar" style={{ "--sec": `var(--tier-${sectionMedal(overall) ?? "bar-default"})` } as React.CSSProperties} role="progressbar" aria-label={`${typeof title === "string" ? title : "Section"} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(overall * 100)}>
            <div style={{ width: `${overall * 100}%` }} />
          </div>
          <span className="muted">{counts.done}/{items.length} completed · {pct(overall)}</span>
        </div>
      )}
      {open && tracked && (
        <div className="tabs" role="tablist">
          {FILTERS.map(([f, label]) => (
            <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "tab active" : "tab"} onClick={() => setPicked(f)}>
              {label} ({counts[f]})
            </button>
          ))}
        </div>
      )}
      {open && (
        <div className="badges scroll-row" tabIndex={0} aria-label={`${typeof title === "string" ? title : "Section"}, scroll sideways`}>
          {shown.map((a) => <Badge key={a.id} a={a} />)}
        </div>
      )}
    </div>
  );
}

/** Original achievements by period, then the new ones by theme, in one flat list of sections. */
export function GroupedBadges<T extends AnyBadge>({ items: all }: { items: T[] }) {
  // Mega Prize challenges (very draft / beta, user 2026-11-04) are not in the normal sections: they only show in a
  // hidden tab that opens with #mega-prizes (no link to it anywhere).
  const items = all.filter((a) => !a.prize);
  // A player's page opens with every section folded (the row at the top already lifts the best ones); a choice made with
  // Expand all / Collapse all or a heading is remembered in this browser (user, 2026-11-03).
  const tracked = items.length > 0 && items.every((a) => status(a) !== null);
  const c = useCollapsed(tracked ? ["p-game", "p-day", "p-week", "p-all", ...[...NEW_GROUPS.map(([n]) => n), "More"].map((n) => `n-${n}`)] : []);
  const sections: { id: string; title: React.ReactNode; items: T[] }[] = [
    ...GROUPS.map(([period, label]) => ({ id: `p-${period}`, title: label, items: items.filter((a) => !a.new && a.period === period) })),
    ...[...NEW_GROUPS, ["More", ""] as [string, string]].map(([name, hint]) => ({
      id: `n-${name}`,
      title: <>{name} {hint && <span className="muted hint">· {hint}</span>}</>,
      items: items.filter((a) => a.new && (NEW_GROUPS.some(([n]) => n === name) ? a.group === name : !NEW_GROUPS.some(([n]) => n === a.group))),
    })),
  ].filter((x) => x.items.length > 0);
  const firstNew = sections.find((x) => x.id.startsWith("n-"))?.id;
  const ids = sections.map((x) => x.id);
  return (
    <>
      <div className="fold-all">
        <button type="button" className="tab" onClick={() => c.setAll(ids, false)}>Expand all</button>
        <button type="button" className="tab" onClick={() => c.setAll(ids, true)}>Collapse all</button>
      </div>
      {sections.map((x) => (
        <Section key={x.id} id={x.id} c={c} title={x.title} items={x.items} anchor={x.id === firstNew ? "new" : undefined} />
      ))}
    </>
  );
}

/** The Mega Prizes tab (/mega-prizes, Preview role only): your own progress first, then the challenges. Public Arena is
 * counted from the live match list, separately from Combat. */
export function MegaPrizes() {
  const result = useApi(getArenaProgress, "arena-progress");
  const arena = result.data;
  if (!arena) return null; // no Preview role (403) or still loading: the tab stays hidden
  const items = arena.combat;
  return (
    <div className="section" id="mega-prizes">
      <h2>
        Mega Prizes <span className="tag">draft</span>
      </h2>
      {arena.me && (
        <div className="panel" aria-label="Your progress">
          <strong>Your progress{arena.me.name ? `, ${arena.me.name}` : ""}</strong>
          <PrizeBar value={arena.me.arena / arena.target} label={`Public Arena: ${arena.me.arena} / ${arena.target} matches → OG High Quality Jack Model`} />
          {arena.me.combat_linked ? (
            <PrizeBar value={(arena.me.combat ?? 0) / (items[0]?.levels?.[items[0].levels.length - 1] ?? 750)} label={`Echo Combat: ${arena.me.combat ?? 0} / ${items[0]?.levels?.[items[0].levels.length - 1] ?? 750} matches → Delta Squad BioMass Chassis`} />
          ) : (
            <span className="muted">Link your Discord account to your player to see your Echo Combat progress.</span>
          )}
        </div>
      )}
      <div className="badges scroll-row" tabIndex={0} aria-label="Mega Prizes, scroll sideways">
        {items.map((a) => (
          <div key={a.id}>
            <img src="/mega-prizes/biomass.png" alt="Delta Squad BioMass Chassis (draft)" style={{ width: 160, borderRadius: 6 }} />
            <Badge a={a} />
            <PrizeBar value={0} label={`Target: ${a.levels?.[a.levels.length - 1] ?? 750} matches (draft: progress not shown yet)`} />
          </div>
        ))}
        <div>
          <img src="/mega-prizes/jack.jpg" alt="Jack, Lone Echo" style={{ width: 160, borderRadius: 6 }} />
          <div className="badge-card">
          <div className="badge-text">
            <strong>Play 750 Public Arena Matches</strong>
            <span className="tag mega-prize">Mega Prize: OG High Quality Jack Model</span>
            <span className="muted">Counted separately from Combat.</span>
          </div>
          </div>
          {arena?.players.length ? (
            arena.players.slice(0, 10).map((p) => (
              <PrizeBar key={p.user_id} value={p.matches / arena.target} label={`${p.name}: ${p.matches} / ${arena.target}`} />
            ))
          ) : (
            <PrizeBar value={0} label="No Arena matches counted yet" />
          )}
          <span className="muted">Public Arena only, 4+ minutes in the match, counted from the live match list.</span>
        </div>
      </div>
    </div>
  );
}

/** Progress toward a Mega Prize; no value = not tracked in this app. */
function PrizeBar({ value, label }: { value: number | null; label: string }) {
  const w = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100);
  return (
    <div className="section-progress">
      <div className="bar" style={{ "--sec": "var(--tier-gold, #c9a227)" } as React.CSSProperties} role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={w}>
        <div style={{ width: `${w}%` }} />
      </div>
      <span className="muted">{label}</span>
    </div>
  );
}

/** Link to the new-challenges section; also scrolls there when the page is opened with #new (data loads late). */
export function JumpToNew({ ready }: { ready: boolean }) {
  const { hash } = useLocation();
  useEffect(() => {
    if (ready && hash === "#new") document.getElementById("new")?.scrollIntoView();
  }, [ready, hash]);
  return (
    <a className="jump-new" href="#new" onClick={(e) => (e.preventDefault(), document.getElementById("new")?.scrollIntoView({ behavior: "smooth" }))}>
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
          return { medal: LEVELS[i], label: need.toLocaleString(), fill: Math.max(0, Math.min(1, (a.count! - prev) / (need - prev))) };
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

function MedalTargets({ levels, unit = "" }: { levels: number[]; unit?: string }) {
  return (
    <details className="medal-targets">
      <summary>Medal targets</summary>
      <ul>
        {levels.map((need, i) => (
          <li key={LEVELS[i]} className={`t-${LEVELS[i]}`}>
            <span className="medal-name">{LEVELS[i]}</span> {need.toLocaleString()}{unit}
          </li>
        ))}
      </ul>
    </details>
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

/** Medal colour of a section's overall progress (ladders give 20 % per medal: bronze 20 ... platinum 100 %). */
function sectionMedal(progress: number): string | null {
  return progress >= 1 ? "platinum" : progress >= 0.8 ? "diamond" : progress >= 0.6 ? "gold" : progress >= 0.4 ? "silver" : progress >= 0.2 ? "bronze" : null;
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

/** A rule with a player's progress, or just the catalogue entry when `progress` is absent. */
/** Tiered achievements: "12 / 25 for diamond", or the top medal once every target is reached. */
function levelText(count: number, levels: number[], unit = ""): string {
  const next = levels.findIndex((need) => count < need);
  if (next < 0) return `${count.toLocaleString()}${unit} · ${LEVELS[levels.length - 1]} (max)`;
  return `${count.toLocaleString()} / ${levels[next].toLocaleString()}${unit} for ${LEVELS[next]}`;
}

export function Badge({ a }: { a: AchievementRule & Partial<Pick<Achievement, "progress" | "tier" | "unlocked_at" | "count">> & Partial<Pick<AchievementRarity, "unlocked_share" | "completed_share">> }) {
  const tier = a.tier ?? null;
  const catalogue = a.progress === undefined;
  const frame = tier ? `${tier}.png` : "white_lock.png";
  const src = IMG + (a.icon ?? GENERIC_ICON);
  // The glyph takes the colour of the tier reached; grey = not started, plain = started, no tier yet (user,
  // 2026-11-02). Built-in art is one colour on transparent, so it is used as a mask; uploads keep their own colours.
  const state = catalogue ? "" : tier ? " tinted" : a.progress! > 0 ? " tinted started" : " not-started";
  const tinted = state.includes("tinted") && a.icon != null && !a.icon.startsWith("custom/");
  return (
    <div className={`badge-card${tier || catalogue ? "" : " locked"}${tier ? ` t-${tier}` : ""}${tinted ? state : state.replace(" tinted", "")}`} title={`${ruleText(a.description)}${a.estimated ? " (estimated)" : ""}`}>
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
        {a.rules && a.rules.length > 0 && <span className="muted rule-notes">{a.rules.join(" · ")}</span>}
        {a.levels && a.levels.length > 0 && <MedalTargets levels={a.levels} unit={a.unit} />}
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
        {a.unlocked_share != null && (
          <span className="muted rarity" title="Share of players with 10+ games">
            {pct(a.unlocked_share)} unlocked · {pct(a.completed_share)} completed
          </span>
        )}
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
          <strong>{peek.one_game}</strong> “In one game” challenges — every one is played in a 4v4 match.
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
  const gold = d.items.filter((a) => a.progress >= 1).length; // platinum for ladders, 100 % for single-step ones
  const unlocked = d.items.filter((a) => a.tier).length;
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
          <span className="label">Completed (platinum)</span>
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
            <span className="muted">gear, wins, payload, emotes</span>
          </Link>
        )}
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
  return (
    <p className={`note${d.active ? "" : " ended"}`}>
      Flamingo Challenge period: <strong>{d.start}</strong> to <strong>{d.end ?? "open-ended"}</strong>
      {d.active ? "" : " (not running now)"} — only matches inside it count.
    </p>
  );
}

/** The counting rules in plain words, on the overview and on every player's page. */
export function AchievementRules({ open = false }: { open?: boolean }) {
  return (
    <details className="rules-help" open={open}>
      <summary>Rules</summary>
      <ul>
        <li>
          <strong>Medals.</strong> Almost every challenge is a ladder: bronze, silver, gold, diamond, platinum. The bar has one step per medal, the
          colour of a name is the medal reached and the number under each step is its target. A few single-step challenges keep white 25%, bronze
          50%, silver 75%, gold 100%.
        </li>
        <li>
          <strong>Completed</strong> means platinum (or 100% for a single-step challenge). <strong>Average progress</strong> counts partial progress
          toward every challenge, so it is always higher than the share completed.
        </li>
        <li>
          <strong>Progress is your best ever</strong>: your best game, best calendar day, best rolling 7 days, or the all-time total. A "7 days" window
          is any 7 days in a row, not a calendar week.
        </li>
        <li>
          <strong>Each achievement lists its own rules</strong> under its description: whether the best game, day or 7 days counts, whether games
          under 4 minutes are ignored, whether it is 4v4 only and how "only" is judged. Recordings that cover less than half a match are ignored
          everywhere.
        </li>
        <li>
          <strong>"Use only" an item</strong> = it was 90% or more of that game's time in its slot, so a quick switch is fine. <strong>"Use"</strong> =
          5% or more.
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
          </div>
          {sort === "group" && <NotYetStarted items={data.items} />}
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
