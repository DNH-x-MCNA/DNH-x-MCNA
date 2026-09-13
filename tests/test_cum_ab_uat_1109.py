"""Cum A/B ke hoach UAT 11-20/09 - khong goi API.
V03 (sheet ghi CAN SUA CHATBOT): doanh so tung ngay/tuan so nhip can thiet, khong bo T7/CN.
Loi cheo M20/C54/V40: khong canh bao co dinh chua dong bo nguon don hang.
Fixture _setup: hom nay 20/04/2026 (thu Hai); 05/04 la CN, 18/04 la T7."""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "backend"))

import sqlite3  # noqa: E402

import local_warehouse  # noqa: E402
import report_templates as rt  # noqa: E402
from test_daily_kpi_status import _make_db as _daily_db  # noqa: E402
from test_management_rounds_remaining import _setup  # noqa: E402


def _nhip(**kw):
    return rt.kpi_gap_run_rate(as_of_date="2026-04-20", group_by="employee", **kw)["nhip_theo_ngay"]


def test_liet_ke_du_moi_ngay_lich_ke_ca_t7_cn(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    n = _nhip()

    ngay = {d["date"]: d for d in n["daily"]}
    assert n["tu_ngay"] == "2026-04-01" and n["den_ngay"] == "2026-04-20"
    assert len(n["daily"]) == 20
    assert (ngay["2026-04-18"]["thu"], ngay["2026-04-18"]["revenue"]) == ("T7", 150)
    assert (ngay["2026-04-05"]["thu"], ngay["2026-04-05"]["revenue"]) == ("CN", 180)
    assert n["tong_doanh_thu_hoa_don"] == 180 + 250 + 600 + 50 + 150
    assert sum(w["revenue"] for w in n["weekly"]) == n["tong_doanh_thu_hoa_don"]
    assert sum(w["so_ngay"] for w in n["weekly"]) == 20


def test_ngay_khong_phat_sinh_tach_cn_va_bo_ngay_dang_chay(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    n = _nhip()

    assert "2026-04-01" in n["ngay_khong_phat_sinh_t2_t7"]
    assert "2026-04-19" in n["chu_nhat_khong_phat_sinh"]
    assert "2026-04-19" not in n["ngay_khong_phat_sinh_t2_t7"]
    # 20/04 la hom nay: moi luy ke mot phan ngay, khong duoc liet ke la khong phat sinh.
    assert n["daily"][-1]["dang_chay_do"] is True
    assert "2026-04-20" not in n["ngay_khong_phat_sinh_t2_t7"]


def test_hai_nhip_can_thiet_tu_target_ca_pham_vi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    n = _nhip(limit=1)

    # Target 3 TDV x 1000 - tinh tren ca pham vi, khong phai 1 dong hien theo limit.
    assert n["scope_target"] == 3000
    assert n["nhip_can_thiet_moi_ngay_lich"] == 100  # 3000 / 30 ngay
    assert n["so_ngay_ban_t2_t7_trong_thang"] == 26
    ngay = {d["date"]: d for d in n["daily"]}
    assert ngay["2026-04-12"]["pct_nhip_ngay_lich"] == 600
    assert ngay["2026-04-12"]["pct_nhip_ngay_ban_t2_t7"] is None  # CN khong co nhip ngay ban


def test_doi_qlv_chi_tinh_hoa_don_cua_doi(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    n = _nhip(scope_area_code="MB", scope_employee_code="Q1")

    # Doi Q1 = T1 (D1), T2 (D2): C1 05/04 180, C3 08/04 250 va 18/04 150. C4 (D3, MN) va ORPHAN bi loai.
    assert n["tong_doanh_thu_hoa_don"] == 580
    assert {d["date"] for d in n["daily"] if d["revenue"]} == {"2026-04-05", "2026-04-08", "2026-04-18"}


def test_khong_co_ngay_tuong_lai(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    n = rt.kpi_gap_run_rate(as_of_date="2026-04-29", group_by="total")["nhip_theo_ngay"]

    assert n["den_ngay"] == "2026-04-20"
    assert n["daily"][-1]["date"] == "2026-04-20"


def _daily_co_thu_bay(tmp_path, monkeypatch):
    db = tmp_path / "warehouse.db"
    _daily_db(db)
    with sqlite3.connect(db) as con:
        # 03/01/2026 la THU BAY - ngay ban nhieu nhat that tren Bravo (T7 = 22,3% doanh thu OTC T8/2026).
        con.execute("INSERT INTO vhoadon_otc VALUES ('2026-01-03', 'NV01', 900000)")
        con.execute("INSERT INTO dim_nhanvien VALUES ('NV02','Nguyen Van B',0,'TDV','MB','NV02')")
        con.execute("INSERT INTO fact_tonghopkhachhang VALUES ('NV02',1000000,'2026-01-15')")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db))


def test_daily_kpi_mot_nguoi_khong_giau_doanh_so_thu_bay(tmp_path, monkeypatch):
    _daily_co_thu_bay(tmp_path, monkeypatch)

    r = rt.employee_daily_kpi("NV01", "2026-01")

    assert {"date": "2026-01-03", "thu": "T7", "revenue": 900000} in r["weekend_days"]
    assert r["weekend_revenue"] == 900000
    assert r["month_total_sales"] == 900000 + 30000 + 50000
    # Mau KPI ngay giu nguyen quy tac T2-T6: T7 khong vao days, khong bi dem do/vang/xanh.
    assert "2026-01-03" not in {d["date"] for d in r["days"]}
    assert r["count_red"] + r["count_yellow"] + r["count_green"] == len(r["days"])


def test_daily_kpi_ca_doi_dua_thu_bay_vao_nhip_va_top_ngay(tmp_path, monkeypatch):
    _daily_co_thu_bay(tmp_path, monkeypatch)

    r = rt.employee_daily_kpi("NV01,NV02", "2026-01")

    tong = r["team_daily_summary"]
    assert tong["weekend_revenue"] == 900000
    assert tong["top_revenue_dates"][0]["date"] == "2026-01-03"
    theo_nguoi = {e["employee_code"]: e["weekend_revenue"] for e in r["employees"]}
    assert theo_nguoi == {"NV01": 900000, "NV02": 0}


# --- Loi cheo M20/C54/V40 (ke hoach 11-20/09): khong phat canh bao CO DINH "chua dong bo" cho nguon
# don hang khi check_order_timing van doc duoc DMS_DonHangHdr tren Bravo.

def test_nguon_don_hang_doc_duoc_thi_khong_bao_chua_dong_bo(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "_trang_thai_nguon_don_hang", lambda: {"status": "OK"})

    r = rt.operational_data_quality(as_of_date="2026-04-20")

    assert r["checks"]["order_invoice_source"]["status"] == "OK"
    assert r["checks"]["order_invoice_source"]["tool"] == "check_order_timing"
    assert not any("don hang" in x.lower() for x in r["unavailable_checks"])
    assert "chua duoc dong bo" not in str(r)


def test_nguon_don_hang_loi_thi_bao_dung_loi_that(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)

    r = rt.operational_data_quality(as_of_date="2026-04-20")

    loi = [x for x in r["unavailable_checks"] if "Don hang" in x]
    assert len(loi) == 1 and "khong ket noi Bravo" in loi[0]


def test_tai_khoan_etc_khong_duoc_thu_nguon_don_otc(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "_trang_thai_nguon_don_hang",
                        lambda: (_ for _ in ()).throw(AssertionError("khong duoc goi")))

    r = rt.operational_data_quality(as_of_date="2026-04-20", scope_channel="ETC")

    assert r["checks"]["order_invoice_source"]["status"] == "NOT_APPLICABLE"


def test_phep_thu_nguon_don_hang_co_cache(monkeypatch):
    goi = []
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params: goi.append(sql) or [{"ok": 1}])
    monkeypatch.setitem(rt._NGUON_DON_HANG_CACHE, "value", None)

    assert rt._trang_thai_nguon_don_hang() == {"status": "OK"}
    assert rt._trang_thai_nguon_don_hang() == {"status": "OK"}
    assert len(goi) == 1 and "DMS_DonHangHdr" in goi[0]


# --- M16 (ke hoach: phan biet giam 3 thang lien tiep voi giam rai rac; thieu thang khong thanh 0;
# tra ca nguyen nhan mat khach / giam tan suat / giam gia tri don).

from test_cat_danh_sach_chuoi_thang import _setup as _setup_chuoi  # noqa: E402


def _chuoi_m16(tmp_path, monkeypatch):
    path = _setup_chuoi(tmp_path, monkeypatch)
    with sqlite3.connect(path) as con:
        con.execute("DELETE FROM fact_thongketinhluong")
        chuoi = {  # 12/2025 .. 03/2026; None = khong co dong thang do
            "D1": [500, 400, 300, 200],   # giam 3 lan lien tiep
            "D2": [300, 400, 300, 200],   # tang roi giam 2 lan
            "D3": [500, 400, None, 300],  # thieu thang 2 -> chuoi dut, khong noi qua
        }
        # Snapshot ngay CUOI thang: 28/03 se bi coi la thang 3 dang chay (MTD) va loai khoi chuoi.
        cuoi_thang = ["2025-12-31", "2026-01-31", "2026-02-28", "2026-03-31"]
        for ma, gia_tri in chuoi.items():
            for ngay, v in zip(cuoi_thang, gia_tri):
                if v is not None:
                    con.execute("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?)",
                                (ma, "TDV " + ma, "TDV", "MB", "Q1", ngay, v, 1000, v / 10))
        # D1 thang 2 co them 1 khach (C9), thang 3 mat khach do: don/khach va AOV giu nguyen.
        con.execute("INSERT INTO vhoadon_otc VALUES ('2026-02-12','C9','A',900,1,900,'OX1',1,'D1',"
                    "'2026-02-12','OTC')")
    return rt.workforce_productivity(month_to="2026-03", months_back=4, group_by="employee")


def test_m16_dem_dung_so_lan_giam_va_thieu_thang_thi_dut_chuoi(tmp_path, monkeypatch):
    r = _chuoi_m16(tmp_path, monkeypatch)

    theo_ma = {x["employee_code"]: x["decline_streak_months"] for x in r["declining_employees"]}
    assert theo_ma == {"D1": 3, "D2": 2}
    assert r["declining_count_by_streak"] == {">=2": 2, ">=3": 1, ">=4": 0}
    assert "D3" not in theo_ma  # thieu 02/2026: khong bac cau, khong coi thang thieu la 0


def test_m16_chi_ra_nguyen_nhan_mat_khach(tmp_path, monkeypatch):
    r = _chuoi_m16(tmp_path, monkeypatch)

    d1 = next(x for x in r["declining_employees"] if x["employee_code"] == "D1")
    assert r["decline_cause_data_available"] is True
    assert d1["cause"]["khach"] == {"truoc": 2, "nay": 1}
    assert d1["cause"]["pct_thay_doi"]["mat_khach"] == -50
    assert d1["cause"]["pct_thay_doi"]["giam_tan_suat"] == 0
    assert d1["cause"]["yeu_to_giam_manh_nhat"] == "mat_khach"
