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


import base64

PHOTO = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8" + b"0" * 40).decode()


def login(c, role="desk", password=None, section="desk", officer="OP-12", photo=PHOTO):
    pw = password or {"desk": "desk-pass", "board": "board-pass"}[role]
    return c.post("/api/auth/login", json={"role": role, "section": section, "officer": officer, "photo": photo, "password": pw})


UMLAZI = {"lat": -29.9697, "lon": 30.8864}


# ---------------------------------------------------------------- citizen reports
def test_an_incomplete_crime_report_is_accepted_and_flagged(client):
    a = client.post("/api/c/report", json={"kind": "crime", "address": "x"})
    b = client.post("/api/c/report", json={"kind": "crime", "type": "theft"})
    c0 = client.post("/api/c/report", json={"kind": "crime"})
    assert a.status_code == b.status_code == c0.status_code == 200
    ca = client.store.get("cases", a.json["id"])
    assert ca["incomplete"] and ca["missing"] == ["the type of crime"] and ca["label_key"] == "other"
    cb = client.store.get("cases", b.json["id"])
    assert cb["incomplete"] and cb["missing"] == ["the place"] and cb["cluster"] == "unlocated"
    assert set(client.store.get("cases", c0.json["id"])["missing"]) == {"the type of crime", "the place"}
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


def test_gbv_help_goes_through_even_with_nothing_filled_in(client):
    bare = client.post("/api/c/report", json={"kind": "gbv"})
    assert bare.status_code == 200
    case = client.store.get("cases", bare.json["id"])
    assert case["incomplete"] and case["safe_now"] == "unsure" and case["needs"]
    nocall = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call"})
    assert nocall.status_code == 200 and client.store.get("cases", nocall.json["id"])["contact_pref"] == "none"
    ok = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call", "mobile": "0600000999"})
    assert ok.status_code == 200
    assert client.store.get("cases", ok.json["id"])["priority"] == "critical"


def test_a_bad_mobile_number_does_not_stop_the_report(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "mobile": "abc", **UMLAZI})
    assert r.status_code == 200
    case = client.store.get("cases", r.json["id"])
    assert case["mobile"] == "" and "a valid mobile number" in case["missing"]


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
    login(client, section="tip_line")
    assert client.get(f"/api/staff/tip-code/{r.json['code']}").json["ref"] == r.json["ref"]


def test_an_unreadable_photo_is_left_out_but_the_report_goes_through(client):
    bad = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI, "photos": ["data:image/jpeg;base64,AAAA"]})
    assert bad.status_code == 200 and client.store.get("cases", bad.json["id"])["media"] == []


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


def test_desk_login_needs_section_officer_id_and_a_photo(client):
    base = {"role": "desk", "password": "desk-pass", "officer": "OP-12", "photo": PHOTO}
    assert client.post("/api/auth/login", json={**base, "section": None}).status_code == 422
    assert client.post("/api/auth/login", json={**base, "section": "kitchen"}).status_code == 422
    assert client.post("/api/auth/login", json={**base, "section": "gbv", "officer": ""}).status_code == 422
    assert client.post("/api/auth/login", json={**base, "section": "gbv", "photo": ""}).status_code == 422
    flagged = client.post("/api/auth/login", json={**base, "section": "gbv", "photo": "", "no_camera": True})  # camera would not start
    assert flagged.status_code == 200
    assert client.post("/api/auth/login", json={**base, "section": "gbv", "photo": "data:image/jpeg;base64,AAAA"}).status_code == 422
    ok = client.post("/api/auth/login", json={**base, "section": "gbv"})
    assert ok.status_code == 200 and ok.json["officer"] == "OP-12 · GBV desk"
    anything = client.post("/api/auth/login", json={**base, "section": "gbv", "officer": "Sipho / 0829"})  # any name or number is accepted
    assert anything.status_code == 200 and anything.json["officer"] == "Sipho / 0829 · GBV desk"
    assert [x["key"] for x in client.get("/api/auth/me").json["sections"]] == ["call_centre", "desk", "tip_line", "gbv"]


def test_board_feed_has_no_personal_details(client):
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    assert "stats" in feed
    for c in feed["cases"]:
        assert c["name"] == "" and c["address"] == ""
    assert client.get("/api/staff/case/anything").status_code == 401  # board cannot open files


