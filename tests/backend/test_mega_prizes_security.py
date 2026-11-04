"""Mega Prizes security (user, 2026-11-04): the prize data is Preview-only, the winners report Console-only, and nothing about
the prizes leaks through a public answer, a shared cache or a public file. Discord is mocked (test_discord_preview)."""

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client
from sqlalchemy import select
from test_discord_preview import BLUE, DB_MEMBER, DB_ROLE, MEMBER, NO_ROLE, discord, login, settings  # noqa: F401  (fixtures)

from backend import admin_actions as actions
from backend import mega_prizes
from backend.models import ArenaPlayer

PRIZE_URLS = ["/api/arena/progress", "/api/arena/search?q=zed", "/api/arena/image/jack.jpg", "/api/arena/image/biomass.jpg"]
CONSOLE_URLS = ["/api/admin/console/mega-prizes", "/api/admin/console/mega-prizes.csv"]
WORDS = ("Echo Combat Veteran", "Mega Prize", "BioMass", "Jack Model", "OG High Quality")


def seed(client):
    with client.app.state.sessionmaker() as db:
        db.add(ArenaPlayer(user_id="n1", username="zed", display_name="Zed", discord_id="99", matches=800, last_match_at="x"))
        db.commit()


def preview_only(client, tmp_user=DB_MEMBER):
    """A Preview role (set in the Console) that is not a Console role."""
    with client.app.state.sessionmaker() as db:
        actions.add_discord_role(db, "preview", DB_ROLE)
        db.commit()


@pytest.mark.parametrize("who", [None, NO_ROLE])
def test_nobody_without_the_preview_role_gets_anything(tmp_path, discord, who):
    with app_client(settings(tmp_path)) as client:
        seed(client)
        if who:
            login(client, who)
        for url in PRIZE_URLS + CONSOLE_URLS:
            r = client.get(url)
            assert r.status_code == 403, url
            assert not any(w.encode() in r.content for w in WORDS + ("zed",)), url  # the refusal carries no data
            assert r.headers["cache-control"] in ("no-store", "private, no-store"), url


def test_preview_role_sees_the_prizes_but_not_the_winners_report(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        seed(client)
        login(client, DB_MEMBER)
        preview_only(client)
        for url in PRIZE_URLS:
            r = client.get(url)
            assert r.status_code == 200, url
            assert r.headers["cache-control"] == "private, no-store" and r.headers["cloudflare-cdn-cache-control"] == "no-store", url
        found = client.get("/api/arena/search?q=zed").json()["results"]
        assert found == [{"kind": "arena", "name": "Zed", "user_id": "n1", "matches": 800}]  # no Discord id in the answer
        assert "discord" not in client.get("/api/arena/progress").text.lower()
        for url in CONSOLE_URLS:  # Console only: it lists Discord ids
            assert client.get(url).status_code == 403, url
        assert client.get("/api/arena/image/../../main.py").status_code in (404, 405)  # only the two named pictures
        assert client.get("/api/arena/image/secret.txt").status_code == 404


def test_console_role_gets_the_winners_report(tmp_path, discord):
    with app_client(settings(tmp_path)) as client:
        seed(client)
        login(client, MEMBER)
        act(client, actions.set_challenge_window, "2000-01-01", None)
        assert all(client.get(u).status_code == 200 for u in PRIZE_URLS)
        report = client.get("/api/admin/console/mega-prizes").json()
        assert [w["name"] for w in report["prizes"][1]["winners"]] == ["Zed"] and report["prizes"][1]["winners"][0]["discord_id"] == "99"
        csv = client.get("/api/admin/console/mega-prizes.csv")
        assert csv.status_code == 200 and "attachment" in csv.headers["content-disposition"] and csv.headers["cache-control"] == "private, no-store"


def test_nothing_about_the_prizes_is_in_a_public_answer(tmp_path, discord):
    """After the launch the achievement answers are public and shared: no prize name, no winner, no Mega Prize challenge."""
    with app_client(settings(tmp_path)) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        seed(client)
        act(client, actions.set_challenge_window, "2000-01-01", None)
        public = ["/api/challenges", "/api/achievements", "/api/achievements/recent", f"/api/players/{BLUE}/achievements",
                  "/api/leaderboard/stats", "/api/leaderboard?stat=achievements&min_games=1", "/api/overview", "/api/health"]
        for url in public:
            r = client.get(url)
            assert r.status_code in (200, 404), url
            assert not any(w.encode() in r.content for w in WORDS), url
        assert client.get("/mega-prizes/jack.jpg").status_code == 404  # the pictures are not public files
        assert client.get("/jack.jpg").status_code == 404


def test_csv_cannot_run_a_formula(tmp_path):
    data = {"period": {"start": "2026-01-01", "end": None},
            "prizes": [{"prize": "P", "challenge": "C", "target": 750,
                        "winners": [{"name": '=HYPERLINK("http://evil","x")', "user_id": "1", "discord_id": "@x", "count": 750}]}]}
    text = mega_prizes.csv_bytes(data).decode("utf-8-sig")
    assert "'=HYPERLINK" in text and ",'@x," in text and '\r\n=' not in text and ',=H' not in text


def test_the_prize_rule_is_not_part_of_the_public_rule_list():
    from backend.achievements import MEGA_COMBAT, RULES
    assert MEGA_COMBAT not in RULES and not any(r.prize for r in RULES)


def test_console_overview_carries_the_saved_visibility(tmp_path, discord):
    """The Console form opens with the saved launch date, end date and "Visible to" (they are kept in the database)."""
    with app_client(settings(tmp_path)) as client:
        login(client, MEMBER)
        act(client, actions.set_challenge_window, "2026-11-02", "2026-12-01")
        act(client, actions.set_achievements_visibility, "preview")
        challenge = client.get("/api/admin/console/overview").json()["challenge"]
        assert (challenge["start"], challenge["end"], challenge["visibility"]) == ("2026-11-02", "2026-12-01", "preview")
