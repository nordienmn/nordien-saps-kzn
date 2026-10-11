"""Domain logic: cases, calls, tips, referrals, audit and the feeds the desk and board read.

Rules baked in here (so the pages cannot get them wrong):
- Tips are stored apart from cases and carry no identity, no device id and no IP address.
- GBV and weather-SOS records are RESTRICTED: names and numbers are hidden in lists and every
  time one is opened it is written to the audit log.
- The board never receives names, mobile numbers or photos.
- Anything the citizen types is kept as plain text. Pages render it with textContent.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from . import blobs, geo, taxonomy
from .store import now

YEAR = lambda ts=None: datetime.fromtimestamp(ts or now(), timezone.utc).year  # noqa: E731

MAX_NOTE = 2000
MAX_TRANSCRIPT_LINES = 300
CALL_LIMIT_S = 60       # demo rule: a live call or video lasts one minute
RING_LIMIT_S = 90       # an unanswered call is closed after this long
DROP_S = 20             # a live call whose caller has not been heard from for this long is treated as dropped
MISSED_KEEP_S = 24 * 3600  # a missed call stays on every desk until it is returned, up to a day
RING_APP_S = 45         # a call-back that rings the caller's app is given up after this long
SAST = timezone(timedelta(hours=2))
_SEEN = {}              # case id -> last time the caller's app checked in (memory only, one worker)
MAX_PHOTO_BYTES = 250_000
MAX_FACE_BYTES = 150_000
MAX_PHOTOS = 3


class Invalid(Exception):
    """A request the citizen or officer can fix. The message is safe to show them."""

    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


# ----------------------------------------------------------------------------- cleaning
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text, limit=200):
    if text is None:
        return ""
    return _CTRL.sub("", str(text)).strip()[:limit]


def clean_mobile(value):
    value = clean(value, 30)
    if not value:
        return ""
    digits = re.sub(r"[^\d+]", "", value)
    body = digits.lstrip("+")
    if not body.isdigit() or not 9 <= len(body) <= 13:
        raise Invalid("That mobile number does not look right.", "mobile")
    return digits


def clean_point(payload):
    """Return (lat, lon, address). Coordinates outside KwaZulu-Natal are dropped, not guessed."""
    lat, lon = payload.get("lat"), payload.get("lon")
    address = clean(payload.get("address"), 200)
    if lat in (None, "") or lon in (None, ""):
        return None, None, address
    if not geo.valid_point(lat, lon):
        return None, None, address
    return round(float(lat), 5), round(float(lon), 5), address


def _check_image(data_url, limit):
    if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
        raise Invalid("That picture could not be read.", "photo")
    try:
        head, _, body = data_url.partition(",")
        raw = base64.b64decode(body, validate=True)
    except Exception:
        raise Invalid("That picture could not be read.", "photo")
    if len(raw) > limit:
        raise Invalid("That picture is too large. Try again.", "photo")
    magic_ok = raw[:2] == b"\xff\xd8" or raw[:4] == b"\x89PNG" or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
    if not magic_ok:
        raise Invalid("That picture could not be read.", "photo")
    return data_url


# ----------------------------------------------------------------------------- audit
def audit(store, actor, role, action, target="", detail=""):
    entry = {
        "id": f"A{store.next_seq('audit'):06d}",
        "at": now(),
        "actor": clean(actor, 40) or "system",
        "role": role,
        "action": action,
        "target": target,
        "detail": clean(detail, 300),
    }
    store.put("audit", entry)
    return entry


def event(case, actor, text, kind="note"):
    case.setdefault("timeline", []).append({"at": now(), "actor": clean(actor, 40) or "system", "text": clean(text, 300), "kind": kind})
    case["updated_at"] = now()


def _ref(store, prefix, width=5):
    return f"{prefix}-{YEAR()}-{store.next_seq(prefix + str(YEAR())):0{width}d}"


# ----------------------------------------------------------------------------- cases
def _save_media(store, case, photos, face, uploads=None):
    media = []
    for i, data_url in enumerate(photos[:MAX_PHOTOS]):
        mid = f"{case['id']}-p{i + 1}"
        try:
            store.put("media", {"id": mid, "case_id": case["id"], "type": "photo", "data_url": _check_image(data_url, MAX_PHOTO_BYTES)})
            media.append({"id": mid, "type": "photo"})
        except Invalid:
            continue  # an unreadable picture is left out; the report still goes through
    if face:
        # The profile photo is optional. A bad one must never stop a call or a report, so it is simply left out.
        try:
            mid = f"{case['id']}-face"
            store.put("media", {"id": mid, "case_id": case["id"], "type": "face", "data_url": _check_image(face, MAX_FACE_BYTES)})
            media.append({"id": mid, "type": "face"})
        except Invalid:
            pass
    for n, upload_id in enumerate((uploads or [])[:2]):
        up = blobs.take_upload(clean(upload_id, 60))
        if not up:
            continue
        mid = f"{case['id']}-v{n + 1}"
        kind = "video" if up["mime"].startswith("video/") else "audio" if up["mime"].startswith("audio/") else "photo_file"
        key = f"media/{case['id']}/{mid}"
        storage = blobs.put(key, up["data"], up["mime"])
        store.put("media", {"id": mid, "case_id": case["id"], "type": kind, "mime": up["mime"], "size": len(up["data"]), "storage": storage, "key": key})
        media.append({"id": mid, "type": kind, "size": len(up["data"])})
    return media


def add_recording_chunk(store, case_id, officer, chunk, source="desk"):
    """Desk uploads the call recording in pieces while the call runs. It is saved on the file automatically."""
    case = store.get("cases", case_id)
    if case is None or not case.get("call"):
        raise Invalid("Call not found.")
    mid = f"{case_id}-rec" if source == "desk" else f"{case_id}-recc"
    meta = store.get("media", mid)
    if meta is None:
        key = f"media/{case_id}/{mid}"
        meta = {"id": mid, "case_id": case_id, "type": "recording", "source": source, "mime": "video/webm", "size": 0, "storage": "gcs" if blobs._bucket() is not None else "memory", "key": key}
        store.put("media", meta)
        blobs.put(key, b"", "video/webm")  # always start a file's recording clean (a demo reset restarts the case numbers)

        def add(c):
            c["media"].append({"id": mid, "type": "recording", "source": source, "size": 0})
            event(c, officer, "Call recording started and saved to this file.", "call")

        store.patch("cases", case_id, add)
    size = blobs.append(meta["key"], chunk, meta["storage"])
    if size is None:
        raise Invalid("The recording is too large.")
    store.patch("media", mid, lambda m: m.update(size=size))
    store.patch("cases", case_id, lambda c: [m.update(size=size) for m in c["media"] if m["id"] == mid])
    return size


def blob_for(store, media_id, officer):
    meta = store.get("media", media_id)
    if meta is None or "key" not in meta:
        return None
    audit(store, officer, "desk", "media.view", meta["case_id"], meta["type"])
    return meta["mime"], blobs.get(meta["key"], meta["storage"])


def _default_needs(wants, given, label_key, age_band):
    """What a GBV file will probably need. The desk can change it. A sexual offence adds the evidence kit and medical care."""
    if isinstance(given, list):
        return [k for k in given if k in taxonomy.GBV_NEEDS]
    needs = ["female_officer", "counsellor"]
    for w, n in (("hospital", "medical"), ("shelter", "shelter"), ("transport", "transport")):
        if w in (wants or []):
            needs.append(n)
    if label_key == "sexual_offence":
        needs += ["kit_d7" if age_band == "under_18" else "kit_d1", "medical", "vfr"]
    return list(dict.fromkeys(needs))


def create_case(store, payload, channel="app", synthetic=False, created_at=None):
    """Create a crime, gbv, sos, area or call case. Returns the stored case (full record)."""
    kind = clean(payload.get("kind"), 12)
    if kind not in ("crime", "gbv", "sos", "area", "call"):
        raise Invalid("Unknown report type.", "kind")

    lat, lon, address = clean_point(payload)
    cluster = geo.nearest_cluster(lat, lon) if lat is not None else geo.UNLOCATED
    if cluster == geo.UNLOCATED and payload.get("cluster") in geo.CLUSTERS and synthetic:
        cluster = payload["cluster"]  # only seed data may name a cluster directly

    missing = []  # what the citizen did not give. A report is NEVER refused for being incomplete; the desk sees what is missing.
    name = clean(payload.get("name"), 80)
    try:
        mobile = clean_mobile(payload.get("mobile"))
    except Invalid:
        mobile = ""
        missing.append("a valid mobile number")
    note = clean(payload.get("note"), MAX_NOTE)
    # Optional, self-described, used only in grouped statistics. Anything not recognised becomes "undisclosed".
    gender = payload.get("gender") if payload.get("gender") in taxonomy.GENDERS else "undisclosed"
    age_band = payload.get("age_band") if payload.get("age_band") in taxonomy.AGE_BANDS else "undisclosed"
    language = payload.get("lang") if payload.get("lang") in taxonomy.LANGUAGES else "en"
    home_address = clean(payload.get("home_address"), 120)
    friend_name = clean(payload.get("friend_name"), 60)
    registered = bool(payload.get("registered")) or bool(name and mobile)  # a citizen with a profile: the file carries it
    label_key = "other"
    priority = "normal"
    extra = {}

    if kind == "crime":
        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.CRIME_TYPES:
            label_key = "other"
            missing.append("the type of crime")
        if lat is None and not address:
            missing.append("the place")
        priority = taxonomy.CRIME_TYPES[label_key][2]
        if taxonomy.CRIME_TYPES[label_key][3]:
            kind = "gbv"  # a domestic-violence or sexual-offence report goes to the GBV door
        occurred = payload.get("occurred_at")
        if occurred not in (None, ""):
            try:
                occurred = float(occurred) / 1000.0
                if now() - 30 * 86400 <= occurred <= now() + 3600:
                    extra["occurred_at"] = occurred
            except (TypeError, ValueError):
                pass  # an unreadable time is simply left out
    elif kind == "gbv":
        label_key = "gbv_request"
        safe = clean(payload.get("safe_now"), 8)
        if safe not in ("yes", "no", "unsure"):
            safe = "unsure"
            missing.append("whether they are safe right now")
        wants = [w for w in (payload.get("wants") or []) if w in ("social_worker", "hospital", "shelter", "transport", "police")]
        contact_pref = clean(payload.get("contact_pref"), 8)
        if contact_pref not in ("call", "sms", "none"):
            contact_pref = "none"
        if contact_pref in ("call", "sms") and not mobile:
            contact_pref = "none"
            missing.append("a number to reach them")
        priority = "critical" if safe == "no" else "high"
        extra.update({
            "safe_now": safe,
            "wants": wants,
            "know_person": clean(payload.get("know_person"), 6) if payload.get("know_person") in ("yes", "no", "skip") else "skip",
            "contact_pref": contact_pref,
            "needs": _default_needs(wants, payload.get("needs"), label_key, payload.get("age_band")),
        })
    elif kind == "sos":
        label_key = "weather_sos"
        priority = "critical"
        extra["needs"] = ["female_officer", "counsellor"]
    elif kind == "area":
        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.AREA_TYPES:
            label_key = "other"
            missing.append("what is unsafe")
        if lat is None and not address:
            missing.append("the place")
        priority = "low"
        name = mobile = home_address = friend_name = ""  # unsafe-area reports never carry a person
        registered = False
    elif kind == "call":
        label_key = "voice_call" if payload.get("mode") != "video" else "video_call"
        priority = "critical"

    prefix = "MUN" if kind == "area" else "KZN"
    cid = _ref(store, prefix)
    ts = created_at or now()
    case = {
        "id": cid,
        "ref": cid,
        "kind": kind,
        "channel": channel,
        "status": "new",
        "priority": priority,
        "label_key": label_key,
        "cluster": cluster,
        "lat": lat,
        "lon": lon,
        "address": address,
        "name": name,
        "mobile": mobile,
        "note": note,
        "assigned_to": "",
        "gender": gender,
        "age_band": age_band,
        "language": language,
        "registered": registered,
        "incomplete": bool(missing),
        "missing": missing,
        "home_address": home_address,
        "friend_name": friend_name,
        "friend": clean(payload.get("friend"), 40) if kind in ("gbv", "sos", "crime", "call") else "",
        "deployments": [],
        "media": [],
        "transcript": [],
        "timeline": [{"at": ts, "actor": "citizen" if not synthetic else "system", "text": f"Received via {channel}.", "kind": "system"}],
        "referrals": [],
        "created_at": ts,
        "updated_at": ts,
        "first_action_at": None,
        "closed_at": None,
        "restricted": kind in taxonomy.RESTRICTED_KINDS,
        "synthetic": synthetic,
    }
    case.update(extra)
    if case["kind"] == "gbv" and "needs" not in case:
        case["needs"] = _default_needs([], None, label_key, age_band)
    if not synthetic:
        case["media"] = _save_media(store, case, payload.get("photos") or [], payload.get("face") or "", payload.get("uploads") or [])
    store.put("cases", case)
    return case


def case_label(case, lang="en"):
    key = case["label_key"]
    if case["kind"] == "area":
        row = taxonomy.AREA_TYPES.get(key)
        return (row[1] if lang == "zu" else row[0]) if row else key
    special = {
        "gbv_request": ("GBV help request", "Isicelo sosizo lwe-GBV"),
        "weather_sos": ("Discreet SOS (GBV)", "I-SOS ecashile (GBV)"),
        "voice_call": ("Voice call", "Ucingo lwezwi"),
        "video_call": ("Video call", "Ucingo lwevidiyo"),
    }
    if key in special:
        return special[key][1 if lang == "zu" else 0]
    return taxonomy.crime_label(key, lang)


# ----------------------------------------------------------------------------- tips
def create_tip(store, payload, synthetic=False, created_at=None):
    """An anonymous tip. Stores no name, no number, no device or network identifier.

    Returns (tip, code). The one-time code is shown to the citizen once; only its hash is kept.
    """
    missing = []
    key = clean(payload.get("type"), 40)
    if key not in taxonomy.TIP_TYPES:
        key = "other"
        missing.append("what is being reported")
    lat, lon, address = clean_point(payload)
    if lat is None and not address:
        missing.append("the place")
    code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
    cluster = geo.nearest_cluster(lat, lon) if lat is not None else geo.UNLOCATED
    if cluster == geo.UNLOCATED and synthetic and payload.get("cluster") in geo.CLUSTERS:
        cluster = payload["cluster"]
    tid = _ref(store, "TIP", 4)
    ts = created_at or now()
    tip = {
        "id": tid,
        "ref": tid,
        "type_key": key,
        "cluster": cluster,
        "lat": lat,
        "lon": lon,
        "address": address,
        "note": clean(payload.get("note"), MAX_NOTE),
        "status": "new",  # new | verified | referred | acknowledged | directed | closed
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "timeline": [{"at": ts, "actor": "system", "text": "Tip received. Not a case. No identity stored.", "kind": "system"}],
        "created_at": ts,
        "updated_at": ts,
        "incomplete": bool(missing),
        "missing": missing,
        "verification": None,
        "referred_at": None,
        "referred_by": "",
        "referral_note": "",
        "referrals": [],
        "synthetic": synthetic,
        "restricted": True,
        "media": [],
    }
    if not synthetic:
        tip["media"] = _save_media(store, tip, (payload.get("photos") or [])[:1], "")  # photos are re-encoded in the browser, so location EXIF is gone
    store.put("tips", tip)
    return tip, code


def tip_label(tip, lang="en"):
    row = taxonomy.TIP_TYPES.get(tip["type_key"])
    return (row[1] if lang == "zu" else row[0]) if row else tip["type_key"]


# Tip life: new -> verified -> referred (a VERIFIED REFERRAL FOR HQ ACTION) -> acknowledged -> directed -> closed.
# The desk's tip-off line sees every tip first, checks it and acts on it. It refers to HQ only after verification.
# HQ sees every tip as it comes in (oversight) and, separately, the verified referrals that need its action.
TIP_OUTCOMES = {
    "used": "The information was used.",
    "no_action": "There was not enough to act on.",
    "duplicate": "This matched another tip already being handled.",
    "not_verified": "It could not be verified.",
}


def verify_tip(store, tip_id, officer, payload):
    result = clean(payload.get("result"), 14)
    note = clean(payload.get("note"), 300)
    if result not in ("verified", "not_verified"):
        raise Invalid("Choose a result.", "result")
    if len(note) < 3:
        raise Invalid("Say how you checked it.", "note")

    def fn(tip):
        if tip["status"] == "closed":
            raise Invalid("This tip is closed.")
        tip["verification"] = {"result": result, "by": officer, "at": now(), "note": note}
        if result == "verified" and tip["status"] == "new":
            tip["status"] = "verified"
        event(tip, officer, ("Verified: " if result == "verified" else "Could not verify: ") + note, "verify")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, officer, "desk", "tip.verify", tip_id, result)
    return tip


def action_tip(store, tip_id, officer, note):
    note = clean(note, 300)
    if len(note) < 3:
        raise Invalid("Write what was done.", "note")

    def fn(tip):
        if tip["status"] == "closed":
            raise Invalid("This tip is closed.")
        event(tip, officer, "Action taken at the desk: " + note, "action")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, officer, "desk", "tip.action", tip_id)
    return tip


def refer_tip_to_hq(store, tip_id, officer, note=""):
    """Only a verified tip can be referred. HQ then sees it as a verified referral for its action."""
    note = clean(note, 300)

    def fn(tip):
        if tip["status"] != "verified":
            raise Invalid("Verify the tip before you refer it to HQ.")
        tip["status"] = "referred"
        tip["referred_at"] = now()
        tip["referred_by"] = officer
        tip["referral_note"] = note
        event(tip, officer, "Verified referral sent to HQ for action." + (" " + note if note else ""), "refer")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, officer, "desk", "tip.refer_hq", tip_id)
    return tip


def acknowledge_tip(store, tip_id, actor):
    def fn(tip):
        if tip["status"] == "referred":
            tip["status"] = "acknowledged"
            event(tip, actor, "Acknowledged by HQ.", "ack")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, actor, "board", "tip.acknowledge", tip_id)
    return tip


def close_tip(store, tip_id, actor, outcome, role="board"):
    if outcome not in TIP_OUTCOMES:
        raise Invalid("Choose an outcome.", "outcome")

    def fn(tip):
        if role == "desk" and tip["status"] in ("referred", "acknowledged", "directed"):
            raise Invalid("This tip is with HQ. HQ closes it.")
        tip["status"] = "closed"
        tip["outcome"] = outcome
        tip["closed_at"] = now()
        tip["closed_by"] = role
        event(tip, actor, "Closed. " + TIP_OUTCOMES[outcome], "close")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, actor, role, "tip.close", tip_id, outcome)
    return tip


def tip_public_status(store, code):
    """What the citizen sees when they check a tip with their one-time code. No identity is involved."""
    tip = check_tip_code(store, code)
    if tip is None:
        return None
    stage = {"new": "received", "verified": "checked", "referred": "senior", "acknowledged": "senior", "directed": "unit", "closed": "closed"}.get(tip["status"], "received")
    return {"ref": tip["ref"], "stage": stage, "outcome": TIP_OUTCOMES.get(tip.get("outcome", ""), ""), "updated_at": tip["updated_at"]}


def check_tip_code(store, code):
    h = hashlib.sha256(clean(code, 12).upper().encode()).hexdigest()
    for tip in store.all("tips"):
        if hmac.compare_digest(tip["code_hash"], h):
            return tip
    return None


# ----------------------------------------------------------------------------- calls
def start_call(store, payload, channel="app"):
    mode = "video" if payload.get("mode") == "video" else "voice"
    payload = dict(payload, kind="call", mode=mode)
    case = create_case(store, payload, channel=channel)
    ctoken = secrets.token_urlsafe(18)

    def fn(c):
        c["_ctoken"] = ctoken
        c["call"] = {"state": "ringing", "mode": mode, "transport": "text", "room": "", "started_at": now(), "answered_at": None, "ended_at": None, "operator": "", "missed": False, "missed_reason": "", "returned": False, "callback": None, "callbacks": [], "app_callback": None, "ring": None, "nature": "", "outcome": "", "action_text": ""}
        event(c, "citizen", f"{mode.capitalize()} call started. Ringing at the control room.", "call")

    case = store.patch("cases", case["id"], fn)
    return case, ctoken


def _ctoken_ok(case, ctoken):
    return bool(case) and bool(ctoken) and hmac.compare_digest(case.get("_ctoken", ""), str(ctoken))


def expire_calls(store):
    """Enforce the demo limits. Called whenever calls are read, so nothing needs a background timer."""
    t = now()
    for c in store.all("cases"):
        call = c.get("call")
        if not call:
            continue
        ring = call.get("ring")
        if ring and ring["state"] == "ringing" and t - ring["at"] > RING_APP_S:
            def _no_answer(x):
                x["call"]["ring"]["state"] = "no_answer"
                event(x, "system", "The call-back was not answered. Try again, or send a message to the app.", "call")
            store.patch("cases", c["id"], _no_answer)
        if call["state"] == "live" and call.get("answered_at") and t - call["answered_at"] > CALL_LIMIT_S:
            end_call(store, c["id"], "system", "the one-minute demo limit")
        elif call["state"] == "live" and c["id"] in _SEEN and t - _SEEN[c["id"]] > DROP_S:
            end_call(store, c["id"], "system", "the line (the caller disconnected)", reason="dropped")
        elif call["state"] == "ringing" and t - call["started_at"] > RING_LIMIT_S:
            end_call(store, c["id"], "system", "the system (nobody answered)", reason="unanswered")


def citizen_call_state(store, case_id, ctoken):
    expire_calls(store)
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken) or not case.get("call"):
        raise Invalid("Call not found.")
    call = case["call"]
    if call["state"] != "ended":
        _SEEN[case_id] = now()
    ahead = 0
    if call["state"] == "ringing":
        ahead = sum(1 for c in store.all("cases") if c.get("call") and c["call"]["state"] == "ringing" and c["call"]["started_at"] < call["started_at"])
    return {
        "state": call["state"],
        "mode": call["mode"],
        "transport": call.get("transport", "text"),
        "room": call.get("room", ""),
        "operator": call.get("operator", ""),
        "queue_ahead": ahead,
        "answered_at": call.get("answered_at"),
        "ended_at": call.get("ended_at"),
        "missed": bool(call.get("missed")),
        "callback_requested": bool(call.get("app_callback")),
        "ring_state": (call.get("ring") or {}).get("state", ""),
        "ring_mode": (call.get("ring") or {}).get("mode", "voice"),
        "limit_s": CALL_LIMIT_S,
        "case": _citizen_case_view(store, case),
        "recording": bool(call.get("recording")),
        "lines": case["transcript"][-60:],
        "ref": case["ref"],
    }


def _citizen_case_view(store, case):
    """What the caller may know about their own file: who has it, where it is going, and what to do now. No other person's details."""
    call = case.get("call") or {}
    going = [{"kind": "station", "name": d["station_name"], "unit": d.get("unit", ""), "status": d["status"]} for d in case.get("deployments", [])]
    for rid in case.get("referrals", []):
        r = store.get("referrals", rid)
        if r:
            going.append({"kind": "partner", "name": r["partner_name"], "status": r["status"]})
    nxt = []
    if call.get("missed") and not call.get("returned"):
        nxt.append("callback")
    if case["status"] != "closed":
        nxt += ["keep_phone", "quote_ref"]
    if any(g["kind"] == "station" for g in going):
        nxt.append("unit")
    if any(g["kind"] == "partner" for g in going):
        nxt.append("partner")
    if case["status"] == "closed":
        nxt.append("closed")
    nxt.append("emergency")
    return {"ref": case["ref"], "status": case["status"], "handler": case.get("assigned_to") or call.get("operator") or "", "going": going,
            "cas": (case.get("external") or {}).get("cas_number", ""), "next": nxt}


