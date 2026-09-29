# -*- coding: utf-8 -*-
"""UAT C43 29/09/2026 - "khong lay duoc nhieu hon 1 hop dong, lech so hop dong dang hoat dong".

1) get_etc_contract_status tra 5 danh sach x toi 50 hop dong, moi dong ~20 truong. Payload vuot
   MAX_PAYLOAD_CHARS nen luoi cat chung ha moi danh sach xuong 1 dong - model bao "cong cu chi tra 1
   dong minh hoa cho moi nhom du limit=10 hay 50".
2) Danh sach duoi 50% xep theo ty le tang dan, nen cau "10 hop dong GIA TRI CAO NHAT trong nhom duoi
   50%" bi tra bang hop dong 0% con lai lon nhat.
3) Hop dong gia tri bat thuong bi loai khoi so dem "con hieu luc" - cau hoi so hop dong dang hoat dong
   can tong ca hai phan.
Du lieu gia, khong cham Bravo, khong goi model."""
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import nl2sql
import report_templates as rt

CAU_HOI = "10 hợp đồng giá trị cao nhất trong nhóm thực hiện dưới 50% là những hợp đồng nào?"


def _dong(i, gia_tri, da_xuat, con_lai_ngay=200, lech=0, so_hoa_don=1):
    return {
        "Id": i, "DocNo": "KTG2-%d/HDGENERIC/2025-2026" % i, "CustomerCode": "HCM%05d" % i,
        "StatusId": 2, "SoDong": 4, "SoDongLechGiaTri": lech, "SoPhienBan": 1, "SoPhuLuc": 0,
        "FromDate": "2026-01-01", "ToDate": "2026-12-31",
        "GiaTri": gia_tri, "DaXuat": da_xuat, "SoHoaDon": so_hoa_don,
        "SoDongGanNham": 0, "TienGanNham": 0, "TienKhacMaKhach": 0,
        "LanXuatCuoi": "2026-09-01", "ConLaiNgay": con_lai_ngay,
    }


def _du_lieu():
    rows = []
    for i in range(1, 2361):                         # 2.360 hop dong sach con hieu luc
        gia_tri = 1_000_000_000.0 + i * 7_000_000.0  # gia tri tang theo i
        da_xuat = gia_tri * (0.1 if i % 10 < 7 else 0.8)   # ~70% duoi 50%
        rows.append(_dong(i, gia_tri, da_xuat))
    for i in range(3001, 3061):                      # 60 hop dong gia tri bat thuong, 45 con hieu luc
        rows.append(_dong(i, 9e15, 0.0, con_lai_ngay=200 if i < 3046 else -3, lech=1, so_hoa_don=0))
    for i in range(4001, 4021):                      # 20 hop dong sach da het han
        rows.append(_dong(i, 5e8, 0.0, con_lai_ngay=-10, so_hoa_don=0))
    return rows


def _chay_tool(monkeypatch, args):
    rows = _du_lieu()
    monkeypatch.setattr(rt, "_q_bravo", lambda sql, params=None: rows)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-29")
    return rt.etc_contract_status(as_of_date="2026-09-29", **args)


def test_cau_gia_tri_cao_nhat_duoi_50_xep_theo_gia_tri_va_du_10_dong_toi_model(monkeypatch):
    args = nl2sql._normalize_tool_input_for_question("get_etc_contract_status", {"limit": 10}, CAU_HOI)
    assert args["sap_xep_duoi_50"] == "gia_tri" and args["limit"] >= 10

    payload = _chay_tool(monkeypatch, args)
    encoded = nl2sql._serialize_payload_for_model("get_etc_contract_status", payload, CAU_HOI)
    assert len(encoded) <= nl2sql.MAX_PAYLOAD_CHARS
    model = json.loads(encoded)

    assert model["_model_view"]["mode"] == "bang_gon_hop_dong_etc"
    bang = model["hop_dong_thuc_hien_duoi_50_pct"]
    gia_tri = [row[bang["cot"].index("gia_tri_hop_dong")] for row in bang["dong"]]
    assert len(gia_tri) == 10                              # truoc day: 1 dong
    assert gia_tri == sorted(gia_tri, reverse=True)       # gia tri lon nhat truoc
    lon_nhat_duoi_50 = max(r["gia_tri_hop_dong"] for r in payload["hop_dong_thuc_hien_duoi_50_pct"])
    assert gia_tri[0] == round(lon_nhat_duoi_50)
    # So dem la tong that, khong phai so dong dang hien.
    assert model["so_hop_dong_thuc_hien_duoi_50_pct"] == payload["so_hop_dong_thuc_hien_duoi_50_pct"] > 1000


def test_xin_50_hop_dong_thi_model_nhan_nhieu_dong_khong_con_1(monkeypatch):
    cau = "Liệt kê 50 hợp đồng ETC thực hiện dưới 50%"
    args = nl2sql._normalize_tool_input_for_question("get_etc_contract_status", {"limit": 50}, cau)
    payload = _chay_tool(monkeypatch, args)
    model = json.loads(nl2sql._serialize_payload_for_model("get_etc_contract_status", payload, cau))

    hien = len(model["hop_dong_thuc_hien_duoi_50_pct"]["dong"])
    assert hien >= 40                                      # truoc day: 1 dong
    assert "KHONG goi lai tool" in model["_model_view"]["giai_thich"]
    ghi_chu = {x["danh_sach"]: x for x in model["_model_view"]["dang_liet_ke"]}
    assert ghi_chu["hop_dong_thuc_hien_duoi_50_pct"]["tong_that"] == payload["so_hop_dong_thuc_hien_duoi_50_pct"]


def test_so_hop_dong_con_hieu_luc_tinh_ca_hop_dong_gia_tri_bat_thuong(monkeypatch):
    payload = _chay_tool(monkeypatch, {})

    assert payload["so_hop_dong_con_hieu_luc"] == 2360                 # phan sach, dung cho tong tien
    assert payload["so_hop_dong_con_hieu_luc_gia_tri_bat_thuong"] == 45
    assert payload["so_hop_dong_con_hieu_luc_tat_ca"] == 2405
    assert "so_hop_dong_con_hieu_luc_tat_ca" in payload["dinh_nghia"]["con_hieu_luc"]
    # Mac dinh van xep theo ty le nhu truoc.
    assert payload["hop_dong_thuc_hien_duoi_50_pct_sap_xep"] == "ty le thuc hien tang dan"


def test_cau_khong_hoi_gia_tri_cao_nhat_thi_giu_thu_tu_ty_le():
    args = nl2sql._normalize_tool_input_for_question(
        "get_etc_contract_status", {}, "Hợp đồng ETC nào thực hiện dưới 50%?")
    assert "sap_xep_duoi_50" not in args
