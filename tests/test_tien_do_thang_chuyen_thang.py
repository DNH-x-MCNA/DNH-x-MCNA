# -*- coding: utf-8 -*-
"""01/10/2026 - lan chuyen thang DAU TIEN ke tu khi muc "Tien do thang / du phong doi" len chay that (14/09).

Tim thay khi doi chieu the Daily 30/09 va chay lai so thang 9/2026 tren kho:
1) Ngay 01, as_of = ngay cuoi thang truoc. Thang 30 ngay bi so voi "toi ngay 30" cua thang 31 ngay (thieu ngay chot
   thang, 16-17% doanh thu OTC) -> "du phong ca thang" cua thang DA HET cao hon so that (~39,5 ty so voi ~37,4 ty).
2) Bao cao in so nhip/du phong tu ngay 1, trong khi luat chi duoc kiem thu nguoc tu ngay 10 (OTC) / 8 (ETC):
   thang 9/2026 ngay 5 du phong OTC -55%, ngay 7 -41%, ca thang that -7%.
3) Ngay 01, so KPI Bravo sang thang moi (dat 2-3%) bi chia cho duong cong thang cu -> moi doi "duoi 60%".
Du lieu gia, khong goi Bravo, khong gui gi."""
import copy
import datetime as dt
from types import SimpleNamespace

import pytest

import main
import src.alerts as alerts
from src import insight_report, insights, notifier
from src.alerts import format_vietnamese_money


def _thang(y, m, theo_ngay):
    return {dt.date(y, m, d): v for d, v in theo_ngay.items()}


def _nen_don_ngay_cuoi():
    """3 thang nen ban 100/thang, mot nua don vao NGAY CUOI thang (30/06, 31/07, 31/08)."""
    daily = {}
    for m, cuoi in ((6, 30), (7, 31), (8, 31)):
        daily.update(_thang(2026, m, {1: 50, cuoi: 50}))
    return daily


# ---- 1) as_of la ngay cuoi thang -----------------------------------------------------------------

def test_ngay_cuoi_thang_30_ngay_so_voi_tron_thang_nen():
    daily = _nen_don_ngay_cuoi()
    daily.update(_thang(2026, 9, {1: 40, 30: 40}))

    pace = insights.month_pace(daily, dt.date(2026, 9, 30), lookback=3)

    assert pace["month_complete"] is True
    assert pace["expected_share_pct"] == pytest.approx(100)        # truoc khi sua: 66,7 (thang 7, 8 thieu ngay 31)
    assert pace["projected_full_month"] == pytest.approx(80)       # thang da het: du phong = so that, khong phai 120
    assert pace["gap_pct"] == pytest.approx(20) and pace["projected_vs_baseline_pct"] == pytest.approx(-20)
    assert pace["prev_month_same_days"] == pytest.approx(100)      # so voi TRON thang 8


def test_ngay_29_van_so_theo_duong_cong_nhu_cu():
    daily = _nen_don_ngay_cuoi()
    daily.update(_thang(2026, 9, {1: 40}))

    pace = insights.month_pace(daily, dt.date(2026, 9, 29), lookback=3)

    assert pace["month_complete"] is False
    assert pace["expected_share_pct"] == pytest.approx(50)
    assert pace["projected_full_month"] == pytest.approx(80)


# ---- 2) dau thang: chi in luy ke -----------------------------------------------------------------

@pytest.fixture
def nhip(monkeypatch):
    monkeypatch.setattr(insights, "_PACE_CACHE", {})
    daily = _nen_don_ngay_cuoi()
    daily.update(_thang(2026, 10, {1: 3, 8: 3}))
    monkeypatch.setattr(insights, "fetch_daily_revenue",
                        lambda f, t, region=None: {"OTC": dict(daily), "ETC": dict(daily)})
    return daily


