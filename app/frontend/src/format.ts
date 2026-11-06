import type { MatchSummary, Team } from "./api";

export const MAPS = ["combustion", "dyson", "fission", "surge"];

/** Which game mode each map is played in: Combustion and Dyson are Capture point, Fission and Surge are Payload. */
export const MAP_MODE: Record<string, string> = { combustion: "capture_point", dyson: "capture_point", fission: "payload", surge: "payload" };

/** Display name as it appears in a profile address: spaces and slashes become "-" so it stays one path segment. */
export function nameSlug(name: string | null | undefined): string {
  return (name ?? "").trim().replace(/[\s/\\]+/g, "-");
}

/** Achievements address: /achievements/<name>/<user id>, like a profile's, so a shared link shows whose they are
 *  (user, 2026-11-02). The old /achievements?player=<id> links still work and move to it. */
export function achievementsPath(userId: string, name?: string | null): string {
  const slug = nameSlug(name);
  return `/achievements/${slug ? `${encodeURIComponent(slug)}/` : ""}${encodeURIComponent(userId)}`;
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

/** Fixed decimals with thousands separators: 1194.6 -> "1,194.6". */
export function num(value: number | null | undefined, digits = 1): string {
  return value == null ? "–" : value.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Whole number with thousands separators: 8689 -> "8,689". */
export function int(value: number | null | undefined): string {
  return value == null ? "–" : Math.round(value).toLocaleString("en-GB");
}

/** Long totals of time: "31 h 24 m" from an hour up (h:mm:ss reads like a clock time there), else m:ss. */
export function hoursMinutes(seconds: number | null | undefined): string {
  if (seconds == null) return "–";
  if (seconds < 3600) return duration(seconds);
  const m = Math.round(seconds / 60);
  return `${Math.floor(m / 60).toLocaleString("en-GB")} h ${m % 60} m`;
}

const UK_CLOCK = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/London", hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric",
});

/** How far UK time is ahead of UTC at this moment, in ms: 0 in winter, one hour in summer. */
function ukOffset(ms: number): number {
  const p = Object.fromEntries(UK_CLOCK.formatToParts(ms).map((x) => [x.type, Number(x.value)]));
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - Math.floor(ms / 1000) * 1000;
}

/** The moment an API time stands for. Match times have no zone: they are on the recorder's clock, UK time (measured 2026-11-05 from
 * the replay files, 2021-2026, D59). Other times carry their zone. The hour repeated when UK clocks go back reads as the second one. */
export function instant(iso: string): Date {
  if (/(Z|[+-]\d\d:\d\d)$/.test(iso)) return new Date(iso);
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(iso);
  if (!m) return new Date(iso);
  const wall = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] ?? 0));
  return new Date(wall - ukOffset(wall - ukOffset(wall)));
}

const two = (n: number) => String(n).padStart(2, "0");

/** "YYYY-MM-DD HH:MM" on the viewer's own clock. A plain date or month has no time to convert and stays as it is. */
export function dateTime(iso: string): string {
  if (!/[T ]\d{2}:\d{2}/.test(iso)) return iso;
  const d = instant(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace("T", " ");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

/** The same moment in UK time, the clock days are counted on: for tooltips. */
export function ukDateTime(iso: string): string {
  const d = instant(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = Object.fromEntries(UK_CLOCK.formatToParts(d).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month.padStart(2, "0")}-${p.day.padStart(2, "0")} ${p.hour.padStart(2, "0")}:${p.minute.padStart(2, "0")}`;
}

/** The viewer's timezone name, e.g. "America/New_York". */
export function viewerZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "your timezone";
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

/** The backend appends every medal target to a ladder's text ("... (1 bronze, 5 gold, ... crown)"): a card shows the
 *  rule itself and keeps the targets behind a "Medal targets" link (user, 2026-11-03). */
export function ruleText(description: string): string {
  return description.replace(/\s*\([^()]*bronze[^()]*crown[^()]*\)\s*$/, "");
}

/** The rule as it applies to one medal: "Play games using only Pulsar in any 7 days" + bronze -> "Play 6 games using only
 *  Pulsar in any 7 days". Rules that do not read "Play ... games ..." (or have a unit like %) get the target appended. */
export function medalRuleText(description: string, medal: string | null): string {
  const base = ruleText(description);
  if (!medal) return base;
  const m = description.match(new RegExp(`\\((?:[^()]*, )?([\\d.]+)([^,()]*?) ${medal}\\b[^()]*\\)\\s*$`));
  if (!m) return base;
  const [, n, unit] = m;
  if (!unit.trim() && /^Play (?:[A-Z][\w ]*? )?games\b/.test(base)) {
    const text = base.replace(/^Play /, `Play ${n} `);
    return n === "1" ? text.replace(/\bgames\b/, "game") : text;
  }
  return `${base} (${n}${unit} for ${medal})`;
}
