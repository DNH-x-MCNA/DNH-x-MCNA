# -*- coding: utf-8 -*-
"""01/10/2026 - Cost of Value thang 9 (log may 24): hai mau "goi lai cung tool" con xay ra sau 27/09.

1) get_inventory_expiry_report: tool tra 30-50 SKU canh bao nhung ban gui model chi co 6-12 dong mau du limit 30,
   100 hay 200. 27/09-01/10 co 8 luot goi lai chi de xin them dong (vo ich); ba lan nguoi dung hoi "danh sach SKU"
   deu khong liet ke duoc, mot luot phai tu viet SQL. Nay cac dong con lai di kem o bang gon.
2) get_employee_directory: tra ten 5 ma nhan vien bang 5 lan goi (ca thang 6 luot, 26 lan goi thua).
Du lieu gia, khong goi model, khong cham Bravo."""
import json
import os
import sqlite3
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import local_warehouse  # noqa: E402
import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

TEN_DAI = " (Kiện x 60 hộp x 1 lọ 125ml) - Chi nhánh 3 - Công ty Cổ phần Dược phẩm mẫu tại Bình Dương"
NHOM = (("CO_NGUY_CO_THIEU_HANG_DERIVED", 14), ("CHAM_LUAN_CHUYEN_DERIVED", 24), ("TON_KHONG_BAN_3_THANG", 12))


def _payload(ten_dai=True, so_ung_vien=10):
    rows = []
    for trang_thai, so in NHOM:
        for i in range(so):
            ma = f"{trang_thai[:3]}{i:03d}"
            rows.append({"item_code": ma, "item_name": f"Sản phẩm mẫu {ma}" + (TEN_DAI if ten_dai else ""),
                         "stock_qty": 19820.0 + i, "average_monthly_qty_3m": 87136.5,
                         "average_monthly_revenue_3m": 4_813_226_467.0, "months_of_cover": 0.23, "status": trang_thai})
    rows[0]["het_hang_ghi_nhan"] = True
    ung_vien = [{"item_code": r["item_code"], "customers": [
        {"item_code": r["item_code"], "customer_code": f"KH{k}", "customer_name": f"Khách hàng mẫu số {k}",
         "qty_3m": 100, "revenue_3m": 3_000_000} for k in range(3)]} for r in rows[:so_ung_vien]]
    return {"as_of": "2026-10-01", "area_code": None, "rows": [], "khong_xac_dinh_han": 0,
            "summary": {"duoi_3_thang": {"so_lo": 8, "tong_so_luong": 1157.0}},
            "supply_risk": {"status": "OK_DERIVED", "focus": "all", "total_actionable_skus": 53,
                            "status_counts": {"CO_NGUY_CO_THIEU_HANG_DERIVED": 15, "CHAM_LUAN_CHUYEN_DERIVED": 26,
                                              "TON_KHONG_BAN_3_THANG": 12},
                            "rows": rows, "recent_customer_candidates": ung_vien,
                            "answer_rule": "x" * 480, "canh_bao_don_vi": "y" * 620, "definition": "z" * 320}}


def _gui(cau, **kw):
    chuoi = nl2sql._serialize_payload_for_model("get_inventory_expiry_report", _payload(**kw), cau)
    assert len(chuoi) <= nl2sql.MAX_PAYLOAD_CHARS
    gui = json.loads(chuoi)
    assert "_model_view" not in gui                      # khong roi vao luoi cat chung (cat moi danh sach)
    return gui["supply_risk"]


def test_hoi_danh_sach_model_nhan_gan_du_50_sku_thay_vi_12():
    sr = _gui("hãy cho tôi danh sách sku")

    mau, bang = sr["rows"], sr["cac_dong_con_lai"]
    so_bang = sum(len(ds) for ds in bang["theo_trang_thai"].values())
    assert len(mau) == 12 == sr["rows_shown_to_model"]                 # dong mau chi tiet giu nguyen (4 moi nhom)
    assert so_bang == sr["rows_in_compact_table"] and len(mau) + so_bang >= 45        # truoc khi sua: 12/50
    assert sr["rows_not_shown_to_model"] == 50 - len(mau) - so_bang
    assert set(bang["theo_trang_thai"]) == {t for t, _ in NHOM}        # phai cat thi nhom nao cung con dong
    assert bang["cot"][:4] == ["item_code", "item_name", "stock_qty", "average_monthly_qty_3m"]
    assert "months_of_cover" not in json.dumps(sr, ensure_ascii=False)
    # Ma du de dinh danh; ten qua dai duoc rut va danh dau.
    ma_hien = {r["item_code"] for r in mau} | {d[0] for ds in bang["theo_trang_thai"].values() for d in ds}
    assert len(ma_hien) == len(mau) + so_bang
    assert any(str(d[1]).endswith("…") for ds in bang["theo_trang_thai"].values() for d in ds)
    # So "chua liet ke" tinh theo ca hai phan: tong that 53, tool tra 50.
    chua = sr["so_dong_chua_hien_theo_trang_thai"]
    assert sum(chua.values()) == 53 - len(mau) - so_bang
    assert "KHONG goi lai" in sr["cac_dong_con_lai_ghi_chu"]


