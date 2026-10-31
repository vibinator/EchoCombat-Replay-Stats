"""Scraper protection for the public site (D48). Cloudflare's own bot and rate rules come first (Setup.MD); this is
the app's layer behind them:
- AI crawlers are refused everywhere (robots.txt asks them too; not all of them listen).
- /api/* answers only this site's own pages: they send the X-EchoVR header (api.ts), plain scripts do not. Links
  the browser opens itself (login, downloads) cannot add a header and are exempt.
- /api/* refuses common scraping libraries and headless browsers by user agent.
- /api/* is rate limited per visitor (token buckets: per minute and per hour); heavy answers (heatmaps, playback, downloads) cost more.
A determined scraper can copy a header and a user agent; the rate limit is what bounds how fast anyone can copy
the archive."""

import re
import time

from fastapi.responses import JSONResponse

AI_CRAWLERS = re.compile(
    r"GPTBot|ChatGPT-User|OAI-SearchBot|ClaudeBot|Claude-Web|anthropic-ai|CCBot|Bytespider|PerplexityBot|"
    r"Amazonbot|meta-externalagent|FacebookBot|Google-Extended|Applebot-Extended|cohere-ai|Diffbot|"
    r"ImagesiftBot|Omgili|Timpibot|YouBot|PetalBot|DataForSeoBot",
    re.IGNORECASE,
)
SCRIPT_AGENTS = re.compile(
    r"python-requests|python-urllib|python-httpx|aiohttp|httpx|curl/|wget/|scrapy|go-http-client|java/|okhttp|"
    r"libwww-perl|node-fetch|undici|axios|got \(|guzzle|postmanruntime|insomnia|headlesschrome|phantomjs|"
    r"puppeteer|playwright|selenium|httpclient|mechanize|colly",
    re.IGNORECASE,
)
# Opened by the browser itself (address bar, <a href>, Discord redirect): no custom header possible.
HEADER_EXEMPT = ("/api/auth/", "/api/health")
HEADER_EXEMPT_SUFFIXES = ("/export", ".csv", ".xlsx")
HEAVY = ("/heatmap", "/playback", "/export", "/compare/", ".csv", ".xlsx")
HEAVY_COST = 10


def client_ip(request) -> str:
    """The visitor's address. Behind the Cloudflare Tunnel every request comes from cloudflared, which passes the
    real one in CF-Connecting-IP."""
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


class RateLimiter:
    """Token bucket per key: `per_minute` sustained, up to `burst` at once."""

    PRUNE_EVERY_S = 300

    def __init__(self, per_minute: int, burst: int):
        self.rate = per_minute / 60
        self.burst = burst
        self.buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last update)
        self._pruned = time.monotonic()

    def take(self, key: str, cost: int = 1, now: float | None = None) -> float:
        """0 = allowed; otherwise seconds until `cost` tokens are available."""
        now = time.monotonic() if now is None else now
        tokens, last = self.buckets.get(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens < cost:
            self.buckets[key] = (tokens, now)
            return (cost - tokens) / self.rate
        self.buckets[key] = (tokens - cost, now)
        if now - self._pruned > self.PRUNE_EVERY_S:
            self._prune(now)
        return 0.0

    def _prune(self, now: float) -> None:
        """Forget visitors whose bucket is full again (they would start full anyway)."""
        full_after = self.burst / self.rate
        self.buckets = {k: v for k, v in self.buckets.items() if now - v[1] < full_after}
        self._pruned = now


def _refuse(status: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error_code": code, "message": message}, status_code=status, headers=headers)


def check(request, limiter: RateLimiter | None, hourly: RateLimiter | None = None) -> JSONResponse | None:
    """None = let the request through; otherwise the refusal to send."""
    path = request.url.path
    agent = request.headers.get("user-agent", "")
    if AI_CRAWLERS.search(agent):
        return _refuse(403, "crawler", "Automated crawling of this site is not allowed.")
    if not path.startswith("/api/") or path.startswith("/api/health"):
        return None
    if not agent or SCRIPT_AGENTS.search(agent):
        return _refuse(403, "automated", "Automated access to this site's data is not allowed.")
    exempt = path.startswith(HEADER_EXEMPT) or path.endswith(HEADER_EXEMPT_SUFFIXES)
    if not exempt and request.headers.get("x-echovr") != "1":
        return _refuse(403, "automated", "Automated access to this site's data is not allowed.")
    if limiter is not None:
        cost = HEAVY_COST if any(h in path for h in HEAVY) else 1
        # the per-minute bucket stops bursts, the hourly one bounds how much one visitor can copy in a day
        wait = max(limiter.take(client_ip(request), cost), hourly.take(client_ip(request), cost) if hourly else 0.0)
        if wait:
            return _refuse(429, "rate_limited", "Too many requests. Wait a moment and try again.",
                           {"Retry-After": str(max(1, round(wait)))})
    return None
