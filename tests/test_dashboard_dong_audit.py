"""Dashboard /audit-logs: dong CHI CO trong audit_log la mot lan goi tool, khong phai mot luot chat.

24/09/2026, hai loi that tren may 24:
  1. Luot cham lai chay tu script (khong co query_runs) hien thoi gian cua MOT tool: do that 33,9 giay
     hien 3,4 giay, 23,8 giay hien 91 ms.
  2. verify_etc_channel_scope.py goi call_template khong danh tinh -> dong audit trong, status "ok"
     -> hien "unknown ... Hoan thanh" nhu mot luot chat thanh cong.
Du lieu gia, khong doc log that.
"""
import importlib.util
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import auth  # noqa: E402

# Nap backend/main.py theo duong dan: repo co main.py o goc, test chay truoc co the da giu
# sys.modules["main"] la file goc -> `import main` lay nham module.
_spec = importlib.util.spec_from_file_location("dnh_dashboard_audit_test_main", BACKEND / "main.py")
main = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = main
_spec.loader.exec_module(main)


def _chay(tmp_path, monkeypatch, audit, cost, runs):
    logs = tmp_path / "backend" / "logs"
    logs.mkdir(parents=True)
    (logs / "audit_log.jsonl").write_text("\n".join(json.dumps(e) for e in audit), encoding="utf-8")
    (logs / "cost_log.jsonl").write_text("\n".join(json.dumps(e) for e in cost), encoding="utf-8")
    monkeypatch.setattr(main, "__file__", str(tmp_path / "backend" / "main.py"))
    monkeypatch.setattr(main, "list_query_runs", lambda limit=10000: runs)
    monkeypatch.setattr(auth, "list_users", lambda *a, **k: [])
    monkeypatch.setattr(main, "get_name_by_username", lambda u: None)
    kq = main.get_audit_logs_dashboard(days=3650, date=None, limit=200, user_filter=None,
                                       role_filter=None, user={"role": "c_level"})
    return {(r["username"], r["question"]): r for r in kq["logs"]}, kq


TS = "2026-09-23T17:12:08"


def test_dong_audit_khong_lay_thoi_gian_mot_tool_lam_thoi_gian_ca_luot(tmp_path, monkeypatch):
    audit = [{"ts": TS, "username": "danh.nguyen", "question": "danh sach khach hang moi",
              "session_id": "chamlai2309-03", "sql": "<template:get_new_customer_list>({})",
              "status": "ok", "duration_ms": 91}]
    cost = [{"ts": TS, "session_id": "chamlai2309-03", "username": "danh.nguyen",
             "question_preview": "danh sach khach hang moi", "model": "claude-sonnet-5",
             "cost_usd": 0.37, "input_tokens": 4431, "output_tokens": 1873}]
    dong, _ = _chay(tmp_path, monkeypatch, audit, cost, runs=[])
    d = dong[("danh.nguyen", "danh sach khach hang moi")]
    assert d["duration_ms"] is None, "91 ms la cua MOT tool - khong duoc hien nhu thoi gian tra loi."
    assert d["tool_duration_ms"] == 91
    assert d["log_source"] == "audit"
    assert d["status"] == "ok", "Luot co goi model (co chi phi) khong phai kiem tra tu dong."


def test_dong_query_run_giu_nguyen_thoi_gian_ca_luot(tmp_path, monkeypatch):
    runs = [{"created_at": "2026-09-23T10:12:08+00:00", "username": "dnh", "question": "doanh thu",
             "session_id": "s1", "query_id": "q1", "status": "completed", "duration_ms": 33900,
             "sql_used": []}]
    dong, _ = _chay(tmp_path, monkeypatch, audit=[], cost=[], runs=runs)
    d = dong[("dnh", "doanh thu")]
    assert d["duration_ms"] == 33900 and d["log_source"] == "query_run"


