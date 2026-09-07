"""
================================================================================
 Chennai Circular City DSS - Data Preprocessing Pipeline
================================================================================
Purpose
-------
Reads the raw datasets in DATA_ROOT (KML, Shapefile, CSV, GeoTIFF), keeps only
the layers that are actually needed for the GIS-Based Circular City
Decision-Support Framework (Water / Waste / Food / Climate / Administrative),
converts KML -> GeoJSON, cleans/reprojects everything to a consistent CRS, and
writes it all into a clean, organised OUTPUT_ROOT folder -- plus a single
analysis-ready GeoPackage -- so the next step (building the actual DSS /
priority scoring) can start immediately without any further data wrangling.

This script does NOT compute the DSS / priority score. It only prepares data.

Run
---
    python preprocess_chennai_gis.py

Requirements
------------
    pip install geopandas fiona shapely rasterio pandas pyproj
(see requirements.txt)
================================================================================
"""



from __future__ import annotations

import json
import logging
import os
import shutil
import sys
import warnings
from pathlib import Path

import pandas as pd
import geopandas as gpd

try:
    import pyogrio  # noqa: F401
    HAVE_PYOGRIO = True
except ImportError:
    HAVE_PYOGRIO = False

import pyproj, os
os.environ["PROJ_DATA"] = pyproj.datadir.get_data_dir()
os.environ["PROJ_LIB"] = pyproj.datadir.get_data_dir()

import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling

warnings.filterwarnings("ignore", category=UserWarning)

# ==============================================================================
# 0. CONFIG -- edit these paths if your folder names ever change
# ==============================================================================

DATA_ROOT = Path(os.environ.get("ICLEI_DATA_ROOT", r"D:\Freelance\ICLEI\DATA"))
OUTPUT_ROOT = Path(os.environ.get("ICLEI_OUTPUT_ROOT", r"D:\Freelance\ICLEI\output"))

KML_DIR = DATA_ROOT / "kml"
SHP_DIR = DATA_ROOT / "Shapefile"
EXCEL_DIR = DATA_ROOT / "excel"
RASTER_DIR = DATA_ROOT / "Chennai_GreenInfra_10m" / "Chennai_GreenInfra_10m"

# GeoJSON outputs are kept in WGS84 (lon/lat), the correct GeoJSON convention.
CRS_GEOJSON = "EPSG:4326"
# Everything that goes into the GeoPackage (and all rasters) is standardised to
# UTM Zone 44N (metres) -- this is what the future DSS step needs for
# buffer/distance-based feasibility scoring (e.g. "STP within 2 km of a park").
CRS_ANALYSIS = "EPSG:32644"

OUT_REPORTS = OUTPUT_ROOT / "00_reports"
OUT_ADMIN = OUTPUT_ROOT / "01_administrative"
OUT_WATER = OUTPUT_ROOT / "02_water"
OUT_WASTE = OUTPUT_ROOT / "03_waste"
OUT_FOOD = OUTPUT_ROOT / "04_food_green_infrastructure"
OUT_CLIMATE = OUTPUT_ROOT / "05_climate"
OUT_RASTER = OUT_CLIMATE / "rasters"
OUT_GPKG_DIR = OUTPUT_ROOT / "06_gis_database"
GPKG_PATH = OUT_GPKG_DIR / "chennai_circular_dss.gpkg"

ALL_DIRS = [OUT_REPORTS, OUT_ADMIN, OUT_WATER, OUT_WASTE, OUT_FOOD, OUT_CLIMATE, OUT_RASTER, OUT_GPKG_DIR]

# ==============================================================================
# 1. LOGGING
# ==============================================================================

def setup_logging() -> logging.Logger:
    OUT_REPORTS.mkdir(parents=True, exist_ok=True)
    log_path = OUT_REPORTS / "preprocessing_log.txt"
    logger = logging.getLogger("chennai_preprocess")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", "%H:%M:%S")

    fh = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


log = setup_logging()

# ==============================================================================
# 2. DATASET SELECTION
#
# Only datasets that are actually used by the circular-economy framework
# (Water / Waste / Food / Climate / Administrative) are included. Everything
# else that exists in DATA_ROOT/kml or DATA_ROOT/excel but is NOT needed is
# listed explicitly in EXCLUDED_* below, with the reason, so the choice is
# documented rather than silent. Flip an entry from excluded to included (or
# vice versa) any time -- nothing else in the script needs to change.
# ==============================================================================

