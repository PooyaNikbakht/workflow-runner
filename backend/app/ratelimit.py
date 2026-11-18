"""Per-IP request budget for /api/*, so one runaway client (a forgotten tab) can't hog it.

A fixed window counted in memory per process: cheap, and good enough for one API process. CORS
preflights (OPTIONS) are not counted. Over the budget the client gets 429 with Retry-After; this
middleware sits inside the CORS one, so that response carries CORS headers and the UI can read it.
"""

import time

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

WINDOW_SECONDS = 60


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, per_minute: int, ip_header: str = "") -> None:
        self.app = app
        self.per_minute = per_minute
        self.ip_header = ip_header.lower().encode()
        self.hits: dict[str, tuple[float, int]] = {}  # ip -> (window start, count)

    def client_ip(self, scope: Scope) -> str:
        if self.ip_header:
            for name, value in scope["headers"]:
                if name == self.ip_header and value:
                    return value.decode("latin-1").strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def check(self, ip: str, now: float) -> int:
        """Counts a request. Returns 0 if allowed, else the seconds until the window resets."""
        if len(self.hits) > 10_000:
            self.hits = {k: v for k, v in self.hits.items() if now - v[0] < WINDOW_SECONDS}
        start, count = self.hits.get(ip, (now, 0))
        if now - start >= WINDOW_SECONDS:
            start, count = now, 0
        if count >= self.per_minute:
            return max(1, int(start + WINDOW_SECONDS - now) + 1)
        self.hits[ip] = (start, count + 1)
        return 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] == "OPTIONS"
            or not scope["path"].startswith("/api/")
        ):
            await self.app(scope, receive, send)
            return
        retry_after = self.check(self.client_ip(scope), time.monotonic())
        if retry_after:
            response = JSONResponse(
                {"detail": "Too many requests. Please slow down and try again shortly."},
                429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
