"""Discord login for achievement previews (D41). Only GET requests: the website stays read-only (D38)."""

import hmac
import secrets
from urllib.parse import urlencode, urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from .. import auth
from ..errors import ApiError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _safe_next(next_: str | None) -> str:
    """Only paths on this site: never an outside address (open redirect)."""
    if not next_ or not next_.startswith("/") or next_.startswith(("//", "/\\")):
        return "/achievements"
    return next_


def _settings(request: Request):
    settings = request.app.state.settings
    if not auth.enabled(settings):
        raise ApiError(404, "login_disabled", "Discord login is not set up")
    return settings


@router.get("/me")
def me(request: Request):
    """Whether Discord login is available, and who is logged in (with or without preview access)."""
    user = auth.viewer(request)
    return {"enabled": auth.enabled(request.app.state.settings),
            "user": user and {"name": user["name"], "preview": auth.has_preview(request), "admin": auth.is_admin(request)}}


@router.get("/login")
def login(request: Request, next: str | None = None):
    settings = _settings(request)
    public = urlparse(settings.public_url)
    if request.url.hostname != public.hostname:  # e.g. www.: Discord returns to public_url, the cookie must be there
        query = urlencode({"next": _safe_next(next)})
        return RedirectResponse(f"{settings.public_url.rstrip('/')}/api/auth/login?{query}", status_code=303)
    state = secrets.token_urlsafe(24)
    response = RedirectResponse(auth.authorize_url(settings, state), status_code=303)
    response.set_cookie(auth.STATE_COOKIE, auth.sign(settings, {"state": state, "next": _safe_next(next)}, auth.STATE_S),
                        max_age=auth.STATE_S, httponly=True, samesite="lax", secure=auth.secure_cookies(settings),
                        path="/api/auth")
    return response


@router.get("/callback")
def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    settings = _settings(request)
    pending = auth.unsign(settings, request.cookies.get(auth.STATE_COOKIE)) or {}
    target = _safe_next(pending.get("next"))
    sep = "&" if "?" in target else "?"
    if error or not code or not state or not hmac.compare_digest(str(pending.get("state", "")), state):
        response = RedirectResponse(f"{target}{sep}login=failed", status_code=303)
    else:
        try:
            user = auth.user_from_code(settings, code)
        except (httpx.HTTPError, KeyError, ValueError):
            response = RedirectResponse(f"{target}{sep}login=failed", status_code=303)
        else:
            auth.forget_roles(user["id"])
            response = RedirectResponse(target, status_code=303)
            response.set_cookie(auth.SESSION_COOKIE, auth.sign(settings, user, auth.SESSION_DAYS * 86400),
                                max_age=auth.SESSION_DAYS * 86400, httponly=True, samesite="lax",
                                secure=auth.secure_cookies(settings), path="/")
    response.delete_cookie(auth.STATE_COOKIE, path="/api/auth")
    return response


@router.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return response
