"""Regression tests for fail-closed auth, scope, glossary and session ownership."""
import os
import sys
import importlib.util

import pytest


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import auth
import conversation_memory
import glossary_memory
import nl2sql
import report_templates as rt


def test_startup_does_not_create_fixed_privileged_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    auth.init_schema()

    assert auth.get_user_by_email_or_username("dnh") is None
    assert auth.get_user_by_email_or_username("admin.dnh") is None


def test_admin_ops_cannot_create_or_approve_an_account(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    module_name = "security_hardening_main"
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = chatbot_main
    spec.loader.exec_module(chatbot_main)

    create_request = chatbot_main.AdminCreateUserRequest(
        username="escalated", role="c_level"
    )
    approve_request = chatbot_main.ApproveUserRequest(role="c_level")
    admin_ops = {"role": "admin_ops", "username": "ops"}

    with pytest.raises(chatbot_main.HTTPException) as create_error:
        chatbot_main.create_user_by_admin(create_request, admin_ops)
    with pytest.raises(chatbot_main.HTTPException) as approve_error:
        chatbot_main.approve_user_endpoint("pending-user", approve_request, admin_ops)

    assert create_error.value.status_code == 403
    assert approve_error.value.status_code == 403


def test_password_change_revokes_all_sessions_and_login_rate_limit_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    module_name = "security_password_main"
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = chatbot_main
    spec.loader.exec_module(chatbot_main)

    auth.create_user(
        "password.user", "current-password", name="Password User", role="c_level"
    )
    user = auth.verify_login("password.user", "current-password")
    token_a = auth.create_session(user["id"])
    token_b = auth.create_session(user["id"])

    result = chatbot_main.change_password(
        chatbot_main.ChangePasswordRequest(
            current_password="current-password", new_password="different-password"
        ),
        user,
    )
    assert result["ok"] is True
    assert auth.get_user_by_session(token_a) is None
    assert auth.get_user_by_session(token_b) is None

    chatbot_main._LOGIN_IDENTIFIER_ATTEMPTS.clear()
    chatbot_main._LOGIN_IP_ATTEMPTS.clear()
    for _ in range(chatbot_main.LOGIN_IDENTIFIER_LIMIT):
        chatbot_main._record_login_failure("target", "10.0.0.1")
    with pytest.raises(chatbot_main.HTTPException) as rate_error:
        chatbot_main._check_login_rate_limit("target", "10.0.0.1")
    assert rate_error.value.status_code == 429


def test_admin_ops_reset_password_is_email_only_and_revokes_sessions(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    module_name = "security_admin_reset_main"
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = chatbot_main
    spec.loader.exec_module(chatbot_main)

    auth.create_user(
        "regional.user", "old-password-value", name="Regional User",
        role="regional_director", scope_value="MB",
        email="regional.user@namhapharma.com",
    )
    target = auth.verify_login("regional.user", "old-password-value")
    old_token = auth.create_session(target["id"])
    sent = {}

    def fake_mail(email, password, is_reset=False):
        sent.update(email=email, password=password, is_reset=is_reset)
        return True

    monkeypatch.setattr(chatbot_main, "send_password_email", fake_mail)
    result = chatbot_main.reset_user_password_endpoint(
        "regional.user", {"role": "admin_ops", "username": "admin.dnh"}
    )

    assert result["ok"] is True
    assert result["email_sent"] is True
    assert "temporary_password" not in result
    assert sent["email"] == "regional.user@namhapharma.com"
    assert sent["is_reset"] is True
    assert auth.verify_login("regional.user", "old-password-value").get("error")
    reset_user = auth.verify_login("regional.user", sent["password"])
    assert reset_user["must_change_password"] == 1
    assert auth.get_user_by_session(old_token) is None


def test_admin_ops_reset_failure_preserves_password_and_privileged_targets_are_blocked(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    module_name = "security_admin_reset_failure_main"
    spec = importlib.util.spec_from_file_location(module_name, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = chatbot_main
    spec.loader.exec_module(chatbot_main)

    auth.create_user(
        "qlv.user", "old-password-value", name="QLV User", role="qlv",
        email="qlv.user@namhapharma.com",
    )
    auth.create_user(
        "privileged.user", "privileged-password", name="Privileged User", role="c_level",
    )
    target = auth.verify_login("qlv.user", "old-password-value")
    old_token = auth.create_session(target["id"])
    monkeypatch.setattr(chatbot_main, "send_password_email", lambda *args, **kwargs: False)
    admin_ops = {"role": "admin_ops", "username": "admin.dnh"}

    with pytest.raises(chatbot_main.HTTPException) as mail_error:
        chatbot_main.reset_user_password_endpoint("qlv.user", admin_ops)
    with pytest.raises(chatbot_main.HTTPException) as privileged_error:
        chatbot_main.reset_user_password_endpoint("privileged.user", admin_ops)
    with pytest.raises(chatbot_main.HTTPException) as c_level_error:
        chatbot_main.reset_user_password_endpoint(
            "qlv.user", {"role": "c_level", "username": "dnh"}
        )

    assert mail_error.value.status_code == 502
    assert privileged_error.value.status_code == 403
    assert c_level_error.value.status_code == 403
    assert auth.verify_login("qlv.user", "old-password-value")["username"] == "qlv.user"
    assert auth.get_user_by_session(old_token) is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"role": "tp", "status": "approved"},
        {"role": "regional_director", "status": "approved"},
        {"role": "regional_director", "scope_value": "XX", "status": "approved"},
        {"role": "qlv", "scope_value": "MB", "status": "approved"},
        {"role": "c_level", "scope_value": "MB", "status": "approved"},
    ],
)
def test_account_assignment_rejects_unknown_or_incomplete_scope(kwargs):
    with pytest.raises(ValueError):
        auth.validate_account_assignment(require_complete=True, **kwargs)


def test_temporary_password_flag_survives_reset_until_user_changes_it(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    auth.init_schema()
    auth.create_user("security.user", "initial-password", name="Security User", role="c_level")

    auth.set_password("security.user", "temporary-password", must_change_password=True)
    assert auth.verify_login("security.user", "temporary-password")["must_change_password"] == 1

    auth.set_password("security.user", "new-secure-password")
    assert auth.verify_login("security.user", "new-secure-password")["must_change_password"] == 0


def test_every_template_has_explicit_channel_policy():
    assert set(rt._CHANNEL_SCOPE_POLICIES) == set(rt.TEMPLATES)


def test_channel_scope_filters_advertised_tools_and_unknown_role_gets_none():
    etc_names = {
        tool["name"] for tool in nl2sql._tools_for_request(
            scope_channel="ETC", scope_role="regional_director"
        )
    }
    assert "get_revenue_by_channel" in etc_names
    assert "get_revenue_reconciliation" not in etc_names
    assert "get_inventory_by_region" not in etc_names
    assert "get_salary_ranking" not in etc_names
    assert not (etc_names & set(nl2sql.RAW_SQL_TOOLS))
    assert nl2sql._tools_for_request(scope_role="tp") == []


def test_channel_policy_is_enforced_again_at_execution(monkeypatch):
    seen = {}

    def fake_daily(**kwargs):
        seen.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setitem(rt.TEMPLATES, "get_employee_daily_kpi", fake_daily)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)

    allowed = rt.call_template(
        "get_employee_daily_kpi", {"employee_code": "NV01", "year_month": "2026-08"},
        scope_channel="ETC", scope_role="regional_director",
    )
    blocked_otc_only = rt.call_template(
        "get_revenue_reconciliation", {}, scope_channel="ETC",
        scope_role="regional_director",
    )
    blocked_unscoped = rt.call_template(
        "get_inventory_by_region", {}, scope_channel="OTC",
        scope_role="regional_director",
    )

    assert allowed["ok"] is True
    assert seen["scope_channel"] == "ETC"
    assert blocked_otc_only["ok"] is False
    assert blocked_unscoped["ok"] is False


def test_salary_is_blocked_for_regional_director_but_scoped_for_qlv(monkeypatch):
    seen = {}

    def fake_salary(**kwargs):
        seen.update(kwargs)
        return {"status": "ok"}

    monkeypatch.setitem(rt.TEMPLATES, "get_salary_ranking", fake_salary)
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)

    regional = rt.call_template(
        "get_salary_ranking", {}, scope_channel="OTC", scope_role="regional_director"
    )
    qlv = rt.call_template(
        "get_salary_ranking", {}, scope_area_code="MB", scope_employee_code="QLV01",
        scope_channel="OTC", scope_role="qlv",
    )

    assert regional["ok"] is False
    assert qlv["ok"] is True
    assert seen["scope_employee_code"] == "QLV01"
    assert seen["scope_role"] == "qlv"


