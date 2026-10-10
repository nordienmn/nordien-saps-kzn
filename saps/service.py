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
import re
import secrets
import time
from datetime import datetime, timezone

from . import geo, taxonomy
from .store import now

YEAR = lambda ts=None: datetime.fromtimestamp(ts or now(), timezone.utc).year  # noqa: E731

MAX_NOTE = 2000
MAX_TRANSCRIPT_LINES = 300
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
def _save_media(store, case, photos, face):
    media = []
    for i, data_url in enumerate(photos[:MAX_PHOTOS]):
        mid = f"{case['id']}-p{i + 1}"
        store.put("media", {"id": mid, "case_id": case["id"], "type": "photo", "data_url": _check_image(data_url, MAX_PHOTO_BYTES)})
        media.append({"id": mid, "type": "photo"})
    if face:
        mid = f"{case['id']}-face"
        store.put("media", {"id": mid, "case_id": case["id"], "type": "face", "data_url": _check_image(face, MAX_FACE_BYTES)})
        media.append({"id": mid, "type": "face"})
    return media


def create_case(store, payload, channel="app", synthetic=False, created_at=None):
    """Create a crime, gbv, sos, area or call case. Returns the stored case (full record)."""
    kind = clean(payload.get("kind"), 12)
    if kind not in ("crime", "gbv", "sos", "area", "call"):
        raise Invalid("Unknown report type.", "kind")

    lat, lon, address = clean_point(payload)
    cluster = geo.nearest_cluster(lat, lon) if lat is not None else geo.UNLOCATED
    if cluster == geo.UNLOCATED and payload.get("cluster") in geo.CLUSTERS and synthetic:
        cluster = payload["cluster"]  # only seed data may name a cluster directly

    name = clean(payload.get("name"), 80)
    mobile = clean_mobile(payload.get("mobile"))
    note = clean(payload.get("note"), MAX_NOTE)
    label_key = "other"
    priority = "normal"
    extra = {}

    if kind == "crime":
        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.CRIME_TYPES:
            raise Invalid("Choose the type of crime.", "type")
        if lat is None and not address:
            raise Invalid("Add a place, or use your current location.", "place")
        priority = taxonomy.CRIME_TYPES[label_key][2]
        if taxonomy.CRIME_TYPES[label_key][3]:
            kind = "gbv"  # a domestic-violence or sexual-offence report goes to the GBV door
        occurred = payload.get("occurred_at")
        if occurred not in (None, ""):
            try:
                occurred = float(occurred) / 1000.0
            except (TypeError, ValueError):
                raise Invalid("That time does not look right.", "time")
            if not now() - 30 * 86400 <= occurred <= now() + 3600:
                raise Invalid("That time does not look right.", "time")
            extra["occurred_at"] = occurred
    elif kind == "gbv":
        label_key = "gbv_request"
        safe = clean(payload.get("safe_now"), 8)
        if safe not in ("yes", "no", "unsure"):
            raise Invalid("Please tell us if you are safe right now.", "safe_now")
        wants = [w for w in (payload.get("wants") or []) if w in ("social_worker", "hospital", "shelter", "transport", "police")]
        contact_pref = clean(payload.get("contact_pref"), 8)
        if contact_pref not in ("call", "sms", "none"):
            contact_pref = "none"
        if contact_pref in ("call", "sms") and not mobile:
            raise Invalid("Add a number we may use, or choose 'Do not contact me'.", "mobile")
        priority = "critical" if safe == "no" else "high"
        extra.update({
            "safe_now": safe,
            "wants": wants,
            "know_person": clean(payload.get("know_person"), 6) if payload.get("know_person") in ("yes", "no", "skip") else "skip",
            "contact_pref": contact_pref,
        })
    elif kind == "sos":
        label_key = "weather_sos"
        priority = "critical"
        extra["friend"] = clean(payload.get("friend"), 80)
    elif kind == "area":
        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.AREA_TYPES:
            raise Invalid("Choose what is unsafe.", "type")
        if lat is None and not address:
            raise Invalid("Add a place, or use your current location.", "place")
        priority = "low"
        name = mobile = ""  # unsafe-area reports never carry a person
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
    if not synthetic:
        case["media"] = _save_media(store, case, payload.get("photos") or [], payload.get("face") or "")
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
    key = clean(payload.get("type"), 40)
    if key not in taxonomy.TIP_TYPES:
        raise Invalid("Choose what you are reporting.", "type")
    lat, lon, address = clean_point(payload)
    if lat is None and not address:
        raise Invalid("Add a place, or use your current location.", "place")
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
        "status": "new",  # new | escalated | acknowledged | closed
        "code_hash": hashlib.sha256(code.encode()).hexdigest(),
        "timeline": [{"at": ts, "actor": "system", "text": "Tip received. Not a case. No identity stored.", "kind": "system"}],
        "created_at": ts,
        "updated_at": ts,
        "escalated_at": None,
        "escalated_by": "",
        "synthetic": synthetic,
        "restricted": True,
    }
    store.put("tips", tip)
    return tip, code


