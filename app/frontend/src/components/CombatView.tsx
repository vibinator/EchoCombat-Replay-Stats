import { Link } from "react-router";
import { getCombatMatch, getCombatPlayer, type CombatEvents, type CombatMatchDetail, type CombatMatchPlayer, type CombatWeapon, type Period } from "../api";
import { TableWrap, TeamBadge } from "./common";
import { InfoTip } from "./ui";
import { dateTime, duration, hoursMinutes, int, num, playerPath, title } from "../format";
import { useApi } from "../useApi";

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
  if (!data || !data.matches || !data.stats) return null;
  const s = data.stats;
  const e = data.events;
  return (
    <>
      <h2>
        Beta Data Collection <span className="tag">beta</span>
      </h2>
      <p className="muted footnote">
        New data we are still collecting and testing. It comes from a separate source than the stats above, is not part of the
        replay stats or the achievements, and may change as more matches are recorded.
      </p>
      <h3>Combat stats</h3>
      <p className="muted footnote">
        The game&apos;s own counters from {int(data.matches)} recorded match{data.matches === 1 ? "" : "es"} ({hoursMinutes(s.present_s)} played).
        Numbers can differ from the replay stats above. <Link to="/combat">All combat stats</Link>
      </p>
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
                <tr><th>Played</th><th>Map</th><th>Team</th><th className="num">K</th><th className="num">D</th><th className="num">A</th><th className="num">Damage</th><th className="num">Length</th></tr>
              </thead>
              <tbody>
                {data.recent.map((m) => (
                  <tr key={m.session_id}>
                    <td data-label="Played"><Link to={`/combat/${m.session_id}`}>{dateTime(m.started_at)}</Link></td>
                    <td data-label="Map">{title(m.map)}</td>
                    <td data-label="Team"><TeamBadge team={m.team} /></td>
                    <td data-label="K" className="num">{m.kills}</td>
                    <td data-label="D" className="num">{m.deaths}</td>
                    <td data-label="A" className="num">{m.assists}</td>
                    <td data-label="Damage" className="num">{int(m.damage)}</td>
                    <td data-label="Length" className="num">{duration(m.duration_s)}</td>
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
                      <td data-label="Player"><Link to={playerPath(p.user_id, p.name)}>{p.name}</Link></td>
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
 * "Beta Data Collection" on a replay match page: the recorder's combat report for the same match id. Shown only when the
 * match has one. Joined by match id at read time; the replay stats on the page never use these numbers.
 */
export function MatchCombatSection({ sessionId }: { sessionId: string }) {
  const { data } = useApi(() => getCombatMatch(sessionId), `combat-match|${sessionId}`);
  if (!data) return null; // no report for this match (or not loaded yet): nothing to show
  return (
    <>
      <h2>
        Beta Data Collection <span className="tag">beta</span>
      </h2>
      <p className="muted footnote">
        New data we are still collecting and testing, from a separate source than the replay stats on this page, so numbers can
        differ. <Link to={`/combat/${data.session_id}`}>Open on its own page</Link>
      </p>
      <h3>Combat stats for this match</h3>
      <CombatMatchBody m={data} />
    </>
  );
}