def test_desk_hides_names_of_restricted_cases_and_logs_opening_them(client):
    login(client, section="gbv")
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
    login(client, section="call_centre")
    assert client.post(f"/api/staff/case/{cid}/answer", json={}).json["transport"] == "p2p"
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
    login(client, section="call_centre")
    client.post(f"/api/staff/case/{cid}/answer", json={})
    assert client.post(f"/api/staff/case/{cid}/answer", json={}).status_code == 422


def test_cannot_close_a_file_with_a_live_call(client):
    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    login(client, section="call_centre")
    assert client.post(f"/api/staff/case/{cid}/action", json={"action": "close"}).status_code == 422


# ---------------------------------------------------------------- referrals and tips
def test_referral_consent_gate(client):
    login(client, section="gbv")
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
    login(client, section="tip_line")
    assert client.post(f"/api/staff/tip/{tip}/refer-hq", json={}).status_code == 422
    assert client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified"}).status_code == 422  # needs a note
    assert client.post(f"/api/staff/tip/{tip}/verify", json={"result": "verified", "note": "Matched a known address."}).json["status"] == "verified"
    assert client.post(f"/api/staff/tip/{tip}/refer-hq", json={"note": "Needs Crime Intelligence."}).json["status"] == "referred"


def test_verified_referral_shows_as_hq_action_and_hq_can_direct_and_close(client):
    tip, code = new_tip(client)
    login(client, section="tip_line")
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
    login(client, section="tip_line")
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
    login(client, section="call_centre")
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
    login(client, section="call_centre")
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
    login(client, section="gbv")
    client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi", "unit": "FCS unit"})
    tasks = client.get("/api/unit/st-umlazi/tasks").json["tasks"]  # staff session needs no link
    t = next(x for x in tasks if x["case_id"] == cid)
    assert t["name"] == "" and t["mobile"] == ""


def test_referral_partner_page_works_for_partners_too(client):
    cid = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "call", "mobile": "0600000888", **UMLAZI}).json["id"]
    login(client, section="gbv")
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



def test_each_section_sees_only_its_own_work(client):
    login(client, section="call_centre")
    kinds = {c["kind"] for c in client.get("/api/staff/feed").json["cases"]}
    assert kinds <= {"call"} and client.get("/api/staff/feed").json["tips"] == []
    login(client, section="desk")
    cases = client.get("/api/staff/feed").json["cases"]
    kinds = {c["kind"] for c in cases}
    assert kinds <= {"crime", "area", "call"} and "crime" in kinds
    assert all(c["call_missed"] or c["call_state"] in ("ringing", "live") for c in cases if c["kind"] == "call")  # only calls that need someone now
    login(client, section="gbv")
    feed = client.get("/api/staff/feed").json
    assert {c["kind"] for c in feed["cases"]} <= {"gbv", "sos", "call"} and feed["tips"] == []
    login(client, section="tip_line")
    feed = client.get("/api/staff/feed").json
    assert {c["kind"] for c in feed["cases"]} <= {"call"} and len(feed["tips"]) >= 5


def test_a_section_cannot_open_or_change_another_sections_files(client):
    crime = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI}).json["id"]
    gbv = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "yes", "contact_pref": "none", **UMLAZI}).json["id"]
    tip = client.post("/api/c/report", json={"kind": "tip", "type": "drugs", **UMLAZI}).json["ref"]
    login(client, section="gbv")
    assert client.get(f"/api/staff/case/{gbv}").status_code == 200
    assert client.get(f"/api/staff/case/{crime}").status_code == 403
    assert client.post(f"/api/staff/case/{crime}/action", json={"action": "accept"}).status_code == 403
    assert client.get(f"/api/staff/tip/{tip}").status_code == 403
    login(client, section="desk")
    assert client.get(f"/api/staff/case/{gbv}").status_code == 403
    assert client.get(f"/api/staff/case/{crime}").status_code == 200
    login(client, section="tip_line")
    assert client.get(f"/api/staff/tip/{tip}").status_code == 200
    assert client.get(f"/api/staff/case/{crime}").status_code == 403