def answer_call(store, case_id, officer, transport="text", room=""):
    sig_reset(case_id)
    def fn(c):
        call = c.get("call")
        if not call or call["state"] != "ringing":
            raise Invalid("That call is no longer ringing.")
        call.update({"state": "live", "answered_at": now(), "operator": officer, "transport": transport, "room": room, "recording": transport == "video"})
        c["assigned_to"] = officer
        c["status"] = "in_progress"
        c["first_action_at"] = c["first_action_at"] or now()
        event(c, officer, "Call answered.", "call")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Call not found.")
    audit(store, officer, "desk", "call.answer", case_id)
    return case


def end_call(store, case_id, actor, who, reason=None):
    def fn(c):
        call = c.get("call")
        if not call or call["state"] == "ended":
            return
        answered = call["state"] == "live"
        call["state"] = "ended"
        call["ended_at"] = now()
        secs = int(call["ended_at"] - call["answered_at"]) if answered and call.get("answered_at") else 0
        call["duration"] = secs
        if answered and reason == "dropped":
            call["missed"] = True
            call["missed_reason"] = "dropped"
            event(c, actor, f"Call dropped: {who}. Duration {secs // 60}:{secs % 60:02d}. Call back.", "call")
        elif answered:
            event(c, actor, f"Call ended by {who}. Duration {secs // 60}:{secs % 60:02d}.", "call")
        else:
            c["status"] = "new"
            call["missed"] = True
            call["missed_reason"] = reason or "unanswered"
            why = "The caller hung up before it was answered." if call["missed_reason"] == "caller_hung_up" else "Nobody answered in time."
            event(c, actor, f"Missed call. {why} Call back.", "call")
        _SEEN.pop(case_id, None)
        _SIG.pop(case_id, None)

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Call not found.")
    return case


