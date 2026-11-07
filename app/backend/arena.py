"""Public Echo Arena matches per player, counted from the live Nakama match list (user, 2026-11-04). Completely
separate from the Combat stats: own tables (arena_players, arena_counted), own module, own endpoint.

The list (https://g.echovrce.com/status/matches) only shows the matches running right now, so this polls it and
remembers who is in which public Arena match. A player counts once per match after MIN_PRESENT_S (4 minutes) in it.
Polling is kept very low (user, 2026-11-04): one small GET per `arena_poll_s` (10 s since 2026-11-05, was 60 s), the database is only written
when a match is counted, a failed request backs off (x2, up to 5 minutes), and the rest of the state is in memory."""

import logging
import threading
import time
from datetime import datetime, timezone

import httpx
from sqlalchemy import delete, select

from .admin_actions import mega_window
from .models import (ArenaCounted, ArenaPlayer, NakamaAccount, NakamaCombatCounted, NakamaCombatPlayer, Player,
                     PlayerProfile)

URL = "https://g.echovrce.com/status/matches"
MIN_PRESENT_S = 240.0  # time spent in one match before it counts (user, 2026-11-04)
MIN_TEAM = 3  # a match needs 3v3 or bigger, or at least MIN_SEEN players seen in it (not spectators), when it would count (user, 2026-11-04)
MIN_SEEN = 6
TIMEOUT_S = 5
MAX_BYTES = 5_000_000
MAX_BACKOFF_S = 300.0
KEEP_COUNTED_S = 2 * 86400
PRUNE_EVERY_S = 3600
ACCOUNT_REFRESH_S = 600  # an account already stored is written again at most this often (last seen)
WINDOW_CHECK_S = 300  # the challenge period is looked up at most this often
NON_PLAYER_TEAMS = {"spectator", "moderator"}  # on the match list's "team" field: watching, not playing, so never counted (user, 2026-11-04)
STATUS_OK_POLLS = 3  # the Console says "working" when the list was read within this many polls
log = logging.getLogger("uvicorn.error")


def _stamp(t: float | None) -> str | None:
    """With its zone: the Console shows it in the viewer's own time."""
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds") if t is not None else None


def is_public_arena(label: dict) -> bool:
    mode = str(label.get("mode") or "")
    return label.get("lobby_type") == "public" and mode.startswith("echo_arena") and "private" not in mode


def is_public_combat(label: dict) -> bool:
    mode = str(label.get("mode") or "")
    return label.get("lobby_type") == "public" and mode.startswith("echo_combat") and "private" not in mode


class _Kind:
    """One game type counted from the same list (Arena, Combat): its own tables and in-memory state, same rules
    (user, 2026-11-05: the Echo Combat Mega Prize is counted from the Nakama match list too, no longer from the replays)."""

    def __init__(self, name, is_match, player_model, counted_model, keep_s):
        self.audited = counted_model is NakamaCombatCounted  # only Combat keeps the audit columns
        self.keep_s = keep_s  # counted rows older than this are pruned; None = kept for good (Combat history)
        self.name, self.is_match, self.player_model, self.counted_model = name, is_match, player_model, counted_model
        self.seen: dict[tuple[str, str], list[float]] = {}  # (match id, user id) -> [last seen, seconds present]
        self.counted: set[tuple[str, str]] = set()
        self.loaded = False
        self.pruned = 0.0
        self.last_counted: float | None = None
        self.counted_since_start = 0
        self.matches_now = self.players_now = 0
        self.sizes: dict[str, tuple[int, int, int]] = {}  # match id -> (blue, orange, spectators) at the latest poll


