"""Per-replay position tracks (D11, D18): `data/processed/<replay_id>/tracks.bin`.

Sampled at 2 Hz. Per player: x, z (int16 decimetres), weapon, tacmod and ordnance index (uint8, 255 = none)
and team (uint8: 0 absent, 1 blue, 2 orange) per sample (version 2; version 1 had no tacmod / ordnance). Plus objective series (capture points or payload
distance) for the timeline. ~30 KB per match after zlib; rebuildable from the replay.

File = zlib( uint32 header length | header JSON | player arrays, in header order ); arrays little-endian.
"""

import json
import os
import struct
import threading
import zlib
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

FORMAT_VERSION = 2
HZ = 2
ABSENT, BLUE, ORANGE = 0, 1, 2
TEAM_CODES = {"blue": BLUE, "orange": ORANGE}
NO_WEAPON = 255


@dataclass
class PlayerTrack:
    user_id: str
    x: list[float | None]  # metres, None when absent
    z: list[float | None]
    team: list[str | None]
    weapon: list[str]  # "" when unknown / absent
    tacmod: list[str]
    ordnance: list[str]


@dataclass
class Tracks:
    hz: int
    samples: int
    players: list[PlayerTrack]
    series: dict[str, list[float | None]]  # e.g. blue_points, orange_points, payload_distance


class TrackRecorder:
    """Fed every frame by stats.compute(); keeps the first frame of each 0.5 s slot."""

    def __init__(self, started_at: datetime):
        self.started_at = started_at
        self.samples = 0
        self.players: dict[str, dict[str, list]] = {}
        self.series: dict[str, list] = {"blue_points": [], "orange_points": [], "payload_distance": []}

    def add(self, frame) -> None:
        slot = int((frame.timestamp - self.started_at).total_seconds() * HZ)
        if slot < self.samples:
            return
        while self.samples <= slot:  # gaps: pad as absent / None
            self.samples += 1
            for track in self.players.values():
                for key in ("x", "z", "team"):
                    track[key].append(None)
                for key in ("weapon", "tacmod", "ordnance"):
                    track[key].append("")
            for values in self.series.values():
                values.append(None)
        index = self.samples - 1
        self.series["blue_points"][index] = frame.blue_points
        self.series["orange_points"][index] = frame.orange_points
        self.series["payload_distance"][index] = frame.payload.distance if frame.payload else None
        for team, players in (("blue", frame.blue), ("orange", frame.orange)):
            for p in players:
                track = self.players.get(p.user_id)
                if track is None:
                    track = self.players[p.user_id] = {
                        "x": [None] * self.samples, "z": [None] * self.samples, "team": [None] * self.samples,
                        "weapon": [""] * self.samples, "tacmod": [""] * self.samples, "ordnance": [""] * self.samples,
                    }
                x, _, z = p.head_position
                track["x"][index], track["z"][index] = x, z
                track["team"][index], track["weapon"][index] = team, p.weapon
                track["tacmod"][index], track["ordnance"][index] = p.tacmod, p.ordnance

    def result(self) -> Tracks:
        series = {k: v for k, v in self.series.items() if any(x is not None for x in v)}
        players = [PlayerTrack(uid, t["x"], t["z"], t["team"], t["weapon"], t["tacmod"], t["ordnance"])
                   for uid, t in self.players.items()]
        return Tracks(HZ, self.samples, players, series)


def _dm(value: float | None) -> int:
    if value is None:
        return 0
    return max(-32767, min(32767, round(value * 10)))


def _codes(tracks: Tracks, attr: str) -> list[str]:
    return sorted({c for p in tracks.players for c in getattr(p, attr) if c})


def _indexes(values: list[str], codes: list[str]) -> bytes:
    index = {c: i for i, c in enumerate(codes)}
    return bytes(index.get(v, NO_WEAPON) if v else NO_WEAPON for v in values)


