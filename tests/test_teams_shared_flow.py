"""Shared transport must preserve audience scope and never fall back on config errors."""
import copy
import json

import pytest

import main
from backend import health_watchdog
from scripts import check_teams_routing
from src import notifier, teams_routing


AUDIENCES = [
    {"audience": "C-Level (Toàn quốc)", "region": None, "channel": None},
    {"audience": "Quản lý Miền Bắc", "region": "bac", "channel": None},
    {"audience": "Quản lý Miền Nam", "region": "nam", "channel": None},
    {"audience": "Quản lý Miền Trung", "region": "trung", "channel": None},
    {"audience": "Quản lý Kênh OTC", "region": None, "channel": "OTC"},
    {"audience": "Quản lý Kênh ETC", "region": None, "channel": "ETC"},
]


@pytest.fixture
def shared(monkeypatch, tmp_path):
    rows = copy.deepcopy(AUDIENCES)
    for row in rows:
        row.update(teams_webhook="https://legacy.invalid/flow", emails=["mail@example.test"])
    config = {"report_recipients": rows}
    mapping = {row["audience"]: f"manager{i}@example.test" for i, row in enumerate(rows)}
    path = tmp_path / "recipients.json"
    path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8-sig")
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "shared")
    monkeypatch.setenv("TEAMS_SHARED_WEBHOOK_URL", "https://shared.invalid/flow?sig=SECRET")
    monkeypatch.setenv("TEAMS_RECIPIENTS_FILE", str(path))
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://legacy.invalid/default")
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(notifier, "load_config", lambda: config)
    monkeypatch.setattr(health_watchdog, "load_teams_environment", lambda: None)
    # No live transport allowed in these tests, even if another path is introduced.
    monkeypatch.setattr(notifier.urllib.request, "urlopen", lambda *a, **k: pytest.fail("unexpected network"))
    return config, mapping, path


def _metrics(region, channel):
    return {
        "date": "22/09/2026", "channel": channel,
        "freshness_note": f"SCOPE:{region}/{channel}",
        "revenue": {"otc": 10, "etc": 20, "total": 30,
                    "otc_invoice_count": 1, "etc_invoice_count": 2, "invoice_count": 3},
        "inventory": {"dead_stock_available": False, "near_stockout_available": False},
    }


@pytest.mark.parametrize("same_person", [False, True])
def test_daily_six_scopes_remain_six_distinct_reports(shared, monkeypatch, same_person):
    config, mapping, path = shared
    original = copy.deepcopy(config)
    if same_person:
        mapping = {key: "tester@example.test" for key in mapping}
        path.write_text(json.dumps(mapping), encoding="utf-8")
    scopes, sends = [], []

    def metrics(**kw):
        scopes.append(kw)
        return _metrics(**kw)

    monkeypatch.setattr(main, "get_daily_digest_metrics", metrics)
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: sends.append(kw) or True)
    assert main.send_daily_digest()
    assert len(sends) == 6
    assert scopes == [{"region": r["region"], "channel": r["channel"]} for r in AUDIENCES]
    for row, payload in zip(AUDIENCES, sends):
        assert payload["recipient"] == mapping[row["audience"]]
        assert payload["audience"] == row["audience"]
        assert payload["webhook_url_override"] == "https://shared.invalid/flow?sig=SECRET"
        assert f"SCOPE:{row['region']}/{row['channel']}" in payload["summary"]
        labels = [r[0] for r in payload["table_rows"]]
        assert ("Doanh thu OTC" in labels) == (row["channel"] != "ETC")
        assert ("Doanh thu ETC" in labels) == (row["channel"] != "OTC")
    assert config == original, "Teams routing must not mutate email recipients or business scopes"


@pytest.mark.parametrize(("region", "channel", "indexes"), [
    ("Miền Bắc", "OTC", [0, 1, 4]),
    ("Miền Nam", "ETC", [0, 2, 5]),
    ("Miền Trung", "OTC", [0, 3, 4]),
    (None, None, [0]),
    (None, "ETC", [0, 5]),
])
def test_alert_only_resolves_matching_scope(shared, region, channel, indexes):
    _, mapping, _ = shared
    routes = notifier._resolve_teams_webhooks(region, channel)
    assert [r[1] for r in routes] == [AUDIENCES[i]["audience"] for i in indexes]
    assert [r[2] for r in routes] == [mapping[AUDIENCES[i]["audience"]] for i in indexes]
    assert {r[0] for r in routes} == {"https://shared.invalid/flow?sig=SECRET"}


