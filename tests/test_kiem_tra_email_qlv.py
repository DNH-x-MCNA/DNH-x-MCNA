"""Offline configuration gate: no network, no report construction, no secret output."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts import kiem_tra_email_qlv as check


@pytest.fixture(autouse=True)
def smtp_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith("SMTP_") or key in {"EMAIL_PROVIDER", "SENDGRID_API_KEY", "SENDER_EMAIL"}:
            monkeypatch.delenv(key)
    for key, value in {"EMAIL_PROVIDER": "smtp", "SMTP_USER": "service@example.invalid",
                       "SMTP_PASSWORD": "test-only-sensitive-marker", "SMTP_SERVER": "smtp.example.invalid",
                       "SENDER_EMAIL": "bot@example.invalid", "SMTP_SECURITY": "starttls"}.items():
        monkeypatch.setenv(key, value)


def config(role="qlv"):
    return {"email": {}, "report_recipients": [
        {"audience": "Manager sensitive name", "role": role, "employee_code": "TEST01",
         "region": "bac", "channel": "OTC", "emails": ["manager@example.invalid"]},
        {"audience": "C-Level", "role": "c_level"},
    ]}


@pytest.mark.parametrize("role", ["qlv", "asm", "rm"])
def test_valid_structure_is_not_live_delivery_or_identity_proof(role):
    result = check.inspect_config(config(role))
    assert result == {"status": "CONFIG_VALID_OFFLINE", "qlv_count": 1, "errors": [],
                      "live_delivery_verified": False, "employee_identity_verified": False}
    assert "manager@example.invalid" not in json.dumps(result)


@pytest.mark.parametrize("field,value,code", [
    ("emails", "manager@example.invalid", "EXPECTED_NONEMPTY_ADDRESS_LIST"),
    ("emails", [], "EXPECTED_NONEMPTY_ADDRESS_LIST"),
    ("emails", ["bad\r\naddress@example.invalid"], "EXPECTED_NONEMPTY_ADDRESS_LIST"),
    ("employee_code", "<DNH supplies code>", "MISSING_OR_PLACEHOLDER"),
    ("region", "unknown-sensitive-value", "INVALID_REGION"),
    ("channel", "", "CONFIRM_EXPLICIT_CHANNEL_RUNTIME_DEFAULTS_OTC"),
    ("channel", "other", "INVALID_CHANNEL"),
    ("role", "", "EMPLOYEE_CODE_REQUIRES_QLV_ASM_RM"),
])
def test_invalid_manager_configuration_reports_field_not_value(field, value, code):
    cfg = config()
    cfg["report_recipients"][0][field] = value
    result = check.inspect_config(cfg)
    assert {"field": "report_recipients[1]." + field, "code": code} in result["errors"]
    assert result["status"] == "NEEDS_CONFIGURATION"
    assert "unknown-sensitive-value" not in json.dumps(result)


def test_manager_name_colliding_with_director_cannot_pass():
    cfg = config()
    cfg["report_recipients"][1]["audience"] = cfg["report_recipients"][0]["audience"]
    assert any(e["code"] == "DUPLICATE_AUDIENCE" for e in check.inspect_config(cfg)["errors"])


def test_no_manager_is_not_ready():
    assert any(e["code"] == "NO_QLV_ASM_RM_CONFIGURED"
               for e in check.inspect_config({"email": {}, "report_recipients": []})["errors"])


@pytest.mark.parametrize("key,value,code", [
    ("SMTP_PASSWORD", "", "INVALID_SETTINGS_CHECK_USER_PASSWORD_PORT_SECURITY_TIMEOUT"),
    ("SMTP_PORT", "sensitive-invalid-port", "INVALID_SETTINGS_CHECK_USER_PASSWORD_PORT_SECURITY_TIMEOUT"),
    ("SMTP_PASSWORD", "<replace me>", "MISSING_OR_PLACEHOLDER"),
    ("SMTP_SECURITY", "none", "TLS_REQUIRED_FOR_DNH"),
    ("SENDER_EMAIL", "invalid", "INVALID_ADDRESS"),
])
def test_smtp_gate_fails_without_echoing_values(monkeypatch, key, value, code):
    monkeypatch.setenv(key, value)
    result = check.inspect_config(config())
    assert any(e["code"] == code for e in result["errors"])
    assert "sensitive" not in json.dumps(result)


def test_auto_with_old_sendgrid_key_is_not_dnh_smtp(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "auto")
    monkeypatch.setenv("SENDGRID_API_KEY", "test-only-marker")
    assert any(e["code"] == "NOT_SMTP_SELECT_SMTP_FOR_DNH" for e in check.inspect_config(config())["errors"])


def test_env_precedence_and_expansion_match_report_loading(tmp_path, monkeypatch):
    # This test loads only the synthetic files below, including under the offline harness.
    monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
    (tmp_path / "backend").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / ".env").write_text("SMTP_PORT=1001\n", encoding="utf-8")
    (tmp_path / "backend" / ".env").write_text("SMTP_PORT=1002\n", encoding="utf-8")
    (tmp_path / "config" / ".env").write_text("SMTP_PORT=1003\n", encoding="utf-8")
    monkeypatch.setenv("SMTP_PORT", "1000")
    monkeypatch.setenv("QLV_TEST_ADDRESS", "manager@example.invalid")
    cfg = config()
    cfg["report_recipients"][0]["emails"] = ["${QLV_TEST_ADDRESS}"]
    # Root config wins over config/config.yaml, just as src.database.load_config.
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")
    (tmp_path / "config" / "config.yaml").write_text("invalid: true", encoding="utf-8")
    assert check.inspect_config(check.load_inputs(tmp_path))["status"] == "CONFIG_VALID_OFFLINE"
    assert os.environ["SMTP_PORT"] == "1003"


@pytest.mark.parametrize("broken", [False, True])
def test_cli_is_offline_and_redacts_even_parser_errors(tmp_path, broken):
    text = "email: [ SECRET_PARSE_MARKER\n" if broken else yaml.safe_dump(config())
    (tmp_path / "config.yaml").write_text(text, encoding="utf-8")
    script = str(Path(check.__file__).resolve())
    program = """
import runpy, sys
def guard(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise AssertionError('Network forbidden')
sys.addaudithook(guard)
script, root = sys.argv[1:]
sys.argv = [script, '--repo', root]
try:
    runpy.run_path(script, run_name='__main__')
except SystemExit as exc:
    assert not any(n in sys.modules for n in ('main', 'src.notifier', 'report_templates', 'backend.report_templates'))
    raise
"""
    proc = subprocess.run([sys.executable, "-c", program, script, str(tmp_path)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert proc.returncode == (1 if broken else 0), proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == ("INPUT_ERROR" if broken else "CONFIG_VALID_OFFLINE")
    for secret in ("test-only-sensitive-marker", "Manager sensitive name", "manager@example.invalid", "SECRET_PARSE_MARKER"):
        assert secret not in proc.stdout + proc.stderr
