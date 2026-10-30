"""Raw line / JSON -> typed frame. Raises ValueError, KeyError or TypeError for a bad line."""

import json
import re
from datetime import datetime

try:  # 3-4x faster than json; optional, json gives the same result
    import orjson
except ImportError:  # pragma: no cover
    orjson = None

from .models import Frame, PayloadState, PlayerFrame, ReplayMeta, Vec3

# Older API sent hex symbols instead of loadout codes (old skims.py table). Normalised here so every stat,
# achievement and leaderboard compares one code per item.
HEX_CODES = {
    "0x2FD69C8C5F615B9E": "assault",
    "0x2FD5839E4D605298": "blaster",
    "0xE32DC7C9DA8051A4": "scout",
    "0x41D2D5321928020A": "rocket",
    "0xC8E8D0B1A894E7FE": "det",
    "0xC8C33E4829670BBE": "stun",
    "0xC8E8D0B1A891F0E9": "arc",
    "0xE32DC7D8CC9D57A4": "burst",
    "0xC8C33E4832761FBC": "heal",
    "0x41D2D4381430080C": "sensor",
    "0x41D2D43513260B1A": "shield",
    "0x41D2D02F1B2A1316": "wraith",
}


def gear_code(value) -> str:
    """Loadout code as text; hex symbols of the older API -> their code (unknown symbols kept as they are)."""
    code = str(value or "")
    if code[:2].lower() == "0x":
        return HEX_CODES.get("0x" + code[2:].upper(), code)
    return code


TIMESTAMP_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S")


# Fast path for the usual stamp; anything else (1-digit fields etc.) goes through strptime as before.
_TIMESTAMP = re.compile(r"([0-9]{4})([-/])([0-9]{2})\2([0-9]{2}) ([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,6}))?")


def parse_timestamp(text: str) -> datetime:
    m = _TIMESTAMP.fullmatch(text)
    if m:
        year, _, month, day, hour, minute, second, fraction = m.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second),
                            int(fraction.ljust(6, "0")) if fraction else 0)
        except ValueError:
            pass
    for fmt in TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    raise ValueError(f"bad timestamp {text!r}")


def split_line(line: str) -> tuple[datetime, dict]:
    stamp, _, body = line.partition("\t")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise TypeError("frame is not a JSON object")
    return parse_timestamp(stamp.strip()), data


def split_raw(raw: bytes) -> tuple[datetime, dict]:
    """split_line(raw.decode("utf-8")) without decoding the line first. orjson refuses a few things json accepts
    (NaN, lone surrogates): those lines go through split_line, so the result is the same. orjson turns integers
    beyond 64 bits into floats instead; only the user id must stay exact (other such values would be nonsense
    either way), so a float user id also goes through split_line."""
    if orjson is None:
        return split_line(raw.decode("utf-8"))
    stamp, _, body = raw.partition(b"\t")
    try:
        data = orjson.loads(body)
    except orjson.JSONDecodeError:
        return split_line(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise TypeError("frame is not a JSON object")
    if _float_user_id(data):
        return split_line(raw.decode("utf-8"))
    return parse_timestamp(stamp.decode("utf-8").strip()), data


def _float_user_id(data: dict) -> bool:
    teams = data.get("teams")
    if type(teams) is not list:
        return False
    for team in teams:
        if type(team) is dict:
            for p in team.get("players") or ():
                if type(p) is dict and type(p.get("userid")) is float:
                    return True
    return False


def _vec(v) -> Vec3:
    x, y, z = v
    return (float(x), float(y), float(z))


def _player(p: dict) -> PlayerFrame:
    return PlayerFrame(
        user_id=str(p["userid"]),
        name=p.get("name", ""),
        slot=p.get("playerid", -1),
        number=p.get("number", 0),
        level=p.get("level", 0),
        ping=p.get("ping", 0),
        packet_loss=p.get("packetlossratio", 0.0),
        head_position=_vec(p["head"]["position"]),
        body_up=_vec(p["body"]["up"]),
        velocity=_vec(p["velocity"]),
        weapon=gear_code(p.get("Weapon", "")),
        tacmod=gear_code(p.get("TacMod", p.get("Ability", ""))),  # older API: Ability / Grenade
        ordnance=gear_code(p.get("Ordnance", p.get("Grenade", ""))),
        arm=p.get("Arm", ""),
        emote=bool(p.get("is_emote_playing", False)),
    )


def _team(teams: list, i: int) -> list[PlayerFrame]:
    # teams = [BLUE TEAM, ORANGE TEAM, SPECTATORS]; "players" is absent when a team is empty.
    return [_player(p) for p in teams[i].get("players", [])] if i < len(teams) else []


def _payload(d: dict | None) -> PayloadState | None:
    if d is None:
        return None
    return PayloadState(
        position=_vec(d["pos"]),
        checkpoint=d.get("checkpoint", 0),
        distance=d.get("distance", 0.0),
        speed=d.get("speed", 0.0),
        attackers=d.get("attackers", 0),
        defenders=d.get("defenders", 0),
    )


def build_frame(index: int, timestamp: datetime, d: dict) -> Frame:
    teams = d["teams"]
    return Frame(
        index=index,
        timestamp=timestamp,
        blue=_team(teams, 0),
        orange=_team(teams, 1),
        blue_round_score=d.get("blue_round_score", 0),
        orange_round_score=d.get("orange_round_score", 0),
        contested=bool(d.get("contested", False)),
        blue_points=d.get("blue_points"),
        orange_points=d.get("orange_points"),
        payload=_payload(d.get("payload")),
        game_timer=(d.get("timers") or {}).get("game_timer"),
    )


def build_meta(timestamp: datetime, d: dict, container: str) -> ReplayMeta:
    return ReplayMeta(
        session_id=d["sessionid"],
        match_type=d.get("match_type", ""),
        map_code=d.get("map_name", ""),
        private_match=bool(d.get("private_match", False)),
        tournament_match=bool(d.get("tournament_match", False)),
        client_name=d.get("client_name"),
        container=container,
        started_at=timestamp,
    )
