from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from dss_logic import (
    load_raw, compute_score, recompute_feasibility, pathway_cutoffs, band,
    reasons, factor_cards, contribution_breakdown,
    WEIGHT_PRESETS, PATHWAY_LABEL, PATHWAY_QUESTION, PRIORITY_HEX,
)
from shared_ui import (
    inject_global_css, render_sidebar, render_priority_panel,
    render_score_badge, render_factor_bars, render_mini_methodology,
    render_limitations, render_credits, COLORS,
)

MAP_ROW_CAP = 250

HIGHLIGHT_COLOR = [21, 101, 255, 255]  # vivid blue -- deliberately outside the red/amber/green
                                        # priority palette, so the selected opportunity is always
                                        # unmistakable regardless of its own priority colour.


def render_pathway_page(pathway: str) -> None:
    st.set_page_config(page_title=f"{PATHWAY_LABEL[pathway]}: Chennai Circular City DSS", layout="wide")
    inject_global_css()
    render_sidebar(active=pathway)

    df = load_raw()
    st.title(PATHWAY_LABEL[pathway])
    st.caption(PATHWAY_QUESTION[pathway])

    # -------------------------------------------------------------- controls
    top1, top2 = st.columns([2, 1])
    with top1:
        max_dist_km = st.slider("Search radius (km)", 1.0, 10.0, 5.0, 0.5)
    with top2:
        preset_name = st.selectbox("What matters most?", list(WEIGHT_PRESETS.keys()))

    with st.expander(":material/tune: Advanced settings"):
        preset = WEIGHT_PRESETS[preset_name]
        w_r = st.slider("Resource strength", 0, 50, preset["resource"], key=f"{pathway}_wr")
        w_d = st.slider("Nearby demand", 0, 50, preset["demand"], key=f"{pathway}_wd")
        w_c = st.slider("Climate need", 0, 50, preset["climate"], key=f"{pathway}_wc")
        w_f = st.slider("Spatial feasibility", 0, 50, preset["feasibility"], key=f"{pathway}_wf")
        w_i = st.slider("Infrastructure readiness", 0, 50, preset["infrastructure"], key=f"{pathway}_wi")
        weights = {"resource": w_r, "demand": w_d, "climate": w_c, "feasibility": w_f, "infrastructure": w_i}

    # City-wide cutoffs computed before radius filtering, so HIGH/MODERATE/LOW
    # always means "top/middle/bottom third city-wide for this pathway".
    cutoffs = pathway_cutoffs(df, pathway, tuple(sorted(weights.items())))

    work = df[df["pathway"] == pathway].copy()
    work = work[work["distance_m"] <= max_dist_km * 1000].copy()
    if work.empty:
        st.info("No matches at this radius. Widen the search radius above.")
        render_credits()
        return

    work["feasibility"] = recompute_feasibility(work, max_dist_km)
    work["score"] = compute_score(work, weights)
    work["priority"] = work["score"].apply(lambda s: band(s, cutoffs))
    work = work.sort_values("score", ascending=False).reset_index(drop=True)

    n_high = int((work["priority"] == "HIGH").sum())
    n_mod = int((work["priority"] == "MODERATE").sum())
    n_low = int((work["priority"] == "LOW").sum())

    st.divider()

    # ---------------------------------------------------- map / table split
    map_col, table_col = st.columns([1.15, 1.0])

    with table_col:
        st.markdown(f"<div class='ccdss-panel-title'>Top {PATHWAY_LABEL[pathway]} Opportunities</div>",
                    unsafe_allow_html=True)
        selected_priorities = render_priority_panel(
            {"HIGH": n_high, "MODERATE": n_mod, "LOW": n_low}, key=pathway
        )
        filtered = (
            work[work["priority"].isin(selected_priorities)].reset_index(drop=True)
            if selected_priorities else work.iloc[0:0]
        )

        if filtered.empty:
            st.info("No opportunities match the selected priority levels.")
            selected_idx = None
        else:
            table_view = pd.DataFrame({
                "Source": filtered["source_label"],
                "Destination": filtered["dest_label"],
                "Distance (km)": (filtered["distance_m"] / 1000).round(1),
                "Priority": filtered["priority"],
            })
            event = st.dataframe(
                table_view,
                hide_index=True,
                width="stretch",
                height=360,
                on_select="rerun",
                selection_mode="single-row",
                key=f"{pathway}_table",
            )
            rows = event.selection.rows if event and event.selection else []
            selected_idx = rows[0] if rows else 0
            st.caption("Click a row to view it on the map.")

    with map_col:
        st.markdown("<div class='ccdss-panel-title'>Map</div>", unsafe_allow_html=True)
        if filtered.empty:
            st.info("Nothing to show on the map for this filter.")
        else:
            selected_row = filtered.iloc[selected_idx]
            render_map(filtered, selected_row)
            render_map_legend()

    st.divider()

    # ------------------------------------------------------- why prioritised
    if not filtered.empty:
        selected_row = filtered.iloc[selected_idx]
        st.markdown(
            f"### {selected_row['source_label']}  &rarr;  {selected_row['dest_label']}"
        )
        d1, d2 = st.columns([1, 3])
        with d1:
            st.metric("Distance", f"{selected_row['distance_m']/1000:.1f} km")
        with d2:
            render_score_badge(float(selected_row["score"]) * 100, selected_row["priority"])

        st.write("")
        st.markdown("<div class='ccdss-panel-title'>Why is this location prioritised?</div>", unsafe_allow_html=True)
        render_factor_bars(
            contribution_breakdown(selected_row, weights),
            overall_priority=selected_row["priority"],
        )
        st.caption("Screening result, not an engineering approval.")

    st.divider()

    with st.expander("Full results table and download"):
        st.dataframe(
            work[["opportunity_id", "source_label", "dest_label", "distance_m", "priority", "score"]]
                .rename(columns={"opportunity_id": "id", "source_label": "source", "dest_label": "destination"}),
            hide_index=True, width="stretch",
        )
        st.download_button(
            "Download filtered results (CSV)", work.to_csv(index=False),
            f"circular_opportunities_{pathway}_filtered.csv",
        )

    st.divider()
    render_mini_methodology(pathway)

    st.divider()
    render_limitations()
    render_credits()


