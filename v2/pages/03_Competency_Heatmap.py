"""Competency Heatmap — native v2 page."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data
from config import COMP_TYPES, SCORE_COLS
from analytics import build_heatmap_matrix

render_navigation()
render_header("🌡️ Competency Heatmap", "Explore assessed competency scores across the workforce")

df = get_master_data()
if df is None or df.empty:
    st.warning("No personnel data is available.")
    st.stop()

filter_cols = st.columns(4)
with filter_cols[0]:
    departments = st.multiselect("Department", sorted(df["Department"].dropna().astype(str).unique()) if "Department" in df else [], key="hm_dept")
with filter_cols[1]:
    positions = st.multiselect("Position", sorted(df["Staff Position"].dropna().astype(str).unique()) if "Staff Position" in df else [], key="hm_pos")
with filter_cols[2]:
    grades = st.multiselect("Salary Grade", sorted(df["SG"].dropna().astype(str).unique()) if "SG" in df else [], key="hm_sg")
with filter_cols[3]:
    types = st.multiselect("Competency Type", list(COMP_TYPES), default=list(COMP_TYPES),
                           format_func=lambda code: COMP_TYPES.get(code, {}).get("label", code), key="hm_type")

filtered = df.copy()
if departments: filtered = filtered[filtered["Department"].astype(str).isin(departments)]
if positions: filtered = filtered[filtered["Staff Position"].astype(str).isin(positions)]
if grades: filtered = filtered[filtered["SG"].astype(str).isin(grades)]

value_cols = []
for competency_type in types:
    value_cols.extend([c for c in COMP_TYPES.get(competency_type, {}).get("cols", []) if c in filtered.columns])
value_cols = list(dict.fromkeys(value_cols))
if not value_cols:
    st.info("No competency columns are available for the selected types.")
    st.stop()

controls = st.columns(2)
with controls[0]:
    sort_option = st.selectbox("Sort personnel by", ["Name", "Average score: high to low", "Average score: low to high", "Low-score cells: high to low"], key="hm_sort")
with controls[1]:
    minimum_coverage = st.slider("Minimum assessment coverage", 0, 100, 0, 5, format="%d%%", key="hm_min_coverage")

matrix = build_heatmap_matrix(filtered, value_cols)
coverage = filtered[value_cols].notna().mean(axis=1) * 100
coverage.index = filtered.index
filtered = filtered.loc[coverage[coverage >= minimum_coverage].index]
matrix = build_heatmap_matrix(filtered, value_cols)
if matrix.empty:
    st.info("No personnel meet the selected filters and minimum assessment coverage.")
    st.stop()

if sort_option == "Average score: high to low":
    matrix = matrix.loc[matrix.mean(axis=1).sort_values(ascending=False).index]
elif sort_option == "Average score: low to high":
    matrix = matrix.loc[matrix.mean(axis=1).sort_values(ascending=True).index]
elif sort_option == "Low-score cells: high to low":
    matrix = matrix.loc[matrix.min(axis=1).sort_values(ascending=False).index]
else:
    matrix = matrix.sort_index()

fig = go.Figure(go.Heatmap(
    z=matrix.values, x=matrix.columns, y=matrix.index,
    zmin=0, zmax=5,
    colorscale="RdYlGn",
    text=np.where(pd.isna(matrix.values), "", np.round(matrix.values, 1)),
    texttemplate="%{text}",
    hovertemplate="<b>%{y}</b><br>Competency: %{x}<br>Score: %{z:.1f}<extra></extra>",
    colorbar={"title": "Score"},
))
fig.update_layout(height=max(520, 28 * len(matrix.index) + 180), xaxis_title="Competency", yaxis_title="Personnel", margin={"l":20,"r":20,"t":50,"b":40})
st.plotly_chart(fig, width="stretch", config={"displaylogo": False, "responsive": True})
st.caption(f"Showing {len(matrix):,} assessed personnel across {len(matrix.columns):,} competency elements.")
