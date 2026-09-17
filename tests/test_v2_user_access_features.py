from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "v2/pages/10_User_Dashboard.py"
ASSESSMENT = ROOT / "v2/pages/11_User_Assessment.py"


def test_user_dashboard_maps_master_email_field_correctly():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert 'person.get("Email Address")' in source
    assert 'person.get("Email")' not in source


def test_user_dashboard_exposes_personal_assessment_metadata_and_gap_summary():
    source = DASHBOARD.read_text(encoding="utf-8")
    for text in [
        "person_db.assessment_level",
        "person_db.last_assessment_date",
        "person_db.chat_status",
        "person_db.potential",
        "person_db.recommendation",
        "person_db.supervisor",
        "Top Development Gaps",
        "Profile Completeness",
        "Actual",
        "Target",
    ]:
        assert text in source


def test_user_dashboard_edit_form_does_not_use_unsupported_width_keyword():
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "st.form_submit_button(\"💾 Save Profile\", type=\"primary\", width=\"stretch\")" not in source


def test_user_assessment_uses_latest_summary_and_metadata_fallbacks():
    source = ASSESSMENT.read_text(encoding="utf-8")
    assert "SummaryScore.updated_at.desc()" in source
    assert "person_db.last_assessment_date" in source
    assert 'person.get("Last Assesment Date")' in source
    assert 'person.get("Last Assessment Date")' in source


def test_user_assessment_includes_self_service_analysis_features():
    source = ASSESSMENT.read_text(encoding="utf-8")
    for text in [
        "Career Target & Readiness",
        "Priority Development Areas",
        "render_actual_target_charts(gap_df)",
        "Competency Strengths",
        "My Assessment History",
        "Existing Assessment Summary Scores",
        "Download My Target Gap Analysis (CSV)",
    ]:
        assert text in source


def test_user_pages_remain_personnel_scoped():
    for path in (DASHBOARD, ASSESSMENT):
        source = path.read_text(encoding="utf-8")
        assert "Personnel.id == linked_id" in source
        assert 'df["Staff ID"].astype(str).str.strip() == staff_id' in source
        assert "Select Personnel" not in source
