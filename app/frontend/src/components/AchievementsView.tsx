import { createContext, useContext, useEffect, useRef, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { LEVELS, getMegaPlayer, getMegaVisible, getAchievements, getArenaProgress, getChallenges, getMe, getRarity, getPins, loginUrl, savePin, type Achievement, type ChallengePins, type AchievementPeek, type AchievementRarity, type AchievementRule } from "../api";
import { achievementsPath, dateTime, medalRuleText, pct, periodStarted, ruleText } from "../format";
import { useApi } from "../useApi";
import { useFullscreen } from "../useFullscreen";
import { GearLabel, Status } from "./common";
import { EmptyState } from "./ui";

// Old ecranked.com badge art (app/images -> public/achievements). Tier frames = progress levels
// 25 / 50 / 75 / 100 % (white / bronze / silver / gold); the lock emblem = below 25 %.
const IMG = "/achievements/";
/** Uploaded icons and built-in "colour_" art keep their own colours; other built-in art is a one-colour silhouette,
 * tinted by the tier (backend achievements.COLOUR_ART; user, 2026-11-20: the sweaty robot is a blob as a silhouette). */
export const keepsColours = (icon: string | null | undefined) => !!icon && (icon.startsWith("custom/") || icon.startsWith("colour_"));
const GENERIC_ICON = "happy_cubesat.png";
export const GROUPS: [Achievement["period"], string][] = [
  ["game", "One Match"],
  ["day", "One Day"], // counts any 24 hours since 2026-11-28 (was the UK calendar day): said by the tab's ⓘ (TAB_INFO)
  ["week", "One Week"],
  ["month", "One Month"], // no challenge uses it now (user, 2026-11-10); an empty page is hidden
  ["all", "Cumulative"],
];

// New achievements (not on the original site) get their own sections, in this order. Merged (user, 2026-11-04): each section lists
// the themes it holds (a challenge's `group`).
export const NEW_GROUPS: [name: string, hint: string, groups: string[]][] = [
  ["Gear", "Experimental weapons and ordnances (never released), and using all four weapons, ordnances or tac mods in one game", ["Experimental gear", "Gear mastery"]],
  ["Modes & wins", "Winning, streaks, and Payload and Capture Point play", ["Wins", "Payload", "Capture Point"]],
  ["Combat", "Kills, assists, damage and objective play, from the game's own counters in the recorder's match reports, from 4 November 2026 on, apart from the replay stats. They count like the rest: in your totals, average progress, Top players and Medal Collector.", ["Combat"]],
];

// Survival, Movement, Emotes and Activity are not themes any more (user, 2026-11-04): their challenges sit with the others of the same
// period (mostly "In one game"; the all-time ones, Activity included, under "All time").
const BY_PERIOD = new Set(["Survival", "Movement", "Emotes", "Activity", "Profile", "George League"]);
/** Challenges that are not about games (Edit your Bio; the George League ones, user 2026-11-27): only their own rules shown. */
const NOT_GAMES = new Set(["Profile", "George League"]);
const GEAR_GROUPS = new Set(["Experimental gear", "Gear mastery"]);
/** Shown under its period (in one game / day / any 7 days / all time) rather than a theme: the old rules, a few themes, and the
 *  "any 7 days" gear challenges (user, 2026-11-04). */
const inPeriodSection = (a: { new: boolean; group: string | null; period: string }) =>
  !a.new || BY_PERIOD.has(a.group ?? "") || (a.period === "week" && GEAR_GROUPS.has(a.group ?? ""));

type AnyBadge = Parameters<typeof Badge>[0]["a"];

/** The game's own end-of-match award cards (MVP, Super Star, Guard ...): their rules all end in "(Award card)" (combat_achievements.py). */
export const isAwardCard = (a: { name: string; award?: boolean }) => !!a.award || a.name.endsWith("(Award card)");  // flag from the server since names lost their tag (2026-11-26)

/** Which section (tab) a challenge sits in: its period. The one-game period is the Specials tab; the in-game award cards sit in
 *  the tab of their period, in an "Award cards" box (user, 2026-11-26: no tab of their own). */
export function sectionId(a: { name: string; period: string }): string {
  // Four pages (user, 2026-11-06, renamed 2026-11-10): One Match, One Day, One Week, Cumulative; the theme is a filter inside the page, see themeOf.
  // The award cards moved out of those into a tab of their own (user, 2026-11-26), split by period inside it.
  return `p-${a.period}`;
}

/** Theme chip of a challenge inside its period page (user, 2026-11-06: themes are filters now, not tabs). */
export function themeOf(a: { new: boolean; group: string | null; period: string }): string {
  if (!inPeriodSection(a)) return NEW_GROUPS.find(([, , gs]) => gs.includes(a.group ?? ""))?.[0] ?? "More";
  return a.new ? "Other new" : "Original";
}

/** The four pages (user, 2026-11-06): in one game, day, week, cumulative (= all time). */
const PAGE_LABELS: Record<string, string> = Object.fromEntries(GROUPS); // One Match, One Day, One Week, Cumulative (user, 2026-11-10)
const PAGES = GROUPS;
/** Every tab in order: the period pages, then Specials (user, 2026-11-26). The one-game page is always empty now, so it is hidden. */
// Specials (the one-game challenges) first, then One Day / One Week / Cumulative; the award cards are in these by period (user, 2026-11-26)
const TAB_LABELS: Record<string, string> = { ...PAGE_LABELS, game: "Specials" };
const SECTION_LIST: [id: string, label: string][] = PAGES.map(([period]) => [`p-${period}`, TAB_LABELS[period]] as [string, string]);

type Filter = "done" | "open" | "new";
const FILTERS: [Filter, string][] = [["open", "In progress"], ["new", "Not started"], ["done", "Completed"]];

/** Where a player stands: completed (100 %), in progress, or not started. Catalogue entries (no progress) have none. */
function status(a: AnyBadge): Filter | null {
  if (a.progress === undefined) return null;
  return a.progress >= 1 ? "done" : a.progress > 0 ? "open" : "new";
}

type SortBy = "default" | "closest" | "complete" | "rarest" | "name";
type Shares = Map<number, number | null>;

/** Order of the rows in a tab. Default: the rule order for everyone, so a challenge stays in the same spot between visits (classic
 *  list, user 2026-11-26: it replaced closest-to-the-next-medal first for a player). */
function sortItems<T extends AnyBadge>(list: T[], by: SortBy, shares: Shares): T[] {
  const out = [...list];
  const closest = (x: T) => nextMedalFraction(x as unknown as Achievement) ?? 0;
  if (by === "complete") return out.sort((x, y) => (y.progress ?? 0) - (x.progress ?? 0)); // overall progress over all tiers
  if (by === "name") return out.sort((x, y) => x.name.localeCompare(y.name));
  if (by === "rarest") return out.sort((x, y) => (shares.get(x.id) ?? 1) - (shares.get(y.id) ?? 1));
  if (by === "closest") return out.sort((x, y) => closest(y) - closest(x));
  return out;
}

/** Colour of each tab (user, 2026-11-26: big coloured tabs, like the old site's Community / Day / Week / Season). */
/** What the time period of a tab means, behind an ⓘ on the tab (user, 2026-11-28): hover shows it, a tap opens it under the tabs (VR). */
const TAB_INFO: Record<string, string> = {
  "p-day": "In any 24 hours: your best 24 hours in a row count, starting at any of your games, so a session across midnight counts as one.",
  "p-week": "In any 7 days: your best 7 days in a row count, starting at any of your games.",
};

const SECTION_COLOUR: Record<string, string> = {
  "p-game": "var(--period-game)",
  "p-day": "var(--period-day)",
  "p-week": "var(--period-week)",
  "p-month": "var(--period-month)",
  "p-all": "var(--period-all)",
};

/** Overall progress of a list of challenges (0..1); null for catalogue entries (no player). */
function listProgress(items: AnyBadge[]): number | null {
  if (items.length === 0 || items.some((a) => a.progress === undefined)) return null;
  return items.reduce((sum, a) => sum + (a.progress ?? 0), 0) / items.length;
}

/** The challenges of one tab as the classic two-column list (user, 2026-11-26, like the original ECRanked page): the first half
 *  down the left, the rest down the right with the icons on the outer edge. Every status shows (completed ones say so), unless
 *  `only` picks one. */
function Section<T extends AnyBadge>({ label, items, only, sort, shares }: { label: string; items: T[]; only: Filter | ""; sort: SortBy; shares: Shares }) {
  const shown = sortItems(only ? items.filter((a) => status(a) === only) : items, sort, shares);
  if (shown.length === 0) return <p className="muted">No challenge matches.</p>;
  // grouped by topic, each in a box (user, 2026-11-26); the award cards of this period in a box of their own
  const groups: [string, AnyBadge[]][] = TOPICS.map((t) => [t, shown.filter((a) => topicOf(a) === t)] as [string, AnyBadge[]]);
  return (
    <div className="ch-groups">
      {packGroups(groups.filter(([, list]) => list.length > 0)).map(({ title, items: list, wide }) => (
        <ChallengeGroup key={title} title={title} items={list} label={`${label}, ${title}`} wide={wide} />
      ))}
    </div>
  );
}

const HALF_MAX = 4; // a box with this many challenges or fewer can sit beside another one

/** The boxes in order, with no empty space (user, 2026-11-26): a short box sits beside the next short box with the SAME number of
 *  challenges (so both are the same height); one without such a partner, and every long box, takes the full width with its
 *  rows in two columns. A pair stays together right after the first box of the two. */
function packGroups(groups: [string, AnyBadge[]][]): { title: string; items: AnyBadge[]; wide: boolean }[] {
  const out: { title: string; items: AnyBadge[]; wide: boolean }[] = [];
  const waiting = new Map<number, string>(); // number of challenges -> the box waiting for a partner
  for (const [title, items] of groups) {
    const n = items.length;
    const key = n;
    if (n > HALF_MAX) {
      out.push({ title, items, wide: true });
      continue;
    }
    const partner = waiting.get(key);
    if (partner !== undefined) {
      out.splice(out.findIndex((b) => b.title === partner) + 1, 0, { title, items, wide: false });
      waiting.delete(key);
    } else {
      waiting.set(key, title);
      out.push({ title, items, wide: false });
    }
  }
  const alone = new Set(waiting.values());
  return out.map((b) => (alone.has(b.title) ? { ...b, wide: true } : b));
}

const WEAPONS = ["pulsar", "nova", "comet", "meteor", "blazar", "protostar", "quark", "starburst"];
const ORDNANCES = ["detonator", "stun field", "arc mine", "instant repair", "attack drone", "dot field", "translocator"];
const TAC_MODS = ["repair matrix", "threat scanner", "energy barrier", "phase shift", "overcharge", "neutron", "umbral veil"];
const MAPS = ["dyson", "combustion", "fission", "surge"];
/** Topic boxes inside a tab, in this order (user, 2026-11-26: weapons, ordnances, tac mods, Payload, Capture Point ...). */
const TOPICS = ["Profile", "George League", "Weapons", "Ordnances", "Tac mods", "Loadouts", "Payload", "Capture Point", "Maps", "Movement", "Positioning", "Survival", "Emotes", "Wins", "Activity", "Award cards", "Combat", "Other"];
const GROUP_TOPIC: Record<string, string> = { Payload: "Payload", "Capture Point": "Capture Point", Emotes: "Emotes", Wins: "Wins", Activity: "Activity", Movement: "Movement", Survival: "Survival", Combat: "Combat", "Gear mastery": "Loadouts", Profile: "Profile", "George League": "George League" };
const mentions = (text: string, words: string[]) => words.some((w) => text.includes(w));

/** The topic box a challenge sits in: its theme, else the gear, mode or map its rule names, else its built-in art. Read from
 *  the rule text first, as an admin may have given the challenge any icon. */
export function topicOf(a: { name: string; description: string; group: string | null; icon: string | null }): string {
  if (isAwardCard(a)) return "Award cards";
  const fromGroup = GROUP_TOPIC[a.group ?? ""];
  if (fromGroup) return fromGroup;
  const name = a.name.toLowerCase();
  const text = `${name} ${a.description.toLowerCase()}`;
  if (text.includes("payload")) return "Payload";
  if (text.includes("capture point")) return "Capture Point";
  if (name.includes("(weapon)")) return "Weapons";
  if (name.includes("(ordnance)")) return "Ordnances";
  if (name.includes("(tac mod)")) return "Tac mods";
  if (mentions(text, WEAPONS)) return "Weapons";
  if (mentions(text, ORDNANCES)) return "Ordnances";
  if (mentions(text, TAC_MODS)) return "Tac mods";
  if (mentions(text, MAPS)) return "Maps";
  if (/loadout|all 12 items|equipable/.test(text)) return "Loadouts";
  if (/upside down|speed/.test(text)) return "Movement";
  if (/close to (a teammate|an enemy)/.test(text)) return "Positioning";
  if (/\bdie\b|dying|deaths/.test(text)) return "Survival";
  if (/pubs|hours played|days you played/.test(text)) return "Activity";
  return "Other";
}

/** One topic box: its name, how far the player is through it, and its rows in two columns (one when it is short). */
function ChallengeGroup({ title, items, label, wide }: { title: string; items: AnyBadge[]; label: string; wide: boolean }) {
  const progress = listProgress(items);
  const done = items.filter((a) => status(a) === "done").length;
  return (
    <section className={`ch-group${wide ? " wide" : ""}`}>
      <header className="ch-group-head">
        <h3>{title}</h3>
        <span className="ch-group-count">{progress === null ? items.length : `${done}/${items.length} · ${pct(progress)}`}</span>
      </header>
      <ChallengeList items={items} label={label} single={!wide} />
    </section>
  );
}

function ChallengeList({ items, label, single = false }: { items: AnyBadge[]; label: string; single?: boolean }) {
  if (single)
    return (
      <div className="ch-list single" aria-label={label}>
        <div className="ch-col left">{items.map((a) => <ChallengeRow key={a.id} a={a} side="left" />)}</div>
      </div>
    );
  // an odd one out stretches across both columns, so no box has an empty slot (user, 2026-11-26)
  const half = Math.floor(items.length / 2);
  const last = items.length % 2 ? items[items.length - 1] : null;
  return (
    <div className="ch-list" aria-label={label}>
      {half > 0 && <div className="ch-col left">{items.slice(0, half).map((a) => <ChallengeRow key={a.id} a={a} side="left" />)}</div>}
      {half > 0 && <div className="ch-col right">{items.slice(half, half * 2).map((a) => <ChallengeRow key={a.id} a={a} side="right" />)}</div>}
      {last && <div className="ch-col full"><ChallengeRow a={last} side="left" /></div>}
    </div>
  );
}

/** One medal step of a challenge for the card: done, being chased (with how far along), or later. */
/** A won-or-not challenge (user, 2026-11-26): a single step, the crown. */
const BINARY_STEP = { medal: "crown", label: "Complete" };

function medalSteps(a: AnyBadge): { medal: string; label: string; state: "done" | "current" | "later"; fill: number }[] {
  const catalogue = a.progress === undefined;
  if (a.binary) {
    const done = !catalogue && (a.progress ?? 0) >= 1;
    return [{ ...BINARY_STEP, fill: done ? 1 : 0, state: done ? "done" : catalogue ? "later" : "current" }];
  }
  const raw = a.levels && (catalogue || a.count != null)
    ? a.levels.map((need, i) => {
        const prev = i ? a.levels![i - 1] : 0;
        return { medal: LEVELS[i] as string, label: `${need.toLocaleString()}${a.unit ?? ""}`, fill: catalogue ? 0 : Math.max(0, Math.min(1, (a.count! - prev) / (need - prev))) };
      })
    : PERCENT_STEPS.map((s, i) => {
        const prev = i ? PERCENT_STEPS[i - 1].at : 0;
        return { medal: s.medal, label: `${Math.round(s.at * 100)}%`, fill: catalogue ? 0 : Math.max(0, Math.min(1, ((a.progress ?? 0) - prev) / (s.at - prev))) };
      });
  const chasing = catalogue ? -1 : raw.findIndex((s) => s.fill < 1);
  return raw.map((s, i) => ({ ...s, state: s.fill >= 1 ? "done" : i === chasing ? "current" : "later" }));
}

/** The challenge's art: a silhouette tinted by the medal reached (uploads and "colour_" art keep their own colours). */
function ChallengeArt({ a, className }: { a: AnyBadge; className: string }) {
  const src = IMG + (a.icon ?? GENERIC_ICON);
  if (keepsColours(a.icon)) return <img className={className} src={src} alt="" />;
  return <span className={`${className} glyph`} style={{ WebkitMaskImage: `url(${src})`, maskImage: `url(${src})` }} aria-hidden="true" />;
}

const HINT_MAX = 48;

/** A few words under a row's name saying what the challenge is (user, 2026-11-26: names stay, but clearer at a glance). */
// Written by hand where the rule's first words would be cut off or mislead
const HINTS: Record<number, string> = {
  18: "Games with 3 deaths or fewer", 23: "Top speed in one game", 42: "Same loadout, games in a row",
  43: "Few deaths, games in a row", 46: "Close to teammates, in 7 days", 47: "Close to enemies, in 7 days",
  48: "Average speed, in 7 days", 49: "Upside down, in 7 days", 71: "Close to teammates, all games",
  72: "Close to enemies, all games", 73: "Average speed, all games", 74: "Upside down, all games",
  86: "Least-used experimental weapon", 93: "Capture Point wins, 2-0", 112: "Games with Overcharge",
  123: "Least-used weapon", 124: "Least-used item", 141: "Capture Point win after losing round one", 96: "Longest payload push, one game", 97: "Longest payload block, one game",
  143: "Far from teammates, one game", 147: "Time on a contested point, one game", 150: "Emotes in one game",
  146: "Capture time, one game", 296: "Capture time, in 24 hours", 297: "Capture time, in 7 days", 298: "Capture time, all games",
  299: "Contested time, in 24 hours", 300: "Contested time, in 7 days", 301: "Contested time, all games",
  151: "Emotes in a game you win", 170: "Kills without dying, one game", 176: "Most kills in the match",
  177: "Games with 5 kills, 5 assists, 5 objective eliminations", 178: "Games with 8+ assists, twice your kills",
  208: "Most kills in the match, in 24 hours", 213: "Most kills in the match, in 7 days",
};

export function shortHint(a: { id: number; description: string; period: string }): string {
  if (HINTS[a.id]) return HINTS[a.id];
  const rule = ruleText(a.description);
  const when = (s: string) => (/in any 24 hours/.test(s) ? ", in 24 hours" : /in any 7 days/.test(s) ? ", in 7 days" : /in any 30 days/.test(s) ? ", in 30 days" : "");
  let m = /^Play games using only (.+?) in (?:any 24 hours|any 7 days|any 30 days)/.exec(rule);
  if (m) return `Only ${m[1]}${when(rule)}`;
  m = /^Play games using (.+)$/.exec(rule);
  if (m) return `Games with ${m[1]}`;
  m = /^Play games on (\w+)(?: in (?:any 24 hours|any 7 days))?$/.exec(rule);
  if (m) return `${m[1]} games${when(rule)}`;
  m = /^Play (Capture Point|Payload|Combat pubs?)(?: games)?(?: in (?:any 24 hours|any 7 days))?$/.exec(rule);
  if (m) return `${m[1].replace(/ pubs?$/, " pubs")}${/games/.test(rule) ? " games" : ""}${when(rule)}`;
  const first = rule.split(/, | \(|: /)[0];
  if (first.length <= HINT_MAX) return first;
  const cut = first.slice(0, HINT_MAX);
  return `${cut.slice(0, cut.lastIndexOf(" "))}…`;
}

/** The one challenge card open at a time (user, 2026-11-27: on a phone open cards stacked up): opening one closes the last. */
let closeOpenCard: (() => void) | null = null;

/** A row of the classic list: icon, name and a slim bar in the colour of the medal reached. Pointing at it (mouse or a VR
 *  controller) peeks the card with the medal steps; a click or tap pins it open, another click or the cross closes it. */
function ChallengeRow({ a, side }: { a: AnyBadge; side: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(false); // closed with the cross while still pointed at: stays shut until the pointer leaves
  const [up, setUp] = useState(false);
  const row = useRef<HTMLDivElement>(null);
  // while open: the card opened before closes, and a tap or click anywhere outside this row closes this one (user,
  // 2026-11-27: on a phone the cross is small and cards stacked up)
  useEffect(() => {
    if (!open) return;
    const mine = () => setOpen(false);
    closeOpenCard?.();
    closeOpenCard = mine;
    const outside = (e: PointerEvent) => {
      if (row.current && !row.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("pointerdown", outside);
      if (closeOpenCard === mine) closeOpenCard = null;
    };
  }, [open]);
  const catalogue = a.progress === undefined;
  const tier = a.tier ?? null;
  const done = !catalogue && a.progress! >= 1;
  const started = !catalogue && a.progress! > 0;
  const fill = catalogue ? a.unlocked_share ?? 0 : a.progress!;
  function place(el: HTMLElement) {
    const r = el.getBoundingClientRect();
    const below = window.innerHeight - r.bottom;
    setUp(below < 320 && r.top > below); // open upward near the bottom of the screen
  }
  function close() {
    setOpen(false);
    setDismissed(true);
  }
  const share = a.unlocked_share == null ? "" : a.unlocked_share === 0 ? "nobody yet" : a.unlocked_share < 0.01 ? "under 1% of players" : `${pct(a.unlocked_share)} of players`;
  return (
    <div ref={row} className={`ch-row ${side}${open ? " open" : ""}${dismissed ? " dismissed" : ""}${done ? " done" : ""}${tier ? ` t-${tier}` : ""}${catalogue ? " catalogue" : started ? " started" : " not-started"}`}
      tabIndex={0} role="button" aria-expanded={open}
      onMouseEnter={(e) => { place(e.currentTarget); }} onFocus={(e) => place(e.currentTarget)}
      onMouseLeave={() => setDismissed(false)}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest(".ch-card")) return; // clicks inside the card (links, text) leave it open
        place(e.currentTarget);
        setDismissed(false);
        setOpen((v) => !v);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          if ((e.target as HTMLElement).closest(".ch-card")) return;
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
      <ChallengeArt a={a} className="ch-icon" />
      <div className="ch-main">
        <div className="ch-line">
          <span className="ch-name">{a.name}</span>
          {!catalogue && <PinButton id={a.id} done={done} />}
          <span className="ch-state" title={catalogue ? "Share of players who reached a tier" : "Overall progress, counting every tier"}>
            {catalogue ? share : done ? "Completed!" : pct(a.progress)}
          </span>
        </div>
        <span className="ch-hint">{shortHint(a)}</span>
        {catalogue ? (
          <div className="ch-bar" role="progressbar" aria-label={a.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fill * 100)}>
            <div style={{ width: `${fill * 100}%` }} />
          </div>
        ) : (
          // one segment per tier, each in its own colour with a clear gap between them (user, 2026-11-26)
          <div className="ch-bar segmented" role="progressbar" aria-label={a.name} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fill * 100)}>
            {medalSteps(a).map((s) => (
              <span key={s.medal} className={`ch-seg t-${s.medal} ${s.state}`} title={`${s.medal}: ${s.label}`}>
                <span style={{ width: `${s.fill * 100}%` }} />
              </span>
            ))}
          </div>
        )}
      </div>
      <div className={`ch-card ${side}${up ? " up" : ""}`} role="tooltip">
        <ChallengeCard a={a} onClose={open ? close : undefined} />
      </div>
    </div>
  );
}

