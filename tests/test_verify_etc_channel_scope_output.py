from scripts import verify_etc_channel_scope as verify


def test_bao_cao_mac_dinh_than_thien_khong_phai_json(capsys):
    verify._print_human({
        "period": {"date_from": "2026-08-01", "date_to": "2026-08-31"},
        "legacy_employee_schema_bypassed_for_identity_only": False,
        "checks": [
            {"check": "revenue_by_channel", "result": "PASS",
             "etc_revenue": 1_200_000, "etc_invoices": 12},
            {"check": "order_timing", "result": "PASS", "etc_flagged": 2},
        ],
        "result": "PASS",
    })

    output = capsys.readouterr().out
    assert "[ĐẠT] Doanh thu ETC không lộ số OTC" in output
    assert "1,200,000đ" in output
    assert "KẾT LUẬN: ĐẠT" in output
    assert '"checks"' not in output