# --- included vector sources -------------------------------------------------
# Each entry: (category, source_path, output_geojson_name, gpkg_layer_name, note)
VECTOR_SOURCES = [
    # ---------------- Administrative ----------------
    ("admin", SHP_DIR / "Chennai_GCC_ZonesMap.shp", OUT_ADMIN / "chennai_zones.geojson",
     "administrative_zones",
     "GCC zones (Shapefile version used -- higher quality than the duplicate KML)."),
    ("admin", KML_DIR / "Chennai GCC Ward Map - 2022.kml", OUT_ADMIN / "chennai_wards.geojson",
     "administrative_wards",
     "Ward boundaries -- primary reporting/analysis unit."),

    # ---------------- Water ----------------
    ("water", KML_DIR / "Sewage Treatment Plants Map.kml", OUT_WATER / "stp_locations.geojson",
     "water_stp_locations",
     "STP locations -- core treated-wastewater resource layer."),
    ("water", KML_DIR / "Sewage Pumping Stations.kml", OUT_WATER / "sewage_pumping_stations.geojson",
     "water_pumping_stations",
     "Existing infrastructure node -- used for the infrastructure-feasibility factor."),
    ("water", KML_DIR / "Sewage Pumping Main Network.kml", OUT_WATER / "sewage_pumping_main_network.geojson",
     "water_pumping_main_network",
     "Existing sewerage conveyance network -- 'is a connection already there?' factor."),
    ("water", KML_DIR / "Sewage Interconnection Pipes.kml", OUT_WATER / "sewage_interconnection_pipes.geojson",
     "water_interconnection_pipes",
     "Existing sewer network -- same infrastructure-feasibility purpose as above."),
    ("water", KML_DIR / "Chennai Waterbodies Map - 2019.kml", OUT_WATER / "waterbodies.geojson",
     "water_waterbodies",
     "City-scoped waterbodies (chosen over the larger Basin-scale duplicate)."),
    ("water", KML_DIR / "Chennai Rivers Map.kml", OUT_WATER / "rivers.geojson",
     "water_rivers",
     "City-scoped rivers (chosen over the Basin-scale duplicate)."),
    ("water", KML_DIR / "Chennai Storm Water Drains - SWD - Map 2023.kml", OUT_WATER / "stormwater_drains.geojson",
     "water_stormwater_drains",
     "Most recent, city-specific drainage layer (chosen over Basin Macro/Micro Drains)."),

    # ---------------- Waste ----------------
    ("waste", KML_DIR / "Chennai Biogas Plants Map - 2022.kml", OUT_WASTE / "biogas_plants.geojson",
     "waste_biogas_plants", "Composting/biogas facility -- essential."),
    ("waste", KML_DIR / "Chennai Biomethanisation Plants - 2022.kml", OUT_WASTE / "biomethanisation_plants.geojson",
     "waste_biomethanisation_plants", "Composting/biogas facility -- essential."),
    ("waste", KML_DIR / "Chennai Ordinary Compost Generation Plants Map - 2022.kml",
     OUT_WASTE / "ordinary_compost_plants.geojson",
     "waste_ordinary_compost_plants", "Composting facility -- essential."),
    ("waste", KML_DIR / "Chennai Vermi Compost Centres Map - 2022.kml", OUT_WASTE / "vermi_compost_centres.geojson",
     "waste_vermi_compost_centres", "Composting facility -- essential."),
    ("waste", KML_DIR / "Chennai Resource Recovery Centres Map - 2022.kml",
     OUT_WASTE / "resource_recovery_centres.geojson",
     "waste_resource_recovery_centres", "Waste-processing facility."),
    ("waste", KML_DIR / "Chennai Dumping Grounds Map - 2022.kml", OUT_WASTE / "dumping_grounds.geojson",
     "waste_dumping_grounds", "Waste-system context layer."),
    ("waste", KML_DIR / "Chennai Bins Map - 2022.kml", OUT_WASTE / "solid_waste_bins.geojson",
     "waste_solid_waste_bins", "Solid-waste generation/collection proxy."),

    # ---------------- Climate ----------------
    ("climate", KML_DIR / "Chennai Flood Hazard Zones Map.kml", OUT_CLIMATE / "flood_hazard_zones.geojson",
     "climate_flood_hazard_zones", "Core flood-risk layer for the climate-vulnerability overlay."),
    ("climate", KML_DIR / "Chennai GCC Flood Hostspots 2020.kml", OUT_CLIMATE / "flood_hotspots_2020.geojson",
     "climate_flood_hotspots", "Supplementary known problem-point layer."),
    ("climate", KML_DIR / "Chennai Inundation Points with Depth of Inundation.kml",
     OUT_CLIMATE / "inundation_points_depth.geojson",
     "climate_inundation_points", "Adds inundation-depth attribute for severity weighting."),
]

