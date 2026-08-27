# -*- coding: utf-8 -*-
import pytest

import main
from scripts.verify_qlv_digest_reconciliation import _discover_qlv_recipients
from src.qlv_digest import (
    QLVDigestScopeError,
    build_qlv_digest_metrics,
    build_qlv_teams_content,
)


class _FakeReportTools:
    def __init__(self):
        self.calls = []

    def revenue_by_channel(self, date_from, date_to, **scope):
        self.calls.append(("revenue", date_from, date_to, scope))
        is_month = date_from.endswith("-01")
        revenue = 12_000_000 if is_month else 2_000_000
        invoices = 6 if is_month else 1
        return {
            "otc": {"revenue": revenue, "invoices": invoices},
            "etc": {"revenue": 0, "invoices": 0},
            "total": {"revenue": revenue, "invoices": invoices},
        }

    def employee_kpi(self, as_of_date, **kwargs):
        self.calls.append(("kpi", as_of_date, kwargs))
        return {
            "as_of": as_of_date,
            "rows": [
                {
                    "employee_code": "QLV01", "name": "Quản lý A", "pct": 72.5,
                    "meets_kpi": False, "meets_full_target": False,
                },
                {
                    "employee_code": "TDV01", "name": "Nhân viên 1", "pct": 85.0,
                    "meets_kpi": True, "meets_full_target": False,
                },
                {
                    "employee_code": "TDV02", "name": "Nhân viên 2", "pct": 45.0,
                    "meets_kpi": False, "meets_full_target": False,
                },
            ],
        }

    def customer_lifecycle_summary(self, **kwargs):
        self.calls.append(("lifecycle", kwargs))
        return {
            "months": [{
                "month": "2026-08", "tong_khach": 30, "khach_moi": 3,
                "doanh_so_khach_moi": 1_500_000,
            }],
        }

    def customer_revenue_debt_risk(self, **kwargs):
        self.calls.append(("debt", kwargs))
        return {
            "status": "ok",
            "customers": [{
                "customer_code": "KH01", "customer_name": "Khách A",
                "overdue": 60_000_000, "change_pct": -20.0,
            }],
        }

    @staticmethod
    def data_freshness_note():
        return "Dữ liệu cập nhật đến 16:00 27/08/2026."


def test_qlv_digest_ep_scope_vao_moi_nguon_nghiep_vu():
    tools = _FakeReportTools()

    result = build_qlv_digest_metrics(
        employee_code="QLV01",
        region="bac",
        channel="OTC",
        as_of_date="2026-08-27",
        report_tools=tools,
    )

    assert result["employee_code"] == "QLV01"
    assert result["area_code"] == "MB"
    assert result["channel"] == "OTC"
    assert result["inventory_included"] is False
    assert "inventory" not in result

    revenue_calls = [call for call in tools.calls if call[0] == "revenue"]
    assert len(revenue_calls) == 2
    for _, _, _, scope in revenue_calls:
        assert scope == {
            "scope_area_code": "MB",
            "scope_channel": "OTC",
            "scope_employee_code": "QLV01",
        }

    kpi_call = next(call for call in tools.calls if call[0] == "kpi")
    assert kpi_call[2]["scope_area_code"] == "MB"
    assert kpi_call[2]["scope_employee_code"] == "QLV01"
    lifecycle_call = next(call for call in tools.calls if call[0] == "lifecycle")
    assert lifecycle_call[1]["scope_employee_code"] == "QLV01"
    debt_call = next(call for call in tools.calls if call[0] == "debt")
    assert debt_call[1]["scope_employee_code"] == "QLV01"
    assert debt_call[1]["scope_channel"] == "OTC"

    assert result["team_kpi"]["member_count"] == 2
    assert result["team_kpi"]["kpi_achieved_count"] == 1
    assert result["team_kpi"]["lowest_completion"][0]["employee_code"] == "TDV02"


@pytest.mark.parametrize(
    "employee_code,region,error_text",
    [
        ("", "bac", "employee_code"),
        ("QLV01", "", "thiếu miền"),
        ("QLV01", "khong-hop-le", "thiếu miền"),
    ],
)
def test_qlv_digest_thieu_scope_thi_dung_khong_fallback(employee_code, region, error_text):
    with pytest.raises(QLVDigestScopeError, match=error_text):
        build_qlv_digest_metrics(
            employee_code=employee_code,
            region=region,
            as_of_date="2026-08-27",
            report_tools=_FakeReportTools(),
        )


