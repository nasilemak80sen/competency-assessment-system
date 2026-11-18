"""UI contract checks for the directory-first personnel administration page."""
import ast
from pathlib import Path


PAGE_PATH = Path(__file__).resolve().parents[1] / "v2" / "pages" / "07_Admin.py"
SOURCE = PAGE_PATH.read_text(encoding="utf-8")


def test_personnel_admin_page_is_valid_python():
    ast.parse(SOURCE)


def test_directory_and_add_workflow_are_available_without_existing_people():
    assert 'directory_tab, add_tab, edit_tab' in SOURCE
    assert 'with directory_tab:' in SOURCE
    assert 'with add_tab:' in SOURCE
    assert 'with edit_tab:' in SOURCE
    assert 'edit_id = st.session_state.get("admin_selected_person_id")' in SOURCE
    assert "admin_edit_person_picker" not in SOURCE
    assert 'There are no active database records to edit yet.' in SOURCE
    assert 'Use Add Personnel to create the first record.' in SOURCE
    assert 'if active_people.empty: st.stop()' not in SOURCE


def test_directory_supports_search_filters_and_single_row_selection():
    assert 'Search personnel' in SOURCE
    assert 'Department' in SOURCE
    assert 'Employment' in SOURCE
    assert 'Salary grade' in SOURCE
    assert 'on_select="rerun"' in SOURCE
    assert 'selection_mode="single-row"' in SOURCE


def test_blank_personnel_dates_stay_blank_in_create_and_edit_forms():
    assert 'def _optional_date(value)' in SOURCE
    assert 'return None if pd.isna(parsed) else parsed.date()' in SOURCE
    assert 'value=_optional_date(source.get("Joining Date"))' in SOURCE
    assert 'value=_optional_date(source.get("Contract Expire Date"))' in SOURCE
    assert 'value=_optional_date(source.get("Chat Date"))' in SOURCE
    assert "def _first_optional_date(*values)" in SOURCE
    assert 'value=date.today()' in SOURCE  # Only the new assessment date is defaulted.


def test_archive_and_restore_use_existing_personnel_service_methods():
    assert 'ok, message = delete_personnel(session, archive_id)' in SOURCE
    assert 'ok, message = update_personnel(' in SOURCE
    assert '"is_deleted": False, "is_active": True' in SOURCE
    assert 'Type the Staff ID to confirm' in SOURCE
    assert 'I confirm this personnel record should be restored.' in SOURCE


def test_existing_service_boundaries_are_used_for_personnel_crud():
    assert 'from services.personnel_service import' in SOURCE
    assert 'add as add_personnel' in SOURCE
    assert 'all as get_all_personnel' in SOURCE
    assert 'delete as delete_personnel' in SOURCE
    assert 'update as update_personnel' in SOURCE