def test_shift_record_has_officer_id_and_photos_in_and_out_and_hq_can_view_it(client):
    login(client, section="call_centre", officer="Thandi Mkhize")
    assert client.post("/api/auth/logout", json={"photo": PHOTO}).status_code == 200
    login(client, section="desk", officer="4471")
    assert client.post("/api/auth/logout", json={}).status_code == 200  # signed out without a photo: recorded and flagged
    assert client.get("/api/staff/shifts").status_code == 401  # a desk officer cannot read the shift log
    login(client, "board")
    shifts = client.get("/api/staff/shifts?limit=100").json["shifts"]
    first = next(x for x in shifts if x["officer_id"] == "Thandi Mkhize")
    second = next(x for x in shifts if x["officer_id"] == "4471")
    assert first["has_in_photo"] and first["has_out_photo"] and first["out_at"] and first["section_label"] == "Call centre"
    assert second["out_photo_missing"] is True and second["has_out_photo"] is False
    assert client.get(f"/api/staff/shift-photo/{first['id']}/in").json["data_url"].startswith("data:image/jpeg")
    assert any(a["action"] == "shift.photo.view" for a in client.store.all("audit"))


def test_photo_requirement_can_be_switched_off_for_a_laptop_with_no_camera(client, monkeypatch):
    monkeypatch.setattr(Config, "REQUIRE_SIGNIN_PHOTO", False)
    assert login(client, photo="").status_code == 200



def test_staff_sign_in_records_are_searched_and_paged_on_the_server(client):
    for n in range(30):
        login(client, section="desk" if n % 2 else "gbv", officer=f"Zed{chr(97 + n % 26)}{chr(97 + n // 26)}")
        client.post("/api/auth/logout", json={"photo": PHOTO})
    login(client, "board")
    first = client.get("/api/staff/shifts?limit=10").json
    assert len(first["shifts"]) == 10 and first["pages"] >= 4 and first["total"] >= 35 and first["counts"]["all"] == first["total"]
    page2 = client.get("/api/staff/shifts?limit=10&page=2").json
    assert page2["page"] == 2 and {x["id"] for x in page2["shifts"]}.isdisjoint({x["id"] for x in first["shifts"]})
    one = client.get("/api/staff/shifts?q=zedha").json
    assert one["total"] == 1 and one["shifts"][0]["officer_id"] == "Zedha"
    gbv = client.get("/api/staff/shifts?section=gbv&limit=100").json
    assert gbv["shifts"] and all(x["section"] == "gbv" for x in gbv["shifts"])
    assert client.get("/api/staff/shifts?q=gbv desk zedka").json["total"] == 1
    assert client.get("/api/staff/shifts?q=zzzz").json["total"] == 0



def test_call_record_file_has_the_chat_and_the_callers_recording_is_saved(client):
    start = client.post("/api/c/call/start", json={"mode": "video", **UMLAZI}).json
    cid, t = start["id"], start["ctoken"]
    assert client.post(f"/api/c/call/{cid}/recording?t=wrong", data=b"AAAA", headers={"Content-Type": "video/webm"}).status_code == 422
    assert client.post(f"/api/c/call/{cid}/recording?t={t}", data=b"AAAA", headers={"Content-Type": "video/webm"}).json["size"] == 4
    assert client.get(f"/api/c/call/{cid}/state?t={t}").json["recording"] is True
    login(client, section="call_centre")
    client.post(f"/api/staff/case/{cid}/answer", json={})
    client.post(f"/api/c/call/{cid}/line", json={"t": t, "text": "I need help now"})
    client.post(f"/api/staff/case/{cid}/line", json={"text": "We are with you"})
    client.post(f"/api/c/call/{cid}/end", json={"t": t})
    rec = client.get(f"/api/staff/case/{cid}/record.txt")
    assert rec.status_code == 200 and "attachment" in rec.headers["Content-Disposition"]
    body = rec.data.decode()
    assert "CALL RECORD" in body and "Caller (typed): I need help now" in body and "Officer (typed): We are with you" in body and "saved on the file" in body
    detail = client.get(f"/api/staff/case/{cid}").json
    media = next(m for m in detail["media"] if m["type"] == "recording")
    assert client.get(f"/api/staff/blob/{media['id']}").data == b"AAAA"
    login(client, section="desk")
    assert client.get(f"/api/staff/case/{cid}/record.txt").status_code == 403  # another section cannot download it



