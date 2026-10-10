"""Categories shown to citizens and used by the desk and board filters.

isiZulu labels are a first draft and NEED A NATIVE-SPEAKER CHECK before any real use.
"""

# key: (English, isiZulu, priority, routes_to_gbv)
CRIME_TYPES = {
    "murder": ("Murder", "Ukubulala", "critical", False),
    "attempted_murder": ("Attempted murder", "Ukuzama ukubulala", "critical", False),
    "sexual_offence": ("Sexual offence", "Icala lokuhlukumeza ngokocansi", "critical", True),
    "domestic_violence": ("Domestic violence", "Udlame lwasekhaya", "high", True),
    "assault": ("Assault", "Ukushaya", "high", False),
    "armed_robbery": ("Armed robbery", "Ukuphanga ngezikhali", "high", False),
    "house_robbery": ("House robbery", "Ukuphangwa kwekhaya", "high", False),
    "hijacking": ("Hijacking", "Ukuhlwithwa kwemoto", "high", False),
    "kidnapping": ("Kidnapping", "Ukuthumba", "critical", False),
    "house_break_in": ("House break-in", "Ukugqekezwa kwendlu", "normal", False),
    "business_break_in": ("Business break-in", "Ukugqekezwa kwebhizinisi", "normal", False),
    "vehicle_theft": ("Vehicle theft", "Ukutshontshwa kwemoto", "normal", False),
    "theft": ("Theft", "Ukuntshontsha", "normal", False),
    "stock_theft": ("Stock theft", "Ukutshontshwa kwemfuyo", "normal", False),
    "drugs": ("Drugs", "Izidakamizwa", "normal", False),
    "vandalism": ("Vandalism", "Ukonakalisa impahla", "low", False),
    "suspicious_activity": ("Suspicious activity", "Umsebenzi osolisayo", "low", False),
    "other": ("Other", "Okunye", "normal", False),
}

TIP_TYPES = {
    "suspicious_vehicle": ("Suspicious vehicle", "Imoto esolisayo"),
    "drugs": ("Drug dealing", "Ukudayiswa kwezidakamizwa"),
    "illegal_firearm": ("Illegal firearm", "Isibhamu esingekho emthethweni"),
    "stolen_goods": ("Stolen goods", "Impahla ebiwe"),
    "planned_crime": ("Crime being planned", "Icala elicatshangelwayo"),
    "wanted_person": ("Wanted person", "Umuntu odingwayo"),
    "other": ("Other", "Okunye"),
}

AREA_TYPES = {
    "broken_light": ("Broken streetlight", "Isibani somgwaqo esilimele"),
    "dark_street": ("Dark street", "Umgwaqo omnyama"),
    "open_ditch": ("Open ditch or drain", "Umsele ovulekile"),
    "overgrown_veld": ("Overgrown veld or path", "Utshani obude"),
    "unsafe_building": ("Abandoned or unsafe building", "Isakhiwo esishiyiwe"),
    "park": ("Unsafe park", "Ipaki engaphephile"),
    "taxi_rank": ("Unsafe taxi rank", "Ikhumbi lamatekisi elingaphephile"),
    "school_grounds": ("School grounds", "Inkundla yesikole"),
    "illegal_dumping": ("Illegal dumping", "Ukulahlwa kwemfucuza"),
    "other": ("Other", "Okunye"),
}

# Referral partner kinds
REFERRAL_TYPES = {
    "gbv_tcc": "Thuthuzela Care Centre",
    "fcs_unit": "SAPS FCS unit",
    "shelter": "Shelter",
    "health": "Hospital or clinic",
    "social_worker": "Social worker",
    "transport": "Transport",
    "municipal": "Municipality",
    "saps_cluster": "SAPS cluster commander",
    "saps_flying": "SAPS Flying Squad",
    "saps_intel": "SAPS Crime Intelligence",
    "saps_detective": "SAPS Detective Service",
    "forensic_supply": "SAPS evidence kit supply",
}
# Units inside SAPS. HQ DIRECTS these; everything else is a REFERRAL out of SAPS.
SAPS_UNIT_TYPES = {"saps_cluster", "saps_flying", "saps_intel", "saps_detective", "fcs_unit", "forensic_supply"}

# Optional, self-described. Collected only when the citizen chooses to give them.
GENDERS = ["female", "male", "other", "undisclosed"]
AGE_BANDS = ["under_18", "18_24", "25_34", "35_49", "50_64", "65_plus", "undisclosed"]
LANGUAGES = ["en", "zu"]
UNIT_KINDS = ["Patrol vehicle", "Flying Squad", "FCS unit", "Detective", "Dog unit", "Public order"]
DEPLOY_STATES = ["dispatched", "on_scene", "cleared"]

STATUSES = ["new", "assigned", "in_progress", "referred", "closed"]
KINDS = ["call", "crime", "gbv", "sos", "area"]  # tips live in their own collection
PRIORITY_ORDER = {"critical": 0, "high": 1, "normal": 2, "low": 3}

# Kinds whose records are access-restricted and logged when opened
RESTRICTED_KINDS = {"gbv", "sos"}


def crime_label(key, lang="en"):
    row = CRIME_TYPES.get(key)
    if not row:
        return key
    return row[1] if lang == "zu" else row[0]


def options(table, lang="en"):
    idx = 1 if lang == "zu" else 0
    return [{"key": k, "label": v[idx]} for k, v in table.items()]


# What a GBV file may need on the ground. The station must say, for each one, whether it has it.
# D1 is the adult sexual assault evidence kit and D7 the kit for a child under 13 (the names SAPS uses).
GBV_NEEDS = {
    "female_officer": "Female officer to attend",
    "counsellor": "Counsellor or victim support",
    "kit_d1": "Evidence kit for an adult (D1 rape kit)",
    "kit_d7": "Evidence kit for a child under 13 (D7 rape kit)",
    "medical": "Medical examination and treatment (including PEP within 72 hours)",
    "vfr": "Victim Friendly Room",
    "transport": "Transport to a care centre",
    "shelter": "A safe place to stay",
    "protection_order": "Help with a protection order",
}
# Who is asked when a station says it does not have something.
GBV_FALLBACK = {
    "female_officer": "cluster", "counsellor": "sw-counsellor", "kit_d1": "kit-supply", "kit_d7": "kit-supply",
    "medical": "health-addington", "vfr": "tcc-gizenga", "transport": "ride-demo", "shelter": "shelter-durban", "protection_order": "sw-fam",
}
