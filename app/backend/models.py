"""Tables as specified in docs/DataModel.MD."""

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Replay(Base):
    """One file in the replay share. Identified by its path relative to the share root."""

    __tablename__ = "replays"
    __table_args__ = (
        Index("ix_replays_status_mtime", "status", "source_mtime"),
        Index("ix_replays_status_processed", "status", "processed_at"),  # data_stamp (cache keys)
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(unique=True)  # e.g. "surge/ABC.echoreplay", forward slashes
    size_bytes: Mapped[int]
    source_mtime: Mapped[float] = mapped_column(index=True)  # file modified time (epoch s); size or mtime change -> reprocess
    discovered_at: Mapped[str]
    container: Mapped[str | None]
    status: Mapped[str]
    error_code: Mapped[str | None]
    error_message: Mapped[str | None]
    warnings: Mapped[str | None]  # JSON list
    parser_version: Mapped[str | None]
    stats_version: Mapped[str | None]
    processed_at: Mapped[str | None]


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (Index("ix_matches_private_started", "private_match", "started_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    replay_id: Mapped[int] = mapped_column(ForeignKey("replays.id", ondelete="CASCADE"), unique=True)
    session_id: Mapped[str] = mapped_column(index=True)
    map_code: Mapped[str]
    map: Mapped[str] = mapped_column(index=True)
    mode: Mapped[str]
    private_match: Mapped[bool]
    tournament_match: Mapped[bool]
    recorded_by: Mapped[str | None]
    started_at: Mapped[str] = mapped_column(index=True)
    ended_at: Mapped[str]
    duration_s: Mapped[float]
    frame_count: Mapped[int]
    frame_rate_hz: Mapped[float]
    blue_rounds: Mapped[int]
    orange_rounds: Mapped[int]
    final_blue_points: Mapped[float | None]
    final_orange_points: Mapped[float | None]
    final_payload_checkpoint: Mapped[int | None]
    final_payload_distance: Mapped[float | None]
    contested_s: Mapped[float]
    winner: Mapped[str | None]
    attacking_team: Mapped[str | None]  # payload only
    final_game_timer: Mapped[float | None]  # payload only
    has_tracks: Mapped[bool]  # position tracks file saved (heatmaps / timeline chart)
    blue_capture_s: Mapped[float]  # capture-point: time blue's progress was rising
    orange_capture_s: Mapped[float]


class DuplicateMatch(Base):
    """The same match recorded in more than one file (D13): `match_id` is a copy that does not count towards stats,
    because `counted_match_id` (same session, overlapping time) does. Its match page still works. Set by duplicates.py."""

    __tablename__ = "duplicate_matches"

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    counted_match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), index=True)


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str] = mapped_column(index=True)
    first_seen_at: Mapped[str]
    last_seen_at: Mapped[str] = mapped_column(index=True)  # players list order


class MatchPlayer(Base):
    __tablename__ = "match_players"
    # per-player counts that leave duplicate recordings out (D13) read only this index
    __table_args__ = (Index("ix_match_players_player_match", "player_id", "match_id"),)

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    team: Mapped[str]
    name: Mapped[str]
    slot: Mapped[int | None]
    number: Mapped[int | None]
    level: Mapped[int | None]
    first_frame: Mapped[int]
    last_frame: Mapped[int]
    frames_present: Mapped[int]
    play_time_s: Mapped[float]
    left_early: Mapped[bool]
    ping_sum: Mapped[float]
    ping_frames: Mapped[int]
    frames_in_bounds: Mapped[int]
    speed_sum: Mapped[float]
    top_speed: Mapped[float] = mapped_column(index=True)  # home page "fastest player"
    frames_stopped: Mapped[int]
    frames_upside_down: Mapped[int]
    frames_near_mate: Mapped[int]
    frames_lone_wolf_near: Mapped[int | None]  # within 3.5 m of a teammate: Lone Wolf only. Added in place, NULL until the replay is read again (D57)
    frames_near_enemy: Mapped[int]
    frames_left_arm: Mapped[int]
    frames_right_arm: Mapped[int]
    deaths_est: Mapped[int]
    payload_push_s: Mapped[float]
    payload_block_s: Mapped[float]
    packet_loss_sum: Mapped[float]
    emote_count: Mapped[int]