def add_line(store, case_id, who, text, src="typed", partial=False):
    """Add to the transcript. A partial line is what someone is saying right now; it is replaced by the next one."""
    text = clean(text, 500)
    if not text:
        raise Invalid("Empty message.")

    def fn(c):
        lines = c["transcript"]
        last = lines[-1] if lines else None
        if last and last.get("partial") and last["who"] == who:
            last.update({"text": text, "at": now(), "partial": bool(partial), "src": src})
        else:
            if len(lines) >= MAX_TRANSCRIPT_LINES:
                raise Invalid("Transcript is full.")
            lines.append({"at": now(), "who": who, "text": text, "src": src, "partial": bool(partial)})
        c["updated_at"] = now()

    return store.patch("cases", case_id, fn)


def citizen_add_line(store, case_id, ctoken, text, src="typed", partial=False):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")
    return add_line(store, case_id, "citizen", text, "caption" if src == "caption" else "typed", partial)


def callback_call(store, case_id, officer, method, note=""):
    """Return a missed or dropped call. phone: logged against the number on record. app: a message in the caller's app.
    ring_voice / ring_video: ring the caller's app now, like a real call."""
    method = method if method in ("phone", "app", "ring_voice", "ring_video") else "app"
    note = clean(note, 200)

    def fn(c):
        call = c.get("call")
        if not call or not call.get("missed"):
            raise Invalid("That call was not missed.")
        if call.get("returned"):
            raise Invalid("A call-back is already logged for this call.")
        if (call.get("ring") or {}).get("state") == "ringing":
            raise Invalid("The caller's app is already ringing.")
        if method == "phone" and not c["mobile"]:
            raise Invalid("There is no number on record for this caller.")
        entry = {"at": now(), "by": officer, "method": method, "note": note}
        call["callback"] = entry
        call.setdefault("callbacks", []).append(entry)
        if method in ("ring_voice", "ring_video"):
            mode = "video" if method == "ring_video" else "voice"
            call["ring"] = {"state": "ringing", "at": now(), "by": officer, "mode": mode}
            call["app_callback"] = {"at": now(), "by": officer}
            event(c, officer, f"Ringing the caller's app ({mode} call). Waiting for them to answer.", "call")
        elif method == "app":
            call["returned"] = True
            call["app_callback"] = {"at": now(), "by": officer}
            event(c, officer, "Call-back message sent to the caller's app (no call possible)." + (" " + note if note else ""), "call")
        else:
            call["returned"] = True
            event(c, officer, "Call-back logged by phone, on the number on record." + (" " + note if note else ""), "call")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Call not found.")
    audit(store, officer, "desk", "call.callback", case_id, method)
    return case


def citizen_answer_ring(store, case_id, ctoken):
    """The caller answers the control room's call-back in the app. The same file goes live again."""
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")

    def fn(c):
        call = c["call"]
        ring = call.get("ring")
        if not ring or ring["state"] != "ringing":
            raise Invalid("Nobody is calling you now.")
        ring["state"] = "answered"
        call.update({"state": "live", "mode": ring["mode"], "transport": "p2p", "room": "", "answered_at": now(), "ended_at": None, "operator": ring["by"], "returned": True, "recording": False})
        call.pop("duration", None)
        c["assigned_to"] = ring["by"]
        c["status"] = "in_progress"
        event(c, "citizen", "The caller answered the call-back.", "call")

    out = store.patch("cases", case_id, fn)
    sig_reset(case_id)
    _SEEN[case_id] = now()
    return out


def citizen_decline_ring(store, case_id, ctoken):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")

    def fn(c):
        ring = (c.get("call") or {}).get("ring")
        if ring and ring["state"] == "ringing":
            ring["state"] = "declined"
            event(c, "citizen", "The caller declined the call-back.", "call")

    return store.patch("cases", case_id, fn)


# ---- signalling for direct voice and video between the app and the desk (messages are kept in memory only)
_SIG = {}
SIG_MAX = 400


def sig_reset(case_id):
    _SIG[case_id] = {"seq": 0, "citizen": [], "desk": []}


def sig_post(case_id, to, kind, data):
    if to not in ("citizen", "desk") or kind not in ("offer", "answer", "ice"):
        raise Invalid("Bad signal.")
    if len(json.dumps(data)) > 20000:
        raise Invalid("Signal too large.")
    box = _SIG.setdefault(case_id, {"seq": 0, "citizen": [], "desk": []})
    if len(box[to]) >= SIG_MAX:
        raise Invalid("Too many signals.")
    box["seq"] += 1
    box[to].append({"n": box["seq"], "type": kind, "data": data})
    return box["seq"]


def sig_get(case_id, side, after):
    box = _SIG.get(case_id)
    return [m for m in box[side] if m["n"] > after] if box else []


def citizen_end_call(store, case_id, ctoken):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")
    return end_call(store, case_id, "citizen", "the caller", reason="caller_hung_up")


