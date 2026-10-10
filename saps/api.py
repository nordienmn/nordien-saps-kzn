"""JSON API. Citizens use /api/c/*; officers use /api/auth/* and /api/staff/*."""
import io
import secrets as _secrets

from flask import Blueprint, Response, current_app, jsonify, request, send_file, session

from . import blobs, geo, security, service, taxonomy, telephony
from .config import Config

bp = Blueprint("api", __name__, url_prefix="/api")


def store():
    return current_app.extensions["store"]


@bp.errorhandler(service.Invalid)
def invalid(exc):
    return jsonify({"error": exc.message, "field": exc.field}), 422


@bp.before_request
def guard():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if not security.same_origin_ok():
            return jsonify({"error": "Blocked: request came from another site."}), 403
        if request.endpoint in ("api.citizen_upload", "api.call_recording"):
            return None  # raw file bytes, checked inside the route
        if not request.is_json:
            return jsonify({"error": "Send JSON."}), 415
    return None


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise service.Invalid("That request could not be read.")
    return data


# ============================================================================ citizen
@bp.get("/c/config")
def citizen_config():
    return jsonify({
        "demo": True,
        "video": Config.video_enabled(),
        "whatsapp": {"enabled": Config.whatsapp_enabled(), "display": Config.WHATSAPP_DISPLAY, "join_hint": Config.WHATSAPP_JOIN_HINT},
        "crime_types": [{"key": k, "en": v[0], "zu": v[1]} for k, v in taxonomy.CRIME_TYPES.items() if not v[3]],
        "tip_types": [{"key": k, "en": v[0], "zu": v[1]} for k, v in taxonomy.TIP_TYPES.items()],
        "area_types": [{"key": k, "en": v[0], "zu": v[1]} for k, v in taxonomy.AREA_TYPES.items()],
        "clusters": geo.cluster_options(),
        "genders": taxonomy.GENDERS, "age_bands": taxonomy.AGE_BANDS,
    })


@bp.post("/c/report")
def citizen_report():
    data = body()
    kind = data.get("kind")
    s = store()
    if kind == "tip":
        tip, code = service.create_tip(s, data)
        return jsonify({"ok": True, "ref": tip["ref"], "code": code, "kind": "tip"})
    if kind not in ("crime", "gbv", "sos", "area"):
        raise service.Invalid("Unknown report type.", "kind")
    channel = "weather" if kind == "sos" or data.get("via") == "weather" else "app"
    case = service.create_case(s, data, channel=channel)
    notified = False
    if case.get("friend") and channel == "weather":
        notified = _alert_friend(case)
    return jsonify({"ok": True, "ref": case["ref"], "id": case["id"], "kind": case["kind"], "located": case["lat"] is not None, "friend_notified": notified})


def _alert_friend(case):
    text = (
        "SAPS KZN demo: a friend asked for help using a discreet alert. "
        + (f"Their location: {telephony.map_link(case['lat'], case['lon'])}. " if case["lat"] is not None else "Their location was not shared. ")
        + "If you think they are in danger call 10111."
    )
    return telephony.send_whatsapp(case["friend"], text)


@bp.get("/c/tip/<code>")
def tip_status(code):
    """Anonymous follow-up: the one-time code shows how far a tip has got. No identity is involved."""
    st = service.tip_public_status(store(), code)
    if st is None:
        return jsonify({"error": "No tip has that code."}), 404
    return jsonify(st)


@bp.post("/c/call/start")
def call_start():
    data = body()
    case, ctoken = service.start_call(store(), data)
    return jsonify({
        "ok": True, "id": case["id"], "ref": case["ref"], "ctoken": ctoken,
        "video": Config.video_enabled(), "mode": case["call"]["mode"],
    })


@bp.get("/c/call/<cid>/state")
def call_state(cid):
    return jsonify(service.citizen_call_state(store(), cid, request.args.get("t", "")))


@bp.post("/c/call/<cid>/line")
def call_line(cid):
    data = body()
    service.citizen_add_line(store(), cid, data.get("t"), data.get("text"), data.get("src", "typed"), bool(data.get("partial")))
    return jsonify({"ok": True})


