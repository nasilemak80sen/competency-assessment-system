"""Phase 3 import reconciliation and Phase 4 user-access audit tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import AuditLog, Base, Personnel
from v2.services.import_service import (
    build_personnel_import_preview,
    build_cv_import_preview,
    resolve_personnel_import,
    resolve_cv_import,
)
from v2.services import auth_service, personnel_service
from v2.services.assessment_service import save_assessment_transaction


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    return engine, session


def test_personnel_preview_reports_field_differences_and_source_duplicates():
    engine, session = _session()
    try:
        session.add(
            Personnel(
                staff_id="100",
                name="A Person",
                department="DPE",
                email="a@example.test",
                is_deleted=False,
                is_active=True,
            )
        )
        session.commit()
        source = pd.DataFrame(
            [
                {"Name": "A Person", "Staff ID": "100", "Department": "PSR", "Email Address": "a@example.test"},
                {"Name": "New Person", "Staff ID": "200", "Department": "DPE"},
                {"Name": "Duplicate New Person", "Staff ID": "200", "Department": "DPE"},
                {"Name": "Other New Person", "Staff ID": "300", "Department": "DPE"},
            ]
        )

        preview = build_personnel_import_preview(session, source)
        plan = preview["plan"].set_index("Source index")

        assert preview["counts"]["source_rows"] == 4
        assert preview["counts"]["duplicate_rows"] == 2
        assert plan.loc[0, "Action"] == "Update"
        assert plan.loc[0, "Match Staff ID"] == "100"
        assert plan.loc[0, "Include"] is True or bool(plan.loc[0, "Include"])
        assert not bool(plan.loc[1, "Include"])
        assert not bool(plan.loc[2, "Include"])
        assert plan.loc[3, "Action"] == "Add"
        assert "Department" in preview["field_differences"]["Field"].tolist()
    finally:
        session.close()
        engine.dispose()


def test_personnel_resolution_requires_one_row_per_duplicate_staff_id():
    engine, session = _session()
    try:
        session.add(
            Personnel(
                staff_id="100",
                name="A Person",
                department="DPE",
                is_deleted=False,
                is_active=True,
            )
        )
        session.commit()
        source = pd.DataFrame(
            [
                {"Name": "A Person", "Staff ID": "100", "Department": "PSR"},
                {"Name": "New One", "Staff ID": "200", "Department": "DPE"},
                {"Name": "New Two", "Staff ID": "200", "Department": "DPE"},
                {"Name": "New Three", "Staff ID": "300", "Department": "DPE"},
            ]
        )
        preview = build_personnel_import_preview(session, source)
        plan = preview["plan"].copy()
        plan.loc[1, "Include"] = True
        plan.loc[2, "Include"] = True

        _, errors, _ = resolve_personnel_import(
            source,
            plan,
            active_people=preview["active_people"],
            all_staff_ids=preview["all_staff_ids"],
        )
        assert any("Select only one source row" in error for error in errors)

        plan.loc[2, "Include"] = False
        result, errors, decisions = resolve_personnel_import(
            source,
            plan,
            active_people=preview["active_people"],
            all_staff_ids=preview["all_staff_ids"],
        )
        assert errors == []
        assert len(result) == 3
        assert decisions[0]["action"] == "update"
        assert decisions[1]["action"] == "add"
        assert decisions[3]["action"] == "add"
    finally:
        session.close()
        engine.dispose()


def test_shared_uptrex_placeholder_is_not_treated_as_a_duplicate_staff_id():
    engine, session = _session()
    try:
        session.add(
            Personnel(
                staff_id="UPTREX",
                name="Existing Placeholder Person",
                is_deleted=False,
                is_active=True,
            )
        )
        session.commit()
        source = pd.DataFrame(
            [
                {"Name": "Existing Placeholder Person", "Staff ID": "UPTREX"},
                {"Name": "Another UPTREX Trainee", "Staff ID": "UPTREX"},
            ]
        )
        preview = build_personnel_import_preview(session, source)
        plan = preview["plan"]

        assert preview["counts"]["duplicate_rows"] == 0
        assert plan.iloc[0]["Action"] == "Update"
        assert plan.iloc[1]["Action"] == "Add"
        assert "Legacy shared placeholder" in plan.iloc[1]["Match method"]

        result, errors, decisions = resolve_personnel_import(
            source,
            plan,
            active_people=preview["active_people"],
            all_staff_ids=preview["all_staff_ids"],
        )
        assert errors == []
        assert len(result) == 2
        assert list(result.index) == [0, 1]
        assert decisions[0]["action"] == "update"
        assert decisions[1]["action"] == "add"
    finally:
        session.close()
        engine.dispose()


def test_numeric_staff_id_float_suffix_is_normalized_before_add():
    engine, session = _session()
    try:
        source = pd.DataFrame([{"Name": "Numeric ID Person", "Staff ID": 902.0}])
        preview = build_personnel_import_preview(session, source)
        result, errors, decisions = resolve_personnel_import(
            source,
            preview["plan"],
            active_people=preview["active_people"],
            all_staff_ids=preview["all_staff_ids"],
        )
        assert errors == []
        assert result.iloc[0]["Staff ID"] == "902"
        assert decisions[0]["action"] == "add"
    finally:
        session.close()
        engine.dispose()


def test_archived_staff_id_cannot_be_reimported_as_a_new_personnel_record():
    engine, session = _session()
    try:
        session.add(
            Personnel(
                staff_id="ARCH-1",
                name="Archived Person",
                is_deleted=True,
                is_active=False,
            )
        )
        session.commit()
        source = pd.DataFrame([{"Name": "Archived Person", "Staff ID": "ARCH-1"}])
        preview = build_personnel_import_preview(session, source)
        plan = preview["plan"].copy()
        plan.loc[0, "Include"] = True
        plan.loc[0, "Action"] = "Add"

        result, errors, _ = resolve_personnel_import(
            source,
            plan,
            active_people=preview["active_people"],
            all_staff_ids=preview["all_staff_ids"],
        )
        assert result.empty
        assert any("active or archived database record" in error for error in errors)
    finally:
        session.close()
        engine.dispose()


def test_database_import_updates_name_by_real_staff_id_and_keeps_uptrex_placeholder_rule():
    engine, session = _session()
    try:
        real_person = Personnel(
            staff_id="REAL-1",
            name="Old Name",
            department="DPE",
            is_deleted=False,
            is_active=True,
        )
        placeholder = Personnel(
            staff_id="UPTREX",
            name="Existing Placeholder Person",
            is_deleted=False,
            is_active=True,
        )
        session.add_all([real_person, placeholder])
        session.commit()
        original_id = real_person.id

        import db_ops
        source = pd.DataFrame(
            [
                {"Name": "Updated Real Name", "Staff ID": "REAL-1", "Department": "PSR"},
                {"Name": "Another UPTREX Trainee", "Staff ID": "UPTREX", "Department": "DPE"},
            ],
            index=[0, 1],
        )
        result = db_ops.bulk_import_from_df(session, source)

        updated_real = session.query(Personnel).filter_by(staff_id="REAL-1").one()
        added_uptrex = session.query(Personnel).filter_by(staff_id="UPTREX-1").one()
        assert updated_real.id == original_id
        assert updated_real.name == "Updated Real Name"
        assert added_uptrex.name == "Another UPTREX Trainee"
        assert result["updated"] == 1
        assert result["added"] == 1
        assert result["errors"] == 0
    finally:
        session.close()
        engine.dispose()


def test_cv_matching_suggests_unique_matches_and_requires_manual_ambiguous_resolution():
    engine, session = _session()
    try:
        session.add_all(
            [
                Personnel(staff_id="T-1", name="Taylor Person", is_deleted=False, is_active=True),
                Personnel(staff_id="T-2", name="Taylor Person", is_deleted=False, is_active=True),
                Personnel(staff_id="U-1", name="Unique Person", is_deleted=False, is_active=True),
            ]
        )
        session.commit()
        cv_source = pd.DataFrame(
            [
                {"Name": "Unique Person", "Staff ID": "", "CV File Name": "unique.pdf"},
                {"Name": "Taylor Person", "Staff ID": "", "CV File Name": "taylor.pdf"},
            ]
        )

        preview = build_cv_import_preview(session, cv_source)
        assert preview["auto_matches"] == {0: "U-1"}
        assert len(preview["unmatched"]) == 1

        resolved, errors, summary = resolve_cv_import(
            cv_source, preview, {1: "T-2"}
        )
        assert errors == []
        assert len(resolved) == 2
        assert resolved.iloc[0]["Staff ID"] == "U-1"
        assert resolved.iloc[1]["Staff ID"] == "T-2"
        assert summary["manual_resolutions"] == 1
    finally:
        session.close()
        engine.dispose()


def test_user_management_audit_records_real_admin_and_never_password_material(monkeypatch, tmp_path):
    db_path = tmp_path / "phase34_auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    auth_service.ensure_auth_table()

    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE personnel (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                staff_id TEXT NOT NULL,
                department TEXT,
                is_deleted INTEGER DEFAULT 0
            )"""
        )
        conn.executemany(
            "INSERT INTO personnel (id, name, staff_id, department, is_deleted) VALUES (?, ?, ?, ?, 0)",
            [(41, "Person One", "P-41", "DPE"), (42, "Person Two", "P-42", "PSR"), (78, "Person Three", "P-78", "DPE")],
        )

    ok, message, admin_id = auth_service.create_user(
        "admin.one", "AdminPassword123!", auth_service.ROLE_ADMIN,
        display_name="Administrator One",
    )
    assert ok, message
    actor = {"id": admin_id, "username": "admin.one", "display_name": "Administrator One"}

    ok, message, user_id = auth_service.create_user(
        "person.one", "InitialPassword123!", auth_service.ROLE_USER,
        personnel_id=41, display_name="Person One",
        actor=actor,
    )
    assert ok, message
    ok, message = auth_service.update_user_access(user_id, auth_service.ROLE_USER, 42, actor=actor)
    assert ok, message
    ok, message = auth_service.set_active(user_id, False, actor=actor)
    assert ok, message
    ok, message = auth_service.reset_password(user_id, "NewPassword123!", actor=actor)
    assert ok, message

    users = auth_service.list_users("P-42")
    assert len(users) == 1
    assert users[0]["username"] == "person.one"
    assert users[0]["personnel_name"] == "Person Two"
    assert users[0]["personnel_staff_id"] == "P-42"

    audit = auth_service.list_auth_audit("admin.one", limit=20)
    assert {row["action"] for row in audit} >= {
        "USER_CREATED", "USER_ACCESS_UPDATED", "USER_DISABLED", "PASSWORD_RESET"
    }
    # The root administrator's own creation event is system-provisioned.
    # All subsequent changes targeting the colleague must identify the actor.
    attributed = [row for row in audit if row["target_username"] == "person.one"]
    assert len(attributed) == 4
    assert all(row["actor_user_id"] == admin_id for row in attributed)
    assert all(row["actor_username"] == "admin.one" for row in attributed)
    assert all("NewPassword123!" not in str(row["details"]) for row in audit)


