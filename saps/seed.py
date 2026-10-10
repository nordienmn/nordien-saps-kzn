"""Synthetic demo data. Every record carries synthetic=True and the pages say so.

Deterministic (fixed random seed) so a rehearsal and the real showing look the same.
Names, numbers and addresses are invented. Numbers use a non-working range.
"""
import random

from . import geo, service, taxonomy
from .store import now

GENDERS_W = [("female", 46), ("male", 44), ("other", 2), ("undisclosed", 8)]
AGES_W = [("under_18", 6), ("18_24", 16), ("25_34", 28), ("35_49", 24), ("50_64", 12), ("65_plus", 6), ("undisclosed", 8)]

HOUR, DAY = 3600, 86400

PLACES = {
    "durban_central": ["Smith Street, Durban CBD", "Berea Road near the station", "Moore Road, Glenwood", "Point Road, Durban", "Florida Road, Morningside"],
    "umlazi": ["Umlazi V Section", "Umlazi Mega City", "Umlazi M Section", "Umlazi BB"],
    "pinetown": ["Pinetown CBD", "New Germany", "Westmead industrial area", "Hillcrest main road"],
    "chatsworth": ["Chatsworth Unit 3", "Chatsworth Centre", "Bayview Chatsworth"],
    "inanda": ["KwaMashu Highway", "Inanda Road", "Ntuzuma section F", "Phoenix Plaza"],
    "pietermaritzburg": ["Church Street, Pietermaritzburg", "Edendale Road", "Scottsville"],
    "richards_bay": ["Meerensee Richards Bay", "Arboretum"],
    "newcastle": ["Newcastle CBD"],
    "port_shepstone": ["Marine Drive, Port Shepstone"],
    "empangeni": ["Empangeni CBD"],
}
FIRST = ["Thandi", "Sipho", "Nomsa", "Bongani", "Lindiwe", "Mpho", "Zanele", "Sandile", "Ayesha", "Priya", "Kyle", "Naledi", "Themba", "Fatima", "Jabu", "Nokuthula"]
LAST = ["M.", "D.", "N.", "K.", "S.", "P.", "Z.", "C.", "G.", "V."]

CRIMES = [
    ("house_break_in", 6), ("vehicle_theft", 4), ("armed_robbery", 4), ("assault", 3), ("theft", 4),
    ("house_robbery", 2), ("hijacking", 2), ("drugs", 2), ("vandalism", 2), ("suspicious_activity", 2),
    ("business_break_in", 2), ("stock_theft", 1),
]
NOTES = {
    "house_break_in": "Back door forced while the family was out.",
    "vehicle_theft": "Car taken from outside the house overnight.",
    "armed_robbery": "Two men with a firearm at the gate.",
    "assault": "Fight outside a tavern. One person hurt.",
    "theft": "Phone taken at the taxi rank.",
    "house_robbery": "Men entered while the family was home.",
    "hijacking": "Vehicle taken at a traffic light.",
    "drugs": "Selling from a house on the corner.",
    "vandalism": "Shop windows broken overnight.",
    "suspicious_activity": "Men watching houses in the street.",
    "business_break_in": "Spaza shop broken into.",
    "stock_theft": "Goats taken from a kraal.",
}
CLUSTER_WEIGHTS = [("durban_central", 8), ("umlazi", 5), ("pinetown", 4), ("chatsworth", 3), ("inanda", 5), ("pietermaritzburg", 4), ("richards_bay", 2), ("newcastle", 1), ("port_shepstone", 1), ("empangeni", 2)]


def _pick(rng, weighted):
    total = sum(w for _, w in weighted)
    n = rng.uniform(0, total)
    for item, w in weighted:
        n -= w
        if n <= 0:
            return item
    return weighted[-1][0]


def _where(rng, cluster):
    base_lat, base_lon = geo.CLUSTERS[cluster][1], geo.CLUSTERS[cluster][2]
    return round(base_lat + rng.uniform(-0.012, 0.012), 5), round(base_lon + rng.uniform(-0.012, 0.012), 5), rng.choice(PLACES[cluster])


def _person(rng, i):
    return f"{rng.choice(FIRST)} {rng.choice(LAST)}", f"0600000{100 + i:03d}"


