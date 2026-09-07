"""
Chennai Circular City DSS -- shared decision logic
====================================================
This module turns the raw scored pairs (circular_opportunities.csv) into
plain-language, decision-first output: a priority band (HIGH / MODERATE /
LOW), a short explanation, and a recommended next action -- instead of a
bare number.

Nothing here changes the underlying scoring model (still Resource 30% /
Demand 25% / Climate 20% / Feasibility 15% / Infrastructure 10% by
default) -- it just translates it for a non-GIS reader.
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import streamlit as st

from geocode import place_label, nearest_place, geocode_trace

DATA_PATH = Path(__file__).parent / "circular_opportunities.csv"

PATHWAY_LABEL = {"water": "Water Reuse", "waste": "Organic Waste", "combined": "Combined"}
PATHWAY_QUESTION = {
    "water": "Where can treated wastewater potentially support nearby green infrastructure?",
    "waste": "Where can organic-waste infrastructure support local circularity?",
}

DEFAULT_WEIGHTS = {"resource": 30, "demand": 25, "climate": 20, "feasibility": 15, "infrastructure": 10}

WEIGHT_PRESETS = {
    "Balanced assessment": DEFAULT_WEIGHTS,
    "Prioritise climate resilience": {"resource": 20, "demand": 20, "climate": 40, "feasibility": 10, "infrastructure": 10},
    "Prioritise sites ready to act now": {"resource": 25, "demand": 15, "climate": 10, "feasibility": 20, "infrastructure": 30},
    "Prioritise nearby demand": {"resource": 15, "demand": 40, "climate": 15, "feasibility": 25, "infrastructure": 5},
}

# Colors for st.badge() -- must be one of Streamlit's fixed color names.
PRIORITY_BADGE_COLOR = {"HIGH": "red", "MODERATE": "orange", "LOW": "green"}

# Hex colors for the maps (muted, professional palette).
PRIORITY_HEX = {"HIGH": "#B23B3B", "MODERATE": "#C98A2C", "LOW": "#2F7D4F"}

PRIORITY_EXPLANATION = {
    "HIGH": "This location combines a suitable resource, nearby demand, real climate need, and a short, "
            "practical spatial connection. It is a strong candidate for further feasibility assessment.",
    "MODERATE": "This location has genuine potential, but at least one supporting factor, such as distance, "
                "nearby demand, or climate need, is only moderate. Worth a closer look before committing.",
    "LOW": "This is not a strong circular-economy opportunity right now, usually because the source and "
           "destination are far apart or the demand/climate need is weak. Not an immediate priority.",
}

DECISION_STATUS = {
    "HIGH": "Candidate for further feasibility assessment",
    "MODERATE": "Worth monitoring, revisit as infrastructure or conditions change",
    "LOW": "Not currently a priority",
}


@st.cache_data
def load_raw() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH)
    df = df.reset_index(drop=True)
    df["opportunity_id"] = df.index + 1

    # ---- coordinate -> place name conversion ----
    # The source file only carries raw coordinates (e.g. "Waste site at
    # 13.09, 80.22"). Each unique point is matched once to the closest known
    # Chennai place (see geocode.py: nearest_place / place_label), and the
    # result is cached and reused for every row that shares that coordinate.
    src_kind = {"water": "stp", "waste": "waste"}
    src_unique = df[["src_lat", "src_lon", "pathway"]].drop_duplicates(subset=["src_lat", "src_lon"])
    src_map = {
        (row.src_lat, row.src_lon): place_label(row.src_lat, row.src_lon, src_kind[row.pathway])
        for row in src_unique.itertuples()
    }
    df["source_label"] = [src_map[(la, lo)] for la, lo in zip(df.src_lat, df.src_lon)]

    dst_unique = df[["dst_lat", "dst_lon"]].drop_duplicates()
    dst_map = {(la, lo): place_label(la, lo, "park") for la, lo in zip(dst_unique.dst_lat, dst_unique.dst_lon)}
    df["dest_label"] = [dst_map[(la, lo)] for la, lo in zip(df.dst_lat, df.dst_lon)]

    return df


def compute_score(df: pd.DataFrame, weights: dict) -> pd.Series:
    wsum = sum(weights.values()) or 1
    return (
        weights["resource"] * df["resource"]
        + weights["demand"] * df["demand"]
        + weights["climate"] * df["climate"]
        + weights["feasibility"] * df["feasibility"]
        + weights["infrastructure"] * df["infrastructure"]
    ) / wsum


def recompute_feasibility(df: pd.DataFrame, max_dist_km: float) -> pd.Series:
    """Re-derive spatial feasibility against a chosen search radius, same
    logic as priority_score.py's f = 1 - (d/max_dist)*0.8, clipped at 0."""
    return (1 - (df["distance_m"] / (max_dist_km * 1000)) * 0.8).clip(lower=0)


