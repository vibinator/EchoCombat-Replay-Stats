"""Achievements (D17): 5-79 from the old ECRanked stat.js comments, thresholds from the rule text; 80+ are new
(user, 2026-10-30), built on data the old site never used: unreleased gear, results, payload push / block, emotes.
Progress = the best value ever reached (old app only ever raised progress): best game, best calendar
day (recorder-local), best rolling 7 days (any 7-day window, Beta 69), or the all-time total. The logic follows the description shown
on the website (user, 2026-10-30): every condition a rule applies is in its text. Computed from stored match
stats on request; nothing is stored. Tiers (user, 2026-10-30): white 25 %, bronze 50 %, silver 75 %, gold 100 %."""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from functools import cached_property

from . import gear

WEAPONS = [("assault", "Pulsar", "pulsar"), ("blaster", "Nova", "nova"), ("scout", "Comet", "comet"), ("rocket", "Meteor", "meteor")]
ORDNANCES = [("det", "Detonator", "detonator"), ("stun", "Stun Field", "stun_field"), ("arc", "Arc Mine", "arcmine"), ("burst", "Instant Repair", "instant_repair")]
TACMODS = [("heal", "Repair Matrix", "repair_matrix"), ("sensor", "Threat Scanner", "threat_scanner"), ("shield", "Energy Barrier", "energy_barrier"), ("wraith", "Phase Shift", "phaseshift")]
SLOTS = {"weapon": 0, "tacmod": 1, "ordnance": 2}  # index into the (weapon, tacmod, ordnance) loadout key
# Unreleased gear seen in recent replays. Attack Drone, Umbral Veil and Neutron are left out: each appears in 35
# games or fewer in the 2026 archive and in none of the 30-31 Oct 2026 replays. Overcharge got a low target (112).
MEDAL_LEVELS = (5, 10, 25, 50, 75)  # Medal Collector: gold-or-better medals held; archive: 36 % bronze, 20 % silver, 11 % gold, 5 % diamond, 1 % platinum
MAPS = ("dyson", "combustion", "fission", "surge")
UNRELEASED_WEAPONS = [("rifle", "Starburst"), ("magnum", "Protostar"), ("smg", "Quark"), ("chain", "Blazar")]
# Badge art for the gear released 2026-10-30 (made from the loadout icons in public/icons). Dot Field and Overcharge
# have no art yet: they keep the generic icon (an admin can pick or upload one on the Console page).
GEAR_ICONS = {"rifle": "starburst", "magnum": "protostar", "smg": "quark", "chain": "blazar", "loc": "translocator"}

ONLY_SHARE = 0.90  # "use only X": X is at least 90 % of the game's loadout time (was 95; user, 2026-11-04: room for mistakes)
USED_SHARE = 0.10  # below 10 % of the game does not count as "used" (was 5 %, the old loadoutCutoff; user, 2026-11-04)
FULL_GAME_S = 240.0  # was 180 (user, 2026-11-04); per-game rules ignore short appearances (A: avoids 0-death 10-second games)
LOADOUT_USED_S = 60.0  # "different loadouts": at least 1 min each (was 3 min; user, 2026-11-04: more achievable)
SEASON_MIN_GAMES = 50  # all-time averages need 50 games (A)
SPEED_MIN_GAMES = 25  # Cyberkinetic Enhancements: 50 left 76 % of the active players out (user, 2026-10-31)
# One ladder per kind of gear challenge, the same for every weapon, ordnance and tac mod, new gear included (user,
# 2026-11-03). Set from the most-used gear (Pulsar, ~110k games in the archive): 500 games was out of reach in the last 500.
GEAR_VETERAN = (6, 17, 55, 170, 400)  # games using it
GEAR_DAY = (3, 6, 9, 13, 17)  # "only X" games in one day (finals 3 / 5 / 8 / 16 / 20; eased 2026-11-03 from the 1-3 Nov games)
GEAR_WEEK = (6, 12, 18, 35, 55)  # "only X" games in any 7 days
TIERS = [(1.0, "gold"), (0.75, "silver"), (0.5, "bronze"), (0.25, "white")]


@dataclass
class Game:
    """One match of one player, as needed by the rules."""

    started_at: str
    map: str
    mode: str
    private: bool
    play_time_s: float
    deaths: int
    in_bounds: int
    near_mate: int
    near_enemy: int
    upside: int
    speed_sum: float
    top_speed: float
    frame_rate: float
    loadouts: dict[tuple[str, str, str], int] = field(default_factory=dict)  # (weapon, tacmod, ordnance) -> frames
    # used by the new challenges (80+)
    team: str = ""
    winner: str | None = None  # None = no result (recording ended early)
    attacking_team: str | None = None  # payload only
    rounds_lost: int = 0  # capture point: rounds won by the other team
    push_s: float = 0.0
    block_s: float = 0.0
    emotes: int = 0
    stopped: int = 0  # in-bounds frames standing still
    left_arm: int = 0
    right_arm: int = 0
    capture_s: float = 0.0  # capture point: time the player's team's progress was rising
    contested_s: float = 0.0
    enough_players: bool = True  # both teams had at least 3 players for at least half of the match (3v3, 3v4, 4v4, 5v5 ... all fine); one-game, win and Payload challenges need it (user, 2026-11-04)

    @property
    def won(self) -> bool:
        return self.winner is not None and self.winner == self.team

    @cached_property
    def day(self) -> date:
        return date.fromisoformat(self.started_at[:10])

    @cached_property
    def start_dt(self) -> datetime:
        return datetime.fromisoformat(self.started_at)

    @cached_property
    def week(self) -> date:  # calendar week: only "Number of different weeks you played" uses it
        return self.day - timedelta(days=self.day.weekday())

    @cached_property
    def _shares(self) -> dict[str, dict[str, float]]:
        """slot -> code -> share of loadout time (computed once; rules ask hundreds of times)."""
        frames: dict[str, dict[str, int]] = {slot: {} for slot in SLOTS}  # plain dicts: built for every game
        for key, n in self.loadouts.items():
            for slot, i in SLOTS.items():
                counts = frames[slot]
                counts[key[i]] = counts.get(key[i], 0) + n
        total = sum(self.loadouts.values())
        return {slot: {c: n / total for c, n in counts.items()} if total else {} for slot, counts in frames.items()}

    @cached_property
    def _only(self) -> dict[str, frozenset[str]]:
        """slot -> codes that are at least ONLY_SHARE of the game's loadout time ("use only")."""
        return {slot: frozenset(c for c, v in shares.items() if c and v >= ONLY_SHARE) for slot, shares in self._shares.items()}

    def share(self, slot: str, code: str) -> float:
        return self._shares[slot].get(code, 0.0)

    def seconds_used(self, slot: str, code: str) -> float:
        """Time the item was equipped, by the game clock: its share of the game x time played. Loadout frames alone only cover
        time on the map, about 60 % of play time (the wait to respawn is left out)."""
        return self.share(slot, code) * self.play_time_s

    @cached_property
    def _used(self) -> dict[str, frozenset[str]]:
        return {slot: frozenset(c for c, v in shares.items() if c and v >= USED_SHARE) for slot, shares in self._shares.items()}

    def used(self, slot: str) -> frozenset[str]:
        return self._used[slot]

    def loadouts_played(self) -> int:
        """Different loadout combinations that were at least USED_SHARE of the game."""
        total = sum(self.loadouts.values())
        return sum(1 for n in self.loadouts.values() if total and n / total >= USED_SHARE)

    def main_loadout(self) -> tuple[str, str, str] | None:
        total = sum(self.loadouts.values())
        if not total:
            return None
        key, n = max(self.loadouts.items(), key=lambda kv: kv[1])
        return key if n / total >= ONLY_SHARE else None


@dataclass(frozen=True)
class Rule:
    id: int
    name: str
    description: str
    period: str  # game | day | week | all
    icon: str | None  # base name in app/images; daily / weekly variants added by period
    score: Callable[[list[Game]], float]  # games of one period -> progress (0..1+)
    estimated: bool = False
    new: bool = False  # not on the original ECRanked site
    group: str | None = None  # theme of a new rule (its own section on the website)
    # Tiered (progression) rules: all-time count targets for bronze, silver, gold, diamond, platinum (LEVELS).
    # The medal is the highest target reached instead of the percentage tiers; platinum = completed.
    levels: tuple[float, ...] = ()
    count: Callable[[list[Game]], float] | None = None  # per period group; the best group counts
    unit: str = ""  # shown after each target ("%", " m/s", " min")
    meta: bool = False  # Medal Collector: counts the medals of the other rules
    prize: str = ""  # Mega Prize (in-game item) for completing it; shown on the site, handed out outside the app
    counted: bool = True  # False: the Combat achievements (combat_achievements.py), not in RULES and out of every total


