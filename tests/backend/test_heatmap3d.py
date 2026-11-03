import numpy as np
import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

from backend import heatmaps, heatmaps3d
from backend.stats.maps import HEATMAP_LAYOUTS

BLUE = str(rf.BIG_USER_ID)
DYSON = HEATMAP_LAYOUTS["dyson"]


def _pose(x, y, z):
    return {"position": [x, y, z], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}


def climbing_match():
    """Dyson, 10 s. Blue walks +x at 2 m/s and rises 1 m per second; orange stands still at a height of 3 m."""
    frames = []
    for i in range(200):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        blue["head"] = _pose(-10 + i * 0.1, i * 0.05, 0.0)
        orange["head"] = _pose(5.0, 3.0, 5.0)
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}]))
    return frames


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {"dyson/climb.echoreplay": rf.plain(rf.lines_from(climbing_match()))})
        yield c


def match_id(client):
    return replay_by_path(client, "dyson/climb.echoreplay")["match_id"]


def voxels(h: dict, layer: dict) -> list:
    return heatmaps3d.unpack(layer["packed"], h["nx"], h["nz"], round(h["origin"][1] / h["vox_m"]))


def test_densify_without_height_is_the_2d_path():
    x, z = np.array([0.0, 1.0, 40.0]), np.array([0.0, 0.0, 0.0])
    xs, zs, ys = heatmaps._densify(x, z, np.array([3]), 0.5)
    assert ys is None
    assert len(xs) == 1 + 4 + 1  # the start, a point every 0.25 m for 1 m, then a jump (> 12 m: no line)
    assert (xs[0], zs[0], xs[-1], zs[-1]) == (0.0, 0.0, 40.0, 0.0)


def test_densify_with_height_joins_in_space():
    x, y, z = np.array([0.0, 0.0]), np.array([0.0, 4.0]), np.array([0.0, 0.0])
    xs, zs, ys = heatmaps._densify(x, z, np.array([2]), 0.5, y)
    assert len(ys) == 17 and ys[0] == 0.0 and ys[-1] == 4.0  # straight up: a point every 0.25 m
    assert np.all(np.diff(ys[1:]) > 0)


def test_aligned_y_uses_the_nearest_sample_in_time_and_fills_absences():
    two = {"team": bytes([1] * 6)}  # 2 Hz: 0, 0.5, 1, 1.5, 2, 2.5 s = 5 Hz samples 0, 2.5, 5, 7.5, 10, 12.5
    three = {"y": np.arange(15, dtype=np.int16) * 10, "team": bytes([1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1])}
    y = heatmaps3d.aligned_y(two, three, 2, 5)
    assert y[0] == 0.0
    assert y[2] in (4.0, 6.0)  # sample 5 is absent: a neighbour stands in
    assert y[4] == pytest.approx(10.0)
    assert heatmaps3d.aligned_y(two, {"y": np.array([], dtype=np.int16), "team": b""}, 2, 5) is None
    assert heatmaps3d.aligned_y(two, {"y": np.zeros(5, dtype=np.int16), "team": bytes(5)}, 2, 5) is None


def test_voxelise_counts_and_axes():
    layout = DYSON
    x, y, z = np.array([0.0, 0.0]), np.array([1.2, 1.2]), np.array([0.0, 0.0])
    ix, iy, iz, n = heatmaps3d.voxelise(layout, x, y, z, np.array([1, 1]))
    assert len(n) == 1 and n[0] == 2
    assert iy[0] == 2  # 1.2 m / 0.5 m
    assert ix[0] == int((0.0 - layout.x_min) / heatmaps3d.VOX_M)
    assert iz[0] == int((0.0 - layout.z_min) / heatmaps3d.VOX_M)


def test_voxelise_drops_what_is_off_the_map():
    out = heatmaps3d.voxelise(DYSON, np.array([500.0]), np.array([0.0]), np.array([0.0]), np.array([1]))
    assert all(len(a) == 0 for a in out)


def test_match_heatmap3d(client):
    mid = match_id(client)
    h = client.get(f"/api/matches/{mid}/heatmap3d").json()
    assert (h["map"], h["matches"], h["matches_3d"], h["vox_m"]) == ("dyson", 1, 1, heatmaps3d.VOX_M)
    assert h["model"].startswith("/maps3d/dyson.glb")
    layers = {layer["key"]: layer for layer in h["layers"]}
    assert set(layers) == {"blue", "orange"}
    blue, orange = voxels(h, layers["blue"]), voxels(h, layers["orange"])
    assert len(blue) > len(orange)
    assert {iy for _, iy, _, _ in orange} == {6}  # 3 m / 0.5 m
    assert len({iy for _, iy, _, _ in blue}) > 1  # blue climbs
    assert h["ny"] >= 2 and h["origin"][0] == DYSON.x_min and h["origin"][2] == DYSON.z_min


def test_match_heatmap3d_per_player_and_filter(client):
    mid = match_id(client)
    h = client.get(f"/api/matches/{mid}/heatmap3d", params={"mode": "player"}).json()
    layers = {layer["key"]: layer for layer in h["layers"]}
    assert set(layers) == {BLUE, "42"} and (layers[BLUE]["team"], layers["42"]["team"]) == ("blue", "orange")
    one = client.get(f"/api/matches/{mid}/heatmap3d", params={"player": "42"}).json()
    assert [layer["key"] for layer in one["layers"]] == ["orange"]


def test_match_heatmap3d_footprint_matches_2d(client):
    """Seen from above the voxels reach as far along the walk as the 2D heatmap's cells."""
    mid = match_id(client)
    flat = client.get(f"/api/matches/{mid}/heatmap").json()
    deep = client.get(f"/api/matches/{mid}/heatmap3d").json()
    blue_2d = heatmaps.unpack_cells(next(layer for layer in flat["layers"] if layer["key"] == "blue")["packed"], flat["cols"])
    reach_2d = (max(c for c, _, _ in blue_2d) - min(c for c, _, _ in blue_2d) + 1) * flat["cell_m"]  # dyson: columns run along x
    xs = [ix for ix, _, _, _ in voxels(deep, next(layer for layer in deep["layers"] if layer["key"] == "blue"))]
    reach_3d = (max(xs) - min(xs) + 1) * heatmaps3d.VOX_M
    assert abs(reach_3d - reach_2d) <= heatmaps3d.VOX_M


@pytest.mark.parametrize("mode", ["weapons", "speed", "loadout", "ordnance", "tacmod"])
def test_match_heatmap3d_modes(client, mode):
    h = client.get(f"/api/matches/{match_id(client)}/heatmap3d", params={"mode": mode}).json()
    assert h["mode"] == mode and h["layers"]


def test_player_heatmap3d(client):
    h = client.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "dyson"}).json()
    assert (h["matches"], h["matches_3d"]) == (1, 1)
    assert [layer["key"] for layer in h["layers"]] == ["blue"]


def test_player_heatmap3d_validation(client):
    assert client.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "moon"}).status_code == 422
    assert client.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "dyson", "mode": "deaths"}).status_code == 422
    assert client.get("/api/players/nobody/heatmap3d", params={"map": "dyson"}).status_code == 404


def test_player_heatmap3d_leaves_out_matches_without_3d_tracks(client):
    from backend import tracks3d

    processed = client.app.state.settings.processed_dir
    tracks3d.tracks3d_path(processed, replay_by_path(client, "dyson/climb.echoreplay")["id"]).unlink()
    h = client.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "dyson"}).json()
    assert (h["matches"], h["matches_3d"], h["layers"]) == (1, 0, [])
