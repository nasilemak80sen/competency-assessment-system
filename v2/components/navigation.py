"""Role-aware top navigation for native v2."""
from __future__ import annotations
import streamlit as st
from core.auth import current_user, is_admin
from core.pages import PAGE_BY_PATH

MAIN_NAV = (
    ("🏠 Dashboard", "🏠 Dashboard Home", ""),
    ("🌡️ Heatmap", "🌡️ Competency Heatmap", "competency-heatmap"),
    ("👤 Assessment", "👤 Individual Assessment & Talent Profile", "individual-assessment"),
    ("🎯 Readiness", "🎯 Readiness & Gaps", "readiness-gaps"),
    ("📊 Charts", "📊 Chart Builder & Depth Analysis", "chart-builder"),
)
USER_NAV = (
    ("🏠 My Dashboard", "🏠 My Dashboard", "my-dashboard"),
    ("👤 My Assessment", "👤 My Assessment", "my-assessment"),
)
ADMIN_NAV = (
    ("📥 Import", "⚙️ Admin: Import Data", "admin-import-data"),
    ("👥 Database", "⚙️ Admin: Personnel Database Settings", "admin-personnel-settings"),
    ("🔐 Users", "🔐 Admin: User Access Management", "admin-user-access"),
)


def render_header(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)


def render_navigation() -> None:
    if st.session_state.get("_v2_navigation_rendered", False):
        return
    st.session_state["_v2_navigation_rendered"] = True
    current_page = st.session_state.get("current_page", "🏠 Dashboard Home")
    admin = is_admin()
    user = current_user()

    with st.container():
        title = "### 📊 DPE | Reservoir Engineering Talent Profile Dashboard (Beta Release)"
        if user:
            title += f" · {user.get('display_name') or user.get('username')}"
        st.markdown(title)
        st.markdown("---")

        visible_nav = MAIN_NAV if admin else USER_NAV
        nav_cols = st.columns(len(visible_nav))
        for idx, (display_name, actual_name, path) in enumerate(visible_nav):
            with nav_cols[idx]:
                is_active = current_page == actual_name
                if st.button(display_name, use_container_width=True, key=f"v2_main_nav_{idx}", disabled=is_active):
                    st.switch_page(PAGE_BY_PATH[path])

        if admin:
            st.markdown("")
            admin_cols = st.columns(len(ADMIN_NAV) + 1)
            for idx, (display_name, actual_name, path) in enumerate(ADMIN_NAV):
                with admin_cols[idx]:
                    if st.button(f"⚙️ {display_name}", use_container_width=True, key=f"v2_admin_nav_{idx}"):
                        st.switch_page(PAGE_BY_PATH[path])
        st.markdown("---")


render_navigation_bar = render_navigation
