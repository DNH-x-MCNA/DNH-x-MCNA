from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import main
from src import etl, notifier
from src import alerts
from src.alerts import format_vietnamese_money


def test_report_freshness_tach_ngay_du_lieu_va_gio_dong_bo(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE sync_meta (table_name TEXT, last_synced_at TEXT, latest_synced_date TEXT)"
    )
    conn.executemany(
        "INSERT INTO sync_meta VALUES (?, ?, ?)",
        [
            ("vhoadon_otc", "2026-09-16T09:10:00", "2026-09-16"),
            ("vhoadon_etc", "2026-09-16T09:11:00", "2026-09-15"),
        ],
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(alerts, "WAREHOUSE_DB_PATH", str(db_path))

    freshness = etl._warehouse_report_freshness()

    assert freshness["available"] is True
    assert freshness["updated_at"] == "09:10 16/09/2026"
    assert freshness["data_date"] == "2026-09-15"
    assert "hóa đơn mới nhất đến 15/09/2026" in freshness["note"]


def test_daily_mac_dinh_chi_hien_tong_cong_no_khong_lap_top_5(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {
        "report_recipients": [{"audience": "GD Miền Bắc", "region": "bac", "channel": None,
                               "teams_webhook": "https://example.test"}],
        "report_feature_flags": {"show_daily_receivables_detail": False,
                                 "show_operational_quality": False},
    })
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kwargs: {
        "date": "16/09/2026", "updated_at": "09:10 16/09/2026",
        "freshness_note": "Kho dữ liệu cập nhật đủ OTC/ETC đến 09:10 16/09/2026.",
        "channel": None, "insights": None,
        "revenue": {"otc": 1, "etc": 2, "total": 3, "otc_invoice_count": 1,
                    "etc_invoice_count": 1, "invoice_count": 2},
        "inventory": {"dead_stock_available": False, "near_stockout_available": False},
        "receivables": {
            "balance_end": 100, "total_overdue": 50, "overdue_pct": 50.0,
            "aging": [{"label": "Trên 45 ngày", "amount": 50}],
            "top_overdue_customers": [{"customer_name": "Khách A", "customer_code": "KH1",
                                        "region": "Miền Nam", "channel": "OTC",
                                        "overdue": 50, "balance": 100}],
        },
    })
    captured = {}
    monkeypatch.setattr(
        main, "send_teams_alert",
        lambda **kwargs: captured.update(kwargs) or True,
    )

    assert main.send_daily_digest() is True
    debt = next(section for section in captured["sections"]
                if section["id"] == "section_receivables_detail")
    assert debt["title"] == "💳 TỔNG QUAN CÔNG NỢ"
    assert len(debt["items"]) == 1
    assert "Tổng dư nợ" in debt["items"][0]
    assert "Khách A" not in str(debt)


def test_monthly_etc_chi_giu_hop_dong_con_tu_500_trieu():
    fake = SimpleNamespace(etc_contract_status=lambda **kwargs: {
        "as_of": "2026-09-15",
        "so_hop_dong_gia_tri_bat_thuong": 2,
        "hop_dong_sap_het_han": [
            {"contract_id": 1, "so_hop_dong": "HD01", "customer_code": "KH1", "den_ngay": "2026-10-01",
             "con_lai_ngay": 16, "con_lai": 800_000_000, "ty_le_thuc_hien_pct": 20.0},
            {"contract_id": 2, "so_hop_dong": "HD02", "customer_code": "KH2", "den_ngay": "2026-09-25",
             "con_lai_ngay": 10, "con_lai": 200_000_000, "ty_le_thuc_hien_pct": 70.0},
        ],
    })

    part = etl._monthly_etc_contracts(region="bac", report_tools=fake)

    assert part["available"] is True
    assert [row["so_hop_dong"] for row in part["rows"]] == ["HD01"]
    assert part["total_remaining"] == 800_000_000
    assert part["invalid_contract_count"] == 2


def test_email_monthly_hien_bang_hop_dong_etc():
    metrics = {
        "date": "15/09/2026", "period_range": "Tháng 09/2026", "updated_at": "16:55 15/09/2026",
        "freshness_note": "Kho dữ liệu cập nhật đủ OTC/ETC đến 16:55 15/09/2026.",
        "region": None, "channel": "ETC", "insights": None,
        "revenue": {"otc": 0, "etc": 1, "total": 1, "invoice_count": 1, "otc_invoice_count": 0,
                    "etc_invoice_count": 1, "prev_total": 0, "change_pct": None, "prev_period_label": ""},
        "receivables": None,
        "inventory": {"dead_stock_available": False, "near_stockout_available": False},
        "trend": [], "region_breakdown": [], "kpi_summary": None, "kpi_breakdown": [],
        "etc_by_employee": [], "region_growth": [], "channel_share": None,
        "etc_contracts_expiring": {
            "available": True, "min_remaining": 500_000_000, "total_rows": 1,
            "invalid_contract_count": 2,
            "rows": [{"contract_id": 1, "so_hop_dong": "HD01", "customer_code": "KH1",
                      "den_ngay": "2026-10-01", "con_lai_ngay": 16, "con_lai": 800_000_000,
                      "ty_le_thuc_hien_pct": 20.0}],
        },
    }

    html = notifier.build_digest_email(metrics, period_label="Monthly")

    assert "Hợp Đồng ETC Sắp Hết Hạn" in html
    assert "HD01" in html and "800,0 triệu đ" in html
    assert "2 hợp đồng giá trị bất thường" in html
    assert metrics["freshness_note"] in html