# ----------------------------------------------------------------------------- case actions
def act(store, case_id, officer, payload):
    action = clean(payload.get("action"), 20)
    note = clean(payload.get("note"), 300)

    def fn(c):
        if action == "accept":
            c["assigned_to"] = officer
            if c["status"] == "new":
                c["status"] = "assigned"
            c["first_action_at"] = c["first_action_at"] or now()
            event(c, officer, "Accepted the file.", "action")
        elif action == "start":
            c["status"] = "in_progress"
            c["assigned_to"] = c["assigned_to"] or officer
            c["first_action_at"] = c["first_action_at"] or now()
            event(c, officer, "Work started.", "action")
        elif action == "note":
            if not note:
                raise Invalid("Write a note first.", "note")
            event(c, officer, note, "note")
        elif action == "station":
            cluster = clean(payload.get("cluster"), 30)
            if cluster not in geo.CLUSTERS:
                raise Invalid("Choose a station cluster.", "cluster")
            c["cluster"] = cluster
            event(c, officer, f"Station cluster set to {geo.name(cluster)}.", "action")
        elif action == "close":
            if c.get("call") and c["call"]["state"] in ("ringing", "live"):
                raise Invalid("End the call before closing the file.")
            c["status"] = "closed"
            c["closed_at"] = now()
            c["first_action_at"] = c["first_action_at"] or now()
            event(c, officer, "Closed. " + note if note else "Closed.", "action")
        elif action == "needs":
            keys = [k for k in (payload.get("needs") or []) if k in taxonomy.GBV_NEEDS]
            c["needs"] = keys
            event(c, officer, "GBV needs set: " + (", ".join(taxonomy.GBV_NEEDS[k] for k in keys) or "none") + ".", "action")
        elif action == "demographics":
            if payload.get("gender") in taxonomy.GENDERS:
                c["gender"] = payload["gender"]
            if payload.get("age_band") in taxonomy.AGE_BANDS:
                c["age_band"] = payload["age_band"]
            event(c, officer, "Recorded gender and age group (grouped statistics only).", "action")
        elif action == "callwrap":
            if not c.get("call"):
                raise Invalid("That file has no call.")
            nature, outcome = clean(payload.get("nature"), 30), clean(payload.get("outcome"), 20)
            if nature not in call_natures() or outcome not in CALL_OUTCOMES:
                raise Invalid("Choose the nature of the call and the action taken.")
            c["call"]["nature"], c["call"]["outcome"] = nature, outcome
            c["call"]["action_text"] = clean(payload.get("action_text"), 160)
            event(c, officer, f"Call wrap-up: {call_natures()[nature]}. {CALL_OUTCOMES[outcome]}." + (" " + c["call"]["action_text"] if c["call"]["action_text"] else ""), "action")
        elif action == "reopen":
            c["status"] = "in_progress"
            c["closed_at"] = None
            event(c, officer, "Reopened.", "action")
        else:
            raise Invalid("Unknown action.")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Case not found.")
    audit(store, officer, "desk", f"case.{action}", case_id)
    return case


# ----------------------------------------------------------------------------- referrals
def seed_partners(store):
    """Referral partners. Names marked 'demo' are placeholders; contact details are never real."""
    rows = [
        ("tcc-crookes", "gbv_tcc", "GJ Crookes Thuthuzela Care Centre, Scottburgh", "Umdoni"),
        ("tcc-gizenga", "gbv_tcc", "Gizenga Mpanza Regional Hospital Thuthuzela Care Centre, KwaDukuza", "iLembe"),
        ("tcc-eshowe", "gbv_tcc", "Eshowe Thuthuzela Care Centre", "King Cetshwayo"),
        ("tcc-estcourt", "gbv_tcc", "Estcourt Thuthuzela Care Centre", "uThukela"),
        ("fcs-durban", "fcs_unit", "SAPS FCS Unit, Durban (demo)", "eThekwini"),
        ("fcs-pmb", "fcs_unit", "SAPS FCS Unit, Pietermaritzburg (demo)", "Msunduzi"),
        ("fcs-umlazi", "fcs_unit", "SAPS FCS Unit, Umlazi (demo)", "Umlazi"),
        ("shelter-durban", "shelter", "Durban safe house (demo placeholder)", "eThekwini"),
        ("shelter-pmb", "shelter", "Pietermaritzburg safe house (demo placeholder)", "Msunduzi"),
        ("health-addington", "health", "Addington Hospital (demo referral)", "eThekwini"),
        ("health-clinic", "health", "Nearest community clinic (demo)", "Any"),
        ("sw-dsd", "social_worker", "Department of Social Development, KZN (demo)", "Province"),
        ("sw-fam", "social_worker", "Family support social worker (demo)", "Any"),
        ("sw-counsellor", "social_worker", "Trauma counsellor on call (demo)", "Any"),
        ("kit-supply", "forensic_supply", "SAPS Forensic Science: evidence kit supply, D1 and D7 (demo)", "Province"),
        ("ride-demo", "transport", "Victim-support transport (demo)", "Any"),
        ("mun-ethekwini-lights", "municipal", "eThekwini Municipality: Roads and street lighting (demo)", "eThekwini"),
        ("mun-ethekwini-parks", "municipal", "eThekwini Municipality: Parks and public safety (demo)", "eThekwini"),
        ("mun-msunduzi", "municipal", "Msunduzi Municipality: Public works (demo)", "Msunduzi"),
        ("unit-flying-dbn", "saps_flying", "Flying Squad, Durban (demo)", "eThekwini"),
        ("unit-intel", "saps_intel", "Provincial Crime Intelligence (demo)", "Province"),
        ("unit-detective", "saps_detective", "Provincial Detective Service (demo)", "Province"),
    ] + [
        (f"unit-cluster-{key}", "saps_cluster", f"Cluster Commander, {val[0]} (demo)", val[0]) for key, val in geo.CLUSTERS.items()
    ]
    for pid, kind, name, area in rows:
        store.put("partners", {"id": pid, "type": kind, "name": name, "area": area, "contact": "Demo contact. Nothing is sent to a real organisation."})


def create_referral(store, case_id, officer, payload, synthetic=False):
    case = store.get("cases", case_id)
    if case is None:
        raise Invalid("Case not found.")
    partner = store.get("partners", clean(payload.get("partner_id"), 40))
    if partner is None:
        raise Invalid("Choose who to refer to.", "partner_id")
    if partner["type"] == "municipal" and case["kind"] != "area":
        raise Invalid("Municipal referrals are for unsafe-infrastructure reports.", "partner_id")
    urgency = "urgent" if payload.get("urgency") == "urgent" else "routine"
    consent = bool(payload.get("consent_to_share", True))  # demo: the disclaimer covers sharing, so the folder goes with the file
    rid = f"R{store.next_seq('referral'):05d}"
    ref = {
        "id": rid,
        "case_id": case_id,
        "case_ref": case["ref"],
        "type": partner["type"],
        "partner_id": partner["id"],
        "partner_name": partner["name"],
        "status": "sent",  # created -> sent -> acknowledged -> completed
        "urgency": urgency,
        "consent_to_share": consent,
        "note": clean(payload.get("note"), 300),
        "created_by": officer,
        "created_at": now(),
        "updated_at": now(),
        "sla_due_at": now() + 15 * 60 if urgency == "urgent" else None,
        "synthetic": synthetic,
    }
    store.put("referrals", ref)

    def fn(c):
        c["referrals"].append(rid)
        c["status"] = "referred"
        c["first_action_at"] = c["first_action_at"] or now()
        shared = "with contact details (citizen agreed)" if consent else "without contact details"
        event(c, officer, f"Referred to {partner['name']}, {shared}.", "referral")

    store.patch("cases", case_id, fn)
    if not synthetic:
        audit(store, officer, "desk", "referral.create", case_id, partner["name"])
    return ref


def create_direction(store, target_id, actor, payload):
    """HQ directs a case or a tip to a unit INSIDE SAPS, with an instruction and a due time."""
    partner = store.get("partners", clean(payload.get("unit_id"), 50))
    if partner is None or partner["type"] not in taxonomy.SAPS_UNIT_TYPES:
        raise Invalid("Choose a SAPS unit.", "unit_id")
    instruction = clean(payload.get("instruction"), 300)
    if len(instruction) < 3:
        raise Invalid("Write the instruction.", "instruction")
    try:
        minutes = int(payload.get("due_minutes") or 60)
    except (TypeError, ValueError):
        minutes = 60
    minutes = min(max(minutes, 15), 24 * 60)

    coll = "cases"
    target = store.get("cases", target_id)
    if target is None:
        target, coll = store.get("tips", target_id), "tips"
    if target is None:
        raise Invalid("That file was not found.")
    share = bool(payload.get("consent_to_share", True))
    rid = f"R{store.next_seq('referral'):05d}"
    ref = {
        "id": rid, "case_id": target_id, "case_ref": target["ref"], "type": partner["type"], "partner_id": partner["id"],
        "partner_name": partner["name"], "status": "sent", "urgency": "urgent" if minutes <= 60 else "routine",
        "consent_to_share": share, "note": instruction, "origin": "board", "instruction": instruction,
        "created_by": actor, "created_at": now(), "updated_at": now(), "due_at": now() + minutes * 60,
        "sla_due_at": now() + minutes * 60, "synthetic": False,
    }
    store.put("referrals", ref)

    def fn(doc):
        doc.setdefault("referrals", []).append(rid)
        event(doc, actor, f"Directed to {partner['name']}: {instruction} Due in {minutes} min.", "direction")
        if coll == "tips" and doc["status"] in ("new", "verified", "referred", "acknowledged"):
            doc["status"] = "directed"
        if coll == "cases":
            if doc["status"] == "new":
                doc["status"] = "assigned"
            doc["first_action_at"] = doc.get("first_action_at") or now()

    store.patch(coll, target_id, fn)
    audit(store, actor, "board", "direction.create", target_id, f"{partner['name']}: {instruction}")
    return ref


