"""All configuration comes from environment variables. Nothing secret lives in code.

A local `.env` file (git-ignored) is read if present, so `python app.py` works on a laptop.
"""
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def env(name, default=""):
    return os.environ.get(name, default)


class Config:
    # Sessions. If SECRET_KEY is unset a random one is made at start, so sessions end on restart.
    SECRET_KEY = env("SECRET_KEY") or secrets.token_hex(32)
    # Staff logins. If a password is unset, that login is switched off rather than left open.
    DESK_PASSWORD = env("DESK_PASSWORD")
    BOARD_PASSWORD = env("BOARD_PASSWORD")
    ADMIN_TOKEN = env("ADMIN_TOKEN")  # lets the demo owner reset to seed data

    # Persistence. "memory" (default) or "firestore". Firestore keeps data across restarts.
    STORE = env("STORE", "memory")
    GCP_PROJECT = env("GCP_PROJECT", "nordien-saps-kzn")
    FIRESTORE_PREFIX = env("FIRESTORE_PREFIX", "saps_")

    # Demo data
    SEED_ON_START = env("SEED_ON_START", "1") == "1"
    # Officers give an ID and a photo when they sign in and out. Set to 0 only if a demo laptop has no working camera.
    REQUIRE_SIGNIN_PHOTO = env("REQUIRE_SIGNIN_PHOTO", "1") == "1"

    # Twilio. Everything here is optional; features switch off cleanly without it.
    ICE_SERVERS = env("ICE_SERVERS")  # optional JSON list of WebRTC servers (STUN/TURN) for calls between the app and the desk
    TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_FROM = env("TWILIO_WHATSAPP_FROM")  # e.g. whatsapp:+14155238886 (sandbox)
    TWILIO_API_KEY_SID = env("TWILIO_API_KEY_SID")  # for Twilio Video access tokens
    TWILIO_API_KEY_SECRET = env("TWILIO_API_KEY_SECRET")
    WHATSAPP_DISPLAY = env("WHATSAPP_DISPLAY")  # shown to citizens, e.g. +1 415 523 8886
    WHATSAPP_JOIN_HINT = env("WHATSAPP_JOIN_HINT")  # sandbox join phrase, shown on the info card

    # Public base URL (used to build map links in WhatsApp messages)
    PUBLIC_URL = env("PUBLIC_URL").rstrip("/")

    PORT = int(env("PORT", "8080"))
    MAX_BODY = 1_500_000  # bytes; photos are shrunk in the browser first

    @classmethod
    def video_enabled(cls):
        return bool(cls.TWILIO_ACCOUNT_SID and cls.TWILIO_API_KEY_SID and cls.TWILIO_API_KEY_SECRET)

    @classmethod
    def whatsapp_enabled(cls):
        return bool(cls.TWILIO_ACCOUNT_SID and cls.TWILIO_AUTH_TOKEN and cls.TWILIO_WHATSAPP_FROM)
