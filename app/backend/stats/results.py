"""Output of stats.compute(); persisted by backend/persist.py. Counters default to 0 until their calculator exists."""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PlayerStats:
    user_id: str
    name: str
    team: str
    slot: int | None
    number: int | None
    level: int | None
    first_frame: int
    last_frame: int
    frames_present: int
    play_time_s: float
    left_early: bool
    ping_sum: float = 0.0
    ping_frames: int = 0  # frames with a real ping reading (not 999)
    ping_capped_sum: float = 0.0  # the same readings capped at player.PING_CAP (400 ms): averages use this (DATA-5)
    frames_in_bounds: int = 0
    speed_sum: float = 0.0
    top_speed: float = 0.0
    frames_stopped: int = 0
    frames_upside_down: int = 0
    frames_near_mate: int = 0
    frames_lone_wolf_near: int = 0  # within 3.5 m of a teammate: Lone Wolf only
    frames_near_enemy: int = 0
    frames_left_arm: int = 0
    frames_right_arm: int = 0
    deaths_est: int = 0
    payload_push_s: float = 0.0  # estimated: within 3 m of payload while attackers counted
    payload_block_s: float = 0.0  # estimated: within 3 m while defenders counted
    packet_loss_sum: float = 0.0  # ÷ frames_present = avg packet loss ratio
    emote_count: int = 0  # emotes started (is_emote_playing false -> true)
    loadouts: dict[tuple[str, str, str], int] = field(default_factory=dict)  # (weapon, tacmod, ordnance) -> frames


@dataclass
class EventRecord:
    frame: int
    t_s: float
    type: str
    user_id: str | None = None
    team: str | None = None
    data: dict | None = None


@dataclass
class MatchStats:
    map: str
    mode: str
    started_at: datetime
    ended_at: datetime
    duration_s: float
    frame_count: int
    frame_rate_hz: float
    blue_rounds: int
    orange_rounds: int
    final_blue_points: float | None
    final_orange_points: float | None
    final_payload_checkpoint: int | None
    final_payload_distance: float | None
    contested_s: float
    blue_capture_s: float
    orange_capture_s: float
    winner: str | None
    attacking_team: str | None
    final_game_timer: float | None
    players: list[PlayerStats]
    events: list[EventRecord] = field(default_factory=list)
