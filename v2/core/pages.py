"""Canonical Streamlit page registry for the v2 application."""
from __future__ import annotations
import streamlit as st

PAGES = [
    st.Page("pages/01_Dashboard.py", title="🏠 Dashboard Home", url_path="", default=True),
    st.Page("pages/03_Competency_Heatmap.py", title="🌡️ Competency Heatmap", url_path="competency-heatmap"),
    st.Page("pages/05_Individual_Assessment.py", title="👤 Individual Assessment & Talent Profile", url_path="individual-assessment"),
    st.Page("pages/04_Readiness_and_Gaps.py", title="🎯 Readiness & Gaps", url_path="readiness-gaps"),
    st.Page("pages/06_Chart_Builder.py", title="📊 Chart Builder & Depth Analysis", url_path="chart-builder"),
    st.Page("pages/08_Admin_Import_Data.py", title="⚙️ Admin: Import Data", url_path="admin-import-data"),
    st.Page("pages/07_Admin.py", title="⚙️ Admin: Personnel Database Settings", url_path="admin-personnel-settings"),
    st.Page("pages/09_Admin_User_Access.py", title="🔐 Admin: User Access Management", url_path="admin-user-access"),
]

PAGE_BY_PATH = {
    "": PAGES[0],
    "competency-heatmap": PAGES[1],
    "individual-assessment": PAGES[2],
    "readiness-gaps": PAGES[3],
    "chart-builder": PAGES[4],
    "admin-import-data": PAGES[5],
    "admin-personnel-settings": PAGES[6],
    "admin-user-access": PAGES[7],
}