def test_team_audience_is_excluded_from_region_alerts(shared):
    config, mapping, path = shared
    config["report_recipients"].append({"audience": "QLV A", "role": "qlv",
                                     "employee_code": "QLV01", "region": "bac", "channel": "OTC"})
    mapping["QLV A"] = "qlv@example.test"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    assert "QLV A" not in [r[1] for r in notifier._resolve_teams_webhooks("Miền Bắc", "OTC")]


@pytest.mark.parametrize("bad", ["missing", "unknown", "empty", "multiple", "array", "malformed", "duplicate", "unreadable"])
def test_invalid_mapping_blocks_before_build_or_send(shared, monkeypatch, capsys, bad):
    config, mapping, path = shared
    if bad == "missing":
        mapping.pop(AUDIENCES[-1]["audience"])
    elif bad == "unknown":
        mapping["audience typo"] = "other@example.test"
    elif bad == "empty":
        mapping[AUDIENCES[0]["audience"]] = ""
    elif bad == "multiple":
        mapping[AUDIENCES[0]["audience"]] = "a@example.test;b@example.test"
    elif bad == "array":
        mapping = list(mapping)
    path.write_text(json.dumps(mapping), encoding="utf-8")
    if bad == "malformed":
        path.write_text("SECRET invalid json", encoding="utf-8")
    elif bad == "duplicate":
        path.write_text('{"dup":"a@example.test","dup":"b@example.test"}', encoding="utf-8")
    elif bad == "unreadable":
        monkeypatch.setenv("TEAMS_RECIPIENTS_FILE", str(path.parent / "missing.json"))
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **k: pytest.fail("must validate before DB"))
    monkeypatch.setattr(main, "send_teams_alert", lambda **k: pytest.fail("must not send"))
    assert main.send_daily_digest(audience_filter=AUDIENCES[0]["audience"]) is False
    with pytest.raises(teams_routing.TeamsRoutingError):
        notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    assert "SECRET" not in capsys.readouterr().out


@pytest.mark.parametrize("url", ["", "http://insecure.test", "https://user:pass@example.test", "https://example.test:bad"])
def test_shared_webhook_invalid_has_no_legacy_fallback(shared, monkeypatch, url):
    monkeypatch.setenv("TEAMS_SHARED_WEBHOOK_URL", url)
    assert main.send_daily_digest() is False
    with pytest.raises(teams_routing.TeamsRoutingError):
        notifier._resolve_teams_webhooks("Miền Bắc", "OTC")


def test_legacy_does_not_read_shared_file(shared, monkeypatch):
    config, _, _ = shared
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "legacy")
    monkeypatch.setattr(teams_routing.Path, "read_text", lambda *a, **k: pytest.fail("legacy must not read shared file"))
    assert teams_routing.load_shared_routes(config) is None
    assert notifier._resolve_teams_webhooks(None, None) == [
        ("https://legacy.invalid/flow", "C-Level (Toàn quốc)", None)]


def test_typo_in_mode_blocks_instead_of_legacy(shared, monkeypatch):
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "shaerd")
    assert main.send_daily_digest() is False


def test_critical_queue_retries_only_failed_recipient(shared, monkeypatch):
    calls = []
    failed = {"manager1@example.test"}

    def post(url, payload):
        calls.append(copy.deepcopy(payload))
        return payload["recipient"] not in failed

    monkeypatch.setattr(notifier, "_post_teams_webhook", post)
    routes = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [{
        "alert_name": "MB OTC", "summary": "MB_ONLY", "period": None,
        "channel": "OTC", "region": "Miền Bắc", "issue": None,
        "table_headers": None, "table_rows": None, "webhooks": routes,
    }])
    notifier.flush_critical_teams_queue()
    assert len(calls) == 3
    assert len(notifier._pending_critical_teams_alerts) == 1
    assert notifier._pending_critical_teams_alerts[0]["webhooks"] == [routes[1]]
    failed.clear()
    notifier.flush_critical_teams_queue()
    assert len(calls) == 4
    assert calls[-1]["recipient"] == "manager1@example.test"
    assert notifier._pending_critical_teams_alerts == []


