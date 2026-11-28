"""A player's challenges kept like the long heatmaps (user, 2026-11-27: a profile with 7,700 games took 25-60 s on the NAS
the first time after every restart, every midnight, or when other pages pushed it out of memory): their own stamp, no day
in the key, kept on disk, and built ahead for the most active players. The answer stays one Cloudflare may keep."""

import pytest
import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions, heights_warm
from backend.api import achievements

BLUE = str(rf.BIG_USER_ID)


def match(*players):
    return rf.plain(rf.lines(20, teams=[{"players": [players[0]]}, {"players": [players[1]]}, {}]))


def no_build(patch):
    patch.setattr(achievements, "_player_result", lambda *a, **k: pytest.fail("worked out again"))


def test_kept_on_disk_and_not_rebuilt_for_other_players_replays(tmp_path):
    settings = make_settings(tmp_path, answer_cache_mb=8)
    with app_client(settings) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        first = c.get(f"/api/players/{BLUE}/achievements").json()
        assert len(list((settings.data_dir / "cache" / "answers").glob("*.bin"))) == 1
        add(c, {"dyson/1.echoreplay": match(rf.player(7, "Seven"), rf.player(8, "Eight", 1))})  # somebody else's match
        with pytest.MonkeyPatch.context() as patch:
            no_build(patch)
            assert c.get(f"/api/players/{BLUE}/achievements").json()["games"] == first["games"]

    with app_client(settings) as c:  # the server started again: the saved answer is used
        with pytest.MonkeyPatch.context() as patch:
            no_build(patch)
            again = c.get(f"/api/players/{BLUE}/achievements")
        assert again.status_code == 200 and again.json()["items"][:3] == first["items"][:3]


def test_a_new_match_of_the_player_builds_it_again(tmp_path):
    with app_client(make_settings(tmp_path, answer_cache_mb=8)) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        assert c.get(f"/api/players/{BLUE}/achievements").json()["games"] == 1
        add(c, {"dyson/1.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two(), start=rf.START.replace(hour=rf.START.hour + 1)))})
        assert c.get(f"/api/players/{BLUE}/achievements").json()["games"] == 2  # tests rebuild before answering


def test_built_ahead_for_the_most_active_players(tmp_path):
    settings = make_settings(tmp_path, answer_cache_mb=8)
    with app_client(settings) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        warmer = heights_warm.HeightsWarmer(c.app.state.sessionmaker, settings, c.app.state.worker, c.app)
        assert warmer.build_challenges(rest=False) == 4  # all four players of the 2v2 match
        assert warmer.build_challenges(rest=False) == 0  # still current
        with pytest.MonkeyPatch.context() as patch:
            no_build(patch)
            r = c.get(f"/api/players/{BLUE}/achievements")
        assert r.status_code == 200 and r.json()["games"] == 1  # from the saved answer


def test_cloudflare_may_keep_the_public_answer(tmp_path):
    """Once challenges are public the answer is the same for everyone: Cloudflare keeps it (D53). Pins and who may edit
    them come from a separate per-visitor call, never from this answer."""
    with app_client(make_settings(tmp_path, answer_cache_mb=8, edge_cache_s=300)) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        r = c.get(f"/api/players/{BLUE}/achievements", headers={"X-EchoVR": "1"})
        assert r.status_code == 200
        assert r.headers["Cloudflare-CDN-Cache-Control"].startswith("max-age=300")
        assert "private" not in r.headers["Cache-Control"]
        pins = c.get(f"/api/profiles/{BLUE}/pins", headers={"X-EchoVR": "1"})
        assert pins.headers["Cloudflare-CDN-Cache-Control"] == "no-store"


def test_a_damaged_saved_answer_is_built_again(tmp_path):
    """Review 2026-11-27: Disk.load checks only the header; a body cut short (power cut on the NAS) must not 500 forever."""
    settings = make_settings(tmp_path, answer_cache_mb=8)
    with app_client(settings) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        assert c.get(f"/api/players/{BLUE}/achievements").status_code == 200
    (saved,) = (settings.data_dir / "cache" / "answers").glob("*.bin")
    saved.write_bytes(saved.read_bytes()[:-40])  # header intact, gzip body cut short
    with app_client(settings) as c:
        r = c.get(f"/api/players/{BLUE}/achievements")
        assert r.status_code == 200 and r.json()["games"] == 1


def test_pins_ride_in_the_shared_answer(tmp_path):
    """Pins are public: anonymous visitors read them from the answer Cloudflare keeps, with no per-visitor request."""
    from backend.achievements import RULES
    from backend.models import ChallengePin

    with app_client(make_settings(tmp_path, answer_cache_mb=8)) as c:
        add(c, {"dyson/0.echoreplay": rf.plain(rf.lines(20, teams=rf.two_v_two()))})
        act(c, actions.set_challenge_window, "2026-01-01", None)
        with c.app.state.sessionmaker() as db:
            db.add(ChallengePin(user_id=BLUE, achievement_id=RULES[-1].id, pinned_at="2026-11-27T10:00:00"))
            db.commit()
        assert c.get(f"/api/players/{BLUE}/achievements").json()["pins"] == [RULES[-1].id]
