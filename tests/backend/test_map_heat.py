"""All-time heat on the home page's map cards (map_heat.py, /api/overview/map-heat)."""

import base64
import struct
import zlib

import numpy as np
import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings
from test_gui_api import moving_match

from backend import heatmaps, map_heat
from backend.stats.maps import HEATMAP_LAYOUTS


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {"dyson/a.echoreplay": moving_match(blue_round_score=2), "dyson/b.echoreplay": moving_match()})
        yield c


def _pixels(data_url: str) -> tuple[np.ndarray, np.ndarray]:
    """(palette entry per pixel, RGBA palette) of a palette PNG data URL."""
    png = base64.b64decode(data_url.removeprefix("data:image/png;base64,"))
    assert png[:8] == heatmaps.PNG_SIGNATURE
    chunks, at = {}, 8
    while at < len(png):
        (length,), kind = struct.unpack(">I", png[at:at + 4]), png[at + 4:at + 8]
        chunks[kind] = png[at + 8:at + 8 + length]
        assert struct.unpack(">I", png[at + 8 + length:at + 12 + length])[0] == zlib.crc32(kind + chunks[kind])
        at += 12 + length
    width, height, depth, color = struct.unpack(">IIBB", chunks[b"IHDR"][:10])
    assert (depth, color) == (8, 3)
    rows = np.frombuffer(zlib.decompress(chunks[b"IDAT"]), dtype=np.uint8).reshape(height, width + 1)
    palette = np.concatenate([np.frombuffer(chunks[b"PLTE"], dtype=np.uint8).reshape(-1, 3),
                              np.frombuffer(chunks[b"tRNS"], dtype=np.uint8).reshape(-1, 1)], axis=1)
    return rows[:, 1:], palette


def test_team_heat_covers_the_minimap(client):
    d = client.get("/api/overview/map-heat").json()
    assert d["layer"] == "team" and d["building"] is False and d["updated_on"]
    assert set(d["maps"]) == {"dyson"} and d["maps"]["dyson"]["matches"] == 2
    index, palette = _pixels(d["maps"]["dyson"]["image"])
    assert index.shape[::-1] == heatmaps.grid_size(HEATMAP_LAYOUTS["dyson"], map_heat.CELL_M)
    painted = palette[index[index > 0]]
    assert 0 < len(painted) < index.size / 10  # two players: mostly clear
    assert palette[0, 3] == 0 and (painted[:, 3] > 0).all()
    red, blue = painted[:, 0].astype(int), painted[:, 2].astype(int)
    assert (blue > red + 60).any() and (red > blue + 60).any()  # a spot takes the colour of the team that is there


def test_gear_layers(client):
    d = client.get("/api/overview/map-heat").json()
    keys = [layer["key"] for layer in d["layers"]]
    assert keys[0] == "team"
    assert {"weapon:assault", "weapon:rocket", "ordnance:det", "ordnance:stun", "tacmod:heal"} <= set(keys)
    assert "weapon:smg" not in keys  # never held: not offered
    weapons = [layer for layer in d["layers"] if layer["group"] == "weapon"]
    assert weapons == sorted(weapons, key=lambda layer: -layer["share"]) and abs(sum(w["share"] for w in weapons) - 1) < 0.01
    assert weapons[0]["label"] in ("Pulsar", "Meteor")

    def painted(layer):
        d = client.get("/api/overview/map-heat", params={"layer": layer, "view": "all"}).json()
        assert d["view"] == ("teams" if layer == "team" else "all")
        index, _ = _pixels(d["maps"]["dyson"]["image"])
        return index > 0

    team, rocket, det = painted("team"), painted("weapon:rocket"), painted("ordnance:det")
    assert rocket.any() and not (rocket & ~team).any()  # the blue player switched to it half way: part of its path
    assert rocket.sum() < team.sum() and not np.array_equal(rocket, det)
    assert client.get("/api/overview/map-heat", params={"layer": "weapon:smg", "view": "all"}).json()["maps"] == {}
    favoured = client.get("/api/overview/map-heat", params={"layer": "weapon:rocket"}).json()
    assert favoured["view"] == "favoured" and favoured["maps"] == {}  # two short matches: too little to say


