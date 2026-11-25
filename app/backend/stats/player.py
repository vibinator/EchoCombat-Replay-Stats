"""Per-player accumulator. Rules follow the old app (ReplayData.MD): ping over all frames (except the 999 placeholder),
everything else over in-bounds frames only; a death is an in-bounds -> out-of-bounds step. Frames at the load-in
spot (maps.LOAD_IN_SPOTS, per map) are neither: leaving it for the war room is not a death."""

import math
from collections import Counter, deque
from datetime import datetime

from parser import Frame, PlayerFrame
from parser.models import Vec3

from .maps import Bounds, at_spawn, in_bounds, is_load_in
from .results import EventRecord, PlayerStats

LEFT_EARLY_S = 45.0  # last seen more than 45 s before the end (old "crashed")
NEAR_DISTANCE_SQ = 7.0  # head distance² in m² (≈ 2.65 m)
LONE_WOLF_DISTANCE_SQ = 12.25  # head distance² in m² (3.5 m): Lone Wolf only; every other "near" stat keeps NEAR_DISTANCE_SQ
STOPPED_SPEED = 1.0  # m/s
PING_PLACEHOLDER = 999  # API value when there is no reading; excluded from average ping
PING_CAP = 400  # a reading above this counts as this much in averages (profile, leaderboard, trends); the match page shows the raw average
# Top speed (user, 2026-11-25): the fastest average over one second, and the distance must really be covered. No peaks
# (single readings spike to 100+ m/s), and never more than the distance travelled, along the way the player went, turns
# included. The way is measured in TOP_SPEED_LEGS parts of the second, not frame by frame: shaking on the spot is no
# way travelled (38 m/s of readings within 2 m seen). Until then it was the highest speed held all through a second.
TOP_SPEED_WINDOW_S = 1.0
TOP_SPEED_LEGS = 4
# The API's velocity alone is not movement: a player whose data stops coming (lag, loading into the match) keeps the
# last velocity while standing still, and may then jump. So the second only counts when the player ended up where the
# velocity takes them. Measured on 800 recent matches, 94,113 seconds above 8 m/s: the two agree within 1 % (median),
# within 12 % in 99 % of those above 12 m/s; frozen players are 95-100 % apart. Recorders below ~15 frames a second run
# the game in slow motion and are 28-30 % apart: those pass, and the distance covered is what counts there.
TOP_SPEED_MISMATCH = 0.5  # share of the distance the velocity stands for
TOP_SPEED_MISMATCH_M = 0.5  # always allowed: the head moves about on its own, the velocity is the body's
TOP_SPEED_MAX_GAP_S = 0.5  # a longer gap in the recording starts a new window: nobody saw what happened in between
FROZEN_S = 0.5  # head at exactly the same spot this long: no data coming in, the velocity is stale. A headset is never that still


