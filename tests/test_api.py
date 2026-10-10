import pytest

from app import create_app
from saps.config import Config
from saps.seed import seed
from saps.store import Store


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(Config, "DESK_PASSWORD", "desk-pass")
    monkeypatch.setattr(Config, "BOARD_PASSWORD", "board-pass")
    monkeypatch.setattr(Config, "ADMIN_TOKEN", "admin-token")
    store = Store()
    seed(store)
    app = create_app(testing=True, store=store)
    c = app.test_client()
    c.store = store
    return c


def login(c, role="desk", password=None, officer="OP-12"):
    pw = password or {"desk": "desk-pass", "board": "board-pass"}[role]
    return c.post("/api/auth/login", json={"role": role, "officer": officer, "password": pw})


UMLAZI = {"lat": -29.9697, "lon": 30.8864}


# ---------------------------------------------------------------- citizen reports
def test_crime_report_needs_type_and_place(client):
    assert client.post("/api/c/report", json={"kind": "crime", "address": "x"}).status_code == 422
    assert client.post("/api/c/report", json={"kind": "crime", "type": "theft"}).status_code == 422
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI})
    assert r.status_code == 200
    assert r.json["ref"].startswith("KZN-2026-") or r.json["ref"].startswith("KZN-")


def test_cluster_comes_from_location_not_a_default(client):
    client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI})
    case = sorted(client.store.all("cases"), key=lambda c: -c["created_at"])[0]
    assert case["cluster"] == "umlazi"


def test_point_outside_kzn_is_dropped(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "lat": 51.5, "lon": -0.12, "address": "somewhere"})
    assert r.json["located"] is False
    case = client.store.get("cases", r.json["id"])
    assert case["cluster"] == "unlocated" and case["lat"] is None


def test_domestic_violence_goes_to_gbv_and_is_restricted(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "domestic_violence", **UMLAZI})
    case = client.store.get("cases", r.json["id"])
    assert case["kind"] == "gbv" and case["restricted"] is True


def test_gbv_requires_safety_answer_and_number_when_contact_wanted(client):
    assert client.post("/api/c/report", json={"kind": "gbv"}).status_code == 422
    assert client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call"}).status_code == 422
    ok = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call", "mobile": "0600000999"})
    assert ok.status_code == 200
    assert client.store.get("cases", ok.json["id"])["priority"] == "critical"


def test_bad_mobile_rejected(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "mobile": "abc", **UMLAZI})
    assert r.status_code == 422 and r.json["field"] == "mobile"


def test_area_report_never_keeps_a_person(client):
    r = client.post("/api/c/report", json={"kind": "area", "type": "broken_light", "name": "Sam", "mobile": "0600000111", **UMLAZI})
    case = client.store.get("cases", r.json["id"])
    assert case["name"] == "" and case["mobile"] == "" and r.json["ref"].startswith("MUN-")


def test_anonymous_tip_stores_no_identity_and_returns_a_code(client):
    r = client.post("/api/c/report", json={"kind": "tip", "type": "drugs", "name": "Spy", "mobile": "0600000222", **UMLAZI})
    assert r.status_code == 200 and len(r.json["code"]) == 6
    tip = client.store.get("tips", r.json["ref"])
    assert "name" not in tip and "mobile" not in tip and "ip" not in tip
    assert r.json["code"] not in str(tip)  # only the hash is kept
    login(client)
    assert client.get(f"/api/staff/tip-code/{r.json['code']}").json["ref"] == r.json["ref"]


def test_photo_must_be_a_real_image(client):
    bad = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI, "photos": ["data:image/jpeg;base64,AAAA"]})
    assert bad.status_code == 422


