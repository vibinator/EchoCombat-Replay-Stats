"""Discord login, only for previewing achievements before their launch date (D41). Login = OAuth2 "identify" (who
you are); access = a preview role in the EchoVR Combat Discord server, checked with the bot token (no user token is
kept). The session is a signed cookie: nothing is written to the database, so the website stays read-only (D38)."""

import base64
import functools
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from typing import Callable
from urllib.parse import urlencode

import httpx
from fastapi import Request

from .admin_actions import discord_roles
from .config import Settings

API = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
SESSION_COOKIE = "echovr_session"
STATE_COOKIE = "echovr_oauth"
SESSION_DAYS = 30
STATE_S = 600  # time allowed on Discord's login page
ROLE_CHECK_S = 300  # a removed role stops working within 5 minutes
ROLE_RETRY_S = 30  # Discord unreachable: keep the last answer, ask again soon

_roles: dict[str, tuple[float, frozenset[str]]] = {}  # discord user id -> (valid until, their role ids in the server)
_roles_lock = threading.Lock()
log = logging.getLogger("uvicorn.error")


# --- one limiter for every Discord request (user, 2026-11-10: never reach, or come near, Discord's limits) ------------
# Discord allows 50 requests a second per bot (the website shares the bot's token with the user's Discord bot) and blocks an
# IP address for a while after 10,000 refused requests (401 / 403 / 429) in 10 minutes. The site stays far below both:
DISCORD_PER_S = 5.0  # all of the site's Discord requests together: a tenth of the per-bot limit
DISCORD_BURST = 10  # at once, after a quiet spell
DISCORD_WAIT_S = 2.0  # a request waits at most this long for its turn, then fails like an unreachable Discord
DISCORD_PAUSE_MAX_S = 600.0  # the longest a 429's Retry-After is obeyed for
INVALID_WINDOW_S = 600.0
INVALID_MAX = 500  # refused answers in INVALID_WINDOW_S that stop every Discord request for INVALID_WINDOW_S (Discord: 10,000)


class DiscordPaused(httpx.HTTPError):
    """No request sent: the site is holding back (over its own rate, Discord said 429, or too many refusals). Every caller
    already treats an httpx.HTTPError as "Discord unreachable": the last known answer is kept."""


class DiscordLimiter:
    def __init__(self):
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.tokens, self.last = float(DISCORD_BURST), time.monotonic()
        self.paused_until, self.pause_reason = 0.0, ""
        self.invalid: list[float] = []

    def acquire(self) -> None:
        """Take one request slot, waiting up to DISCORD_WAIT_S; raises DiscordPaused instead of sending."""
        deadline = time.monotonic() + DISCORD_WAIT_S
        while True:
            with self.lock:
                now = time.monotonic()
                if now < self.paused_until:
                    raise DiscordPaused(f"Discord requests paused for {self.paused_until - now:.0f} s ({self.pause_reason})")
                self.tokens = min(float(DISCORD_BURST), self.tokens + (now - self.last) * DISCORD_PER_S)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / DISCORD_PER_S
            if now + wait > deadline:
                raise DiscordPaused("too many Discord requests at once: the site's own limit")
            time.sleep(wait)

    def record(self, response: httpx.Response) -> None:
        """Count refusals; obey a 429 (every request waits, not only that kind)."""
        status = response.status_code
        if status not in (401, 403, 429):
            return
        now = time.monotonic()
        with self.lock:
            self.invalid = [t for t in self.invalid if now - t < INVALID_WINDOW_S] + [now]
            if status == 429:
                try:
                    wait = float(response.headers.get("Retry-After") or response.json().get("retry_after") or 5)
                except (ValueError, TypeError, AttributeError):
                    wait = 5.0
                wait = min(max(wait, 1.0), DISCORD_PAUSE_MAX_S)
                if now + wait > self.paused_until:
                    self.paused_until, self.pause_reason = now + wait, "Discord asked to slow down (429)"
                    log.warning("Discord said 429: every Discord request waits %.0f s", wait)
            if len(self.invalid) >= INVALID_MAX and self.paused_until < now + INVALID_WINDOW_S:
                self.paused_until = now + INVALID_WINDOW_S
                self.pause_reason = f"{len(self.invalid)} refused requests in {INVALID_WINDOW_S / 60:.0f} min"
                log.error("Discord refused %d requests in %.0f minutes: every Discord request stops for %.0f minutes "
                          "(protects the IP address from Discord's block; check the bot token)",
                          len(self.invalid), INVALID_WINDOW_S / 60, INVALID_WINDOW_S / 60)