# --- Parks are merged from 3 files into a single layer -----------------------
PARK_SOURCES = [
    (KML_DIR / "Chennai City Parks Map.kml", "City Park"),
    (KML_DIR / "Chennai Community Parks Map.kml", "Community Park"),
    (KML_DIR / "Chennai Neighbourhood Parks Map.kml", "Neighbourhood Park"),
]
PARKS_GEOJSON = OUT_FOOD / "parks_combined.geojson"
PARKS_GPKG_LAYER = "green_parks_combined"
PARKS_NOTE = ("All three park layers merged into one 'green space demand' layer, "
              "tagged by park_type. Used both as Food/Green-Infrastructure inventory "
              "and as the demand layer for the STP-reuse pathway.")

# --- CSV sources ---------------------------------------------------------------
CSV_SOURCES = [
    (EXCEL_DIR / "Chennai Sewerage Capacity - 2018.csv", OUT_WATER / "stp_sewerage_capacity_2018.csv",
     "STP/sewerage treated-water capacity -- tells us HOW MUCH treated water is available per STP."),
]

# --- Raster sources --------------------------------------------------------
RASTER_SOURCES = [
    (RASTER_DIR / "A_LST_Celsius_10m.tif", OUT_RASTER / "lst_celsius_10m.tif",
     "Land Surface Temperature (deg C) -- urban heat layer."),
    (RASTER_DIR / "B_Rainfall_Annual_mm_10m.tif", OUT_RASTER / "rainfall_annual_mm_10m.tif",
     "Annual rainfall (mm) -- climate context."),
    (RASTER_DIR / "B_Rainfall_Summer_mm_10m.tif", OUT_RASTER / "rainfall_summer_mm_10m.tif",
     "Summer rainfall (mm) -- climate context."),
    (RASTER_DIR / "C_NDVI_10m.tif", OUT_RASTER / "ndvi_10m.tif",
     "NDVI (continuous) -- existing green-cover layer."),
    (RASTER_DIR / "C_NDVI_Class_10m.tif", OUT_RASTER / "ndvi_class_10m.tif",
     "NDVI classified (low/med/high vegetation)."),
    (RASTER_DIR / "D_NDBI_10m.tif", OUT_RASTER / "ndbi_10m.tif",
     "NDBI -- built-up/impervious-surface layer."),
    (RASTER_DIR / "E_GreenInfra_Priority_Index_10m.tif", OUT_RASTER / "greeninfra_priority_index_10m.tif",
     "Pre-computed Green-Infra priority index -- kept as a REFERENCE layer only; "
     "the actual DSS score will be (re)built from the raw layers above, not derived from this."),
]

