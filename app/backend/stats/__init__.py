"""Frames -> MatchStats in a single pass. No database imports."""

from bisect import bisect_left, bisect_right
from collections import Counter
from collections.abc import Iterable

from parser import Frame, ReplayMeta

from .maps import BOUNDS, LOAD_IN_SPOTS, MAP_MODES, SPAWN_CIRCLES, map_name
from .payload import FINAL_CHECKPOINT, PayloadAccumulator
from .player import PlayerAccumulator
from .results import EventRecord, MatchStats, PlayerStats

STATS_VERSION = "16"  # 16: that move is told by everybody leaving the map at once, in a wide window (ROUND_MOVE_WINDOW_S), not by the clock alone. 15: the move to the war room after a round that does not decide the match is not a death. 14: the spawn points are the measured ones (1.5 m, Dyson's two entry tubes too; its bounds reach x = +-110 for them). 13: leaving the play area from a spawn point (maps.SPAWN_CIRCLES) is not a death. 12: play-area bounds of Combustion, Surge and Fission had x and z swapped (maps.BOUNDS): deaths, in-bounds time and everything counted in bounds change on those maps. 11: ping_capped_sum (ping spikes capped at 400 ms in averages, DATA-5; in place, D57). 10: frames_lone_wolf_near (3.5 m, Lone Wolf). 9: no deaths / respawns after the capture match is decided or the payload run is over. 8: the map's load-in spot (maps.LOAD_IN_SPOTS) is no longer a death, in-bounds time or track sample

CAPTURE_ROUNDS_TO_WIN = 2  # best of three: the round that makes it 2 decides the match
# After a round that does not decide the match, everybody still on the map is moved to the war room about 18.65 s
# after the round is won. Measured on 8,388 such exits in 1,660 rounds (Dyson and Combustion alike, 2023 and 2026 the
# same): the first player of a round leaves at 18.64 s (median), half of all exits fall between 18.65 and 18.72 s,
# 98 % between 18.55 and 20.0 s, the last at 21.5 s. The spread is the recording, not the game: replays hold 20 to
# 30 frames a second (0.03-0.05 s a frame, for the round's end and for the exit), and the players of one round leave
# within 0.1 s of each other. Those moves were counted as deaths: 3.7 to 5.2 a round, about 7 % of all deaths on
# Dyson (user, 2026-11-11). A death between these two moments after such a round is that move. The window is wide
# Dyson (user, 2026-11-11).
# The move is told by what it is, not by the clock alone (user, 2026-11-11: "the widest margin for error, but only
# when everyone teleports"): somewhere in ROUND_MOVE_WINDOW_S after such a round the map empties - the number of
# players on it drops to none and stays none for ROUND_MOVE_EMPTY_S. The deaths that emptied it are the move: the
# last one, and before it every death that follows the next within ROUND_MOVE_CHAIN_S (the players of one round
# leave within 0.1 s of each other, 1.1 s in 99 % of rounds; a straggler up to 2.8 s behind was seen and is still
# part of it). A death in the
# window that leaves others on the map is a real one and stays, as does the fight that goes on for some 7 s after
# a round is won and the players coming back from 30.8 s on. Payload maps have no such move: a run is one round.
ROUND_MOVE_WINDOW_S = (8.0, 30.0)  # after the round is won: from the end of the fight to just before players come back
ROUND_MOVE_EMPTY_S = 3.0
ROUND_MOVE_CHAIN_S = 3.0
# "Everybody" is everybody who is playing: a player whose head has not moved at all for this long has dropped out
# and is left standing where they were (seen: one stood in the middle of Dyson through the move while the other
# three were moved). They are not on the map for this count.
ROUND_MOVE_FROZEN_S = 5.0

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