# ---------------------------------------------------------------- request safety
def test_cross_site_write_is_blocked(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_non_json_write_is_refused(client):
    r = client.post("/api/c/report", data="kind=crime", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415


def test_security_headers_present(client):
    r = client.get("/api/c/config")
    assert "default-src 'self'" in r.headers["Content-Security-Policy"]
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Server" not in r.headers or "Werkzeug" not in r.headers.get("Server", "")


def test_no_path_traversal_through_static(client):
    assert client.get("/static/../app.py").status_code == 404
    assert client.get("/static/%2e%2e/app.py").status_code == 404


# ---------------------------------------------------------------- auth and access
def test_staff_routes_need_login(client):
    for path in ("/api/staff/feed", "/api/staff/audit", "/api/staff/partners"):
        assert client.get(path).status_code == 401
    assert client.post("/api/staff/case/KZN-2026-00001/action", json={"action": "accept"}).status_code == 401


def test_wrong_password_and_switched_off_login(client, monkeypatch):
    assert login(client, password="nope").status_code == 401
    monkeypatch.setattr(Config, "BOARD_PASSWORD", "")
    assert login(client, "board").status_code == 503


def test_desk_needs_officer_id(client):
    assert client.post("/api/auth/login", json={"role": "desk", "officer": "", "password": "desk-pass"}).status_code == 422


def test_board_feed_has_no_personal_details(client):
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    assert "stats" in feed
    for c in feed["cases"]:
        assert c["name"] == "" and c["address"] == ""
    assert client.get("/api/staff/case/anything").status_code == 401  # board cannot open files


def test_desk_hides_names_of_restricted_cases_and_logs_opening_them(client):
    login(client)
    feed = client.get("/api/staff/feed").json
    gbv = next(c for c in feed["cases"] if c["restricted"])
    assert gbv["name"] == ""
    before = len([a for a in client.store.all("audit") if a["action"] == "restricted.view"])
    detail = client.get(f"/api/staff/case/{gbv['id']}").json
    assert detail["restricted"] is True
    after = len([a for a in client.store.all("audit") if a["action"] == "restricted.view"])
    assert after == before + 1


def test_feed_unchanged_shortcut(client):
    login(client)
    v = client.get("/api/staff/feed").json["version"]
    assert client.get(f"/api/staff/feed?since={v}").json["unchanged"] is True


def test_script_text_is_stored_as_plain_text(client):
    payload = "<img src=x onerror=alert(1)>"
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "address": payload, "note": payload})
    login(client)
    d = client.get(f"/api/staff/case/{r.json['id']}").json
    assert d["note"] == payload and d["address"] == payload  # data stays data; pages render with textContent


# ---------------------------------------------------------------- calls
def test_call_lifecycle(client):
    start = client.post("/api/c/call/start", json={"mode": "voice", **UMLAZI}).json
    cid, t = start["id"], start["ctoken"]
    assert client.get(f"/api/c/call/{cid}/state?t={t}").json["state"] == "ringing"
    assert client.get(f"/api/c/call/{cid}/state?t=wrong").status_code == 422
    login(client)
    assert client.post(f"/api/staff/case/{cid}/answer", json={}).json["transport"] == "text"
    assert client.post(f"/api/c/call/{cid}/line", json={"t": t, "text": "I need help"}).status_code == 200
    assert client.post(f"/api/staff/case/{cid}/line", json={"text": "Where are you?"}).status_code == 200
    state = client.get(f"/api/c/call/{cid}/state?t={t}").json
    assert state["state"] == "live" and len(state["lines"]) == 2
    assert client.post(f"/api/c/call/{cid}/end", json={"t": t}).status_code == 200
    assert client.get(f"/api/c/call/{cid}/state?t={t}").json["state"] == "ended"
    case = client.store.get("cases", cid)
    assert any("Call ended" in e["text"] for e in case["timeline"])


def test_second_answer_is_refused(client):
    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    login(client)
    client.post(f"/api/staff/case/{cid}/answer", json={})
    assert client.post(f"/api/staff/case/{cid}/answer", json={}).status_code == 422


def test_cannot_close_a_file_with_a_live_call(client):
    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    login(client)
    assert client.post(f"/api/staff/case/{cid}/action", json={"action": "close"}).status_code == 422


# ---------------------------------------------------------------- referrals and tips
def test_referral_consent_gate(client):
    login(client)
    r = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "call", "mobile": "0600000333", "name": "Nomsa", **UMLAZI})
    cid = r.json["id"]
    no = client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "tcc-gizenga", "consent_to_share": False}).json["referral"]
    yes = client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "shelter-durban", "consent_to_share": True}).json["referral"]
    hidden = client.get("/api/staff/partner/tcc-gizenga").json["items"][0]
    shared = client.get("/api/staff/partner/shelter-durban").json["items"]
    shared = [i for i in shared if i["case_ref"] == r.json["ref"]][0]
    assert "mobile" not in hidden and "name" not in hidden
    assert shared["mobile"] == "0600000333"
    assert no["consent_to_share"] is False and yes["consent_to_share"] is True


def test_municipal_referral_only_for_area_reports(client):
    login(client)
    crime = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI}).json["id"]
    assert client.post(f"/api/staff/case/{crime}/refer", json={"partner_id": "mun-ethekwini-lights"}).status_code == 422


