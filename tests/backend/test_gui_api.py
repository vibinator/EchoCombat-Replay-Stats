import json

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

BLUE = str(rf.BIG_USER_ID)


def _pose(x, z):
    return {"position": [x, 0.0, z], "forward": [0, 0, 1], "left": [1, 0, 0], "up": [0, 1, 0]}


def moving_match(weapon_switch_at=40, n=80, **kw):
    frames = []
    for i in range(n):
        blue, orange = rf.player(), rf.player(42, "Other", 1)
        blue["head"] = _pose(-10 + i * 0.25, 0.0)  # 5 m/s
        if i >= weapon_switch_at:
            blue["Weapon"], blue["Ordnance"] = "rocket", "stun"
        orange["head"] = _pose(5.0, 5.0)  # stopped
        frames.append(rf.frame(teams=[{"players": [blue]}, {"players": [orange]}, {}], **kw))
    return rf.plain(rf.lines_from(frames))


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {
            "dyson/a.echoreplay": moving_match(blue_round_score=2),
            "dyson/b.echoreplay": moving_match(),
            "surge/c.echoreplay": rf.plain(rf.lines(40, payload=True)),
        })
        yield c


def mid(client, path):
    return replay_by_path(client, path)["match_id"]


def test_overview_and_global_stats(client):
    o = client.get("/api/overview").json()
    assert (o["matches"], o["players"]) == (3, 2)
    assert o["by_map"] == {"dyson": 2, "surge": 1} and o["most_played_map"] == "dyson"
    g = o["global"]
    assert g["top_weapons"][0]["name"] in ("Pulsar", "Meteor") and g["top_weapons"][0]["share"] > 0
    assert {x["name"] for x in g["top_ordnances"]} >= {"Detonator", "Stun Field"}
    assert g["top_tacmods"][0]["name"] == "Repair Matrix"
    assert g["avg_match_s"] > 0 and g["avg_players_per_match"] == 2.0
    assert g["most_active"]["games"] == 3 and g["fastest"]["top_speed"] > 0
    assert g["capture_wins"] == {"blue": 1, "orange": 0}
    assert len(o["latest"]) == 3


def test_processing_is_zero_once_everything_is_read(client):
    assert client.get("/api/overview/processing").json() == {"pending": 0}


def test_last_match_matches_the_overview(client):
    last = client.get("/api/overview/last-match").json()["last_match_at"]
    assert last and last == client.get("/api/overview").json()["last_match_at"]
    # the end of the game, not its start
    newest = client.get("/api/overview").json()["latest"][0]
    assert last > newest["started_at"]


def test_activity_and_players_seen(client):
    a = client.get("/api/overview/activity", params={"bucket": "day"}).json()
    # per day: the 90 days up to the newest match, empty days included
    assert len(a["items"]) == 90 and (a["items"][0]["period"], a["items"][-1]["period"]) == ("2026-07-31", "2026-10-28")
    assert a["items"][-1] == {"period": "2026-10-28", "matches": 3, "hours": a["items"][-1]["hours"],
                              "maps": a["items"][-1]["maps"]}
    assert sum(a["items"][-1]["maps"].values()) == 3
    assert all(i["matches"] == 0 and i["maps"] == {} for i in a["items"][:-1])
    month = client.get("/api/overview/activity", params={"bucket": "month"}).json()["items"]
    assert [i["period"] for i in month] == ["2026-10"]  # other buckets: whole archive, only periods with matches
    seen = client.get("/api/overview/players-seen", params={"range": "24h", "anchor": "latest"}).json()
    assert seen["unique_players"] == 2 and seen["matches"] == 3 and len(seen["items"]) in (24, 25)
    assert max(i["players"] for i in seen["items"]) == 2
    week = client.get("/api/overview/players-seen", params={"range": "7d", "anchor": "latest"}).json()
    assert len(week["items"]) in (7, 8)
    assert client.get("/api/overview/players-seen", params={"range": "1y"}).status_code == 422


def test_search(client):
    r = client.get("/api/search", params={"q": "oth"}).json()
    assert [p["name"] for p in r["players"]] == ["Other"] and r["matches"] == []
    match_id = mid(client, "dyson/a.echoreplay")
    assert client.get("/api/search", params={"q": f"#{match_id}"}).json()["matches"][0]["id"] == match_id


def test_match_filters_and_cards(client):
    assert client.get("/api/matches", params={"result": "blue"}).json()["total"] == 1
    assert client.get("/api/matches", params={"result": "unknown"}).json()["total"] == 2  # dyson draw + unfinished payload
    assert client.get("/api/matches", params={"min_players": 3}).json()["total"] == 0
    assert client.get("/api/matches", params={"player_name": "OTH"}).json()["total"] == 3
    assert client.get("/api/matches", params={"private": "true"}).json()["total"] == 0
    cards = client.get("/api/matches", params={"with_players": "true"}).json()["items"]
    assert {p["name"] for p in cards[0]["players"]} == {"Player", "Other"}


