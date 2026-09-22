"""Opt-in routing to one Power Automate Flow, without changing business scopes."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


class TeamsRoutingError(ValueError):
    """Configuration error safe to print; never includes a webhook or file contents."""


def delivery_mode():
    mode = os.getenv("TEAMS_DELIVERY_MODE", "legacy").strip().lower()
    if mode not in {"legacy", "shared"}:
        raise TeamsRoutingError("TEAMS_DELIVERY_MODE phải là legacy hoặc shared.")
    return mode


def load_teams_environment():
    """Same file precedence as main.py: root, backend, then config (last wins)."""
    from dotenv import load_dotenv

    for relative in (".env", "backend/.env", "config/.env"):
        load_dotenv(ROOT / relative, override=True)


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TeamsRoutingError("Bảng người nhận Teams có audience bị lặp.")
        result[key] = value
    return result


def load_shared_routes(config):
    """Validate the complete mapping before any sends; None preserves legacy routing.

    The local JSON contains only audience -> Teams UPN. It cannot change scopes,
    email recipients or webhook URLs. An invalid shared configuration never falls
    back to a legacy destination.
    """
    if delivery_mode() == "legacy":
        return None
    if not isinstance(config, dict):
        raise TeamsRoutingError("Không đọc được cấu hình audience cho Flow chung.")

    webhook = os.getenv("TEAMS_SHARED_WEBHOOK_URL", "").strip()
    try:
        url = urlsplit(webhook)
        valid = (url.scheme == "https" and url.hostname and not url.username
                 and not url.password and not url.fragment
                 and not any(c.isspace() for c in webhook))
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise TeamsRoutingError("TEAMS_SHARED_WEBHOOK_URL phải là webhook HTTPS hợp lệ.")

    audiences = config.get("report_recipients") or []
    if not isinstance(audiences, list) or any(not isinstance(r, dict) for r in audiences):
        raise TeamsRoutingError("report_recipients phải là danh sách audience.")
    names = [r.get("audience") for r in audiences]
    if not names or any(not isinstance(n, str) or not n.strip() for n in names):
        raise TeamsRoutingError("Flow chung yêu cầu danh sách audience có tên đầy đủ.")
    if len(set(names)) != len(names):
        raise TeamsRoutingError("Danh sách audience có tên bị lặp.")

    path = Path(os.getenv("TEAMS_RECIPIENTS_FILE") or "config/teams_recipients.local.json")
    if not path.is_absolute():
        path = ROOT / path
    try:
        mapping = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
    except (OSError, UnicodeError, ValueError):
        raise TeamsRoutingError("Không đọc được bảng người nhận Teams; kiểm tra file JSON và khóa trùng.") from None
    if not isinstance(mapping, dict) or set(mapping) != set(names):
        raise TeamsRoutingError("Bảng người nhận Teams phải có đúng các audience trong report_recipients.")

    routes = {}
    for name in names:
        recipient = mapping[name]
        if (not isinstance(recipient, str)
                or not re.fullmatch(r"[^\s@;,<>]+@[^\s@;,<>]+\.[^\s@;,<>]+", recipient.strip())):
            raise TeamsRoutingError(f"Audience '{name}' thiếu hoặc sai UPN Teams (mỗi audience một người).")
        routes[name] = (webhook, recipient.strip())
    return routes


def resolve_destination(audience_config, shared_routes, webhook_override=None):
    if shared_routes is not None:
        webhook, recipient = shared_routes[audience_config["audience"]]
    else:
        webhook = ((audience_config.get("teams_webhook") or "").strip()
                   or os.getenv("TEAMS_WEBHOOK_URL"))
        recipient = (audience_config.get("teams_recipient") or "").strip() or None
    return webhook_override or webhook, recipient
