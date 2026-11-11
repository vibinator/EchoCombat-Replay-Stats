"""Frames -> MatchStats in a single pass. No database imports."""

from collections import Counter
from collections.abc import Iterable

from parser import Frame, ReplayMeta

from .maps import BOUNDS, LOAD_IN_SPOTS, MAP_MODES, SPAWN_CIRCLES, map_name
from .payload import FINAL_CHECKPOINT, PayloadAccumulator
from .player import PlayerAccumulator
from .results import EventRecord, MatchStats, PlayerStats

STATS_VERSION = "16"  # 16: deaths are the game's own kill records where the recording has them (KILL_TO_EXIT_S); a payload run no longer ends when the game timer first reaches zero (overtime, the next checkpoint: its deaths were all dropped); nobody can be killed once a round is won (ROUND_OVER): after KILL_SHOWS_S no exit is a death until the next round, and the kills from just before the round that decides the match count again. 15: the move to the war room after a round that does not decide the match is not a death. 14: the spawn points are the measured ones (1.5 m, Dyson's two entry tubes too; its bounds reach x = +-110 for them). 13: leaving the play area from a spawn point (maps.SPAWN_CIRCLES) is not a death. 12: play-area bounds of Combustion, Surge and Fission had x and z swapped (maps.BOUNDS): deaths, in-bounds time and everything counted in bounds change on those maps. 11: ping_capped_sum (ping spikes capped at 400 ms in averages, DATA-5; in place, D57). 10: frames_lone_wolf_near (3.5 m, Lone Wolf). 9: no deaths / respawns after the capture match is decided or the payload run is over. 8: the map's load-in spot (maps.LOAD_IN_SPOTS) is no longer a death, in-bounds time or track sample

CAPTURE_ROUNDS_TO_WIN = 2  # best of three: the round that makes it 2 decides the match
# Once a round is won nobody can be killed (user, 2026-11-11), and the recorded API data bears it out: `last_kill`
# changes 0.87 times a round in the 10 s before a round is won and practically never after it. What the app counts
# as a death is the player leaving the map, and that comes after the kill: 6.6 s after it (median; 95 % within
# 6.8 s, the killed player lies where they fell first). So:
# - a death up to KILL_SHOWS_S after a round is won is a kill from just before it, and counts;
# - after that, a player leaving the map was not killed. About 18.65 s after the round everybody still on it is
#   moved to the war room (8,388 such exits in 1,660 rounds: half between 18.65 and 18.72 s), which was counted as
#   3.7 to 5.2 deaths a round, about 7 % of all deaths on Dyson; a few leave by themselves earlier or later;
# - after a round that does not decide the match this lasts until ROUND_BACK_S: the first players are back on the
#   map 30.8 s after the round was won, and the next round is on. After the round that decides the match (or the
#   end of a payload run) it lasts to the end of the recording.
# The round's end is the round score in the API data going up (blue_round_score / orange_round_score), the end of
# a payload run its last checkpoint or the game timer reaching zero: no clock of the app's own.
KILL_SHOWS_S = 8.0
ROUND_BACK_S = 30.0

# Recordings from 2026-11-04 on carry the game's own record of the latest kill (Frame.last_kill). Where a replay has
# it, a death is a kill (user, 2026-11-11: "if the new data makes current / future matches more accurate, build
# this out"); older replays keep the estimate above, the only thing they have. Measured on 100 matches, 2,353 kills
# against 2,441 estimated deaths: 96 % of the kills had their estimated death, always 6.5 to 6.95 s later (median
# 6.67 s: the killed player lies where they fell, then is moved out); 3 % of the estimated deaths were no kill at
# all (somebody leaving the map another way), and 4 % of the kills had no estimated death (the recording ended
# first, or the exit was not seen).
# The record only says who was killed last, by whom and with what: the same player killed again by the same player
# with the same weapon leaves it unchanged, so that kill does not show (4 % of all deaths in those matches). Those
# are taken from the estimate: a player leaving the map with no kill of theirs KILL_TO_EXIT_S before, while the
# standing record names them, was killed again.
KILL_TO_EXIT_S = (6.0, 7.5)  # an exit this long after a kill of the same player is that kill
KILL_TO_EXIT_TYPICAL_S = 6.67

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


def _kill(frame: Frame, t_s: float):
    """(frame, seconds, killed user id, killer user id, weapon, where the killed player is) of the kill the frame's
    last_kill has just changed to. A player is named by name or as "playerid:<n>" (the slot in the low 16 bits);
    None when nobody in the frame answers to it."""
    everyone = frame.blue + frame.orange

    def who(text: str):
        if text.startswith("playerid:") and text[9:].isdigit():
            slot = int(text[9:]) & 0xFFFF
            return next((p for p in everyone if p.slot == slot), None)
        return next((p for p in everyone if p.name == text), None)

    killed, killer, weapon = frame.last_kill
    victim, by = who(killed), who(killer)
    spot = (victim.head_position[0], victim.head_position[2]) if victim else None
    return frame.index, round(t_s, 3), victim.user_id if victim else None, by.user_id if by else None, weapon, spot


