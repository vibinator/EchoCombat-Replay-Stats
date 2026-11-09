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


def test_latest_matches_are_the_overviews(client):
    latest = client.get("/api/overview/latest").json()
    assert latest and latest == client.get("/api/overview").json()["latest"]


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
    assert h["mode"] == mode and h["cell_m"] == 0.1
    labels = {layer["key"]: layer["label"] for layer in h["layers"]}
    if mode == "loadout":
        assert labels["rocket|stun|heal"] == "Meteor · Stun Field · Repair Matrix"


def test_heatmap_resolution(client):
    url = f"/api/matches/{mid(client, 'dyson/a.echoreplay')}/heatmap"
    assert client.get(url).json()["cell_m"] == 0.1  # super fine is the only resolution
    for cell in (0.25, 0.5, 1, 0.3):
        assert client.get(url, params={"cell": cell}).json()["error_code"] == "bad_cell"
    player = client.get(f"/api/players/{BLUE}/heatmap", params={"map": "dyson", "mode": "loadout"}).json()
    assert player["matches"] == 2 and player["cell_m"] == 0.1


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


def test_playback3d(client):
    p = client.get(f"/api/matches/{mid(client, 'dyson/a.echoreplay')}/playback3d").json()
    assert p["hz"] == 5 and p["samples"] == 20 and p["model"].startswith("/maps3d/dyson.glb?v=")  # 80 frames = 4 s
    assert p["objects"]["point"][2] > 0 and p["payload"] is None and p["extent"] == [-54.625, 54.625, -41.125, 28.375]
    blue = next(x for x in p["players"] if x["user_id"] == BLUE)
    assert blue["x"][0] == -100 and blue["x"][-1] > blue["x"][0]  # decimetres, moving +x
    assert set(blue["y"]) == {0} and set(blue["yaw"]) == {0} and set(blue["pitch"]) == {0}  # facing +z, level
    assert blue["team"].count(0) == 1 and blue["team"][10] == 0  # (0, 0, 0) is dyson's load-in spot: absent, as in 2D
    assert set(blue["team"]) == {0, 1} and len(blue["x"]) == p["samples"] and len(blue["hands"]) == 6
    surge = client.get(f"/api/matches/{mid(client, 'surge/c.echoreplay')}/playback3d").json()
    assert surge["model"].startswith("/maps3d/surge.glb?v=") and surge["objects"]["route"] and any(surge["payload"])
    assert surge["payload_model"].startswith("/maps3d/surge_payload.glb?v=") and p["payload_model"] is None  # dyson has no payload
    assert client.get("/api/matches/999/playback3d").status_code == 404


def test_playback3d_built_on_first_view(client, tmp_path):
    # matches processed before 3D playback have no tracks3d.bin: the first view builds it from the replay
    match_id = mid(client, "dyson/b.echoreplay")
    replay_id = replay_by_path(client, "dyson/b.echoreplay")["id"]
    path = client.app.state.settings.processed_dir / str(replay_id) / "tracks3d.bin"
    path.unlink()
    p = client.get(f"/api/matches/{match_id}/playback3d").json()
    assert path.exists() and p["samples"] == 20 and p["model"].startswith("/maps3d/dyson.glb?v=")


def _tracks3d_file(client, name):
    replay_id = replay_by_path(client, name)["id"]
    return mid(client, name), client.app.state.settings.processed_dir / str(replay_id) / "tracks3d.bin"


def test_playback3d_damaged_file_is_built_again(client):
    match_id, path = _tracks3d_file(client, "dyson/b.echoreplay")
    path.write_bytes(b"not a tracks file")  # cut off by a crash, corrupt on disk
    p = client.get(f"/api/matches/{match_id}/playback3d")
    assert p.status_code == 200 and p.json()["samples"] == 20


def test_playback3d_unreadable_replay_is_a_404_not_a_500_and_not_read_again(client, monkeypatch):
    from concurrent.futures.process import BrokenProcessPool
    from backend import tracks3d
    from backend.api import matches
    match_id, path = _tracks3d_file(client, "dyson/b.echoreplay")
    path.unlink()
    matches._failed.clear()
    calls = []
    outcomes = iter([False, KeyError("frame"), BrokenProcessPool("killed")])

    def build(*args):
        calls.append(args)
        out = next(outcomes)
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(tracks3d, "build", build)
    first = client.get(f"/api/matches/{match_id}/playback3d")
    assert first.status_code == 404 and first.json()["error_code"] == "no_tracks3d"
    for _ in range(3):  # a repeated view (or a crawler) does not parse the replay again
        assert client.get(f"/api/matches/{match_id}/playback3d").status_code == 404
    assert len(calls) == 1
    # after the wait, it is tried again; an error raised by the build (not just "False") is also a 404
    matches._failed.clear()
    assert client.get(f"/api/matches/{match_id}/playback3d").status_code == 404
    matches._failed.clear()
    assert client.get(f"/api/matches/{match_id}/playback3d").status_code == 404  # the pool died under it
    assert len(calls) == 3


