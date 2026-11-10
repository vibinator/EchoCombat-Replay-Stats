import { Component, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { forgetAnswers, reloadOnce, siteUpdate } from "../api";

/** Renders `children` only once this spot is near the screen: sections far down a page (heatmaps, trends,
 *  teammates) ask the server nothing for visitors who never scroll there. */
export function WhenVisible({ children, minHeight = 160 }: { children: ReactNode; minHeight?: number }) {
  const spot = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(() => typeof IntersectionObserver === "undefined");
  useEffect(() => {
    const el = spot.current;
    if (shown || !el) return;
    const near = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) {
        setShown(true);
        near.disconnect();
      }
    }, { rootMargin: "400px 0px" });
    near.observe(el);
    return () => near.disconnect();
  }, [shown]);
  return shown ? <>{children}</> : <div ref={spot} style={{ minHeight }} aria-hidden="true" />;
}

/** Plain-language explanations shown as tooltips next to stat names. */
export const STAT_HELP: Record<string, string> = {
  "Play time": "Time this player was in the match.",
  "Deaths*": "Estimated: counted each time the player left the map's play area (the replay has no kill data).",
  Ping: "Average network latency in milliseconds (placeholder readings of 999 are ignored).",
  "Avg speed": "Average movement speed inside the play area.",
  "Top speed": "Fastest speed held for at least one full second.",
  Stopped: "Share of time moving slower than 1 m/s.",
  Inverted: "Share of time upside down.",
  "Near mate": "Share of time within ~2.6 m of a teammate.",
  "Near enemy": "Share of time within ~2.6 m of an enemy.",
  Loss: "Average packet loss.",
  Emotes: "Number of emotes started.",
  "Push / block*": "Estimated time standing on the payload as attacker / defender (within 3 m).",
  Arm: "Dominant arm.",
  "Main loadout": "Weapon · ordnance · tac mod used most.",
};

export function InfoTip({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <span className="info" title={text} aria-label={text} tabIndex={0}>
      ⓘ
    </span>
  );
}

/**
 * A pane in a card grid that shows / hides the extra cards of that grid (user, 2026-11-09: a square pane like the cards
 * beside it, not a dropdown under them). Used by the player page's "More stats" and the combat tab's awards not won yet.
 */
export function MoreCard({ open, count, onToggle, label = "More stats", detail }: {
  open: boolean; count: number; onToggle: () => void; label?: string; detail?: string;
}) {
  return (
    <button type="button" className="card more-card" aria-expanded={open} onClick={onToggle}>
      <span className="label">{open ? "Show less" : label}</span>
      <strong>{open ? "Hide" : `+${count}`}</strong>
      {detail && <span className="muted footnote">{detail}</span>}
    </button>
  );
}

export function Skeleton({ lines = 3, cards = 0 }: { lines?: number; cards?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading">
      {cards > 0 && (
        <div className="cards">
          {Array.from({ length: cards }, (_, i) => (
            <div key={i} className="card skel-block" />
          ))}
        </div>
      )}
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="skel-line" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

/** For a tab strip that scrolls sideways on phones: brings the active tab into view (a link can open any tab). Moves
 *  only the strip, never the page. `dep`: whatever changes which tab is active or which tabs exist. */
export function useActiveTabInView(dep: string) {
  const strip = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = strip.current;
    const active = box?.querySelector<HTMLElement>(".tab.active");
    if (!box || !active || box.scrollWidth <= box.clientWidth) return;
    const outer = box.getBoundingClientRect();
    const tab = active.getBoundingClientRect();
    if (tab.left < outer.left || tab.right > outer.right) box.scrollLeft += tab.left - outer.left - (outer.width - tab.width) / 2;
  }, [dep]);
  return strip;
}

const FIT_MIN_PX = 10;

/** One line, always: shrinks the font until the text fits its box (long player names in cards). Below
 *  FIT_MIN_PX it stops shrinking and cuts the end off with "…"; the full text is in the tooltip. */
export function FitText({ children, title }: { children: ReactNode; title?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    let width = -1;
    const fit = () => {
      const box = el.parentElement?.clientWidth ?? 0;
      if (box === width) return; // only the width matters; ignore height changes caused by fitting
      width = box;
      el.style.fontSize = "";
      const full = parseFloat(getComputedStyle(el).fontSize);
      if (el.scrollWidth > el.clientWidth && el.clientWidth > 0) {
        const size = Math.max(FIT_MIN_PX, Math.floor(((full * el.clientWidth) / el.scrollWidth) * 0.97 * 10) / 10);
        el.style.fontSize = `${size}px`;
      }
    };
    fit();
    const observer = new ResizeObserver(fit);
    if (el.parentElement) observer.observe(el.parentElement);
    document.fonts?.ready.then(() => ((width = -1), fit()));
    return () => observer.disconnect();
  }, [children]);
  return (
    <span ref={ref} className="fit-text" title={title}>
      {children}
    </span>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <img src="/achievements/happy_cubesat.png" alt="" />
      <strong>{title}</strong>
      {children && <span className="muted">{children}</span>}
    </div>
  );
}

/** A page file that could not be loaded: after an update of the site the old files are gone from the server. */
const PAGE_FILE_ERROR = /dynamically imported module|module script failed|error loading dynamically|Unable to preload|Failed to fetch/i;
const RETRY_AFTER_MS = 1_500;
const RETRY_GAP_MS = 60_000;
let retriedAt = 0;

/** A page that crashes shows a message instead of taking the whole site blank. Reset by `key` (the address).
 *  Before the message it tries what usually fixes it (2026-11-10), each at most once a minute:
 *  - the site was updated since this tab opened (a page file is gone, or the server answers as a newer version): the
 *    tab is reloaded, which loads the current site;
 *  - otherwise the saved answers are forgotten (the page may have crashed on one of them, and a plain reload would
 *    hand it the same one from this tab's store) and the page is shown again with fresh ones. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean; fixing: boolean }> {
  state = { failed: false, fixing: false };
  private timer: ReturnType<typeof setTimeout> | undefined;
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: unknown) {
    console.error("Page error:", error);
    const text = error instanceof Error ? `${error.name}: ${error.message}` : String(error);
    if ((PAGE_FILE_ERROR.test(text) || siteUpdate.available()) && reloadOnce()) {
      this.setState({ fixing: true }); // the tab is reloading
      return;
    }
    forgetAnswers();
    if (Date.now() - retriedAt < RETRY_GAP_MS) return; // tried moments ago: show the message
    retriedAt = Date.now();
    this.setState({ fixing: true });
    this.timer = setTimeout(() => this.setState({ failed: false, fixing: false }), RETRY_AFTER_MS);
  }
  componentWillUnmount() {
    clearTimeout(this.timer);
  }
  render() {
    if (!this.state.failed) return this.props.children;
    if (this.state.fixing) return <Skeleton lines={4} />;
    return (
      <div className="empty-state">
        <p className="error">Something went wrong showing this page.</p>
        <p className="muted">Reloading usually fixes it. If it keeps happening, tell us which page it was.</p>
        <button
          type="button"
          onClick={() => {
            forgetAnswers();
            location.reload();
          }}
        >
          Reload
        </button>
      </div>
    );
  }
}