def tip_label(tip, lang="en"):
    row = taxonomy.TIP_TYPES.get(tip["type_key"])
    return (row[1] if lang == "zu" else row[0]) if row else tip["type_key"]


def escalate_tip(store, tip_id, officer):
    def fn(tip):
        if tip["status"] in ("new", "acknowledged"):
            tip["status"] = "escalated"
            tip["escalated_at"] = now()
            tip["escalated_by"] = officer
            event(tip, officer, "Escalated to senior leadership.", "escalate")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, officer, "desk", "tip.escalate", tip_id)
    return tip


def acknowledge_tip(store, tip_id, actor):
    def fn(tip):
        if tip["status"] == "escalated":
            tip["status"] = "acknowledged"
            event(tip, actor, "Acknowledged by senior leadership.", "ack")

    tip = store.patch("tips", tip_id, fn)
    if tip is None:
        raise Invalid("Tip not found.")
    audit(store, actor, "board", "tip.acknowledge", tip_id)
    return tip


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
        c["call"] = {"state": "ringing", "mode": mode, "transport": "text", "room": "", "started_at": now(), "answered_at": None, "ended_at": None, "operator": ""}
        event(c, "citizen", f"{mode.capitalize()} call started. Ringing at the control room.", "call")

    case = store.patch("cases", case["id"], fn)
    return case, ctoken


def _ctoken_ok(case, ctoken):
    return bool(case) and bool(ctoken) and hmac.compare_digest(case.get("_ctoken", ""), str(ctoken))


def citizen_call_state(store, case_id, ctoken):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken) or not case.get("call"):
        raise Invalid("Call not found.")
    call = case["call"]
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
        "lines": case["transcript"][-60:],
        "ref": case["ref"],
    }


def answer_call(store, case_id, officer, transport="text", room=""):
    def fn(c):
        call = c.get("call")
        if not call or call["state"] != "ringing":
            raise Invalid("That call is no longer ringing.")
        call.update({"state": "live", "answered_at": now(), "operator": officer, "transport": transport, "room": room})
        c["assigned_to"] = officer
        c["status"] = "in_progress"
        c["first_action_at"] = c["first_action_at"] or now()
        event(c, officer, "Call answered.", "call")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Call not found.")
    audit(store, officer, "desk", "call.answer", case_id)
    return case


def end_call(store, case_id, actor, who):
    def fn(c):
        call = c.get("call")
        if not call or call["state"] == "ended":
            return
        answered = call["state"] == "live"
        call["state"] = "ended"
        call["ended_at"] = now()
        secs = int(call["ended_at"] - call["answered_at"]) if answered and call.get("answered_at") else 0
        call["duration"] = secs
        if answered:
            event(c, actor, f"Call ended by {who}. Duration {secs // 60}:{secs % 60:02d}.", "call")
        else:
            c["status"] = "new"
            event(c, actor, f"Call ended by {who} before it was answered. Call back.", "call")

    case = store.patch("cases", case_id, fn)
    if case is None:
        raise Invalid("Call not found.")
    return case


