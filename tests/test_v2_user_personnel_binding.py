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

    # Self-scoped target/readiness workflow.
    assert "get_ruler_data" in source
    assert "_rg_get_person_ruler" in source
    assert "_rg_determine_target_sg" in source
    assert "build_target_gap_dataframe" in source
    assert "calculate_readiness_metrics" in source
    assert 'key="user_target_ruler"' in source
    assert 'key="user_target_mode"' in source

    # Shared visual language: emerald Actual bars + red Target line/radar.
    assert "render_actual_target_charts(gap_df)" in source

    # Useful personal features replicated from Individual Assessment.
    assert "Priority Development Areas" in source
    assert "Competency Strengths" in source
    assert "My Assessment History" in source
    assert "Existing Assessment Summary Scores" in source

    # USER page must not expose organisation-wide personnel selection or admin controls.
    assert "Select Personnel" not in source
    assert "CVDocument" not in source
    assert "create_user(" not in source
    assert "reset_password(" not in source
    assert "set_active(" not in source