def new_tip(client):
    r = client.post("/api/c/report", json={"kind": "tip", "type": "drugs", **UMLAZI})
    return r.json["ref"], r.json["code"]


def test_every_tip_reaches_hq_for_oversight_before_the_desk_touches_it(client):
    tip, _ = new_tip(client)
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    row = next(t for t in feed["tips"] if t["ref"] == tip)
    assert row["status"] == "new" and feed["insights"]["tips"]["pipeline"]["new"] >= 1
    assert "name" not in row and row["address"] == ""  # HQ sees no address text, no identity


def test_desk_must_verify_before_referring_a_tip_to_hq(client):
    tip, _ = new_tip(client)
    login(client)
    assert client.post(f"/api/staff/tip/{tip}/refer-hq", json={}).status_code == 422
    assert client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified"}).status_code == 422  # needs a note
    assert client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified", "note": "Matched a known address."}).json["status"] == "verified"
    assert client.post(f"/api/staff/tip/{tip}/refer-hq", json={"note": "Needs Crime Intelligence."}).json["status"] == "referred"


def test_verified_referral_shows_as_hq_action_and_hq_can_direct_and_close(client):
    tip, code = new_tip(client)
    login(client)
    client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified", "note": "Checked."})
    client.post(f"/api/staff/tip/{tip}/refer-hq", json={})
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    assert any(a["type"] == "verified_referral" and a["ref"] == tip for a in feed["attention"])
    assert feed["stats"]["hq_referrals_waiting"] >= 1
    d = client.post("/api/staff/direct", json={"target_id": tip, "unit_id": "unit-intel", "instruction": "Look into this address.", "due_minutes": 90})
    assert d.status_code == 200 and d.json["direction"]["origin"] == "board"
    assert client.get(f"/api/c/tip/{code}").json["stage"] == "unit"
    assert client.post(f"/api/staff/tip/{tip}/close", json={"outcome": "used"}).json["status"] == "closed"
    pub = client.get(f"/api/c/tip/{code}").json
    assert pub["stage"] == "closed" and "used" in pub["outcome"]


def test_desk_cannot_close_a_tip_that_is_with_hq(client):
    tip, _ = new_tip(client)
    login(client)
    client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified", "note": "Checked."})
    client.post(f"/api/staff/tip/{tip}/refer-hq", json={})
    assert client.post(f"/api/staff/tip/{tip}/close", json={"outcome": "no_action"}).status_code == 422


def test_citizen_tip_follow_up_needs_the_right_code(client):
    _, code = new_tip(client)
    assert client.get(f"/api/c/tip/{code}").json["stage"] == "received"
    assert client.get("/api/c/tip/AAAAAA").status_code == 404


def test_directions_only_for_hq_and_only_to_saps_units(client):
    tip, _ = new_tip(client)
    login(client)
    assert client.post("/api/staff/direct", json={"target_id": tip, "unit_id": "unit-intel", "instruction": "Do it."}).status_code == 401
    login(client, "board")
    assert client.post("/api/staff/direct", json={"target_id": tip, "unit_id": "shelter-durban", "instruction": "Do it."}).status_code == 422
    assert client.post("/api/staff/direct", json={"target_id": tip, "unit_id": "unit-intel", "instruction": ""}).status_code == 422


def test_dispatch_records_station_and_times_and_feeds_hq(client):
    cid = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI}).json["id"]
    login(client)
    d = client.get(f"/api/staff/case/{cid}").json
    assert d["suggested_station"] == "umlazi"
    dep = client.post(f"/api/staff/case/{cid}/dispatch", json={"station": d["suggested_station"], "unit": "Patrol vehicle"}).json["deployment"]
    assert client.post(f"/api/staff/case/{cid}/deployment/{dep['id']}", json={"status": "on_scene"}).status_code == 200
    assert client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "nowhere"}).status_code == 422
    login(client, "board")
    ins = client.get("/api/staff/feed").json["insights"]
    assert any(r["key"] == "umlazi" for r in ins["deployments_by_station"])
    assert ins["response"]["deployments_7d"] >= 1


