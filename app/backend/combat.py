"""Combat stats from the recorder's match reports (user, 2026-11-04). Completely separate from the replay data: own tables
(combat_files, combat_matches, combat_players), own reader (this module), own endpoints (api/combat.py).

Collected the same way as the replays (scanner.py + worker.py): the recorder folder is mounted read-only next to the
replay share, a scanner thread lists `matches/*.json`, a new or changed file is read and saved in one transaction, and
a file still being written (modified in the last `settle_s`) waits for a later scan. A match report is small (a few KB)
and already holds everything: the game's own counters per player and, when the match has an event log, the shots / kills
/ deaths per weapon, tac mod use, heal bubbles and stuns. So there is no process pool, one thread reads them.

Format rules (E:\\ECRanked\\reference\\formats\\FORMATS.md): ids are TEXT (64-bit), join on userid, `events` is null when the
match has no event log (unknown, not 0), damage taken is never available to spectators, unknown fields are ignored."""

import json
import logging
import math
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .db import utcnow
from .models import CombatFile, CombatMatch, CombatPlayer

log = logging.getLogger(__name__)

COMBAT_VERSION = "2"  # raise when this module reads more or differently: every report is read again ("2": awards)
FOLDER = "matches"
MAX_BYTES = 5_000_000
MAX_PLAYERS = 64
SESSION_ID = re.compile(r"^[0-9A-Fa-f]{8}(-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}$")
USER_ID = re.compile(r"^[0-9]{1,24}$")
MAPS = {"mpl_combat_combustion": "combustion", "mpl_combat_dyson": "dyson", "mpl_combat_fission": "fission",
        "mpl_combat_gauss": "surge"}
INT_STATS = ("kills", "assists", "deaths", "eliminations", "objective_eliminations", "hill_captures", "hill_defends")
FLOAT_STATS = ("damage", "objective_damage", "objective_time")
EVENT_COUNTS = ("shots", "tacmod_activations", "heal_bubbles", "stuns_given", "stuns_received", "self_kills")
WEAPON_MAPS = ("shots_by_weapon", "kills_by_weapon", "deaths_by_weapon")
MAX_AWARDS = 32

# The game's own end-of-match awards (reports since 2026-11-09, FORMATS.md): symbol -> (name shown in game, the stat it is
# based on, how it is earned). There are no thresholds: the game hands each card to the top player of that stat. Every
# match gets MVP plus up to three more cards, picked by the game among the categories whose top value is above 0.
AWARDS: dict[str, tuple[str, str, str]] = {
    "mvp": ("MVP", "Score", "The highest score in the match. Given in every match that was played out."),
    "assassin": ("Assassin", "Kills", "The most kills of other players."),
    "cannoneer": ("Cannoneer", "Damage", "The most damage dealt."),
    "super_star": ("Super Star", "Eliminations", "The most eliminations (kills and assists together)."),
    "hot_shot": ("Hot Shot", "Best elimination streak", "The longest run of eliminations without dying."),
    "sniper": ("Sniper", "Headshot kills", "The most headshot kills."),
    "renegade": ("Renegade", "Solo kills", "The most kills made without a teammate's help."),
    "specialist": ("Specialist", "Assists", "The most assists."),
    "shock_trooper": ("Shock Trooper", "Stuns", "The most enemies stunned."),
    "medic": ("Medic", "Healing", "The most healing done."),
    "tank": ("Tank", "Damage absorbed", "The most damage absorbed."),
    "guard": ("Guard", "Objective time", "The most time spent on the objective."),
    "defender": ("Defender", "Objective eliminations", "The most eliminations of enemies on the objective."),
    "controller": ("Controller", "Objective damage", "The most damage to enemies on the objective."),
    "infiltrator": ("Infiltrator", "Hill captures", "The most hill captures (point-capture maps)."),
    "immovable_object": ("Immovable Object", "Hill defends", "The most hill defends (point-capture maps)."),
}


def award_name(symbol: str) -> str:
    """The in-game name of an award symbol; an unknown symbol is tidied up (a raw 0x... hash stays as it is)."""
    if symbol in AWARDS:
        return AWARDS[symbol][0]
    return symbol if symbol.startswith("0x") else symbol.replace("_", " ").title()


def _award_symbol(value) -> str | None:
    symbol = str(value or "").strip().lower()[:64]
    return symbol or None


def _player_awards(value) -> list[str] | None:
    """The award symbols of one player, or None when the report does not know them (older events file, no events)."""
    if not isinstance(value, list):
        return None
    symbols = [s for s in (_award_symbol(v) for v in value[:MAX_AWARDS]) if s]
    return list(dict.fromkeys(symbols))  # one card per award, in the game's order


def _match_awards(value) -> list[dict] | None:
    """The match's award cards (who won what, with the game's value), or None when unknown."""
    if not isinstance(value, list):
        return None
    cards = []
    for entry in value[:MAX_AWARDS]:
        if not isinstance(entry, dict):
            continue
        symbol = _award_symbol(entry.get("award"))
        if not symbol:
            continue
        user_id = str(entry.get("userid") or "")
        cards.append({"award": symbol, "stat": str(entry.get("stat") or "")[:64], "value": round(_number(entry.get("value")), 3),
                      "user_id": user_id if USER_ID.match(user_id) else None, "name": str(entry.get("name") or "Unknown")[:64],
                      "team": entry.get("team") if entry.get("team") in ("blue", "orange") else None})
    return cards


