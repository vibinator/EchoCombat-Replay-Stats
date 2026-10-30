from datetime import date

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings

from backend.api.derived import period_start

BLUE = str(rf.BIG_USER_ID)


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {
            "dyson/cp.echoreplay": rf.plain(rf.lines(40, blue_round_score=2, orange_round_score=1)),
            "surge/pl.echoreplay": rf.plain(rf.lines(40, payload=True, sessionid="OTHER")),
        })
        yield c


def test_list_and_filter_matches(client):
    page = client.get("/api/matches").json()
    assert page["total"] == 2
    assert {m["map"] for m in page["items"]} == {"dyson", "surge"}
    assert all(m["player_count"] == 2 for m in page["items"])
    assert client.get("/api/matches", params={"mode": "payload"}).json()["total"] == 1
    assert client.get("/api/matches", params={"map": "dyson"}).json()["items"][0]["winner"] == "blue"
    assert client.get("/api/matches", params={"player": "42"}).json()["total"] == 2
    assert client.get("/api/matches", params={"player": "nobody"}).json()["total"] == 0
    assert client.get("/api/matches", params={"from": "2026-10-28", "to": "2026-10-28"}).json()["total"] == 2
    assert client.get("/api/matches", params={"from": "2026-10-29"}).json()["total"] == 0


def test_match_detail(client):
    match_id = client.get("/api/matches", params={"map": "dyson"}).json()["items"][0]["id"]
    m = client.get(f"/api/matches/{match_id}").json()
    assert (m["blue_rounds"], m["orange_rounds"], m["winner"]) == (2, 1, "blue")
    blue = m["teams"]["blue"][0]
    assert blue["user_id"] == BLUE  # exact, as a string
    assert blue["avg_ping"] == 60 and blue["avg_speed"] == 5.0
    assert blue["dominant_arm"] == "Right"
    lo = blue["loadouts"][0]
    assert (lo["weapon"]["name"], lo["tacmod"]["name"], lo["ordnance"]["name"]) == ("Pulsar", "Repair Matrix", "Detonator")
    assert lo["share"] == 1.0
    assert m["also_recorded_in"] == []


def test_match_events_and_404(client):
    match_id = client.get("/api/matches", params={"map": "dyson"}).json()["items"][0]["id"]
    events = client.get(f"/api/matches/{match_id}/events", params={"type": "loadout_change"}).json()
    assert {e["name"] for e in events} == {"Player", "Other"}
    assert client.get("/api/matches/999").json()["error_code"] == "not_found"


def test_player_search_and_profile(client):
    found = client.get("/api/players", params={"q": "play"}).json()
    assert [p["user_id"] for p in found["items"]] == [BLUE]
    assert found["items"][0]["games"] == 2

    profile = client.get(f"/api/players/{BLUE}").json()
    s = profile["stats"]
    assert (s["games"], s["wins"], s["losses"]) == (2, 1, 0)  # payload match has no winner
    assert s["games_by_map"] == {"dyson": 1, "surge": 1}
    assert s["avg_ping"] == 60 and s["pct_stopped"] == 0
    assert profile["level"] == 30
    assert profile["loadouts"][0]["weapon"]["name"] == "Pulsar"
    assert [m["result"] for m in profile["recent_matches"]].count("win") == 1

    assert client.get(f"/api/players/{BLUE}", params={"map": "surge"}).json()["stats"]["games"] == 1
    assert client.get(f"/api/players/{BLUE}", params={"period": "day"}).json()["stats"]["games"] == 0
    assert client.get(f"/api/players/{BLUE}", params={"period": "year"}).status_code == 422
    assert client.get("/api/players/missing").status_code == 404


def test_period_start():
    wednesday = date(2026, 10, 28)
    assert period_start("day", wednesday) == "2026-10-28"
    assert period_start("week", wednesday) == "2026-10-26"
    assert period_start("month", wednesday) == "2026-10-01"
    assert period_start("all", wednesday) is None
