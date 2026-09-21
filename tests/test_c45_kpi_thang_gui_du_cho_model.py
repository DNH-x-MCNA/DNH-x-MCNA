# -*- coding: utf-8 -*-
"""Bang KPI tung thang phai toi duoc model, ke ca khi danh sach nhan vien rat dai."""
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql


def test_c45_giu_du_thang_vung_chuc_danh_trong_ngan_sach_payload():
    months = [f"2026-{month:02d}" for month in range(1, 7)]
    rows = [
        {
            "month": month, "area_code": area, "position_code": position,
            "employees_with_target": 20,
            "count_gate": 12, "count_80": 10, "count_100": 5, "count_120": 2,
            "pct_gate": 60.0, "pct_80": 50.0, "pct_100": 25.0, "pct_120": 10.0,
        }
        for month in months for area in ("MB", "MT", "MN")
        for position in ("TDV", "CTV", "CS", "QLV")
    ]
    payload = {
        "du_lieu": {
            "as_of": "2026-06-30", "total_employees": 170,
            "rows": [{"employee_code": f"NV{i:03d}", "name": "Nhan vien " + "X" * 70}
                     for i in range(200)],
            "monthly_threshold_summary": {
                "month_from": "2026-01", "month_to": "2026-06",
                "group_by": "area_position", "channel_scope": "OTC",
                "rows": rows, "definition": "Dem nhan vien co target theo snapshot tung thang.",
            },
        },
        "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": ["Canh bao thu nghiem"],
    }

    encoded = nl2sql._serialize_payload_for_model(
        "get_employee_kpi", payload,
        "Tỷ lệ nhân sự đạt 65/70%, 80%, 100%, 120% KPI từng tháng theo kênh/miền/chức danh",
    )
    sent = json.loads(encoded)
    monthly = sent["du_lieu"]["monthly_threshold_summary"]

    assert len(encoded) <= nl2sql.MAX_PAYLOAD_CHARS
    assert len(monthly["rows"]) == len(rows) == 72
    assert {row[0] for row in monthly["rows"]} == set(months)
    assert monthly["columns"][:3] == ["month", "area_code", "position_code"]
    assert monthly["channel_scope"] == "OTC"
    assert "total_employees" not in sent["du_lieu"]
    assert sent["CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG"] == ["Canh bao thu nghiem"]


def test_m12_giu_du_chuoi_doi_va_xu_huong_ba_thang():
    rows = [
        {
            "month": month, "manager_code": manager, "employees_with_target": 10,
            "count_gate": 7, "count_80": 6, "count_100": 4, "count_120": 1,
            "pct_gate": 70.0, "pct_80": 60.0, "pct_100": 40.0, "pct_120": 10.0,
            "pct_gate_change_vs_previous_month": 5.0,
            "pct_gate_rolling_3_month_avg": 65.0,
        }
        for month in ("2026-06", "2026-07", "2026-08")
        for manager in ("MBKV1", "MBKV2")
    ]
    payload = {
        "as_of": "2026-08-31", "rows": [{"employee_code": "T1"}],
        "monthly_team_threshold_summary": {
            "month_from": "2026-06", "month_to": "2026-08", "group_by": "manager",
            "channel_scope": "OTC", "rows": rows,
        },
    }

    sent = json.loads(nl2sql._serialize_payload_for_model(
        "get_employee_kpi", payload,
        "Đội nào đạt 100%, 80%, qua cổng 65/70% hoặc dưới cổng; xu hướng 3 tháng?",
    ))
    monthly = sent["monthly_team_threshold_summary"]

    assert len(monthly["rows"]) == 6
    assert "pct_gate_rolling_3_month_avg" in monthly["columns"]
    assert monthly["rows"][-1][1] == "MBKV2"