/** A short rule tag from the server written out as a sentence (user, 2026-11-26: the rules in full in the card). */
function ruleSentence(tag: string): string {
  const fixed: Record<string, string> = {
    "Best game": "Your best single game counts",
    "Best 24 hours": "Your best 24 hours in a row count",
    "Best 7 days": "Your best 7 days in a row count",
    "Best 30 days": "Your best 30 days in a row count",
    "All-time total": "Every game in the challenge period adds up",
    "2+ players per team": "Only games with 2+ players on each team count", // every challenge (user, 2026-11-28)
  };
  let r = /^Best (\d+) games in a row$/.exec(tag);
  if (r) return `Your best ${r[1]} games in a row count, however long they took`;
  r = /^([\d.]+)\+ min in bounds per game$/.exec(tag);
  if (r) return `Only games with ${r[1]}+ minutes in bounds count; shorter ones are skipped`;
  if (fixed[tag]) return fixed[tag];
  let m = /^([\d.]+)\+ min games$/.exec(tag);
  if (m) return `Only games of ${m[1]}+ minutes count`;
  m = /^Average, (\d+)\+ games$/.exec(tag);
  if (m) return `Your average over all your games; needs ${m[1]}+ games`;
  m = /^([\d.]+)\+ min on the map$/.exec(tag);
  if (m) return `You must be on the map for ${m[1]}+ minutes`;
  m = /^"Only" = (\d+%)\+ of the game$/.exec(tag);
  if (m) return `"Only" means ${m[1]}+ of the game with it`;
  m = /^Silver\+: (\d+)\+ different days$/.exec(tag);
  if (m) return `Silver and up need games on ${m[1]}+ different days of the 7 (any days, not in a row)`;
  m = /^([\d.]+)\+ min per loadout$/.exec(tag);
  if (m) return `A loadout counts after ${m[1]}+ minutes with it`;
  return tag;
}

