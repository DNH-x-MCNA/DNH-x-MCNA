"""One shortened DMS code can name several real promotion programs."""

import json
import os
import sys


BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt


def test_m35_limit_keeps_same_code_siblings_and_shows_both_to_model(monkeypatch):
    """TOP revenue used to drop the 644-order sibling of the 4,251-order program."""
    code = "Q4.2025_NHOM_BOPHE_SIRO_"

    def fake_bravo(sql, params=None):
        if "LinkRowId" in sql:
            return [{"CoverageDate": "2026-01-09", "LinkSyncedAt": "2026-01-09", "LinkRowId": 9}]
        # Return the ordered aggregate rows. The SQL must leave limiting until
        # after rows sharing a code can be found.
        assert "SELECT TOP (" not in sql
        common = {"Customers": 10, "OrdersWithoutInvoice": 0,
                  "PaidProductOccurrences": 0, "GiftProductCount": 0,
                  "ConfiguredProductCount": 0}
        return [
            {"ProgramId": 118969, "ProgramCode": code, "ProgramName": "Siro 10",
             "Orders": 4251, "AssociatedRevenue": 10_757_944_139, **common},
            {"ProgramId": 222, "ProgramCode": "OTHER", "ProgramName": "Other",
             "Orders": 100, "AssociatedRevenue": 5_000_000_000, **common},
            {"ProgramId": 118972, "ProgramCode": code, "ProgramName": "Siro 5",
             "Orders": 644, "AssociatedRevenue": 1_261_462_541, **common},
        ]

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.promotion_effectiveness(scope_area_code="MB", limit=1)

    assert [p["program_id"] for p in result["programs"]] == [118969, 118972]
    assert result["program_count_returned"] == 2
    assert all(p["code_is_ambiguous"] for p in result["programs"])
    assert [p["program_id"] for p in result["same_code_programs_to_distinguish"]] == [118969, 118972]
    shown = nl2sql._serialize_payload_for_model(
        "get_promotion_effectiveness", result,
        "Khuyen mai nhieu khach tham gia nhung khong tao tang truong")
    model_view = json.loads(shown)
    assert "118969" in shown and "118972" in shown
    assert len(shown) <= nl2sql.MAX_PAYLOAD_CHARS
    assert model_view["same_code_programs_to_distinguish"][1]["program_id"] == 118972


def test_m35_compact_model_view_keeps_program_ids_outside_top_eight(monkeypatch):
    """The actual UAT code ranked 12th; the ordinary model view kept eight rows."""
    code = "Q4.2025_NHOM_BOPHE_SIRO_"
    common = {"Customers": 10, "OrdersWithoutInvoice": 0,
              "PaidProductOccurrences": 0, "GiftProductCount": 0,
              "ConfiguredProductCount": 0}
    rows = [
        {"ProgramId": 300000 + i, "ProgramCode": f"OTHER_{i}",
         "ProgramName": "Chuong trinh khuyen mai " + "x" * 150,
         "Orders": 100,
         "AssociatedRevenue": (30 - i if i < 11 else 10 - (i - 11)) * 1_000_000_000,
         **common}
        for i in range(19)
    ]
    rows.insert(11, {"ProgramId": 118969, "ProgramCode": code,
                     "ProgramName": "Siro 10 " + "x" * 150,
                     "Orders": 4251, "AssociatedRevenue": 10_757_944_139, **common})
    rows.append({"ProgramId": 118972, "ProgramCode": code,
                 "ProgramName": "Siro 5 " + "x" * 150,
                 "Orders": 644, "AssociatedRevenue": 1_261_462_541, **common})

    def fake_bravo(sql, params=None):
        if "LinkRowId" in sql:
            return [{"CoverageDate": "2026-01-09", "LinkSyncedAt": "2026-01-09", "LinkRowId": 9}]
        return rows

    monkeypatch.setattr(rt, "_q_bravo", fake_bravo)
    result = rt.promotion_effectiveness(scope_area_code="MB", limit=20)
    shown = nl2sql._serialize_payload_for_model(
        "get_promotion_effectiveness", result, "Khuyen mai nao nhieu khach nhung khong tang truong")
    model_view = json.loads(shown)

    assert result["program_count_returned"] == 21
    assert model_view["_model_view"]["mode"] == "concise_priority_view"
    assert model_view["_model_view"]["collections"][0]["shown"] < 12
    assert [p["program_id"] for p in model_view["same_code_programs_to_distinguish"]] == [
        118969, 118972]
    assert len(shown) <= nl2sql.MAX_PAYLOAD_CHARS
