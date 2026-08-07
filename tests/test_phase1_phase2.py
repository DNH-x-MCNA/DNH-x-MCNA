import pytest
import os
import json
from src.alerts import AGING_BUCKET_LABELS
from src.notifier import _fit_teams_payload, _TEAMS_DETAIL_MAX_ROWS
from src.etl import kpi_pace_bucket, reconciliation_variance, _company_wide_alert_visible_to
from main import send_daily_digest, send_weekly_report, send_monthly_report

def test_nhan_tuoi_no():
    """Kiểm tra 4 nhãn tuổi nợ được hiển thị chính xác theo quy chuẩn."""
    assert AGING_BUCKET_LABELS["overdue_1_15"] == "Từ 1 đến 15 ngày"
    assert AGING_BUCKET_LABELS["overdue_15_30"] == "Từ 16 đến 30 ngày"
    assert AGING_BUCKET_LABELS["overdue_30_45"] == "Từ 31 đến 45 ngày"
    assert AGING_BUCKET_LABELS["overdue_gt_45"] == "Trên 45 ngày"

def test_cat_tia_payload_teams():
    """Kiểm tra cơ chế cắt tỉa payload Adaptive Card Teams luôn dưới trần 28KB."""
    card = {
        "type": "AdaptiveCard",
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "version": "1.4",
        "body": [
            {
                "type": "Container",
                "items": [
                    {
                        "type": "FactSet",
                        "facts": [{"title": f"Mục {i}", "value": f"Giá trị {i}"} for i in range(50)]
                    }
                ]
            }
        ]
    }
    table_headers = ["Cột 1", "Cột 2", "Cột 3"]
    table_rows = [[f"Dữ liệu ô {r}-{c} nội dung dài " * 10 for c in range(3)] for r in range(50)]
    card["body"].append({
        "type": "Table",
        "columns": [{"width": 1} for _ in table_headers],
        "rows": [
            {
                "type": "TableRow",
                "cells": [
                    {
                        "type": "TableCell",
                        "items": [{"type": "TextBlock", "text": cell}]
                    } for cell in row
                ]
            } for row in table_rows
        ]
    })

    fitted_card = _fit_teams_payload(card)
    raw_json = json.dumps(fitted_card, ensure_ascii=False)
    assert len(raw_json.encode('utf-8')) <= 28000


def test_cac_ham_helper_thuan():
    """Kiểm tra logic tính toán của các hàm helper thuần."""
    assert kpi_pace_bucket(2.5) == "RED"
    assert kpi_pace_bucket(3.5) == "YELLOW"
    assert kpi_pace_bucket(4.5) == "GREEN"

    diff_v, diff_p = reconciliation_variance(100000, 90000)
    assert diff_v == 10000.0
    assert abs(diff_p - 0.1) < 1e-5

    diff_v0, diff_p0 = reconciliation_variance(0, 5000)
    assert diff_v0 == 5000.0
    assert diff_p0 == 0.0

def test_quy_tac_hien_thi_canh_bao_toan_cong_ty():
    """Kiểm tra phân quyền lọc cảnh báo theo miền."""
    assert _company_wide_alert_visible_to("Toàn quốc", "nam") is True
    assert _company_wide_alert_visible_to("Nhiều miền", "bac") is True
    assert _company_wide_alert_visible_to("Miền Nam", "nam") is True
    assert _company_wide_alert_visible_to("Miền Bắc", "nam") is False
    assert _company_wide_alert_visible_to("Miền Nam", None) is True

def test_chay_dry_run_tat_ca_audiences():
    """Kiểm tra chạy thử dry-run cho cả 3 loại báo cáo không phát sinh lỗi."""
    res_daily = send_daily_digest(dry_run=True)
    assert res_daily is True

    res_weekly = send_weekly_report(dry_run=True)
    assert res_weekly is True

    res_monthly = send_monthly_report(dry_run=True)
    assert res_monthly is True
