import type { ReactNode } from "react";

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

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <img src="/achievements/happy_cubesat.png" alt="" />
      <strong>{title}</strong>
      {children && <span className="muted">{children}</span>}
    </div>
  );
}
