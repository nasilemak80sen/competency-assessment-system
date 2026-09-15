"""Readiness and competency-gap page."""
import streamlit as st

from core.bootstrap import initialise_session, get_master_data
from components.navigation import render_header, render_navigation
import analytics as an

initialise_session()
render_navigation()
render_header("🎯 Readiness & Gaps", "Shared readiness calculations with filtering and export-friendly tables.")

df = get_master_data().copy()

if "Department" in df.columns:
    departments = ["All"] + sorted(df["Department"].dropna().astype(str).unique().tolist())
    dept = st.selectbox("Department", departments)
    if dept != "All":
        df = df[df["Department"].astype(str) == dept]

readiness = an.readiness_table(df)
if readiness.empty:
    st.info("No readiness records are available.")
    st.stop()

c1, c2, c3 = st.columns(3)
valid = readiness["Achievement %"].notna()
with c1:
    st.metric("Assessed", int(valid.sum()))
with c2:
    st.metric("Ready", int((readiness["Ready for Assessment"] == "Ready").sum()))
with c3:
    st.metric("Not Ready", int((readiness["Ready for Assessment"] == "Not Ready").sum()))

status = st.multiselect(
    "Readiness status",
    options=["Ready", "Not Ready", "N/A"],
    default=["Ready", "Not Ready", "N/A"],
)
view = readiness[readiness["Ready for Assessment"].isin(status)].copy()

if not view.empty:
    view = view.sort_values("Achievement %", ascending=False, na_position="last")
st.dataframe(view, use_container_width=True, hide_index=True)

st.download_button(
    "Download readiness CSV",
    data=view.to_csv(index=False).encode("utf-8"),
    file_name="readiness_v2.csv",
    mime="text/csv",
)
