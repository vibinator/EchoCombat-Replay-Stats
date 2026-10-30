import csv
import io
import json
from collections import Counter
from datetime import timedelta

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

from backend import heatmaps, tracks
from backend.stats.maps import HEATMAP_LAYOUTS

BLUE = str(rf.BIG_USER_ID)


def _pose(x, z):
    return {"position": [x, 0.0, z], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}


def walking_match(blue_points_end=50.0, emote_frames=()):
    """Dyson, 10 s. Blue walks +x at 2 m/s; orange stands still. Blue dies at 5 s (out of bounds)."""
    frames = []
    for i in range(200):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        x = -10 + i * 0.1
        blue["head"] = _pose(200.0, 0.0) if 100 <= i < 110 else _pose(x, 0.0)
        blue["is_emote_playing"] = i in emote_frames
        blue["packetlossratio"] = 0.01
        orange["head"] = _pose(5.0, 5.0)
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}],
                               blue_points=blue_points_end * i / 199, orange_points=0.0))
    return frames


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {"dyson/walk.echoreplay": rf.plain(rf.lines_from(walking_match(emote_frames=(10, 11, 50))))})
        yield c


def match_id(client):
    return replay_by_path(client, "dyson/walk.echoreplay")["match_id"]


# --- tracks file -------------------------------------------------------------------------

def test_tracks_round_trip(client):
    path = tracks.tracks_path(client.app.state.settings.processed_dir, replay_by_path(client, "dyson/walk.echoreplay")["id"])
    header, players = tracks.read(path)
    assert header["hz"] == 2 and header["samples"] == 20  # 10 s at 2 Hz
    assert set(players) == {BLUE, "42"}
    blue = players[BLUE]
    assert blue["x"][0] == -100 and blue["z"][0] == 0  # decimetres
    assert set(blue["team"]) == {tracks.BLUE}
    assert header["weapons"] == ["assault"] and set(blue["weapon"]) == {0}
    assert header["series"]["blue_points"][0] == 0.0 and header["series"]["blue_points"][-1] > 45


def test_recorder_pads_gaps_and_absence():
    from parser import Frame

    rec = tracks.TrackRecorder(rf.START)
    def frame(seconds, players):
        return Frame(0, rf.START + timedelta(seconds=seconds), players, [], 0, 0, False, None, None, None, None)
    p = type("P", (), {"user_id": "1", "head_position": (1.0, 0.0, 2.0), "weapon": "", "tacmod": "", "ordnance": "", "team": "blue"})
    rec.add(frame(0.0, []))
    rec.add(frame(1.6, [p]))  # slot 3; slots 1-2 padded
    t = rec.result()
    assert t.samples == 4
    assert t.players[0].x == [None, None, None, 1.0]
    header, players = tracks.decode(tracks.encode(t))
    assert list(players["1"]["team"]) == [0, 0, 0, tracks.BLUE]


# --- heatmap geometry --------------------------------------------------------------------

def test_cells_follow_verified_orientation():
    d = HEATMAP_LAYOUTS["dyson"]  # x right, z up
    cols, rows = heatmaps.grid_size(d)
    assert heatmaps.to_cell(d, d.x_min, d.z_max) == (0, 0)
    assert heatmaps.to_cell(d, d.x_max, d.z_min) == (cols - 1, rows - 1)
    s = HEATMAP_LAYOUTS["surge"]  # x right, z down
    assert heatmaps.to_cell(s, s.x_min, s.z_min) == (0, 0)
    c = HEATMAP_LAYOUTS["combustion"]  # rotated: z right, x down
    cols, rows = heatmaps.grid_size(c)
    assert cols > rows  # landscape image
    assert heatmaps.to_cell(c, c.x_min, c.z_min) == (0, 0)
    assert heatmaps.to_cell(c, c.x_max, c.z_max) == (cols - 1, rows - 1)
    assert heatmaps.to_cell(d, 500.0, 0.0) is None


def test_rasterise_draws_lines_but_not_jumps():
    d = HEATMAP_LAYOUTS["dyson"]
    counts = Counter()
    heatmaps.rasterise(d, [(0.0, 0.0), (5.0, 0.0)], counts, cell_m=0.5)
    assert len(counts) == 11  # 5 m line in 0.5 m cells
    fine = Counter()
    heatmaps.rasterise(d, [(0.0, 0.0), (5.0, 0.0)], fine)
    assert len(fine) == 21  # default 0.25 m cells
    counts = Counter()
    heatmaps.rasterise(d, [(0.0, 0.0), (40.0, 0.0)], counts)  # 80 m/s: teleport
    assert len(counts) == 2


# --- endpoints ---------------------------------------------------------------------------

def test_match_heatmap(client):
    mid = match_id(client)
    h = client.get(f"/api/matches/{mid}/heatmap").json()
    assert (h["map"], h["image"], h["matches"]) == ("dyson", "/minimaps/dyson.png", 1)
    layers = {layer["key"]: layer for layer in h["layers"]}
    assert set(layers) == {"blue", "orange"}
    assert len(layers["blue"]["cells"]) > len(layers["orange"]["cells"])  # blue walks, orange stands
    only_orange = client.get(f"/api/matches/{mid}/heatmap", params={"player": "42"}).json()
    assert [layer["key"] for layer in only_orange["layers"]] == ["orange"]


