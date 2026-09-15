# -*- coding: utf-8 -*-
"""Báo cáo định kỳ (src/etl.py) — kỳ so sánh và công nợ theo kênh người nhận. Không DB, không Bravo.

15/09/2026:
- Kỳ trước của báo cáo tháng lấy prev_start + period_len: chạy 30/09 bỏ mất 31/08 (ngày dồn doanh thu
  cuối tháng), chạy 31/03 lấn 3 ngày tháng 3.
- Giám đốc kênh OTC/ETC nhận tuổi nợ và top khách nợ của CẢ HAI kênh, chỉ con số tổng được đổi.
"""
from datetime import datetime
from types import SimpleNamespace

from src import etl


def _cua_so(start, end, granularity, now):
    return etl._previous_period_window(start, end, granularity, now=now)


# ---------- Kỳ trước ----------

def test_bao_cao_thang_ngay_cuoi_thang_30_so_nguyen_thang_truoc_31_ngay():
    s, e = _cua_so(datetime(2026, 9, 1), datetime(2026, 10, 1), "monthly", datetime(2026, 9, 30, 17, 45))
    assert (s, e) == (datetime(2026, 8, 1), datetime(2026, 9, 1))  # gồm 31/08


def test_bao_cao_thang_ngay_cuoi_thang_31_khong_lan_sang_thang_nay():
    s, e = _cua_so(datetime(2026, 3, 1), datetime(2026, 4, 1), "monthly", datetime(2026, 3, 31, 17, 45))
    assert (s, e) == (datetime(2026, 2, 1), datetime(2026, 3, 1))


def test_bao_cao_thang_giua_thang_so_cung_so_ngay():
    s, e = _cua_so(datetime(2026, 9, 1), datetime(2026, 9, 16), "monthly", datetime(2026, 9, 15, 10, 0))
    assert (s, e) == (datetime(2026, 8, 1), datetime(2026, 8, 16))


def test_bao_cao_thang_tran_thang_truoc_ngan_thi_chan_o_dau_thang_nay():
    # 30/03, chưa hết tháng: 30 ngày đã qua nhưng tháng 2 chỉ 28 ngày.
    s, e = _cua_so(datetime(2026, 3, 1), datetime(2026, 3, 31), "monthly", datetime(2026, 3, 30, 9, 0))
    assert (s, e) == (datetime(2026, 2, 1), datetime(2026, 3, 1))


def test_bao_cao_thang_thang_1_lui_ve_thang_12_nam_truoc():
    s, e = _cua_so(datetime(2026, 1, 1), datetime(2026, 1, 11), "monthly", datetime(2026, 1, 10, 9, 0))
    assert (s, e) == (datetime(2025, 12, 1), datetime(2025, 12, 11))


def test_bao_cao_tuan_va_ngay_giu_nguyen_cach_so_cu():
    tuan = _cua_so(datetime(2026, 9, 14), datetime(2026, 9, 20), "weekly", datetime(2026, 9, 19, 18, 0))
    assert tuan == (datetime(2026, 9, 7), datetime(2026, 9, 13))  # thứ 2-thứ 7 tuần trước
    ngay = _cua_so(datetime(2026, 9, 15), datetime(2026, 9, 16), None, datetime(2026, 9, 15, 17, 45))
    assert ngay == (datetime(2026, 9, 14), datetime(2026, 9, 15))


def test_nhan_thang_ngay_cuoi_thang_ghi_tam_tinh(monkeypatch):
    class _Gio(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 30, 17, 45)

    seen = {}
    monkeypatch.setattr(etl, "datetime", _Gio)
    monkeypatch.setattr(etl, "get_digest_metrics",
                        lambda s, e, label, **kw: seen.setdefault("label", label))
    etl.get_monthly_digest_metrics()
    assert "tạm tính đến 17:45" in seen["label"]


# ---------- Công nợ theo kênh người nhận ----------

def _no(code, channel, area, d1=0, d15=0, d30=0, d45=0, balance=0):
    return SimpleNamespace(customer_code=code, customer_name="KH " + code, sales_channel=channel,
                           area_code=area, overdue_1_15=d1, overdue_15_30=d15, overdue_30_45=d30,
                           overdue_gt_45=d45, balance_end=balance)