# ----------------------------------------------------------------------------- deployments
def dispatch(store, case_id, officer, payload):
    """The desk sends a station or unit to a case. Times feed the HQ response statistics."""
    station = clean(payload.get("station"), 30)
    if station not in geo.STATIONS:
        raise Invalid("Choose a station.", "station")
    unit = clean(payload.get("unit"), 30)
    if unit not in taxonomy.UNIT_KINDS:
        unit = "Patrol vehicle"
    dep = {
        "id": f"D{store.next_seq('deployment'):05d}", "station": station, "station_name": geo.station_name(station),
        "unit": unit, "status": "dispatched", "dispatched_at": now(), "dispatched_by": officer, "arrived_at": None, "cleared_at": None,
        "acknowledged_at": None, "instruction": clean(payload.get("note"), 200),
    }
    case0 = store.get("cases", case_id)
    if case0 and case0["kind"] in ("gbv", "sos"):
        asked = [k for k in (payload.get("needs") if isinstance(payload.get("needs"), list) else case0.get("needs", [])) if k in taxonomy.GBV_NEEDS]
        dep["needs"] = {k: {"status": "asked", "note": "", "at": None, "request_id": "", "request_partner": ""} for k in asked}

    def fn(c):
        if c["status"] == "closed":
            raise Invalid("This file is closed. Reopen it first.")
        c.setdefault("deployments", []).append(dep)
        c["assigned_to"] = c["assigned_to"] or officer
        if c["status"] in ("new", "assigned"):
            c["status"] = "in_progress"
        c["first_action_at"] = c.get("first_action_at") or now()
        note = clean(payload.get("note"), 200)
        event(c, officer, f"{unit} dispatched from {dep['station_name']}." + (" " + note if note else ""), "deployment")
        if dep.get("needs"):
            event(c, officer, "The station was asked to have ready: " + ", ".join(taxonomy.GBV_NEEDS[k] for k in dep["needs"]) + ".", "deployment")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Case not found.")
    audit(store, officer, "desk", "deployment.dispatch", case_id, f"{unit} from {dep['station_name']}")
    return dep


def update_deployment(store, case_id, dep_id, officer, status):
    if status not in ("acknowledged", "on_scene", "cleared"):
        raise Invalid("Unknown status.")

    def fn(c):
        for d in c.get("deployments", []):
            if d["id"] == dep_id:
                if status == "acknowledged" and d["status"] == "dispatched":
                    d["status"], d["acknowledged_at"] = "acknowledged", now()
                    event(c, officer, f"{d['station_name']} acknowledged the task.", "deployment")
                elif status == "on_scene" and not d["arrived_at"]:
                    d["status"], d["arrived_at"] = "on_scene", now()
                    event(c, officer, f"{d['unit']} from {d['station_name']} on scene.", "deployment")
                elif status == "cleared":
                    d["status"], d["cleared_at"] = "cleared", now()
                    d["arrived_at"] = d["arrived_at"] or now()
                    event(c, officer, f"{d['unit']} from {d['station_name']} cleared.", "deployment")
                return
        raise Invalid("Deployment not found.")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Case not found.")
    audit(store, officer, "desk", f"deployment.{status}", case_id)
    return case


def update_referral(store, referral_id, actor, status):
    if status not in ("acknowledged", "completed"):
        raise Invalid("Unknown status.")
    ref = store.patch("referrals", referral_id, lambda r: r.update({"status": status, "updated_at": now()}))
    if ref is None:
        raise Invalid("Referral not found.")

    def fn(c):
        event(c, actor, f"{ref['partner_name']}: {status}.", "referral")
        if status == "completed" and c.get("kind") == "area":
            c["status"] = "closed"
            c["closed_at"] = now()

    coll = "cases" if store.get("cases", ref["case_id"]) else "tips"
    store.patch(coll, ref["case_id"], fn)
    audit(store, actor, "desk", f"referral.{status}", ref["case_id"])
    return ref


def partner_view(store, partner_id):
    """What a receiving partner may see: no contact details unless the citizen agreed."""
    out = []
    for r in sorted(store.all("referrals"), key=lambda x: -x["created_at"]):
        if r["partner_id"] != partner_id:
            continue
        case = store.get("cases", r["case_id"])
        is_tip = False
        if case is None:
            case, is_tip = store.get("tips", r["case_id"]), True
        case = case or {}
        item = {
            "id": r["id"], "case_ref": r["case_ref"], "status": r["status"], "urgency": r["urgency"],
            "created_at": r["created_at"], "note": r["note"], "origin": r.get("origin", "desk"),
            "due_at": r.get("due_at"), "instruction": r.get("instruction", ""),
            "cluster": geo.name(case.get("cluster", geo.UNLOCATED)),
            "label": (tip_label(case) if is_tip else case_label(case)) if case else "",
            "lat": case.get("lat"), "lon": case.get("lon"), "address": case.get("address", ""),
            "is_tip": is_tip,
        }
        if r.get("origin") == "board" and case:
            item["detail"] = case.get("note", "")  # a SAPS unit acting on a direction needs what was reported
        if r["consent_to_share"] and case and not is_tip:
            item["name"], item["mobile"] = case.get("name", ""), case.get("mobile", "")
        out.append(item)
    return out


# ----------------------------------------------------------------------------- views
SLA_LIMITS = {"critical": (300, 900), "high": (3600, 14400), "normal": (14400, 86400), "low": (86400, 259200)}


def sla_level(case):
    if case["status"] == "closed":
        return "done"
    age = now() - case["created_at"]
    green, amber = SLA_LIMITS.get(case["priority"], SLA_LIMITS["normal"])
    return "green" if age < green else "amber" if age < amber else "red"


def _caller_profile(case, role):
    """What the desk sees about a caller who is registered in the app. Never sent to HQ."""
    call = case.get("call") or {}
    active = call.get("state") in ("ringing", "live") or (call.get("missed") and not call.get("returned"))
    if role != "desk" or case["kind"] != "call" or not active:
        return None
    return {"registered": bool(case.get("registered")), "name": case["name"], "mobile": case["mobile"], "gender": case["gender"], "age_band": case["age_band"],
            "home_address": case.get("home_address", ""), "has_photo": any(m["type"] == "face" for m in case["media"])}


def face_image(store, case_id):
    """The profile photo a registered caller sent with the call, as (mime, bytes), or None."""
    m = store.get("media", f"{case_id}-face")
    if not m or not m.get("data_url", "").startswith("data:"):
        return None
    head, _, body = m["data_url"].partition(",")
    try:
        return head[5:].split(";")[0] or "image/jpeg", base64.b64decode(body)
    except Exception:
        return None


def _summary(case, role, lang="en"):
    """A list row. Names and numbers appear only for the desk, and never for restricted kinds."""
    show_person = role == "desk" and not case["restricted"]
    call = case.get("call") or {}
    return {
        "id": case["id"], "ref": case["ref"], "kind": case["kind"], "channel": case["channel"],
        "status": case["status"], "priority": case["priority"], "sla": sla_level(case),
        "label": case_label(case, lang), "label_key": case["label_key"],
        "cluster": case["cluster"], "cluster_name": geo.name(case["cluster"]),
        "lat": case["lat"], "lon": case["lon"],
        "address": case["address"] if role == "desk" else "",
        "name": case["name"] if show_person else "",
        "has_contact": bool(case["mobile"]),
        "restricted": case["restricted"],
        "assigned_to": case["assigned_to"],
        "created_at": case["created_at"], "updated_at": case["updated_at"],
        "call_state": call.get("state", ""), "call_mode": call.get("mode", ""),
        "call_answered_at": call.get("answered_at"), "call_ended_at": call.get("ended_at"), "call_operator": call.get("operator", ""),
        "call_missed": bool(call.get("missed")), "call_missed_reason": call.get("missed_reason", ""),
        "call_callback": bool(call.get("returned")), "call_ring": (call.get("ring") or {}).get("state", ""),
        "call_transport": call.get("transport", ""),
        "caller": _caller_profile(case, role) if call else None,
        "referrals": len(case["referrals"]),
        "incomplete": case.get("incomplete", False), "missing": case.get("missing", []),
        "deployed": sum(1 for d in case.get("deployments", []) if d["status"] != "cleared"),
        "has_media": bool(case["media"]),
        "synthetic": case.get("synthetic", False),
    }


def _tip_summary(tip, role, lang="en"):
    return {
        "id": tip["id"], "ref": tip["ref"], "kind": "tip", "status": tip["status"],
        "label": tip_label(tip, lang), "label_key": tip["type_key"],
        "cluster": tip["cluster"], "cluster_name": geo.name(tip["cluster"]),
        "lat": tip["lat"], "lon": tip["lon"],
        "address": tip["address"] if role == "desk" else "",
        "created_at": tip["created_at"], "updated_at": tip["updated_at"],
        "referred_at": tip.get("referred_at"), "referred_by": tip.get("referred_by", ""), "verification": tip.get("verification"), "closed_by": tip.get("closed_by", ""),
        "outcome": tip.get("outcome", ""), "referrals": len(tip.get("referrals", [])), "has_media": bool(tip.get("media")),
        "incomplete": tip.get("incomplete", False), "missing": tip.get("missing", []),
        "restricted": True, "priority": "normal", "synthetic": tip.get("synthetic", False),
    }


# The four sections of the control room. Each officer signs in to ONE section and sees only that section's work.
SECTIONS = {
    "call_centre": {"label": "Call centre", "kinds": {"call"}, "tips": False},
    "desk": {"label": "Desk", "kinds": {"crime", "area"}, "tips": False},
    "tip_line": {"label": "Tip-off line", "kinds": set(), "tips": True},
    "gbv": {"label": "GBV desk", "kinds": {"gbv", "sos"}, "tips": False},
}


def section_options():
    return [{"key": k, "label": v["label"]} for k, v in SECTIONS.items()]


def call_window(case):
    """A call that every desk section must be able to see: ringing, live, or missed and not yet returned."""
    call = case.get("call")
    if not call:
        return False
    if call["state"] in ("ringing", "live"):
        return True
    return bool(call.get("missed")) and not call.get("returned") and now() - (call.get("ended_at") or 0) < MISSED_KEEP_S


def section_allows_case(section, case, officer=None):
    if section not in SECTIONS:
        return False
    if case["kind"] in SECTIONS[section]["kinds"]:
        return True
    call = case.get("call")
    if call and case["kind"] == "call":  # calling is shared by every section so that anyone free can answer
        if call_window(case):
            return True
        return bool(officer) and officer in (call.get("operator"), (call.get("callback") or {}).get("by"))
    return False


def section_allows_tips(section):
    return section in SECTIONS and SECTIONS[section]["tips"]


