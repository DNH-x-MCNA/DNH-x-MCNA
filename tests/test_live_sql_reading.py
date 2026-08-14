# -*- coding: utf-8 -*-
import os
import sys
import time

import pytest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import nl2sql  # noqa: E402
import query_engine  # noqa: E402
import sql_schema_retriever as retriever  # noqa: E402


def _catalog():
    return {
        "generated_at": "2026-08-14T00:00:00+00:00",
        "source": {"database": "NH_Report_TM"},
        "summary": {"object_count": 4, "metadata_gaps": []},
        "objects": [
            {
                "schema": "dbo", "name": "vHoaDonTotal", "full_name": "dbo.vHoaDonTotal",
                "object_type": "V", "type_desc": "VIEW", "has_read_permission": True,
                "row_count_estimate": 0, "description": None,
                "definition": "SELECT Amount9 FROM BRV_HoaDonCt",
                "columns": [
                    {"name": "DocDate", "data_type": "date", "nullable": False},
                    {"name": "Amount9", "data_type": "decimal(18,2)", "nullable": True},
                ], "foreign_keys": [],
            },
            {
                "schema": "dbo", "name": "FACT_ThongKeTinhLuong",
                "full_name": "dbo.FACT_ThongKeTinhLuong", "object_type": "U",
                "type_desc": "USER_TABLE", "has_read_permission": True, "row_count_estimate": 100,
                "description": None, "definition": None,
                "columns": [
                    {"name": "V15Date", "data_type": "date", "nullable": True},
                    {"name": "V22Date", "data_type": "date", "nullable": True},
                    {"name": "V25Date", "data_type": "date", "nullable": True},
                    {"name": "PassCheckASOBonus", "data_type": "tinyint", "nullable": True},
                ], "foreign_keys": [],
            },
            {
                "schema": "dbo", "name": "DMS_CTKM", "full_name": "dbo.DMS_CTKM",
                "object_type": "U", "type_desc": "USER_TABLE", "has_read_permission": True,
                "row_count_estimate": 200, "description": None, "definition": None,
                "columns": [{"name": "PromotionCode", "data_type": "varchar(24)", "nullable": False}],
                "foreign_keys": [],
            },
            {
                "schema": "dbo", "name": "NoRead", "full_name": "dbo.NoRead",
                "object_type": "U", "type_desc": "USER_TABLE", "has_read_permission": False,
                "row_count_estimate": 0, "description": None, "definition": None,
                "columns": [], "foreign_keys": [],
            },
        ],
    }


@pytest.fixture(autouse=True)
def cached_catalog(monkeypatch):
    monkeypatch.setattr(retriever, "_catalog_cache", _catalog())
    monkeypatch.setattr(retriever, "_catalog_cache_loaded_at", time.time())


def test_catalog_search_finds_business_objects_without_full_static_schema():
    salary = retriever.search_sql_catalog("thưởng V15 V22 V25 ASO", limit=2, include_definition=False)
    promotion = retriever.search_sql_catalog("khuyến mãi", limit=2, include_definition=False)

    assert salary["matches"][0]["full_name"] == "dbo.FACT_ThongKeTinhLuong"
    assert promotion["matches"][0]["full_name"] == "dbo.DMS_CTKM"
    assert all(item["full_name"] != "dbo.NoRead" for item in salary["matches"])


def test_dynamic_context_is_tsql_and_does_not_dump_definitions():
    context = retriever.relevant_schema_context("doanh thu hóa đơn")

    assert "dbo.vHoaDonTotal" in context
    assert "TOP" in context and "khong dung LIMIT" in context
    assert "SELECT Amount9 FROM" not in context


def test_live_sql_tool_only_available_to_unscoped_privileged_roles():
    c_level_names = {tool["name"] for tool in nl2sql._tools_for_request(scope_role="c_level")}
    normal_names = {tool["name"] for tool in nl2sql._tools_for_request(scope_role="employee")}
    scoped_names = {
        tool["name"] for tool in nl2sql._tools_for_request(
            scope_area_code="MB", scope_role="regional_director"
        )
    }

    assert "query_sql_server" in c_level_names
    assert "search_sql_server_catalog" in c_level_names
    assert "query_sql_server" not in normal_names
    assert "query_sql_server" not in scoped_names
    assert set(nl2sql.RAW_SQL_TOOLS).isdisjoint(scoped_names)
    assert "search_sql_server_catalog" in scoped_names


def test_missing_warehouse_schema_returns_live_catalog_fallback(monkeypatch):
    monkeypatch.setattr(
        nl2sql,
        "search_sql_catalog",
        lambda *a, **kw: {"matches": [{"full_name": "dbo.DMS_CTKM"}]},
    )

    payload = nl2sql._raw_query_payload(
        {"ok": False, "error": "no such table: DMS_CTKM"},
        "local",
        "khuyến mãi",
    )

    assert payload["sql_server_catalog_fallback"]["matches"][0]["full_name"] == "dbo.DMS_CTKM"
    assert "query_sql_server" in payload["next_action"]
    assert "khong truy cap" in payload["next_action"]


@pytest.mark.parametrize("sql", [
    "SELECT * INTO dbo.CopyTable FROM dbo.vHoaDonTotal",
    "SELECT TOP 1 * FROM dbo.DIM_Pass",
    "SELECT TOP 1 * FROM OtherDatabase.dbo.vHoaDonTotal",
    "SELECT * FROM OPENROWSET(BULK 'x', SINGLE_CLOB) AS x",
    "SELECT 1 WAITFOR DELAY '00:00:05'",
    "SELECT TOP 10 * FROM dbo.vHoaDonTotal",
])
def test_live_sql_validator_blocks_write_secret_cross_db_and_external_access(sql):
    with pytest.raises(query_engine.SqlRejected):
        query_engine.validate_sql(sql, db="bravo")


def test_live_sql_validator_accepts_bounded_tsql_select():
    sql = "SELECT TOP (20) [DocDate], [Amount9] FROM dbo.vHoaDonTotal WHERE [DocDate] >= '2026-08-01'"
    assert query_engine.validate_sql(sql, db="bravo") == sql
