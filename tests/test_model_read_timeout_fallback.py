"""Model read timeouts return an honest partial answer; no paid API is called."""

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

import conversation_memory as memory  # noqa: E402
import nl2sql  # noqa: E402
from test_data_freshness import _patch_nl2sql_runtime  # noqa: E402


QUESTION = "Doanh thu tháng 8/2026 là bao nhiêu?"


class FakeStream:
    def __init__(self, message=None, error=None):
        self.message = message
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        if self.error:
            raise self.error
        return iter(())

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self, stage, error_type=TimeoutError):
        self.stage = stage
        self.error_type = error_type
        self.calls = 0

    def _next(self):
        self.calls += 1
        should_timeout = (self.stage == "first" and self.calls == 1) or (
            self.stage in {"retry", "after_tool", "final"} and self.calls == 2
        )
        if should_timeout:
            return None, self.error_type("The read operation timed out")
        if self.stage == "retry" and self.calls == 1:
            return SimpleNamespace(content=[SimpleNamespace(type="text", text="")],
                                   usage=SimpleNamespace()), None
        return SimpleNamespace(content=[SimpleNamespace(
            type="tool_use", id="tool-1", name="get_revenue_by_channel",
            input={"date_from": "2026-08-01", "date_to": "2026-08-31"},
        )], usage=SimpleNamespace()), None

    def create(self, **kwargs):
        message, error = self._next()
        if error:
            raise error
        return message

    def stream(self, **kwargs):
        message, error = self._next()
        return FakeStream(message, error)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("stage", ["first", "retry", "after_tool", "final"])
def test_read_timeout_returns_partial_answer_and_preserves_tool_trace(
    tmp_path, monkeypatch, streaming, stage,
):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    memory.create_query_run("q-timeout", "unit-timeout", "tester", QUESTION)
    messages = FakeMessages(stage)
    appended = []
    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=messages), appended)
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "test")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *args: "test")
    monkeypatch.setattr(nl2sql, "call_template", lambda *args, **kwargs: {
        "ok": True, "result": {"revenue": 123, "data_as_of": "2026-08-31"},
    })
    if stage == "final":
        monkeypatch.setattr(nl2sql, "_max_tool_rounds", lambda *args: 1)

    kwargs = dict(session_id="unit-timeout", username="tester", query_id="q-timeout")
    if streaming:
        events = list(nl2sql.ask_stream(QUESTION, **kwargs))
        result = events[-1]
        assert [event["type"] for event in events] == ["text_delta", "done"]
        assert events[0]["text"] == result["answer"]
    else:
        result = nl2sql.ask(QUESTION, **kwargs)

    assert "Hết thời gian" in result["answer"]
    assert "123" not in result["answer"]  # no unsupported number in fallback
    assert result["query_plan"]["status"] == "partial"
    assert result["completion_status"] == "partial_timeout"
    assert appended[-1][2] == result["answer"]
    if stage in {"first", "retry"}:
        assert result["sql_used"] == []
    else:
        assert len(result["sql_used"]) == 1
        assert "get_revenue_by_channel" in result["sql_used"][0]
    run = memory.get_query_run("q-timeout")
    assert run["sql_used"] == result["sql_used"]
    memory.complete_query_run(
        "q-timeout", result["answer"], sql_used=result["sql_used"],
        status=result["completion_status"], error_message=result["timeout_error"],
    )
    run = memory.get_query_run("q-timeout")
    assert run["status"] == "partial_timeout"
    assert run["error_message"] == "The read operation timed out"


def test_failed_run_keeps_tool_trace_written_before_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    memory.create_query_run("q-failed", "s", "tester", QUESTION)
    memory.update_query_run_progress("q-failed", ["[bao cao chuan] get_revenue_by_channel({})"])
    memory.fail_query_run("q-failed", "The read operation timed out", status="error")
    run = memory.get_query_run("q-failed")
    assert run["status"] == "error"
    assert run["sql_used"] == ["[bao cao chuan] get_revenue_by_channel({})"]


def test_non_timeout_model_failure_still_raises(monkeypatch):
    class BadMessages:
        def create(self, **kwargs):
            raise ValueError("Bad response")

    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=BadMessages()), [])
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "test")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *args: "test")
    with pytest.raises(ValueError, match="Bad response"):
        nl2sql.ask(QUESTION, session_id="unit-non-timeout", username="tester")


def test_chat_endpoint_records_partial_timeout_as_distinct_status(tmp_path, monkeypatch):
    from backend import main as api_main

    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    monkeypatch.setattr(api_main, "_business_scopes", lambda user: (None, None, None))
    monkeypatch.setattr(api_main, "_check_rate_limit", lambda username: None)
    monkeypatch.setattr(api_main, "register_session", lambda *args: None)
    monkeypatch.setattr(api_main, "_require_session_write_access", lambda *args: None)
    monkeypatch.setattr(api_main, "_quota_for_question", lambda *args: {})
    monkeypatch.setattr(api_main, "ask", lambda *args, **kwargs: {
        "answer": "Hết thời gian xử lý; chưa thể kết luận đầy đủ.",
        "sql_used": ["[bao cao chuan] get_revenue_by_channel({})"],
        "completion_status": "partial_timeout",
        "timeout_error": "The read operation timed out",
        "query_plan": {"status": "partial"},
    })

    response = api_main.chat(api_main.ChatRequest(question=QUESTION, session_id="unit-timeout"),
                             user={"username": "tester", "role": "c_level"})
    run = memory.get_query_run(response.query_id)
    assert response.completion_status == "partial_timeout"
    assert run["status"] == "partial_timeout"
    assert run["sql_used"] == ["[bao cao chuan] get_revenue_by_channel({})"]
    assert run["error_message"] == "The read operation timed out"
