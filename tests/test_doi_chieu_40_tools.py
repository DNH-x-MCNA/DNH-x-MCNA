"""Khoa danh sach smoke/contract de tool moi khong bi bo quen khoi doi chieu."""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "doi_chieu_so_lieu_tool_moi.py"
SPEC = importlib.util.spec_from_file_location("doi_chieu_so_lieu_tool_moi", MODULE_PATH)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def test_catalog_smoke_phu_dung_toan_bo_tool_da_dang_ky():
    cases = checker._tool_cases_40()

    # 10/09/2026: 41 sau khi them get_customer_attrition_risk cho M22/S88.
    # 11/09/2026: 44 sau khi gop sku_revenue_drop_vs_stock, revenue_view_reconciliation,
    # salary_aso_detail tu hai nhanh sua tay may 24.
    # 13/09/2026: 45 sau khi them get_etc_contract_status cho C44/M42.
    # 15/09/2026: 46 sau khi them get_etc_revenue_by_item_type (UAT dnh_etc, nhom hang ETC).
    # 15/09/2026: 49 sau khi them danh sach khach moi, khach chua tai don, KPI trong tam.
    # 15/09/2026: 50 sau khi them get_inventory_item_stock (ton kho theo ten san pham).
    # 21/09/2026: 51 sau khi them get_revenue_seasonality (C08/S80, tranh timeout).
    assert len(cases) == 51
    assert set(cases) == set(checker.rt.TEMPLATES)


def test_payload_rong_khong_duoc_tinh_la_da_kiem():
    assert checker._ly_do_khong_co_payload([]) == "danh sach rong"
    assert checker._ly_do_khong_co_payload({"warning": "khong co du lieu"}) is not None
    assert checker._ly_do_khong_co_payload({"error": "loi truy van"}) == "loi truy van"


def test_payload_co_du_lieu_hoac_moc_snapshot_duoc_chap_nhan():
    assert checker._ly_do_khong_co_payload([{"value": 1}]) is None
    assert checker._ly_do_khong_co_payload({"total": 12}) is None
    assert checker._ly_do_khong_co_payload({"total": 0, "snapshot_date": "2026-08-31"}) is None


def test_gate_cho_phep_hai_gioi_han_nguon_da_biet():
    bo_qua = [
        "get_promotion_effectiveness",
        "get_receivables_period_compare",
    ]

    da_biet, bat_thuong = checker._phan_loai_bo_qua(bo_qua)

    assert da_biet == bo_qua
    assert bat_thuong == []
    assert checker._ma_thoat_gate(86, [], bo_qua) == 0


def test_gate_van_chan_muc_bo_qua_ngoai_danh_sach():
    bo_qua = ["get_promotion_effectiveness", "get_inventory_expiry_report"]

    da_biet, bat_thuong = checker._phan_loai_bo_qua(bo_qua)

    assert da_biet == ["get_promotion_effectiveness"]
    assert bat_thuong == ["get_inventory_expiry_report"]
    assert checker._ma_thoat_gate(86, [], bo_qua) == 1


def test_gate_chan_ket_qua_trang_va_bat_ky_cho_lech_nao():
    assert checker._ma_thoat_gate(0, [], []) == 1
    assert checker._ma_thoat_gate(86, ["doanh thu lech"], []) == 1
