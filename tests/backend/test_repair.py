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
