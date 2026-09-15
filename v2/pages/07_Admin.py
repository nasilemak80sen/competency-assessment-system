"""V2 administration/diagnostics page.

Write-heavy import and CRUD workflows are deliberately not duplicated here yet.
They remain on the v3 application until their service-layer extraction is tested.
"""
import streamlit as st

from core.bootstrap import initialise_session, get_master_data, get_database_engine
from components.navigation import render_header, render_navigation
from config import EXCEL_PATH
from models import Personnel, Assessment, CompetencyScore, CVDocument, AuditLog

initialise_session()
render_navigation()
render_header("⚙️ Administration & Diagnostics", "Safe v2 diagnostics while write workflows are being migrated.")

st.subheader("Source status")
st.write(f"Workbook: `{EXCEL_PATH}`")
st.write(f"Workbook exists: **{EXCEL_PATH}**")

try:
    df = get_master_data()
    st.success(f"Master workbook loaded: {len(df)} personnel rows.")
except Exception as exc:
    st.error(f"Master workbook failed to load: {exc}")
    df = None

st.subheader("Database status")
try:
    session = __import__('core.bootstrap', fromlist=['open_session']).open_session()
    try:
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Personnel", session.query(Personnel).count())
        with c2: st.metric("Assessments", session.query(Assessment).count())
        with c3: st.metric("Scores", session.query(CompetencyScore).count())
        with c4: st.metric("CV Documents", session.query(CVDocument).count())
    finally:
        session.close()
except Exception as exc:
    st.warning(f"Database diagnostics unavailable: {exc}")

st.divider()
st.subheader("Migration guardrails")
st.info(
    "Import, personnel CRUD and assessment-write workflows are intentionally not duplicated in v2 yet. "
    "They will be moved behind services after their current v3 behaviour is mapped and regression-tested."
)

if st.button("Clear cached v2 data"):
    st.cache_data.clear()
    st.success("V2 data caches cleared. Reload the page to refresh the source.")
