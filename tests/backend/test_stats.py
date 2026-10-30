import json
import sqlite3
from pathlib import Path

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings, replay_by_path, sync, write

from backend import admin_actions as actions
from sqlalchemy import func, select

from backend.db import open_db
from backend.models import Event, Match, MatchPlayer, MatchPlayerLoadout, Player, Replay
from backend.stats import compute
from parser import open_replay

SAMPLES = Path(__file__).resolve().parents[1] / "sample-replays"


def stats_for(tmp_path, text_lines):
    path = tmp_path / "r.echoreplay"
    path.write_bytes(rf.plain(text_lines))
    replay = open_replay(path)
    return compute(replay.meta, replay.frames())


def test_match_fields_capture_point(tmp_path):
    lines = rf.lines(20) + rf.lines(1, blue_round_score=2, orange_round_score=1, contested=True)
    s = stats_for(tmp_path, lines)
    assert (s.map, s.mode, s.frame_count) == ("dyson", "capture_point", 21)
    assert s.duration_s == pytest.approx(0.0)  # rf.lines restarts timestamps per call
    assert (s.blue_rounds, s.orange_rounds, s.winner) == (2, 1, "blue")
    assert s.final_orange_points == 10.0 and s.final_payload_distance is None


def test_payload_mode_has_no_winner(tmp_path):
    s = stats_for(tmp_path, rf.lines(40, payload=True))
    assert (s.map, s.mode, s.winner) == ("surge", "payload", None)
    assert s.final_payload_checkpoint == 1 and s.final_payload_distance == 12.5
    assert s.duration_s == pytest.approx(39 / 20)
    assert s.frame_rate_hz == pytest.approx(40 / (39 / 20), rel=1e-3)


def test_presence_and_left_early(tmp_path):
    # Player 42 (orange) is only in the first 2 s of a 60 s match.
    lines = rf.lines(1200)
    without_orange = json.dumps(rf.frame(teams=[{"players": [rf.player()]}, {}, {}]))
    lines = lines[:40] + [line.split("\t")[0] + "\t" + without_orange for line in lines[40:]]
    s = stats_for(tmp_path, lines)
    by_id = {p.user_id: p for p in s.players}
    blue, orange = by_id[str(rf.BIG_USER_ID)], by_id["42"]
    assert (blue.team, orange.team) == ("blue", "orange")
    assert blue.frames_present == 1200 and orange.frames_present == 40
    assert blue.play_time_s == pytest.approx(1199 / 20)
    assert orange.last_frame == 39
    assert not blue.left_early and orange.left_early


def test_presence_events(tmp_path):
    lines = rf.lines(1200)
    without_orange = json.dumps(rf.frame(teams=[{"players": [rf.player()]}, {}, {}]))
    lines = [line.split("\t")[0] + "\t" + without_orange for line in lines[:10]] + lines[10:40] + \
            [line.split("\t")[0] + "\t" + without_orange for line in lines[40:]]
    events = [(e.type, e.frame, e.user_id) for e in stats_for(tmp_path, lines).events
              if e.type in ("player_join", "player_leave")]
    assert events == [("player_join", 10, "42"), ("player_leave", 39, "42")]


def _pose(position, up=(0.0, 1.0, 0.0)):
    return {"position": list(position), "forward": [0, 0, 1], "left": [1, 0, 0], "up": list(up)}


def scripted_match() -> list[dict]:
    """100 frames (5 s) on dyson. Blue: in bounds 0-39 at 5 m/s, out of bounds 40-59 (death),
    back 60-99 stopped with a blaster, upside down 60-79. Orange stays 1.4 m away."""
    frames = []
    for i in range(100):
        blue = rf.player()
        out = 40 <= i < 60
        blue["head"] = _pose((200.0, 0.0, 0.0) if out else (0.0, 0.0, 0.0))
        blue["body"] = _pose((0.0, 0.0, 0.0), up=(0.0, -1.0, 0.0) if 60 <= i < 80 else (0.0, 1.0, 0.0))
        blue["velocity"] = [3.0, 0.0, 4.0] if i < 40 else [0.0, 0.0, 0.0]
        if i >= 60:
            blue["Weapon"] = "blaster"
        orange = rf.player(42, "Other", 1)
        orange["head"] = _pose((1.0, 0.0, 1.0))
        frames.append(rf.frame(
            teams=[{"players": [blue]}, {"players": [orange]}, {}],
            contested=10 <= i < 20,
            blue_round_score=1 if i >= 50 else 0,
        ))
    return frames