def test_user_accounts_cannot_be_created_or_reenabled_with_archived_personnel(monkeypatch, tmp_path):
    db_path = tmp_path / "phase34_archived_link.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    auth_service.ensure_auth_table()

    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE personnel (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                staff_id TEXT NOT NULL,
                department TEXT,
                is_deleted INTEGER DEFAULT 0
            )"""
        )
        conn.executemany(
            "INSERT INTO personnel (id, name, staff_id, department, is_deleted) VALUES (?, ?, ?, ?, ?)",
            [
                (91, "Active Person", "P-91", "DPE", 0),
                (92, "Archived Person", "P-92", "DPE", 1),
            ],
        )

    archived_create = auth_service.create_user(
        "archived.user", "InitialPassword123!", auth_service.ROLE_USER,
        personnel_id=92,
    )
    assert archived_create[0] is False
    assert "non-archived personnel" in archived_create[1]

    created = auth_service.create_user(
        "active.user", "InitialPassword123!", auth_service.ROLE_USER,
        personnel_id=91,
    )
    assert created[0] is True
    user_id = created[2]
    assert auth_service.set_active(user_id, False)[0] is True

    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE personnel SET is_deleted = 1 WHERE id = 91")

    enabled, message = auth_service.set_active(user_id, True)
    assert enabled is False
    assert "missing or archived personnel" in message


def test_duplicate_personnel_link_and_last_admin_lockout_are_prevented(monkeypatch, tmp_path):
    db_path = tmp_path / "phase34_security.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    auth_service.ensure_auth_table()
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE personnel (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                staff_id TEXT NOT NULL,
                department TEXT,
                is_deleted INTEGER DEFAULT 0
            )"""
        )
        conn.executemany(
            "INSERT INTO personnel (id, name, staff_id, department, is_deleted) VALUES (?, ?, ?, ?, 0)",
            [(77, "Linked Person", "P-77", "DPE"), (78, "Another Person", "P-78", "PSR")],
        )

    ok, message, admin_id = auth_service.create_user(
        "only.admin", "AdminPassword123!", auth_service.ROLE_ADMIN
    )
    assert ok, message
    actor = {"id": admin_id, "username": "only.admin", "display_name": "Only Admin"}

    first = auth_service.create_user(
        "first.user", "InitialPassword123!", auth_service.ROLE_USER, personnel_id=77
    )
    assert first[0] is True
    duplicate = auth_service.create_user(
        "second.user", "InitialPassword123!", auth_service.ROLE_USER, personnel_id=77
    )
    assert duplicate[0] is False
    assert "already linked" in duplicate[1]

    disable_ok, disable_message = auth_service.set_active(admin_id, False, actor=None)
    assert disable_ok is False
    assert "last active administrator" in disable_message.lower()
    demote_ok, demote_message = auth_service.update_user_access(
        admin_id, auth_service.ROLE_USER, 78, actor=None
    )
    assert demote_ok is False
    assert "last active administrator" in demote_message.lower()


