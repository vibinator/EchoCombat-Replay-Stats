import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { LEVELS, getAchievements, getChallenges, getMe, loginUrl, type Achievement, type AchievementPeek, type AchievementRarity, type AchievementRule } from "../api";
import { pct } from "../format";
import { useApi } from "../useApi";
import { Status } from "./common";
import { EmptyState } from "./ui";

// Old ecranked.com badge art (app/images -> public/achievements). Tier frames = progress levels
// 25 / 50 / 75 / 100 % (white / bronze / silver / gold); the lock emblem = below 25 %.
const IMG = "/achievements/";
const GENERIC_ICON = "happy_cubesat.png";
export const GROUPS: [Achievement["period"], string][] = [
  ["day", "In one day"],
  ["week", "In one week"],
  ["game", "In one game"],
  ["all", "All time"],
];

// New achievements (not on the original site) get their own section, in this theme order.
export const NEW_GROUPS: [string, string][] = [
  ["Unreleased gear", "Weapons and ordnances that were never released, seen in recent replays (now public)"],
  ["Gear mastery", "All four weapons, ordnances or tac mods in one game"],
  ["Wins", "Results: streaks, totals, sweeps, attack and defence"],
  ["Payload", "Time pushing or blocking the payload"],
  ["Activity", "How often and how long you play"],
  ["Emotes", ""],
];

type AnyBadge = Parameters<typeof Badge>[0]["a"];