def test_ten_ngan_thi_du_ca_50_va_khong_rut_ten():
    sr = _gui("liệt kê các SKU tồn cao", ten_dai=False)
    bang = sr["cac_dong_con_lai"]["theo_trang_thai"]
    assert sr["rows_in_compact_table"] == 38 and sr["rows_not_shown_to_model"] == 0
    assert not any(str(d[1]).endswith("…") for ds in bang.values() for d in ds)
    assert sr["so_dong_chua_hien_theo_trang_thai"] == {"CO_NGUY_CO_THIEU_HANG_DERIVED": 1,
                                                       "CHAM_LUAN_CHUYEN_DERIVED": 2}
    # Dong can danh dau het hang nam trong dong mau nen bang khong can cot ghi_chu.
    assert sr["cac_dong_con_lai"]["cot"] == ["item_code", "item_name", "stock_qty", "average_monthly_qty_3m"]


def test_cau_khong_hoi_danh_sach_giu_khach_goi_y_va_khong_rut_ten():
    sr = _gui("SKU khách cần nhưng kho thiếu; đơn/DT nguy cơ mất vì thiếu hàng")
    assert len(sr["rows"]) == 12 and sr["customer_candidate_groups_shown"] == 3      # nhu ban dang dat UAT (V39)
    bang = (sr.get("cac_dong_con_lai") or {}).get("theo_trang_thai") or {}
    assert sr["rows_in_compact_table"] == sum(len(ds) for ds in bang.values()) > 0
    assert not any(str(d[1]).endswith("…") for ds in bang.values() for d in ds)


def test_it_dong_thi_khong_co_bang_gon():
    payload = _payload()
    payload["supply_risk"]["rows"] = payload["supply_risk"]["rows"][:5]            # mot nhom, 5 dong <= 6 dong mau
    gui = nl2sql._payload_for_model("get_inventory_expiry_report", payload, "danh sách sku")
    assert gui["supply_risk"]["rows_shown_to_model"] == 5 and gui["supply_risk"]["rows_in_compact_table"] == 0
    assert "cac_dong_con_lai" not in gui["supply_risk"]


def test_hoi_danh_sach_thi_goi_tool_voi_muc_tran_50(monkeypatch):
    nhan = {}
    monkeypatch.setattr(rt, "_write_log", lambda *a, **k: None)
    monkeypatch.setitem(rt.TEMPLATES, "get_inventory_expiry_report", lambda **kw: nhan.update(kw) or {"rows": []})

    rt.call_template("get_inventory_expiry_report", {"focus": "all"}, question="hãy cho tôi danh sách sku tồn cao")
    assert nhan["limit"] == 50 and nhan["focus"] == "overstock"

    nhan.clear()
    rt.call_template("get_inventory_expiry_report", {"focus": "all", "limit": 30},
                     question="Giá trị tồn kho, số tháng tồn, chậm luân chuyển theo tháng")
    assert nhan["limit"] == 30                                          # khong hoi danh sach: giu nguyen


def _kho_nhan_vien(tmp_path, monkeypatch):
    path = tmp_path / "warehouse.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE dim_nhanvien (employee_code TEXT, dmsid TEXT, name TEXT, position_code TEXT, area_code TEXT,
                                   is_duplicate INTEGER);
        CREATE TABLE dim_chucvu (position_code TEXT, description TEXT);
        CREATE TABLE dmssx_nhanvien (dmscode TEXT, code TEXT, name TEXT);
        INSERT INTO dim_chucvu VALUES ('TDV', 'Trinh duoc vien');
    """)
    conn.executemany("INSERT INTO dim_nhanvien VALUES (?,?,?,?,?,?)",
                     [(f"DNH{i:05d}", f"DMS{i}", f"Nhân viên {i:02d}", "TDV", "MB", 0) for i in range(1, 41)])
    conn.execute("INSERT INTO dmssx_nhanvien VALUES ('SX01', 'SALE01', 'Dung ETC')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(local_warehouse, "DB_PATH", str(path))


def test_tra_nhieu_ma_nhan_vien_trong_mot_lan_goi(tmp_path, monkeypatch):
    _kho_nhan_vien(tmp_path, monkeypatch)

    rows = rt.employee_directory(search="DNH00007, DNH00012; SALE01, DNH00007")

    assert {r["employee_code"] for r in rows} == {"DNH00007", "DNH00012", "SX01"}
    assert {r["name"] for r in rows} == {"Nhân viên 07", "Nhân viên 12", "Dung ETC"}


def test_mot_tu_khoa_giu_nguyen_hanh_vi_cu(tmp_path, monkeypatch):
    _kho_nhan_vien(tmp_path, monkeypatch)
    assert [r["employee_code"] for r in rt.employee_directory(search="Nhân viên 07")] == ["DNH00007"]
    assert len(rt.employee_directory(search="DNH", limit=5)) == 5
    assert len(rt.employee_directory()) == 30                           # khong tim: mac dinh 30 nguoi dau


def test_schema_noi_ro_tra_nhieu_ma_mot_lan():
    tool = next(t for t in nl2sql.TEMPLATE_TOOLS if t["name"] == "get_employee_directory")
    assert "MOT lan goi" in tool["input_schema"]["properties"]["search"]["description"]
