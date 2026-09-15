"""Dashboard Home — native v2 page."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import POSITION_HIERARCHY_ORDER, SG_HIERARCHY, SG_TO_POSITION_BRACKET
from core.bootstrap import get_master_data
from analytics.nationality import prepare_nationality_map_data, create_nationality_bubble_map
from components.navigation import render_navigation, render_header


def _scatter_age_vs_grade(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare legacy-compatible Age vs SG scatter data without root analytics import."""
    size_cols = ["Years of RE Experience", "Years in PET"]
    size_col = next((column for column in size_cols if column in df.columns), None)
    columns = ["Name", "Age", "SG", "Staff Position", "Department", "Overall_avg"]
    if size_col:
        columns.append(size_col)
    columns = [column for column in columns if column in df.columns]
    out = df[columns].copy()
    for column in ("Years of RE Experience", "Years in PET"):
        if column in out.columns:
            out[column] = out[column].fillna(0)
    required = [column for column in ("Age", "SG") if column in out.columns]
    return out.dropna(subset=required) if len(required) == 2 else out

render_navigation()
render_header("🏠 Dashboard Home", "DPE Reservoir Engineering workforce overview")

df = get_master_data()
if df is None or df.empty:
    st.warning("⚠️ No personnel data is available. Go to Admin: Import Data to load the master workbook.")
    st.stop()

# Top metrics
metric_cols = st.columns(5)
total = len(df)
metric_cols[0].metric("Total Personnel", total)
if "Department" in df.columns:
    metric_cols[1].metric("Departments", df["Department"].nunique())
if "Staff Position" in df.columns:
    metric_cols[2].metric("Positions", df["Staff Position"].nunique())
if "SG" in df.columns:
    metric_cols[3].metric("Salary Grades", df["SG"].nunique())
if "Gender" in df.columns:
    metric_cols[4].metric("Female", int((df["Gender"].astype(str).str.upper() == "FEMALE").sum()))

st.markdown("---")

# Nationality
if "Nationality" in df.columns:
    st.subheader("🌍 Nationality Distribution")
    map_data = prepare_nationality_map_data(df)
    if map_data is not None and not map_data.empty:
        try:
            fig = create_nationality_bubble_map(map_data)
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            st.dataframe(map_data, use_container_width=True)

# Position breakdown
if "Staff Position" in df.columns:
    st.subheader("👔 Position Breakdown")
    position_counts = df["Staff Position"].fillna("Not Specified").value_counts().reindex(POSITION_HIERARCHY_ORDER).dropna()
    if not position_counts.empty:
        st.plotly_chart(px.bar(position_counts.reset_index(name="Personnel"), x="Staff Position", y="Personnel"), use_container_width=True)

# Salary grade distribution
if "SG" in df.columns:
    st.subheader("💼 Salary Grade Distribution")
    sg_counts = df["SG"].fillna("Not Specified").value_counts()
    ordered = [sg for sg in SG_HIERARCHY if sg in sg_counts.index]
    remaining = [sg for sg in sg_counts.index if sg not in ordered]
    sg_plot = sg_counts.reindex(ordered + remaining).dropna()
    st.plotly_chart(px.bar(sg_plot.reset_index(name="Personnel"), x="SG", y="Personnel"), use_container_width=True)

# Gender distribution
if "Gender" in df.columns:
    st.subheader("⚥ Gender Distribution")
    gender = df["Gender"].fillna("Not Specified").value_counts().reset_index(name="Personnel")
    st.plotly_chart(px.pie(gender, names="Gender", values="Personnel"), use_container_width=True)

# Office / current assignment distribution
for column, title in [("Office Location", "📍 Office Location Distribution"), ("Current Assignment", "🏢 Current Assignment Distribution")]:
    if column in df.columns:
        st.subheader(title)
        counts = df[column].fillna("Not Specified").value_counts().reset_index(name="Personnel")
        st.plotly_chart(px.bar(counts, x=column, y="Personnel"), use_container_width=True)

# Age vs salary grade
if {"Age", "SG"}.issubset(df.columns):
    st.subheader("📈 Age vs Salary Grade")
    scatter_df = df.copy()
    if "Overall_avg" not in scatter_df.columns:
        score_columns = [column for column in scatter_df.columns if str(column).startswith(("B", "K", "P", "E")) and str(column)[1:].isdigit()]
        if score_columns:
            scatter_df["Overall_avg"] = scatter_df[score_columns].mean(axis=1, skipna=True)
    scatter_df = _scatter_age_vs_grade(scatter_df)
    if not scatter_df.empty:
        size_col = next((c for c in ("Years of RE Experience", "Years in PET") if c in scatter_df.columns), None)
        kwargs = {"size": size_col} if size_col else {}
        fig = px.scatter(scatter_df, x="Age", y="SG", hover_name="Name", color="Department" if "Department" in scatter_df.columns else None, **kwargs)
        st.plotly_chart(fig, use_container_width=True)

# 3D career landscape
required_3d = {"Age", "Years in Salary Grade", "SG"}
if required_3d.issubset(df.columns):
    st.subheader("🧭 3D Career Landscape")
    career_df = df.copy()
    career_df["Age"] = pd.to_numeric(career_df["Age"], errors="coerce")
    career_df["Years in Salary Grade"] = pd.to_numeric(career_df["Years in Salary Grade"], errors="coerce")
    career_df["SG Rank"] = career_df["SG"].map(lambda value: SG_HIERARCHY.index(value) if value in SG_HIERARCHY else None)
    career_df = career_df.dropna(subset=["Age", "Years in Salary Grade", "SG Rank"])
    if not career_df.empty:
        fig = px.scatter_3d(career_df, x="Age", y="Years in Salary Grade", z="SG Rank", color="Department" if "Department" in career_df.columns else None, hover_name="Name")
        st.plotly_chart(fig, use_container_width=True)