def test_movement_and_bounds_stats(tmp_path):
    s = stats_for(tmp_path, rf.lines_from(scripted_match()))
    by_id = {p.user_id: p for p in s.players}
    blue, orange = by_id[str(rf.BIG_USER_ID)], by_id["42"]

    assert (blue.frames_present, blue.frames_in_bounds, blue.deaths_est) == (100, 80, 1)
    assert (blue.ping_sum, blue.ping_frames) == (6000, 100)  # ping counts out of bounds too
    assert blue.speed_sum == pytest.approx(40 * 5.0)
    assert blue.top_speed == pytest.approx(5.0)
    assert (blue.frames_stopped, blue.frames_upside_down) == (40, 20)
    assert (blue.frames_near_mate, blue.frames_near_enemy) == (0, 80)
    assert (blue.frames_right_arm, blue.frames_left_arm) == (80, 0)
    assert blue.loadouts == {("assault", "heal", "det"): 40, ("blaster", "heal", "det"): 40}

    assert (orange.frames_in_bounds, orange.deaths_est, orange.frames_near_enemy) == (100, 0, 80)
    assert orange.top_speed == pytest.approx(5.0)


def test_timeline_events(tmp_path):
    events = stats_for(tmp_path, rf.lines_from(scripted_match())).events
    blue_id = str(rf.BIG_USER_ID)
    summary = [(e.type, e.frame) for e in events if e.user_id in (blue_id, None)]
    assert summary == [
        ("loadout_change", 0),
        ("contest_start", 10),
        ("contest_end", 20),
        ("death_est", 40),
        ("round_won", 50),
        ("respawn", 60),
        ("loadout_change", 60),
    ]
    death = next(e for e in events if e.type == "death_est")
    assert death.data == {"x": 0.0, "z": 0.0} and death.team == "blue"
    assert death.t_s == pytest.approx(2.0)
    won = next(e for e in events if e.type == "round_won")
    assert won.team == "blue" and won.data == {"blue": 1, "orange": 0}


def test_top_speed_needs_a_full_second(tmp_path):
    # One 30 m/s spike frame must not become the top speed.
    frames = []
    for i in range(60):
        p = rf.player()
        p["velocity"] = [30.0, 0.0, 0.0] if i == 30 else [2.0, 0.0, 0.0]
        frames.append(rf.frame(teams=[{"players": [p]}, {}, {}]))
    s = stats_for(tmp_path, rf.lines_from(frames))
    assert s.players[0].top_speed == pytest.approx(2.0)


def test_unknown_map_counts_all_frames_in_bounds(tmp_path):
    frames = scripted_match()
    for f in frames:
        f["map_name"] = "mpl_combat_new"
    s = stats_for(tmp_path, rf.lines_from(frames))
    blue = next(p for p in s.players if p.team == "blue")
    assert s.map == "unknown"
    assert (blue.frames_in_bounds, blue.deaths_est) == (100, 0)


def test_saved_rows_include_loadouts_and_events(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines_from(scripted_match()))})
        assert replay_by_path(client, "dyson/a.echoreplay")["status"] == "done"
        with client.app.state.sessionmaker() as db:
            assert db.scalar(select(func.count()).select_from(MatchPlayerLoadout)) == 3
            death = db.scalar(select(Event).where(Event.type == "death_est"))
            assert death.player_id is not None and json.loads(death.data) == {"x": 0.0, "z": 0.0}


