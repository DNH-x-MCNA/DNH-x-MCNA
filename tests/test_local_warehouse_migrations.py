import sqlite3

from backend import local_warehouse


def test_init_schema_nang_cap_dim_targetvungmien_tu_ten_cot_bravo(tmp_path, monkeypatch):
    """Kho cu dung AreaCode/ChannelCode/DocDate khong duoc lam service chet khi tao index moi."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE dim_targetvungmien ("
        "Id INTEGER, AreaCode TEXT, ChannelCode TEXT, Amount REAL, DocDate TEXT)"
    )
    conn.execute(
        "INSERT INTO dim_targetvungmien (AreaCode,ChannelCode,Amount,DocDate) VALUES (?,?,?,?)",
        ("MB", "OTC", 123.0, "2026-08-31"),
    )
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    local_warehouse.init_schema()

    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(dim_targetvungmien)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(dim_targetvungmien)")}
    finally:
        conn.close()

    assert {"area_code", "channel_code", "doc_date"} <= cols
    assert "idx_tvm_docdate" in indexes


def test_init_schema_them_don_vi_hoa_don_va_bang_quy_doi_sku(tmp_path, monkeypatch):
    """Kho cu van mo duoc khi them Unit va cac danh muc phuc vu doi chieu SKU/M40."""
    db_path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE vhoadon_otc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, city_id INTEGER,
            employee_code TEXT, created_at TEXT, channel_code TEXT);
        CREATE TABLE vhoadon_etc (doc_date TEXT, customer_code TEXT, item_code TEXT,
            amount9 REAL, quantity REAL, unit_price REAL, stt TEXT, employee_code TEXT,
            created_at TEXT);
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    local_warehouse.init_schema()

    conn = sqlite3.connect(db_path)
    try:
        otc_columns = {row[1] for row in conn.execute("PRAGMA table_info(vhoadon_otc)")}
        etc_columns = {row[1] for row in conn.execute("PRAGMA table_info(vhoadon_etc)")}
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()

    assert "unit" in otc_columns
    assert "unit" in etc_columns
    assert {"brvsx_sanpham", "brvsx_sanphamdvt", "dim_targetsanphametc",
            "fact_targetsanphammn2025"} <= tables
