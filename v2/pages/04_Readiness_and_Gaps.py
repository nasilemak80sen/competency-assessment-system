"""Readiness & Gaps — native v2 page.

The page owns Streamlit interaction; readiness calculations and visualization
helpers live in v2.analytics so pages do not depend on the legacy runtime.
"""
from __future__ import annotations

import streamlit as st

from core.bootstrap import get_master_data, get_ruler_data
from analytics.readiness import (
    apply_readiness_personnel_filters,
    build_personnel_readiness_summary,
    build_readiness_detail_dataframe,
)
from analytics.charts import (
    _build_competency_risk_summary,
    _create_category_gap_distribution,
    _create_category_readiness_heatmap,
    _create_competency_risk_matrix,
    _create_department_competency_heatmap,
    _create_department_readiness_chart,
    _create_personnel_priority_scatter,
    _create_readiness_box_plot,
    _create_readiness_coverage_scatter,
    _create_readiness_status_chart,
    _create_top_competency_gap_chart,
)
from components.navigation import render_navigation, render_header

render_navigation()
render_header("🎯 Readiness & Gaps", "Workforce readiness, competency coverage and development priorities")

try:
    personnel_df = get_master_data()
    ruler_map, _tech_labels = get_ruler_data()
except Exception as exc:
    st.error(f"Unable to load readiness data: {exc}")
    st.stop()

if personnel_df is None or personnel_df.empty:
    st.warning("No personnel records are available for readiness analysis.")
    st.stop()

st.markdown("### 🔎 Filters")
filter_cols = st.columns(5)
with filter_cols[0]:
    search_text = st.text_input("Search Personnel", placeholder="Search by name or Staff ID", key="rg_search")
with filter_cols[1]:
    departments = sorted(personnel_df["Department"].dropna().astype(str).str.strip().unique()) if "Department" in personnel_df else []
    selected_departments = st.multiselect("Department", departments, key="rg_department")
with filter_cols[2]:
    positions = sorted(personnel_df["Staff Position"].dropna().astype(str).str.strip().unique()) if "Staff Position" in personnel_df else []
    selected_positions = st.multiselect("Staff Position", positions, key="rg_position")
with filter_cols[3]:
    grades = sorted(personnel_df["SG"].dropna().astype(str).str.strip().str.upper().unique()) if "SG" in personnel_df else []
    selected_grades = st.multiselect("Salary Grade", grades, key="rg_sg")
with filter_cols[4]:
    employment = sorted(personnel_df["Employment Category"].dropna().astype(str).str.strip().unique()) if "Employment Category" in personnel_df else []
    selected_employment = st.multiselect("Employment Category", employment, key="rg_employment")

filtered_df = apply_readiness_personnel_filters(
    personnel_df, search_text=search_text, departments=selected_departments,
    positions=selected_positions, salary_grades=selected_grades,
    employment_categories=selected_employment,
)

mode_col, target_col = st.columns([1, 1])
with mode_col:
    target_mode = st.radio("Target Mode", ["Current requirement", "Next salary grade", "Selected target grade"],
                           horizontal=True, key="rg_target_mode")
selected_target_sg = None
if target_mode == "Selected target grade":
    all_target_grades = sorted(
        {grade for ruler in ruler_map.values() for grade in ruler.keys()},
        key=lambda value: int(str(value)[1:]) if str(value).startswith("P") and str(value)[1:].isdigit() else 999,
    )
    with target_col:
        selected_target_sg = st.selectbox("Target Salary Grade", all_target_grades, key="rg_selected_target_sg")

detail_df = build_readiness_detail_dataframe(filtered_df, ruler_map, target_mode, selected_target_sg)
summary_df = build_personnel_readiness_summary(detail_df)
if summary_df.empty:
    st.info("No personnel meet the selected readiness target/filter combination.")
    st.stop()

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

st.markdown("### 📊 Readiness Overview")
chart_cols = st.columns(2)
with chart_cols[0]:
    st.plotly_chart(_create_readiness_status_chart(summary_df), width="stretch",
                    config={"displaylogo": False, "responsive": True})
with chart_cols[1]:
    st.plotly_chart(_create_department_readiness_chart(summary_df), width="stretch",
                    config={"displaylogo": False, "responsive": True})

# The extracted helpers are now the single visualization layer for the page.
# Keeping these charts here also preserves the analytical depth of the legacy
# readiness branch without importing app.py.
analysis_tabs = st.tabs([
    "📈 Coverage", "🎓 Salary Grade", "🧩 Category", "⚠️ Gap Risk", "👥 Prioritization",
])
with analysis_tabs[0]:
    st.plotly_chart(_create_readiness_coverage_scatter(summary_df), width="stretch",
                    config={"displaylogo": False, "responsive": True})
