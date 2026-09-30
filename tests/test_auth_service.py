import auth_service


def test_bootstrap_admin_from_environment_fallback(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(auth_service, "_streamlit_admin_credentials", lambda: ("", "", ""))
    monkeypatch.setenv("POC_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("POC_ADMIN_PASSWORD", "StrongTestPassword123!")
    monkeypatch.setenv("POC_ADMIN_DISPLAY_NAME", "Test Administrator")

    assert auth_service.bootstrap_admin_from_environment() is True

    users = auth_service.list_users()
    assert len(users) == 1
    assert users[0]["username"] == "admin"
    assert users[0]["role"] == auth_service.ROLE_ADMIN
    assert auth_service.authenticate("admin", "StrongTestPassword123!") is not None


def test_bootstrap_is_one_time(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("admin", "StrongTestPassword123!", "Administrator"),
    )

    assert auth_service.bootstrap_admin_from_environment() is True
    assert auth_service.bootstrap_admin_from_environment() is False
    assert len(auth_service.list_users()) == 1


def test_streamlit_secret_credentials_are_preferred(monkeypatch, tmp_path):
    db_path = tmp_path / "auth.db"
    monkeypatch.setattr(auth_service, "DATABASE_PATH", str(db_path))
    monkeypatch.setattr(
        auth_service,
        "_streamlit_admin_credentials",
        lambda: ("cloudadmin", "CloudStrongPassword123!", "Cloud Administrator"),
    )
    monkeypatch.setenv("POC_ADMIN_USERNAME", "legacy-admin")
    monkeypatch.setenv("POC_ADMIN_PASSWORD", "LegacyStrongPassword123!")

    assert auth_service.bootstrap_admin_from_environment() is True

    users = auth_service.list_users()
    assert users[0]["username"] == "cloudadmin"
    assert auth_service.authenticate("cloudadmin", "CloudStrongPassword123!") is not None
    assert auth_service.authenticate("legacy-admin", "LegacyStrongPassword123!") is None
