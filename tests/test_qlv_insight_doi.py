# -*- coding: utf-8 -*-
"""Báo cáo QLV có Tiến độ đội và Việc cần xử lý, chỉ gồm khách thuộc đội — 15/09/2026.

Dữ liệu giả, không chạm Bravo: bundle insight dựng tay, kho phân công KPI là SQLite trong bộ nhớ.
"""
import datetime as dt
import sqlite3

import pytest

from src.insights import scope_insight_bundle_to_team
from src.insight_report import team_progress_lines
from src.qlv_digest import (
    _team_customer_codes,
    build_qlv_digest_metrics,
    build_qlv_period_email,
    build_qlv_period_metrics,
    build_qlv_teams_content,
)


def tien(value):
    return f"{value:,.0f}"


class _KhoGia:
    """report_tools giả: _q chạy SQLite thật cho phân công KPI; doanh thu/KPI trả số cố định."""

    def __init__(self, fact_rows=()):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("CREATE TABLE fact_tonghopkhachhang (employee_code, customer_code, manager_code, save_date)")
        self.conn.execute("CREATE TABLE dim_nhanvien (employee_code, position_code, area_code, is_resigned)")
        self.conn.execute("INSERT INTO dim_nhanvien VALUES ('QLV01', 'QLV', 'MB', 0)")
        self.conn.executemany("INSERT INTO fact_tonghopkhachhang VALUES (?,?,?,?)", list(fact_rows))

    def _q(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params)]

    def revenue_by_channel(self, date_from, date_to, **scope):
        return {"total": {"revenue": 1_000_000, "invoices": 1}}

    def employee_kpi(self, as_of_date, **kwargs):
        return {"rows": [
            {"employee_code": "QLV01", "name": "Quản lý", "pct": 50.0},
            {"employee_code": "TDV01", "name": "TDV 1", "pct": 40.0, "meets_kpi": False, "meets_full_target": False},
        ]}

    def customer_lifecycle_summary(self, **kwargs):
        return {"months": []}

    def customer_revenue_debt_risk(self, **kwargs):
        return {"customers": []}


PHAN_CONG = [
    ("TDV01", "K1", "QLV01", "2026-08-31"),
    ("TDV01", "K2", "QLV01", "2026-07-31"),   # K2 đã chuyển sang đội khác ở snapshot mới hơn
    ("TDV09", "K2", "QLV02", "2026-08-31"),
    ("QLV01", "K3", None, "2026-08-31"),      # khách QLV tự phụ trách
    ("TDV01", "K4", "QLV01", "2025-06-30"),   # quá cửa sổ 200 ngày
    ("TDV09", "K9", "QLV02", "2026-08-31"),
]


def _bundle(silent_codes=("K1", "K2"), team_projection=45.0):
    return {
        "as_of": dt.date(2026, 9, 14),
        "errors": {},
        "team_pace": {
            "evaluated": True, "min_day": 15, "threshold_pct": 60.0,
            "basis_note": "Dự phóng tính trên chỉ tiêu và doanh số của TDV trong đội.",
            "teams": [
                {"team_code": "QLV01", "team_name": "Đội 1", "actual": 30e6, "target": 100e6,
                 "achievement_pct": 30.0, "projection_pct": team_projection},
                {"team_code": "QLV02", "team_name": "Đội 2", "actual": 10e6, "target": 100e6,
                 "achievement_pct": 10.0, "projection_pct": 15.0},
            ],
            "at_risk": [t for t in (
                {"team_code": "QLV01", "team_name": "Đội 1", "achievement_pct": 30.0, "projection_pct": team_projection},
                {"team_code": "QLV02", "team_name": "Đội 2", "achievement_pct": 10.0, "projection_pct": 15.0},
            ) if t["projection_pct"] < 60],
            "not_projected": [{"team_code": "QLV03", "team_name": "Đội 3", "target": 5e6}],
        },
        "silent_customers": {"evaluated": True, "rows": [
            {"customer_code": cc, "customer_name": f"Khach {cc}", "sales_channel": "OTC", "baseline_monthly": 60e6}
            for cc in silent_codes
        ] + [{"customer_code": "K1", "customer_name": "Khach K1 ETC", "sales_channel": "ETC",
              "baseline_monthly": 200e6}]},
        "new_over45": {"available": True, "rows": [
            {"customer_code": "K3", "customer_name": "Khach K3", "sales_channel": "OTC", "overdue_gt_45": 70e6},
            {"customer_code": "K9", "customer_name": "Khach K9", "sales_channel": "OTC", "overdue_gt_45": 90e6},
        ]},
        "overdue_ordering": {"rows": [
            {"customer_code": "K9", "customer_name": "Khach K9", "sales_channel": "OTC", "overdue_gt_45": 90e6,
             "new_orders": 2, "new_order_value": 5e6},
        ]},
    }


def _builder(bundle):
    def build(team_code, customer_codes):
        view = scope_insight_bundle_to_team(bundle, team_code, customer_codes)
        view["as_of_display"] = "14/09/2026"
        return view
    return build


def test_loc_bundle_chi_giu_doi_minh_va_khach_cua_doi():
    view = scope_insight_bundle_to_team(_bundle(), "QLV01", {"K1", "K3"})

    assert [t["team_code"] for t in view["team_pace"]["teams"]] == ["QLV01"]
    assert [t["team_code"] for t in view["team_pace"]["at_risk"]] == ["QLV01"]
    assert view["team_pace"]["not_projected"] == []
    assert [(r["customer_code"], r["sales_channel"]) for r in view["silent_customers"]["rows"]] == [("K1", "OTC")]
    assert [r["customer_code"] for r in view["new_over45"]["rows"]] == ["K3"]
    assert view["overdue_ordering"]["rows"] == []