with analysis_tabs[1]:
    st.plotly_chart(_create_readiness_box_plot(summary_df), width="stretch",
                    config={"displaylogo": False, "responsive": True})
with analysis_tabs[2]:
    category_cols = st.columns(2)
    with category_cols[0]:
        st.plotly_chart(_create_category_readiness_heatmap(summary_df), width="stretch",
                        config={"displaylogo": False, "responsive": True})
    with category_cols[1]:
        st.plotly_chart(_create_category_gap_distribution(detail_df), width="stretch",
                        config={"displaylogo": False, "responsive": True})
with analysis_tabs[3]:
    risk_df = _build_competency_risk_summary(detail_df)
    if risk_df.empty:
        st.info("No assessed competency risk records are available.")
    else:
        risk_cols = st.columns(2)
        with risk_cols[0]:
            st.plotly_chart(_create_competency_risk_matrix(risk_df), width="stretch",
                            config={"displaylogo": False, "responsive": True})
        with risk_cols[1]:
            ranking_metric = st.selectbox(
                "Rank competency gaps by",
                ["Affected personnel", "Average gap severity", "Total gap burden", "Major-gap count"],
                key="rg_ranking_metric",
            )
            st.plotly_chart(_create_top_competency_gap_chart(risk_df, ranking_metric), width="stretch",
                            config={"displaylogo": False, "responsive": True})
        heatmap_scope = st.radio("Competencies shown", ["Top 10", "Top 15", "All"], horizontal=True, key="rg_heatmap_scope")
        heatmap_top_n = {"Top 10": 10, "Top 15": 15, "All": "All"}[heatmap_scope]
        heatmap = _create_department_competency_heatmap(detail_df, heatmap_top_n)
        if heatmap is not None:
            st.plotly_chart(heatmap, width="stretch", config={"displaylogo": False, "responsive": True})
        with st.expander("Competency Risk Detail"):
            st.dataframe(risk_df.sort_values(["Gap Burden", "Affected Personnel"], ascending=False),
                         width="stretch", hide_index=True)
with analysis_tabs[4]:
    priority_figure = _create_personnel_priority_scatter(summary_df)
    if priority_figure is not None:
        st.plotly_chart(priority_figure, width="stretch", config={"displaylogo": False, "responsive": True})
    priority_order = {
        "Leadership Review Required": 0, "Targeted Technical Development": 1,
        "Focused Development Plan": 2, "Close 1-2 Minor Gaps": 3,
        "Complete Assessment": 4, "Ready for Assessment": 5,
    }
    priority_df = summary_df.copy()
    priority_df["_Priority Order"] = priority_df["Recommended Action"].map(priority_order).fillna(99)
    priority_df = priority_df.sort_values(["_Priority Order", "Major Gaps", "Gap Burden"], ascending=[True, False, False]).drop(columns=["_Priority Order"])
    priority_columns = [
        "Name", "Staff ID", "Department", "Staff Position", "Current SG", "Career Ruler", "Target SG",
        "Assessment Coverage %", "Weighted Readiness %", "Strict Readiness %", "Major Gaps", "Minor Gaps",
        "Gap Burden", "Top Gap", "Years in Grade", "Readiness Status", "Recommended Action",
    ]
    priority_columns = [c for c in priority_columns if c in priority_df.columns]
    st.dataframe(priority_df[priority_columns], width="stretch", hide_index=True)

st.markdown("### ⚠️ Competency Gap Detail")
gap_detail = detail_df[detail_df["Gap"].notna() & (detail_df["Gap"] < 0)].copy()
if gap_detail.empty:
    st.success("No assessed competency gaps were found for the selected population.")
else:
    gap_columns = ["Name", "Staff ID", "Department", "Current SG", "Target SG", "Category", "Competency Code",
                   "Competency Name", "Actual Score", "Target Score", "Gap", "Gap Severity"]
    gap_columns = [c for c in gap_columns if c in gap_detail.columns]
    st.dataframe(gap_detail.sort_values("Gap", ascending=True)[gap_columns], width="stretch", hide_index=True)

with st.expander("📐 Metric Methodology"):
    st.markdown(
        "**Assessment Coverage** = assessed required competencies ÷ required competencies × 100.\n\n"
        "**Strict Readiness** = competencies meeting target ÷ required competencies × 100.\n\n"
        "**Weighted Readiness** = capped actual competency score ÷ total target requirement × 100.\n\n"
        "**Ready** requires weighted readiness ≥ 80%, strict readiness ≥ 75%, coverage ≥ 90%, and zero major gaps.\n\n"
        "**Near Ready** requires weighted readiness ≥ 65%, coverage ≥ 75%, and no more than two major gaps.\n\n"
        "Coverage below 40% is **Not Assessed**; other cases are **Development Required**."
    )
