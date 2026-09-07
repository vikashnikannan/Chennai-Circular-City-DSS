"""Data & Methodology: the ONLY page with the full pipeline, dataset list,
and coordinate-to-name conversion detail. Every other page shows just a
five-step summary for its own pathway and links back here."""
from pathlib import Path

import pandas as pd
import streamlit as st

from dss_logic import (
    load_raw, compute_score, pathway_cutoffs, band, DEFAULT_WEIGHTS, WEIGHT_PRESETS,
    methodology_stats, DATA_PATH, name_conversion_examples, PRIORITY_HEX,
)
from shared_ui import (
    inject_global_css, render_sidebar, render_methodology,
    render_limitations, render_credits, COLORS, icon_html,
)

st.set_page_config(page_title="Methodology: Chennai Circular City DSS", layout="wide")
inject_global_css()
render_sidebar(active="methodology")

st.title("Data & Methodology")
st.caption("A transparent account of how every recommendation in this tool is produced.")

df = load_raw()
combined_cutoffs = pathway_cutoffs(df, "combined", tuple(sorted(DEFAULT_WEIGHTS.items())))
df_scored = df.copy()
df_scored["score_default"] = compute_score(df_scored, DEFAULT_WEIGHTS)
df_scored["priority_default"] = df_scored["score_default"].apply(lambda s: band(s, combined_cutoffs))

render_methodology(methodology_stats(df, df_scored), condensed=False)

# ---------------------------------------------------------------------------
# Coordinate -> place name conversion: the icon flow, colour coding, and a
# real worked example straight from the loaded data.
# ---------------------------------------------------------------------------
st.divider()
st.subheader("From coordinates to place names")
st.caption(
    "The source data only carries raw latitude/longitude. Every point is matched, live in "
    "the app, to the closest known Chennai locality -- turning a coordinate into a name a "
    "planner can actually read."
)

f1, f2, f3, f4 = st.columns(4)
with f1:
    st.markdown(
        f"""<div class="ccdss-step-card"><div class="ccdss-step-icon">{icon_html(':material/my_location:', 28)}</div>
        <div class="ccdss-step-title2">1. Raw coordinate</div>
        <div class="ccdss-step-desc2">Each source/destination is a lat, lon pair from the GIS layer.</div></div>""",
        unsafe_allow_html=True,
    )
with f2:
    st.markdown(
        f"""<div class="ccdss-step-card"><div class="ccdss-step-icon">{icon_html(':material/travel_explore:', 28)}</div>
        <div class="ccdss-step-title2">2. Nearest-place match</div>
        <div class="ccdss-step-desc2">Compared against ~55 known Chennai localities and landmarks.</div></div>""",
        unsafe_allow_html=True,
    )
with f3:
    st.markdown(
        f"""<div class="ccdss-step-card"><div class="ccdss-step-icon">{icon_html(':material/label:', 28)}</div>
        <div class="ccdss-step-title2">3. Label assigned</div>
        <div class="ccdss-step-desc2">"STP", "Waste Facility" or "Green space", plus the matched place.</div></div>""",
        unsafe_allow_html=True,
    )
with f4:
    st.markdown(
        f"""<div class="ccdss-step-card"><div class="ccdss-step-icon">{icon_html(':material/palette:', 28)}</div>
        <div class="ccdss-step-title2">4. Colour by priority</div>
        <div class="ccdss-step-desc2">Red = High, amber = Moderate, green = Low, on every map and table.</div></div>""",
        unsafe_allow_html=True,
    )

st.write("")
st.markdown("**Worked examples, from the live dataset**")
examples = name_conversion_examples(df, n=3)
for ex in examples:
    c1, c2, c3 = st.columns([1, 0.3, 1])
    with c1:
        st.markdown(
            f"""<div class="ccdss-geo-card">
                <b>Source</b> ({'Water' if ex['pathway']=='water' else 'Waste'})<br/>
                <span class="ccdss-geo-coord">{ex['source']['raw_coordinate']}</span><br/><br/>
                nearest known place: <b>{ex['source']['matched_place']}</b>
                ({ex['source']['distance_km']} km away)<br/><br/>
                <b>Final label:</b> {ex['source']['final_label']}
            </div>""",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(f"<div class='ccdss-geo-arrow'>{icon_html(':material/arrow_forward:', 26)}</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(
            f"""<div class="ccdss-geo-card">
                <b>Destination</b> (Park / green space)<br/>
                <span class="ccdss-geo-coord">{ex['dest']['raw_coordinate']}</span><br/><br/>
                nearest known place: <b>{ex['dest']['matched_place']}</b>
                ({ex['dest']['distance_km']} km away)<br/><br/>
                <b>Final label:</b> {ex['dest']['final_label']}
            </div>""",
            unsafe_allow_html=True,
        )
    st.write("")

st.markdown(
    """<div class="ccdss-info-box">
    This is a nearest-known-place match, not a verified facility identity. Where the closest
    match is more than 2.5 km away, the label says "area" to make that distance honest rather
    than implying precision the data does not have.
    </div>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
st.divider()
st.subheader("How priority bands are set")
st.markdown("""
For each pathway, the tool scores every opportunity city-wide, then splits that full set into
three equal-sized groups (terciles):

- **HIGH**: top third of scores for that pathway, city-wide
- **MODERATE**: middle third
- **LOW**: bottom third

Cutoffs are calculated on the full city-wide set before any search-radius filtering, so "HIGH
priority" keeps its meaning even as someone narrows the radius on an assessment page.
""")

st.divider()
st.subheader("Weighting presets available in the tool")
preset_df = pd.DataFrame(WEIGHT_PRESETS).T
preset_df.columns = [c.capitalize() for c in preset_df.columns]
preset_df.index.name = "Preset"
st.dataframe(preset_df, width="stretch")

st.divider()
st.subheader("Data & Downloads")
st.caption("Resources that actually exist in this project.")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESOURCES = [
    {
        "name": "Opportunity data", "description": "Every scored source-to-destination pair used in the DSS.",
        "path": DATA_PATH, "format": "CSV", "mime": "text/csv", "icon": ":material/table_chart:",
    },
    {
        "name": "GIS preprocessing script", "description": "Cleans and prepares the raw GCC GIS layers.",
        "path": PROJECT_ROOT / "scripts" / "preprocess_chennai_gis.py", "format": "Python",
        "mime": "text/x-python", "icon": ":material/code:",
    },
    {
        "name": "Priority scoring script", "description": "Computes the five-factor priority score for every pair.",
        "path": PROJECT_ROOT / "scripts" / "priority_score.py", "format": "Python",
        "mime": "text/x-python", "icon": ":material/code:",
    },
    {
        "name": "Project documentation", "description": "Repo layout, local run, and deploy instructions.",
        "path": PROJECT_ROOT / "README.md", "format": "Markdown", "mime": "text/markdown",
        "icon": ":material/description:",
    },
]

res_cols = st.columns(2)
for i, res in enumerate(RESOURCES):
    with res_cols[i % 2]:
        with st.container(border=True):
            st.markdown(f"**{res['icon']} {res['name']}**  ({res['format']})")
            st.caption(res["description"])
            if res["path"].exists():
                st.download_button(
                    f"Download {res['format']}", res["path"].read_bytes(), res["path"].name,
                    mime=res["mime"], key=f"dl_{res['name']}", icon=":material/download:",
                )
            else:
                st.caption("Data layer unavailable.")

st.divider()
render_limitations()
render_credits()
