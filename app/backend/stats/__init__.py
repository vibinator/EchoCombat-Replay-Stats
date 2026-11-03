"""Frames -> MatchStats in a single pass. No database imports."""

from collections import Counter
from collections.abc import Iterable

from parser import Frame, ReplayMeta

from .maps import BOUNDS, LOAD_IN_SPOTS, MAP_MODES, map_name
from .payload import FINAL_CHECKPOINT, PayloadAccumulator
from .player import PlayerAccumulator
from .results import EventRecord, MatchStats, PlayerStats

STATS_VERSION = "9"  # 9: no deaths / respawns after the capture match is decided or the payload run is over. 8: the map's load-in spot (maps.LOAD_IN_SPOTS) is no longer a death, in-bounds time or track sample

CAPTURE_ROUNDS_TO_WIN = 2  # best of three: the round that makes it 2 decides the match

MAX_FRAME_GAP_S = 1.0  # cap per-frame time credit so a recording gap does not count as play time


class _MatchEvents:
    """Round, payload-checkpoint and contest transitions."""

    def __init__(self, meta: ReplayMeta, events: list[EventRecord]):
        self.started_at = meta.started_at
        self.events = events
        self.prev: Frame | None = None

    def _event(self, frame: Frame, type_: str, team: str | None = None, data: dict | None = None) -> None:
        t_s = round((frame.timestamp - self.started_at).total_seconds(), 3)
        self.events.append(EventRecord(frame.index, t_s, type_, team=team, data=data))

    def add(self, frame: Frame) -> None:
        prev = self.prev
        self.prev = frame
        if prev is None:
            return
        scores = {"blue": frame.blue_round_score, "orange": frame.orange_round_score}
        for team, before in (("blue", prev.blue_round_score), ("orange", prev.orange_round_score)):
            if scores[team] > before:
                self._event(frame, "round_won", team, scores)
        if frame.payload and prev.payload and frame.payload.checkpoint > prev.payload.checkpoint:
            data = {"checkpoint": frame.payload.checkpoint, "time_left_s": prev.game_timer}
            self._event(frame, "payload_checkpoint", data=data)
        if frame.contested != prev.contested:
            self._event(frame, "contest_start" if frame.contested else "contest_end")


def _capture_point_winner(last: Frame) -> str | None:
    if last.blue_round_score == last.orange_round_score:
        return None
    return "blue" if last.blue_round_score > last.orange_round_score else "orange"


def compute(meta: ReplayMeta, frames: Iterable[Frame], recorder=None) -> MatchStats:
    """`recorder` (backend.tracks.TrackRecorder) optionally collects 2 Hz position tracks."""
    name = map_name(meta.map_code)
    bounds = BOUNDS.get(name)
    load_in = LOAD_IN_SPOTS.get(name)
    events: list[EventRecord] = []
    match_events = _MatchEvents(meta, events)
    payload = PayloadAccumulator()
    players: dict[str, PlayerAccumulator] = {}
    prev: Frame | None = None
    count = 0
    contested_s = 0.0
    capture_s = {"blue": 0.0, "orange": 0.0}  # time each team's capture progress was rising
    has_payload = False
    capture_end = payload_end = None  # first frame after which nothing counts as play: players are moved out (fake deaths)

    for frame in frames:
        dt = 0.0 if prev is None else min(max((frame.timestamp - prev.timestamp).total_seconds(), 0.0), MAX_FRAME_GAP_S)
        if frame.contested:
            contested_s += dt
        if prev is not None:
            for team, now_points, before in (("blue", frame.blue_points, prev.blue_points),
                                             ("orange", frame.orange_points, prev.orange_points)):
                if now_points is not None and before is not None and now_points > before:
                    capture_s[team] += dt
        if recorder is not None:
            recorder.add(frame)
        has_payload = has_payload or frame.payload is not None
        if capture_end is None and max(frame.blue_round_score, frame.orange_round_score) >= CAPTURE_ROUNDS_TO_WIN:
            capture_end = frame.index
        if payload_end is None and frame.payload is not None and (
                frame.payload.checkpoint >= FINAL_CHECKPOINT
                or (prev is not None and prev.game_timer and frame.game_timer is not None and frame.game_timer <= 0)):
            payload_end = frame.index
        match_events.add(frame)
        payload.add(frame, dt)
        for team, own, other in (("blue", frame.blue, frame.orange), ("orange", frame.orange, frame.blue)):
            for p in own:
                acc = players.get(p.user_id)
                if acc is None:
                    acc = players[p.user_id] = PlayerAccumulator(p.user_id, bounds, meta.started_at, events, load_in)
                    if frame.index > 0:
                        acc.team = team
                        acc.event(frame, "player_join")
                acc.add(frame, team, p, dt, own, other)
        prev = frame
        count += 1

    last = prev
    for acc in players.values():
        if acc.last_frame < last.index:
            t_s = round((acc.last_seen - meta.started_at).total_seconds(), 3)
            events.append(EventRecord(acc.last_frame, t_s, "player_leave", acc.user_id, acc.team))
    events.sort(key=lambda e: e.frame)
    end_frame = payload_end if has_payload else capture_end
    if end_frame is not None:  # deaths after the match is over are the players being moved on, not real deaths
        late = Counter(e.user_id for e in events if e.frame > end_frame and e.type == "death_est")
        for user_id, n in late.items():
            players[user_id].deaths -= n
        events[:] = [e for e in events if not (e.frame > end_frame and e.type in ("death_est", "respawn"))]

    duration_s = (last.timestamp - meta.started_at).total_seconds()
    mode = MAP_MODES.get(name) or ("payload" if has_payload else "capture_point")
    player_stats = [acc.result(last.timestamp) for acc in players.values()]
    for p in player_stats:
        p.payload_push_s, p.payload_block_s = payload.push_block(p.user_id)
    return MatchStats(
        map=name,
        mode=mode,
        started_at=meta.started_at,
        ended_at=last.timestamp,
        duration_s=round(duration_s, 3),
        frame_count=count,
        frame_rate_hz=round(count / duration_s, 3) if duration_s > 0 else 0.0,
        blue_rounds=last.blue_round_score,
        orange_rounds=last.orange_round_score,
        final_blue_points=last.blue_points,
        final_orange_points=last.orange_points,
        final_payload_checkpoint=last.payload.checkpoint if last.payload else None,
        final_payload_distance=last.payload.distance if last.payload else None,
        contested_s=round(contested_s, 3),
        blue_capture_s=round(capture_s["blue"], 3),
        orange_capture_s=round(capture_s["orange"], 3),
        winner=payload.winner(last) if mode == "payload" else _capture_point_winner(last),
        attacking_team=payload.attacking_team() if mode == "payload" else None,
        final_game_timer=last.game_timer,
        players=player_stats,
        events=events,
    )


__all__ = ["STATS_VERSION", "EventRecord", "MatchStats", "PlayerStats", "compute"]
