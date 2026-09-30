from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_user_dashboard_uses_db_personnel_id_then_staff_id_join():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert "session.query(Personnel)" in source
    assert "Personnel.id == linked_id" in source
    assert '"Staff ID" not in df.columns' in source
    assert 'df["Staff ID"].astype(str).str.strip() == staff_id' in source
    assert 'df["id"]' not in source


def test_user_assessment_uses_db_personnel_id_then_staff_id_join():
    source = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")
    assert "session.query(Personnel)" in source
    assert "Personnel.id == linked_id" in source
    assert '"Staff ID" not in df.columns' in source
    assert 'df["Staff ID"].astype(str).str.strip() == staff_id' in source
    assert 'df["id"]' not in source


def test_user_assessment_is_scoped_and_reuses_shared_readiness_features():
    source = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")

    assert "get_ruler_data" in source
    assert "_rg_get_person_ruler" in source
    assert "_rg_determine_target_sg" in source
    assert "build_target_gap_dataframe" in source
    assert "calculate_readiness_metrics" in source
    assert 'key="user_target_ruler"' in source
    assert 'key="user_target_mode"' in source

    assert "render_actual_target_charts(gap_df)" in source
    assert "classify_readiness_status" in source
    assert "recommend_readiness_action" in source
    assert '"Target Coverage"' in source

    assert "Priority Development Areas" in source
    assert "Competency Strengths" in source
    assert "My Assessment History" in source
    assert "Existing Assessment Summary Scores" in source
    assert "Assessment Feedback & Remarks" in source

    assert "Select Personnel" not in source
    assert "CVDocument" not in source
    assert "create_user(" not in source
    assert "reset_password(" not in source
    assert "set_active(" not in source


def test_user_dashboard_keeps_workbook_as_authority_for_controlled_fields():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert 'def _controlled_value(workbook_value, db_value=None' in source
    assert 'assessment_level = _controlled_value(person.get("Assessment Level")' in source
    assert 'potential = _controlled_value(person.get("Potential")' in source
    assert 'recommendation = _controlled_value(person.get("Recommendation")' in source
    assert 'supervisor = _controlled_value(person.get("Supervisor")' in source


def test_user_dashboard_provides_read_only_personal_documents():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert "from models import CVDocument, Personnel" in source
    assert "CVDocument.personnel_id == linked_id" in source
    assert '"📄 My Documents"' in source
    assert "Open Latest Document in SharePoint" in source


def test_user_assessment_provides_personal_report_exports():
    source = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")
    assert "def _personal_pdf(" in source
    assert "Download My Assessment Report (PDF)" in source
    assert "Download My Competency Scorecard (CSV)" in source


def test_user_assessment_keeps_controlled_context_workbook_first():
    source = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")
    assert 'def _controlled_value(workbook_value, db_value=None' in source
    assert 'assessment_level = _controlled_value(person.get("Assessment Level")' in source
    assert 'potential = _controlled_value(person.get("Potential")' in source
    assert 'supervisor = _controlled_value(person.get("Supervisor")' in source


def test_user_dashboard_has_profile_parity_and_shared_visuals():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert '"Age": person.get("Age")' in source
    assert 'person.get("Background") or person.get("Sub-Disciplines")' in source
    assert "render_actual_target_charts(score_df)" in source
    assert "missing_profile_fields" in source
    assert "Profile Completeness" in source


def test_user_dashboard_reconciles_assessment_date_from_db_and_workbook():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert "db_assessment_dates" in source
    assert "person_db.assessments" in source
    assert "metadata_last_assessment" in source
    assert "last_assessment = max(assessment_dates)" in source


def test_user_dashboard_uses_compatible_form_submit_button_api():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assert 'st.form_submit_button("💾 Save Profile", type="primary")' in source
    assert 'st.form_submit_button("💾 Save Profile", type="primary", width=' not in source


def test_user_pages_do_not_expose_cross_personnel_selection_or_admin_controls():
    dashboard = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")
    assessment = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")
    for source in (dashboard, assessment):
        assert "Select Personnel" not in source
        assert "create_user(" not in source
        assert "reset_password(" not in source
        assert "set_active(" not in source
