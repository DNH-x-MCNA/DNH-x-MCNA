"""25/09/2026: bo han Supabase. Canh bao/bao cao doc thang Bravo tu 20/07; ban sao Supabase da ngung duoc cap nhat
(5 task DNH_Bravo_Sync tren may 24 deu LastTaskResult=255). Khoa ba dieu: chatbot khong con tool doc Supabase (bang
inventory dung tu 20/07 -> tra ton kho so thang 7), canh bao ton kho khong phu thuoc script dong bo Supabase (script do
sys.exit(1) luc import neu thieu CLOUD_DB_URL), va canh bao no chuyen nhom tuoi khong du phong sang Supabase."""
import sys
import types
from pathlib import Path

import pandas as pd

GOC = Path(__file__).resolve().parents[1]
for duong in (str(GOC), str(GOC / "backend")):
    if duong not in sys.path:
        sys.path.insert(0, duong)

import nl2sql  # noqa: E402
import src.alerts as alerts  # noqa: E402
import src.bravo_inventory as bravo_inventory  # noqa: E402
import src.database as database  # noqa: E402


def test_chatbot_khong_con_tool_doc_supabase():
    ten_tool = {t["name"] for t in nl2sql.TEMPLATE_TOOLS}
    assert "query_inventory_receivables" not in ten_tool
    assert "supabase" not in set(nl2sql.RAW_SQL_TOOLS.values())
    assert "query_inventory_receivables" not in nl2sql._static_system_prompt()


def test_khong_con_engine_supabase_va_run_with_failover():
    assert not hasattr(database, "_get_cloud_engine") and not hasattr(database, "run_with_failover")
    assert not (GOC / "scripts" / "sync_from_bravo_to_supabase.py").exists()


def test_canh_bao_ton_kho_doc_bravo_qua_module_moi_khi_khong_co_cloud_db_url(monkeypatch):
    monkeypatch.delenv("CLOUD_DB_URL", raising=False)
    monkeypatch.setattr(database, "_get_bravo_engine", lambda: object())
    dong = []
    monkeypatch.setattr(bravo_inventory, "get_sql_server_connection",
                        lambda: types.SimpleNamespace(close=lambda: dong.append("dong")))
    monkeypatch.setattr(bravo_inventory, "build_inventory_dataframe", lambda conn: pd.DataFrame([
        {"item_code": "SP1", "item_name": "Siro", "unit": "Lo", "opening_qty": 1, "inward_qty": 0, "outward_qty": 0,
         "closing_qty": 1, "closing_value": 0, "months_to_sell": None, "warehouse": "B02", "channel": "OTC"}]))
    rows = alerts.get_bravo_inventory_snapshot(force_refresh=True)
    assert [r.item_code for r in rows] == ["SP1"] and dong == ["dong"]


def test_no_chuyen_nhom_tuoi_bravo_loi_thi_bo_qua_khong_du_phong_supabase(monkeypatch):
    def loi():
        raise RuntimeError("Bravo khong truy cap duoc")
    monkeypatch.setattr(alerts, "_bravo_overdue_gt45_by_customer", loi)
    gui = []
    monkeypatch.setattr(alerts, "send_alert_to_all_channels", lambda *a, **k: gui.append(a))
    assert alerts.check_debt_aging_migration_alert() is None
    assert gui == [], "Khong duoc gui canh bao khi khong co so lieu Bravo."