_SNAP = [
    _no("O1", "OTC", "MB", d1=10, d45=40, balance=100),
    _no("E1", "ETC", "MB", d45=900, balance=1000),   # khách ETC nợ lớn nhất
    _no("O2", "OTC", "MN", d30=5, balance=50),
    _no("E2", "ETC", "MN", balance=70),              # không quá hạn
]


def _tong_aging(rec):
    return round(sum(a["amount"] for a in rec["aging"]), 2)


def test_giam_doc_kenh_otc_chi_thay_khach_va_tuoi_no_otc():
    rec = etl._build_receivables(_SNAP, channel="OTC", now=datetime(2026, 9, 15, 17, 45))

    assert {c["customer_code"] for c in rec["top_overdue_customers"]} == {"O1", "O2"}
    assert rec["total_overdue"] == 55 and rec["balance_end"] == 150
    assert _tong_aging(rec) == rec["total_overdue"]
    assert sum(r["overdue"] for r in rec["by_region"]) == 55
    assert rec["by_channel"] == []
    # Số từng kênh vẫn giữ để đối chiếu.
    assert (rec["otc_overdue"], rec["etc_overdue"]) == (55, 900)


def test_giam_doc_kenh_etc_khong_thay_khach_otc():
    rec = etl._build_receivables(_SNAP, channel="ETC")

    assert [c["customer_code"] for c in rec["top_overdue_customers"]] == ["E1"]
    assert _tong_aging(rec) == rec["total_overdue"] == 900
    assert rec["overdue_pct"] == round(900 / 1070 * 100, 1)


def test_toan_quoc_thay_ca_hai_kenh_va_chia_theo_kenh():
    rec = etl._build_receivables(_SNAP)

    assert [c["customer_code"] for c in rec["top_overdue_customers"]] == ["E1", "O1", "O2"]
    assert _tong_aging(rec) == rec["total_overdue"] == 955
    assert {r["channel"]: r["overdue"] for r in rec["by_channel"]} == {"OTC": 55, "ETC": 900}


def _kpi(code, pos, area, manager, target, amount):
    return SimpleNamespace(employee_code=code, employee_name="NV " + code, area_code=area, position_code=pos,
                           manager_code=manager, month_sale_target=target, month_sale_amount=amount,
                           month_sale_percent=amount / target if target else None)


def test_cay_kpi_theo_tang_quan_ly_giu_nhom_kenh_mt_va_cap_duoi_tk_cs():
    rows = [
        _kpi("TM23100148", "QLV", "MN", None, 1000, 400),   # QLV thường
        _kpi("MN1", "QLV", "MN", None, 6000, 1100),         # "Kênh MT" - Bravo gắn cờ trùng
        _kpi("MN4", "QLV", "MN", None, 2000, 600),          # "Chợ sỉ"
        _kpi("T1", "TDV", "MN", "TM23100148", 900, 350),
        _kpi("HUE", "TK", "MN", "MN1", 6000, 1100),
        _kpi("LOL", "CS", "MN", "MN4", 2000, 600),
    ]
    managers = {"TM23100148", "MN1", "MN4"}

    cay = etl._build_kpi_hierarchy(rows, "nam", manager_codes=managers)

    nut = {q["employee_code"]: q for q in cay[0]["qlvs"]}
    assert set(nut) == managers
    assert [c["employee_code"] for c in nut["MN1"]["tdvs"]] == ["HUE"]
    assert [c["employee_code"] for c in nut["MN4"]["tdvs"]] == ["LOL"]
    assert sum(q["target"] for q in cay[0]["qlvs"]) == 9000   # = tổng chỉ tiêu tầng quản lý

    # Cách cũ (theo chức danh) vẫn giữ khi không truyền manager_codes.
    cu = etl._build_kpi_hierarchy(rows, "nam")
    assert {c["employee_code"] for q in cu[0]["qlvs"] for c in q["tdvs"]} == {"T1"}


def test_bao_cao_vung_khong_chia_theo_vung_nua():
    rec = etl._build_receivables([r for r in _SNAP if r.area_code == "MB"], region="bac", channel="OTC")

    assert rec["by_region"] == []
    assert rec["total_overdue"] == 50