def test_favoured_view_shows_where_gear_is_held_more_than_usual():
    rows, cols = 60, 80
    group = np.full((rows, cols), 1000, dtype=np.int64)  # everybody evenly over the map
    gear = np.full((rows, cols), 200, dtype=np.int64)  # this gear: a fifth of them ...
    gear[10:25, 10:25] = 600  # ... but three fifths in one corner
    group[40, 60], gear[40, 60] = 5_000_000, 5_000_000  # and somebody parked in one cell for hours
    png = map_heat.render_favoured(gear, group)
    index, palette = _pixels("data:image/png;base64," + base64.b64encode(png).decode())
    reach = 2 * map_heat.FAVOURED_BLUR  # how far the smoothing carries the surroundings into the corner
    inside = index[10 + reach:25 - reach, 10 + reach:25 - reach]
    assert inside.size and (inside == index.max()).all() and palette[index.max(), 3] > 200  # the corner, at full strength
    assert (index[35:46, 30:50] == 0).all() and (index[30:, :50] == 0).all()  # as often as anywhere, the parked cell: clear
    assert map_heat.render_favoured(np.zeros((rows, cols), dtype=np.int64), group) is None
    assert map_heat.render_favoured(gear // 100, group // 100) is None  # a handful of samples per cell: not drawn


def test_rare_gear_is_not_offered(client):
    client.get("/api/overview/map-heat")
    heat = client.app.state.map_heat
    with heat.lock:
        heat.counts["dyson"][map_heat.LAYER_INDEX["weapon:assault"], 5, 5] += 10_000
        heat.counts["dyson"][map_heat.LAYER_INDEX["weapon:smg"], 5, 5] = 10  # a moment of one player: 0.1 %
    keys = [layer["key"] for layer in heat.answer()["layers"]]
    assert "weapon:smg" not in keys and "weapon:assault" in keys


def test_bad_layer(client):
    assert client.get("/api/overview/map-heat", params={"layer": "weapon:nope"}).json()["error_code"] == "bad_layer"
    assert client.get("/api/overview/map-heat", params={"layer": "x"}).status_code == 422
    assert client.get("/api/overview/map-heat", params={"layer": "weapon:assault", "view": "x"}).status_code == 422


def test_counted_once_a_month_and_kept_on_disk(client, tmp_path, monkeypatch):
    first = client.get("/api/overview/map-heat").json()
    heat = client.app.state.map_heat
    assert heat.path.is_file() and len(heat.included) == 2 and not heat.due()
    add(client, {"dyson/c.echoreplay": moving_match(), "surge/d.echoreplay": rf.plain(rf.lines(40, payload=True))})
    assert client.get("/api/overview/map-heat").json()["maps"] == first["maps"]  # same month: not counted again

    class NextMonth(map_heat.date):
        @classmethod
        def today(cls):
            return cls(2099, 1, 1)

    monkeypatch.setattr(map_heat, "date", NextMonth)
    later = client.get("/api/overview/map-heat").json()
    assert later["updated_on"] == "2099-01-01" and later["maps"]["dyson"]["matches"] == 3 and "surge" in later["maps"]
    assert not heat.path.with_name("map-heat.next.npz").exists() and heat.fresh is None  # counted beside it, then swapped in

    again = map_heat.MapHeat(client.app.state.sessionmaker, client.app.state.settings)  # as after a restart
    again.ensure()
    assert again.included == heat.included and not again.due()
    assert all(np.array_equal(again.counts[m], heat.counts[m]) for m in heat.counts)


def test_a_replay_that_stops_counting_is_taken_out(client):
    client.get("/api/overview/map-heat")
    heat = client.app.state.map_heat
    before = {m: c.copy() for m, c in heat.counts.items()}
    replay_id, map_ = next(iter(heat.included.items()))
    heat._apply([(replay_id, map_)], -1)
    assert replay_id not in heat.included and heat.counts[map_].sum() < before[map_].sum()
    heat._apply([(replay_id, map_)], 1)
    assert all(np.array_equal(heat.counts[m], before[m]) for m in before)


def _heat_with(tmp_path, replays):
    with app_client(make_settings(tmp_path)) as c:
        add(c, replays)
        c.get("/api/overview/map-heat")
        yield c


def _handed_match(**kw):
    """Blue (left-handed, upside down in the second half) flies along z = 0, orange (right-handed) stands still."""
    frames = []
    for i in range(80):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        up = [0, -1, 0] if i >= 40 else [0, 1, 0]
        blue["head"] = {"position": [-10 + i * 0.25, 0.0, 0.0], "forward": [0, 0, 1], "left": [1, 0, 0], "up": up}
        blue["body"] = dict(blue["head"])
        blue["Arm"] = "Left"
        orange["head"] = {"position": [5.0, 0.0, 5.0], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}], **kw))
    return rf.plain(rf.lines_from(frames))


