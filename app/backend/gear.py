"""Loadout API codes -> in-game names (source: docs/reference/gear-table.json).
`cut` = never released, but seen in recent replays. Unknown codes are shown as the raw code."""

from typing import NamedTuple

from parser.frames import gear_code


class Gear(NamedTuple):
    display_name: str
    cut: bool = False


WEAPONS = {
    "assault": Gear("Pulsar"),
    "blaster": Gear("Nova"),
    "scout": Gear("Comet"),
    "rocket": Gear("Meteor"),
    "magnum": Gear("Protostar", cut=True),
    "smg": Gear("Quark", cut=True),
    "chain": Gear("Blazar", cut=True),
    "rifle": Gear("Starburst", cut=True),
}

ORDNANCES = {
    "det": Gear("Detonator"),
    "stun": Gear("Stun Field"),
    "arc": Gear("Arc Mine"),
    "burst": Gear("Instant Repair"),
    "loc": Gear("Translocator", cut=True),
    "dot": Gear("Dot Field", cut=True),
    "drone": Gear("Attack Drone", cut=True),
}

TACMODS = {
    "heal": Gear("Repair Matrix"),
    "sensor": Gear("Threat Scanner"),
    "shield": Gear("Energy Barrier"),
    "wraith": Gear("Phase Shift"),
    "buff": Gear("Overcharge", cut=True),
    "smoke": Gear("Umbral Veil", cut=True),
    "point": Gear("Neutron", cut=True),
}

NONE = Gear("None")

def lookup(table: dict[str, Gear], code: str) -> Gear:
    if not code:
        return NONE
    code = gear_code(code)  # rows saved before the parser normalised hex symbols
    return table.get(code, Gear(code))
