/** Where a player is from (user, 2026-11-28): a country, shown as its flag, and a game region, shown as text. The same
 *  lists as backend/regions.py. Flags are pictures (flag-icons, MIT): Windows does not draw flag emoji. Each picture is
 *  its own small file, loaded only when a flag is shown. */

const FLAG_FILES = import.meta.glob("../node_modules/flag-icons/flags/4x3/*.svg", {
  query: "?no-inline",  // a file each, not inlined into the page code (~200 kB otherwise)
  import: "default",
  eager: true,
}) as Record<string, string>;

const NOT_COUNTRIES = new Set(["eu", "un", "xx", "pc"]);
const SUBDIVISIONS: Record<string, string> = {
  "gb-eng": "England",
  "gb-sct": "Scotland",
  "gb-wls": "Wales",
  "gb-nir": "Northern Ireland",
};

const FLAGS: Record<string, string> = {};
for (const [path, url] of Object.entries(FLAG_FILES)) {
  const code = path.slice(path.lastIndexOf("/") + 1, -4);
  if ((code.length === 2 && !NOT_COUNTRIES.has(code)) || code in SUBDIVISIONS) FLAGS[code] = url;
}

const names = typeof Intl !== "undefined" && "DisplayNames" in Intl ? new Intl.DisplayNames(["en"], { type: "region" }) : null;

export function countryName(code: string): string {
  if (code in SUBDIVISIONS) return SUBDIVISIONS[code];
  try {
    return names?.of(code.toUpperCase()) ?? code.toUpperCase();
  } catch {
    return code.toUpperCase();
  }
}

export const flagUrl = (code: string | null | undefined): string | null => (code && FLAGS[code]) || null;

/** Every country for the picker, by name. */
export const COUNTRIES: { code: string; name: string }[] = Object.keys(FLAGS)
  .map((code) => ({ code, name: countryName(code) }))
  .sort((a, b) => a.name.localeCompare(b.name));

/** The game's server regions, in picker order. */
export const REGIONS: { key: string; label: string }[] = [
  { key: "us-east", label: "US East" },
  { key: "us-central", label: "US Central" },
  { key: "us-west", label: "US West" },
  { key: "europe", label: "Europe" },
  { key: "japan", label: "Japan" },
  { key: "singapore", label: "Singapore" },
  { key: "australia", label: "Australia" },
];

export const regionLabel = (key: string | null | undefined): string | null => REGIONS.find((r) => r.key === key)?.label ?? null;