@pytest.mark.parametrize(("mode", "keys"), [
    ("weapons", {"assault", "rocket"}),
    ("ordnance", {"det", "stun"}),
    ("tacmod", {"heal"}),
    ("loadout", {"assault|det|heal", "rocket|stun|heal"}),
    ("speed", {"stopped", "medium"}),
])
def test_heatmap_modes(client, mode, keys):
    h = client.get(f"/api/matches/{mid(client, 'dyson/a.echoreplay')}/heatmap", params={"mode": mode}).json()
    assert {layer["key"] for layer in h["layers"]} == keys
    assert h["mode"] == mode and h["cell_m"] == 0.25
    labels = {layer["key"]: layer["label"] for layer in h["layers"]}
    if mode == "loadout":
        assert labels["rocket|stun|heal"] == "Meteor · Stun Field · Repair Matrix"


def test_heatmap_resolution(client):
    url = f"/api/matches/{mid(client, 'dyson/a.echoreplay')}/heatmap"
    fine, coarse = client.get(url).json(), client.get(url, params={"cell": 1}).json()
    assert abs(fine["cols"] - coarse["cols"] * 4) <= 4  # edges round up
    assert client.get(url, params={"cell": 0.3}).json()["error_code"] == "bad_cell"
    player = client.get(f"/api/players/{BLUE}/heatmap", params={"map": "dyson", "mode": "loadout", "cell": 0.5}).json()
    assert player["matches"] == 2 and player["cell_m"] == 0.5


def _png_info(url: str) -> tuple[int, int, bytes]:
    import base64
    import struct
    import zlib

    assert url.startswith("data:image/png;base64,")
    png = base64.b64decode(url.split(",", 1)[1])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width, height, depth, color = struct.unpack(">IIBB", png[16:26])
    assert (depth, color) == (8, 6)  # 8-bit RGBA
    idat_len = struct.unpack(">I", png[33:37])[0]
    return width, height, zlib.decompress(png[41:41 + idat_len])


def test_match_thumbnails(client):
    from backend import heatmaps
    from backend.stats.maps import HEATMAP_LAYOUTS

    a, b = mid(client, "dyson/a.echoreplay"), mid(client, "dyson/b.echoreplay")
    r = client.get("/api/matches/thumbnails", params={"ids": f"{b},{a},{a},999999"})
    assert r.status_code == 200
    thumbs = r.json()["thumbnails"]
    assert set(thumbs) == {str(a), str(b)}  # unknown ids left out, duplicates once
    width, height, raw = _png_info(thumbs[str(a)])
    assert (width, height) == heatmaps.grid_size(HEATMAP_LAYOUTS["dyson"], heatmaps.THUMB_CELL_M)
    pixels = [raw[row * (width * 4 + 1) + 1:(row + 1) * (width * 4 + 1)] for row in range(height)]
    painted = [px[i:i + 4] for px in pixels for i in range(0, len(px), 4) if px[i + 3]]
    assert painted and all(p[3] >= 0.25 * 255 - 1 for p in painted)  # mostly transparent, heat at least 25 % opaque
    assert any(tuple(p[:3]) == heatmaps.TEAM_RGB["blue"] for p in painted)
    assert any(tuple(p[:3]) == heatmaps.TEAM_RGB["orange"] for p in painted)


def test_match_thumbnails_limits(client):
    assert client.get("/api/matches/thumbnails").status_code == 422
    assert client.get("/api/matches/thumbnails", params={"ids": "1,x"}).status_code == 422
    many = ",".join(str(i) for i in range(1, 50))
    assert client.get("/api/matches/thumbnails", params={"ids": many}).json()["error_code"] == "too_many"


def test_playback(client):
    p = client.get(f"/api/matches/{mid(client, 'dyson/a.echoreplay')}/playback").json()
    assert p["hz"] == 2 and p["samples"] == 8 and p["image"] == "/minimaps/dyson.png"  # 80 frames = 4 s
    blue = next(x for x in p["players"] if x["user_id"] == BLUE)
    u0, v0, team = blue["points"][0]
    u1 = blue["points"][-1][0]
    assert team == 1 and 0 <= v0 <= 1 and u1 > u0  # moves right (+x on dyson)


def test_trends_companions_compare(client):
    t = client.get(f"/api/players/{BLUE}/trends", params={"bucket": "month"}).json()
    assert t["items"][0]["period"] == "2026-10" and t["items"][0]["games"] == 3
    c = client.get(f"/api/players/{BLUE}/companions").json()
    assert c["teammates"] == [] and c["opponents"][0]["name"] == "Other" and c["opponents"][0]["games"] == 3
    cmp = client.get(f"/api/players/compare/{BLUE},42").json()
    assert [p["name"] for p in cmp["players"]] == ["Player", "Other"]
    assert cmp["head_to_head"]["against"]["games"] == 3 and cmp["head_to_head"]["against"]["wins"] == 1
    assert client.get(f"/api/players/compare/{BLUE}").json()["error_code"] == "need_two"


def test_leaderboard_rank_change(client):
    board = client.get("/api/leaderboard", params={"stat": "games", "min_games": 1, "compare": "true"}).json()
    assert all("previous_rank" in r for r in board["items"])


def test_import_throughput_and_years(client):
    s = client.get("/api/import").json()
    assert len(s["throughput"]) == 60 and sum(m["replays"] for m in s["throughput"]) == 3
    assert sum(y["done"] for y in s["by_year"]) == 3
