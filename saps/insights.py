"""Decision data for HQ. Everything here is grouped. No names, numbers, photos or free text.

Privacy rules applied to every grouped table:
- A cell with fewer than 5 records is shown as "<5", never as a number (small-number rule).
- GBV and SOS records never appear as map points. They appear only as a count per cluster, banded.
- Anonymous tips never appear as map points either; they are counted per cluster.
- Gender and age are optional, self-described and only counted. Anything not given is "undisclosed".
"""
from collections import Counter
from datetime import datetime, timedelta, timezone

from . import geo, service, taxonomy
from .store import now

LOCAL = timezone(timedelta(hours=2))  # South Africa
SMALL = 5
DAY = 86400

# Published national 10111 figures, for context. Source: a written parliamentary reply (question CW502),
# 8 July 2026, via the Parliamentary Monitoring Group. Read from search results; the reply PDF itself was not opened.
REFERENCE_10111 = {
    "title": "National 10111 response times, as reported to Parliament",
    "as_of": "30 April 2026",
    "alpha_min": 28.5, "bravo_min": 25.75, "charlie_min": 24.57,
    "source": "https://pmg.org.za/committee-question/40584/",
    "note": "Reported national average response times. They measure the police response, not how fast a call is answered.",
}


def _cell(n):
    return n if n >= SMALL or n == 0 else "<5"


def _avg(values):
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values)) if values else 0


def _gender_label(key):
    return {"female": "Female", "male": "Male", "other": "Other / self-described", "undisclosed": "Not given"}.get(key, key)


def _age_label(key):
    return {"under_18": "Under 18", "18_24": "18-24", "25_34": "25-34", "35_49": "35-49", "50_64": "50-64", "65_plus": "65+", "undisclosed": "Not given"}.get(key, key)


