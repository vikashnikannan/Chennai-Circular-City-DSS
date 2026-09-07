"""
Chennai Circular City DSS -- shared visual design system and UI components.

Design language: a persistent dark sidebar for navigation (large icon + label
buttons, one click to any section), light content area, big legible type, and
short-as-possible copy. Every icon uses Streamlit's built-in Material Symbols
shortcodes (":material/xxx:") -- no emoji anywhere in the interface.

Each page pulls only the pieces it needs from here, so the table, map, and
score views feel like one connected tool instead of separate pages.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dss_logic import (
    DATASETS, METHOD_FLOW, DATA_TO_ACTION_FLOW, SCORE_FORMULA_TERMS,
    DEFAULT_WEIGHTS, PRIORITY_HEX, PATHWAY_MINI_METHOD, PATHWAY_MINI_INTRO,
)

# ------------------------------------------------------------------ palette --
COLORS = {
    "primary": "#0B4F3F",
    "primary_dark": "#083B30",
    "teal": "#0E7C86",
    "water": "#1565C0",
    "green": "#2E7D32",
    "orange": "#C56A1F",
    "high": "#C0392B",
    "moderate": "#C98A2C",
    "low": "#2F7D4F",
    "border": "#E1E5E2",
    "text": "#1F2A24",
    "muted": "#5B6B63",
    "panel": "#F6F8F6",
    "sidebar": "#0B2B22",
    "sidebar_active": "#123D30",
}

PROJECT_REPO_URL = ""  # left blank on purpose -- see credits section


def icon_html(code: str, size: int = 22, color: str | None = None) -> str:
    """Converts a Streamlit-style ':material/xxx:' shortcode into an actual
    rendered icon glyph for use INSIDE raw HTML (st.markdown unsafe_allow_html
    blocks). Streamlit only auto-renders ':material/xxx:' shortcodes inside
    its own native widgets (buttons, page_link, metric, etc.) -- inside plain
    HTML strings they show up as literal text, which is what this fixes."""
    name = code.strip()
    if name.startswith(":material/") and name.endswith(":"):
        name = name[len(":material/"):-1]
    style = f"font-size:{size}px;"
    if color:
        style += f"color:{color};"
    return f'<span class="material-symbols-outlined" style="{style}">{name}</span>'


def _priority_dot(level: str) -> str:
    hexcolor = PRIORITY_HEX[level]
    return f':color[\u25cf]{{foreground="{hexcolor}"}}'


def inject_global_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,300..600,0..1,-50..200&display=swap');

        .material-symbols-outlined {{
            font-family: 'Material Symbols Outlined'; font-weight: normal; font-style: normal;
            line-height: 1; letter-spacing: normal; text-transform: none; display: inline-block;
            white-space: nowrap; word-wrap: normal; direction: ltr; vertical-align: middle;
            -webkit-font-smoothing: antialiased;
        }}

        :root {{ --ccdss-font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; }}
        html {{ font-size: 18px; }}
        html, body, .stApp, .block-container,
        h1, h2, h3, h4, h5, h6, p, li, span, label, div,
        button, input, textarea, select, table, th, td {{ font-family: var(--ccdss-font); }}

        .block-container {{ padding-top: 1.4rem; padding-bottom: 2rem; max-width: 1340px; }}
        h1, h2, h3 {{ color: {COLORS['text']}; font-weight: 800; }}
        h1 {{ font-size: 2.5rem !important; }}
        h2 {{ font-size: 1.7rem !important; }}
        h3 {{ font-size: 1.35rem !important; }}
        h4, h5 {{ font-size: 1.15rem !important; }}
        p, li, span, label, .stMarkdown {{ color: {COLORS['text']}; font-size: 1.08rem; }}
        [data-testid="stCaptionContainer"], .stCaption {{ font-size: 1rem; }}
        [data-testid="stMetricValue"] {{ font-size: 2.2rem !important; }}
        [data-testid="stMetricLabel"] {{ font-size: 1.05rem !important; }}
        .stButton > button, .stDownloadButton > button {{ font-size: 1.05rem; }}
        [data-testid="stExpander"] summary {{ font-size: 1.1rem; font-weight: 600; }}

        /* Hide Streamlit's own auto-generated page list -- we render a
        custom nav below, so this stops the sidebar showing every page
        twice ("app", "Water Reuse", ... followed by our own nav). */
        [data-testid="stSidebarNav"] {{ display: none !important; }}

        /* ---------------------------------------------------------- sidebar */
        section[data-testid="stSidebar"] {{
            background: {COLORS['sidebar']}; min-width: 300px !important; width: 300px !important;
        }}
        section[data-testid="stSidebar"] * {{ color: #EAF3EE; }}
        section[data-testid="stSidebar"] .stButton > button {{
            width: 100%; text-align: left; background: transparent; border: none;
            color: #CFE3D8; font-size: 1.22rem; font-weight: 600; padding: 0.7rem 0.6rem;
            border-radius: 10px; margin-bottom: 0.15rem; display: flex; gap: 0.6rem;
        }}
        section[data-testid="stSidebar"] .stButton > button:hover {{
            background: {COLORS['sidebar_active']}; color: #FFFFFF;
        }}
        section[data-testid="stSidebar"] [data-testid="stPageLink"] p {{ font-size: 1.22rem !important; font-weight: 600; }}
        section[data-testid="stSidebar"] .stButton > button:focus:not(:active) {{ color: #FFFFFF; }}
        .ccdss-side-brand {{ font-size: 1.55rem; font-weight: 900; color: #FFFFFF; line-height: 1.3; letter-spacing: 0.01em; }}
        .ccdss-side-sub {{ font-size: 0.92rem; color: #9FC2AF; margin-bottom: 1.2rem; }}
        .ccdss-side-active {{
            background: #FFFFFF; color: {COLORS['primary_dark']} !important; font-weight: 800;
            border-radius: 10px; padding: 0.7rem 0.9rem; margin-bottom: 0.15rem; font-size: 1.22rem;
            display: flex; align-items: center; gap: 0.6rem;
        }}
        .ccdss-side-active .material-symbols-outlined {{ color: {COLORS['primary_dark']}; }}
        .ccdss-side-tagline {{
            font-size: 1.12rem; color: #FFFFFF; font-weight: 500; line-height: 1.55rem;
            margin-top: 1.8rem; padding-top: 1.2rem; border-top: 1px solid rgba(255,255,255,0.18);
        }}
        .ccdss-side-tagline b {{ display:block; font-size: 1.22rem; font-weight: 800; margin-bottom: 0.4rem; }}
        .ccdss-side-foot {{ font-size: 0.82rem; color: #7FA895; margin-top: 1rem; line-height: 1.4rem; }}

        /* ------------------------------------------------------------- hero */
        .ccdss-hero {{
            background: linear-gradient(120deg, {COLORS['primary_dark']} 0%, {COLORS['teal']} 100%);
            border-radius: 18px; padding: 2.3rem 2.4rem; color: #FFFFFF; margin-bottom: 1.3rem;
        }}
        .ccdss-hero h1 {{ color: #FFFFFF !important; font-size: 2.6rem !important; margin-bottom: 0.5rem; line-height: 1.2; }}
        .ccdss-hero p {{ color: #DDEEE6 !important; font-size: 1.22rem; max-width: 720px; }}

        /* ------------------------------------------------------------ tiles */
        .ccdss-tile {{
            border-radius: 16px; padding: 1.4rem 1.5rem; height: 100%;
            color: #FFFFFF; min-height: 178px; display: flex; flex-direction: column; justify-content: space-between;
        }}
        .ccdss-tile-icon {{ font-size: 2.1rem; margin-bottom: 0.5rem; }}
        .ccdss-tile-icon .material-symbols-outlined {{ font-size: 2.1rem; color: #FFFFFF; }}
        .ccdss-tile-title {{ font-size: 1.4rem; font-weight: 800; margin-bottom: 0.3rem; }}
        .ccdss-tile-desc {{ font-size: 1.05rem; opacity: 0.96; }}

        /* ---------------------------------------------------------- panels */
        .ccdss-panel-title {{
            font-weight: 800; font-size: 1.15rem; letter-spacing: 0.02em;
            color: {COLORS['primary']}; margin-bottom: 0.5rem; text-transform: uppercase;
        }}
        .ccdss-score-badge {{
            display: inline-block; padding: 0.35rem 0.9rem; border-radius: 8px;
            font-weight: 800; font-size: 1.02rem; color: #fff; letter-spacing: 0.02em;
        }}
        .ccdss-priority-pill {{
            display: inline-block; padding: 0.55rem 1.2rem; border-radius: 10px;
            font-weight: 800; font-size: 1.45rem; color: #fff; text-align: center;
        }}

        /* --------------------------------------------------- factor bars ---*/
        .ccdss-fb-row {{ margin-bottom: 0.6rem; }}
        .ccdss-fb-label {{ font-size: 1.02rem; font-weight: 600; color: {COLORS['text']}; margin-bottom: 0.2rem; }}
        .ccdss-fb-track {{ background: #E7ECE8; border-radius: 6px; height: 12px; width: 100%; overflow: hidden; }}
        .ccdss-fb-fill {{ background: {COLORS['teal']}; height: 12px; border-radius: 6px; }}

        /* ------------------------------------------------------- mini-flow */
        .ccdss-step-card {{
            border: 1px solid {COLORS['border']}; border-radius: 12px; padding: 1.1rem 1.15rem;
            background: #FFFFFF; height: 100%;
        }}
        .ccdss-step-icon {{ font-size: 1.7rem; }}
        .ccdss-step-icon .material-symbols-outlined {{ font-size: 1.7rem; color: {COLORS['teal']}; }}
        .ccdss-step-title2 {{ font-weight: 800; font-size: 1.1rem; margin: 0.35rem 0 0.15rem 0; }}
        .ccdss-step-desc2 {{ font-size: 0.98rem; color: {COLORS['muted']}; }}

        .ccdss-flow-row {{ display: flex; align-items: stretch; flex-wrap: wrap; gap: 0.4rem; }}
        .ccdss-flow-box {{
            border: 1px solid {COLORS['teal']}; color: {COLORS['primary_dark']};
            background: #EAF4F3; border-radius: 8px; padding: 0.55rem 0.75rem;
            font-size: 0.92rem; font-weight: 700; text-align: center; flex: 1 1 auto;
            min-width: 130px; display: flex; align-items: center; justify-content: center;
        }}
        .ccdss-flow-arrow {{ display: flex; align-items: center; color: {COLORS['muted']}; font-weight: 700; }}

        /* -------------------------------------------------------- geocode -*/
        .ccdss-geo-card {{
            border: 1px solid {COLORS['border']}; border-radius: 12px; padding: 1rem 1.1rem;
            background: {COLORS['panel']}; font-size: 1.02rem;
        }}
        .ccdss-geo-arrow {{ text-align: center; padding-top: 1.5rem; }}
        .ccdss-geo-arrow .material-symbols-outlined {{ font-size: 1.6rem; color: {COLORS['teal']}; }}
        .ccdss-geo-coord {{
            font-family: 'SFMono-Regular', Consolas, monospace; background: #EFF3F0;
            padding: 0.25rem 0.55rem; border-radius: 6px; font-size: 1rem;
        }}

        .ccdss-limit-box {{
            border-left: 5px solid {COLORS['moderate']}; background: #FBF4E9;
            border-radius: 8px; padding: 0.9rem 1.05rem; margin-bottom: 0.6rem; font-size: 1.05rem;
        }}
        .ccdss-info-box {{
            border-left: 5px solid {COLORS['teal']}; background: #EAF4F3;
            border-radius: 8px; padding: 0.9rem 1.05rem; margin-bottom: 0.6rem; font-size: 1.05rem;
        }}
        .ccdss-credits {{
            border-top: 1px solid {COLORS['border']}; margin-top: 1rem; padding-top: 1rem;
            font-size: 0.95rem; color: {COLORS['muted']}; line-height: 1.5rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------- sidebar ----
APP_TITLE = "CHENNAI CIRCULAR CITY DSS"
APP_SUBTITLE = "A GIS Based Spatial Decision Support Framework for Action Oriented Circular Urban Transitions"
APP_TAGLINE = (
    "Spatial decision support for local circular resource opportunities. Identify where "
    "existing urban resources may have the greatest potential for circular use."
)

NAV_ITEMS = [
    {"key": "home", "label": "Overview", "icon": ":material/space_dashboard:", "page": "app.py"},
    {"key": "water", "label": "Water Reuse", "icon": ":material/water_drop:", "page": "pages/1_Water_Reuse.py"},
    {"key": "waste", "label": "Organic Waste", "icon": ":material/recycling:", "page": "pages/2_Organic_Waste.py"},
    {"key": "map", "label": "Decision Map", "icon": ":material/map:", "page": "pages/3_Decision_Map.py"},
    {"key": "methodology", "label": "Methodology", "icon": ":material/school:", "page": "pages/4_Data_Methodology.py"},
]


def render_sidebar(active: str) -> None:
    """Persistent left-hand navigation: large icon + label per section, one
    click to get anywhere. The active section is a plain highlighted block
    (not a link) so it's always obvious where you are. The full name +
    one-line description of the tool sits at the bottom, large and white."""
    with st.sidebar:
        st.markdown(
            f"<div class='ccdss-side-brand'>Chennai Circular<br/>City DSS</div>"
            f"<div class='ccdss-side-sub'>Spatial decision support</div>",
            unsafe_allow_html=True,
        )
        for item in NAV_ITEMS:
            if item["key"] == active:
                st.markdown(
                    f"<div class='ccdss-side-active'>{icon_html(item['icon'], size=24)} {item['label']}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.page_link(item["page"], label=item["label"], icon=item["icon"])
        st.markdown(
            f"""<div class='ccdss-side-tagline'>
                    <b>{APP_TITLE}</b>{APP_TAGLINE}
                </div>
                <div class='ccdss-side-foot'>Screening tool, not an engineering approval. Every score is a starting point for a closer look.</div>""",
            unsafe_allow_html=True,
        )


# ------------------------------------------------------------------- hero ---
def render_hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""<div class="ccdss-hero"><h1>{title}</h1><p>{subtitle}</p></div>""",
        unsafe_allow_html=True,
    )


