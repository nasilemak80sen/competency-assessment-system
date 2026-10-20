"""Admin: Import Data — native v2 page."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import get_database_engine
from data_loader import load_master_data, load_ruler_and_tech_mapping, load_cv_list
from services.import_service import bulk_import_from_dataframe, bulk_import_cv_list

render_navigation()
render_header("⚙️ Admin: Import Data", "Import personnel, competency, ruler and CV records from the master workbook")

uploaded_file = st.file_uploader("Upload the RE Fraternity master workbook", type=["xlsx", "xlsm"], key="master_workbook_upload")
if uploaded_file is None:
    st.info("Upload the master workbook to preview and import personnel, ruler, assessment, and CV data.")
    st.stop()

tmp_path = None
try:
    suffix = Path(uploaded_file.name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(uploaded_file.getbuffer())
        tmp_path = temporary_file.name

    raw_df = load_master_data(tmp_path)
    ruler_map, tech_labels = load_ruler_and_tech_mapping(tmp_path)
    cv_df = load_cv_list(tmp_path, verbose=True)

    st.success(f"Loaded {len(raw_df):,} personnel records.")
    st.success(f"Loaded {len(cv_df):,} CV and supporting-document records.")
    valid_links = 0
    if not cv_df.empty and "SharePoint URL" in cv_df.columns:
        valid_links = int(cv_df["SharePoint URL"].fillna("").astype(str).str.lower().str.startswith(("https://", "http://")).sum())
    st.info(f"Valid SharePoint links detected: {valid_links:,}")

    personnel_tab, cv_tab = st.tabs(["Personnel Preview", "CV List Preview"])
    with personnel_tab:
        st.dataframe(raw_df.head(20), width="stretch", hide_index=True)
    with cv_tab:
        if cv_df.empty:
            st.warning("No CV records were detected.")
        else:
            columns = [c for c in ["Name","Staff ID","Staff Position","CV File Name","File Type","SharePoint URL","Match Method"] if c in cv_df.columns]
            st.dataframe(cv_df[columns].head(20), width="stretch", hide_index=True)

    if st.button("✅ Confirm Import to Database", type="primary", width="stretch"):
        session = get_database_engine()
        db_session = None
        try:
            from models import get_session
            db_session = get_session(session)
            with st.spinner("Importing personnel, assessments, ruler requirements, and CV links…"):
                personnel_result = bulk_import_from_dataframe(db_session, raw_df, ruler_map=ruler_map)
                cv_result = bulk_import_cv_list(db_session, cv_df)
            st.success(f"Personnel import complete. Added: {personnel_result.get('added', 0)}, Updated: {personnel_result.get('updated', 0)}, Errors: {personnel_result.get('errors', 0)}")
            st.success(f"CV import complete. Added: {cv_result.get('added', 0)}, Updated: {cv_result.get('updated', 0)}, Unmatched: {cv_result.get('unmatched', 0)}, Skipped: {cv_result.get('skipped', 0)}, Errors: {cv_result.get('errors', 0)}")
            if cv_result.get("unmatched", 0) > 0:
                st.warning("Some CV records could not be matched uniquely to personnel. Populate Staff ID in the CV list worksheet for those rows.")
            st.cache_data.clear()
        except Exception as exc:
            if db_session is not None:
                db_session.rollback()
            st.error(f"Import failed: {exc}")
        finally:
            if db_session is not None:
                db_session.close()
finally:
    if tmp_path and os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