class Tracker:
    def __init__(self, sessionmaker, settings, fetch=None):
        self.sessionmaker, self.interval = sessionmaker, settings.arena_poll_s
        self.fetch = fetch or self._fetch
        self.arena = _Kind("arena", is_public_arena, ArenaPlayer, ArenaCounted, KEEP_COUNTED_S)
        self.combat = _Kind("combat", is_public_combat, NakamaCombatPlayer, NakamaCombatCounted, None)
        self._kinds = (self.arena, self.combat)
        self._accounts: dict[str, tuple] = {}  # Nakama user id -> (discord id, username, display name, written at)
        self.accounts_seen = 0
        self._window: tuple[float, bool] = (0.0, False)  # (checked at, inside the challenge period)
        # for the Console's status line; in memory, costs no request. Unix times.
        self._last_ok: float | None = None
        self._last_error: tuple[float, str] | None = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="arena-poll", daemon=True)

    def start(self) -> None:
        if self.interval > 0:
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _fetch() -> dict:
        r = httpx.get(URL, timeout=TIMEOUT_S, headers={"User-Agent": "EchoVR-Replay-Stats"})
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:  # the list is a few KB: a huge answer is not it
            raise ValueError("match list too large")
        return r.json()

    def _run(self) -> None:
        wait = self.interval
        while not self._stop.wait(wait):
            try:
                self.poll()
                wait = self.interval
            except Exception as e:  # network down, bad JSON...: ask less often until it works again
                wait = min(max(wait, self.interval) * 2, MAX_BACKOFF_S)
                # first line only: a database error carries its SQL statement, which the Console must not show (Review SEC-3)
                self._last_error = (time.time(), f"{type(e).__name__}: {str(e).splitlines()[0] if str(e) else ''}"[:160])
                log.warning("arena poll failed (%s); next try in %d s", e, wait)

    def _in_period(self, now: float) -> bool:
        """Counting starts at the Mega Prize period (user, 2026-11-05; before that the challenge period, 2026-11-04): nothing before its start date or after its end.
        No start date set = nothing counts yet (unlike Combat, there is no archive to count from)."""
        if now - self._window[0] >= WINDOW_CHECK_S or self._window[0] == 0.0:
            with self.sessionmaker() as db:
                start, end = mega_window(db)
            today = datetime.fromtimestamp(now).date().isoformat()
            self._window = (now, bool(start) and start <= today and (not end or today <= end))
        return self._window[1]

    def poll(self, now: float | None = None) -> int:
        """One look at the list; returns how many player-matches were newly counted (Arena and Combat)."""
        now = time.time() if now is None else now
        data = self.fetch()
        self._collect_accounts(data, now)  # every poll, inside the period or not: who is playing, and their links
        self._last_ok = now
        if not self._in_period(now):
            for k in self._kinds:
                k.seen.clear()  # time spent before the period does not count towards the 4 minutes
            return 0  # nothing is counted outside the period
        return sum(self._poll_kind(k, data, now) for k in self._kinds)

    def _collect_accounts(self, data: dict, now: float) -> None:
        """Every poll: store each account on the list (any lobby, spectators too: it is only who they are, no count) and link
        it to its replay player. The database is touched only for a new or changed account, or an old one gone stale."""
        seen: dict[str, dict] = {}
        for label in data.get("labels") or []:
            for p in label.get("players") or []:
                if p.get("user_id"):
                    seen[str(p["user_id"])] = p
        todo = []
        for uid, p in seen.items():
            row = (p.get("discord_id") or None, p.get("username") or "?", p.get("display_name") or None)
            old = self._accounts.get(uid)
            if old is None or old[:3] != row or now - old[3] >= ACCOUNT_REFRESH_S:
                todo.append((uid, row))
        self.accounts_seen = len(seen)
        if not todo:
            return
        stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        with self.sessionmaker() as db:
            for uid, (discord_id, username, display) in todo:
                acc = db.get(NakamaAccount, uid)
                if acc is None:
                    acc = NakamaAccount(user_id=uid, discord_id=discord_id, username=username, display_name=display,
                                        first_seen_at=stamp, last_seen_at=stamp)
                    db.add(acc)
                acc.discord_id, acc.username, acc.display_name, acc.last_seen_at = discord_id or acc.discord_id, username, display or acc.display_name, stamp
                self._link(db, acc)
                self._accounts[uid] = (discord_id, username, display, now)
            db.commit()

    @staticmethod
    def _link(db, acc: NakamaAccount) -> None:
        """Replay player of this account: a bot / admin link first, then a replay player whose id IS the Discord id."""
        acc.replay_user_id = acc.link = None
        if not acc.discord_id:
            return
        profile = db.scalar(select(PlayerProfile.user_id).where(PlayerProfile.discord_id == acc.discord_id))
        if profile is not None:
            acc.replay_user_id, acc.link = profile, "profile"
        elif db.scalar(select(Player.id).where(Player.user_id == acc.discord_id)) is not None:
            acc.replay_user_id, acc.link = acc.discord_id, "player_id"

    def _poll_kind(self, k: _Kind, data: dict, now: float) -> int:
        if not k.loaded:  # after a restart: what was already counted
            with self.sessionmaker() as db:
                k.counted = {(m, u) for m, u in db.execute(select(k.counted_model.match_id, k.counted_model.user_id))}
            k.loaded = True
        present: dict[tuple[str, str], dict] = {}
        barred: set[str] = set()
        small: set[tuple[str, str]] = set()  # in a match that is smaller than 3v3 right now: may not count yet
        k.sizes = {}
        for label in data.get("labels") or []:
            if k.is_match(label):
                teams = [p.get("team") for p in label.get("players") or []]
                k.sizes[str(label.get("id"))] = (teams.count("blue"), teams.count("orange"), sum(1 for t in teams if t in NON_PLAYER_TEAMS))
                seen = sum(1 for t in teams if t not in NON_PLAYER_TEAMS)
                too_small = seen < MIN_SEEN and (teams.count("blue") < MIN_TEAM or teams.count("orange") < MIN_TEAM)
                for p in label.get("players") or []:
                    if not (p.get("user_id") and label.get("id")):
                        continue
                    if p.get("team") in NON_PLAYER_TEAMS:
                        barred.add(str(p["user_id"]))
                    else:
                        present[(str(label["id"]), str(p["user_id"]))] = p
                        if too_small:
                            small.add((str(label["id"]), str(p["user_id"])))
        if barred:
            self._purge(k, barred)
            present = {key: v for key, v in present.items() if key[1] not in barred}
        new: list[tuple[tuple[str, str], dict]] = []
        for key, p in present.items():
            if key in k.seen:
                last, secs = k.seen[key]
                # a gap (left and came back, or a missed poll) adds at most two intervals: only time in the match counts
                secs += min(now - last, 2 * self.interval)
            else:
                secs = 0.0
            k.seen[key] = [now, secs]
            if secs >= MIN_PRESENT_S and key not in k.counted and key not in small:  # needs 3+ per team (user, 2026-11-04)
                new.append((key, p))
        for key in [key for key, v in k.seen.items() if key not in present and now - v[0] > 2 * self.interval + 1]:
            del k.seen[key]  # gone from the list
        prune = k.keep_s is not None and now - k.pruned >= PRUNE_EVERY_S
        if new or prune:
            self._save(k, new, now, prune)
        k.matches_now = sum(1 for label in data.get("labels") or [] if k.is_match(label))
        k.players_now = len(present)
        if new:
            k.last_counted = now
            k.counted_since_start += len(new)
        return len(new)

    def status(self, now: float | None = None) -> dict:
        """The Console's status line. state: off, outside_period, waiting (no answer yet), working, failing."""
        now = time.time() if now is None else now
        recent = self._last_ok is not None and now - self._last_ok <= STATUS_OK_POLLS * self.interval
        if self.interval <= 0 or not self._thread.is_alive():
            state = "off"
        elif not self._window[1]:
            state = "outside_period" if self._window[0] else "waiting"
        elif recent:
            state = "working"
        else:
            state = "failing" if self._last_error else "waiting"
        a, c = self.arena, self.combat
        return {"state": state, "last_ok_at": _stamp(self._last_ok), "last_counted_at": _stamp(a.last_counted),
                "matches_now": a.matches_now, "players_now": a.players_now, "counted_since_start": a.counted_since_start,
                "accounts_now": self.accounts_seen,
                "combat": {"last_counted_at": _stamp(c.last_counted), "matches_now": c.matches_now,
                           "players_now": c.players_now, "counted_since_start": c.counted_since_start},
                "last_error": self._last_error[1] if self._last_error else None,
                "last_error_at": _stamp(self._last_error[0]) if self._last_error else None}

    def _purge(self, k: _Kind, user_ids: set[str]) -> None:
        """Spectators and moderators keep no record (user, 2026-11-04): whoever is seen as one loses their counted matches."""
        with self.sessionmaker() as db:
            hit = db.scalars(select(k.player_model.user_id).where(k.player_model.user_id.in_(user_ids))).all()
            if hit:
                db.execute(delete(k.counted_model).where(k.counted_model.user_id.in_(hit)))
                db.execute(delete(k.player_model).where(k.player_model.user_id.in_(hit)))
                db.commit()
        k.counted = {key for key in k.counted if key[1] not in user_ids}
        k.seen = {key: v for key, v in k.seen.items() if key[1] not in user_ids}

    def _save(self, k: _Kind, new, now: float, prune: bool) -> None:
        stamp = datetime.fromtimestamp(now).isoformat(timespec="seconds")
        with self.sessionmaker() as db:
            for (match_id, user_id), p in new:
                audit = {}
                if k.audited:
                    blue, orange, spectators = k.sizes.get(match_id, (None, None, None))
                    audit = {"present_s": k.seen.get((match_id, user_id), [0, None])[1], "blue": blue, "orange": orange, "spectators": spectators}
                db.add(k.counted_model(match_id=match_id, user_id=user_id, counted_at=now, **audit))
                row = db.get(k.player_model, user_id)
                if row is None:
                    row = k.player_model(user_id=user_id, username=p.get("username") or "?", display_name=p.get("display_name"),
                                         discord_id=p.get("discord_id") or None, matches=0, last_match_at=stamp)
                    db.add(row)
                row.matches += 1
                row.username = p.get("username") or row.username
                row.display_name = p.get("display_name") or row.display_name
                row.discord_id = p.get("discord_id") or row.discord_id
                row.last_match_at = stamp
                k.counted.add((match_id, user_id))
            if prune:
                db.execute(delete(k.counted_model).where(k.counted_model.counted_at < now - k.keep_s))
            db.commit()
        if prune:
            k.pruned = now
            k.loaded = False  # re-read what is still counted (pruned rows leave memory too)
