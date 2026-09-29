# -*- coding: utf-8 -*-
"""UAT M32 lan 2 (29/09/2026). Sau #158 phan % dat va xep hang TDV da dung, con hai loi:

1) "Vung nao co khoang trong do phu lon nhat": model goi them get_customer_product_coverage, tool tu chon mode
   sku_target va tra "khong co target theo SKU" -> model noi khong tinh duoc. Kho CO KPI SKU tung TDV
   (SKUQuantity/SKUTarget trong ket qua tinh luong) - dung lam khoang trong do phu theo doi/mien.
2) Cuoi cau bi gan "Doi chieu KPI va cay doi ngu: Model chua goi nguon" + "Gioi han ket luan": buoc KPI khong nhan
   get_focus_product_kpi va quy tac team_employee_rollup chi nhan get_revenue_tree/get_kpi_ranking.
Du lieu gia, khong cham Bravo, khong goi model."""
import sqlite3
import sys
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
for duong in (GOC / "backend", GOC / "tests"):
    if str(duong) not in sys.path:
        sys.path.append(str(duong))

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402
import test_m32_xep_hang_trong_tam as goc  # noqa: E402
from query_plan import build_query_plan  # noqa: E402

CAU_M32 = "SKU chiến lược đạt bao nhiêu % target tại từng vùng; vùng nào có khoảng trống độ phủ lớn nhất?"


def _kho_co_sku(tmp_path, monkeypatch):
    goc._kho(tmp_path, monkeypatch)
    c = sqlite3.connect(local_warehouse.DB_PATH)
    for cot in ("sku_quantity", "sku_target", "sku_percent"):
        c.execute(f"ALTER TABLE fact_thongketinhluong ADD COLUMN {cot} REAL")
    # Chi tieu 40 ma moi TDV; doi MBKV5 ban it ma nhat (20 ma), MBKV9 vua du, cac doi khac 35 ma.
    c.execute("UPDATE fact_thongketinhluong SET sku_target=40, sku_quantity=35, sku_percent=35.0/40 "
              "WHERE position_code='TDV'")
    c.execute("UPDATE fact_thongketinhluong SET sku_quantity=20, sku_percent=0.5 "
              "WHERE position_code='TDV' AND manager_code='MBKV5'")
    c.execute("UPDATE fact_thongketinhluong SET sku_quantity=40, sku_percent=1.0 "
              "WHERE position_code='TDV' AND manager_code='MBKV9'")
    c.commit()
    c.close()


def test_khoang_trong_do_phu_sku_theo_doi_xep_thieu_nhieu_nhat_truoc(tmp_path, monkeypatch):
    _kho_co_sku(tmp_path, monkeypatch)
    kt = rt.focus_product_kpi("2026-09", area_code="MB")["khoang_trong_do_phu_sku"]

    doi = kt["theo_doi"]
    assert doi[0]["manager_code"] == "MBKV5"
    assert doi[0]["so_ma_con_thieu"] == 9 * 20 and doi[0]["so_tdv_chua_dat_sku"] == 9
    assert round(doi[0]["pct_sku_trung_binh"], 6) == 50.0
    mbkv9 = next(d for d in doi if d["manager_code"] == "MBKV9")
    assert mbkv9["so_ma_con_thieu"] == 0 and mbkv9["so_tdv_chua_dat_sku"] == 0 and doi[-1] is mbkv9
    assert [d["so_ma_con_thieu"] for d in doi] == sorted((d["so_ma_con_thieu"] for d in doi), reverse=True)
    mien = {m["mien"]: m for m in kt["theo_mien"]}
    assert mien["MB"]["so_ma_con_thieu"] == 9 * 20 + 8 * 9 * 5          # MBKV5 + 8 doi thieu 5 ma/nguoi
    assert "KHONG rieng SKU trong tam" in kt["dinh_nghia"]


def test_kho_chua_co_cot_sku_thi_khong_bia_khoang_trong(tmp_path, monkeypatch):
    goc._kho(tmp_path, monkeypatch)
    assert "khoang_trong_do_phu_sku" not in rt.focus_product_kpi("2026-09", area_code="MB")


def test_ghi_chu_m32_chi_duong_do_phu_trong_cung_ket_qua():
    _tool, ghi_chu = nl2sql._required_tool_for_request(
        CAU_M32, [{"name": "get_focus_product_kpi"}, {"name": "get_customer_product_coverage"}])
    assert "khoang_trong_do_phu_sku" in ghi_chu and "KHONG goi" in ghi_chu and "sku_target" in ghi_chu


def _ke_hoach(vai_tro="regional_director", vung="MB"):
    return build_query_plan(CAU_M32, query_id="m32-plan", scope_role=vai_tro, scope_area_code=vung,
                            scope_employee_code=None, scope_channel=None, max_rounds=10, max_tools_per_round=5,
                            max_unique_tools=12, request_timeout_seconds=110)


def test_ke_hoach_m32_hoan_tat_khi_chi_goi_tool_trong_tam(tmp_path, monkeypatch):
    _kho_co_sku(tmp_path, monkeypatch)
    payload = rt.focus_product_kpi("2026-09", area_code="MB")
    plan = _ke_hoach()
    assert {s.domain for s in plan.steps} == {"kpi", "product"}
    plan.start_tool("get_focus_product_kpi", {"area_code": "MB"}, "k1")
    plan.finish_tool("k1", ok=True, payload=payload, source="template:get_focus_product_kpi",
                     duration_ms=5, timeout_seconds=40)
    plan.finalize()
    assert plan.status == "completed", plan.as_dict()
    assert [(r.rule, r.status) for r in plan.reconciliation_rules] == [("team_employee_rollup", "passed")]


def test_ke_hoach_m32_tool_loi_thi_khong_danh_dau_hoan_tat():
    plan = _ke_hoach()
    plan.start_tool("get_focus_product_kpi", {}, "k1")
    plan.finish_tool("k1", ok=False, payload={"error": "Kho chua co ket qua KPI tinh luong."},
                     source="template:get_focus_product_kpi", duration_ms=5, timeout_seconds=40)
    plan.finalize()
    assert plan.status != "completed"
