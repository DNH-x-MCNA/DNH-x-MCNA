# -*- coding: utf-8 -*-
"""Kiem chung cac tool quan tri chua co test rieng truoc 28/08/2026.

Khong goi API. Du lieu duoc dung trong SQLite tam hoac monkeypatch ham tong hop cap duoi.
"""
import datetime as real_dt
import os
import sqlite3
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse
import report_templates as rt


class _FixedDate(real_dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 8, 28)


def _period_result(revenue, invoices=1, otc=None, etc=None):
    otc = revenue if otc is None else otc
    etc = 0 if etc is None else etc
    return {
        "otc": {"revenue": otc, "invoices": invoices if otc else 0},
        "etc": {"revenue": etc, "invoices": invoices if etc else 0},
        "total": {"revenue": revenue, "invoices": invoices},
    }


def test_compare_periods_giu_nguyen_toan_bo_scope(monkeypatch):
    calls = []

    def fake_revenue(date_from, date_to, area, channel, employee):
        calls.append((date_from, date_to, area, channel, employee))
        return _period_result(200 if date_from == "2026-08-01" else 100)

    monkeypatch.setattr(rt, "revenue_by_channel", fake_revenue)
    result = rt.compare_periods(
        "2026-08-01", "2026-08-28", "2026-07-01", "2026-07-28",
        scope_area_code="MB", scope_channel="ETC", scope_employee_code="QLV01",
    )

    assert calls == [
        ("2026-08-01", "2026-08-28", "MB", "ETC", "QLV01"),
        ("2026-07-01", "2026-07-28", "MB", "ETC", "QLV01"),
    ]
    assert result["delta"] == 100
    assert result["pct_change"] == 100.0


def test_compare_periods_khong_coi_ky_thieu_kho_la_0_dong(monkeypatch):
    def fake_revenue(date_from, *_args):
        result = _period_result(200 if date_from == "2026-08-01" else 0)
        result["data_coverage"] = {"complete": date_from == "2026-08-01"}
        return result

    monkeypatch.setattr(rt, "revenue_by_channel", fake_revenue)
    result = rt.compare_periods(
        "2026-08-01", "2026-08-31", "2025-08-01", "2025-08-31",
    )

    assert result["comparison_valid"] is False
    assert result["delta"] is None
    assert result["pct_change"] is None


def test_revenue_ytd_cumulative_tinh_tang_truong_va_giu_scope(monkeypatch):
    calls = []
    revenues = {"2026": 300.0, "2025": 200.0, "2024": 100.0}

    def fake_revenue(date_from, date_to, area, channel, employee):
        calls.append((date_from, date_to, area, channel, employee))
        return _period_result(revenues[date_from[:4]])

    monkeypatch.setattr(rt, "revenue_by_channel", fake_revenue)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-08-28")
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: ("2020-01", "2026-08"))
    result = rt.revenue_ytd_cumulative(
        "2026-08", from_month="03", years_back=3,
        scope_area_code="MN", scope_channel="ETC", scope_employee_code="QLV02",
    )

    assert [row["year"] for row in result["cac_nam"]] == [2026, 2025, 2024]
    assert result["cac_nam"][0]["pct_change_vs_prev_year"] == 50.0
    assert result["cac_nam"][1]["pct_change_vs_prev_year"] == 100.0
    assert all(call[2:] == ("MN", "ETC", "QLV02") for call in calls)
    assert calls[0][:2] == ("2026-03-01", "2026-08-31")


def test_revenue_ytd_cumulative_tra_ke_hoach_va_phan_con_lai_tu_target_da_nhap(monkeypatch):
    monkeypatch.setattr(rt, "revenue_by_channel", lambda *args: _period_result(300.0))
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: ("2020-01", "2026-08"))
    monkeypatch.setattr(rt, "_ytd_plan", lambda *args: {
        "total": 500.0, "otc": 400.0, "etc": 100.0, "note": None,
    })

    result = rt.revenue_ytd_cumulative("2026-08", years_back=1)

    row = result["cac_nam"][0]
    assert row["plan_revenue"] == 500.0
    assert row["pct_of_plan"] == 60.0
    assert row["plan_gap_remaining"] == 200.0
    assert row["months_remaining"] == 4
    assert row["average_monthly_plan_needed"] == 50.0


