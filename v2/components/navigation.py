"""Shared v2 navigation."""

from __future__ import annotations

import streamlit as st


NAVIGATION_PAGES = [
    ("app.py", "🏠 Home"),
    ("pages/02_Personnel.py", "👥 Personnel"),
    ("pages/03_Competency_Heatmap.py", "🌡️ Heatmap"),
    ("pages/04_Readiness_and_Gaps.py", "🎯 Readiness"),
    ("pages/05_Individual_Assessment.py", "👤 Assessment"),
    ("pages/06_Chart_Builder.py", "📊 Charts"),
    ("pages/08_Admin_Import_Data.py", "⚙️ Import"),
    ("pages/07_Admin.py", "⚙️ Admin"),
]


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_top_navigation() -> None:
    """Render the persistent navigation strip at the top of every v2 page."""
    st.markdown(
        """
        <style>
        div[data-testid="stPageLink-NavLink"] a {
            border-radius: 8px;
            padding: 0.45rem 0.75rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    with st.container():
        cols = st.columns(len(NAVIGATION_PAGES))
        for column, (page_path, label) in zip(cols, NAVIGATION_PAGES):
            with column:
                st.page_link(page_path, label=label)

    st.markdown("---")


def render_navigation() -> None:
    """Render the v2 top navigation and the full sidebar navigation."""
    render_top_navigation()

    st.sidebar.markdown("### RE Fraternity")
    st.sidebar.page_link("app.py", label="🏠 Dashboard Home")
    st.sidebar.page_link("pages/02_Personnel.py", label="👥 Personnel Directory")
    st.sidebar.page_link("pages/03_Competency_Heatmap.py", label="🌡️ Competency Heatmap")
    st.sidebar.page_link("pages/05_Individual_Assessment.py", label="👤 Individual Assessment & Talent Profile")
    st.sidebar.page_link("pages/04_Readiness_and_Gaps.py", label="🎯 Readiness & Gaps")
    st.sidebar.page_link("pages/06_Chart_Builder.py", label="📊 Chart Builder & Depth Analysis")
    st.sidebar.page_link("pages/08_Admin_Import_Data.py", label="⚙️ Admin: Import Data")
    st.sidebar.page_link("pages/07_Admin.py", label="⚙️ Admin: Personnel Database Settings")

    selected = st.session_state.get("selected_person_name")
    if selected:
        st.sidebar.divider()
        st.sidebar.caption("Selected personnel")
        st.sidebar.markdown(f"**{selected}**")
        st.sidebar.page_link(
            "pages/05_Individual_Assessment.py",
            label="Open profile →",
        )