def test_gan_co_chua_toi_ngay_da_kiem_thu(nhip):
    ngay_5 = insights.channel_pace_for_scope(dt.date(2026, 10, 5), rules=insights.DEFAULT_RULES)
    assert (ngay_5["OTC"]["evaluated"], ngay_5["OTC"]["min_day"]) == (False, 10)
    assert (ngay_5["ETC"]["evaluated"], ngay_5["ETC"]["min_day"]) == (False, 8)

    ngay_8 = insights.channel_pace_for_scope(dt.date(2026, 10, 8), rules=insights.DEFAULT_RULES)
    assert ngay_8["OTC"]["evaluated"] is False and ngay_8["ETC"]["evaluated"] is True

    ngay_10 = insights.channel_pace_for_scope(dt.date(2026, 10, 10), rules=insights.DEFAULT_RULES)
    assert ngay_10["OTC"]["evaluated"] is True


def _view(month_pace, **over):
    view = {"as_of_display": "05/10/2026", "lookback": 3, "errors": {}, "month_pace": month_pace,
            "team_pace": {"applicable": True, "evaluated": False, "min_day": 15},
            "silent_customers": {"evaluated": False, "min_day": 20, "rows": []},
            "new_over45": {"available": True, "rows": []}, "overdue_ordering": {"rows": []}}
    view.update(over)
    view["action_count"] = insight_report.action_count(view)
    return view


_DAU_THANG = {"mtd": 1_510_000_000, "gap_pct": 55.0, "projected_full_month": 18_340_000_000,
              "projected_vs_baseline_pct": -55.0, "day": 5, "min_day": 10, "evaluated": False}
_HET_THANG = {"mtd": 37_370_000_000, "gap_pct": 7.5, "projected_full_month": 37_370_000_000,
              "projected_vs_baseline_pct": -7.5, "day": 30, "min_day": 10, "evaluated": True, "month_complete": True}


def test_the_teams_dau_thang_chi_in_luy_ke():
    (nhan, gia_tri), = insight_report.pace_lines(_view({"OTC": _DAU_THANG}), format_vietnamese_money)

    assert nhan == "Lũy kế tháng OTC (đến 05/10/2026)"
    assert gia_tri.startswith("1,51 tỷ") and "đánh giá từ ngày 10 hằng tháng" in gia_tri
    for sai in ("chậm", "nhanh", "18,34", "-55", "so TB"):
        assert sai not in gia_tri, sai


def test_the_teams_thang_da_het_khong_con_du_phong():
    (_, gia_tri), = insight_report.pace_lines(_view({"OTC": _HET_THANG}, as_of_display="30/09/2026"),
                                              format_vietnamese_money)

    assert gia_tri.startswith("37,37 tỷ") and gia_tri.endswith("đã hết tháng; thấp hơn TB 3 tháng 8%")
    assert "dự phóng" not in gia_tri and "nhịp" not in gia_tri


def test_the_teams_view_cu_khong_co_co_van_in_nhu_truoc():
    cu = {"mtd": 21_500_000_000, "gap_pct": 18.4, "projected_full_month": 33_000_000_000,
          "projected_vs_baseline_pct": -18.4}
    (_, gia_tri), = insight_report.pace_lines(_view({"OTC": cu}), format_vietnamese_money)
    assert "chậm 18% so nhịp thường lệ; dự phóng cả tháng 33,00 tỷ" in gia_tri


def _metrics(view):
    return {"date": "05/10/2026", "period_range": "Tuần 05/10/2026 - 05/10/2026", "updated_at": "17:45 05/10/2026",
            "region": None, "channel": None,
            "revenue": {"otc": 7e9, "etc": 5e9, "total": 12e9, "invoice_count": 300, "otc_invoice_count": 250,
                        "etc_invoice_count": 50, "prev_total": 11e9, "change_pct": 9.1,
                        "prev_period_label": "28/09-29/09/2026"},
            "receivables": None, "inventory": {"dead_stock_available": False, "near_stockout_available": False},
            "highlights": [], "warning_alerts": [], "has_critical": False, "insights": view}


