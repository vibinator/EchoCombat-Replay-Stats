import { type RefObject, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { MatchSummary } from "../api";
import { dateTime, duration, modeLabel, scoreText, title } from "../format";
import { TeamBadge } from "./common";
import { EmptyState } from "./ui";

/** How many cards to render so that none is cut off. A container whose height CSS fixes (position: absolute,
 * e.g. beside the home page video) keeps the cards that fit in that height; any other keeps the first row.
 * Renders all cards, measures, then drops the rest (before paint), and again whenever the width changes. Cards
 * that do not fit are not rendered at all, so the keyboard and screen readers never reach a hidden one. */
function useFit(ref: RefObject<HTMLDivElement | null>, enabled: boolean, count: number): number {
  const [limit, setLimit] = useState(Infinity);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!enabled || !el || limit !== Infinity) return;
    const cards = Array.from(el.children) as HTMLElement[];
    if (cards.length === 0) return;
    const fixedHeight = getComputedStyle(el).position === "absolute";
    const fits = (c: HTMLElement) => (fixedHeight ? c.offsetTop + c.offsetHeight <= el.clientHeight : c.offsetTop === cards[0].offsetTop);
    setLimit(Math.max(1, cards.filter(fits).length));
  }, [ref, enabled, limit, count]);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!enabled || !el) return;
    let width = el.clientWidth;
    let height = el.clientHeight;
    const observer = new ResizeObserver(() => {
      // re-measure on a width change, or a height change the content did not cause (the video beside it resized)
      const fixedHeight = getComputedStyle(el).position === "absolute";
      if (el.clientWidth !== width || (fixedHeight && el.clientHeight !== height)) {
        width = el.clientWidth;
        height = el.clientHeight;
        setLimit(Infinity);
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, enabled]);
  useLayoutEffect(() => setLimit(Infinity), [count]); // new data: measure again
  return limit;
}

/** Visual match list: minimap thumbnail, score, winner and (when loaded) the players' names.
 * `fit`: only the matches that fit without being cut off (home page, see useFit). */
export function MatchCards({ matches, fit = false, className = "" }: { matches: MatchSummary[]; fit?: boolean; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const limit = useFit(ref, fit, matches.length);
  if (matches.length === 0) return <EmptyState title="No matches match these filters" />;
  const shown = fit ? matches.slice(0, limit) : matches;
  return (
    <div className={`match-cards ${className}`.trim()} ref={ref}>
      {shown.map((m) => (
        <Link key={m.id} to={`/matches/${m.id}`} className="match-card">
          <img src={`/minimaps/${m.map}_small.png`} alt="" loading="lazy" />
          <div className="match-card-body">
            <div className="match-card-head">
              <strong>{title(m.map)}</strong>
              <span className="muted">{modeLabel(m.mode)}</span>
            </div>
            <div className="match-card-score">
              <span>{scoreText(m)}</span>
              <TeamBadge team={m.winner} />
            </div>
            <span className="muted">
              {dateTime(m.started_at)} · {duration(m.duration_s)}
              {m.player_count != null && ` · ${m.player_count} players`}
            </span>
            {m.players && m.players.length > 0 && (
              <div className="match-card-players">
                {m.players.slice(0, 10).map((p) => (
                  <span key={p.user_id} className={`name-chip ${p.team}`}>
                    {p.name}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Link>
      ))}
    </div>
  );
}
