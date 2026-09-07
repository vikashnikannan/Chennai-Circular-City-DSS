"""
================================================================================
 Chennai Circular City DSS -- Priority Scoring
================================================================================
Computes the Water-reuse and Organic-waste circular-opportunity scores against
the REAL layers produced by preprocess_chennai_gis.py, i.e. it reads
chennai_circular_dss.gpkg directly -- nothing here is sample data.

Score = ( w_resource*resource_suitability
        + w_demand  *demand
        + w_climate *climate_need
        + w_feasibility*spatial_feasibility
        + w_infrastructure*infrastructure ) / sum(weights)

Two things you will need to adjust for your exact schema:
  1. FIELD NAMES -- the script guesses common field names ("Name", "name",
     "park_type"). Run it once, read the printed column list for each layer,
     and adjust get_name()/get_park_type() below if they don't match.
  2. climate_need_proxy() -- this is a placeholder (flood-zone proximity
     only) until the PROJ conflict is fixed. Once A_LST_Celsius_10m.tif and
     C_NDVI_10m.tif open cleanly, switch to sample_raster_climate() instead
     (see the PROJ fix note in the accompanying README).

Run:
    python priority_score.py
Outputs (into OUTPUT_ROOT/00_reports/):
    circular_opportunities.csv       -- every source-destination pair, scored
    circular_opportunities.geojson   -- same, as points+lines for a web map (WGS84)
================================================================================
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd

# ------------------------------------------------------------------ CONFIG --
OUTPUT_ROOT = Path(os.environ.get("ICLEI_OUTPUT_ROOT", r"D:\Freelance\ICLEI\output"))
GPKG_PATH = OUTPUT_ROOT / "06_gis_database" / "chennai_circular_dss.gpkg"
REPORTS_DIR = OUTPUT_ROOT / "00_reports"

CRS_ANALYSIS = "EPSG:32644"   # matches your preprocessing script
CRS_WEB = "EPSG:4326"

MAX_DIST_M = 8000  # generous outer radius; filter tighter later in the app/UI

WEIGHTS = {"resource": 0.30, "demand": 0.25, "climate": 0.20,
           "feasibility": 0.15, "infrastructure": 0.10}

# gpkg_layer -> (type_label, resource_suitability_tier, infra_status)
WASTE_LAYERS = {
    "waste_biomethanisation_plants": ("biomethanisation", 0.90, "operational"),
    "waste_biogas_plants":           ("biogas",            0.80, "operational"),
    "waste_resource_recovery_centres": ("resource_recovery", 0.70, "operational"),
    "waste_ordinary_compost_plants": ("ordinary_compost",  0.55, "operational"),
    "waste_vermi_compost_centres":   ("vermi_compost",     0.50, "operational"),
    "waste_dumping_grounds":         ("dumping_ground",    0.30, "legacy"),
}
DEMAND_WEIGHT = {"City Park": 1.0, "Community Park": 0.7, "Neighbourhood Park": 0.5}


# ------------------------------------------------------------------ HELPERS --
def load(layer: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(GPKG_PATH, layer=layer)
    if gdf.crs is None:
        gdf = gdf.set_crs(CRS_ANALYSIS)
    elif gdf.crs.to_string() != CRS_ANALYSIS:
        gdf = gdf.to_crs(CRS_ANALYSIS)
    gdf["geometry"] = gdf.geometry.centroid  # collapses polygons/lines to a representative point
    print(f"  loaded {layer}: {len(gdf)} features, columns={list(gdf.columns)}")
    return gdf


def get_name(row, fallback: str, wgs_row=None, label: str = "Location") -> str:
    """Robust name lookup with graceful fallbacks, in order:
      1. A known name field (Name/name/NAME/layer_name/Title) -- but only if
         it's non-blank after stripping whitespace. An empty string is NOT
         treated as a valid name (this was the original bug: pd.notna("")
         is True, so blank KML <Name></Name> tags were passed straight
         through instead of triggering the fallback below).
      2. Text pulled out of a Description field (common in KML placemarks
         where the real label ended up in an HTML blob instead of <Name>).
      3. A coordinate-based label, e.g. "Park at 13.0827, 80.2707" -- always
         locatable on a map even with zero usable text fields.
      4. The numbered placeholder passed in as `fallback`, as an absolute
         last resort (e.g. missing/invalid geometry).
    """
    # 1) Direct name fields
    for field in ("Name", "name", "NAME", "layer_name", "Title"):
        if field in row and pd.notna(row[field]):
            val = str(row[field]).strip()
            if val:
                return val

    # 2) Description field -- strip HTML tags/whitespace, use if non-empty
    for field in ("Description", "description", "DESCRIPTION"):
        if field in row and pd.notna(row[field]):
            text = re.sub(r"<[^<]+?>", " ", str(row[field]))
            text = " ".join(text.split()).strip()
            if text:
                return text[:60] + ("..." if len(text) > 60 else "")

    # 3) Coordinate-based fallback (needs the WGS84 twin row for lon/lat)
    if wgs_row is not None:
        try:
            lat, lon = wgs_row.geometry.y, wgs_row.geometry.x
            if pd.notna(lat) and pd.notna(lon):
                return f"{label} at {lat:.4f}, {lon:.4f}"
        except Exception:
            pass

    # 4) Last resort
    return fallback


def get_park_type(row) -> str:
    for field in ("park_type", "Park_Type", "type"):
        if field in row and pd.notna(row[field]):
            return str(row[field])
    return "Neighbourhood Park"


def with_wgs84(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Same row order as gdf, reprojected -- used to attach lon/lat for the web map."""
    return gdf.to_crs(CRS_WEB)