def render_map(filtered: pd.DataFrame, selected_row: pd.Series) -> None:
    map_data = filtered.head(MAP_ROW_CAP)
    lines = pd.DataFrame({
        "source_position": list(zip(map_data.src_lon, map_data.src_lat)),
        "target_position": list(zip(map_data.dst_lon, map_data.dst_lat)),
        "color": map_data["priority"].map({
            "HIGH": [192, 57, 43, 160], "MODERATE": [201, 138, 44, 140], "LOW": [47, 125, 79, 110],
        }),
        "tooltip": [
            f"{s} \u2192 {d}<br/>{p} priority \u00b7 {round(m/1000, 1)} km"
            for s, d, p, m in zip(map_data.source_label, map_data.dest_label, map_data.priority, map_data.distance_m)
        ],
    })
    line_layer = pdk.Layer(
        "LineLayer", data=lines, get_source_position="source_position",
        get_target_position="target_position", get_width=2.5, get_color="color",
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
    highlight_line_layer = pdk.Layer(
        "LineLayer", data=highlight_line, get_source_position="source_position",
        get_target_position="target_position", get_width=7, get_color=HIGHLIGHT_COLOR,
        pickable=True,
    )

    points = pd.DataFrame({
        "position": [
            (selected_row["src_lon"], selected_row["src_lat"]),
            (selected_row["dst_lon"], selected_row["dst_lat"]),
        ],
        "tooltip": [
            f"SOURCE<br/>{selected_row['source_label']}",
            f"DESTINATION<br/>{selected_row['dest_label']}",
        ],
    })
    point_layer = pdk.Layer(
        "ScatterplotLayer", data=points, get_position="position",
        get_fill_color=HIGHLIGHT_COLOR, get_line_color=[255, 255, 255, 255], get_line_width=2, stroked=True,
        get_radius=100, pickable=True,
    )

    mid_lat = (selected_row["src_lat"] + selected_row["dst_lat"]) / 2
    mid_lon = (selected_row["src_lon"] + selected_row["dst_lon"]) / 2
    # zoom is tighter for a short hop, wider for a long one, so the selected
    # pair always fills the frame -- this is the "click a row -> jump there" behaviour.
    span_km = selected_row["distance_m"] / 1000
    zoom = 14 if span_km < 1 else 13 if span_km < 3 else 12 if span_km < 6 else 11
    view = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=zoom)

    st.pydeck_chart(pdk.Deck(
        layers=[line_layer, highlight_line_layer, point_layer],
        initial_view_state=view, map_style=None,
        tooltip={"html": "{tooltip}", "style": {"backgroundColor": "#0B2B22", "color": "white", "fontSize": "0.95rem"}},
    ), height=430, key=f"map_{selected_row.name}_{span_km:.2f}")


def render_map_legend() -> None:
    st.markdown(
        f"""
        <div style="font-size:1rem; color:{COLORS['muted']};">
        <span style="color:{PRIORITY_HEX['HIGH']};">&#9679;</span> High &nbsp;
        <span style="color:{PRIORITY_HEX['MODERATE']};">&#9679;</span> Moderate &nbsp;
        <span style="color:{PRIORITY_HEX['LOW']};">&#9679;</span> Low &nbsp;
        &nbsp;|&nbsp;
        <span style="color:rgb(21,101,255);">&#9679;</span> Selected (blue) &nbsp;
        &nbsp;|&nbsp; hover any line or point for details
        </div>
        """,
        unsafe_allow_html=True,
    )
