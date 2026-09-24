"""Khong de luot chat ket thuc/restart bi treo running trong so cai UAT."""
import asyncio
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import conversation_memory as memory


def _main():
    spec = importlib.util.spec_from_file_location("dnh_running_test_main", BACKEND / "main.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _db(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()


def test_stream_ket_thuc_khong_done_duoc_dong_va_bao_loi(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    main = _main()
    monkeypatch.setattr(main, "_business_scopes", lambda user: (None, None, None))
    monkeypatch.setattr(main, "_check_rate_limit", lambda username: None)
    monkeypatch.setattr(main, "register_session", lambda *args: None)
    monkeypatch.setattr(main, "_require_session_write_access", lambda *args: None)
    monkeypatch.setattr(main, "_quota_for_question", lambda *args: {})

    def incomplete(*args, **kwargs):
        yield {"type": "text", "text": "Mot phan"}

    monkeypatch.setattr(main, "ask_stream", incomplete)
    response = main.chat_stream(
        main.ChatRequest(question="Doanh thu?", session_id="web-test-1"),
        {"username": "uat.test", "role": "c_level"},
    )

    async def collect():
        return [part async for part in response.body_iterator]

    events = [json.loads(part.removeprefix("data: ")) for part in asyncio.run(collect())]
    run = memory.get_query_run(events[-1]["query_id"])
    assert events[-1]["code"] == "stream_incomplete"
    assert run["status"] == "abandoned"
    assert "without done" in run["error_message"]


def test_startup_chi_dong_running_qua_lau_va_giu_dau_tool(tmp_path, monkeypatch):
    _db(tmp_path, monkeypatch)
    for query_id in ("old", "recent", "complete"):
        memory.create_query_run(query_id, "web-test", "uat.test", "Cau hoi")
    memory.update_query_run_progress("old", ["tool:get_revenue_by_channel"])
    memory.complete_query_run("complete", "Da tra loi")
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat(timespec="seconds")
    with sqlite3.connect(memory.DB_PATH) as conn:
        conn.execute("UPDATE query_runs SET created_at=? WHERE query_id='old'", (old_time,))

    main = _main()
    main.close_stale_query_runs_on_startup()
    old = memory.get_query_run("old")
    assert old["status"] == "abandoned"
    # Sau restart khong biet request dung luc nao; thoi gian den startup khong phai runtime.
    assert old["duration_ms"] is None
    assert old["sql_used"] == ["tool:get_revenue_by_channel"]
    assert memory.get_query_run("recent")["status"] == "running"
    assert memory.get_query_run("complete")["status"] == "completed"
    main.close_stale_query_runs_on_startup()
    assert memory.get_query_run("old")["status"] == "abandoned"