def test_reprocess_replaces_match(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        add(client, {"dyson/a.echoreplay": rf.zipped(rf.lines(30))})
        rid = replay_by_path(client, "dyson/a.echoreplay")["id"]
        act(client, actions.reprocess, rid)
        client.app.state.worker.wait_idle()
        replay = client.get(f"/api/replays/{rid}").json()
        with client.app.state.sessionmaker() as db:
            assert db.scalar(select(func.count()).select_from(Match)) == 1
            assert db.scalar(select(func.count()).select_from(Player)) == 2
            names = sorted(db.scalars(select(MatchPlayer.name)))
    assert replay["status"] == "done" and replay["match_id"]
    assert names == ["Other", "Player"]


def test_failed_reprocess_removes_old_match(tmp_path):
    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        add(client, {"dyson/a.echoreplay": rf.plain(rf.lines(5))})
        write(settings, {"dyson/a.echoreplay": rf.plain(rf.lines(1))})  # file changes: now incomplete
        sync(client)
        replay = replay_by_path(client, "dyson/a.echoreplay")
        assert client.get("/api/matches").json()["total"] == 0
    assert replay["status"] == "failed" and replay["error_code"] == "incomplete"
    assert replay["match_id"] is None and replay["stats_version"] is None


@pytest.mark.parametrize("name", sorted(p.name for p in SAMPLES.glob("*.echoreplay")))
def test_real_samples(name):
    replay = open_replay(SAMPLES / name)
    s = compute(replay.meta, replay.frames())
    assert s.mode == ("payload" if "fission" in name else "capture_point")
    assert 18 < s.frame_rate_hz < 21
    assert s.players and all(0 < p.play_time_s <= s.duration_s + 1 for p in s.players)


def payload_match(final_checkpoint: int, final_timer: float) -> list[dict]:
    """Orange (42) pushes for 2 s, blue blocks (contested) for 1 s, then the last frame sets the end state."""
    frames = []
    for i in range(61):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        orange["head"] = _pose((1.0, 0.0, 0.0))  # 1 m from payload
        contested = 40 <= i < 60
        blue["head"] = _pose((0.0, 0.0, 2.0) if contested else (50.0, 0.0, 0.0))
        f = rf.frame(payload=True, teams=[{"players": [blue]}, {"players": [orange]}, {}], contested=contested)
        f["payload"].update(attackers=1, defenders=1 if contested else 0, checkpoint=1)
        f["timers"]["game_timer"] = 100.0
        if i == 60:
            f["payload"]["checkpoint"], f["timers"]["game_timer"] = final_checkpoint, final_timer
        frames.append(f)
    return frames


@pytest.mark.parametrize(("checkpoint", "timer", "winner"), [(3, 50.0, "orange"), (2, 0.0, "blue"), (2, 30.0, None)])
def test_payload_winner(tmp_path, checkpoint, timer, winner):
    s = stats_for(tmp_path, rf.lines_from(payload_match(checkpoint, timer)))
    assert (s.mode, s.attacking_team, s.winner, s.final_game_timer) == ("payload", "orange", winner, timer)


def test_payload_push_and_block_time(tmp_path):
    s = stats_for(tmp_path, rf.lines_from(payload_match(3, 50.0)))
    by_id = {p.user_id: p for p in s.players}
    orange, blue = by_id["42"], by_id[str(rf.BIG_USER_ID)]
    assert orange.payload_push_s == pytest.approx(60 / 20)  # every frame after the first
    assert (orange.payload_block_s, blue.payload_push_s) == (0.0, 0.0)
    assert blue.payload_block_s == pytest.approx(20 / 20)
    checkpoint = next(e for e in s.events if e.type == "payload_checkpoint")
    assert checkpoint.data == {"checkpoint": 3, "time_left_s": 100.0}


def test_capture_point_has_no_payload_fields(tmp_path):
    s = stats_for(tmp_path, rf.lines_from(scripted_match()))
    assert (s.attacking_team, s.final_game_timer) == (None, None)
    assert all(p.payload_push_s == p.payload_block_s == 0 for p in s.players)


def _db_with_one_done_replay(settings):
    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        db.add(Replay(source_path="dyson/a.echoreplay", size_bytes=1, source_mtime=1.0, discovered_at="x",
                      status="done", parser_version="2", stats_version="2"))
        db.commit()
    engine.dispose()


def test_stale_derived_tables_are_rebuilt(tmp_path):
    settings = make_settings(tmp_path)
    _db_with_one_done_replay(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("ALTER TABLE matches DROP COLUMN attacking_team")  # simulate an older schema
    con.commit()
    con.close()

    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        assert db.get(Replay, 1).stats_version is None  # kept, stats will be rebuilt
    cols = [r[1] for r in sqlite3.connect(settings.db_path).execute("PRAGMA table_info(matches)")]
    assert "attacking_team" in cols
    engine.dispose()


def test_stale_replays_table_rebuilds_everything(tmp_path):
    settings = make_settings(tmp_path)
    _db_with_one_done_replay(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("ALTER TABLE replays ADD COLUMN sha256 TEXT")  # e.g. the old upload-era schema
    con.commit()
    con.close()

    engine, sessions = open_db(settings.db_path)
    with sessions() as db:
        assert db.query(Replay).count() == 0  # the scanner rediscovers every file
    engine.dispose()


def test_ping_placeholder_is_excluded(tmp_path):
    frames = []
    for i in range(10):
        p = rf.player()
        p["ping"] = 999 if i < 3 else 50
        frames.append(rf.frame(teams=[{"players": [p]}, {}, {}]))
    player = stats_for(tmp_path, rf.lines_from(frames)).players[0]
    assert (player.ping_sum, player.ping_frames, player.frames_present) == (350, 7, 10)


def test_mode_comes_from_map_for_old_replays(tmp_path):
    # Before ~2022 Q4 payload maps had no `payload` block.
    s = stats_for(tmp_path, rf.lines(5, map_name="mpl_combat_fission"))
    assert (s.map, s.mode, s.winner, s.attacking_team) == ("fission", "payload", None, None)


def test_missing_loadout_fields_are_not_counted(tmp_path):
    frames = []
    for _ in range(5):
        p = rf.player()
        for key in ("Weapon", "TacMod", "Ordnance", "Arm"):
            del p[key]  # 2021-era replays
        frames.append(rf.frame(teams=[{"players": [p]}, {}, {}]))
    s = stats_for(tmp_path, rf.lines_from(frames))
    player = s.players[0]
    assert player.loadouts == {} and player.frames_in_bounds == 5
    assert (player.frames_left_arm, player.frames_right_arm) == (0, 0)
    assert not [e for e in s.events if e.type == "loadout_change"]