class PlayerAccumulator:
    def __init__(self, user_id: str, bounds: Bounds | None, started_at: datetime, events: list[EventRecord],
                 load_in: Vec3 | None = None, spawns=None):
        self.user_id = user_id
        self.spawns = spawns  # this map's spawn circles (maps.SPAWN_CIRCLES): leaving from one is not a death
        self.bounds = bounds  # None for unknown maps: every frame counts as in bounds, no deaths
        self.load_in = load_in  # this map's load-in spot (maps.LOAD_IN_SPOTS); None: no load-in rule
        self.started_at = started_at
        self.events = events
        self.first_frame = self.last_frame = -1
        self.frames = 0
        self.play_time_s = 0.0
        self.team_frames: Counter[str] = Counter()
        self.last_seen: datetime | None = None
        self.latest: PlayerFrame | None = None
        self.team = ""

        self.ping_sum = 0.0
        self.ping_capped_sum = 0.0
        self.packet_loss_sum = 0.0
        self.emote_count = 0
        self._emoting = False
        self.ping_frames = 0
        self.frames_in_bounds = 0
        self.speed_sum = 0.0
        self.top_speed = 0.0
        self.frames_stopped = 0
        self.frames_upside_down = 0
        self.frames_near_mate = 0
        self.frames_lone_wolf_near = 0
        self.frames_near_enemy = 0
        self.frames_left_arm = 0
        self.frames_right_arm = 0
        self.deaths = 0
        self.loadouts: Counter[tuple[str, str, str]] = Counter()

        self._was_in_bounds: bool | None = None
        self._last_in_bounds_position = None
        self._loadout: tuple[str, str, str] | None = None
        self._window: deque[tuple] = deque()  # (t_s, speed, head position, velocity), in-bounds only
        self._window_m = 0.0  # the distance the speeds in it stand for
        self._still_at: Vec3 | None = None  # where the head has been exactly since _still_from
        self._still_from = 0.0
        self._still_sum = 0.0  # speed_sum counted since then, taken back when the player turns out to be frozen

    def event(self, frame: Frame, type_: str, data: dict | None = None) -> None:
        t_s = round((frame.timestamp - self.started_at).total_seconds(), 3)
        self.events.append(EventRecord(frame.index, t_s, type_, self.user_id, self.team, data))

    def add(self, frame: Frame, team: str, p: PlayerFrame, dt: float,
            teammates: list[PlayerFrame], enemies: list[PlayerFrame]) -> None:
        if self.first_frame < 0:
            self.first_frame = frame.index
        self.last_frame = frame.index
        self.last_seen = frame.timestamp
        self.frames += 1
        self.play_time_s += dt
        self.team_frames[team] += 1
        self.team = team
        self.latest = p
        self.packet_loss_sum += p.packet_loss
        if p.emote and not self._emoting:
            self.emote_count += 1
        self._emoting = p.emote
        if p.ping < PING_PLACEHOLDER:
            self.ping_sum += p.ping
            self.ping_capped_sum += min(p.ping, PING_CAP)  # spikes count as PING_CAP in averages (user, 2026-11-07)
            self.ping_frames += 1

        loading_in = is_load_in(p.head_position, self.load_in)  # parked at the load-in spot: neither in nor out
        inside = not loading_in and (self.bounds is None or in_bounds(p.head_position, self.bounds))
        if inside:
            if self._was_in_bounds is False:
                self.event(frame, "respawn")
            self._last_in_bounds_position = p.head_position
            self._add_in_bounds(frame, p, teammates, enemies)
        elif self._was_in_bounds and not loading_in:
            # gone from the play area. From a spawn point: back to the war room by choice, not a death (user,
            # 2026-11-10); coming back out still shows as a respawn, which it is
            if not at_spawn(self._last_in_bounds_position, self.spawns):
                self.deaths += 1
                x, _, z = self._last_in_bounds_position
                self.event(frame, "death_est", {"x": round(x, 2), "z": round(z, 2)})
        if not inside:
            self._window.clear()
            self._window_m = 0.0
            self._still_at = None
        self._was_in_bounds = inside

    def _add_in_bounds(self, frame: Frame, p: PlayerFrame, teammates, enemies) -> None:
        self.frames_in_bounds += 1
        if p.body_up[1] < 0:
            self.frames_upside_down += 1

        speed = math.hypot(*p.velocity)
        t_s = (frame.timestamp - self.started_at).total_seconds()
        self._track_speed_sum(t_s, speed, p.head_position)
        if speed < STOPPED_SPEED:
            self.frames_stopped += 1
        self._track_top_speed(t_s, speed, p.head_position, p.velocity)

        if p.arm == "Right":
            self.frames_right_arm += 1
        elif p.arm == "Left":
            self.frames_left_arm += 1

        x, y, z = p.head_position  # head distance² written out: ~100k player frames x team size per match
        closest = LONE_WOLF_DISTANCE_SQ
        for o in teammates:
            if o is not p:
                ox, oy, oz = o.head_position
                closest = min(closest, (x - ox) ** 2 + (y - oy) ** 2 + (z - oz) ** 2)
                if closest < NEAR_DISTANCE_SQ:
                    self.frames_near_mate += 1
                    break
        if closest < LONE_WOLF_DISTANCE_SQ:
            self.frames_lone_wolf_near += 1
        for o in enemies:
            ox, oy, oz = o.head_position
            if (x - ox) ** 2 + (y - oy) ** 2 + (z - oz) ** 2 < NEAR_DISTANCE_SQ:
                self.frames_near_enemy += 1
                break

        loadout = (p.weapon, p.tacmod, p.ordnance)
        if not any(loadout):
            return  # no loadout info (replays before ~2021 Q4 have no loadout fields)
        self.loadouts[loadout] += 1
        if loadout != self._loadout:
            self._loadout = loadout
            self.event(frame, "loadout_change", dict(zip(("weapon", "tacmod", "ordnance"), loadout)))

    def _track_speed_sum(self, t_s: float, speed: float, head: Vec3) -> None:
        """Average speed and distance: a frozen player's stale velocity is no movement (FROZEN_S)."""
        if head != self._still_at:
            self._still_at, self._still_from, self._still_sum = head, t_s, 0.0
        elif t_s - self._still_from >= FROZEN_S:
            self.speed_sum = max(0.0, self.speed_sum - self._still_sum)
            self._still_sum = 0.0
            return
        self.speed_sum += speed
        self._still_sum += speed

    def _track_top_speed(self, t_s: float, speed: float, head: Vec3, velocity: Vec3) -> None:
        window = self._window
        if window:
            t0, before = window[-1][:2]
            if t_s - t0 > TOP_SPEED_MAX_GAP_S:
                window.clear()
                self._window_m = 0.0
            else:
                self._window_m += (before + speed) / 2 * (t_s - t0)
        window.append((t_s, speed, head, velocity))
        # Keep the shortest run of samples that still spans the window.
        while len(window) > 1 and window[1][0] <= t_s - TOP_SPEED_WINDOW_S:
            t0, before = window.popleft()[:2]
            self._window_m -= (before + window[0][1]) / 2 * (window[0][0] - t0)
        span = t_s - window[0][0]
        if span < TOP_SPEED_WINDOW_S:
            return
        if self._window_m > self.top_speed * span:
            self.top_speed = max(self.top_speed, min(self._window_m, self._travelled(span)) / span)

    def _travelled(self, span: float) -> float:
        """Distance travelled in the window (TOP_SPEED_LEGS); 0 when the player did not end up where its velocities
        take them (TOP_SPEED_MISMATCH)."""
        distance = travelled = dx = dy = dz = 0.0
        leg = 1
        samples = iter(self._window)
        t0, v0, start, (x0, y0, z0) = next(samples)
        began, corner, head = t0, start, start
        for t1, v1, head, (x1, y1, z1) in samples:
            half = (t1 - t0) / 2
            distance += (v0 + v1) * half
            dx += (x0 + x1) * half
            dy += (y0 + y1) * half
            dz += (z0 + z1) * half
            if t1 - began >= span * leg / TOP_SPEED_LEGS:
                travelled += math.dist(corner, head)
                corner, leg = head, int((t1 - began) / span * TOP_SPEED_LEGS) + 1
            t0, v0, x0, y0, z0 = t1, v1, x1, y1, z1
        travelled += math.dist(corner, head)
        carried = (start[0] + dx, start[1] + dy, start[2] + dz)
        return travelled if math.dist(carried, head) <= max(TOP_SPEED_MISMATCH_M, TOP_SPEED_MISMATCH * distance) else 0.0

    def result(self, ended_at: datetime) -> PlayerStats:
        p = self.latest
        return PlayerStats(
            user_id=self.user_id,
            name=p.name,
            team=self.team_frames.most_common(1)[0][0],
            slot=p.slot,
            number=p.number,
            level=p.level,
            first_frame=self.first_frame,
            last_frame=self.last_frame,
            frames_present=self.frames,
            play_time_s=round(self.play_time_s, 3),
            left_early=(ended_at - self.last_seen).total_seconds() > LEFT_EARLY_S,
            ping_sum=self.ping_sum,
            ping_frames=self.ping_frames,
            ping_capped_sum=self.ping_capped_sum,
            packet_loss_sum=round(self.packet_loss_sum, 4),
            emote_count=self.emote_count,
            frames_in_bounds=self.frames_in_bounds,
            speed_sum=round(self.speed_sum, 3),
            top_speed=round(self.top_speed, 3),
            frames_stopped=self.frames_stopped,
            frames_upside_down=self.frames_upside_down,
            frames_near_mate=self.frames_near_mate,
            frames_lone_wolf_near=self.frames_lone_wolf_near,
            frames_near_enemy=self.frames_near_enemy,
            frames_left_arm=self.frames_left_arm,
            frames_right_arm=self.frames_right_arm,
            deaths_est=self.deaths,
            loadouts=dict(self.loadouts),
        )
