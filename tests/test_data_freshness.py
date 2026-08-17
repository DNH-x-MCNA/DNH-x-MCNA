import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
from backend import conversation_memory as memory
from backend.data_freshness import FreshnessCollector, strip_model_freshness_footer


TZ7 = timezone(timedelta(hours=7))
NOW = datetime(2026, 8, 17, 10, 0, 0, tzinfo=TZ7)


def make_warehouse(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT);
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT);
        CREATE TABLE fact_tonghopkhachhang (save_date TEXT);
        CREATE TABLE fact_thongketinhluong (save_date TEXT);
        CREATE TABLE sync_meta (
            table_name TEXT PRIMARY KEY,
            last_synced_at TEXT,
            earliest_synced_date TEXT,
            latest_synced_date TEXT
        );
        """
    )
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-08-16')")
    conn.execute("INSERT INTO vhoadon_etc VALUES ('2026-08-15')")
    conn.execute("INSERT INTO fact_congno_khachhang VALUES (?, ?)",
                 ("2026-08-17", "2026-08-17T09:20:00+07:00"))
    conn.executemany(
        "INSERT INTO sync_meta VALUES (?, ?, ?, ?)",
        [
            ("vhoadon_otc", "2026-08-17T09:30:00+07:00", "2026-01-01", "2026-08-16"),
            ("vhoadon_etc", "2026-08-17T09:35:00+07:00", "2026-01-01", "2026-08-15"),
            ("fact_congno_khachhang", "2026-08-17T09:25:00+07:00", "2026-08-17", "2026-08-17"),
        ],
    )
    conn.commit()
    conn.close()
    return str(path)


def collector_for(path, *, stale_minutes=90, now=NOW):
    return FreshnessCollector(
        warehouse_path=path,
        stale_minutes=stale_minutes,
        now=lambda: now,
    )


def test_single_local_source_uses_exact_business_and_sync_times(tmp_path):
    collector = collector_for(make_warehouse(tmp_path))

    collector.record_template(
        "get_top_products", [{"revenue": 100}], args={"channel": "OTC"}
    )

    records = collector.records()
    assert len(records) == 1
    assert records[0].source_key == "sales_otc"
    assert records[0].business_data_date == "2026-08-16"
    assert records[0].sync_completed_at == "2026-08-17T09:30:00+07:00"
    assert records[0].is_stale is False
    answer = collector.finalize_answer("Doanh thu là 100 đồng.")
    assert "dữ liệu đến 16/08/2026" in answer
    assert "đồng bộ lúc 09:30 17/08/2026" in answer


def test_debt_uses_snapshot_metadata(tmp_path):
    collector = collector_for(make_warehouse(tmp_path))

    collector.record_template(
        "get_receivables_overview",
        {"snapshot_date": "2026-08-17", "receivable_snapshot_at": "2026-08-17T09:20:00+07:00"},
    )

    record = collector.records()[0]
    assert record.source_key == "debt"
    assert record.snapshot_date == "2026-08-17"
    assert "snapshot 17/08/2026" in collector.finalize_answer("Công nợ là 1 tỷ.")


def test_multiple_sources_are_deduplicated_and_keep_stable_order(tmp_path):
    collector = collector_for(make_warehouse(tmp_path))

    collector.record_template("get_revenue_by_channel", {"total": {"revenue": 1}})
    collector.record_template("get_revenue_by_channel", {"total": {"revenue": 2}})

    assert [item.source_key for item in collector.records()] == ["sales_otc", "sales_etc"]
    assert collector.finalize_answer("Kết quả.").count("Nguồn dữ liệu:") == 1


def test_live_sql_records_query_execution_time_without_stale_warning(tmp_path):
    collector = collector_for(make_warehouse(tmp_path))

    collector.record_raw("bravo", {"ok": True, "row_count": 1}, "SELECT COUNT_BIG(*) FROM dbo.DMS_CTKM")

    record = collector.records()[0]
    assert record.source_key == "sql_server"
    assert record.is_live is True
    assert record.is_stale is False
    assert record.query_executed_at == "2026-08-17T10:00:00+07:00"
    assert "truy vấn lúc 10:00 17/08/2026" in collector.finalize_answer("Có 7.235 dòng.")


def test_old_model_generated_footer_is_removed_only_at_the_end(tmp_path):
    collector = collector_for(make_warehouse(tmp_path))
    collector.record_raw("bravo", {"ok": True}, "SELECT 1")
    raw = "Kết quả thực tế.\n\n_Du lieu cap nhat den 15:22 13/08/2026._"

    answer = collector.finalize_answer(raw)

    assert "15:22 13/08/2026" not in answer
    assert answer.count("Dữ liệu trực tiếp:") == 1
    assert strip_model_freshness_footer("Cụm 'dữ liệu cập nhật' ở giữa câu vẫn còn.")


def test_stale_threshold_is_configurable_and_warning_is_deterministic(tmp_path):
    path = make_warehouse(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE sync_meta SET last_synced_at=? WHERE table_name='vhoadon_otc'",
        ("2026-08-17T07:00:00+07:00",),
    )
    conn.commit()
    conn.close()
    collector = collector_for(path, stale_minutes=90)

    collector.record_template("get_top_products", [], args={"channel": "OTC"})

    record = collector.records()[0]
    assert record.is_stale is True
    assert "180 phút" in record.warning
    assert "ngưỡng tạm thời 90 phút" in collector.finalize_answer("Kết quả.")


def test_future_dated_rows_are_not_shown_as_data_freshness(tmp_path):
    path = make_warehouse(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO vhoadon_otc VALUES ('2026-08-31')")
    conn.commit()
    conn.close()

    collector = collector_for(path)
    collector.record_template("get_revenue_by_channel", {"total": {"revenue": 1}})

    otc = collector.records()[0]
    assert otc.business_data_date == "2026-08-16"
    assert "ngày tương lai 31/08/2026" in otc.warning
    footer = collector.finalize_answer("Kết quả.")
    assert "dữ liệu đến 16/08/2026" in footer
    assert "dữ liệu đến 31/08/2026" not in footer


def test_collectors_are_isolated_between_concurrent_requests(tmp_path):
    path = make_warehouse(tmp_path)
    revenue_request = collector_for(path)
    live_request = collector_for(path)

    revenue_request.record_template("get_top_products", [], args={"channel": "OTC"})
    live_request.record_raw("bravo", {"ok": True}, "SELECT 1")

    assert [item.source_key for item in revenue_request.records()] == ["sales_otc"]
    assert [item.source_key for item in live_request.records()] == ["sql_server"]


def test_query_run_persists_structured_freshness(tmp_path, monkeypatch):
    db_path = tmp_path / "memory.db"
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))
    memory.init()
    freshness = [{"source_key": "sql_server", "is_live": True}]
    memory.create_query_run("q-fresh", "s-fresh", "alice", "Có bao nhiêu CTKM?")

    memory.complete_query_run("q-fresh", "7.235", freshness=freshness)

    assert memory.get_query_run("q-fresh")["freshness"] == freshness
    assert memory.list_query_runs(limit=1)[0]["freshness"] == freshness


def test_init_adds_freshness_column_to_existing_query_runs(tmp_path, monkeypatch):
    db_path = tmp_path / "old-memory.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE query_runs (
            query_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, username TEXT NOT NULL,
            question TEXT NOT NULL, answer TEXT, status TEXT NOT NULL DEFAULT 'running',
            sql_used_json TEXT, row_count INTEGER, duration_ms INTEGER, error_message TEXT,
            feedback_rating INTEGER, feedback_category TEXT, feedback_comment TEXT,
            feedback_by TEXT, feedback_at TEXT, created_at TEXT NOT NULL, completed_at TEXT
        )"""
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(memory, "DB_PATH", str(db_path))

    memory.init()

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(query_runs)")}
    conn.close()
    assert "freshness_json" in columns