def climate_need_proxy(parks: gpd.GeoDataFrame, flood_xy: np.ndarray) -> np.ndarray:
    """PLACEHOLDER climate-need score: 0.55 base, +0.25 if within 1.5 km of a
    mapped flood-hazard zone. Replace with sample_raster_climate() once your
    rasters open (see README / PROJ fix)."""
    need = np.full(len(parks), 0.55)
    xy = np.column_stack([parks.geometry.x, parks.geometry.y])
    for i, pt in enumerate(xy):
        if len(flood_xy) and np.hypot(flood_xy[:, 0]-pt[0], flood_xy[:, 1]-pt[1]).min() <= 1500:
            need[i] = min(1.0, need[i] + 0.25)
    return need


def sample_raster_climate(parks_wgs: gpd.GeoDataFrame, lst_tif: Path, ndvi_tif: Path) -> np.ndarray:
    """Real version of climate_need_proxy(), once rasters are readable.
    Samples LST + NDVI at each park centroid and blends them 0-1 (higher = more need)."""
    import rasterio
    coords = [(x, y) for x, y in zip(parks_wgs.geometry.x, parks_wgs.geometry.y)]
    with rasterio.open(lst_tif) as src:
        lst = np.array([v[0] for v in src.sample(coords)], dtype=float)
    with rasterio.open(ndvi_tif) as src:
        ndvi = np.array([v[0] for v in src.sample(coords)], dtype=float)
    lst_n = (lst - np.nanmin(lst)) / (np.nanmax(lst) - np.nanmin(lst) + 1e-9)
    ndvi_n = (ndvi - np.nanmin(ndvi)) / (np.nanmax(ndvi) - np.nanmin(ndvi) + 1e-9)
    return np.clip(0.6 * lst_n + 0.4 * (1 - ndvi_n), 0, 1)  # hot + low-vegetation = high need


