"""Readiness & Gaps — faithful native-v2 reproduction of the golden page."""
from __future__ import annotations

import streamlit as st

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
from analytics.readiness import (
    READINESS_STATUS_ORDER,
    _build_filter_options,
    _reset_readiness_filters,
    _rg_get_person_ruler,
    _rg_sort_salary_grades,
    apply_readiness_personnel_filters,
    build_personnel_readiness_summary,
    build_readiness_detail_dataframe,
)
from components.navigation import render_header, render_navigation
from core.bootstrap import get_master_data, get_ruler_data


render_navigation()
render_header(
    "🎯 Readiness & Gaps Deep Dive",
    "Understand competency readiness, capability constraints, assessment coverage, and personnel development priorities.",
)

try:
    df = get_master_data()
    ruler_map, _tech_labels = get_ruler_data()
except Exception as exc:
    st.error(f"Unable to load readiness data: {exc}")
    st.stop()

if df is None or df.empty:
    st.warning("No personnel data is available.")
    st.stop()

required_columns = ["Name", "Department", "Staff Position", "SG"]
missing_columns = [column for column in required_columns if column not in df.columns]
if missing_columns:
    st.error(f"The personnel dataset is missing required columns: {missing_columns}")
    st.stop()
if not ruler_map:
    st.error("No Career Ruler requirements are available.")
    st.stop()

# -----------------------------------------------------------------------------
# GLOBAL FILTERS
# -----------------------------------------------------------------------------

st.subheader("🔎 Global Filters")

department_options = _build_filter_options(df, "Department")
position_options = _build_filter_options(df, "Staff Position")
salary_grade_options = _rg_sort_salary_grades(_build_filter_options(df, "SG"))
employment_options = _build_filter_options(df, "Employment Category")
ruler_options = sorted(str(ruler).strip() for ruler in ruler_map.keys())
all_target_grades = _rg_sort_salary_grades(
    grade for requirements in ruler_map.values() for grade in requirements.keys()
)

search_col, dept_col, pos_col, sg_col, ruler_col = st.columns([2.2, 1.2, 1.2, 1, 1.1])
with search_col:
    search_text = st.text_input(
        "Search Personnel",
        placeholder="Search by name or Staff ID",
        key="rg_search",
    )
with dept_col:
    selected_departments = st.multiselect("Department", department_options, key="rg_department")
with pos_col:
    selected_positions = st.multiselect("Staff Position", position_options, key="rg_position")
with sg_col:
    selected_salary_grades = st.multiselect("Current SG", salary_grade_options, key="rg_sg")
with ruler_col:
    selected_rulers = st.multiselect("Career Ruler", ruler_options, key="rg_ruler")

employment_col, target_mode_col, target_sg_col, reset_col = st.columns([1.4, 1.6, 1.4, 0.8], vertical_alignment="bottom")
with employment_col:
    selected_employment = st.multiselect("Employment Category", employment_options, key="rg_employment")
with target_mode_col:
    target_mode = st.selectbox(
        "Target Requirement",
        ["Next salary grade", "Current requirement", "Selected target grade"],
        index=0,
        key="rg_target_mode",
        help="Next salary grade compares each person against the next available grade in the assigned Career Ruler.",
    )
with target_sg_col:
    if target_mode == "Selected target grade":
        selected_target_sg = st.selectbox("Selected Target SG", all_target_grades, key="rg_selected_target_sg")
    else:
        selected_target_sg = None
        st.text_input(
            "Selected Target SG",
            value="Automatically determined",
            disabled=True,
            key="rg_target_sg_disabled",
        )
with reset_col:
    if st.button("Reset", type="secondary", width="stretch", key="rg_reset_filters"):
        _reset_readiness_filters(st.session_state)
        st.rerun()

filtered_personnel_df = apply_readiness_personnel_filters(
    df,
    search_text=search_text,
    departments=selected_departments,
    positions=selected_positions,
    salary_grades=selected_salary_grades,
    employment_categories=selected_employment,
)

if selected_rulers:
    ruler_series = filtered_personnel_df.apply(
        lambda row: str(_rg_get_person_ruler(row, ruler_map)), axis=1
    )
    filtered_personnel_df = filtered_personnel_df[ruler_series.isin(selected_rulers)]

if filtered_personnel_df.empty:
    st.warning("No personnel match the selected filters.")
    st.stop()

# -----------------------------------------------------------------------------
# READINESS CALCULATION
# -----------------------------------------------------------------------------

