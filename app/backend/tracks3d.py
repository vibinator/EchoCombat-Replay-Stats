"""Per-replay 3D tracks for 3D playback (docs/WebReplayer-Review.MD, Phase 2): `data/processed/<replay_id>/tracks3d.bin`.

Sampled at 5 Hz (the 2 Hz tracks.bin is too coarse for 3D). Per player and sample:
- x, y, z: head position, int16 decimetres;
- yaw: uint8, 256 steps (1.4 degrees), 0 = facing +z, increasing towards +x (atan2(forward.x, forward.z));
- pitch: int8 degrees, + = looking up;
- team: uint8 (0 absent, 1 blue, 2 orange).
The header also holds the payload cart position per sample ([x, y, z] in metres, 1 decimal, or null), for payload maps.

File = zlib( uint32 header length | header JSON | per player: x, y, z (int16) | yaw (uint8) | pitch (int8) | team (uint8) ),
little-endian, players in header order. About 9 bytes per player per sample before zlib. Rebuildable from the replay.
Gear and objective series stay in tracks.bin (2 Hz); this file only adds what the 3D view needs.
"""

import json
import math
import os
import struct
import zlib
from array import array
from datetime import datetime
from pathlib import Path

from .stats.maps import is_load_in
from .tracks import ABSENT, TEAM_CODES, _dm

FORMAT_VERSION = 1
HZ = 5


def yaw_code(forward) -> int:
    fx, _, fz = forward
    return round(math.atan2(fx, fz) / (2 * math.pi) * 256) % 256


def pitch_code(forward) -> int:
    fy = max(-1.0, min(1.0, forward[1]))
    return max(-90, min(90, round(math.degrees(math.asin(fy)))))


class Track3DRecorder:
    """Fed every frame by stats.compute() (through Recorders); keeps the first frame of each 0.2 s slot."""

    def __init__(self, started_at: datetime, load_in=None):
        self.started_at = started_at
        self.load_in = load_in
        self.samples = 0
        self.players: dict[str, dict[str, list]] = {}
        self.payload: list = []

    def add(self, frame) -> None:
        slot = int((frame.timestamp - self.started_at).total_seconds() * HZ)
        if slot < self.samples:
            return
        while self.samples <= slot:  # gaps: pad as absent
            self.samples += 1
            for track in self.players.values():
                for key in ("x", "y", "z", "yaw", "pitch"):
                    track[key].append(0)
                track["team"].append(ABSENT)
            self.payload.append(None)
        index = self.samples - 1
        if frame.payload is not None:
            self.payload[index] = [round(v, 1) for v in frame.payload.position]
        for team, players in (("blue", frame.blue), ("orange", frame.orange)):
            for p in players:
                if is_load_in(p.head_position, self.load_in):
                    continue  # parked at the load-in spot: absent, as in tracks.bin
                track = self.players.get(p.user_id)
                if track is None:
                    track = self.players[p.user_id] = {k: [0] * self.samples for k in ("x", "y", "z", "yaw", "pitch")}
                    track["team"] = [ABSENT] * self.samples
                x, y, z = p.head_position
                track["x"][index], track["y"][index], track["z"][index] = _dm(x), _dm(y), _dm(z)
                track["yaw"][index], track["pitch"][index] = yaw_code(p.head_forward), pitch_code(p.head_forward)
                track["team"][index] = TEAM_CODES[team]

    def encode(self) -> bytes:
        header = {"version": FORMAT_VERSION, "hz": HZ, "samples": self.samples, "players": list(self.players)}
        if any(v is not None for v in self.payload):
            header["payload"] = self.payload
        body = bytearray()
        for t in self.players.values():
            for key in ("x", "y", "z"):
                body += array("h", t[key]).tobytes()
            body += bytes(t["yaw"])
            body += array("b", t["pitch"]).tobytes()
            body += bytes(t["team"])
        head = json.dumps(header, separators=(",", ":")).encode()
        return zlib.compress(struct.pack("<I", len(head)) + head + bytes(body), 6)


class Recorders:
    """Several recorders fed from the one pass over the frames that stats.compute() makes."""

    def __init__(self, *recorders):
        self.recorders = recorders

    def add(self, frame) -> None:
        for r in self.recorders:
            r.add(frame)


def decode(data: bytes) -> tuple[dict, dict[str, dict[str, array | bytes]]]:
    """Returns (header, {user_id: {"x", "y", "z": array('h'), "yaw": bytes, "pitch": array('b'), "team": bytes}})."""
    raw = zlib.decompress(data)
    (length,) = struct.unpack_from("<I", raw)
    header = json.loads(raw[4 : 4 + length])
    n = header["samples"]
    offset = 4 + length
    players = {}
    for user_id in header["players"]:
        t = {}
        for key in ("x", "y", "z"):
            t[key] = array("h"); t[key].frombytes(raw[offset : offset + 2 * n]); offset += 2 * n
        t["yaw"] = raw[offset : offset + n]; offset += n
        t["pitch"] = array("b"); t["pitch"].frombytes(raw[offset : offset + n]); offset += n
        t["team"] = raw[offset : offset + n]; offset += n
        players[user_id] = t
    return header, players


def tracks3d_path(processed_dir: Path, replay_id: int) -> Path:
    return processed_dir / str(replay_id) / "tracks3d.bin"


def write(path: Path, recorder: Track3DRecorder) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp3d")
    tmp.write_bytes(recorder.encode())
    os.replace(tmp, path)


def read(path: Path) -> tuple[dict, dict] | None:
    try:
        return decode(path.read_bytes())
    except FileNotFoundError:
        return None