def build(cases, tips, refs):
    t = now()
    week_ago, two_weeks = t - 7 * DAY, t - 14 * DAY
    people = [c for c in cases if c["kind"] in ("crime", "gbv", "sos", "call")]  # files that concern a person
    out = {}

    # ---- crime types, with the previous seven days for comparison
    this_week, last_week = Counter(), Counter()
    for c in cases:
        if c["kind"] == "area":
            continue
        key = c["label_key"]
        if c["created_at"] >= week_ago:
            this_week[key] += 1
        elif c["created_at"] >= two_weeks:
            last_week[key] += 1
    by_type = []
    for key in sorted(set(this_week) | set(last_week), key=lambda k: -(this_week[k] + last_week[k]))[:12]:
        label = service.case_label({"kind": "crime", "label_key": key})
        restricted = key in ("gbv_request", "weather_sos", "domestic_violence", "sexual_offence")
        by_type.append({"key": key, "label": label, "restricted": restricted,
                        "this_week": _cell(this_week[key]) if restricted else this_week[key],
                        "last_week": _cell(last_week[key]) if restricted else last_week[key],
                        "_n": this_week[key]})
    out["by_type"] = by_type

    # ---- gender and age (grouped, small-number rule applied)
    g, a = Counter(c.get("gender", "undisclosed") for c in people), Counter(c.get("age_band", "undisclosed") for c in people)
    out["gender"] = [{"key": k, "label": _gender_label(k), "n": _cell(g[k])} for k in taxonomy.GENDERS]
    out["age"] = [{"key": k, "label": _age_label(k), "n": _cell(a[k])} for k in taxonomy.AGE_BANDS]
    cross = {}
    for c in people:
        if c["kind"] in ("gbv", "sos"):
            tkey = "gbv"
        else:
            tkey = c["label_key"]
        cross.setdefault(tkey, Counter())[c.get("gender", "undisclosed")] += 1
    top_types = sorted(cross, key=lambda k: -sum(cross[k].values()))[:8]
    out["crime_by_gender"] = [
        {"label": "GBV and SOS" if k == "gbv" else service.case_label({"kind": "crime", "label_key": k}),
         **{gk: _cell(cross[k][gk]) for gk in taxonomy.GENDERS}}
        for k in top_types
    ]
    ag = {}
    for c in people:
        ag.setdefault(c.get("age_band", "undisclosed"), Counter())[c.get("gender", "undisclosed")] += 1
    out["age_by_gender"] = [{"label": _age_label(k), **{gk: _cell(ag.get(k, Counter())[gk]) for gk in taxonomy.GENDERS}} for k in taxonomy.AGE_BANDS]

    # ---- when
    hours, days = [0] * 24, [0] * 7
    for c in cases:
        if c["kind"] == "area":
            continue
        d = datetime.fromtimestamp(c["created_at"], LOCAL)
        hours[d.hour] += 1
        days[d.weekday()] += 1
    out["by_hour"] = hours
    out["by_weekday"] = days

    # ---- channels, language
    out["channels"] = dict(Counter(c["channel"] for c in cases))
    out["languages"] = dict(Counter(c.get("language", "en") for c in people))

    # ---- calls (the reason this app exists: calls answered, fast)
    calls = [c for c in cases if c.get("call")]
    answered = [c for c in calls if c["call"].get("answered_at")]
    waits = [c["call"]["answered_at"] - c["call"]["started_at"] for c in answered]
    abandoned = [c for c in calls if c["call"]["state"] == "ended" and not c["call"].get("answered_at")]
    out["calls"] = {
        "total": len(calls), "answered": len(answered), "abandoned": len(abandoned),
        "ringing_now": sum(1 for c in calls if c["call"]["state"] == "ringing"),
        "avg_wait_s": _avg(waits), "within_30s_pct": round(100 * sum(1 for w in waits if w <= 30) / len(calls)) if calls else 0,
        "abandoned_pct": round(100 * len(abandoned) / len(calls)) if calls else 0,
    }
    out["reference_10111"] = REFERENCE_10111

    # ---- deployments: which stations are being sent, how fast
    deps = []
    for c in cases:
        for d in c.get("deployments", []):
            deps.append((c, d))
    active = [(c, d) for c, d in deps if d["status"] != "cleared"]
    out["deployments_active"] = [
        {"case_ref": c["ref"], "label": service.case_label(c), "cluster_name": geo.name(c["cluster"]), "station": d["station_name"],
         "station_key": d["station"], "unit": d["unit"], "status": d["status"], "since": d["dispatched_at"], "kind": c["kind"]}
        for c, d in sorted(active, key=lambda x: x[1]["dispatched_at"])
    ][:40]
    recent = [(c, d) for c, d in deps if d["dispatched_at"] >= week_ago]
    by_station = {}
    for c, d in recent:
        row = by_station.setdefault(d["station"], {"station": d["station_name"], "key": d["station"], "cluster": geo.name(geo.STATIONS[d["station"]][1]), "dispatched": 0, "_disp": [], "_arr": []})
        row["dispatched"] += 1
        row["_disp"].append(d["dispatched_at"] - c["created_at"])
        if d["arrived_at"]:
            row["_arr"].append(d["arrived_at"] - d["dispatched_at"])
    stations = []
    for row in by_station.values():
        stations.append({"station": row["station"], "key": row["key"], "cluster": row["cluster"], "dispatched": row["dispatched"],
                         "avg_dispatch_s": _avg(row["_disp"]), "avg_arrival_s": _avg(row["_arr"])})
    out["deployments_by_station"] = sorted(stations, key=lambda r: -r["dispatched"])
    all_disp = [d["dispatched_at"] - c["created_at"] for c, d in recent]
    all_arr = [d["arrived_at"] - d["dispatched_at"] for c, d in recent if d["arrived_at"]]
    out["response"] = {"avg_to_dispatch_s": _avg(all_disp), "avg_to_arrival_s": _avg(all_arr), "deployments_7d": len(recent), "active": len(active)}

    # demand against deployment, per cluster (where is the province under-served?)
    demand = {k: 0 for k in geo.CLUSTERS}
    sent = {k: 0 for k in geo.CLUSTERS}
    for c in cases:
        if c["kind"] != "area" and c["created_at"] >= week_ago and c["cluster"] in demand:
            demand[c["cluster"]] += 1
    for c, d in recent:
        if c["cluster"] in sent:
            sent[c["cluster"]] += 1
    rows = []
    for k in geo.CLUSTERS:
        rows.append({"key": k, "name": geo.name(k), "incidents": demand[k], "deployments": sent[k],
                     "per_deployment": round(demand[k] / sent[k], 1) if sent[k] else (demand[k] if demand[k] else 0)})
    out["demand_vs_deployment"] = rows

    # ---- where callers and reporters are (points for the map)
    points = []
    for c in cases:
        if c["lat"] is None or c["restricted"]:
            continue
        points.append({"lat": round(c["lat"], 3), "lon": round(c["lon"], 3), "kind": c["kind"], "label": service.case_label(c), "priority": c["priority"],
                       "status": c["status"], "cluster": geo.name(c["cluster"]), "at": c["created_at"]})
    out["points"] = points[:400]
    out["restricted_by_cluster"] = {k: ("0" if n == 0 else "<5" if n < SMALL else "5+") for k, n in (
        (k, sum(1 for c in cases if c["cluster"] == k and c["restricted"]) + sum(1 for x in tips if x["cluster"] == k)) for k in geo.CLUSTERS)}
    out["stations"] = geo.station_options()

    # ---- referrals out of SAPS, and directions inside it
    external = [r for r in refs if r.get("origin") != "board"]
    out["referrals"] = {
        "out": len(external),
        "by_type": dict(Counter(taxonomy.REFERRAL_TYPES.get(r["type"], r["type"]) for r in external)),
        "by_status": dict(Counter(r["status"] for r in external)),
        "avg_to_acknowledge_s": _avg([r["updated_at"] - r["created_at"] for r in external if r["status"] in ("acknowledged", "completed")]),
        "completed_pct": round(100 * sum(1 for r in external if r["status"] == "completed") / len(external)) if external else 0,
        "directions": len([r for r in refs if r.get("origin") == "board"]),
        "directions_overdue": sum(1 for r in refs if r.get("origin") == "board" and r["status"] != "completed" and r.get("due_at") and t > r["due_at"]),
    }

    # ---- the anonymous tip pipeline: desk checks, HQ oversees
    verified_at = [x["verification"]["at"] - x["created_at"] for x in tips if x.get("verification")]
    hq_wait = []
    for x in tips:
        if x.get("referred_at"):
            for e in x["timeline"]:
                if e["kind"] == "ack":
                    hq_wait.append(e["at"] - x["referred_at"])
                    break
    pipeline = {k: sum(1 for x in tips if x["status"] == k) for k in ("new", "verified", "referred", "acknowledged", "directed", "closed")}
    out["tips"] = {
        "total": len(tips), "pipeline": pipeline,
        "by_type": dict(Counter(service.tip_label(x) for x in tips)),
        "avg_to_verify_s": _avg(verified_at), "avg_hq_ack_s": _avg(hq_wait),
        "unverified_over_1h": sum(1 for x in tips if x["status"] == "new" and t - x["created_at"] > 3600),
        "verified_pct": round(100 * sum(1 for x in tips if x.get("verification") and x["verification"]["result"] == "verified") / len(tips)) if tips else 0,
    }

    # ---- 14 day trend by kind
    series = []
    for i in range(13, -1, -1):
        lo, hi = t - (i + 1) * DAY, t - i * DAY
        row = {"day": datetime.fromtimestamp(hi, LOCAL).strftime("%d %b")}
        for kind in ("call", "crime", "gbv", "sos", "area"):
            row[kind] = sum(1 for c in cases if c["kind"] == kind and lo <= c["created_at"] < hi)
        row["tip"] = sum(1 for x in tips if lo <= x["created_at"] < hi)
        series.append(row)
    out["trend"] = series

    out["signals"] = signals(out)
    for row in out["by_type"]:
        row.pop("_n", None)
    return out


