import copy
import json
import sqlite3

from backend.sql_catalog import (
    CatalogPolicy,
    compare_source_to_warehouse,
    diff_catalogs,
    extract_sql_server_catalog,
    extract_warehouse_catalog,
    structural_hash,
    write_catalog_snapshot,
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        sql = str(statement)
        if "SERVERPROPERTY('ProductVersion')" in sql:
            return FakeResult([{"database_name": "NH_Report_TM", "product_version": "16.0", "edition": "Dev"}])
        if "FROM sys.objects o" in sql and "sys.partitions" in sql:
            return FakeResult([
                {
                    "object_id": 1, "schema_name": "dbo", "object_name": "AllowedTable",
                    "object_type": "U", "type_desc": "USER_TABLE", "create_date": "2026-01-01",
                    "modify_date": "2026-08-01", "row_count_estimate": 10, "description": "Allowed",
                    "has_read_permission": 1,
                },
                {
                    "object_id": 2, "schema_name": "dbo", "object_name": "DeniedTable",
                    "object_type": "U", "type_desc": "USER_TABLE", "create_date": "2026-01-01",
                    "modify_date": "2026-08-01", "row_count_estimate": 20, "description": None,
                    "has_read_permission": 1,
                },
            ])
        if "FROM sys.columns c" in sql:
            return FakeResult([
                {
                    "object_id": 1, "column_id": 1, "column_name": "CustomerName",
                    "data_type": "nvarchar", "max_length": 200, "precision": 0, "scale": 0,
                    "is_nullable": 0, "is_identity": 0, "is_computed": 0, "collation_name": None,
                    "default_definition": None, "computed_definition": None, "description": "Tên khách hàng",
                },
                {
                    "object_id": 2, "column_id": 1, "column_name": "Secret",
                    "data_type": "varchar", "max_length": 50, "precision": 0, "scale": 0,
                    "is_nullable": 1, "is_identity": 0, "is_computed": 0, "collation_name": None,
                    "default_definition": None, "computed_definition": None, "description": None,
                },
            ])
        if "FROM sys.indexes i" in sql:
            return FakeResult([{
                "object_id": 1, "index_id": 1, "index_name": "PK_Allowed", "type_desc": "CLUSTERED",
                "is_unique": 1, "is_primary_key": 1, "has_filter": 0, "filter_definition": None,
                "key_ordinal": 1, "index_column_id": 1, "is_included_column": 0,
                "is_descending_key": 0, "column_name": "CustomerName",
            }])
        if "FROM sys.foreign_keys fk" in sql:
            return FakeResult([])
        if "FROM sys.sql_expression_dependencies d" in sql:
            return FakeResult([])
        if "FROM sys.sql_modules m" in sql:
            return FakeResult([])
        raise AssertionError(f"Unexpected metadata query: {sql[:100]}")


class FakeEngine:
    def connect(self):
        return FakeConnection()


def test_sql_catalog_applies_allowlist_and_classification():
    policy = CatalogPolicy(
        allowed_schemas=("dbo",),
        allowed_objects=("dbo.Allowed*",),
        sensitive_columns={"dbo.AllowedTable.Customer*": "pii"},
    )

    catalog = extract_sql_server_catalog(FakeEngine(), policy)

    assert [obj["full_name"] for obj in catalog["objects"]] == ["dbo.AllowedTable"]
    column = catalog["objects"][0]["columns"][0]
    assert column["data_type"] == "nvarchar(100)"
    assert column["data_classification"] == "pii"
    assert catalog["objects"][0]["indexes"][0]["primary_key"] is True
    assert catalog["summary"]["objects_without_read_permission"] == []


def test_warehouse_catalog_is_read_only_and_mapping_status_is_explicit(tmp_path):
    db_path = tmp_path / "warehouse.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        "CREATE TABLE target_table (id INTEGER PRIMARY KEY, amount REAL);"
        "CREATE INDEX idx_target_amount ON target_table(amount);"
        "CREATE TABLE sync_meta (table_name TEXT PRIMARY KEY, last_synced_at TEXT, "
        "earliest_synced_date TEXT, latest_synced_date TEXT);"
        "INSERT INTO sync_meta VALUES ('target_table','2026-08-14','2026-01-01','2026-08-14');"
    )
    connection.commit()
    connection.close()

    warehouse = extract_warehouse_catalog(db_path)
    sql_catalog = {"objects": [{"full_name": "dbo.SourceTable"}]}
    mappings = compare_source_to_warehouse(sql_catalog, warehouse, [
        {"source": "dbo.SourceTable", "target": "target_table"},
        {"source": "dbo.Missing", "target": "target_table"},
        {"source": "dbo.SourceTable", "target": "missing_target"},
    ])

    target = next(obj for obj in warehouse["objects"] if obj["name"] == "target_table")
    assert target["sync_meta"]["latest_synced_date"] == "2026-08-14"
    assert target["indexes"][0]["columns"] == ["amount"]
    assert [mapping["status"] for mapping in mappings] == ["ok", "missing_source", "missing_target"]


def sample_catalog():
    return {
        "catalog_version": 1,
        "generated_at": "2026-08-14T00:00:00+00:00",
        "source": {"kind": "sql_server", "database": "NH_Report_TM"},
        "policy": {},
        "summary": {
            "object_count": 1,
            "column_count": 1,
            "columns_with_description": 0,
            "classified_column_count": 0,
            "warehouse_mapping_statuses": {"ok": 1},
        },
        "objects": [{
            "schema": "dbo", "name": "Source", "full_name": "dbo.Source", "object_type": "U",
            "type_desc": "USER_TABLE", "description": None, "row_count_estimate": 10,
            "has_read_permission": True, "columns": [{"ordinal": 1, "name": "id", "data_type": "int",
            "nullable": False, "data_classification": None, "description": None}], "indexes": [],
            "foreign_keys": [], "dependencies": [], "definition": None,
        }],
        "warehouse": {"kind": "sqlite", "path": "D:/one/warehouse.db", "available": True, "objects": []},
        "warehouse_mappings": [],
    }


def test_snapshot_versions_only_on_structural_change(tmp_path):
    first = sample_catalog()
    first_result = write_catalog_snapshot(first, tmp_path / "catalog")

    runtime_only = copy.deepcopy(first)
    runtime_only["generated_at"] = "2026-08-14T01:00:00+00:00"
    runtime_only["objects"][0]["row_count_estimate"] = 999
    runtime_only["warehouse"]["path"] = "E:/other/warehouse.db"
    second_result = write_catalog_snapshot(runtime_only, tmp_path / "catalog")

    changed = copy.deepcopy(runtime_only)
    changed["objects"][0]["columns"].append({
        "ordinal": 2, "name": "amount", "data_type": "decimal(18,2)", "nullable": True,
        "data_classification": None, "description": None,
    })
    changed["summary"]["column_count"] = 2
    third_result = write_catalog_snapshot(changed, tmp_path / "catalog")

    assert first_result["changed"] is True
    assert second_result["changed"] is False
    assert structural_hash(first) == structural_hash(runtime_only)
    assert third_result["changed"] is True
    assert diff_catalogs(runtime_only, changed)["sql_objects_changed"] == ["dbo.Source"]
    latest = json.loads((tmp_path / "catalog" / "latest.json").read_text(encoding="utf-8"))
    assert latest["structural_hash"] == third_result["structural_hash"]
