function errorMessage(body: unknown, status: number): string {
  const message = (body as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : `Request failed (${status})`;
}

/** The server refused because of the rate limit (429); `retryAfter` is the wait it asked for, in seconds. */
export class RateLimitError extends Error {
  constructor(message: string, readonly retryAfter: number) {
    super(message);
  }
}

// When the rate limit lifts (ms since epoch); the pages show a countdown to it and reload by themselves.
let blockedUntil = 0;
const blockListeners = new Set<() => void>();
export const rateLimit = {
  subscribe(fn: () => void) {
    blockListeners.add(fn);
    return () => void blockListeners.delete(fn);
  },
  until: () => blockedUntil,
};

// The server is too busy or out of reach (time-outs, 5xx): pages keep showing the answers they have and the top bar
// says so, until any request gets through again.
let unreachable = false;
const connectionListeners = new Set<() => void>();
export const connection = {
  subscribe(fn: () => void) {
    connectionListeners.add(fn);
    return () => void connectionListeners.delete(fn);
  },
  unreachable: () => unreachable,
};
function setUnreachable(value: boolean) {
  if (value === unreachable) return;
  unreachable = value;
  connectionListeners.forEach((fn) => fn());
}

const TIMEOUT_MS = 30_000; // a request still unanswered is given up (and a GET asked once more)
// Heatmaps are built from every game's tracks: a cold one for a busy player takes 8-10 s on the NAS, longer while
// replays are imported. They rarely change (kept by the server once built), so waiting longer beats "Server busy";
// kept under Cloudflare's own 100 s limit (user, 2026-11-02).
const HEATMAP_TIMEOUT_MS = 90_000;
const RETRY_MS = 2_000;
const pause = (ms: number) => new Promise((done) => setTimeout(done, ms));

interface Reply<T> {
  data: T;
  etag: string | null;
  /** the server sent an older answer while it builds a fresher one: ask again shortly */
  stale: boolean;
  /** the server allows keeping it (not an answer for this visitor only) */
  keep: boolean;
}

async function fetchReply<T>(path: string, init?: RequestInit): Promise<Reply<T>> {
  const retryable = !init?.method || init.method === "GET";
  for (let attempt = 0; ; attempt++) {
    const timeout = new AbortController();
    const timer = setTimeout(() => timeout.abort(), path.includes("/heatmap") ? HEATMAP_TIMEOUT_MS : TIMEOUT_MS);
    let res: Response;
    try {
      // X-EchoVR: the server answers /api only to this site's own pages (scraper protection, D48)
      res = await fetch(path, { ...init, signal: timeout.signal, headers: { "X-EchoVR": "1", ...init?.headers } });
    } catch {
      if (retryable && attempt === 0) {
        await pause(RETRY_MS);
        continue;
      }
      setUnreachable(true);
      throw new Error(timeout.signal.aborted ? "The server is taking too long to answer. Try again in a moment."
        : "Could not reach the server. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
    }
    if (res.status >= 500 && retryable && attempt === 0) {
      await pause(RETRY_MS); // 502 / 503 / 504 / 524: busy for a moment
      continue;
    }
    setUnreachable(res.status >= 500);
    if (res.status === 429) {
      const seconds = Math.min(Math.max(Math.ceil(Number(res.headers.get("Retry-After"))) || 5, 1), 120);
      blockedUntil = Date.now() + seconds * 1000;
      blockListeners.forEach((fn) => fn());
      throw new RateLimitError(errorMessage(await res.json().catch(() => null), 429), seconds);
    }
    if (!res.ok) throw new Error(errorMessage(await res.json().catch(() => null), res.status));
    return {
      data: (res.status === 204 ? undefined : await res.json()) as T,
      etag: res.headers.get("ETag"),
      stale: res.headers.get("X-EchoVR-Cache") === "STALE",
      keep: !/no-store/i.test(res.headers.get("Cache-Control") ?? ""),
    };
  }
}

/** Never cached: writes, admin pages, live status. */
async function send<T>(path: string, init?: RequestInit): Promise<T> {
  return (await fetchReply<T>(path, init)).data;
}

// ---- Answers, stale-while-revalidate (D53) --------------------------------------------------------------------------
// The website is read-only: an answer is reused without asking for FRESH_MS (going back to a page is instant; two
// components asking for the same thing share one request). An older one is shown at once while a fresh one is fetched
// in the background (KEEP_MS at most); pages showing it update when it changed. Answers are kept per tab in
// sessionStorage, so a reload is instant too. Never kept: answers the server marks no-store (logins) and big ones
// (heatmaps, playback: the browser's own cache revalidates those by ETag).
const FRESH_MS = 60_000;
const KEEP_MS = 60 * 60_000;
const RECHECK_MS = 3_000;
const MAX_RECHECKS = 3;
const MAX_ENTRIES = 200;
const STORE_PREFIX = "echovr:";
const STORE_BUILD = `${STORE_PREFIX}${__BUILD_ID__}:`; // a new version never reads answers of the old one
const STORE_MAX_CHARS = 150_000;

interface Entry {
  at: number;
  data?: unknown;
  etag?: string | null;
  pending?: Promise<unknown>;
}
const entries = new Map<string, Entry>();
const changeListeners = new Set<(path: string) => void>();
const rechecks = new Map<string, number>();
let tracking: Set<string> | null = null;

function tabStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null; // blocked (privacy settings): memory only
  }
}

function forgetStored(keep: (key: string) => boolean = () => false): void {
  const store = tabStore();
  if (!store) return;
  try {
    for (const key of Object.keys(store)) if (key.startsWith(STORE_PREFIX) && !keep(key)) store.removeItem(key);
  } catch {
    /* unavailable */
  }
}
forgetStored((key) => key.startsWith(STORE_BUILD)); // answers saved by an older version of the site

function setEntry(path: string, entry: Entry): void {
  entries.delete(path); // most recently used last
  entries.set(path, entry);
  while (entries.size > MAX_ENTRIES) entries.delete(entries.keys().next().value!);
}

