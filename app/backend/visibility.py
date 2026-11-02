"""Stats hidden from players (admin console: "hide-stats"). A hidden group is left out of the API answers for every
visitor except logged-in admins (user, 2026-11-02). Asking who the visitor is marks the answer per visitor
(auth.viewer), so Cloudflare never keeps an admin's copy for others or the other way round; while nothing is hidden,
answers stay shared and edge-cached as before."""

import time
import weakref

from . import auth
from .admin_actions import hidden_stats

TTL_S = 2.0  # the admin console is another process: a change shows on the website within this
_memo: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()  # sessionmaker -> (read at, hidden groups)


def hidden_groups(sessions) -> frozenset[str]:
    now = time.monotonic()
    memo = _memo.get(sessions)
    if memo is not None and now - memo[0] < TTL_S:
        return memo[1]
    with sessions() as db:
        groups = frozenset(hidden_stats(db))
    _memo[sessions] = (now, groups)
    return groups


def shows(request, group: str) -> bool:
    """Whether this visitor sees stat group `group`. Part of the cache key of every answer that has it."""
    if group not in hidden_groups(request.app.state.sessionmaker):
        return True
    return auth.is_admin(request)


def win_loss(request) -> bool:
    return shows(request, "win_loss")


WIN_LOSS_KEYS = ("wins", "losses", "win_rate", "result")


def without(d: dict, keys=WIN_LOSS_KEYS) -> dict:
    return {k: v for k, v in d.items() if k not in keys}