# Tiered rules (user, 2026-10-31): almost every rule is a ladder. Order (user, 2026-10-31): bronze, silver, gold, diamond, platinum (platinum is the top medal).
LEVELS = ("bronze", "silver", "gold", "diamond", "platinum")


def _levelled(count, levels: tuple[float, ...]):
    """Progress spread evenly over the medals: bronze 20 %, silver 40 %, ... platinum 100 %, partial in between."""
    def score(games):
        n, prev = count(games), 0
        for i, need in enumerate(levels):
            if n < need:
                return (i + (n - prev) / (need - prev)) / len(levels)
            prev = need
        return 1.0
    return score


def level_tier(n: float, levels: tuple[float, ...]) -> str | None:
    reached = sum(n >= need for need in levels)
    return LEVELS[reached - 1] if reached else None


def unlock_threshold(rule: "Rule") -> float:
    """Progress at which a rule counts as unlocked (rarity): the first medal."""
    return 1 / len(rule.levels) if rule.levels else TIERS[-1][0]


def _num(n: float) -> str:
    return f"{n:g}"


HARDER_TOP = 1.3  # diamond and platinum need 30 % more than the targets written below (user, 2026-11-03)


def _harder(levels: tuple[float, ...], unit: str) -> tuple[float, ...]:
    """Diamond and platinum (the last two targets) x HARDER_TOP. A percentage cannot pass 100: it only closes 30 % of
    the way to 100 when that is less. Whole-number targets stay whole and always rise by at least one step."""
    whole = all(float(v).is_integer() for v in levels)
    out = list(levels)
    for i in (3, 4):
        v = levels[i] * HARDER_TOP
        if unit == "%":
            v = min(v, levels[i] + 0.3 * (100 - levels[i]))
        v = float(int(v + 0.5)) if whole else round(v, 1)
        out[i] = max(v, out[i - 1] + (1 if whole else 0.1))
    return tuple(int(v) if whole else v for v in out)


ALL_TIME_RAISE = 1.2  # all-time count ladders need 20 % more than the targets written below (user, 2026-11-04; to be reviewed)


def _all_time(levels: tuple[float, ...], unit: str) -> tuple[float, ...]:
    """All-time count ladders x ALL_TIME_RAISE, before _harder. Averages (% and m/s) are left alone: they are not counts and
    would become unreachable. Whole-number targets stay whole and always rise by at least one step."""
    if unit in ("%", " m/s"):
        return levels
    whole = all(float(v).is_integer() for v in levels)
    out: list[float] = []
    for v in levels:
        v = float(int(v * ALL_TIME_RAISE + 0.5)) if whole else round(v * ALL_TIME_RAISE, 1)
        out.append(max(v, out[-1] + (1 if whole else 0.1)) if out else v)
    return tuple(int(v) if whole else v for v in out)


PLATINUM_EASIER = 0.9  # gear Veteran ladders (every weapon, ordnance and tac mod): platinum needs 10 % less than after _harder (user, 2026-11-04)


def _easier_platinum(levels: tuple[float, ...]) -> tuple[float, ...]:
    """Platinum (last target) x PLATINUM_EASIER, still above diamond. Whole-number targets stay whole."""
    whole = all(float(v).is_integer() for v in levels)
    v = levels[4] * PLATINUM_EASIER
    v = float(int(v + 0.5)) if whole else round(v, 1)
    v = max(v, levels[3] + (1 if whole else 0.1))
    return tuple(int(x) if whole else x for x in (*levels[:4], v))


VETERAN_HARDER = 1.32  # gear Veteran ladders (every weapon, ordnance and tac mod): every tier needs 20 % more, then another 10 % (1.2 x 1.1), after the steps above (user, 2026-11-04)


VETERAN_TOP = (115, 150)  # gear Veteran diamond and platinum: all 18 platinums = ~1,200 weapon games (was 260 = ~2,100), so completing every gear Veteran is possible; platinum is reachable for well over 10 % of active players in 3 months (user, 2026-11-04; from the 31 Oct-3 Nov pace)


def _scaled(levels: tuple[float, ...], factor: float) -> tuple[float, ...]:
    """Every target x factor, whole numbers stay whole and strictly ascending."""
    out: list[int] = []
    for v in levels:
        v = int(v * factor + 0.5)
        out.append(max(v, out[-1] + 1) if out else v)
    return tuple(out)


# Platinum for about 5 % of the active players (user, 2026-11-04). Measured on the whole archive (1,885 players with 10+ games):
# bronze / silver / gold / diamond / platinum are what 40 / 20 / 12 / 7.5 / 5 % of them reached. Every weapon, ordnance and tac mod
# has the same ladder per kind of challenge (Veteran, "only X" in a day, "only X" in 7 days). Replaces the written targets of the
# ladders below: those whose platinum was over 2 % before, and all the gear ladders together. The others keep their written targets.
TUNED_LEVELS: dict[int, tuple[float, ...]] = {
    5: (1, 3, 4, 5, 7),  # One with the Pulsar
    6: (1, 3, 4, 5, 7),  # One with the Nova
    7: (1, 3, 4, 5, 7),  # One with the Comet
    8: (1, 3, 4, 5, 7),  # One with the Meteor
    9: (1, 3, 4, 5, 7),  # Yeet and Delete
    10: (1, 3, 4, 5, 7),  # Ride the Lightning
    11: (1, 3, 4, 5, 7),  # Paralyzer
    12: (1, 3, 4, 5, 7),  # RAD_DavidN Heal Us w/5th Map
    13: (1, 3, 4, 5, 7),  # Damage Control
    14: (1, 3, 4, 5, 7),  # Search and Destroy
    15: (1, 3, 4, 5, 7),  # n00b Protector 9000
    16: (1, 3, 4, 5, 7),  # Wraith
    18: (2, 5, 8, 15, 23),  # My Other Chassis Is a Toaster
    21: (50, 61, 69, 74, 81),  # Full Team Salvo
    22: (26, 34, 42, 51, 60),  # Can We Talk About This?
    24: (15, 35, 52, 66, 78),  # I’m Bat Bot (eased 2026-11-04, user; was 19/43/61/78/89)
    30: (1, 4, 6, 9, 13),  # Pulse Check
    31: (1, 4, 6, 9, 13),  # Eat My Nova!
    32: (1, 4, 6, 9, 13),  # Silicon Assassin
    33: (1, 4, 6, 9, 13),  # I Came to Drop Bombs
    34: (1, 4, 6, 9, 13),  # Throws Better Than an Arena Disc
    35: (1, 4, 6, 9, 13),  # Don't Taze Me Bro Bot
    36: (1, 4, 6, 9, 13),  # Electroshock Therapy
    37: (1, 4, 6, 9, 13),  # Fully Juiced
    38: (1, 4, 6, 9, 13),  # Built to Last
    39: (1, 4, 6, 9, 13),  # X-Ray Vision Implant Upgrade
    40: (1, 4, 6, 9, 13),  # Check Out My Cool Screensaver
    41: (1, 4, 6, 9, 13),  # Ghost in the Shell
    46: (32, 42, 49, 53, 58),  # Tech Support w/RAD_Natalie
    47: (18, 24, 28, 33, 40),  # Hug Your Frenemy
    49: (9.3, 22, 36, 47, 57),  # I’ɯ ꓭɐʇ ꓭoʇ
    55: (5, 11, 19, 29, 49),  # Pulsar Veteran
    56: (5, 11, 19, 29, 49),  # Nova Veteran
    57: (5, 11, 19, 29, 49),  # Comet Veteran
    58: (5, 11, 19, 29, 49),  # Meteor Veteran
    59: (5, 11, 19, 29, 49),  # Detonator Veteran
    60: (5, 11, 19, 29, 49),  # Stun Field Veteran
    61: (5, 11, 19, 29, 49),  # Arc Mine Veteran
    62: (5, 11, 19, 29, 49),  # Instant Repair Veteran
    63: (5, 11, 19, 29, 49),  # Repair Matrix Veteran
    64: (5, 11, 19, 29, 49),  # Threat Scanner Veteran
    65: (5, 11, 19, 29, 49),  # Energy Barrier Veteran
    66: (5, 11, 19, 29, 49),  # Phase Shift Veteran
    68: (205, 440, 810, 1460, 2470),  # Pixel Party!
    69: (14, 30, 54, 95, 165),  # King of the Hill
    70: (14, 29, 51, 90, 155),  # Feed the Flamingo
    75: (8, 16, 27, 50, 80),  # Brute Force Attack
    76: (7, 15, 26, 49, 80),  # Molten Mechanical Mayhem
    77: (7, 15, 26, 45, 80),  # George and I Go Way Back
    78: (7, 15, 26, 46, 75),  # Good ol' George
    79: (28, 60, 105, 190, 320),  # King/Queen of Pubs
    90: (3, 4, 5, 6, 7),  # On a Roll
    96: (112, 160, 182, 198, 207),  # Pedal to the Metal
    97: (22, 44, 60, 73, 84),  # Immovable Object
    98: (3.3, 8.6, 15, 25, 46),  # Freight Train
    101: (1, 3, 4, 5, 7),  # Starburst Stream
    102: (1, 3, 4, 5, 7),  # Protostar Power Trip
    103: (1, 3, 4, 5, 7),  # Quark Storm
    104: (1, 3, 4, 5, 7),  # Here, There and Everywhere
    105: (5, 11, 19, 29, 49),  # Starburst Veteran
    106: (5, 11, 19, 29, 49),  # Protostar Veteran
    107: (5, 11, 19, 29, 49),  # Quark Veteran
    108: (5, 11, 19, 29, 49),  # Translocator Veteran
    112: (5, 11, 19, 29, 49),  # Overclocked
    113: (28, 60, 105, 190, 320),  # Frequent Flyer
    114: (10, 19, 31, 47, 75),  # Regular
    115: (6, 11, 16, 23, 32),  # Loyal Bot
    117: (3.5, 7.7, 14, 26, 43),  # Time Well Wasted
    122: (1, 2, 3, 7, 12),  # Grand Tour
    127: (1, 4, 6, 9, 13),  # Star Power
    128: (1, 4, 6, 9, 13),  # Protostar Powerhouse
    129: (1, 4, 6, 9, 13),  # Quark Quake
    130: (1, 4, 6, 9, 13),  # Blink and You'll Miss It
    131: (1, 3, 4, 5, 7),  # Full Charge
    132: (1, 4, 6, 9, 13),  # Charged Up
    133: (5, 11, 19, 29, 49),  # Blazar Veteran
    134: (5, 11, 19, 29, 49),  # Dot Field Veteran
    135: (1, 3, 4, 5, 7),  # Blazing Trail
    136: (1, 3, 4, 5, 7),  # Dot to Dot
    137: (1, 4, 6, 9, 13),  # Blazar Barrage
    138: (1, 4, 6, 9, 13),  # Dot Matrix
    142: (45, 54, 61, 67, 73),  # Statue (eased 2026-11-04, user; was 59/67/73/79/85)
    143: (94.6, 96.4, 98.2, 99.1, 100),  # Lone Wolf (a share of one game: it cannot pass 100; most players are above 95, so it is easy on purpose; user, 2026-11-04)
    148: (2, 6, 12, 22, 38),  # One-Trick Pony
}


