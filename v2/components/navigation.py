"""Shared navigation and page chrome for the v2 application."""
import streamlit as st


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_navigation() -> None:
    """Provide explicit cross-page links instead of page-to-page imports."""
    st.sidebar.markdown("### RE Fraternity")
    st.sidebar.page_link("app.py", label="🏠 V2 Home")
    st.sidebar.page_link("pages/02_Personnel.py", label="👥 Personnel")
    st.sidebar.page_link("pages/03_Competency_Heatmap.py", label="🌡️ Competency Heatmap")
    st.sidebar.page_link("pages/04_Readiness_and_Gaps.py", label="🎯 Readiness & Gaps")
    st.sidebar.page_link("pages/05_Individual_Assessment.py", label="👤 Individual Assessment")
    st.sidebar.page_link("pages/06_Chart_Builder.py", label="📊 Chart Builder")
    st.sidebar.page_link("pages/07_Admin.py", label="⚙️ Administration")

    selected = st.session_state.get("selected_person_name")
    if selected:
        st.sidebar.divider()
        st.sidebar.caption("Selected personnel")
        st.sidebar.markdown(f"**{selected}**")
        st.sidebar.page_link("pages/05_Individual_Assessment.py", label="Open profile →")