with st.spinner("Calculating readiness and competency gaps..."):
    detail_df = build_readiness_detail_dataframe(
        filtered_personnel_df,
        ruler_map,
        target_mode,
        selected_target_sg,
    )
    summary_df = build_personnel_readiness_summary(detail_df)

if detail_df is None or detail_df.empty:
    st.warning("No target requirements could be matched to the selected personnel and target mode.")
    with st.expander("Readiness calculation diagnostics"):
        st.write(
            {
                "Filtered personnel": len(filtered_personnel_df),
                "Target mode": target_mode,
                "Selected target SG": selected_target_sg,
                "Available rulers": list(ruler_map.keys()),
            }
        )
    st.stop()

if summary_df is None or summary_df.empty:
    st.warning("The competency data was loaded, but personnel-level readiness could not be summarized.")
    st.stop()

# -----------------------------------------------------------------------------
# RESULT FILTERS
# -----------------------------------------------------------------------------

st.markdown("#### Readiness Result Filters")
coverage_col, status_col, result_count_col = st.columns([2, 2, 1], vertical_alignment="bottom")
with coverage_col:
    coverage_range = st.slider(
        "Assessment Coverage (%)",
        min_value=0,
        max_value=100,
        value=(0, 100),
        step=5,
        key="rg_coverage",
    )
with status_col:
    selected_statuses = st.multiselect(
        "Readiness Status",
        READINESS_STATUS_ORDER,
        key="rg_status",
    )

filtered_summary_df = summary_df[
    summary_df["Assessment Coverage %"].between(
        coverage_range[0], coverage_range[1], inclusive="both"
    )
].copy()
if selected_statuses:
    filtered_summary_df = filtered_summary_df[
        filtered_summary_df["Readiness Status"].isin(selected_statuses)
    ]
with result_count_col:
    st.metric("Filtered Personnel", len(filtered_summary_df))

if filtered_summary_df.empty:
    st.info("No readiness results match the selected coverage and readiness-status filters.")
    st.stop()

selected_indices = filtered_summary_df["DataFrame Index"].dropna().tolist()
filtered_detail_df = detail_df[detail_df["DataFrame Index"].isin(selected_indices)].copy()

# -----------------------------------------------------------------------------
# KPI SUMMARY
# -----------------------------------------------------------------------------

total_personnel = len(filtered_summary_df)
fully_assessed = int((filtered_summary_df["Assessment Coverage %"] >= 90).sum())
ready_count = int((filtered_summary_df["Readiness Status"] == "Ready").sum())
near_ready_count = int((filtered_summary_df["Readiness Status"] == "Near Ready").sum())
major_gap_personnel = int((filtered_summary_df["Major Gaps"] > 0).sum())
median_readiness = filtered_summary_df["Weighted Readiness %"].median()

kpis = st.columns(6)
kpis[0].metric("Personnel", total_personnel)
kpis[1].metric(
    "Fully Assessed",
    fully_assessed,
    f"{fully_assessed / total_personnel * 100:.0f}%" if total_personnel else None,
)
kpis[2].metric("Ready", ready_count)
kpis[3].metric("Near Ready", near_ready_count)
kpis[4].metric("With Major Gaps", major_gap_personnel)
kpis[5].metric("Median Readiness", f"{median_readiness:.0f}%" if pd.notna(median_readiness) else "N/A")

# -----------------------------------------------------------------------------
# TABS
# -----------------------------------------------------------------------------

overview_tab, distribution_tab, gap_deep_dive_tab, prioritization_tab = st.tabs(
    ["📊 Overview", "📈 Readiness Distribution", "🔍 Gap Deep Dive", "🎯 Personnel Prioritization"]
)

