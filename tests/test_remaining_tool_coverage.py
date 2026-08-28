# -*- coding: utf-8 -*-
"""Test truc tiep 3/40 cong cu cuoi cung chua co coverage rieng truoc 28/08/2026."""
import json
import os
import sqlite3
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import conversation_memory
import local_warehouse
import report_templates as rt


def _make_employee_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE dim_nhanvien (
            employee_code TEXT, dmsid TEXT, name TEXT, position_code TEXT,
            area_code TEXT, is_duplicate INTEGER
        );
        CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        """
    )
    conn.executemany("INSERT INTO dim_chucvu VALUES (?,?)", [
        ("TDV", "Trinh duoc vien"), ("QLV", "Quan ly vung"),
    ])
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?)", [
        ("NV01", "DMS-TRUNG", "Anh MB", "TDV", "MB", 0),
        ("NV02", "DMS-TRUNG", "Binh MB", "QLV", "MB", 1),
        ("NV03", "DMS-MN", "Cuong MN", "TDV", "MN", 0),
    ])
    conn.execute("INSERT INTO dmssx_nhanvien VALUES (?,?,?)", ("SX01", "SALE01", "Dung ETC"))
    conn.commit()
    conn.close()


def test_employee_directory_giu_du_ma_trung_va_tra_nhan_vai_tro(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_employee_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.employee_directory(search="DMS-TRUNG")

    assert [row["employee_code"] for row in rows] == ["NV01", "NV02"]
    assert {row["is_duplicate"] for row in rows} == {0, 1}
    assert {row["position_label"] for row in rows} == {"Trinh duoc vien", "Quan ly vung"}


def test_employee_directory_scope_vung_ghi_de_tham_so_va_limit_duoc_chan(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_employee_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.employee_directory(area_code="MN", scope_area_code="MB", limit=-1)

    assert len(rows) == 1
    assert rows[0]["area_code"] == "MB"


def test_employee_directory_tim_duoc_nhan_vien_etc_chi_co_o_dmssx(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_employee_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    rows = rt.employee_directory(search="SALE01")

    assert rows == [{
        "employee_code": "SX01", "dmsid": "SALE01", "name": "Dung ETC",
        "position_code": None, "position_label": None, "area_code": None,
        "is_duplicate": 0,
    }]


def _make_receivables_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE fact_congno_khachhang_history (snapshot_date TEXT)")
    conn.executemany("INSERT INTO fact_congno_khachhang_history VALUES (?)", [
        ("2026-08-21",), ("2026-08-22",), ("2026-08-22",), ("2026-08-27",),
    ])
    conn.commit()
    conn.close()


def test_receivables_history_dates_distinct_moi_nhat_va_gioi_han(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_receivables_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.receivables_history_dates(limit=2)

    assert result["so_ngay_co_du_lieu"] == 2
    assert result["cac_ngay"] == ["2026-08-27", "2026-08-22"]
    assert "21/08/2026" in result["ghi_chu"]


def test_receivables_history_dates_limit_am_khong_duoc_tra_toan_bo(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_receivables_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    result = rt.receivables_history_dates(limit=-1)
    assert result["cac_ngay"] == ["2026-08-27"]


def test_receivables_history_dates_exempt_scope_khong_bi_ep_tham_so_la(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_receivables_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt, "_write_log", lambda _entry: None)

    wrapped = rt.call_template(
        "get_receivables_history_dates", {"limit": 2},
        scope_area_code="MB", scope_channel="ETC", scope_role="regional_director",
    )

    assert wrapped["ok"] is True
    assert wrapped["result"]["cac_ngay"] == ["2026-08-27", "2026-08-22"]


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _setup_audit_files(tmp_path, monkeypatch):
    audit_path = tmp_path / "audit.jsonl"
    cost_path = tmp_path / "cost.jsonl"
    memory_path = tmp_path / "memory.db"
    _write_jsonl(audit_path, [
        {"ts": "2026-08-28T08:00:00", "username": "alice", "session_id": "s1",
         "question": "Doanh thu?", "sql": "<template:get_revenue_by_channel>({})",
         "status": "ok", "row_count": 1, "duration_ms": 10},
        {"ts": "2026-08-28T08:00:01", "username": "alice", "session_id": "s1",
         "question": "Doanh thu?", "sql": "SELECT 1", "status": "ok", "row_count": 1},
        {"ts": "2026-08-28T08:05:00", "username": "bob", "session_id": "s2",
         "question": "Cong no?", "sql": "<template:get_receivables_overview>({})",
         "status": "ok", "row_count": 1, "duration_ms": 20},
    ])
    _write_jsonl(cost_path, [
        {"ts": "2026-08-28T08:00:02", "username": "alice", "session_id": "s1",
         "question_preview": "Doanh thu?", "cost_usd": 0.1, "input_tokens": 10,
         "output_tokens": 2},
        {"ts": "2026-08-28T08:00:03", "username": "alice", "session_id": "s1",
         "question_preview": "Doanh thu?", "cost_usd": 0.2, "input_tokens": 20,
         "output_tokens": 3},
        {"ts": "2026-08-28T08:05:01", "username": "bob", "session_id": "s2",
         "question_preview": "Cong no?", "cost_usd": 0.5, "input_tokens": 50,
         "output_tokens": 5},
    ])
    conn = sqlite3.connect(memory_path)
    conn.execute("CREATE TABLE sessions (session_id TEXT, owner_username TEXT)")
    conn.executemany("INSERT INTO sessions VALUES (?,?)", [("s1", "alice"), ("s2", "bob")])
    conn.commit()
    conn.close()
    monkeypatch.setattr(rt, "AUDIT_LOG_PATH", str(audit_path))
    monkeypatch.setattr(rt, "COST_LOG_PATH", str(cost_path))
    monkeypatch.setattr(conversation_memory, "DB_PATH", str(memory_path))


def test_audit_log_tai_khoan_thuong_khong_the_tu_nang_quyen(tmp_path, monkeypatch):
    _setup_audit_files(tmp_path, monkeypatch)

    wrapped = rt.call_template(
        "get_audit_log",
        {"days": 0, "limit": 30, "username": "bob", "scope_role": "c_level",
         "target_username": "bob"},
        username="alice", scope_role="qlv", session_id="audit-test",
    )

    assert wrapped["ok"] is True
    result = wrapped["result"]
    assert result["scope"] == "ca nhan alice"
    assert result["total_queries"] == 1
    assert result["total_cost_usd"] == 0.3
    assert result["total_tokens"] == 35
    assert result["user_breakdown"] is None
    assert {row["username"] for row in result["history"]} == {"alice"}


def test_audit_log_clevel_loc_mot_nguoi_thi_ca_lich_su_va_chi_phi_cung_scope(tmp_path, monkeypatch):
    _setup_audit_files(tmp_path, monkeypatch)

    result = rt.audit_log_summary(
        days=0, target_username="bob", username="dnh", scope_role="c_level",
    )

    assert result["scope"] == "nguoi dung bob"
    assert result["total_queries"] == 1
    assert result["total_cost_usd"] == 0.5
    assert result["total_tokens"] == 55
    assert result["user_breakdown"] is None
    assert {row["username"] for row in result["history"]} == {"bob"}


def test_audit_log_toan_cong_ty_tach_chi_phi_theo_nguoi_va_limit_duoc_chan(tmp_path, monkeypatch):
    _setup_audit_files(tmp_path, monkeypatch)

    result = rt.audit_log_summary(
        days=0, limit=-1, target_username="all", username="dnh", scope_role="c_level",
    )

    assert len(result["history"]) == 1
    assert result["total_queries"] == 2
    assert result["total_cost_usd"] == 0.8
    by_user = {row["username"]: row for row in result["user_breakdown"]}
    assert by_user["alice"]["queries"] == 1
    assert by_user["alice"]["cost_usd"] == 0.3
    assert by_user["bob"]["queries"] == 1
    assert by_user["bob"]["cost_usd"] == 0.5
