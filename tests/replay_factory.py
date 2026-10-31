"""Builds small synthetic .echoreplay content shaped like the Echo VR /session API."""

import io
import itertools
import json
import zipfile
from datetime import datetime, timedelta

START = datetime(2026, 10, 28, 20, 45, 44, 123456)
SESSION_ID = "BF48D570-ED45-426E-AF95-F0D6A033BF03"
_sessions = itertools.count(1)
BIG_USER_ID = 1324398816765673576  # > 2^53


def player(user_id: int = BIG_USER_ID, name: str = "Player", slot: int = 0) -> dict:
    pose = {"position": [1.0, 2.0, 3.0], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}
    hand = {"pos": [0, 0, 0], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}
    return {
        "name": name, "userid": user_id, "playerid": slot, "number": 7, "level": 30,
        "ping": 60, "packetlossratio": 0.0, "head": pose, "body": pose, "lhand": hand, "rhand": hand,
        "velocity": [3.0, 0.0, 4.0], "Weapon": "assault", "TacMod": "heal", "Ordnance": "det",
        "Arm": "Right", "is_emote_playing": False,
    }


def frame(match_type: str = "Echo_Combat", payload: bool = False, **overrides) -> dict:
    d = {
        "sessionid": SESSION_ID, "sessionip": "0.0.0.0",
        "match_type": match_type, "map_name": "mpl_combat_dyson", "private_match": False,
        "tournament_match": False, "client_name": "Recorder", "blue_round_score": 0,
        "orange_round_score": 0, "total_round_count": 0, "contested": False,
        "teams": [
            {"team": "BLUE TEAM", "players": [player()]},
            {"team": "ORANGE TEAM", "players": [player(42, "Other", 1)]},
            {"team": "SPECTATORS"},
        ],
    }
    if payload:
        d["map_name"] = "mpl_combat_gauss"
        d["payload"] = {"pos": [0, 0, 0], "checkpoint": 1, "distance": 12.5, "speed": 0.5,
                        "attackers": 1, "defenders": 0, "multiplier": 1}
        d["timers"] = {"game_timer": 170.0, "overtime_timer": 0.0}
    else:
        d["blue_points"], d["orange_points"] = 0.0, 10.0
    d.update(overrides)
    return d


def new_session_id() -> str:
    """Each generated file is its own match: all start at START, so one shared id would make them copies (D13)."""
    return f"00000000-0000-4000-8000-{next(_sessions):012d}"


def lines(count: int = 3, stamp_format: str = "%Y-%m-%d %H:%M:%S.%f", start: datetime = START,
          **frame_kwargs) -> list[str]:
    frame_kwargs.setdefault("sessionid", new_session_id())
    return [
        f"{(start + timedelta(seconds=i / 20)).strftime(stamp_format)}\t{json.dumps(frame(**frame_kwargs))}"
        for i in range(count)
    ]


def lines_from(frames: list[dict]) -> list[str]:
    """One line per frame dict, 20 Hz timestamps from START. Frames with the default session id get a new one."""
    session = new_session_id()
    frames = [f | {"sessionid": session} if f.get("sessionid") == SESSION_ID else f for f in frames]
    return [
        f"{(START + timedelta(seconds=i / 20)).strftime('%Y-%m-%d %H:%M:%S.%f')}\t{json.dumps(f)}"
        for i, f in enumerate(frames)
    ]


def plain(text_lines: list[str]) -> bytes:
    return ("\n".join(text_lines) + "\n").encode()


def zipped(text_lines: list[str], extra_png: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("BF48D570.echoreplay", plain(text_lines))
        if extra_png:
            z.writestr("images/image.png", plain(text_lines))
    return buf.getvalue()
