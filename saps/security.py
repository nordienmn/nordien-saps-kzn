"""Login, sessions, request checks and security headers."""
import hmac
import re
from functools import wraps
from urllib.parse import urlparse

from flask import jsonify, request, session

from .config import Config

OFFICER_RE = re.compile(r"^[A-Za-z0-9-]{2,12}$")

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://unpkg.com https://cdnjs.cloudflare.com https://sdk.twilio.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com https://cdnjs.cloudflare.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://*.tile.openstreetmap.org https://unpkg.com https://cdnjs.cloudflare.com",
    "media-src 'self' blob:",
    "connect-src 'self' https://*.twilio.com wss://*.twilio.com https://tile.openstreetmap.org https://*.tile.openstreetmap.org",
    "worker-src 'self' blob:",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
])


def apply_headers(resp):
    resp.headers["Content-Security-Policy"] = CSP
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    # Camera, microphone and location are used by the citizen app itself.
    resp.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=(self)"
    if request.path.startswith("/api/") or request.path in ("/", "/citizen", "/desk", "/commissioner", "/weather", "/partner"):
        resp.headers["Cache-Control"] = "no-store"
    resp.headers.pop("Server", None)
    return resp


def same_origin_ok():
    """Reject cross-site writes. Browsers send Origin on POST; a mismatch means another site."""
    origin = request.headers.get("Origin")
    if not origin:
        return True
    return urlparse(origin).netloc == request.host


def check_password(role, supplied):
    expected = {"desk": Config.DESK_PASSWORD, "board": Config.BOARD_PASSWORD}.get(role, "")
    if not expected:
        return None  # login switched off
    return hmac.compare_digest(str(supplied or ""), expected)


def current():
    return session.get("role"), session.get("officer", "")


def login_required(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            role, _ = current()
            if role not in roles:
                return jsonify({"error": "Please sign in.", "code": "auth"}), 401
            return fn(*a, **kw)

        return wrapper

    return deco
