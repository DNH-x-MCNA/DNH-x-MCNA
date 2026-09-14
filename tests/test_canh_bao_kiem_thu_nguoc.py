# -*- coding: utf-8 -*-
"""Bộ cảnh báo đã kiểm thử ngược (14/09/2026): chống lặp, định tuyến vùng/kênh, main chỉ gọi bộ mới.

Không gọi Bravo, không gửi Teams: send_alert_to_all_channels bị thay bằng bộ ghi, DB trạng thái
chống lặp nằm trong tmp_path.
"""
import copy
import datetime as dt

import pytest

import src.alerts as alerts
from src import insights

AS_OF = dt.date(2026, 9, 22)


@pytest.fixture
def gui(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts, "STATE_DB_DIR", str(tmp_path))
    monkeypatch.setattr(alerts, "STATE_DB_PATH", str(tmp_path / "alerts_state.db"))
    sent = []
    monkeypatch.setattr(alerts, "send_alert_to_all_channels", lambda **kw: sent.append(kw) or True)
    return sent


def _pace(day, gap):
    return {"as_of": "2026-09-22", "day": day, "mtd": 7e9, "expected_mtd": 10e9, "gap_pct": gap,
            "expected_share_pct": 40.0, "projected_full_month": 17.5e9, "projected_vs_baseline_pct": -gap,
            "baseline_full_month": 25e9, "prev_month_same_days": 9e9, "vs_prev_month_same_days_pct": -22.2}


def _bundle(**parts):
    bundle = {"as_of": AS_OF, "rules": copy.deepcopy(insights.DEFAULT_RULES), "errors": {},
              "channel_pace": {}, "team_pace": {"evaluated": False, "teams": [], "at_risk": []},
              "silent_customers": {"evaluated": False, "rows": []},
              "new_over45": {"available": False, "rows": []}, "overdue_ordering": {"rows": []}}
    bundle.update(parts)
    return bundle


def test_nhip_kenh_gui_mot_lan_va_chi_gui_lai_khi_xau_them_tron_bac(gui):
    bundle = _bundle(channel_pace={"OTC": _pace(22, 35.0), "ETC": _pace(22, 5.0)})

    alerts.check_channel_month_pace_alert(bundle)
    alerts.check_channel_month_pace_alert(bundle)
    assert [s["channel"] for s in gui] == ["OTC"]
    assert gui[0]["severity"] == "CRITICAL" and gui[0]["region"] == "Toàn quốc"

    bundle["channel_pace"]["OTC"]["gap_pct"] = 39.0      # vẫn bậc 30
    alerts.check_channel_month_pace_alert(bundle)
    assert len(gui) == 1
    bundle["channel_pace"]["OTC"]["gap_pct"] = 41.0      # sang bậc 40
    alerts.check_channel_month_pace_alert(bundle)
    assert len(gui) == 2


def test_nhip_kenh_chua_toi_ngay_danh_gia_thi_khong_bao_du_cham_nhieu(gui):
    alerts.check_channel_month_pace_alert(_bundle(channel_pace={"OTC": _pace(9, 60.0), "ETC": _pace(7, 60.0)}))
    alerts.check_channel_month_pace_alert(_bundle(channel_pace={"OTC": None}))
    assert gui == []


def _doi(code, region_key, projection):
    return {"team_code": code, "team_name": f"QLV {code}", "members": 6, "achievement_pct": projection / 2,
            "projection_pct": projection, "region_key": region_key, "sales_channel": "OTC"}