def test_playback3d_older_file_is_used_when_it_cannot_be_rebuilt(client, monkeypatch):
    import json, struct, zlib
    from backend import tracks3d
    from backend.api import matches
    match_id, path = _tracks3d_file(client, "dyson/b.echoreplay")
    raw = zlib.decompress(path.read_bytes())
    (length,) = struct.unpack_from("<I", raw)
    header = json.loads(raw[4:4 + length])
    header["version"] = 1  # written before hands existed
    new = json.dumps(header).encode()
    path.write_bytes(zlib.compress(struct.pack("<I", len(new)) + new + raw[4 + length:]))
    matches._failed.clear()
    monkeypatch.setattr(tracks3d, "build", lambda *a: False)
    p = client.get(f"/api/matches/{match_id}/playback3d")
    assert p.status_code == 200 and p.json()["samples"] == 20  # still has 3D, without hands
    assert set(p.json()["players"][0]["hands"][0]) <= {0}


def test_playback3d_waiting_requests_are_capped(client, monkeypatch):
    import threading
    from backend.api import matches
    match_id, path = _tracks3d_file(client, "dyson/b.echoreplay")
    path.unlink()
    matches._failed.clear()
    monkeypatch.setattr(matches, "_waiters", threading.BoundedSemaphore(0))  # every waiting place is taken
    r = client.get(f"/api/matches/{match_id}/playback3d")
    assert r.status_code == 503 and r.json()["error_code"] == "tracks3d_building"
    assert not path.exists()  # and nothing was started for it


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


def test_filters_only_take_known_values(client):
    # every distinct filter value is a cached answer and a full scan: junk values are refused (security review)
    for url, params in (("/api/leaderboard", {"map": "nowhere"}), ("/api/leaderboard", {"stat": "loadout", "weapon": "zzz"}),
                        ("/api/matches", {"map": "x" * 40}), ("/api/matches", {"mode": "arena"}),
                        ("/api/matches", {"player_name": "a" * 65}), ("/api/players", {"q": "a" * 65}),
                        (f"/api/players/{BLUE}", {"map": "nowhere"})):
        r = client.get(url, params=params)
        assert r.status_code in (400, 422), (url, params, r.status_code)
    assert client.get("/api/leaderboard", params={"map": "dyson", "min_games": 1}).status_code == 200
    assert client.get("/api/matches", params={"map": "dyson", "mode": "capture_point"}).status_code == 200


def test_discord_ids_are_digits_only():
    from backend import auth

    assert auth.is_discord_id("123456789012345678")
    for bad in ("../../channels/1/messages", "12345", "１２３４５６７８９０１２３４５６７８", "²" * 18, "123456789012345678/x"):
        assert not auth.is_discord_id(bad), bad


def test_leaderboard_summary_columns(client):
    # every row carries wins / losses / win rate / hours beside the ranked stat, whichever stat is ranked
    for stat in ("games", "avg_speed", "loadout"):
        board = client.get("/api/leaderboard", params={"stat": stat, "min_games": 1}).json()
        assert board["items"]
        for r in board["items"]:
            assert {"wins", "losses", "win_rate", "hours_played"} <= r.keys()
            assert r["wins"] is not None and r["hours_played"] is not None


def test_import_throughput_and_years(client):
    s = client.get("/api/import").json()
    assert len(s["throughput"]) == 60 and sum(m["replays"] for m in s["throughput"]) == 3
    assert sum(y["done"] for y in s["by_year"]) == 3


def test_leaderboard_sort_by_summary_column(client):
    # clicking a column header re-ranks the # column by that column, highest first; same players as the stat board
    base = client.get("/api/leaderboard", params={"stat": "avg_speed", "min_games": 1}).json()
    board = client.get("/api/leaderboard", params={"stat": "avg_speed", "min_games": 1, "sort": "hours_played", "compare": "true"}).json()
    assert board["sort"] == "hours_played" and board["total"] == base["total"]
    hours = [r["hours_played"] for r in board["items"]]
    assert hours == sorted(hours, reverse=True)
    assert [r["rank"] for r in board["items"]] == list(range(1, len(hours) + 1))
    assert client.get("/api/leaderboard", params={"sort": "avg_speed"}).status_code == 400
