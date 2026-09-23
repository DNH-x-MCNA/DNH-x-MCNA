"""Keep the actual consecutive-month KPI matches visible to the model.

These tests call pure Python helpers with a synthetic payload; no model API is used.
"""
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(1, str(BACKEND))

import nl2sql  # noqa: E402


QUESTION = "Cá nhân/đội dưới 80% liên tiếp 3 tháng; khoảng hụt bao nhiêu?"


@pytest.mark.parametrize("group_by", ["manager", "employee"])
def test_streak_payload_keeps_current_qualifiers_after_large_history(group_by):
    historical = [{
        "group_code": f"OLD{i}", "group_name": "Dòng cũ " + "x" * 170,
        "month": "2026-06", "actual": 10, "target": 100,
        "achievement_pct": 10, "below_80_streak_months": 1,
    } for i in range(120)]
    candidate = {
        "group_code": "MATCH3", "group_name": "Đội đạt điều kiện" if group_by == "manager" else "Nhân viên đạt điều kiện",
        "month": "2026-08", "actual": 50, "target": 100,
        "achievement_pct": 50, "below_80_streak_months": 3,
    }
    payload = {
        "group_by": group_by, "month_from": "2026-05", "month_to": "2026-09",
        "decline_evaluated_through": "2026-08", "month_to_is_partial": True,
        "so_nhom_khong_hien": 0, "pham_vi_kenh": "OTC", "data_as_of": "2026-09-15",
        "rows": historical + [candidate],
    }

    view = json.loads(nl2sql._serialize_payload_for_model(
        "get_workforce_productivity", payload, QUESTION))

    assert len(json.dumps(view, ensure_ascii=False)) <= nl2sql.MAX_PAYLOAD_CHARS
    assert view["streak_below_80"]["evaluated_month"] == "2026-08"
    assert view["streak_below_80"]["qualifying_count"] == 1
    assert view["streak_below_80"]["rows"][0]["code"] == "MATCH3"
    assert view["streak_below_80"]["rows"][0]["gap_to_80"] == 30
    assert view["streak_below_80"]["rows"][0]["gap_to_target"] == 50
    assert view["streak_below_80"]["source_groups_not_shown"] == 0
    assert view["streak_below_80"]["other_group_by_needed_for_both_levels"] == (
        "employee" if group_by == "manager" else "manager")
    assert payload["rows"][-1] == candidate  # original result remains complete


def test_streak_question_requests_all_employee_groups_and_three_full_months():
    args = nl2sql._normalize_tool_input_for_question(
        "get_workforce_productivity", {"group_by": "employee", "months_back": 1, "limit": 10}, QUESTION)
    assert args["group_by"] == "employee"
    assert args["months_back"] >= 4  # running month is excluded from the three-month streak
    assert args["limit"] >= 1000


def test_unrelated_workforce_question_preserves_tool_arguments():
    args = {"group_by": "manager", "months_back": 1, "limit": 10}
    assert nl2sql._normalize_tool_input_for_question(
        "get_workforce_productivity", args, "Đội nào tăng nhân sự?") == args


def test_streak_view_preserves_scope_warning_and_marks_incomplete_source():
    payload = {
        "du_lieu": {
            "group_by": "employee", "decline_evaluated_through": "2026-08",
            "so_nhom_khong_hien": 17,
            "rows": [{"group_code": "E1", "group_name": "Một nhân viên", "month": "2026-08",
                      "actual": 50, "target": 100, "achievement_pct": 50,
                      "below_80_streak_months": 3}],
        },
        "CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG": "Phạm vi dữ liệu bị giới hạn.",
    }
    view = json.loads(nl2sql._serialize_payload_for_model(
        "get_workforce_productivity", payload, QUESTION))
    assert view["CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG"] == payload["CANH_BAO_BAT_BUOC_NOI_VOI_NGUOI_DUNG"]
    assert view["du_lieu"]["streak_below_80"]["count_is_complete"] is False
    assert view["du_lieu"]["streak_below_80"]["source_groups_not_shown"] == 17
