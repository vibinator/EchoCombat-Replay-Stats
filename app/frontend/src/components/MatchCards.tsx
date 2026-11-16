import { Fragment } from "react";
import { Link } from "react-router";
import { getMatchThumbnails, type MatchSummary, type MatchTag } from "../api";
import { duration, instant, minimapUrl, modeLabel, scoreText, title } from "../format";
import { useApi } from "../useApi";
import { LocalTime, TeamBadge } from "./common";
import { EmptyState } from "./ui";

/** Team heat of every listed match, fetched in one request; empty until it arrives (or if it fails). */
function useThumbnails(matches: MatchSummary[]): Record<string, string> {
  const ids = matches.map((m) => m.id);
  const key = [...ids].sort((a, b) => a - b).join(",");
  const heat = useApi(() => (ids.length ? getMatchThumbnails(ids) : Promise.resolve({ thumbnails: {} })), `thumbnails:${key}`);
  return heat.data?.thumbnails ?? {};
}

/** Minimap thumbnail with the players' heat on top; both images fill the same box with object-fit: contain, and the
 * heat PNG covers the whole minimap, so they line up at any card size. */
function MatchThumb({ map, heat }: { map: string; heat: string | undefined }) {
  return (
    <div className={heat ? "match-card-thumb has-heat" : "match-card-thumb"}>
      <img src={minimapUrl(map, true)} alt="" loading="lazy" />
      {heat && <img className="match-card-heat" src={heat} alt="" />}
    </div>
  );
}

const TAG_LABEL: Record<MatchTag, string> = { close: "Close", stomp: "Stomp", full: "Full lobby", combat: "Combat report", repaired: "Repaired" };

/** Why a tag is on this card (the thresholds live in backend/api/matches.py CLOSENESS). */
function tagHint(tag: MatchTag, m: MatchSummary): string {
  const delivered = m.winner != null && m.winner === m.attacking_team;
  if (tag === "close") {
    if (m.mode === "capture_point") return "Decided in the third round (2–1)";
    return delivered ? "Payload delivered with 30 s or less on the clock" : "Defence held at the last checkpoint";
  }
  if (tag === "stomp") {
    if (m.mode === "capture_point") return "Won without losing a round (2–0)";
    return delivered ? "Payload delivered with 3 minutes or more left" : "Defence held before the first checkpoint";
  }
  if (tag === "full") return "10 or more players took part";
  if (tag === "combat") return "The recorder sent kills, damage and awards: see the Combat tab";
  return "Read from a damaged file: some stats may be incomplete";
}

function MatchTags({ m }: { m: MatchSummary }) {
  if (!m.tags?.length) return null;
  return (
    <div className="match-tags">
      {m.tags.map((t) => (
        <span key={t} className={`match-tag ${t}`} title={tagHint(t, m)}>{TAG_LABEL[t]}</span>
      ))}
    </div>
  );
}

/** Blue names on the left, orange on the right, most time played first (as the server sends them). `max` names per
 * team, the rest as "+N" (compact rows show one line per team). */
function TeamNames({ players, max = 6 }: { players: NonNullable<MatchSummary["players"]>; max?: number }) {
  return (
    <div className="match-card-teams">
      {(["blue", "orange"] as const).map((team) => {
        const all = players.filter((p) => p.team === team);
        return (
          <div key={team} className={`match-card-team ${team}`}>
            {all.slice(0, max).map((p) => (
              <span key={p.user_id} className={`name-chip ${team}`}>{p.name}</span>
            ))}
            {all.length > max && <span className="name-more muted">+{all.length - max}</span>}
          </div>
        );
      })}
    </div>
  );
}

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

/** "Today" / "Yesterday" / "Sun 15 Nov" (with the year when it is not this one), on the viewer's own clock. */
function dayLabel(iso: string, now = new Date()): string {
  const d = instant(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (dayKey(d) === dayKey(now)) return "Today";
  if (dayKey(d) === dayKey(yesterday)) return "Yesterday";
  return d.toLocaleDateString(undefined, {
    weekday: "short", day: "numeric", month: "short", ...(d.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
  });
}

function Card({ m, heat, compact = false }: { m: MatchSummary; heat: string | undefined; compact?: boolean }) {
  return (
    <Link to={`/matches/${m.id}`} className="match-card">
      <MatchThumb map={m.map} heat={heat} />
      <div className="match-card-body">
        <div className="match-card-head">
          <strong>{title(m.map)}</strong>
          <span className="muted">
            {modeLabel(m.mode)} · <span className="match-id">#{m.id}</span>
          </span>
        </div>
        <div className="match-card-score">
          <span>{scoreText(m)}</span>
          <TeamBadge team={m.winner} />
        </div>
        <span className="muted">
          <LocalTime iso={m.started_at} /> · {duration(m.duration_s)}
          {m.player_count != null && ` · ${m.player_count} players`}
        </span>
        <MatchTags m={m} />
        {m.players && m.players.length > 0 && <TeamNames players={m.players} max={compact ? 5 : 6} />}
      </div>
    </Link>
  );
}

/** Visual match list: minimap thumbnail with team heat, score, winner, tags and (when loaded) the players' names.
 * `compact`: one short row per match, small thumbnail on the left (home page, beside the live video); when the list is
 * wide enough the tags and names sit beside the score (styles.css, container query on .live-latest-matches).
 * `byDay`: a heading over each day's matches (the Matches page; the list is newest first). */
export function MatchCards({ matches, compact = false, byDay = false }: { matches: MatchSummary[]; compact?: boolean; byDay?: boolean }) {
  const thumbnails = useThumbnails(matches);
  if (matches.length === 0) return <EmptyState title="No matches match these filters" />;
  if (!byDay || compact) {
    return (
      <div className={compact ? "match-cards compact" : "match-cards"}>
        {matches.map((m) => <Card key={m.id} m={m} heat={thumbnails[m.id]} compact={compact} />)}
      </div>
    );
  }
  const days: { label: string; items: MatchSummary[] }[] = [];
  for (const m of matches) {
    const label = dayLabel(m.started_at);
    if (days.at(-1)?.label === label) days.at(-1)!.items.push(m);
    else days.push({ label, items: [m] });
  }
  return (
    <>
      {days.map((d, i) => (
        <Fragment key={`${d.label}-${i}`}>
          <h2 className="match-day">{d.label}</h2>
          <div className="match-cards">
            {d.items.map((m) => <Card key={m.id} m={m} heat={thumbnails[m.id]} />)}
          </div>
        </Fragment>
      ))}
    </>
  );
}