def _finish(store, case, rng, age, status, officer):
    """Give a seeded case a believable life after creation."""
    def fn(c):
        c["status"] = status
        if status != "new":
            c["assigned_to"] = officer
            c["first_action_at"] = c["created_at"] + rng.randint(120, 1500)
            c["timeline"].append({"at": c["first_action_at"], "actor": officer, "text": "Accepted the file.", "kind": "action"})
            # most attended files have a station deployed; some are still on the way or on scene
            if c["kind"] in ("crime", "gbv", "sos") and rng.random() < 0.75 and c["lat"] is not None:
                station = geo.nearest_station(c["lat"], c["lon"])
                disp = c["first_action_at"] + rng.randint(30, 600)
                arrived = disp + rng.randint(420, 2700) if (status == "closed" or age > 3 * HOUR) else None
                cleared = arrived + rng.randint(900, 5400) if (arrived and status == "closed") else None
                unit = "FCS unit" if c["kind"] == "gbv" else rng.choice(["Patrol vehicle", "Patrol vehicle", "Patrol vehicle", "Flying Squad", "Detective"])
                dep = {"id": f"D9{rng.randint(1000, 9999)}", "station": station, "station_name": geo.station_name(station), "unit": unit,
                       "status": "cleared" if cleared else ("on_scene" if arrived else "dispatched"), "dispatched_at": disp,
                       "dispatched_by": officer, "arrived_at": arrived, "cleared_at": cleared}
                c["deployments"].append(dep)
                c["timeline"].append({"at": disp, "actor": officer, "text": f"{unit} dispatched from {dep['station_name']}.", "kind": "deployment"})
        if status == "closed":
            c["closed_at"] = c["created_at"] + rng.randint(2 * HOUR, 30 * HOUR)
            c["timeline"].append({"at": c["closed_at"], "actor": officer, "text": "Closed.", "kind": "action"})
        c["updated_at"] = c.get("closed_at") or c.get("first_action_at") or c["created_at"]

    store.patch("cases", case["id"], fn)


