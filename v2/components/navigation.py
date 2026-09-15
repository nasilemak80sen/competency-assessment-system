"""Shared v2 navigation."""

import streamlit as st


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_navigation() -> None:
    """Native page links for the exact-parity migration pages."""
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