def feed(store, role, section=None, officer=None):
    expire_calls(store)
    cases = sorted(store.all("cases"), key=lambda c: -c["created_at"])
    tips = sorted(store.all("tips"), key=lambda t: -t["created_at"])
    refs = store.all("referrals")
    if role == "desk":
        cases = [c for c in cases if section_allows_case(section, c, officer)]
        tips = tips if section_allows_tips(section) else []
        ids = {c["id"] for c in cases} | {t["id"] for t in tips}
        refs = [r for r in refs if r["case_id"] in ids]
    out = {
        "version": store.snapshot_version(),
        "now": now(),
        "cases": [_summary(c, role) for c in cases],
        "tips": [_tip_summary(t, role) for t in tips],
    }
    if role == "desk":
        out["referrals"] = [
            {k: r[k] for k in ("id", "case_id", "case_ref", "type", "partner_name", "status", "urgency", "created_at", "sla_due_at")}
            for r in sorted(refs, key=lambda x: -x["created_at"])
        ]
    if role == "board":
        from . import insights  # local import: insights reads the helpers defined above

        out["stats"] = stats(store, cases, tips, refs)
        out["attention"] = attention(store, cases, tips, refs)
        out["clusters"] = cluster_performance(cases)
        out["insights"] = insights.build(cases, tips, refs)
        out["directions"] = [
            {k: r.get(k) for k in ("id", "case_id", "case_ref", "partner_name", "instruction", "status", "created_at", "due_at", "created_by")}
            for r in sorted(refs, key=lambda x: -x["created_at"]) if r.get("origin") == "board"
        ][:30]
    return out


def case_detail(store, case_id, officer, role="desk"):
    case = store.get("cases", case_id)
    if case is None:
        return None
    if case["restricted"]:
        audit(store, officer, role, "restricted.view", case_id)
    detail = _summary(case, "desk")
    detail.update({
        "name": case["name"], "mobile": case["mobile"], "note": case["note"],
        "timeline": case["timeline"], "transcript": case["transcript"],
        "call": case.get("call"), "media": case["media"],
        "occurred_at": case.get("occurred_at"),
        "safe_now": case.get("safe_now"), "wants": case.get("wants"), "know_person": case.get("know_person"),
        "contact_pref": case.get("contact_pref"), "friend": case.get("friend"),
        "gender": case.get("gender", "undisclosed"), "age_band": case.get("age_band", "undisclosed"), "language": case.get("language", "en"),
        "registered": case.get("registered", False), "home_address": case.get("home_address", ""), "friend_name": case.get("friend_name", ""),
        "call_options": ({"natures": [{"key": k, "label": v} for k, v in call_natures().items()], "outcomes": [{"key": k, "label": v} for k, v in CALL_OUTCOMES.items()]} if case.get("call") else None),
        "needs": case.get("needs", []), "needs_labels": {k: taxonomy.GBV_NEEDS[k] for k in taxonomy.GBV_NEEDS},
        "deployments": case.get("deployments", []),
        "suggested_station": geo.nearest_station(case["lat"], case["lon"]) if case["lat"] is not None else None,
        "referral_list": [store.get("referrals", rid) for rid in case["referrals"]],
    })
    detail["call"] = case.get("call")
    return detail


def tip_detail(store, tip_id, officer, role="desk"):
    tip = store.get("tips", tip_id)
    if tip is None:
        return None
    audit(store, officer, role, "restricted.view", tip_id)
    d = _tip_summary(tip, "desk")
    d.update({"note": tip["note"], "timeline": tip["timeline"], "media": tip.get("media", []), "outcome": tip.get("outcome", ""), "referral_list": [store.get("referrals", rid) for rid in tip.get("referrals", [])]})
    return d


# ----------------------------------------------------------------------------- board: what needs HQ
def attention(store, cases, tips, refs):
    """The list HQ acts on first. Most severe first."""
    t = now()
    items = []
    for x in tips:
        if x["status"] == "referred":
            items.append({"type": "verified_referral", "severity": 1, "id": x["id"], "ref": x["ref"], "kind": "tip", "label": tip_label(x),
                          "cluster_name": geo.name(x["cluster"]), "since": x.get("referred_at") or x["created_at"],
                          "reason": "Verified referral from the desk. Waiting for HQ action."})
        elif x["status"] == "new" and t - x["created_at"] > 3600:
            items.append({"type": "tip_waiting", "severity": 3, "id": x["id"], "ref": x["ref"], "kind": "tip", "label": tip_label(x),
                          "cluster_name": geo.name(x["cluster"]), "since": x["created_at"], "reason": "Tip received more than an hour ago and still unverified at the desk."})
    for c in cases:
        if c["status"] == "closed":
            continue
        call = c.get("call") or {}
        if call.get("missed") and not call.get("returned") and t - (call.get("ended_at") or t) > 300:
            items.append({"type": "missed_call", "severity": 2, "id": c["id"], "ref": c["ref"], "kind": c["kind"], "label": case_label(c),
                          "cluster_name": geo.name(c["cluster"]), "since": call["ended_at"], "reason": "Missed call not returned for over 5 minutes."})
        if call.get("state") == "ringing" and t - call["started_at"] > 30:
            items.append({"type": "unanswered_call", "severity": 1, "id": c["id"], "ref": c["ref"], "kind": c["kind"], "label": case_label(c),
                          "cluster_name": geo.name(c["cluster"]), "since": call["started_at"], "reason": "Call ringing for over 30 seconds."})
        elif c["priority"] in ("critical", "high") and c["status"] != "referred" and sla_level(c) == "red":  # referred files are tracked through their referral
            items.append({"type": "past_limit", "severity": 2, "id": c["id"], "ref": c["ref"], "kind": c["kind"], "label": case_label(c),
                          "cluster_name": geo.name(c["cluster"]), "since": c["created_at"], "reason": "Urgent file past its time limit."})
    for r in refs:
        if r["status"] == "completed":
            continue
        due = r.get("due_at") or r.get("sla_due_at")
        if r.get("origin") == "board" and due and t > due:
            items.append({"type": "direction_overdue", "severity": 2, "id": r["case_id"], "ref": r["case_ref"], "kind": "direction", "label": r["partner_name"],
                          "cluster_name": "", "since": due, "reason": "Your direction is overdue: " + (r.get("instruction") or "")[:80]})
        elif r.get("origin") != "board" and r["urgency"] == "urgent" and r["status"] == "sent" and r.get("sla_due_at") and t > r["sla_due_at"]:
            items.append({"type": "referral_unacknowledged", "severity": 2, "id": r["case_id"], "ref": r["case_ref"], "kind": "referral", "label": r["partner_name"],
                          "cluster_name": "", "since": r["sla_due_at"], "reason": "Urgent referral not acknowledged in time."})
    for c in cases:
        if c["status"] == "closed" or c["kind"] not in ("gbv", "sos"):
            continue
        for d in c.get("deployments", []):
            if d["status"] == "cleared":
                continue
            for need, v in d.get("needs", {}).items():
                label = taxonomy.GBV_NEEDS[need]
                if v["status"] == "unavailable":
                    req = next((r for r in refs if r["id"] == v.get("request_id")), None)
                    if req and req["status"] != "completed":
                        items.append({"type": "gbv_gap", "severity": 1, "id": c["id"], "ref": c["ref"], "kind": "gbv", "label": f"GBV: {label}",
                                      "cluster_name": geo.name(c["cluster"]), "since": v.get("at") or d["dispatched_at"],
                                      "reason": f"{d['station_name']} cannot supply it. Requested from {v.get('request_partner')} ({req['status']})."})
                elif v["status"] == "asked" and t - d["dispatched_at"] > 600:
                    items.append({"type": "gbv_unconfirmed", "severity": 1, "id": c["id"], "ref": c["ref"], "kind": "gbv", "label": f"GBV: {label}",
                                  "cluster_name": geo.name(c["cluster"]), "since": d["dispatched_at"], "reason": f"{d['station_name']} has not said whether it has this ready."})
    items.sort(key=lambda i: (i["severity"], i["since"]))
    return items[:40]


def cluster_performance(cases):
    """Per cluster: what the cluster commander answers for."""
    rows = {}
    for key in list(geo.CLUSTERS):
        mine = [c for c in cases if c["cluster"] == key]
        responded = [c for c in mine if c.get("first_action_at")]
        avg = round(sum(c["first_action_at"] - c["created_at"] for c in responded) / len(responded)) if responded else 0
        rows[key] = {
            "name": geo.name(key), "received": len(mine),
            "open": sum(1 for c in mine if c["status"] != "closed"),
            "closed_pct": round(100 * sum(1 for c in mine if c["status"] == "closed") / len(mine)) if mine else 0,
            "avg_first_response_s": avg,
            "past_limit": sum(1 for c in mine if c["status"] != "closed" and sla_level(c) == "red"),
        }
    return rows


# ----------------------------------------------------------------------------- board stats
SMALL = 5


def _band(n):
    return "0" if n == 0 else "<5" if n < SMALL else "5+"


def stats(store, cases, tips, refs):
    t = now()
    day = 86400
    opened = [c for c in cases if c["status"] != "closed"]
    urgent_open = [c for c in opened if c["priority"] in ("critical", "high")]
    responded = [c for c in cases if c.get("first_action_at")]
    avg_resp = round(sum(c["first_action_at"] - c["created_at"] for c in responded) / len(responded)) if responded else 0
    calls = [c for c in cases if c.get("call")]
    answered = [c for c in calls if c["call"].get("answered_at")]
    in30 = [c for c in answered if c["call"]["answered_at"] - c["call"]["started_at"] <= 30]
    series = []
    for i in range(13, -1, -1):
        lo, hi = t - (i + 1) * day, t - i * day
        series.append({
            "day": datetime.fromtimestamp(hi, timezone.utc).strftime("%d %b"),
            "opened": sum(1 for c in cases if lo <= c["created_at"] < hi),
            "closed": sum(1 for c in cases if c["closed_at"] and lo <= c["closed_at"] < hi),
        })
    by_cluster = {}
    for key in list(geo.CLUSTERS) + [geo.UNLOCATED]:
        general = [c for c in cases if c["cluster"] == key and not c["restricted"]]
        restricted = [c for c in cases if c["cluster"] == key and c["restricted"]] + [x for x in tips if x["cluster"] == key]
        by_cluster[key] = {
            "name": geo.name(key),
            "total": len(general),
            "open": sum(1 for c in general if c["status"] != "closed"),
            "restricted": _band(len(restricted)),
        }
    by_kind = {}
    for c in cases:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {
        "received": len(cases) + len(tips),
        "open": len(opened),
        "closed": len(cases) - len(opened),
        "urgent_open": len(urgent_open),
        "tips_total": len(tips),
        "tips_open": sum(1 for x in tips if x["status"] != "closed"),
        "gbv_total": sum(1 for c in cases if c["restricted"]),
        "calls_today": sum(1 for c in calls if c["created_at"] > t - day),
        "calls_answered_30s_pct": round(100 * len(in30) / len(calls)) if calls else 0,
        "avg_first_response_s": avg_resp,
        "referrals_out": len(refs),
        "referrals_done": sum(1 for r in refs if r["status"] == "completed"),
        "hq_referrals_waiting": sum(1 for x in tips if x["status"] == "referred"),
        "tips_by_status": {k: sum(1 for x in tips if x["status"] == k) for k in ("new", "verified", "referred", "acknowledged", "directed", "closed")},
        "by_kind": by_kind,
        "by_cluster": by_cluster,
        "series": series,
        "small_number_rule": f"Counts under {SMALL} for GBV and anonymous records are shown as a band, not a number.",
    }