# --- explicitly excluded, with reasons (for the report / transparency) -----
EXCLUDED_KML = {
    "Chennai Basin Buckingham Canal Map.kml":
        "Basin-scale canal segment; overlaps with the waterbodies/rivers layers already selected.",
    "Chennai Basin Krishna Water Canal Map.kml":
        "Basin-scale canal segment; overlaps with the waterbodies/rivers layers already selected.",
    "Chennai Basin Macro Drains Map.kml":
        "Superseded by the more recent, city-specific 'Storm Water Drains - SWD - 2023' layer.",
    "Chennai Basin Micro Drains Map.kml":
        "Superseded by the more recent, city-specific 'Storm Water Drains - SWD - 2023' layer.",
    "Chennai Basin Rivers and Streams Map.kml":
        "Basin-scale duplicate of the city-scoped 'Chennai Rivers Map.kml' already selected.",
    "Chennai Basin Waterbodies Map.kml":
        "Basin-scale duplicate of the city-scoped 'Chennai Waterbodies Map - 2019.kml' already selected.",
    "Chennai Fire Stations Locations.kml":
        "Emergency infrastructure -- not part of the water/waste/food/climate circular framework.",
    "Chennai Flooding Points in 2015.kml":
        "Superseded by the more recent Flood Hazard Zones + 2020 hotspots + inundation-depth layers.",
    "Chennai Flows 5/10/25/50/100/200 Years Return Period.kml (6 files)":
        "Detailed hydraulic-model outputs; over-detailed for a screening-level DSS given Flood "
        "Hazard Zones already covers flood risk. The framework explicitly avoids complex hydrology.",
    "Chennai GCC Zones Map - 2022.kml":
        "Duplicate of the Shapefile zones layer, which is higher-quality vector data -- Shapefile used instead.",
    "Chennai Road Centerline Map.kml":
        "Roads are optional in the framework; not needed for the Euclidean-distance screening used at this stage.",
    "Chennai Slum Boundaries Map.kml":
        "Not part of the water/waste/food/climate/administrative layer set. Worth adding later for an "
        "equity-weighted score, but out of scope for this preprocessing pass.",
    "Chennai Slums.kml":
        "Same reasoning as Slum Boundaries.",
    "Pump motors to pump sewage.kml":
        "Individual equipment inventory, not a spatial network/demand layer needed for screening.",
    "Pumping Machine DG Sets.kml":
        "Backup power equipment -- not relevant to the circular-resource framework.",
    "Pumping Specials.kmz":
        "Ambiguous content, KMZ container, operational equipment -- excluded for the same reason as the pump/DG layers.",
    "Sewage Flow Meters.kml":
        "Monitoring equipment, not a resource/demand/infrastructure layer.",
    "Sewage Silt Pits.kml":
        "Maintenance infrastructure -- too granular for zone-level screening.",
    "Sewage Wells.kml":
        "Ambiguous purpose and not called for in the framework.",
    "Sewer Chambers.kml":
        "Manholes/chambers -- maintenance-level detail, not needed for feasibility screening.",
    "Water Transmission Main Line Map.kml":
        "Drinking-water transmission network, not treated-wastewater reuse infrastructure -- out of scope.",
}

EXCLUDED_CSV = {
    "Chennai Watersupply Capacity 2018.csv":
        "Drinking-water supply capacity, not treated-wastewater/STP capacity -- not part of the "
        "circular reuse pathway this framework targets.",
}

MISSING_CATEGORIES_NOTE = (
    "No dataset for 'Food / urban & peri-urban agriculture' was found in DATA_ROOT. The framework "
    "lists this as its 3rd pillar (Pathway 3). Parks/green-infrastructure demand IS covered "
    "(parks_combined.geojson). If time allows, agriculture plots can be pulled from OpenStreetMap "
    "(landuse=farmland / landuse=allotments) as suggested in the framework notes."
)

# ==============================================================================
# 3. HELPERS
# ==============================================================================

def read_kml_all_layers(path: Path) -> gpd.GeoDataFrame:
    """Read every internal layer of a KML (KMLs with multiple <Folder> elements
    are exposed by GDAL as separate layers) and merge them into one GeoDataFrame.
    """
    engine = "pyogrio" if HAVE_PYOGRIO else "fiona"

    if HAVE_PYOGRIO:
        layer_info = pyogrio.list_layers(str(path))
        layer_names = [row[0] for row in layer_info]
    else:
        import fiona
        fiona.drvsupport.supported_drivers["KML"] = "rw"
        fiona.drvsupport.supported_drivers["LIBKML"] = "rw"
        layer_names = fiona.listlayers(str(path))

    if not layer_names:
        raise RuntimeError("No layers found in KML.")

    frames = []
    for lyr in layer_names:
        try:
            gdf = gpd.read_file(str(path), layer=lyr, engine=engine)
            if len(gdf) > 0:
                frames.append(gdf)
        except Exception as e:  # noqa: BLE001
            log.warning(f"    layer '{lyr}' in {path.name} could not be read ({e}) -- skipped")

    if not frames:
        raise RuntimeError("All layers were empty or unreadable.")

    combined = pd.concat(frames, ignore_index=True)
    combined = gpd.GeoDataFrame(combined, geometry="geometry", crs=frames[0].crs or "EPSG:4326")
    return combined