@pytest.fixture
def handed(tmp_path):
    yield from _heat_with(tmp_path, {"dyson/a.echoreplay": _handed_match()})


def test_hand_and_pose_layers(handed):
    counts = handed.app.state.map_heat.counts["dyson"]
    n = {key: int(counts[i].sum()) for key, i in map_heat.LAYER_INDEX.items()}
    assert n["hand:left"] == n["team:blue"] > 0 and n["hand:right"] == n["team:orange"] > 0  # the arm set, per player
    assert n["pose:upside"] + n["pose:upright"] == n["team:blue"] + n["team:orange"]  # every sample is one of the two
    assert 0 < n["pose:upside"] < n["team:blue"]  # only blue, half of the match
    d = handed.get("/api/overview/map-heat", params={"layer": "hand:left", "view": "all"}).json()
    by_key = {layer["key"]: layer for layer in d["layers"]}
    assert by_key["hand:left"]["group"] == "hand" and by_key["hand:left"]["label"] == "Left-handed"
    assert by_key["pose:upside"]["label"] == "Upside down" and 0 < by_key["pose:upside"]["share"] < 0.5
    left, _ = _pixels(d["maps"]["dyson"]["image"])
    team, _ = _pixels(handed.get("/api/overview/map-heat").json()["maps"]["dyson"]["image"])
    assert (left > 0).any() and (left > 0).sum() < (team > 0).sum()
    upside = handed.get("/api/overview/map-heat", params={"layer": "pose:upside", "view": "all"}).json()
    assert upside["maps"]["dyson"]["matches"] == 1  # the matches with 3D tracks


def test_older_tracks_take_the_pose_from_the_3d_roll(handed, monkeypatch, tmp_path):
    from backend import tracks

    exact = handed.app.state.map_heat
    upside = map_heat.LAYER_INDEX["pose:upside"]
    assert exact.posed and exact.counts["dyson"][upside].sum() > 0  # from the flags of tracks.bin

    def before_flags(data):  # a tracks.bin as written before version 3
        header, players = real(data)
        return header | {"version": 2}, {uid: t | {"flags": b""} for uid, t in players.items()}

    real = tracks.decode
    monkeypatch.setattr(tracks, "decode", before_flags)

    def counted(name):
        heat = map_heat.MapHeat(handed.app.state.sessionmaker, handed.app.state.settings)
        heat.path = tmp_path / f"{name}.npz"  # counts of its own, from the same track files
        heat.update()
        return heat

    rolled = counted("rolled")  # no flags: the head's roll in tracks3d.bin stands in
    assert rolled.posed == exact.posed
    assert abs(int(rolled.counts["dyson"][upside].sum()) - int(exact.counts["dyson"][upside].sum())) <= 2
    for replay_id in exact.included:
        (handed.app.state.settings.processed_dir / str(replay_id) / "tracks3d.bin").unlink()
    neither = counted("neither")  # no flags and no 3D tracks: in no pose layer, everything else counts
    counts = neither.counts["dyson"]
    assert counts[upside].sum() == 0 and counts[map_heat.LAYER_INDEX["pose:upright"]].sum() == 0 and not neither.posed
    assert counts[map_heat.LAYER_INDEX["hand:left"]].sum() > 0
    assert "pose:upside" not in [layer["key"] for layer in neither.answer()["layers"]]