def test_dong_kiem_tu_dong_khong_danh_tinh_khong_hien_hoan_thanh(tmp_path, monkeypatch):
    audit = [{"ts": TS, "username": None, "question": "", "session_id": None,
              "sql": "<template:get_revenue_by_channel>({})", "status": "ok", "duration_ms": 15}]
    dong, kq = _chay(tmp_path, monkeypatch, audit, cost=[], runs=[])
    d = dong[("unknown", "")]
    assert d["status"] == "tool_check", "Dong audit trong, khong goi model - khong phai luot chat."
    assert d["duration_ms"] is None
    assert kq["summary"]["total_queries"] == 0, "Kiem tra tu dong khong duoc dem vao tong so cau hoi."
    assert not [u for u in kq["user_breakdown"] if u["username"] == "unknown"], \
        "Khong hien dong 'unknown - 0 cau hoi' trong bang theo nguoi dung."


def test_dong_kiem_tu_dong_co_tien_to_kiemtra(tmp_path, monkeypatch):
    audit = [{"ts": TS, "username": "kiem_tu_dong",
              "question": "[Kiem tra tu dong] Phan quyen kenh ETC: get_revenue_by_channel",
              "session_id": "kiemtra-etc-2026-09-24", "sql": "<template:get_revenue_by_channel>({})",
              "status": "ok", "duration_ms": 20}]
    dong, _ = _chay(tmp_path, monkeypatch, audit, cost=[], runs=[])
    assert dong[("kiem_tu_dong", audit[0]["question"])]["status"] == "tool_check"


def test_dong_co_cau_hoi_nhung_khong_username_khong_session_la_kiem_tu_dong(tmp_path, monkeypatch):
    # Dang that tren may dev/may 24: test/script goi call_template kem cau hoi nhung khong danh tinh.
    audit = [{"ts": TS, "username": None, "question": "Top 10 san pham ban chay nhat?", "session_id": None,
              "sql": "<template:get_top_products>({})", "status": "ok", "duration_ms": 40}]
    dong, kq = _chay(tmp_path, monkeypatch, audit, cost=[], runs=[])
    assert dong[("unknown", "Top 10 san pham ban chay nhat?")]["status"] == "tool_check"
    assert kq["summary"]["total_queries"] == 0
    assert not [u for u in kq["user_breakdown"] if u["username"] == "unknown"]


def test_dong_khong_username_nhung_co_session_van_la_luot_can_xem(tmp_path, monkeypatch):
    # Co session ma mat username la bat thuong - giu nguyen de con thay, khong giau thanh kiem tu dong.
    audit = [{"ts": TS, "username": None, "question": "doanh thu", "session_id": "web-abc",
              "sql": "<template:get_revenue_ytd>({})", "status": "ok", "duration_ms": 40}]
    dong, kq = _chay(tmp_path, monkeypatch, audit, cost=[], runs=[])
    assert dong[("unknown", "doanh thu")]["status"] == "ok"
    assert kq["summary"]["total_queries"] == 1


def test_dong_security_khong_dem_la_cau_hoi(tmp_path, monkeypatch):
    audit = [{"ts": TS, "username": "dnh", "question": "", "session_id": None,
              "sql": "<auth:login>", "status": "ok"},
             {"ts": TS, "username": "dnh", "question": "", "session_id": None,
              "sql": "<admin:create_user>", "status": "ok"}]
    dong, kq = _chay(tmp_path, monkeypatch, audit, cost=[], runs=[])
    assert kq["summary"]["total_queries"] == 0, "Dang nhap/thao tac admin khong phai luot truy van."
    assert not [u for u in kq["user_breakdown"] if u["username"] == "dnh"]
    assert all(r["log_source"] == "security" for r in kq["logs"]), "Dong security van phai hien o tab Security."


def test_dong_chi_co_cost_log_co_nguon(tmp_path, monkeypatch):
    cost = [{"ts": TS, "session_id": "web-1", "username": "dnh", "question_preview": "chao bot",
             "model": "claude-sonnet-5", "cost_usd": 0.01, "input_tokens": 10, "output_tokens": 5}]
    dong, kq = _chay(tmp_path, monkeypatch, audit=[], cost=cost, runs=[])
    d = dong[("dnh", "chao bot")]
    assert d["status"] == "no_sql" and d["log_source"] == "cost_log"
    assert kq["summary"]["total_queries"] == 1