def test_revenue_ytd_cumulative_khong_chia_doanh_thu_thieu_lich_su_voi_target_day_du(monkeypatch):
    """C03 UAT 07/09: T1-T6 doanh thu chua nam trong kho, nhung target da co du T1-T8. 15% la
    phep chia sai (2 thang actual / 8 thang target), phai bao thieu du lieu va khong tao %KH/gap."""
    monkeypatch.setattr(rt, "revenue_by_channel", lambda *args: _period_result(100.0))
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: ("2026-07", "2026-08"))
    monkeypatch.setattr(rt, "_ytd_plan", lambda *args: {
        "total": 500.0, "otc": 400.0, "etc": 100.0, "note": None,
    })

    result = rt.revenue_ytd_cumulative("2026-08", years_back=1)

    row = result["cac_nam"][0]
    assert row["revenue_history_complete"] is False
    assert row["revenue_history_available_from"] == "2026-07"
    assert row["pct_of_plan"] is None
    assert "plan_gap_remaining" not in row
    assert "canh_bao_thieu_lich_su_doanh_thu" in result


def _make_inventory_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE brv_tonkhodklot (
            branch_code TEXT, warehouse_id INTEGER, item_id INTEGER,
            item_lot_code TEXT, quantity REAL, is_active INTEGER
        );
        CREATE TABLE brv_lot (
            item_lot_code TEXT, item_id INTEGER, mfg_date TEXT,
            expiry_date TEXT, is_active INTEGER
        );
        CREATE TABLE brv_sanpham (
            code TEXT, name TEXT, group_code TEXT, unit TEXT, id_code INTEGER
        );
        CREATE TABLE brv_kho (id_code INTEGER, branch_code TEXT, code TEXT, name TEXT);
        """
    )
    conn.executemany("INSERT INTO brv_kho VALUES (?,?,?,?)", [
        (2, "B02", "KMB", "Kho Mien Bac"),
        (4, "B04", "KMN", "Kho Mien Nam"),
    ])
    conn.executemany("INSERT INTO brv_sanpham VALUES (?,?,?,?,?)", [
        ("SP1", "San pham het han", "G", "hop", 1),
        ("SP2", "San pham sap het han", "G", "hop", 2),
        ("SP3", "San pham khong co han", "G", "hop", 3),
        ("SP4", "San pham mien Nam", "G", "hop", 4),
    ])
    conn.executemany("INSERT INTO brv_tonkhodklot VALUES (?,?,?,?,?,?)", [
        ("B02", 2, 1, "LO-TRUNG", 10, 1),
        ("B02", 2, 2, "LO-TRUNG", 20, 1),
        ("B02", 2, 3, "LO-KHONG-HAN", 30, 1),
        ("B04", 4, 4, "LO-MN", 40, 1),
        ("B02", 2, 2, "LO-KHONG-HOAT-DONG", 999, 0),
    ])
    conn.executemany("INSERT INTO brv_lot VALUES (?,?,?,?,?)", [
        ("LO-TRUNG", 1, "2025-01-01", "2026-08-01", 1),
        ("LO-TRUNG", 2, "2026-01-01", "2026-10-01", 1),
        ("LO-MN", 4, "2026-01-01", "2026-12-31", 1),
    ])
    conn.commit()
    conn.close()


def test_inventory_expiry_phan_loai_dung_va_join_lo_bang_ca_item_id(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_inventory_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _table: (None, None, None))

    result = rt.inventory_expiry_report(scope_area_code="MB", limit=30)

    assert result["area_code"] == "MB"
    assert result["summary"]["het_han"] == {"so_lo": 1, "tong_so_luong": 10.0}
    assert result["summary"]["duoi_3_thang"] == {"so_lo": 1, "tong_so_luong": 20.0}
    assert result["khong_xac_dinh_han"] == 1
    assert [row["item_name"] for row in result["rows"]] == [
        "San pham het han", "San pham sap het han"
    ]
    assert all(row["branch_code"] == "B02" for row in result["rows"])


def test_inventory_expiry_scope_ghi_de_vung_ai_truyen_va_max_bucket(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    _make_inventory_db(db_path)
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))
    monkeypatch.setattr(rt.dt, "date", _FixedDate)
    monkeypatch.setattr(rt, "get_sync_meta", lambda _table: (None, None, None))

    result = rt.inventory_expiry_report(
        area_code="MN", scope_area_code="MB", max_bucket="het_han", limit=30,
    )

    assert result["area_code"] == "MB"
    assert len(result["rows"]) == 1
    assert result["rows"][0]["bucket"] == "het_han"


def test_inventory_expiry_tu_choi_scope_vung_khong_hop_le():
    result = rt.inventory_expiry_report(scope_area_code="XX")
    assert "error" in result
    assert "XX" in result["error"]