def _deaths_from_kills(events: list[EventRecord], kills: list, players: dict) -> None:
    """Replace the estimated deaths (players leaving the map) by the game's kills (the comment at KILL_TO_EXIT_S):
    one death for every kill, where the killed player was, with the killer and the weapon; an estimated death stays
    only when it must be a kill the record could not show."""
    estimated = [e for e in events if e.type == "death_est"]
    deaths: list[EventRecord] = []
    for frame, t_s, victim, killer, weapon, spot in kills:
        if victim is None or victim not in players:
            continue  # nobody in that frame answers to the name: a player who dropped out of the match at that
            # very moment (the game writes a kill for it; 43 of 2,353 kills, 33 of them never came back). Not a death
        data = {"x": round(spot[0], 2), "z": round(spot[1], 2), "with": weapon}
        if killer:
            data["by"] = killer
        deaths.append(EventRecord(frame, t_s, "death_est", victim, players[victim].team, data))
    for e in estimated:
        mine = [t for _, t, victim, *_ in kills if victim == e.user_id]
        if any(KILL_TO_EXIT_S[0] <= e.t_s - t <= KILL_TO_EXIT_S[1] for t in mine):
            continue  # this exit is one of the kills above
        before = [victim for _, t, victim, *_ in kills if t <= e.t_s - KILL_TO_EXIT_TYPICAL_S]
        if before and before[-1] == e.user_id:  # the record still names them: killed again the same way
            deaths.append(EventRecord(e.frame, e.t_s, "death_est", e.user_id, e.team, {**(e.data or {}), "repeat": True}))
    events[:] = [e for e in events if e.type != "death_est"] + deaths
    events.sort(key=lambda e: e.frame)
    counts = Counter(e.user_id for e in deaths)
    for user_id, acc in players.items():
        acc.deaths = counts.get(user_id, 0)


def _capture_point_winner(last: Frame) -> str | None:
    if last.blue_round_score == last.orange_round_score:
        return None
    return "blue" if last.blue_round_score > last.orange_round_score else "orange"


def compute(meta: ReplayMeta, frames: Iterable[Frame], recorder=None, use_kills: bool = True) -> MatchStats:
    """`recorder` (backend.tracks.TrackRecorder) optionally collects 2 Hz position tracks. `use_kills=False`: deaths
    by the estimate even when the recording has the game's kill records (app/tools/check_deaths.py compares the two)."""
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
    end_s = None  # when that was, seconds into the match
    # A payload run is over at its last checkpoint, or when the attackers fail: the last frame a timer was running in.
    # Not the first time the game timer reaches zero (the rule until 2026-11-11): overtime follows while the
    # attackers hold on, and a checkpoint reached in it sets the timer to 120 s again and the run goes on. That rule
    # threw away every death after that moment: about a fifth of the kills in the API data of 50 recent matches.
    live_frame = live_s = None
    kills: list[tuple[int, float, str | None, str | None, str, tuple[float, float] | None]] = []  # _kill, in order
    standing: tuple[str, str, str] | None = None  # last_kill of the previous frame
    has_kills = False  # the recording carries last_kill

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
        now_s = (frame.timestamp - meta.started_at).total_seconds()
        if capture_end is None and max(frame.blue_round_score, frame.orange_round_score) >= CAPTURE_ROUNDS_TO_WIN:
            capture_end = frame.index
            end_s = end_s if has_payload else now_s
        if payload_end is None and frame.payload is not None:
            if frame.payload.checkpoint >= FINAL_CHECKPOINT:
                payload_end = frame.index
                end_s = now_s
            elif (frame.game_timer or 0) > 0 or (frame.overtime_timer or 0) > 0:
                live_frame, live_s = frame.index, now_s  # the run is on: a timer is running
        match_events.add(frame)
        payload.add(frame, dt)
        if frame.last_kill is not None:
            if has_kills and frame.last_kill != standing and frame.last_kill[0]:
                kills.append(_kill(frame, now_s))
            has_kills, standing = True, frame.last_kill
        for team, own, other in (("blue", frame.blue, frame.orange), ("orange", frame.orange, frame.blue)):
            for p in own:
                acc = players.get(p.user_id)
                if acc is None:
                    acc = players[p.user_id] = PlayerAccumulator(p.user_id, bounds, meta.started_at, events, load_in, spawns)
                    if frame.index > 0:
                        acc.team = team
                        acc.event(frame, "player_join")
                acc.add(frame, team, p, dt, own, other)
        prev = frame
        count += 1

    last = prev
    if has_payload and payload_end is None and live_frame is not None and live_frame < last.index:
        payload_end, end_s = live_frame, live_s  # the timers stopped and the recording went on: the attackers failed
    for acc in players.values():
        if acc.last_frame < last.index:
            t_s = round((acc.last_seen - meta.started_at).total_seconds(), 3)
            events.append(EventRecord(acc.last_frame, t_s, "player_leave", acc.user_id, acc.team))
    events.sort(key=lambda e: e.frame)
    end_frame = payload_end if has_payload else capture_end
    breaks = [(e.frame, e.t_s) for e in events if e.type == "round_won" and e.data
              and max(e.data.values()) < CAPTURE_ROUNDS_TO_WIN]

    def not_killed(e: EventRecord) -> bool:
        """A death that is no kill: the player left the map after a round was over (the comment at KILL_SHOWS_S)."""
        if end_s is not None and e.frame > end_frame and e.t_s > end_s + KILL_SHOWS_S:
            return True
        return any(won_s + KILL_SHOWS_S < e.t_s <= won_s + ROUND_BACK_S for _, won_s in breaks)

    if end_frame is not None or breaks:
        late = Counter(e.user_id for e in events if e.type == "death_est" and not_killed(e))
        for user_id, n in late.items():
            players[user_id].deaths -= n
        # respawns after the match is over are the players being moved on, as before
        events[:] = [e for e in events if not ((e.type == "death_est" and not_killed(e))
                                                or (e.type == "respawn" and end_frame is not None and e.frame > end_frame))]
    if has_kills and use_kills:
        _deaths_from_kills(events, kills, players)

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