with overview_tab:
    st.subheader("Fraternity Readiness Overview")
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            _create_readiness_status_chart(filtered_summary_df),
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )
    with right:
        st.plotly_chart(
            _create_department_readiness_chart(filtered_summary_df),
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )

    st.subheader("Personnel Ready for Assessment")
    ready_df = filtered_summary_df[
        filtered_summary_df["Readiness Status"] == "Ready"
    ].sort_values(["Weighted Readiness %", "Strict Readiness %"], ascending=[False, False])
    ready_columns = [
        "Name", "Staff ID", "Department", "Staff Position", "Current SG", "Career Ruler", "Target SG",
        "Base Readiness %", "Key Readiness %", "Pacing Readiness %", "Emerging Readiness %",
        "Assessment Coverage %", "Weighted Readiness %", "Strict Readiness %", "Major Gaps", "Recommended Action",
    ]
    ready_columns = [c for c in ready_columns if c in ready_df.columns]
    if ready_df.empty:
        st.info("No personnel currently satisfy all competency readiness requirements.")
    else:
        st.dataframe(
            ready_df[ready_columns],
            width="stretch",
            hide_index=True,
            column_config={
                "Assessment Coverage %": st.column_config.ProgressColumn("Coverage", min_value=0, max_value=100, format="%.0f%%"),
                "Weighted Readiness %": st.column_config.ProgressColumn("Weighted Readiness", min_value=0, max_value=100, format="%.0f%%"),
                "Strict Readiness %": st.column_config.ProgressColumn("Strict Readiness", min_value=0, max_value=100, format="%.0f%%"),
            },
        )

    with st.expander("Full Personnel Readiness Table"):
        overview_columns = [
            "Name", "Staff ID", "Department", "Staff Position", "Employment Category", "Current SG", "Career Ruler",
            "Target SG", "Required Competencies", "Assessed Competencies", "Base Readiness %", "Key Readiness %",
            "Pacing Readiness %", "Emerging Readiness %", "Assessment Coverage %", "Weighted Readiness %",
            "Strict Readiness %", "Met Competencies", "Minor Gaps", "Major Gaps", "Gap Burden", "Readiness Status",
            "Recommended Action",
        ]
        overview_columns = [c for c in overview_columns if c in filtered_summary_df.columns]
        st.dataframe(
            filtered_summary_df[overview_columns].sort_values("Weighted Readiness %", ascending=False),
            width="stretch",
            hide_index=True,
        )

with distribution_tab:
    st.subheader("Readiness Distribution and Assessment Coverage")
    st.plotly_chart(
        _create_readiness_box_plot(filtered_summary_df),
        width="stretch",
        config={"displaylogo": False, "responsive": True},
    )
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            _create_category_readiness_heatmap(filtered_summary_df),
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )
    with right:
        st.plotly_chart(
            _create_readiness_coverage_scatter(filtered_summary_df),
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )
    with st.expander("How to interpret the coverage quadrant"):
        st.markdown(
            "**Upper right:** High measured readiness and sufficient assessment coverage.\n\n"
            "**Lower right:** Sufficiently assessed, but competency development is required.\n\n"
            "**Upper left:** Strong measured results, but insufficient assessment evidence.\n\n"
            "**Lower left:** Both under-assessed and below readiness expectations."
        )

with gap_deep_dive_tab:
    st.subheader("Competency Gap Deep Dive")
    st.plotly_chart(
        _create_category_gap_distribution(filtered_detail_df),
        width="stretch",
        config={"displaylogo": False, "responsive": True},
    )
    risk_df = _build_competency_risk_summary(filtered_detail_df)
    if risk_df.empty:
        st.info("No assessed competency gaps are available for risk analysis.")
    else:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(
                _create_competency_risk_matrix(risk_df),
                width="stretch",
                config={"displaylogo": False, "responsive": True},
            )
        with right:
            ranking_metric = st.selectbox(
                "Rank competency gaps by",
                ["Affected personnel", "Average gap severity", "Total gap burden", "Major-gap count"],
                key="rg_ranking_metric",
            )
            st.plotly_chart(
                _create_top_competency_gap_chart(risk_df, ranking_metric),
                width="stretch",
                config={"displaylogo": False, "responsive": True},
            )

        st.subheader("Department by Competency Gap Rate")
        heatmap_scope = st.radio(
            "Competencies shown",
            ["Top 10", "Top 15", "All"],
            horizontal=True,
            key="rg_heatmap_scope",
        )
        heatmap = _create_department_competency_heatmap(
            filtered_detail_df,
            {"Top 10": 10, "Top 15": 15, "All": "All"}[heatmap_scope],
        )
        if heatmap is None:
            st.info("No assessed competency data is available for the department heatmap.")
        else:
            st.plotly_chart(heatmap, width="stretch", config={"displaylogo": False, "responsive": True})

        with st.expander("Competency Risk Detail"):
            st.dataframe(
                risk_df.sort_values(["Gap Burden", "Affected Personnel"], ascending=[False, False]),
                width="stretch",
                hide_index=True,
                column_config={
                    "Gap Prevalence %": st.column_config.ProgressColumn("Gap Prevalence", min_value=0, max_value=100, format="%.0f%%"),
                    "Average Gap Severity": st.column_config.NumberColumn("Average Severity", format="%.2f"),
                    "Gap Burden": st.column_config.NumberColumn("Gap Burden", format="%.0f"),
                },
            )

