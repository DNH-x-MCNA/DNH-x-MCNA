"""Mandatory tool caveats reach the final answer even when the fake model omits them."""
from types import SimpleNamespace

import pytest

from test_query_plan import _plan
from test_data_freshness import _patch_nl2sql_runtime
import nl2sql


MESSAGE = (
    "Chưa có dữ liệu đội hình cho kỳ đến 2025-12-31. "
    "Báo cáo dùng đội hình tại 2026-06-30; thành viên có thể khác kỳ được hỏi."
)
WARNING = {"code": "historical_team_roster_after_period", "severity": "warning", "message": MESSAGE}
INTERNAL = "DOI LICH SU KHONG CO SNAPSHOT: PHAI noi ro, khong duoc khang dinh doi hinh dung ky."


class FakeStream:
    def __init__(self, message=None, error=None):
        self.message, self.error = message, error

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __iter__(self):
        if self.error:
            raise self.error
        # Intermediate model text must not be emitted ahead of the final caveat.
        return iter([SimpleNamespace(type="text", text="Bản nháp chưa kiểm tra.")])

    def get_final_message(self):
        return self.message


class FakeMessages:
    def __init__(self, draft, mode):
        self.draft, self.mode, self.calls = draft, mode, 0

    def _next(self):
        self.calls += 1
        if self.calls == 1:
            content = [SimpleNamespace(type="tool_use", id="t1", name="get_revenue_by_channel",
                                       input={"date_from": "2025-12-01", "date_to": "2025-12-31"})]
        elif self.mode == "timeout":
            return None, TimeoutError("The read operation timed out")
        elif self.mode == "later_clean_tool" and self.calls == 2:
            content = [SimpleNamespace(type="tool_use", id="t2", name="get_revenue_by_region", input={})]
        else:
            content = [SimpleNamespace(type="text", text=self.draft)]
        return SimpleNamespace(content=content, usage=SimpleNamespace()), None

    def create(self, **kwargs):
        message, error = self._next()
        if error:
            raise error
        return message

    def stream(self, **kwargs):
        return FakeStream(*self._next())


def run_fake(monkeypatch, *, streaming, mode="normal", draft="Doanh thu: 100 đồng.", warning=WARNING):
    appended = []
    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=FakeMessages(draft, mode)), appended)
    monkeypatch.setattr(nl2sql, "_static_system_prompt", lambda: "test")
    monkeypatch.setattr(nl2sql, "_dynamic_context_note", lambda *args: "test")
    monkeypatch.setattr(nl2sql, "update_query_run_progress", lambda *args: None)

    def template(name, *args, **kwargs):
        if name == "get_revenue_by_region":
            return {"ok": True, "result": {"revenue": 100}}
        payload = ({"otc": {"revenue": 40}, "etc": {"revenue": 60}, "total": {"revenue": 150}}
                   if mode == "reconciliation_failed" else {"revenue": 100})
        return {"ok": True, "result": payload, "canh_bao": [INTERNAL], "user_warnings": [warning]}

    monkeypatch.setattr(nl2sql, "call_template", template)
    if mode == "forced":
        monkeypatch.setattr(nl2sql, "_max_tool_rounds", lambda *args: 1)
    kwargs = dict(session_id="unit-warning", username="unit-test", query_id="q-warning")
    question = "Doanh thu tháng 12/2025"
    if streaming:
        events = list(nl2sql.ask_stream(question, **kwargs))
        result = events[-1]
        assert result["type"] == "done"
        assert "".join(e["text"] for e in events if e["type"] == "text_delta") == result["answer"]
    else:
        result = nl2sql.ask(question, **kwargs)
    assert appended[-1][2] == result["answer"]
    assert "Bản nháp chưa kiểm tra" not in result["answer"]
    return result


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("mode", ["normal", "forced", "timeout", "later_clean_tool", "reconciliation_failed"])
def test_omitted_warning_reaches_every_final_answer_path(monkeypatch, streaming, mode):
    result = run_fake(monkeypatch, streaming=streaming, mode=mode)
    assert MESSAGE in result["answer"]
    assert result["answer"].count(MESSAGE) == 1
    assert INTERNAL not in result["answer"]
    assert result["query_plan"]["user_warnings"] == [WARNING]
    if mode == "timeout":
        assert result["completion_status"] == "partial_timeout"


@pytest.mark.parametrize("streaming", [False, True])
def test_already_disclosed_warning_is_not_repeated(monkeypatch, streaming):
    draft = "Doanh thu: 100 đồng.\n\n" + MESSAGE
    result = run_fake(monkeypatch, streaming=streaming, draft=draft)
    assert result["answer"].count(MESSAGE) == 1
    assert "### Lưu ý về số liệu" not in result["answer"]


@pytest.mark.parametrize("streaming", [False, True])
def test_valid_salary_snapshot_info_is_not_a_user_warning(monkeypatch, streaming):
    info = {"code": "team_roster_salary_snapshot", "severity": "info",
            "message": "Đội hình đã được chốt đúng kỳ bằng dữ liệu lương."}
    result = run_fake(monkeypatch, streaming=streaming, warning=info)
    assert info["message"] not in result["answer"]
    assert "### Lưu ý về số liệu" not in result["answer"]


def test_warning_does_not_prevent_removing_fake_model_freshness(monkeypatch):
    result = run_fake(monkeypatch, streaming=False,
                      draft="Doanh thu: 100 đồng.\n\n_Du lieu cap nhat den 15:22 13/08/2026._")
    assert "15:22" not in result["answer"]
    assert MESSAGE in result["answer"]


def test_warning_collection_deduplicates_but_keeps_different_periods_and_requests_separate():
    plan = _plan()
    later = {**WARNING, "message": MESSAGE.replace("2025-12-31", "2026-01-31")}
    plan.record_tool_warnings([WARNING, WARNING, later])
    result = plan.finalize_warnings("Có dữ liệu.")
    assert result.count("Chưa có dữ liệu đội hình cho kỳ đến 2025-12-31") == 1
    assert "2026-01-31" in result
    assert plan.finalize_warnings(result) == result
    assert _plan(query_id="other").finalize_warnings("Không cảnh báo.") == "Không cảnh báo."


def test_existing_sentences_are_compared_without_accents_or_markdown():
    plan = _plan()
    plan.record_tool_warnings([WARNING])
    draft = ("**Chua co du lieu doi hinh cho ky den 2025-12-31.**\n"
             "Bao cao dung doi hinh tai 2026-06-30; thanh vien co the khac ky duoc hoi.")
    assert plan.finalize_warnings(draft) == draft


def test_generic_disclaimer_does_not_hide_specific_caveat():
    plan = _plan()
    plan.record_tool_warnings([WARNING])
    result = plan.finalize_warnings("Lưu ý: dữ liệu có thể chưa đủ.")
    assert MESSAGE in result


def test_only_missing_sentence_is_appended():
    plan = _plan()
    plan.record_tool_warnings([WARNING])
    first, second = MESSAGE.split(". ", 1)
    draft = "Doanh thu: 100 đồng. " + first + "."
    result = plan.finalize_warnings(draft)
    assert result.count(first) == 1
    assert second in result


def test_negating_the_warning_is_not_counted_as_disclosing_it():
    plan = _plan()
    plan.record_tool_warnings([WARNING])
    draft = "Không đúng rằng " + MESSAGE.replace(". ", ". Không đúng rằng ", 1)
    result = plan.finalize_warnings(draft)
    assert "### Lưu ý về số liệu" in result
    assert MESSAGE in result
