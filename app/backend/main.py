from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from parser import PARSER_VERSION

from . import auth, icons
from .api import achievements, admin, auth as auth_api, console, imports, leaderboard, matches, overview, permissions, players, replays
from .config import PROJECT_ROOT, Settings
from .db import open_db
from .errors import ApiError, api_error_handler
from .stats import STATS_VERSION
from .version import APP_VERSION
from .scanner import Scanner
from .worker import Worker

FRONTEND_DIST = PROJECT_ROOT / "app" / "frontend" / "dist"
PER_VISITOR = ("/api/admin", "/api/auth", "/api/challenges", "/api/achievements", "/api/players", "/api/leaderboard")


class SinglePageApp(StaticFiles):
    """Serve index.html for client-side routes such as /matches/12."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            if e.status_code != 404 or path.startswith("api"):
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, app.state.sessionmaker = open_db(settings.db_path)
        app.state.worker = Worker(app.state.sessionmaker, settings)
        app.state.scanner = Scanner(app.state.sessionmaker, settings, on_queued=app.state.worker.notify)
        app.state.worker.start()
        if settings.auto_scan:
            app.state.scanner.start()
            achievements.warm(app.state.sessionmaker, previews=auth.enabled(settings))
        yield
        if settings.auto_scan:
            app.state.scanner.stop()
        app.state.worker.stop()
        engine.dispose()

    app = FastAPI(title="EchoVR Replay Stats", lifespan=lifespan)
    app.state.settings = settings
    app.add_exception_handler(ApiError, api_error_handler)
    # heatmaps / playback are 100s of KB of JSON. Level 4: 12x faster than the default 9 for 8 % more bytes
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=4)

    @app.middleware("http")
    async def read_only(request, call_next):
        """The website never changes data: every change is made in the admin console (admin.bat). Exceptions:
        achievement icons (D43), and the Console page (D45, admin.bat itself), for
        ECHOVR_DISCORD_PREVIEW_ROLES members, and the Permissions page (console users); the X-EchoVR header proves the request comes from this site's own pages
        (other sites cannot send it without a CORS preflight, which is refused)."""
        if (request.method in ("PUT", "POST") and request.url.path.startswith(("/api/admin/achievements/", "/api/admin/console/", "/api/admin/permissions"))
                and request.headers.get("x-echovr") == "1"):
            return await call_next(request)  # the endpoint checks the role
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            return JSONResponse({"error_code": "read_only", "message": "The website is read-only. Use the admin console (admin.bat)."},
                                status_code=405)
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request, call_next):
        """Public site (echocombat.com): no sniffing, no framing by other sites, no full URLs leaked to other sites."""
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith(PER_VISITOR):  # differs per logged-in visitor (D41): never shared by a cache
            response.headers["Cache-Control"] = "private, no-store"
        elif (request.url.path.startswith("/assets/") and response.status_code == 200
              and not response.headers.get("content-type", "").startswith("text/html")):  # not the index.html fallback
            # built JS / CSS: the file name changes with the content, so browsers keep it instead of asking again
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    if settings.import_api:
        app.include_router(replays.router)
        app.include_router(imports.router)
    app.include_router(matches.router)
    app.include_router(players.router)
    app.include_router(leaderboard.router)
    app.include_router(achievements.router)
    app.include_router(overview.router)
    app.include_router(auth_api.router)
    app.include_router(admin.router)
    app.include_router(console.router)
    app.include_router(permissions.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": APP_VERSION, "parser_version": PARSER_VERSION, "stats_version": STATS_VERSION,
                "source_dir": str(settings.source_dir)}

    @app.get("/achievements/custom/{name}")
    def custom_icon(name: str):
        """Icons uploaded on the Console page (D43). Before the site mount, which serves the built-in ones."""
        path = icons.custom_dir(settings) / name
        if not icons.CUSTOM_NAME.match(name) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    # Built frontend (npm run build); in development Vite serves it instead.
    if FRONTEND_DIST.is_dir():
        app.mount("/", SinglePageApp(directory=FRONTEND_DIST, html=True), name="frontend")

    return app


app = create_app()
