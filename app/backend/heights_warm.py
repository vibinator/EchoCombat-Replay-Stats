"""Prepares the heatmaps of the most active players while the server is idle. First it writes the heights.bin files (heatmaps3d.py) of the most active players' matches while the server is idle (user,
2026-11-10), so their 3D heatmaps are fast the first time too: these are the players with thousands of matches, where
the first view would otherwise unpack thousands of 3D track files.

One thread, one match at a time, newest first, and only while no replay is being processed; after each match it
rests as long as the match took, so it never uses more than half of one core. New matches get their file when they
are processed (worker.py); this is for the matches from before, and is done once they all have one (it looks again
every RECHECK_S for players who entered the top since).

Then (when `app` is given and answers are kept on disk, cache.py) it builds the two long heatmaps of each of these
players on every map they played (all time, all matches, by team: flat and 3D) and saves them, so the first look at
them is instant. A saved one is only built again when the player has a new match on that map."""

import logging
import threading
import time

from sqlalchemy import func, select

from . import heatmaps3d, tracks, tracks3d
from .models import Match, MatchPlayer, Player

log = logging.getLogger(__name__)

TOP_PLAYERS = 100  # by matches played
START_AFTER_S = 120  # after the server starts: the caches that people wait for are warmed first
BUSY_WAIT_S = 20  # between looks while replays are being processed
RECHECK_S = 6 * 3600
PROGRESS_EVERY = 2000


def replay_ids(sessions, top: int = TOP_PLAYERS) -> list[int]:
    """The replay ids of every match with tracks that one of the `top` most active players is in, newest first."""
    with sessions() as db:
        players = db.scalars(select(MatchPlayer.player_id).group_by(MatchPlayer.player_id)
                             .order_by(func.count().desc()).limit(top)).all()
        if not players:
            return []
        return list(db.scalars(
            select(Match.replay_id).where(Match.has_tracks, Match.id.in_(
                select(MatchPlayer.match_id).where(MatchPlayer.player_id.in_(players))))
            .order_by(Match.started_at.desc())))


def players_and_maps(sessions, top: int = TOP_PLAYERS) -> list[tuple[str, str]]:
    """(user id, map) for every map each of the `top` most active players has a match with tracks on, the most
    active player first."""
    with sessions() as db:
        players = db.execute(select(MatchPlayer.player_id, Player.user_id).join(Player, Player.id == MatchPlayer.player_id)
                             .group_by(MatchPlayer.player_id).order_by(func.count().desc()).limit(top)).all()
        out = []
        for player_id, user_id in players:
            maps = db.scalars(select(Match.map).join(MatchPlayer, MatchPlayer.match_id == Match.id)
                              .where(MatchPlayer.player_id == player_id, Match.has_tracks)
                              .group_by(Match.map).order_by(func.count().desc())).all()
            out += [(user_id, m) for m in maps]
        return out


def missing(processed_dir, ids: list[int]) -> list[int]:
    """Those with 3D tracks and no heights.bin."""
    out = []
    for rid in ids:
        p3 = tracks3d.tracks3d_path(processed_dir, rid)
        if not heatmaps3d.heights_path(p3).exists() and p3.exists():
            out.append(rid)
    return out


def write_one(processed_dir, rid: int) -> bool:
    return heatmaps3d.save_heights(tracks.tracks_path(processed_dir, rid), tracks3d.tracks3d_path(processed_dir, rid))


class HeightsWarmer:
    def __init__(self, sessions, settings, worker, app=None):
        self.sessions, self.settings, self.worker, self.app = sessions, settings, worker, app
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="heights-warm", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def run_once(self, rest: bool = True) -> tuple[int, int]:
        """(written, not written) for everything missing now. Waits while replays are processed; ends early on stop."""
        todo = missing(self.settings.processed_dir, replay_ids(self.sessions))
        if todo:
            log.info("Heights of the %d most active players: %d matches to write", TOP_PLAYERS, len(todo))
        done = failed = 0
        for rid in todo:
            while self.worker.busy and not self._stop.wait(BUSY_WAIT_S):
                pass
            if self._stop.is_set():
                break
            started = time.monotonic()
            try:
                ok = write_one(self.settings.processed_dir, rid)
            except Exception as e:  # noqa: BLE001 - one damaged match must not end the pass
                log.warning("Heights of replay %s not written: %s: %s", rid, type(e).__name__, e)
                ok = False
            done, failed = done + ok, failed + (not ok)
            if (done + failed) % PROGRESS_EVERY == 0:
                log.info("Heights: %d of %d matches", done + failed, len(todo))
            if rest and self._stop.wait(time.monotonic() - started):
                break
        if todo:
            log.info("Heights: %d written, %d not (no readable tracks, or the folder cannot be written)", done, failed)
        return done, failed

    def build_heatmaps(self, rest: bool = True) -> int:
        """The long heatmaps of the most active players onto disk; returns how many were built (those still current
        are left). Waits while replays are processed; ends early on stop."""
        from .api.players import prebuild_heatmaps  # here: the api package imports the app's modules

        if self.app is None:
            return 0
        built = 0
        for user_id, map_ in players_and_maps(self.sessions):
            while self.worker.busy and not self._stop.wait(BUSY_WAIT_S):
                pass
            if self._stop.is_set():
                break
            started = time.monotonic()
            try:
                n = prebuild_heatmaps(self.app, user_id, map_)
            except Exception as e:  # noqa: BLE001 - one player must not end the pass
                log.warning("Heatmaps of %s on %s not built: %s: %s", user_id, map_, type(e).__name__, e)
                continue
            built += n
            if n and rest and self._stop.wait(time.monotonic() - started):
                break
        if built:
            log.info("Heatmaps of the %d most active players: %d built and saved", TOP_PLAYERS, built)
        return built

    def _run(self) -> None:
        wait = START_AFTER_S
        while not self._stop.wait(wait):
            try:
                self.run_once()
                self.build_heatmaps()
            except Exception:  # noqa: BLE001 - try again at the next look
                log.exception("Heights pass failed")
            wait = RECHECK_S