discord_limiter = DiscordLimiter()


def _send(client: httpx.Client, method: str, url: str, **kw) -> httpx.Response:
    """Every request to Discord: a slot from the shared limiter first, the answer counted after."""
    discord_limiter.acquire()
    response = client.request(method, url, **kw)
    discord_limiter.record(response)
    return response


def http_client() -> httpx.Client:
    """Replaced in tests."""
    return httpx.Client(timeout=httpx.Timeout(5, connect=3))  # the limit applies to each of connect / write / read: 10 s meant up to 30 s


def enabled(settings: Settings) -> bool:
    """Login is possible. Who gets a preview: the role ids from the admin console (and ECHOVR_DISCORD_PREVIEW_ROLES)."""
    return bool(settings.discord_client_id and settings.discord_client_secret and settings.discord_bot_token
                and settings.discord_guild_id)


def is_discord_id(value: str) -> bool:
    """A Discord snowflake (17-20 digits). Ids typed by people must pass this before they go into a Discord API path
    called with the bot token (anything else could reach other endpoints, e.g. '../../channels/...')."""
    return value.isascii() and value.isdigit() and 17 <= len(value) <= 20


def _bot_get(settings: Settings, path: str) -> httpx.Response:
    with http_client() as client:
        return _send(client, "GET", f"{API}{path}", headers={"Authorization": f"Bot {settings.discord_bot_token}"})


SERVER_ROLES_S = 300  # the server's role list is asked at most every 5 minutes (Permissions page, startup check)
_server_roles: dict[str, tuple[float, list[dict]]] = {}  # guild id -> (asked at, roles)


def server_roles(settings: Settings) -> list[dict]:
    """Every role in the Discord server ({"id", "name"}), highest first: for picking preview roles in the admin
    console. Remembered SERVER_ROLES_S. Raises httpx.HTTPError when Discord cannot be asked."""
    hit = _server_roles.get(settings.discord_guild_id)
    if hit and time.monotonic() - hit[0] < SERVER_ROLES_S:
        return hit[1]
    r = _bot_get(settings, f"/guilds/{settings.discord_guild_id}/roles")
    r.raise_for_status()
    roles = sorted(r.json(), key=lambda x: -x.get("position", 0))
    result = [{"id": x["id"], "name": x["name"]} for x in roles if x["id"] != settings.discord_guild_id]  # not @everyone
    _server_roles[settings.discord_guild_id] = (time.monotonic(), result)
    return result


def check_fixed_ids(settings: Settings) -> list[str]:
    """Startup check (Review SEC-2): every id in ECHOVR_DISCORD_PREVIEW_ROLES gives the Console, so an id that is
    neither a role nor a member of the server is most likely a typo (and would hand staff rights to whoever owns it).
    Logged as warnings; returns the suspect ids. Needs the bot token; quiet when Discord cannot be asked."""
    suspects: list[str] = []
    if not settings.discord_bot_token or not settings.discord_preview_roles:
        return suspects
    try:
        roles = {r["id"] for r in server_roles(settings)}
    except (httpx.HTTPError, ValueError, KeyError) as e:
        log.warning("ECHOVR_DISCORD_PREVIEW_ROLES not checked (Discord could not be asked): %s", e)
        return suspects
    for value in settings.discord_preview_roles:
        if value in roles:
            continue
        if not is_discord_id(value):
            log.warning("ECHOVR_DISCORD_PREVIEW_ROLES: %r is not a Discord id; it gives nobody access", value)
            suspects.append(value)
            continue
        try:
            r = _bot_get(settings, f"/guilds/{settings.discord_guild_id}/members/{value}")
        except httpx.HTTPError:
            continue
        if r.status_code == 404:
            log.warning("ECHOVR_DISCORD_PREVIEW_ROLES: %s is neither a role nor a member of the Discord server (a typo?): "
                        "it gives the Console to nobody today, or to a stranger if they ever join", value)
            suspects.append(value)
    return suspects


_names: dict[str, str] = {}  # discord user id -> display name (names rarely change; the list is short)


