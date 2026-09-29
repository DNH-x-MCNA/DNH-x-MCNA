# -*- coding: utf-8 -*-
"""UAT M32 29/09/2026 - "SKU chien luoc dat %KH tai vung": khong tra danh sach TDV; hoi rieng top 10 thi thieu
doi MBKV2 va xep sai thu tu.

1) Cau M32 di vao get_customer_product_coverage(mode=sku_target) - luon tra "khong co mau so target theo SKU".
   Nhung chi tieu SKU trong tam CO o cap TDV (TPRTargetAmount) - dung nguon dap an SQL cua anh Dang.
2) get_kpi_scorecard khong loc doi chi tra 20 nguoi % DOANH SO THAP nhat -> model goi tung doi (10 doi MB), cham
   gioi han 5 tool/vong, bo sot doi MBKV2 va tu xep top 10 sai.
Dap an (anh Dang): chi PositionCode TDV, snapshot moi nhat tung nguoi trong thang, xep TargetProductPercent_R
giam dan; chi tieu = TPRTargetAmount < 1 ? TPRTargetAmount x MonthSaleAmount : TPRTargetAmount.
Du lieu gia, khong cham Bravo, khong goi model."""
import json
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.append(str(GOC / "backend"))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

DOI = ["MBKV%d" % i for i in range(1, 11)]          # 10 doi MB, MBKV2 la doi tung bi sot


def _pct_mb(i):
    """% he thong gia lap: moi TDV mot gia tri khac nhau, doi MBKV2 co nguoi dan dau."""
    return 1.60 - 0.01 * i


def _kho(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    c = sqlite3.connect(path)
    c.executescript("""
        CREATE TABLE vhoadon_otc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        CREATE TABLE vhoadon_etc (customer_code TEXT, amount9 REAL, doc_date TEXT, employee_code TEXT);
        INSERT INTO vhoadon_otc VALUES ('K','1','2026-09-28','D1');
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER, position_code TEXT,
            area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT, is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE fact_thongketinhluong (employee_code TEXT, employee_name TEXT, position_code TEXT,
            area_code TEXT, manager_code TEXT, save_date TEXT, month_sale_amount REAL, month_sale_target REAL,
            month_sale_percent REAL, target_product_amount REAL, tpr_target_amount REAL,
            target_product_percent REAL, tpr_point REAL);
    """)
    rows, i = [], 0
    # Doi MBKV2 dat cuoi danh sach doi de chac chan khong phai "doi dau tien" duoc liet ke.
    for doi in DOI[2:] + DOI[:2]:
        rows.append((doi, "QLV " + doi, "QLV", "MB", None, "2026-09-28", 5e9, 5e9, 1.0, 2e9, 0, None, None))
        for k in range(9):
            i += 1
            ma, msa, ty_trong = "TDV%03d" % i, 400_000_000.0, 0.5
            pct = _pct_mb(i if doi != "MBKV2" else k)          # MBKV2 giu cac hang dau
            actual = pct * ty_trong * msa
            rows.append((ma, "TDV so %d" % i, "TDV", "MB", doi, "2026-09-28", msa, msa, 1.0, actual, ty_trong,
                         pct, None))
            # Snapshot cu hon trong thang KHONG duoc dung.
            rows.append((ma, "TDV so %d" % i, "TDV", "MB", doi, "2026-09-20", msa, msa, 1.0, 1.0, ty_trong, 9.99,
                         None))
        # CTV co % rat cao nhung dap an chi xep TDV.
        rows.append(("CTV" + doi, "CTV " + doi, "CTV", "MB", doi, "2026-09-28", 1e8, 1e8, 1.0, 9e7, 0.5, 1.8, None))
    # Mien Nam: chi tieu so tien.
    rows.append(("TDVMN", "TDV Nam", "TDV", "MN", "QMN", "2026-09-28", 300.0, 300.0, 1.0, 90.0, 120.0, 0.75, None))
    c.executemany("INSERT INTO fact_thongketinhluong VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    c.commit()
    c.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))
    return rows


def _dap_an(rows, vung="MB"):
    """Tinh lai dung nhu SQL cua anh Dang: TDV, snapshot moi nhat, xep % he thong giam dan."""
    moi_nhat = {}
    for r in rows:
        if r[2] == "TDV" and r[3] == vung and (r[0] not in moi_nhat or r[5] > moi_nhat[r[0]][5]):
            moi_nhat[r[0]] = r
    return [r[0] for r in sorted(moi_nhat.values(), key=lambda r: -r[11])]


def test_focus_kpi_tra_xep_hang_tdv_du_moi_doi_dung_thu_tu_dap_an(tmp_path, monkeypatch):
    rows = _kho(tmp_path, monkeypatch)
    r = rt.focus_product_kpi("2026-09", area_code="MB", limit_tdv=10)

    assert r["so_tdv"] == 90                                   # 10 doi x 9 TDV, khong CTV, khong MN
    ma = [x["employee_code"] for x in r["tdv_xep_hang"]]
    assert ma == _dap_an(rows)[:10]
    assert [x["hang"] for x in r["tdv_xep_hang"]] == list(range(1, 11))
    assert {x["manager_code"] for x in r["tdv_xep_hang"]} >= {"MBKV2"}   # doi tung bi sot
    dau = r["tdv_xep_hang"][0]
    assert round(dau["pct_he_thong"], 6) == 160.0 == round(dau["pct_dat"], 6)
    # Chi tieu quy doi MB = ty trong 0,5 x doanh so thang 400tr = 200tr; con thieu am = da vuot.
    assert dau["chi_tieu_quy_doi"] == 200_000_000.0
    assert round(dau["con_thieu"]) == round(200_000_000.0 - dau["doanh_so_trong_tam"])
    assert all(x["employee_code"].startswith("TDV") for x in r["tdv_xep_hang"])


