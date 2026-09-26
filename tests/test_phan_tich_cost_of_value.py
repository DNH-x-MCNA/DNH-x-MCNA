"""Script Cost of Value (hop 24/09): chi doc, gop vong goi model thanh luot, noi query_runs lay ket qua, phan loai
luot khong ra gia tri va tool goi trung, loai luot kiem thu. Du lieu gia."""
import importlib.util
import json
import sqlite3
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]


def _nap(monkeypatch, tmp_path):
    cost = tmp_path / "cost_log.jsonl"
    dong = [
        # luot 1: 2 vong, tra loi co tool, goi trung 1 lan
        {"ts": "2026-09-20T09:00:00", "session_id": "s1", "username": "qlv_a", "question_preview": "Doanh thu doi toi thang 9", "cost_usd": 0.10},
        {"ts": "2026-09-20T09:00:30", "session_id": "s1", "username": "qlv_a", "question_preview": "Doanh thu doi toi thang 9", "cost_usd": 0.10},
        # luot 2: het gio
        {"ts": "2026-09-20T10:00:00", "session_id": "s2", "username": "sep", "question_preview": "So sanh doanh thu thang 8 voi thang 7", "cost_usd": 0.50},
        # luot 3: chi hoi lai
        {"ts": "2026-09-20T11:00:00", "session_id": "s3", "username": "sep", "question_preview": "KPI the nao", "cost_usd": 0.05},
        # luot kiem thu -> bi loai mac dinh
        {"ts": "2026-09-20T12:00:00", "session_id": "cham-01", "username": "cham_uat", "question_preview": "x", "cost_usd": 9.0},
        # cham lai UAT chay bang TAI KHOAN THAT (qlv_a) - phai nhan theo session "chamlai..." (26/09: tung bi tinh that)
        {"ts": "2026-09-24T15:06:00", "session_id": "chamlai2409-02", "username": "qlv_a", "question_preview": "danh sach khach moi", "cost_usd": 7.0},
        {"ts": "2026-09-10T15:00:00", "session_id": "beval-1", "username": "business-eval", "question_preview": "y", "cost_usd": 3.0},
        # nguoi dung that nhung khong co trong auth.db, luot loi
        {"ts": "2026-09-21T09:00:00", "session_id": "s4", "username": "nguoi_cu", "question_preview": "Top SKU mien Bac", "cost_usd": 0.20},
        # cung session + cau hoi hai lan: lan 1 hong ket noi (khong co dong cost), lan 2 tra loi luc 08:05 dia phuong
        {"ts": "2026-09-22T08:05:10", "session_id": "s5", "username": "qlv_a", "question_preview": "Cong no doi", "cost_usd": 0.30},
    ]
    cost.write_text("\n".join(json.dumps(d) for d in dong), encoding="utf-8")
    mem = tmp_path / "memory.db"
    c = sqlite3.connect(mem)
    c.execute("CREATE TABLE query_runs (query_id TEXT, session_id TEXT, username TEXT, question TEXT, answer TEXT, "
              "status TEXT, sql_used_json TEXT, duration_ms INTEGER, created_at TEXT, error_message TEXT)")
    c.executemany("INSERT INTO query_runs (query_id, session_id, username, question, answer, status, sql_used_json, "
                  "duration_ms, created_at) VALUES (?,?,?,?,?,?,?,?,?)", [
        ("q1", "s1", "qlv_a", "Doanh thu doi toi thang 9", "Doanh thu doi 5 ty.", "completed",
         json.dumps(["<template:get_revenue_by_channel>({'a': 1})", "<template:get_revenue_by_channel>({'a': 1})"]),
         4000, "2026-09-20T02:00:00"),
        ("q2", "s2", "sep", "So sanh doanh thu thang 8 voi thang 7", "", "partial_timeout", "[]", 161000,
         "2026-09-20T03:00:00"),
        ("q3", "s3", "sep", "KPI the nao", "Anh muon xem KPI cua doi nao, thang nao?", "completed", "[]", 3000,
         "2026-09-20T04:00:00"),
        ("q4", "s4", "nguoi_cu", "Top SKU mien Bac", "", "error", "[]", 900, "2026-09-21T02:00:00"),
        ("q5a", "s5", "qlv_a", "Cong no doi", "", "error", "[]", 100, "2026-09-22T01:00:00"),
        ("q5b", "s5", "qlv_a", "Cong no doi", "No doi 1 ty.", "completed", '["t"]', 5000, "2026-09-22T01:05:00"),
    ])
    c.execute("UPDATE query_runs SET error_message='Error code: 529 - overloaded req_abc123' WHERE query_id='q4'")
    c.commit(); c.close()
    auth = tmp_path / "auth.db"
    c = sqlite3.connect(auth)
    c.execute("CREATE TABLE users (username TEXT, role TEXT)")
    c.executemany("INSERT INTO users VALUES (?,?)", [("qlv_a", "qlv"), ("sep", "c_level")])
    c.commit(); c.close()
    monkeypatch.setenv("DNH_COST_LOG", str(cost))
    monkeypatch.setenv("DNH_MEMORY_DB", str(mem))
    monkeypatch.setenv("DNH_AUTH_DB", str(auth))
    spec = importlib.util.spec_from_file_location("phan_tich_cov", GOC / "scripts" / "phan_tich_cost_of_value.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bao_cao_tach_luot_khong_gia_tri_va_goi_trung(tmp_path, monkeypatch, capsys):
    mod = _nap(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["x", "--tu", "2026-09-01", "--den", "2026-09-30"])
    mod.main()
    out = capsys.readouterr().out
    assert "| 5 luot |" in out, "5 luot that; cham_uat, chamlai (tai khoan that), beval bi loai."
    assert "danh sach khach moi" not in out and "business-eval" not in out
    assert "Khong ra gia tri: 3 luot" in out
    assert "Error code: N - overloaded <id>" in out, "Loi gom theo noi dung, bo so/ma request."
    assert "nguoi_cu" in out.split("USERNAME KHONG CO TRONG auth.db")[1]
    assert "TOOL GOI TRUNG: 1 luot, 1 lan goi thua" in out
    assert "het_gio" in out and "chi_hoi_lai" in out
    assert "cham_uat" not in out


def test_phan_loai_ket_qua_va_loai_cau(tmp_path, monkeypatch):
    mod = _nap(monkeypatch, tmp_path)
    assert mod._ket_qua_luot({"status": "partial_timeout"}) == "het_gio"
    assert mod._ket_qua_luot({"status": "api_credit_exhausted"}) == "loi"
    assert mod._ket_qua_luot({"status": "completed", "sql_used_json": "[]", "answer": "Thang nao a?"}) == "chi_hoi_lai"
    assert mod._ket_qua_luot({"status": "completed", "sql_used_json": '["t"]', "answer": "Ban co can them?"}) == "tra_loi"
    assert mod._ket_qua_luot(None) == "khong_co_query_run"
    assert mod._loai_cau("So sánh doanh thu tháng 8 với tháng 7") == "so_sanh"


def test_ca_kiem_thu_tach_theo_nguon(tmp_path, monkeypatch, capsys):
    mod = _nap(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["x", "--tu", "2026-09-01", "--den", "2026-09-30", "--ca-kiem-thu"])
    mod.main()
    out = capsys.readouterr().out.split("THEO NGUON")[1]
    assert "kiem_thu:chamlai" in out and "kiem_thu:beval" in out and "that" in out


def test_ghep_query_run_theo_gio_khong_theo_thu_tu(tmp_path, monkeypatch, capsys):
    # 24/09: lan cham lai hong ket noi (0 dong cost) tung "an" chi phi cua lan chay sau cung session+cau hoi.
    mod = _nap(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.argv", ["x", "--tu", "2026-09-01", "--den", "2026-09-30"])
    mod.main()
    out = capsys.readouterr().out
    assert "Khong ra gia tri: 3 luot" in out, "Chi phi 08:05 thuoc lan tra loi q5b, khong phai lan loi q5a."
    assert "Cong no doi" not in out.split("TOP 12 LUOT DAT NHAT KHONG RA GIA TRI")[1].split("TOP 12 LUOT DAT NHAT CO")[0]
