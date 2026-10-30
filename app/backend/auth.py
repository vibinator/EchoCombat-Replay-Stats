"""Discord login, only for previewing achievements before their launch date (D41). Login = OAuth2 "identify" (who
you are); access = a preview role in the EchoVR Combat Discord server, checked with the bot token (no user token is
kept). The session is a signed cookie: nothing is written to the database, so the website stays read-only (D38)."""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
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


def http_client() -> httpx.Client:
    """Replaced in tests."""
    return httpx.Client(timeout=10)


def enabled(settings: Settings) -> bool:
    """Login is possible. Who gets a preview: the role ids from the admin console (and ECHOVR_DISCORD_PREVIEW_ROLES)."""
    return bool(settings.discord_client_id and settings.discord_client_secret and settings.discord_bot_token
                and settings.discord_guild_id)


def _bot_get(settings: Settings, path: str) -> httpx.Response:
    with http_client() as client:
        return client.get(f"{API}{path}", headers={"Authorization": f"Bot {settings.discord_bot_token}"})


def server_roles(settings: Settings) -> list[dict]:
    """Every role in the Discord server ({"id", "name"}), highest first: for picking preview roles in the admin
    console. Raises httpx.HTTPError when Discord cannot be asked."""
    r = _bot_get(settings, f"/guilds/{settings.discord_guild_id}/roles")
    r.raise_for_status()
    roles = sorted(r.json(), key=lambda x: -x.get("position", 0))
    return [{"id": x["id"], "name": x["name"]} for x in roles if x["id"] != settings.discord_guild_id]  # not @everyone


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
        token = client.post(f"{API}/oauth2/token", data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri(settings),
            "client_id": settings.discord_client_id, "client_secret": settings.discord_client_secret,
        })
        token.raise_for_status()
        access = token.json()["access_token"]
        me = client.get(f"{API}/users/@me", headers={"Authorization": f"Bearer {access}"})
        me.raise_for_status()
        try:
            client.post(f"{API}/oauth2/token/revoke", data={
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


def member_roles(settings: Settings, user_id: str) -> frozenset[str]:
    """The user's role ids in the server, asked with the bot token; remembered for ROLE_CHECK_S."""
    now = time.monotonic()
    with _roles_lock:
        hit = _roles.get(user_id)
    if hit and hit[0] > now:
        return hit[1]
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


# --- the current visitor --------------------------------------------------------------------

def viewer(request: Request) -> dict | None:
    """{"id", "name"} of the logged-in visitor, or None."""
    settings = request.app.state.settings
    if not enabled(settings):
        return None
    session = unsign(settings, request.cookies.get(SESSION_COOKIE))
    return {"id": session["id"], "name": session["name"]} if session and "id" in session else None


def _has_role(request: Request, kind: str) -> bool:
    user = viewer(request)
    if not user:
        return False
    settings = request.app.state.settings
    with request.app.state.sessionmaker() as db:
        allowed = set(discord_roles(db, "admin"))
        if kind == "preview":  # admins see everything
            allowed |= set(settings.discord_preview_roles) | set(discord_roles(db, "preview"))
    return bool(allowed & member_roles(settings, user["id"]))


def has_preview(request: Request) -> bool:
    """The visitor may see achievements before their launch date (preview or admin role)."""
    return _has_role(request, "preview")


def is_admin(request: Request) -> bool:
    """The visitor has an admin role: the website's Admin tab (D42). Still read-only: changes are made in admin.bat."""
    return _has_role(request, "admin")
