"""WhatsApp bot (Twilio). Same cases, same desk, a different front door.

It follows the Municipal bot's pattern: Twilio signature check, ProxyFix so the public URL
matches, and an in-memory conversation state that is never written to the database.

Honest limits, said inside the chat:
- WhatsApp itself sees the sender's number, so a tip sent here is not anonymous. The tip record
  stores no number, but the message does pass through WhatsApp and Twilio.
- This is a demo. It never calls or dispatches anyone.
isiZulu text is a first draft and needs a native-speaker check.
"""
import threading
import time

from flask import Blueprint, Response, abort, current_app, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from . import service, taxonomy
from .config import Config

bp = Blueprint("whatsapp", __name__)

SESSIONS = {}
LOCK = threading.Lock()
TTL = 30 * 60

CRIME_MENU = ["house_break_in", "vehicle_theft", "armed_robbery", "assault", "theft", "hijacking", "drugs", "suspicious_activity"]
AREA_MENU = ["broken_light", "dark_street", "open_ditch", "overgrown_veld", "unsafe_building", "park", "illegal_dumping"]
TIP_MENU = ["suspicious_vehicle", "drugs", "illegal_firearm", "stolen_goods", "planned_crime", "other"]
WANTS = {"1": "social_worker", "2": "hospital", "3": "shelter", "4": "transport"}

S = {
    "en": {
        "hello": "SAPS KZN demo (not a real police service).\nReply 1 for English or 2 for isiZulu.",
        "consent": "Your messages are received by SAPS KZN, through WhatsApp and Twilio. In a real emergency call 10111.\nReply YES to continue, or EXIT.",
        "menu": "How can we help?\n1 Report a crime\n2 GBV help\n3 Anonymous tip\n4 Unsafe area\n5 Emergency\nReply EXIT at any time to clear this chat from our side.",
        "crime_type": "What happened? Reply with a number:\n{opts}",
        "place": "Where? Share your location with the attachment button, or type the place. Reply SKIP if you cannot.",
        "place_req": "Where? Share your location with the attachment button, or type the place.",
        "desc": "Tell us a little about it, or reply SKIP.",
        "done_case": "Received. Your reference is {ref}. A member of SAPS KZN will review it. Keep this number. (Demo.)",
        "gbv_safe": "You are believed. Are you safe right now?\n1 Yes\n2 No\n3 Not sure",
        "gbv_wants": "What help would you like? Reply with numbers, for example 1,2:\n1 Social worker\n2 Hospital or clinic\n3 Shelter\n4 Transport\nOr reply 0 for none.",
        "gbv_contact": "May we contact you on this WhatsApp number?\n1 Yes\n2 No, do not contact me",
        "gbv_done": "Received. Your reference is {ref}. You are not alone. If you are in danger now, call 10111. The GBV Command Centre is 0800 428 428, day and night. (Demo.)",
        "tip_note": "WhatsApp is not anonymous. Your number is seen by WhatsApp and Twilio. We store no name and no number with the tip. For full privacy use the app.\nWhat are you reporting?\n{opts}",
        "tip_done": "Tip received. Not a case. Your code is {code}. Quote it if you contact us again. (Demo.)",
        "area_type": "What is unsafe? Reply with a number:\n{opts}",
        "area_done": "Received. Reference {ref}. This is not a crime report. It can be shared with the municipality. (Demo.)",
        "emerg": "This demo does not call or dispatch anyone. In a real emergency call 10111.\nReply 1 to send a demo alert, with your location, to the SAPS KZN desk.",
        "emerg_done": "Alert sent to the demo desk. Reference {ref}. In a real emergency call 10111.",
        "bad": "Sorry, I did not understand. Reply with one of the numbers, or MENU.",
        "cleared": "Cleared on our side. Please also delete this chat on your phone.",
        "fail": "Sorry, we could not save that. Please try again.",
    },
    "zu": {
        "hello": "I-SAPS KZN yesilingo (hhayi isevisi yamaphoyisa yangempela).\nPhendula ngo-1 ngesiNgisi noma ngo-2 ngesiZulu.",
        "consent": "Imiyalezo yakho itholwa yi-SAPS KZN, nge-WhatsApp ne-Twilio. Esimeni esiphuthumayo shayela u-10111.\nPhendula ngo-YES ukuqhubeka, noma EXIT.",
        "menu": "Singakusiza kanjani?\n1 Bika ubugebengu\n2 Usizo lwe-GBV\n3 Ithiphu elingaziwa\n4 Indawo engaphephile\n5 Isimo esiphuthumayo\nPhendula ngo-EXIT noma nini ukususa le nkulumo ohlangothini lwethu.",
        "crime_type": "Kwenzekeni? Phendula ngenombolo:\n{opts}",
        "place": "Kuphi? Yabelana ngendawo yakho, noma ubhale indawo. Phendula ngo-SKIP uma ungakwazi.",
        "place_req": "Kuphi? Yabelana ngendawo yakho, noma ubhale indawo.",
        "desc": "Sitshele kancane, noma uphendule ngo-SKIP.",
        "done_case": "Kutholakele. Inombolo yakho yereferensi ngu-{ref}. Ilungu le-SAPS KZN lizokubheka. Gcina le nombolo. (Isilingo.)",
        "gbv_safe": "Uyakholelwa. Uphephile manje?\n1 Yebo\n2 Cha\n3 Angiqiniseki",
        "gbv_wants": "Usizo luni ofuna lona? Phendula ngezinombolo, isib. 1,2:\n1 Usomlomo\n2 Isibhedlela noma ikliniki\n3 Indawo yokukhosela\n4 Ukuthuthwa\nNoma 0 uma ungafuni lutho.",
        "gbv_contact": "Singakuthinta kule nombolo ye-WhatsApp?\n1 Yebo\n2 Cha, ungangithinti",
        "gbv_done": "Kutholakele. Inombolo yakho yereferensi ngu-{ref}. Awuwedwa. Uma usengozini manje shayela u-10111. I-GBV Command Centre ingu-0800 428 428, sonke isikhathi. (Isilingo.)",
        "tip_note": "I-WhatsApp ayifihli igama lakho. Inombolo yakho ibonwa yi-WhatsApp ne-Twilio. Asigcini igama noma inombolo nethiphu. Ukuze ufihleke ngokugcwele sebenzisa uhlelo lokusebenza.\nUbika ini?\n{opts}",
        "tip_done": "Ithiphu litholakele. Akulona icala. Ikhodi yakho ngu-{code}. Yisebenzise uma usithinta futhi. (Isilingo.)",
        "area_type": "Yini engaphephile? Phendula ngenombolo:\n{opts}",
        "area_done": "Kutholakele. Ireferensi {ref}. Lokhu akuyona ingxenye yecala. Kungabelwana nomasipala. (Isilingo.)",
        "emerg": "Lesi silingo asishayeli muntu futhi asithumeli muntu. Esimeni esiphuthumayo shayela u-10111.\nPhendula ngo-1 ukuthumela isexwayiso sesilingo, nendawo yakho, edeskini le-SAPS KZN.",
        "emerg_done": "Isexwayiso sithunyelwe edeskini lesilingo. Ireferensi {ref}. Esimeni esiphuthumayo shayela u-10111.",
        "bad": "Uxolo, angiqondanga. Phendula ngenye yezinombolo, noma MENU.",
        "cleared": "Kususiwe ohlangothini lwethu. Sicela futhi ususe le nkulumo efonini yakho.",
        "fail": "Uxolo, asikwazanga ukugcina lokho. Zama futhi.",
    },
}