with prioritization_tab:
    st.subheader("Personnel Development Prioritization")
    priority_figure = _create_personnel_priority_scatter(filtered_summary_df)
    if priority_figure is not None:
        st.plotly_chart(
            priority_figure,
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )

    priority_order = {
        "Leadership Review Required": 0,
        "Targeted Technical Development": 1,
        "Focused Development Plan": 2,
        "Close 1-2 Minor Gaps": 3,
        "Complete Assessment": 4,
        "Ready for Assessment": 5,
    }
    priority_df = filtered_summary_df.copy()
    priority_df["_Priority Order"] = priority_df["Recommended Action"].map(priority_order).fillna(99)
    priority_df = priority_df.sort_values(
        ["_Priority Order", "Major Gaps", "Gap Burden"],
        ascending=[True, False, False],
    ).drop(columns=["_Priority Order"])
    priority_columns = [
        "Name", "Staff ID", "Department", "Staff Position", "Current SG", "Career Ruler", "Target SG",
        "Assessment Coverage %", "Weighted Readiness %", "Strict Readiness %", "Major Gaps", "Minor Gaps",
        "Gap Burden", "Top Gap", "Years in Grade", "Readiness Status", "Recommended Action",
    ]
    priority_columns = [c for c in priority_columns if c in priority_df.columns]
    st.dataframe(
        priority_df[priority_columns],
        width="stretch",
        hide_index=True,
        column_config={
            "Assessment Coverage %": st.column_config.ProgressColumn("Coverage", min_value=0, max_value=100, format="%.0f%%"),
            "Weighted Readiness %": st.column_config.ProgressColumn("Weighted Readiness", min_value=0, max_value=100, format="%.0f%%"),
            "Strict Readiness %": st.column_config.ProgressColumn("Strict Readiness", min_value=0, max_value=100, format="%.0f%%"),
            "Gap Burden": st.column_config.NumberColumn("Gap Burden", format="%.0f"),
            "Years in Grade": st.column_config.NumberColumn("Years in Grade", format="%.0f"),
        },
    )

    st.markdown("#### Selected Personnel Detail")
    person_options = priority_df["Name"].dropna().astype(str).unique().tolist()
    if not person_options:
        st.info("No personnel are available for detailed review.")
    else:
        selected_person = st.selectbox("Select personnel for gap detail", person_options, key="rg_priority_person")
        selected_summary_rows = priority_df[priority_df["Name"] == selected_person]
        if selected_summary_rows.empty:
            st.info("The selected personnel summary could not be found.")
        else:
            selected_summary = selected_summary_rows.iloc[0]
            person_detail = filtered_detail_df[
                filtered_detail_df["DataFrame Index"] == selected_summary["DataFrame Index"]
            ].copy()
            severity_order = {"Major Gap": 0, "Minor Gap": 1, "Not Assessed": 2, "Met": 3}
            person_detail["_Severity Order"] = person_detail["Gap Severity"].map(severity_order).fillna(99)
            person_detail = person_detail.sort_values(
                ["_Severity Order", "Gap", "Competency Code"],
                ascending=[True, True, True],
                na_position="last",
            ).drop(columns=["_Severity Order"])
            detail_kpis = st.columns(4)
            detail_kpis[0].metric("Readiness", f"{selected_summary['Weighted Readiness %']:.0f}%")
            detail_kpis[1].metric("Coverage", f"{selected_summary['Assessment Coverage %']:.0f}%")
            detail_kpis[2].metric("Major Gaps", int(selected_summary["Major Gaps"]))
            detail_kpis[3].metric("Recommended Action", str(selected_summary["Recommended Action"]))
            detail_columns = [
                "Competency Code", "Competency Name", "Category", "Current SG", "Target SG",
                "Actual Score", "Target Score", "Gap", "Gap Severity",
            ]
            detail_columns = [c for c in detail_columns if c in person_detail.columns]
            st.dataframe(person_detail[detail_columns], width="stretch", hide_index=True)

# -----------------------------------------------------------------------------
# GAP DETAIL + METHODOLOGY
# -----------------------------------------------------------------------------

st.markdown("### ⚠️ Competency Gap Detail")
gap_detail = filtered_detail_df[
    filtered_detail_df["Gap"].notna() & (filtered_detail_df["Gap"] < 0)
].copy()
if gap_detail.empty:
    st.success("No assessed competency gaps were found for the selected population.")
else:
    gap_columns = [
        "Name", "Staff ID", "Department", "Current SG", "Target SG", "Category",
        "Competency Code", "Competency Name", "Actual Score", "Target Score", "Gap", "Gap Severity",
    ]
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
