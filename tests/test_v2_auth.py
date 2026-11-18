from __future__ import annotations

from pathlib import Path

from v2.services import auth_service



def test_password_hash_round_trip():
    encoded = auth_service.hash_password("DemoPass123")
    assert encoded.startswith("scrypt$")
    assert auth_service.verify_password("DemoPass123", encoded)
    assert not auth_service.verify_password("WrongPass123", encoded)


def test_auth_service_creates_and_authenticates_user(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)

    auth_service.ensure_auth_table()
    ok, message, user_id = auth_service.create_user(
        "person@example.test",
        "DemoPass123",
        auth_service.ROLE_USER,
        personnel_id=42,
        display_name="Demo Person",
    )
    assert ok, message
    assert user_id is not None

    user = auth_service.authenticate("PERSON@example.test", "DemoPass123")
    assert user is not None
    assert user["role"] == auth_service.ROLE_USER
    assert user["personnel_id"] == 42


def test_duplicate_user_is_rejected(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    auth_service.ensure_auth_table()

    first = auth_service.create_user("admin", "DemoPass123", auth_service.ROLE_ADMIN)
    second = auth_service.create_user("admin", "DemoPass456", auth_service.ROLE_ADMIN)
    assert first[0] is True
    assert second[0] is False


def test_user_account_requires_personnel_link(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    auth_service.ensure_auth_table()

    ok, message, _ = auth_service.create_user("orphan", "DemoPass123", auth_service.ROLE_USER)
    assert ok is False
    assert "linked to a personnel" in message


def test_admin_user_access_uses_database_personnel_ids():
    page_source = Path("v2/pages/09_Admin_User_Access.py").read_text(encoding="utf-8")

    # USER linkage must use the SQLAlchemy Personnel table because the master
    # workbook does not contain the database primary-key ``id`` field.
    assert "from models import AuditLog, Personnel" in page_source
    assert "session.query(Personnel)" in page_source
    assert "Personnel.is_deleted.is_(False)" in page_source
    assert "int(person.id)" in page_source
    assert "get_master_data" not in page_source


def test_app_and_navigation_define_two_role_surfaces():
    app_source = Path("v2/app.py").read_text(encoding="utf-8")
    pages_source = Path("v2/core/pages.py").read_text(encoding="utf-8")
    nav_source = Path("v2/components/navigation.py").read_text(encoding="utf-8")

    assert "USER_PAGES" in app_source
    assert "PAGES if is_admin() else USER_PAGES" in app_source
    assert "My Dashboard" in pages_source
    assert "My Assessment" in pages_source
    assert "USER_NAV" in nav_source
    assert "ADMIN_NAV" in nav_source


def test_configured_admin_bootstrap_repairs_existing_inactive_account(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("admin", "ConfiguredPass123", "System Administrator"),
    )

    auth_service.ensure_auth_table()
    ok, message, admin_id = auth_service.create_user(
        "admin", "OldPassword123", auth_service.ROLE_USER,
        personnel_id=42, display_name="Stale account",
    )
    assert ok, message
    assert admin_id is not None
    assert auth_service.set_active(admin_id, False)[0]

    # The app must repair the configured administrator even though other users
    # or stale rows already exist in app_users.
    ok, message, _ = auth_service.create_user(
        "colleague", "ColleaguePass123", auth_service.ROLE_USER,
        personnel_id=43, display_name="Colleague",
    )
    assert ok, message

    assert auth_service.bootstrap_admin_from_environment() is True
    admin = auth_service.authenticate("ADMIN", "ConfiguredPass123")
    assert admin is not None
    assert admin["role"] == auth_service.ROLE_ADMIN
    assert admin["display_name"] == "System Administrator"
    assert admin["is_active"] == 1
    assert auth_service.authenticate("admin", "OldPassword123") is None
    assert auth_service.authenticate("colleague", "ColleaguePass123") is not None


def test_configured_admin_bootstrap_does_not_reset_password_on_each_rerun(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("admin", "ConfiguredPass123", "System Administrator"),
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    admin = auth_service.authenticate("admin", "ConfiguredPass123")
    assert admin is not None

    ok, message = auth_service.reset_password(admin["id"], "ManualResetPass123")
    assert ok, message

    # The configured secret has not changed, so an intentional admin reset
    # must survive subsequent Streamlit reruns.
    assert auth_service.bootstrap_admin_from_environment() is False
    assert auth_service.authenticate("admin", "ManualResetPass123") is not None
    assert auth_service.authenticate("admin", "ConfiguredPass123") is None


def test_configured_admin_secret_rotation_is_applied_once(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    credentials = {"password": "ConfiguredPass123"}
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("admin", credentials["password"], "System Administrator"),
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    credentials["password"] = "RotatedPass456"
    assert auth_service.bootstrap_admin_from_environment() is True
    assert auth_service.authenticate("admin", "RotatedPass456") is not None
    assert auth_service.authenticate("admin", "ConfiguredPass123") is None
    assert auth_service.bootstrap_admin_from_environment() is False


def test_relt2026_is_bootstrapped_as_admin_from_private_streamlit_secrets(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("RELT2026", "TestOnlySecret_934!", "RELT Administrator"),
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    admin = auth_service.authenticate("relt2026", "TestOnlySecret_934!")
    assert admin is not None
    assert admin["username"] == "relt2026"
    assert admin["role"] == auth_service.ROLE_ADMIN
    assert admin["personnel_id"] is None
    assert auth_service.bootstrap_admin_from_environment() is False

    # The database stores only the one-way scrypt verifier, not the password.
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        encoded = conn.execute(
            "SELECT password_hash FROM app_users WHERE username = ?",
            ("relt2026",),
        ).fetchone()[0]
    assert encoded.startswith("scrypt$")
    assert encoded != "TestOnlySecret_934!"


def test_private_streamlit_admin_template_is_gitignored():
    template = Path(".streamlit/secrets.toml.example").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8-sig")

    assert 'username = "RELT2026"' in template
    assert 'display_name = "RELT Administrator"' in template
    assert 'password = "SET_ADMIN_PASSWORD_PRIVATELY"' in template
    assert 'password = "SET_RELT_PASSWORD_PRIVATELY"' in template
    assert ".streamlit/secrets.toml" in gitignore
    assert "SET_THIS_PRIVATELY" not in gitignore


def test_multiple_named_admin_accounts_are_bootstrapped_independently(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth-multi-admin.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials_list",
        lambda: [
            ("admin", "SystemSecret_123!", "System Administrator"),
            ("RELT2026", "ReltSecret_456!", "RELT Administrator"),
        ],
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    system_admin = auth_service.authenticate("ADMIN", "SystemSecret_123!")
    relt_admin = auth_service.authenticate("relt2026", "ReltSecret_456!")

    assert system_admin is not None
    assert system_admin["role"] == auth_service.ROLE_ADMIN
    assert system_admin["display_name"] == "System Administrator"
    assert relt_admin is not None
    assert relt_admin["role"] == auth_service.ROLE_ADMIN
    assert relt_admin["display_name"] == "RELT Administrator"

    # A second bootstrap run must leave both passwords unchanged.
    assert auth_service.bootstrap_admin_from_environment() is False
    assert auth_service.authenticate("admin", "SystemSecret_123!") is not None
    assert auth_service.authenticate("RELT2026", "ReltSecret_456!") is not None


def test_rotating_one_named_admin_does_not_reset_another(monkeypatch, tmp_path: Path):
    db_path = tmp_path / "auth-multi-admin-rotation.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", db_path)
    credentials = [
        ("admin", "SystemSecret_123!", "System Administrator"),
        ("RELT2026", "ReltSecret_456!", "RELT Administrator"),
    ]
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials_list",
        lambda: list(credentials),
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    users = {row["username"]: row for row in auth_service.list_users()}
    ok, message = auth_service.reset_password(users["admin"]["id"], "AdminManual_789!")
    assert ok, message

    credentials[1] = ("RELT2026", "ReltSecret_Rotated!", "RELT Administrator")
    assert auth_service.bootstrap_admin_from_environment() is True

    assert auth_service.authenticate("admin", "AdminManual_789!") is not None
    assert auth_service.authenticate("admin", "SystemSecret_123!") is None
    assert auth_service.authenticate("RELT2026", "ReltSecret_Rotated!") is not None
    assert auth_service.authenticate("RELT2026", "ReltSecret_456!") is None


def test_multiple_admin_secrets_example_uses_distinct_toml_tables():
    example = Path(".streamlit/secrets.toml.example").read_text(encoding="utf-8")
    assert "[admins.system]" in example
    assert "[admins.relt2026]" in example
    assert sum(line.strip().startswith("[admins.") for line in example.splitlines()) == 2


def test_named_admin_table_parser_extracts_multiple_accounts():
    configured = {
        "system": {
            "username": "admin",
            "password": "SystemSecret_123!",
            "display_name": "System Administrator",
        },
        "relt2026": {
            "username": "RELT2026",
            "password": "ReltSecret_456!",
            "display_name": "RELT Administrator",
        },
    }

    assert auth_service._admin_credentials_from_mapping(configured) == [
        ("admin", "SystemSecret_123!", "System Administrator"),
        ("RELT2026", "ReltSecret_456!", "RELT Administrator"),
    ]


def test_admin_secrets_example_is_valid_toml():
    import tomllib

    example = Path(".streamlit/secrets.toml.example").read_text(encoding="utf-8")
    parsed = tomllib.loads(example)

    assert parsed["admins"]["system"]["username"] == "admin"
    assert parsed["admins"]["relt2026"]["username"] == "RELT2026"
    assert parsed["admins"]["system"]["display_name"] == "System Administrator"
    assert parsed["admins"]["relt2026"]["display_name"] == "RELT Administrator"
