"""The same match recorded in several files (D13): every copy has a match page, only the most complete counts."""

from datetime import timedelta

import pytest
import replay_factory as rf
from app_helpers import add, app_client, make_settings, replay_by_path

from sqlalchemy import delete, select

from backend import duplicates
from backend.models import DuplicateMatch, Match
from backend.persist import delete_match

SESSION = "11111111-2222-4333-8444-555555555555"
BLUE, ORANGE = str(rf.BIG_USER_ID), "42"


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        yield c


def match_id(client, path: str) -> int:
    return replay_by_path(client, path)["match_id"]


def counted_games(client, user_id: str) -> dict:
    """What the site shows for a player, from every place that counts matches."""
    g = client.get
    board = {r["user_id"]: r["games"] for r in g("/api/leaderboard", params={"stat": "games", "min_games": 1}).json()["items"]}
    return {
        "profile": g(f"/api/players/{user_id}").json()["stats"]["games"],
        "list": g("/api/players").json()["items"][0]["games"],
        "search": g("/api/search", params={"q": "Player"}).json()["players"][0]["games"],
        "leaderboard": board[user_id],
        "matches": g("/api/matches", params={"player": user_id}).json()["total"],
        "trends": sum(i["games"] for i in g(f"/api/players/{user_id}/trends").json()["items"]),
        "teammate_games": g(f"/api/players/{user_id}/companions").json()["opponents"][0]["games"],
        "overview": g("/api/overview").json()["matches"],
        "activity": sum(i["matches"] for i in g("/api/overview/activity").json()["items"]),
    }


def test_copy_of_a_match_counts_once(client):
    add(client, {
        "dyson/full.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION)),
        "dyson/copy.echoreplay": rf.plain(rf.lines(20, sessionid=SESSION)),  # same match, cut short
    })
    assert counted_games(client, BLUE) == dict.fromkeys(counted_games(client, BLUE), 1)

    full, copy = match_id(client, "dyson/full.echoreplay"), match_id(client, "dyson/copy.echoreplay")
    counted, extra = client.get(f"/api/matches/{full}").json(), client.get(f"/api/matches/{copy}").json()
    assert (counted["duplicate_of"], counted["also_recorded_in"]) == (None, [copy])  # longest recording counts
    assert (extra["duplicate_of"], extra["also_recorded_in"]) == (full, [full])
    assert extra["teams"]["blue"][0]["user_id"] == BLUE  # the copy keeps its own page
    assert [m["id"] for m in client.get("/api/matches").json()["items"]] == [full]


def test_back_to_back_matches_in_one_lobby_both_count(client):
    add(client, {
        "dyson/first.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION)),
        "dyson/second.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION, start=rf.START + timedelta(seconds=5))),
    })
    assert counted_games(client, BLUE)["profile"] == 2
    first = client.get(f"/api/matches/{match_id(client, 'dyson/first.echoreplay')}").json()
    assert (first["duplicate_of"], first["also_recorded_in"]) == (None, [])


def test_other_copy_counts_when_the_counted_one_goes(client):
    add(client, {
        "dyson/full.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION)),
        "dyson/copy.echoreplay": rf.plain(rf.lines(20, sessionid=SESSION)),
    })
    copy = match_id(client, "dyson/copy.echoreplay")
    with client.app.state.sessionmaker() as db:
        delete_match(db, replay_by_path(client, "dyson/full.echoreplay")["id"])
        db.commit()
        assert db.scalars(select(DuplicateMatch)).all() == []
    assert client.get(f"/api/matches/{copy}").json()["duplicate_of"] is None
    assert client.get(f"/api/players/{BLUE}").json()["stats"]["games"] == 1


def test_startup_finds_duplicates_in_an_existing_database(client):
    add(client, {
        "dyson/a.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION)),
        "dyson/b.echoreplay": rf.plain(rf.lines(40, sessionid=SESSION)),  # identical: the first file found counts
    })
    sessions = client.app.state.sessionmaker
    with sessions() as db:
        before = db.execute(select(DuplicateMatch.match_id, DuplicateMatch.counted_match_id)).all()
        db.execute(delete(DuplicateMatch))  # a database from before this change
        db.commit()
    duplicates.refresh_all(sessions)
    with sessions() as db:
        assert db.execute(select(DuplicateMatch.match_id, DuplicateMatch.counted_match_id)).all() == before
        a = db.scalar(select(Match.id).where(Match.replay_id == replay_by_path(client, "dyson/a.echoreplay")["id"]))
    assert before[0][1] == a
