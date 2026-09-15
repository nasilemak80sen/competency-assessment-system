"""V2 dashboard entry point.

Every v2 page is registered through Streamlit's explicit navigation API.
Pages own their UI and call shared v2 services/analytics rather than loading
branches from the legacy root app.
"""
import streamlit as st

# Bootstrap the v2 import path before Streamlit executes any page. Streamlit's
# navigation runner executes page scripts in a context where the repository
# root is not guaranteed to be on sys.path, so pages importing shared legacy
# modules such as config.py would otherwise fail with ModuleNotFoundError.
from core import bootstrap  # noqa: F401,E402

pages = [
    st.Page("pages/01_Dashboard.py", title="🏠 Dashboard Home", url_path="", default=True),
    st.Page("pages/02_Personnel.py", title="👥 Personnel Directory", url_path="personnel"),
    st.Page("pages/03_Competency_Heatmap.py", title="🌡️ Competency Heatmap", url_path="competency-heatmap"),
    st.Page("pages/04_Readiness_and_Gaps.py", title="🎯 Readiness & Gaps", url_path="readiness-gaps"),
    st.Page("pages/05_Individual_Assessment.py", title="👤 Individual Assessment & Talent Profile", url_path="individual-assessment"),
    st.Page("pages/06_Chart_Builder.py", title="📊 Chart Builder & Depth Analysis", url_path="chart-builder"),
    st.Page("pages/08_Admin_Import_Data.py", title="⚙️ Admin: Import Data", url_path="admin-import-data"),
    st.Page("pages/07_Admin.py", title="⚙️ Admin: Personnel Database Settings", url_path="admin-personnel-settings"),
]

pg = st.navigation(pages, position="hidden")
pg.run()
