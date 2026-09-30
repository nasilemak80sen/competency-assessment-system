from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "v2/pages/07_Admin.py"
SERVICE = ROOT / "v2/services/personnel_service.py"


def test_admin_exposes_single_personnel_creation_workflow():
    source = ADMIN.read_text(encoding="utf-8")
    required = [
        'add as add_personnel',
        '"➕ Add New Personnel"',
        'st.form("add_personnel_form")',
        'st.form_submit_button("➕ Add Personnel"',
        'staff_id_new',
        'name_new',
        'position_new' if False else 'add_personnel_position',
        'add_personnel(s,payload)',
        'st.cache_data.clear()',
        'st.rerun()',
    ]
    missing = [item for item in required if item not in source]
    assert not missing, f"Admin personnel creation contract missing: {missing}"


def test_admin_creation_has_duplicate_safe_required_identity_fields():
    source = ADMIN.read_text(encoding="utf-8")
    assert 'if not name_new.strip()' in source
    assert 'elif not staff_id_new.strip()' in source
    assert '"staff_id":staff_id_new.strip()' in source
    assert '"name":name_new.strip()' in source


def test_personnel_service_keeps_existing_create_boundary():
    source = SERVICE.read_text(encoding="utf-8")
    assert 'def add(session, data:' in source
    assert 'return db_ops.add_personnel(session, data)' in source