def _round_move(events: list[EventRecord], frame_times: list[float], on_map: list[int], won_s: float) -> list[EventRecord]:
    """The death events that are everybody being moved to the war room after the round won at `won_s`: [] when the
    map does not empty in the window (ROUND_MOVE_WINDOW_S and the comment above it)."""
    start = bisect_left(frame_times, won_s + ROUND_MOVE_WINDOW_S[0])
    stop = bisect_right(frame_times, won_s + ROUND_MOVE_WINDOW_S[1])
    for i in range(max(start, 1), stop):
        if on_map[i] or not on_map[i - 1]:
            continue  # not the frame the last player left in
        until = bisect_right(frame_times, frame_times[i] + ROUND_MOVE_EMPTY_S)
        if any(on_map[i:until]):
            continue  # somebody was back at once: the map did not empty for good
        deaths = [e for e in events if e.type == "death_est" and won_s < e.t_s <= frame_times[i]]
        move, latest = [], frame_times[i]
        for e in reversed(deaths):  # the last ones, each within the chain of the one after it
            if latest - e.t_s > ROUND_MOVE_CHAIN_S:
                break
            move.append(e)
            latest = e.t_s
        return move
    return []


def _capture_point_winner(last: Frame) -> str | None:
    if last.blue_round_score == last.orange_round_score:
        return None
    return "blue" if last.blue_round_score > last.orange_round_score else "orange"


def compute(meta: ReplayMeta, frames: Iterable[Frame], recorder=None) -> MatchStats:
    """`recorder` (backend.tracks.TrackRecorder) optionally collects 2 Hz position tracks."""
    name = map_name(meta.map_code)
    bounds = BOUNDS.get(name)
    load_in = LOAD_IN_SPOTS.get(name)
    spawns = SPAWN_CIRCLES.get(name)
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
    frame_times: list[float] = []  # of every frame, seconds into the match, and how many players were on the map in
    on_map: list[int] = []  # it (in bounds): tells the moment everybody is moved to the war room after a round

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
        here, now_s = 0, (frame.timestamp - meta.started_at).total_seconds()
        for team, own, other in (("blue", frame.blue, frame.orange), ("orange", frame.orange, frame.blue)):
            for p in own:
                acc = players.get(p.user_id)
                if acc is None:
                    acc = players[p.user_id] = PlayerAccumulator(p.user_id, bounds, meta.started_at, events, load_in, spawns)
                    if frame.index > 0:
                        acc.team = team
                        acc.event(frame, "player_join")
                acc.add(frame, team, p, dt, own, other)
                here += acc._was_in_bounds is True and now_s - acc.moved_s < ROUND_MOVE_FROZEN_S
        frame_times.append(round(now_s, 3))
        on_map.append(here)
        prev = frame
        count += 1

    last = prev
    for acc in players.values():
        if acc.last_frame < last.index:
            t_s = round((acc.last_seen - meta.started_at).total_seconds(), 3)
            events.append(EventRecord(acc.last_frame, t_s, "player_leave", acc.user_id, acc.team))
    events.sort(key=lambda e: e.frame)
    end_frame = payload_end if has_payload else capture_end
    breaks = [(e.frame, e.t_s) for e in events if e.type == "round_won" and e.data
              and max(e.data.values()) < CAPTURE_ROUNDS_TO_WIN]

    moved = set()  # id() of the death events that are the move to the war room after a round
    for _, won_s in breaks:
        moved |= {id(e) for e in _round_move(events, frame_times, on_map, won_s)}

    def moved_on(e: EventRecord) -> bool:
        """Not a real death (or respawn): after the match is over, the players being moved on; and the deaths at the
        moment everybody is moved to the war room after a round."""
        if end_frame is not None and e.frame > end_frame:
            return True
        return id(e) in moved

    if end_frame is not None or breaks:
        late = Counter(e.user_id for e in events if e.type == "death_est" and moved_on(e))
        for user_id, n in late.items():
            players[user_id].deaths -= n
        events[:] = [e for e in events if not (e.type in ("death_est", "respawn") and moved_on(e))]

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