def test_email_dau_thang_va_het_thang(monkeypatch):
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_feature_flags": {}})

    dau = notifier.build_digest_email(_metrics(_view({"OTC": _DAU_THANG})), period_label="Weekly")
    assert "Đánh giá từ ngày 10 hằng tháng" in dau
    assert "Chậm 55%" not in dau and "-55% so TB" not in dau

    het = notifier.build_digest_email(_metrics(_view({"OTC": _HET_THANG}, as_of_display="30/09/2026")),
                                      period_label="Weekly")
    assert "Đã hết tháng" in het and "-8% so TB 3 tháng" in het and "Chậm 8%" not in het


def test_bang_the_daily_dau_thang(monkeypatch):
    _, rows = main._digest_table(_metrics(_view({"OTC": _DAU_THANG})))
    dong = next(r for r in rows if r[0].startswith("Lũy kế tháng OTC"))
    assert "đánh giá từ ngày 10 hằng tháng" in dong[1]


def test_the_daily_ngay_01_ghi_ngay_du_lieu_o_muc_viec_can_xu_ly(monkeypatch):
    """Ngay 01/10 cac dong "... thang nay" la cua thang 9 (du lieu den 30/09) - tieu de phai noi ro."""
    view = _view({"OTC": _HET_THANG}, as_of_display="30/09/2026",
                 silent_customers={"evaluated": True, "min_day": 20, "rows": [
                     {"customer_code": "K1", "customer_name": "Khách A", "sales_channel": "OTC",
                      "baseline_monthly": 100_000_000}]})
    monkeypatch.delenv("TEAMS_DELIVERY_MODE", raising=False)
    monkeypatch.setattr(main, "load_config", lambda: {
        "report_recipients": [{"audience": "C-Level", "region": None, "channel": None,
                               "teams_webhook": "https://example.test"}],
        "report_feature_flags": {}})
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: {**_metrics(view), "date": "01/10/2026"})
    captured = {}
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: captured.update(kw) or True)

    assert main.send_daily_digest() is True

    muc = next(s for s in captured["sections"] if s["id"] == "section_action_items")
    assert muc["title"] == "📌 VIỆC CẦN XỬ LÝ (1) — dữ liệu đến 30/09/2026"
    dong = next(r for r in captured["table_rows"] if r[0] == "Lũy kế tháng OTC (đến 30/09/2026)")
    assert "đã hết tháng" in dong[1]


# ---- 3) so KPI Bravo lech thang voi as_of ----------------------------------------------------------

def _kpi(code, pos, manager, target, amount):
    return SimpleNamespace(employee_code=code, employee_name=code, area_code="MB", position_code=pos,
                           manager_code=manager, month_sale_target=target, month_sale_amount=amount,
                           month_sale_percent=None)


@pytest.fixture
def bravo(monkeypatch):
    goi = []
    tdv = [_kpi(f"T{i}", "TDV", "MBKV2", 1e9, 0.03e9) for i in range(3)]     # ngay 01/10: moi dat 3%

    def snapshot(position_codes=("TDV",), include_duplicates=False):
        goi.append(position_codes)
        return tdv if position_codes == ("TDV",) else [_kpi("MBKV2", "QLV", None, 3e9, 0.09e9)]

    monkeypatch.setattr(alerts, "get_bravo_kpi_tdv_snapshot", snapshot)
    monkeypatch.setattr(alerts, "get_bravo_manager_codes", lambda: {"MBKV2"})
    return goi


