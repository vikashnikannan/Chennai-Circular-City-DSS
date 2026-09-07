"""
Chennai Circular City DSS -- Home
==================================
Entry point for the workflow: pick a pathway, then explore priorities,
opportunities, the map, and the evidence behind each recommendation.

Local run:   streamlit run app.py
Deploy:      push this whole folder to a GitHub repo, then deploy app.py
             on https://share.streamlit.io (Streamlit Community Cloud).
"""
import altair as alt
import streamlit as st

from dss_logic import (
    load_raw, compute_score, pathway_cutoffs, band, DEFAULT_WEIGHTS, PRIORITY_HEX,
    methodology_stats,
)
from shared_ui import (
    inject_global_css, render_sidebar, render_hero, render_tile,
    render_methodology, render_limitations, render_credits, COLORS,
    APP_TITLE, APP_SUBTITLE,
)

st.set_page_config(page_title="Chennai Circular City DSS", layout="wide", initial_sidebar_state="expanded")
inject_global_css()
render_sidebar(active="home")

render_hero(APP_TITLE, APP_SUBTITLE)

df = load_raw()
combined_cutoffs = pathway_cutoffs(df, "combined", tuple(sorted(DEFAULT_WEIGHTS.items())))
df_scored = df.copy()
df_scored["score_default"] = compute_score(df_scored, DEFAULT_WEIGHTS)
df_scored["priority_default"] = df_scored["score_default"].apply(lambda s: band(s, combined_cutoffs))
stats = methodology_stats(df, df_scored)

# ------------------------------------------------------------- feature tiles
t1, t2, t3 = st.columns(3)
with t1:
    render_tile(":material/water_drop:", "Water Reuse",
                "Treated wastewater to nearby green infrastructure.", COLORS["water"])
    st.page_link("pages/1_Water_Reuse.py", label="Open Water Reuse", icon=":material/arrow_forward:")
with t2:
    render_tile(":material/recycling:", "Organic Waste",
                "Waste sites to nearby circular opportunities.", COLORS["green"])
    st.page_link("pages/2_Organic_Waste.py", label="Open Organic Waste", icon=":material/arrow_forward:")
with t3:
    render_tile(":material/eco:", "Decision Map",
                "Explore every opportunity across the city, together.", COLORS["orange"])
    st.page_link("pages/3_Decision_Map.py", label="Open Decision Map", icon=":material/arrow_forward:")

st.write("")

# ---------------------------------------------------------------- KPI strip
k1, k2, k3, k4 = st.columns(4)
with k1, st.container(border=True):
    st.metric("Opportunities assessed", f"{stats['n_total']:,}")
with k2, st.container(border=True):
    st.metric("High priority", f"{stats['n_high']:,}")
with k3, st.container(border=True):
    st.metric("Water reuse", f"{stats['n_water']:,}")
with k4, st.container(border=True):
    st.metric("Organic waste", f"{stats['n_waste']:,}")

st.divider()
st.subheader("Opportunities by priority")
band_counts = df_scored.groupby(["pathway", "priority_default"]).size().unstack(fill_value=0)
band_counts = band_counts.reindex(columns=["HIGH", "MODERATE", "LOW"], fill_value=0)
band_counts.index = band_counts.index.map({"water": "Water Reuse", "waste": "Organic Waste"})
chart_data = band_counts.reset_index().melt(
    id_vars="pathway", var_name="Priority", value_name="Count"
).rename(columns={"pathway": "Pathway"})

chart = (
    alt.Chart(chart_data)
    .mark_bar()
    .encode(
        x=alt.X("Pathway:N", title=None),
        y=alt.Y("Count:Q", title="Opportunities"),
        color=alt.Color(
            "Priority:N",
            scale=alt.Scale(domain=["HIGH", "MODERATE", "LOW"],
                             range=[PRIORITY_HEX["HIGH"], PRIORITY_HEX["MODERATE"], PRIORITY_HEX["LOW"]]),
        ),
        xOffset="Priority:N",
        tooltip=["Pathway", "Priority", "Count"],
    )
    .properties(height=260)
)
st.altair_chart(chart, width="stretch")

st.divider()
st.subheader("Methodology")
st.caption("How every recommendation in this tool is produced.")
st.page_link("pages/4_Data_Methodology.py", label="View full methodology", icon=":material/school:")

st.divider()
st.subheader("Data & Resources")
d1, d2 = st.columns(2)
with d1:
    st.download_button(
        "Download opportunity data (CSV)",
        df.to_csv(index=False),
        "circular_opportunities.csv",
        icon=":material/download:",
        width="stretch",
    )
with d2:
    st.page_link(
        "pages/4_Data_Methodology.py",
        label="View Data & Methodology",
        icon=":material/database:",
        width="stretch",
    )

st.divider()
render_limitations()
render_credits()