def read_vector(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() == ".kml":
        return read_kml_all_layers(path)
    engine = "pyogrio" if HAVE_PYOGRIO else "fiona"
    return gpd.read_file(str(path), engine=engine)


def clean_gdf(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Drop empty/invalid geometries, force 2D (drop Z), keep it lightweight."""
    gdf = gdf[~gdf.geometry.isna() & ~gdf.geometry.is_empty].copy()
    gdf["geometry"] = gdf["geometry"].apply(lambda g: gpd.GeoSeries([g]).force_2d().iloc[0] if g is not None else g)
    if gdf.crs is None:
        log.warning("    no CRS on source data -- assuming EPSG:4326 (typical for KML).")
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def write_layer(gdf: gpd.GeoDataFrame, geojson_path: Path, gpkg_layer: str) -> dict:
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    gdf_wgs84 = gdf.to_crs(CRS_GEOJSON)
    gdf_wgs84.to_file(geojson_path, driver="GeoJSON")

    gdf_utm = gdf.to_crs(CRS_ANALYSIS)
    GPKG_PATH.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if GPKG_PATH.exists() else "w"
    gdf_utm.to_file(GPKG_PATH, layer=gpkg_layer, driver="GPKG", mode=mode)

    return {"features": len(gdf), "geom_types": sorted(gdf.geom_type.unique().tolist())}


def process_vector_sources(manifest: dict) -> None:
    log.info("=" * 70)
    log.info("STEP 1/4 -- Vector layers (KML / Shapefile -> GeoJSON + GeoPackage)")
    log.info("=" * 70)
    for category, src, dst, gpkg_layer, note in VECTOR_SOURCES:
        entry = {"source": str(src), "output": str(dst), "gpkg_layer": gpkg_layer, "note": note}
        if not src.exists():
            log.warning(f"[MISSING] {src.name} -- expected but not found, skipped.")
            entry["status"] = "missing_source"
            manifest["vector_layers"].append(entry)
            continue
        try:
            gdf = read_vector(src)
            gdf = clean_gdf(gdf)
            stats = write_layer(gdf, dst, gpkg_layer)
            entry.update(status="ok", **stats)
            log.info(f"[OK] {src.name} -> {dst.name}  ({stats['features']} features, {stats['geom_types']})")
        except Exception as e:  # noqa: BLE001
            log.error(f"[FAILED] {src.name}: {e}")
            entry["status"] = f"failed: {e}"
        manifest["vector_layers"].append(entry)


def process_administrative_boundary(manifest: dict) -> None:
    """Dissolve the GCC zones into a single city-boundary polygon."""
    src = SHP_DIR / "Chennai_GCC_ZonesMap.shp"
    dst = OUT_ADMIN / "chennai_boundary.geojson"
    entry = {"source": str(src), "output": str(dst), "gpkg_layer": "administrative_boundary",
              "note": "Single dissolved polygon covering all GCC zones -- overall study-area boundary."}
    if not src.exists():
        log.warning("[MISSING] GCC zones shapefile -- cannot derive city boundary.")
        entry["status"] = "missing_source"
        manifest["vector_layers"].append(entry)
        return
    try:
        zones = clean_gdf(read_vector(src))
        boundary = zones.dissolve()
        boundary = boundary[["geometry"]].copy()
        boundary["name"] = "Greater Chennai Corporation - study area boundary"
        stats = write_layer(boundary, dst, "administrative_boundary")
        entry.update(status="ok", **stats)
        log.info(f"[OK] Derived city boundary (dissolved GCC zones) -> {dst.name}")
    except Exception as e:  # noqa: BLE001
        log.error(f"[FAILED] deriving city boundary: {e}")
        entry["status"] = f"failed: {e}"
    manifest["vector_layers"].append(entry)


def process_parks(manifest: dict) -> None:
    log.info("-" * 70)
    log.info("Merging Parks (City + Community + Neighbourhood) into one layer")
    frames = []
    sources_used = []
    for src, park_type in PARK_SOURCES:
        if not src.exists():
            log.warning(f"[MISSING] {src.name} -- skipped in Parks merge.")
            continue
        try:
            gdf = clean_gdf(read_vector(src))
            gdf["park_type"] = park_type
            frames.append(gdf)
            sources_used.append(src.name)
            log.info(f"    + {src.name}: {len(gdf)} features")
        except Exception as e:  # noqa: BLE001
            log.error(f"[FAILED] {src.name}: {e}")

    entry = {"sources": sources_used, "output": str(PARKS_GEOJSON), "gpkg_layer": PARKS_GPKG_LAYER, "note": PARKS_NOTE}
    if not frames:
        log.warning("No park layers available -- Parks merge skipped entirely.")
        entry["status"] = "no_sources_found"
    else:
        merged = pd.concat(frames, ignore_index=True)
        merged = gpd.GeoDataFrame(merged, geometry="geometry", crs=frames[0].crs)
        stats = write_layer(merged, PARKS_GEOJSON, PARKS_GPKG_LAYER)
        entry.update(status="ok", **stats)
        log.info(f"[OK] Parks merged -> {PARKS_GEOJSON.name} ({stats['features']} features total)")
    manifest["vector_layers"].append(entry)


def process_rasters(manifest: dict) -> None:
    log.info("=" * 70)
    log.info("STEP 2/4 -- Raster layers (climate / green-cover, 10m)")
    log.info("=" * 70)
    OUT_RASTER.mkdir(parents=True, exist_ok=True)
    for src, dst, note in RASTER_SOURCES:
        entry = {"source": str(src), "output": str(dst), "note": note}
        if not src.exists():
            log.warning(f"[MISSING] {src.name} -- skipped.")
            entry["status"] = "missing_source"
            manifest["rasters"].append(entry)
            continue
        try:
            with rasterio.open(src) as ds:
                src_crs = ds.crs
                width, height, count = ds.width, ds.height, ds.count
            if src_crs is None:
                log.warning(f"[NO CRS] {src.name} -- copied unchanged, verify CRS manually in QGIS.")
                shutil.copy2(src, dst)
                entry.update(status="copied_no_crs", width=width, height=height, bands=count)
            elif src_crs.to_string() == CRS_ANALYSIS or (src_crs.to_epsg() == int(CRS_ANALYSIS.split(":")[1])):
                shutil.copy2(src, dst)
                entry.update(status="copied", crs=str(src_crs), width=width, height=height, bands=count)
                log.info(f"[OK] {src.name} already in {CRS_ANALYSIS} -- copied as-is.")
            else:
                _reproject_raster(src, dst, CRS_ANALYSIS)
                entry.update(status="reprojected", from_crs=str(src_crs), to_crs=CRS_ANALYSIS,
                             width=width, height=height, bands=count)
                log.info(f"[OK] {src.name} reprojected {src_crs} -> {CRS_ANALYSIS}")
        except Exception as e:  # noqa: BLE001
            log.error(f"[FAILED] {src.name}: {e}")
            entry["status"] = f"failed: {e}"
        manifest["rasters"].append(entry)


def _reproject_raster(src_path: Path, dst_path: Path, target_crs: str) -> None:
    with rasterio.open(src_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        kwargs = src.meta.copy()
        kwargs.update({"crs": target_crs, "transform": transform, "width": width, "height": height})
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(dst_path, "w", **kwargs) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                )


def process_csvs(manifest: dict) -> None:
    log.info("=" * 70)
    log.info("STEP 3/4 -- Tables (CSV)")
    log.info("=" * 70)
    for src, dst, note in CSV_SOURCES:
        entry = {"source": str(src), "output": str(dst), "note": note}
        if not src.exists():
            log.warning(f"[MISSING] {src.name} -- skipped.")
            entry["status"] = "missing_source"
            manifest["tables"].append(entry)
            continue
        try:
            df = None
            for enc in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    df = pd.read_csv(src, encoding=enc)
                    break
                except UnicodeDecodeError:
                    continue
            if df is None:
                raise RuntimeError("Could not decode file with utf-8/utf-8-sig/latin-1.")
            df.columns = [str(c).strip() for c in df.columns]
            df = df.dropna(how="all")
            dst.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(dst, index=False, encoding="utf-8-sig")
            entry.update(status="ok", rows=len(df), columns=list(df.columns))
            log.info(f"[OK] {src.name} -> {dst.name} ({len(df)} rows)")
        except Exception as e:  # noqa: BLE001
            log.error(f"[FAILED] {src.name}: {e}")
            entry["status"] = f"failed: {e}"
        manifest["tables"].append(entry)


def write_manifest_and_report(manifest: dict) -> None:
    log.info("=" * 70)
    log.info("STEP 4/4 -- Writing manifest + data inventory report")
    log.info("=" * 70)

    manifest_path = OUT_REPORTS / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)
    log.info(f"[OK] {manifest_path}")

    report_path = OUT_REPORTS / "data_inventory_report.md"
    lines = []
    lines.append("# Chennai Circular City DSS -- Data Inventory & Preprocessing Report\n")
    lines.append(f"Output folder: `{OUTPUT_ROOT}`\n")
    lines.append(f"Analysis CRS: `{CRS_ANALYSIS}` (UTM Zone 44N, metres) | GeoJSON CRS: `{CRS_GEOJSON}`\n")

    def status_icon(s):
        if s == "ok":
            return "OK"
        if s and str(s).startswith("failed"):
            return "FAILED"
        if s == "missing_source":
            return "MISSING"
        return str(s)

    lines.append("\n## Vector layers included\n")
    lines.append("| Layer (GeoPackage) | Output file | Features | Status | Note |")
    lines.append("|---|---|---|---|---|")
    for e in manifest["vector_layers"]:
        out_name = Path(e.get("output", "")).name
        lines.append(f"| `{e.get('gpkg_layer','-')}` | {out_name} | {e.get('features','-')} "
                      f"| {status_icon(e.get('status'))} | {e.get('note','')} |")

    lines.append("\n## Raster layers included\n")
    lines.append("| File | Size (px) | Bands | Status | Note |")
    lines.append("|---|---|---|---|---|")
    for e in manifest["rasters"]:
        out_name = Path(e.get("output", "")).name
        size = f"{e.get('width','-')}x{e.get('height','-')}"
        lines.append(f"| {out_name} | {size} | {e.get('bands','-')} | {status_icon(e.get('status'))} | {e.get('note','')} |")

    lines.append("\n## Tables included\n")
    lines.append("| File | Rows | Status | Note |")
    lines.append("|---|---|---|---|")
    for e in manifest["tables"]:
        out_name = Path(e.get("output", "")).name
        lines.append(f"| {out_name} | {e.get('rows','-')} | {status_icon(e.get('status'))} | {e.get('note','')} |")

    lines.append("\n## KML files deliberately excluded (and why)\n")
    lines.append("| File | Reason |")
    lines.append("|---|---|")
    for fname, reason in EXCLUDED_KML.items():
        lines.append(f"| {fname} | {reason} |")

    lines.append("\n## CSV files deliberately excluded (and why)\n")
    lines.append("| File | Reason |")
    lines.append("|---|---|")
    for fname, reason in EXCLUDED_CSV.items():
        lines.append(f"| {fname} | {reason} |")

    lines.append("\n## Gaps to be aware of before building the DSS\n")
    lines.append(f"- {MISSING_CATEGORIES_NOTE}\n")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"[OK] {report_path}")


# ==============================================================================
# MAIN
# ==============================================================================

def main() -> None:
    log.info("Chennai Circular City DSS -- preprocessing started")
    log.info(f"DATA_ROOT   = {DATA_ROOT}")
    log.info(f"OUTPUT_ROOT = {OUTPUT_ROOT}")
    log.info(f"KML engine  = {'pyogrio' if HAVE_PYOGRIO else 'fiona'}")

    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    if GPKG_PATH.exists():
        GPKG_PATH.unlink()  # start clean each run

    manifest = {"vector_layers": [], "rasters": [], "tables": []}

    process_vector_sources(manifest)
    process_administrative_boundary(manifest)
    process_parks(manifest)
    process_rasters(manifest)
    process_csvs(manifest)
    write_manifest_and_report(manifest)

    ok_vec = sum(1 for e in manifest["vector_layers"] if e.get("status") == "ok")
    ok_ras = sum(1 for e in manifest["rasters"] if e.get("status") in ("ok", "copied", "reprojected", "copied_no_crs"))
    ok_tab = sum(1 for e in manifest["tables"] if e.get("status") == "ok")

    log.info("=" * 70)
    log.info(f"DONE. Vector layers OK: {ok_vec}/{len(manifest['vector_layers'])} | "
             f"Rasters OK: {ok_ras}/{len(manifest['rasters'])} | Tables OK: {ok_tab}/{len(manifest['tables'])}")
    log.info(f"GeoPackage: {GPKG_PATH}")
    log.info(f"Report:     {OUT_REPORTS / 'data_inventory_report.md'}")
    log.info("Everything needed for the DSS step is now in the output folder.")


if __name__ == "__main__":
    main()