@bp.post("/c/call/<cid>/end")
def call_end(cid):
    service.citizen_end_call(store(), cid, body().get("t"))
    return jsonify({"ok": True})


@bp.post("/c/call/<cid>/token")
def call_token(cid):
    """A Twilio Video token for the citizen, only once the officer has answered and opened a room."""
    data = body()
    state = service.citizen_call_state(store(), cid, data.get("t"))
    if not Config.video_enabled() or state["transport"] != "video" or state["state"] != "live":
        raise service.Invalid("Video is not available for this call.")
    return jsonify({"token": telephony.video_token(f"citizen-{cid}", state["room"]), "room": state["room"]})


# ============================================================================ auth
@bp.post("/c/upload")
def citizen_upload():
    """Evidence video or audio from the citizen. Held until the report is sent, then attached to the file."""
    mime = (request.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if mime not in blobs.ALLOWED_UPLOAD:
        return jsonify({"error": "That kind of file is not accepted."}), 415
    data = request.get_data(cache=False)
    if not data or len(data) > blobs.MAX_UPLOAD:
        return jsonify({"error": "That file is too large. Try a shorter video."}), 413
    upload_id = _secrets.token_urlsafe(12)
    blobs.stash_upload(upload_id, mime, data)
    return jsonify({"ok": True, "upload_id": upload_id, "size": len(data)})


@bp.post("/staff/case/<cid>/recording")
@security.login_required("desk")
def call_recording(cid):
    _, officer = security.current()
    chunk = request.get_data(cache=False)
    if not chunk or len(chunk) > 4 * 1024 * 1024:
        return jsonify({"error": "Bad chunk."}), 413
    size = service.add_recording_chunk(store(), cid, officer, chunk)
    return jsonify({"ok": True, "size": size})


@bp.get("/staff/blob/<mid>")
@security.login_required("desk")
def staff_blob(mid):
    _, officer = security.current()
    found = service.blob_for(store(), mid, officer)
    if found is None:
        return jsonify({"error": "Not found."}), 404
    mime, data = found
    return send_file(io.BytesIO(data), mimetype=mime, conditional=True, max_age=0)


@bp.get("/staff/action-points")
@security.login_required("desk", "board")
def staff_action_points():
    load = service.ap_load(store())
    points = service.action_points(store())
    for ap in points:
        ap["load"] = load.get(ap["id"], {"open": 0, "urgent": 0})
        ap["url"] = f"/unit/{ap['id']}?k={service.unit_token(ap['id'])}"
    return jsonify({"points": points})


def _unit_access(ap_id):
    role, _ = security.current()
    token = request.args.get("k") or (request.get_json(silent=True) or {}).get("k", "")
    return role in ("desk", "board") or service.unit_token_ok(ap_id, token)


@bp.get("/unit/<ap_id>/tasks")
def unit_tasks(ap_id):
    if not _unit_access(ap_id):
        return jsonify({"error": "This link is not valid.", "code": "auth"}), 403
    data = service.unit_tasks(store(), ap_id)
    if data is None:
        return jsonify({"error": "Not found."}), 404
    return jsonify(data)


@bp.post("/unit/<ap_id>/task")
def unit_task(ap_id):
    if not _unit_access(ap_id):
        return jsonify({"error": "This link is not valid.", "code": "auth"}), 403
    d = body()
    data = service.unit_tasks(store(), ap_id)
    name = data["point"]["name"] if data else ap_id
    service.unit_update(store(), ap_id, d.get("task_kind"), str(d.get("task_id") or ""), d.get("status"), d.get("note", ""), name)
    return jsonify({"ok": True})


@bp.post("/auth/login")
def login():
    data = body()
    role = data.get("role")
    if role not in ("desk", "board"):
        raise service.Invalid("Unknown login.")
    ok = security.check_password(role, data.get("password"))
    if ok is None:
        return jsonify({"error": "This login is not switched on for this demo."}), 503
    if not ok:
        service.audit(store(), "unknown", role, "login.failed")
        return jsonify({"error": "That password is not right."}), 401
    officer = str(data.get("officer") or "").strip().upper()
    if role == "desk" and not security.OFFICER_RE.match(officer):
        raise service.Invalid("Enter your officer ID (letters, numbers, dash).", "officer")
    if role == "board":
        officer = officer if security.OFFICER_RE.match(officer) else "EXEC"
    session.clear()
    session.update({"role": role, "officer": officer})
    session.permanent = False
    service.audit(store(), officer, role, "login")
    return jsonify({"ok": True, "role": role, "officer": officer})


@bp.post("/auth/logout")
def logout():
    role, officer = security.current()
    if role:
        service.audit(store(), officer, role, "logout")
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def me():
    role, officer = security.current()
    return jsonify({
        "role": role, "officer": officer,
        "video": Config.video_enabled(), "whatsapp": Config.whatsapp_enabled(),
        "login_desk": bool(Config.DESK_PASSWORD), "login_board": bool(Config.BOARD_PASSWORD),
    })


# ============================================================================ staff
@bp.get("/staff/feed")
@security.login_required("desk", "board")
def staff_feed():
    role, _ = security.current()
    s = store()
    since = request.args.get("since", type=int)
    if since is not None and since == s.snapshot_version():
        return jsonify({"unchanged": True, "version": since, "now": service.now()})
    return jsonify(service.feed(s, role))


@bp.get("/staff/case/<cid>")
@security.login_required("desk")
def staff_case(cid):
    _, officer = security.current()
    detail = service.case_detail(store(), cid, officer)
    if detail is None:
        return jsonify({"error": "Not found."}), 404
    return jsonify(detail)


@bp.get("/staff/tip/<tid>")
@security.login_required("desk", "board")
def staff_tip(tid):
    role, officer = security.current()
    detail = service.tip_detail(store(), tid, officer, role)
    if detail is None:
        return jsonify({"error": "Not found."}), 404
    return jsonify(detail)


@bp.get("/staff/tip-code/<code>")
@security.login_required("desk")
def tip_code(code):
    tip = service.check_tip_code(store(), code)
    if not tip:
        return jsonify({"error": "No tip has that code."}), 404
    return jsonify({"ref": tip["ref"], "status": tip["status"]})


@bp.post("/staff/case/<cid>/action")
@security.login_required("desk")
def staff_action(cid):
    _, officer = security.current()
    case = service.act(store(), cid, officer, body())
    return jsonify({"ok": True, "status": case["status"]})


@bp.post("/staff/case/<cid>/line")
@security.login_required("desk")
def staff_line(cid):
    _, officer = security.current()
    data = body()
    case = store().get("cases", cid)
    if not case or not case.get("call") or case["call"]["state"] != "live":
        raise service.Invalid("There is no live call on this file.")
    service.add_line(store(), cid, "operator", data.get("text"), "caption" if data.get("src") == "caption" else "typed", bool(data.get("partial")))
    return jsonify({"ok": True})


@bp.post("/staff/case/<cid>/answer")
@security.login_required("desk")
def staff_answer(cid):
    _, officer = security.current()
    data = body()
    want_video = bool(data.get("video")) and Config.video_enabled()
    case = store().get("cases", cid)
    room = ""
    transport = "text"
    if want_video and case and case.get("call") and case["call"]["mode"] in ("voice", "video"):
        room = telephony.room_name(cid)
        if telephony.ensure_room(room):
            transport = "video"
        else:
            room = ""
    case = service.answer_call(store(), cid, officer, transport, room)
    out = {"ok": True, "transport": transport, "room": room}
    if transport == "video":
        out["token"] = telephony.video_token(f"desk-{officer}", room)
    return jsonify(out)


@bp.post("/staff/case/<cid>/end")
@security.login_required("desk")
def staff_end(cid):
    _, officer = security.current()
    service.end_call(store(), cid, officer, "the officer")
    return jsonify({"ok": True})


@bp.post("/staff/case/<cid>/dispatch")
@security.login_required("desk")
def staff_dispatch(cid):
    _, officer = security.current()
    dep = service.dispatch(store(), cid, officer, body())
    return jsonify({"ok": True, "deployment": dep})


@bp.post("/staff/case/<cid>/deployment/<did>")
@security.login_required("desk")
def staff_deployment(cid, did):
    _, officer = security.current()
    service.update_deployment(store(), cid, did, officer, body().get("status"))
    return jsonify({"ok": True})


@bp.post("/staff/case/<cid>/refer")
@security.login_required("desk")
def staff_refer(cid):
    _, officer = security.current()
    ref = service.create_referral(store(), cid, officer, body())
    return jsonify({"ok": True, "referral": ref})


@bp.post("/staff/referral/<rid>")
@security.login_required("desk", "board")
def staff_referral(rid):
    _, officer = security.current()
    ref = service.update_referral(store(), rid, officer, body().get("status"))
    return jsonify({"ok": True, "referral": ref})


@bp.post("/staff/tip/<tid>/verify")
@security.login_required("desk")
def staff_tip_verify(tid):
    _, officer = security.current()
    tip = service.verify_tip(store(), tid, officer, body())
    return jsonify({"ok": True, "status": tip["status"]})


@bp.post("/staff/tip/<tid>/action")
@security.login_required("desk")
def staff_tip_action(tid):
    _, officer = security.current()
    service.action_tip(store(), tid, officer, body().get("note"))
    return jsonify({"ok": True})


@bp.post("/staff/tip/<tid>/refer-hq")
@security.login_required("desk")
def staff_tip_refer_hq(tid):
    _, officer = security.current()
    tip = service.refer_tip_to_hq(store(), tid, officer, body().get("note", ""))
    return jsonify({"ok": True, "status": tip["status"]})


@bp.post("/staff/tip/<tid>/close")
@security.login_required("desk", "board")
def staff_tip_close(tid):
    role, officer = security.current()
    tip = service.close_tip(store(), tid, officer or "EXEC", body().get("outcome"), role)
    return jsonify({"ok": True, "status": tip["status"]})


@bp.post("/staff/tip/<tid>/ack")
@security.login_required("board")
def staff_ack(tid):
    _, officer = security.current()
    tip = service.acknowledge_tip(store(), tid, officer or "EXEC")
    return jsonify({"ok": True, "status": tip["status"]})


@bp.get("/staff/partners")
@security.login_required("desk", "board")
def staff_partners():
    return jsonify({
        "partners": sorted(store().all("partners"), key=lambda p: (p["type"], p["name"])),
        "types": taxonomy.REFERRAL_TYPES,
    })


@bp.get("/staff/media/<mid>")
@security.login_required("desk")
def staff_media(mid):
    _, officer = security.current()
    m = store().get("media", mid)
    if m is None:
        return jsonify({"error": "Not found."}), 404
    service.audit(store(), officer, "desk", "media.view", m["case_id"])
    return jsonify({"data_url": m["data_url"]})


@bp.get("/staff/audit")
@security.login_required("board")
def staff_audit():
    rows = sorted(store().all("audit"), key=lambda a: -a["at"])[:200]
    return jsonify({"audit": rows})


@bp.get("/staff/stations")
@security.login_required("desk", "board")
def staff_stations():
    return jsonify({"stations": geo.station_options(), "units": taxonomy.UNIT_KINDS})


@bp.get("/staff/units")
@security.login_required("desk", "board")
def staff_units():
    units = [p for p in store().all("partners") if p["type"] in taxonomy.SAPS_UNIT_TYPES]
    return jsonify({"units": sorted(units, key=lambda p: (p["type"], p["name"]))})


@bp.post("/staff/direct")
@security.login_required("board")
def staff_direct():
    _, officer = security.current()
    data = body()
    ref = service.create_direction(store(), str(data.get("target_id") or ""), officer or "EXEC", data)
    return jsonify({"ok": True, "direction": ref})


@bp.get("/staff/partner/<pid>")
@security.login_required("desk", "board")
def staff_partner_view(pid):
    return jsonify({"items": service.partner_view(store(), pid)})


@bp.post("/admin/reset")
def admin_reset():
    role, officer = security.current()
    token = request.headers.get("X-Admin-Token", "")
    import hmac

    token_ok = bool(Config.ADMIN_TOKEN) and hmac.compare_digest(token, Config.ADMIN_TOKEN)
    if not (token_ok or role == "board"):
        return jsonify({"error": "Not allowed."}), 403
    from .seed import seed

    s = store()
    s.clear()
    seed(s)
    service.audit(s, officer or "admin", role or "admin", "reset", "", "Demo data reset to the seed set.")
    return jsonify({"ok": True})
