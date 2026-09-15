"""V2 dashboard entry point.

Streamlit's explicit navigation API is used here so every v2 page is
registered before the custom navigation links are rendered. This avoids the
legacy pages/ auto-discovery issue that can raise StreamlitPageNotFoundError.

The dashboard itself remains the original app.py branch through the exact
parity runtime until that branch is statically migrated.
"""

import streamlit as st

from core.legacy_runtime import render_legacy_page


def dashboard_page() -> None:
    """Render the original Dashboard Home branch unchanged."""
    render_legacy_page("🏠 Dashboard Home")


pages = [
    st.Page(dashboard_page, title="🏠 Dashboard Home", url_path="", default=True),
    st.Page(
        "pages/02_Personnel.py",
        title="👥 Personnel Directory",
        url_path="personnel",
    ),
    st.Page(
        "pages/03_Competency_Heatmap.py",
        title="🌡️ Competency Heatmap",
        url_path="competency-heatmap",
    ),
    st.Page(
        "pages/05_Individual_Assessment.py",
        title="👤 Individual Assessment & Talent Profile",
        url_path="individual-assessment",
    ),
    st.Page(
        "pages/04_Readiness_and_Gaps.py",
        title="🎯 Readiness & Gaps",
        url_path="readiness-gaps",
    ),
    st.Page(
        "pages/06_Chart_Builder.py",
        title="📊 Chart Builder & Depth Analysis",
        url_path="chart-builder",
    ),
    st.Page(
        "pages/08_Admin_Import_Data.py",
        title="⚙️ Admin: Import Data",
        url_path="admin-import-data",
    ),
    st.Page(
        "pages/07_Admin.py",
        title="⚙️ Admin: Personnel Database Settings",
        url_path="admin-personnel-settings",
    ),
]

# Register all pages explicitly. The built-in navigation stays hidden because
# the legacy UI has a custom sidebar navigation shell that we are preserving.
pg = st.navigation(pages, position="hidden")
pg.run()