def add_line(store, case_id, who, text, src="typed"):
    text = clean(text, 500)
    if not text:
        raise Invalid("Empty message.")

    def fn(c):
        if len(c["transcript"]) >= MAX_TRANSCRIPT_LINES:
            raise Invalid("Transcript is full.")
        c["transcript"].append({"at": now(), "who": who, "text": text, "src": src})
        c["updated_at"] = now()

    return store.patch("cases", case_id, fn)


def citizen_add_line(store, case_id, ctoken, text, src="typed"):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")
    return add_line(store, case_id, "citizen", text, "caption" if src == "caption" else "typed")


def citizen_end_call(store, case_id, ctoken):
    case = store.get("cases", case_id)
    if not _ctoken_ok(case, ctoken):
        raise Invalid("Call not found.")
    return end_call(store, case_id, "citizen", "the caller")


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
        ("ride-demo", "transport", "Victim-support transport (demo)", "Any"),
        ("mun-ethekwini-lights", "municipal", "eThekwini Municipality: Roads and street lighting (demo)", "eThekwini"),
        ("mun-ethekwini-parks", "municipal", "eThekwini Municipality: Parks and public safety (demo)", "eThekwini"),
        ("mun-msunduzi", "municipal", "Msunduzi Municipality: Public works (demo)", "Msunduzi"),
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
    consent = bool(payload.get("consent_to_share"))
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


def update_referral(store, referral_id, actor, status):
    if status not in ("acknowledged", "completed"):
        raise Invalid("Unknown status.")
    ref = store.patch("referrals", referral_id, lambda r: r.update({"status": status, "updated_at": now()}))
    if ref is None:
        raise Invalid("Referral not found.")

    def fn(c):
        event(c, actor, f"{ref['partner_name']}: {status}.", "referral")
        if status == "completed" and c["kind"] == "area":
            c["status"] = "closed"
            c["closed_at"] = now()

    store.patch("cases", ref["case_id"], fn)
    audit(store, actor, "desk", f"referral.{status}", ref["case_id"])
    return ref


def partner_view(store, partner_id):
    """What a receiving partner may see: no contact details unless the citizen agreed."""
    out = []
    for r in sorted(store.all("referrals"), key=lambda x: -x["created_at"]):
        if r["partner_id"] != partner_id:
            continue
        case = store.get("cases", r["case_id"]) or {}
        item = {
            "id": r["id"], "case_ref": r["case_ref"], "status": r["status"], "urgency": r["urgency"],
            "created_at": r["created_at"], "note": r["note"],
            "cluster": geo.name(case.get("cluster", geo.UNLOCATED)),
            "label": case_label(case) if case else "",
            "lat": case.get("lat"), "lon": case.get("lon"), "address": case.get("address", ""),
        }
        if r["consent_to_share"] and case:
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
        "referrals": len(case["referrals"]),
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
        "escalated_at": tip["escalated_at"], "escalated_by": tip["escalated_by"],
        "restricted": True, "priority": "normal", "synthetic": tip.get("synthetic", False),
    }


def feed(store, role):
    cases = sorted(store.all("cases"), key=lambda c: -c["created_at"])
    tips = sorted(store.all("tips"), key=lambda t: -t["created_at"])
    refs = store.all("referrals")
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
        out["stats"] = stats(store, cases, tips, refs)
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
    d.update({"note": tip["note"], "timeline": tip["timeline"]})
    return d


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
        "escalated_unacknowledged": sum(1 for x in tips if x["status"] == "escalated"),
        "by_kind": by_kind,
        "by_cluster": by_cluster,
        "series": series,
        "small_number_rule": f"Counts under {SMALL} for GBV and anonymous records are shown as a band, not a number.",
    }
