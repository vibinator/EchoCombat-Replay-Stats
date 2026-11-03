"""3D playback tracks (tracks3d.bin): facing codes, encode / decode round trip."""
import math
from datetime import datetime, timedelta

from backend import tracks3d
from parser.models import Frame, PlayerFrame

START = datetime(2026, 10, 1, 12, 0, 0)


def _player(uid, pos, forward, lhand=None, rhand=None):
    return PlayerFrame(uid, "P", 0, 0, 0, 0, 0.0, pos, forward, lhand or pos, rhand or pos, (0.0, 1.0, 0.0), (0.0, 0.0, 0.0),
                       "", "", "", "", False)


def _frame(i, seconds, blue):
    return Frame(i, START + timedelta(seconds=seconds), blue, [], 0, 0, False, None, None, None, None)


def test_facing_codes():
    assert tracks3d.yaw_code((0, 0, 1)) == 0
    assert tracks3d.yaw_code((1, 0, 0)) == 64  # a quarter turn towards +x
    assert tracks3d.yaw_code((0, 0, -1)) == 128
    assert tracks3d.yaw_code((-1, 0, 0)) == 192
    up = (0.0, math.sin(math.radians(30)), math.cos(math.radians(30)))
    assert tracks3d.pitch_code(up) == 30 and tracks3d.pitch_code((0, -1.0000001, 0)) == -90


def test_round_trip_with_gaps_and_absent_players():
    rec = tracks3d.Track3DRecorder(START)
    rec.add(_frame(0, 0.0, [_player("1", (1.25, -2.0, 3.0), (1.0, 0.0, 0.0), lhand=(1.75, -2.4, 3.0), rhand=(9.0, -2.0, 3.0))]))
    rec.add(_frame(1, 0.1, [_player("1", (9.0, 9.0, 9.0), (1.0, 0.0, 0.0))]))  # same 0.2 s slot: ignored
    rec.add(_frame(2, 0.6, [_player("2", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]))  # slot 3; slots 1-2 are gaps
    header, players = tracks3d.decode(rec.encode())
    assert header["hz"] == 5 and header["samples"] == 4 and header["players"] == ["1", "2"] and "payload" not in header
    one, two = players["1"], players["2"]
    assert (one["x"][0], one["y"][0], one["z"][0], one["yaw"][0], one["pitch"][0]) == (12, -20, 30, 64, 0)  # 1.25 -> 12 dm
    assert list(one["team"]) == [1, 0, 0, 0] and list(two["team"]) == [0, 0, 0, 1]
    # hands relative to the head in 2 cm steps; far ones clamp at 127 steps (2.54 m)
    assert [one[k][0] for k in tracks3d.HAND_KEYS] == [25, -20, 0, 127, 0, 0]


def test_version_1_files_read_without_hands():
    import json, struct, zlib
    header = json.dumps({"version": 1, "hz": 5, "samples": 1, "players": ["1"]}).encode()
    body = struct.pack("<hhhBbB", 10, 20, 30, 64, 5, 1)
    header_out, players = tracks3d.decode(zlib.compress(struct.pack("<I", len(header)) + header + body))
    assert players["1"]["x"][0] == 10 and players["1"]["team"][0] == 1 and players["1"]["rz"].tolist() == [0]


def test_roll_codes():
    f = (0.0, 0.0, 1.0)
    assert tracks3d.roll_code(f, (0.0, 1.0, 0.0)) == 0  # upright
    assert tracks3d.roll_code(f, (0.0, -1.0, 0.0)) == 128  # upside down
    # a quarter turn about +z (right-handed): up swings from +y to -x (three.js rotation.z turns +x towards +y)
    assert tracks3d.roll_code(f, (-1.0, 0.0, 0.0)) == 64
    assert tracks3d.roll_code(f, (1.0, 0.0, 0.0)) == 192
    # the same when looking up 30 degrees: tilted forward, upright stays 0, upside down stays 128
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    pitched = (0.0, s, c)
    assert tracks3d.roll_code(pitched, (0.0, c, -s)) == 0
    assert tracks3d.roll_code(pitched, (0.0, -c, s)) == 128
    # straight up has no reference: reads 0; an up that is not square to the facing direction is squared first
    assert tracks3d.roll_code((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)) == 0
    assert tracks3d.roll_code(f, (0.0, -1.0, 0.3)) == 128


def test_roll_round_trip_and_version_3_header():
    rec = tracks3d.Track3DRecorder(START)
    p = _player("1", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    p.head_up = (0.0, -1.0, 0.0)  # upside down
    rec.add(_frame(0, 0.0, [p]))
    data = rec.encode()
    header, players = tracks3d.decode(data)
    assert header["version"] == 3 and players["1"]["roll"][0] == 128


def test_older_files_read_with_zero_roll():
    import json, struct, zlib
    header = json.dumps({"version": 2, "hz": 5, "samples": 1, "players": ["1"]}).encode()
    body = struct.pack("<hhhBbB", 10, 20, 30, 64, 5, 1) + bytes(6)  # version 2: six hand bytes, no roll
    _, players = tracks3d.decode(zlib.compress(struct.pack("<I", len(header)) + header + body))
    assert list(players["1"]["roll"]) == [0]


def test_file_version_reads_only_the_header(tmp_path):
    rec = tracks3d.Track3DRecorder(START)
    rec.add(_frame(0, 0.0, [_player("1", (0.0, 0.0, 0.0), (0.0, 0.0, 1.0))]))
    path = tmp_path / "tracks3d.bin"
    tracks3d.write(path, rec)
    assert tracks3d.file_version(path) == tracks3d.FORMAT_VERSION
    assert tracks3d.file_version(tmp_path / "missing.bin") is None
