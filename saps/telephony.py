"""Twilio: Video access tokens (real calls) and outbound WhatsApp or SMS.

Everything degrades cleanly. With no Twilio settings the app uses the text call path and says so.
Secrets come only from environment variables.
"""
import re
import threading

from .config import Config


def _client_for_messages():
    from twilio.rest import Client

    return Client(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_AUTH_TOKEN)


def _client_for_video():
    from twilio.rest import Client

    return Client(Config.TWILIO_API_KEY_SID, Config.TWILIO_API_KEY_SECRET, Config.TWILIO_ACCOUNT_SID)


def room_name(case_id):
    return "saps-" + re.sub(r"[^A-Za-z0-9-]", "", case_id)


def ensure_room(room):
    """Create the room if it does not exist. Tries the cheapest room types first."""
    try:
        client = _client_for_video()
        for rtype in ("go", "peer-to-peer", "group"):
            try:
                client.video.v1.rooms.create(unique_name=room, type=rtype)
                return True
            except Exception as exc:  # already exists, or type not allowed on this account
                if "53113" in str(exc) or "already exists" in str(exc).lower():
                    return True
        return False
    except Exception as exc:
        print(f"[video] ensure_room failed: {type(exc).__name__}: {exc}", flush=True)
        return False


def video_token(identity, room):
    from twilio.jwt.access_token import AccessToken
    from twilio.jwt.access_token.grants import VideoGrant

    token = AccessToken(Config.TWILIO_ACCOUNT_SID, Config.TWILIO_API_KEY_SID, Config.TWILIO_API_KEY_SECRET, identity=identity, ttl=3600)
    token.add_grant(VideoGrant(room=room))
    jwt = token.to_jwt()
    return jwt.decode() if isinstance(jwt, bytes) else jwt


def _send(to, body, from_=None):
    try:
        _client_for_messages().messages.create(from_=from_ or Config.TWILIO_WHATSAPP_FROM, to=to, body=body)
        print("[twilio] message sent", flush=True)
        return True
    except Exception as exc:
        print(f"[twilio] send failed: {type(exc).__name__}: {exc}", flush=True)
        return False


def whatsapp_to(number):
    digits = re.sub(r"[^\d+]", "", number or "")
    if digits.startswith("0"):
        digits = "+27" + digits[1:]
    elif not digits.startswith("+"):
        digits = "+" + digits
    return "whatsapp:" + digits


def send_whatsapp(number, body):
    """Fire and forget. Never raises, never blocks the request."""
    if not Config.whatsapp_enabled() or not number:
        return False
    threading.Thread(target=_send, args=(whatsapp_to(number), body), daemon=True).start()
    return True


def map_link(lat, lon):
    if lat is None or lon is None:
        return ""
    return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=17/{lat}/{lon}"