def test_theo_mien_tinh_tu_tdv_co_chi_tieu(tmp_path, monkeypatch):
    rows = _kho(tmp_path, monkeypatch)
    mien = {t["mien"]: t for t in rt.focus_product_kpi("2026-09")["theo_mien_tdv"]}

    assert mien["MB"]["so_tdv"] == 90 and mien["MN"]["so_tdv"] == 1
    assert round(mien["MN"]["pct_dat"], 6) == 75.0
    moi_nhat = {r[0]: r for r in rows if r[2] == "TDV" and r[3] == "MB" and r[5] == "2026-09-28"}
    assert mien["MB"]["so_tdv_dat_100"] == sum(1 for r in moi_nhat.values() if r[11] >= 1.0)
    # % mien = tong doanh so trong tam / tong chi tieu quy doi (0,5 x doanh so thang), tren TDV co chi tieu.
    tong_ds = sum(r[9] for r in moi_nhat.values())
    tong_ct = sum(r[10] * r[6] for r in moi_nhat.values())
    assert round(mien["MB"]["pct_dat"], 6) == round(tong_ds / tong_ct * 100, 6)


def test_pham_vi_tai_khoan_thang_tham_so_vung(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = rt.focus_product_kpi("2026-09", area_code="MB", scope_area_code="MN")
    assert r["so_tdv"] == 1 and r["tdv_xep_hang"][0]["employee_code"] == "TDVMN"


def test_cau_m32_dinh_tuyen_vao_trong_tam_va_toi_model_du_10_dong(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    cau = "Top 10 TDV đạt %KH SKU chiến lược cao nhất vùng MB"
    assert nl2sql._required_tool_for_question(cau) == "get_focus_product_kpi"
    args = nl2sql._normalize_tool_input_for_question("get_focus_product_kpi", {"area_code": "MB"}, cau)
    payload = rt.focus_product_kpi("2026-09", **args)
    model = json.loads(nl2sql._serialize_payload_for_model("get_focus_product_kpi", payload, cau))
    assert len(json.dumps(model, ensure_ascii=False)) <= nl2sql.MAX_PAYLOAD_CHARS
    bang = model["tdv_xep_hang"]
    so_dong = len(bang["dong"]) if isinstance(bang, dict) else len(bang)
    assert so_dong == 10


def test_cau_m32_goc_va_v30_theo_khach_di_dung_duong():
    assert nl2sql._required_tool_for_question(
        "SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoảng trống độ phủ lớn nhất?"
    ) == "get_focus_product_kpi"
    assert nl2sql._required_tool_for_question(
        "SKU chiến lược đạt %KH tại vùng; khoảng trống độ phủ lớn nhất") == "get_focus_product_kpi"
    # V30 hoi theo KHACH HANG: chi tieu theo khach/SKU khong co -> van bao thieu nguon.
    assert nl2sql._required_tool_for_question(
        "SKU trọng tâm đạt bao nhiêu % target theo từng TDV và khách hàng; khoảng thiếu bao nhiêu?"
    ) == "get_customer_product_coverage"
    _tool, ghi_chu = nl2sql._required_tool_for_request(
        "SKU chiến lược đạt %KH tại vùng; khoảng trống độ phủ lớn nhất",
        [{"name": "get_focus_product_kpi"}, {"name": "get_customer_product_coverage"}])
    assert "get_customer_product_coverage" in ghi_chu


def test_bang_kpi_top_cao_nhat_theo_trong_tam_mot_lan_goi(tmp_path, monkeypatch):
    rows = _kho(tmp_path, monkeypatch)
    cau = "Top 10 TDV đạt % trọng tâm cao nhất miền Bắc"
    args = nl2sql._normalize_tool_input_for_question("get_kpi_scorecard", {"area_code": "MB"}, cau)
    assert args == {"area_code": "MB", "thu_tu": "cao_truoc", "xep_theo": "trong_tam_pct_dat",
                    "position_code": "TDV", "limit": 10}
    r = rt.kpi_scorecard(**args)

    assert [x["employee_code"] for x in r["nhan_vien"]] == _dap_an(rows)[:10]
    assert r["so_nguoi"] == 90 and r["thu_tu_danh_sach"] == "trong_tam_pct_dat CAO truoc"
    assert r["nhan_vien"][0]["hang"] == 1


def test_bang_kpi_mac_dinh_van_xep_doanh_so_thap_truoc(tmp_path, monkeypatch):
    _kho(tmp_path, monkeypatch)
    r = rt.kpi_scorecard(area_code="MB")
    pct = [x["pct_doanh_so"] for x in r["nhan_vien"]]
    assert pct == sorted(pct) and r["thu_tu_danh_sach"] == "pct_doanh_so THAP truoc"