@pytest.mark.parametrize(
    "position,own_region,error_text",
    [
        ("TDV", "MB", "không phải mã QLV"),
        ("QLV", "MN", "không khớp miền"),
    ],
)
def test_qlv_digest_kiem_tra_dung_danh_tinh_va_mien(position, own_region, error_text):
    tools = _FakeReportTools()
    tools._q = lambda sql, params: [{"position_code": position, "area_code": own_region}]

    with pytest.raises(QLVDigestScopeError, match=error_text):
        build_qlv_digest_metrics(
            employee_code="QLV01",
            region="MB",
            as_of_date="2026-08-27",
            report_tools=tools,
        )


def test_noi_dung_teams_qlv_khong_co_ton_kho():
    metrics = build_qlv_digest_metrics(
        employee_code="QLV01",
        region="MB",
        channel="OTC",
        as_of_date="2026-08-27",
        report_tools=_FakeReportTools(),
    )

    headers, rows, sections = build_qlv_teams_content(metrics, lambda value: f"{value:,.0f} đ")
    rendered = str([headers, rows, sections]).lower()

    assert "tồn kho" not in rendered
    assert "inventory" not in rendered
    assert "doanh số đội trong ngày" in rendered
    assert "tiến độ đội" in rendered
    assert "khách hàng cần ưu tiên công nợ" in rendered


def _fake_qlv_metrics():
    return {
        "date": "2026-08-27",
        "employee_code": "QLV01",
        "area_code": "MB",
        "channel": "OTC",
        "daily_revenue": {"total": {"revenue": 1, "invoices": 1}},
        "month_to_date_revenue": {"total": {"revenue": 10, "invoices": 2}},
        "team_kpi": {"not_applicable": True},
        "customer_lifecycle": {"not_applicable": True},
        "debt_risk": {"customers": []},
        "freshness_note": "Dữ liệu mới.",
        "inventory_included": False,
    }


def test_send_daily_qlv_di_nhanh_rieng_va_dinh_tuyen_dung_nguoi(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {
        "report_recipients": [{
            "audience": "QLV A",
            "role": "qlv",
            "region": "bac",
            "channel": "OTC",
            "employee_code": "QLV01",
            "teams_recipient": "nguoi-nhan-a",
            "teams_webhook": "https://flow.example.test",
        }],
    })
    captured = {}

    def fake_builder(**kwargs):
        captured["scope"] = kwargs
        return _fake_qlv_metrics()

    monkeypatch.setattr(main, "build_qlv_digest_metrics", fake_builder)
    monkeypatch.setattr(
        main,
        "get_daily_digest_metrics",
        lambda **kwargs: pytest.fail("QLV không được chạy nhánh digest toàn miền cũ"),
    )
    monkeypatch.setattr(main, "send_teams_alert", lambda **kwargs: captured.setdefault("send", kwargs) or True)

    assert main.send_daily_digest(dry_run=False) is True
    assert captured["scope"] == {
        "employee_code": "QLV01", "region": "bac", "channel": "OTC",
    }
    assert captured["send"]["recipient"] == "nguoi-nhan-a"
    assert captured["send"]["audience"] == "QLV A"
    assert all("tồn kho" not in str(section).lower() for section in captured["send"]["sections"])


@pytest.mark.parametrize("missing_field", ["employee_code", "region", "teams_recipient"])
def test_send_daily_qlv_thieu_cau_hinh_thi_khong_gui(monkeypatch, missing_field):
    recipient = {
        "audience": "QLV lỗi cấu hình",
        "role": "qlv",
        "region": "bac",
        "channel": "OTC",
        "employee_code": "QLV01",
        "teams_recipient": "nguoi-nhan-a",
    }
    recipient[missing_field] = None
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [recipient]})
    monkeypatch.setattr(
        main,
        "build_qlv_digest_metrics",
        lambda **kwargs: pytest.fail("Không được dựng báo cáo khi thiếu cấu hình fail-closed"),
    )
    monkeypatch.setattr(
        main,
        "send_teams_alert",
        lambda **kwargs: pytest.fail("Không được gửi khi thiếu cấu hình fail-closed"),
    )

    assert main.send_daily_digest(dry_run=False) is False


