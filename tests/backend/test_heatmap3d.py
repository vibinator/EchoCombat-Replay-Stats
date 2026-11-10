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


def test_heights_file_is_written_with_the_tracks_and_used(client):
    """heights.bin (the height of every 2 Hz sample) is made when a match is processed; it holds what tracks3d.bin
    gives, and it is made again when it is gone, damaged or tracks3d.bin has changed."""
    import os

    from backend import tracks, tracks3d

    processed = client.app.state.settings.processed_dir
    rid = replay_by_path(client, "dyson/climb.echoreplay")["id"]
    p2, p3 = tracks.tracks_path(processed, rid), tracks3d.tracks3d_path(processed, rid)
    saved = heatmaps3d.heights_path(p3)
    assert saved.exists()
    two = tracks.read(p2)
    direct = heatmaps3d.heights_of(two[1], tracks3d.read(p3)[1], 2, 5)
    kept = heatmaps3d.match_heights(two, p3)
    assert set(kept) == set(direct) == {BLUE, "42"}
    assert all(np.array_equal(kept[uid], direct[uid]) for uid in direct)
    assert kept["42"].tolist() == [30] * len(kept["42"])  # 3 m, in decimetres

    saved.unlink()
    assert heatmaps3d.match_heights(two, p3, save=False) is not None and not saved.exists()
    assert heatmaps3d.match_heights(two, p3) is not None and saved.exists()

    st = p3.stat()
    os.utime(p3, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # tracks3d.bin written again
    source = [p3.stat().st_mtime_ns, st.st_size]
    assert heatmaps3d.decode_heights(saved.read_bytes(), two[0]["samples"], source) is None
    assert heatmaps3d.match_heights(two, p3) is not None
    assert heatmaps3d.decode_heights(saved.read_bytes(), two[0]["samples"], source) is not None

    saved.write_bytes(b"not a heights file")
    assert set(heatmaps3d.match_heights(two, p3)) == {BLUE, "42"}
    h = client.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "dyson"}).json()
    assert (h["matches_3d"], [layer["key"] for layer in h["layers"]]) == (1, ["blue"])


def test_voxels_counted_in_parts_add_up(monkeypatch):
    """A heatmap counted a few samples at a time (FLUSH_SAMPLES), or sorted instead of counted in a plain array, is
    the same as one counted at once; the points between samples are those of heatmaps._densify."""
    rng = np.random.default_rng(3)
    n = 400
    x, z = np.round(np.cumsum(rng.normal(0, 1.5, n)), 1), np.round(np.cumsum(rng.normal(0, 0.5, n)), 1)
    y = np.round(np.abs(np.cumsum(rng.normal(0, 0.4, n))), 1)
    x[200:] += 60  # a jump: no line
    lengths = np.array([150, 0, 250])
    xs, zs, ys = heatmaps._densify(x, z, lengths, heatmaps3d.VOX_M, y)
    px, py, pz = heatmaps3d._points(x, y, z, lengths)
    assert len(px) > 2 * n
    assert sorted(zip(xs.tolist(), ys.tolist(), zs.tolist())) == sorted(zip(px.tolist(), py.tolist(), pz.tolist()))

    def layers():
        found = heatmaps3d._Layers(DYSON)
        for start in range(0, n, 50):
            found.add("a", x[start:start + 50], y[start:start + 50], z[start:start + 50], np.array([50]))
        return sorted(zip(*(a.tolist() for a in found.result()["a"])))

    whole = layers()
    assert sum(v[3] for v in whole) > n
    monkeypatch.setattr(heatmaps3d, "FLUSH_SAMPLES", 120)
    assert layers() == whole
    monkeypatch.setattr(heatmaps3d, "DENSE_PER_POINT", 0)
    assert layers() == whole


def test_idle_pass_writes_the_heights_of_the_most_active_players(client):
    from backend import heights_warm, tracks3d

    app = client.app
    processed = app.state.settings.processed_dir
    rid = replay_by_path(client, "dyson/climb.echoreplay")["id"]
    saved = heatmaps3d.heights_path(tracks3d.tracks3d_path(processed, rid))
    assert heights_warm.replay_ids(app.state.sessionmaker) == [rid]
    assert heights_warm.missing(processed, [rid]) == []
    saved.unlink()
    assert heights_warm.missing(processed, [rid]) == [rid]
    warmer = heights_warm.HeightsWarmer(app.state.sessionmaker, app.state.settings, app.state.worker)
    assert warmer.run_once(rest=False) == (1, 0) and saved.exists()
    assert warmer.run_once(rest=False) == (0, 0)