function restore(path: string): Entry | undefined {
  try {
    const text = tabStore()?.getItem(STORE_BUILD + path);
    if (!text) return undefined;
    const saved = JSON.parse(text) as Entry;
    if (Date.now() - saved.at > KEEP_MS) return undefined;
    setEntry(path, saved);
    return saved;
  } catch {
    return undefined;
  }
}

function save(path: string, entry: Entry): void {
  const store = tabStore();
  if (!store) return;
  let text: string;
  try {
    text = JSON.stringify({ at: entry.at, data: entry.data, etag: entry.etag });
  } catch {
    return;
  }
  if (text.length > STORE_MAX_CHARS) return;
  try {
    store.setItem(STORE_BUILD + path, text);
  } catch {
    // full: start this tab's store over with the newest answer
    forgetStored();
    try {
      store.setItem(STORE_BUILD + path, text);
    } catch {
      /* not kept */
    }
  }
}

function load<T>(path: string): Promise<T> {
  const before = entries.get(path);
  if (before?.pending) return before.pending as Promise<T>;
  const pending = fetchReply<T>(path).then((reply) => {
    const entry = { at: Date.now(), data: reply.data, etag: reply.etag };
    setEntry(path, entry);
    if (reply.keep) save(path, entry);
    if (reply.stale) recheck(path);
    else rechecks.delete(path);
    return reply.data;
  });
  setEntry(path, { ...(before ?? { at: 0 }), pending });
  pending.catch(() => {
    const entry = entries.get(path);
    if (entry?.pending !== pending) return;
    if (entry.data === undefined) entries.delete(path); // never keep an error
    else delete entry.pending; // keep the older answer
  });
  return pending;
}

/** Fetch again in the background; pages showing it are told when it changed. */
function refresh(path: string): void {
  const before = entries.get(path);
  if (before?.pending) return;
  load(path).then(
    () => {
      const after = entries.get(path);
      const same = before?.etag && after?.etag ? before.etag === after.etag : JSON.stringify(before?.data) === JSON.stringify(after?.data);
      if (!same) changeListeners.forEach((fn) => fn(path));
    },
    () => undefined, // busy or unreachable: keep showing the older answer
  );
}

function recheck(path: string): void {
  const n = rechecks.get(path) ?? 0;
  if (n >= MAX_RECHECKS) return;
  rechecks.set(path, n + 1);
  setTimeout(() => refresh(path), RECHECK_MS * (n + 1));
}

function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (init) return send<T>(path, init);
  tracking?.add(path);
  const entry = entries.get(path) ?? restore(path);
  const age = entry && entry.data !== undefined ? Date.now() - entry.at : Infinity;
  if (age < KEEP_MS) {
    if (age >= FRESH_MS) refresh(path);
    return Promise.resolve(entry!.data as T);
  }
  return load<T>(path);
}

/** Runs `fn` and lists the answers it asked for (useApi re-renders a page when one of them changes). */
export function track<T>(fn: () => T): { result: T; paths: Set<string> } {
  const outer = tracking;
  const paths = new Set<string>();
  tracking = paths;
  try {
    return { result: fn(), paths };
  } finally {
    tracking = outer;
  }
}

export function onAnswerChange(fn: (path: string) => void): () => void {
  changeListeners.add(fn);
  return () => void changeListeners.delete(fn);
}

/** After a change (icons, Console): ask the server again instead of reusing answers. */
export function forgetResponses(): void {
  entries.clear();
  forgetStored();
}

export type Team = "blue" | "orange";

export interface Page<T> {
  items: T[];
  total: number;
}

export interface MatchSummary {
  id: number;
  replay_id: number;
  session_id: string;
  map: string;
  mode: "capture_point" | "payload";
  started_at: string;
  duration_s: number;
  blue_rounds: number;
  orange_rounds: number;
  final_payload_checkpoint: number | null;
  attacking_team: Team | null;
  winner: Team | null;
  player_count: number | null;
  players?: { user_id: string; name: string; team: Team }[];
}

export interface GearItem {
  code: string;
  name: string;
  cut: boolean;
}

export interface Loadout {
  weapon: GearItem;
  tacmod: GearItem;
  ordnance: GearItem;
  frames: number;
  share: number | null;
}

/** One weapon / ordnance / tac mod: times picked (switched to it), games used (player totals only), time share. */
export interface GearUse extends GearItem {
  picks: number;
  games?: number;
  share: number | null;
}

export interface GearUseSet {
  weapons: GearUse[];
  ordnances: GearUse[];
  tacmods: GearUse[];
}

export interface MatchPlayer {
  user_id: string;
  name: string;
  team: Team;
  number: number | null;
  level: number | null;
  play_time_s: number;
  left_early: boolean;
  avg_ping: number | null;
  avg_speed: number | null;
  top_speed: number;
  pct_stopped: number | null;
  pct_upside_down: number | null;
  pct_near_mate: number | null;
  pct_near_enemy: number | null;
  dominant_arm: string | null;
  deaths_est: number;
  payload_push_s: number;
  payload_block_s: number;
  avg_packet_loss: number | null;
  emote_count: number;
  loadouts: Loadout[];
  gear: GearUseSet;
}

export interface MatchDetail extends MatchSummary {
  ended_at: string;
  frame_rate_hz: number;
  recorded_by: string | null;
  private_match: boolean;
  final_blue_points: number | null;
  final_orange_points: number | null;
  final_payload_distance: number | null;
  final_game_timer: number | null;
  contested_s: number;
  blue_capture_s: number;
  orange_capture_s: number;
  teams: Record<Team, MatchPlayer[]>;
  also_recorded_in: number[]; // other recordings of the same match
  duplicate_of: number | null; // set: that recording counts in the stats, this one does not
  repaired: { aggressive: boolean; frames: number | null } | null; // read from a damaged file by a repair
}

export interface PlayerListItem {
  user_id: string;
  name: string;
  games: number;
  last_seen_at: string;
}

export type Period = "day" | "week" | "month" | "all";

