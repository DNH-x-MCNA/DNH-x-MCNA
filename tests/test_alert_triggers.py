"""
Unit test đơn giản cho logic ngưỡng của các trigger cảnh báo (Go-Live Plan Phase 1.2).
Chỉ test phần logic thuần (pure), KHÔNG gọi DB/gửi thông báo thật.

Chạy:  python -m pytest tests/test_alert_triggers.py -v
Hoặc:  python tests/test_alert_triggers.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.alerts import (
    revenue_drop_ratio, overdue_ratio, concentration_ratio, return_rate,
    kpi_sales_force_risk_reasons,
)

RISK_MAP = {"TDV": 0.65, "CS": 0.65, "TK": 0.60, "TBP": 0.70, "TP": 0.70}


def test_revenue_drop_fires_above_threshold():
    # Giảm 25% (100 -> 75), ngưỡng 20% -> phải vượt ngưỡng (fire)
    ratio = revenue_drop_ratio(prev_revenue=100.0, latest_revenue=75.0)
    assert ratio is not None
    assert abs(ratio - 0.25) < 1e-9
    assert ratio > 0.20  # trigger bắn


def test_revenue_drop_silent_below_threshold():
    # Giảm 10% (100 -> 90), ngưỡng 20% -> KHÔNG bắn
    ratio = revenue_drop_ratio(prev_revenue=100.0, latest_revenue=90.0)
    assert ratio is not None
    assert abs(ratio - 0.10) < 1e-9
    assert ratio <= 0.20  # không bắn


def test_revenue_growth_is_negative_ratio():
    # Tăng trưởng (100 -> 120) -> tỷ lệ âm, chắc chắn không bắn
    ratio = revenue_drop_ratio(prev_revenue=100.0, latest_revenue=120.0)
    assert ratio is not None
    assert ratio < 0


def test_revenue_drop_handles_zero_prev():
    # Kỳ trước = 0 -> không chia được, trả None (không bắn, không crash)
    assert revenue_drop_ratio(prev_revenue=0.0, latest_revenue=50.0) is None


def test_revenue_drop_handles_none():
    assert revenue_drop_ratio(None, 50.0) is None
    assert revenue_drop_ratio(50.0, None) is None


def test_revenue_drop_exactly_at_threshold_does_not_fire():
    # Đúng bằng ngưỡng 20% -> điều kiện là "> threshold" nên KHÔNG bắn
    ratio = revenue_drop_ratio(prev_revenue=100.0, latest_revenue=80.0)
    assert abs(ratio - 0.20) < 1e-9
    assert not (ratio > 0.20)


def test_overdue_ratio_basic_and_zero_guard():
    assert abs(overdue_ratio(35.0, 100.0) - 0.35) < 1e-9
    assert overdue_ratio(35.0, 0.0) is None          # chia 0 -> None
    assert overdue_ratio(None, 100.0) is None
    assert overdue_ratio(0.0, 100.0) == 0.0          # không nợ quá hạn -> 0, hợp lệ


def test_concentration_ratio_basic_and_zero_guard():
    assert abs(concentration_ratio(60.0, 100.0) - 0.60) < 1e-9
    assert concentration_ratio(10.0, 0.0) is None
    assert concentration_ratio(None, 100.0) is None


def test_return_rate_basic_and_zero_guard():
    assert abs(return_rate(5.0, 100.0) - 0.05) < 1e-9
    assert return_rate(5.0, 0.0) is None             # doanh số 0 -> None (không chia)
    assert return_rate(None, 100.0) is None


def test_kpi_risk_fires_at_or_below_role_threshold():
    # TDV, ngưỡng 65% -> đúng bằng ngưỡng cũng phải bắn ("<=", không phải "<")
    reasons = kpi_sales_force_risk_reasons("TDV", 0.65, 0.90, 0.90, RISK_MAP, 0.80, 0.75)
    assert any("chấm dứt HĐLĐ" in r for r in reasons)


def test_kpi_risk_silent_above_role_threshold():
    reasons = kpi_sales_force_risk_reasons("TDV", 0.66, 0.90, 0.90, RISK_MAP, 0.80, 0.75)
    assert not any("chấm dứt HĐLĐ" in r for r in reasons)


def test_kpi_risk_uses_role_specific_threshold():
    # 0.62 dưới ngưỡng TK (0.60)? Không -> không bắn cho TK; nhưng bắn cho TDV/CS (ngưỡng 0.65)
    assert kpi_sales_force_risk_reasons("TK", 0.62, 0.90, 0.90, RISK_MAP, 0.80, 0.75) == []
    reasons = kpi_sales_force_risk_reasons("TDV", 0.62, 0.90, 0.90, RISK_MAP, 0.80, 0.75)
    assert any("chấm dứt HĐLĐ" in r for r in reasons)


def test_kpi_risk_quarter_and_year_floor():
    reasons = kpi_sales_force_risk_reasons("TP", 0.90, 0.79, 0.74, RISK_MAP, 0.80, 0.75)
    assert any("thưởng quý" in r for r in reasons)
    assert any("sàn 0%" in r for r in reasons)


def test_kpi_risk_no_reasons_when_all_healthy():
    assert kpi_sales_force_risk_reasons("TP", 0.90, 0.85, 0.80, RISK_MAP, 0.80, 0.75) == []


def test_kpi_risk_unmapped_position_code_skips_contract_check():
    # QLV không nằm trong 5 vai trò của QĐ 0429-2 -> không có ngưỡng chấm dứt HĐLĐ, không crash
    reasons = kpi_sales_force_risk_reasons("QLV", 0.10, 0.90, 0.90, RISK_MAP, 0.80, 0.75)
    assert reasons == []


def test_kpi_risk_none_values_do_not_crash():
    reasons = kpi_sales_force_risk_reasons("TDV", None, None, None, RISK_MAP, 0.80, 0.75)
    assert reasons == []


def test_kpi_risk_all_three_reasons_combine():
    reasons = kpi_sales_force_risk_reasons("TBP", 0.50, 0.50, 0.50, RISK_MAP, 0.80, 0.75)
    assert len(reasons) == 3


if __name__ == '__main__':
    passed = 0
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith('test_') and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
                passed += 1
            except AssertionError as e:
                print(f"  FAIL  {name}: {e}")
                failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
