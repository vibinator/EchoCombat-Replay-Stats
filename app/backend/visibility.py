"""Stats hidden from players (admin console: "hide-stats"), site-wide or for chosen players. Hidden stats are left out
of the API answers for every visitor except logged-in admins (user, 2026-11-02).

Who sees what (2026-11-20, to let Cloudflare keep the home page, leaderboard and profiles again): an answer asked for
without `?view=admin` is always the public one (hidden stats left out) and nobody is asked who they are, so it is the
same for everyone and Cloudflare may keep it. An admin's page adds `view=admin` (api.ts, from the echovr_admin cookie
that /api/auth/me sets); only then is the login checked (auth.is_admin), which marks the answer per visitor, so
Cloudflare never keeps an admin's copy, and a non-admin who adds it still gets the public stats. While nothing is
hidden, answers are shared and edge-cached for everyone.

A View is part of the cache key of every answer that has win-loss stats: (hidden site-wide, players hidden)."""

import time
import weakref
from typing import NamedTuple

from sqlalchemy import select

from . import auth
from .admin_actions import hidden_players, hidden_stats
from .models import PlayerAlias

TTL_S = 2.0  # the admin console is another process: a change shows on the website within this
ADMIN_PARAM, ADMIN_VALUE = "view", "admin"  # ?view=admin: the admin's version (login checked, never shared)
_memo: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()  # sessionmaker -> (read at, groups, players)


class View(NamedTuple):
    everything: bool  # hidden site-wide
    players: frozenset[str]  # main user ids hidden one by one

    def hides(self, *user_ids: str) -> bool:
        """Whether the stats of a player (any of the ids given: the asked id, its main id) are hidden."""
        return self.everything or bool(self.players.intersection(user_ids))


ALL_SHOWN = View(False, frozenset())


def _settings(sessions) -> tuple[frozenset[str], dict[str, frozenset[str]]]:
    now = time.monotonic()
    memo = _memo.get(sessions)
    if memo is not None and now - memo[0] < TTL_S:
        return memo[1], memo[2]
    with sessions() as db:
        groups = frozenset(hidden_stats(db))
        players = {"win_loss": frozenset(hidden_players(db, "win_loss"))}
    _memo[sessions] = (now, groups, players)
    return groups, players


def hidden_groups(sessions) -> frozenset[str]:
    return _settings(sessions)[0]


def view(request, group: str = "win_loss") -> View:
    groups, players = _settings(request.app.state.sessionmaker)
    seen = View(group in groups, players.get(group, frozenset()))
    if seen == ALL_SHOWN:
        return ALL_SHOWN
    if request.query_params.get(ADMIN_PARAM) != ADMIN_VALUE:
        return seen  # the public answer: who is asking is not looked at, so it may be shared (Cloudflare)
    return ALL_SHOWN if auth.is_admin(request) else seen


def win_loss(request) -> bool:
    """Whether this visitor sees win-loss stats site-wide (team win rates, the leaderboard's win stats)."""
    return not view(request).everything


def ids(db, user_id: str) -> tuple[str, ...]:
    """The asked id and, for a merged id, its main player's: either may be the one hidden."""
    alias = db.get(PlayerAlias, user_id)
    return (user_id, alias.main_user_id) if alias else (user_id,)


def hidden_player_ids(db, v: View) -> set[int]:
    """players.id of the players hidden one by one (their leaderboard rows lose win-loss)."""
    from .models import Player
    if not v.players:
        return set()
    return set(db.scalars(select(Player.id).where(Player.user_id.in_(v.players))))


WIN_LOSS_KEYS = ("wins", "losses", "win_rate", "result")


def without(d: dict, keys=WIN_LOSS_KEYS) -> dict:
    return {k: v for k, v in d.items() if k not in keys}