def encode(tracks: Tracks) -> bytes:
    weapons, tacmods, ordnances = _codes(tracks, "weapon"), _codes(tracks, "tacmod"), _codes(tracks, "ordnance")
    header = {
        "version": FORMAT_VERSION, "hz": tracks.hz, "samples": tracks.samples,
        "weapons": weapons, "tacmods": tacmods, "ordnances": ordnances,
        "players": [p.user_id for p in tracks.players],
        "series": {k: [None if v is None else round(v, 2) for v in vals] for k, vals in tracks.series.items()},
    }
    body = bytearray()
    for p in tracks.players:
        body += array("h", (_dm(v) for v in p.x)).tobytes()
        body += array("h", (_dm(v) for v in p.z)).tobytes()
        body += _indexes(p.weapon, weapons)
        body += bytes(TEAM_CODES.get(t, ABSENT) if t else ABSENT for t in p.team)
        body += _indexes(p.tacmod, tacmods)
        body += _indexes(p.ordnance, ordnances)
    head = json.dumps(header, separators=(",", ":")).encode()
    return zlib.compress(struct.pack("<I", len(head)) + head + bytes(body), 6)


def decode(data: bytes) -> tuple[dict, dict[str, dict[str, array | bytes]]]:
    """Returns (header, {user_id: {"x", "z": array('h'), "weapon", "team", "tacmod", "ordnance": bytes}}).
    Version-1 files have no tacmod / ordnance: those come back as 'none' (255)."""
    raw = zlib.decompress(data)
    (length,) = struct.unpack_from("<I", raw)
    header = json.loads(raw[4 : 4 + length])
    n = header["samples"]
    offset = 4 + length
    players = {}
    for user_id in header["players"]:
        x = array("h"); x.frombytes(raw[offset : offset + 2 * n]); offset += 2 * n
        z = array("h"); z.frombytes(raw[offset : offset + 2 * n]); offset += 2 * n
        weapon = raw[offset : offset + n]; offset += n
        team = raw[offset : offset + n]; offset += n
        if header.get("version", 1) >= 2:
            tacmod = raw[offset : offset + n]; offset += n
            ordnance = raw[offset : offset + n]; offset += n
        else:
            tacmod = ordnance = bytes([NO_WEAPON]) * n
        players[user_id] = {"x": x, "z": z, "weapon": weapon, "team": team, "tacmod": tacmod, "ordnance": ordnance}
    header.setdefault("tacmods", [])
    header.setdefault("ordnances", [])
    return header, players


def tracks_path(processed_dir: Path, replay_id: int) -> Path:
    return processed_dir / str(replay_id) / "tracks.bin"


def write(path: Path, tracks: Tracks) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(encode(tracks))
    os.replace(tmp, path)


# Decoded tracks kept in RAM (D49): player heatmaps read up to 5000 files per request. Least recently used first
# out once over the limit; keyed on the file's mtime + size, so a reprocessed replay is read again. Callers never
# change what read() returns, so one decoded copy is shared.
_cache: OrderedDict = OrderedDict()  # path -> (mtime_ns, size, cost, decoded)
_cache_lock = threading.Lock()
_cache_limit = 0
_cache_used = 0


def set_cache_limit(mb: int) -> None:
    """0 = no cache (the default, and the tests)."""
    global _cache_limit, _cache_used
    with _cache_lock:
        _cache_limit = max(0, mb) * 1024 * 1024
        _cache.clear()
        _cache_used = 0


def _cost(header: dict, players: dict) -> int:
    """Bytes in RAM, roughly: the arrays plus a flat allowance for the header JSON."""
    return 4096 + sum(len(t["x"]) * 4 + sum(len(t[k]) for k in ("weapon", "team", "tacmod", "ordnance"))
                      for t in players.values())


def read(path: Path) -> tuple[dict, dict] | None:
    global _cache_used
    if not _cache_limit:
        try:
            return decode(path.read_bytes())
        except FileNotFoundError:
            return None
    key = str(path)
    try:
        st = path.stat()
    except FileNotFoundError:
        with _cache_lock:
            if (gone := _cache.pop(key, None)) is not None:
                _cache_used -= gone[2]
        return None
    with _cache_lock:
        hit = _cache.get(key)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            _cache.move_to_end(key)
            return hit[3]
    try:
        decoded = decode(path.read_bytes())
    except FileNotFoundError:
        return None
    cost = _cost(*decoded)
    with _cache_lock:
        if (old := _cache.pop(key, None)) is not None:
            _cache_used -= old[2]
        if cost <= _cache_limit:
            _cache[key] = (st.st_mtime_ns, st.st_size, cost, decoded)
            _cache_used += cost
            while _cache_used > _cache_limit:
                _cache_used -= _cache.popitem(last=False)[1][2]
    return decoded