def _opts(table, keys, lang):
    idx = 1 if lang == "zu" else 0
    return "\n".join(f"{i + 1} {table[k][idx]}" for i, k in enumerate(keys))


def _purge():
    cutoff = time.time() - TTL
    for k in [k for k, v in SESSIONS.items() if v["at"] < cutoff]:
        del SESSIONS[k]


def _point(form):
    try:
        return float(form.get("Latitude")), float(form.get("Longitude"))
    except (TypeError, ValueError):
        return None, None


def _pick(text, keys):
    t = text.strip()
    if t.isdigit() and 1 <= int(t) <= len(keys):
        return keys[int(t) - 1]
    return None


def handle(store, number, text, form):
    """One incoming message in, one reply out."""
    text = (text or "").strip()
    low = text.lower()
    with LOCK:
        _purge()
        sess = SESSIONS.setdefault(number, {"step": "lang", "lang": "en", "d": {}, "at": time.time()})
        sess["at"] = time.time()
        lang = sess["lang"]
        t = S[lang]

        if low in ("exit", "quit", "stop"):
            SESSIONS.pop(number, None)
            return t["cleared"]
        if low in ("menu", "hi", "hello", "start", "sawubona") and sess["step"] not in ("lang", "consent"):
            sess["step"], sess["d"] = "menu", {}
            return t["menu"]

        step = sess["step"]
        d = sess["d"]

        if step == "lang":
            if low in ("1", "2"):
                sess["lang"] = "en" if low == "1" else "zu"
                sess["step"] = "consent"
                return S[sess["lang"]]["consent"]
            return S["en"]["hello"]

        if step == "consent":
            if low in ("yes", "yebo", "y"):
                sess["step"] = "menu"
                return t["menu"]
            return t["consent"]

        if step == "menu":
            routes = {
                "1": ("crime_type", t["crime_type"].format(opts=_opts(taxonomy.CRIME_TYPES, CRIME_MENU, lang))),
                "2": ("gbv_safe", t["gbv_safe"]),
                "3": ("tip_type", t["tip_note"].format(opts=_opts(taxonomy.TIP_TYPES, TIP_MENU, lang))),
                "4": ("area_type", t["area_type"].format(opts=_opts(taxonomy.AREA_TYPES, AREA_MENU, lang))),
                "5": ("emerg", t["emerg"]),
            }
            if low in routes:
                sess["step"], reply = routes[low]
                sess["d"] = {}
                return reply
            return t["menu"]

        # ---- crime
        if step == "crime_type":
            key = _pick(text, CRIME_MENU)
            if not key:
                return t["bad"]
            d["type"], sess["step"] = key, "crime_place"
            return t["place_req"]
        if step in ("crime_place", "area_place", "tip_place"):
            lat, lon = _point(form)
            if lat is not None:
                d["lat"], d["lon"] = lat, lon
                d["address"] = (form.get("Address") or form.get("Label") or "")[:200]
            else:
                d["address"] = text[:200] if low != "skip" else ""
            if "lat" not in d and not d.get("address"):
                return t["place_req"]
            if step == "crime_place":
                sess["step"] = "crime_desc"
                return t["desc"]
            return _finish(store, number, sess, "area" if step == "area_place" else "tip")
        if step == "crime_desc":
            d["note"] = "" if low == "skip" else text
            return _finish(store, number, sess, "crime")

        # ---- gbv
        if step == "gbv_safe":
            safe = {"1": "yes", "2": "no", "3": "unsure"}.get(low)
            if not safe:
                return t["bad"]
            d["safe_now"], sess["step"] = safe, "gbv_wants"
            return t["gbv_wants"]
        if step == "gbv_wants":
            picks = [WANTS[c] for c in text.replace(" ", "").split(",") if c in WANTS]
            if not picks and low != "0":
                return t["bad"]
            d["wants"], sess["step"] = picks, "gbv_contact"
            return t["gbv_contact"]
        if step == "gbv_contact":
            if low not in ("1", "2"):
                return t["bad"]
            d["contact_pref"] = "sms" if low == "1" else "none"
            d["mobile"] = number.replace("whatsapp:", "") if low == "1" else ""
            sess["step"] = "gbv_place"
            return t["place"]
        if step == "gbv_place":
            lat, lon = _point(form)
            if lat is not None:
                d["lat"], d["lon"] = lat, lon
            elif low != "skip":
                d["address"] = text[:200]
            return _finish(store, number, sess, "gbv")

        # ---- tip and area type pick
        if step == "tip_type":
            key = _pick(text, TIP_MENU)
            if not key:
                return t["bad"]
            d["type"], sess["step"] = key, "tip_place"
            return t["place_req"]
        if step == "area_type":
            key = _pick(text, AREA_MENU)
            if not key:
                return t["bad"]
            d["type"], sess["step"] = key, "area_place"
            return t["place_req"]

        # ---- emergency
        if step == "emerg":
            if low == "1":
                lat, lon = _point(form)
                d = {"kind": "sos", "note": "Demo alert from WhatsApp."}
                if lat is not None:
                    d.update({"lat": lat, "lon": lon})
                sess["step"] = "menu"
                try:
                    case = service.create_case(store, d, channel="whatsapp")
                except service.Invalid:
                    return t["fail"]
                return t["emerg_done"].format(ref=case["ref"])
            return t["emerg"]

        sess["step"] = "menu"
        return t["menu"]


