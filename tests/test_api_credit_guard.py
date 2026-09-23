"""Regression tests for API credit failures and attributable model calls.

Every model client and Teams sender in this file is a stub; no paid request is made.
"""
import importlib.util
import asyncio
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(1, str(BACKEND))

import nl2sql  # noqa: E402
import health_watchdog as watchdog  # noqa: E402


class FakeCreditError(Exception):
    status_code = 400

    def __str__(self):
        return "Error code: 400 - Your credit balance is too low to access the Anthropic API"


class FakeOtherBadRequest(Exception):
    status_code = 400

    def __str__(self):
        return "Error code: 400 - invalid model name"


def _fake_model(monkeypatch, stream=False):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key-never-used")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-09-22")
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append("create")
            raise FakeCreditError()

        def stream(self, **kwargs):
            calls.append("stream")
            raise FakeCreditError()

    monkeypatch.setattr(nl2sql, "_llm_client", lambda: SimpleNamespace(messages=Messages()))
    return calls


@pytest.mark.parametrize("stream", [False, True])
def test_credit_error_translated_at_model_boundary(monkeypatch, stream):
    calls = _fake_model(monkeypatch, stream)
    with pytest.raises(nl2sql.ApiCreditExhaustedError) as caught:
        if stream:
            list(nl2sql.ask_stream("Doanh thu?", session_id="uat-credit-case", username="uat.user"))
        else:
            nl2sql.ask("Doanh thu?", session_id="uat-credit-case", username="uat.user")
    assert calls
    assert "credit balance is too low" in caught.value.raw_message
    assert isinstance(caught.value.__cause__, FakeCreditError)


def test_other_400_is_not_mislabeled_as_credit(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key-never-used")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-09-22")

    class Messages:
        def create(self, **kwargs):
            raise FakeOtherBadRequest()

    monkeypatch.setattr(nl2sql, "_llm_client", lambda: SimpleNamespace(messages=Messages()))
    with pytest.raises(FakeOtherBadRequest):
        nl2sql.ask("Doanh thu?", session_id="uat-other-case", username="uat.user")


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("username,session_id", [(None, "uat-case-1"), ("unknown", "uat-case-1"),
                                                  ("alice", "uat-case-1"), ("test", "uat-case-1"),
                                                  ("admin", "uat-case-1"),
                                                  ("uat.user", "default"), ("uat.user", "plain")])
def test_model_call_requires_attribution_before_client(monkeypatch, stream, username, session_id):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "stub-key-never-used")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    created = []
    monkeypatch.setattr(nl2sql, "_llm_client", lambda: created.append(1))
    with pytest.raises(nl2sql.UnattributedModelCallError):
        if stream:
            list(nl2sql.ask_stream("Doanh thu?", session_id=session_id, username=username))
        else:
            nl2sql.ask("Doanh thu?", session_id=session_id, username=username)
    assert not created


