import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { getActivity, getOverview, getPlayersSeen, type GearShare, type PlayersSeen } from "../api";
import { BarChart, StackedBarChart } from "../components/charts";
import { MatchCards } from "../components/MatchCards";
import { PlayerSearch } from "../components/PlayerSearch";
import { EmptyState, FitText, Skeleton } from "../components/ui";
import { Status } from "../components/common";
import { MAPS, dateTime, duration, num, pct, periodLabel, title } from "../format";
import { useApi } from "../useApi";

function GearTop({ label, items }: { label: string; items: GearShare[] }) {
  return (
    <div className="card gear-top">
      <span className="label">{label}</span>
      {items.length === 0 ? (
        <strong>–</strong>
      ) : (
        <>
          <strong>
            {items[0].name}
            {items[0].cut && <sup className="cut">cut</sup>}
          </strong>
          <span className="muted">{pct(items[0].share)} of the time</span>
          <ol className="runner-up muted">
            {items.slice(1).map((g) => (
              <li key={g.code}>
                {g.name} {pct(g.share)}
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
  const [range, setRange] = useState<PlayersSeen["range"]>("7d");
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
                tooltip: d.unit === "hour" ? `${i.bucket.slice(0, 10)} ${i.bucket.slice(11)}:00` : i.bucket,
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
  const [bucket, setBucket] = useState<"day" | "month" | "year">("month");
  const activity = useApi(() => getActivity(bucket), bucket);
  return (
    <section className="panel">
      <div className="section-head">
        <h2>Matches recorded over time</h2>
        <div className="tabs" role="tablist">
          {(["day", "month", "year"] as const).map((b) => (
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
 * page does not start making sound. */
function LiveStream() {
  // The player is several MB of third-party script and video: load it once the page has settled and the box is on
  // screen, so it does not compete with the numbers (user, 2026-10-31: the home page was slow).
  const box = useRef<HTMLDivElement>(null);
  const [show, setShow] = useState(false);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    let timer = 0;
    const seen = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        timer = window.setTimeout(() => setShow(true), 1200);
        seen.disconnect();
      }
    });
    seen.observe(el);
    return () => {
      seen.disconnect();
      window.clearTimeout(timer);
    };
  }, []);
  const src = `https://player.twitch.tv/?channel=${TWITCH_CHANNEL}&parent=${encodeURIComponent(window.location.hostname)}&muted=true`;
  return (
    <div className="twitch-embed" ref={box}>
      {show && <iframe src={src} title="Live Echo Combat spectator bot on Twitch" allowFullScreen />}
    </div>
  );
}

/** "3 min ago", "5 h ago", "2 days ago" */
function since(iso: string): string {
  const min = Math.max(0, (Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 60) return `${Math.round(min)} min ago`;
  if (min < 48 * 60) return `${Math.round(min / 60)} h ago`;
  return `${Math.round(min / 1440)} days ago`;
}

/** Most useful first: what is happening now (recent matches, who is playing), then maps and gear, then the
 * all-time numbers and history. */
export function HomePage() {
  const overview = useApi(getOverview, "overview");
  // the two charts are only drawn once the overview is there; ask for their data now instead of afterwards
  useEffect(() => {
    getActivity("month").catch(() => undefined);
    getPlayersSeen("7d", "now").catch(() => undefined);
  }, []);
  const o = overview.data;
  const g = o?.global;

  return (
    <section>
      <div className="hero">
        <h1>Echo Combat replay stats</h1>
        <p className="muted">Match and player statistics from the Echo Combat replay archive.</p>
        <p className="announcement">
          <strong>Echo Combat has been released to Quest Standalone</strong> as of Oct 30th 2026. Learn more on{" "}
          <a href="https://discord.gg/echo-vr-lounge" target="_blank" rel="noopener noreferrer">Discord</a> and/or at{" "}
          <a href="https://echovrce.com" target="_blank" rel="noopener noreferrer">echovrce.com</a>.
        </p>
        <PlayerSearch large />
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
                <div className="card">
                  <span className="label">Last match</span>
                  <strong>{o.last_match_at ? since(o.last_match_at) : "–"}</strong>
                  {o.last_match_at && <span className="muted">{dateTime(o.last_match_at)}</span>}
                </div>
                <div className="card">
                  <span className="label">Most played map</span>
                  <strong>{o.most_played_map ? <Link to={`/matches?map=${o.most_played_map}`}>{title(o.most_played_map)}</Link> : "–"}</strong>
                  {o.most_played_map && <span className="muted">{pct(o.by_map[o.most_played_map] / o.matches)} of matches</span>}
                </div>
              </div>

              <div className="section-head">
                <h2>Latest matches</h2>
                <span>
                  <a href={`https://www.twitch.tv/${TWITCH_CHANNEL}`} target="_blank" rel="noopener noreferrer">Live on Twitch</a>
                  {" · "}
                  <Link to="/matches">All matches</Link>
                </span>
              </div>
              {/* live video left, the newest matches right (compact, scrolls within the video's height); stacked on
                  narrow screens */}
              <div className="live-latest">
                <LiveStream />
                <div className="live-latest-matches">
                  <MatchCards matches={o.latest} compact />
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
                            <Link to={`/players/${p.user_id}`} className="active-name">{p.name}</Link>
                            <div className="active-bar" aria-hidden="true">
                              <div style={{ width: `${(p.games / o.top_this_week[0].games) * 100}%` }} />
                            </div>
                          </div>
                          <div className="active-stat">
                            <strong>{p.games.toLocaleString()}</strong>
                            <span className="muted">matches</span>
                          </div>
                          <div className="active-stat">
                            <strong>{pct(p.wins / p.games)}</strong>
                            <span className="muted">{p.wins.toLocaleString()} won</span>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="muted">No matches recorded this week yet.</p>
                  )}
                </section>
                <PlayersSeenChart />
              </div>

              <h2>Matches per map</h2>
              <div className="map-cards">
                {Object.entries(o.by_map)
                  .sort((a, b) => b[1] - a[1])
                  .map(([m, n]) => (
                    <Link key={m} to={`/matches?map=${m}`} className="map-card">
                      <img src={`/minimaps/${m}_small.png`} alt="" loading="lazy" decoding="async" />
                      <strong>{title(m)}</strong>
                      <span className="muted">
                        {n.toLocaleString()} matches · {pct(n / o.matches)}
                      </span>
                    </Link>
                  ))}
              </div>

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
                  <strong>{g.fastest ? <FitText title={g.fastest.name}><Link to={`/players/${g.fastest.user_id}`}>{g.fastest.name}</Link></FitText> : "–"}</strong>
                  {g.fastest && <span className="muted">{num(g.fastest.top_speed)} m/s</span>}
                </div>
                <div className="card">
                  <span className="label">Most matches</span>
                  <strong>{g.most_active ? <FitText title={g.most_active.name}><Link to={`/players/${g.most_active.user_id}`}>{g.most_active.name}</Link></FitText> : "–"}</strong>
                  {g.most_active && <span className="muted">{g.most_active.games.toLocaleString()} matches</span>}
                </div>
                <div className="card">
                  <span className="label">Busiest day</span>
                  <strong>{g.busiest_day?.day ?? "–"}</strong>
                  {g.busiest_day && <span className="muted">{g.busiest_day.matches} matches</span>}
                </div>
                <div className="card" title="Payload matches with a known result">
                  <span className="label">Payload attack wins</span>
                  <strong>{pct(g.payload_attack_win_rate)}</strong>
                  <span className="muted">of {g.payload_decided.toLocaleString()} decided</span>
                </div>
                <div className="card">
                  <span className="label">Capture point wins</span>
                  <strong>
                    <span className="team-text blue">{g.capture_wins.blue}</span> – <span className="team-text orange">{g.capture_wins.orange}</span>
                  </strong>
                  <span className="muted">blue – orange</span>
                </div>
              </div>

              <ActivityChart />
            </>
          )}
        </>
      )}
    </section>
  );
}
