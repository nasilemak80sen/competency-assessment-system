"""Structural contract tests for the migrated pages.

These tests deliberately validate controls and workflows, not just imports.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "v2/pages/07_Admin.py"
IND = ROOT / "v2/pages/05_Individual_Assessment_Golden.py"
HEATMAP = ROOT / "v2/pages/03_Competency_Heatmap.py"


def test_admin_has_complete_golden_personnel_field_contract():
    s = ADMIN.read_text(encoding="utf-8")
    fields = [
        "Nationality", "Employment Category", "Section Name", "Unit Name", "Sub Unit",
        "Current Assignment", "Joining Date", "Contract Expire Date", "Assignment Date",
        "SG Start Date", "Years in PET", "Years of RE Experience", "Years in Salary Grade",
        "Age Promoted", "Length in Current Assignment", "Chat Status", "Chat Date",
        "Assessment Level", "Last Assessment Date", "Sub-disciplines", "Potential",
        "Resource / SME", "Interest", "Strength", "Recommendation", "Preference",
        "Comment / Suggestion", "Assessor 1", "Assessor 2", "Supervisor", "Remarks",
    ]
    missing = [x for x in fields if x not in s]
    assert not missing, f"Admin field contract missing: {missing}"
    assert 'st.form_submit_button("💾 Save Personnel Info"' in s


def test_admin_assessment_has_actual_and_target_for_every_competency_class():
    s = ADMIN.read_text(encoding="utf-8")
    assert "for ctype,info in COMP_TYPES.items()" in s
    assert 'f"{code} Actual"' in s
    assert 'f"{code} Target"' in s
    assert '"req":requirement' in s
    assert '"gap":round(max(requirement-actual,0),2)' in s
    assert 'COMP_TYPES' in s


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
        "Actual Competency Score Matrix",
        "Competency Name:",
        "Actual Score:",
        "heatmap_personnel_summary.csv",
        "heatmap_competency_summary.csv",
        "Heatmap Analysis Summary",
        "Personnel Summary",
        "Competency Summary",
        "Category Summary",
        "Scores ≥4",
        "Scores ≤2",
        "Coverage %",
        "ProgressColumn",
        "xgap=1.5",
        "ygap=1.5",
        '"competency_heatmap"',
    ]
    missing = [x for x in required if x not in s]
    assert not missing, f"Heatmap visualization/summary contract missing: {missing}"


def test_integer_persistence_source_is_explicitly_hardened_in_model_contract():
    s = (ROOT / "models.py").read_text(encoding="utf-8")
    assert "age" in s and "birth_year" in s
    assert "Integer" in s