def _load_main():
    spec = importlib.util.spec_from_file_location("dnh_credit_test_main", BACKEND / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stream", [False, True])
def test_chat_marks_credit_status_and_shows_actionable_message(monkeypatch, stream):
    main = _load_main()
    logged = []
    monkeypatch.setattr(main, "_business_scopes", lambda user: (None, None, None))
    monkeypatch.setattr(main, "_check_rate_limit", lambda username: None)
    monkeypatch.setattr(main, "register_session", lambda *args: None)
    monkeypatch.setattr(main, "_require_session_write_access", lambda *args: None)
    monkeypatch.setattr(main, "_quota_for_question", lambda *args: {})
    monkeypatch.setattr(main, "create_query_run", lambda *args: None)
    monkeypatch.setattr(main, "fail_query_run", lambda *args, **kwargs: logged.append((args, kwargs)))
    credit = nl2sql.ApiCreditExhaustedError("Error code: 400 - Your credit balance is too low")

    def raise_credit(*args, **kwargs):
        raise credit

    monkeypatch.setattr(main, "ask", raise_credit)
    monkeypatch.setattr(main, "ask_stream", raise_credit)
    req = main.ChatRequest(question="Doanh thu?", session_id="web-session-1")
    user = {"username": "uat.user", "role": "c_level"}
    if stream:
        response = main.chat_stream(req, user)
        async def collect():
            return [chunk async for chunk in response.body_iterator]
        event = json.loads(asyncio.run(collect())[0].removeprefix("data: "))
        message = event["message"]
        assert event["type"] == "error"
        assert event["code"] == "api_credit_exhausted"
    else:
        with pytest.raises(main.HTTPException) as caught:
            main.chat(req, user)
        assert caught.value.status_code == 503
        message = caught.value.detail
    assert "hết hạn mức" in message.lower()
    assert "không phải" in message.lower()
    assert logged[0][1]["status"] == "api_credit_exhausted"
    assert "credit balance is too low" in logged[0][0][1]


def test_watchdog_warns_once_before_estimated_credit_exhaustion(monkeypatch, tmp_path):
    cost_path = tmp_path / "cost_log.jsonl"
    cost_path.write_text("\n".join(json.dumps(row) for row in [
        {"ts": "2026-09-23T08:00:00", "provider": "Anthropic", "cost_usd": 3.1},
        {"ts": "2026-09-23T08:10:00", "provider": "DeepSeek", "cost_usd": 50},
        {"ts": "2026-09-22T08:10:00", "provider": "Anthropic", "cost_usd": 50},
    ]), encoding="utf-8")
    monkeypatch.setenv("WATCHDOG_API_CREDIT_SNAPSHOT_USD", "5")
    monkeypatch.setenv("WATCHDOG_API_CREDIT_SNAPSHOT_AT", "2026-09-23T07:00:00")
    monkeypatch.setenv("WATCHDOG_API_CREDIT_LOW_USD", "2")
    monkeypatch.setattr(watchdog, "COST_LOG_PATH", str(cost_path))
    monkeypatch.setattr(watchdog, "_check_sync_stale", lambda: (False, 0))
    monkeypatch.setattr(watchdog, "_check_tunnel_mismatch", lambda: (False, None, None))
    state = {}
    monkeypatch.setattr(watchdog, "_load_state", lambda: dict(state))
    monkeypatch.setattr(watchdog, "_save_state", lambda new: state.update(new))
    alerts = []
    monkeypatch.setattr(watchdog, "_send_teams_alert", lambda title, summary, severity="WARNING": alerts.append((title, summary, severity)) or True)
    watchdog.run_check()
    watchdog.run_check()
    assert len(alerts) == 1
    assert "1.90" in alerts[0][1]
    assert "ước tính" in alerts[0][1].lower()
    assert state["api_credit_low_alerted"] is True


def test_watchdog_without_balance_snapshot_stays_unknown(monkeypatch):
    monkeypatch.delenv("WATCHDOG_API_CREDIT_SNAPSHOT_USD", raising=False)
    monkeypatch.delenv("WATCHDOG_API_CREDIT_SNAPSHOT_AT", raising=False)
    assert watchdog._check_api_credit() == (None, None, None)


def test_watchdog_alerts_on_recent_credit_rejection_without_snapshot(monkeypatch, tmp_path):
    memory_db = tmp_path / "memory.db"
    created_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(memory_db) as conn:
        conn.execute("CREATE TABLE query_runs (created_at TEXT, username TEXT, status TEXT, error_message TEXT)")
        conn.execute("INSERT INTO query_runs VALUES (?, ?, ?, ?)",
                     (created_at, "uat.user", "error", "Your credit balance is too low"))
    monkeypatch.setattr(watchdog, "MEMORY_DB", str(memory_db))
    monkeypatch.delenv("WATCHDOG_API_CREDIT_SNAPSHOT_USD", raising=False)
    monkeypatch.delenv("WATCHDOG_API_CREDIT_SNAPSHOT_AT", raising=False)
    monkeypatch.setattr(watchdog, "_check_sync_stale", lambda: (False, 0))
    monkeypatch.setattr(watchdog, "_check_tunnel_mismatch", lambda: (False, None, None))
    state = {}
    monkeypatch.setattr(watchdog, "_load_state", lambda: dict(state))
    monkeypatch.setattr(watchdog, "_save_state", lambda new: state.update(new))
    alerts = []
    monkeypatch.setattr(watchdog, "_send_teams_alert", lambda *args, **kwargs: alerts.append(args) or True)
    watchdog.run_check()
    watchdog.run_check()
    assert len(alerts) == 1
    assert "HET credit" in alerts[0][0]
    assert state["api_credit_exhausted_alerted"] is True
