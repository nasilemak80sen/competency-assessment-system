"""Canonical Streamlit page registry for the v2 application.

The same ``st.Page`` objects are shared by ``st.navigation`` and sidebar
``st.page_link`` calls. This is required when using Streamlit's explicit
navigation API; raw file-path links are not valid navigation targets once
``st.navigation`` owns the page registry.
"""
from __future__ import annotations

import streamlit as st


PAGES = [
    st.Page("pages/01_Dashboard.py", title="🏠 Dashboard Home", url_path="", default=True),
    st.Page("pages/02_Personnel.py", title="👥 Personnel Directory", url_path="personnel"),
    st.Page("pages/03_Competency_Heatmap.py", title="🌡️ Competency Heatmap", url_path="competency-heatmap"),
    st.Page("pages/04_Readiness_and_Gaps.py", title="🎯 Readiness & Gaps", url_path="readiness-gaps"),
    st.Page("pages/05_Individual_Assessment.py", title="👤 Individual Assessment & Talent Profile", url_path="individual-assessment"),
    st.Page("pages/06_Chart_Builder.py", title="📊 Chart Builder & Depth Analysis", url_path="chart-builder"),
    st.Page("pages/08_Admin_Import_Data.py", title="⚙️ Admin: Import Data", url_path="admin-import-data"),
    st.Page("pages/07_Admin.py", title="⚙️ Admin: Personnel Database Settings", url_path="admin-personnel-settings"),
]

PAGE_BY_PATH = {
    "": PAGES[0],
    "personnel": PAGES[1],
    "competency-heatmap": PAGES[2],
    "readiness-gaps": PAGES[3],
    "individual-assessment": PAGES[4],
    "chart-builder": PAGES[5],
    "admin-import-data": PAGES[6],
    "admin-personnel-settings": PAGES[7],
}