def _ladder(id_: int, name: str, what: str, icon: str | None, count, levels: tuple[float, ...], period: str = "all",
            unit: str = "", raise_all_time: bool = True, **kw) -> "Rule":
    """A medal ladder: `count` is evaluated per period group (game / day / week / all time); the best group counts.
    The text lists every target. All-time count ladders are raised by _all_time; diamond and platinum are made harder by
    _harder, then platinum of the gear Veteran ladders is eased by _easier_platinum. The Mega Prize ladder and Medal Collector (meta) keep their written targets."""
    gear_veteran = levels == GEAR_VETERAN  # one ladder for all gear, so one platinum target for all gear
    if period == "all" and raise_all_time and not kw.get("meta"):
        levels = _all_time(levels, unit)
    levels = _harder(levels, unit)
    if gear_veteran:
        levels = (*_scaled(_easier_platinum(levels), VETERAN_HARDER)[:3], *VETERAN_TOP)
    targets = ", ".join(f"{_num(n)}{unit} {medal}" for n, medal in zip(levels, LEVELS))
    return Rule(id_, name, f"{what} ({targets})", period, icon, _levelled(count, levels), levels=levels, count=count,
                unit=unit, **kw)


def _tiered(id_: int, name: str, what: str, icon: str | None, pred, levels: tuple[float, ...], period: str = "all", **kw) -> "Rule":
    """Ladder over the number of games matching `pred`."""
    return _ladder(id_, name, what, icon, lambda games: sum(1 for g in games if pred(g)), levels, period, **kw)


def clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def ratio(num: float, den: float) -> float:
    return num / den if den else 0.0


def _only(slot: str, code: str, need: int):
    def only(games):
        return sum(1 for g in games if g.share(slot, code) >= ONLY_SHARE) / need
    only.use_only = True
    return only


def _count(pred, need: int):
    return lambda games: sum(1 for g in games if pred(g)) / need


class _AvgValue:
    """100 x sum(attr) / in-bounds frames over the games (percent), or sum(attr) / frames when scale is 1 (speed).
    0 until min_games games (all-time averages ramp: 50+ games)."""

    def __init__(self, attr: str, scale: float = 100.0, min_games: int = 0):
        self.attr, self.scale, self.min_games = attr, scale, min_games

    def _value(self, total: float, frames: int, n: int) -> float:
        return round(self.scale * ratio(total, frames), 6) if n >= self.min_games else 0.0

    def __call__(self, games) -> float:
        return self._value(sum(getattr(g, self.attr) for g in games), sum(g.in_bounds for g in games), len(games))

    def first_reached(self, ordered: list, need: float) -> int | None:
        """Index of the game at which the running average first reached `need` (it can drop again later, so the
        binary search used for counts does not apply)."""
        total = frames = 0
        for i, g in enumerate(ordered):
            total += getattr(g, self.attr)
            frames += g.in_bounds
            if self._value(total, frames, i + 1) >= need:
                return i
        return None


def _full(value):
    """Per-game rules: only games played at least FULL_GAME_S."""
    def full(games):
        return value(games) if games and games[0].play_time_s >= FULL_GAME_S else 0.0
    full.min_length = True  # shown as a rule note
    return full


def _gearhead_run(games):
    """Longest run of consecutive games on one single loadout."""
    best = run = 0
    prev = None
    for g in sorted(games, key=lambda g: g.started_at):
        key = g.main_loadout()
        run = run + 1 if key is not None and key == prev else (1 if key else 0)
        prev = key
        best = max(best, run)
    return best


PEW_PEW_MIN_S = FULL_GAME_S  # recordings shorter than this are ignored (4 min = half an average game; revisit, user 2026-11-04)
PEW_PEW_MAX_DEATHS = 5  # was 3 in the original text; raised by the user (2026-10-30)


def _pew_pew_proof(games):
    """Average fewer than PEW_PEW_MAX_DEATHS deaths per game over any 7 days with at least 25 games. Exactly the
    limit is not fewer: partial progress stays below 100 % until the average is under it. Recordings shorter than
    PEW_PEW_MIN_S are ignored: a spectator bot that joins late only sees the tail of a game, with few deaths."""
    games = [g for g in games if g.play_time_s >= PEW_PEW_MIN_S]
    if not games:
        return 0.0
    avg = sum(g.deaths for g in games) / len(games)
    limit = PEW_PEW_MAX_DEATHS
    return min(1.0, len(games) / 25) * (1.0 if avg < limit else min(limit / avg, 0.99))


TEST_DRIVE_S = 180.0
ONE_GAME_GEAR = "Gear in one game"  # new challenges shown under the "In one game" period, not a theme of their own


def _test_drive(slot: str, code: str):
    """Share of TEST_DRIVE_S that the item was used in one game with 3+ players per team."""
    def test_drive(games):
        g = games[0]
        return g.seconds_used(slot, code) / TEST_DRIVE_S if g.enough_players else 0.0
    test_drive.enough_players = True  # shown as a rule note
    return test_drive


def _released_gear() -> tuple[list[str], list[str], list[str]]:
    """(weapons, tac mods, ordnances) in use, the most played first (archive hours, 2026-11-04): 8 x 5 x 6 = 240 loadouts."""
    return (["assault", "scout", "blaster", "rocket", "rifle", "magnum", "smg", "chain"],
            ["heal", "wraith", "sensor", "shield", "buff"],
            ["det", "burst", "stun", "arc", "loc", "dot"])


def _loadouts_tried(games) -> set[tuple[str, str, str]]:
    """Released loadouts (weapon, tac mod, ordnance) played at least LOADOUT_USED_S in total."""
    seconds = Counter()
    for g in games:
        for key, frames in g.loadouts.items():
            seconds[key] += frames / (g.frame_rate or 20)
    gear = [set(x) for x in _released_gear()]
    return {k for k, s in seconds.items() if s >= LOADOUT_USED_S and all(k[i] in gear[i] for i in range(3))}