def test_the_call_folder_travels_with_the_file_to_every_action_point(client):
    start = client.post("/api/c/call/start", json={"mode": "video", "name": "Sam", "mobile": "0600000444", **UMLAZI}).json
    cid, t = start["id"], start["ctoken"]
    client.post(f"/api/c/call/{cid}/recording?t={t}", data=b"REC1", headers={"Content-Type": "video/webm"})
    login(client, section="call_centre")
    client.post(f"/api/staff/case/{cid}/answer", json={})
    client.post(f"/api/c/call/{cid}/line", json={"t": t, "text": "Two men at my gate"})
    client.post(f"/api/staff/case/{cid}/line", json={"text": "Stay inside"})
    client.post(f"/api/c/call/{cid}/end", json={"t": t})
    client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi", "unit": "Patrol vehicle"})
    client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "unit-flying-dbn"})
    client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "health-addington", "consent_to_share": False})
    client.post(f"/api/staff/case/{cid}/refer", json={"partner_id": "sw-dsd", "consent_to_share": True})
    pts = {p["id"]: p["url"].split("?k=")[1] for p in client.get("/api/staff/action-points").json["points"]}
    client.post("/api/auth/logout", json={})

    def folder(ap):
        tasks = client.get(f"/api/unit/{ap}/tasks?k={pts[ap]}").json["tasks"]
        return next(x for x in tasks if x["case_id"] == cid)["folder"]

    f = folder("st-umlazi")  # a SAPS station always gets the whole folder
    assert [l["text"] for l in f["call"]["lines"]] == ["Two men at my gate", "Stay inside"]
    rec = next(e for e in f["evidence"] if e["type"] == "recording")
    assert client.get(f"/api/unit/st-umlazi/media/{rec['id']}?k={pts['st-umlazi']}").data == b"REC1"
    assert folder("unit-flying-dbn")["call"]["lines"]  # a SAPS unit gets it too
    assert folder("health-addington")["call"]["lines"]  # demo: the folder goes to every action point
    assert folder("sw-dsd")["call"]["lines"]
    assert client.get(f"/api/unit/health-addington/media/{rec['id']}?k={pts['health-addington']}").data == b"REC1"
    assert client.get(f"/api/unit/st-pinetown/media/{rec['id']}?k={pts['st-pinetown']}").status_code == 404  # not their file



def test_gbv_file_carries_needs_and_a_station_that_lacks_one_triggers_a_request_and_an_hq_alert(client):
    login(client, section="gbv")
    cid = client.post("/api/c/report", json={"kind": "crime", "type": "sexual_offence", **UMLAZI}).json["id"]
    d = client.get(f"/api/staff/case/{cid}").json
    assert d["kind"] == "gbv" and {"female_officer", "counsellor", "kit_d1", "medical", "vfr"} <= set(client.store.get("cases", cid)["needs"])
    assert client.post(f"/api/staff/case/{cid}/action", json={"action": "needs", "needs": ["female_officer", "kit_d7"]}).status_code == 200
    assert client.store.get("cases", cid)["needs"] == ["female_officer", "kit_d7"]
    dep = client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi", "unit": "FCS unit", "needs": ["female_officer", "counsellor", "kit_d1"]}).json["deployment"]
    assert set(dep["needs"]) == {"female_officer", "counsellor", "kit_d1"}
    points = {p["id"]: p["url"].split("?k=")[1] for p in client.get("/api/staff/action-points").json["points"]}
    tok = points["st-umlazi"]
    client.post("/api/auth/logout", json={})
    tasks = client.get(f"/api/unit/st-umlazi/tasks?k={tok}").json["tasks"]
    mine = next(t for t in tasks if t["case_id"] == cid)
    assert {n["key"]: n["status"] for n in mine["needs"]} == {"female_officer": "asked", "counsellor": "asked", "kit_d1": "asked"}
    ok = client.post(f"/api/unit/st-umlazi/need?k={tok}", json={"task_id": mine["id"], "need": "female_officer", "answer": "available"})
    no = client.post(f"/api/unit/st-umlazi/need?k={tok}", json={"task_id": mine["id"], "need": "kit_d1", "answer": "unavailable", "note": "Shelf is empty"})
    assert ok.status_code == 200 and no.status_code == 200
    case = client.store.get("cases", cid)
    kit = case["deployments"][0]["needs"]["kit_d1"]
    assert kit["status"] == "unavailable" and kit["request_partner"].startswith("SAPS Forensic Science")
    req = client.store.get("referrals", kit["request_id"])
    assert req["origin"] == "request" and req["urgency"] == "urgent" and "does not have" in req["instruction"]
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    gap = next(a for a in feed["attention"] if a["type"] == "gbv_gap")
    assert "D1" in gap["label"] and "Umlazi" in gap["reason"]
    assert any(r["label"].startswith("Evidence kit for an adult") for r in feed["insights"]["gbv_needs"])
    assert "name" not in str(feed["insights"]["gbv_needs"])  # counts only