def _patch_nl2sql_runtime(monkeypatch, fake_client, appended):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(nl2sql, "_llm_client", lambda: fake_client)
    monkeypatch.setattr(nl2sql, "load_history", lambda *args, **kwargs: [])
    monkeypatch.setattr(nl2sql, "append_message", lambda *args, **kwargs: appended.append(args))
    monkeypatch.setattr(nl2sql, "set_query_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(nl2sql, "compute_and_log_cost", lambda *args, **kwargs: None)

    class FixedCollector(FreshnessCollector):
        def __init__(self):
            super().__init__(warehouse_path="missing.db", now=lambda: NOW)

    monkeypatch.setattr(nl2sql, "FreshnessCollector", FixedCollector)
    monkeypatch.setattr(
        nl2sql,
        "call_template",
        lambda *args, **kwargs: {"ok": True, "result": {"promotion_link_coverage_to": "2026-08-16"}},
    )


def test_ask_replaces_model_timestamp_and_persists_final_answer(monkeypatch):
    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def create(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = [SimpleNamespace(type="tool_use", id="tool-1", name="get_promotion_effectiveness", input={})]
            else:
                content = [SimpleNamespace(
                    type="text",
                    text="Có 3 chương trình.\n\n_Du lieu cap nhat den 15:22 13/08/2026._",
                )]
            return SimpleNamespace(content=content, usage=SimpleNamespace())

    appended = []
    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=FakeMessages()), appended)

    result = nl2sql.ask("Đánh giá CTKM", session_id="s", query_id="q")

    assert "13/08/2026" not in result["answer"]
    assert result["answer"].count("Dữ liệu trực tiếp:") == 1
    assert appended[-1][2] == result["answer"]
    assert result["freshness"][0]["source_key"] == "promotion_live"


def test_ask_stream_emits_exactly_the_final_persisted_answer(monkeypatch):
    class FakeStream:
        def __init__(self, message):
            self.message = message

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def __iter__(self):
            block = self.message.content[0]
            if block.type == "tool_use":
                yield SimpleNamespace(type="content_block_start", content_block=block)
            else:
                yield SimpleNamespace(type="text", text=block.text[:10])
                yield SimpleNamespace(type="text", text=block.text[10:])

        def get_final_message(self):
            return self.message

    class FakeMessages:
        def __init__(self):
            self.calls = 0

        def stream(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                content = [SimpleNamespace(type="tool_use", id="tool-1", name="get_promotion_effectiveness", input={})]
            else:
                content = [SimpleNamespace(
                    type="text",
                    text="Có 3 chương trình.\n\n_Du lieu cap nhat den 15:22 13/08/2026._",
                )]
            return FakeStream(SimpleNamespace(content=content, usage=SimpleNamespace()))

    appended = []
    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=FakeMessages()), appended)

    chunks = list(nl2sql.ask_stream("Đánh giá CTKM", session_id="s", query_id="q"))
    done = chunks[-1]
    streamed = "".join(chunk["text"] for chunk in chunks if chunk["type"] == "text_delta")

    assert streamed == done["answer"] == appended[-1][2]
    assert "13/08/2026" not in done["answer"]
    assert done["answer"].count("Dữ liệu trực tiếp:") == 1
    assert done["freshness"][0]["source_key"] == "promotion_live"