class CombatFileError(Exception):
    pass


@dataclass
class CombatState:
    reachable: bool | None = None  # None = not scanned yet
    last_scan_at: str | None = None
    files: int = 0
    settling: int = 0
    read: int = 0  # read (new or changed) by the last scan
    failed: int = 0
    error: str | None = None


def _number(value, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _count(value) -> int:
    return max(0, int(round(_number(value))))


def _weapon_counts(value) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    return {str(k)[:64]: _count(v) for k, v in list(value.items())[:64] if _count(v) > 0}


def _names(value) -> list[str]:
    return [str(v)[:64] for v in value[:32]] if isinstance(value, list) else []


def parse_report(path: Path) -> dict:
    """The report as plain values, or CombatFileError. Pure: no database."""
    try:
        if path.stat().st_size > MAX_BYTES:
            raise CombatFileError("File too large")
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as e:
        raise CombatFileError(f"Could not read file: {e}") from e
    except json.JSONDecodeError as e:
        raise CombatFileError(f"Not valid JSON: {e}") from e
    if not isinstance(data, dict) or data.get("format") != "ecranked.match":
        raise CombatFileError("Not an ecranked.match report")
    session_id = str(data.get("session_id") or "")
    if not SESSION_ID.match(session_id):
        raise CombatFileError("Missing or invalid session_id")
    started, ended = str(data.get("started") or ""), str(data.get("ended") or "")
    if not started:
        raise CombatFileError("Missing start time")
    raw_map = str(data.get("map") or "unknown")
    players = []
    for p in (data.get("players") if isinstance(data.get("players"), list) else [])[:MAX_PLAYERS]:
        user_id = str(p.get("userid") or "") if isinstance(p, dict) else ""
        if not USER_ID.match(user_id):  # the id is text; a number from an older tool version is turned into text
            continue
        stats = p.get("stats") if isinstance(p.get("stats"), dict) else {}
        row = {"user_id": user_id, "name": str(p.get("name") or "Unknown")[:64],
               "team": p.get("team") if p.get("team") in ("blue", "orange") else None,
               "present_s": _number(p.get("present_seconds")),
               "loadouts": json.dumps({k: _names((p.get("loadouts") or {}).get(k)) for k in ("weapons", "tacmods", "ordnance")}
                                      if isinstance(p.get("loadouts"), dict) else {})}
        row |= {k: _count(stats.get(k)) for k in INT_STATS} | {k: round(_number(stats.get(k)), 3) for k in FLOAT_STATS}
        events = p.get("events") if isinstance(p.get("events"), dict) else None
        for k in EVENT_COUNTS:
            row[k] = _count(events.get(k)) if events else None
        for k in WEAPON_MAPS:
            counts = _weapon_counts(events.get(k)) if events else None
            row[k] = json.dumps(counts) if counts is not None else None
        awards = _player_awards(p.get("awards"))
        row["awards"] = json.dumps(awards) if awards is not None else None
        players.append(row)
    if len({p["user_id"] for p in players}) != len(players):
        seen, unique = set(), []
        for p in players:  # one row per account (a report already sums slots; a repeat would break the primary key)
            if p["user_id"] not in seen:
                seen.add(p["user_id"])
                unique.append(p)
        players = unique
    teams = data.get("teams") if isinstance(data.get("teams"), dict) else {}
    complete = data.get("events_complete")
    match_awards = _match_awards(data.get("awards"))
    if match_awards is None and any(p["awards"] is not None for p in players):
        # only the players carry the award list (an older report shape): rebuild the cards from it, without values
        match_awards = [{"award": a, "stat": "", "value": None, "user_id": p["user_id"], "name": p["name"], "team": p["team"]}
                        for p in players for a in json.loads(p["awards"])]
    return {
        "session_id": session_id.upper(), "map": MAPS.get(raw_map, raw_map.removeprefix("mpl_combat_") or "unknown"),
        "started_at": started, "ended_at": ended or started, "duration_s": _number(data.get("duration_s")),
        "has_events": any(p["shots"] is not None for p in players),
        "events_complete": complete if isinstance(complete, bool) else None,
        "teams": json.dumps({t: {k: _number(v) for k, v in teams[t].items() if isinstance(v, (int, float))}
                             for t in ("blue", "orange") if isinstance(teams.get(t), dict)}),
        "awards": json.dumps(match_awards) if match_awards is not None else None,
        "players": players,
    }


def save_report(db, file_id: int, parsed: dict) -> None:
    """Replace the file's match with the parsed report. Caller commits."""
    db.execute(delete(CombatMatch).where((CombatMatch.file_id == file_id) | (CombatMatch.session_id == parsed["session_id"])))
    db.flush()
    match = CombatMatch(file_id=file_id, **{k: v for k, v in parsed.items() if k != "players"})
    db.add(match)
    db.flush()
    db.add_all(CombatPlayer(match_id=match.id, **p) for p in parsed["players"])


def _process(sessions: sessionmaker, root: Path, rel: str, size: int, mtime: float) -> bool:
    """Read one report and save it. False = it failed (kept as a failed row, retried when the file changes)."""
    try:
        parsed, error = parse_report(root / rel), None
    except CombatFileError as e:
        parsed, error = None, str(e)
    with sessions() as db:
        row = db.scalar(select(CombatFile).where(CombatFile.source_path == rel))
        if row is None:
            row = CombatFile(source_path=rel, size_bytes=size, source_mtime=mtime, status="queued")
            db.add(row)
        row.size_bytes, row.source_mtime, row.processed_at, row.parser_version = size, mtime, utcnow(), COMBAT_VERSION
        try:
            db.flush()
            db.execute(delete(CombatMatch).where(CombatMatch.file_id == row.id))
            if parsed:
                save_report(db, row.id, parsed)
            row.status, row.error_message = ("done", None) if parsed else ("failed", error)
            db.commit()
        except OperationalError as e:
            # database busy / locked: nothing is wrong with the report; it is not recorded, so the next scan reads it
            # again (Review BUG-1 / BUG-3)
            db.rollback()
            log.warning("Saving combat report %s postponed, the database was busy: %s", rel, str(e).splitlines()[0][:160])
            return False
        except Exception as e:  # noqa: BLE001 - one bad report never stops the others
            db.rollback()
            log.exception("Saving combat report %s failed", rel)
            with sessions() as db2:
                failed = db2.scalar(select(CombatFile).where(CombatFile.source_path == rel))
                if failed is None:
                    failed = CombatFile(source_path=rel, size_bytes=size, source_mtime=mtime, status="failed")
                    db2.add(failed)
                failed.status, failed.error_message = "failed", f"Save failed: {e}"
                failed.size_bytes, failed.source_mtime, failed.parser_version, failed.processed_at = size, mtime, COMBAT_VERSION, utcnow()
                db2.commit()
            return False
    return parsed is not None


def sync_once(sessions: sessionmaker, settings: Settings, state: CombatState) -> int:
    """Look at the report folder and read every new or changed report. Returns how many were read."""
    root = settings.combat_dir
    folder = root / FOLDER
    try:
        if not folder.is_dir():
            state.reachable, state.error = False, f"Combat folder not reachable: {folder}"
            return 0
        now = time.time()
        found: dict[str, tuple[int, float]] = {}
        settling = 0
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.name.lower().endswith(".json") or not entry.is_file():
                    continue
                try:
                    st = entry.stat()
                except FileNotFoundError:
                    continue
                if settings.settle_s and now < max(st.st_mtime, getattr(st, "st_birthtime", st.st_ctime)) + settings.settle_s:
                    settling += 1  # still being written / copied: a later scan reads it
                    continue
                found[f"{FOLDER}/{entry.name}"] = (st.st_size, st.st_mtime)
        with sessions() as db:
            known = {path: (size, mtime, version) for path, size, mtime, version in db.execute(
                select(CombatFile.source_path, CombatFile.size_bytes, CombatFile.source_mtime, CombatFile.parser_version))}
        todo = [(rel, size, mtime) for rel, (size, mtime) in found.items()
                if known.get(rel) != (size, mtime, COMBAT_VERSION)]
        failed = 0
        for rel, size, mtime in sorted(todo, key=lambda t: -t[2]):  # newest first, like the replays
            failed += not _process(sessions, root, rel, size, mtime)
        state.reachable, state.error = True, None
        state.files, state.settling, state.read, state.failed = len(found), settling, len(todo), failed
        return len(todo)
    except OSError as e:
        log.warning("Scan of %s failed: %s", folder, e)
        state.reachable, state.error = False, f"Scan failed: {e}"
        return 0
    finally:
        state.last_scan_at = utcnow()


class CombatIngest:
    """Checks the report folder every `combat_scan_s` (one stat of the folder in between; a full listing when its modified
    time changed or every few minutes)."""

    FULL_EVERY_S = 300.0

    def __init__(self, sessions: sessionmaker, settings: Settings, on_saved=None):
        self.sessions, self.settings, self.on_saved = sessions, settings, on_saved
        self.state = CombatState()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="combat-ingest", daemon=True)

    def start(self) -> None:
        if self.settings.combat_scan_s > 0:
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()

    def _run(self) -> None:
        folder = self.settings.combat_dir / FOLDER
        last_full, last_mtime = 0.0, None
        while not self._stop.is_set():
            try:
                mtime = folder.stat().st_mtime_ns if folder.is_dir() else None
            except OSError:
                mtime = None
            if mtime != last_mtime or time.monotonic() - last_full >= self.FULL_EVERY_S or self.state.settling:
                try:
                    if sync_once(self.sessions, self.settings, self.state) and self.on_saved:
                        self.on_saved()
                except Exception:  # noqa: BLE001
                    log.exception("Combat scan failed")
                last_full, last_mtime = time.monotonic(), mtime
            self._stop.wait(self.settings.combat_scan_s)
