import io
import zipfile
from pathlib import Path

import pytest
import replay_factory as rf

from parser import CorruptReplay, IncompleteReplay, UnsupportedReplay, open_replay

SAMPLES = Path(__file__).resolve().parents[1] / "sample-replays"


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "r.echoreplay"
    path.write_bytes(content)
    return path


def parse_all(path: Path, **kwargs):
    replay = open_replay(path, **kwargs)
    return replay, list(replay.frames())


@pytest.mark.parametrize("make", [rf.plain, rf.zipped])
def test_parses_plain_and_zip(tmp_path, make):
    replay, frames = parse_all(write(tmp_path, make(rf.lines(5))))
    assert replay.meta.container == ("zip" if make is rf.zipped else "plain")
    assert replay.meta.map_code == "mpl_combat_dyson"
    assert replay.meta.started_at == rf.START
    assert replay.frame_count == len(frames) == 5
    assert replay.warnings == []
    first = frames[0]
    assert [p.user_id for p in first.blue] == [str(rf.BIG_USER_ID)]  # exact, no float rounding
    assert first.orange[0].name == "Other"
    assert first.blue[0].velocity == (3.0, 0.0, 4.0)
    assert first.orange_points == 10.0 and first.payload is None


def test_payload_fields(tmp_path):
    _, frames = parse_all(write(tmp_path, rf.plain(rf.lines(2, payload=True))))
    assert frames[0].payload.distance == 12.5
    assert frames[0].game_timer == 170.0
    assert frames[0].blue_points is None


def test_old_converter_timestamp_format(tmp_path):
    _, frames = parse_all(write(tmp_path, rf.plain(rf.lines(2, stamp_format="%Y/%m/%d %H:%M:%S.%f"))))
    assert frames[0].timestamp == rf.START


def test_older_loadout_key_names(tmp_path):
    p = rf.player()
    p["Ability"], p["Grenade"] = p.pop("TacMod"), p.pop("Ordnance")
    lines = rf.lines(2, teams=[{"players": [p]}, {}, {}])
    _, frames = parse_all(write(tmp_path, rf.plain(lines)))
    assert (frames[0].blue[0].tacmod, frames[0].blue[0].ordnance) == ("heal", "det")


def test_empty_team_has_no_players_key(tmp_path):
    lines = rf.lines(2, teams=[{"team": "BLUE TEAM"}, {"team": "ORANGE TEAM"}, {"team": "SPECTATORS"}])
    _, frames = parse_all(write(tmp_path, rf.plain(lines)))
    assert frames[0].blue == [] and frames[0].orange == []


def test_arena_is_unsupported(tmp_path):
    with pytest.raises(UnsupportedReplay, match="Echo_Arena"):
        open_replay(write(tmp_path, rf.plain(rf.lines(2, match_type="Echo_Arena"))))


def test_truncated_last_line_is_a_warning(tmp_path):
    lines = rf.lines(4)
    lines[-1] = lines[-1][:40]
    replay, frames = parse_all(write(tmp_path, rf.plain(lines)))
    assert len(frames) == 3
    assert replay.warnings == ["Last line is truncated (recording was cut off); ignored"]


def test_few_bad_lines_are_skipped_with_warning(tmp_path):
    lines = rf.lines(20)
    lines[5] = "garbage"
    replay, frames = parse_all(write(tmp_path, rf.plain(lines)))
    assert len(frames) == 19
    assert replay.warnings == ["1 unreadable line(s) skipped"]


def test_many_bad_lines_are_corrupt(tmp_path):
    lines = rf.lines(1) + ["garbage"] * 20 + rf.lines(2)
    with pytest.raises(CorruptReplay, match="Too many unreadable lines"):
        parse_all(write(tmp_path, rf.plain(lines)))


def test_unreadable_first_frame_is_corrupt(tmp_path):
    with pytest.raises(CorruptReplay, match="First frame"):
        open_replay(write(tmp_path, rf.plain(["2026-10-28 20:45:44.1\tnot json"] + rf.lines(2))))


def test_single_frame_is_incomplete(tmp_path):
    with pytest.raises(IncompleteReplay):
        parse_all(write(tmp_path, rf.plain(rf.lines(1))))


def test_damaged_zip_is_corrupt(tmp_path):
    content = rf.zipped(rf.lines(50))
    with pytest.raises(CorruptReplay, match="Damaged zip"):
        parse_all(write(tmp_path, content[: len(content) // 2]))


def test_zip_without_replay_entry_is_corrupt(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("images/image.png", b"x")
    with pytest.raises(CorruptReplay, match="no .echoreplay entry"):
        open_replay(write(tmp_path, buf.getvalue()))


def test_uncompressed_size_limit(tmp_path):
    with pytest.raises(CorruptReplay, match="exceeds"):
        parse_all(write(tmp_path, rf.zipped(rf.lines(50))), max_uncompressed_bytes=1024)


@pytest.mark.parametrize("name", sorted(p.name for p in SAMPLES.glob("*.echoreplay")))
def test_real_samples_parse(name):
    replay, frames = parse_all(SAMPLES / name)
    assert replay.meta.match_type == "Echo_Combat"
    assert replay.frame_count > 1000 and replay.warnings == []
    assert any(f.blue or f.orange for f in frames)
    assert (frames[-1].payload is not None) == ("fission" in name or "surge" in name)


@pytest.mark.parametrize("raw", [
    b'2026-10-28 20:45:44.123\t{"a": 1.5, "b": "\xc3\xa9", "c": [1, 2e3, null, true]}\n',
    b'2026/10/28 20:45:44\t{"n": NaN, "i": -Infinity}\n',  # orjson refuses NaN: falls back to json
    # user id beyond 64 bits: orjson would make it a float
    b'2026-10-28 20:45:44.5\t{"teams": [{"players": [{"userid": 123456789012345678901234567890}]}, {}]}\n',
    b'2026-10-28 20:45:44.5\t{"teams": [{"players": [{"userid": 18446744073709551615}]}]}\n',  # u64 max
    b'2026-10-28 20:45:44.5\t{"s": "\ud800"}\n',  # lone surrogate
    b' 2026-1-28 20:45:44.5 \t{}',  # 1-digit month: strptime path
])
def test_fast_json_path_matches_json(raw):
    from parser.frames import split_line, split_raw

    assert split_raw(raw) == split_line(raw.decode("utf-8"))


@pytest.mark.parametrize("raw, error", [
    (b'2026-10-28 20:45:44\t[1, 2]', TypeError), (b'2026-10-28 20:45:44\t{"a": "\xff"}', ValueError),
    (b'2026-10-28 20:45:44\t{"a": ', ValueError), (b'2026-13-28 20:45:44\t{}', ValueError),
])
def test_fast_json_path_rejects_the_same_lines(raw, error):
    from parser.frames import split_line, split_raw

    with pytest.raises(error):
        split_line(raw.decode("utf-8"))  # the old path: decode, then json
    with pytest.raises(error):
        split_raw(raw)


def test_chunked_lines_match_file_iteration():
    import random

    from parser.reader import _chunk_lines

    rng = random.Random(3)
    for _ in range(500):
        data = bytes(rng.choice(b"ab\n\r\t") for _ in range(rng.randint(0, 60)))
        for size in (1, 2, 5, 64):
            assert list(_chunk_lines(io.BytesIO(data), size)) == list(io.BytesIO(data))
