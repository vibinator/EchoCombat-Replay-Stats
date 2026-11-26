"""Every achievement / Flamingo Challenge with the rule to win it, for the Console page's export (D45). Built from
RULES on every request, so a changed rule shows up straight away; the rule text is the text on the website (D39)."""

import csv
from io import StringIO

from .achievements import RULES
from .combat_achievements import COMBAT_RULES


def name_and_rule() -> list[dict]:
    """Console export (D45): just the name and the rule to win it, the text on the website."""
    return [{"id": r.id, "name": r.name, "rule": r.description + (" (deaths are estimated)" if r.estimated else "")}
            for r in RULES + COMBAT_RULES]


def csv_bytes() -> bytes:
    """name_and_rule as CSV; UTF-8 with BOM so Excel shows accents and symbols correctly."""
    out = StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["Name", "How to win it"])
    writer.writerows([r["name"], r["rule"]] for r in name_and_rule())
    return out.getvalue().encode("utf-8-sig")
