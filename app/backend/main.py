import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from parser import PARSER_VERSION

from . import auth, discord_names, guard, icons, tracks
from .api import achievements, admin, auth as auth_api, console, imports, profiles, leaderboard, matches, overview, permissions, players, replays
from .config import PROJECT_ROOT, Settings
from .db import open_db, warm
from .errors import ApiError, api_error_handler
from .middleware import SiteMiddleware
from .stats import STATS_VERSION
from .version import APP_VERSION, RELEASED, VERSION
from .scanner import Scanner
from .worker import Worker

FRONTEND_DIST = PROJECT_ROOT / "app" / "frontend" / "dist"


class SinglePageApp(StaticFiles):
    """Serve index.html for client-side routes such as /matches/12."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as e:
            # only page routes (/matches/12) fall back to index.html; a missing file (/x.txt, /a.echoreplay) stays a 404
            # `path` uses the OS separator (backslashes on Windows): basename, so a dot in an earlier segment (a player
            # name in /players/<name>/<id>) does not make it look like a file
            if e.status_code != 404 or path.startswith("api") or "." in os.path.basename(path):
                raise
            return await super().get_response("index.html", scope)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine, app.state.sessionmaker = open_db(settings.db_path, settings.db_cache_mb)
        tracks.set_cache_limit(settings.track_cache_mb)
        if settings.db_cache_mb > 0:
            warm(settings.db_path, settings.db_cache_mb)
        app.state.worker = Worker(app.state.sessionmaker, settings)
        app.state.scanner = Scanner(app.state.sessionmaker, settings, on_queued=app.state.worker.notify)
        app.state.worker.start()
        if settings.auto_scan:
            app.state.scanner.start()

            def warm_caches():  # the home page first (the first thing people open), then the heavy achievements ranking
                overview.warm(app)
                achievements.warm(app.state.sessionmaker, previews=auth.enabled(settings))

            threading.Thread(target=warm_caches, name="warm-caches", daemon=True).start()
            discord_names.refresh_soon(settings)  # player pictures by Discord name, read in the background
        yield
        if settings.auto_scan:
            app.state.scanner.stop()
        app.state.worker.stop()
        engine.dispose()

    # no /docs, /redoc or /openapi.json on the public site: they list every route, the admin ones included
    app = FastAPI(title="EchoVR Replay Stats", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.add_exception_handler(ApiError, api_error_handler)
    # Large answers that are not cached (cached ones are gzipped once, cache.py). Level 4: 12x faster than the
    # default 9 for 8 % more bytes
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=4)

    per_min = settings.rate_limit_per_min
    limiter = guard.RateLimiter(per_min, 2 * per_min) if per_min > 0 else None
    per_hour = settings.rate_limit_per_hour
    hourly = guard.RateLimiter(per_hour / 60, per_hour) if per_hour > 0 else None
    # replay files, read-only site, scraper protection, security and cache headers (middleware.py); outside GZip
    app.add_middleware(SiteMiddleware, settings=settings, limiter=limiter, hourly=hourly)

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
    app.include_router(profiles.router)
    app.include_router(profiles.bot_router)
    app.include_router(permissions.router)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": APP_VERSION, "build": VERSION, "released": RELEASED, "parser_version": PARSER_VERSION, "stats_version": STATS_VERSION}

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
