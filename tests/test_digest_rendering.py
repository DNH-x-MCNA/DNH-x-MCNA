"""
Unit test cho logic render Daily Digest (1.6)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.etl import _company_wide_alert_visible_to
from main import _digest_table


def test_company_wide_alert_visible_to():
    # Audience không bị giới hạn vùng (None) -> luôn thấy
    assert _company_wide_alert_visible_to(None, "Miền Nam") == True
    assert _company_wide_alert_visible_to(None, "Toàn quốc") == True

    # Alert thuộc cấp toàn quốc -> mọi audience vùng đều thấy
    assert _company_wide_alert_visible_to("nam", "Toàn quốc") == True
    assert _company_wide_alert_visible_to("trung", "Nhiều miền") == True
    assert _company_wide_alert_visible_to("bac", None) == True

    # Alert của vùng cụ thể -> chỉ audience vùng đó mới thấy
    assert _company_wide_alert_visible_to("nam", "Miền Nam") == True
    assert _company_wide_alert_visible_to("bac", "Miền Nam") == False
    assert _company_wide_alert_visible_to("trung", "Miền Nam") == False


def test_digest_table_with_and_without_warnings():
    metrics = {
        'revenue': {
            'change_pct': 5.0,
            'otc': 100, 'etc': 200, 'total': 300,
            'otc_invoice_count': 1, 'etc_invoice_count': 2, 'invoice_count': 3
        },
        'inventory': {
            'dead_stock_count': 0, 'near_stockout_count': 0
        },
        'highlights': []
    }
    
    # Không truyền warnings -> sections = None
    headers, rows, sections = _digest_table(metrics)
    assert sections is None
    
    # Truyền warnings -> tạo sections
    warnings = [
        {"label": "Tồn kho thấp", "value_display": "đã lặp 5 lần hôm nay"},
        {"label": "Cảnh báo hệ thống", "value_display": "đã lặp 2 lần hôm nay"}
    ]
    headers, rows, sections = _digest_table(metrics, warnings=warnings)
    
    assert sections is not None
    assert len(sections) == 1
    
    sec = sections[0]
    assert "Cảnh báo trong ngày (2)" in sec['title']
    assert sec['table_headers'] == ["Cảnh báo", "Số lần xuất hiện"]
    assert len(sec['table_rows']) == 2
    assert sec['table_rows'][0] == ["Tồn kho thấp", "đã lặp 5 lần hôm nay"]


def test_digest_table_warning_limit():
    metrics = {
        'revenue': {
            'change_pct': 5.0,
            'otc': 100, 'etc': 200, 'total': 300,
            'otc_invoice_count': 1, 'etc_invoice_count': 2, 'invoice_count': 3
        },
        'inventory': {
            'dead_stock_count': 0, 'near_stockout_count': 0
        },
        'highlights': []
    }
    
    # Truyền > 8 warnings -> trần 8 dòng
    warnings = [{"label": f"Alert {i}", "value_display": "1 lần"} for i in range(10)]
    _, _, sections = _digest_table(metrics, warnings=warnings)
    
    sec = sections[0]
    assert len(sec['table_rows']) == 8


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