def test_doi_qlv_gom_theo_mien_gui_teams_ngay_va_khong_lap(gui):
    teams = [_doi("MBKV1", "bac", 45.0), _doi("MBKV7", "bac", 55.0), _doi("TM24050201", "nam", 50.0)]
    bundle = _bundle(team_pace={"evaluated": True, "min_day": 15, "threshold_pct": 60.0,
                                "teams": teams, "at_risk": teams})

    alerts.check_team_pace_alert(bundle)
    alerts.check_team_pace_alert(bundle)

    assert sorted(s["region"] for s in gui) == ["Miền Bắc", "Miền Nam"]
    bac = next(s for s in gui if s["region"] == "Miền Bắc")
    assert len(bac["table_rows"]) == 2
    assert bac["channel"] == "OTC" and bac["severity"] == "WARNING"
    assert bac["require_critical_for_teams"] is False       # việc cần xử lý trong tuần phải tới Teams

    teams[0]["projection_pct"] = 38.0                        # tụt từ bậc 50 xuống bậc 60 thiếu hụt
    alerts.check_team_pace_alert(bundle)
    assert len(gui) == 3 and gui[-1]["table_rows"][0][0].startswith("QLV MBKV1")


def test_doi_qlv_chua_danh_gia_thi_khong_gui(gui):
    teams = [_doi("MBKV1", "bac", 10.0)]
    alerts.check_team_pace_alert(_bundle(team_pace={"evaluated": False, "min_day": 15, "teams": teams,
                                                    "at_risk": teams}))
    assert gui == []


def test_khach_mua_deu_im_lang_gui_theo_kenh_vung_moi_khach_mot_lan_trong_thang(gui):
    rows = [
        {"customer_code": "HDU00443", "customer_name": "Dược Thái Bình An", "sales_channel": "OTC",
         "region_key": "bac", "baseline_monthly": 184e6, "months_ordered_by_this_day": 6, "lookback_months": 6},
        {"customer_code": "BV01", "customer_name": "Bệnh viện 01", "sales_channel": "ETC",
         "region_key": "bac", "baseline_monthly": 300e6, "months_ordered_by_this_day": 5, "lookback_months": 6},
    ]
    bundle = _bundle(silent_customers={"evaluated": True, "rows": rows})

    alerts.check_silent_regular_customers_alert(bundle)
    alerts.check_silent_regular_customers_alert(bundle)

    assert sorted((s["channel"], s["region"]) for s in gui) == [("ETC", "Miền Bắc"), ("OTC", "Miền Bắc")]
    assert all(s["require_critical_for_teams"] is False for s in gui)
    assert next(s for s in gui if s["channel"] == "ETC")["table_rows"][0][3] == "5/6"


def test_khach_moi_vao_no_tren_45_ngay_can_ban_chup_cu_va_moi_khach_mot_lan(gui):
    row = {"customer_code": "HBI00286", "customer_name": "BVĐK Hoà Bình", "sales_channel": "ETC",
           "area_code": "MB", "overdue_gt_45": 3.07e9, "region_key": "bac"}
    alerts.check_new_over45_debtors_alert(_bundle(new_over45={"available": False, "rows": [row]}))
    assert gui == []

    bundle = _bundle(new_over45={"available": True, "compared_with": "2026-09-15", "min_value": 50e6, "rows": [row]})
    alerts.check_new_over45_debtors_alert(bundle)
    alerts.check_new_over45_debtors_alert(bundle)
    assert len(gui) == 1
    assert gui[0]["severity"] == "CRITICAL" and gui[0]["region"] == "Miền Bắc" and gui[0]["channel"] == "ETC"


def test_no_tren_45_ngay_van_len_don_moi_khach_mot_lan_moi_thang(gui):
    rows = [{"customer_code": "A", "customer_name": "Nhà thuốc A", "sales_channel": "OTC", "area_code": "MN",
             "overdue_gt_45": 80e6, "balance_end": 120e6, "new_orders": 2, "new_order_value": 15e6,
             "region_key": "nam"}]
    bundle = _bundle(overdue_ordering={"rows": rows})
    alerts.check_overdue_over45_still_ordering_alert(bundle)
    alerts.check_overdue_over45_still_ordering_alert(bundle)
    assert len(gui) == 1 and gui[0]["region"] == "Miền Nam" and gui[0]["table_rows"][0][3] == "2"