def test_tracks_keep_who_is_upside_down(handed):
    from backend import tracks

    heat = handed.app.state.map_heat
    replay_id = next(iter(heat.included))
    header, players = tracks.decode(tracks.tracks_path(handed.app.state.settings.processed_dir, replay_id).read_bytes())
    assert header["version"] == tracks.FORMAT_VERSION == 3
    flags = {uid: np.frombuffer(t["flags"], dtype=np.uint8) for uid, t in players.items()}
    assert all(len(f) == header["samples"] for f in flags.values())
    assert sorted(int(f.sum()) > 0 for f in flags.values()) == [False, True]  # blue in the second half, orange never
    blue = next(f for f in flags.values() if f.any())
    assert not blue[: len(blue) // 2 - 1].any() and blue[len(blue) // 2 + 1:].all()


def test_compare_shows_where_each_layer_is_more_often():
    rows, cols = 60, 80
    one = np.full((rows, cols), 1000, dtype=np.int64)
    other = np.full((rows, cols), 100, dtype=np.int64)  # a tenth of the samples: compared by share, so even so far
    one[10:25, 10:25] = 4000  # `one` is in this corner far more often ...
    other[40:55, 50:70] = 400  # ... and `other` in that one
    png = map_heat.render_compare(one, other)
    index, palette = _pixels("data:image/png;base64," + base64.b64encode(png).decode())
    first, second = index[14:21, 14:21], index[44:51, 54:66]
    assert ((first >= 1) & (first <= map_heat.COMPARE_STEPS)).all() and (second > map_heat.COMPARE_STEPS).all()
    assert tuple(palette[first.max(), :3]) != tuple(palette[second.max(), :3])
    assert (index[30:36, :] == 0).all()  # as often as each other: clear
    assert map_heat.render_compare(one, one * 3) is None and map_heat.render_compare(one, other * 0) is None


def test_compare_api(handed):
    d = handed.get("/api/overview/map-heat", params={"layer": "team:blue", "against": "team:orange"}).json()
    assert d["view"] == "compare" and d["against"] == "team:orange"
    same = handed.get("/api/overview/map-heat", params={"layer": "hand:left", "against": "hand:left", "view": "all"}).json()
    assert same["view"] == "all" and same["against"] is None  # nothing is compared with itself
    assert handed.get("/api/overview/map-heat", params={"against": "weapon:nope"}).json()["error_code"] == "bad_layer"
    assert handed.get("/api/overview/map-heat", params={"layer": "payload:stop", "against": "team"}).json()["view"] == "payload"


def test_payload_counts_per_metre_of_route():
    series = [0.0] * 20 + [0.0, 0.5, 1.0, 1.5, 1.5, 1.5, 2.0, 1.75, 2.5, 3.5] + [3.5] * 30
    counts = map_heat.payload_counts("surge", {"series": {"payload_distance": series}, "hz": 2})
    assert counts[:, map_heat.P_TIME].sum() == 9  # from its first move to its last: the wait before and after is left out
    assert list(counts[:4, map_heat.P_TIME]) == [2, 5, 2, 0]
    assert counts[1, map_heat.P_STOPPED] == 2 and counts[:, map_heat.P_STOPPED].sum() == 2
    assert counts[:, map_heat.P_BACK].sum() == 1 and counts[2, map_heat.P_BACK] == 1
    assert counts[:, map_heat.P_FORWARD].sum() == 6 and counts[:, map_heat.P_FORWARD_CM].sum() == 375
    assert map_heat.payload_counts("dyson", {"series": {"payload_distance": series}}) is None
    assert map_heat.payload_counts("surge", {"series": {"payload_distance": [12.5] * 40}}) is None  # it never moved
    jump = map_heat.payload_counts("surge", {"series": {"payload_distance": [0, 1, 150, 151, 0, 1]}})
    assert jump[:, map_heat.P_TIME].sum() == 3  # the two resets are not movement


def test_payload_band_along_the_route():
    n = len(map_heat.PAYLOAD_ROUTES["surge"])
    counts = np.zeros((n, 5), dtype=np.int64)
    counts[:, map_heat.P_TIME], counts[:, map_heat.P_STOPPED] = 1000, 100
    counts[50:70, map_heat.P_STOPPED] = 600  # it gets stuck here
    counts[150:, map_heat.P_TIME], counts[150:, map_heat.P_STOPPED] = 10, 5  # hardly ever reached: not drawn
    values = map_heat.payload_values(counts, "payload:stop")
    assert abs(values[60] - 0.6) < 0.01 and abs(values[20] - 0.1) < 0.01 and np.isnan(values[160])
    index, _ = _pixels("data:image/png;base64," + base64.b64encode(
        map_heat.render_payload("surge", values, map_heat.payload_scale([values]))).decode())
    assert 0 < (index > 0).mean() < 0.05 and index.max() == map_heat.GEAR_STEPS and index[index > 0].min() == 1
    counts[:, map_heat.P_FORWARD], counts[:, map_heat.P_FORWARD_CM] = 500, 500 * 60
    assert abs(map_heat.payload_values(counts, "payload:speed")[20] - 1.2) < 1e-6  # 0.6 m per half second


def test_payload_layers_only_when_a_payload_moved(client, tmp_path):
    assert "payload:stop" not in [layer["key"] for layer in client.get("/api/overview/map-heat").json()["layers"]]
    heat = client.app.state.map_heat
    with heat.lock:
        heat.payload["surge"][:, map_heat.P_TIME], heat.payload["surge"][:, map_heat.P_STOPPED] = 1000, 100
        heat.payload["surge"][40:60, map_heat.P_STOPPED] = 500
        heat.revision += 1
        heat._save()
    d = client.get("/api/overview/map-heat", params={"layer": "payload:stop"}).json()
    assert d["view"] == "payload" and set(d["maps"]) == {"surge"} and d["scale"]["min"] < d["scale"]["max"]
    assert [layer["label"] for layer in d["layers"] if layer["group"] == "payload"] == ["Stops", "Speed", "Rollback"]
    assert abs(d["maps"]["surge"]["average"] - heat.payload["surge"][:, 1].sum() / heat.payload["surge"][:, 0].sum()) < 0.001
    again = map_heat.MapHeat(client.app.state.sessionmaker, client.app.state.settings)  # as after a restart
    again.ensure()
    assert np.array_equal(again.payload["surge"], heat.payload["surge"]) and again.posed == heat.posed


def test_result_speed_and_death_layers(handed):
    heat = handed.app.state.map_heat
    counts = heat.counts["dyson"]
    n = {key: int(counts[i].sum()) for key, i in map_heat.LAYER_INDEX.items()}
    assert n["result:won"] == n["result:lost"] == 0  # nobody won this one: in neither layer
    assert n["speed:medium"] > 0 and n["speed:stopped"] > 0 and n["speed:fast"] == 0  # blue at 5 m/s, orange standing
    assert n["speed:stopped"] + n["speed:slow"] + n["speed:medium"] <= n["team:blue"] + n["team:orange"]
    keys = [layer["key"] for layer in heat.answer()["layers"]]
    assert "speed:medium" in keys and "speed:fast" not in keys and "result:won" not in keys and "death:all" not in keys


@pytest.fixture
def decided(tmp_path):
    yield from _heat_with(tmp_path, {"dyson/a.echoreplay": _handed_match(blue_round_score=2)})


def test_winners_and_losers(decided):
    heat = decided.app.state.map_heat
    counts = heat.counts["dyson"]
    won, lost = counts[map_heat.LAYER_INDEX["result:won"]], counts[map_heat.LAYER_INDEX["result:lost"]]
    assert np.array_equal(won, counts[map_heat.LAYER_INDEX["team:blue"]])  # blue won
    assert np.array_equal(lost, counts[map_heat.LAYER_INDEX["team:orange"]])
    d = decided.get("/api/overview/map-heat", params={"layer": "result:won", "view": "all"}).json()
    assert [layer["label"] for layer in d["layers"] if layer["group"] == "result"] == ["Winners", "Losers"]


def test_deaths_are_counted_where_they_happened(decided):
    from backend.models import Event, Match

    heat = decided.app.state.map_heat
    replay_id, map_ = next(iter(heat.included.items()))
    heat._apply([(replay_id, map_)], -1)
    with decided.app.state.sessionmaker() as db:
        match_id = db.query(Match.id).filter(Match.replay_id == replay_id).scalar()
        for x, z in ((4.0, 2.0), (4.0, 2.0), (-12.0, 6.0), (500.0, 0.0)):  # the last one is off the picture
            db.add(Event(match_id=match_id, frame=1, t_s=1.0, type="death_est", team="blue", data=f'{{"x": {x}, "z": {z}}}'))
        db.commit()
    heat._apply([(replay_id, map_)], 1)
    deaths = heat.counts[map_][map_heat.LAYER_INDEX["death:all"]]
    assert deaths.sum() == 3 and deaths.max() == 2
    col, row, _ = heatmaps.cells_of(HEATMAP_LAYOUTS[map_], np.array([4.0 + map_heat.NUDGE_M]), np.array([2.0 + map_heat.NUDGE_M]), map_heat.CELL_M)
    assert deaths[row[0], col[0]] == 2
    layer = next(layer for layer in heat.answer("death:all", "all")["layers"] if layer["group"] == "death")
    assert layer["label"] == "Deaths" and "share" not in layer
    index, _ = _pixels(heat.answer("death:all", "all")["maps"][map_]["image"])
    assert 3 < (index > 0).sum() < 400  # smoothed over about a metre: two patches, not three single cells
    heat._apply([(replay_id, map_)], -1)
    assert heat.counts[map_].sum() == 0


def test_sparse_favoured_view_measures_against_where_everybody_is():
    rows, cols = 60, 80
    everybody = np.full((rows, cols), 2000, dtype=np.int64)
    deaths = np.full((rows, cols), 4, dtype=np.int64)  # a few a cell: far below what time-based layers need
    deaths[20:32, 30:44] = 16  # four times as deadly for the time spent
    assert map_heat.render_favoured(deaths, everybody) is None  # as a time layer: too little to say
    info = {}
    png = map_heat.render_favoured(deaths, everybody, map_heat.SPARSE_BLUR, map_heat.SPARSE_MIN_EXPECTED, info=info)
    index, _ = _pixels("data:image/png;base64," + base64.b64encode(png).decode())
    assert (index[24:28, 35:39] == index.max()).all() and (index[45:, :] == 0).all() and (index[:10, :] == 0).all()
    assert map_heat.FAVOURED_TOP[0] <= info["top"] <= map_heat.FAVOURED_TOP[1]


def test_answers_say_how_to_read_them_and_are_cached(handed):
    for params, view in (({}, "teams"), ({"layer": "hand:left", "view": "all"}, "all"),
                         ({"layer": "team:blue", "against": "team:orange"}, "compare"),
                         ({"layer": "speed:medium", "against": "team"}, "compare")):
        first = handed.get("/api/overview/map-heat", params=params)
        again = handed.get("/api/overview/map-heat", params=params)
        d = first.json()
        assert d["view"] == view and d["read"] == map_heat.READ[view]
        assert again.headers["x-echovr-cache"] == "HIT" and again.json() == d and again.headers["etag"] == first.headers["etag"]
        not_modified = handed.get("/api/overview/map-heat", params=params, headers={"If-None-Match": first.headers["etag"]})
        assert not_modified.status_code == 304
    compare = handed.get("/api/overview/map-heat", params={"layer": "team:blue", "against": "team:orange"}).json()
    assert all(map_heat.COMPARE_TOP[0] <= m["top"] <= map_heat.COMPARE_TOP[1] for m in compare["maps"].values())
    heat = handed.app.state.map_heat
    with heat.lock:
        heat.revision += 1  # the counts changed: every answer is built again
    assert handed.get("/api/overview/map-heat").headers["x-echovr-cache"] != "HIT"


def test_time_range_counts_only_recent_matches(client, monkeypatch):
    from datetime import timedelta

    assert client.get("/api/overview/map-heat", params={"days": 7}).json()["error_code"] == "bad_range"
    everything = client.get("/api/overview/map-heat").json()
    assert everything["days"] == 0 and everything["matches"] == 2

    class Day(map_heat.date):
        at = rf.START.date() + timedelta(days=10)

        @classmethod
        def today(cls):
            return cls(cls.at.year, cls.at.month, cls.at.day)

    monkeypatch.setattr(map_heat, "date", Day)
    recent = client.get("/api/overview/map-heat", params={"days": 30}).json()
    assert recent["days"] == 30 and recent["matches"] == 2 and recent["maps"]["dyson"]["image"] == everything["maps"]["dyson"]["image"]
    heats = client.app.state.map_heats
    assert set(heats) == {0, 30} and heats[30].path.name == "map-heat-30d.npz" and heats[30].path.is_file()
    assert heats[0] is client.app.state.map_heat and not heats[30].due()

    # a time range nobody looks at lets go of its counts, and has them again when asked
    heats[30].used_at -= map_heat.IDLE_S + 1
    heats[0].used_at -= map_heat.IDLE_S + 1
    client.get("/api/overview/map-heat")
    assert not heats[30].loaded and heats[30].counts == {} and heats[0].loaded  # all time stays
    assert heats[30].answer()["maps"] == recent["maps"] and heats[30].loaded

    # the next day it is brought up to date; 40 days on the two matches have left the range and are taken out again
    Day.at = rf.START.date() + timedelta(days=40)
    later = client.get("/api/overview/map-heat", params={"days": 30}).json()
    assert later["maps"] == {} and later["matches"] == 0 and later["updated_on"] == Day.at.isoformat()
    assert all(not c.any() for c in heats[30].counts.values()) and not heats[30].included
    assert client.get("/api/overview/map-heat", params={"days": 90}).json()["matches"] == 2
