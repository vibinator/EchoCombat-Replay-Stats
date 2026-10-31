function errorMessage(body: unknown, status: number): string {
  const message = (body as { message?: unknown } | null)?.message;
  return typeof message === "string" ? message : `Request failed (${status})`;
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  // X-EchoVR: the server answers /api only to this site's own pages (scraper protection, D48)
  const res = await fetch(path, { ...init, headers: { "X-EchoVR": "1", ...init?.headers } });
  if (!res.ok) throw new Error(errorMessage(await res.json().catch(() => null), res.status));
  return (res.status === 204 ? undefined : await res.json()) as T;
}

// The website is read-only (changes are made in the admin console). GET responses are reused for a minute: going
// back to a page is instant, and two components asking for the same thing share one request.
const CACHE_MS = 60_000;
const responses = new Map<string, { at: number; value: Promise<unknown> }>();

function request<T>(path: string, init?: RequestInit): Promise<T> {
  if (init) return send<T>(path, init);
  const hit = responses.get(path);
  if (hit && Date.now() - hit.at < CACHE_MS) return hit.value as Promise<T>;
  const value = send<T>(path);
  responses.set(path, { at: Date.now(), value });
  value.catch(() => responses.delete(path)); // never keep an error
  return value;
}

/** After a change (icons, Console): ask the server again instead of reusing answers. */
export function forgetResponses(): void {
  responses.clear();
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
  wins: number;
  losses: number;
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
  result: "win" | "loss" | null;
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
  loadouts: Loadout[];
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
  cells: [number, number, number][];
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
}

export interface Leaderboard {
  stat: string;
  label: string;
  higher_is_better: boolean;
  total: number;
  items: LeaderboardRow[];
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
  request<Heatmap>(`/api/matches/${id}/heatmap${query({ player })}`);

export const getTimeline = (id: number) => request<Timeline>(`/api/matches/${id}/timeline`);

export const getPlayerHeatmap = (userId: string, map: string, mode: HeatmapMode, period: Period, last: number) =>
  request<Heatmap>(`/api/players/${encodeURIComponent(userId)}/heatmap${query({ map, mode, period, last })}`);

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
  period: "game" | "day" | "week" | "all";
  icon: string | null;
  estimated: boolean;
  new: boolean; // added in this app (80+), not on the original ECRanked site
  group: string | null; // theme of a new achievement
}

export interface Achievement extends AchievementRule {
  progress: number;
  tier: "white" | "bronze" | "silver" | "gold" | null;
  unlocked_at: string | null;
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
  payload_attack_win_rate: number | null;
  payload_decided: number;
  capture_wins: { blue: number; orange: number };
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
  top_this_week: { user_id: string; name: string; games: number; wins: number }[];
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

export interface Playback {
  map: string;
  image: string;
  hz: number;
  samples: number;
  players: { user_id: string; name: string; points: ([number, number, number] | null)[] }[];
}

export interface TrendPoint {
  period: string;
  games: number;
  win_rate: number | null;
  deaths_per_game_est: number | null;
  avg_speed: number | null;
  top_speed: number;
  avg_ping: number | null;
}

export interface Companion {
  user_id: string;
  name: string;
  games: number;
  wins: number;
  losses: number;
}

export interface Comparison {
  period: Period;
  players: { user_id: string; name: string; stats: PlayerStats }[];
  head_to_head: Record<"together" | "against", { games: number; wins: number; losses: number }>;
}

export interface ChallengeWindow {
  start: string | null;
  end: string | null;
  updated_at: string | null;
  /** false until the admin-set start date: achievements and challenges are "Coming soon" */
  launched: boolean;
  /** before the launch: this visitor has the Discord preview role and sees everything */
  preview: boolean;
  active: boolean;
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
  user_id: string;
  name: string;
  id: number;
  achievement: string;
  icon: string | null;
}

export const getMe = () => request<Me>("/api/auth/me");
/** Full-page navigation (not a fetch): Discord's login page, then back to `next`. */
export const loginUrl = (next: string) => `/api/auth/login?next=${encodeURIComponent(next)}`;
export const LOGOUT_URL = "/api/auth/logout";
export const getHealth = () => request<{ version: string }>("/api/health");
export const getOverview = () => request<Overview>("/api/overview");
export const getProcessing = () => request<{ pending: number }>("/api/overview/processing");
export const getActivity = (bucket: "day" | "week" | "month" | "year") =>
  request<{ bucket: string; items: { period: string; matches: number; hours: number; maps: Record<string, number> }[] }>(`/api/overview/activity?bucket=${bucket}`);
export const getPlayersSeen = (range: PlayersSeen["range"], anchor: PlayersSeen["anchor"]) =>
  request<PlayersSeen>(`/api/overview/players-seen?range=${range}&anchor=${anchor}`);
export const search = (q: string) => request<SearchResult>(`/api/search${query({ q })}`);
export const getPlayback = (id: number) => request<Playback>(`/api/matches/${id}/playback`);
export const getTrends = (userId: string, bucket: "week" | "month" | "year") =>
  request<{ bucket: string; items: TrendPoint[] }>(`/api/players/${encodeURIComponent(userId)}/trends?bucket=${bucket}`);
export const getCompanions = (userId: string) =>
  request<{ teammates: Companion[]; opponents: Companion[] }>(`/api/players/${encodeURIComponent(userId)}/companions`);
export const comparePlayers = (userIds: string[], period: Period) =>
  request<Comparison>(`/api/players/compare/${userIds.map(encodeURIComponent).join(",")}?period=${period}`);
export const getChallenges = () => request<ChallengeWindow>("/api/challenges");
export const getRarity = () => request<AchievementRarity[]>("/api/achievements");
export const getRecentUnlocks = () => request<RecentUnlock[]>("/api/achievements/recent");

export type HeatmapLayerMode = "team" | "weapons" | "ordnance" | "tacmod" | "loadout" | "speed";

export const getMatchHeatmapBy = (id: number, mode: HeatmapLayerMode | "player", cell: number, player?: string) =>
  request<Heatmap>(`/api/matches/${id}/heatmap${query({ mode, cell, player })}`);
export const getPlayerHeatmapBy = (userId: string, map: string, mode: HeatmapLayerMode | "deaths", period: Period, last: number, cell: number) =>
  request<Heatmap>(`/api/players/${encodeURIComponent(userId)}/heatmap${query({ map, mode, period, last, cell })}`);
