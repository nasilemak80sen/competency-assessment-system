"""Competency Assessment System v2 modular entry point.

This app is intentionally isolated from the current v3 monolith. The existing
root app.py remains untouched while v2 pages are migrated incrementally.
"""
import streamlit as st

from core.bootstrap import initialise_session, get_master_data
from components.navigation import render_header, render_navigation

st.set_page_config(page_title="RE Fraternity | v2", page_icon="📊", layout="wide")
initialise_session()
render_navigation()

render_header(
    "📊 DPE | Reservoir Engineering Talent Profile",
    "Modular v2 architecture — migration-safe parallel build",
)

df = get_master_data()

if df.empty:
    st.error("No master data could be loaded. Check COMPETENCY_EXCEL_PATH / workbook availability.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Personnel", len(df))
with c2:
    st.metric("Departments", df["Department"].nunique() if "Department" in df else 0)
with c3:
    st.metric("Assessed", int(df[[c for c in df.columns if c in __import__('config').SCORE_COLS]].notna().any(axis=1).sum()))
with c4:
    st.metric("Competencies", len(__import__('config').SCORE_COLS))

st.divider()
st.subheader("V2 migration status")
st.info(
    "The v2 shell is isolated from the current production entry point. "
    "Pages share one data/session context and communicate through session state, "
    "not direct imports between pages. Existing v3 behaviour is preserved while modules are migrated."
)

st.markdown("### Start here")
a, b, c = st.columns(3)
with a:
    st.page_link("pages/02_Personnel.py", label="👥 Browse Personnel", use_container_width=True)
with b:
    st.page_link("pages/03_Competency_Heatmap.py", label="🌡️ Explore Competencies", use_container_width=True)
with c:
    st.page_link("pages/04_Readiness_and_Gaps.py", label="🎯 Review Readiness", use_container_width=True)