def test_unconfirmed_gbv_needs_are_flagged_to_hq_after_ten_minutes(client):
    import time

    login(client, section="gbv")
    cid = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "none", **UMLAZI}).json["id"]
    client.post(f"/api/staff/case/{cid}/dispatch", json={"station": "umlazi"})
    client.store.patch("cases", cid, lambda c: c["deployments"][0].update(dispatched_at=time.time() - 700))
    login(client, "board")
    assert any(a["type"] == "gbv_unconfirmed" for a in client.get("/api/staff/feed").json["attention"])



def test_a_registered_citizens_profile_is_on_every_file_they_open(client):
    profile = {"name": "Nomsa Dube", "mobile": "0600000501", "home_address": "12 Jacaranda Rd, Umlazi", "gender": "female", "age_band": "25_34",
               "friend": "0600000502", "friend_name": "Thandi", "registered": True, "lang": "zu"}
    login(client, section="gbv")
    gbv = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "none", **profile, **UMLAZI}).json["id"]
    d = client.get(f"/api/staff/case/{gbv}").json
    assert d["registered"] and d["name"] == "Nomsa Dube" and d["mobile"] == "0600000501" and d["home_address"].startswith("12 Jacaranda")
    assert d["gender"] == "female" and d["age_band"] == "25_34" and d["friend"] == "0600000502" and d["friend_name"] == "Thandi" and d["language"] == "zu"
    assert d["contact_pref"] == "none"  # she asked not to be called; the details are there to identify her, not to call her
    login(client, section="desk")
    crime = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **profile, **UMLAZI}).json["id"]
    c = client.get(f"/api/staff/case/{crime}").json
    assert c["registered"] and c["mobile"] == "0600000501" and c["friend_name"] == "Thandi"
    login(client, section="call_centre")
    call = client.post("/api/c/call/start", json={"mode": "voice", **profile, **UMLAZI}).json["id"]
    assert client.get(f"/api/staff/case/{call}").json["registered"]
    # an anonymous tip and an unsafe-area report never carry a person
    area = client.post("/api/c/report", json={"kind": "area", "type": "broken_light", **profile, **UMLAZI}).json["id"]
    a = client.store.get("cases", area)
    assert not a["registered"] and a["name"] == "" and a["home_address"] == "" and a["friend_name"] == ""
    # HQ never sees any of it
    login(client, "board")
    feed = client.get("/api/staff/feed").json
    assert "Nomsa" not in str(feed) and "0600000501" not in str(feed) and "Jacaranda" not in str(feed)



def test_anonymous_tip_and_unsafe_place_and_weather_help_all_go_through_when_incomplete(client):
    tip = client.post("/api/c/report", json={"kind": "tip"})
    assert tip.status_code == 200 and len(tip.json["code"]) == 6
    t = client.store.get("tips", tip.json["ref"])
    assert t["incomplete"] and t["type_key"] == "other" and set(t["missing"]) == {"what is being reported", "the place"}
    area = client.post("/api/c/report", json={"kind": "area"})
    assert area.status_code == 200 and client.store.get("cases", area.json["id"])["incomplete"]
    weather = client.post("/api/c/report", json={"kind": "gbv", "via": "weather"})
    assert weather.status_code == 200 and client.store.get("cases", weather.json["id"])["channel"] == "weather"
    sos = client.post("/api/c/report", json={"kind": "sos"})
    assert sos.status_code == 200
    login(client, section="tip_line")
    assert any(x["incomplete"] for x in client.get("/api/staff/feed").json["tips"])


def test_home_screen_icons_and_weather_cover(client):
    """The app installs with the SAPS badge. The weather cover must never show it."""
    page = client.get("/citizen").get_data(as_text=True)
    assert "manifest-saps.json" in page and "saps-180.png" in page
    weather = client.get("/weather").get_data(as_text=True)
    assert "manifest-weather.json" in weather and "weather-180.png" in weather
    assert "saps" not in weather.lower().split("<body")[0].replace("manifest-weather", "")
    for path in ("/static/manifest-saps.json", "/static/manifest-weather.json", "/static/img/saps-512.png", "/static/img/weather-512.png"):
        assert client.get(path).status_code == 200
    names = client.get("/static/manifest-weather.json").get_json()
    assert names["name"] == "Weather" and names["start_url"] == "/weather"