def test_glossary_is_private_by_default_and_global_only_when_marked(tmp_path, monkeypatch):
    monkeypatch.setattr(glossary_memory, "DB_PATH", str(tmp_path / "memory.db"))
    glossary_memory.init()
    glossary_memory.save_glossary_term("doanh thu rong", "dinh nghia cua A", defined_by="user.a")
    glossary_memory.save_glossary_term(
        "cong no", "dinh nghia chung", defined_by="c.level", is_global=True
    )

    assert glossary_memory.retrieve_relevant_glossary(
        "doanh thu rong", username="user.a"
    ) == ['"doanh thu rong" = dinh nghia cua A']
    assert glossary_memory.retrieve_relevant_glossary(
        "doanh thu rong", username="user.b"
    ) == []
    assert glossary_memory.retrieve_relevant_glossary(
        "cong no", username="user.b"
    ) == ['"cong no" = dinh nghia chung']


def test_session_claim_is_atomic_and_cannot_be_taken_over(tmp_path, monkeypatch):
    monkeypatch.setattr(conversation_memory, "DB_PATH", str(tmp_path / "memory.db"))
    conversation_memory.init()
    conversation_memory.register_session("same-id", "user.a", "cau dau")

    with pytest.raises(PermissionError):
        conversation_memory.register_session("same-id", "user.b", "chiem session")

    assert conversation_memory.get_session_owner("same-id") == "user.a"