# ----------------------------------------------------------------------------- action points and their own pages
import hashlib as _hashlib
import hmac as _hmac

from .config import Config as _Config

EXTERNAL_TYPES = {"gbv_tcc", "shelter", "health", "social_worker", "transport", "municipal"}


def action_points(store):
    """Everywhere a file can be dropped for action. Stations take deployments; units and partners take referrals."""
    out = []
    for key, (name, cluster, lat, lon) in geo.STATIONS.items():
        out.append({"id": "st-" + key, "name": name + " SAPS", "group": "Police stations", "type": "station", "cluster": geo.name(cluster), "station": key})
    for p in sorted(store.all("partners"), key=lambda x: (x["type"], x["name"])):
        group = "SAPS units" if p["type"] in taxonomy.SAPS_UNIT_TYPES else "Partners outside SAPS"
        out.append({"id": p["id"], "name": p["name"], "group": group, "type": p["type"], "cluster": p.get("area", "")})
    return out


def unit_token(ap_id):
    """A private link token per action point. No account is needed; whoever holds the link sees that point's tasks only."""
    return _hmac.new(_Config.SECRET_KEY.encode(), ("unit:" + ap_id).encode(), _hashlib.sha256).hexdigest()[:20]


def unit_token_ok(ap_id, token):
    return bool(token) and _hmac.compare_digest(unit_token(ap_id), str(token))


def _find_point(store, ap_id):
    for ap in action_points(store):
        if ap["id"] == ap_id:
            return ap
    return None


def unit_tasks(store, ap_id):
    ap = _find_point(store, ap_id)
    if ap is None:
        return None
    tasks = []
    if ap["type"] == "station":
        for c in store.all("cases"):
            for d in c.get("deployments", []):
                if d["station"] == ap["station"]:
                    show_person = not c["restricted"]
                    tasks.append({
                        "kind": "deployment", "id": d["id"], "case_id": c["id"], "case_ref": c["ref"], "label": case_label(c), "cluster": geo.name(c["cluster"]),
                        "address": c["address"], "lat": c["lat"], "lon": c["lon"], "since": d["dispatched_at"], "status": d["status"], "unit": d["unit"],
                        "instruction": d.get("instruction", ""), "detail": c["note"], "priority": c["priority"],
                        "name": c["name"] if show_person else "", "mobile": c["mobile"] if show_person else "", "closed": c["status"] == "closed",
                        "registered": c.get("registered", False), "home_address": c.get("home_address", "") if show_person else "",
                        "folder": _folder(c),
                        "needs": [{"key": k, "label": taxonomy.GBV_NEEDS[k], "status": v["status"], "note": v.get("note", ""), "request_partner": v.get("request_partner", "")} for k, v in d.get("needs", {}).items()],
                    })
    else:
        for item in partner_view(store, ap_id):
            raw = store.get("referrals", item["id"]) or {}
            rcase = store.get("cases", raw.get("case_id", ""))
            shares = bool(rcase)  # demo: the whole folder goes with the file to every action point
            tasks.append({
                "folder": _folder(rcase) if shares else None,
                "kind": "referral", "id": item["id"], "case_id": raw.get("case_id", ""), "case_ref": item["case_ref"], "label": item["label"], "cluster": item["cluster"],
                "address": item["address"], "lat": item["lat"], "lon": item["lon"], "since": item["created_at"], "status": item["status"], "unit": "",
                "instruction": item.get("instruction") or item["note"], "detail": item.get("detail", ""), "priority": "high" if item["urgency"] == "urgent" else "normal",
                "name": item.get("name", ""), "mobile": item.get("mobile", ""), "due_at": item.get("due_at"), "origin": item.get("origin", "desk"), "closed": item["status"] == "completed",
            })
    tasks.sort(key=lambda t: (t["closed"], -t["since"]))
    return {"point": ap, "tasks": tasks}


def unit_update(store, ap_id, kind, task_id, status, note, actor):
    ap = _find_point(store, ap_id)
    if ap is None:
        raise Invalid("Unknown action point.")
    if kind == "deployment":
        owner = None
        for c in store.all("cases"):
            if any(d["id"] == task_id and d["station"] == ap.get("station") for d in c.get("deployments", [])):
                owner = c["id"]
        if owner is None:
            raise Invalid("Task not found.")
        update_deployment(store, owner, task_id, actor, status)
        if note:
            store.patch("cases", owner, lambda c: event(c, actor, "Note from " + ap["name"] + ": " + clean(note, 200), "note"))
        return True
    ref = store.get("referrals", task_id)
    if ref is None or ref["partner_id"] != ap_id:
        raise Invalid("Task not found.")
    update_referral(store, task_id, actor, status)
    if note:
        coll = "cases" if store.get("cases", ref["case_id"]) else "tips"
        store.patch(coll, ref["case_id"], lambda c: event(c, actor, "Note from " + ap["name"] + ": " + clean(note, 200), "note"))
    return True


def ap_load(store):
    """Open tasks per action point, so the desk can see where the work is sitting."""
    load = {}
    for c in store.all("cases"):
        if c["status"] == "closed":
            continue
        for d in c.get("deployments", []):
            if d["status"] != "cleared":
                row = load.setdefault("st-" + d["station"], {"open": 0, "urgent": 0})
                row["open"] += 1
                row["urgent"] += 1 if c["priority"] in ("critical", "high") else 0
    for r in store.all("referrals"):
        if r["status"] != "completed":
            row = load.setdefault(r["partner_id"], {"open": 0, "urgent": 0})
            row["open"] += 1
            row["urgent"] += 1 if r["urgency"] == "urgent" else 0
    return load


# ----------------------------------------------------------------------------- shifts: who is on, with a photo in and out
def start_shift(store, section, officer_id, photo):
    sid = f"S{store.next_seq('shift'):05d}"
    t = now()
    store.put("shifts", {
        "id": sid, "section": section, "section_label": SECTIONS[section]["label"], "officer_id": officer_id,
        "in_at": t, "out_at": None, "has_in_photo": bool(photo), "in_photo_missing": not photo, "has_out_photo": False, "out_photo_missing": False,
    })
    if photo:
        store.put("media", {"id": f"{sid}-in", "case_id": sid, "type": "shift_photo", "data_url": _check_image(photo, MAX_FACE_BYTES)})
    return sid


def end_shift(store, shift_id, photo):
    def fn(sh):
        if sh["out_at"] is None:
            sh["out_at"] = now()
            sh["has_out_photo"] = bool(photo)
            sh["out_photo_missing"] = not photo  # signed out without a photo: flagged for HQ
    sh = store.patch("shifts", shift_id, fn)
    if sh and photo:
        try:
            store.put("media", {"id": f"{shift_id}-out", "case_id": shift_id, "type": "shift_photo", "data_url": _check_image(photo, MAX_FACE_BYTES)})
        except Invalid:
            store.patch("shifts", shift_id, lambda x: x.update(has_out_photo=False, out_photo_missing=True))
    return sh