def seed(store):
    rng = random.Random(2026)
    t = now()
    service.seed_partners(store)
    officers = ["OP-12", "OP-07", "OP-21", "OP-33"]

    # ---- crime cases over the last six days
    crimes = []
    for key, n in CRIMES:
        crimes += [key] * n
    rng.shuffle(crimes)
    for i, key in enumerate(crimes):
        cluster = _pick(rng, CLUSTER_WEIGHTS)
        lat, lon, place = _where(rng, cluster)
        name, mobile = _person(rng, i)
        age = rng.uniform(0.3 * HOUR, 6 * DAY)
        case = service.create_case(store, {
            "kind": "crime", "type": key, "lat": lat, "lon": lon, "address": place,
            "name": name, "mobile": mobile, "note": NOTES[key],
            "gender": _pick(rng, GENDERS_W), "age_band": _pick(rng, AGES_W), "lang": "zu" if rng.random() < 0.38 else "en",
        }, channel=rng.choice(["app", "app", "app", "whatsapp"]), synthetic=True, created_at=t - age)
        prio = taxonomy.CRIME_TYPES[key][2]
        if age < 3 * HOUR:
            status = rng.choice(["new", "new", "assigned", "in_progress"])
        elif prio in ("critical", "high") and age > 4 * HOUR:
            status = "closed" if rng.random() < 0.95 else "in_progress"  # a couple of genuinely overdue urgent files
        elif age > 2 * DAY:
            status = "closed" if rng.random() < 0.8 else "in_progress"
        else:
            status = rng.choice(["assigned", "in_progress", "in_progress", "closed"])
        _finish(store, case, rng, age, status, rng.choice(officers))

    # ---- unsafe infrastructure (area) reports, two already shared with the municipality
    area_rows = [("broken_light", "durban_central"), ("park", "chatsworth"), ("dark_street", "umlazi"), ("open_ditch", "pinetown"), ("unsafe_building", "pietermaritzburg")]
    for i, (key, cluster) in enumerate(area_rows):
        lat, lon, place = _where(rng, cluster)
        case = service.create_case(store, {"kind": "area", "type": key, "lat": lat, "lon": lon, "address": place, "note": ""}, synthetic=True, created_at=t - rng.uniform(0.5 * DAY, 5 * DAY))
        if i < 2:
            partner = "mun-ethekwini-lights" if key in ("broken_light", "dark_street") else "mun-ethekwini-parks"
            ref = service.create_referral(store, case["id"], "OP-07", {"partner_id": partner}, synthetic=True)
            if i == 0:
                service.update_referral(store, ref["id"], "OP-07", "acknowledged")

    # ---- GBV: one urgent open, two referred, one closed
    gbv_rows = [
        ("umlazi", "no", ["social_worker", "hospital"], "call", 0.4 * HOUR, "new"),
        ("durban_central", "yes", ["shelter"], "sms", 5 * HOUR, "referred"),
        ("inanda", "yes", ["hospital", "social_worker"], "none", 1.2 * DAY, "referred"),
        ("pinetown", "yes", ["social_worker"], "call", 4 * DAY, "closed"),
    ]
    for i, (cluster, safe, wants, pref, age, status) in enumerate(gbv_rows):
        lat, lon, place = _where(rng, cluster)
        name, mobile = _person(rng, 80 + i)
        case = service.create_case(store, {
            "kind": "gbv", "safe_now": safe, "wants": wants, "contact_pref": pref, "know_person": "skip",
            "gender": "female" if rng.random() < 0.9 else "undisclosed", "age_band": rng.choice(["under_18", "18_24", "25_34", "25_34", "35_49", "35_49", "50_64"]), "lang": "zu" if rng.random() < 0.5 else "en",
            "lat": lat, "lon": lon, "address": place, "name": name if pref != "none" else "", "mobile": mobile if pref != "none" else "",
            "note": "Help requested.",
        }, synthetic=True, created_at=t - age)
        if status == "referred":
            pid = "tcc-gizenga" if cluster == "inanda" else "shelter-durban"
            service.create_referral(store, case["id"], "OP-21", {"partner_id": pid, "urgency": "routine", "consent_to_share": pref != "none"}, synthetic=True)
        elif status == "closed":
            service.create_referral(store, case["id"], "OP-21", {"partner_id": "sw-dsd"}, synthetic=True)
            _finish(store, case, rng, age, "closed", "OP-21")

    # ---- three finished calls, with transcripts
    call_rows = [
        ("durban_central", "voice", 1.5 * DAY, [("citizen", "I need help. There are men at my gate."), ("operator", "SAPS KZN control room. Stay inside. Where are you?"), ("citizen", "Berea Road, number fourteen."), ("operator", "A unit is being advised. Stay on the line.")]),
        ("pinetown", "video", 2.5 * DAY, [("citizen", "My car was taken. I am at the Pinetown mall."), ("operator", "Are you hurt?"), ("citizen", "No, I am fine."), ("operator", "Stay where you are. We will send someone.")]),
        ("umlazi", "voice", 3.4 * DAY, [("citizen", "There is a fight outside my house."), ("operator", "Is anyone hurt?"), ("citizen", "I think one person is."), ("operator", "Medical help and a unit are being advised.")]),
    ]
    for i, (cluster, mode, age, lines) in enumerate(call_rows):
        lat, lon, place = _where(rng, cluster)
        name, mobile = _person(rng, 60 + i)
        case = service.create_case(store, {"kind": "call", "mode": mode, "lat": lat, "lon": lon, "address": place, "name": name, "mobile": mobile, "gender": _pick(rng, GENDERS_W), "age_band": _pick(rng, AGES_W)}, synthetic=True, created_at=t - age)
        started = t - age
        secs = rng.randint(70, 240)

        def fn(c, started=started, secs=secs, mode=mode, lines=lines):
            c["call"] = {"state": "ended", "mode": mode, "transport": "demo", "room": "", "started_at": started, "answered_at": started + rng.randint(6, 22), "ended_at": started + secs, "operator": "OP-12", "duration": secs}
            c["transcript"] = [{"at": started + 10 + n * 15, "who": who, "text": text, "src": "caption"} for n, (who, text) in enumerate(lines)]
            c["status"] = "closed"
            c["assigned_to"] = "OP-12"
            c["first_action_at"] = c["call"]["answered_at"]
            c["closed_at"] = started + secs + 600
            c["timeline"].append({"at": started + secs, "actor": "OP-12", "text": f"Call ended. Duration {secs // 60}:{secs % 60:02d}.", "kind": "call"})

        store.patch("cases", case["id"], fn)

    # ---- tips. The desk's tip-off line checks each one; only verified tips are referred to HQ.
    # HQ sees all of them (oversight), plus a short list of verified referrals that need its action.
    tip_rows = [
        ({"type": "drugs", "lat": -29.8587, "lon": 31.0218, "address": "Point Road, Durban", "note": "Dealing from a flat on the corner."}, 3 * DAY, "closed_desk"),
        ({"type": "illegal_firearm", "lat": -29.6006, "lon": 30.3794, "address": "Edendale Road", "note": "A man shows a pistol at the taxi rank."}, 2 * DAY, "directed"),
        ({"type": "planned_crime", "lat": -29.7500, "lon": 30.9800, "address": "KwaMashu", "note": "Talk of a robbery at the weekend market."}, 1.2 * DAY, "acknowledged"),
        ({"type": "stolen_goods", "lat": -29.8167, "lon": 30.8667, "address": "Pinetown CBD", "note": "A house is selling new TVs very cheaply."}, 1 * DAY, "new"),
        ({"type": "wanted_person", "lat": -29.9697, "lon": 30.8864, "address": "Umlazi V Section", "note": "A man on the wanted posters was seen at the spaza shop."}, 5 * HOUR, "verified"),
        ({"type": "drugs", "lat": -29.7000, "lon": 31.0000, "address": "Phoenix Plaza", "note": "Regular late-night handovers behind the shops."}, 1.6 * HOUR, "referred"),
        ({"type": "suspicious_vehicle", "lat": -29.6970, "lon": 30.9460, "address": "KwaMashu Highway", "note": "White van parked near the school for three days with men inside."}, 0.3 * HOUR, "new"),
    ]
    for payload, age, status in tip_rows:
        tip, _ = service.create_tip(store, payload, synthetic=True, created_at=t - age)
        ts = tip["created_at"]

        def fn(x, status=status, ts=ts):
            def ev(at, actor, text, kind):
                x["timeline"].append({"at": at, "actor": actor, "text": text, "kind": kind})

            if status in ("closed_desk", "verified", "referred", "acknowledged", "directed"):
                v_at = ts + 900
                result = "not_verified" if status == "closed_desk" else "verified"
                x["verification"] = {"result": result, "by": "OP-12", "at": v_at, "note": "Checked against known incidents and the area."}
                ev(v_at, "OP-12", ("Verified: " if result == "verified" else "Could not verify: ") + "Checked against known incidents and the area.", "verify")
                if result == "verified":
                    x["status"] = "verified"
            if status == "closed_desk":
                x["status"], x["outcome"], x["closed_at"], x["closed_by"] = "closed", "not_verified", ts + 3600, "desk"
                ev(ts + 3600, "OP-12", "Closed. It could not be verified.", "close")
            if status in ("referred", "acknowledged", "directed"):
                x["status"], x["referred_at"], x["referred_by"] = "referred", ts + 1500, "OP-12"
                ev(ts + 1500, "OP-12", "Verified referral sent to HQ for action.", "refer")
            if status in ("acknowledged", "directed"):
                x["status"] = "acknowledged"
                ev(ts + 2400, "EXEC", "Acknowledged by HQ.", "ack")
            if status == "directed":
                x["status"] = "directed"
                ev(ts + 3000, "EXEC", "Directed to Provincial Crime Intelligence (demo): Gather what you can about the man and report back. Due in 120 min.", "direction")
            x["updated_at"] = x["timeline"][-1]["at"]

        store.patch("tips", tip["id"], fn)
        if status == "directed":
            rid = f"R{store.next_seq('referral'):05d}"
            store.put("referrals", {
                "id": rid, "case_id": tip["id"], "case_ref": tip["ref"], "type": "saps_intel", "partner_id": "unit-intel",
                "partner_name": "Provincial Crime Intelligence (demo)", "status": "acknowledged", "urgency": "routine", "consent_to_share": False,
                "note": "Gather what you can about the man and report back.", "origin": "board",
                "instruction": "Gather what you can about the man and report back.", "created_by": "EXEC", "created_at": ts + 3000,
                "updated_at": ts + 4000, "due_at": ts + 3000 + 7200, "sla_due_at": ts + 3000 + 7200, "synthetic": True,
            })
            store.patch("tips", tip["id"], lambda x, rid=rid: x["referrals"].append(rid))

    service.audit(store, "system", "system", "seed", "", "Synthetic demo data loaded.")
    return store
