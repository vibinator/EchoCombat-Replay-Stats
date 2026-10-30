import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { getAchievements, getChallenges, getMe, loginUrl, type Achievement, type AchievementRarity, type AchievementRule } from "../api";
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
  ["Unreleased gear", "Weapons and ordnances that were never released, seen in recent replays"],
  ["Gear mastery", "All four weapons, ordnances or tac mods in one game"],
  ["Wins", "Results: streaks, totals, sweeps, attack and defence"],
  ["Payload", "Time pushing or blocking the payload"],
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
          <p className="muted">Not on the original ECRanked site: they use replay data it never read.</p>
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

/** A rule with a player's progress, or just the catalogue entry when `progress` is absent. */
export function Badge({ a }: { a: AchievementRule & Partial<Pick<Achievement, "progress" | "tier" | "unlocked_at">> & Partial<Pick<AchievementRarity, "unlocked_share" | "completed_share">> }) {
  const tier = a.tier ?? null;
  const catalogue = a.progress === undefined;
  const frame = tier ? `${tier}.png` : "white_lock.png";
  return (
    <div className={`badge-card${tier || catalogue ? "" : " locked"}`} title={`${a.description}${a.estimated ? " (estimated)" : ""}`}>
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
            <div className="bar" role="progressbar" aria-valuenow={Math.round(a.progress! * 100)} aria-label={a.name}>
              <div style={{ width: `${a.progress! * 100}%` }} />
            </div>
            <span className="muted">
              {pct(a.progress)}
              {tier && ` · ${tier}`}
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
}

export function useAchievementsAccess(): AchievementsAccess {
  const d = useApi(getChallenges, "challenge").data;
  return { visible: d ? d.launched || d.preview : null, launched: !!d?.launched, preview: !!d?.preview, start: d?.start ?? null };
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

export function ComingSoon({ start }: { start: string | null }) {
  return (
    <>
      <EmptyState title="Coming soon">
        Achievements and Flamingo Challenges are on their way
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
    </>
  );
}

export function AchievementsSummary({ userId }: { userId: string }) {
  const { visible } = useAchievementsAccess();
  return visible ? (
    <LaunchedSummary userId={userId} />
  ) : visible === false ? (
    <div className="section-head">
      <h2>
        Achievements <span className="tag">coming soon</span>
      </h2>
    </div>
  ) : null;
}

function LaunchedSummary({ userId }: { userId: string }) {
  const result = useApi(() => getAchievements(userId), userId);
  const d = result.data;
  if (!d) return null;
  const gold = d.items.filter((a) => a.tier === "gold").length;
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
          <span className="label">Completed (gold)</span>
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
              {added.filter((a) => a.tier === "gold").length} / {added.length}
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
  const [show, setShow] = useState<"all" | "earned" | "open">("all");
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
                  ["all", "All"],
                  ["earned", "Unlocked (25%+)"],
                  ["open", "Locked"],
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
                .filter((a) => a.progress < 1 && (show === "all" || (show === "earned" ? a.tier : !a.tier)))
                .sort((a, b) => b.progress - a.progress)
                .map((a) => <Badge key={a.id} a={a} />)}
            </div>
          )}
          {sort === "group" && (
            <GroupedBadges items={data.items.filter((a) => show === "all" || (show === "earned" ? a.tier : !a.tier))} />
          )}
          <p className="muted footnote">
            Progress is the best ever reached (best game, best calendar day or week, or all-time total). Tiers: white 25%,
            bronze 50%, silver 75%, gold 100%. "Use only" an item = 95%+ of that game's loadout time; "use" = 5%+. Days are
            calendar days, weeks start on Monday. * Based on estimated deaths.
          </p>
        </>
      )}
    </>
  );
}
