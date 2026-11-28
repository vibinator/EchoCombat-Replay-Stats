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

/** The game region follows the country (user, 2026-11-28: "the region should match the country"; "if they pick United
 *  States they should only see East, West, Central"). The same table as backend/regions.py _NEAREST
 *  (tests/backend/test_profile_place.py keeps them equal). */
// region-table-start
const NEAREST: Record<string, string> = {
  "europe": [
    "ad al at ax ba be bg by ch cy cz de dk ee es fi fo fr gb gg gi gr hr hu ie im is it je li lt lu lv mc md me mk",
    "mt nl no pl pt ro rs ru se si sj sk sm ua va xk ic bv tf gb-eng gb-sct gb-wls gb-nir tr il ae am az bh ge iq",
    "ir jo kw lb om ps qa sa sy ye kz kg tj tm uz dz ao bj bw bf bi cm cv cf td km cg cd ci dj eg gq er sz et ga gm",
    "gh gn gw ke ls lr ly mg mw ml mr mu yt ma mz na ne ng re rw sh st sn sc sl so za ss sd tz tg tn ug eh zm zw",
  ].join(" "),
  "japan": "jp kr kp tw hk mo cn mn",
  "singapore": "sg my id th vn ph kh la mm bn tl in pk bd lk np bt mv af io dg",
  "australia": "au nz fj pg sb vu nc pf ws to tv ki nr fm mh pw gu mp as ck nu tk wf pn nf cc cx hm aq",
  "us-east": [
    "ar bo br cl co ec fk gf gy py pe sr uy ve gs gl pm ag ai aw bb bl bm bq bs cu cw dm do gd gp ht jm kn ky lc mf",
    "mq ms pr sx tc tt vc vg vi",
  ].join(" "),
  "us-central": "mx gt bz sv hn ni cr pa",
  "us-west": "um cp",
};
// region-table-end
const REGION_OF: Record<string, string> = {};
for (const [region, codes] of Object.entries(NEAREST)) for (const code of codes.split(" ")) REGION_OF[code] = region;
const NORTH_AMERICA = ["us-east", "us-central", "us-west"];

/** The regions that match a country: its one, or East / Central / West for the US and Canada. */
export function regionsFor(country: string | null | undefined): string[] {
  if (!country) return [];
  if (country === "us" || country === "ca") return NORTH_AMERICA;
  return REGION_OF[country] ? [REGION_OF[country]] : [];
}

/** How a region reads in the picker once a country is chosen: "East" for a US player, "Europe" for a French one. */
export const pickerLabel = (key: string, country: string | null | undefined): string =>
  (country === "us" || country === "ca") ? (regionLabel(key) ?? key).replace(/^US /, "") : (regionLabel(key) ?? key);
