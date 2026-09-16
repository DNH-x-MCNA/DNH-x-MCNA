from __future__ import annotations

import datetime as dt
import sqlite3

import src.alerts as alerts


def _warehouse(path, otc_at, etc_at):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE sync_meta (table_name TEXT, last_synced_at TEXT, latest_synced_date TEXT)")
    conn.executemany(
        "INSERT INTO sync_meta VALUES (?, ?, ?)",
        [("vhoadon_otc", otc_at, "2026-09-15"), ("vhoadon_etc", etc_at, "2026-09-15")],
    )
    conn.commit()
    conn.close()


def test_freshness_khong_bao_gia_sau_cuoi_tuan():
    assert alerts._business_days_since(dt.date(2026, 9, 11), dt.date(2026, 9, 14)) == 1
    assert alerts._business_days_since(dt.date(2026, 9, 11), dt.date(2026, 9, 15)) == 2


def test_warehouse_sync_status_phan_biet_tuoi_cua_tung_bang(tmp_path):
    path = tmp_path / "warehouse.db"
    _warehouse(path, "2026-09-16T08:00:00", "2026-09-16T09:30:00")

    status = alerts._warehouse_sync_status(
        str(path), stale_minutes=90, now=dt.datetime(2026, 9, 16, 10, 0, 0),
    )

    assert status["available"] is True
    assert [row["table"] for row in status["stale"]] == ["vhoadon_otc"]
    assert status["stale"][0]["age_minutes"] == 120


def test_alert_freshness_bao_kho_local_treo_khong_bao_bravo_cu(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse.db"
    _warehouse(warehouse, "2020-01-01T00:00:00", "2020-01-01T00:00:00")
    state = tmp_path / "alerts_state.db"
    monkeypatch.setattr(alerts, "WAREHOUSE_DB_PATH", str(warehouse))
    monkeypatch.setattr(alerts, "STATE_DB_DIR", str(tmp_path))
    monkeypatch.setattr(alerts, "STATE_DB_PATH", str(state))
    monkeypatch.setattr(alerts, "_last_complete_data_day", lambda: dt.datetime.now().date())
    monkeypatch.setattr(
        alerts, "_biz_threshold",
        lambda name, default: 90 if name == "warehouse_stale_minutes" else 2,
    )
    sent = []
    monkeypatch.setattr(alerts, "send_alert_to_all_channels", lambda **kw: sent.append(kw) or True)

    alerts.check_etl_freshness_alert()

    assert [item["alert_name"] for item in sent] == [
        "CẢNH BÁO HỆ THỐNG: KHO BÁO CÁO NGỪNG ĐỒNG BỘ"
    ]