def _loadouts_used(games):
    """Different released loadouts (of 240: 8 weapons x 5 tac mods x 6 ordnances) played at least 1 minute in total."""
    return len(_loadouts_tried(games))


def loadouts_to_try(games, n: int = 3) -> list[dict]:
    """The `n` loadouts this player has not tried yet, made of the most played gear (so they are easy to find a game with)."""
    tried = _loadouts_tried(games)
    weapons, tacmods, ordnances = _released_gear()
    todo = sorted(((wi + ti + oi, w, t, o) for wi, w in enumerate(weapons) for ti, t in enumerate(tacmods) for oi, o in enumerate(ordnances)
                   if (w, t, o) not in tried))
    return [{"weapon": w, "tacmod": t, "ordnance": o,
             "label": " · ".join((gear.lookup(gear.WEAPONS, w).display_name, gear.lookup(gear.ORDNANCES, o).display_name, gear.lookup(gear.TACMODS, t).display_name))}
            for _, w, t, o in todo[:n]]


LOADOUT_RULE_ID = 67
RELEASED = {c for c, _, _ in WEAPONS + ORDNANCES + TACMODS}


def _equipables_used(games):
    used = set()
    for g in games:
        for slot in SLOTS:
            used |= g.used(slot)
    return len(used & RELEASED)


def _days_all_equipables(games):
    """Days (recorder-local calendar days) on which all 12 released equipables were used."""
    return sum(1 for day in _groups(games, "day") if _equipables_used(day) == 12)


def _games_using(slot: str, code: str):
    return lambda games: sum(1 for g in games if code in g._used[slot])


def _only_games(slot: str, code: str):
    def only_games(games):
        return sum(1 for g in games if code in g._only[slot])
    only_games.use_only = True  # shown as a rule note
    return only_games


def _all_used(slot: str, codes: set[str]):
    """Share of `codes` used (10%+ of a game) in these games."""
    return lambda games: len(set().union(*(g.used(slot) for g in games)) & codes) / len(codes)


def _win_streak(games):
    """Longest run of wins over games with a result (games without a result are skipped)."""
    best = run = 0
    for g in sorted(games, key=lambda g: g.started_at):
        if g.winner is None:
            continue
        run = run + 1 if g.won else 0
        best = max(best, run)
    return best


def _day_streak(games):
    """Longest run of consecutive calendar days with at least one game."""
    best = run = 0
    prev = None
    for day in sorted({g.day for g in games}):
        run = run + 1 if prev is not None and (day - prev).days == 1 else 1
        best, prev = max(best, run), day
    return best


def _fewest_wins(games):
    """Wins on the map where the player has the fewest (all four maps count)."""
    return min(sum(1 for g in games if g.map == m and g.won) for m in MAPS)


def _least_used(slot: str, items):
    return lambda games: min(sum(1 for g in games if code in g.used(slot)) for code, _, _ in items)


def _least_used_equipable(games):
    return min(_least_used(slot, items)(games) for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)))


def _v4(count):
    """Challenges that only count games with at least 3 players per team (was 4v4 only, user 2026-11-03; eased and widened 2026-11-04)."""
    def only_enough(games):
        games = [g for g in games if g.enough_players]
        return count(games) if games else 0.0
    only_enough.enough_players = True  # shown as a rule note
    only_enough.min_length = getattr(count, "min_length", False)
    return only_enough


def _away_from_mates(games):
    """% of the in-bounds time not near a teammate (4+ minute games only, see _full)."""
    return 100.0 - _pct("near_mate")(games) if games[0].in_bounds else 0.0


def _both_arms(games):
    g = games[0]
    return 1.0 if g.in_bounds and min(g.left_arm, g.right_arm) / g.in_bounds >= 0.4 else 0.0


def _capture(g):
    return g.mode == "capture_point"


def _payload(g):
    return g.mode == "payload"


def _pub(g):
    return not g.private


def _pct(attr: str) -> "_AvgValue":
    return _AvgValue(attr)


