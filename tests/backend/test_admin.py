"""Player merges, challenge period, reprocess: run from the admin console (backend.admin_actions); the website
only reads."""

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings, replay_by_path, sync

from sqlalchemy import select

from backend import admin_actions as actions
from backend.achievements import RULES
from backend.api.achievements import REVEALED_IDS
from backend.models import PlayerAlias


def match(players_blue, players_orange, **kw):
    return rf.plain(rf.lines(30, teams=[{"players": players_blue}, {"players": players_orange}, {}], **kw))


@pytest.fixture
def client(tmp_path):
    with app_client(make_settings(tmp_path)) as c:
        add(c, {
            # "Alt" (200) and "Main" (100) never play together; "Mate" (300) plays with both
            "dyson/1.echoreplay": match([rf.player(100, "Main")], [rf.player(300, "Mate", 1)], blue_round_score=1),
            "dyson/2.echoreplay": match([rf.player(100, "Main")], [rf.player(300, "Mate", 1)]),
            "surge/3.echoreplay": match([rf.player(200, "Alt")], [rf.player(300, "Mate", 1)], payload=True),
        })
        yield c


def snapshot(client):
    """Everything the site shows per player, keyed by user id."""
    out = {}
    for p in client.get("/api/players", params={"limit": 200}).json()["items"]:
        profile = client.get(f"/api/players/{p['user_id']}").json()
        out[p["user_id"]] = {
            "name": profile["name"], "stats": profile["stats"], "loadouts": profile["loadouts"],
            "matches": sorted(m["replay_id"] for m in profile["recent_matches"]),
        }
    return out


def wait(client):
    client.app.state.worker.wait_idle()


def test_website_is_read_only(client):
    for method, url in (("post", "/api/admin/players/merge"), ("put", "/api/admin/challenges"),
                        ("delete", "/api/admin/aliases/200"), ("post", "/api/replays/1/reprocess"),
                        ("post", "/api/replays/repair-failed"), ("post", "/api/import/scan")):
        r = getattr(client, method)(url)
        assert r.status_code == 405 and r.json()["error_code"] == "read_only", url


def test_import_lists_are_not_on_the_website(tmp_path):
    with app_client(make_settings(tmp_path, import_api=False)) as c:
        for url in ("/api/import", "/api/replays", "/api/replays/1"):
            assert c.get(url).status_code == 404, url
        assert c.get("/api/health").status_code == 200


def test_merge_then_undo_restores_everything(client):
    before = snapshot(client)
    assert set(before) == {"100", "200", "300"}

    assert len(act(client, actions.merge_players, "100", ["200"])) == 1
    wait(client)
    merged = snapshot(client)
    assert set(merged) == {"100", "300"}  # the alt no longer shows as its own player
    assert merged["100"]["stats"]["games"] == 3
    assert merged["100"]["stats"]["games_by_map"] == {"dyson": 2, "surge": 1}
    assert client.get("/api/players/100").json()["merged_ids"] == ["200"]
    assert merged["300"] == before["300"]  # other players untouched

    # undo
    assert len(act(client, actions.unmerge_player, "200")) == 3
    wait(client)
    assert snapshot(client) == before  # identical: nothing lost


def test_merged_id_leaves_search_and_opens_the_main_profile(client):
    act(client, actions.merge_players, "100", ["200"])
    wait(client)
    assert {p["user_id"] for p in client.get("/api/search", params={"q": "a"}).json()["players"]} == {"100", "300"}
    old_link = client.get("/api/players/200").json()  # old links to the alt
    assert (old_link["user_id"], old_link["stats"]["games"]) == ("100", 3)

    act(client, actions.unmerge_player, "200")
    wait(client)
    assert {p["user_id"] for p in client.get("/api/search", params={"q": "a"}).json()["players"]} == {"100", "200", "300"}
    assert client.get("/api/players/200").json()["user_id"] == "200"


def test_merge_survives_rebuild(client):
    act(client, actions.merge_players, "100", ["200"])
    wait(client)
    for r in client.get("/api/replays").json()["items"]:  # reprocess everything from the files
        act(client, actions.reprocess, r["id"])
    wait(client)
    assert client.get("/api/players/100").json()["stats"]["games"] == 3