def render_tile(icon: str, title: str, desc: str, color: str) -> None:
    st.markdown(
        f"""<div class="ccdss-tile" style="background:{color};">
                <div class="ccdss-tile-icon">{icon_html(icon, size=34)}</div>
                <div>
                    <div class="ccdss-tile-title">{title}</div>
                    <div class="ccdss-tile-desc">{desc}</div>
                </div>
            </div>""",
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------- priority panel --
def render_priority_panel(counts: dict, key: str) -> list[str]:
    st.markdown("<div class='ccdss-panel-title'>Priority</div>", unsafe_allow_html=True)
    selected = []
    for level in ("HIGH", "MODERATE", "LOW"):
        c = int(counts.get(level, 0))
        label = f"{_priority_dot(level)}  {level}   ({c})"
        if st.checkbox(label, value=True, key=f"{key}_priority_{level}"):
            selected.append(level)
    if not selected:
        st.caption("Select at least one priority level.")
    return selected


# --------------------------------------------------------- factor / score ---
def render_score_badge(score_0_100: float, priority: str) -> None:
    color = PRIORITY_HEX[priority]
    st.markdown(
        f"""
        <div>
          <span style="font-size:2.1rem; font-weight:900; color:{COLORS['primary']};">
            {score_0_100:.0f}</span><span style="color:{COLORS['muted']}; font-size:1.1rem;"> / 100</span>
          &nbsp;&nbsp;
          <span class="ccdss-score-badge" style="background:{color};">{priority} PRIORITY</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_factor_bars(breakdown: list[dict], overall_priority: str | None = None) -> None:
    """The 'Why is this location prioritised?' bar list from the mockup:
    one labelled bar per factor (out of 50, matching weight scale), plus an
    optional big 'Overall priority' pill alongside it."""
    left, right = st.columns([3, 1]) if overall_priority else (st.container(), None)
    with left:
        for item in breakdown:
            pct = min(100, item["factor_score"])
            st.markdown(
                f"""<div class="ccdss-fb-row">
                        <div class="ccdss-fb-label">{item['label']}</div>
                        <div class="ccdss-fb-track"><div class="ccdss-fb-fill" style="width:{pct}%;"></div></div>
                    </div>""",
                unsafe_allow_html=True,
            )
    if overall_priority and right is not None:
        with right:
            color = PRIORITY_HEX[overall_priority]
            st.markdown(
                f"""<div style="text-align:center;">
                        <div style="font-size:0.85rem; font-weight:700; color:{COLORS['muted']}; margin-bottom:0.4rem;">OVERALL PRIORITY</div>
                        <div class="ccdss-priority-pill" style="background:{color};">{overall_priority}</div>
                    </div>""",
                unsafe_allow_html=True,
            )


def render_factor_cards(cards: list[dict]) -> None:
    cols = st.columns(3)
    for i, card in enumerate(cards):
        with cols[i % 3]:
            value = card.get("display") or f"{card['value']} / 100"
            st.markdown(
                f"""<div style="border:1px solid {COLORS['border']}; border-radius:10px; padding:0.7rem 0.85rem; background:#fff; margin-bottom:0.6rem;">
                        <div style="font-size:0.88rem; color:{COLORS['muted']};">{card['label']}</div>
                        <div style="font-size:1.4rem; font-weight:800; color:{COLORS['primary']};">{value}</div>
                    </div>""",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------- flow diagram ----
def render_flow(steps: list[str]) -> None:
    parts = []
    for i, step in enumerate(steps):
        parts.append(f'<div class="ccdss-flow-box">{step}</div>')
        if i < len(steps) - 1:
            parts.append('<div class="ccdss-flow-arrow">&rarr;</div>')
    st.markdown(f'<div class="ccdss-flow-row">{"".join(parts)}</div>', unsafe_allow_html=True)


# --------------------------------------------------- one-tab-only method ----
def render_mini_methodology(pathway_key: str) -> None:
    """The SHORT, single-tab methodology block: five icon steps for exactly
    this pathway, nothing more. Full detail lives only on the Methodology
    page, linked at the bottom."""
    st.markdown(f"##### {PATHWAY_MINI_INTRO[pathway_key]}")
    steps = PATHWAY_MINI_METHOD[pathway_key]
    cols = st.columns(len(steps))
    for col, (icon, title, desc) in zip(cols, steps):
        with col:
            st.markdown(
                f"""<div class="ccdss-step-card">
                        <div class="ccdss-step-icon">{icon_html(icon, size=28)}</div>
                        <div class="ccdss-step-title2">{title}</div>
                        <div class="ccdss-step-desc2">{desc}</div>
                    </div>""",
                unsafe_allow_html=True,
            )
    st.page_link(
        "pages/4_Data_Methodology.py",
        label="Full methodology & data sources",
        icon=":material/arrow_forward:",
    )


# ------------------------------------------------------ methodology block ---
def render_methodology(stats: dict, condensed: bool = False) -> None:
    st.subheader("Data & Methodology")
    st.caption("How every recommendation in this tool is produced, from source data to priority score.")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Datasets used", stats["n_datasets"])
    m2.metric("Opportunities screened", f"{stats['n_total']:,}")
    m3.metric("Water reuse pairs", f"{stats['n_water']:,}")
    m4.metric("Organic waste pairs", f"{stats['n_waste']:,}")

    m5, m6, m7 = st.columns(3)
    m5.metric("High priority", f"{stats['n_high']:,}")
    m6.metric("Moderate priority", f"{stats['n_moderate']:,}")
    m7.metric("Low priority", f"{stats['n_low']:,}")

    st.markdown("**Processing flow**")
    render_flow(METHOD_FLOW)

    st.write("")
    st.markdown("**Data to action**")
    render_flow(DATA_TO_ACTION_FLOW)

    st.write("")
    st.markdown("**How the priority score is calculated**")
    formula = "Priority score = " + " + ".join(
        f"({label} x {DEFAULT_WEIGHTS[field]}%)" for label, field in SCORE_FORMULA_TERMS
    )
    st.code(formula, language="text")
    st.caption(
        "Each factor is standardised to a 0 to 1 scale before weighting. The weighted sum is divided "
        "by the total of the weights in use, then compared against city-wide terciles for that pathway "
        "to assign HIGH, MODERATE or LOW. Presets on each assessment page change the weights above; the "
        "balanced default is Resource 30%, Demand 25%, Climate 20%, Spatial feasibility 15%, "
        "Infrastructure 10%."
    )

    if not condensed:
        st.write("")
        st.markdown("**Datasets used**")
        st.caption(f"{stats['n_datasets']} datasets feed the current scoring model, listed below by category.")
        data_df = pd.DataFrame(
            DATASETS, columns=["Category", "Dataset", "Source", "Period", "Resolution", "Role in the DSS"]
        )
        st.dataframe(data_df, hide_index=True, width="stretch")


def render_limitations() -> None:
    st.markdown("### Screening tool, not an approval")
    st.markdown(
        """
        <div class="ccdss-limit-box">
        This DSS prioritises locations using available spatial data. It does not replace detailed
        engineering design, field verification, water-quality testing, regulatory approval,
        environmental assessment, or feasibility studies. Treat every score as a starting point for
        further assessment.
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------- footer -------
def render_footer_links() -> None:
    st.markdown("<div>", unsafe_allow_html=True)
    if PROJECT_REPO_URL:
        c1, c2 = st.columns(2)
    else:
        c1, c2 = st.columns([1, 3])
    with c1:
        st.page_link("pages/4_Data_Methodology.py", label="Data & Methodology", icon=":material/database:")
    if PROJECT_REPO_URL:
        with c2:
            st.link_button("Project Repository", PROJECT_REPO_URL, icon=":material/open_in_new:")
    st.markdown("</div>", unsafe_allow_html=True)


def render_credits() -> None:
    render_footer_links()
    st.markdown(
        f"""
        <div class="ccdss-credits">
        <b>{APP_TITLE}</b><br/>
        {APP_SUBTITLE}<br/><br/>
        Team name: CCCDM &nbsp;|&nbsp; Submitted by: Vikashni<br/><br/>
        Theme: Action-Oriented Transitions: Translating resilient, scalable, and inclusive
        Solutions for Circular Cities<br/>
        ICLEI, Local Governments for Sustainability &nbsp;|&nbsp; Youth for Climate Hackathon 2.0
        </div>
        """,
        unsafe_allow_html=True,
    )