/** Every counting rule of a challenge: its own, then what is NOT required (no length / team size rule), then the rule all
 *  share. Profile challenges (Edit your Bio) are not about games, so only their own lines. */
function countingRules(a: AnyBadge): string[] {
  const tags = a.rules ?? [];
  if (NOT_GAMES.has(a.group ?? "")) return tags;
  const out = tags.map(ruleSentence);
  if (!tags.some((t) => / min games$/.test(t))) out.push("Any game length");
  if (!tags.some((t) => /players (per|on each) team/.test(t))) out.push("Any team size");
  out.push("Public matches only, played inside the challenge period");
  return out;
}

/** Every loadout this player has not used yet, for "I Use All the Loadouts" (67; user, 2026-11-27: "show the player which
 *  combination hasn't been used yet"): folded away under its count, then per weapon each ordnance with the tac mods
 *  still to use with it. */
function UntriedLoadouts({ list }: { list: NonNullable<Achievement["untried"]> }) {
  const left = list.reduce((n, x) => n + x.tacmods.length, 0);
  const weapons = [...new Set(list.map((x) => x.weapon))];
  return (
    <details className="untried-loadouts" onClick={(e) => e.stopPropagation()}>
      <summary>{left} loadout{left === 1 ? "" : "s"} not used yet</summary>
      <ul>
        {weapons.map((w) => {
          const rows = list.filter((x) => x.weapon === w);
          return (
            <li key={w}>
              <strong><GearLabel name={w} /></strong> <span className="muted">({rows.reduce((n, x) => n + x.tacmods.length, 0)} left)</span>
              <ul>
                {rows.map((x) => (
                  <li key={x.ordnance}><GearLabel name={x.ordnance} />: {x.tacmods.join(" · ")}</li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

/** The player's best on the card (user, 2026-11-28: "put their best achieved"): `count` is the best game / 24 hours /
 *  7 days / 30 days, or the challenge-period total for all-time ones. */
const BEST_LABELS: Record<string, string> = {
  game: "Your best game", day: "Your best 24 hours", week: "Your best 7 days", month: "Your best 30 days", all: "Your total",
};

/** The card a row opens: what to do, every medal step (ticked when reached), where the player stands, and the big picture. */
function ChallengeCard({ a, onClose }: { a: AnyBadge; onClose?: () => void }) {
  const catalogue = a.progress === undefined;
  const tier = a.tier ?? null;
  const steps = medalSteps(a);
  return (
    <div className={`ch-card-inner${tier ? ` t-${tier}` : ""}`}>
      {onClose && <button type="button" className="tile-close" aria-label="Close" title="Close" onClick={(e) => { e.stopPropagation(); onClose(); }}>×</button>}
      <div className="ch-card-text">
        <span className="ch-kicker">{isAwardCard(a) ? "In-game award card" : a.period === "game" ? "Special" : `${PAGE_LABELS[a.period] ?? ""} challenge`}{a.new && <span className="tag" title="A newer challenge">new</span>}</span>
        <h4>{a.name}</h4>
        <p className="ch-rule">{ruleText(a.description)}{a.estimated && " *"}</p>
        <ol className="ch-steps">
          {steps.map((s) => (
            <li key={s.medal} className={`t-${s.medal} ${s.state}`}>
              <span className="ch-frame-step"><img src={`${IMG}${s.medal}.png`} alt="" />{s.state === "done" && <i className="ch-tick" aria-hidden="true">✓</i>}</span>
              <span className="ch-medal">{s.medal}</span>
              <span className="ch-target">{s.label}</span>
              {s.state === "current" && s.fill > 0 && <span className="ch-step-bar"><span style={{ width: `${s.fill * 100}%` }} /></span>}
            </li>
          ))}
        </ol>
        {!catalogue && !a.binary && a.levels && a.count != null && (
          <span className="ch-best">
            {BEST_LABELS[a.period] ?? "Your best"}: <b>{a.count.toLocaleString(undefined, { maximumFractionDigits: 2 })}{a.unit ?? ""}</b>
          </span>
        )}
        {!catalogue && (
          <span className="ch-status">
            {a.progress! >= 1
              ? `Completed${a.unlocked_at ? ` ${a.unlocked_at}` : ""}`
              : a.levels && a.count != null ? levelText(a.count, a.levels, a.unit) : `${pct(a.progress)} of the way`}
          </span>
        )}
        {!catalogue && <PinButton id={a.id} done={a.progress! >= 1} label />}
        {a.prize && <span className="tag mega-prize" title="Mega Prize for completing this challenge">Mega Prize: {a.prize}</span>}
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
        {!catalogue && a.untried && a.untried.length > 0 && a.progress! < 1 && <UntriedLoadouts list={a.untried} />}
        {!catalogue && a.needs && a.needs.length > 0 && a.progress! < 1 && <NeedsLeft needs={a.needs} />}
        {!catalogue && a.per_item && a.per_item.length > 0 && <LeastUsed items={a.per_item} levels={a.levels ?? undefined} />}
        <div className="ch-rules">
          <span className="ch-rules-head">How it counts</span>
          <ul>{countingRules(a).map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
        {a.unlocked_share != null && (
          <span className="muted ch-notes" title="Share of players with 10+ games">{pct(a.unlocked_share)} of players reached a tier · {pct(a.completed_share)} completed</span>
        )}
      </div>
      <div className="ch-card-art">
        <ChallengeArt a={a} className="ch-big" />
        {!catalogue && <img className="ch-frame" src={IMG + (tier ? `${tier}.png` : "lock_clear_no_square.png")} alt={tier ? `${tier} tier` : "no tier yet"} />}
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
  const [only, setOnly] = useState<Filter | "">("");
  // the theme chips and the "New only" box are gone (user, 2026-11-07): the search box and the status / sort selects remain
  const sort: SortBy = "default"; // no sort chips (user, 2026-11-28: "looking a bit cluttered"): the original order only
  const [topic, setTopic] = useState(""); // category chip (user, 2026-11-28: "a way to filter it on category"), "" = all
  const [tabInfo, setTabInfo] = useState<string | null>(null); // the tab whose ⓘ text is open
  const [params, setParams] = useSearchParams();
  const tracked = items.length > 0 && items.every((a) => status(a) !== null);
  // no search box (user, 2026-11-28: "no need for it, as we have filters")
  const visible = items.filter((a) => !tracked || !only || status(a) === only);
  const sections: { id: string; label: string; items: T[] }[] = SECTION_LIST.map(([id, label]) => ({ id, label, items: [] as T[] }));
  for (const a of visible) sections.find((x) => x.id === sectionId(a))?.items.push(a);
  const shownSections = sections.filter((x) => x.items.length > 0);
  // the page comes from the address (?section=), so a link can open one; links to #new scroll to the tabs
  const wanted = params.get("section");
  const active = shownSections.find((x) => x.id === wanted) ?? shownSections[0];
  // the theme chips (All / New / Original / Gear / Modes & wins / Other new / Combat) under the tabs were removed
  // (user, 2026-11-07: no longer needed, added confusion); "New only" and the search filter instead
  // categories = the topic boxes of the open tab; a category the tab does not have counts as All, so a tab is never empty
  const tabItems = active?.items ?? [];
  const topics = TOPICS.map((t) => [t, tabItems.filter((a) => topicOf(a) === t).length] as [string, number]).filter(([, n]) => n > 0);
  const shownTopic = topics.some(([t]) => t === topic) ? topic : "";
  const pageItems = shownTopic ? tabItems.filter((a) => topicOf(a) === shownTopic) : tabItems;
  // every tab opens on All for both filters (user, 2026-11-28), also when the tab changes through the address (back / forward)
  const activeId = active?.id;
  useEffect(() => { setTopic(""); setOnly(""); }, [activeId]);
  function pick(id: string) {
    const next = new URLSearchParams(params);
    if (id === shownSections[0]?.id) next.delete("section");
    else next.set("section", id);
    setParams(next, { replace: true, preventScrollReset: true });
  }
  // status and sort are tap chips in plain view (user, 2026-11-28: the filter button that hid them was pointless; 2026-11-26:
  // nobody should have to type in VR), the search box is a small extra at the end of the row for keyboards
  const filtering = only !== "" || topic !== "";
  return (
    <>
      <div className="ch-tabs-row">
        {active && (
          <div className="ch-tabs" id="new" role="tablist" aria-label="Challenge groups">
            {shownSections.map((x) => {
              const progress = listProgress(x.items);
              const done = progress === null ? 0 : x.items.filter((a) => status(a) === "done").length;
              const info = TAB_INFO[x.id];
              const tab = (
                <button key={x.id} role="tab" aria-selected={active.id === x.id} className={`ch-tab${active.id === x.id ? " active" : ""}`}
                  style={{ "--per": SECTION_COLOUR[x.id] ?? "var(--blue)" } as React.CSSProperties} onClick={() => pick(x.id)}>
                  <span className="ch-tab-fill" style={{ width: `${(progress ?? 0) * 100}%` }} aria-hidden="true" />
                  <span className="ch-tab-label">{x.label}</span>
                  <span className="ch-tab-hint">{progress === null ? `${x.items.length} challenges` : `${done}/${x.items.length} · ${pct(progress)}`}</span>
                </button>
              );
              if (!info) return tab;
              // the ⓘ sits beside the tab button, not inside it (a button cannot hold another one)
              return (
                <div key={x.id} className="ch-tab-wrap" role="presentation">
                  {tab}
                  <button type="button" className={`ch-tab-info${tabInfo === x.id ? " on" : ""}`} title={info} aria-label={`${x.label}: ${info}`}
                    aria-expanded={tabInfo === x.id} onClick={() => setTabInfo((v) => (v === x.id ? null : x.id))}>
                    i
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
      {tabInfo && TAB_INFO[tabInfo] && (
        <p className="ch-tab-note" role="note">
          <strong>{TAB_LABELS[tabInfo.slice(2)]}</strong> · {TAB_INFO[tabInfo]}
          <button type="button" className="ch-tab-note-close" aria-label="Close" onClick={() => setTabInfo(null)}>×</button>
        </p>
      )}
      <div className="ach-toolbar ch-tools">
        {topics.length > 1 && (
          // a quiet text row, one line that scrolls sideways; the count is hover text (user, 2026-11-28: "less cluttered")
          <div className="ch-cats" role="group" aria-label="Category">
            {([["", tabItems.length], ...topics] as [string, number][]).map(([t, n]) => (
              <button key={t || "all"} type="button" className={`ch-cat${shownTopic === t ? " on" : ""}`} aria-pressed={shownTopic === t}
                title={`${n} challenge${n === 1 ? "" : "s"}`} onClick={() => setTopic(t)}>{t || "All"}</button>
            ))}
          </div>
        )}
        {tracked && (
          <div className="ch-pills" role="group" aria-label="Show">
            <span className="ch-pills-label">Show</span>
            {([["", "All"], ...FILTERS] as [Filter | "", string][]).map(([f, text]) => (
              <button key={f || "all"} type="button" className={`ch-pill${only === f ? " on" : ""}`} aria-pressed={only === f} onClick={() => setOnly(f)}>{text}</button>
            ))}
          </div>
        )}
        {filtering && <button type="button" className="ch-pill" onClick={() => { setOnly(""); setTopic(""); }}>Clear</button>}
      </div>
      {shownSections.length === 0 && <p className="muted">No challenge matches.</p>}
      {active && (
        <>
          {tracked && <NotYetStarted items={pageItems as unknown as Achievement[]} />}
          <div style={{ "--per": SECTION_COLOUR[active.id] ?? "var(--blue)" } as React.CSSProperties}>
            <Section key={active.id} label={active.label} items={pageItems} only={only} sort={sort} shares={shares} />
          </div>
        </>
      )}
    </>
  );
}

/** The Mega Prizes section of the Achievements page: only for the Preview role (the server checks it too, so nobody else
 * even asks for the data). */
export function MegaPrizesSection() {
  const visible = useApi(getMegaVisible, "mega-visible").data?.visible;
  return visible ? <MegaPrizes /> : null; // who sees it is set in the Console ("Visible to"); the server checks it too
}

/** The player profile's Mega Prizes (user, 2026-11-26): only this player's own progress toward each prize, no ranking or
 *  other players. Shown to whoever may see the Mega Prizes (Console "Visible to"); the server checks it too. */
export function MegaPrizesProfile({ userId }: { userId: string }) {
  const visible = useApi(getMegaVisible, "mega-visible").data?.visible;
  return visible ? <MegaPrizesProfileBody userId={userId} /> : null;
}

/** What counts for each Mega Prize: shared by the Mega Prizes section and a player's profile row. */
const MEGA_NOTES = {
  // Combat: 2v2 and up (user, 2026-11-27: was 3v3); Arena keeps 3v3. The time period line (user, 2026-11-27: "include
  // that there is a time period"), without the end date (removed the same day)
  // cut to one short line each (user, 2026-11-28: "too many words, need to reduce the pane size")
  combat: ["Prize period only · 4+ min · 2v2 or bigger"],
  arena: ["Prize period only · public · 4+ min · 3v3 or bigger"],
};

function MegaPrizesProfileBody({ userId }: { userId: string }) {
  const d = useApi(() => getMegaPlayer(userId), `mega-player|${userId}`).data;
  // the row opens to the prize cards: pictures, the prize and what counts (user, 2026-11-27); open by default
  // (user, 2026-11-27), "Less" still closes it
  const [open, setOpen] = useState(true);
  if (!d) return null;
  // one row (user, 2026-11-26: "too much data"): each prize as a short name, a slim bar and the count; the rest is hover text
  const prizes = [
    { key: "combat" as const, short: "Delta-13", photos: "d13", rule: `Play ${d.combat.target.toLocaleString()} Echo Combat matches`, ...d.combat, prize: d.combat.prize ?? "Delta-13 from Lone Echo 2" },
    { key: "arena" as const, short: "Jack Series 11", photos: "jack", rule: `Play ${d.arena.target.toLocaleString()} Public Arena matches`, ...d.arena },
  ];
  return (
    <section className="mega-profile mega-row" aria-label="Mega Prizes">
      {/* no period / account line, nor as hover text (user, 2026-11-27: removed "Only matches inside the Mega Prize period
          count: <start> → <end> (recording). No game account is linked to this player yet.") */}
      <strong className="mega-row-label">
        Mega Prizes{d.period.active && <span className="live-dot" aria-label="recording" />}
      </strong>
      {/* on the left, after the label (user, 2026-11-27), like the Challenges row's View all */}
      <button type="button" className="secondary mega-row-toggle" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={`mega-profile-more-${userId}`}>
        {open ? "Less ▴" : "More ▾"}
      </button>
      {prizes.map((x) => {
        const won = x.matches >= x.target;
        return (
          <span key={x.key} className={`mega-row-prize ${x.key}${won ? " won" : ""}`}
            title={`${x.prize}: ${x.rule}. ${won ? "Prize won!" : `${(x.target - x.matches).toLocaleString()} to go.`}`}>
            <span className="mega-row-name">{x.short}</span>
            <span className="mega-profile-bar" role="progressbar" aria-label={`${x.prize}: ${x.matches} of ${x.target}`} aria-valuemin={0} aria-valuemax={x.target} aria-valuenow={x.matches}>
              <span style={{ width: `${Math.min(1, x.matches / x.target) * 100}%` }} />
            </span>
            <span className="mega-row-count">{won ? "won!" : <><b>{x.matches.toLocaleString()}</b> / {x.target.toLocaleString()}</>}</span>
          </span>
        );
      })}
      {open && (
        <div className="mega-row-more" id={`mega-profile-more-${userId}`}>
          <div className="mega-cards">
            {prizes.map((x) => {
              const won = x.matches >= x.target;
              return (
                <article key={x.key} className="mega-card">
                  <PrizePhotos prefix={x.photos} alt={x.prize} />
                  <div className="mega-body">
                    <strong>{x.rule}</strong>
                    <span className="tag mega-prize">Mega Prize: {x.prize}</span>
                    {MEGA_NOTES[x.key].map((n) => <span key={n} className="muted">{n}</span>)}
                    <span>{won ? "Prize won!" : <><b>{x.matches.toLocaleString()}</b> / {x.target.toLocaleString()} · {(x.target - x.matches).toLocaleString()} to go</>}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}

/** Every player who reaches the target wins the prize: there can be many winners (user, 2026-11-05). */
const winnersText = (n: number, target: number) =>
  `${n === 0 ? "No winners yet" : `${n} ${n === 1 ? "winner" : "winners"}`} · all who reach ${target} win`;

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

/** The two prize cards, each with its own player search: the players found show inside that card with their progress bar.
 *  Public Arena is counted from the live match list, separately from Combat. */
const MEGA_OPEN_KEY = "echovr-mega-open";

function storedMegaOpen(): boolean | null {
  try {
    const v = localStorage.getItem(MEGA_OPEN_KEY);
    return v === "1" ? true : v === "0" ? false : null;
  } catch {
    return null;
  }
}

function MegaPrizes() {
  const result = useApi(getArenaProgress, "arena-progress");
  const arena = result.data;
  // a one-line banner, open by default only while the prize period runs; a visitor's own choice is remembered in their
  // browser (user, 2026-11-07, Achievements idea 10)
  const [chosen, setChosen] = useState<boolean | null>(storedMegaOpen);
  if (!arena) return null; // no Preview role (403) or still loading: the section stays hidden
  const combat = arena.combat[0];
  const combatTarget = combat?.levels?.[combat.levels.length - 1] ?? 1000;
  const open = chosen ?? !!arena.period.active;
  const toggle = () => {
    setChosen(!open);
    try {
      localStorage.setItem(MEGA_OPEN_KEY, open ? "0" : "1");
    } catch {
      /* storage unavailable */
    }
  };
  const leader = arena.top_combat[0];
  return (
    <div className={`section mega${open ? "" : " closed"}`} id="mega-prizes">
      <div className="mega-banner">
        <h2>Mega Prizes</h2>{/* no "draft" tag (user, 2026-11-28) */}
        <span className="muted mega-summary">
          {/* the start only, no end date (user, 2026-11-27) */}
          {arena.period.start && <>From {dateTime(arena.period.start)} · </>}
          {combat?.prize ?? "Delta-13"} ({combatTarget} Combat matches) · Jack Series 11 ({arena.target} Arena matches)
          {leader && <> · top: {leader.name} {leader.matches}</>}
          {/* the separator outside the green span: its dot sat against the leader's count (user, 2026-11-27) */}
          {arena.period.active && <> · <span className="live-text">recording</span></>}
        </span>
        <button type="button" className="secondary" onClick={toggle} aria-expanded={open} aria-controls="mega-prizes-body">
          {open ? "Hide ▴" : "Show ▾"}
        </button>
      </div>
      {open && <div id="mega-prizes-body">
      {/* no "From <date>" box here: the banner above already shows the start (user, 2026-11-28: "this is duplicated") */}
      <div className="mega-cards">
        <article className="mega-card">
          <PrizePhotos prefix="d13" alt="Delta-13 from Lone Echo 2" />
          <div className="mega-body">
            <strong>Play {combatTarget} Echo Combat Matches</strong>
            <span className="tag mega-prize">Mega Prize: {combat?.prize ?? "Delta-13 from Lone Echo 2"}</span>
            {MEGA_NOTES.combat.map((n) => <span key={n} className="muted">{n}</span>)}
            <span className="muted">{winnersText(arena.winners_combat, combatTarget)}</span>
            {arena.top_combat.length > 0 && (
              <>
                <span className="muted" title="▲▼ = places gained or lost in the last 24 h">Top {arena.top_combat.length} · ▲▼ last 24 h</span>
                <ul className="mega-results scroll">{arena.top_combat.map((r) => <PlayerBar key={r.user_id} r={r} target={combatTarget} />)}</ul>
              </>
            )}
          </div>
        </article>
        <article className="mega-card">
          <PrizePhotos prefix="jack" alt="Jack, Lone Echo" />
          <div className="mega-body">
            <strong>Play {arena.target} Public Arena Matches</strong>
            <span className="tag mega-prize">Mega Prize: Jack Series 11 from Lone Echo 1/2</span>
            {MEGA_NOTES.arena.map((n) => <span key={n} className="muted">{n}</span>)}
            <span className="muted">{winnersText(arena.winners_arena, arena.target)}</span>
            {arena.top_arena.length > 0 && (
              <>
                <span className="muted" title="▲▼ = places gained or lost in the last 24 h">Top {arena.top_arena.length} · ▲▼ last 24 h</span>
                <ul className="mega-results scroll">{arena.top_arena.map((p) => <PlayerBar key={p.user_id} r={p} target={arena.target} />)}</ul>
              </>
            )}
          </div>
        </article>
      </div>
      </div>}
    </div>
  );
}

/** Front and back of a prize, side by side (user, 2026-11-06). Both fit the window at first; the + / − buttons zoom (up to 6x), dragging
 *  (mouse or finger) moves the pictures in any direction, Reset puts them back. No mouse wheel, so scrolling the page never moves them.
 *  With the window focused, the arrow keys move and + / − zoom. */
const PHOTO_MAX_ZOOM = 6;

function PrizePhotos({ prefix, alt }: { prefix: string; alt: string }) {
  const box = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; from: [number, number] } | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pos, setPos] = useState<[number, number]>([0, 0]);
  // full screen (user, 2026-11-27): the pictures, with their zoom buttons, fill the screen; Esc or ✕ leaves
  const wrap = useRef<HTMLDivElement>(null);
  const screen = useFullscreen(wrap);
  useEffect(() => { setZoom(1); setPos([0, 0]); }, [screen.full]); // the window changes size, so start again fitted

  /** keep the pictures inside the window: at 1x they cannot move, zoomed they can travel half of the extra size */
  function clamp(p: [number, number], z: number): [number, number] {
    const w = box.current?.clientWidth ?? 0;
    const h = box.current?.clientHeight ?? 0;
    const mx = (w * (z - 1)) / 2;
    const my = (h * (z - 1)) / 2;
    return [Math.max(-mx, Math.min(mx, p[0])), Math.max(-my, Math.min(my, p[1]))];
  }
  function zoomTo(z: number) {
    const next = Math.min(PHOTO_MAX_ZOOM, Math.max(1, z));
    setZoom(next);
    setPos((p) => (next === 1 ? [0, 0] : clamp(p, next)));
  }
  const move = (dx: number, dy: number) => setPos((p) => clamp([p[0] + dx, p[1] + dy], zoom));

  return (
    <div className={`mega-photos-wrap${screen.full ? " is-full" : ""}${screen.fakeClass}`} ref={wrap}>
      <div ref={box} className={`mega-photos${zoom > 1 ? " zoomed" : ""}`} tabIndex={0} role="group"
        aria-label={`${alt}: front and back. Use the plus and minus buttons to zoom, drag to move`}
        onKeyDown={(e) => {
          const step = 40;
          if (e.key === "+" || e.key === "=") zoomTo(zoom * 1.5);
          else if (e.key === "-") zoomTo(zoom / 1.5);
          else if (e.key === "0") zoomTo(1);
          else if (e.key === "ArrowLeft") move(step, 0);
          else if (e.key === "ArrowRight") move(-step, 0);
          else if (e.key === "ArrowUp") move(0, step);
          else if (e.key === "ArrowDown") move(0, -step);
          else return;
          e.preventDefault();
        }}
        onPointerDown={(e) => {
          if (zoom <= 1) return;
          drag.current = { x: e.clientX, y: e.clientY, from: pos };
          e.currentTarget.setPointerCapture(e.pointerId);
          e.currentTarget.classList.add("dragging");
        }}
        onPointerMove={(e) => {
          if (drag.current) setPos(clamp([drag.current.from[0] + e.clientX - drag.current.x, drag.current.from[1] + e.clientY - drag.current.y], zoom));
        }}
        onPointerUp={(e) => {
          drag.current = null;
          e.currentTarget.classList.remove("dragging");
        }}
        onPointerCancel={(e) => {
          drag.current = null;
          e.currentTarget.classList.remove("dragging");
        }}>
        <div className="mega-photos-row" style={{ transform: `translate(${pos[0]}px, ${pos[1]}px) scale(${zoom})` }}>
          <PrizeImage name={`${prefix}_front.png`} alt={`${alt}, front`} />
          <PrizeImage name={`${prefix}_back.png`} alt={`${alt}, back`} />
        </div>
      </div>
      <div className="mega-zoom" role="group" aria-label="Zoom the pictures">
        <button type="button" className="secondary" onClick={() => zoomTo(zoom * 1.5)} disabled={zoom >= PHOTO_MAX_ZOOM} aria-label="Zoom in">+</button>
        <button type="button" className="secondary" onClick={() => zoomTo(zoom / 1.5)} disabled={zoom <= 1} aria-label="Zoom out">−</button>
        <button type="button" className="secondary" onClick={() => zoomTo(1)} disabled={zoom === 1}>Reset</button>
        <button type="button" className="secondary" onClick={screen.toggle} aria-pressed={screen.full}
          aria-label={screen.full ? "Leave full screen" : "Full screen"} title={screen.full ? "Leave full screen (Esc)" : "Full screen"}>
          {screen.full ? "✕" : "⛶"}
        </button>
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

/** Scrolls to the new-challenges tabs when the page is opened with #new (data loads late). The visible
 *  "Jump to new challenges ↓" link is gone (user, 2026-11-27); links to #new from other cards still land there. */
export function ScrollToNew({ ready }: { ready: boolean }) {
  const { hash } = useLocation();
  useEffect(() => {
    if (ready && hash === "#new") document.getElementById("new")?.scrollIntoView();
  }, [ready, hash]);
  return null;
}

/** Percentage-tiered rules: medals at 25 / 50 / 75 / 100 % of the way. */
const PERCENT_STEPS = [{ medal: "white", at: 0.25 }, { medal: "bronze", at: 0.5 }, { medal: "silver", at: 0.75 }, { medal: "gold", at: 1 }];

/** One segment per medal, each filled in its own colour with the target underneath, so the progress to every
 *  tier is visible (user, 2026-10-31). Tiered rules segment by count, the others by percentage. */
function TierSteps({ a }: { a: Achievement & AchievementRule }) {
  const steps = a.binary
    ? [{ ...BINARY_STEP, fill: a.progress >= 1 ? 1 : 0 }]
    : a.levels && a.count != null
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

/** The medal ladder as four dots on a compact tile (user, 2026-11-07, Achievements idea 4): filled = earned, half = the
 *  one being chased, empty = later. Ladders use bronze / silver / gold / crown; single-step rules their percentage steps. */
function MedalDots({ a }: { a: Achievement }) {
  const steps = a.binary ? [{ medal: "crown", done: a.progress >= 1 }] : a.levels && a.count != null
    ? a.levels.map((need, i) => ({ medal: LEVELS[i], done: a.count! >= need }))
    : PERCENT_STEPS.map((s) => ({ medal: s.medal, done: a.progress >= s.at }));
  const chasing = steps.findIndex((s) => !s.done);
  const earned = steps.filter((s) => s.done).length;
  return (
    <span className="medal-dots" role="img" aria-label={`${earned} of ${steps.length} tiers${chasing >= 0 ? `, chasing ${steps[chasing].medal}` : ""}`}>
      {steps.map((s, i) => (
        <i key={s.medal} className={`t-${s.medal}${s.done ? " full" : i === chasing && a.progress > 0 ? " half" : ""}`} />
      ))}
    </span>
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
  return progress >= 1 ? "crown" : progress >= 0.75 ? "gold" : progress >= 0.5 ? "silver" : progress >= 0.25 ? "bronze" : null;
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
          <div key={a.id} className="next-card" style={{ "--next": "var(--tier-bronze)" } as React.CSSProperties} title="First tier: bronze">
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

export function Badge({ a, compact = false }: { a: AchievementRule & Partial<Pick<Achievement, "progress" | "tier" | "unlocked_at" | "count" | "try_next" | "untried" | "needs" | "per_item">> & Partial<Pick<AchievementRarity, "unlocked_share" | "completed_share">>; compact?: boolean }) {
  const tier = a.tier ?? null;
  const catalogue = a.progress === undefined;
  const frame = tier ? `${tier}.png` : "lock_clear_no_square.png";
  const src = IMG + (a.icon ?? GENERIC_ICON);
  // The glyph takes the colour of the tier reached; grey = not started, plain = started, no tier yet (user,
  // 2026-11-02). Built-in art is one colour on transparent, so it is used as a mask; uploads keep their own colours.
  const state = catalogue ? "" : tier ? " tinted" : a.progress! > 0 ? " tinted started" : " not-started";
  const tinted = (catalogue || state.includes("tinted")) && !keepsColours(a.icon); // catalogue (no player): one neutral colour for every icon (user, 2026-11-06) // the generic cubesat (no icon of its own) is a silhouette too: it takes the tier colour like the rest (user, 2026-11-06)
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
          {a.new && <span className="tag" title="A newer challenge">new</span>}
        </strong>
        {!compact && ( // compact tiles show the description only on hover (title above) (user, 2026-11-06)
          <span className="muted rule-text">
            {ruleText(a.description)}
            {a.estimated && " *"}
          </span>
        )}
        {compact && (
          <span className="tile-pct" title={catalogue ? "Share of players who have unlocked it" : "Overall progress, counting every tier"}>
            {!catalogue && <MedalDots a={a as Achievement} />}
            {catalogue
              ? a.unlocked_share == null ? "" : a.unlocked_share === 0 ? "nobody yet" : a.unlocked_share < 0.01 ? "under 1% of players" : `${pct(a.unlocked_share)} of players`
              : pct(a.progress)}{/* "0 % of players" looked broken (Review GUI-9) */}
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
        {!catalogue && a.untried && a.untried.length > 0 && a.progress! < 1 && <UntriedLoadouts list={a.untried} />}
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

// in a file of its own: the top bar (App.tsx) needs only this, not this whole file in the first download
export { useAchievementsAccess, type AchievementsAccess } from "../achievementsAccess";
import { useAchievementsAccess } from "../achievementsAccess";

const PEEK_HYPE: Record<string, string> = {
  game: "Peak performance, one game",
  day: "Own the day",
  week: "Seven days of glory",
  month: "A month of mastery",
  all: "The long game: build a legend",
};

/** Before the launch: how many achievements per section, a few shown in full and a few more as hidden badges. */
function SneakPeek({ peek }: { peek: AchievementPeek }) {
  const total = Object.values(peek.periods).reduce((a, b) => a + (b ?? 0), 0);
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
              <img className="tier" src={IMG + "lock_clear_no_square.png"} alt="locked" />
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
          <strong>{peek.one_game}</strong> Specials: one game, everything on the line. Every one needs at least 3 players on each team.
        </p>
      )}
      <h3>
        <strong>{total}</strong> challenges to conquer
      </h3>
      <p className="muted">Land the perfect match, own the day, rule the week, and build a legacy. More being forged.</p>
      <div className="cards">
        {GROUPS.filter(([period]) => peek.periods[period]).map(([period, label]) => (
          <div key={period} className="card">
            <span className="label">{label}</span>
            <strong>{peek.periods[period]}</strong>
            <span className="muted">{PEEK_HYPE[period]}</span>
          </div>
        ))}
      </div>
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
      Have preview access? <a href={loginUrl("/challenges")}>Log in with Discord</a>
    </p>
  );
}

export function ComingSoon({ start, total, peek }: { start: string | null; total: number | null; peek: AchievementPeek | null }) {
  return (
    <>
      <EmptyState title="Coming soon">
        {total ? <><strong>{total}</strong> Flamingo Challenges</> : "Flamingo Challenges"} are on their way
        {start && !periodStarted(start) ? (
          <>
            {" "}
            — they start on <strong>{dateTime(start)}</strong>. Only matches from then on count.
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

/** A player's challenges as one bar: how many are fully complete (every tier, up to the crown) out of the regular ones (user,
 *  2026-11-26: the tier split was still confusing; the tier counts and average progress are hover text now). The Combat
 *  challenges count too (user, 2026-11-27: "Make Combat count"). On the player page and at the top of their Challenges page. */
function MedalBar({ items, overall, compact = false }: { items: Achievement[]; overall: number; compact?: boolean }) {
  const counted = items.filter((a) => a.counted && !a.prize);
  const total = counted.length;
  const complete = counted.filter((a) => a.progress >= 1).length;
  const share = total ? complete / total : 0;
  const per = (m: string) => counted.filter((a) => a.progress < 1 && a.levels && a.tier === m).length;
  const tiers = (["gold", "silver", "bronze"] as const).map((m) => `${per(m)} at ${m}`);
  const started = counted.filter((a) => a.progress > 0).length;
  const hover = [`${complete} complete`, ...tiers, `${total - started} not started`, `Average progress: ${pct(overall)}`].join(" · ");
  const headline = compact ? (
    <strong className="medal-headline compact" title={hover}>
      <img className="medal-crown" src={`${IMG}crown.png`} alt="" /><b>{complete}</b>&nbsp;of {total} fully complete
    </strong>
  ) : (
    <strong className="medal-headline" title={hover}>
      <img className="medal-crown" src={`${IMG}crown.png`} alt="" /><span><b>{complete}</b> of {total} challenges fully complete</span>
    </strong>
  );
  const bar = (
    <div className={`complete-track${compact ? " compact" : ""}`} role="progressbar" title={hover}
      aria-label={`${complete} of ${total} challenges fully complete`} aria-valuemin={0} aria-valuemax={total} aria-valuenow={complete}>
      <div style={{ width: `${share * 100}%` }} />
      <span className="complete-pct">{pct(share)}</span>
    </div>
  );
  if (compact) return <>{headline}{bar}</>;
  return <>{headline}{bar}</>;
}

function StripBody({ userId, onOpen }: { userId: string; onOpen: () => void }) {
  const result = useApi(() => getAchievements(userId), userId);
  const d = result.data;
  if (!d) {
    // while it is worked out the row says so (2026-11-27 review: a long history took 25-60 s and the row was simply
    // missing, which looked like a bug); refused or failed (coming soon, unknown player): no row
    if (!result.loading) return null;
    return (
      <section className="ach-strip ach-row" aria-label="Challenges" aria-busy="true">
        <button className="ach-row-label" onClick={onOpen} title="Open the Challenges tab">Challenges</button>
        <span className="muted">Working out this player's progress…</span>
      </section>
    );
  }
  // a big area (user, 2026-11-28: "on their profile, there should be a big button/area with info about their challenges"),
  // was one row (2026-11-26): the headline and bar, how far along each tab is, and a big button to it all (the pins have
  // their own row just below)
  const counted = d.items.filter((a) => a.counted && !a.prize);
  const path = achievementsPath(d.user_id, d.name);
  return (
    <section className="ach-strip ach-hero" aria-label="Flamingo Challenges">
      <div className="ach-hero-main">
        <button className="ach-hero-label" onClick={onOpen} title="Open the challenges">Flamingo Challenges</button>
        <MedalBar items={d.items} overall={d.overall} />
        <ul className="ach-hero-tabs">
          {HERO_TABS.map((period) => {
            const list = counted.filter((a) => a.period === period);
            if (!list.length) return null;
            return (
              <li key={period} style={{ "--tab-colour": `var(--period-${period})` } as React.CSSProperties}>
                <span className="label">{TAB_LABELS[period] ?? period}</span>
                <strong>{list.filter((a) => a.progress >= 1).length}<span className="muted"> / {list.length}</span></strong>
              </li>
            );
          })}
        </ul>
      </div>
      <Link className="ach-all-big ach-hero-button" to={path} title={`All of ${d.name}'s challenges`}>
        View all Flamingo Challenges <span aria-hidden="true">→</span>
      </Link>
    </section>
  );
}

/** The tabs of the Challenges page, in their order (Specials, One Day, One Week, Cumulative). */
const HERO_TABS = ["game", "day", "week", "all"];

export function AchievementsSummary({ userId }: { userId: string }) {
  const { visible, start, total } = useAchievementsAccess();
  if (visible) return <LaunchedSummary userId={userId} />;
  if (visible === null) return null;
  // Before the Flamingo Challenge start date set in the console: the section, but no personal progress (previewers excepted)
  return (
    <>
      <div className="section-head">
        <h2>
          Challenges <span className="tag">Coming soon</span>
        </h2>
        <Link to="/challenges">Sneak peek</Link>
      </div>
      <p className="muted">
        {total ? `${total} Flamingo Challenges` : "Flamingo Challenges"}.{" "}
        {start ? (
          <>
            This player's progress shows from <strong>{dateTime(start)}</strong>, counting matches from then on.
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
  if (!d) return result.loading ? <p className="muted" aria-busy="true">Working out this player's challenges…</p> : null;
  const counted = d.items.filter((a) => a.counted); // Combat included since 2026-11-27 (user: "Make Combat count")
  const gold = counted.filter((a) => a.progress >= 1).length; // crown for ladders, 100 % for single-step ones
  const unlocked = counted.filter((a) => a.tier).length;
  const added = d.items.filter((a) => a.new);
  return (
    <>
      <div className="section-head">
        <h2>Challenges</h2>
        <Link to={achievementsPath(d.user_id, d.name)}>View all challenges</Link>
      </div>
      <div className="cards">
        <div className="card">
          <span className="label" title="Average progress across every challenge, counting partial progress toward each one">Average progress</span>
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
        {SECTION_LIST.map(([id, label]) => {
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
        {d.visibility === "preview" && d.start && periodStarted(d.start) ? (
          <> It counts matches from <strong>{dateTime(d.start)}</strong>; it is not public yet.</>
        ) : d.start ? (
          <>
            {" "}
            It counts every match in the archive; from the launch on <strong>{dateTime(d.start)}</strong> only matches from then on count.
          </>
        ) : (
          " It counts every match in the archive; after the launch only matches from its start date count."
        )}
      </p>
    );
  // after the launch: no period box (user, 2026-11-27: removed "<start> → <end>, only matches played inside this period
  // count for challenges; the player stats pages count every match")
  return null;
}

/** The counting rules in plain words, on the overview and on every player's page. */
export function AchievementRules({ open = false }: { open?: boolean }) {
  return (
    <details className="rules-help" open={open}>
      <summary>Rules</summary>
      <ul>
        <li>
          <strong>Tiers.</strong> Almost every challenge is a ladder: bronze, silver, gold and a pink crown for completing it. The bar has a notch at each tier, the
          colour of a name is the tier reached and the number beside each tier is its target. A few single-step challenges keep white 25%, bronze
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
          Medal Collector counts the silver (or better) medals you hold on all the others.
        </li>
        <li>
          <strong>Each challenge lists its own rules</strong> under its description: whether the best game, day or 7 days counts, whether games
          under 4 minutes are ignored, and how "only" is judged. <strong>"2+ players per team"</strong> (every challenge) = both teams had at least 2 players for at least half of the match (2v2, 2v3, 3v3, 5v5 and so on all count); smaller games count for no challenge. Recordings that cover less than half a match are ignored
          everywhere.
        </li>
        <li>
          <strong>Using an item.</strong> In every game you carry a weapon, an ordnance and a tac mod, and you can change them. For each of those
          three slots the site measures how long each item was equipped during the game. <strong>"Use"</strong> an item = it was equipped for at least
          10% of the game, so trying it out for a moment does not count. <strong>"Use only"</strong> an item = it was equipped for at least 90% of
          the game in its slot, so a short switch is fine: in a 10-minute game up to 1 minute of something else is allowed.
        </li>
        <li>
          <strong>"Any 24 hours" and "any 7 days" slide</strong>: they can start at any of your games, so a session across midnight counts as one. The challenge dates are UK days, midnight to midnight UK time. Match times on the site are shown in your own timezone.
        </li>
        <li>
          <strong>Highlighted cards</strong> are close to their next medal: at least a quarter of the way there, from yellow to green as you get closer.
        </li>
        <li>
          <strong>Combat section.</strong> These use the game's own counters from the recorder's match reports, from 4 November 2026 on, apart from the
          replay stats. They count like every other challenge: toward average progress, totals, Top players, the leaderboard and Medal Collector.
        </li>
        <li>* Deaths are estimated from the recording.</li>
      </ul>
    </details>
  );
}

/** What a challenge still needs besides its target (user, 2026-11-28: "tell them how many games left"): games for the
 *  all-time averages, days and minutes in the latest 7 days for the 7-day ones. */
function NeedsLeft({ needs }: { needs: NonNullable<Achievement["needs"]> }) {
  const num = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 1 });
  const window = needs.find((n) => n.window)?.window;
  return (
    <div className="ch-needs">
      <span className="ch-rules-head">{window ? `Your latest 7 days (to ${window})` : "To count"}</span>
      <ul>
        {needs.map((n) => {
          const left = Math.max(0, n.need - n.have);
          return (
            <li key={n.what} className={left > 0 ? "todo" : "done"}>
              {num(n.have)} of {num(n.need)} {n.what}
              {left > 0 ? <b> · {num(left)} to go</b> : <span aria-label="done"> ✓</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/** "Least-used" challenges (user, 2026-11-28: "confusing, help the user understand it"): your games with each item, the
 *  lowest one being your count, and how many more games each needs for the next medal. */
function LeastUsed({ items, levels }: { items: NonNullable<Achievement["per_item"]>; levels?: number[] }) {
  const lowest = items[0]?.games ?? 0;
  const next = (levels ?? []).find((n) => n > lowest);
  const medal = next != null ? LEVELS[(levels ?? []).indexOf(next)] : null;
  const short = next != null ? items.filter((i) => i.games < next) : [];
  return (
    <div className="ch-needs">
      <span className="ch-rules-head">Your games with each (the lowest is your count)</span>
      <ul className="ch-items">
        {items.map((i) => (
          <li key={i.name} className={i.games === lowest ? "todo" : "done"}>
            {i.name}: {i.games.toLocaleString()}{i.games === lowest && <b> · play this next</b>}
          </li>
        ))}
      </ul>
      {next != null && short.length > 0 && (
        <span className="ch-items-next">
          For {medal} ({next.toLocaleString()} each): {short.map((i) => `${(next - i.games).toLocaleString()} more ${i.name}`).join(", ")}.
        </span>
      )}
    </div>
  );
}

const NEXT_TIERS = 5;

/** How to reach the next tier quickly (user, 2026-11-26): where it has to happen (one game / one day / any 7 days / adds up),
 *  the player's best so far, and the conditions a game must meet. */
function nextTierHow(a: Achievement, need: number): { where: string; conditions: string } {
  const unit = a.unit ?? "";
  const best = `${(a.count ?? 0).toLocaleString()}${unit}`;
  const goal = `${need.toLocaleString()}${unit}`;
  const where: Record<string, string> = {
    game: `In a single game: reach ${goal}. Your best game so far: ${best}.`,
    day: `Within any 24 hours: reach ${goal}. Your best 24 hours so far: ${best}.`,
    week: `Within any 7 days: reach ${goal}. Your best 7 days so far: ${best}.`,
    month: `Within any 30 days: reach ${goal}. Your best 30 days so far: ${best}.`,
    all: `${Math.max(0, need - (a.count ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit} more: everything in the challenge period adds up.`,
  };
  const tags = (a.rules ?? []).filter((t) => / min games$| players per team$|^"Only"|different days$|min on the map$|^Average| in a row$| per game$/.test(t));
  return { where: where[a.period] ?? "", conditions: tags.map(ruleSentence).join(" · ") };
}

/** The challenges closest to their next tier (user, 2026-11-26: back, with more detail): what to do, the tier being chased, how
 *  much is left, a bar to that tier, the four tier crowns and how many players have reached a tier in it. Ladders only (they have
 *  a count); Mega Prizes and the out-of-totals challenges left out. */
function NextTiers({ items }: { items: Achievement[] }) {
  const rarity = useApi(getRarity, "rarity").data;
  const share = new Map((rarity ?? []).map((r) => [r.id, r.unlocked_share]));
  const next = items
    .filter((a) => a.counted && !a.prize && a.progress < 1 && a.levels && a.levels.length > 0 && a.count != null)
    .map((a) => ({ a, next: nextMedal(a) }))
    .filter((x): x is { a: Achievement; next: { fraction: number; medal: string } } => x.next !== null)
    .sort((x, y) => y.next.fraction - x.next.fraction || LEVELS.indexOf(x.next.medal as (typeof LEVELS)[number]) - LEVELS.indexOf(y.next.medal as (typeof LEVELS)[number]))
    .slice(0, NEXT_TIERS);
  if (next.length === 0) return null;
  return (
    <section className="next-tiers" aria-label="Your next tiers">
      <h3>Your next tiers <span className="muted hint">· closest first</span></h3>
      <div className="next-tier-cards">
        {next.map(({ a, next: n }) => <TierCard key={a.id} a={a} n={n} share={share.get(a.id)} />)}
      </div>
    </section>
  );
}

/** One "next tier" card: the tier ahead, how far along, where and how it counts, and the ladder (Your next tiers, Pinned). */
function TierCard({ a, n, share: s, pin = false }: { a: Achievement; n: { fraction: number; medal: string }; share: number | null | undefined; pin?: boolean }) {
  const i = LEVELS.indexOf(n.medal as (typeof LEVELS)[number]);
  const need = a.levels![i];
  const unit = a.unit ?? "";
  const how = nextTierHow(a, need);
  return (
    <article className={`next-tier-card t-${n.medal}`}>
      <div className="next-tier-top">
        <ChallengeArt a={a} className="next-tier-icon" />
        <div className="next-tier-title">
          <strong>{a.name}</strong>
          <span className="muted">{medalRuleText(a.description, n.medal)}</span>
        </div>
        {pin && <PinButton id={a.id} done={false} />}
      </div>
      <span className="next-tier-left">{levelText(a.count ?? 0, a.levels ?? [], unit)}</span>
      <div className="next-tier-bar" role="progressbar" aria-label={`${a.name}: ${pct(n.fraction)} of the way to ${n.medal}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(n.fraction * 100)}>
        <div style={{ width: `${n.fraction * 100}%` }} />
      </div>
      <span className="next-tier-how">{how.where}</span>
      {how.conditions && <span className="muted next-tier-req">{how.conditions}</span>}
      <span className="next-tier-count">
        <b>{(a.count ?? 0).toLocaleString()}{unit}</b> / {need.toLocaleString()}{unit} <span className="muted">· {pct(n.fraction)} of the way</span>
        {pin && <span className="next-tier-finish"> · {leftToComplete(a)}</span>}
      </span>
      <div className="next-tier-ladder" aria-hidden="true">
        {a.levels!.map((_, j) => (
          <span key={j} className={j < i ? "done" : j === i ? "current" : "later"} title={`${LEVELS[j]}: ${a.levels![j].toLocaleString()}${unit}`}>
            <img src={`${IMG}${LEVELS[j]}.png`} alt="" />
          </span>
        ))}
        <span className="muted next-tier-share">{s == null ? "" : s === 0 ? "nobody has a tier yet" : `${pct(s)} of players reached a tier`}</span>
      </div>
    </article>
  );
}

const COUNT_NOUNS = /\b(games|days|kills|assists|wins|matches|rounds|deaths|minutes|checkpoints|captures|points)\b/;

/** What is left to complete a pinned ladder (the crown, its last tier) (user, 2026-11-28: "xx more games/etc to complete"):
 *  "40 more games to complete". Best-in-one-game / 24 hours / 7 days / 30 days rules say where the rest has to come from. */
function leftToComplete(a: Achievement): string {
  const levels = a.levels ?? [];
  const left = Math.max(0, Math.round(((levels[levels.length - 1] ?? 0) - (a.count ?? 0)) * 100) / 100);
  const shown = Number.isInteger(left) ? left : Math.ceil(left * 10) / 10; // round up: "0.0 more" would be wrong
  const n = shown.toLocaleString();
  const unit = a.unit ?? "";
  const noun = unit.trim() ? undefined : ruleText(a.description).match(COUNT_NOUNS)?.[1];
  const one = noun && shown === 1 ? (noun === "matches" ? "match" : noun.slice(0, -1)) : noun;
  const amount = unit.trim() ? `${n}${unit} more` : one ? `${n} more ${one}` : `${n} more`; // "3.2 m/s more", "40 more games"
  const within: Record<string, string> = { game: " in one game", day: " within 24 hours", week: " within 7 days", month: " within 30 days" };
  return `${amount}${within[a.period] ?? ""} to complete`;
}

// --- Pinned challenges (user, 2026-11-27) ------------------------------------------------------------------------------
// A player pins up to 3 challenges to work on; everyone sees them on the player page and their Challenges page, only their
// own Discord account can change them (api/pins.py). A completed one is unpinned by itself (the server drops it when it
// works out the player's challenges; the page leaves it out at once).

interface PinState extends ChallengePins {
  busy: boolean;
  error: string | null;
  toggle: (id: number) => void;
}

const PinsContext = createContext<PinState | null>(null);
const PIN_MAX = 3; // api/pins.py MAX_PINS

/** `shared`: the pins in the shared challenges answer (Cloudflare keeps it). Only a logged-in visitor asks the per-visitor
 *  /pins call (fresh pins and whether they may change them), so anonymous views cost the NAS nothing extra. */
function usePinState(userId: string, shared: number[] | undefined): PinState | null {
  const loggedIn = !!useApi(getMe, "me").data?.user;
  const loaded = useApi(() => (loggedIn ? getPins(userId) : Promise.resolve(null)), `pins|${userId}|${loggedIn}`);
  const [saved, setSaved] = useState<ChallengePins | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setSaved(null), [loaded.data]);
  const d = saved ?? loaded.data ?? (shared ? { pins: shared, max: PIN_MAX, editable: false } : null);
  if (!d) return null;
  const toggle = (id: number) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    savePin(userId, id, !d.pins.includes(id))
      .then(setSaved)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };
  return { ...d, busy, error, toggle };
}

const PIN_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
    <path d="M15 3l6 6-2.5.8-3.8 3.8.8 4.4-1.6 1.6-4-4-5.2 5.2-1.3-1.3 5.2-5.2-4-4L6.2 8.7l4.4.8 3.8-3.8z" fill="currentColor" />
  </svg>
);

/** The pin toggle for the player's own Discord account; visitors see a mark on what is pinned. Hidden once completed. */
function PinButton({ id, done, label = false }: { id: number; done: boolean; label?: boolean }) {
  const p = useContext(PinsContext);
  if (!p || done) return null;
  const on = p.pins.includes(id);
  if (!p.editable) return on ? <span className="pin-mark" title="Pinned: this player is working on it">{PIN_ICON}{label && " Pinned"}</span> : null;
  const full = !on && p.pins.length >= p.max;
  const title = on ? "Unpin" : full ? `You can pin ${p.max} challenges: unpin one first` : "Pin it to work on it (shown on your player page)";
  return (
    <button type="button" className={`pin-btn${on ? " on" : ""}${label ? " labelled" : ""}`} aria-pressed={on} disabled={p.busy || full}
      title={title} aria-label={title}
      onClick={(e) => { e.stopPropagation(); p.toggle(id); }} onKeyDown={(e) => e.stopPropagation()}>
      {PIN_ICON}{label && (on ? " Unpin" : full ? ` ${p.max} pinned` : " Pin")}
    </button>
  );
}

/** Pinned and not completed yet, in the order they were pinned. */
function pinnedItems(items: Achievement[], pins: number[]): Achievement[] {
  const by = new Map(items.map((a) => [a.id, a]));
  return pins.map((id) => by.get(id)).filter((a): a is Achievement => !!a && a.progress < 1);
}

/** The Challenges page: the pinned ones as full cards, above Your next tiers. */
function PinnedChallenges({ items }: { items: Achievement[] }) {
  const p = useContext(PinsContext);
  const rarity = useApi(getRarity, "rarity").data;
  if (!p) return null;
  const list = pinnedItems(items, p.pins);
  if (list.length === 0) {
    return p.editable ? <p className="muted pinned-hint">{PIN_ICON} Pin up to {p.max} challenges to work on: open one and press Pin. They show here and on your player page.</p> : null;
  }
  const share = new Map((rarity ?? []).map((r) => [r.id, r.unlocked_share]));
  return (
    <section className="next-tiers pinned" aria-label="Pinned challenges">
      <h3>Pinned <span className="muted hint">· {p.editable ? "what you are working on" : "what this player is working on"}</span></h3>
      {p.error && <p className="error">{p.error}</p>}
      <div className="next-tier-cards">
        {list.map((a) => {
          const n = a.levels && a.levels.length > 0 && a.count != null ? nextMedal(a) : null;
          return n ? <TierCard key={a.id} a={a} n={n} share={share.get(a.id)} pin /> : (
            <article key={a.id} className="next-tier-card">
              <div className="next-tier-top">
                <ChallengeArt a={a} className="next-tier-icon" />
                <div className="next-tier-title">
                  <strong>{a.name}</strong>
                  <span className="muted">{ruleText(a.description)}</span>
                </div>
                <PinButton id={a.id} done={false} />
              </div>
              <div className="next-tier-bar" role="progressbar" aria-label={`${a.name}: ${pct(a.progress)}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(a.progress * 100)}>
                <div style={{ width: `${a.progress * 100}%` }} />
              </div>
              <span className="next-tier-count">{pct(a.progress)} of the way</span>
            </article>
          );
        })}
      </div>
    </section>
  );
}

/** The player page: one row (like the Challenges and Mega Prizes rows), each pin as its name, a slim bar and the count. */
export function PinnedRow({ userId }: { userId: string }) {
  const { visible } = useAchievementsAccess();
  if (!visible) return null;
  return <PinnedRowBody userId={userId} />;
}

function PinnedRowBody({ userId }: { userId: string }) {
  const d = useApi(() => getAchievements(userId), userId).data;
  const p = usePinState(userId, d?.pins);
  if (!d || !p) return null;
  const list = pinnedItems(d.items, p.pins);
  if (list.length === 0) return null;
  return (
    <section className="pinned-row mega-row" aria-label="Pinned challenges">
      <Link className="mega-row-label pinned-row-label" to={achievementsPath(d.user_id, d.name)} title="Pinned challenges: open the Challenges page">
        {PIN_ICON} Pinned
      </Link>
      {list.map((a) => {
        const n = a.levels && a.levels.length > 0 && a.count != null ? nextMedal(a) : null;
        const fill = n ? n.fraction : a.progress;
        const count = n && a.levels ? `${(a.count ?? 0).toLocaleString()} / ${a.levels[LEVELS.indexOf(n.medal as (typeof LEVELS)[number])].toLocaleString()}${a.unit ?? ""}` : pct(a.progress);
        return (
          <span key={a.id} className={`mega-row-prize pinned-row-item${n ? ` t-${n.medal}` : ""}`} title={`${a.name}: ${ruleText(a.description)}${n ? ` · next: ${n.medal}` : ""}`}>
            <span className="mega-row-name">{a.name}</span>
            <span className="mega-profile-bar" role="progressbar" aria-label={`${a.name}: ${pct(fill)}${n ? ` of the way to ${n.medal}` : ""}`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(fill * 100)}>
              <span style={{ width: `${fill * 100}%` }} />
            </span>
            <span className="mega-row-count">{count}{n && <span className="muted"> {n.medal}</span>}</span>
          </span>
        );
      })}
    </section>
  );
}

export function AchievementsView({ userId }: { userId: string }) {
  const result = useApi(() => getAchievements(userId), userId);
  const data = result.data;
  const pins = usePinState(userId, data?.pins);

  return (
    <PinsContext.Provider value={pins}>
      <Status loading={result.loading} error={result.error} />
      {data && (
        <>
          <div className="medal-bar-big" aria-label="Tiers">
            <MedalBar items={data.items} overall={data.overall} />
          </div>
          {/* the player's own Mega Prize progress (user, 2026-11-26), as on their profile; only for who may see the prizes */}
          <MegaPrizesProfile userId={userId} />
          <PinnedChallenges items={data.items} />
          <NextTiers items={data.items} />
          <ScrollToNew ready />
          {/* the "Sort by closest to the next medal" checkbox is gone (user, 2026-11-27): Your next tiers above covers it */}
          <GroupedBadges items={data.items} />
          <AchievementRules />
        </>
      )}
    </PinsContext.Provider>
  );
}
