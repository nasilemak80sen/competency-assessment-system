from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shared_actual_target_chart_uses_requested_palette_and_trace_types():
    source = (ROOT / "v2/components/competency_charts.py").read_text(encoding="utf-8")

    assert 'ACTUAL_COLOR = "#00A651"' in source
    assert 'TARGET_COLOR = "#D62728"' in source
    assert "go.Bar(" in source
    assert 'name="Actual"' in source
    assert "marker_color=ACTUAL_COLOR" in source
    assert "go.Scatter(" in source
    assert 'name="Target"' in source
    assert 'mode="lines+markers"' in source
    assert 'line={"color": TARGET_COLOR' in source
    assert "go.Scatterpolar(" in source
    assert 'line={"color": ACTUAL_COLOR' in source
    assert 'line={"color": TARGET_COLOR' in source


def test_admin_individual_assessment_uses_shared_actual_target_chart_component():
    source = (ROOT / "v2/pages/05_Individual_Assessment_Golden.py").read_text(encoding="utf-8")

    assert "from components.competency_charts import render_actual_target_charts" in source
    assert "render_actual_target_charts(gap)" in source
    assert 'go.Bar(x=gap["Competency"], y=gap["Target"], name="Target")' not in source
    assert 'go.Bar(x=gap["Competency"], y=gap["Actual"], name="Actual")' not in source


def test_user_assessment_uses_shared_actual_target_chart_component():
    source = (ROOT / "v2/pages/11_User_Assessment.py").read_text(encoding="utf-8")

    assert "from components.competency_charts import render_actual_target_charts" in source
    assert "render_actual_target_charts(assessment_df)" in source


def test_user_dashboard_exposes_self_service_profile_edit_without_org_control_fields():
    source = (ROOT / "v2/pages/10_User_Dashboard.py").read_text(encoding="utf-8")

    assert 'st.tabs(["👤 My Profile", "✏️ Edit Profile"])' in source
    assert 'st.form("user_edit_profile_form")' in source
    assert 'from db_ops import update_personnel' in source
    assert '"email": email.strip() or None' in source
    assert '"gender": gender.strip() or None' in source
    assert '"nationality": nationality.strip() or None' in source
    assert '"current_assignment": current_assignment.strip() or None' in source
    assert '"interest": interest.strip() or None' in source
    assert '"preference": preference.strip() or None' in source
    assert '"strength": strength.strip() or None' in source

    edit_block_start = source.index('payload = {')
    edit_block_end = source.index('}', edit_block_start) + 1
    payload = source[edit_block_start:edit_block_end]
    for forbidden in [
        '"staff_id"',
        '"sg"',
        '"department"',
        '"staff_position"',
        '"assessment_level"',
        '"last_assessment_date"',
    ]:
        assert forbidden not in payload