def test_co_employee_code_nhung_quen_role_qlv_thi_khong_fallback_toan_mien(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [{
        "audience": "QLV quên role", "region": "bac", "channel": "OTC",
        "employee_code": "QLV01", "teams_recipient": "nguoi-nhan-a",
    }]})
    monkeypatch.setattr(
        main,
        "get_daily_digest_metrics",
        lambda **kwargs: pytest.fail("Không được chạy nhánh toàn miền khi đã có employee_code"),
    )
    monkeypatch.setattr(
        main,
        "send_teams_alert",
        lambda **kwargs: pytest.fail("Không được gửi khi role QLV cấu hình thiếu"),
    )

    assert main.send_daily_digest(dry_run=False) is False


def test_qlv_etc_khong_lay_kpi_otc_gan_nhan_etc():
    tools = _FakeReportTools()
    result = build_qlv_digest_metrics(
        employee_code="QLV01",
        region="MB",
        channel="ETC",
        as_of_date="2026-08-27",
        report_tools=tools,
    )

    assert result["team_kpi"]["not_applicable"] is True
    assert result["customer_lifecycle"]["not_applicable"] is True
    assert not any(call[0] in {"kpi", "lifecycle"} for call in tools.calls)


def test_weekly_monthly_khong_duoc_gui_bao_cao_toan_mien_cho_qlv(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {
        "report_feature_flags": {},
        "report_recipients": [
            {
                "audience": "QLV A", "role": "qlv", "region": "bac", "channel": "OTC",
                "employee_code": "QLV01", "emails": ["qlv@example.test"],
            },
            {
                "audience": "Quản lý Miền Bắc", "region": "bac", "channel": None,
                "emails": ["manager@example.test"],
            },
        ],
    })
    metric_calls = []

    def fake_metrics(**scope):
        metric_calls.append(scope)
        return {"date": "2026-08-27", "period_range": "Tuần thử"}

    monkeypatch.setattr(main, "build_digest_email", lambda *args, **kwargs: "<html></html>")

    result = main._send_periodic_email_report(
        fake_metrics,
        "Weekly",
        "Báo cáo tuần",
        dry_run=True,
    )

    assert result is True
    assert metric_calls == [{"region": "bac", "channel": None}]


def test_weekly_monthly_chi_co_qlv_thi_dung_khong_fallback_toan_quoc(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: {
        "report_feature_flags": {},
        "report_recipients": [{
            "audience": "QLV A", "role": "qlv", "region": "bac", "channel": "OTC",
            "employee_code": "QLV01", "emails": ["qlv@example.test"],
        }],
    })
    monkeypatch.setattr(
        main,
        "build_digest_email",
        lambda *args, **kwargs: pytest.fail("Không được dựng báo cáo toàn quốc fallback"),
    )

    assert main._send_periodic_email_report(
        lambda **scope: pytest.fail("Không được đọc số toàn miền/toàn quốc"),
        "Monthly",
        "Báo cáo tháng",
        dry_run=True,
    ) is False


def test_discover_qlv_tu_snapshot_khong_can_mapping_teams():
    class DiscoveryTools:
        @staticmethod
        def _q(sql, params):
            if "MAX(save_date)" in sql:
                return [{"d": "2026-08-27"}]
            if "DISTINCT manager_code" in sql:
                return [{"manager_code": "QLV01"}, {"manager_code": "QLV02"}]
            if "FROM dim_nhanvien" in sql:
                return [
                    {"employee_code": "QLV01", "area_code": "MB", "position_code": "QLV"},
                    {"employee_code": "QLV02", "area_code": "MN", "position_code": "QLV"},
                ]
            raise AssertionError(sql)

    result = _discover_qlv_recipients(DiscoveryTools(), "2026-08-27")

    assert [(row["employee_code"], row["region"]) for row in result] == [
        ("QLV01", "MB"), ("QLV02", "MN"),
    ]
    assert all(row["role"] == "qlv" and row["channel"] == "OTC" for row in result)