def _build_rules() -> list[Rule]:
    rules: list[Rule] = []
    # Daily (5-29): the most games in one calendar day
    names = {
        "assault": "One with the Pulsar", "blaster": "One with the Nova", "scout": "One with the Comet", "rocket": "One with the Meteor",
        "det": "Yeet and Delete", "stun": "Ride the Lightning", "arc": "Paralyzer", "burst": "RAD_DavidN Heal Us w/5th Map",
        "heal": "Damage Control", "sensor": "Search and Destroy", "shield": "n00b Protector 9000", "wraith": "Wraith",
    }
    i = 5
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, names[code], f"Play games using only {label} in one day", icon,
                                 _only_games(slot, code), GEAR_DAY, "day"))
            i += 1
    rules += [
        _ladder(17, "Versatile Bot", "Days on which you used all 12 items (4 weapons, 4 ordnances, 4 tac mods)", None, _days_all_equipables, (1, 2, 4, 8, 15)),
        _tiered(18, "My Other Chassis Is a Toaster", "Finish games with 3 deaths or fewer", "deaths",
                lambda g: g.play_time_s >= FULL_GAME_S and g.deaths <= 3, (1, 4, 7, 16, 24), estimated=True),
        _tiered(19, "Point Captured", "Play Capture Point games in one day", "capture_point", _capture, (5, 7, 9, 12, 17), "day"),
        _tiered(20, "Checkpoint Reached", "Play Payload games in one day", "payload", _payload, (5, 7, 9, 12, 17), "day"),
        _ladder(21, "Full Team Salvo", "Share of one game spent close to a teammate", "team_proximity",
                _full(_pct("near_mate")), (45, 55, 65, 80, 92), "game", "%"),
        _ladder(22, "Can We Talk About This?", "Share of one game spent close to an enemy", "enemy_proximity",
                _full(_pct("near_enemy")), (10, 25, 40, 55, 75), "game", "%"),
        _ladder(23, "Super Ultra Hyper Turbo", "Reach a high top speed in one game", "speed",
                lambda gs: gs[0].top_speed, (14, 17, 20, 20, 23), "game", " m/s"),
        _ladder(24, "I’m Bat Bot", "Share of one game spent upside down", "inverted",
                _full(_pct("upside")), (15, 30, 55, 80, 92), "game", "%"),
    ]
    for rid, name, m in ((25, "Constant Contesting", "dyson"), (26, "Blast Furnace", "combustion"),
                         (27, "Techneium-99", "fission"), (28, "Bird of Prey", "surge")):
        rules.append(_tiered(rid, name, f"Play games on {m.title()} in one day", m,
                             lambda g, m=m: g.map == m, (3, 4, 6, 8, 10), "day"))
    rules.append(_tiered(29, "Combat on Quest When?", "Play Combat pubs in one day", "pubs", _pub, (9, 13, 18, 24, 32), "day"))  # 20 % lower (user, 2026-11-03)

    # Weekly (30-54): the most in one calendar week (Monday start)
    names = {
        "assault": "Pulse Check", "blaster": "Eat My Nova!", "scout": "Silicon Assassin", "rocket": "I Came to Drop Bombs",
        "det": "Throws Better Than an Arena Disc", "stun": "Don't Taze Me Bro Bot", "arc": "Electroshock Therapy", "burst": "Fully Juiced",
        "heal": "Built to Last", "sensor": "X-Ray Vision Implant Upgrade", "shield": "Check Out My Cool Screensaver", "wraith": "Ghost in the Shell",
    }
    i = 30
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, names[code], f"Play games using only {label} in any 7 days", icon,
                                 _only_games(slot, code), GEAR_WEEK, "week"))
            i += 1
    rules += [
        _ladder(42, "Gearhead", "Play games in a row with the same single loadout, within any 7 days", "loadout", _gearhead_run, (4, 8, 15, 30, 50), "week"),
        Rule(43, "Pew Pew Proof", "Play 25+ games in any 7 days and average fewer than 5 deaths per game", "week", "deaths", _pew_pew_proof, estimated=True),
        _tiered(44, "I'd Rather Be on Kronos II", "Play Capture Point games in any 7 days", "capture_point", _capture, (10, 18, 25, 40, 50), "week"),
        _tiered(45, "Sakura's Dancing Flamingo", "Play Payload games in any 7 days", "payload", _payload, (10, 18, 25, 40, 50), "week"),
        _ladder(46, "Tech Support w/RAD_Natalie", "Average share of your games spent close to a teammate, over any 7 days", "team_proximity", _pct("near_mate"), (22, 27, 32, 40, 55), "week", "%"),
        _ladder(47, "Hug Your Frenemy", "Average share of your games spent close to an enemy, over any 7 days", "enemy_proximity", _pct("near_enemy"), (15, 20, 25, 35, 50), "week", "%"),
        _ladder(48, "The Wings of RAD_Wyvern", "Your average speed over any 7 days", "speed", _AvgValue("speed_sum", 1.0), (3.5, 4, 4.5, 5, 6), "week", " m/s"),
        _ladder(49, "I’ɯ ꓭɐʇ ꓭoʇ", "Average share of your games spent upside down, over any 7 days", "inverted", _pct("upside"), (5, 10, 15, 30, 50), "week", "%"),
    ]
    for rid, name, m in ((50, "Frame-Drop Hell", "dyson"), (51, "I've Got a Fever, and the Only Prescription Is Pew Pew Pew!", "combustion"),
                         (52, "Phoeniconaias minor", "fission"), (53, "Phoenicopterus ruber", "surge")):
        rules.append(_tiered(rid, name, f"Play games on {m.title()} in any 7 days", m,
                             lambda g, m=m: g.map == m, (4, 6, 8, 18, 34), "week"))
    rules.append(_tiered(54, "Who Do I Have to Pew Pew Pew to Get a Combat Update Around Here?",
                         "Play Combat pubs in any 7 days", "pubs", _pub, (15, 30, 60, 100, 150), "week"))

    # All time (55-79). 55-66 have no title in the old code (A: names generated).
    i = 55
    for slot, items in (("weapon", WEAPONS), ("ordnance", ORDNANCES), ("tacmod", TACMODS)):
        for code, label, icon in items:
            rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", icon, _games_using(slot, code), GEAR_VETERAN))
            i += 1
    rules += [
        _ladder(67, "5th Loadout when? \"Soon™\"", "Use different loadouts (weapon + ordnance + tac mod), at least 1 minute each; there are 240 in total", "loadout", _loadouts_used, (6, 12, 24, 40, 56)),
        _ladder(68, "Pixel Party!", "Total number of times you died, across all games", "deaths", lambda gs: sum(g.deaths for g in gs), (75, 225, 563, 1500, 3000), estimated=True),
        _tiered(69, "King of the Hill", "Play Capture Point games", "capture_point", _capture, (12, 29, 58, 115, 288)),
        _tiered(70, "Feed the Flamingo", "Play Payload games", "payload", _payload, (12, 29, 58, 115, 288)),
        _ladder(71, "Robot Wrecking Squad", "Average share of each game spent close to a teammate (needs 50+ games)", "team_proximity",
                _AvgValue("near_mate", 100.0, SEASON_MIN_GAMES), (14, 15.5, 17, 19.5, 22.5), "all", "%"),
        _ladder(72, "Roboticide", "Average share of each game spent close to an enemy (needs 50+ games)", "enemy_proximity",
                _AvgValue("near_enemy", 100.0, SEASON_MIN_GAMES), (6, 8, 10, 12.5, 15), "all", "%"),
        _ladder(73, "Cyberkinetic Enhancements", "Your average speed across all games (needs 25+ games)", "speed",
                _AvgValue("speed_sum", 1.0, SPEED_MIN_GAMES), (2.6, 2.8, 3.0, 3.2, 3.5), "all", " m/s"),
        _ladder(74, "toB taB m'I", "Average share of each game spent upside down (needs 50+ games)", "inverted",
                _AvgValue("upside", 100.0, SEASON_MIN_GAMES), (2, 4, 8, 20, 40), "all", "%"),
    ]
    for rid, name, m in ((75, "Brute Force Attack", "dyson"), (76, "Molten Mechanical Mayhem", "combustion"),
                         (77, "George and I Go Way Back", "fission"), (78, "Good ol' George", "surge")):
        rules.append(_tiered(rid, name, f"Play games on {m.title()}", m, lambda g, m=m: g.map == m, (5, 10, 25, 75, 150)))
    rules.append(_tiered(79, "King/Queen of Pubs", "Play Combat pubs", "pubs", _pub, (25, 75, 150, 250, 400)))

    # New (80+): data the old site never used.
    starts = {"rifle": ("Starburst Beta Tester", (1, 5, 25, 50, 100)), "magnum": ("Protostar Prototype", (1, 5, 25, 50, 100)),
              "smg": ("Quantum of Quark", (1, 5, 25, 50, 100)), "chain": ("Blazar of Glory", (1, 5, 25, 50, 100))}
    i = 80
    for code, label in UNRELEASED_WEAPONS:
        name, levels = starts[code]
        rules.append(_ladder(i, name, f"Play games using {label} (experimental weapon)", GEAR_ICONS[code], _games_using("weapon", code), levels,
                             new=True, group="Experimental gear"))
        i += 1
    rules += [
        _ladder(84, "Now You See Me", "Play games using Translocator (experimental ordnance)", "translocator", _games_using("ordnance", "loc"), (1, 5, 25, 50, 100),
                new=True, group="Experimental gear"),
        _ladder(85, "Connect the Dots", "Play games using Dot Field (experimental ordnance)", None, _games_using("ordnance", "dot"), (1, 5, 25, 50, 100),
                new=True, group="Experimental gear"),
        Rule(86, "Forbidden Arsenal", "Use all 4 experimental weapons: Starburst, Protostar, Quark and Blazar", "all", "loadout",
             _all_used("weapon", {c for c, _ in UNRELEASED_WEAPONS}), new=True, group="Experimental gear"),
        Rule(87, "Jack of All Trades", "Use all 4 weapons (Pulsar, Nova, Comet and Meteor) in one game", "game", "loadout",
             _all_used("weapon", {c for c, _, _ in WEAPONS}), new=True, group="Gear mastery"),
        Rule(88, "Ordnance Sampler", "Use all 4 ordnances (Detonator, Stun Field, Arc Mine and Instant Repair) in one game", "game", "loadout",
             _all_used("ordnance", {c for c, _, _ in ORDNANCES}), new=True, group="Gear mastery"),
        Rule(89, "Tac Mod Tinkerer", "Use all 4 tac mods (Repair Matrix, Threat Scanner, Energy Barrier and Phase Shift) in one game", "game",
             "loadout", _all_used("tacmod", {c for c, _, _ in TACMODS}), new=True, group="Gear mastery"),
        _ladder(90, "On a Roll", "Win games in a row (games with no result do not break the streak)", None, _v4(_win_streak), (2, 2, 3, 4, 5), new=True, group="Wins"),
        # id 91 (Unstoppable, win games in a row) was removed on 2026-11-04: On a Roll is the same challenge (user)
        _tiered(92, "Centurion", "Win games", None, lambda g: g.enough_players and g.won, (5, 10, 30, 100, 300), new=True, group="Wins"),
        # the attacking team wins exactly when the payload reaches the end (stats/payload.py)
        _tiered(93, "Clean Sweep", "Win Capture Point games without losing a round (2-0)", "capture_point",
                lambda g: g.enough_players and _capture(g) and g.won and g.rounds_lost == 0, (1, 5, 10, 25, 100), new=True, group="Capture Point"),
        _tiered(94, "Special Delivery", "Deliver the payload to the end: win Payload games as the attacking team", "payload",
                lambda g: g.enough_players and _payload(g) and g.won and g.attacking_team == g.team, (1, 5, 10, 25, 60), new=True, group="Payload"),
        _tiered(95, "Hold the Line", "Win Payload games as the defending team (the other team does not get the payload to the end)", "payload",
                lambda g: g.enough_players and _payload(g) and g.won and g.attacking_team not in (None, g.team), (1, 5, 10, 25, 60), new=True, group="Payload"),  # left as is 2026-11-04 (user: only ease what is unrealistic): 1/6/12/39/94 wins, platinum reached by 29 players
        _ladder(96, "Pedal to the Metal", "Longest time your team pushes the payload in one game, in seconds", "payload",
                _v4(lambda gs: gs[0].push_s), (40, 70, 100, 115, 154), "game", " s", estimated=True, new=True, group="Payload"),  # seconds, eased 2026-11-04 (user): 40/70/100/150/200 s; was 1-8 min
        _ladder(97, "Immovable Object", "Longest time you block the payload in one game, in seconds", "payload",
                _v4(lambda gs: gs[0].block_s), (15, 30, 45, 48, 62), "game", " s", estimated=True, new=True, group="Payload"),  # seconds, eased 2026-11-04 (user): 15/30/45/62/81 s; was 0.5-3.9 min
        _ladder(98, "Freight Train", "Total time spent pushing the payload, in minutes", "payload",
                _v4(lambda gs: sum(g.push_s for g in gs) / 60), (5, 12, 25, 35, 54), "all", " min", raise_all_time=False, estimated=True, new=True, group="Payload"),  # eased 2026-11-04 (user): 5/12/25/46/70 min; was 12/36/72/234/468, platinum 0.3 % of players
        # id 99 (the first Showboat, emotes in any game) was removed on 2026-11-05: id 151, emotes in a won game, took its name (user)
        _ladder(100, "Dance Floor Legend", "Use emotes (total across all games)", None, lambda gs: sum(g.emotes for g in gs), (40, 200, 800, 2000, 8000),  # x4 (user, 2026-11-03)
                new=True, group="Emotes"),
    ]

    # Unreleased gear, now in everyday use (user, 2026-10-31): the replays of 30-31 Oct 2026 show Quark in 75 of 84
    # games and Translocator in 74.
    now_public = (("weapon", "rifle", "Starburst", "Starburst Stream"), ("weapon", "magnum", "Protostar", "Protostar Power Trip"),
                  ("weapon", "smg", "Quark", "Quark Storm"), ("ordnance", "loc", "Translocator", "Here, There and Everywhere"))
    for i, (slot, code, label, name) in enumerate(now_public, 101):
        rules.append(_ladder(i, name, f"Play games using only {label} in one day", GEAR_ICONS[code],
                             _only_games(slot, code), GEAR_DAY, "day", new=True, group="Experimental gear"))
    for i, (slot, code, label, _) in enumerate(now_public, 105):
        rules.append(_ladder(i, f"{label} Veteran", f"Play games using {label}", GEAR_ICONS[code], _games_using(slot, code),
                             GEAR_VETERAN,  # released 2026-10-30: the same ladder as the older gear (user, 2026-10-31)
                             new=True, group="Experimental gear"))
    rules += [
        Rule(109, "Beam Me Up", "Use Translocator and Dot Field in one game", "game", "translocator",
             _all_used("ordnance", {"loc", "dot"}), new=True, group="Experimental gear"),
        Rule(110, "Arsenal Overload", "Use 5 different weapons in one game", "game", None,
             lambda gs: len(gs[0].used("weapon")) / 5, new=True, group="Gear mastery"),
        Rule(111, "Ordnance Overload", "Use 5 different ordnances in one game", "game", None,
             lambda gs: len(gs[0].used("ordnance")) / 5, new=True, group="Gear mastery"),
        _ladder(112, "Overclocked", "Play games using Overcharge (experimental tac mod)", None, _games_using("tacmod", "buff"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
    ]

    # New challenges from the 2026-10-31 review (113+). Targets chosen from the archive (docs/Achievement-Tiers-Proposal.MD).
    rules += [
        _ladder(113, "Frequent Flyer", "Total games played", None, len, (10, 50, 150, 300, 500), new=True, group="Activity"),
        _ladder(114, "Regular", "Number of different days you played", None, lambda gs: len({g.day for g in gs}), (5, 15, 30, 60, 100), new=True, group="Activity"),
        _ladder(115, "Loyal Bot", "Number of different weeks you played", None, lambda gs: len({g.week for g in gs}), (3, 6, 9, 12, 15), new=True, group="Activity"),
        _ladder(116, "Daily Grind", "Days in a row with at least one game played", None, _day_streak, (3, 5, 7, 14, 30), new=True, group="Activity"),
        _ladder(117, "Time Well Wasted", "Total hours played", None, lambda gs: sum(g.play_time_s for g in gs) / 3600, (1, 5, 20, 50, 80), "all", " h",
                new=True, group="Activity"),
        _tiered(118, "Overtime", "Games of 10 minutes or longer", None, lambda g: g.play_time_s >= 600, (5, 20, 50, 100, 250), new=True, group="Activity"),
        _tiered(119, "Hot Day", "Win games in one day", None, lambda g: g.enough_players and g.won, (3, 5, 8, 12, 18), "day", new=True, group="Wins"),
        _tiered(120, "Point Taker", "Win Capture Point games", "capture_point", lambda g: g.enough_players and _capture(g) and g.won, (5, 10, 30, 80, 150), new=True, group="Capture Point"),
        _tiered(121, "Cargo Hauler", "Win Payload games", "payload", lambda g: g.enough_players and _payload(g) and g.won, (5, 10, 30, 80, 150), new=True, group="Payload"),
        _ladder(122, "Grand Tour", "Win games on all 4 maps (your weakest map sets the count)", None, _v4(_fewest_wins), (1, 3, 6, 12, 20),
                raise_all_time=False, new=True, group="Wins"),  # eased 2026-11-04 (user): 1/3/6/16/26; was 1/4/10/39/117, platinum reached by ~10 players
        _ladder(123, "Weapons Master", "Play games with your least-used weapon (of Pulsar, Nova, Comet and Meteor)", "loadout", _least_used("weapon", WEAPONS),
                (1, 5, 15, 50, 100), new=True, group="Gear mastery"),
        _ladder(124, "Loadout Scholar", "Play games with your least-used item (of all 12 weapons, ordnances and tac mods)", None, _least_used_equipable,
                (1, 5, 15, 50, 100), new=True, group="Gear mastery"),
        _ladder(125, "Wall of Steel", "Total time spent blocking the payload", "payload", lambda gs: sum(g.block_s for g in gs) / 60, (2, 10, 30, 60, 120),
                "all", " min", estimated=True, new=True, group="Payload"),
        # Medal Collector counts the other rules' medals; filled in by evaluate() (meta)
        _ladder(126, "Medal Collector", "Earn gold or better on other challenges (each challenge counts once, Test Drives do not count)", None, lambda gs: 0.0, MEDAL_LEVELS,
                new=True, group="Activity", meta=True),
    ]
    # Gear released on 2026-10-30 gets what the older gear has: "only X" in a week (127-130) and Overcharge in a day / week
    # (131-132), on the same ladders (user, 2026-10-31: estimated, the archive holds little of it yet).
    weekly = (("weapon", "rifle", "Starburst", "Star Power"), ("weapon", "magnum", "Protostar", "Protostar Powerhouse"),
              ("weapon", "smg", "Quark", "Quark Quake"), ("ordnance", "loc", "Translocator", "Blink and You'll Miss It"))
    for i, (slot, code, label, name) in enumerate(weekly, 127):
        rules.append(_ladder(i, name, f"Play games using only {label} in any 7 days", GEAR_ICONS[code],
                             _only_games(slot, code), GEAR_WEEK, "week", new=True, group="Experimental gear"))
    rules += [
        _ladder(131, "Full Charge", "Play games using only Overcharge in one day", None,
                _only_games("tacmod", "buff"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(132, "Charged Up", "Play games using only Overcharge in any 7 days", None,
                _only_games("tacmod", "buff"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
        # Blazar and Dot Field were released too (user, 2026-10-31): the same set as the other new gear
        _ladder(133, "Blazar Veteran", "Play games using Blazar", "blazar", _games_using("weapon", "chain"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
        _ladder(134, "Dot Field Veteran", "Play games using Dot Field", None, _games_using("ordnance", "dot"), GEAR_VETERAN,
                new=True, group="Experimental gear"),
        _ladder(135, "Blazing Trail", "Play games using only Blazar in one day", "blazar",
                _only_games("weapon", "chain"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(136, "Dot to Dot", "Play games using only Dot Field in one day", None,
                _only_games("ordnance", "dot"), GEAR_DAY, "day", new=True, group="Experimental gear"),
        _ladder(137, "Blazar Barrage", "Play games using only Blazar in any 7 days", "blazar",
                _only_games("weapon", "chain"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
        _ladder(138, "Dot Matrix", "Play games using only Dot Field in any 7 days", None,
                _only_games("ordnance", "dot"), GEAR_WEEK, "week", new=True, group="Experimental gear"),
    ]

    # In one game (user, 2026-11-03); 4v4 games only. Targets from the archive's per-game distributions (4+ minute games):
    # standing still median 34 % / p99 70 %, average speed p50 2.8 / p99 4.6 m/s, length p50 8.5 / p99 17 min,
    # own capture time p90 3.2 / p99 4.1 min, up to 8 loadouts. Left / right arm is a handedness flag (0 or 100 % in
    # nearly every game), so there is no arm ladder, only "both arms". Glass Cannon (most deaths) was dropped by the user.
    rules += [
        _tiered(139, "Untouchable", "Win a game without dying once", "deaths",
                lambda g: g.enough_players and g.won and g.play_time_s >= FULL_GAME_S and g.deaths == 0, (1, 2, 3, 5, 8), estimated=True, new=True, group="Survival"),
        _ladder(140, "Marathon Bot", "Play one very long game (your longest game counts)", None, _v4(lambda gs: gs[0].play_time_s / 60),
                (12, 15, 18, 21, 26), "game", " min", new=True, group="Activity"),
        _tiered(141, "Comeback Kid", "Win a Capture Point game after losing the first round (a 2-1 win)", "capture_point",
                lambda g: g.enough_players and _capture(g) and g.won and g.rounds_lost == 1, (1, 5, 15, 40, 100), new=True, group="Capture Point"),
        _ladder(142, "Statue", "Stand still (moving slower than 1 m/s) for part of one game", None,
                _v4(_full(_pct("stopped"))), (50, 60, 70, 80, 90), "game", "%", new=True, group="Movement"),
        _ladder(143, "Lone Wolf", "Stay far from your teammates (more than 2.6 m away) for most of one game",
                "team_proximity", _v4(_full(_away_from_mates)), (93.2, 95.8, 97.5, 98.7, 99.6), "game", "%", new=True, group="Movement"),
        Rule(144, "Ambidextrous", "Play one game using both the left-arm and the right-arm setting, each for at least 40 % of the time", "game", None,
             _v4(_full(_both_arms)), new=True, group="Movement"),
        _ladder(145, "Speed Demon", "Keep a high average speed through one whole game", "speed",
                _v4(_full(_AvgValue("speed_sum", 1.0))), (3.5, 4, 4.5, 5.5, 7), "game", " m/s", new=True, group="Movement"),
        _ladder(146, "Point Guard", "Spend time capturing the point in one Capture Point game (your team's capture progress is rising)",
                "capture_point", _v4(lambda gs: gs[0].capture_s / 60 if _capture(gs[0]) else 0.0), (2, 3, 3.5, 4.2, 5), "game", " min",
                new=True, group="Capture Point"),
        _ladder(147, "Contested Ground", "Spend time in one Capture Point game with both teams on the point (contested)",
                "capture_point", _v4(lambda gs: gs[0].contested_s / 60 if _capture(gs[0]) else 0.0), (2, 3.5, 5, 6.5, 8), "game", " min",
                new=True, group="Capture Point"),
        _tiered(148, "One-Trick Pony", "Win a game using just one loadout (one weapon, one tac mod and one ordnance)",
                "loadout", lambda g: g.enough_players and g.won and g.main_loadout() is not None, (1, 10, 18, 36, 70), new=True, group="Gear mastery"),
        _ladder(149, "Loadout Roulette", "Use many different loadouts in one game (each must be used for at least 10 % of the game)",
                "loadout", _v4(lambda gs: gs[0].loadouts_played()), (4, 5, 6, 7, 8), "game", new=True, group="Gear mastery"),
        _ladder(150, "Mime Troupe", "Use as many emotes as you can in one game without dying", None,
                _v4(lambda gs: gs[0].emotes if gs[0].play_time_s >= FULL_GAME_S and gs[0].deaths == 0 else 0), (4, 8, 12, 16, 20), "game",  # x4 (user, 2026-11-03)
                estimated=True, new=True, group="Emotes"),
        _ladder(151, "Showboat", "Use as many emotes as you can in a game your team wins", None,
                _v4(lambda gs: gs[0].emotes if gs[0].won else 0), (12, 24, 40, 60, 100), "game", new=True, group="Emotes"),
    ]
    # "Nothing but <item>" (one game using only an item, ids 152-163) was removed on 2026-11-04: the daily "One with the <item>" ladders
    # test the same thing (user).

    # One challenge per released item (user, 2026-11-05): use it for 3 minutes of one game, shown under "In one game". The most
    # rarely used stay within reach, as one game with the item is enough; in the archive Overcharge has 4 players, Blazar 35.
    icons = {code: icon for code, _, icon in WEAPONS + ORDNANCES + TACMODS} | GEAR_ICONS
    weapons, tacmods, ordnances = _released_gear()
    i = 179
    for slot, table, codes in (("weapon", gear.WEAPONS, weapons), ("tacmod", gear.TACMODS, tacmods), ("ordnance", gear.ORDNANCES, ordnances)):
        for code in codes:
            label = gear.lookup(table, code).display_name
            rules.append(Rule(i, f"Test Drive: {label}", f"Use {label} for at least {TEST_DRIVE_S / 60:g} minutes in one game", "game", icons.get(code),
                              _test_drive(slot, code), new=True, group=ONE_GAME_GEAR))
            i += 1
    return rules


_NOTE_MIN_IDS = {18, 43, 139, 150}  # rules that check the length in their own function
_NOTE_4V4_IDS = {95, 119, 120, 121, 139, 141, 148, 92, 93, 94}  # rules whose test is a lambda that checks enough_players itself
_NOTE_ONLY_IDS = {42, 148}


def rule_notes(rule: Rule) -> list[str]:
    """The counting rules of one achievement in short lines (shown on the site; the description says what to do)."""
    if rule.meta:
        return []
    fn = rule.count or rule.score
    # Short tags (user, 2026-11-04): the site shows them on one line, "Best game · 4+ min · 3+ players per team · "Only" = 90%+"
    notes = [{"game": "Best game", "day": "Best day", "week": "Best 7 days"}.get(rule.period)]
    if rule.period == "all":
        need = getattr(rule.count, "min_games", 0)
        notes = [f"Average, {need}+ games" if need else "All-time total"]
    if getattr(fn, "min_length", False) or rule.id in _NOTE_MIN_IDS:
        notes.append(f"{FULL_GAME_S / 60:g}+ min games")
    if getattr(fn, "enough_players", False) or rule.id in _NOTE_4V4_IDS:
        notes.append("3+ players per team")
    if getattr(fn, "use_only", False) or rule.id in _NOTE_ONLY_IDS:
        notes.append(f"\"Only\" = {ONLY_SHARE:.0%}+ of the game")
    if rule.id == 67:
        notes.append(f"{LOADOUT_USED_S / 60:g}+ min per loadout")
    return [n for n in notes if n]


def _tuned(rule: Rule, levels: tuple[float, ...] | None = None) -> Rule:
    """The rule with the given targets or its TUNED_LEVELS (targets, text and scoring), if it has any."""
    levels = levels or TUNED_LEVELS.get(rule.id)
    if levels is None:
        return rule
    what = rule.description.rsplit(" (", 1)[0]
    targets = ", ".join(f"{_num(n)}{rule.unit} {medal}" for n, medal in zip(levels, LEVELS))
    return replace(rule, description=f"{what} ({targets})", levels=levels, score=_levelled(rule.count, levels))


RULES = [_tuned(r) for r in _build_rules()]

# Mega Prize (user, 2026-11-04): NOT in RULES on purpose. RULES feeds every public list, ranking, medal feed and total; the
# prize is Preview-only and only served by api/arena.py and the Console report (mega_prizes.py). Written targets are
# /HARDER_TOP so that platinum = 750 and diamond = 450 matches.
MEGA_COMBAT = _ladder(0, "Echo Combat Veteran", "Play Echo Combat matches", None, len, (25, 100, 250, 346, 577),
                      raise_all_time=False, new=True, group="Activity", prize="Delta Squad BioMass Chassis")


def icon_file(rule: Rule) -> str | None:
    """Old badge art: ids 5-29 were the daily set, 30-54 weekly, 55-79 all-time."""
    if rule.icon is None:
        return None
    suffix = "_daily" if rule.id < 30 else "_weekly" if rule.id < 55 else ""
    return f"{rule.icon}{suffix}.png"


def tier(progress: float) -> str | None:
    return next((name for level, name in TIERS if progress >= level), None)


WEEK = timedelta(days=7)


def _rolling_weeks(games: list[Game], maximal: bool) -> list[list[Game]]:
    """Every 7-day window that starts at one of the player's games (any 7 days can be slid to start at its first game).
    `maximal`: skip windows that are a part of the one before (same last game), for rules where more games can
    never lower the value (counts); averages and ratios need every window."""
    ordered = sorted(games, key=lambda g: g.start_dt)
    out: list[list[Game]] = []
    end = prev_end = 0
    for i, g in enumerate(ordered):
        limit = g.start_dt + WEEK
        end = max(end, i + 1)
        while end < len(ordered) and ordered[end].start_dt < limit:
            end += 1
        if maximal and i and end == prev_end:
            continue
        out.append(ordered[i:end])
        prev_end = end
    return out


def _monotone(rule: "Rule") -> bool:
    """True when adding games to a group can never lower the rule's value (so only maximal windows need checking)."""
    return bool(rule.levels) and not isinstance(rule.count, _AvgValue)


def _week_key(rule: "Rule") -> str:
    if rule.period != "week":
        return rule.period
    return "week" if _monotone(rule) else "week_all"


def _groups(games: list[Game], period: str) -> list[list[Game]]:
    if period == "all":
        return [games]
    if period == "game":
        return [[g] for g in games]
    if period in ("week", "week_all"):
        return _rolling_weeks(games, maximal=period == "week")
    key = lambda g: g.day
    groups = defaultdict(list)
    for g in games:
        groups[key(g)].append(g)
    return list(groups.values())


def _reached_gold(entry: dict, rule: Rule) -> bool:
    """Medal Collector: a ladder counts from gold (third medal) on, a single-step rule when completed."""
    return entry["count"] >= rule.levels[2] if rule.levels else entry["progress"] >= 1


def evaluate(games: list, rules: list[Rule] = RULES) -> list[dict]:
    """Progress per rule: best period, capped at 1. Ladders also report the best count per period group."""
    groups = {p: _groups(games, p) for p in ("game", "day", "week", "week_all", "all")}
    entries: dict[int, dict] = {}
    for rule in rules:
        if rule.meta:
            continue
        n = None
        if rule.levels:  # ladder: the best count over the period groups (once: progress follows from it)
            n = max((rule.count(g) for g in groups[_week_key(rule)] if g), default=0)
            best = _levelled(lambda _, n=n: n, rule.levels)([])
        else:
            best = max((rule.score(g) for g in groups[_week_key(rule)] if g), default=0.0)
        progress = round(clamp(best), 4)
        entry = {
            "id": rule.id, "name": rule.name, "description": rule.description, "rules": rule_notes(rule), "period": rule.period,
            "icon": icon_file(rule), "estimated": rule.estimated, "new": rule.new, "group": rule.group, "counted": rule.counted, "progress": progress, "tier": tier(progress),
        }
        if n is not None:  # the website shows "12 / 25 for diamond"
            entry |= {"tier": level_tier(n, rule.levels), "count": round(n, 2), "levels": list(rule.levels), "unit": rule.unit}
        if rule.id == LOADOUT_RULE_ID:
            entry["try_next"] = loadouts_to_try(games)  # "try these next": the website links each to its leaderboard
        entries[rule.id] = entry
    for rule in rules:
        if rule.meta:
            n = sum(1 for r in rules if not r.meta and r.group != ONE_GAME_GEAR and _reached_gold(entries[r.id], r))  # Test Drives are left out (user, 2026-11-05)
            progress = round(clamp(_levelled(lambda _: n, rule.levels)([])), 4)
            entries[rule.id] = {
                "id": rule.id, "name": rule.name, "description": rule.description, "rules": rule_notes(rule), "period": rule.period, "icon": icon_file(rule),
                "estimated": False, "new": rule.new, "group": rule.group, "counted": rule.counted, "progress": progress, "tier": level_tier(n, rule.levels),
                "count": n, "levels": list(rule.levels), "unit": rule.unit,
            }
    return [entries[rule.id] for rule in rules]


PERIOD_SECTIONS = {"game": "In one game", "day": "In one day", "week": "In any 7 days", "all": "All time"}
SECTION_MIN_RULES = 4  # a section needs this many challenges to be somebody's "strongest" (not a lone rule)


def section_of(rule: Rule) -> str:
    """The section of the website a rule is shown in: its period (original rules) or its theme (new ones)."""
    if rule.group == ONE_GAME_GEAR:
        return PERIOD_SECTIONS[rule.period]
    if rule.new and not (rule.period == "week" and rule.group in ("Experimental gear", "Gear mastery")):  # 7-day gear rules: by period
        return rule.group or "More"
    return PERIOD_SECTIONS[rule.period]


def achiever_facts(progress: list[float]) -> dict:
    """Fun facts about one player from the progress per rule (same order as RULES): challenges completed, medals earned
    (one per ladder step reached, a single-step rule counts once), challenges at gold or better, and the section with
    the highest average progress."""
    completed = medals = gold_plus = 0
    sections: dict[str, list[float]] = defaultdict(list)
    for rule, p in zip(RULES, progress):
        sections[section_of(rule)].append(p)
        completed += p >= 1
        if rule.levels:
            reached = int(p * len(rule.levels) + 1e-6)
            medals += reached
            gold_plus += reached >= 3
        elif p >= 1:
            medals += 1
            gold_plus += 1
    best = max(((sum(v) / len(v), name) for name, v in sections.items() if len(v) >= SECTION_MIN_RULES), default=(0.0, None))
    return {"completed": completed, "total": len(RULES), "medals": medals, "gold_plus": gold_plus,
            "best_section": best[1] if best[0] > 0 else None, "best_section_share": round(best[0], 4)}


def overall(results: list[dict]) -> float:
    return round(sum(r["progress"] for r in results) / len(results), 4) if results else 0.0


def mega_combat_games(games: list[Game], start: str | None, end: str | None) -> int:
    """Combat games that count for the Mega Prize (user, 2026-11-04): started inside the challenge period and 4+ minutes
    played (FULL_GAME_S), so a short appearance does not count, and 3v3 or bigger (enough_players)."""
    return sum(1 for g in in_window(games, start, end) if g.play_time_s >= FULL_GAME_S and g.enough_players)


def in_window(games: list[Game], start: str | None, end: str | None) -> list[Game]:
    """Challenge period (admin-set, D33): only games started on/after `start` and on/before `end` (dates)."""
    return [g for g in games
            if (not start or g.started_at[:10] >= start) and (not end or g.started_at[:10] <= end)]


def unlock_dates(games: list, rules: list[Rule] = RULES) -> dict[int, str]:
    """Date each rule first reached 100 % (ISO date). Game / day / week rules: the earliest group that
    reached it; all-time rules: the first game at which the running total reached it (averages: scanned in
    order, they can go down again; counts only grow, so a binary search finds it)."""
    ordered = sorted(games, key=lambda g: g.started_at)
    groups = {p: _groups(ordered, p) for p in ("game", "day", "week", "week_all")}
    out: dict[int, str] = {}
    for rule in rules:
        if rule.meta:
            continue
        if rule.period == "all":
            if not ordered or rule.score(ordered) < 1:
                continue
            if isinstance(rule.count, _AvgValue):
                out[rule.id] = ordered[rule.count.first_reached(ordered, rule.levels[-1])].started_at[:10]
                continue
            lo, hi = 1, len(ordered)
            while lo < hi:
                mid = (lo + hi) // 2
                if rule.score(ordered[:mid]) >= 1:
                    hi = mid
                else:
                    lo = mid + 1
            out[rule.id] = ordered[lo - 1].started_at[:10]
        else:
            # a rolling week is complete at its last game, a day / game at its first (as before)
            pick = max if rule.period == "week" else min
            done = [pick(g.started_at for g in group) for group in groups[_week_key(rule)] if group and rule.score(group) >= 1]
            if done:
                out[rule.id] = min(done)[:10]
    return out


def medal_times(games: list, rules: list[Rule] = RULES) -> dict[int, dict[str | None, str]]:
    """When each medal of each rule was first earned: {rule id: {medal: started_at of the game that completed it}}.
    A ladder has one entry per medal (bronze ... platinum); a single-step rule one entry under the key None (completed).
    Same rules as unlock_dates (a rolling week is complete at its last game, a day / game at its first), but for
    every medal and with the full time, not just the date."""
    ordered = sorted(games, key=lambda g: g.started_at)
    groups = {p: _groups(ordered, p) for p in ("game", "day", "week", "week_all")}
    out: dict[int, dict[str | None, str]] = {}
    eps = 1e-9
    for rule in rules:
        if rule.meta or not ordered:
            continue
        n = len(rule.levels)
        steps = [((k + 1) / n, LEVELS[k] if n == len(LEVELS) else None) for k in range(n)] if n else [(1.0, None)]
        found: dict[str | None, str] = {}
        if rule.period == "all":
            if rule.score(ordered) < steps[0][0] - eps:
                continue
            for k, (thr, medal) in enumerate(steps):
                if rule.score(ordered) < thr - eps:
                    break
                if isinstance(rule.count, _AvgValue):
                    i = rule.count.first_reached(ordered, rule.levels[k])
                    if i is None:
                        break
                    found[medal] = ordered[i].started_at
                    continue
                lo, hi = 1, len(ordered)
                while lo < hi:
                    mid = (lo + hi) // 2
                    if rule.score(ordered[:mid]) >= thr - eps:
                        hi = mid
                    else:
                        lo = mid + 1
                found[medal] = ordered[lo - 1].started_at
        else:
            pick = max if rule.period == "week" else min
            for group in groups[_week_key(rule)]:
                if not group:
                    continue
                score = rule.score(group)
                when = None
                for thr, medal in steps:
                    if score >= thr - eps:
                        when = when or pick(g.started_at for g in group)
                        if medal not in found or when < found[medal]:
                            found[medal] = when
        if found:
            out[rule.id] = found
    return out
