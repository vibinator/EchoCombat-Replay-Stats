import type { MatchSummary, Team } from "./api";

export const MAPS = ["combustion", "dyson", "fission", "surge"];

/** Display name as it appears in a profile address: spaces and slashes become "-" so it stays one path segment. */
export function nameSlug(name: string | null | undefined): string {
  return (name ?? "").trim().replace(/[\s/\\]+/g, "-");
}

/** Profile address: /players/<name>/<user id> (the name is only for people reading it; the id decides). */
export function playerPath(userId: string, name?: string | null): string {
  const slug = nameSlug(name);
  return `/players/${slug ? `${encodeURIComponent(slug)}/` : ""}${encodeURIComponent(userId)}`;
}

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

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
  "October", "November", "December"];

/** Chart periods from the API ("2026-10-31" day, "2026-10" month, "2026-43" week, "2026" year) as "31 Oct" /
 *  "Oct 2026" / "Wk 43 2026"; `long` spells it out ("31 October 2026", "October 2026"), for tooltips. */
export function periodLabel(period: string, bucket: string, long = false): string {
  const [year, part, day] = period.split("-");
  if (!part) return period;
  if (bucket === "week") return `${long ? "Week" : "Wk"} ${Number(part)} ${year}`;
  if (bucket !== "month" && bucket !== "day") return period;
  const name = MONTH_NAMES[Number(part) - 1] ?? part;
  const month = long ? name : name.slice(0, 3);
  if (bucket === "day") return long ? `${Number(day)} ${month} ${year}` : `${Number(day)} ${month}`;
  return `${month} ${year}`;
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
