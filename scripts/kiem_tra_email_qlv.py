"""Check QLV email configuration offline; never build a report or send anything."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import yaml
from backend.mail_transport import MailConfigurationError, report_email_provider, smtp_settings
from src.database import _thay_bien_env
from src.qlv_digest import _normalise_area, _normalise_channel, QLVDigestScopeError
from src.teams_routing import TEAM_ROLES


def _present(value):
    return (isinstance(value, str) and bool(value.strip())
            and not value.strip().startswith(("${", "<")))


def _email(value):
    return _present(value) and bool(re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", value.strip()))


def inspect_config(config):
    """Return only controlled labels, row indices and counts, never config values."""
    errors = []

    def error(field, code):
        errors.append({"field": field, "code": code})

    if not isinstance(config, dict):
        config = {}
        error("config", "EXPECTED_MAPPING")
    try:
        if report_email_provider() != "smtp":
            error("EMAIL_PROVIDER", "NOT_SMTP_SELECT_SMTP_FOR_DNH")
    except MailConfigurationError:
        error("EMAIL_PROVIDER", "INVALID_PROVIDER_CONFIGURATION")

    defaults = config.get("email")
    if not isinstance(defaults, dict):
        error("email", "EXPECTED_MAPPING")
    else:
        try:
            settings = smtp_settings(defaults)
            for key in ("user", "password", "sender", "server"):
                if not _present(settings[key]):
                    error("smtp." + key, "MISSING_OR_PLACEHOLDER")
            if not _email(settings["sender"]):
                error("SENDER_EMAIL", "INVALID_ADDRESS")
            if settings["security"] not in {"starttls", "ssl"}:
                error("SMTP_SECURITY", "TLS_REQUIRED_FOR_DNH")
        except MailConfigurationError:
            error("smtp", "INVALID_SETTINGS_CHECK_USER_PASSWORD_PORT_SECURITY_TIMEOUT")

    recipients = config.get("report_recipients")
    if not isinstance(recipients, list):
        recipients = []
        error("report_recipients", "EXPECTED_LIST")
    names = Counter(r.get("audience") for r in recipients if isinstance(r, dict)
                    and isinstance(r.get("audience"), str))
    managers = 0
    for index, row in enumerate(recipients, 1):
        prefix = f"report_recipients[{index}]"
        if not isinstance(row, dict):
            error(prefix, "EXPECTED_MAPPING")
            continue
        role = str(row.get("role") or "").strip().lower()
        if role not in TEAM_ROLES:
            if row.get("employee_code"):
                error(prefix + ".role", "EMPLOYEE_CODE_REQUIRES_QLV_ASM_RM")
            continue
        managers += 1
        for key in ("audience", "employee_code"):
            if not _present(row.get(key)):
                error(prefix + "." + key, "MISSING_OR_PLACEHOLDER")
        audience = row.get("audience")
        if isinstance(audience, str) and names[audience] > 1:
            error(prefix + ".audience", "DUPLICATE_AUDIENCE")
        try:
            _normalise_area(row.get("region"))
        except QLVDigestScopeError:
            error(prefix + ".region", "INVALID_REGION")
        # Require an explicit confirmed channel in the handover configuration.
        if not _present(row.get("channel")):
            error(prefix + ".channel", "CONFIRM_EXPLICIT_CHANNEL_RUNTIME_DEFAULTS_OTC")
        else:
            try:
                _normalise_channel(row["channel"])
            except QLVDigestScopeError:
                error(prefix + ".channel", "INVALID_CHANNEL")
        emails = row.get("emails")
        if not isinstance(emails, list) or not emails or not all(_email(e) for e in emails):
            error(prefix + ".emails", "EXPECTED_NONEMPTY_ADDRESS_LIST")
    if not managers:
        error("report_recipients", "NO_QLV_ASM_RM_CONFIGURED")
    return {"status": "NEEDS_CONFIGURATION" if errors else "CONFIG_VALID_OFFLINE",
            "qlv_count": managers, "errors": errors,
            "live_delivery_verified": False, "employee_identity_verified": False}


def load_inputs(root):
    # Same explicit files/order and fallback as main.load_env; do not import main,
    # notifier, report_templates or the application that could build reports.
    for relative in (".env", "backend/.env", "config/.env"):
        path = root / relative
        if path.is_file():
            load_dotenv(path, override=True)
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ.setdefault(key.strip(), value.strip())
    path = root / "config.yaml"
    if not path.is_file():
        path = root / "config" / "config.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return raw
    # Omit unrelated Teams/database settings and suppress the shared resolver's
    # missing-variable notices so stdout stays a single redacted JSON object.
    recipients = raw.get("report_recipients")
    if isinstance(recipients, list):
        recipients = [{k: r.get(k) for k in ("audience", "role", "employee_code", "region", "channel", "emails")}
                      if isinstance(r, dict) else r for r in recipients]
    with redirect_stdout(io.StringIO()):
        return _thay_bien_env({"email": raw.get("email"), "report_recipients": recipients})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Kiem cau hinh email QLV offline; khong gui, khong truy DB")
    parser.add_argument("--repo", type=Path, default=ROOT, help="Repo chua config va cac file .env")
    args = parser.parse_args(argv)
    try:
        result = inspect_config(load_inputs(args.repo.resolve()))
    except Exception:
        # YAML/parser/OS exceptions may include the secret-bearing source line.
        result = {"status": "INPUT_ERROR", "errors": [{"field": "config/env", "code": "CHECK_FILES_LOCALLY"}],
                  "live_delivery_verified": False, "employee_identity_verified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "CONFIG_VALID_OFFLINE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