def test_watchdog_uses_shared_clevel_route(shared, monkeypatch):
    from src import database
    monkeypatch.setattr(database, "load_config", lambda: shared[0])
    calls = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False

    def send(request, timeout):
        calls.append((request.full_url, json.loads(request.data)))
        return Response()

    monkeypatch.setattr(health_watchdog.urllib.request, "urlopen", send)
    assert health_watchdog._send_teams_alert("test", "test")
    assert calls[0][0] == "https://shared.invalid/flow?sig=SECRET"
    assert calls[0][1]["recipient"] == "manager0@example.test"
    assert calls[0][1]["audience"] == "C-Level (Toàn quốc)"


def test_critical_cards_do_not_mix_regions_or_channels(shared, monkeypatch):
    cards = {}
    pending = []
    for region, channel, marker in [("Miền Bắc", "OTC", "MB_ONLY"), ("Miền Nam", "ETC", "MN_ONLY")]:
        pending.append({
            "alert_name": marker, "summary": marker, "period": None,
            "channel": channel, "region": region, "issue": None,
            "table_headers": None, "table_rows": None,
            "webhooks": notifier._resolve_teams_webhooks(region, channel),
        })

    def post(url, payload):
        cards[payload["recipient"]] = json.dumps(payload, ensure_ascii=False)
        return True

    monkeypatch.setattr(notifier, "_post_teams_webhook", post)
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", pending)
    notifier.flush_critical_teams_queue()
    assert set(cards) == {f"manager{i}@example.test" for i in [0, 1, 2, 4, 5]}
    for i in [1, 4]:
        assert "MB_ONLY" in cards[f"manager{i}@example.test"]
        assert "MN_ONLY" not in cards[f"manager{i}@example.test"]
    for i in [2, 5]:
        assert "MN_ONLY" in cards[f"manager{i}@example.test"]
        assert "MB_ONLY" not in cards[f"manager{i}@example.test"]
    assert "MB_ONLY" in cards["manager0@example.test"] and "MN_ONLY" in cards["manager0@example.test"]


def test_watchdog_bad_config_does_not_fallback(shared, monkeypatch):
    from src import database
    monkeypatch.setattr(database, "load_config", lambda: shared[0])
    monkeypatch.delenv("TEAMS_SHARED_WEBHOOK_URL")
    assert health_watchdog._send_teams_alert("test", "test") is False


@pytest.mark.parametrize("was_alerted", [False, True])
def test_watchdog_does_not_record_failed_delivery(monkeypatch, was_alerted):
    state = {"sync_stale_alerted": was_alerted, "tunnel_mismatch_alerted": was_alerted}
    original = state.copy()
    monkeypatch.setattr(health_watchdog, "_load_state", lambda: state)
    monkeypatch.setattr(health_watchdog, "_check_sync_stale", lambda: (not was_alerted, 100))
    monkeypatch.setattr(health_watchdog, "_check_tunnel_mismatch", lambda: (not was_alerted, "old", "new"))
    monkeypatch.setattr(health_watchdog, "_send_teams_alert", lambda *a, **k: False)
    monkeypatch.setattr(health_watchdog, "_save_state", lambda *a: pytest.fail("no delivery to record"))
    health_watchdog.run_check()
    assert state == original


def test_preflight_does_not_call_webhook(shared, monkeypatch, tmp_path, capsys):
    import yaml
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(shared[0]), encoding="utf-8")
    monkeypatch.setattr(check_teams_routing, "ROOT", tmp_path)
    monkeypatch.setattr(check_teams_routing, "load_teams_environment", lambda: None)
    assert check_teams_routing.main([]) == 0
    output = capsys.readouterr().out
    assert "PASS cấu hình" in output
    assert "SECRET" not in output


def test_daily_dry_run_does_not_print_signed_webhook(shared, monkeypatch, capsys):
    monkeypatch.setattr(main, "get_daily_digest_metrics", _metrics)
    assert main.send_daily_digest(dry_run=True)
    assert "SECRET" not in capsys.readouterr().out


def test_teams_env_precedence_matches_report_runner(tmp_path, monkeypatch):
    monkeypatch.setattr(teams_routing, "ROOT", tmp_path)
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "process")
    for relative, value in [(".env", "root"), ("backend/.env", "backend"), ("config/.env", "shared")]:
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"TEAMS_DELIVERY_MODE={value}\n", encoding="utf-8")
    teams_routing.load_teams_environment()
    assert teams_routing.delivery_mode() == "shared"