class MatchPlayerLoadout(Base):
    __tablename__ = "match_player_loadouts"
    # covering index for the home page's most-used gear (one pass in gear order, no temp table): 330 -> 95 ms
    __table_args__ = (Index("ix_loadouts_gear", "weapon", "ordnance", "tacmod", "match_id", "frames"),)

    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True)
    weapon: Mapped[str] = mapped_column(primary_key=True)
    tacmod: Mapped[str] = mapped_column(primary_key=True)
    ordnance: Mapped[str] = mapped_column(primary_key=True)
    frames: Mapped[int]


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (Index("ix_events_match_t", "match_id", "t_s"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id", ondelete="CASCADE"))
    frame: Mapped[int]
    t_s: Mapped[float]
    type: Mapped[str]
    player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"))
    team: Mapped[str | None]
    data: Mapped[str | None]  # JSON


class AppSetting(Base):
    """Admin-editable settings (e.g. the Flamingo Challenge period, D33). Not rebuilt from the share."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str | None]
    updated_at: Mapped[str]


class PlayerProfile(Base):
    """Discord link + what the player may change about their page (user, 2026-11-02): the bio and whether their
    Discord avatar is shown. Linked by the Discord bot (trusted, POST /api/bot/link); edited on the website by the
    linked Discord account only. Kept across rebuilds."""

    __tablename__ = "player_profiles"

    user_id: Mapped[str] = mapped_column(primary_key=True)  # EchoVR user id (the main id when merged, D34)
    discord_id: Mapped[str] = mapped_column(unique=True)  # one player per Discord account
    bio: Mapped[str | None]
    show_avatar: Mapped[bool] = mapped_column(default=True)
    linked_at: Mapped[str]
    updated_at: Mapped[str]


class PlayerAlias(Base):
    """Admin player merge (D34): `alias_user_id` is the same person as `main_user_id`. Kept across rebuilds."""

    __tablename__ = "player_aliases"

    alias_user_id: Mapped[str] = mapped_column(primary_key=True)
    main_user_id: Mapped[str] = mapped_column(index=True)
    created_at: Mapped[str]


class RepairRequest(Base):
    """Replays to process in repair (salvage) mode (D36). Kept across rebuilds, keyed by file path."""

    __tablename__ = "repair_requests"

    source_path: Mapped[str] = mapped_column(primary_key=True)
    requested_at: Mapped[str]


class AggressiveRepair(Base):
    """Replays to process in aggressive repair mode (D36b): failed ones that repair mode could not fix. Kept across
    rebuilds, keyed by file path."""

    __tablename__ = "aggressive_repairs"

    source_path: Mapped[str] = mapped_column(primary_key=True)
    requested_at: Mapped[str]


class PriorityReplay(Base):
    """Queued replays to process before the backlog (admin console merges / repairs). Removed when claimed."""

    __tablename__ = "priority_replays"

    replay_id: Mapped[int] = mapped_column(primary_key=True)


class HiddenReplay(Base):
    """Failed replays an admin chose to hide (they cannot be repaired): left out of the failed lists and
    counts and of "repair all". Set in the admin console; kept across rebuilds, keyed by file path."""

    __tablename__ = "hidden_replays"

    source_path: Mapped[str] = mapped_column(primary_key=True)
    hidden_at: Mapped[str]


class ConsoleLog(Base):
    """Audit log of console commands (user, 2026-11-02): who ran what, from the website's Console page or admin.bat.
    Kept across rebuilds."""

    __tablename__ = "console_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(index=True)  # UTC, ISO
    source: Mapped[str]  # "website" / "admin.bat"
    who_id: Mapped[str | None]  # Discord user id (website)
    who_name: Mapped[str]
    command: Mapped[str]
    args: Mapped[str | None]  # JSON
    ok: Mapped[bool]
    output: Mapped[str | None]  # what it printed, cut to OUTPUT_MAX


class ArenaPlayer(Base):
    """Public Echo Arena matches per player, counted from the live Nakama match list (arena.py). Completely separate
    from the Combat stats (user, 2026-11-04). Kept across rebuilds: it cannot be recomputed from anything."""

    __tablename__ = "arena_players"

    user_id: Mapped[str] = mapped_column(primary_key=True)  # Nakama user id
    username: Mapped[str]
    display_name: Mapped[str | None]
    discord_id: Mapped[str | None] = mapped_column(index=True)  # links the visitor (Discord login) to their Arena matches
    matches: Mapped[int] = mapped_column(default=0, index=True)
    last_match_at: Mapped[str]


class ArenaCounted(Base):
    """A (match, player) already counted, so a restart or a rejoin never counts it twice. Pruned after 2 days."""

    __tablename__ = "arena_counted"

    match_id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[str] = mapped_column(primary_key=True)
    counted_at: Mapped[float] = mapped_column(index=True)  # epoch s


class CombatFile(Base):
    """One match report (`matches/<MatchID>.json`) in the recorder's data folder: the combat-stats twin of `Replay`.
    Completely separate from the replay data (user, 2026-11-04): own tables, own reader (combat.py), own endpoints."""

    __tablename__ = "combat_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_path: Mapped[str] = mapped_column(unique=True)  # relative to the recorder folder, e.g. "matches/ABC.json"
    size_bytes: Mapped[int]
    source_mtime: Mapped[float]
    status: Mapped[str]  # done / failed
    error_message: Mapped[str | None]
    parser_version: Mapped[str | None]
    processed_at: Mapped[str | None]


class CombatMatch(Base):
    __tablename__ = "combat_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("combat_files.id", ondelete="CASCADE"), unique=True)
    session_id: Mapped[str] = mapped_column(unique=True)  # upper-case match id
    map: Mapped[str] = mapped_column(index=True)  # combustion / dyson / fission / surge (or the raw level name)
    started_at: Mapped[str] = mapped_column(index=True)  # recorder-local time, no zone (same clock as replay matches)
    ended_at: Mapped[str]
    duration_s: Mapped[float]
    has_events: Mapped[bool]  # the event log (shots, weapons...) was available for this match
    events_complete: Mapped[bool | None]  # False = event counts of this match are too low
    teams: Mapped[str | None]  # JSON {"blue": {...stats}, "orange": {...}}


class CombatPlayer(Base):
    """One player in one match, keyed by the account id as TEXT (64-bit). `damage_taken` is not stored: spectator
    captures always have 0 there (not available)."""

    __tablename__ = "combat_players"
    __table_args__ = (Index("ix_combat_players_user_match", "user_id", "match_id"),)

    match_id: Mapped[int] = mapped_column(ForeignKey("combat_matches.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    team: Mapped[str | None]
    present_s: Mapped[float]
    kills: Mapped[int]
    assists: Mapped[int]
    deaths: Mapped[int]
    eliminations: Mapped[int]
    damage: Mapped[float]
    objective_eliminations: Mapped[int]
    objective_damage: Mapped[float]
    objective_time: Mapped[float]
    hill_captures: Mapped[int]
    hill_defends: Mapped[int]
    loadouts: Mapped[str | None]  # JSON {"weapons": [...], "tacmods": [...], "ordnance": [...]}
    # event-log numbers: NULL = no event log for this match (unknown, not zero)
    shots: Mapped[int | None]
    tacmod_activations: Mapped[int | None]
    heal_bubbles: Mapped[int | None]
    stuns_given: Mapped[int | None]
    stuns_received: Mapped[int | None]
    self_kills: Mapped[int | None]
    shots_by_weapon: Mapped[str | None]  # JSON {weapon: count}
    kills_by_weapon: Mapped[str | None]
    deaths_by_weapon: Mapped[str | None]
