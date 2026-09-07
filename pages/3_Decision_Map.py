"""Decision Map: one combined city map across both pathways. Select a row in
the table (or leave the top recommendation selected) to see the full
reasoning behind that opportunity. Uses pydeck only (no folium/streamlit-
folium dependency), so it needs nothing beyond requirements.txt."""
import pandas as pd
import pydeck as pdk
import streamlit as st

from dss_logic import (
    load_raw, compute_score, recompute_feasibility, pathway_cutoffs, band,
    contribution_breakdown, DEFAULT_WEIGHTS, PRIORITY_HEX,
)
from shared_ui import (
    inject_global_css, render_sidebar, render_priority_panel,
    render_score_badge, render_factor_bars, render_mini_methodology,
    render_limitations, render_credits, COLORS,
)

st.set_page_config(page_title="Decision Map: Chennai Circular City DSS", layout="wide")
inject_global_css()
render_sidebar(active="map")

MAP_CAP = 300

st.title("Decision Map")
st.caption("Explore all circular opportunities across Chennai.")

df = load_raw()

c1, c2 = st.columns([1, 1])
with c1:
    pathway_choice = st.selectbox("Pathway", ["Combined", "Water Reuse", "Organic Waste"])
with c2:
    max_dist_km = st.slider("Search radius (km)", 1.0, 10.0, 3.0, 0.5)

pathway_key = {"Combined": "combined", "Water Reuse": "water", "Organic Waste": "waste"}[pathway_choice]

work = df.copy()
if pathway_key != "combined":
    work = work[work["pathway"] == pathway_key]
work = work[work["distance_m"] <= max_dist_km * 1000].copy()

weights_tuple = tuple(sorted(DEFAULT_WEIGHTS.items()))
frames = []
for p in (["water", "waste"] if pathway_key == "combined" else [pathway_key]):
    cutoffs = pathway_cutoffs(df, p, weights_tuple)
    sub = work[work["pathway"] == p].copy()
    if sub.empty:
        continue
    sub["feasibility"] = recompute_feasibility(sub, max_dist_km)
    sub["score"] = compute_score(sub, DEFAULT_WEIGHTS)
    sub["priority"] = sub["score"].apply(lambda s: band(s, cutoffs))
    frames.append(sub)

work = pd.concat(frames, ignore_index=True) if frames else work.iloc[0:0]

st.divider()
map_col, side_col = st.columns([1.6, 1.0])

with side_col:
    counts = work["priority"].value_counts().to_dict() if len(work) else {}
    priority_pick = st.selectbox("Priority", ["All", "High", "Moderate", "Low"])
    selected_priorities = (
        ["HIGH", "MODERATE", "LOW"] if priority_pick == "All" else [priority_pick.upper()]
    )

filtered = work[work["priority"].isin(selected_priorities)].reset_index(drop=True) if len(work) else work.iloc[0:0]
filtered = filtered.sort_values("score", ascending=False).reset_index(drop=True).head(MAP_CAP)

with side_col:
    if filtered.empty:
        st.info("No opportunities match these filters. Widen the radius.")
        selected_idx = None
    else:
        table_view = pd.DataFrame({
            "Source": filtered["source_label"],
            "Destination": filtered["dest_label"],
            "Priority": filtered["priority"],
        })
        event = st.dataframe(
            table_view, hide_index=True, width="stretch", height=280,
            on_select="rerun", selection_mode="single-row", key="decision_map_table",
        )
        rows = event.selection.rows if event and event.selection else []
        selected_idx = rows[0] if rows else 0
        st.caption(f"Top {len(filtered):,} by score. Click a row to jump the map to it.")

