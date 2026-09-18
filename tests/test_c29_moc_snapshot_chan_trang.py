# -*- coding: utf-8 -*-
"""18/09/2026 - cau C29: chan trang ghi "KPI kinh doanh (snapshot 30/06/2026)" va "Doanh thu OTC
(snapshot 30/06/2026)" trong khi chinh bang ngay phia tren co so lieu den 18/09/2026.

_first_value() duyet ca cay ket qua cua tool va lay khoa "snapshot_date" DAU TIEN gap duoc.
customer_lifecycle_summary tra months[] xep tu CU den MOI, nen dong dau tien la thang cu nhat -
moc do bi lay lam moc do moi cho ca cau tra loi. Nang hon: gia tri boc duoc con duoc dan sang MOI
nguon kho trong cung cau tra loi, ke ca "Doanh thu OTC" - bang von khong he co cot snapshot.

Chan trang sai kieu nay nguy hiem am tham: no khong lam sai con so nao trong bang, chi lam nguoi
doc tuong toan bo cau tra loi cu hon thuc te gan ba thang, va co the khien ho bo qua mot canh bao
that. business_date da uu tien so do tu bang tu truoc; rieng snapshot_date thi chua - do la cho
khong nhat quan trong cung mot khoi lenh.

Du lieu gia, khong cham Bravo."""
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import data_freshness as df


def _kho(tmp_path):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE fact_tonghopkhachhang (employee_code TEXT, customer_code TEXT, save_date TEXT);
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, amount9 REAL);
    """)
    conn.executemany("INSERT INTO fact_tonghopkhachhang VALUES ('NV1','KH1',?)",
                     [("2026-06-30",), ("2026-07-31",), ("2026-08-31",), ("2026-09-15",)])
    conn.executemany("INSERT INTO vhoadon_otc VALUES (?,'KH1',100)",
                     [("2026-06-30",), ("2026-09-18",)])
    conn.commit()
    conn.close()
    return str(path)


def _ket_qua_kieu_vong_doi():
    """Dang payload that cua customer_lifecycle_summary: months xep tu CU den MOI."""
    return {
        "months": [
            {"month": "2026-06", "snapshot_date": "2026-06-30", "khach_moi": 765},
            {"month": "2026-07", "snapshot_date": "2026-07-31", "khach_moi": 613},
            {"month": "2026-08", "snapshot_date": "2026-08-31", "khach_moi": 627},
        ],
        "data_as_of": "2026-09-18",
    }


def _chan_trang(tmp_path):
    c = df.FreshnessCollector(warehouse_path=_kho(tmp_path))
    c.record_template("get_customer_lifecycle_summary", _ket_qua_kieu_vong_doi())
    return c.finalize_answer("")


def _nguon(tmp_path, ten):
    c = df.FreshnessCollector(warehouse_path=_kho(tmp_path))
    c.record_template("get_customer_lifecycle_summary", _ket_qua_kieu_vong_doi())
    return next(x for x in c.as_dicts() if x["source_name"] == ten)


def test_khong_lay_moc_cu_nhat_trong_payload_lam_moc_do_moi(tmp_path):
    kpi = _nguon(tmp_path, "KPI kinh doanh")

    assert kpi["snapshot_date"] == "2026-09-15"     # MAX(save_date) that cua bang
    assert kpi["snapshot_date"] != "2026-06-30"     # khong phai months[0]


def test_khong_dan_moc_snapshot_sang_nguon_khong_co_cot_snapshot(tmp_path):
    """vhoadon_otc khong co cot snapshot nao - khong duoc muon moc cua bang KPI."""
    otc = _nguon(tmp_path, "Doanh thu OTC")

    assert otc["snapshot_date"] is None
    assert otc["business_data_date"] == "2026-09-18"


def test_chan_trang_ghi_dung_nhan_cho_tung_nguon(tmp_path):
    chan = _chan_trang(tmp_path)

    assert "KPI kinh doanh (snapshot 15/09/2026" in chan
    assert "Doanh thu OTC (dữ liệu đến 18/09/2026" in chan
    assert "30/06/2026" not in chan