def user_name(settings: Settings, user_id: str) -> str:
    """Display name of a Discord user via the bot, or '?'."""
    user_id = user_id.strip()
    if user_id in _names:
        return _names[user_id]
    if not settings.discord_bot_token or not is_discord_id(user_id):
        return "?"
    try:
        r = _bot_get(settings, f"/users/{user_id}")
        if r.status_code != 200:
            return "?"
        _names[user_id] = r.json().get("global_name") or r.json().get("username") or "?"
        return _names[user_id]
    except Exception:
        return "?"


AVATAR_CHECK_S = 24 * 3600  # a changed Discord avatar shows within a day (at once when the player saves their profile)
AVATAR_MAX_PER_MIN = 20  # at most this many /users/{id} requests per minute for all visitors together (Discord allows far more)
AVATAR_FILE = "discord-avatars.json"  # in the data folder: the answers survive restarts and updates (user, 2026-11-10)
AVATAR_KEEP_S = 30 * 86400  # an entry nobody needed for this long is dropped from the file
_avatars: dict[str, tuple[float, str | None]] = {}  # discord user id -> (valid until, unix time; avatar hash or None)
_avatars_loaded: set[str] = set()  # data folders whose saved answers were read
_avatar_lock = threading.Lock()
_avatar_calls: list[float] = []  # monotonic times of the requests made in the last minute
_avatar_blocked_until = 0.0  # Discord said 429: no request before this


def _avatar_budget(now: float) -> bool:
    """True (and counted) when another Discord request is allowed: not blocked by a 429 and under AVATAR_MAX_PER_MIN."""
    with _avatar_lock:
        if now < _avatar_blocked_until:
            return False
        _avatar_calls[:] = [t for t in _avatar_calls if now - t < 60]
        if len(_avatar_calls) >= AVATAR_MAX_PER_MIN:
            return False
        _avatar_calls.append(now)
        return True


def _avatar_path(settings: Settings):
    return settings.data_dir / AVATAR_FILE


