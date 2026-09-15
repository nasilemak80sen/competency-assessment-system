"""Golden-app-compatible top navigation for the native v2 application."""
from __future__ import annotations

import streamlit as st

from core.pages import PAGE_BY_PATH


MAIN_NAV = (
    ("🏠 Dashboard", "🏠 Dashboard Home", ""),
    ("🌡️ Heatmap", "🌡️ Competency Heatmap", "competency-heatmap"),
    ("👤 Assessment", "👤 Individual Assessment & Talent Profile", "individual-assessment"),
    ("🎯 Readiness", "🎯 Readiness & Gaps", "readiness-gaps"),
    ("📊 Charts", "📊 Chart Builder & Depth Analysis", "chart-builder"),
)

ADMIN_NAV = (
    ("📥 Import", "⚙️ Admin: Import Data", "admin-import-data"),
    ("👥 Database", "⚙️ Admin: Personnel Database Settings", "admin-personnel-settings"),
)


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_navigation() -> None:
    """Render the same top navigation structure and labels as golden navigation.py.

    These explicit widget keys intentionally use a v2-specific namespace. The
    application also uses Streamlit's native ``st.navigation`` with
    ``position=\"hidden\"``; short keys such as ``nav_0`` can collide with
    Streamlit's internal navigation widget keys and raise
    ``StreamlitDuplicateElementKey``.
    """
    current_page = st.session_state.get("current_page", "🏠 Dashboard Home")

    nav_container = st.container()
    with nav_container:
        col_title, _ = st.columns([0.85, 0.15])
        with col_title:
            st.markdown(
                "### 📊 DPE | Reservoir Engineering Talent Profile Dashboard (Beta Release)"
            )

        st.markdown("---")

        nav_cols = st.columns(5)
        for idx, (display_name, actual_name, path) in enumerate(MAIN_NAV):
            with nav_cols[idx]:
                is_active = current_page == actual_name
                if st.button(
                    display_name,
                    use_container_width=True,
                    key=f"v2_main_nav_{idx}",
                    disabled=is_active,
                ):
                    st.switch_page(PAGE_BY_PATH[path])

        st.markdown("")

        admin_col1, admin_col2, _ = st.columns([1, 1, 3])
        for idx, (display_name, actual_name, path) in enumerate(ADMIN_NAV):
            with [admin_col1, admin_col2][idx]:
                if st.button(
                    f"⚙️ {display_name}",
                    use_container_width=True,
                    key=f"v2_admin_nav_{idx}",
                ):
                    st.switch_page(PAGE_BY_PATH[path])

        st.markdown("---")


# Backwards-compatible alias used by pages that only need the top navigation.
render_navigation_bar = render_navigation