# ---------------------------------------------------------------- calling is shared, missed and dropped calls
def test_every_section_sees_a_ringing_call_and_can_answer_it(client):
    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    for section in ("desk", "tip_line", "gbv", "call_centre"):
        login(client, section=section)
        feed = client.get("/api/staff/feed").json
        assert any(c["id"] == cid and c["call_state"] == "ringing" for c in feed["cases"]), section
    login(client, section="gbv")
    assert client.post(f"/api/staff/case/{cid}/answer", json={}).status_code == 200
    assert client.get(f"/api/staff/case/{cid}").status_code == 200
    # an ordinary crime file is still closed to the GBV section
    login(client, section="desk")
    crime = client.post("/api/c/report", json={"kind": "crime", "type": "theft"}).json["id"]
    login(client, section="gbv")
    assert client.get(f"/api/staff/case/{crime}").status_code == 403


def test_unanswered_call_becomes_a_missed_call_on_every_desk_until_returned(client):
    import time

    start = client.post("/api/c/call/start", json={"mode": "voice", "name": "Thandi", "mobile": "0821234567"}).json
    cid = start["id"]
    client.store.patch("cases", cid, lambda c: c["call"].update(started_at=time.time() - 120))
    login(client, section="tip_line")
    row = next(c for c in client.get("/api/staff/feed").json["cases"] if c["id"] == cid)
    assert row["call_missed"] and row["call_missed_reason"] == "unanswered" and not row["call_callback"]
    # return it by phone, from a section that is not the call centre
    assert client.post(f"/api/staff/case/{cid}/callback", json={"method": "phone", "note": "Rang back"}).status_code == 200
    assert client.post(f"/api/staff/case/{cid}/callback", json={"method": "phone"}).status_code == 422
    login(client, section="gbv")
    assert not any(c["id"] == cid for c in client.get("/api/staff/feed").json["cases"])


def test_missed_call_without_a_number_goes_back_to_the_app(client):
    start = client.post("/api/c/call/start", json={"mode": "voice"}).json
    cid, t = start["id"], start["ctoken"]
    client.post(f"/api/c/call/{cid}/end", json={"t": t})  # the caller hangs up before anyone answers
    login(client, section="desk")
    row = next(c for c in client.get("/api/staff/feed").json["cases"] if c["id"] == cid)
    assert row["call_missed"] and row["call_missed_reason"] == "caller_hung_up"
    assert client.post(f"/api/staff/case/{cid}/callback", json={"method": "phone"}).status_code == 422  # no number on record
    assert client.post(f"/api/staff/case/{cid}/callback", json={"method": "app"}).status_code == 200
    state = client.get(f"/api/c/call/{cid}/state?t={t}").json
    assert state["missed"] and state["callback_requested"]


def test_dropped_live_call_is_flagged_for_call_back(client):
    import time
    from saps import service

    start = client.post("/api/c/call/start", json={"mode": "voice"}).json
    cid, t = start["id"], start["ctoken"]
    login(client, section="call_centre")
    client.post(f"/api/staff/case/{cid}/answer", json={})
    assert client.get(f"/api/c/call/{cid}/state?t={t}").json["state"] == "live"  # the caller's app checks in
    service._SEEN[cid] = time.time() - 40  # then goes quiet
    state = client.get(f"/api/c/call/{cid}/state?t={t}").json
    assert state["state"] == "ended" and state["missed"]
    assert client.store.get("cases", cid)["call"]["missed_reason"] == "dropped"


def test_board_is_alerted_to_a_missed_call_not_returned(client):
    import time

    cid = client.post("/api/c/call/start", json={"mode": "voice"}).json["id"]
    client.store.patch("cases", cid, lambda c: c["call"].update(started_at=time.time() - 900))
    login(client, "board")
    client.get("/api/staff/feed")  # the unanswered call closes itself and becomes a missed call
    client.store.patch("cases", cid, lambda c: c["call"].update(ended_at=time.time() - 400))
    feed = client.get("/api/staff/feed").json
    assert any(a["type"] == "missed_call" and a["id"] == cid for a in feed["attention"])
