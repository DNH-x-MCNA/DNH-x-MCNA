import sqlite3
from types import SimpleNamespace
import os
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)
import debt_source
from debt_source import fetch_debt_snapshot
import sync_warehouse


class FakeCursor:
    def __init__(self):
        self.timeout = None
        self.executed = None
        self.description = [
            (name,) for name in (
                "CustomerCode", "CustomerName", "ClassCode", "AreaCode", "CloseBal",
                "CloseBal5", "CloseBal6", "CloseBal7", "CloseBal8", "OverDueAmount",
            )
        ]

    def execute(self, statement, *parameters):
        self.executed = (statement, parameters)

    def fetchall(self):
        return [(
            "KH01", "Khach A", "TM", "MB1", 1_000, 10, 20, 30, 40, 100,
        )]

    def nextset(self):
        return False


class FakeRawConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def test_fetch_debt_snapshot_executes_only_whitelisted_sp_and_rolls_back():
    raw = FakeRawConnection()
    engine = SimpleNamespace(raw_connection=lambda: raw)

    snapshot = fetch_debt_snapshot("2026-08-17", engine=engine)

    statement, parameters = raw.cursor_instance.executed
    assert statement.startswith("EXEC dbo.usp_DeptAccDueDate_GetData")
    assert parameters == ("2026-01-01", "2026-08-17", 7, 15, 1, 1)
    assert raw.cursor_instance.timeout == 60
    assert raw.rolled_back is True
    assert raw.closed is True
    assert snapshot.rows[0]["sales_channel"] == "OTC"
    assert snapshot.rows[0]["area_code"] == "MB"
    assert snapshot.rows[0]["total_overdue"] == 100.0
    assert snapshot.rows[0]["source_overdue_amount"] == 100.0


def test_sync_fact_congno_writes_snapshot_from_shared_source(tmp_path, monkeypatch):
    db_path = tmp_path / "warehouse.db"
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE fact_congno_khachhang (
            snapshot_date TEXT,snapshot_at TEXT,customer_code TEXT,customer_name TEXT,
            sales_channel TEXT,area_code TEXT,balance_end REAL,overdue_1_15 REAL,
            overdue_15_30 REAL,overdue_30_45 REAL,overdue_gt_45 REAL,total_overdue REAL
        )
    """)
    # 21/08/2026: them bang lich su (xem local_warehouse.py::SCHEMA) - phan anh dung thuc te
    # production (init_schema() luon tao bang nay) va verify sync_fact_congno() ghi dung vao day.
    connection.execute("""
        CREATE TABLE fact_congno_khachhang_history (
            snapshot_date TEXT,snapshot_at TEXT,customer_code TEXT,customer_name TEXT,
            sales_channel TEXT,area_code TEXT,balance_end REAL,overdue_1_15 REAL,
            overdue_15_30 REAL,overdue_30_45 REAL,overdue_gt_45 REAL,total_overdue REAL
        )
    """)
    connection.commit()
    connection.close()
    snapshot = SimpleNamespace(
        as_of_date="2026-08-17",
        executed_at="2026-08-17T10:00:00+07:00",
        rows=[{
            "customer_code": "KH01",
            "customer_name": "Khach A",
            "sales_channel": "OTC",
            "area_code": "MN",
            "balance_end": 1_000.0,
            "overdue_1_15": 10.0,
            "overdue_15_30": 20.0,
            "overdue_30_45": 30.0,
            "overdue_gt_45": 40.0,
            "total_overdue": 100.0,
        }],
    )
    sync_meta_calls = []
    monkeypatch.setattr(debt_source, "fetch_debt_snapshot", lambda: snapshot)
    monkeypatch.setattr(sync_warehouse, "get_conn", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(
        sync_warehouse,
        "set_sync_meta",
        lambda table, earliest, latest: sync_meta_calls.append((table, earliest, latest)),
    )

    sync_warehouse.sync_fact_congno()

    connection = sqlite3.connect(db_path)
    row = connection.execute(
        "SELECT snapshot_date,snapshot_at,customer_code,total_overdue "
        "FROM fact_congno_khachhang"
    ).fetchone()
    hist_row = connection.execute(
        "SELECT snapshot_date,customer_code,total_overdue FROM fact_congno_khachhang_history"
    ).fetchone()
    connection.close()
    assert row == ("2026-08-17", "2026-08-17T10:00:00+07:00", "KH01", 100.0)
    assert sync_meta_calls == [("fact_congno_khachhang", "2026-08-17", "2026-08-17")]
    # 21/08/2026: snapshot cung phai duoc ghi vao bang lich su (1 lan/ngay) de so sanh cong no
    # giua cac ky - xem sync_fact_congno() trong sync_warehouse.py.
    assert hist_row == ("2026-08-17", "KH01", 100.0)


def test_sync_fact_congno_history_khong_trung_lap_khi_sync_nhieu_lan_1_ngay(tmp_path, monkeypatch):
    """21/08/2026: sync_scheduler.ps1 chay nhieu lan/ngay - bang lich su CHI duoc ghi 1 lan/ngay,
    KHONG duoc phinh to moi lan sync (xem ghi chu trong sync_fact_congno())."""
    db_path = tmp_path / "warehouse.db"
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE fact_congno_khachhang (
            snapshot_date TEXT,snapshot_at TEXT,customer_code TEXT,customer_name TEXT,
            sales_channel TEXT,area_code TEXT,balance_end REAL,overdue_1_15 REAL,
            overdue_15_30 REAL,overdue_30_45 REAL,overdue_gt_45 REAL,total_overdue REAL
        )
    """)
    connection.execute("""
        CREATE TABLE fact_congno_khachhang_history (
            snapshot_date TEXT,snapshot_at TEXT,customer_code TEXT,customer_name TEXT,
            sales_channel TEXT,area_code TEXT,balance_end REAL,overdue_1_15 REAL,
            overdue_15_30 REAL,overdue_30_45 REAL,overdue_gt_45 REAL,total_overdue REAL
        )
    """)
    connection.commit()
    connection.close()
    snapshot = SimpleNamespace(
        as_of_date="2026-08-17",
        executed_at="2026-08-17T10:00:00+07:00",
        rows=[{
            "customer_code": "KH01", "customer_name": "Khach A", "sales_channel": "OTC",
            "area_code": "MN", "balance_end": 1_000.0, "overdue_1_15": 10.0,
            "overdue_15_30": 20.0, "overdue_30_45": 30.0, "overdue_gt_45": 40.0,
            "total_overdue": 100.0,
        }],
    )
    monkeypatch.setattr(debt_source, "fetch_debt_snapshot", lambda: snapshot)
    monkeypatch.setattr(sync_warehouse, "get_conn", lambda: sqlite3.connect(db_path))
    monkeypatch.setattr(sync_warehouse, "set_sync_meta", lambda *a: None)

    sync_warehouse.sync_fact_congno()
    sync_warehouse.sync_fact_congno()  # sync lan 2 CUNG NGAY (mo phong scheduler chay nhieu lan/ngay)

    connection = sqlite3.connect(db_path)
    count = connection.execute(
        "SELECT COUNT(*) FROM fact_congno_khachhang_history WHERE snapshot_date='2026-08-17'"
    ).fetchone()[0]
    connection.close()
    assert count == 1
