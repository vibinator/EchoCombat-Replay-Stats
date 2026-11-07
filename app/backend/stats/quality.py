"""Which matches count for averages (user, 2026-11-07, Review DATA-3): a game of at least COUNTED_MIN_S with at least
COUNTED_MIN_PER_TEAM players on each team for half of it. Totals (games played, hours) still include every match;
averages, rates and win rates on profiles, trends, compare and the leaderboard use counted games only.

Stored per match (`matches.counted_for_stats`, 1 / 0; NULL = not decided yet, filled at startup by db.py for matches
saved before this column existed) so the aggregates stay one scan. Achievements keep their own, stricter rule
(4+ minutes, 3+ per team, achievements.py)."""

from sqlalchemy import case

COUNTED_MIN_S = 120.0
COUNTED_MIN_PER_TEAM = 2
PRESENT_SHARE = 0.5  # a player counts towards the team size when present for at least this share of the match

# SQL for matches saved before the column existed (same rule): run once at startup on NULL rows
BACKFILL_SQL = f"""
UPDATE matches SET counted_for_stats = CASE WHEN duration_s >= {COUNTED_MIN_S} AND id IN (
    SELECT match_id FROM (
        SELECT mp.match_id AS match_id, mp.team AS team, COUNT(*) AS n
        FROM match_players mp JOIN matches m ON m.id = mp.match_id
        WHERE mp.play_time_s >= {PRESENT_SHARE} * m.duration_s
        GROUP BY mp.match_id, mp.team
    ) GROUP BY match_id HAVING COUNT(*) = 2 AND MIN(n) >= {COUNTED_MIN_PER_TEAM}
) THEN 1 ELSE 0 END WHERE counted_for_stats IS NULL
"""


def counted_for_stats(duration_s: float, players) -> bool:
    """`players`: anything with `.team` and `.play_time_s` (stats.results.PlayerStats)."""
    if duration_s < COUNTED_MIN_S:
        return False
    sizes: dict[str, int] = {}
    for p in players:
        if p.play_time_s >= PRESENT_SHARE * duration_s:
            sizes[p.team] = sizes.get(p.team, 0) + 1
    return sizes.get("blue", 0) >= COUNTED_MIN_PER_TEAM and sizes.get("orange", 0) >= COUNTED_MIN_PER_TEAM


def only_counted(match_table, expr, strict: bool):
    """`expr` summed over counted matches only (strict), or over every match (tests, or the rule switched off)."""
    return case((match_table.counted_for_stats == 1, expr), else_=0) if strict else expr


def rule_text() -> str:
    return (f"games of {COUNTED_MIN_S / 60:.0f}+ minutes with {COUNTED_MIN_PER_TEAM}+ players per team for at least half of the game")
