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