def test_hang_tra_etc_30_ngay_can_ca_ty_le_va_gia_tri(gui, monkeypatch):
    monkeypatch.setattr(insights, "rule_config", lambda config=None: copy.deepcopy(insights.DEFAULT_RULES))
    monkeypatch.setattr(alerts, "_last_complete_data_day", lambda: AS_OF)
    goi = []
    monkeypatch.setattr(insights, "fetch_etc_returns", lambda f, t: goi.append((f, t)) or (30e6, 470e6))
    alerts.check_etc_return_rate_30d_alert()
    assert gui == [] and goi == [(AS_OF - dt.timedelta(days=29), AS_OF)]   # 6% nhưng chỉ 30 triệu

    monkeypatch.setattr(insights, "fetch_etc_returns", lambda f, t: (250e6, 4_750e6))
    alerts.check_etc_return_rate_30d_alert()
    alerts.check_etc_return_rate_30d_alert()
    assert len(gui) == 1 and gui[0]["channel"] == "ETC"


_MOI_NHAN_BUNDLE = ("check_channel_month_pace_alert", "check_team_pace_alert",
                    "check_silent_regular_customers_alert", "check_new_over45_debtors_alert",
                    "check_overdue_over45_still_ordering_alert")
_KHONG_BUNDLE = ("check_etc_return_rate_30d_alert", "check_zero_sales_rep_alert",
                 "check_kpi_revenue_reconciliation_alert")
_CONFIG = {"environment": "production", "alert_feature_flags": {
    "etl_freshness_check": False, "credit_limit_check": False, "dead_stock_check": False,
    "near_expiry_check": False, "kpi_sales_force_risk_check": False}}


def _gan_main(monkeypatch, bundle_fn):
    import main
    goi = []
    monkeypatch.setattr(main, "build_insight_bundle", bundle_fn)
    for name in _MOI_NHAN_BUNDLE:
        monkeypatch.setattr(main, name, lambda b, _n=name: goi.append((_n, b)))
    for name in _KHONG_BUNDLE:
        monkeypatch.setattr(main, name, lambda _n=name: goi.append((_n, None)))
    monkeypatch.setattr(main, "check_data_sanity_ok", lambda: True)
    monkeypatch.setattr(main, "flush_critical_teams_queue", lambda: goi.append(("flush", None)))
    return main, goi


def test_main_chi_goi_bo_canh_bao_moi_voi_mot_bundle_chung(monkeypatch):
    bundle = _bundle()
    main, goi = _gan_main(monkeypatch, lambda force=False: bundle)
    for cu in ("check_revenue_drop_alert", "run_smart_business_alerts", "run_sales_kpi_insights_alert",
               "check_customer_churn_alert", "check_daily_kpi_pace_alert", "check_kpi_milestone_drop_alert",
               "check_revenue_concentration_alert", "check_company_overdue_ratio_alert",
               "check_debt_aging_migration_alert", "check_overdue_customer_new_orders_alert"):
        assert not hasattr(main, cu), cu

    main.run_all_alert_checks(_CONFIG)

    ten = [g[0] for g in goi]
    assert ten[:5] == list(_MOI_NHAN_BUNDLE) and all(g[1] is bundle for g in goi[:5])
    assert set(_KHONG_BUNDLE) <= set(ten) and ten[-1] == "flush"


def test_main_mot_canh_bao_loi_khong_chan_cac_canh_bao_con_lai(monkeypatch):
    def hong():
        raise RuntimeError("Bravo mất kết nối")
    main, goi = _gan_main(monkeypatch, lambda force=False: hong())

    main.run_all_alert_checks(_CONFIG)

    ten = [g[0] for g in goi]
    assert not set(_MOI_NHAN_BUNDLE) & set(ten)          # không có bundle thì không đoán
    assert set(_KHONG_BUNDLE) <= set(ten) and ten[-1] == "flush"

    bundle = _bundle()
    main, goi = _gan_main(monkeypatch, lambda force=False: bundle)
    monkeypatch.setattr(main, "check_team_pace_alert", lambda b: (_ for _ in ()).throw(ValueError("hỏng")))
    main.run_all_alert_checks(_CONFIG)
    assert "check_silent_regular_customers_alert" in [g[0] for g in goi]
