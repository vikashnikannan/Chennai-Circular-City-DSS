# Chennai Circular City DSS

A decision-first spatial screening tool for two circular-economy pathways in Chennai:

- **Water reuse** -- where treated wastewater (STPs) could support nearby parks or green infrastructure
- **Organic waste** -- where waste facilities (biogas, biomethanisation, compost, resource-recovery)
  could support local circularity

Built so a municipal officer or planner with no GIS background can open it and immediately see what
to do, not a table of scores.

Flow: Question -> Opportunity -> Why -> Priority -> Recommended action -> Map -> Evidence
(instead of: Map -> Score -> Table).

## Live app

Once deployed (see below), your public link will look like:
`https://<your-app-name>.streamlit.app`

## Pages

| Page | What it answers |
|---|---|
| Overview (app.py) | Hero banner, 3 pathway tiles, KPI strip, priority chart |
| Water Reuse | Map + ranked table linked together, "why is this prioritised" bars |
| Organic Waste | Map + ranked table linked together, "why is this prioritised" bars |
| Decision Map | One combined map across both pathways, click a row to jump the map to it |
| Methodology | The ONLY page with the full pipeline, dataset list, and the coordinate-to-place-name conversion detail |

**Navigation** is a persistent dark left sidebar (large icon + label buttons), not a top bar --
one click to any section from anywhere, and the current section is always highlighted.

**Each assessment page shows only its own methodology** -- five short icon steps specific to that
pathway (Water Reuse, Organic Waste, or the Decision Map), not the full pipeline. The full detail,
dataset list, and scoring formula live solely on the Methodology page, linked from the bottom of
every short summary.

**Click a table row -> jump to it on the map.** Every table (pathway pages and the Decision Map)
uses Streamlit's row-selection; picking a row re-centres and re-zooms the map to that exact
source-destination pair and highlights it with a thicker, brighter line.

**Coordinates -> place names.** The raw data only carries latitude/longitude. `geocode.py` matches
every point, live in the app, to the closest of ~55 known Chennai localities/landmarks and produces
a readable label (e.g. "Kodungaiyur STP", "Green space near Velachery"). This is a nearest-known-
place match, not a verified facility identity -- labels say "area" when the nearest match is more
than 2.5 km away, so the tool doesn't imply more precision than the data actually has. The full
worked example (icon by icon) is on the Methodology page under "From coordinates to place names".

Important: this is a spatial screening/prioritisation tool. It does not certify that a pathway is
technically safe, permitted, or engineered, it tells you where it is worth assessing further.

## Repo layout

```
app.py                        Home page: hero, pathway tiles, KPIs, chart
dss_logic.py                  Scoring, priority bands, datasets, per-pathway methodology content
geocode.py                    Chennai place gazetteer + coordinate -> place-name matching
shared_ui.py                  Design system: sidebar nav, hero/tiles, factor bars, methodology/credits
ui_components.py              Shared rendering for the two pathway pages (map + table + why)
pages/
  1_Water_Reuse.py
  2_Organic_Waste.py
  3_Decision_Map.py           Uses pydeck only (no folium) -- see note below
  4_Data_Methodology.py
circular_opportunities.csv    Scored source-to-destination pairs (output of scripts/priority_score.py)
requirements.txt              Dependencies for the deployed app
.streamlit/config.toml        Theme
scripts/                      Original GIS preprocessing and scoring pipeline (not run by the app itself)
  preprocess_chennai_gis.py
  priority_score.py
  requirements_gis.txt
```

### About the `ModuleNotFoundError: No module named 'folium'` fix

The Decision Map previously used `folium` + `streamlit-folium` for its map, which is a separate
dependency from the `pydeck` used elsewhere. That mismatch is what caused the crash. The Decision
Map has been rebuilt on `pydeck` (matching the other two map pages), so `folium` and
`streamlit-folium` have been removed from `requirements.txt` entirely -- nothing extra to install.

If you still see that error, it means your virtual environment has an old install; run:
```bash
pip install -r requirements.txt
```
from inside the `chennai-dss` folder with your venv active, then re-run the app.

All filenames are plain ASCII on purpose -- Streamlit's multipage routing (`st.page_link`, the
`pages/` folder) matches on the exact filename, and non-ASCII filenames are a common source of
"page not found" errors, especially on Windows.

## Run locally

```bash
python -m venv venv
source venv/bin/activate        # venv\Scripts\activate on Windows
pip install -r requirements.txt
streamlit run app.py
```

## Deploy for a public link (Streamlit Community Cloud, free)

1. Push this folder to GitHub.
2. Go to https://share.streamlit.io -> New app.
3. Pick this repo, branch `main`, main file path `app.py`.
4. Deploy. You will get a public `https://<name>.streamlit.app` URL -- share that link (or a QR code
   of it) directly; no login needed for viewers.

If you already deployed a previous version of this app from the same repo, pushing new commits to
`main` triggers an automatic redeploy -- no need to create a new app on Streamlit Community Cloud.

## Updating the data

If you re-run the GIS pipeline in `scripts/` (see `scripts/preprocess_chennai_gis.py` and
`scripts/priority_score.py`) and it produces a new `circular_opportunities.csv`, replace the file at
the repo root and push -- the app reads it directly, no code changes needed.

## Known next step

The climate-need factor currently uses a flood-hazard-proximity proxy (see `scripts/priority_score.py`
-> `climate_need_proxy()`). Once the LST/NDVI rasters open cleanly (PROJ conflict resolved), switch to
`sample_raster_climate()` in the same file for a more defensible climate-need score -- everything
downstream (bands, explanations, map) will pick it up automatically.