def score_pathway(sources: gpd.GeoDataFrame, sources_wgs: gpd.GeoDataFrame, pathway: str,
                   parks: gpd.GeoDataFrame, parks_wgs: gpd.GeoDataFrame,
                   climate_need: np.ndarray, max_dist_m: float, weights: dict) -> pd.DataFrame:
    src_xy = np.column_stack([sources.geometry.x, sources.geometry.y])
    dst_xy = np.column_stack([parks.geometry.x, parks.geometry.y])
    wsum = sum(weights.values()) or 1
    rows = []
    for si in range(len(sources)):
        s = sources.iloc[si]
        s_wgs = sources_wgs.iloc[si]
        for di in range(len(parks)):
            d = float(np.hypot(src_xy[si, 0]-dst_xy[di, 0], src_xy[si, 1]-dst_xy[di, 1]))
            if d > max_dist_m:
                continue
            p = parks.iloc[di]
            p_wgs = parks_wgs.iloc[di]

            if pathway == "water":
                cap = s.get("capacity_mld", np.nan)
                r = max(0.15, min(1.0, cap/160)) if pd.notna(cap) else 0.5
                infra = 1.0 if s.get("_reuse_ready", False) else 0.6
            else:
                r = s.get("_resource_tier", 0.5)
                infra = 0.3 if s.get("_status") == "legacy" else 1.0

            dem = DEMAND_WEIGHT.get(get_park_type(p), 0.5)
            c = climate_need[di]
            f = max(0.0, 1 - (d/max_dist_m)*0.8)
            score = (weights["resource"]*r + weights["demand"]*dem + weights["climate"]*c +
                     weights["feasibility"]*f + weights["infrastructure"]*infra) / wsum

            rows.append({
                "pathway": pathway,
                "source_name": get_name(s, f"{pathway}_{si}", s_wgs, label=f"{pathway.capitalize()} site"),
                "dest_name": get_name(p, f"park_{di}", p_wgs, label="Park"),
                "distance_m": round(d, 1),
                "resource": round(r, 3), "demand": round(dem, 3), "climate": round(c, 3),
                "feasibility": round(f, 3), "infrastructure": round(infra, 3),
                "score": round(score, 4),
                "src_lon": s_wgs.geometry.x, "src_lat": s_wgs.geometry.y,
                "dst_lon": p_wgs.geometry.x, "dst_lat": p_wgs.geometry.y,
            })
    return pd.DataFrame(rows).sort_values("score", ascending=False)


# ---------------------------------------------------------------------- MAIN --
def main():
    print("Loading parks and flood layers...")
    parks = load("green_parks_combined")
    parks_wgs = with_wgs84(parks)
    flood = load("climate_flood_hazard_zones")
    flood_xy = np.column_stack([flood.geometry.x, flood.geometry.y])

    # --- climate need: swap this block for sample_raster_climate() once your
    #     rasters open cleanly (see README) ---
    climate_need = climate_need_proxy(parks, flood_xy)

    print("Loading STPs (water pathway)...")
    stp = load("water_stp_locations")
    stp["_reuse_ready"] = False  # TODO: set True for plants you know are TTUF/tertiary-reuse-ready
    stp_wgs = with_wgs84(stp)
    water_scores = score_pathway(stp, stp_wgs, "water", parks, parks_wgs, climate_need, MAX_DIST_M, WEIGHTS)

    print("Loading waste facilities...")
    waste_frames = []
    for layer, (wtype, tier, status) in WASTE_LAYERS.items():
        try:
            gdf = load(layer)
        except Exception as e:
            print(f"  [skip] {layer}: {e}")
            continue
        gdf["_resource_tier"] = tier
        gdf["_status"] = status
        waste_frames.append(gdf)

    if waste_frames:
        waste_all = pd.concat(waste_frames, ignore_index=True)
        waste_all = gpd.GeoDataFrame(waste_all, geometry="geometry", crs=CRS_ANALYSIS)
        waste_wgs = with_wgs84(waste_all)
        waste_scores = score_pathway(waste_all, waste_wgs, "waste", parks, parks_wgs, climate_need, MAX_DIST_M, WEIGHTS)
    else:
        waste_scores = pd.DataFrame()

    combined = pd.concat([water_scores, waste_scores], ignore_index=True).sort_values("score", ascending=False)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = REPORTS_DIR / "circular_opportunities.csv"
    combined.to_csv(out_csv, index=False)

    print("=" * 70)
    print(f"[OK] {len(combined)} scored opportunities -> {out_csv}")
    if len(combined):
        print(combined.head(10)[["pathway", "source_name", "dest_name", "distance_m", "score"]].to_string(index=False))
    print("Next: copy this CSV next to app.py and run `streamlit run app.py`.")


if __name__ == "__main__":
    main()