if not filtered.empty:
    selected_row = filtered.iloc[selected_idx]

    with map_col:
        HIGHLIGHT_COLOR = [21, 101, 255, 255]  # vivid blue, distinct from the red/amber/green
                                                # priority palette, so the selection always stands out.
        lines = pd.DataFrame({
            "source_position": list(zip(filtered.src_lon, filtered.src_lat)),
            "target_position": list(zip(filtered.dst_lon, filtered.dst_lat)),
            "color": filtered["priority"].map({
                "HIGH": [192, 57, 43, 150], "MODERATE": [201, 138, 44, 130], "LOW": [47, 125, 79, 100],
            }),
            "tooltip": [
                f"{s} \u2192 {d}<br/>{p} priority \u00b7 {round(m/1000, 1)} km"
                for s, d, p, m in zip(filtered.source_label, filtered.dest_label, filtered.priority, filtered.distance_m)
            ],
        })
        line_layer = pdk.Layer(
            "LineLayer", data=lines, get_source_position="source_position",
            get_target_position="target_position", get_width=2, get_color="color",
            pickable=True,
        )

        sel_tooltip = (
            f"SELECTED<br/>{selected_row['source_label']} \u2192 {selected_row['dest_label']}<br/>"
            f"{selected_row['priority']} priority \u00b7 {selected_row['distance_m']/1000:.1f} km \u00b7 "
            f"score {selected_row['score']*100:.0f}/100"
        )
        highlight_line = pd.DataFrame({
            "source_position": [(selected_row["src_lon"], selected_row["src_lat"])],
            "target_position": [(selected_row["dst_lon"], selected_row["dst_lat"])],
            "tooltip": [sel_tooltip],
        })
        highlight_layer = pdk.Layer(
            "LineLayer", data=highlight_line, get_source_position="source_position",
            get_target_position="target_position", get_width=7, get_color=HIGHLIGHT_COLOR,
            pickable=True,
        )

        all_points = pd.DataFrame({
            "position": list(zip(filtered.src_lon, filtered.src_lat)) + list(zip(filtered.dst_lon, filtered.dst_lat)),
            "color": (
                list(filtered["priority"].map({
                    "HIGH": [192, 57, 43, 200], "MODERATE": [201, 138, 44, 180], "LOW": [47, 125, 79, 160],
                }))
                * 2
            ),
            "tooltip": (
                [f"SOURCE<br/>{s}" for s in filtered.source_label]
                + [f"DESTINATION<br/>{d}" for d in filtered.dest_label]
            ),
        })
        point_layer = pdk.Layer(
            "ScatterplotLayer", data=all_points, get_position="position",
            get_fill_color="color", get_radius=55, pickable=True,
        )

        selected_points = pd.DataFrame({
            "position": [
                (selected_row["src_lon"], selected_row["src_lat"]),
                (selected_row["dst_lon"], selected_row["dst_lat"]),
            ],
            "tooltip": [
                f"SOURCE (selected)<br/>{selected_row['source_label']}",
                f"DESTINATION (selected)<br/>{selected_row['dest_label']}",
            ],
        })
        selected_point_layer = pdk.Layer(
            "ScatterplotLayer", data=selected_points, get_position="position",
            get_fill_color=HIGHLIGHT_COLOR, get_line_color=[255, 255, 255, 255], get_line_width=2, stroked=True,
            get_radius=120, pickable=True,
        )

        mid_lat = (selected_row["src_lat"] + selected_row["dst_lat"]) / 2
        mid_lon = (selected_row["src_lon"] + selected_row["dst_lon"]) / 2
        span_km = selected_row["distance_m"] / 1000
        zoom = 14 if span_km < 1 else 13 if span_km < 3 else 12 if span_km < 6 else 11
        view = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=zoom)

        st.pydeck_chart(
            pdk.Deck(
                layers=[line_layer, highlight_layer, point_layer, selected_point_layer],
                initial_view_state=view, map_style=None,
                tooltip={"html": "{tooltip}", "style": {"backgroundColor": "#0B2B22", "color": "white", "fontSize": "0.95rem"}},
            ),
            height=560,
            key=f"decision_map_{selected_idx}_{span_km:.2f}",
        )
        st.markdown(
            f"""<div style="font-size:1rem; color:{COLORS['muted']};">
            <span style="color:{PRIORITY_HEX['HIGH']};">&#9679;</span> High &nbsp;
            <span style="color:{PRIORITY_HEX['MODERATE']};">&#9679;</span> Moderate &nbsp;
            <span style="color:{PRIORITY_HEX['LOW']};">&#9679;</span> Low &nbsp;
            &nbsp;|&nbsp;
            <span style="color:rgb(21,101,255);">&#9679;</span> Selected (blue) &nbsp;
            &nbsp;|&nbsp; hover any line or point for details
            </div>""",
            unsafe_allow_html=True,
        )

    with side_col:
        st.markdown("<div class='ccdss-panel-title'>Opportunity Details</div>", unsafe_allow_html=True)
        st.markdown(f"**{selected_row['source_label']}  &rarr;  {selected_row['dest_label']}**")
        d1, d2 = st.columns(2)
        d1.metric("Distance", f"{selected_row['distance_m']/1000:.1f} km")
        d2.metric("Pathway", "Water" if selected_row["pathway"] == "water" else "Waste")
        render_score_badge(float(selected_row["score"]) * 100, selected_row["priority"])

    st.divider()
    st.markdown("<div class='ccdss-panel-title'>Why is this location prioritised?</div>", unsafe_allow_html=True)
    render_factor_bars(
        contribution_breakdown(selected_row, DEFAULT_WEIGHTS),
        overall_priority=selected_row["priority"],
    )
    st.caption("Screening result, not an engineering approval.")

st.divider()
render_mini_methodology("map")

st.divider()
render_limitations()
render_credits()