def test_demographics_are_optional_grouped_and_never_itemised_for_hq(client):
    client.post("/api/c/report", json={"kind": "crime", "type": "theft", "gender": "female", "age_band": "25_34", **UMLAZI})
    client.post("/api/c/report", json={"kind": "crime", "type": "theft", "gender": "nonsense", "age_band": "xx", **UMLAZI})
    login(client, "board")
    ins = client.get("/api/staff/feed").json["insights"]
    assert all(set(g) == {"key", "label", "n"} for g in ins["gender"])
    assert all(v in ("<5", 0) or isinstance(v, int) for row in ins["crime_by_gender"] for k, v in row.items() if k != "label")
    case = sorted(client.store.all("cases"), key=lambda c: -c["created_at"])[0]
    assert case["gender"] == "undisclosed" and case["age_band"] == "undisclosed"  # unknown values are not kept


def test_hq_map_never_carries_gbv_or_tip_points(client):
    client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "none", **UMLAZI})
    login(client, "board")
    ins = client.get("/api/staff/feed").json["insights"]
    assert all(p["kind"] in ("crime", "call", "area") for p in ins["points"])
    assert all(v in ("0", "<5", "5+") for v in ins["restricted_by_cluster"].values())


def test_board_small_number_rule(client):
    login(client, "board")
    clusters = client.get("/api/staff/feed").json["stats"]["by_cluster"]
    assert all(v["restricted"] in ("0", "<5", "5+") for v in clusters.values())


# ---------------------------------------------------------------- admin
def test_reset_needs_token_or_board(client):
    assert client.post("/api/admin/reset", json={}).status_code == 403
    assert client.post("/api/admin/reset", json={}, headers={"X-Admin-Token": "admin-token"}).status_code == 200
    login(client)  # a desk officer is not allowed to reset
    assert client.post("/api/admin/reset", json={}).status_code == 403


def test_seed_is_marked_synthetic_and_board_is_not_empty(client):
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    assert len(feed["cases"]) >= 30 and all(c["synthetic"] for c in feed["cases"])
    assert feed["stats"]["received"] >= 35


# ---------------------------------------------------------------- demo call limit and live captions
def test_live_call_ends_itself_after_one_minute(client):
    import time

    start = client.post("/api/c/call/start", json={"mode": "voice"}).json
    cid, t = start["id"], start["ctoken"]
    login(client)
    client.post(f"/api/staff/case/{cid}/answer", json={})

    def age_call(seconds):
        def fn(c):
            c["call"]["answered_at"] = time.time() - seconds
        client.store.patch("cases", cid, fn)

    age_call(30)
    assert client.get(f"/api/c/call/{cid}/state?t={t}").json["state"] == "live"
    age_call(61)
    state = client.get(f"/api/c/call/{cid}/state?t={t}").json
    assert state["state"] == "ended" and state["limit_s"] == 60
    assert any("one-minute demo limit" in e["text"] for e in client.store.get("cases", cid)["timeline"])


def test_unanswered_call_is_closed_after_ringing_too_long(client):
    import time

    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    client.store.patch("cases", cid, lambda c: c["call"].update(started_at=time.time() - 120))
    login(client)
    client.get("/api/staff/feed")
    assert client.store.get("cases", cid)["call"]["state"] == "ended"


def test_partial_captions_are_replaced_then_finalised(client):
    start = client.post("/api/c/call/start", json={"mode": "voice"}).json
    cid, t = start["id"], start["ctoken"]
    for text, partial in (("I need", True), ("I need help", True), ("I need help now", False)):
        assert client.post(f"/api/c/call/{cid}/line", json={"t": t, "text": text, "src": "caption", "partial": partial}).status_code == 200
    lines = client.store.get("cases", cid)["transcript"]
    assert len(lines) == 1 and lines[0]["text"] == "I need help now" and lines[0]["partial"] is False


# ---------------------------------------------------------------- evidence, recordings, action points
def test_citizen_video_is_saved_with_the_report_and_playable_by_the_desk(client):
    video = b"\x1aE\xdf\xa3" + b"0" * 5000
    up = client.post("/api/c/upload", data=video, headers={"Content-Type": "video/webm"})
    assert up.status_code == 200
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "uploads": [up.json["upload_id"]], **UMLAZI})
    login(client)
    d = client.get(f"/api/staff/case/{r.json['id']}").json
    vid = next(m for m in d["media"] if m["type"] == "video")
    got = client.get(f"/api/staff/blob/{vid['id']}")
    assert got.status_code == 200 and got.data == video and got.mimetype == "video/webm"
    assert any(a["action"] == "media.view" for a in client.store.all("audit"))


