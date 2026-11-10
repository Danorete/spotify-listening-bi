"""Protection for the local HTTP endpoints (decision D2).

Threats covered: a web page in the same browser sending requests to 127.0.0.1 (cross-site
request forgery, DNS rebinding), and another local process guessing the port. Not covered:
malware running as the same macOS user, which can read the database file directly.
"""

from __future__ import annotations

import secrets
from typing import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

COOKIE_NAME = "cc_session"
CSRF_HEADER = "x-csrf-token"
MAX_BODY_BYTES = 1_000_000
SAFE_METHODS = {"GET", "HEAD"}
MAX_FAILED_EXCHANGES = 5

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}


class Security:
    def __init__(self, port: int):
        self.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
        self.launch_token = secrets.token_urlsafe(32)
        self._token_used = False
        self._failed = 0
        self._sessions: dict[str, str] = {}  # session id -> CSRF token

    def exchange(self, token: str) -> tuple[str, str] | None:
        """Trade the single-use launch token for a browser session."""
        if self._token_used or self._failed >= MAX_FAILED_EXCHANGES:
            return None
        if not secrets.compare_digest(token.encode(), self.launch_token.encode()):
            self._failed += 1
            return None
        self._token_used = True
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._sessions[sid] = csrf
        return sid, csrf

    def csrf_for(self, sid: str | None) -> str | None:
        return self._sessions.get(sid) if sid else None

    def new_session_for_tests(self) -> tuple[str, str]:
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._sessions[sid] = csrf
        return sid, csrf


def _deny(status: int, reason: str) -> Response:
    resp = JSONResponse({"error": reason}, status_code=status)
    resp.headers.update(SECURITY_HEADERS)
    return resp


def make_guard(security: Security) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        # 1. Host allowlist: defeats DNS rebinding, where a hostile domain resolves to 127.0.0.1.
        if request.headers.get("host", "") not in security.allowed_hosts:
            return _deny(400, "host not allowed")

        method = request.method.upper()
        if method not in SAFE_METHODS and method not in {"POST", "PUT", "DELETE"}:
            return _deny(405, "method not allowed")  # includes OPTIONS: no CORS preflight support

        # 2. Origin and fetch metadata: a cross-site page cannot forge these.
        origin = request.headers.get("origin")
        if origin is not None and origin not in security.allowed_origins:
            return _deny(403, "origin not allowed")
        fetch_site = request.headers.get("sec-fetch-site")
        if fetch_site is not None and fetch_site not in {"same-origin", "none"}:
            return _deny(403, "cross-site request")

        mutating = method not in SAFE_METHODS
        if mutating:
            if origin is None:
                return _deny(403, "origin required")
            # POST and PUT must be JSON: an HTML form on another site cannot send that.
            # DELETE carries no body; a form cannot issue it at all, and it still needs Origin and CSRF.
            if method != "DELETE" and not request.headers.get("content-type", "").startswith("application/json"):
                return _deny(415, "json required")
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                return _deny(400, "bad content-length")
            if length > MAX_BODY_BYTES:
                return _deny(413, "body too large")

        # 3. Session cookie and CSRF header for every API call.
        if request.url.path.startswith("/api/"):
            csrf = security.csrf_for(request.cookies.get(COOKIE_NAME))
            if csrf is None:
                return _deny(401, "not signed in")
            if mutating:
                sent = request.headers.get(CSRF_HEADER, "")
                if not secrets.compare_digest(sent.encode(), csrf.encode()):
                    return _deny(403, "bad csrf token")

        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    return guard
