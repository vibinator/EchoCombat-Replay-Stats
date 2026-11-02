import io
import zipfile

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings, replay_by_path

from backend import admin_actions as actions

from parser import CorruptReplay, IncompleteReplay, open_replay


def big_zip(frames=400, extra_png=False):
    return rf.zipped(rf.lines(frames), extra_png=extra_png)


def snapshot(root):
    return sorted((str(p.relative_to(root)), p.stat().st_size, p.stat().st_mtime) for p in root.rglob("*"))


def test_truncated_zip_is_salvaged(tmp_path):
    content = big_zip()
    path = tmp_path / "r.echoreplay"
    path.write_bytes(content[: len(content) * 2 // 3])  # cut off: no central directory, partial data
    with pytest.raises(CorruptReplay):
        open_replay(path)
    replay = open_replay(path, repair=True)
    frames = list(replay.frames())
    assert 2 <= len(frames) < 400
    assert replay.warnings[0].startswith("Repaired:") and "later frames lost" in replay.warnings[0]


def test_damaged_central_directory_recovers_everything(tmp_path):
    content = bytearray(big_zip())
    cd = content.rfind(b"PK\x01\x02")
    content[cd : cd + 4] = b"XXXX"  # break the zip index only
    path = tmp_path / "r.echoreplay"
    path.write_bytes(bytes(content))
    with pytest.raises(CorruptReplay):
        open_replay(path)
    replay = open_replay(path, repair=True)
    assert len(list(replay.frames())) == 400


def test_many_bad_lines_and_bad_first_line(tmp_path):
    lines = ["garbage"] * 30 + rf.lines(10) + ["garbage"] * 30 + rf.lines(10)
    path = tmp_path / "r.echoreplay"
    path.write_bytes(rf.plain(lines))
    with pytest.raises(CorruptReplay):
        open_replay(path)
    replay = open_replay(path, repair=True)
    assert len(list(replay.frames())) == 20
    assert any("unreadable line" in w for w in replay.warnings)


def test_nothing_readable_stays_failed(tmp_path):
    path = tmp_path / "r.echoreplay"
    path.write_bytes(b"\n".join([b"garbage"] * 10))
    with pytest.raises(IncompleteReplay):
        open_replay(path, repair=True)


def test_repair_from_admin_console(tmp_path):
    settings = make_settings(tmp_path)
    content = big_zip()
    with app_client(settings) as client:
        add(client, {"dyson/broken.echoreplay": content[: len(content) * 2 // 3],
                     "dyson/arena.echoreplay": rf.plain(rf.lines(5, match_type="Echo_Arena")),
                     "dyson/ok.echoreplay": rf.plain(rf.lines(5))})
        before = snapshot(settings.source_dir)
        broken = replay_by_path(client, "dyson/broken.echoreplay")
        assert broken["status"] == "failed" and broken["error_code"] == "corrupt"

        act(client, actions.repair, broken["id"])
        assert replay_by_path(client, "dyson/broken.echoreplay")["repair_requested"]
        client.app.state.worker.wait_idle()
        repaired = replay_by_path(client, "dyson/broken.echoreplay")
        assert repaired["status"] == "done" and repaired["match_id"]
        assert repaired["warnings"][0].startswith("Repaired:")

        arena = replay_by_path(client, "dyson/arena.echoreplay")
        with pytest.raises(actions.AdminError, match="Only damaged"):
            act(client, actions.repair, arena["id"])
        ok = replay_by_path(client, "dyson/ok.echoreplay")
        with pytest.raises(actions.AdminError, match="processed successfully"):
            act(client, actions.repair, ok["id"])

        # repair stays in effect on later reprocessing
        act(client, actions.reprocess, repaired["id"])
        client.app.state.worker.wait_idle()
        assert replay_by_path(client, "dyson/broken.echoreplay")["status"] == "done"
        assert snapshot(settings.source_dir) == before  # share never modified


def test_repair_all_failed(tmp_path):
    content = big_zip()
    with app_client(make_settings(tmp_path)) as client:
        add(client, {f"dyson/b{i}.echoreplay": content[: len(content) // 2] for i in range(2)})
        assert len(act(client, actions.repair_all_failed)) == 2
        client.app.state.worker.wait_idle()
        assert client.get("/api/import").json()["counts"]["failed"] == 0


# --- aggressive repair (D36b) ---------------------------------------------------------------------

def noisy_lines(count=600, seed=1, **kw):
    """Frames whose positions change every frame: compresses like a real replay (one 4 KB block = many frames)."""
    import random
    rnd = random.Random(seed)
    frames = []
    for _ in range(count):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        for p in (blue, orange):
            p["head"] = dict(p["head"], position=[round(rnd.uniform(-50, 50), 3) for _ in range(3)])
            p["velocity"] = [round(rnd.uniform(-5, 5), 3) for _ in range(3)]
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}], **kw))
    return rf.lines_from(frames)


def entries(content):
    """(local header offset, data start, compressed size) of each zip entry."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        return [(i.header_offset, i.header_offset + 30 + len(i.filename.encode()) + len(i.extra), i.compress_size)
                for i in z.infolist()]


def damage(content, start, size, junk=False):
    import random
    data = bytearray(content)
    data[start : start + size] = bytes(random.Random(start).randrange(256) for _ in range(size)) if junk else bytes(size)
    return bytes(data)


def frame_lines(replay):
    return [f.timestamp for f in replay.frames()]


def test_aggressive_takes_wiped_parts_from_the_second_copy(tmp_path):
    lines = noisy_lines()
    content = rf.zipped(lines)
    (h1, d1, size), (_, d2, _) = entries(content)
    content = damage(content, 0, d1 + size // 3)  # local header and the first third of copy 1 wiped
    content = damage(content, d2 + size * 2 // 3, 2048, junk=True)  # copy 2 damaged elsewhere (foreign data)
    path = tmp_path / "r.echoreplay"
    path.write_bytes(content)
    with pytest.raises((CorruptReplay, IncompleteReplay)):
        list(open_replay(path, repair=True).frames())
    replay = open_replay(path, repair="aggressive")
    assert len(frame_lines(replay)) == len(lines)  # every frame back
    assert replay.warnings[0].startswith("Repaired (aggressive): 600 readable frames")
    assert "second copy" in replay.warnings[0]


def test_aggressive_never_guesses_past_damage_in_both_copies(tmp_path):
    lines = noisy_lines()
    content = rf.zipped(lines)
    (_, d1, size), (_, d2, _) = entries(content)
    for start in (d1, d2):  # the same part of the frames lost in both copies
        content = damage(content, start + size // 2, 4096, junk=start == d2)
    path = tmp_path / "r.echoreplay"
    path.write_bytes(content)
    replay = open_replay(path, repair="aggressive")
    got = [f for f in replay.frames()]
    assert 2 <= len(got) < len(lines)
    original = [f for f in open_replay(_write(tmp_path / "ok.echoreplay", rf.zipped(lines))).frames()]
    assert got == original[: len(got)]  # exactly the frames before the damage, nothing invented
    assert "frames after the damage lost" in replay.warnings[0]


def _write(path, content):
    path.write_bytes(content)
    return path


def test_aggressive_keeps_only_the_replays_own_session(tmp_path):
    ours, theirs = noisy_lines(200, seed=2), noisy_lines(200, seed=3)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:  # another match's data ended up in the file
        z.writestr("a.echoreplay", rf.plain(theirs))
        z.writestr("b.echoreplay", rf.plain(ours))
    session = ours[0].split('"sessionid": "')[1][:36]
    path = tmp_path / f"[2026-10-28 20-45-44] {session}.echoreplay"
    path.write_bytes(damage(buf.getvalue(), 0, 64))
    replay = open_replay(path, repair="aggressive")
    assert replay.meta.session_id == session
    assert len(frame_lines(replay)) == 200


def test_aggressive_repair_from_admin_console(tmp_path):
    content = rf.zipped(noisy_lines())
    _, d1, size = entries(content)[0]
    broken = damage(content, 0, d1 + size // 2)  # header gone: repair mode finds no .echoreplay entry
    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        add(client, {"dyson/broken.echoreplay": broken, "dyson/ok.echoreplay": rf.plain(rf.lines(5))})
        before = snapshot(settings.source_dir)
        replay = replay_by_path(client, "dyson/broken.echoreplay")
        assert replay["status"] == "failed"
        ok = replay_by_path(client, "dyson/ok.echoreplay")
        with pytest.raises(actions.AdminError, match="processed successfully"):
            act(client, actions.repair_aggressive, ok["id"])

        assert act(client, actions.aggressive_failures) == []  # repair mode first
        act(client, actions.repair_all_failed)
        client.app.state.worker.wait_idle()
        assert replay_by_path(client, "dyson/broken.echoreplay")["status"] == "failed"
        with client.app.state.sessionmaker() as db:
            from sqlalchemy import func, select
            from backend.models import Replay
            assert db.scalar(select(func.count()).select_from(Replay).where(actions.unrepairable())) == 0

        assert len(act(client, actions.repair_aggressive_all_failed)) == 1
        client.app.state.worker.wait_idle()
        repaired = replay_by_path(client, "dyson/broken.echoreplay")
        assert repaired["status"] == "done" and repaired["match_id"]
        assert repaired["warnings"][0].startswith("Repaired (aggressive): 600 readable frames")
        assert act(client, actions.aggressive_failures) == []
        assert snapshot(settings.source_dir) == before  # share never modified


def test_repaired_match_says_so(tmp_path):
    content = rf.zipped(noisy_lines())
    _, d1, size = entries(content)[0]
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/broken.echoreplay": damage(content, 0, d1 + size // 2),
                     "dyson/ok.echoreplay": rf.plain(rf.lines(5))})
        assert client.get(f"/api/matches/{replay_by_path(client, 'dyson/ok.echoreplay')['match_id']}").json()["repaired"] is None
        act(client, actions.repair_aggressive, replay_by_path(client, "dyson/broken.echoreplay")["id"])
        client.app.state.worker.wait_idle()
        match = client.get(f"/api/matches/{replay_by_path(client, 'dyson/broken.echoreplay')['match_id']}").json()
        assert match["repaired"] == {"aggressive": True, "frames": 600}
