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
