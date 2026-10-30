import json
from pathlib import Path

from backend.gear import NONE, ORDNANCES, TACMODS, WEAPONS, lookup

REFERENCE = Path(__file__).resolve().parents[2] / "docs" / "reference" / "gear-table.json"


def test_matches_reference_table():
    ref = json.loads(REFERENCE.read_text())["gear_table"]
    for key, table in (("weapons", WEAPONS), ("ordnances", ORDNANCES), ("tacmods", TACMODS)):
        assert {g["name"]: (g["display_name"].lower(), g.get("cut", False)) for g in ref[key]} == {
            code: (gear.display_name.lower(), gear.cut) for code, gear in table.items()
        }


def test_lookup():
    assert lookup(WEAPONS, "rifle") == ("Starburst", True)
    assert lookup(TACMODS, "") is NONE
    assert lookup(ORDNANCES, "new_thing").display_name == "new_thing"
    assert lookup(WEAPONS, "0x2fd69c8c5f615b9e").display_name == "Pulsar"
