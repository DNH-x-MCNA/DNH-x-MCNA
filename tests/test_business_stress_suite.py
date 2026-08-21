import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "business_stress_suite.py"
SPEC = importlib.util.spec_from_file_location("business_stress_suite", MODULE_PATH)
suite = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = suite
SPEC.loader.exec_module(suite)


def test_catalog_has_90_contiguous_business_cases():
    assert suite.validate_catalog() == []
    assert len(suite.CASES) == 90
    assert [case.id for case in suite.CASES] == [f"Q{i:03d}" for i in range(1, 91)]


def test_every_case_maps_to_sql_server_ground_truth():
    for case in suite.CASES:
        checker = suite.CHECKERS[case.checker_id]
        assert checker.database in {"bravo", "bravo_sp"}
        assert checker.sql.lstrip().upper().startswith(("SELECT", "WITH"))
        assert suite._FORBIDDEN.search(checker.sql) is None
    assert all(checker.database != "local" for checker in suite.CHECKERS.values())


def test_required_high_risk_scenarios_are_covered():
    questions = "\n".join(case.question.lower() for case in suite.CASES)
    assert "doanh thu lớn, nợ quá hạn cao và sức mua giảm" in questions
    assert "tỷ lệ v25 nằm trong bậc có thưởng" in questions
    assert "đánh giá hiệu quả từng chương trình khuyến mãi" in questions
    assert "nguồn nào hiện chưa đủ độ phủ" in questions


def test_day20_distributor_checker_ranks_customers_inside_each_channel():
    checker = suite.CHECKERS["REV_DISTRIBUTOR"]
    assert "CustomerCode DistributorCode" in checker.sql
    assert "PARTITION BY Channel" in checker.sql
    assert "RankInChannel<=20" in checker.sql
    # DistributorCode gốc chỉ là mã nguồn tổng OTC/ETC, không phải thực thể để xếp top 20.
    assert "SELECT 'OTC' Channel, DistributorCode" not in checker.sql


def test_day20_kpi_quality_cases_use_semantically_separate_checkers():
    cases = {case.id: case for case in suite.CASES}
    assert cases["Q016"].checker_id == "KPI_MISSING_MANAGER"
    assert cases["Q016"].answer_columns == ("MissingManagerCount",)
    assert cases["Q017"].checker_id == "KPI_MISSING_TARGET"
    assert cases["Q024"].checker_id == "KPI_MISSING_TARGET_MANAGER"
    assert cases["Q024"].answer_columns == ("MatchingEmployees", "EmployeeCode")
    assert cases["Q062"].checker_id == "KPI_MISSING_MANAGER"
    assert cases["Q062"].answer_columns == ("MissingManagerCount", "EmployeeCode")

    manager_sql = suite.CHECKERS["KPI_MISSING_MANAGER"].sql
    intersection_sql = suite.CHECKERS["KPI_MISSING_TARGET_MANAGER"].sql
    assert "PositionCode='TDV' AND NULLIF(e.ManagerCode,'') IS NULL" in manager_sql
    assert "ISNULL(e.Target,0)<=0 AND n.PositionCode='TDV'" in intersection_sql


def test_markdown_contains_questions_and_direct_sql():
    rendered = suite.render_markdown()
    assert "Q001" in rendered and "Q090" in rendered
    assert "```sql" in rendered
    assert "DMS_DonHangCTKM" in rendered
    assert "usp_DeptAccDueDate_GetData" in rendered
    assert "Nguồn: `bravo_sp`" in rendered


def _fake_debt_snapshot():
    base = {
        "snapshot_date": "2026-08-17",
        "snapshot_at": "2026-08-17T10:00:00+07:00",
        "source_class_code": "TM",
        "sales_channel": "OTC",
        "area_code": "MN",
        "overdue_1_15": 10_000_000.0,
        "overdue_15_30": 20_000_000.0,
        "overdue_30_45": 30_000_000.0,
        "overdue_gt_45": 40_000_000.0,
        "total_overdue": 100_000_000.0,
        "source_overdue_amount": 100_000_000.0,
    }
    return SimpleNamespace(
        procedure="dbo.usp_DeptAccDueDate_GetData",
        as_of_date="2026-08-17",
        executed_at="2026-08-17T10:00:00+07:00",
        parameters={"@_DocDate2": "2026-08-17"},
        rows=[
            dict(base, customer_code="KH01", customer_name="A", balance_end=200.0),
            dict(
                base,
                customer_code="KH01",
                customer_name="A",
                source_class_code="SX",
                sales_channel="ETC",
                balance_end=300.0,
            ),
            dict(base, customer_code="KH02", customer_name="B", area_code="MB", balance_end=150.0),
        ],
    )


def test_all_debt_checkers_execute_from_sp_materialized_in_memory(monkeypatch):
    monkeypatch.setattr(suite, "_debt_snapshot", lambda as_of_date=None: _fake_debt_snapshot())
    monkeypatch.setattr(suite, "_sales_customer_period", lambda: [{
        "customer_code": "KH01",
        "recent_revenue": 200_000_000.0,
        "prior_revenue": 300_000_000.0,
        "change_pct": -33.33,
    }])

    for checker in suite.CHECKERS.values():
        if checker.database != "bravo_sp":
            continue
        result = suite._execute_debt_checker(
            checker,
            as_of_date="2026-08-17",
            scope_area="MN",
        )
        assert result["status"] == "ok", checker.id
        assert result["source"]["procedure"] == "dbo.usp_DeptAccDueDate_GetData"


def test_qlv_debt_checker_fails_closed_without_scope(monkeypatch):
    monkeypatch.setattr(suite, "_debt_snapshot", lambda as_of_date=None: _fake_debt_snapshot())

    try:
        suite._execute_debt_checker(suite.CHECKERS["DEBT_SCOPE_AGING"])
    except RuntimeError as exc:
        assert "--scope-area" in str(exc)
    else:
        raise AssertionError("Q042 phải fail-closed khi thiếu scope tài khoản")


def test_debt_source_gate_compares_values_dimensions_and_freshness(tmp_path, monkeypatch):
    import local_warehouse

    db_path = tmp_path / "warehouse.db"
    connection = sqlite3.connect(db_path)
    connection.execute("""
        CREATE TABLE fact_congno_khachhang (
            snapshot_date TEXT,snapshot_at TEXT,customer_code TEXT,sales_channel TEXT,
            area_code TEXT,balance_end REAL,overdue_1_15 REAL,overdue_15_30 REAL,
            overdue_30_45 REAL,overdue_gt_45 REAL,total_overdue REAL
        )
    """)
    for row in _fake_debt_snapshot().rows:
        connection.execute(
            "INSERT INTO fact_congno_khachhang VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                row["snapshot_date"], "2026-08-17T09:30:00+07:00", row["customer_code"],
                row["sales_channel"], row["area_code"], row["balance_end"],
                row["overdue_1_15"], row["overdue_15_30"], row["overdue_30_45"],
                row["overdue_gt_45"], row["total_overdue"],
            ),
        )
    connection.commit()
    connection.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(db_path))

    matched = suite._reconcile_debt_source_with_warehouse(_fake_debt_snapshot())
    assert matched["status"] == "ok"
    assert matched["max_abs_value_delta"] == 0

    connection = sqlite3.connect(db_path)
    connection.execute("UPDATE fact_congno_khachhang SET area_code='SAI' WHERE customer_code='KH02'")
    connection.commit()
    connection.close()
    mismatched = suite._reconcile_debt_source_with_warehouse(_fake_debt_snapshot())
    assert mismatched["status"] == "dimension_mismatch"
    assert mismatched["area_mismatch_count"] == 1
