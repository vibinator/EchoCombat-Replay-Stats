import { Link } from "react-router";
import { getCombatAwards, getCombatMatch, getCombatPlayer, type CombatAward, type CombatAwardCount, type CombatAwardsWon, type CombatEvents, type CombatMatchDetail, type CombatMatchPlayer, type CombatWeapon, type Period } from "../api";
import { LocalTime, TableWrap, TeamBadge } from "./common";
import { InfoTip } from "./ui";
import { duration, hoursMinutes, int, num, playerPath, title } from "../format";
import { useApi } from "../useApi";

/** How an award is earned, for a tooltip: "Guard · Objective time: the most time spent on the objective." */
export function awardHint(a: CombatAward): string {
  return a.stat ? `${a.name} · ${a.stat}: ${a.description}` : `${a.name}: ${a.description}`;
}

/** One of the game's end-of-match award cards as a small badge; hover / focus tells how it is earned. */
export function AwardBadge({ award, count }: { award: CombatAward; count?: number }) {
  return (
    <span className={`award-badge award-${award.key}`} title={awardHint(award)} aria-label={awardHint(award)} tabIndex={0}>
      {award.name}
      {count != null && count > 1 && <span className="award-count">×{int(count)}</span>}
    </span>
  );
}

/** The award badges a player won in one match: "–" for none, nothing at all when the report does not know them. */
export function AwardBadges({ awards }: { awards: CombatAwardsWon | undefined }) {
  if (awards == null) return null;
  if (awards.length === 0) return <span className="muted">–</span>;
  return <span className="award-badges">{awards.map((a) => <AwardBadge key={a.key} award={a} />)}</span>;
}

/**
 * The list of every award the game can hand out and how it is earned (from /api/combat/awards). There are no thresholds:
 * the top player of the stat gets the card, so the same number can win one match and not the next.
 */