@st.cache_data
def pathway_cutoffs(_df: pd.DataFrame, pathway: str, weights_tuple: tuple) -> tuple[float, float]:
    """Terciles computed on the FULL, city-wide set for that pathway (not the
    currently filtered subset), so 'HIGH priority' always means 'top third
    of opportunities city-wide for this pathway' -- it doesn't drift as
    someone narrows the search radius. weights_tuple makes this cache-safe
    (sliders change the score, so the cutoffs must be recomputed)."""
    weights = dict(weights_tuple)
    subset = _df if pathway == "combined" else _df[_df["pathway"] == pathway]
    s = compute_score(subset, weights)
    return float(s.quantile(0.33)), float(s.quantile(0.67))


def band(score: float, cutoffs: tuple[float, float]) -> str:
    lo, hi = cutoffs
    if score >= hi:
        return "HIGH"
    if score >= lo:
        return "MODERATE"
    return "LOW"


def reasons(row: pd.Series) -> list[str]:
    """Plain-language bullet reasons, derived from which underlying factors
    are actually strong for this specific pair."""
    out = []
    if row["resource"] >= 0.7:
        out.append("High resource suitability at the source")
    if row["demand"] >= 0.7:
        out.append("Strong nearby demand")
    if row["climate"] >= 0.7:
        out.append("High climate need (heat / low vegetation)")
    if row["feasibility"] >= 0.7:
        out.append("Short, practical spatial connection")
    if row["infrastructure"] >= 0.7:
        out.append("Existing infrastructure nearby")
    if not out:
        out.append("Moderate scores across most factors, no single standout strength")
    return out


def recommended_action(pathway: str, priority: str) -> str:
    if pathway == "water":
        base = "assessing the feasibility of local non-potable treated-wastewater reuse for green infrastructure at this site"
    else:
        base = "assessing whether organic-waste output from this site could be routed to support circular use at this nearby green space"
    if priority == "LOW":
        return f"Not an immediate priority, but keep on record: worth {base} if conditions change."
    if priority == "MODERATE":
        return f"Worth a closer look: consider {base}, alongside a check on the specific limiting factor above."
    return f"Recommended next step: begin {base}."


def format_opportunity(row: pd.Series, priority: str) -> dict:
    return {
        "id": int(row["opportunity_id"]),
        "pathway": row["pathway"],
        "source": row.get("source_label", row["source_name"]),
        "destination": row.get("dest_label", row["dest_name"]),
        "distance_km": round(row["distance_m"] / 1000, 2),
        "priority": priority,
        "reasons": reasons(row),
        "action": recommended_action(row["pathway"], priority),
        "status": DECISION_STATUS[priority],
        "score": round(float(row["score"]), 3),
    }


# ==============================================================================
# Factor cards, weight breakdown, and methodology data used by the
# "Why this location?" and "Data & Methodology" sections. Values below are
# read from the live scoring model (dss_logic / priority_score.py); nothing
# here is invented for display purposes.
# ==============================================================================

FACTOR_FIELDS = [
    ("resource", "Resource strength"),
    ("demand", "Nearby demand"),
    ("climate", "Climate need"),
    ("feasibility", "Spatial feasibility"),
    ("infrastructure", "Infrastructure"),
]


def factor_cards(row: pd.Series) -> list[dict]:
    """Six evidence cards for the selected opportunity: the five scored
    factors (0 to 100) plus the raw distance, shown as a fact rather than a
    score since distance is already folded into spatial feasibility."""
    cards = [{"label": label, "value": round(float(row[field]) * 100)} for field, label in FACTOR_FIELDS]
    cards.append({"label": "Distance (source to destination)", "value": None,
                  "display": f"{round(row['distance_m'] / 1000, 2)} km"})
    return cards