def _finish(store, number, sess, kind):
    lang, t, d = sess["lang"], S[sess["lang"]], sess["d"]
    try:
        if kind == "tip":
            tip, code = service.create_tip(store, d)
            reply = t["tip_done"].format(code=code)
        elif kind == "area":
            case = service.create_case(store, dict(d, kind="area"), channel="whatsapp")
            reply = t["area_done"].format(ref=case["ref"])
        elif kind == "gbv":
            case = service.create_case(store, dict(d, kind="gbv"), channel="whatsapp")
            reply = t["gbv_done"].format(ref=case["ref"])
        else:
            case = service.create_case(store, dict(d, kind="crime"), channel="whatsapp")
            reply = t["done_case"].format(ref=case["ref"])
    except service.Invalid as exc:
        return exc.message + "\n" + t["place"]
    sess["step"], sess["d"] = "menu", {}
    return reply + "\n\nMENU"


@bp.post("/whatsapp")
def webhook():
    if not (Config.TWILIO_AUTH_TOKEN and Config.whatsapp_enabled()):
        abort(503)
    signature = request.headers.get("X-Twilio-Signature", "")
    if not RequestValidator(Config.TWILIO_AUTH_TOKEN).validate(request.url, request.form, signature):
        abort(403)
    store = current_app.extensions["store"]
    number = request.form.get("From", "")
    reply = handle(store, number, request.form.get("Body", ""), request.form)
    resp = MessagingResponse()
    resp.message(reply)
    return Response(str(resp), mimetype="application/xml")
