"""Dashboard Home — native v2 page."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from config import POSITION_HIERARCHY_ORDER, SG_HIERARCHY, SG_TO_POSITION_BRACKET
from core.bootstrap import get_master_data
from analytics.nationality import prepare_nationality_map_data, create_nationality_bubble_map
from components.navigation import render_navigation, render_header

render_navigation()
render_header("🏠 Dashboard Home", "DPE Reservoir Engineering workforce overview")

df = get_master_data()
if df is None or df.empty:
    st.warning("⚠️ No personnel data is available. Go to Admin: Import Data to load the master workbook.")
    st.stop()

# -----------------------------------------------------------------------------
# Top metrics
# -----------------------------------------------------------------------------
metric_cols = st.columns(5)
total = len(df)
gender = df.get("Gender", pd.Series(dtype=object)).astype(str).str.strip().str.upper()
employment = df.get("Employment Category", pd.Series(dtype=object)).astype(str).str.strip().str.upper()
metric_cols[0].metric("Total Personnel", int(total))
metric_cols[1].metric("Permanent Employees", int(employment.eq("PERMANENT").sum()))
metric_cols[2].metric("CDH Employees", int(employment.eq("CDH").sum()))
metric_cols[3].metric("Male", int(gender.eq("M").sum()))
metric_cols[4].metric("Female", int(gender.eq("F").sum()))

# -----------------------------------------------------------------------------
# Nationality distribution
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("🌐 RE Nationalities")
nationality_df, unmatched = prepare_nationality_map_data(df)
if not nationality_df.empty:
    top = nationality_df.head(5)
    cols = st.columns(min(5, len(top)))
    for index, (_, row) in enumerate(top.iterrows()):
        cols[index].metric(row["Nationality"], int(row["Personnel Count"]), row["Representation Display"])
    st.plotly_chart(
        create_nationality_bubble_map(nationality_df), width="stretch",
        config={"displaylogo": True, "scrollZoom": True, "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                "toImageButtonOptions": {"format": "png", "filename": "RE_personnel_nationality_map", "height": 800, "width": 1400, "scale": 2}},
    )
    st.caption("Bubble size and color represent the number of personnel associated with each nationality. Markers use approximate country-centroid coordinates.")
else:
    st.info("No valid nationality data is available for the geographical visualization.")
if unmatched:
    with st.expander("⚠️ Nationality values requiring mapping"):
        st.write(unmatched)

# -----------------------------------------------------------------------------
# Workforce distributions
# -----------------------------------------------------------------------------
st.markdown("---")
filter_cols = st.columns(3)
with filter_cols[0]:
    selected_units = st.multiselect("Filter by Unit Name", sorted(df["Unit Name"].dropna().astype(str).unique()) if "Unit Name" in df else [], key="dash_unit1")
with filter_cols[1]:
    selected_positions = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().astype(str).unique()) if "Staff Position" in df else [], key="dash_pos1")
with filter_cols[2]:
    selected_people = st.multiselect("Filter by Personnel", sorted(df["Name"].dropna().astype(str).unique()) if "Name" in df else [], key="dash_name")

filtered = df.copy()
if selected_units: filtered = filtered[filtered["Unit Name"].astype(str).isin(selected_units)]
if selected_positions: filtered = filtered[filtered["Staff Position"].astype(str).isin(selected_positions)]
if selected_people: filtered = filtered[filtered["Name"].astype(str).isin(selected_people)]

chart_cols = st.columns(2)
with chart_cols[0]:
    st.subheader("📊 Position Breakdown")
    if "SG" in filtered and "Employment Category" in filtered:
        chart = filtered.copy()
        chart["Position"] = chart["SG"].map(SG_TO_POSITION_BRACKET).fillna("Other")
        chart["Employment Type"] = chart["Employment Category"].astype(str).str.strip().str.upper().map({"PERMANENT":"Permanent","CDH":"CDH"}).fillna("Other")
        grouped = chart.groupby(["Position","Employment Type"]).size().reset_index(name="Personnel")
        st.plotly_chart(px.bar(grouped, x="Position", y="Personnel", color="Employment Type", barmode="stack",
                               category_orders={"Position": [p for p in POSITION_HIERARCHY_ORDER if p in grouped["Position"].unique()]}),
                        width="stretch", config={"displaylogo": False, "responsive": True})
with chart_cols[1]:
    st.subheader("📊 Salary Grade Distribution")
    if "SG" in filtered and "Employment Category" in filtered:
        chart = filtered.copy()
        chart["Employment Type"] = chart["Employment Category"].astype(str).str.strip().str.upper().map({"PERMANENT":"Permanent","CDH":"CDH"}).fillna("Other")
        grouped = chart.groupby(["SG","Employment Type"]).size().reset_index(name="Personnel")
        order = [g for g in SG_HIERARCHY if g in grouped["SG"].unique()]
        st.plotly_chart(px.bar(grouped, x="SG", y="Personnel", color="Employment Type", barmode="stack",
                               category_orders={"SG": order}), width="stretch", config={"displaylogo": False, "responsive": True})