def test_match_heatmap_per_player(client):
    mid = match_id(client)
    h = client.get(f"/api/matches/{mid}/heatmap", params={"mode": "player"}).json()
    assert h["mode"] == "player"
    layers = {layer["key"]: layer for layer in h["layers"]}
    assert set(layers) == {BLUE, "42"}
    assert (layers[BLUE]["team"], layers["42"]["team"]) == ("blue", "orange")
    assert all(layer["label"] != layer["key"] for layer in h["layers"])  # names, not ids
    assert len(layers[BLUE]["cells"]) > len(layers["42"]["cells"])
    one = client.get(f"/api/matches/{mid}/heatmap", params={"mode": "player", "player": "42"}).json()
    assert [layer["key"] for layer in one["layers"]] == ["42"]


def test_timeline(client):
    t = client.get(f"/api/matches/{match_id(client)}/timeline").json()
    assert t["hz"] == 2 and len(t["series"]["blue_points"]) == 20
    assert "payload_distance" not in t["series"]
    assert {e["type"] for e in t["events"]} >= {"death_est", "respawn", "loadout_change"}


def test_capture_time_packet_loss_and_emotes(client):
    m = client.get(f"/api/matches/{match_id(client)}").json()
    assert m["blue_capture_s"] == pytest.approx(199 / 20, rel=0.01) and m["orange_capture_s"] == 0
    blue = m["teams"]["blue"][0]
    assert blue["avg_packet_loss"] == pytest.approx(0.01)
    assert blue["emote_count"] == 2  # frames 10-11 = one emote, frame 50 = another
    profile = client.get(f"/api/players/{BLUE}").json()["stats"]
    assert profile["emote_count"] == 2 and profile["avg_packet_loss"] == pytest.approx(0.01)


@pytest.mark.parametrize("mode", ["team", "weapons", "deaths"])
def test_player_heatmap(client, mode):
    h = client.get(f"/api/players/{BLUE}/heatmap", params={"map": "dyson", "mode": mode}).json()
    assert h["matches"] == 1
    keys = [layer["key"] for layer in h["layers"]]
    assert keys == {"team": ["blue"], "weapons": ["assault"], "deaths": ["deaths"]}[mode]
    if mode == "weapons":
        assert h["layers"][0]["label"] == "Pulsar"
    if mode == "deaths":
        assert sum(n for _, _, n in h["layers"][0]["cells"]) == 1


def test_player_heatmap_validation(client):
    assert client.get(f"/api/players/{BLUE}/heatmap", params={"map": "moon"}).status_code == 422
    assert client.get("/api/players/nobody/heatmap", params={"map": "dyson"}).status_code == 404


def test_player_heatmap_cache_refreshes_after_import(client):
    first = client.get(f"/api/players/{BLUE}/heatmap", params={"map": "dyson"}).json()
    add(client, {"dyson/second.echoreplay": rf.plain(rf.lines_from(walking_match()))})
    second = client.get(f"/api/players/{BLUE}/heatmap", params={"map": "dyson"}).json()
    assert (first["matches"], second["matches"]) == (1, 2)


def test_leaderboard(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        files = {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20, blue_round_score=1)) for i in range(3)}
        add(c, files)
        board = c.get("/api/leaderboard", params={"stat": "wins", "min_games": 3}).json()
        assert [(r["rank"], r["name"], r["value"]) for r in board["items"]] == [(1, "Player", 3), (2, "Other", 0)]
        assert c.get("/api/leaderboard", params={"stat": "wins", "min_games": 4}).json()["total"] == 0
        ping = c.get("/api/leaderboard", params={"stat": "avg_ping", "min_games": 1}).json()
        assert ping["higher_is_better"] is False
        mine = c.get("/api/leaderboard", params={"stat": "games", "min_games": 1, "player": "42"}).json()
        assert mine["player"]["name"] == "Other"
        lo = c.get("/api/leaderboard", params={"stat": "loadout", "weapon": "assault", "min_games": 1}).json()
        assert lo["items"][0]["value"] > 0 and lo["loadout"]["weapon"]["name"] == "Pulsar"
        assert c.get("/api/leaderboard", params={"stat": "nope"}).json()["error_code"] == "unknown_stat"
        assert len(c.get("/api/leaderboard/stats").json()) > 10


def test_match_export(client):
    mid = match_id(client)
    r = client.get(f"/api/matches/{mid}/export", params={"format": "csv"})
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert {row["name"] for row in rows} == {"Player", "Other"}
    assert next(row for row in rows if row["name"] == "Player")["main_weapon"] == "Pulsar"
    data = json.loads(client.get(f"/api/matches/{mid}/export", params={"format": "json"}).content)
    assert data["id"] == mid and data["teams"]["blue"][0]["user_id"] == BLUE


def test_player_export(client):
    rows = list(csv.DictReader(io.StringIO(
        client.get(f"/api/players/{BLUE}/export").content.decode("utf-8-sig"))))
    assert len(rows) == 1 and rows[0]["map"] == "dyson" and rows[0]["deaths_est"] == "1"
    data = json.loads(client.get(f"/api/players/{BLUE}/export", params={"format": "json"}).content)
    assert data["user_id"] == BLUE and len(data["matches"]) == 1
