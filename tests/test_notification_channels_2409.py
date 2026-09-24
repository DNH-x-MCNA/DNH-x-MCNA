"""Decision 24/09: ASM/RM use email; business Teams goes only to directors."""
import json

import pytest

import main
from src import notifier


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for key in ("TEAMS_DELIVERY_MODE", "TEAMS_SHARED_WEBHOOK_URL", "TEAMS_RECIPIENTS_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(notifier.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Real HTTP forbidden"))


def _team(role="qlv"):
    return {"audience": "ASM A", "role": role, "employee_code": "QLV01",
            "region": "bac", "channel": "OTC", "emails": ["asm@example.invalid"],
            "teams_webhook": "https://legacy.invalid", "teams_recipient": "old@example.invalid"}


def _director():
    return {"audience": "GD MB", "role": "regional_director", "region": "bac",
            "teams_webhook": "https://legacy.invalid"}


def _team_metrics():
    return {"report_type": "qlv_team_daily", "date": "2026-09-24", "employee_code": "QLV01",
            "area_code": "MB", "channel": "OTC", "daily_revenue": {"total": {"revenue": 10, "invoices": 1}},
            "month_to_date_revenue": {"total": {"revenue": 100, "invoices": 4}},
            "team_kpi": {}, "customer_lifecycle": {}, "debt_risk": {"customers": []}}


@pytest.mark.parametrize("role", ["qlv", "asm", "rm"])
def test_daily_manager_uses_email_with_exact_team_scope(monkeypatch, role):
    recipient = _team(role)
    recipient.pop("teams_recipient")
    calls = []
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [recipient]})
    monkeypatch.setattr(main, "build_qlv_digest_metrics", lambda **kw: calls.append(kw) or _team_metrics())
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: pytest.fail("Whole region queried for ASM"))
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: pytest.fail("ASM/RM must not use Teams"))
    monkeypatch.setattr(main, "send_email", lambda subject, body, **kw: calls.append((subject, body, kw)) or True)

    assert main.send_daily_digest()
    assert calls[0] == {"employee_code": "QLV01", "region": "bac", "channel": "OTC"}
    subject, body, kwargs = calls[1]
    assert kwargs["recipient_override"] == ["asm@example.invalid"]
    assert "HÀNG NGÀY" in subject and "HÀNG NGÀY" in body
    assert "QLV01" in body and "Doanh số đội trong ngày" in body


def test_missing_manager_email_never_uses_legacy_teams(monkeypatch):
    recipient = _team()
    recipient["emails"] = []
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [recipient]})
    monkeypatch.setattr(main, "build_qlv_digest_metrics", lambda **kw: pytest.fail("Missing email must stop before query"))
    monkeypatch.setattr(main, "send_email", lambda *a, **kw: pytest.fail("No fallback mailbox"))
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: pytest.fail("No fallback Teams"))
    assert not main.send_daily_digest()


def test_alert_routes_exclude_managers_clevel_and_unknown_roles(monkeypatch):
    recipients = [_team(), _team("asm"), _team("rm"), _director(),
                  {"audience": "GD OTC", "role": "channel_director", "channel": "OTC",
                   "teams_webhook": "https://otc.invalid"},
                  {"audience": "C-Level", "teams_webhook": "https://clevel.invalid"},
                  {"audience": "Other", "role": "staff", "region": "bac", "teams_webhook": "https://other.invalid"}]
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_recipients": recipients})
    assert {route[1] for route in notifier._resolve_teams_webhooks("Miền Bắc", "OTC")} == {"GD MB", "GD OTC"}


def test_no_recipient_configuration_never_sends_global_teams(monkeypatch):
    monkeypatch.setattr(notifier, "load_config", lambda: {})
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://old.invalid")
    assert notifier._resolve_teams_webhooks("Miền Bắc", "OTC") == []


