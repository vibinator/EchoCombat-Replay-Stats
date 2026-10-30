"""Every achievement / Flamingo Challenge with how to get it, for the admin tab and its Excel download (D42).
Built from RULES on every request, so a changed rule shows up straight away. "Requirement" is the exact text on the
website (it holds every condition, D39); "How to achieve it" and "Good to know" only explain it."""

import csv
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .achievements import RULES, Rule

TIMEFRAME = {"game": "One game", "day": "One day", "week": "One week", "all": "All time"}
HINT = {
    "game": "It has to happen within one match; your best match counts.",
    "day": "It has to happen within one calendar day (midnight to midnight); your best day counts, so one good day "
           "is enough.",
    "week": "It has to happen within one Monday-to-Sunday week; your best week counts.",
    "all": "Builds up over every counted match, at your own pace.",
}
PROGRESS = {"game": "Your best single game", "day": "Your best day", "week": "Your best week",
            "all": "Your running total / average"}

COLUMNS = [  # (key, header, Excel width)
    ("id", "ID", 6), ("name", "Name", 30), ("category", "Category", 18), ("theme", "Theme", 16),
    ("timeframe", "Timeframe", 12), ("requirement", "Requirement (as on the website)", 48),
    ("how", "How to achieve it", 58), ("progress", "Progress is measured by", 26), ("notes", "Good to know", 52),
]

GUIDE = [
    ("Start date", "Only matches played on or after the start date set in the admin console count (and on or before "
                   "the end date, if one is set). Before the start date the website shows \"Coming soon\"."),
    ("Tiers", "Each achievement has four tiers by progress towards its target: White 25%, Bronze 50%, Silver 75%, "
              "Gold 100%. Gold = completed."),
    ("Progress", "The best value ever reached, capped at 100%: your best game, best day, best week, or your all-time "
                 "total / average, depending on the timeframe."),
    ("One game", "Reached inside a single match. Where the text says (3+ minutes), shorter appearances do not count."),
    ("One day", "Calendar day of the match (the recorder's local date), midnight to midnight."),
    ("One week", "Calendar week, Monday to Sunday. A new week starts every Monday."),
    ("All time", "Adds up every counted match. Rules marked \"all-time average, 50+ games\" need that many games "
                 "before they can reach 100%."),
    ("\"Use only X\"", "X is 95% or more of that game's loadout time."),
    ("\"Use X\"", "X for at least 5% of that game's loadout time."),
    ("*", "Based on estimated deaths: the replay does not record deaths exactly."),
    ("New challenge", "Not on the original ECRanked site: built on data it never used (unreleased gear, wins, "
                      "payload push / block time, emotes)."),
]


def _notes(rule: Rule) -> str:
    d, out = rule.description, []
    if "only" in d.lower() and "use" in d.lower():
        out.append('"Use only X" = X is 95%+ of your loadout time in that game.')
    elif d.startswith("Use ") or " using " in d:
        out.append('"Use X" = X for at least 5% of the game\'s loadout time.')
    if rule.estimated:
        out.append("Deaths are estimated from the replay, so this can be slightly off.")
    if d.startswith("Win") or " win" in d.lower():
        out.append("Matches with no result (recording ended early) do not count as wins.")
    if "average" in d.lower():
        out.append("An average: it can go down again after it rises.")
    return " ".join(out)


def rows() -> list[dict]:
    return [{
        "id": r.id, "name": r.name, "category": "New challenge" if r.new else "Original ECRanked",
        "theme": r.group or "", "timeframe": TIMEFRAME[r.period],
        "requirement": r.description + (" *" if r.estimated else ""),
        "how": f"{r.description}. {HINT[r.period]}",
        "progress": PROGRESS[r.period], "notes": _notes(r),
    } for r in RULES]


def name_and_rule() -> list[dict]:
    """Console export (D45): just the name and the rule to win it, the text on the website."""
    return [{"id": r.id, "name": r.name, "rule": r.description + (" (deaths are estimated)" if r.estimated else "")}
            for r in RULES]


def csv_bytes() -> bytes:
    """name_and_rule as CSV; UTF-8 with BOM so Excel shows accents and symbols correctly."""
    out = StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(["Name", "How to win it"])
    writer.writerows([r["name"], r["rule"]] for r in name_and_rule())
    return out.getvalue().encode("utf-8-sig")


def workbook_bytes(version: str) -> bytes:
    font, bold = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
    head, fill = Font(name="Arial", size=10, bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F2228")
    wrap = Alignment(wrap_text=True, vertical="top")
    wb = Workbook()

    ws = wb.active
    ws.title = "Achievements"
    ws.append([h for _, h, _ in COLUMNS])
    for row in rows():
        ws.append([row[k] for k, _, _ in COLUMNS])
    for i, (_, _, width) in enumerate(COLUMNS, 1):
        ws.column_dimensions[get_column_letter(i)].width = width
    for row in ws.iter_rows():
        for c in row:
            c.font, c.alignment = font, wrap
    for c in ws[1]:
        c.font, c.fill, c.alignment = head, fill, Alignment(wrap_text=True, vertical="center")
    ws.freeze_panes = "C2"
    table = Table(displayName="Achievements", ref=f"A1:{get_column_letter(len(COLUMNS))}{ws.max_row}")
    table.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
    ws.add_table(table)

    guide = wb.create_sheet("How it works")
    guide.append(["How achievements and Flamingo Challenges work"])
    guide.append([])
    for key, text in GUIDE + [("Source", f"EchoVR Replay Stats {version}: generated from the app's achievement "
                                         "rules when downloaded. The Requirement column is the text on the website.")]:
        guide.append([key, text])
    guide.column_dimensions["A"].width, guide.column_dimensions["B"].width = 18, 100
    for row in guide.iter_rows():
        for c in row:
            c.font, c.alignment = font, wrap
        row[0].font = bold
    guide["A1"].font = Font(name="Arial", size=14, bold=True)

    summary = wb.create_sheet("Summary")
    summary.append(["Timeframe", "Original ECRanked", "New challenge", "Total"])
    for i, timeframe in enumerate(TIMEFRAME.values(), start=2):
        summary.append([timeframe,
                        f"=COUNTIFS(Achievements!$E:$E,$A{i},Achievements!$C:$C,B$1)",
                        f"=COUNTIFS(Achievements!$E:$E,$A{i},Achievements!$C:$C,C$1)",
                        f"=B{i}+C{i}"])
    total = summary.max_row + 1
    summary.append(["Total", f"=SUM(B2:B{total - 1})", f"=SUM(C2:C{total - 1})", f"=SUM(D2:D{total - 1})"])
    for col, width in zip("ABCD", (20, 20, 16, 10)):
        summary.column_dimensions[col].width = width
    for row in summary.iter_rows():
        for c in row:
            c.font = font
    for c in summary[1]:
        c.font, c.fill = head, fill
    for c in summary[total]:
        c.font, c.border = bold, Border(top=Side(style="thin"))

    wb.calculation.fullCalcOnLoad = True  # the Summary formulas are computed when the file is opened
    out = BytesIO()
    wb.save(out)
    return out.getvalue()
