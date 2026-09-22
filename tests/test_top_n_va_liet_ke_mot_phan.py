# -*- coding: utf-8 -*-
"""22/09/2026 - hai loi bat duoc khi cham lai UAT, cung mot goc: du lieu dung nhung BANG TRA LOI sai.

1. Top 10 khach no qua han (dnh_etc): SQL da ORDER BY no qua han giam dan, bang tra loi lai ra
   1,90 - 1,68 - 1,51 - 1,94 - 1,89 ty. Thu tu phai nam trong chinh du lieu (rank), khong de model
   tu xep lai luc trinh bay.
2. Doi QLV TM23100148: payload bi cat con dung 12 dong (nguong max_items dau tien), model doc 12
   dong roi viet "Tong cong 12 khach" trong khi tong that la 27. Moc bao phai nam NGAY CANH danh
   sach, khong de rieng o cuoi payload.
"""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import nl2sql
import report_templates as rt


def _kho_cong_no(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE fact_congno_khachhang (snapshot_date TEXT, snapshot_at TEXT, customer_code TEXT,
            customer_name TEXT, sales_channel TEXT, area_code TEXT, balance_end REAL,
            overdue_1_15 REAL, overdue_15_30 REAL, overdue_30_45 REAL, overdue_gt_45 REAL,
            total_overdue REAL);
        CREATE TABLE dim_nhanvien (employee_code TEXT, name TEXT, is_duplicate INTEGER,
            position_code TEXT, area_code TEXT, dmsid TEXT, start_date TEXT, end_date TEXT,
            is_resigned INTEGER, manager_area_code TEXT);
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, amount_ct REAL,
            month_sale_target REAL, save_date TEXT, is_nc INTEGER, manager_code TEXT);
        """
    )
    # Du no va no qua han xep NGUOC nhau, dung bay ma bang tra loi that da sap: khach du no lon nhat
    # (6,41 ty) khong phai khach qua han nhieu nhat (1,94 ty).
    conn.executemany(
        "INSERT INTO fact_congno_khachhang VALUES ('2026-09-22','2026-09-22T15:49:00',?,?,'ETC',?,?,0,0,0,?,?)",
        [("KH1", "Benh vien 1", "MB", 6_410_000_000, 1_680_000_000, 1_680_000_000),
         ("KH2", "Benh vien 2", "MB", 2_420_000_000, 1_940_000_000, 1_940_000_000),
         ("KH3", "Benh vien 3", "MN", 4_320_000_000, 1_900_000_000, 1_900_000_000),
         ("KH4", "Benh vien 4", "MT", 2_060_000_000, 1_890_000_000, 1_890_000_000),
         ("KH5", "Benh vien 5", None, 1_000_000_000, 500_000_000, 500_000_000)],
    )
    conn.commit()
    conn.close()


def test_top_no_qua_han_mang_san_rank_theo_dung_thu_tu(tmp_path, monkeypatch):
    _kho_cong_no(tmp_path / "warehouse.db")
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(tmp_path / "warehouse.db"))

    out = rt.receivables_overview(top_n=3, scope_channel="ETC")

    top = out["top_overdue_customers"]
    assert [r["rank"] for r in top] == [1, 2, 3]
    assert [r["customer_code"] for r in top] == ["KH2", "KH3", "KH4"]  # theo qua han, KHONG theo du no
    assert [r["total_overdue"] for r in top] == [1_940_000_000, 1_900_000_000, 1_890_000_000]
    assert "rank" in out["ranking_basis"]
    # Vung chua xac dinh van phai co trong by_region, neu khong tong cac vung se khong khop.
    assert sum(r["total_overdue"] for r in out["by_region"]) == out["total_overdue"]
    assert "Khac/chua xac dinh" in out["by_region_note"] or "Khac" in str(out["by_region"])
    tool = next(t for t in nl2sql.TEMPLATE_TOOLS if t["name"] == "get_receivables_overview")
    assert "rank" in tool["description"] and "by_region" in tool["description"]


def test_danh_sach_bi_cat_phai_co_moc_bao_ngay_canh():
    payload = {"total_pending_customers": 27, "rows": [{"i": n} for n in range(27)],
               "kpi_tai_don_theo_nhan_vien": [{"e": n} for n in range(9)]}
    overview = []

    goi = nl2sql._compact_collections_for_model(payload, 12, "", overview)

    assert len(goi["rows"]) == 12
    assert "27" in goi["rows__dang_liet_ke"] and "12" in goi["rows__dang_liet_ke"]
    assert "KHONG duoc noi tong bang so dong dang hien" in goi["rows__dang_liet_ke"]
    # Danh sach khong bi cat thi khong duoc them nhieu nhieu moc bao thua.
    assert "kpi_tai_don_theo_nhan_vien__dang_liet_ke" not in goi
    assert goi["total_pending_customers"] == 27
    assert overview == [{"path": "rows", "total": 27, "shown": 12}]


def test_cau_phan_kpi_con_thieu_phai_duoc_chi_sang_tool_luong():
    """14/09 (chosi.mn) doi thuong SP danh muc, V15/V22, ASO/Active Customer, tong trong so KPI;
    22/09 cham lai van chi ra doanh so/chi tieu/%dat. Cac so do nam o tool luong, khong o KPI."""
    tool = next(t for t in nl2sql.TEMPLATE_TOOLS if t["name"] == "get_employee_kpi")
    d = tool["description"]
    assert "get_salary_achievement_summary" in d
    assert "V15/V22" in d and "Active Customer" in d
    assert "PHAI liet ke ro cau phan nao chua co" in d
    # Quy tac da chot: khong duoc doi thuong V25 tu ky 07/2026.
    assert "V25" in d and "01/07/2026" in d


def test_payload_gui_model_giu_rank_va_bao_vung_chua_gan():
    """22/09 cham lai: thu tu da dung nhung bang theo vung VAN bo dong 'Khac/chua xac dinh' (0,81 ty).
    Ly do: _payload_for_model loc trang cot, rank va by_region_note bi cat truoc khi toi model."""
    payload = {
        "receivable_status": "ok", "total_overdue": 62.94e9, "total_balance_end": 160.54e9,
        "by_region": [{"region": "Mien Bac", "total_overdue": 30.29e9},
                      {"region": "Mien Nam", "total_overdue": 25.41e9},
                      {"region": "Mien Trung", "total_overdue": 6.43e9},
                      {"region": "Khac/chua xac dinh", "total_overdue": 0.81e9}],
        "by_region_note": "by_region da gom DU moi vung",
        "ranking_basis": "Top xep theo NO QUA HAN, in theo rank",
        "top_overdue_requested_count": 2, "top_overdue_returned_count": 2,
        "top_overdue_eligible_count": 9,
        "top_overdue_customers": [
            {"rank": 1, "customer_code": "KH2", "customer_name": "B", "balance_end": 2.42e9,
             "total_overdue": 1.94e9, "employee_code": None},
            {"rank": 2, "customer_code": "KH3", "customer_name": "C", "balance_end": 4.32e9,
             "total_overdue": 1.90e9, "employee_code": None}],
    }

    goi = nl2sql._payload_for_model("get_receivables_overview", payload, "top 10 khach no qua han")

    assert [r["rank"] for r in goi["top_overdue_customers"]] == [1, 2]
    assert "by_region_note" in goi
    assert "810000000" in goi["by_region_warning"].replace(".", "")
    assert "MOT DONG rieng" in goi["by_region_warning"]
    # Khong co nhom chua gan thi khong duoc canh bao thua.
    sach = dict(payload, by_region=payload["by_region"][:3])
    assert "by_region_warning" not in nl2sql._payload_for_model(
        "get_receivables_overview", sach, "top 10 khach no qua han")


def test_payload_kpi_liet_ke_cau_phan_con_thieu():
    payload = {"as_of": "2026-09-22", "total_employees": 1,
               "rows": [{"employee_code": "TM23100153", "name": "CS", "position_code": "CS",
                         "sales": 108_500_000, "target": 1_700_000_000, "pct": 6.38}]}

    goi = nl2sql._payload_for_model("get_employee_kpi", payload,
                                    "tinh hinh thuc hien kpi cua cac trinh duoc vien")

    cau_phan = goi["cau_phan_kpi_ngoai_tool_nay"]
    assert "V15" in cau_phan["chua_co_trong_ket_qua_nay"]
    assert "get_salary_achievement_summary" in cau_phan["lay_o_dau"]
    assert "01/07/2026" in cau_phan["answer_rule"]
    # Cau hoi khong ve KPI thi khong gan them nhieu chu vao payload.
    assert "cau_phan_kpi_ngoai_tool_nay" not in nl2sql._payload_for_model(
        "get_employee_kpi", payload, "doanh so thang nay cua doi")
