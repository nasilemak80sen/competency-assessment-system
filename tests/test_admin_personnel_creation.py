from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADMIN = ROOT / "v2/pages/07_Admin.py"
SERVICE = ROOT / "v2/services/personnel_service.py"


def test_admin_exposes_directory_first_personnel_creation_workflow():
    source = ADMIN.read_text(encoding="utf-8")
    required = [
        "directory_tab, add_tab, edit_tab",
        'with add_tab:',
        'with st.form(form_key, clear_on_submit=False):',
        '"Full name *"',
        '"Staff ID *"',
        '"Create personnel record" if is_add else "Save profile changes"',
        'ok, message, new_id = add_personnel(session, payload)',
        'st.cache_data.clear()',
        'st.session_state["admin_selected_person_id"] = new_id',
        'st.rerun()',
    ]
    missing = [item for item in required if item not in source]
    assert not missing, f"Directory-first personnel creation contract missing: {missing}"


def test_admin_creation_validates_required_identity_and_uses_existing_service():
    source = ADMIN.read_text(encoding="utf-8")
    assert 'if not payload["name"]:' in source
    assert 'elif not payload["staff_id"]:' in source
    assert '"name": name.strip()' in source
    assert '"staff_id": staff_id.strip()' in source
    assert "Add Personnel" in source
    assert "Full name is required." in source
    assert "Staff ID is required." in source


def test_personnel_service_keeps_existing_create_boundary():
    source = SERVICE.read_text(encoding="utf-8")
    assert "def add(session, data:" in source
    assert "return db_ops.add_personnel(session, data)" in source