def test_alias_and_main_in_same_match_stay_separate(client):
    add(client, {"dyson/4.echoreplay": match([rf.player(100, "Main")], [rf.player(200, "Alt", 1)])})
    act(client, actions.merge_players, "100", ["200"])
    wait(client)
    m = client.get("/api/matches", params={"player": "100"}).json()["total"]
    assert m == 4  # 3 own + the alt's match
    rid = replay_by_path(client, "dyson/4.echoreplay")["id"]
    both = next(x for x in client.get("/api/matches").json()["items"] if x["replay_id"] == rid)
    players = client.get(f"/api/matches/{both['id']}").json()["teams"]
    assert {p["name"] for t in players.values() for p in t} == {"Main", "Alt"}  # nobody dropped


def test_merge_validation(client):
    with pytest.raises(actions.AdminError, match="at least one"):
        act(client, actions.merge_players, "100", ["100"])
    with pytest.raises(actions.AdminError, match="not found"):
        act(client, actions.merge_players, "999", ["200"])
    with pytest.raises(actions.AdminError, match="not found"):
        act(client, actions.merge_players, "100", ["999"])
    with pytest.raises(actions.AdminError, match="No merge"):
        act(client, actions.unmerge_player, "555")


def test_unreadable_reprocess_keeps_previous_results(client):
    settings = client.app.state.settings
    rid = replay_by_path(client, "dyson/1.echoreplay")["id"]
    (settings.source_dir / "dyson" / "1.echoreplay").unlink()  # share offline / file gone
    act(client, actions.reprocess, rid)
    wait(client)
    replay = client.get(f"/api/replays/{rid}").json()
    assert replay["status"] == "done" and replay["match_id"]
    assert "previous results kept" in replay["warnings"][0]


def test_challenge_period(client):
    info = client.get("/api/challenges").json()
    peek = info.pop("peek")
    assert info == {"start": None, "end": None, "updated_at": None, "launched": False, "active": False, "preview": False,
                    "total": len(RULES)}
    # the sneak peek gives counts and pictures; only the revealed few have names and descriptions
    assert sum(peek["periods"].values()) + sum(peek["new"].values()) == len(RULES) and peek["icons"]
    assert [a["id"] for a in peek["revealed"]] == list(REVEALED_IDS)
    hidden = str(peek["periods"]) + str(peek["new"]) + str(peek["icons"])
    assert not any(r.name in hidden or r.description in hidden for r in RULES)
    rest = [r for r in RULES if r.id not in REVEALED_IDS]
    assert not any(r.name in str(peek) or r.description in str(peek) for r in rest)
    assert client.get("/api/players/100/achievements").status_code == 403  # coming soon
    act(client, actions.set_challenge_window, "2026-01-01", None)
    before = client.get("/api/players/100/achievements").json()
    assert before["games"] == 2

    with pytest.raises(actions.AdminError, match="on or before"):
        act(client, actions.set_challenge_window, "2026-11-02", "2026-11-01")
    assert act(client, actions.set_challenge_window, "2026-01-01", "2026-01-31") == ("2026-01-01", "2026-01-31")
    after = client.get("/api/players/100/achievements").json()
    assert after["games"] == 0 and after["overall"] == 0  # sample matches are on 2026-10-28
    assert after["window"] == {"start": "2026-01-01", "end": "2026-01-31"}

    act(client, actions.set_challenge_window, "2026-01-01", None)
    assert client.get("/api/players/100/achievements").json()["games"] == 2


def test_settings_and_merges_survive_database_rebuild(tmp_path):
    import sqlite3

    settings = make_settings(tmp_path)
    with app_client(settings) as c:
        add(c, {"dyson/1.echoreplay": match([rf.player(100, "Main")], [rf.player(200, "Alt", 1)])})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        add(c, {"dyson/2.echoreplay": match([rf.player(300, "Other")], [rf.player(200, "Alt", 1)])})
        act(c, actions.merge_players, "100", ["300"])
    con = sqlite3.connect(settings.db_path)
    con.execute("ALTER TABLE replays ADD COLUMN junk TEXT")  # forces a full rebuild
    con.commit()
    con.close()
    with app_client(settings) as c:
        assert c.get("/api/challenges").json()["start"] == "2026-01-01"
        with c.app.state.sessionmaker() as db:
            assert [a.alias_user_id for a in db.scalars(select(PlayerAlias))] == ["300"]
        sync(c)  # re-import from the share
        assert c.get("/api/matches").json()["total"] == 2


def test_rarity_and_recent(client):
    act(client, actions.set_challenge_window, "2026-01-01", None)
    rules = client.get("/api/achievements").json()
    assert len(rules) == len(RULES) and "unlocked_share" in rules[0]
    recent = client.get("/api/achievements/recent").json()
    assert isinstance(recent, list)
    assert all({"date", "name", "achievement"} <= set(e) for e in recent)
