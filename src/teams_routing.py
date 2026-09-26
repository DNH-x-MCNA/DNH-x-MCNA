"""Business delivery policy agreed on 24/09 (C-Level keeps Teams, 26/09); optional shared Teams Flow from #41."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TEAM_ROLES = frozenset({"qlv", "asm", "rm"})


class TeamsRoutingError(ValueError):
    """Configuration error safe to log without credentials or webhook URLs."""


def is_team_manager(recipient):
    return str(recipient.get("role") or "").strip().lower() in TEAM_ROLES


def teams_audience_allowed(recipient):
    """Business Teams: C-Level plus regional/channel directors; QLV/ASM/RM use email only.

    26/09/2026: anh Dang chot phuong an A - C-Level GIU Teams (Daily + canh bao) nhu truoc #106. Ghi chu
    tay hop 24/09 ghi "Teams: C-Level, Giam doc mien, Giam doc kenh"; ban tom tat chu chi ghi giam doc
    mien/kenh nen #106 da bo C-Level. C-Level = audience KHONG gioi han vung/kenh (legacy: role rong).

    Legacy YAML has no roles on the six audiences. Continue to recognize those
    scopes, but never infer a role from a name or an UPN. A team code always excludes Teams.
    """
    if is_team_manager(recipient) or str(recipient.get("employee_code") or "").strip():
        return False
    role = str(recipient.get("role") or "").strip().lower()
    if role not in {"", "c_level", "regional_director", "channel_director"}:
        return False
    region, channel = recipient.get("region"), recipient.get("channel")
    if role == "c_level":
        return not region and not channel
    if role == "regional_director":
        return bool(region)
    if role == "channel_director":
        return bool(channel)
    return True


def delivery_mode():
    mode = os.getenv("TEAMS_DELIVERY_MODE", "legacy").strip().lower()
    if mode not in {"legacy", "shared"}:
        raise TeamsRoutingError("TEAMS_DELIVERY_MODE phải là legacy hoặc shared.")
    return mode


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise TeamsRoutingError("Bảng người nhận Teams có audience bị lặp.")
        result[key] = value
    return result


def load_shared_routes(config):
    """Validate all director UPNs before Teams sends; never fall back from shared.

    Only audience -> UPN is allowed in the local mapping. It cannot widen data
    scopes. Email-only managers (QLV/ASM/RM) must not appear in that mapping.
    """
    if delivery_mode() == "legacy":
        return None
    audiences = config.get("report_recipients") or []
    if not isinstance(audiences, list) or any(not isinstance(r, dict) for r in audiences):
        raise TeamsRoutingError("report_recipients phải là danh sách audience.")
    names = [r.get("audience") for r in audiences if teams_audience_allowed(r)]
    if not names:
        return {}
    if any(not isinstance(name, str) or not name.strip() for name in names) or len(set(names)) != len(names):
        raise TeamsRoutingError("Audience Teams phải có tên đầy đủ và không trùng.")
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
    path_text = os.getenv("TEAMS_RECIPIENTS_FILE", "").strip()
    if not path_text:
        raise TeamsRoutingError("Thiếu TEAMS_RECIPIENTS_FILE trỏ tới bảng UPN local do DNH cấp.")
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT / path
    try:
        mapping = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
    except (OSError, UnicodeError, ValueError):
        raise TeamsRoutingError("Không đọc được bảng UPN Teams; kiểm tra JSON và khóa trùng.") from None
    if not isinstance(mapping, dict) or set(mapping) != set(names):
        raise TeamsRoutingError("Bảng UPN phải có đúng các audience C-Level và giám đốc miền/kênh; không có QLV.")
    routes = {}
    for name in names:
        recipient = mapping[name]
        if (not isinstance(recipient, str)
                or not re.fullmatch(r"[^\s@;,<>]+@[^\s@;,<>]+\.[^\s@;,<>]+", recipient.strip())):
            raise TeamsRoutingError(f"Audience '{name}' thiếu hoặc sai UPN Teams (mỗi audience một người).")
        routes[name] = (webhook, recipient.strip())
    return routes


def resolve_destination(recipient_config, shared_routes, webhook_override=None):
    if not teams_audience_allowed(recipient_config):
        raise TeamsRoutingError("Teams nghiệp vụ chỉ dành cho giám đốc miền và giám đốc kênh.")
    if shared_routes is not None:
        webhook, upn = shared_routes[recipient_config["audience"]]
    else:
        webhook = ((recipient_config.get("teams_webhook") or "").strip()
                   or os.getenv("TEAMS_WEBHOOK_URL"))
        upn = (recipient_config.get("teams_recipient") or "").strip() or None
    webhook = webhook_override or webhook
    if not webhook:
        raise TeamsRoutingError("Chưa cấu hình webhook Teams cho giám đốc.")
    return webhook, upn
