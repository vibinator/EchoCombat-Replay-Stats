"""Every request and answer of the site in one pure ASGI layer (it replaces four @app.middleware layers that cost
~0.6 ms per request, static files included).

Requests, in this order: replay files are refused (404), changes are refused (405: the website is read-only, D38,
except the icon / Console / Permissions writes with the X-EchoVR header), bots and floods are turned away (D48,
guard.py).

Answers get the security headers, and say who may keep a copy (D53, user 2026-11-01):
- API answers that depend on who is logged in (auth.viewer was asked, and everything under /api/auth and /api/admin):
  private, no-store.
- Errors (anything but 200 / 304): no-store, so a refusal is never shown to someone else.
- Other API answers: browsers keep them but ask again every time (no-cache; the ETag makes that a 304). Cloudflare may
  keep them ECHOVR_EDGE_CACHE_S seconds (Cloudflare-CDN-Cache-Control: browsers never see it) and serve them up to
  10 minutes longer while the NAS answers 5xx; not a STALE answer (a fresher one is being built).
- Built JS / CSS (/assets): a year (the file name changes with the content). Page addresses (index.html): always
  checked, so a new version shows at once. Images and other files: 4 hours (what Cloudflare gave them before)."""

from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.requests import Request

from . import guard
from .cache import STATUS_HEADER

PER_VISITOR = ("/api/auth", "/api/admin", "/api/profiles", "/api/bot")
WRITES = ("/api/admin/achievements/", "/api/admin/console/", "/api/admin/permissions", "/api/profiles/")
BOT = "/api/bot/"  # the Discord bot: POST with its shared secret (checked by the endpoint), no X-EchoVR header
STATIC_MAX_AGE_S = 4 * 3600
EDGE_STALE_IF_ERROR_S = 600


def _refusal(request: Request, settings, limiter, hourly):
    path = request.url.path
    if guard.asks_for_replay_file(path):
        return JSONResponse({"error_code": "not_found", "message": "Not found"}, status_code=404)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not (
            request.method in ("PUT", "POST") and path.startswith(WRITES) and request.headers.get("x-echovr") == "1"
    ) and not (request.method == "POST" and path.startswith(BOT)):
        return JSONResponse({"error_code": "read_only", "message": "The website is read-only. Use the admin console (admin.bat)."},
                            status_code=405)  # the allowed writes check the visitor's role themselves
    if settings.scraper_guard:
        return guard.check(request, limiter, hourly)
    return None


def _api_cache(headers: MutableHeaders, status: int, per_visitor: bool, edge_s: int) -> None:
    if per_visitor or status not in (200, 304):
        headers["Cache-Control"] = "private, no-store" if per_visitor else "no-store"
        headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        return
    headers.setdefault("Cache-Control", "no-cache" if edge_s else "private, no-cache")
    if "cloudflare-cdn-cache-control" not in headers:
        fresh = headers.get(STATUS_HEADER) != "STALE"
        headers["Cloudflare-CDN-Cache-Control"] = (f"max-age={edge_s}, stale-if-error={EDGE_STALE_IF_ERROR_S}"
                                                   if edge_s and fresh else "no-store")


def _static_cache(headers: MutableHeaders, path: str, status: int) -> None:
    if status not in (200, 304):
        return
    name = path.rsplit("/", 1)[-1]
    if "." not in name or name.endswith(".html") or headers.get("content-type", "").startswith("text/html"):
        headers["Cache-Control"] = "no-cache"  # index.html for every page address (SinglePageApp)
    elif path.startswith("/assets/"):
        headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        headers.setdefault("Cache-Control", f"public, max-age={STATIC_MAX_AGE_S}")


class SiteMiddleware:
    def __init__(self, app, settings, limiter=None, hourly=None):
        self.app, self.settings, self.limiter, self.hourly = app, settings, limiter, hourly

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        path = scope["path"]
        https = guard.is_https(request)
        edge_s = self.settings.edge_cache_s

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in guard.SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
                if https:
                    headers.setdefault("Strict-Transport-Security", "max-age=31536000")
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "SAMEORIGIN")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                status = message["status"]
                if path.startswith("/api/"):
                    headers["X-Robots-Tag"] = "noindex, nofollow"  # data, not pages: keep it out of search results
                    per_visitor = path.startswith(PER_VISITOR) or bool(scope.get("state", {}).get("per_visitor"))
                    _api_cache(headers, status, per_visitor, edge_s)
                else:
                    _static_cache(headers, path, status)
            await send(message)

        app = _refusal(request, self.settings, self.limiter, self.hourly) or self.app
        await app(scope, receive, send_with_headers)