def _shared(monkeypatch, tmp_path, mapping):
    path = tmp_path / "recipients.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "shared")
    monkeypatch.setenv("TEAMS_SHARED_WEBHOOK_URL", "https://flow.example.invalid/secret")
    monkeypatch.setenv("TEAMS_RECIPIENTS_FILE", str(path))


def test_shared_flow_requires_only_director_upns(monkeypatch, tmp_path):
    _shared(monkeypatch, tmp_path, {"GD MB": "director@example.invalid"})
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_recipients": [_team(), _director()]})
    assert notifier._resolve_teams_webhooks("Miền Bắc", "OTC") == [
        ("https://flow.example.invalid/secret", "GD MB", "director@example.invalid")]


@pytest.mark.parametrize("mapping", [{}, {"GD MB": "bad-upn"},
                                     {"GD MB": "director@example.invalid", "ASM A": "asm@example.invalid"}])
def test_shared_flow_invalid_mapping_never_falls_back(monkeypatch, tmp_path, mapping):
    from src.teams_routing import TeamsRoutingError
    _shared(monkeypatch, tmp_path, mapping)
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_recipients": [_director()]})
    with pytest.raises(TeamsRoutingError):
        notifier._resolve_teams_webhooks("Miền Bắc", "OTC")


def test_teams_missing_config_does_not_block_manager_email(monkeypatch):
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "shared")
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [_director(), _team()]})
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: pytest.fail("No Teams destination"))
    monkeypatch.setattr(main, "build_qlv_digest_metrics", lambda **kw: _team_metrics())
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: pytest.fail("No Teams destination"))
    sent = []
    monkeypatch.setattr(main, "send_email", lambda *a, **kw: sent.append(kw) or True)
    assert not main.send_daily_digest()
    assert sent[0]["recipient_override"] == ["asm@example.invalid"]


def test_director_daily_shared_flow_carries_scoped_payload_and_upn(monkeypatch, tmp_path):
    _shared(monkeypatch, tmp_path, {"GD MB": "director@example.invalid"})
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [_director()]})
    scopes, sent = [], []
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: scopes.append(kw) or {
        "date": "2026-09-24", "freshness_note": "Dữ liệu đến 24/09", "insights": None,
        "revenue": {"otc": 10, "etc": 20, "total": 30, "otc_invoice_count": 1,
                    "etc_invoice_count": 2, "invoice_count": 3},
        "inventory": {"dead_stock_available": False, "near_stockout_available": False},
    })
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: sent.append(kw) or True)
    monkeypatch.setattr(main, "send_email", lambda *a, **kw: pytest.fail("Director Daily still uses Teams"))
    assert main.send_daily_digest()
    assert scopes == [{"region": "bac", "channel": None}]
    assert sent[0]["webhook_url_override"] == "https://flow.example.invalid/secret"
    assert sent[0]["recipient"] == "director@example.invalid"
    assert sent[0]["audience"] == "GD MB"


def test_manager_daily_dry_run_never_sends_email_or_teams(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [_team()]})
    monkeypatch.setattr(main, "build_qlv_digest_metrics", lambda **kw: _team_metrics())
    monkeypatch.setattr(main, "send_email", lambda *a, **kw: pytest.fail("Dry-run cannot send email"))
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: pytest.fail("Dry-run cannot send Teams"))
    assert main.send_daily_digest(dry_run=True)


def test_critical_retry_only_failed_recipient(monkeypatch):
    routes = [("https://flow.invalid", "GD MB", "mb@example.invalid"),
              ("https://flow.invalid", "GD OTC", "otc@example.invalid")]
    item = {"alert_name": "A", "summary": "x", "period": None, "channel": "OTC", "region": "Miền Bắc",
            "issue": None, "table_headers": None, "table_rows": None, "webhooks": routes}
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [item])
    monkeypatch.setattr(notifier, "_send_with_retry", lambda fn, url, payload: payload["recipient"] == "mb@example.invalid")
    notifier.flush_critical_teams_queue()
    assert notifier._pending_critical_teams_alerts[0]["webhooks"] == [routes[1]]
