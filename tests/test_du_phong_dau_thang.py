# -*- coding: utf-8 -*-
"""01/10/2026 - du phong cuoi thang cua chatbot trong nhung ngay dau thang (hai co du phong/bieu do dang BAT).

Chay lai 6 thang 03-08/2026 tren kho: truoc ngay 5, kich ban "Tot" cao gap 3-19 lan so that o 4/6 thang (T7 ngay 2:
368 ty so voi 74,8 ty), "Co so" lech -100%..+169%. Tu ngay 5 moi ve muc dung duoc. Chua du 5 ngay du lieu thi tra
thong bao ro ly do, khong dua bang so. Du lieu gia, khong goi model, khong cham Bravo."""
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))
import conversation_memory as memory  # noqa: E402
import nl2sql  # noqa: E402
import period_projection as pp  # noqa: E402
import report_templates as rt  # noqa: E402


def _ngay(y, m, d):
    class Ngay(dt.date):
        @classmethod
        def today(cls):
            return cls(y, m, d)
    return Ngay


@pytest.fixture
def kho(monkeypatch, tmp_path):
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-09-01")
    monkeypatch.setattr(rt, "_write_log", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda *a, **k: pytest.fail("du phong khong duoc doc Bravo"))
    monkeypatch.setattr(nl2sql, "sync_freshness_note", lambda: "")
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    goi = []

    def doanh_thu(first, last, **scope):
        goi.append((first, last[:10]))
        ngay = (dt.date.fromisoformat(last[:10]) - dt.date.fromisoformat(first)).days + 1
        return {"total": {"revenue": ngay * 10.0}, "data_coverage": {"complete": True}}

    monkeypatch.setattr(rt, "revenue_by_channel", doanh_thu)
    monkeypatch.setattr(rt, "_ytd_plan", lambda *a, **k: {"total": 600.0, "note": None})
    return goi


def _hom_nay(monkeypatch, y, m, d):
    monkeypatch.setattr(pp.dt, "date", _ngay(y, m, d))
    monkeypatch.setattr(rt, "latest_data_date", lambda: str(dt.date(y, m, d) - dt.timedelta(days=1)))


def test_doanh_thu_moi_co_2_ngay_du_lieu_thi_khong_dua_so(kho, monkeypatch):
    _hom_nay(monkeypatch, 2026, 10, 3)                       # du lieu den 02/10

    kq = pp.current_period_projection()

    assert "Tháng 10/2026 mới có 2 ngày dữ liệu (đến 02/10/2026)" in kq["error"]
    assert "ít nhất 5 ngày" in kq["error"] and kq["as_of"] == "2026-10-02"
    assert kho == []                                          # khong tinh gi tren ty le lich su


def test_doanh_thu_du_5_ngay_thi_du_phong_binh_thuong(kho, monkeypatch):
    _hom_nay(monkeypatch, 2026, 10, 6)                       # du lieu den 05/10

    kq = pp.current_period_projection()

    assert "error" not in kq and kq["as_of"] == "2026-10-05"
    assert kq["rows"][0]["scenarios"] is not None


def test_ngay_4_van_chua_du(kho, monkeypatch):
    _hom_nay(monkeypatch, 2026, 10, 5)                       # du lieu den 04/10
    assert "mới có 4 ngày dữ liệu" in pp.current_period_projection(group_by="channel")["error"]
    assert "mới có 4 ngày dữ liệu" in pp.current_period_projection(period="quarter")["error"]


def _kpi_snapshot(monkeypatch, ngay_snapshot):
    def kpi(day, group, limit, **scope):
        return {"as_of": ngay_snapshot, "rows": [{"group_code": "QLV1", "group_name": "Đội 1", "actual": 100.0,
                                                  "target": 300.0, "linear_run_rate": 190.0}]}
    monkeypatch.setattr(rt, "kpi_gap_run_rate", kpi)


def test_bang_kpi_tinh_theo_ngay_snapshot(kho, monkeypatch):
    # Bang KPI dung moc snapshot (hom nay), nen ngay 05 da du 5 ngay trong khi bang doanh thu (den 04) thi chua.
    _hom_nay(monkeypatch, 2026, 10, 4)
    _kpi_snapshot(monkeypatch, "2026-10-04")
    assert "mới có 4 ngày dữ liệu (đến 04/10/2026)" in pp.current_period_projection(group_by="qlv")["error"]

    _hom_nay(monkeypatch, 2026, 10, 5)
    _kpi_snapshot(monkeypatch, "2026-10-05")
    kq = pp.current_period_projection(group_by="qlv")
    assert "error" not in kq and kq["as_of"] == "2026-10-05"


def test_cau_tra_loi_chatbot_dau_thang_noi_ro_ly_do_mot_lan(kho, monkeypatch):
    _hom_nay(monkeypatch, 2026, 10, 3)

    kq = nl2sql.ask("Dự báo doanh thu cuối tháng/quý theo kênh/miền là bao nhiêu; khoảng tin cậy và giả định chính là gì?",
                    session_id="dau-thang", scope_role="c_level")

    tra_loi = kq["answer"]
    assert tra_loi.count("mới có 2 ngày dữ liệu") == 1         # 4 bang cung mot ly do -> in mot lan
    assert "| Phạm vi |" not in tra_loi and kq["charts"] == []
    assert memory.get_session_history("dau-thang")[-1]["content"] == tra_loi
