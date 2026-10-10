base = r"C:\MN Work\claude\SAPS_KZN"


def edit(path, pairs):
    s = open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert old in s, (path.split("\\")[-1], old[:80])
        s = s.replace(old, new, 1)
    open(path, "w", encoding="utf-8").write(s)


# ================================================================ service: accept anything, say what is missing
edit(base + r"\saps\service.py", [
    ('''    name = clean(payload.get("name"), 80)
    mobile = clean_mobile(payload.get("mobile"))
    note = clean(payload.get("note"), MAX_NOTE)''', '''    missing = []  # what the citizen did not give. A report is NEVER refused for being incomplete; the desk sees what is missing.
    name = clean(payload.get("name"), 80)
    try:
        mobile = clean_mobile(payload.get("mobile"))
    except Invalid:
        mobile = ""
        missing.append("a valid mobile number")
    note = clean(payload.get("note"), MAX_NOTE)'''),
    ('''        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.CRIME_TYPES:
            raise Invalid("Choose the type of crime.", "type")
        if lat is None and not address:
            raise Invalid("Add a place, or use your current location.", "place")
        priority = taxonomy.CRIME_TYPES[label_key][2]''', '''        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.CRIME_TYPES:
            label_key = "other"
            missing.append("the type of crime")
        if lat is None and not address:
            missing.append("the place")
        priority = taxonomy.CRIME_TYPES[label_key][2]'''),
    ('''            try:
                occurred = float(occurred) / 1000.0
            except (TypeError, ValueError):
                raise Invalid("That time does not look right.", "time")
            if not now() - 30 * 86400 <= occurred <= now() + 3600:
                raise Invalid("That time does not look right.", "time")
            extra["occurred_at"] = occurred''', '''            try:
                occurred = float(occurred) / 1000.0
                if now() - 30 * 86400 <= occurred <= now() + 3600:
                    extra["occurred_at"] = occurred
            except (TypeError, ValueError):
                pass  # an unreadable time is simply left out'''),
    ('''        if safe not in ("yes", "no", "unsure"):
            raise Invalid("Please tell us if you are safe right now.", "safe_now")''', '''        if safe not in ("yes", "no", "unsure"):
            safe = "unsure"
            missing.append("whether they are safe right now")'''),
    ('''        if contact_pref in ("call", "sms") and not mobile:
            raise Invalid("Add a number we may use, or choose 'Do not contact me'.", "mobile")''', '''        if contact_pref in ("call", "sms") and not mobile:
            contact_pref = "none"
            missing.append("a number to reach them")'''),
    ('''        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.AREA_TYPES:
            raise Invalid("Choose what is unsafe.", "type")
        if lat is None and not address:
            raise Invalid("Add a place, or use your current location.", "place")
        priority = "low"''', '''        label_key = clean(payload.get("type"), 40)
        if label_key not in taxonomy.AREA_TYPES:
            label_key = "other"
            missing.append("what is unsafe")
        if lat is None and not address:
            missing.append("the place")
        priority = "low"'''),
    # the case records what is missing
    ('''        "registered": registered,
        "home_address": home_address,''', '''        "registered": registered,
        "incomplete": bool(missing),
        "missing": missing,
        "home_address": home_address,'''),
    # tips: accept anything
    ('''    key = clean(payload.get("type"), 40)
    if key not in taxonomy.TIP_TYPES:
        raise Invalid("Choose what you are reporting.", "type")
    lat, lon, address = clean_point(payload)
    if lat is None and not address:
        raise Invalid("Add a place, or use your current location.", "place")
    code =''', '''    missing = []
    key = clean(payload.get("type"), 40)
    if key not in taxonomy.TIP_TYPES:
        key = "other"
        missing.append("what is being reported")
    lat, lon, address = clean_point(payload)
    if lat is None and not address:
        missing.append("the place")
    code ='''),
    ('''        "verification": None,
        "referred_at": None,''', '''        "incomplete": bool(missing),
        "missing": missing,
        "verification": None,
        "referred_at": None,'''),
    # photos that cannot be read are skipped, never a reason to refuse the report
    ('''    for i, data_url in enumerate(photos[:MAX_PHOTOS]):
        mid = f"{case['id']}-p{i + 1}"
        store.put("media", {"id": mid, "case_id": case["id"], "type": "photo", "data_url": _check_image(data_url, MAX_PHOTO_BYTES)})
        media.append({"id": mid, "type": "photo"})''', '''    for i, data_url in enumerate(photos[:MAX_PHOTOS]):
        mid = f"{case['id']}-p{i + 1}"
        try:
            store.put("media", {"id": mid, "case_id": case["id"], "type": "photo", "data_url": _check_image(data_url, MAX_PHOTO_BYTES)})
            media.append({"id": mid, "type": "photo"})
        except Invalid:
            continue  # an unreadable picture is left out; the report still goes through'''),
    # summaries and details show it
    ('''        "referrals": len(case["referrals"]),
        "deployed":''', '''        "referrals": len(case["referrals"]),
        "incomplete": case.get("incomplete", False), "missing": case.get("missing", []),
        "deployed":'''),
    ('''        "outcome": tip.get("outcome", ""), "referrals": len(tip.get("referrals", [])), "has_media": bool(tip.get("media")),''', '''        "outcome": tip.get("outcome", ""), "referrals": len(tip.get("referrals", [])), "has_media": bool(tip.get("media")),
        "incomplete": tip.get("incomplete", False), "missing": tip.get("missing", []),'''),
])