def test_khach_gan_doi_theo_snapshot_gan_nhat_cua_chinh_khach():
    codes = _team_customer_codes(_KhoGia(PHAN_CONG), "QLV01", dt.date(2026, 9, 15))

    assert codes == {"K1", "K3"}


def test_khong_ra_khach_nao_thi_dung_khong_mo_rong_pham_vi():
    with pytest.raises(ValueError):
        _team_customer_codes(_KhoGia([("TDV09", "K9", "QLV02", "2026-08-31")]), "QLV01", dt.date(2026, 9, 15))


def test_bao_cao_ngay_co_viec_can_xu_ly_chi_khach_cua_doi_va_du_phong_doi():
    metrics = build_qlv_digest_metrics(employee_code="QLV01", region="MB", channel="OTC",
                                       as_of_date="2026-09-14", report_tools=_KhoGia(PHAN_CONG),
                                       insight_builder=_builder(_bundle()))

    _, _, sections = build_qlv_teams_content(metrics, tien)
    action = sections[0]
    rendered = str(sections)

    assert action["title"] == "📌 VIỆC CẦN XỬ LÝ (2)"
    assert "Khach K1 (K1, OTC)" in rendered and "Khach K3 (K3)" in rendered
    assert "Khach K2" not in rendered and "Khach K9" not in rendered and "Khach K1 ETC" not in rendered
    assert "Đội 2" not in rendered and "Đội 3" not in rendered
    # Dự phóng đội ở mục Tiến độ đội, không lặp thành "1 đội QLV..." trong Việc cần xử lý.
    assert not any("đội QLV" in item for item in action["items"])
    kpi = next(s for s in sections if s["id"] == "section_qlv_team_kpi")
    assert any("đạt 30% chỉ tiêu; dự phóng cuối tháng 45% — DƯỚI ngưỡng 60%" in item for item in kpi["items"])


def test_khong_xac_dinh_duoc_khach_cua_doi_thi_bao_chua_dung_duoc_va_khong_goi_bravo():
    metrics = build_qlv_digest_metrics(
        employee_code="QLV01", region="MB", channel="OTC", as_of_date="2026-09-14",
        report_tools=_KhoGia([("TDV09", "K9", "QLV02", "2026-08-31")]),
        insight_builder=lambda *a: pytest.fail("Không được dựng insight khi chưa biết khách của đội"))

    _, _, sections = build_qlv_teams_content(metrics, tien)

    assert sections[0]["title"] == "📌 VIỆC CẦN XỬ LÝ (chưa đánh giá)"
    assert "CHƯA dựng được" in sections[0]["items"][0]
    kpi = next(s for s in sections if s["id"] == "section_qlv_team_kpi")
    assert any("CHƯA đánh giá được" in item for item in kpi["items"])


def test_teams_toi_da_5_dong_email_toi_da_15_dong():
    tam_khach = [f"K{i}" for i in range(10, 18)]
    phan_cong = [("TDV01", cc, "QLV01", "2026-08-31") for cc in tam_khach]
    bundle = _bundle(silent_codes=tam_khach)

    daily = build_qlv_digest_metrics(employee_code="QLV01", region="MB", channel="OTC", as_of_date="2026-09-14",
                                     report_tools=_KhoGia(phan_cong), insight_builder=_builder(bundle))
    _, _, sections = build_qlv_teams_content(daily, tien)
    assert any("Đang liệt kê 5/8 khách" in item for item in sections[0]["items"])

    weekly = build_qlv_period_metrics(employee_code="QLV01", region="MB", channel="OTC", period_type="weekly",
                                      as_of_date="2026-09-14", report_tools=_KhoGia(phan_cong),
                                      insight_builder=_builder(bundle))
    html = build_qlv_period_email(weekly, tien)
    assert all(f"Khach {cc}" in html for cc in tam_khach)
    assert "Đang liệt kê" not in html


def test_kenh_etc_khong_co_insight_doi():
    metrics = build_qlv_digest_metrics(
        employee_code="QLV01", region="MB", channel="ETC", as_of_date="2026-09-14",
        report_tools=_KhoGia(PHAN_CONG), insight_builder=lambda *a: pytest.fail("ETC không có insight đội"))

    assert metrics["insights"] is None
    _, _, sections = build_qlv_teams_content(metrics, tien)
    assert not any(s["id"] == "section_qlv_action_items" for s in sections)


def test_tien_do_doi_truoc_ngay_15_chua_du_phong_va_doi_it_tdv():
    bundle = _bundle()
    bundle["team_pace"]["evaluated"] = False
    view = scope_insight_bundle_to_team(bundle, "QLV01", {"K1"})
    assert team_progress_lines(view, tien) == [
        "• Doanh số TDV trong đội: 30,000,000/100,000,000, đạt 30% chỉ tiêu; dự phóng cuối tháng tính từ ngày 15."]

    it_tdv = scope_insight_bundle_to_team(_bundle(), "QLV03", {"K1"})
    assert team_progress_lines(it_tdv, tien) == ["• Đội có ít TDV nên không dự phóng cuối tháng (chỉ tiêu 5,000,000)."]