def test_player_heatmaps_are_kept_until_the_player_has_a_new_match(tmp_path):
    """Another player's replay does not make a player's heatmap out of date; a new match of the player does. The
    answers are on disk: a server started again sends them without working them out."""
    from backend.api import players

    settings = make_settings(tmp_path, answer_cache_mb=8)
    urls = [(f"/api/players/{BLUE}/heatmap3d", {"map": "dyson"}), (f"/api/players/{BLUE}/heatmap", {"map": "dyson"})]
    with app_client(settings) as c:
        add(c, {"dyson/climb.echoreplay": rf.plain(rf.lines_from(climbing_match()))})
        first = [c.get(url, params=p) for url, p in urls]
        assert [r.headers["X-EchoVR-Cache"] for r in first] == ["MISS", "MISS"]
        assert len(list((settings.data_dir / "cache" / "answers").glob("*.bin"))) == 2

        strangers = []
        for i in range(40):
            a, b = rf.player(7, "Seven"), rf.player(8, "Eight", 1)
            a["head"], b["head"] = _pose(1.0, 1.0, i * 0.1), _pose(2.0, 1.0, 2.0)
            strangers.append(rf.frame(teams=[{"players": [a]}, {"players": [b]}, {}]))
        add(c, {"dyson/strangers.echoreplay": rf.plain(rf.lines_from(strangers))})
        again = [c.get(url, params=p) for url, p in urls]
        assert [r.headers["X-EchoVR-Cache"] for r in again] == ["HIT", "HIT"]
        assert [r.content for r in again] == [r.content for r in first]

    def must_not_run(*args, **kwargs):
        raise AssertionError("worked out again")

    with app_client(settings) as c:  # a restart: nothing in memory
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(players, "_player_heatmap3d", must_not_run)
            patch.setattr(players, "_player_heatmap", must_not_run)
            later = [c.get(url, params=p) for url, p in urls]
            assert [r.headers["X-EchoVR-Cache"] for r in later] == ["HIT", "HIT"]
            assert [r.json() for r in later] == [r.json() for r in first]
        add(c, {"dyson/climb2.echoreplay": rf.plain(rf.lines_from(climbing_match()[:150]))})
        new = c.get(urls[0][0], params=urls[0][1])
        assert new.headers["X-EchoVR-Cache"] == "MISS" and new.json()["matches"] == 2


def test_idle_pass_builds_the_long_heatmaps_onto_disk(tmp_path):
    from backend import heights_warm
    from backend.api import players

    settings = make_settings(tmp_path, answer_cache_mb=8)
    with app_client(settings) as c:
        add(c, {"dyson/climb.echoreplay": rf.plain(rf.lines_from(climbing_match()))})
        app = c.app
        assert (BLUE, "dyson") in heights_warm.players_and_maps(app.state.sessionmaker)
        warmer = heights_warm.HeightsWarmer(app.state.sessionmaker, settings, app.state.worker, app)
        assert warmer.build_heatmaps(rest=False) == 4  # two players, flat and 3D
        assert warmer.build_heatmaps(rest=False) == 0  # still current
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(players, "_player_heatmap3d", lambda *a, **k: pytest.fail("worked out again"))
            h = c.get(f"/api/players/{BLUE}/heatmap3d", params={"map": "dyson", "last": players.ALL_MATCHES})
        assert h.headers["X-EchoVR-Cache"] == "HIT" and [layer["key"] for layer in h.json()["layers"]] == ["blue"]


def test_answers_on_disk_stay_within_their_limit(tmp_path):
    from backend import cache

    disk = cache.Disk(tmp_path / "answers", 3000)
    for i in range(6):
        disk.save(("x", (i,), None), cache.Entry((1, [2, "a"]), 0.0, gz=bytes(900), etag="e"))
    assert disk.stamp(("x", (5,), None)) == (1, (2, "a")) and disk.load(("x", (5,), None)).gz == bytes(900)
    disk.prune()
    left = list((tmp_path / "answers").glob("*.bin"))
    assert 0 < len(left) < 6 and sum(f.stat().st_size for f in left) <= 3000
    assert disk.load(("x", (99,), None)) is None


def test_answers_on_disk_keep_what_was_used_last(tmp_path):
    import os
    import time

    from backend import cache

    disk = cache.Disk(tmp_path / "answers", 4500)
    keys = [("x", (i,), None) for i in range(3)]
    for i, key in enumerate(keys):
        disk.save(key, cache.Entry((1,), 0.0, gz=bytes(900), etag="e"))
        os.utime(disk.path(key), (time.time() - 1000 + i, time.time() - 1000 + i))  # written long ago, 0 first
    assert disk.load(keys[0]) is not None  # read for a request: used now
    disk.used(keys[1])  # found current by the idle pass
    for i in range(3, 5):
        disk.save(("x", (i,), None), cache.Entry((1,), 0.0, gz=bytes(900), etag="e"))
    disk.prune()
    assert disk.load(keys[2]) is None  # the one nobody used went first
    assert disk.load(keys[0]) is not None and disk.load(keys[1]) is not None