def list_shifts(store, q="", section="", since="", page=1, limit=25):
    """Search and page the staff sign-in records on the server, so thousands of rows never reach the browser at once."""
    rows = sorted(store.all("shifts"), key=lambda x: -x["in_at"])
    counts = {"all": len(rows)}
    for r in rows:
        counts[r["section"]] = counts.get(r["section"], 0) + 1
    if section and section != "all":
        rows = [r for r in rows if r["section"] == section]
    if since in ("today", "7d", "30d"):
        cutoff = now() - {"today": 86400, "7d": 7 * 86400, "30d": 30 * 86400}[since]
        rows = [r for r in rows if r["in_at"] >= cutoff]
    q = clean(q, 60).lower()
    if q:
        def hay(r):
            when = datetime.fromtimestamp(r["in_at"], timezone.utc).strftime("%Y-%m-%d %d %b %B %A").lower()
            flags = " no photo" if (r.get("in_photo_missing") or r.get("out_photo_missing")) else ""
            flags += " on shift" if not r["out_at"] else ""
            return f"{r['officer_id']} {r['section_label']} {when}{flags}".lower()
        rows = [r for r in rows if q == r["id"].lower() or all(tok in hay(r) for tok in q.split())]
    limit = max(5, min(int(limit or 25), 100))
    pages = max(1, -(-len(rows) // limit))
    page = max(1, min(int(page or 1), pages))
    return {"shifts": rows[(page - 1) * limit: page * limit], "total": len(rows), "page": page, "pages": pages, "counts": counts}


# ----------------------------------------------------------------------------- call record (the file an officer or HQ can open and keep)
def citizen_recording_chunk(store, case_id, ctoken, chunk):
    """The caller's own phone records the call and sends it in pieces. Saved onto the file automatically."""
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")
    size = add_recording_chunk(store, case_id, "Caller's phone", chunk, source="caller")
    store.patch("cases", case_id, lambda c: c["call"].update(recording=True))
    return size


def call_record_text(store, case_id, officer):
    """A plain-text file of the call: who, when, how long, the whole chat or captions, and what was saved with it."""
    case = store.get("cases", case_id)
    if case is None or not case.get("call"):
        return None
    call = case["call"]
    fmt = lambda ts: datetime.fromtimestamp(ts, timezone.utc).astimezone(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S") if ts else "n/a"
    secs = call.get("duration")
    if secs is None and call.get("answered_at") and call.get("ended_at"):
        secs = int(call["ended_at"] - call["answered_at"])
    lines = [
        "SAPS KZN DEMO. CALL RECORD (synthetic demonstration data; not a real police record)",
        "=" * 72,
        f"Reference : {case['ref']}",
        f"Type      : {'Video call' if call.get('mode') == 'video' else 'Voice call'}",
        f"Started   : {fmt(call.get('started_at'))}",
        f"Answered  : {fmt(call.get('answered_at'))} by {call.get('operator') or 'n/a'}",
        f"Ended     : {fmt(call.get('ended_at'))}",
        f"Duration  : {f'{secs // 60}:{secs % 60:02d}' if secs is not None else 'n/a'}",
        f"Channel   : {call.get('transport', 'text')}",
        f"Recording : {'saved on the file' if any(m['type'] == 'recording' for m in case['media']) else 'none'}",
        "-" * 72,
        "CHAT AND CAPTIONS",
    ]
    if not case["transcript"]:
        lines.append("(nothing was said or typed)")
    for l in case["transcript"]:
        who = "Caller" if l["who"] == "citizen" else "Officer"
        kind = "caption" if l.get("src") == "caption" else "typed"
        lines.append(f"[{fmt(l['at'])[11:]}] {who} ({kind}): {l['text']}")
    lines += ["-" * 72, "FILE TIMELINE"]
    for e in case["timeline"]:
        lines.append(f"[{fmt(e['at'])}] {e['actor']}: {e['text']}")
    audit(store, officer, "desk", "call.record.download", case_id)
    return "\n".join(lines) + "\n"


# ----------------------------------------------------------------------------- the folder that goes with a file
def _folder(case):
    """Call record, recording and evidence. Never the profile photo."""
    call = case.get("call")
    out = {"call": None, "evidence": []}
    if call:
        out["call"] = {
            "mode": call.get("mode"), "state": call.get("state"), "operator": call.get("operator", ""), "duration": call.get("duration"),
            "started_at": call.get("started_at"), "answered_at": call.get("answered_at"),
            "lines": [{"at": l["at"], "who": l["who"], "text": l["text"], "src": l.get("src", "typed")} for l in case["transcript"]],
        }
    for m in case.get("media", []):
        if m["type"] in ("recording", "video", "audio", "photo"):
            out["evidence"].append({"id": m["id"], "type": m["type"], "size": m.get("size"), "source": m.get("source", "")})
    return out if (out["call"] or out["evidence"]) else None


def unit_media(store, ap_id, media_id):
    """A station, unit or partner may open a file's media only if that file is on its page."""
    data = unit_tasks(store, ap_id)
    if data is None:
        return None
    meta = store.get("media", media_id)
    if meta is None:
        return None
    allowed = {t["case_id"] for t in data["tasks"] if t.get("folder")}
    if meta["case_id"] not in allowed or meta["type"] == "face":
        return None
    audit(store, data["point"]["name"], "unit", "folder.media.view", meta["case_id"], meta["type"])
    if "data_url" in meta:
        return ("image", meta["data_url"])
    return ("blob", (meta["mime"], blobs.get(meta["key"], meta["storage"])))


# ----------------------------------------------------------------------------- GBV: the station says what it has
def _fallback_partner(store, need, cluster):
    target = taxonomy.GBV_FALLBACK.get(need)
    if target == "cluster":
        target = f"unit-cluster-{cluster}" if store.get("partners", f"unit-cluster-{cluster}") else "unit-detective"
    return store.get("partners", target) or store.get("partners", "unit-detective")


def unit_need_answer(store, ap_id, task_id, need, answer, note, actor):
    ap = _find_point(store, ap_id)
    if ap is None or ap["type"] != "station":
        raise Invalid("Unknown action point.")
    if need not in taxonomy.GBV_NEEDS or answer not in ("available", "unavailable"):
        raise Invalid("Choose have it or do not have it.")
    owner = None
    for c in store.all("cases"):
        if any(d["id"] == task_id and d["station"] == ap["station"] and need in d.get("needs", {}) for d in c.get("deployments", [])):
            owner = c
    if owner is None:
        raise Invalid("Task not found.")
    note = clean(note, 200)
    partner = None
    request_id = ""
    if answer == "unavailable":
        partner = _fallback_partner(store, need, owner["cluster"])
        request_id = f"R{store.next_seq('referral'):05d}"
        label = taxonomy.GBV_NEEDS[need]
        instruction = f"{ap['name']} does not have: {label}. Please supply it, or arrange it, for {owner['ref']}."
        store.put("referrals", {
            "id": request_id, "case_id": owner["id"], "case_ref": owner["ref"], "type": partner["type"], "partner_id": partner["id"],
            "partner_name": partner["name"], "status": "sent", "urgency": "urgent", "consent_to_share": True, "note": instruction, "origin": "request",
            "instruction": instruction, "created_by": ap["name"], "created_at": now(), "updated_at": now(), "due_at": now() + 30 * 60, "sla_due_at": now() + 30 * 60, "synthetic": False,
        })

    def fn(c):
        for d in c["deployments"]:
            if d["id"] == task_id:
                d["needs"][need].update({"status": answer, "note": note, "at": now(), "request_id": request_id, "request_partner": partner["name"] if partner else ""})
        if request_id:
            c.setdefault("referrals", []).append(request_id)
            event(c, ap["name"], f"Cannot supply: {taxonomy.GBV_NEEDS[need]}. Requested from {partner['name']}." + (" " + note if note else ""), "gbv")
        else:
            event(c, ap["name"], f"Has ready: {taxonomy.GBV_NEEDS[need]}." + (" " + note if note else ""), "gbv")

    store.patch("cases", owner["id"], fn)
    audit(store, ap["name"], "unit", "gbv.need." + answer, owner["id"], need)
    return True


# ----------------------------------------------------------------------------- the end-of-day call log (HQ)
CALL_OUTCOMES = {
    "advice": "Advice given", "dispatched": "Station or unit dispatched", "referred": "Referred out of SAPS",
    "report": "Opened a file for follow-up", "no_action": "No action needed", "hoax": "Hoax or test call",
}


def call_natures():
    out = {k: v[0] for k, v in taxonomy.CRIME_TYPES.items() if not v[3]}
    out.update({"enquiry": "Enquiry or advice", "hoax": "Hoax or test call", "other": "Other"})
    return out


def _day_range(day):
    """Local (SAST) day boundaries for the log."""
    t = datetime.fromtimestamp(now(), SAST)
    start = t.replace(hour=0, minute=0, second=0, microsecond=0)
    if day == "yesterday":
        return (start - timedelta(days=1)).timestamp(), start.timestamp(), "Yesterday"
    if day == "7d":
        return (start - timedelta(days=6)).timestamp(), (start + timedelta(days=1)).timestamp(), "Last 7 days"
    return start.timestamp(), (start + timedelta(days=1)).timestamp(), "Today"


def call_log(store, day="today", q=""):
    """Every call in the period: file number, time, duration, operator, nature, action taken. No names or numbers."""
    expire_calls(store)
    lo, hi, label = _day_range(day)
    natures = call_natures()
    rows = []
    for c in store.all("cases"):
        call = c.get("call")
        if not call or not (lo <= call["started_at"] < hi):
            continue
        answered = bool(call.get("answered_at"))
        parts = []
        if call.get("outcome"):
            parts.append(CALL_OUTCOMES[call["outcome"]])
        stations = sorted({d["station_name"] for d in c.get("deployments", [])})
        if stations:
            parts.append("Unit from " + ", ".join(stations))
        for rid in c.get("referrals", []):
            r = store.get("referrals", rid)
            if r:
                parts.append("Referred to " + r["partner_name"])
        if call.get("action_text"):
            parts.append(call["action_text"])
        if call.get("missed"):
            cb = call.get("callback")
            parts.append(("Call-back " + {"phone": "by phone", "app": "message sent to the app", "ring_voice": "rang the app", "ring_video": "rang the app (video)"}.get(cb["method"], "") + " by " + cb["by"]) if cb else "Not yet returned")
        result = ("Dropped" if call.get("missed_reason") == "dropped" else "Answered") if answered else "Missed"
        rows.append({
            "id": c["id"], "ref": c["ref"], "started_at": call["started_at"], "answered_at": call.get("answered_at"),
            "duration": call.get("duration") if answered else None, "operator": call.get("operator") or "",
            "nature": natures.get(call.get("nature"), "") , "action": "; ".join(parts), "result": result, "mode": call.get("mode", "voice"),
            "returned": bool(call.get("returned")), "cluster_name": geo.name(c["cluster"]),
            "wrap_missing": answered and not call.get("nature"),
        })
    q = clean(q, 60).lower()
    if q:
        rows = [r for r in rows if q in " ".join(str(r[k]) for k in ("ref", "operator", "nature", "action", "result", "cluster_name")).lower()]
    rows.sort(key=lambda r: -r["started_at"])
    answered = [r for r in rows if r["result"] != "Missed"]
    durs = [r["duration"] for r in answered if r["duration"]]
    in30 = [r for r in answered if r["answered_at"] and r["answered_at"] - r["started_at"] <= 30]
    summary = {
        "calls": len(rows), "answered": len(answered), "missed": sum(1 for r in rows if r["result"] == "Missed"), "dropped": sum(1 for r in rows if r["result"] == "Dropped"),
        "not_returned": sum(1 for r in rows if r["result"] != "Answered" and not r["returned"]),
        "avg_duration": round(sum(durs) / len(durs)) if durs else 0,
        "answered_30s_pct": round(100 * len(in30) / len(rows)) if rows else 0, "wrap_missing": sum(1 for r in rows if r["wrap_missing"]),
    }
    return {"day": day, "label": label, "from": lo, "to": hi, "summary": summary, "rows": rows}


def call_log_csv(log):
    import csv
    import io

    f = lambda ts: datetime.fromtimestamp(ts, SAST).strftime("%Y-%m-%d %H:%M:%S") if ts else ""  # noqa: E731
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["File / case number", "Date and time", "Duration (seconds)", "Desk operator", "Nature of call", "Action taken", "Result", "Area"])
    for r in log["rows"]:
        w.writerow([r["ref"], f(r["started_at"]), r["duration"] if r["duration"] is not None else "", r["operator"], r["nature"] or "Not recorded", r["action"] or "None recorded", r["result"], r["cluster_name"]])
    return out.getvalue()
