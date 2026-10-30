"""Payload maps: attacking team, winner, per-player time on the payload (ReplayData "Payload semantics")."""

import math
from collections import Counter

from parser import Frame

ON_PAYLOAD_RADIUS_M = 3.0  # best match to the API's attackers/defenders counts in samples (92 % / 99 %)
FINAL_CHECKPOINT = 3  # track end


class PayloadAccumulator:
    """The attacking team is only known at the end, so time near the payload is kept per
    (user_id, team) twice: while the API counts attackers, and while it counts defenders."""

    def __init__(self):
        self.attacker_presence: Counter[str] = Counter()  # team -> player-frames near payload, attackers only
        self.near_while_attackers: Counter[tuple[str, str]] = Counter()
        self.near_while_defenders: Counter[tuple[str, str]] = Counter()

    def add(self, frame: Frame, dt: float) -> None:
        pl = frame.payload
        if pl is None or (pl.attackers == 0 and pl.defenders == 0):
            return
        for team, players in (("blue", frame.blue), ("orange", frame.orange)):
            for p in players:
                if math.dist(p.head_position, pl.position) >= ON_PAYLOAD_RADIUS_M:
                    continue
                key = (p.user_id, team)
                if pl.attackers:
                    self.near_while_attackers[key] += dt
                    if not pl.defenders:
                        self.attacker_presence[team] += 1
                if pl.defenders:
                    self.near_while_defenders[key] += dt

    def attacking_team(self) -> str | None:
        if not self.attacker_presence:
            return None
        return self.attacker_presence.most_common(1)[0][0]

    def winner(self, last: Frame) -> str | None:
        attacking = self.attacking_team()
        if attacking is None or last.payload is None:
            return None
        if last.payload.checkpoint >= FINAL_CHECKPOINT:
            return attacking
        if last.game_timer is not None and last.game_timer <= 0:
            return _other(attacking)
        return None  # recording stopped before the end

    def push_block(self, user_id: str) -> tuple[float, float]:
        """(seconds pushing as attacker, seconds blocking as defender); 0 when no side is known."""
        attacking = self.attacking_team()
        if attacking is None:
            return 0.0, 0.0
        push = self.near_while_attackers.get((user_id, attacking), 0.0)
        block = self.near_while_defenders.get((user_id, _other(attacking)), 0.0)
        return round(push, 3), round(block, 3)


def _other(team: str) -> str:
    return "orange" if team == "blue" else "blue"
