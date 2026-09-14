# -*- coding: utf-8 -*-
"""Báo cáo định kỳ dùng insight đã kiểm thử ngược (14/09/2026) — không gọi Bravo, không gửi gì."""
import datetime as dt

import pytest

import main
from src import insight_report, insights, notifier
from src.alerts import format_vietnamese_money


def _view(**over):
    view = {
        "as_of_display": "22/09/2026", "lookback": 3, "errors": {},
        "month_pace": {
            "OTC": {"mtd": 21_500_000_000, "gap_pct": 18.4, "projected_full_month": 33_000_000_000,
                    "projected_vs_baseline_pct": -18.4},
            "ETC": {"mtd": 19_800_000_000, "gap_pct": -6.2, "projected_full_month": 34_100_000_000,
                    "projected_vs_baseline_pct": 6.2},
        },
        "team_pace": {"applicable": True, "evaluated": True, "min_day": 15, "threshold_pct": 60.0,
                      "at_risk": [{"team_code": "TM23110105", "team_name": "QLV mẫu Một", "members": 6,
                                   "achievement_pct": 38.2, "projection_pct": 52.0}]},
        "silent_customers": {"evaluated": True, "min_day": 20, "rows": [
            {"customer_code": "HDU00443", "customer_name": "Nhà thuốc mẫu A", "sales_channel": "OTC",
             "baseline_monthly": 184_000_000}]},
        "new_over45": {"available": True, "compared_with": "2026-09-15", "rows": [
            {"customer_code": "HBI00286", "customer_name": "Bệnh viện mẫu B", "sales_channel": "ETC",
             "overdue_gt_45": 3_071_770_064}]},
        "overdue_ordering": {"rows": [
            {"customer_code": "NDI00720", "customer_name": "Bệnh viện mẫu C", "sales_channel": "ETC",
             "overdue_gt_45": 120_000_000, "new_orders": 2, "new_order_value": 15_300_000}]},
    }
    view.update(over)
    view["action_count"] = insight_report.action_count(view)
    return view


def _metrics(insight_view):
    return {
        "date": "22/09/2026", "period_range": "Tuần 21/09/2026 - 22/09/2026", "updated_at": "17:45 22/09/2026",
        "region": None, "channel": None,
        "revenue": {"otc": 7_000_000_000, "etc": 5_345_678_900, "total": 12_345_678_900, "invoice_count": 300,
                    "otc_invoice_count": 250, "etc_invoice_count": 50, "prev_total": 11_000_000_000,
                    "change_pct": 12.2, "prev_period_label": "14/09-15/09/2026"},
        "receivables": None,
        "inventory": {"dead_stock_available": False, "near_stockout_available": False},
        # Log cảnh báo cũ vẫn có trong metrics nhưng không được hiển thị nữa.
        "highlights": [{"label": "Nợ quá hạn lớn (top 5)", "sent_at_display": "09:12 22/09", "value_display": "2,4 tỷ"}],
        "warning_alerts": [{"alert_name": "CẢNH BÁO LẶP", "repeat_count": 16, "issue": "lặp"}],
        "has_critical": True,
        "insights": insight_view,
    }


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_feature_flags": {}})


def test_email_thay_log_canh_bao_bang_viec_can_xu_ly_va_tien_do_thang():
    html = notifier.build_digest_email(_metrics(_view()), period_label="Weekly", audience="C-Level",
                                       scope_label="Toàn quốc")

    assert "Việc Cần Xử Lý" in html and "Tiến Độ Tháng" in html
    assert "Điểm Nổi Bật" not in html and "Cảnh Báo Trong Kỳ" not in html and "CẢNH BÁO LẶP" not in html
    for text in ("QLV mẫu Một", "HDU00443", "HBI00286", "NDI00720", "Chậm 18%", "Nhanh 6%"):
        assert text in html, text
    # Tiền theo kiểu Việt Nam, không còn "12,345,678,900 đ".
    assert "12,35 tỷ đ" in html and "12,345,678,900" not in html
    assert "4 việc cần xử lý" in html          # preheader trong hộp thư


