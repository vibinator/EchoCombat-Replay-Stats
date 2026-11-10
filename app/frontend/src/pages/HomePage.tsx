import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { getActivity, getLastMatch, getLatestMatches, getLive, getMapHeat, getOverview, getPlayersSeen, type GearShare, type MapHeatLayer, type MapHeatView, type MatchSummary, type PlayersSeen } from "../api";
import { BarChart, StackedBarChart } from "../components/charts";
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
            {items[0].cut && <sup className="cut">cut</sup>}
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

const RANGES: [PlayersSeen["range"], string][] = [
  ["24h", "24 hours"],
  ["7d", "7 days"],
  ["30d", "1 month"],
];

function PlayersSeenChart() {
  const [range, setRange] = useState<PlayersSeen["range"]>("7d"); // 7 days: a quiet day no longer opens on an empty chart (Review GUI-2, user 2026-11-07)
  const [anchor, setAnchor] = useState<PlayersSeen["anchor"]>("now");
  const seen = useApi(() => getPlayersSeen(range, anchor), `${range}|${anchor}`);
  const d = seen.data;
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Players seen in Combat</h2>
        <div className="tabs" role="tablist">
          {RANGES.map(([value, label]) => (
            <button key={value} role="tab" aria-selected={range === value} className={range === value ? "tab active" : "tab"} onClick={() => setRange(value)}>
              {label}
            </button>
          ))}
        </div>
      </div>
      <label className="inline-check">
        <input type="checkbox" checked={anchor === "latest"} onChange={(e) => setAnchor(e.target.checked ? "latest" : "now")} /> Count back from the
        latest recorded match instead of now
      </label>
      {!d && <Skeleton lines={2} />}
      {d && (
        <>
          <p className="muted">
            <strong className="big-number">{d.unique_players.toLocaleString()}</strong> different players in {d.matches.toLocaleString()} matches,{" "}
            {dateTime(d.start)} – {dateTime(d.end)}
          </p>
          {d.unique_players === 0 ? (
            <EmptyState title="No matches in this period">Try "count back from the latest recorded match".</EmptyState>
          ) : (
            <BarChart
              title={`Players per ${d.unit}`}
              unit=" players"
              data={d.items.map((i) => ({
                label: d.unit === "hour" ? i.bucket.slice(11, 13) + "h" : i.bucket.slice(5),
                tooltip: `${d.unit === "hour" ? `${i.bucket.slice(0, 10)} ${i.bucket.slice(11)}:00` : i.bucket} (UK time)`,
                value: i.players,
              }))}
            />
          )}
        </>
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

const HEAT_GROUPS: [MapHeatLayer["group"], string][] = [
  ["team", "Teams"],
  ["weapon", "Weapon"],
  ["ordnance", "Ordnance"],
  ["tacmod", "Tac mod"],
];

const HEAT_VIEWS: [MapHeatView, string, string][] = [
  ["favoured", "Favoured spots", "Where it is held more often than on the map as a whole"],
  ["all", "Everywhere", "Everywhere it was held"],
];

/** "Matches per map": a card per map, its minimap under the all-time heat of every counted match (counted once a
 * month on the server, map_heat.py). The heat is of both teams, or of the players holding one weapon, ordnance or
 * tac mod: one request per choice, four small PNGs, kept by the answer cache so going back to a choice is instant.
 * Gear opens on its "favoured spots" (where it is held more than usual): everywhere it was held looks much the same
 * for every piece of gear, the objective and the payload's route. Until the first answer (or if it fails) the cards
 * show the plain minimap. Clicking a card's picture opens that map large under the cards (user, 2026-11-10), over
 * the full-size minimap (loaded only then); the same tabs switch what it shows. The map's name still leads to its
 * matches. */
function MapCards({ byMap, total }: { byMap: Record<string, number>; total: number }) {
  const [layer, setLayer] = useState("team");
  const [view, setView] = useState<MapHeatView>("favoured");
  const heat = useApi(() => getMapHeat(layer, view), `map-heat:${layer}:${layer === "team" ? "" : view}`);
  const d = heat.data; // the previous choice's answer stays until the new one is there
  const layers = d?.layers ?? [];
  const group = layers.find((l) => l.key === layer)?.group ?? "team";
  const inGroup = layers.filter((l) => l.group === group);
  const shown = layers.find((l) => l.key === d?.layer);
  const [big, setBig] = useState<string | null>(null);
  const bigBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!big) return;
    bigBox.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setBig(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [big]);
  const bigImage = big ? d?.maps[big]?.image : undefined;
  const what = shown && shown.group !== "team" ? shown.label : "both teams";
  return (
    <>
      <div className="section-head map-heat-head">
        <h2>Matches per map</h2>
        {layers.length > 1 && (
          <div className="tabs" role="tablist" aria-label="All-time heatmap of">
            {HEAT_GROUPS.filter(([g]) => layers.some((l) => l.group === g)).map(([g, label]) => (
              <button key={g} role="tab" aria-selected={group === g} className={group === g ? "tab active" : "tab"}
                onClick={() => g !== group && setLayer(layers.find((l) => l.group === g)!.key)}>
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
      {group !== "team" && (
        <div className="chips map-heat-gear">
          {inGroup.map((l) => (
            <button key={l.key} className={l.key === layer ? "chip active" : "chip"} aria-pressed={l.key === layer} onClick={() => setLayer(l.key)}
              title={l.share != null ? `Held ${pct(l.share)} of the time` : undefined}>
              <GearLabel name={l.label} />
              {l.cut && <sup className="cut">cut</sup>}
            </button>
          ))}
          <span className="tabs map-heat-view" role="group" aria-label="What the heatmap shows">
            {HEAT_VIEWS.map(([v, label, hint]) => (
              <button key={v} className={view === v ? "tab active" : "tab"} aria-pressed={view === v} title={hint} onClick={() => setView(v)}>
                {label}
              </button>
            ))}
          </span>
        </div>
      )}
      <div className="map-cards">
        {Object.entries(byMap)
          .sort((a, b) => b[1] - a[1])
          .map(([m, n]) => {
            const image = d?.maps[m]?.image;
            return (
              <div key={m} className={big === m ? "map-card open" : "map-card"}>
                <button type="button" className={image ? "map-card-thumb has-heat" : "map-card-thumb"} aria-expanded={big === m}
                  title={big === m ? "Close the large view" : `Show ${title(m)} large`} onClick={() => setBig(big === m ? null : m)}>
                  <img src={`/minimaps/${m}_small.png`} alt={`${title(m)} heatmap`} loading="lazy" decoding="async" />
                  {image && <img className="map-card-heat" src={image} alt="" />}
                  <span className="map-card-zoom" aria-hidden="true">{big === m ? "−" : "+"}</span>
                </button>
                <Link to={`/matches?map=${m}`} className="map-card-name">
                  <strong>{title(m)}</strong>
                  <span className="muted">
                    {n.toLocaleString()} matches · {pct(n / total)}
                  </span>
                </Link>
              </div>
            );
          })}
      </div>
      {big && (
        <div className="panel map-heat-big" ref={bigBox}>
          <div className="section-head">
            <h3>
              {title(big)} <span className="muted">· all time · {what}</span>
            </h3>
            <span>
              <Link to={`/matches?map=${big}`}>Matches on {title(big)}</Link>
              <button type="button" className="secondary map-heat-close" onClick={() => setBig(null)}>Close</button>
            </span>
          </div>
          <div className="map-heat-big-stage">
            <div className={bigImage ? "map-heat-big-inner has-heat" : "map-heat-big-inner"}>
              <img key={big} src={`/minimaps/${big}.png`} alt={`${title(big)} minimap`} decoding="async" />
              {bigImage && <img className="map-card-heat" src={bigImage} alt={`All-time heatmap of ${what} on ${title(big)}`} />}
            </div>
          </div>
          {d && !bigImage && <p className="muted">Nothing to show for this choice on {title(big)}.</p>}
        </div>
      )}
      {d && Object.keys(d.maps).length > 0 && (
        <p className="muted map-heat-note">
          {shown && shown.group !== "team" ? (
            <>
              <span className="map-heat-scale" aria-hidden="true" />{" "}
              {d.view === "all" ? (
                <>Everywhere <GearLabel name={shown.label} /> was held, all time: brighter where it is held most.</>
              ) : (
                <>Where <GearLabel name={shown.label} /> is held more often than on the rest of the map, all time: brighter = more often than usual.</>
              )}
            </>
          ) : (
            <>All-time heatmap of every match: each spot in the colour of the team that is there most (<span className="team-text blue">blue</span> / <span className="team-text orange">orange</span>), brighter where players are most.</>
          )}{" "}
          {d.building ? "Still being counted, more matches are added as it goes." : d.updated_on && `Updated once a month, last on ${d.updated_on}.`}
        </p>
      )}
    </>
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
    getPlayersSeen("24h", "now").catch(() => undefined);
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
    <section>
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
              <div className="cards">
                <div className="card"><span className="label">Matches today</span><strong>{o.today.toLocaleString()}</strong></div>
                <div className="card"><span className="label">This week</span><strong>{o.this_week.toLocaleString()}</strong></div>
                <LastMatchCard fromOverview={o.last_match_at} />
                <RecentlyPlayedCard latest={latest[0]} />
              </div>

              {/* live video left, the newest matches right (compact, scrolls within the video's height); stacked on
                  narrow screens. Each column has its own heading. */}
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

              <div className="two-col">
                <section className="panel">
                  <div className="section-head">
                    <h2>Most active this week</h2>
                    <span>
                      <Link to="/leaderboard">Leaderboard</Link>
                    </span>
                  </div>
                  {o.top_this_week.length > 0 ? (
                    <ol className="active-list">
                      {o.top_this_week.map((p, i) => (
                        <li key={p.user_id} className={`active-row place-${i + 1}`}>
                          <span className="active-rank">{i + 1}</span>
                          <div className="active-main">
                            <Link to={playerPath(p.user_id, p.name)} className="active-name">{p.name}</Link>
                            <div className="active-bar" aria-hidden="true">
                              <div style={{ width: `${(p.games / o.top_this_week[0].games) * 100}%` }} />
                            </div>
                          </div>
                          <div className="active-stat">
                            <strong>{p.games.toLocaleString()}</strong>
                            <span className="muted">matches</span>
                          </div>
                          {p.wins != null && (
                            <div className="active-stat">
                              <strong>{pct(p.wins / p.games)}</strong>
                              <span className="muted">{p.wins.toLocaleString()} won</span>
                            </div>
                          )}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="muted">No matches recorded this week yet.</p>
                  )}
                </section>
                <PlayersSeenChart />
              </div>

              <MapCards byMap={o.by_map} total={o.matches} />

              <h2>Most popular gear</h2>
              <div className="cards gear-cards">
                <GearTop label="Weapon" items={g.top_weapons} />
                <GearTop label="Ordnance" items={g.top_ordnances} />
                <GearTop label="Tac mod" items={g.top_tacmods} />
              </div>

              <h2>All time</h2>
              <p className="muted">
                Archive {o.first_match_at && dateTime(o.first_match_at).slice(0, 10)} – {o.last_match_at && dateTime(o.last_match_at).slice(0, 10)}
              </p>
              <div className="cards">
                <div className="card"><span className="label">Matches</span><strong>{o.matches.toLocaleString()}</strong></div>
                <div className="card"><span className="label">Players</span><strong>{o.players.toLocaleString()}</strong></div>
                <div className="card"><span className="label">Recorded replay time</span><strong>{g.recorded_hours.toLocaleString()} h</strong></div>
                <div className="card"><span className="label">Time played (all players)</span><strong>{o.player_hours.toLocaleString()} h</strong></div>
                <div className="card"><span className="label">Average match</span><strong>{duration(g.avg_match_s)}</strong></div>
                <div className="card">
                  <span className="label">Longest match</span>
                  <strong>{g.longest_match ? <Link to={`/matches/${g.longest_match.id}`}>{duration(g.longest_match.duration_s)}</Link> : "–"}</strong>
                </div>
                <div className="card"><span className="label">Players per match</span><strong>{num(g.avg_players_per_match)}</strong></div>
                <div className="card" title="Estimated from players leaving the play area"><span className="label">Deaths (est.)</span><strong>{g.deaths_est.toLocaleString()}</strong></div>
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
              </div>

              <ActivityChart />
            </>
          )}
        </>
      )}
    </section>
  );
}