export function AwardGuide({ open }: { open?: boolean }) {
  const { data } = useApi(getCombatAwards, "combat-awards");
  return (
    <details className="award-guide" open={open}>
      <summary>How the game&apos;s awards are earned</summary>
      <p className="muted footnote">
        At the end of a match the game shows award cards on the scoreboard: <strong>MVP</strong> for the highest score, plus up to
        three more. Each card goes to the player with the <em>highest</em> value of that stat in the match; there is no minimum, so
        a single kill can win Assassin in a quiet match. Which three extra cards appear is the game&apos;s own pick among the stats
        that anyone scored in. A match that ended empty hands out none. Recorded since 9 November 2026.
      </p>
      {data && (
        <ul className="award-list">
          {data.map((a) => (
            <li key={a.key}>
              <AwardBadge award={a} />
              <span className="award-desc">
                {a.stat && <span className="muted">{a.stat} · </span>}
                {a.description}
              </span>
            </li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** One labelled number in the card grid. */
function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="card">
      <span className="label">
        {label}
        <InfoTip text={hint} />
      </span>
      <strong>{value}</strong>
    </div>
  );
}

/** A top-N list of weapons with a bar relative to the biggest one. */
export function WeaponList({ heading, items, hint }: { heading: string; items: CombatWeapon[]; hint?: string }) {
  const top = items[0]?.count || 1;
  return (
    <div className="combat-weapons">
      <h3>
        {heading}
        <InfoTip text={hint} />
      </h3>
      {items.length === 0 ? (
        <p className="muted">None recorded.</p>
      ) : (
        <ul className="plain">
          {items.slice(0, 8).map((w) => (
            <li key={w.code} title={w.code}>
              <span className="share-cell">
                <span className="share-track"><span className="share-fill" style={{ width: `${Math.max(2, (w.count / top) * 100)}%` }} /></span>
                <span className="share-pct">{w.name} · {int(w.count)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function EventCards({ e, matches }: { e: Pick<CombatEvents, "shots" | "tacmod_activations" | "heal_bubbles" | "stuns_given" | "stuns_received" | "self_kills">; matches?: number }) {
  const per = (n: number) => (matches ? ` (${num(n / matches, 1)} / match)` : "");
  return (
    <div className="cards">
      <Stat label="Shots fired" value={int(e.shots)} hint={`Every shot in the matches that have an event log${per(e.shots)}.`} />
      <Stat label="Tac mod uses" value={int(e.tacmod_activations)} hint="Times the tac mod was switched on." />
      <Stat label="Heal bubbles" value={int(e.heal_bubbles)} hint="Repair Matrix bubbles dropped." />
      <Stat label="Stuns given" value={int(e.stuns_given)} />
      <Stat label="Stuns received" value={int(e.stuns_received)} />
      <Stat label="Self-kills" value={int(e.self_kills)} hint="Killed by their own ordnance. Counted in deaths, not in kills." />
    </div>
  );
}

/**
 * The player's combat stats from the recorder's match reports. Separate from the replay-derived stats on the page
 * (own endpoint, own data): the game's own counters, plus shots / weapons / tac mod use for matches with an event log.
 */
export function CombatSection({ userId, period, map }: { userId: string; period: Period; map: string }) {
  const { data } = useApi(() => getCombatPlayer(userId, period, map || undefined), `combat|${userId}|${period}|${map}`);
  const guide = useApi(getCombatAwards, "combat-awards").data; // every award the game can give, so the ones not won show 0
  if (!data || !data.matches || !data.stats) return null;
  const s = data.stats;
  const e = data.events;
  // all awards with this player's count (0 when never won), most won first, then the game's order; an award the guide does
  // not know (a new one) is kept
  const won = new Map((data.awards?.items ?? []).map((a) => [a.key, a.count]));
  const awardCards: CombatAwardCount[] = [
    ...(guide ?? []).map((a) => ({ ...a, count: won.get(a.key) ?? 0 })),
    ...(data.awards?.items ?? []).filter((a) => !guide?.some((g) => g.key === a.key)),
  ].sort((a, b) => b.count - a.count);
  return (
    <>
      <h2>Combat stats</h2>
      <p className="muted footnote">
        The game&apos;s own counters from {int(data.matches)} recorded match{data.matches === 1 ? "" : "es"} ({hoursMinutes(s.present_s)} played).
        From a separate source than the replay stats above, so numbers can differ. Only data collected from 4 November 2026
        onwards. <Link to="/leaderboard?board=combat">All combat stats</Link>
      </p>
      {/* the game's award cards first, for every player: all 16 with a count (0 when never won), even before any of
          their matches carries award data */}
      <h3>
        Awards
        <InfoTip text="The game's own end-of-match award cards (MVP, Assassin, Guard...). Each goes to the top player of that stat in the match; there is no minimum." />
      </h3>
      <p className="muted footnote">
        {data.awards
          ? <>{int(data.awards.total)} award{data.awards.total === 1 ? "" : "s"} in {data.awards.matches} of {data.matches} match{data.matches === 1 ? "" : "es"}
            {data.awards.matches < data.matches && " (matches recorded before 9 November 2026 do not carry awards)"}.</>
          : <>None of these {int(data.matches)} match{data.matches === 1 ? "" : "es"} carry awards yet: the game&apos;s award cards are recorded from 9 November 2026 onwards.</>}
      </p>
      <div className="cards award-cards">
        {awardCards.map((a) => (
          <div key={a.key} className={`card award-card award-${a.key}${a.count === 0 ? " award-none" : ""}`} title={awardHint(a)}>
            <span className="label">
              {a.name}
              <InfoTip text={awardHint(a)} />
            </span>
            <strong>{int(a.count)}</strong>
            <span className="muted footnote award-stat">{a.stat || a.description}</span>
          </div>
        ))}
      </div>
      <AwardGuide />

      <h3>Game counters</h3>
      <div className="cards">
        <Stat label="Matches" value={int(data.matches)} />
        <Stat label="Kills" value={int(s.kills)} hint="Kills of other players, as the game counts them. Self-kills are not included." />
        <Stat label="Deaths" value={int(s.deaths)} hint="Includes self-kills." />
        <Stat label="K/D" value={s.kd == null ? "–" : num(s.kd, 2)} hint="Kills divided by deaths." />
        <Stat label="Assists" value={int(s.assists)} />
        <Stat label="Eliminations" value={int(s.eliminations)} hint="The game's separate elimination counter; usually higher than kills." />
        <Stat label="Damage dealt" value={int(s.damage)} hint="Game damage units." />
        <Stat label="Damage / min" value={num(s.damage_per_min, 0)} hint="Per minute played." />
        <Stat label="Kills / min" value={num(s.kills_per_min, 2)} hint="Per minute played." />
        <Stat label="Objective damage" value={int(s.objective_damage)} hint="Damage to the payload / objective (payload maps)." />
        <Stat label="Objective time" value={hoursMinutes(s.objective_time)} hint="Time on the objective (payload maps)." />
        {(s.hill_captures > 0 || s.hill_defends > 0) && (
          <Stat label="Hill captures / defends" value={`${int(s.hill_captures)} / ${int(s.hill_defends)}`} hint="Point-capture modes." />
        )}
      </div>
      <p className="muted footnote">Damage taken is not shown: the game does not give it to spectators.</p>

      {e && (
        <>
          <h3>
            Shots, weapons and tac mods
            <InfoTip text="From the game's network events, which only exist for matches recorded with the event log." />
          </h3>
          <p className="muted footnote">
            {e.matches} of {data.matches} match{data.matches === 1 ? "" : "es"} have an event log
            {e.events_incomplete > 0 && `; in ${e.events_incomplete} of them the log ended early, so these counts are a little low`}.
          </p>
          <EventCards e={e} matches={e.matches} />
          <div className="combat-weapon-grid">
            <WeaponList heading="Kills by weapon" items={e.kills_by_weapon} hint="Kills of other players (self-kills excluded)." />
            <WeaponList heading="Deaths by weapon" items={e.deaths_by_weapon} hint="What killed this player, including their own ordnance." />
            <WeaponList heading="Shots by weapon" items={e.shots_by_weapon} hint="The weapon held in the nearest frame, so a shot right at a weapon swap can be filed under the wrong one." />
          </div>
        </>
      )}

      {data.by_map && data.by_map.length > 0 && (
        <>
          <h3>Combat stats per map</h3>
          <TableWrap>
            <table className="stack">
              <thead>
                <tr><th>Map</th><th className="num">Matches</th><th className="num">Kills</th><th className="num">Deaths</th><th className="num">Assists</th><th className="num">Damage</th><th className="num">Objective dmg</th></tr>
              </thead>
              <tbody>
                {data.by_map.map((m) => (
                  <tr key={m.map}>
                    <td data-label="Map">{title(m.map)}</td>
                    <td data-label="Matches" className="num">{int(m.matches)}</td>
                    <td data-label="Kills" className="num">{int(m.kills)}</td>
                    <td data-label="Deaths" className="num">{int(m.deaths)}</td>
                    <td data-label="Assists" className="num">{int(m.assists)}</td>
                    <td data-label="Damage" className="num">{int(m.damage)}</td>
                    <td data-label="Objective dmg" className="num">{int(m.objective_damage)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </>
      )}

      {data.recent && data.recent.length > 0 && (
        <>
          <h3>Recent combat matches</h3>
          <TableWrap>
            <table className="stack">
              <thead>
                <tr><th>Played</th><th>Map</th><th>Team</th><th className="num">K</th><th className="num">D</th><th className="num">A</th><th className="num">Damage</th><th className="num">Length</th>{data.awards && <th>Awards</th>}</tr>
              </thead>
              <tbody>
                {data.recent.map((m) => (
                  <tr key={m.session_id}>
                    <td data-label="Played"><Link to={`/combat/${m.session_id}`}><LocalTime iso={m.started_at} /></Link></td>
                    <td data-label="Map">{title(m.map)}</td>
                    <td data-label="Team"><TeamBadge team={m.team} /></td>
                    <td data-label="K" className="num">{m.kills}</td>
                    <td data-label="D" className="num">{m.deaths}</td>
                    <td data-label="A" className="num">{m.assists}</td>
                    <td data-label="Damage" className="num">{int(m.damage)}</td>
                    <td data-label="Length" className="num">{duration(m.duration_s)}</td>
                    {data.awards && <td data-label="Awards">{m.awards == null ? <span className="muted">unknown</span> : <AwardBadges awards={m.awards} />}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        </>
      )}
    </>
  );
}

function PlayerEvents({ p }: { p: CombatMatchPlayer }) {
  if (!p.events) return null;
  return (
    <details className="combat-player-events">
      <summary>
        {p.name} · {int(p.events.shots)} shots
      </summary>
      <EventCards e={p.events} />
      <div className="combat-weapon-grid">
        <WeaponList heading="Kills by weapon" items={p.events.kills_by_weapon} />
        <WeaponList heading="Deaths by weapon" items={p.events.deaths_by_weapon} />
        <WeaponList heading="Shots by weapon" items={p.events.shots_by_weapon} />
      </div>
    </details>
  );
}

/** Scoreboard + per-player shots / weapons of one match, from the match report. Used by /combat/:id and the match page. */
export function CombatMatchBody({ m }: { m: CombatMatchDetail }) {
  return (
    <>
      <p className="muted">
        {duration(m.duration_s)} · {m.players.length} players.{" "}
        {!m.has_events && "No event log for this match, so shots and weapon numbers are not available. "}
        {m.events_complete === false && "The event log ended early: shot and weapon counts are too low. "}
        Damage taken is not available (spectators do not get it).
      </p>
      {m.awards && (
        <>
          <h3>
            Awards
            <InfoTip text="The award cards the game showed on the scoreboard. Each goes to the top player of that stat in this match; there is no minimum." />
          </h3>
          {m.awards.length === 0 ? (
            <p className="muted">The game handed out no awards for this match (it ended empty).</p>
          ) : (
            <div className="cards award-cards">
              {m.awards.map((a, i) => (
                <div key={`${a.key}-${i}`} className={`card award-card award-${a.key}`} title={awardHint(a)}>
                  <span className="label">
                    {a.name}
                    <InfoTip text={awardHint(a)} />
                  </span>
                  <strong>{a.user_id ? <Link to={playerPath(a.user_id, a.winner || "")}>{a.winner}</Link> : a.winner || "Unknown"}</strong>
                  <span className="muted footnote award-stat">
                    <TeamBadge team={a.team} />
                    {a.value != null && ` ${a.stat || "value"}: ${Number.isInteger(a.value) ? int(a.value) : num(a.value, 1)}`}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {(["blue", "orange"] as const).map((team) => {
        const players = m.players.filter((p) => p.team === team);
        if (players.length === 0) return null;
        return (
          <div key={team}>
            <h3><TeamBadge team={team} /></h3>
            <TableWrap>
              <table className="stack">
                <thead>
                  <tr>
                    <th>Player</th><th className="num">K</th><th className="num">D</th><th className="num">A</th>
                    <th className="num">Elims<InfoTip text="The game's separate elimination counter." /></th>
                    <th className="num">Damage</th><th className="num">Obj. dmg</th><th className="num">Obj. time</th><th>Weapons</th>
                  </tr>
                </thead>
                <tbody>
                  {players.map((p) => (
                    <tr key={p.user_id}>
                      <td data-label="Player"><Link to={playerPath(p.user_id, p.name)}>{p.name}</Link>{p.awards && p.awards.length > 0 && <> <AwardBadges awards={p.awards} /></>}</td>
                      <td data-label="K" className="num">{p.kills}</td>
                      <td data-label="D" className="num">{p.deaths}</td>
                      <td data-label="A" className="num">{p.assists}</td>
                      <td data-label="Elims" className="num">{p.eliminations}</td>
                      <td data-label="Damage" className="num">{int(p.damage)}</td>
                      <td data-label="Obj. dmg" className="num">{int(p.objective_damage)}</td>
                      <td data-label="Obj. time" className="num">{duration(p.objective_time)}</td>
                      <td data-label="Weapons">{p.weapons.join(", ") || "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </TableWrap>
          </div>
        );
      })}
      {m.has_events && (
        <>
          <h3>Shots, weapons and tac mods</h3>
          {m.players.map((p) => <PlayerEvents key={p.user_id} p={p} />)}
        </>
      )}
    </>
  );
}

/**
 * Combat stats on a replay match page, under the players: the recorder's report for the same match id (the game's own
 * counters, not beta). Shown only when the match has one. Joined by match id at read time; the replay stats on the page
 * never use these numbers.
 */
export function MatchCombatSection({ sessionId }: { sessionId: string }) {
  const { data } = useApi(() => getCombatMatch(sessionId), `combat-match|${sessionId}`);
  if (!data) return null; // no report for this match (or not loaded yet): nothing to show
  return (
    <>
      <p className="muted footnote">
        From a separate source than the replay stats on this page, so numbers can differ. Only data collected from
        4 November 2026 onwards.{" "}
        <Link to={`/combat/${data.session_id}`}>Open on its own page</Link>
      </p>
      <CombatMatchBody m={data} />
    </>
  );
}
