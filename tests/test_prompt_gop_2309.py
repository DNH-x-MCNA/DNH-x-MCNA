"""Business meanings exposed to the model without any model API call."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import nl2sql
import schema_context


def _description(name):
    return next(tool["description"] for tool in nl2sql.TEMPLATE_TOOLS
                if tool["name"] == name)


def test_silent_customer_top_product_names_its_own_period():
    description = _description("get_customers_silent")
    assert "ky_san_pham" in description
    assert "ky_nhin_lai" in description
    assert "12 thang" in description
    assert "6 thang" in description
    assert "san pham mua nhieu nhat" in description
    assert "ghi ro" in description


def test_etc_channel_total_identifies_all_three_regions():
    description = _description("get_revenue_by_channel")
    assert "ETC" in description
    assert "ca 3 mien" in description
    assert "scope_area_code" in description


def test_etc_scope_note_says_three_regions_only_without_area_scope(monkeypatch):
    monkeypatch.setattr(nl2sql, "latest_data_date", lambda: "2026-09-15")
    monkeypatch.setattr(nl2sql, "sync_freshness_note", lambda: "")
    monkeypatch.setattr(nl2sql, "retrieve_relevant_glossary", lambda *a, **k: [])
    monkeypatch.setattr(nl2sql, "retrieve_similar_examples", lambda *a, **k: [])
    monkeypatch.setattr(nl2sql, "relevant_schema_context", lambda *a, **k: "")

    all_regions = nl2sql._dynamic_context_note(scope_channel="ETC")
    mb_only = nl2sql._dynamic_context_note(scope_channel="ETC", scope_area_code="MB")
    assert "toan kenh ETC, gom ca 3 mien" in all_regions
    assert "toan kenh ETC, gom ca 3 mien" not in mb_only


def test_c31_compensation_includes_reactivated_revenue():
    description = _description("get_customer_movement")
    assert "added_revenue" in description
    assert "reactivated_revenue" in description
    assert "compensation_pct_of_lost_revenue" in description
    assert "lost_previous_revenue" in description


def test_known_customer_area_error_stays_on_correctable_local_query(monkeypatch):
    def unexpected_catalog(*_args, **_kwargs):
        raise AssertionError("A wrong column in a known local table is not a source gap")

    monkeypatch.setattr(nl2sql, "search_sql_catalog", unexpected_catalog)
    payload = nl2sql._raw_query_payload(
        {"ok": False, "error": "sqlite3.OperationalError: no such column: c.area_code"},
        "local", "Doanh thu theo mien",
    )
    assert "tp.area_code" in payload["query_correction"]
    assert "query_database" in payload["next_action"]
    assert "sql_server_catalog_fallback" not in payload


def test_free_sql_schema_names_the_only_customer_region_join():
    context = schema_context.SCHEMA_CONTEXT
    assert "c.area_code" in context
    assert "LEFT JOIN dim_tinhthanhpho tp ON tp.city_id=c.city_id" in context
    assert "tp.area_code" in context
