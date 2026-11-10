"""Achievement calculations outside the web server's threads (api/achievements.py, helper processes; 2026-11-10):
same answers as calculated in place, a ranking still being built answers "try again" instead of holding the request,
and the saved per-player results survive an update of the site."""

import pickle
import threading
from concurrent.futures import Future, ThreadPoolExecutor

import replay_factory as rf
from app_helpers import act, add, app_client, make_settings

from backend import admin_actions as actions
from backend import version
from backend.api import achievements as api

BLUE = str(rf.BIG_USER_ID)


class SideLanes:
    """Stands in for the import worker: runs the job in a thread, like a helper process would (the job only gets the
    database path, so it opens its own read-only sessions exactly as in a real helper)."""

    def __init__(self):
        self.pool = ThreadPoolExecutor(2)
        self.jobs: list[tuple[str, str]] = []

    def run_side(self, fn, *args, lane="side") -> Future:
        self.jobs.append((lane, fn.__name__))
        return self.pool.submit(fn, *args)


def test_helper_process_gives_the_same_answers(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        add(client, {f"dyson/{i}.echoreplay": rf.plain(rf.lines(20)) for i in range(2)})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        paths = [f"/api/players/{BLUE}/achievements", "/api/achievements", "/api/achievements/recent",
                 "/api/leaderboard?stat=achievements&min_games=1", "/api/leaderboard/achievers"]
        here = [client.get(p).json() for p in paths]
        assert client.get("/api/players/nobody/achievements").status_code == 404

        # the same questions, now answered through the helper lanes
        sessions = client.app.state.sessionmaker
        api._cache.pop(id(sessions), None)
        for name in ("value_cache", "response_cache"):  # the answers kept from the first round
            if (store := getattr(client.app.state, name, None)) is not None:
                store.entries.clear()
        lanes = SideLanes()
        monkeypatch.setattr(api, "OFFLOAD_MIN_GAMES", 1)
        api.offload(sessions, lanes, settings)
        try:
            assert client.get(paths[3]).json() == here[3]  # waits for the ranking; the catalogue and the feed do not
            assert [client.get(p).json() for p in paths] == here
            assert client.get("/api/players/nobody/achievements").status_code == 404
            assert ("ranking", "_ranking_job") in lanes.jobs and ("side", "_player_job") in lanes.jobs
        finally:
            api.stop_offload(sessions)


def test_helper_that_fails_falls_back_to_this_process(tmp_path, monkeypatch):
    class Broken:
        def run_side(self, fn, *args, lane="side"):
            raise RuntimeError("The worker is stopping")

    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        sessions = client.app.state.sessionmaker
        monkeypatch.setattr(api, "OFFLOAD_MIN_GAMES", 1)
        api.offload(sessions, Broken(), settings)
        try:
            assert client.get(f"/api/players/{BLUE}/achievements").json()["games"] == 1
            assert client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1}).status_code == 200
        finally:
            api.stop_offload(sessions)


def test_ranking_still_being_built_says_try_again(tmp_path, monkeypatch):
    """No ranking yet and the build takes longer than FIRST_WAIT_S: 503 with a message, not a request held for minutes.
    Pages that can do without the ranking (the catalogue, recent medals) answer at once."""
    release = threading.Event()

    class Slow(SideLanes):
        def run_side(self, fn, *args, lane="side"):
            def job():
                release.wait(20)
                return fn(*args)
            return self.pool.submit(job)

    settings = make_settings(tmp_path)
    with app_client(settings) as client:
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        act(client, actions.set_challenge_window, "2026-01-01", None)
        sessions = client.app.state.sessionmaker
        api._cache.pop(id(sessions), None)
        monkeypatch.setattr(api, "FIRST_WAIT_S", 0.3)
        api.offload(sessions, Slow(), settings)
        try:
            r = client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1})
            assert r.status_code == 503 and r.json()["error_code"] == "ranking_building"
            assert client.get("/api/achievements").status_code == 200 and client.get("/api/achievements/recent").json() == []
            release.set()
            monkeypatch.setattr(api, "FIRST_WAIT_S", 20)
            assert client.get("/api/leaderboard", params={"stat": "achievements", "min_games": 1}).status_code == 200
        finally:
            release.set()
            api.stop_offload(sessions)


def test_saved_results_survive_a_new_version_and_keep_medal_times(tmp_path, monkeypatch):
    """Until 2026-11-10 the saved results carried the app version: every update evaluated all players again."""
    with app_client(make_settings(tmp_path)) as client:
        sessions = client.app.state.sessionmaker
        add(client, {"dyson/0.echoreplay": rf.plain(rf.lines(20))})
        first = api._compute(sessions, (None, None))
        signature, saved = pickle.loads(api._cache_file(sessions).read_bytes())
        assert signature == api._signature() and saved
        assert all(entry[3] is not None for entry in saved.values())  # medal times of the players active lately

        monkeypatch.setattr(version, "VERSION", "2099.01.01.1")
        monkeypatch.setattr(version, "APP_VERSION", "Beta v99.1.1-1")
        assert api._signature() == signature
        api._evaluated.clear()  # as after a restart
        evaluated = []
        real = api.evaluate
        monkeypatch.setattr(api, "evaluate", lambda games: evaluated.append(len(games)) or real(games))
        timed = []
        real_times = api.medal_times
        monkeypatch.setattr(api, "medal_times", lambda games: timed.append(len(games)) or real_times(games))
        assert api._compute(sessions, (None, None)) == first and evaluated == [] and timed == []


def test_every_api_answer_names_its_version(tmp_path):
    with app_client(make_settings(tmp_path)) as client:
        assert client.get("/api/health").headers["x-echovr-build"] == version.VERSION
        assert client.get("/api/matches/999999").headers["x-echovr-build"] == version.VERSION  # errors too
        assert "x-echovr-build" not in client.get("/").headers
