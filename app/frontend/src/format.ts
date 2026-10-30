import type { MatchSummary, Team } from "./api";

export const MAPS = ["combustion", "dyson", "fission", "surge"];

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "–";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
}

export function pct(value: number | null | undefined): string {
  return value == null ? "–" : `${Math.round(value * 100)}%`;
}

export function num(value: number | null | undefined, digits = 1): string {
  return value == null ? "–" : value.toFixed(digits);
}

// Match times are the recorder's local time with no zone (ReplayData Q6): show as-is.
export function dateTime(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

export function title(word: string): string {
  return word ? word[0].toUpperCase() + word.slice(1) : word;
}

export function modeLabel(mode: string): string {
  return mode === "payload" ? "Payload" : "Capture point";
}

export function teamLabel(team: Team | null): string {
  return team ? title(team) : "–";
}

export function scoreText(m: MatchSummary): string {
  if (m.mode === "payload") {
    return m.final_payload_checkpoint == null ? "–" : `Checkpoint ${m.final_payload_checkpoint}/3`;
  }
  return `${m.blue_rounds} – ${m.orange_rounds}`;
}
