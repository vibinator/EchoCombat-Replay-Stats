"""Discord login, only for previewing achievements before their launch date (D41). Login = OAuth2 "identify" (who
you are); access = a preview role in the EchoVR Combat Discord server, checked with the bot token (no user token is
kept). The session is a signed cookie: nothing is written to the database, so the website stays read-only (D38)."""

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from urllib.parse import urlencode

import httpx
from fastapi import Request

from .config import Settings

API = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
SESSION_COOKIE = "echovr_session"
STATE_COOKIE = "echovr_oauth"
SESSION_DAYS = 30
STATE_S = 600  # time allowed on Discord's login page
ROLE_CHECK_S = 300  # a removed role stops working within 5 minutes
ROLE_RETRY_S = 30  # Discord unreachable: keep the last answer, ask again soon

_roles: dict[str, tuple[float, bool]] = {}  # discord user id -> (checked at, has a preview role)
_roles_lock = threading.Lock()


def http_client() -> httpx.Client:
    """Replaced in tests."""
    return httpx.Client(timeout=10)


def enabled(settings: Settings) -> bool:
    return bool(settings.discord_client_id and settings.discord_client_secret and settings.discord_bot_token
                and settings.discord_guild_id and settings.discord_preview_roles)


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


def has_preview_role(settings: Settings, user_id: str) -> bool:
    """Asks the bot whether the user is in the server with a preview role; remembered for ROLE_CHECK_S."""
    now = time.monotonic()
    with _roles_lock:
        hit = _roles.get(user_id)
    if hit and hit[0] > now:
        return hit[1]
    try:
        with http_client() as client:
            r = client.get(f"{API}/guilds/{settings.discord_guild_id}/members/{user_id}",
                           headers={"Authorization": f"Bot {settings.discord_bot_token}"})
        if r.status_code == 404:  # not in the server (any more)
            allowed, until = False, now + ROLE_CHECK_S
        else:
            r.raise_for_status()
            allowed, until = bool(set(r.json().get("roles", [])) & set(settings.discord_preview_roles)), now + ROLE_CHECK_S
    except (httpx.HTTPError, ValueError):
        allowed, until = (hit[1] if hit else False), now + ROLE_RETRY_S
    with _roles_lock:
        _roles[user_id] = (until, allowed)
    return allowed


# --- the current visitor --------------------------------------------------------------------

def viewer(request: Request) -> dict | None:
    """{"id", "name"} of the logged-in visitor, or None."""
    settings = request.app.state.settings
    if not enabled(settings):
        return None
    session = unsign(settings, request.cookies.get(SESSION_COOKIE))
    return {"id": session["id"], "name": session["name"]} if session and "id" in session else None


def has_preview(request: Request) -> bool:
    """The visitor may see achievements before their launch date."""
    user = viewer(request)
    return bool(user) and has_preview_role(request.app.state.settings, user["id"])
