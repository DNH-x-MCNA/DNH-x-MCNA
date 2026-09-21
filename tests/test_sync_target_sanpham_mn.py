import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import sync_warehouse


def test_sync_target_sanpham_mn_dung_ten_cot_bravo_that(tmp_path, monkeypatch):
    """Full sync khong duoc goi cac alias khong ton tai tren FACT_TargetSanPhamMN2025."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE fact_targetsanphammn2025 ("
        "item_code TEXT, area_code INTEGER, month INTEGER, quantity REAL, value REAL)"
    )
    conn.commit()
    conn.close()

    captured = {}

    def fake_bravo_query(sql, **_params):
        captured["sql"] = sql
        return ["MaSp", "MaVungMN", "Month", "SL", "GT"], [
            ("80320000001", 2, 3, 125.0, 4_500_000.0),
        ]

    monkeypatch.setattr(sync_warehouse, "bravo_query", fake_bravo_query)
    monkeypatch.setattr(sync_warehouse, "get_conn", lambda: sqlite3.connect(db_path))

    spec = next(
        item for item in sync_warehouse.SMALL_TABLES
        if item[0] == "FACT_TargetSanPhamMN2025"
    )
    sync_warehouse.sync_small_table(*spec)

    assert "SELECT MaSp, MaVungMN, Month, SL, GT" in captured["sql"]
    assert "ItemCode" not in captured["sql"]
    assert "AreaCode" not in captured["sql"]

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT item_code, area_code, month, quantity, value "
            "FROM fact_targetsanphammn2025"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("80320000001", 2, 3, 125.0, 4_500_000.0)