def signals(d):
    """Plain-language prompts for decision makers, each with the number behind it."""
    notes = []
    rows = [r for r in d["demand_vs_deployment"] if r["incidents"] >= 3]
    if rows:
        total_inc = sum(r["incidents"] for r in d["demand_vs_deployment"])
        total_dep = sum(r["deployments"] for r in d["demand_vs_deployment"])
        avg = total_inc / total_dep if total_dep else 0
        worst = max(rows, key=lambda r: r["per_deployment"])
        if worst["per_deployment"] > max(avg * 1.4, 2):
            notes.append({"level": "attention", "text": f"{worst['name']}: {worst['incidents']} incidents and {worst['deployments']} deployments in 7 days ({worst['per_deployment']} per deployment, province {avg:.1f}). Consider more cover."})
    slow = [s for s in d["deployments_by_station"] if s["dispatched"] >= 3 and s["avg_arrival_s"]]
    if slow:
        w = max(slow, key=lambda s: s["avg_arrival_s"])
        notes.append({"level": "info", "text": f"Slowest average arrival: {w['station']} ({round(w['avg_arrival_s'] / 60)} min over {w['dispatched']} deployments)."})
    c = d["calls"]
    if c["total"]:
        notes.append({"level": "good" if c["within_30s_pct"] >= 80 else "attention", "text": f"{c['within_30s_pct']}% of calls were answered within 30 seconds; average wait {c['avg_wait_s']} s."})
    t = d["tips"]
    if t["unverified_over_1h"]:
        notes.append({"level": "attention", "text": f"{t['unverified_over_1h']} anonymous tip(s) have been unverified at the desk for over an hour."})
    peak = max(range(24), key=lambda h: d["by_hour"][h]) if sum(d["by_hour"]) else None
    if peak is not None:
        notes.append({"level": "info", "text": f"Busiest hour: {peak:02d}:00 to {peak + 1:02d}:00 ({d['by_hour'][peak]} reports in the period)."})
    return notes