def test_kpi_da_sang_thang_moi_thi_khong_du_phong_doi_theo_duong_cong_thang_cu(bravo, monkeypatch):
    monkeypatch.setattr(alerts, "get_bravo_kpi_snapshot_date", lambda: dt.date(2026, 10, 1))

    part = insights._team_pace_part(dt.date(2026, 9, 30), {"expected_share_pct": 100}, insights.DEFAULT_RULES)

    assert part["evaluated"] is False and part["teams"] == [] and part["at_risk"] == []   # truoc khi sua: 1 doi 3%
    assert "đã sang tháng 10/2026" in part["skipped_reason"] and bravo == []
    view = _view({}, team_pace={**part, "applicable": True})
    assert "• Đội QLV: đánh giá nguy cơ hụt chỉ tiêu từ ngày 15 hằng tháng." in \
        insight_report.action_lines(view, format_vietnamese_money)
    assert insight_report.team_progress_lines({"team_pace": part, "errors": {}}, format_vietnamese_money) == [
        "• Dự phóng cuối tháng của đội: Số KPI trên Bravo đã sang tháng 10/2026; dự phóng đội tính lại từ ngày 15 "
        "của tháng mới."]


def test_kpi_cung_thang_thi_du_phong_nhu_cu(bravo, monkeypatch):
    monkeypatch.setattr(alerts, "get_bravo_kpi_snapshot_date", lambda: dt.date(2026, 9, 30))
    part = insights._team_pace_part(dt.date(2026, 9, 30), {"expected_share_pct": 100}, insights.DEFAULT_RULES)
    assert part["evaluated"] is True and [t["team_code"] for t in part["at_risk"]] == ["MBKV2"]
    assert part["at_risk"][0]["projection_pct"] == pytest.approx(part["at_risk"][0]["achievement_pct"])


def test_kpi_chua_co_thang_cua_bao_cao_thi_bao_chua_danh_gia_duoc(bravo, monkeypatch):
    monkeypatch.setattr(alerts, "get_bravo_kpi_snapshot_date", lambda: dt.date(2026, 9, 30))
    part = insights._team_pace_part(dt.date(2026, 10, 20), {"expected_share_pct": 60}, insights.DEFAULT_RULES)
    assert part["evaluated"] is True and part["teams"] == [] and "chưa có tháng 10/2026" in part["skipped_reason"]
    view = insight_report.mark_errors(_view({}, team_pace={**part, "applicable": True}))
    assert view["team_pace"]["error"] is True


def test_khong_doc_duoc_ngay_snapshot_thi_giu_cach_cu(bravo, monkeypatch):
    def loi():
        raise RuntimeError("Bravo")
    monkeypatch.setattr(alerts, "get_bravo_kpi_snapshot_date", loi)
    part = insights._team_pace_part(dt.date(2026, 9, 20), {"expected_share_pct": 50}, insights.DEFAULT_RULES)
    assert [t["team_code"] for t in part["teams"]] == ["MBKV2"]


# ---- canh bao tuc thoi: thang da het thi khong bao "nguy co hut chi tieu" --------------------------

@pytest.fixture
def gui(monkeypatch, tmp_path):
    monkeypatch.setattr(alerts, "STATE_DB_DIR", str(tmp_path))
    monkeypatch.setattr(alerts, "STATE_DB_PATH", str(tmp_path / "alerts_state.db"))
    sent = []
    monkeypatch.setattr(alerts, "send_alert_to_all_channels", lambda **kw: sent.append(kw) or True)
    return sent


def _bundle(as_of):
    doi = {"team_code": "MBKV2", "team_name": "Đội mẫu", "members": 4, "achievement_pct": 48.0,
           "projection_pct": 48.0, "region_key": "bac", "sales_channel": "OTC"}
    return {"as_of": as_of, "rules": copy.deepcopy(insights.DEFAULT_RULES), "errors": {},
            "team_pace": {"evaluated": True, "min_day": 15, "threshold_pct": 60.0, "teams": [doi], "at_risk": [doi]}}


def test_canh_bao_doi_khong_gui_khi_thang_da_het(gui):
    alerts.check_team_pace_alert(_bundle(dt.date(2026, 9, 30)))
    assert gui == []

    alerts.check_team_pace_alert(_bundle(dt.date(2026, 9, 29)))
    assert [s["alert_name"] for s in gui] == ["ĐỘI QLV CÓ NGUY CƠ HỤT CHỈ TIÊU THÁNG"]
