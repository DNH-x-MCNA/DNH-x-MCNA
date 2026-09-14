# -*- coding: utf-8 -*-
"""Dua ban sua tay tren may 24 ngay 13/09/2026 vao repo co test (14/09/2026).

Hai file backend tren may 24 bi sua truc tiep sau khi pull a9b4059 (supervisor bao "backend LECH
origin/master"). Ca hai deu va loi that nen duoc giu, khong xoa:
  1. C12: check_order_timing them group_by_month - cau "tang truong cot loi TUNG THANG" truoc day
     bat model goi lai tool 6-10 lan (moi thang mot lan) va het thoi gian request.
  2. salary_aso_detail tra nguyen Decimal tu Bravo (ASOQuantity/ASOBonus...) lam buoc dong goi ket
     qua gui model nem TypeError. Kem gia co tan goc: _json_mac_dinh cho ca ask va ask_stream.
Doi chieu tren du lieu that 14/09: tong doanh thu cot loi cac thang khop tuyet doi voi ket qua gop
theo kenh (ETC 12.043.610.140d, OTC 13.400.163.532d, ky 07-08/2026).
"""
import datetime as dt
import json
import os
import sqlite3
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402
from test_qlv_unblocked_area_only_tools import _make_min_db  # noqa: E402
from test_data_freshness import _patch_nl2sql_runtime  # noqa: E402


# --- C12: group_by_month -------------------------------------------------------------------------

