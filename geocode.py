"""
Chennai Circular City DSS -- coordinate to place-name conversion
==================================================================
The raw opportunity data only carries source/destination coordinates
(circular_opportunities.csv: src_lat, src_lon, dst_lat, dst_lon). This module
turns those coordinates into a human-readable place name by matching each
point to the closest known Chennai locality/landmark -- a lightweight, fully
offline "reverse geocode" step that runs live in the app (no external API).

This is intentionally a NEAREST-KNOWN-PLACE match, not a claim of exact
facility identification. Every generated label says "near <place>" for
anything beyond a short walking distance, so it stays honest about what it
actually knows: proximity, not verified identity.
"""
from __future__ import annotations

import math
from functools import lru_cache

# name, latitude, longitude -- well-known Chennai localities and landmarks,
# covering the bounding box of the opportunity dataset (~lat 12.85-13.25,
# lon 80.10-80.33). Coordinates are approximate locality centroids, adequate
# for "which neighbourhood is this near" screening, not survey-grade.
CHENNAI_PLACES: list[tuple[str, float, float]] = [
    ("Marina Beach", 13.0500, 80.2824),
    ("Besant Nagar", 13.0002, 80.2667),
    ("Adyar", 13.0067, 80.2570),
    ("Thiruvanmiyur", 12.9830, 80.2594),
    ("Injambakkam", 12.9308, 80.2530),
    ("Neelankarai", 12.9530, 80.2570),
    ("Sholinganallur", 12.9010, 80.2279),
    ("Semmancheri", 12.8650, 80.2270),
    ("Pallikaranai", 12.9380, 80.2150),
    ("Velachery", 12.9750, 80.2200),
    ("Perungudi", 12.9640, 80.2420),
    ("Guindy", 13.0100, 80.2200),
    ("Kotturpuram", 13.0250, 80.2440),
    ("Nandanam", 13.0330, 80.2380),
    ("Saidapet", 13.0210, 80.2230),
    ("T Nagar", 13.0420, 80.2340),
    ("Mylapore", 13.0340, 80.2700),
    ("Triplicane", 13.0570, 80.2760),
    ("Alwarpet", 13.0330, 80.2540),
    ("R.A. Puram", 13.0300, 80.2610),
    ("Teynampet", 13.0430, 80.2500),
    ("Nungambakkam", 13.0600, 80.2420),
    ("Egmore", 13.0730, 80.2610),
    ("Chetpet", 13.0700, 80.2420),
    ("Kilpauk", 13.0800, 80.2400),
    ("Purasaiwalkam", 13.0850, 80.2570),
    ("Anna Nagar", 13.0850, 80.2100),
    ("Kodambakkam", 13.0520, 80.2240),
    ("Vadapalani", 13.0500, 80.2120),
    ("Ashok Nagar", 13.0380, 80.2100),
    ("Virugambakkam", 13.0530, 80.1930),
    ("Valasaravakkam", 13.0430, 80.1780),
    ("Porur", 13.0380, 80.1580),
    ("Koyambedu", 13.0700, 80.1960),
    ("Nesapakkam (Jafferkhanpet)", 13.0350, 80.1980),
    ("Ambattur", 13.1140, 80.1550),
    ("Avadi", 13.1150, 80.1000),
    ("Red Hills", 13.1900, 80.1830),
    ("Madhavaram", 13.1480, 80.2300),
    ("Manali", 13.1670, 80.2660),
    ("Tiruvottiyur", 13.1600, 80.3000),
    ("Kodungaiyur", 13.1220, 80.2450),
    ("Perambur", 13.1090, 80.2350),
    ("Royapuram", 13.1140, 80.2930),
    ("Tondiarpet", 13.1250, 80.2900),
    ("Washermanpet", 13.1130, 80.2830),
    ("George Town", 13.0940, 80.2870),
    ("Chromepet", 12.9510, 80.1410),
    ("Pallavaram", 12.9670, 80.1500),
    ("Meenambakkam", 12.9930, 80.1710),
    ("St. Thomas Mount", 13.0020, 80.1980),
    ("Nanganallur", 12.9800, 80.1780),
    ("Adambakkam", 12.9820, 80.1980),
    ("Tambaram", 12.9250, 80.1270),
    ("Sembakkam", 12.9210, 80.1670),
    ("Medavakkam", 12.9180, 80.1960),
]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@lru_cache(maxsize=None)
def nearest_place(lat: float, lon: float) -> tuple[str, float]:
    """Returns (place_name, distance_km) of the closest known place. Cached
    since the same coordinates recur often across opportunity pairs."""
    lat_r, lon_r = round(lat, 4), round(lon, 4)
    best_name, best_dist = None, float("inf")
    for name, plat, plon in CHENNAI_PLACES:
        d = _haversine_km(lat_r, lon_r, plat, plon)
        if d < best_dist:
            best_name, best_dist = name, d
    return best_name, round(best_dist, 2)


def place_label(lat: float, lon: float, kind: str) -> str:
    """kind: 'stp', 'waste', or 'park'. Produces the short display name used
    throughout the app, e.g. 'Kodungaiyur STP', 'Green space near Velachery'."""
    place, dist_km = nearest_place(lat, lon)
    suffix = "" if dist_km <= 2.5 else " area"
    if kind == "stp":
        return f"{place}{suffix} STP"
    if kind == "waste":
        return f"{place}{suffix} Waste Facility"
    return f"Green space near {place}{suffix}"


def geocode_trace(lat: float, lon: float, kind: str) -> dict:
    """Full worked example of the coordinate-to-name step, used on the
    Methodology page to show exactly how a label was produced."""
    place, dist_km = nearest_place(lat, lon)
    return {
        "raw_coordinate": f"{lat:.4f}, {lon:.4f}",
        "matched_place": place,
        "distance_km": dist_km,
        "final_label": place_label(lat, lon, kind),
    }
