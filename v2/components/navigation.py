"""Shared v2 navigation."""

import streamlit as st

from core.pages import PAGE_BY_PATH


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_navigation() -> None:
    """Render sidebar links using the canonical st.Page objects.

    With Streamlit's explicit ``st.navigation`` API, raw paths such as
    ``app.py`` are not valid page targets. Reusing the exact ``st.Page``
    instances registered by the entry point keeps sidebar navigation and the
    navigation registry in sync.
    """
    st.sidebar.markdown("### RE Fraternity")

    for path, label in (
        ("", "🏠 Dashboard Home"),
        ("personnel", "👥 Personnel Directory"),
        ("competency-heatmap", "🌡️ Competency Heatmap"),
        ("individual-assessment", "👤 Individual Assessment & Talent Profile"),
        ("readiness-gaps", "🎯 Readiness & Gaps"),
        ("chart-builder", "📊 Chart Builder & Depth Analysis"),
        ("admin-import-data", "⚙️ Admin: Import Data"),
        ("admin-personnel-settings", "⚙️ Admin: Personnel Database Settings"),
    ):
        st.sidebar.page_link(PAGE_BY_PATH[path], label=label)

    selected = st.session_state.get("selected_person_name")
    if selected:
        st.sidebar.divider()
        st.sidebar.caption("Selected personnel")
        st.sidebar.markdown(f"**{selected}**")
        st.sidebar.page_link(
            PAGE_BY_PATH["individual-assessment"],
            label="Open profile →",
        )