# ================================================================ tests: incomplete reports are accepted and flagged
p = base + r"\tests\test_api.py"
s = open(p, encoding="utf-8").read()
s = s.replace('''def test_crime_report_needs_type_and_place(client):
    assert client.post("/api/c/report", json={"kind": "crime", "address": "x"}).status_code == 422
    assert client.post("/api/c/report", json={"kind": "crime", "type": "theft"}).status_code == 422''', '''def test_an_incomplete_crime_report_is_accepted_and_flagged(client):
    a = client.post("/api/c/report", json={"kind": "crime", "address": "x"})
    b = client.post("/api/c/report", json={"kind": "crime", "type": "theft"})
    c0 = client.post("/api/c/report", json={"kind": "crime"})
    assert a.status_code == b.status_code == c0.status_code == 200
    ca = client.store.get("cases", a.json["id"])
    assert ca["incomplete"] and ca["missing"] == ["the type of crime"] and ca["label_key"] == "other"
    cb = client.store.get("cases", b.json["id"])
    assert cb["incomplete"] and cb["missing"] == ["the place"] and cb["cluster"] == "unlocated"
    assert set(client.store.get("cases", c0.json["id"])["missing"]) == {"the type of crime", "the place"}''')
s = s.replace('''def test_gbv_requires_safety_answer_and_number_when_contact_wanted(client):
    assert client.post("/api/c/report", json={"kind": "gbv"}).status_code == 422
    assert client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call"}).status_code == 422''', '''def test_gbv_help_goes_through_even_with_nothing_filled_in(client):
    bare = client.post("/api/c/report", json={"kind": "gbv"})
    assert bare.status_code == 200
    case = client.store.get("cases", bare.json["id"])
    assert case["incomplete"] and case["safe_now"] == "unsure" and case["needs"]
    nocall = client.post("/api/c/report", json={"kind": "gbv", "safe_now": "no", "contact_pref": "call"})
    assert nocall.status_code == 200 and client.store.get("cases", nocall.json["id"])["contact_pref"] == "none"''')
s = s.replace('''def test_bad_mobile_rejected(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "mobile": "abc", **UMLAZI})
    assert r.status_code == 422 and r.json["field"] == "mobile"''', '''def test_a_bad_mobile_number_does_not_stop_the_report(client):
    r = client.post("/api/c/report", json={"kind": "crime", "type": "theft", "mobile": "abc", **UMLAZI})
    assert r.status_code == 200
    case = client.store.get("cases", r.json["id"])
    assert case["mobile"] == "" and "a valid mobile number" in case["missing"]''')
s = s.replace('''def test_photo_must_be_a_real_image(client):
    bad = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI, "photos": ["data:image/jpeg;base64,AAAA"]})
    assert bad.status_code == 422''', '''def test_an_unreadable_photo_is_left_out_but_the_report_goes_through(client):
    bad = client.post("/api/c/report", json={"kind": "crime", "type": "theft", **UMLAZI, "photos": ["data:image/jpeg;base64,AAAA"]})
    assert bad.status_code == 200 and client.store.get("cases", bad.json["id"])["media"] == []''')
s += '''


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
'''
# the old test that expected a tip without a place to fail
s = s.replace('''def test_anonymous_tip_stores_no_identity_and_returns_a_code(client):''', '''def test_anonymous_tip_stores_no_identity_and_returns_a_code(client):''')
open(p, "w", encoding="utf-8").write(s)
print("lenient backend ok")