/** Original achievements by period, then the new ones by theme. */
export function GroupedBadges<T extends AnyBadge>({ items }: { items: T[] }) {
  const original = items.filter((a) => !a.new);
  const added = items.filter((a) => a.new);
  return (
    <>
      {GROUPS.map(([period, label]) => {
        const group = original.filter((a) => a.period === period);
        return group.length === 0 ? null : (
          <div key={period}>
            <h3>{label}</h3>
            <div className="badges">{group.map((a) => <Badge key={a.id} a={a} />)}</div>
          </div>
        );
      })}
      {added.length > 0 && (
        <section className="new-challenges" id="new">
          <h2>
            New challenges <span className="tag">new</span>
          </h2>
          <p className="muted">Not on the original ECRanked site: they use replay data it never read. More being developed.</p>
          {[...NEW_GROUPS, ["More", ""] as [string, string]].map(([name, hint]) => {
            const known = NEW_GROUPS.some(([n]) => n === name);
            const group = added.filter((a) => (known ? a.group === name : !NEW_GROUPS.some(([n]) => n === a.group)));
            return group.length === 0 ? null : (
              <div key={name}>
                <h3>
                  {name} {hint && <span className="muted hint">· {hint}</span>}
                </h3>
                <div className="badges">{group.map((a) => <Badge key={a.id} a={a} />)}</div>
              </div>
            );
          })}
        </section>
      )}
    </>
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

/** A rule with a player's progress, or just the catalogue entry when `progress` is absent. */
/** Tiered achievements: "12 / 25 for platinum", or the top medal once every target is reached. */
function levelText(count: number, levels: number[], unit = ""): string {
  const next = levels.findIndex((need) => count < need);
  if (next < 0) return `${count.toLocaleString()}${unit} · ${LEVELS[levels.length - 1]} (max)`;
  return `${count.toLocaleString()} / ${levels[next].toLocaleString()}${unit} for ${LEVELS[next]}`;
}

export function Badge({ a }: { a: AchievementRule & Partial<Pick<Achievement, "progress" | "tier" | "unlocked_at" | "count">> & Partial<Pick<AchievementRarity, "unlocked_share" | "completed_share">> }) {
  const tier = a.tier ?? null;
  const catalogue = a.progress === undefined;
  const frame = tier ? `${tier}.png` : "white_lock.png";
  return (
    <div className={`badge-card${tier || catalogue ? "" : " locked"}${tier ? ` t-${tier}` : ""}`} title={`${a.description}${a.estimated ? " (estimated)" : ""}`}>
      <div className="badge-art">
        <img className="icon" src={IMG + (a.icon ?? GENERIC_ICON)} alt="" />
        {!catalogue && <img className="tier" src={IMG + frame} alt={tier ?? "locked"} />}
      </div>
      <div className="badge-text">
        <strong>
          {a.name}
          {a.new && <span className="tag" title="Not on the original ECRanked site: uses data it never read">new</span>}
        </strong>
        <span className="muted">
          {a.description}
          {a.estimated && " *"}
        </span>
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
                {theme === "Unreleased gear" && <span className="muted">Now public</span>}
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
  const failed = new URLSearchParams(location.search).get("login") === "failed";
  if (!me?.enabled) return null;
  if (me.user)
    return (
      <p className="muted">
        Logged in as <strong>{me.user.name}</strong>, but your Discord account does not have the preview role.
      </p>
    );
  return (
    <p className="muted">
      {failed && <>The Discord login did not work, please try again. </>}
      Have preview access? <a href={loginUrl("/achievements")}>Log in with Discord</a>
    </p>
  );
}

export function ComingSoon({ start, total, peek }: { start: string | null; total: number | null; peek: AchievementPeek | null }) {
  return (
    <>
      <EmptyState title="Coming soon">
        {total ? <><strong>{total}</strong> achievements</> : "Achievements"} and Flamingo Challenges are on their way
        {start ? (
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
  const gold = d.items.filter((a) => a.progress >= 1).length; // diamond for ladders, 100 % for single-step ones
  const unlocked = d.items.filter((a) => a.tier).length;
  const added = d.items.filter((a) => a.new);
  return (
    <>
      <div className="section-head">
        <h2>Achievements</h2>
        <Link to={`/achievements?player=${encodeURIComponent(userId)}`}>View all achievements</Link>
      </div>
      <div className="cards">
        <div className="card">
          <span className="label">Overall</span>
          <strong>{pct(d.overall)}</strong>
        </div>
        <div className="card">
          <span className="label">Completed (diamond)</span>
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
          <Link className="card link-card" to={`/achievements?player=${encodeURIComponent(userId)}#new`}>
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
        <strong>Preview</strong> — only people with the Discord preview role see this. It counts every match in the archive;
        {d.start ? (
          <>
            {" "}
            from the launch on <strong>{d.start}</strong> only matches from that day count.
          </>
        ) : (
          " after the launch only matches from its start date count."
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

export function AchievementsView({ userId }: { userId: string }) {
  const result = useApi(() => getAchievements(userId), userId);
  const [show, setShow] = useState<"open" | "done" | "all">("open"); // completed ones are tucked away by default
  const [sort, setSort] = useState<"group" | "closest">("group");
  const data = result.data;

  return (
    <>
      <Status loading={result.loading} error={result.error} />
      {data && (
        <>
          <div className="filters">
            <div className="card">
              <span className="label">Overall</span>
              <strong>{pct(data.overall)}</strong>
            </div>
            <div className="card">
              <span className="label">Completed</span>
              <strong>
                {data.completed} / {data.total}
              </strong>
            </div>
            <div className="tabs" role="tablist">
              {(
                [
                  ["open", `In progress (${data.total - data.completed})`],
                  ["done", `Completed (${data.completed})`],
                  ["all", "All"],
                ] as const
              ).map(([value, label]) => (
                <button key={value} role="tab" aria-selected={show === value} className={show === value ? "tab active" : "tab"} onClick={() => setShow(value)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          {sort === "group" && <JumpToNew ready />}
          <label className="inline-check">
            <input type="checkbox" checked={sort === "closest"} onChange={(e) => setSort(e.target.checked ? "closest" : "group")} /> Sort by closest
            to completing
          </label>
          {sort === "closest" && (
            <div className="badges">
              {data.items
                .filter((a) => a.progress < 1 && show !== "done")
                .sort((a, b) => b.progress - a.progress)
                .map((a) => <Badge key={a.id} a={a} />)}
            </div>
          )}
          {show === "done" && data.completed === 0 && <p className="muted">Nothing completed yet: a challenge lands here once it reaches diamond (or 100 %).</p>}
          {show === "open" && data.completed === data.total && <p className="muted">Everything is completed. Look under Completed.</p>}
          {sort === "group" && (
            <GroupedBadges items={data.items.filter((a) => show === "all" || (show === "done") === a.progress >= 1)} />
          )}
          <p className="muted footnote">
            Almost every challenge is a ladder of medals (bronze, silver, gold, platinum, diamond): the bar has one step per medal, the
            colour of a name is the medal reached, and the number under each step is its target. Progress is the best ever reached (best game,
            best calendar day or week, or all-time total). A few single-step challenges keep white 25%, bronze 50%, silver 75%, gold 100%.
            "Use only" an item = 95%+ of that game's loadout time; "use" = 5%+. Days are
            calendar days, weeks start on Monday. * Based on estimated deaths.
          </p>
        </>
      )}
    </>
  );
}
