"""Readiness & Gaps — native v2 page.

This page intentionally does not import ``legacy_runtime``. The golden
reference remains root ``app.py`` while this native implementation is
regression-tested against the extracted calculation rules.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from config import EXCEL_PATH
from core.bootstrap import get_master_data, get_ruler_data
from analytics.readiness import (
    READINESS_STATUS_ORDER,
    apply_readiness_personnel_filters,
    build_personnel_readiness_summary,
    build_readiness_detail_dataframe,
)
from components.navigation import render_navigation, render_header


render_navigation()
render_header(
    "🎯 Readiness & Gaps",
    "Workforce readiness, competency coverage and development priorities",
)

try:
    personnel_df = get_master_data()
    ruler_map, tech_labels = get_ruler_data()
except Exception as exc:
    st.error(f"Unable to load readiness data: {exc}")
    st.stop()

if personnel_df is None or personnel_df.empty:
    st.warning("No personnel records are available for readiness analysis.")
    st.stop()

# ---------------------------------------------------------------------------
# FILTERS
# ---------------------------------------------------------------------------

st.markdown("### 🔎 Filters")
filter_cols = st.columns(5)

with filter_cols[0]:
    search_text = st.text_input(
        "Search Personnel",
        placeholder="Search by name or Staff ID",
        key="rg_search",
    )

with filter_cols[1]:
    departments = sorted(personnel_df["Department"].dropna().astype(str).str.strip().unique().tolist()) if "Department" in personnel_df.columns else []
    selected_departments = st.multiselect("Department", departments, key="rg_department")

with filter_cols[2]:
    positions = sorted(personnel_df["Staff Position"].dropna().astype(str).str.strip().unique().tolist()) if "Staff Position" in personnel_df.columns else []
    selected_positions = st.multiselect("Staff Position", positions, key="rg_position")

with filter_cols[3]:
    grades = sorted(personnel_df["SG"].dropna().astype(str).str.strip().str.upper().unique().tolist()) if "SG" in personnel_df.columns else []
    selected_grades = st.multiselect("Salary Grade", grades, key="rg_sg")

with filter_cols[4]:
    employment = sorted(personnel_df["Employment Category"].dropna().astype(str).str.strip().unique().tolist()) if "Employment Category" in personnel_df.columns else []
    selected_employment = st.multiselect("Employment Category", employment, key="rg_employment")

filtered_df = apply_readiness_personnel_filters(
    personnel_df,
    search_text=search_text,
    departments=selected_departments,
    positions=selected_positions,
    salary_grades=selected_grades,
    employment_categories=selected_employment,
)

# ---------------------------------------------------------------------------
# TARGET MODE
# ---------------------------------------------------------------------------

mode_col, target_col = st.columns([1, 1])
with mode_col:
    target_mode = st.radio(
        "Target Mode",
        ["Current requirement", "Next salary grade", "Selected target grade"],
        horizontal=True,
        key="rg_target_mode",
    )

selected_target_sg = None
if target_mode == "Selected target grade":
    all_target_grades = sorted(
        {grade for ruler in ruler_map.values() for grade in ruler.keys()},
        key=lambda value: int(value[1:]) if str(value).startswith("P") and str(value)[1:].isdigit() else 999,
    )
    with target_col:
        selected_target_sg = st.selectbox(
            "Target Salary Grade",
            all_target_grades,
            key="rg_selected_target_sg",
        )

# ---------------------------------------------------------------------------
# CALCULATION STACK
# ---------------------------------------------------------------------------

detail_df = build_readiness_detail_dataframe(
    filtered_df,
    ruler_map,
    target_mode,
    selected_target_sg,
)
summary_df = build_personnel_readiness_summary(detail_df)

if summary_df.empty:
    st.info("No personnel meet the selected readiness target/filter combination.")
    st.stop()

# ---------------------------------------------------------------------------
# KPI SUMMARY
# ---------------------------------------------------------------------------

ready_count = int((summary_df["Readiness Status"] == "Ready").sum())
near_ready_count = int((summary_df["Readiness Status"] == "Near Ready").sum())
development_count = int((summary_df["Readiness Status"] == "Development Required").sum())
not_assessed_count = int((summary_df["Readiness Status"] == "Not Assessed").sum())

kpis = st.columns(5)
kpis[0].metric("Personnel", f"{len(summary_df):,}")
kpis[1].metric("Ready", f"{ready_count:,}")
kpis[2].metric("Near Ready", f"{near_ready_count:,}")
kpis[3].metric("Development Required", f"{development_count:,}")
kpis[4].metric("Not Assessed", f"{not_assessed_count:,}")

# ---------------------------------------------------------------------------
# VISUAL SUMMARY
# ---------------------------------------------------------------------------

st.markdown("### 📊 Readiness Overview")
chart_cols = st.columns(2)

status_counts = (
    summary_df["Readiness Status"]
    .value_counts()
    .reindex(READINESS_STATUS_ORDER, fill_value=0)
    .rename_axis("Readiness Status")
    .reset_index(name="Personnel")
)

with chart_cols[0]:
    fig = px.bar(
        status_counts,
        x="Personnel",
        y="Readiness Status",
        orientation="h",
        text="Personnel",
        category_orders={"Readiness Status": READINESS_STATUS_ORDER},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(height=390, showlegend=False, xaxis_title="Personnel", yaxis_title=None)
    st.plotly_chart(fig, use_container_width=True)

with chart_cols[1]:
    department_summary = (
        summary_df.groupby("Department", as_index=False)
        .agg(
            Median_Readiness=("Weighted Readiness %", "median"),
            Personnel=("Name", "count"),
        )
        .sort_values("Median_Readiness")
    )
    fig = px.scatter(
        department_summary,
        x="Median_Readiness",
        y="Department",
        size="Personnel",
        text="Median_Readiness",
    )
    fig.add_vline(x=80, line_dash="dash")
    fig.update_traces(texttemplate="%{x:.0f}%", textposition="middle right")
    fig.update_layout(height=390, xaxis_title="Median Weighted Readiness (%)", yaxis_title=None)
    fig.update_xaxes(range=[0, 105])
    st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------
# PERSONNEL PRIORITY TABLE
# ---------------------------------------------------------------------------

st.markdown("### 👥 Personnel Readiness")

priority_columns = [
    "Name", "Staff ID", "Department", "Staff Position", "Current SG",
    "Career Ruler", "Target SG", "Assessment Coverage %", "Weighted Readiness %",
    "Strict Readiness %", "Minor Gaps", "Major Gaps", "Gap Burden",
    "Readiness Status", "Recommended Action", "Top Gap",
]
priority_columns = [c for c in priority_columns if c in summary_df.columns]

display_df = summary_df[priority_columns].copy()
for column in ["Assessment Coverage %", "Weighted Readiness %", "Strict Readiness %"]:
    if column in display_df.columns:
        display_df[column] = display_df[column].round(1)

st.dataframe(display_df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# GAP DETAIL
# ---------------------------------------------------------------------------

st.markdown("### ⚠️ Competency Gap Detail")
gap_detail = detail_df[detail_df["Gap"].notna() & (detail_df["Gap"] < 0)].copy()
if gap_detail.empty:
    st.success("No assessed competency gaps were found for the selected population.")
else:
    gap_columns = [
        "Name", "Staff ID", "Department", "Current SG", "Target SG",
        "Category", "Competency Code", "Competency Name", "Actual Score",
        "Target Score", "Gap", "Gap Severity",
    ]
    gap_columns = [c for c in gap_columns if c in gap_detail.columns]
    gap_detail = gap_detail.sort_values("Gap", ascending=True)
    st.dataframe(gap_detail[gap_columns], use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------------
# METHODOLOGY
# ---------------------------------------------------------------------------

with st.expander("📐 Metric Methodology"):
    st.markdown(
        """
**Assessment Coverage** = assessed required competencies ÷ required competencies × 100.

**Strict Readiness** = competencies meeting target ÷ required competencies × 100.

**Weighted Readiness** = capped actual competency score ÷ total target requirement × 100.

**Ready** requires weighted readiness ≥ 80%, strict readiness ≥ 75%, coverage ≥ 90%, and zero major gaps.

**Near Ready** requires weighted readiness ≥ 65%, coverage ≥ 75%, and no more than two major gaps.

Below those thresholds, the personnel are classified as **Development Required**; coverage below 40% is **Not Assessed**.
        """
    )