def contribution_breakdown(row: pd.Series, weights: dict) -> list[dict]:
    """Ranked list of factors by their actual contribution to the total
    score: weight percent x factor score, using whatever weights are
    currently in effect for this assessment."""
    wsum = sum(weights.values()) or 1
    out = []
    for field, label in FACTOR_FIELDS:
        weight_pct = round(weights[field] / wsum * 100, 1)
        factor_score = round(float(row[field]) * 100)
        out.append({
            "label": label,
            "weight_pct": weight_pct,
            "factor_score": factor_score,
            "contribution": weight_pct / 100 * factor_score,
        })
    out.sort(key=lambda d: d["contribution"], reverse=True)
    return out


# --- Data & Methodology content, read from the actual preprocessing /
# scoring pipeline (scripts/preprocess_chennai_gis.py, scripts/priority_score.py).
# Update these lists if the underlying pipeline changes; do not add datasets
# that are not actually read by that pipeline.

DATASETS = [
    # category, dataset name, source, period, spatial resolution, role in the DSS
    ("Administrative", "GCC administrative zones", "Greater Chennai Corporation open GIS data", "Current", "Zone polygons", "Reporting and analysis boundary"),
    ("Administrative", "GCC ward boundaries (2022)", "Greater Chennai Corporation open GIS data", "2022", "Ward polygons", "Reporting and analysis unit"),
    ("Water", "Sewage treatment plant (STP) locations", "Greater Chennai Corporation open GIS data", "Current", "Point", "Core treated-wastewater resource layer"),
    ("Water", "Sewage pumping stations", "Greater Chennai Corporation open GIS data", "Current", "Point", "Existing infrastructure factor"),
    ("Water", "Sewage pumping main network", "Greater Chennai Corporation open GIS data", "Current", "Line network", "Existing infrastructure factor"),
    ("Water", "Sewage interconnection pipes", "Greater Chennai Corporation open GIS data", "Current", "Line network", "Existing infrastructure factor"),
    ("Water", "Waterbodies (city-scoped)", "Greater Chennai Corporation open GIS data", "2019", "Polygon", "Water context layer"),
    ("Water", "Rivers (city-scoped)", "Greater Chennai Corporation open GIS data", "Current", "Line", "Water context layer"),
    ("Water", "Storm water drains (SWD)", "Greater Chennai Corporation open GIS data", "2023", "Line network", "Drainage / infrastructure context"),
    ("Water", "Sewerage treatment capacity", "Greater Chennai Corporation records", "2018", "Per-STP (MLD)", "Sizes the resource-strength factor for each STP"),
    ("Waste", "Biogas plants", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste resource-strength factor"),
    ("Waste", "Biomethanisation plants", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste resource-strength factor"),
    ("Waste", "Ordinary compost generation plants", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste resource-strength factor"),
    ("Waste", "Vermi-compost centres", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste resource-strength factor"),
    ("Waste", "Resource recovery centres", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste resource-strength factor"),
    ("Waste", "Dumping grounds", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste-system context (legacy infrastructure)"),
    ("Waste", "Solid waste bins", "Greater Chennai Corporation open GIS data", "2022", "Point", "Waste generation / collection context"),
    ("Climate", "Flood hazard zones", "Greater Chennai Corporation open GIS data", "Current", "Polygon", "Core climate-need factor"),
    ("Climate", "Flood hotspots", "Greater Chennai Corporation open GIS data", "2020", "Point", "Supplementary climate-need context"),
    ("Climate", "Inundation depth points", "Greater Chennai Corporation open GIS data", "Current", "Point + depth attribute", "Severity weighting for climate need"),
    ("Demand", "Parks: city, community and neighbourhood (merged)", "Greater Chennai Corporation open GIS data", "Current", "Point / polygon, 10 m", "Combined green-space demand layer"),
    ("Climate (raster)", "Land surface temperature", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Urban heat context for climate need"),
    ("Climate (raster)", "Annual rainfall", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Climate context"),
    ("Climate (raster)", "Summer rainfall", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Climate context"),
    ("Climate (raster)", "NDVI, continuous", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Existing vegetation / green-cover context"),
    ("Climate (raster)", "NDVI, classified", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Vegetation class context"),
    ("Climate (raster)", "NDBI (built-up index)", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Impervious-surface context"),
    ("Climate (raster)", "Green infrastructure priority index", "Remote sensing raster, 10 m resolution", "Current", "10 m raster", "Reference layer only, not used in the live score"),
]

METHOD_FLOW = [
    "Data collection", "Data cleaning", "Spatial processing", "Buffer / distance analysis",
    "Criteria calculation", "Standardisation", "Weighting", "Priority score",
    "High / Moderate / Low classification", "Map visualisation", "Recommendation",
]

DATA_TO_ACTION_FLOW = ["Data", "Indicators", "Spatial analysis", "Scoring", "Prioritisation", "Map", "Action"]

SCORE_FORMULA_TERMS = [
    ("Resource strength", "resource"),
    ("Nearby demand", "demand"),
    ("Climate need", "climate"),
    ("Spatial feasibility", "feasibility"),
    ("Infrastructure", "infrastructure"),
]

# ------------------------------------------------------------------------
# Short, ONE-TAB-ONLY methodology content. Each assessment page shows only
# its own row here (a handful of icon steps), not the full pipeline -- the
# full pipeline and dataset list live solely on the Methodology tab.
# ------------------------------------------------------------------------
PATHWAY_MINI_METHOD = {
    "water": [
        (":material/water_drop:", "Resource", "STP locations + treatment capacity"),
        (":material/park:", "Demand", "Distance to parks & green infrastructure"),
        (":material/thermostat:", "Climate need", "Flood risk & heat exposure nearby"),
        (":material/plumbing:", "Infrastructure", "Existing sewer / pumping network"),
        (":material/speed:", "Priority score", "Weighted sum -> HIGH / MODERATE / LOW"),
    ],
    "waste": [
        (":material/compost:", "Resource", "Biogas, compost & recovery facility type"),
        (":material/park:", "Demand", "Distance to parks & urban farms"),
        (":material/thermostat:", "Climate need", "Flood risk & heat exposure nearby"),
        (":material/local_shipping:", "Infrastructure", "Access road / collection readiness"),
        (":material/speed:", "Priority score", "Weighted sum -> HIGH / MODERATE / LOW"),
    ],
    "map": [
        (":material/layers:", "Combine", "Both pathways plotted on one map"),
        (":material/tune:", "Filter", "By pathway, priority band and radius"),
        (":material/touch_app:", "Select", "Click a row to zoom the map to it"),
        (":material/insights:", "Explain", "Ranked factors behind that priority"),
    ],
}

PATHWAY_MINI_INTRO = {
    "water": "How Water Reuse priority is worked out, in five steps.",
    "waste": "How Organic Waste priority is worked out, in five steps.",
    "map": "How the combined map is built.",
}


def name_conversion_examples(df: pd.DataFrame, n: int = 3) -> list[dict]:
    """Real worked examples of the coordinate -> place-name step, pulled
    straight from the loaded data, for the Methodology page."""
    out = []
    picks = [
        df[df.pathway == "water"].iloc[0],
        df[df.pathway == "waste"].iloc[0],
        df[df.pathway == "waste"].iloc[len(df[df.pathway == "waste"]) // 2],
    ][:n]
    for row in picks:
        kind = "stp" if row["pathway"] == "water" else "waste"
        src_trace = geocode_trace(row["src_lat"], row["src_lon"], kind)
        dst_trace = geocode_trace(row["dst_lat"], row["dst_lon"], "park")
        out.append({"pathway": row["pathway"], "source": src_trace, "dest": dst_trace})
    return out


def methodology_stats(df: pd.DataFrame, df_scored: pd.DataFrame) -> dict:
    return {
        "n_datasets": len(DATASETS),
        "n_total": int(len(df)),
        "n_water": int((df["pathway"] == "water").sum()),
        "n_waste": int((df["pathway"] == "waste").sum()),
        "n_high": int((df_scored["priority_default"] == "HIGH").sum()),
        "n_moderate": int((df_scored["priority_default"] == "MODERATE").sum()),
        "n_low": int((df_scored["priority_default"] == "LOW").sum()),
    }
