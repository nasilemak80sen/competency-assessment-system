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