def _load_avatars(settings: Settings) -> None:
    """Once per data folder: the answers saved by the last run (no Discord request for them after a restart)."""
    key = str(settings.data_dir)
    with _avatar_lock:
        if key in _avatars_loaded:
            return
        _avatars_loaded.add(key)
        try:
            saved = json.loads(_avatar_path(settings).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        entries = saved.get("avatars") if isinstance(saved, dict) else None
        for uid, entry in (entries or {}).items():
            try:
                until, avatar = float(entry[0]), entry[1]
            except (TypeError, ValueError, IndexError):
                continue
            if is_discord_id(uid) and (avatar is None or (isinstance(avatar, str) and avatar.replace("a_", "", 1).isalnum())):
                _avatars.setdefault(uid, (until, avatar))


def _save_avatars(settings: Settings) -> None:
    """Written after each Discord answer (at most AVATAR_MAX_PER_MIN a minute): a small file, replaced in one step."""
    cutoff = time.time() - AVATAR_KEEP_S
    with _avatar_lock:
        data = {"avatars": {uid: [until, avatar] for uid, (until, avatar) in _avatars.items() if until > cutoff}}
    path = _avatar_path(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    except OSError as e:
        log.warning("Discord avatar cache not saved: %s", e)


def avatar_url(settings: Settings, user_id: str, fresh: bool = False, ask: bool = True) -> str | None:
    """Discord avatar of a user (asked via the bot, remembered AVATAR_CHECK_S), Discord's default one when they have
    none, or None when Discord cannot be asked. Requests are budgeted (AVATAR_MAX_PER_MIN, and a 429 is obeyed): over
    the budget the last known picture is kept and asked again later.
    ask=False (list pages, user 2026-11-10): never asks Discord; the saved picture however old, or None. Only opening a
    player's profile page (and saving one's own profile) asks."""
    global _avatar_blocked_until
    if not is_discord_id(user_id):
        return None
    _load_avatars(settings)
    now, mono = time.time(), time.monotonic()  # wall clock for the saved expiry times, monotonic for the request budget
    hit = _avatars.get(user_id)
    if not ask:
        if not hit:
            return None
    elif not hit or hit[0] <= now or fresh:
        if not settings.discord_bot_token:
            return None
        if _avatar_budget(mono):
            try:
                r = _bot_get(settings, f"/users/{user_id}")
                if r.status_code == 429:
                    try:
                        wait = float(r.headers.get("Retry-After") or r.json().get("retry_after") or 60)
                    except (ValueError, TypeError):
                        wait = 60.0
                    with _avatar_lock:
                        _avatar_blocked_until = mono + min(max(wait, 1.0), 600.0)
                    raise httpx.HTTPError("rate limited")
                if r.status_code == 404:  # no such account: remembered as "none" for the hour, not asked every 30 s (PERF-6)
                    hit = (now + AVATAR_CHECK_S, None)
                else:
                    r.raise_for_status()
                    hit = (now + AVATAR_CHECK_S, r.json().get("avatar"))
            except (httpx.HTTPError, ValueError) as e:
                log.warning("Discord avatar of %s failed: %s", user_id, e)
                hit = (now + ROLE_RETRY_S, hit[1]) if hit else None
        elif hit:
            hit = (now + ROLE_RETRY_S, hit[1])  # over budget: keep the old picture, look again soon
        if hit is None:
            return None
        _avatars[user_id] = hit
        if hit[0] - now > ROLE_RETRY_S:  # a real answer from Discord (not a retry-soon placeholder): keep it across restarts
            _save_avatars(settings)
    avatar = hit[1]
    if avatar and avatar.replace("a_", "", 1).isalnum():
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.png?size=256"
    return f"https://cdn.discordapp.com/embed/avatars/{(int(user_id) >> 22) % 6}.png"


def redirect_uri(settings: Settings) -> str:
    return settings.public_url.rstrip("/") + "/api/auth/callback"


def secure_cookies(settings: Settings) -> bool:
    return settings.public_url.startswith("https://")


# --- signed cookies -------------------------------------------------------------------------

def _key(settings: Settings) -> bytes:
    """Random signing key in the data folder, made on first use. Deleting it logs everyone out."""
    path = settings.data_dir / "session.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return bytes.fromhex(path.read_text().strip())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(settings: Settings, payload: dict, max_age_s: int) -> str:
    body = _b64(json.dumps(payload | {"exp": int(time.time()) + max_age_s}, separators=(",", ":")).encode())
    return body + "." + _b64(hmac.new(_key(settings), body.encode(), hashlib.sha256).digest())


def unsign(settings: Settings, value: str | None) -> dict | None:
    if not value or value.count(".") != 1:
        return None
    body, signature = value.split(".")
    expected = _b64(hmac.new(_key(settings), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    return payload if isinstance(payload, dict) and payload.get("exp", 0) > time.time() else None


# --- Discord --------------------------------------------------------------------------------

def authorize_url(settings: Settings, state: str) -> str:
    return AUTHORIZE_URL + "?" + urlencode({
        "client_id": settings.discord_client_id, "response_type": "code", "scope": "identify",
        "redirect_uri": redirect_uri(settings), "state": state, "prompt": "none",
    })


def user_from_code(settings: Settings, code: str) -> dict:
    """OAuth code -> {"id", "name"}. The user token is revoked straight away: only the id is needed."""
    with http_client() as client:
        token = _send(client, "POST", f"{API}/oauth2/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings),
            "client_id": settings.discord_client_id, "client_secret": settings.discord_client_secret,
        })
        token.raise_for_status()
        access = token.json()["access_token"]
        me = _send(client, "GET", f"{API}/users/@me", headers={"Authorization": f"Bearer {access}"})
        me.raise_for_status()
        try:
            _send(client, "POST", f"{API}/oauth2/token/revoke", data={
                "token": access, "token_type_hint": "access_token",
                "client_id": settings.discord_client_id, "client_secret": settings.discord_client_secret,
            })
        except httpx.HTTPError:
            pass  # expires on its own
    user = me.json()
    return {"id": user["id"], "name": user.get("global_name") or user["username"]}


def forget_roles(user_id: str) -> None:
    """A fresh login asks Discord again (a role just given shows at once)."""
    with _roles_lock:
        _roles.pop(user_id, None)


def _ask_roles(settings: Settings, user_id: str, hit) -> frozenset[str]:
    """Ask Discord and remember the answer. If it cannot be asked, keep the last answer (none = no roles) and retry soon."""
    now = time.monotonic()
    try:
        r = _bot_get(settings, f"/guilds/{settings.discord_guild_id}/members/{user_id}")
        if r.status_code == 404:  # not in the server (any more)
            roles, until = frozenset(), now + ROLE_CHECK_S
        else:
            r.raise_for_status()
            roles, until = frozenset(r.json().get("roles", [])), now + ROLE_CHECK_S
    except (httpx.HTTPError, ValueError) as e:  # bad bot token, bot not in the server, Discord down
        log.warning("Discord role check for %s failed: %s", user_id, e)
        roles, until = (hit[1] if hit else frozenset()), now + ROLE_RETRY_S
    with _roles_lock:
        _roles[user_id] = (until, roles)
    return roles


_asking: dict[str, threading.Lock] = {}  # one Discord question per user at a time


def member_roles(settings: Settings, user_id: str) -> frozenset[str]:
    """The user's role ids in the server, asked with the bot token; remembered for ROLE_CHECK_S. After that the last
    answer is still used while a background question refreshes it, so a slow Discord never holds a page up. Only the
    very first question (or one after forget_roles) waits for Discord; parallel requests share that one question."""
    now = time.monotonic()
    with _roles_lock:
        hit = _roles.get(user_id)
        lock = _asking.setdefault(user_id, threading.Lock())
    if hit and hit[0] > now:
        return hit[1]
    if hit:  # expired: answer from the last known roles, refresh in the background
        if lock.acquire(blocking=False):
            def refresh():
                try:
                    _ask_roles(settings, user_id, hit)
                finally:
                    lock.release()
            threading.Thread(target=refresh, name="discord-roles", daemon=True).start()
        return hit[1]
    with lock:  # nothing known yet: wait, but only one request asks
        with _roles_lock:
            again = _roles.get(user_id)
        if again and again[0] > time.monotonic():
            return again[1]
        return _ask_roles(settings, user_id, None)


# --- the current visitor --------------------------------------------------------------------

def viewer(request: Request) -> dict | None:
    """{"id", "name"} of the logged-in visitor, or None. The answer being built now depends on who asks: no shared
    cache may keep it (middleware.py). Every check of the visitor comes through here."""
    try:
        request.state.per_visitor = True
    except AttributeError:  # not a real request
        pass
    settings = request.app.state.settings
    if not enabled(settings):
        return None
    session = unsign(settings, request.cookies.get(SESSION_COOKIE))
    return {"id": session["id"], "name": session["name"]} if session and "id" in session else None


def allowed(settings: Settings, db, user_id: str, kind: str, roles: Callable[[], frozenset[str]]) -> bool:
    """Whether a person has permission `kind` ("admin" / "console" / "preview" / "cloud_view" / "cloud_edit"): by
    their user id or one of their Discord roles (Permissions page). ECHOVR_DISCORD_PREVIEW_ROLES ids (YAML) always give
    the console. Admins and console users also get the preview; console users get Cloud edit, and Cloud edit includes
    Cloud view. `roles` is only called when an id does not settle it."""
    if kind == "cloud_view" and allowed(settings, db, user_id, "cloud_edit", roles):
        return True
    if kind == "cloud_edit" and allowed(settings, db, user_id, "console", roles):
        return True
    if kind == "preview" and (allowed(settings, db, user_id, "admin", roles) or allowed(settings, db, user_id, "console", roles)):
        return True
    ids = set(settings.discord_preview_roles) if kind == "console" else set()
    if user_id in ids | set(discord_roles(db, f"{kind}_user")):
        return True
    role_ids = ids | set(discord_roles(db, kind))
    return bool(role_ids and role_ids & roles())


def _has(request: Request, kind: str, fresh: bool = False) -> bool:
    """fresh: ask Discord now instead of using the remembered roles, and refuse when it cannot be asked."""
    user = viewer(request)
    if not user:
        return False
    settings = request.app.state.settings
    if fresh:
        forget_roles(user["id"])
    with request.app.state.sessionmaker() as db:
        return allowed(settings, db, user["id"], kind, functools.cache(lambda: member_roles(settings, user["id"])))


def has_preview(request: Request) -> bool:
    """The visitor may see achievements before their launch date."""
    return _has(request, "preview")


def is_admin(request: Request) -> bool:
    """Admin: the Status page (and the preview)."""
    return _has(request, "admin")


def has_console(request: Request, fresh: bool = False) -> bool:
    """The Console and Permissions pages (D45). Every command asks with fresh=True: a removed role stops working
    at once."""
    return _has(request, "console", fresh)


def cloud_access(request: Request, fresh: bool = False) -> str | None:
    """Open Cloud (cloud.py): "edit", "view" or None. fresh: ask Discord now (deleting, renaming, starting an upload)."""
    if _has(request, "cloud_edit", fresh):
        return "edit"
    return "view" if _has(request, "cloud_view") else None