def test_personnel_crud_audit_uses_the_signed_in_administrator():
    engine, session = _session()
    try:
        ok, message, personnel_id = personnel_service.add(
            session,
            {"staff_id": "AUDIT-1", "name": "Audited Person"},
            changed_by="admin.audit",
        )
        assert ok, message

        ok, message = personnel_service.update(
            session, personnel_id, {"department": "DPE"},
            changed_by="admin.audit",
        )
        assert ok, message
        ok, message = personnel_service.delete(
            session, personnel_id, changed_by="admin.audit"
        )
        assert ok, message

        entries = (
            session.query(AuditLog)
            .filter_by(entity_type="Personnel", entity_id=personnel_id)
            .order_by(AuditLog.id.asc())
            .all()
        )
        assert [entry.action for entry in entries] == ["CREATE", "UPDATE", "DELETE"]
        assert all(entry.changed_by == "admin.audit" for entry in entries)
    finally:
        session.close()
        engine.dispose()


def test_assessment_audit_records_authenticated_administrator_in_the_save_transaction():
    engine, session = _session()
    try:
        person = Personnel(
            staff_id="ASSESS-AUDIT-1",
            name="Assessment Audit Person",
            is_deleted=False,
            is_active=True,
        )
        session.add(person)
        session.commit()
        from config import SCORE_COLS
        scores = {code: {"actual": 3.0, "req": 4.0} for code in SCORE_COLS}
        ok, message, assessment_id = save_assessment_transaction(
            session,
            person.id,
            {
                "assessment_date": pd.Timestamp("2026-11-18").date(),
                "assessment_level": "Staff",
            },
            scores,
            actor={
                "id": 4,
                "username": "admin.audit",
                "display_name": "Audit Administrator",
            },
        )
        assert ok, message
        audit = (
            session.query(AuditLog)
            .filter_by(entity_type="Assessment", entity_id=assessment_id)
            .one()
        )
        assert audit.action == "CREATE"
        assert audit.changed_by == "admin.audit"
        assert '"score_count": 24' in audit.new_values
    finally:
        session.close()
        engine.dispose()


def test_admin_pages_expose_reconciliation_search_and_audit_controls():
    root = Path(__file__).resolve().parents[1]
    import_page = (root / "v2/pages/08_Admin_Import_Data.py").read_text(encoding="utf-8")
    user_page = (root / "v2/pages/09_Admin_User_Access.py").read_text(encoding="utf-8")

    for label in [
        "Run Dry Run", "Commit Reviewed Import", "Field-level comparison",
        "Duplicate source Staff IDs", "CV rows are never attached automatically",
        '"personnel_plan": personnel_preview["plan"].to_dict(orient="records")',
        '"personnel_field_differences": differences.to_dict(orient="records")',
    ]:
        assert label.casefold() in import_page.casefold()
    for token in [
        "Searchable user directory", "Search accounts", "Save role and personnel link",
        "Administrator activity log", "list_auth_audit", "actor=user",
        "Personnel and assessment changes", "_load_personnel_assessment_audit",
    ]:
        assert token in user_page