def test_email_chua_toi_ngay_danh_gia_va_danh_sach_dai():
    silent_rows = [{"customer_code": f"KH{i:02d}", "customer_name": f"Khách {i}", "sales_channel": "OTC",
                    "baseline_monthly": 60_000_000} for i in range(12)]
    view = _view(team_pace={"applicable": True, "evaluated": False, "min_day": 15, "at_risk": []},
                 silent_customers={"evaluated": True, "min_day": 20, "rows": silent_rows},
                 new_over45={"available": False, "rows": []}, overdue_ordering={"rows": []})

    html = notifier.build_digest_email(_metrics(view), period_label="Monthly")

    assert "Đánh giá từ ngày 15" in html
    assert "Đang liệt kê 10/12 khách" in html
    assert "Chưa có bản chụp công nợ đủ cũ" in html


def test_email_khong_dung_duoc_insight_van_gui_phan_con_lai():
    html = notifier.build_digest_email(_metrics(None), period_label="Weekly")
    assert "Việc Cần Xử Lý" not in html and "Doanh Thu (OTC + ETC)" in html


def test_email_kenh_etc_khong_co_muc_doi_qlv():
    view = _view(team_pace={"applicable": False, "evaluated": True, "at_risk": []})
    html = notifier.build_digest_email({**_metrics(view), "channel": "ETC"}, period_label="Weekly")
    assert "Đội QLV có nguy cơ" not in html


def test_teams_daily_bo_so_sanh_hom_nay_do_dang_voi_hom_qua_va_bo_log_canh_bao():
    headers, rows = main._digest_table(_metrics(_view()))

    labels = [r[0] for r in rows]
    assert not any(label.startswith("Cảnh báo:") for label in labels)
    assert all("so kỳ" not in str(r[1]) for r in rows)
    assert any(label.startswith("Tổng doanh thu hôm nay") for label in labels)
    pace = next(r for r in rows if r[0].startswith("Lũy kế tháng OTC"))
    assert "chậm 18%" in pace[1] and "dự phóng cả tháng 33,00 tỷ đ" in pace[1]


def test_action_lines_gioi_han_moi_nhom_va_ghi_so_da_liet_ke():
    rows = [{"customer_code": f"KH{i}", "customer_name": f"Khách {i}", "sales_channel": "OTC",
             "baseline_monthly": 60e6} for i in range(7)]
    lines = insight_report.action_lines(_view(silent_customers={"evaluated": True, "rows": rows}),
                                        format_vietnamese_money, max_rows=5)
    assert "• 7 khách mua đều chưa có đơn tháng này:" in lines
    assert "   - Đang liệt kê 5/7 khách." in lines

    empty = _view(team_pace={"applicable": True, "evaluated": True, "at_risk": []},
                  silent_customers={"evaluated": True, "rows": []}, new_over45={"available": True, "rows": []},
                  overdue_ordering={"rows": []}, errors={"receivables": "timeout"})
    lines = insight_report.action_lines(empty, format_vietnamese_money)
    assert "• Không có việc nào vượt ngưỡng cảnh báo." in lines
    assert any("chưa lấy được" in line and "receivables" in line for line in lines)


def test_attach_insights_loc_pham_vi_nguoi_nhan_va_loi_khong_lam_hong_bao_cao(monkeypatch):
    bundle = {
        "as_of": dt.date(2026, 9, 22), "rules": insights.DEFAULT_RULES, "errors": {},
        "team_pace": {"evaluated": True, "min_day": 15, "threshold_pct": 60.0, "at_risk": [
            {"team_code": "Q1", "region_key": "bac", "sales_channel": "OTC"},
            {"team_code": "Q2", "region_key": "nam", "sales_channel": "OTC"}]},
        "silent_customers": {"evaluated": True, "rows": [{"customer_code": "K1", "region_key": "nam",
                                                          "sales_channel": "ETC"}]},
        "new_over45": {"available": True, "rows": []}, "overdue_ordering": {"rows": []},
    }
    goi = []
    monkeypatch.setattr(insights, "build_insight_bundle", lambda: bundle)
    monkeypatch.setattr(insights, "channel_pace_for_scope",
                        lambda as_of, region=None, channel=None, rules=None: goi.append((region, channel)) or {})

    view = insight_report.attach_insights(region="bac", channel="OTC")

    assert [t["team_code"] for t in view["team_pace"]["at_risk"]] == ["Q1"]
    assert view["silent_customers"]["rows"] == [] and view["action_count"] == 1
    assert goi == [("bac", "OTC")] and view["as_of_display"] == "22/09/2026"

    monkeypatch.setattr(insights, "build_insight_bundle", lambda: (_ for _ in ()).throw(RuntimeError("Bravo")))
    assert insight_report.attach_insights(region="bac") is None
