# -*- coding: utf-8 -*-
"""
Suy luan cay to chuc TP (Truong phong/GD mien) -> QLV -> TDV tu dim_nhanvien.

Bravo KHONG co bang phan cap to chuc tuong minh (da kiem chung 15/07/2026 - khong co bang
History/Log/Audit/Change nao, cung khong co khoa ngoai "ManagerId" tren DIM_NhanVien). Phai suy luan
tu 2 dau moi gian tiep:

1. TP <-> QLV: ca 2 deu co area_code rieng (MB/MT/MN) - TP phu trach ca vung, QLV phu trach 1 phan
   trong vung do. Lien ket qua area_code trung nhau (khong chinh xac 100% vi 1 vung co the co nhieu
   TP, nhung la cach tot nhat hien co).
2. QLV <-> TDV: TDV mang manager_area_code (ma "to" nho, dang V01-V22) tren chinh ban ghi cua ho. QLV
   phu trach 1 to lai co 1 ban ghi "bong" rieng - POSITION_CODE ghi la 'TDV' (khong phai 'QLV'!), TEN
   co hau to "(QLV)" (vd 'Pham Van Phuong (QLV)'), va ban ghi bong nay CUNG mang dung manager_area_code
   cua to do. Suy luan: tim ban ghi bong nay, cat hau to "(QLV)" khoi ten, roi khop voi ban ghi QLV
   THAT (position_code='QLV') co cung ten.

Do day la suy luan qua quy uoc dat ten (KHONG phai khoa ngoai chinh thuc), ~30% cac to (6/20 tai thoi
diem khao sat 15/07/2026) KHONG xac dinh duoc QLV phu trach qua cach nay (ban ghi bong da EndDate/doi
vai tro nhung chua co ban ghi bong moi thay the). MOI ham o day LUON tra ve "Chua xac dinh" cho
truong hop nay, TUYET DOI KHONG doan bua/gan mac dinh vao 1 QLV bat ky - sai du lieu quy trach nhiem
canh nay rat nghiem trong (vd tinh nham doanh thu/KPI cho dung nguoi).
"""
from local_warehouse import get_conn


def _q(sql, params=()):
    conn = get_conn()
    try:
        conn.row_factory = None
        cur = conn.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def zone_to_qlv_map() -> dict:
    """Tra ve {manager_area_code (V0x): {employee_code, name} cua QLV THAT phu trach, hoac None neu
    khong xac dinh duoc}. Chi xet nguoi dang con hieu luc (end_date IS NULL, is_resigned khac 1)."""
    shadows = _q("""
        SELECT manager_area_code, name FROM dim_nhanvien
        WHERE position_code='TDV' AND name LIKE '%(QLV)%'
          AND end_date IS NULL AND COALESCE(is_resigned,0)<>1 AND manager_area_code IS NOT NULL
    """)
    result = {}
    for s in shadows:
        zone = s["manager_area_code"]
        base_name = s["name"].replace("(QLV)", "").strip()
        real = _q("""
            SELECT employee_code, name FROM dim_nhanvien
            WHERE position_code='QLV' AND end_date IS NULL AND COALESCE(is_resigned,0)<>1
              AND name=? LIMIT 1
        """, (base_name,))
        result[zone] = {"employee_code": real[0]["employee_code"], "name": real[0]["name"]} if real else None
    return result


def qlv_zones(employee_code: str) -> list:
    """Danh sach cac zone (V0x) ma 1 QLV (theo employee_code THAT) dang phu trach - dao nguoc cua
    zone_to_qlv_map()."""
    m = zone_to_qlv_map()
    return [z for z, qlv in m.items() if qlv and qlv["employee_code"] == employee_code]


def team_of_qlv(employee_code: str) -> list:
    """Danh sach TDV (khong gom ban ghi bong cua chinh QLV) thuoc quyen quan ly cua 1 QLV - GOM tat
    ca cac zone ma QLV do phu trach (1 QLV co the phu trach nhieu zone)."""
    zones = qlv_zones(employee_code)
    if not zones:
        return []
    placeholders = ",".join(["?"] * len(zones))
    return _q(f"""
        SELECT employee_code, name, position_code, area_code, manager_area_code FROM dim_nhanvien
        WHERE manager_area_code IN ({placeholders}) AND end_date IS NULL AND COALESCE(is_resigned,0)<>1
          AND name NOT LIKE '%(QLV)%'
        ORDER BY name
    """, tuple(zones))


def qlv_history_for_zone(zone: str) -> list:
    """Timeline nguoi tung/dang giu vai tro 'ban ghi bong QLV' cua 1 zone V0x, sap xep theo
    start_date - dung de tra loi 'QLV vung nay tung doi qua ai'. CHI hien thi cac ban ghi CO ten
    dang '(QLV)' (loai cac TDV thuong trong cung zone)."""
    return _q("""
        SELECT employee_code, name, start_date, end_date, is_resigned FROM dim_nhanvien
        WHERE manager_area_code=? AND name LIKE '%(QLV)%'
        ORDER BY start_date
    """, (zone,))


def all_zones_with_qlv_status() -> list:
    """Toan bo cac zone V0x dang hoat dong, kem trang thai xac dinh duoc QLV hay khong - dung de
    liet ke tong quan/canh bao zone nao dang 'trong' QLV ro rang."""
    zones = _q("""
        SELECT DISTINCT manager_area_code FROM dim_nhanvien
        WHERE manager_area_code IS NOT NULL AND end_date IS NULL AND COALESCE(is_resigned,0)<>1
        ORDER BY manager_area_code
    """)
    m = zone_to_qlv_map()
    out = []
    for z in zones:
        zone = z["manager_area_code"]
        qlv = m.get(zone)
        out.append({"zone": zone, "qlv_employee_code": qlv["employee_code"] if qlv else None,
                     "qlv_name": qlv["name"] if qlv else "Chưa xác định"})
    return out
