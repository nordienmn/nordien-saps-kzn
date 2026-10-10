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


def test_escalation_reaches_the_board_and_can_be_acknowledged(client):
    tip = client.post("/api/c/report", json={"kind": "tip", "type": "drugs", **UMLAZI}).json["ref"]
    login(client)
    assert client.post(f"/api/staff/tip/{tip}/escalate", json={}).json["status"] == "escalated"
    login(client, "board")
    stats = client.get("/api/staff/feed").json["stats"]
    assert stats["escalated_unacknowledged"] >= 1
    assert client.post(f"/api/staff/tip/{tip}/ack", json={}).json["status"] == "acknowledged"
    assert client.get("/api/staff/feed").json["stats"]["escalated_unacknowledged"] == 0


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