def _kho_hai_thang(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_min_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT);
        """
    )

    def otc(ngay, kh, tien, stt):
        conn.execute("INSERT INTO vhoadon_otc VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (ngay, kh, "SP01", tien, 1, abs(tien), stt, 1, "TDV01_DMS", ngay, "ASM01"))

    # Du don binh thuong de trung vi gia tri don DUONG (340.000d -> nguong don lon 1.020.000d), nen
    # chi don tra hang bi danh dau. Neu don tra chiem da so, trung vi am va MOI don duong deu thanh
    # "don lon" - canh yeu cua quy tac 3x trung vi co san, khong phai cua ban va theo thang.
    otc("2026-07-10", "KH01", 500000, "HD1")
    otc("2026-07-12", "KH09", 450000, "HD1B")
    otc("2026-07-13", "KH10", 480000, "HD1C")
    otc("2026-07-11", "KH01", -100000, "HD-TRA1")   # hang tra -> bi danh dau
    otc("2026-08-05", "KH02", 300000, "HD3")
    otc("2026-08-06", "KH03", 400000, "HD4")
    otc("2026-08-07", "KH11", 420000, "HD5")
    otc("2026-08-08", "KH12", 380000, "HD6")
    for i in range(2, 6):                            # them 4 don tra de co > 3 dong bi danh dau
        otc("2026-08-%02d" % (10 + i), "KH0%d" % (3 + i), -10000, "HD-TRA%d" % i)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt, "_write_log", lambda entry: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: [])


def test_c12_tach_theo_thang_khop_tong_theo_kenh_va_khong_doi_chieu_don(tmp_path, monkeypatch):
    _kho_hai_thang(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "_order_fulfillment_exceptions",
                        lambda *a, **k: pytest.fail("group_by_month khong duoc goi doi chieu don-hoa don"))

    r = rt.order_timing_check("2026-07-01", "2026-08-31", group_by_month=True)

    thang = {(x["month"], x["channel"]): x for x in r["core_result_by_month"]}
    assert set(thang) == {("2026-07", "OTC"), ("2026-08", "OTC")}
    assert thang[("2026-07", "OTC")]["flagged_orders"] == 1
    assert thang[("2026-07", "OTC")]["core_revenue_excluding_flagged"] == 500000 + 450000 + 480000
    kenh = {x["channel"]: x for x in r["core_result_by_channel"]}["OTC"]
    # Cung tap don, cung dinh nghia: cong cac thang phai ra dung ket qua gop ca ky.
    for truong in ("total_orders", "flagged_orders", "revenue_including_flagged",
                   "core_revenue_excluding_flagged", "flagged_revenue"):
        assert sum(x[truong] for x in r["core_result_by_month"]) == pytest.approx(kenh[truong]), truong
    assert "skipped_reason" in r["order_fulfillment_exceptions"]
    json.dumps(r, ensure_ascii=False)


def test_c12_gioi_han_chi_tiet_3_dong_khi_theo_thang_20_dong_khi_mac_dinh(tmp_path, monkeypatch):
    _kho_hai_thang(tmp_path, monkeypatch)
    monkeypatch.setattr(rt, "_order_fulfillment_exceptions",
                        lambda *a, **k: {"status": "OK", "rows": []})

    theo_thang = rt.order_timing_check("2026-07-01", "2026-08-31", group_by_month=True)
    mac_dinh = rt.order_timing_check("2026-07-01", "2026-08-31")
    tu_truyen = rt.order_timing_check("2026-07-01", "2026-08-31", group_by_month=True, limit=5)

    assert theo_thang["total_flagged"] == 5
    assert len(theo_thang["top_detail"]) == 3 and theo_thang["top_detail_truncated"] is True
    assert len(mac_dinh["top_detail"]) == 5 and "core_result_by_month" not in mac_dinh
    assert mac_dinh["order_fulfillment_exceptions"]["status"] == "OK"
    assert len(tu_truyen["top_detail"]) == 5  # model tu truyen limit thi van duoc ghi de


# --- ASO: Decimal tu Bravo -----------------------------------------------------------------------

def test_aso_chuyen_decimal_tu_bravo_sang_float_va_dong_goi_duoc(monkeypatch):
    def fake_bravo(sql, params=None):
        if "MAX(SaveDate)" in sql:
            return [{"snapshot_date": "2026-08-31"}]
        return [{
            "EmployeeCode": "T1", "EmployeeName": "TDV 1", "PositionCode": "TDV", "AreaCode": "MB",
            "IsCalASOBonus": 1, "PassCheckASOForASO": 1, "PassCheckSaleForASO": 1,
            "PassCheckASOBonus": 1, "ASOQuantity": Decimal("16.00"),
            "ASOQuantityTarget": Decimal("20.00"), "ASOPercent_R": Decimal("0.8000"),
            "ASOBonus": Decimal("1743750.00"), "IsSuspend": 0,
        }]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)

    r = rt.salary_aso_detail("2026-08", scope_role="c_level")

    dong = r["rows"][0]
    for truong in ("aso_quantity", "aso_quantity_target", "aso_ratio_raw", "aso_bonus"):
        assert isinstance(dong[truong], float), truong
    assert dong["aso_percent"] == pytest.approx(80.0)
    json.dumps(r, ensure_ascii=False)  # khong default: truoc ban va se nem TypeError


# --- Gia co tan goc buoc dong goi ket qua tool ---------------------------------------------------

def test_json_mac_dinh_chuyen_decimal_va_ngay():
    goi = json.dumps({"so": Decimal("1.5"), "ngay": dt.date(2026, 9, 14),
                      "luc": dt.datetime(2026, 9, 14, 8, 22, 49)}, default=nl2sql._json_mac_dinh)
    assert json.loads(goi) == {"so": 1.5, "ngay": "2026-09-14", "luc": "2026-09-14T08:22:49"}


def test_ca_ask_va_ask_stream_deu_dong_goi_bang_json_mac_dinh():
    nguon = Path(nl2sql.__file__).read_text(encoding="utf-8")
    assert nguon.count("default=_json_mac_dinh) if isinstance(model_payload, (dict, list))") == 2


def test_ask_khong_vo_khi_tool_tra_decimal(monkeypatch):
    calls = []

    class Messages:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                content = [SimpleNamespace(type="tool_use", name="get_revenue_by_channel",
                                           id="t1", input={})]
            else:
                content = [SimpleNamespace(type="text", text="Doanh thu la 1,5.")]
            return SimpleNamespace(content=content, usage=SimpleNamespace())

    _patch_nl2sql_runtime(monkeypatch, SimpleNamespace(messages=Messages()), [])
    monkeypatch.setattr(nl2sql, "call_template", lambda *a, **k: {
        "ok": True, "result": {"total": {"revenue": Decimal("1.5")},
                               "as_of": dt.date(2026, 9, 14)}})

    nl2sql.ask("Doanh thu tháng 8 theo kênh là bao nhiêu?", session_id="unit-decimal",
               username="unit", scope_role="c_level")

    assert len(calls) == 2, "vong gui ket qua tool cho model phai chay duoc"
    noi_dung = json.dumps(calls[1]["messages"], ensure_ascii=False, default=str)
    assert "1.5" in noi_dung and "2026-09-14" in noi_dung
