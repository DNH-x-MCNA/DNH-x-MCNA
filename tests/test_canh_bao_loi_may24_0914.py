# -*- coding: utf-8 -*-
"""Loi thay tren dich vu canh bao may 24 ngay 14/09/2026 - khong goi Bravo, khong gui gi.

  - 13:33:51 "cannot rollback - no transaction is active": DB trang thai bi khoa, should_send_alert
    rollback mot giao dich chua mo, che loi goc va dung ca vong quet.
  - Ban chup no >45 ngay dung tu 10/08: dong cong no khong ma khach lam INSERT loi, ket noi giu khoa.
  - So voi ban chup 10/08 se bao don vai chuc khach "moi" trong mot lan.
"""
import copy
import datetime as dt
import sqlite3
from collections import namedtuple

import pytest

import src.alerts as alerts
from src import insights


@pytest.fixture
def state_db(monkeypatch, tmp_path):
    path = tmp_path / "alerts_state.db"
    monkeypatch.setattr(alerts, "STATE_DB_DIR", str(tmp_path))
    monkeypatch.setattr(alerts, "STATE_DB_PATH", str(path))
    return path


def test_db_bi_khoa_thi_bao_dung_loi_goc_khong_phai_loi_rollback(state_db, monkeypatch):
    alerts.init_state_db()
    that_connect = sqlite3.connect
    monkeypatch.setattr(alerts.sqlite3, "connect",
                        lambda path, timeout=5.0, **kw: that_connect(path, timeout=0.05, **kw))
    giu_khoa = that_connect(str(state_db), isolation_level=None)
    giu_khoa.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sqlite3.OperationalError) as loi:
            alerts.should_send_alert("channel_pace:OTC:2026-09", cooldown_hours=24, current_value="30")
        assert "locked" in str(loi.value)
        assert "cannot rollback" not in str(loi.value)
    finally:
        giu_khoa.execute("ROLLBACK")
        giu_khoa.close()


def test_ban_chup_cong_no_bo_dong_khong_ma_khach_va_khong_giu_khoa(state_db):
    alerts._save_debt_aging_snapshot([("KH01", "Khách 1", 80e6), (None, "Dòng lỗi từ SP", 1.0), ("", "Rỗng", 2.0)])

    kiem = sqlite3.connect(str(state_db), timeout=0.05, isolation_level=None)
    kiem.execute("BEGIN IMMEDIATE")      # con ai giu khoa ghi thi dong nay nem "database is locked"
    kiem.execute("ROLLBACK")
    kiem.close()
    today = dt.datetime.now().strftime("%Y-%m-%d")
    assert alerts._get_debt_aging_snapshot(today) == {"KH01": ("Khách 1", 80e6)}


Row = namedtuple("Row", "customer_code customer_name sales_channel area_code overdue_gt_45")


def _snapshot():
    return [Row("KH_MOI", "Khách mới nợ", "ETC", "MB", 90e6), Row(None, "Dòng lỗi", "ETC", "MB", 5e6)]


def test_ban_chup_qua_cu_thi_chua_so_de_khong_bao_don(state_db, monkeypatch):
    rules = copy.deepcopy(insights.DEFAULT_RULES)
    monkeypatch.setattr(alerts, "_find_debt_snapshot_on_or_before", lambda before: "2026-08-10")
    monkeypatch.setattr(alerts, "_get_debt_aging_snapshot", lambda d: {})

    part = insights._new_over45_part(_snapshot(), rules, today=dt.date(2026, 9, 14))

    assert part["available"] is False and part["stale_snapshot"] == "2026-08-10" and part["rows"] == []


def test_ban_chup_trong_han_van_so_binh_thuong(state_db, monkeypatch):
    rules = copy.deepcopy(insights.DEFAULT_RULES)
    monkeypatch.setattr(alerts, "_find_debt_snapshot_on_or_before", lambda before: "2026-09-07")
    monkeypatch.setattr(alerts, "_get_debt_aging_snapshot", lambda d: {"KH_CU": ("Cũ", 10.0)})

    part = insights._new_over45_part(_snapshot(), rules, today=dt.date(2026, 9, 14))

    assert part["available"] is True and part["stale_snapshot"] is None
    assert [r["customer_code"] for r in part["rows"]] == ["KH_MOI"]


def test_email_noi_ro_ban_chup_qua_cu(monkeypatch):
    from src import notifier
    from test_bao_cao_insight import _metrics, _view
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_feature_flags": {}})
    view = _view(new_over45={"available": False, "stale_snapshot": "2026-08-10", "rows": []})
    html = notifier.build_digest_email(_metrics(view), period_label="Weekly")
    assert "Bản chụp công nợ gần nhất (ngày 2026-08-10) đã quá cũ" in html


def test_co_tat_tung_canh_bao_moi(monkeypatch):
    from test_canh_bao_kiem_thu_nguoc import _CONFIG, _bundle, _gan_main
    main, goi = _gan_main(monkeypatch, lambda force=False: _bundle())
    config = copy.deepcopy(_CONFIG)
    config["alert_feature_flags"].update(insight_team_pace=False, insight_etc_returns=False)

    main.run_all_alert_checks(config)

    ten = [g[0] for g in goi]
    assert "check_team_pace_alert" not in ten and "check_etc_return_rate_30d_alert" not in ten
    assert "check_channel_month_pace_alert" in ten and ten[-1] == "flush"
