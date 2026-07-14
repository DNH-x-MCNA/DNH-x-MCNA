# -*- coding: utf-8 -*-
"""Suy luan vung mien (MB/MT/MN) tu tien to ma khach hang - dung lam FALLBACK CHI khi khach hang
khong map duoc vung qua duong chinh (LEFT JOIN dms_khachhang/dmssx_khachhang -> dim_tinhthanhpho),
vi du khach "mo coi" khong co ho so trong bang khach hang goc (vd HCM13508).

Nguon: DNH dat ma khach hang theo TIEN TO VIET TAT TINH/THANH (HCM=Ho Chi Minh, HNO=Ha Noi,
AGI=An Giang...). Bang duoi xay tu doi chieu ~47.500 khach hang DA xac dinh duoc vung qua duong
chinh (ben D:\\DNH, repo backend khac cung du an) - chi giu tien to co do THUAN >=95% (it nhat 95%
khach cung tien to roi vao dung 1 vung) VA co it nhat 5 khach hang mau, de tranh tien to hiem/mo ho.

CHI dung de SUY LUAN vung cho khach KHONG map duoc qua duong chinh - khong bao gio ghi de len vung
da xac dinh dung qua CityId (duong chinh luon uu tien, dang tin hon).
"""
import re

CUSTOMER_CODE_PREFIX_TO_REGION = {
    "AGI": "MN", "BDI": "MT", "BDU": "MN", "BGI": "MB", "BKA": "MB", "BLI": "MN", "BNI": "MB",
    "BPH": "MN", "BRV": "MN", "BTH": "MN", "BTR": "MN", "CBA": "MB", "CMA": "MN", "CTH": "MN",
    "DBI": "MB", "DLA": "MT", "DNA": "MT", "DNI": "MN", "DNO": "MT", "DTH": "MN", "GLA": "MT",
    "HBI": "MB", "HCM": "MN", "HDU": "MB", "HGA": "MN", "HGI": "MB", "HNA": "MB", "HNO": "MB",
    "HPH": "MB", "HTI": "MB", "HYE": "MB", "KGI": "MN", "KHO": "MT", "KTU": "MT", "LAN": "MN",
    "LCA": "MB", "LCH": "MB", "LDO": "MT", "LSO": "MB", "NAN": "MB", "NBI": "MB", "NDI": "MB",
    "NTH": "MT", "PTH": "MB", "PYE": "MT", "QBI": "MT", "QNA": "MT", "QNG": "MT", "QNI": "MB",
    "QTI": "MT", "SLA": "MB", "STR": "MN", "TBI": "MB", "TGI": "MN", "THO": "MB", "TNG": "MB",
    "TNI": "MN", "TQU": "MB", "TTH": "MT", "TVI": "MN", "VLO": "MN", "VPH": "MB", "YBA": "MB",
}


def region_from_customer_code(customer_code):
    """Suy luan AreaCode (MB/MT/MN) tu tien to chu cai dau cua ma khach hang - tra None neu tien to
    khong nam trong bang da kiem chung (an toan hon la doan bua). CHI nen goi khi khach hang khong
    map duoc vung qua duong chinh (CityId/dms_khachhang)."""
    if not customer_code:
        return None
    m = re.match(r'^([A-Za-z]+)', str(customer_code))
    if not m:
        return None
    return CUSTOMER_CODE_PREFIX_TO_REGION.get(m.group(1).upper())
