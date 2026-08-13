"""Regression test: role do admin cap nhat phai ton tai qua lan khoi dong backend."""
from backend import auth


def test_regional_director_role_survives_backend_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    auth.init_schema()
    auth.create_user(
        username="giamdoc.mienbac",
        password="temporary-password",
        name="Giam doc Mien Bac",
        role="qlv",
        scope_value="MB",
    )

    assert auth.approve_user("giamdoc.mienbac", "regional_director", "MB")
    assert auth.get_user_by_email_or_username("giamdoc.mienbac")["role"] == "regional_director"

    # backend/main.py goi init_schema() moi lan service start/restart.
    auth.init_schema()

    user = auth.get_user_by_email_or_username("giamdoc.mienbac")
    assert user["role"] == "regional_director"
    assert user["scope_value"] == "MB"


def test_startup_does_not_override_existing_manager_role(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    auth.init_schema()
    auth.create_user(
        username="manager_custom",
        password="temporary-password",
        name="Manager Custom",
        role="qlv",
    )

    auth.init_schema()

    assert auth.get_user_by_email_or_username("manager_custom")["role"] == "qlv"
