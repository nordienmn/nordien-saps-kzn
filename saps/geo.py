"""Station clusters and nearest-cluster lookup.

Centres are approximate town centres, good enough for a demo map. They are NOT official SAPS
cluster boundaries; the demo says so wherever the map is shown.
"""
import math

# key: (display name, lat, lon)
CLUSTERS = {
    "durban_central": ("Durban Central", -29.8587, 31.0218),
    "pinetown": ("Pinetown", -29.8167, 30.8667),
    "umlazi": ("Umlazi", -29.9697, 30.8864),
    "chatsworth": ("Chatsworth", -29.9175, 30.8870),
    "inanda": ("Inanda", -29.6970, 30.9460),
    "pietermaritzburg": ("Pietermaritzburg", -29.6006, 30.3794),
    "richards_bay": ("Richards Bay", -28.7830, 32.0377),
    "newcastle": ("Newcastle", -27.7577, 29.9318),
    "port_shepstone": ("Port Shepstone", -30.7410, 30.4550),
    "empangeni": ("Empangeni", -28.7500, 31.9000),
}
UNLOCATED = "unlocated"

# Rough bounding box of KwaZulu-Natal, used to reject coordinates that are plainly elsewhere.
KZN_BOX = (-31.2, -26.7, 28.8, 33.0)  # lat_min, lat_max, lon_min, lon_max


def name(cluster_key):
    if cluster_key == UNLOCATED:
        return "Location not shared"
    return CLUSTERS.get(cluster_key, (cluster_key,))[0]


def valid_point(lat, lon):
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return KZN_BOX[0] <= lat <= KZN_BOX[1] and KZN_BOX[2] <= lon <= KZN_BOX[3]


def _hav(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_cluster(lat, lon):
    """Return the cluster key nearest to the point, or UNLOCATED if the point is unusable."""
    if not valid_point(lat, lon):
        return UNLOCATED
    lat, lon = float(lat), float(lon)
    return min(CLUSTERS, key=lambda k: _hav(lat, lon, CLUSTERS[k][1], CLUSTERS[k][2]))


def cluster_options():
    return [{"key": k, "name": v[0], "lat": v[1], "lon": v[2]} for k, v in CLUSTERS.items()]
