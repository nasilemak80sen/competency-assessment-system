"""Structural contract tests for the migrated pages.

These tests deliberately validate controls and workflows, not just imports.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "v2/pages/07_Admin.py"
IND = ROOT / "v2/pages/05_Individual_Assessment_Golden.py"
HEATMAP = ROOT / "v2/pages/03_Competency_Heatmap.py"
READINESS = ROOT / "v2/pages/04_Readiness_and_Gaps.py"
CHARTS = ROOT / "v2/pages/06_Chart_Builder.py"


def test_admin_has_complete_golden_personnel_field_contract():
    s = ADMIN.read_text(encoding="utf-8")
    fields = [
        "Nationality", "Employment Category", "Section Name", "Unit Name", "Sub Unit",
        "Current Assignment", "Joining Date", "Contract Expire Date", "Assignment Date",
        "SG Start Date", "Years in PET", "Years of RE Experience", "Years in Salary Grade",
        "Age Promoted", "Length in Current Assignment", "Chat Status", "Chat Date",
        "Assessment Level", "Last Assessment Date", "Sub-disciplines", "Potential",
        "Resource / SME", "Interest", "Strength", "Recommendation", "Preference",
        "Comments / suggestions", "Assessor 1", "Assessor 2", "Supervisor", "Remarks",
    ]
    missing = [x for x in fields if x not in s]
    assert not missing, f"Admin field contract missing: {missing}"
    assert '"Create personnel record" if is_add else "Save profile changes"' in s
    assert "add_personnel(" in s
    assert "changed_by=_current_admin_actor()" in s
    assert "Edit personnel profile" in s


def test_admin_assessment_uses_complete_editable_competency_matrix():
    s = ADMIN.read_text(encoding="utf-8")
    assert "for competency_type, info in COMP_TYPES.items()" in s
    assert "COMPETENCY_FULLNAMES.get(code, code)" in s
    assert "st.data_editor(" in s
    assert '"Actual": actual_default' in s
    assert '"Target": target_default' in s
    assert '"Actual": st.column_config.NumberColumn(' in s
    assert '"Target": st.column_config.NumberColumn(' in s
    assert "save_assessment_transaction(" in s
    assert "Save assessment and all 24 scores" in s


def test_individual_has_golden_profile_document_target_and_summary_contract():
    s = IND.read_text(encoding="utf-8")
    required = [
        "👤 Personnel Overview", "📄 CV & Documents", "Position / Grade", "Department / Section",
        "Current Assignment", "Years in PETRONAS", "Years of RE Experiences", "Contract Expiry Date",
        "Length in Grade", "Assessment Type", "📊 Assessment-Based Competency Strength",
        "🟢 Base", "🔵 Key", "🟠 Pace", "🟣 Emerging", "🎯 Target Definition & Career Progression",
        "Career Ruler", "Target Requirement", "Selected Target SG", "Next salary grade",
        "Current requirement", "Selected target grade", "Assessment Summary vs Target", "Weighted Readiness",
        "Strict Readiness", "Major Gaps", "Not Assessed", "📊 Summary Personnel Scores and Competencies",
        "📅 Assessment History", "📥 Download PDF Report",
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Individual golden contract missing: {missing}"


def test_individual_competency_strength_has_ranked_top_cards_and_full_ranking():
    s = IND.read_text(encoding="utf-8")
    required = [
        "def _strength_frame",
        "def _render_competency_strength_class",
        "🥇",
        "🥈",
        "🥉",
        'st.metric("Score"',
        '"Target"',
        '"Gap Status"',
        "Full {class_label} competency ranking",
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Individual competency-strength contract missing: {missing}"


def test_individual_documents_validate_rank_and_diagnose_sharepoint_links():
    s = IND.read_text(encoding="utf-8")
    assert 'str.startswith(\n                ("https://", "http://")\n            )' in s
    assert "sort_columns = [column for column in [\"Modified Date\", \"id\"]" in s
    assert "Open Latest Document in SharePoint" in s
    assert "Documents without valid links" in s
    assert "Personnel matching diagnostics" in s


def test_individual_uses_target_gap_and_readiness_calculations():
    s = IND.read_text(encoding="utf-8")
    assert "build_target_gap_dataframe" in s
    assert "calculate_readiness_metrics" in s
    assert 'requirements.get(target, {})' in s
    assert 'metrics["weighted_readiness"]' in s


def test_heatmap_has_golden_filters_sorting_and_coverage_controls():
    s = HEATMAP.read_text(encoding="utf-8")
    required = [
        '"Department"',
        '"Position"',
        '"Salary Grade"',
        '"Competency Type"',
        '"Show score inside cells"',
        '"Minimum assessment coverage"',
        '"Low-score cells: high to low"',
        '"Assessment coverage: low to high"',
        '"Heatmap Label"',
        '"High Score Cells"',
        '"Low Score Cells"',
        '"Missing Competencies"',
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Heatmap control contract missing: {missing}"


def test_heatmap_has_golden_visual_and_summary_workflows():
    s = HEATMAP.read_text(encoding="utf-8")
    required = [
        "Actual Competency Score Matrix", "Competency Name:", "Actual Score:",
        "heatmap_personnel_summary.csv", "heatmap_competency_summary.csv", "Heatmap Analysis Summary",
        "Personnel Summary", "Competency Summary", "Category Summary", "Scores ≥4", "Scores ≤2",
        "Coverage %", "ProgressColumn", "xgap=1.5", "ygap=1.5", '"competency_heatmap"',
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Heatmap visualization/summary contract missing: {missing}"


def test_readiness_has_full_golden_filter_kpi_and_tab_contract():
    s = READINESS.read_text(encoding="utf-8")
    required = [
        "Global Filters", "Search Personnel", "Career Ruler", "Employment Category", "Target Requirement",
        "Selected Target SG", "Reset", "Assessment Coverage (%)", "Readiness Status", "Filtered Personnel",
        "Fully Assessed", "Median Readiness", "📊 Overview", "📈 Readiness Distribution", "🔍 Gap Deep Dive",
        "🎯 Personnel Prioritization", "Personnel Ready for Assessment", "Full Personnel Readiness Table",
        "Competency Risk Detail", "Rank competency gaps by", "Top 10", "Top 15", "Selected Personnel Detail",
        "Competency Gap Detail", "Metric Methodology",
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Readiness workflow contract missing: {missing}"


def test_readiness_uses_native_readiness_analytics_stack():
    s = READINESS.read_text(encoding="utf-8")
    for text in [
        "build_readiness_detail_dataframe",
        "build_personnel_readiness_summary",
        "apply_readiness_personnel_filters",
        "_create_readiness_status_chart",
        "_create_department_readiness_chart",
        "_create_readiness_box_plot",
        "_create_category_readiness_heatmap",
        "_create_readiness_coverage_scatter",
        "_build_competency_risk_summary",
        "_create_competency_risk_matrix",
        "_create_top_competency_gap_chart",
        "_create_department_competency_heatmap",
        "_create_personnel_priority_scatter",
    ]:
        assert text in s, f"Readiness analytics dependency missing: {text}"


def test_chart_builder_has_guided_axes_numeric_measures_and_result_validation():
    s = CHARTS.read_text(encoding="utf-8")
    required = [
        "Workforce Chart Builder",
        "get_chart_builder_fields",
        "X-axis field",
        "Y-axis measure",
        "Number of personnel records",
        'aggregation_options = ["Average", "Median", "Sum", "Minimum", "Maximum"]',
        "Valid Values",
        "cb_last_chart_source_data",
        "generate the chart again to refresh it",
        "Compare individual competency profiles",
        "cb-hero",
        "01 · Define your workforce",
        "Personnel search",
        "More workforce filters",
        "Numeric range filter",
        "03 · Choose how to visualise",
        "04 · Create your chart",
        "05 · Review your results",
        "Inspect the values behind this chart",
        "filter_signature",
        "WORKFORCE FILTER TOOLBAR",
        'chart_controls_col, chart_workspace_col = st.columns([3, 9]',
        "with chart_workspace_col:",
        "cb_live_update_v2",
        "cb_reset_filters_v2",
        "cb_reset_chart_setup_v2",
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Chart Builder workflow contract missing: {missing}"
    assert "Count of rows" not in s, "Record counts should be an explicit mode, not the default Y-axis."
    assert "X-axis · Group, category or explanatory variable" not in s
    assert "Y-axis · Numeric measure" not in s
    assert "with chart_col:" not in s


def test_integer_persistence_source_is_explicitly_hardened_in_model_contract():
    s = (ROOT / "models.py").read_text(encoding="utf-8")
    assert "age" in s and "birth_year" in s
    assert "Integer" in s