def test_upload_rejects_wrong_type_and_oversize(client):
    assert client.post("/api/c/upload", data=b"x", headers={"Content-Type": "application/x-msdownload"}).status_code == 415
    assert client.post("/api/c/upload", data=b"x" * (15 * 1024 * 1024 + 1), headers={"Content-Type": "video/mp4"}).status_code == 413


def test_call_recording_chunks_are_saved_on_the_file(client):
    cid = client.post("/api/c/call/start", json={"mode": "video"}).json["id"]
    login(client)
    client.post(f"/api/staff/case/{cid}/answer", json={})
    assert client.post(f"/api/staff/case/{cid}/recording", data=b"AAAA", headers={"Content-Type": "video/webm"}).json["size"] == 4
    assert client.post(f"/api/staff/case/{cid}/recording", data=b"BBBB", headers={"Content-Type": "video/webm"}).json["size"] == 8
    rec = next(m for m in client.get(f"/api/staff/case/{cid}").json["media"] if m["type"] == "recording")
    assert client.get(f"/api/staff/blob/{rec['id']}").data == b"AAAABBBB"


def test_a_station_gets_its_own_task_page_by_private_link(client):
    cid = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "name": "Sam", "mobile": "0600000555", **UMLAZI}).json["id"]
    login(client)
    client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi", "unit": "Patrol vehicle", "note": "Man at the gate."})
    points = {p["id"]: p for p in client.get("/api/staff/action-points").json["points"]}
    st = points["st-umlazi"]
    assert st["load"]["open"] >= 1 and "?k=" in st["url"]
    token = st["url"].split("?k=")[1]
    client.post("/api/auth/logout", json={})  # now an anonymous visitor holding only the link
    assert client.get("/api/unit/st-umlazi/tasks").status_code == 403
    assert client.get("/api/unit/st-umlazi/tasks?k=wrong").status_code == 403
    tasks = client.get(f"/api/unit/st-umlazi/tasks?k={token}").json["tasks"]
    mine = next(t for t in tasks if t["case_id"] == cid)
    assert mine["instruction"] == "Man at the gate." and mine["mobile"] == "0600000555"
    other_token = points["st-pinetown"]["url"].split("?k=")[1]
    assert client.get(f"/api/unit/st-umlazi/tasks?k={other_token}").status_code == 403  # a link opens one door only
    for status in ("acknowledged", "on_scene", "cleared"):
        assert client.post(f"/api/unit/st-umlazi/task?k={token}", json={"task_kind": "deployment", "task_id": mine["id"], "status": status}).status_code == 200
    login(client, "board")
    assert client.get("/api/staff/feed").json["insights"]["response"]["deployments_7d"] >= 1


def test_unit_page_hides_names_of_restricted_files(client):
    cid = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "call", "mobile": "0600000777", "name": "Zinhle", **UMLAZI}).json["id"]
    login(client)
    client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi", "unit": "FCS unit"})
    tasks = client.get("/api/unit/st-umlazi/tasks").json["tasks"]  # staff session needs no link
    t = next(x for x in tasks if x["case_id"] == cid)
    assert t["name"] == "" and t["mobile"] == ""


def test_referral_partner_page_works_for_partners_too(client):
    cid = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "call", "mobile": "0600000888", **UMLAZI}).json["id"]
    login(client)
    client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "tcc-gizenga", "consent_to_share": True, "urgency": "urgent"})
    token = next(p for p in client.get("/api/staff/action-points").json["points"] if p["id"] == "tcc-gizenga")["url"].split("?k=")[1]
    client.post("/api/auth/logout", json={})
    tasks = client.get(f"/api/unit/tcc-gizenga/tasks?k={token}").json["tasks"]
    task = next(t for t in tasks if t["case_id"] == cid)
    assert task["mobile"] == "0600000888"  # the citizen agreed to share
    assert client.post(f"/api/unit/tcc-gizenga/task?k={token}", json={"task_kind": "referral", "task_id": task["id"], "status": "acknowledged"}).status_code == 200


def test_a_bad_profile_photo_never_blocks_a_call_or_report(client):
    r = client.post("/api/c/call/start", json={"mode": "voice", "name": "Sam", "mobile": "0600000999", "face": "data:image/gif;base64,R0lGODlhAQABAAAAACw="})
    assert r.status_code == 200
    r2 = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "face": "not-an-image", **UMLAZI})
    assert r2.status_code == 200


def test_csp_allows_the_map_tile_host(client):
    csp = client.get("/api/c/config").headers["Content-Security-Policy"]
    assert "https://tile.openstreetmap.org" in csp
