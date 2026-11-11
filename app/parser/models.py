"""Typed frame data. Only fields confirmed in docs/ReplayData.MD; add new ones here and in frames.py."""

from dataclasses import dataclass
from datetime import datetime

Vec3 = tuple[float, float, float]


@dataclass(slots=True)
class PlayerFrame:
    user_id: str  # > 2^53, kept as text
    name: str
    slot: int  # playerid
    number: int
    level: int
    ping: int
    packet_loss: float
    head_position: Vec3
    head_forward: Vec3  # unit vector the head faces (3D playback)
    lhand: Vec3  # hand positions (3D playback); the head position when missing
    rhand: Vec3
    body_up: Vec3
    velocity: Vec3
    weapon: str
    tacmod: str
    ordnance: str
    arm: str
    emote: bool  # is_emote_playing
    head_up: Vec3 = (0.0, 1.0, 0.0)  # unit vector out of the top of the head: with head_forward it gives the roll (3D playback)


@dataclass(slots=True)
class PayloadState:
    position: Vec3
    checkpoint: int
    distance: float
    speed: float
    attackers: int
    defenders: int


@dataclass(slots=True)
class Frame:
    index: int
    timestamp: datetime  # naive, recorder local time
    blue: list[PlayerFrame]
    orange: list[PlayerFrame]
    blue_round_score: int
    orange_round_score: int
    contested: bool
    blue_points: float | None  # capture-point maps
    orange_points: float | None
    payload: PayloadState | None  # payload maps
    game_timer: float | None
    overtime_timer: float | None = None  # payload maps: runs while the attackers hold on after the game timer's end
    # The game's record of the latest kill: (killed, killer, killed_with), each a player's name or "playerid:<n>" and
    # a weapon code or hash; ("", "", "") before the first kill. None: the recording has no such field (every replay
    # before 2026-11-04).
    last_kill: tuple[str, str, str] | None = None


@dataclass(frozen=True)
class ReplayMeta:
    session_id: str
    match_type: str
    map_code: str
    private_match: bool
    tournament_match: bool
    client_name: str | None
    container: str  # zip | plain
    started_at: datetime