export interface PlayerStats {
  games: number;
  /** wins / losses / result / win_rate: left out while win-loss stats are hidden (Console: Hide stats from players) */
  wins?: number;
  losses?: number;
  games_by_map: Record<string, number>;
  games_by_mode: Record<string, number>;
  hours_played: number;
  deaths_est: number;
  deaths_per_game_est: number | null;
  avg_speed: number | null;
  top_speed: number | null;
  avg_ping: number | null;
  pct_stopped: number | null;
  pct_upside_down: number | null;
  pct_near_mate: number | null;
  pct_near_enemy: number | null;
  pct_left_early: number | null;
  dominant_arm: string | null;
  pct_left_arm: number | null;
  payload_push_s: number;
  payload_block_s: number;
  avg_packet_loss: number | null;
  emote_count: number;
}

export interface PlayerMatch extends MatchSummary {
  team: Team;
  result?: "win" | "loss" | null;
  deaths_est: number;
  play_time_s: number;
}

export interface PlayerProfile {
  user_id: string;
  name: string;
  merged_ids: string[];
  level: number | null;
  first_seen_at: string;
  last_seen_at: string;
  period: Period;
  map: string | null;
  stats: PlayerStats;
  /** every player's shares over the same period / map */
  site_avg?: Partial<Record<"pct_stopped" | "pct_upside_down" | "pct_near_mate" | "pct_near_enemy" | "pct_left_early", number | null>>;
  loadouts: Loadout[];
  gear: GearUseSet;
  recent_matches: PlayerMatch[];
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export interface MatchFilters {
  map?: string;
  mode?: string;
  player?: string;
  from?: string;
  to?: string;
  private?: string;
  min_players?: string | number;
  result?: string;
  player_name?: string;
  with_players?: boolean | string;
  limit?: number;
  offset?: number;
}

export const listMatches = (filters: MatchFilters = {}) =>
  request<Page<MatchSummary>>(`/api/matches${query({ ...filters })}`);

export const getMatch = (id: number) => request<MatchDetail>(`/api/matches/${id}`);

export const searchPlayers = (q: string, limit = 50) =>
  request<Page<PlayerListItem>>(`/api/players${query({ q, limit })}`);

export const getPlayer = (userId: string, period: Period, map?: string) =>
  request<PlayerProfile>(`/api/players/${encodeURIComponent(userId)}${query({ period, map })}`);

export interface HeatmapLayer {
  key: string;
  label: string;
  cells: [number, number, number][]; // [col, row, samples], unpacked from `packed` by heatmapRequest
  max: number;
  team?: string; // "player" mode only
}

export interface Heatmap {
  map: string;
  image: string;
  cols: number;
  rows: number;
  cell_m: number;
  mode: string;
  matches: number;
  layers: HeatmapLayer[];
}

/** As sent: cells packed (heatmaps.pack_cells): d = base64 uint32 index differences, n = base64 counts (w bytes each). */
type PackedLayer = Omit<HeatmapLayer, "cells"> & { packed: { d: string; n: string; w: 2 | 4 } };
type PackedHeatmap = Omit<Heatmap, "layers"> & { layers: PackedLayer[] };

function bytes(b64: string): ArrayBuffer {
  const text = atob(b64);
  const out = new Uint8Array(text.length);
  for (let i = 0; i < text.length; i++) out[i] = text.charCodeAt(i);
  return out.buffer;
}

export function unpackCells(packed: PackedLayer["packed"], cols: number): [number, number, number][] {
  if (!packed.d) return [];
  const view = new DataView(bytes(packed.d));
  const counts = new DataView(bytes(packed.n));
  const cells = new Array<[number, number, number]>(view.byteLength / 4);
  let index = 0;
  for (let i = 0; i < cells.length; i++) {
    index += view.getUint32(i * 4, true);
    const n = packed.w === 2 ? counts.getUint16(i * 2, true) : counts.getUint32(i * 4, true);
    cells[i] = [index % cols, Math.floor(index / cols), n];
  }
  return cells;
}

// one unpacked copy per answer: the answer cache hands the same object to every page that asks
const unpacked = new WeakMap<PackedHeatmap, Heatmap>();

function heatmapRequest(path: string): Promise<Heatmap> {
  return request<PackedHeatmap>(path).then((raw) => {
    let h = unpacked.get(raw);
    if (!h) {
      h = { ...raw, layers: raw.layers.map(({ packed, ...layer }) => ({ ...layer, cells: unpackCells(packed, raw.cols) })) };
      unpacked.set(raw, h);
    }
    return h;
  });
}

export interface MatchEvent {
  frame: number;
  t_s: number;
  type: string;
  team: Team | null;
  user_id: string | null;
  name: string | null;
  data: Record<string, unknown> | null;
}

export interface Timeline {
  hz: number;
  duration_s: number;
  series: Partial<Record<"blue_points" | "orange_points" | "payload_distance", (number | null)[]>>;
  events: MatchEvent[];
}

export interface LeaderboardRow {
  rank: number;
  user_id: string;
  name: string;
  games: number;
  value: number;
  previous_rank: number | null;
  /** same period / map, all modes and gear; null when the player has no plain match rows */
  wins?: number | null;
  losses?: number | null;
  win_rate?: number | null;
  hours_played: number | null;
}

export interface Leaderboard {
  stat: string;
  label: string;
  higher_is_better: boolean;
  /** summary column the ranks follow instead of the stat; null = the stat */
  sort?: string | null;
  total: number;
  items: LeaderboardRow[];
  /** biggest value on the whole board: the value bars are scaled to it */
  max_value?: number | null;
}

export interface StatOption {
  key: string;
  label: string;
  higher_is_better: boolean;
}

export interface GearList {
  weapons: GearItem[];
  tacmods: GearItem[];
  ordnances: GearItem[];
}

export type HeatmapMode = "team" | "weapons" | "deaths";

export const getMatchHeatmap = (id: number, player?: string) =>
  heatmapRequest(`/api/matches/${id}/heatmap${query({ player })}`);

/** Team heat PNGs (data URLs) for a page of match cards, keyed by match id; one request for the whole page. */
export const getMatchThumbnails = (ids: number[]) =>
  request<{ thumbnails: Record<string, string> }>(`/api/matches/thumbnails${query({ ids: [...ids].sort((a, b) => a - b).join(",") })}`);

export const getTimeline = (id: number) => request<Timeline>(`/api/matches/${id}/timeline`);

export const getPlayerHeatmap = (userId: string, map: string, mode: HeatmapMode, period: Period, last: number) =>
  heatmapRequest(`/api/players/${encodeURIComponent(userId)}/heatmap${query({ map, mode, period, last })}`);

export interface LeaderboardQuery {
  stat: string;
  period: Period;
  map?: string;
  min_games: number;
  weapon?: string;
  tacmod?: string;
  ordnance?: string;
  offset?: number;
  limit?: number;
  compare?: boolean;
  /** rank by this summary column (games, wins, losses, win_rate, hours_played) instead of the stat */
  sort?: string;
}

export const getLeaderboard = (q: LeaderboardQuery) =>
  request<Leaderboard>(`/api/leaderboard${query({ ...q })}`);

export const getLeaderboardStats = () => request<StatOption[]>("/api/leaderboard/stats");

export const getGear = () => request<GearList>("/api/leaderboard/gear");

export const matchExportUrl = (id: number, format: "csv" | "json") => `/api/matches/${id}/export?format=${format}`;

export interface AchievementRule {
  id: number;
  name: string;
  description: string;
  rules?: string[]; // how it is counted (best game / day / 7 days, minimum length, 3v3+, "only" share)
  period: "game" | "day" | "week" | "all";
  icon: string | null;
  estimated: boolean;
  counted: boolean; // false: the Combat section, from the recorder's reports: earns medals, out of overall %, totals and Medal Collector
  new: boolean; // added in this app (80+), not on the original ECRanked site
  group: string | null; // theme of a new achievement
  unit?: string; // ladder targets are in this unit ("%", " m/s", " min"); empty = a count
  levels?: number[] | null; // tiered achievements: count targets for bronze, gold, platinum, crown
  prize?: string | null; // Mega Prize (in-game item) for completing it
}

export const LEVELS = ["bronze", "gold", "platinum", "crown"] as const;

export interface Achievement extends AchievementRule {
  progress: number;
  tier: "white" | "bronze" | "silver" | "gold" | "platinum" | "crown" | null;
  unlocked_at: string | null;
  count?: number; // tiered achievements: games counted so far
  try_next?: { weapon: string; tacmod: string; ordnance: string; label: string }[]; // "Different loadouts": ones this player has not tried
}

export interface PlayerAchievements {
  user_id: string;
  name: string;
  window: { start: string | null; end: string | null };
  games: number;
  overall: number;
  completed: number;
  total: number;
  items: Achievement[];
}

export const getAchievements = (userId: string) =>
  request<PlayerAchievements>(`/api/players/${encodeURIComponent(userId)}/achievements`);

export const listAchievements = () => request<AchievementRule[]>("/api/achievements");

// ---- GUI round 2 -------------------------------------------------------------------------

export interface GearShare extends GearItem {
  hours: number;
  share: number | null;
}

export interface GlobalStats {
  recorded_hours: number;
  avg_match_s: number | null;
  longest_match: { id: number; duration_s: number } | null;
  avg_players_per_match: number | null;
  deaths_est: number;
  top_weapons: GearShare[];
  top_ordnances: GearShare[];
  top_tacmods: GearShare[];
  fastest: { user_id: string; name: string; top_speed: number; match_id: number } | null;
  most_active: { user_id: string; name: string; games: number } | null;
  busiest_day: { day: string; matches: number } | null;
  /** payload_* and capture_wins: left out while win-loss stats are hidden */
  payload_attack_win_rate?: number | null;
  payload_decided?: number;
  capture_wins?: { blue: number; orange: number };
}

export interface Overview {
  global: GlobalStats;
  matches: number;
  players: number;
  match_hours: number;
  player_hours: number;
  today: number;
  this_week: number;
  by_map: Record<string, number>;
  most_played_map: string | null;
  first_match_at: string | null;
  last_match_at: string | null;
  top_this_week: { user_id: string; name: string; games: number; wins?: number }[];
  latest: MatchSummary[];
}

export interface PlayersSeen {
  range: "24h" | "7d" | "30d";
  unit: "hour" | "day";
  anchor: "now" | "latest";
  start: string;
  end: string;
  unique_players: number;
  matches: number;
  items: { bucket: string; players: number }[];
}

export interface SearchResult {
  players: { user_id: string; name: string; games: number }[];
  matches: MatchSummary[];
}

export interface PlaybackGear {
  code: string;
  name: string;
  cut: boolean;
}

export interface Playback {
  map: string;
  image: string;
  hz: number;
  samples: number;
  mode: "capture_point" | "payload";
  attacking_team: Team | null;
  duration_s: number;
  series: Partial<Record<"blue_points" | "orange_points" | "payload_distance", (number | null)[]>>;
  gear: { weapon: PlaybackGear[]; ordnance: PlaybackGear[]; tacmod: PlaybackGear[] };
  events: MatchEvent[];
  objects: { route?: ([number, number] | null)[]; point?: { u: number; v: number; r: number } };
  players: {
    user_id: string;
    name: string;
    points: ([number, number, number] | null)[];
    speed: (number | null)[]; // m/s between samples
    loadout: [number, number, number, number][]; // [sample, weapon, ordnance, tac mod] on every change; -1 = none
  }[];
}

/** 3D playback (5 Hz, world space): GET /api/matches/{id}/playback3d. Positions in decimetres; absent = team 0. */
export interface Playback3D {
  map: string;
  model: string | null; // /maps3d/<map>.glb, null = no 3D map for this map
  payload_model: string | null; // /maps3d/<map>_payload.glb (the flamingo, centred on itself), null = draw a box
  extent?: [number, number, number, number] | null; // play area: x min, x max, z min, z max (metres)
  hz: number;
  samples: number;
  duration_s: number;
  payload: ([number, number, number] | null)[] | null; // cart position (metres) per sample, payload maps
  objects: { route?: [number, number][]; point?: [number, number, number] }; // metres: route (x, z), point (x, z, radius)
  players: {
    user_id: string;
    name: string;
    x: number[];
    y: number[];
    z: number[];
    yaw: number[]; // 0-255 = one turn, 0 = facing +z, 64 = facing +x
    pitch: number[]; // degrees, + = up
    roll?: number[]; // 0-255 = one turn of the head around where it faces: 0 upright, 128 upside down (older files: missing)
    team: number[]; // 0 absent, 1 blue, 2 orange
    hands?: number[][]; // [lx, ly, lz, rx, ry, rz] per sample: relative to the head, 2 cm steps (older servers: missing)
  }[];
}

export interface TrendPoint {
  period: string;
  games: number;
  win_rate?: number | null;
  deaths_per_game_est: number | null;
  avg_speed: number | null;
  top_speed: number;
  avg_ping: number | null;
}

export interface Companion {
  user_id: string;
  name: string;
  games: number;
  wins?: number;
  losses?: number;
}

export interface Comparison {
  period: Period;
  players: { user_id: string; name: string; stats: PlayerStats }[];
  head_to_head: Record<"together" | "against", { games: number; wins?: number; losses?: number }>;
}

export interface ChallengeWindow {
  start: string | null;
  end: string | null;
  updated_at: string | null;
  /** false until the admin-set start date: achievements and challenges are "Coming soon" */
  launched: boolean;
  /** before the launch: this visitor has the Discord preview role and sees everything */
  preview: boolean;
  /** who may see achievements: everyone (from the start date), only the Preview role, or nobody */
  visibility: "everyone" | "preview" | "hidden";
  active: boolean;
  /** number of achievements and challenges available (public before the launch too) */
  total: number;
  /** sneak peek for the "Coming soon" page: counts per section and a few badge pictures, no names */
  peek: AchievementPeek;
}

export interface AchievementPeek {
  periods: Partial<Record<AchievementRule["period"], number>>;
  new: Record<string, number>; // theme -> count
  revealed: AchievementRule[]; // shown in full before the launch
  icons: string[]; // more badge pictures, shown blurred
  one_game: number; // "In one game" challenges (all 3v3 or bigger), original and new
}

export interface Me {
  /** Discord login is set up on this server */
  enabled: boolean;
  /** console: a role from ECHOVR_DISCORD_PREVIEW_ROLES, the Console page (admin.bat on the website, D45) */
  user: { name: string; preview: boolean; admin: boolean; console: boolean } | null;
}

// Writes (icons, Console, Permissions): X-EchoVR marks this site's own pages.
const ADMIN_WRITE = { "X-EchoVR": "1" };
export const getIconChoices = () => request<string[]>("/api/admin/icons");
export const setIcon = (id: number, icon: string | null) =>
  send<{ id: number; icon: string }>(`/api/admin/achievements/${id}/icon`, {
    method: "PUT",
    headers: { ...ADMIN_WRITE, "Content-Type": "application/json" },
    body: JSON.stringify({ icon }),
  });
export const uploadIcon = (id: number, file: File) =>
  send<{ id: number; icon: string }>(`/api/admin/achievements/${id}/icon`, {
    method: "POST",
    headers: { ...ADMIN_WRITE, "Content-Type": "image/png" },
    body: file,
  });

/** Console page (D45): runs an admin.bat command on the server; `output` is what it printed. */
export const runConsole = (command: string, args: Record<string, unknown>) =>
  send<{ ok: boolean; output: string }>(`/api/admin/console/${command}`, {
    method: "POST",
    headers: { ...ADMIN_WRITE, "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });

/** What the icon picker needs (Console export). */
export interface IconRow {
  id: number;
  name: string;
  icon: string | null;
  default_icon: string | null;
}

export interface ConsoleAchievement extends IconRow {
  rule: string;
}

/** Console export: every achievement and challenge, name + the rule to win it + its icon. */
export const getConsoleAchievements = () => send<ConsoleAchievement[]>("/api/admin/console/achievements");
export const CONSOLE_ACHIEVEMENTS_CSV = "/api/admin/console/achievements.csv";

/** Console report: who has reached each Mega Prize target inside the challenge period (prizes are given out by hand). */
export interface MegaPrizeReport {
  period: { start: string | null; end: string | null };
  prizes: {
    prize: string;
    challenge: string;
    target: number;
    winners: { name: string; user_id: string; discord_id: string | null; count: number }[];
  }[];
}
export const getMegaPrizeWinners = () => send<MegaPrizeReport>("/api/admin/console/mega-prizes");
export const CONSOLE_MEGA_PRIZES_CSV = "/api/admin/console/mega-prizes.csv";

/** Console merge suggestions: player records that used the same name (backend/merge_suggestions.py). */
export interface MergeCandidate {
  user_id: string;
  name: string;
  /** other names this id was seen with */
  names: string[];
  games: number;
  first_seen_at: string;
  last_seen_at: string;
  /** ids already merged into this one */
  merged_ids: number;
}
export interface MergeSuggestion {
  name: string;
  /** every id's current name is the same (else they match ignoring case and punctuation, or by an older name) */
  exact: boolean;
  /** matches where two of these ids played: usually different people */
  played_together: number;
  /** suggested player to keep */
  keep: string;
  players: MergeCandidate[];
}
export const getMergeSuggestions = () => send<MergeSuggestion[]>("/api/admin/console/merge-suggestions");

/** Console audit log: one command run on the Console page or with admin.bat. */
export interface ConsoleLogEntry {
  id: number;
  at: string; // UTC
  source: "website" | "admin.bat";
  who: string;
  who_id: string | null;
  command: string;
  args: Record<string, unknown>;
  ok: boolean;
  output: string;
}

/** Console dashboard facts (processing progress comes from getProcessingStatus). */
/** Is the Public Arena counter alive? From the server's memory: resets on a restart. */
export interface ArenaStatus {
  state: "off" | "outside_period" | "waiting" | "working" | "failing";
  last_ok_at?: string | null;
  last_counted_at?: string | null;
  matches_now?: number;
  players_now?: number;
  counted_since_start?: number;
  last_error?: string | null;
  last_error_at?: string | null;
}

export interface ConsoleOverview {
  arena_status: ArenaStatus;
  players: number;
  merges: number;
  cannot_repair: number;
  repairable: number;
  aggressive_repairable: number;
  hidden_replays: number;
  challenge: { start: string | null; end: string | null; launched: boolean; visibility: "everyone" | "preview" | "hidden" };
  /** The Mega Prizes' own dates; null / null = none set, they follow the challenge period */
  mega_period: { start: string | null; end: string | null };
  stat_groups: { key: string; label: string; hidden: boolean; players: { user_id: string; name: string }[] }[];
  recent: ConsoleLogEntry[];
}

/** Console player tools: a search result. */
export interface ConsolePlayer {
  user_id: string;
  name: string;
  games: number;
  first_seen_at: string;
  last_seen_at: string;
  merged_into: { user_id: string; name: string } | null;
  merged_ids: { user_id: string; name: string }[];
  win_loss_hidden: boolean;
}

export const getConsoleOverview = () => send<ConsoleOverview>("/api/admin/console/overview");
export const searchConsolePlayers = (q: string) => send<ConsolePlayer[]>(`/api/admin/console/players${query({ q })}`);
export const getConsoleLog = (q = "", before?: number) =>
  send<ConsoleLogEntry[]>(`/api/admin/console/log${query({ q: q || undefined, before, limit: 100 })}`);

/** Status page (admins and console users): live replay processing progress. Never cached. */
export interface ProcessingStatus {
  source_dir: string;
  workers: number;
  busy: number;
  counts: { queued: number; processing: number; done: number; failed: number };
  hidden_failed: number;
  redo: number;
  versions: { parser: string; stats: string };
  rate_per_min: number;
  eta_min: number | null;
  matches_by_map: Record<string, number>;
  throughput: { minute: string; replays: number }[];
  by_year: { year: string; queued: number; processing: number; done: number; failed: number }[];
  stages: { key: string; label: string; done: number; total: number | null; detail: string }[];
  current: { replay_id: number; source_path: string; seconds: number }[];
  scan: {
    reachable: boolean | null;
    scanning: boolean;
    last_scan_at: string | null;
    last_scan_s: number | null;
    files: number;
    settling: number;
    added: number;
    changed: number;
    error: string | null;
  };
  achievement_ranking: { calculating: boolean; calculated: boolean; up_to_date: boolean; age_s: number | null };
}
export const getProcessingStatus = () => send<ProcessingStatus>("/api/admin/status");

/** Permissions page: who gets Admin, the Console and the Preview, by Discord role or user id. */
export type Permission = "admin" | "console" | "preview";
export interface DiscordEntry {
  id: string;
  name: string;
}
export interface PermissionState {
  permissions: Record<Permission, { roles: DiscordEntry[]; users: DiscordEntry[] }>;
  /** ECHOVR_DISCORD_PREVIEW_ROLES (YAML): always the Console, cannot be removed on the page */
  fixed: (DiscordEntry & { type: "role" | "user" })[];
  /** every role in the Discord server; null when the bot cannot list them */
  server_roles: DiscordEntry[] | null;
}
export const getPermissions = () => send<PermissionState>("/api/admin/permissions");
export const changePermission = (change: { permission: Permission; type: "role" | "user"; id: string; remove?: boolean }) =>
  send<PermissionState>("/api/admin/permissions", {
    method: "POST",
    headers: { ...ADMIN_WRITE, "Content-Type": "application/json" },
    body: JSON.stringify(change),
  });

export interface AchievementRarity extends AchievementRule {
  unlocked_share: number | null;
  completed_share: number | null;
}

export interface RecentUnlock {
  date: string;
  at: string; // started_at of the game that earned it, "YYYY-MM-DDTHH:MM:SS"
  medal: "bronze" | "gold" | "platinum" | "crown" | null; // null = a single-step challenge, completed
  user_id: string;
  name: string;
  id: number;
  achievement: string;
  description: string;
  icon: string | null;
}

export const getMe = () => request<Me>("/api/auth/me");
/** Full-page navigation (not a fetch): Discord's login page, then back to `next`. */
export const loginUrl = (next: string) => `/api/auth/login?next=${encodeURIComponent(next)}`;
export const LOGOUT_URL = "/api/auth/logout";
/** `version` e.g. "Beta v26.11.1-7" (shown), `build` the full "2026.11.01.7", `released` local "YYYY-MM-DDTHH:MM" */
export const getHealth = () => request<{ version: string; build: string; released: string }>("/api/health");
// The home page starts its chart requests together with the overview; request() lets the charts reuse them.
export const getOverview = () => request<Overview>("/api/overview");
/** Live queue length for the top bar: always asked (Cloudflare may answer it), never reused from the cache. */
export const getProcessing = () => send<{ pending: number }>("/api/overview/processing");
/** Newest match end time for the home page. Polled: never reused from the cache (Cloudflare may answer it). */
export const getLastMatch = () => send<{ last_match_at: string | null }>("/api/overview/last-match");
/** Is a game being played now (the spectator bot is live on Twitch; live null = could not tell)? Never cached
 * anywhere: no-store for the browser and Cloudflare, and send() keeps no copy. */
export const getLive = () => send<{ live: boolean | null; since: string | null }>("/api/overview/live");
export const getActivity = (bucket: "day" | "week" | "month" | "year") =>
  request<{ bucket: string; items: { period: string; matches: number; hours: number; maps: Record<string, number> }[] }>(`/api/overview/activity?bucket=${bucket}`);
export const getPlayersSeen = (range: PlayersSeen["range"], anchor: PlayersSeen["anchor"]) =>
  request<PlayersSeen>(`/api/overview/players-seen?range=${range}&anchor=${anchor}`);
export const search = (q: string) => request<SearchResult>(`/api/search${query({ q })}`);
/** A server that has not been restarted after an update answers the older, smaller playback: fill in what is missing. */
export const getPlayback = (id: number) =>
  request<Playback>(`/api/matches/${id}/playback`).then(
    (p): Playback => ({
      ...p,
      mode: p.mode ?? "capture_point",
      attacking_team: p.attacking_team ?? null,
      duration_s: p.duration_s ?? p.samples / p.hz,
      series: p.series ?? {},
      gear: p.gear ?? { weapon: [], ordnance: [], tacmod: [] },
      events: p.events ?? [],
      objects: p.objects ?? {},
      players: p.players.map((q) => ({ ...q, speed: q.speed ?? [], loadout: q.loadout ?? [] })),
    }),
  );
export const getTrends = (userId: string, bucket: "week" | "month" | "year") =>
  request<{ bucket: string; items: TrendPoint[] }>(`/api/players/${encodeURIComponent(userId)}/trends?bucket=${bucket}`);
export type CompanionWindow = "24h" | "7d" | "1m" | "3m" | "6m" | "12m" | "all";

export const getPlayback3d = (id: number) => request<Playback3D>(`/api/matches/${id}/playback3d`);
export const getCompanions = (userId: string, window: CompanionWindow = "all") =>
  request<{ teammates: Companion[]; opponents: Companion[] }>(`/api/players/${encodeURIComponent(userId)}/companions?window=${window}`);
export const comparePlayers = (userIds: string[], period: Period) =>
  request<Comparison>(`/api/players/compare/${userIds.map(encodeURIComponent).join(",")}?period=${period}`);
export const getChallenges = () => request<ChallengeWindow>("/api/challenges");
export const getRarity = () => request<AchievementRarity[]>("/api/achievements");
export const getRecentUnlocks = () => request<RecentUnlock[]>("/api/achievements/recent");

/** One row of the Achievements page "Top players": the ranking plus facts about the player. */
export interface Achiever {
  rank: number;
  user_id: string;
  name: string;
  games: number;
  overall: number;
  completed: number; // challenges at 100 %
  total: number;
  medals: number; // ladder steps reached (a single-step challenge counts once)
  gold_plus: number; // challenges at gold or better
  best_section: string | null; // section with the highest average progress
  best_section_share: number;
}
export const getAchievers = (limit = 10) => request<Achiever[]>(`/api/leaderboard/achievers?limit=${limit}`);

export type HeatmapLayerMode = "team" | "weapons" | "ordnance" | "tacmod" | "loadout" | "speed";

export const getMatchHeatmapBy = (id: number, mode: HeatmapLayerMode | "player", cell: number, player?: string) =>
  heatmapRequest(`/api/matches/${id}/heatmap${query({ mode, cell, player })}`);
export const getPlayerHeatmapBy = (userId: string, map: string, mode: HeatmapLayerMode | "deaths", period: Period, last: number, cell: number) =>
  heatmapRequest(`/api/players/${encodeURIComponent(userId)}/heatmap${query({ map, mode, period, last, cell })}`);

/** 3D heatmap (heatmaps3d.py): the layers of a heatmap as voxels in world space. Voxel (ix, iy, iz) covers the cube of
 * `vox_m` metres whose lowest corner is origin + (ix, iy, iz) * vox_m. */
export interface Heatmap3DLayer {
  key: string;
  label: string;
  count: number;
  ix: Uint16Array;
  iy: Uint16Array;
  iz: Uint16Array;
  n: Uint32Array;
  max: number;
  team?: string;
}

export interface Heatmap3D {
  map: string;
  model: string | null;
  mode: string;
  vox_m: number;
  nx: number;
  ny: number;
  nz: number;
  origin: [number, number, number];
  matches: number;
  matches_3d: number;
  layers: Heatmap3DLayer[];
}

type PackedLayer3D = Omit<Heatmap3DLayer, "count" | "ix" | "iy" | "iz" | "n"> & { packed: PackedLayer["packed"] };
type PackedHeatmap3D = Omit<Heatmap3D, "layers"> & { layers: PackedLayer3D[] };

function unpackVoxels(packed: PackedLayer3D["packed"], nx: number, nz: number): Pick<Heatmap3DLayer, "count" | "ix" | "iy" | "iz" | "n"> {
  const count = packed.d ? bytes(packed.d).byteLength / 4 : 0;
  const out = { count, ix: new Uint16Array(count), iy: new Uint16Array(count), iz: new Uint16Array(count), n: new Uint32Array(count) };
  if (!count) return out;
  const gaps = new DataView(bytes(packed.d));
  const counts = new DataView(bytes(packed.n));
  const plane = nx * nz;
  let index = 0;
  for (let i = 0; i < count; i++) {
    index += gaps.getUint32(i * 4, true);
    const iy = Math.floor(index / plane);
    const rest = index - iy * plane;
    const iz = Math.floor(rest / nx);
    out.ix[i] = rest - iz * nx;
    out.iy[i] = iy;
    out.iz[i] = iz;
    out.n[i] = packed.w === 2 ? counts.getUint16(i * 2, true) : counts.getUint32(i * 4, true);
  }
  return out;
}

const unpacked3d = new WeakMap<PackedHeatmap3D, Heatmap3D>();

function heatmap3dRequest(path: string): Promise<Heatmap3D> {
  return request<PackedHeatmap3D>(path).then((raw) => {
    let h = unpacked3d.get(raw);
    if (!h) {
      h = { ...raw, layers: raw.layers.map(({ packed, ...layer }) => ({ ...layer, ...unpackVoxels(packed, raw.nx, raw.nz) })) };
      unpacked3d.set(raw, h);
    }
    return h;
  });
}

export const getMatchHeatmap3d = (id: number, mode: HeatmapLayerMode | "player", player?: string) =>
  heatmap3dRequest(`/api/matches/${id}/heatmap3d${query({ mode, player })}`);
export const getPlayerHeatmap3d = (userId: string, map: string, mode: HeatmapLayerMode, period: Period, last: number) =>
  heatmap3dRequest(`/api/players/${encodeURIComponent(userId)}/heatmap3d${query({ map, mode, period, last })}`);

/** Discord-linked player profile (user, 2026-11-02): linked by the Discord bot; the linked person may change only the
 * bio and whether their Discord avatar is shown. Per visitor (`editable`), never cached. */
export interface PlayerBioProfile {
  linked: boolean;
  bio: string | null;
  show_avatar: boolean;
  avatar_url: string | null;
  editable: boolean;
  /** the Echo account linked to this player, seen on the live match list (no Discord id) */
  account?: { name: string; last_seen: string } | null;
}
export const BIO_MAX = 500;
export const getPlayerBio = (userId: string) => send<PlayerBioProfile>(`/api/profiles/${encodeURIComponent(userId)}`);
export const savePlayerBio = (userId: string, edit: { bio: string | null; show_avatar: boolean }) =>
  send<PlayerBioProfile>(`/api/profiles/${encodeURIComponent(userId)}`, {
    method: "POST",
    headers: { ...ADMIN_WRITE, "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  });

/** The logged-in visitor's own profile; known = their Discord account has been seen playing. */
export type MyProfile = PlayerBioProfile & { name: string; known: boolean; user_id: string | null };
export const getMyProfile = () => send<MyProfile>("/api/profiles/me");
export const saveMyProfile = (edit: { bio: string | null; show_avatar: boolean }) =>
  send<MyProfile>("/api/profiles/me", {
    method: "POST",
    headers: { ...ADMIN_WRITE, "Content-Type": "application/json" },
    body: JSON.stringify(edit),
  });

/** Public Echo Arena matches (Mega Prize, hidden tab, Preview role only): separate from the Combat stats. */
export interface MegaTopPlayer {
  user_id: string;
  name: string;
  matches: number;
  rank: number;
  rank_change: number | null; // + climbed, - dropped, null = new in the list (or nothing a day ago)
  gained: number; // matches in the last day
}

export interface ArenaProgress {
  target: number;
  min_minutes: number;
  combat: AchievementRule[]; // the Combat Mega Prize challenges
  players: { user_id: string; name: string; matches: number; completed: boolean }[];
  winners_combat: number; // players who reached the target
  winners_arena: number;
  closest_combat: { user_id: string; name: string; matches: number }[]; // top 2 not yet at the target
  closest_arena: { user_id: string; name: string; matches: number }[];
  /** the top 10 of each prize, with the change over the last day */
  top_combat: MegaTopPlayer[];
  top_arena: MegaTopPlayer[];
  /** the Mega Prize period (its own dates, or the challenge period); active = running today */
  period: { start: string | null; end: string | null; active: boolean };
}
export const getArenaProgress = () => send<ArenaProgress>("/api/arena/progress");

/** Search a player by name: their progress toward each Mega Prize (from the challenge period on). */
export interface MegaPrizeSearch {
  target: number;
  results: { kind: "combat" | "arena"; name: string; user_id: string; matches: number }[];
}
export const searchMegaPrizes = (q: string) => send<MegaPrizeSearch>(`/api/arena/search?q=${encodeURIComponent(q)}`);

// ---- Combat stats (the recorder's match reports; separate from the replay-derived stats above) -----------------------
export interface CombatWeapon {
  code: string;
  name: string;
  count: number;
}

export interface CombatTotals {
  matches: number;
  present_s: number;
  kills: number;
  assists: number;
  deaths: number;
  eliminations: number;
  damage: number;
  objective_eliminations: number;
  objective_damage: number;
  objective_time: number;
  hill_captures: number;
  hill_defends: number;
  kd: number | null;
  kills_per_min: number | null;
  damage_per_min: number | null;
}

export interface CombatEvents {
  matches: number;
  events_incomplete: number;
  shots: number;
  tacmod_activations: number;
  heal_bubbles: number;
  stuns_given: number;
  stuns_received: number;
  self_kills: number;
  shots_by_weapon: CombatWeapon[];
  kills_by_weapon: CombatWeapon[];
  deaths_by_weapon: CombatWeapon[];
}

export interface CombatRecent {
  session_id: string;
  map: string;
  started_at: string;
  duration_s: number;
  team: Team | null;
  kills: number;
  deaths: number;
  assists: number;
  damage: number;
  objective_damage: number;
}

export interface CombatPlayerStats {
  user_id: string;
  name: string | null;
  matches: number;
  stats?: CombatTotals;
  by_map?: { map: string; matches: number; kills: number; deaths: number; assists: number; damage: number; objective_damage: number }[];
  events?: CombatEvents | null;
  recent?: CombatRecent[];
}

export interface CombatBoardRow {
  rank: number;
  user_id: string;
  name: string;
  matches: number;
  value: number;
  kills: number;
  deaths: number;
  assists: number;
  damage: number;
  kd: number | null;
}

export interface CombatBoard {
  stat: string;
  label: string;
  higher_is_better: boolean;
  items: CombatBoardRow[];
  total: number;
}

export interface CombatStatOption {
  key: string;
  label: string;
  higher_is_better: boolean;
  hint: string;
}

export interface CombatSummary {
  matches: number;
  players: number;
  matches_with_events: number;
  last_match_at: string | null;
}

export interface CombatMatchItem {
  session_id: string;
  map: string;
  started_at: string;
  duration_s: number;
  players: number;
  kills: number;
  damage: number;
  has_events: boolean;
}

export interface CombatMatchPlayer {
  user_id: string;
  name: string;
  team: Team | null;
  present_s: number;
  kills: number;
  assists: number;
  deaths: number;
  eliminations: number;
  damage: number;
  objective_eliminations: number;
  objective_damage: number;
  objective_time: number;
  hill_captures: number;
  hill_defends: number;
  weapons: string[];
  tacmods: string[];
  ordnance: string[];
  events: (Omit<CombatEvents, "matches" | "events_incomplete">) | null;
}

export interface CombatMatchDetail {
  session_id: string;
  map: string;
  started_at: string;
  ended_at: string;
  duration_s: number;
  has_events: boolean;
  events_complete: boolean | null;
  replay_match_id: number | null;
  teams: Partial<Record<Team, Record<string, number>>>;
  players: CombatMatchPlayer[];
}

export const getCombatPlayer = (userId: string, period: Period = "all", map?: string) =>
  request<CombatPlayerStats>(`/api/combat/players/${encodeURIComponent(userId)}${query({ period, map })}`);

export const getCombatBoard = (q: { stat: string; period: Period; map?: string; min_games: number; offset: number; limit: number }) =>
  request<CombatBoard>(`/api/combat/leaderboard${query({ ...q })}`);

export const getCombatStats = () => request<CombatStatOption[]>("/api/combat/stats");
export const getCombatSummary = () => request<CombatSummary>("/api/combat/summary");
export const listCombatMatches = (limit = 30, offset = 0, map?: string) =>
  request<Page<CombatMatchItem>>(`/api/combat/matches${query({ limit, offset, map })}`);
export const getCombatMatch = (id: string) => request<CombatMatchDetail>(`/api/combat/matches/${encodeURIComponent(id)}`);
