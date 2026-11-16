import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { getActivity, getCombatBoard, getLastMatch, getLatestMatches, getLive, getOverview, getPlayersSeen, type GearShare, type GlobalStats, type MatchSummary, type PlayersSeen } from "../api";
import { BarChart, StackedBarChart } from "../components/charts";
import { Sparkline } from "../components/bars";
import { MapHeatCards } from "../components/MapHeatCards";
import { MatchCards } from "../components/MatchCards";
import { EmptyState, FitText, Skeleton } from "../components/ui";
import { GearLabel, LocalTime, Status } from "../components/common";
import { MAPS, dateTime, duration, instant, int, modeLabel, num, pct, periodLabel, playerPath, scoreText, title } from "../format";
import { useApi, useWhileVisible } from "../useApi";
import { usePageTitle } from "../usePageTitle";

function GearTop({ label, items }: { label: string; items: GearShare[] }) {
  return (
    <div className="card gear-top">
      <span className="label">{label}</span>
      {items.length === 0 ? (
        <strong>–</strong>
      ) : (
        <>
          <strong>
            <GearLabel name={items[0].name} />
          </strong>
          <span className="muted">{pct(items[0].share)} of the time</span>
          <ol className="runner-up muted">
            {items.slice(1).map((g) => (
              <li key={g.code}>
                <GearLabel name={g.name} /> {pct(g.share)}
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

/** The most used full set (weapon + ordnance + tac mod at the same time), beside the three single-slot cards. */
function LoadoutTop({ loadout }: { loadout: GlobalStats["top_loadout"] }) {
  return (
    <div className="card gear-top">
      <span className="label">Full loadout</span>
      {!loadout ? (
        <strong>–</strong>
      ) : (
        <>
          <strong className="loadout-set">
            <GearLabel name={loadout.weapon.name} />
            <GearLabel name={loadout.ordnance.name} />
            <GearLabel name={loadout.tacmod.name} />
          </strong>
          <span className="muted">{pct(loadout.share)} of the time, all three together</span>
        </>
      )}
    </div>
  );
}

type WeekTab = "active" | "kills" | "mvp";
const WEEK_TABS: [WeekTab, string][] = [
  ["active", "Most active"],
  ["kills", "Most kills"],
  ["mvp", "Most MVPs"],
];
const WEEK_ROWS = 15; // asked for; the panel shows as many as it has room for, five at least (styles.css, .week-rows)
/** one ranked row: the bar is the value against the first row's */
type WeekRow = { user_id: string; name: string; value: number; unit: string; note?: string };

/** "This week" (user, 2026-11-16: one panel instead of "Most active" and "Combat this week" side by side). The tabs
 * keep their sources apart: most active = matches in the replays; kills and MVPs = the Combat stats (the game's own
 * counters in the recorder's match reports), said under those two tabs. All three count from Monday. */
function ThisWeek({ top }: { top: { user_id: string; name: string; games: number; wins?: number }[] }) {
  const [tab, setTab] = useState<WeekTab>("active");
  const kills = useApi(() => getCombatBoard({ stat: "kills", period: "week", min_games: 1, offset: 0, limit: WEEK_ROWS }), "home-combat-kills");
  const mvp = useApi(() => getCombatBoard({ stat: "mvp", period: "week", min_games: 1, offset: 0, limit: WEEK_ROWS }), "home-combat-mvp");
  const combat = tab === "kills" ? kills : tab === "mvp" ? mvp : null;
  const tabs = kills.error ? WEEK_TABS.slice(0, 1) : WEEK_TABS; // the Combat stats are an extra: no error box on the home page
  const rows: WeekRow[] | null = combat
    ? combat.data
      ? combat.data.items.filter((r) => r.value > 0).map((r) => ({
          user_id: r.user_id, name: r.name, value: r.value, unit: tab === "kills" ? "kills" : "MVP",
          // a second number beside the ranked one: kills per death, or all award cards won (MVP is one of them)
          note: `${int(r.matches)} matches${tab === "kills" ? (r.kd != null ? ` · ${num(r.kd, 1)} K/D` : "") : r.awards > r.mvp ? ` · ${int(r.awards)} awards` : ""}`,
        }))
      : null
    : top.map((p) => ({
        user_id: p.user_id, name: p.name, value: p.games, unit: "matches",
        note: p.wins != null ? `${pct(p.wins / p.games)} won` : undefined,
      }));
  return (
    <section className="panel this-week">
      <div className="section-head">
        <h2>This week</h2>
        <span>
          {combat ? <Link to="/leaderboard?board=combat&period=week">Combat leaderboard</Link> : <Link to="/leaderboard">Leaderboard</Link>}
        </span>
      </div>
      <div className="tabs" role="tablist">
        {tabs.map(([value, label]) => (
          <button key={value} role="tab" aria-selected={tab === value} className={tab === value ? "tab active" : "tab"} onClick={() => setTab(value)}>
            {label}
          </button>
        ))}
      </div>
      {combat && <p className="muted this-week-note">From the game's own match reports (Combat stats), not the replays.</p>}
      {!rows && <Skeleton lines={3} />}
      {rows && rows.length === 0 && <p className="muted">{combat ? "No combat matches recorded this week yet." : "No matches recorded this week yet."}</p>}
      {rows && rows.length > 0 && (
        // the list fills the height the panel is given (wide screens: beside the video and the chart, where five rows
        // left most of it empty, user 2026-11-16); rows that do not fit whole are not shown
        <div className="week-rows" style={{ "--rows": Math.min(5, rows.length) } as React.CSSProperties}>
        <ol className="active-list">
          {rows.map((r, i) => (
            <li key={r.user_id} className={`active-row place-${i + 1}`}>
              <span className="active-rank">{i + 1}</span>
              <div className="active-main">
                <Link to={playerPath(r.user_id, r.name)} className="active-name">{r.name}</Link>
                <div className="active-bar" aria-hidden="true">
                  <div style={{ width: `${(r.value / rows[0].value) * 100}%` }} />
                </div>
              </div>
              <div className="active-stat">
                <strong>{int(r.value)} <span className="muted">{r.unit}</span></strong>
                {r.note && <span className="muted">{r.note}</span>}
              </div>
            </li>
          ))}
        </ol>
        </div>
      )}
    </section>
  );
}

/** A labelled group of stat cards in the "All time" block. Groups sit side by side while they fit (a group of n cards
 * asks for about n card widths), so the block takes two rows on a wide window instead of one short row per group.
 * Lined up (user, 2026-11-16, a 2500 px window): a group takes its share of the spare room by its number of cards, so
 * every card of a row is the same width; a card also asks for a tenth of the row, so a very wide window gets two full
 * rows (9 + 8 cards) instead of 15 cards and two stretched ones left over below; and the cards of a row are one
 * height across the groups (styles.css, .stat-group). */
function StatGroup({ title, n, children }: { title: string; n: number; children: React.ReactNode }) {
  return (
    <div className="stat-group" style={{ flexBasis: `max(${n * 150}px, ${n * 10}%)`, flexGrow: n, maxWidth: n * 360 }}>
      <h3 className="cards-head">{title}</h3>
      <div className="cards">{children}</div>
    </div>
  );
}

const RANGES: [PlayersSeen["range"], string][] = [
  ["24h", "24 hours"],
  ["7d", "7 days"],
  ["30d", "1 month"],
];

const SEEN_CHART_PX: [number, number] = [76, 220]; // as short as this where it has a row to itself, taller only to fill a panel

/** The height the layout has given a box, for a chart that fills it. */
function useBoxHeight(start: number): [(el: HTMLDivElement | null) => void, number] {
  const [el, setEl] = useState<HTMLDivElement | null>(null);
  const [height, setHeight] = useState(start);
  useLayoutEffect(() => {
    if (!el) return;
    setHeight(Math.round(el.getBoundingClientRect().height));
    const observer = new ResizeObserver(([entry]) => setHeight(Math.round(entry.contentRect.height)));
    observer.observe(el);
    return () => observer.disconnect();
  }, [el]);
  return [setEl, height];
}

/** One line (title, total, period) and a short chart (user, 2026-11-16, twice: "simplify this, make it smaller"). The
 * "From the latest match" tick box is gone: when nobody played in the period counted back from now (the archive can
 * stop before now), it is counted back from the newest match by itself, and the line says so. */
function PlayersSeenChart() {
  const [range, setRange] = useState<PlayersSeen["range"]>("7d"); // 7 days: a quiet day no longer opens on an empty chart (Review GUI-2, user 2026-11-07)
  const [fromLatest, setFromLatest] = useState(false);
  const anchor: PlayersSeen["anchor"] = fromLatest ? "latest" : "now";
  const seen = useApi(() => getPlayersSeen(range, anchor), `${range}|${anchor}`);
  const d = seen.data;
  useEffect(() => {
    if (d && d.range === range && d.anchor === "now" && d.unique_players === 0) setFromLatest(true);
  }, [d, range]);
  const [chartBox, boxHeight] = useBoxHeight(SEEN_CHART_PX[0]);
  const empty = !!d && d.unique_players === 0;
  return (
    <section className="panel players-seen">
      <div className="section-head">
        <div className="seen-title">
          <h2>Players seen in Combat</h2>
          {d && !empty && (
            <span className="muted" title={`${dateTime(d.start)} – ${dateTime(d.end)}`}>
              <strong className="big-number">{d.unique_players.toLocaleString()}</strong> players in {d.matches.toLocaleString()} matches
              {d.anchor === "latest" && ` · up to the latest match, ${dateTime(d.end).slice(0, 10)}`}
            </span>
          )}
        </div>
        <div className="tabs" role="tablist">
          {RANGES.map(([value, label]) => (
            <button key={value} role="tab" aria-selected={range === value} className={range === value ? "tab active" : "tab"}
              onClick={() => {
                setRange(value);
                setFromLatest(false);
              }}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {(!d || (empty && d.anchor === "now")) && <Skeleton lines={2} />}
      {d && empty && d.anchor === "latest" && <p className="muted">No matches recorded yet.</p>}
      {d && !empty && (
        <div className="seen-chart" ref={chartBox}>
          <BarChart
            title={`Players per ${d.unit}`}
            caption={false}
            height={Math.max(SEEN_CHART_PX[0], Math.min(SEEN_CHART_PX[1], boxHeight))}
            unit=" players"
            data={d.items.map((i) => ({
              label: d.unit === "hour" ? i.bucket.slice(11, 13) + "h" : i.bucket.slice(5),
              tooltip: `${d.unit === "hour" ? `${i.bucket.slice(0, 10)} ${i.bucket.slice(11)}:00` : i.bucket} (UK time)`,
              value: i.players,
            }))}
          />
        </div>
      )}
    </section>
  );
}

function ActivityChart() {
  const [bucket, setBucket] = useState<"day" | "week" | "month" | "year">("day");
  const activity = useApi(() => getActivity(bucket), bucket);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Matches recorded over time</h2>
        <div className="tabs" role="tablist">
          {(["day", "week", "month", "year"] as const).map((b) => (
            <button key={b} role="tab" aria-selected={bucket === b} className={bucket === b ? "tab active" : "tab"} onClick={() => setBucket(b)}>
              Per {b}
            </button>
          ))}
        </div>
      </div>
      {!activity.data && <Skeleton lines={2} />}
      {activity.data && activity.data.items.length > 0 && (
        <StackedBarChart
          title={bucket === "day" ? "Matches per day, by map (last 90 days of recordings)" : `Matches per ${bucket}, by map`}
          unit=" matches"
          series={MAPS.map((m) => ({ key: m, label: title(m), color: `var(--map-${m})` }))}
          data={activity.data.items.map((i) => ({
            label: periodLabel(i.period, activity.data!.bucket),
            values: i.maps,
            tooltip: `${periodLabel(i.period, activity.data!.bucket, true)}: ${i.hours} h`,
          }))}
        />
      )}
    </section>
  );
}

const TWITCH_CHANNEL = "combat_stream_bot";

/** The live Echo Combat spectator bot (offline: Twitch's offline screen). Twitch only plays embeds whose `parent`
 * is the hostname of the page showing them (and only over HTTPS, apart from localhost). Muted autoplay, so the
 * page does not start making sound. Twitch pauses an autoplaying player at once when it is smaller than 400x300 or
 * not visible enough (user 2026-11-01: it started and paused straight away): it loads once half of it is on screen,
 * and a smaller one (phones) does not autoplay, it shows its play button instead. */
function LiveStream() {
  // The player is several MB of third-party script, video and trackers: it loads only when the visitor asks for it
  // (click to load, Review SEC-5 / PERF-5, approved 2026-11-07). Until then a poster says whether the bot is live.
  const box = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(false);
  const [autoplay, setAutoplay] = useState(true);
  const [live, setLive] = useState<boolean | null>(null);
  useWhileVisible(() => {
    if (show) return;
    getLive()
      .then((d) => setLive(d.live))
      .catch(() => undefined);
  }, LIVE_POLL_MS);
  const open = () => {
    const r = box.current?.getBoundingClientRect();
    setAutoplay(!!r && r.width >= 400 && r.height >= 300);
    setShow(true);
  };
  const src = `https://player.twitch.tv/?channel=${TWITCH_CHANNEL}&parent=${encodeURIComponent(window.location.hostname)}&muted=true&autoplay=${autoplay}`;
  return (
    <div className="twitch-embed" ref={box}>
      {show ? (
        <iframe src={src} title="Live Echo Combat spectator bot on Twitch" allow="autoplay; fullscreen; picture-in-picture; encrypted-media" allowFullScreen />
      ) : (
        <button type="button" className={`twitch-poster${live ? " live" : ""}`} onClick={open} aria-label="Load the Twitch player">
          <span className="twitch-state">{live ? "● Live now" : live === false ? "Offline" : "Twitch"}</span>
          <span className="twitch-play" aria-hidden="true">▶</span>
          <strong>{live ? "Watch the game" : "Open the player"}</strong>
          <small>Loads the Twitch player and its scripts only when you click.</small>
        </button>
      )}
    </div>
  );
}

/** "3 min ago", "5 h ago", "2 days ago" */
function since(iso: string, now: number): string {
  const min = Math.max(0, (now - instant(iso).getTime()) / 60000); // new Date() would read a match time as the viewer's own clock
  if (min < 60) return `${Math.round(min)} min ago`;
  if (min < 48 * 60) return `${Math.round(min / 60)} h ago`;
  return `${Math.round(min / 1440)} days ago`;
}

const LAST_MATCH_POLL_MS = 60_000; // Cloudflare keeps the answer as long, asking more often gains nothing
const LIVE_POLL_MS = 10_000; // "Game in progress": never cached, the server checks Twitch as often
const TICK_MS = 20_000;

/** The "Last match" card, kept current while the tab is visible: "x min ago" counts on by itself, and the newest
 * match time is asked separately because the overview is rebuilt only every few minutes (and then refreshed too).
 * While the spectator bot is live on Twitch a game is being played: a "Game in progress" card appears beside it
 * (none at all otherwise, user 2026-11-01). */
/** Map of the newest match, linking to it; mode and score underneath. */
function RecentlyPlayedCard({ latest }: { latest: MatchSummary | undefined }) {
  return (
    <div className="card">
      <span className="label">Recently played</span>
      <strong>{latest ? <Link to={`/matches/${latest.id}`}>{title(latest.map)}</Link> : "–"}</strong>
      {latest && <span className="muted">{modeLabel(latest.mode)} · {scoreText(latest)}</span>}
    </div>
  );
}

function LastMatchCard({ fromOverview }: { fromOverview: string | null }) {
  const [live, setLive] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [now, setNow] = useState(Date.now);
  useWhileVisible(() => {
    getLastMatch()
      .then((d) => setLive(d.last_match_at))
      .catch(() => undefined); // keep what is shown
    getOverview().catch(() => undefined); // refreshed in the background once a minute old; the page updates if it changed
  }, LAST_MATCH_POLL_MS);
  useWhileVisible(() => {
    getLive()
      .then((d) => setPlaying(d.live === true))
      .catch(() => undefined); // keep what is shown
  }, LIVE_POLL_MS);
  useWhileVisible(() => setNow(Date.now()), TICK_MS);
  const last = live && (!fromOverview || live > fromOverview) ? live : fromOverview;
  return (
    <>
      <div className="card">
        <span className="label">Last match</span>
        <strong>{last ? since(last, now) : "–"}</strong>
        {last && <span className="muted"><LocalTime iso={last} /></span>}
      </div>
      {playing && (
        <div className="card live-card">
          <span className="label">Right now</span>
          <strong className="live-text">Game in progress</strong>
          <a href={`https://www.twitch.tv/${TWITCH_CHANNEL}`} target="_blank" rel="noopener noreferrer">Watch on Twitch</a>
        </div>
      )}
    </>
  );
}

/** Most useful first: what is happening now (recent matches, who is playing), then maps and gear, then the
 * all-time numbers and history. */
export function HomePage() {
  usePageTitle(null);
  const overview = useApi(getOverview, "overview");
  // the two charts are only drawn once the overview is there; ask for their data now instead of afterwards
  useEffect(() => {
    getActivity("day").catch(() => undefined);
    getPlayersSeen("7d", "now").catch(() => undefined); // the range the chart opens on
  }, []);
  const o = overview.data;
  const g = o?.global;
  // the newest matches are asked separately: the overview is rebuilt only every few minutes
  const [polled, setPolled] = useState<MatchSummary[] | null>(null);
  useWhileVisible(() => {
    getLatestMatches()
      .then(setPolled)
      .catch(() => undefined); // keep what is shown
  }, LAST_MATCH_POLL_MS);
  const latest = polled ?? o?.latest ?? [];

  return (
    <section className="home">
      <div className="hero">
        <h1>Echo Combat Stats</h1>
        <p className="muted">Match and player statistics from the Echo Combat replay archive.</p>
        <p className="announcement">
          <strong>Echo Combat has been released to Quest Standalone</strong> as of Oct 30th 2026. Learn more on{" "}
          <a href="https://discord.gg/echo-vr-lounge" target="_blank" rel="noopener noreferrer">Discord</a> and/or at{" "}
          <a href="https://echovrce.com" target="_blank" rel="noopener noreferrer">echovrce.com</a>.
        </p>
      </div>

      {!o && !overview.error && <Skeleton cards={6} lines={0} />}
      <Status loading={false} error={overview.error} />

      {o && g && (
        <>
          {o.matches === 0 ? (
            <EmptyState title="No matches yet">
              Replays are still being imported.
            </EmptyState>
          ) : (
            <>
              <div className="cards home-strip">
                <LastMatchCard fromOverview={o.last_match_at} />
                {o.trend ? (
                  <>
                    <div className="card" title="Matches started in the last 7 days (to the minute). The line: matches per day, last 4 weeks (today so far at the end).">
                      <span className="label">Matches · last 7 days</span>
                      <strong>{int(o.trend.matches_7d)}</strong>
                      {/* no "vs the 7 days before" on these three cards (user, 2026-11-16): the number and the line are enough */}
                      <span className="muted">{int(o.today)} today</span>
                      <Sparkline values={o.trend.matches} label="Matches per day, last 4 weeks" />
                    </div>
                    <div className="card" title="Players whose first recorded match was in the last 7 days. The line: new players per day, last 4 weeks.">
                      <span className="label">New players · last 7 days</span>
                      <strong>{int(o.trend.new_7d)}</strong>
                      <Sparkline values={o.trend.new_players} label="New players per day, last 4 weeks" />
                    </div>
                  </>
                ) : ( /* an overview from before 2026.11.16.18 (cached a few minutes): the calendar-week cards */
                  <div className="card">
                    <span className="label">Matches today</span>
                    <strong>{o.today.toLocaleString()}</strong>
                    <span className="muted">{o.this_week.toLocaleString()} this week</span>
                  </div>
                )}
                {o.newcomers && (
                  <div className="card" title={`Of the players whose first match was 8 to 14 days ago, the share who played again on a later day within ${o.newcomers.return_days} days.`}>
                    <span className="label">New players who came back</span>
                    <strong>{pct(o.newcomers.return_rate)}</strong>
                    <span className="muted">{int(o.newcomers.returned)} of {int(o.newcomers.return_group)}</span>
                  </div>
                )}
                <RecentlyPlayedCard latest={latest[0]} />
              </div>

              {/* live video left, the newest matches right (compact, scrolls within the video's height); stacked on
                  narrow screens. Each column has its own heading. */}
              {/* wide screens: one grid of video | latest matches | most active, then players seen | Combat (styles.css) */}
              <div className="home-top">
              <div className="live-latest">
                <div className="live-latest-col">
                  <div className="section-head">
                    <h2>Live on Twitch</h2>
                    <span>
                      <a href={`https://www.twitch.tv/${TWITCH_CHANNEL}`} target="_blank" rel="noopener noreferrer">Open on Twitch</a>
                    </span>
                  </div>
                  <LiveStream />
                </div>
                <div className="live-latest-col">
                  <div className="section-head">
                    <h2>Latest matches</h2>
                    <span>
                      <Link to="/matches">All matches</Link>
                    </span>
                  </div>
                  <div className="live-latest-matches">
                    <MatchCards matches={latest} compact />
                  </div>
                </div>
              </div>

              <div className="two-col home-week">
                <ThisWeek top={o.top_this_week} />
                <PlayersSeenChart />
              </div>
              </div>

              <MapHeatCards byMap={o.by_map} total={o.matches} avgByMap={g.avg_match_s_by_map} />

              <h2>Most popular gear</h2>
              <div className="cards gear-cards">
                <GearTop label="Weapon" items={g.top_weapons} />
                <GearTop label="Ordnance" items={g.top_ordnances} />
                <GearTop label="Tac mod" items={g.top_tacmods} />
                <LoadoutTop loadout={g.top_loadout} />
              </div>

              <h2>
                All time{" "}
                <span className="muted heading-note">
                  archive {o.first_match_at && dateTime(o.first_match_at).slice(0, 10)} – {o.last_match_at && dateTime(o.last_match_at).slice(0, 10)}
                </span>
              </h2>
              <div className="stat-groups">
              <StatGroup title="Archive" n={5}>
                <div className="card"><span className="label">Matches</span><strong>{o.matches.toLocaleString()}</strong></div>
                <div className="card"><span className="label">Players</span><strong>{o.players.toLocaleString()}</strong></div>
                <div className="card"><span className="label">Time played (all players)</span><strong>{o.player_hours.toLocaleString()} h</strong></div>
                <div className="card">
                  <span className="label">Average match</span>
                  <strong>{duration(g.avg_match_s)}</strong>
                  {Object.entries(g.avg_match_s_by_mode ?? {}).map(([mode, s]) => (
                    <span key={mode} className="muted">{modeLabel(mode)} {duration(s)}</span>
                  ))}
                </div>
                <div className="card"><span className="label">Players per match</span><strong>{num(g.avg_players_per_match)}</strong></div>
              </StatGroup>
              {g.fun && (
                <StatGroup title="Fun facts" n={4}>
                  <div className="card"><span className="label">Emotes used</span><strong>{int(g.fun.emotes)}</strong></div>
                  <div className="card" title="Share of all play time spent upside down">
                    <span className="label">Upside down</span><strong>{pct(g.fun.upside_down_share)}</strong>
                    <span className="muted">of all play time</span>
                  </div>
                  <div className="card" title="Share of play time with the left-hand setting">
                    <span className="label">Left-handed</span><strong>{pct(g.fun.left_arm_share)}</strong>
                    <span className="muted">of play time</span>
                  </div>
                  <div className="card" title="Share of player appearances that left before the match ended">
                    <span className="label">Left early</span><strong>{pct(g.fun.left_early_share)}</strong>
                    <span className="muted">of players in a match</span>
                  </div>
                </StatGroup>
              )}
              <StatGroup title="Records" n={6}>
                <div className="card">
                  <span className="label">Longest match</span>
                  <strong>{g.longest_match ? <Link to={`/matches/${g.longest_match.id}`}>{duration(g.longest_match.duration_s)}</Link> : "–"}</strong>
                </div>
                <div className="card">
                  <span className="label">Fastest player</span>
                  <strong>{g.fastest ? <FitText title={g.fastest.name}><Link to={playerPath(g.fastest.user_id, g.fastest.name)}>{g.fastest.name}</Link></FitText> : "–"}</strong>
                  {g.fastest && <span className="muted">{num(g.fastest.top_speed)} m/s</span>}
                </div>
                <div className="card">
                  <span className="label">Most matches</span>
                  <strong>{g.most_active ? <FitText title={g.most_active.name}><Link to={playerPath(g.most_active.user_id, g.most_active.name)}>{g.most_active.name}</Link></FitText> : "–"}</strong>
                  {g.most_active && <span className="muted">{g.most_active.games.toLocaleString()} matches</span>}
                </div>
                <div className="card">
                  <span className="label">Busiest day</span>
                  <strong>{g.busiest_day?.day ?? "–"}</strong>
                  {g.busiest_day && <span className="muted">{int(g.busiest_day.matches)} matches</span>}
                </div>
                {g.payload_decided != null && (
                  <div className="card" title="Payload matches with a known result">
                    <span className="label">Payload attack wins</span>
                    <strong>{pct(g.payload_attack_win_rate ?? null)}</strong>
                    <span className="muted">of {g.payload_decided.toLocaleString()} decided</span>
                  </div>
                )}
                {g.capture_wins && (
                  <div className="card">
                    <span className="label">Capture point wins</span>
                    <strong>
                      <span className="team-text blue">{int(g.capture_wins.blue)}</span> – <span className="team-text orange">{int(g.capture_wins.orange)}</span>
                    </strong>
                    <span className="muted">blue – orange · of {int(g.capture_wins.blue + g.capture_wins.orange)} decided</span>
                  </div>
                )}
              </StatGroup>
              <StatGroup title="More archive numbers" n={2}>
                <div className="card"><span className="label">Recorded replay time</span><strong>{g.recorded_hours.toLocaleString()} h</strong></div>
                <div className="card" title="Estimated from players leaving the play area"><span className="label">Deaths (est.)</span><strong>{g.deaths_est.toLocaleString()}</strong></div>
              </StatGroup>
              </div>

              <ActivityChart />
            </>
          )}
        </>
      )}
    </section>
  );
}
