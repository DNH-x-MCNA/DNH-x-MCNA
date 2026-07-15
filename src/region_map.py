# -*- coding: utf-8 -*-
"""Nguồn chuẩn duy nhất cho mapping vùng miền (mã AreaCode Bravo <-> tên tiếng Việt).

Tách riêng khỏi ai_agent/chatbot.py (14/07/2026) — trước đó src/etl.py, src/alerts.py,
src/notifier.py đều import DNHChatbot._REGION_SQL_MARKERS/_REGION_NAMES_VI thẳng từ file chatbot,
khiến service báo cáo/cảnh báo (chạy nền trên máy 24, không liên quan gì tới chatbot) phụ thuộc
runtime vào 1 file vốn thuộc phần chatbot — nếu file đó bị xoá/thay thế (vd giao hẳn phần chatbot
cho người khác) thì service vỡ ngay vì mất nguồn mapping vùng miền này. ai_agent/chatbot.py giờ
import ngược lại từ đây để giữ nguyên hành vi nội bộ của nó.
"""

REGION_SQL_MARKERS = {"bac": ["MB", "MB2"], "nam": ["MN"], "trung": ["MT"]}  # mã miền, không quote — quote khi dùng
REGION_NAMES_VI = {"bac": "Miền Bắc", "nam": "Miền Nam", "trung": "Miền Trung"}

# 14/07/2026: bảng tra cứu VÙNG MIỀN theo TIỀN TỐ MÃ KHÁCH HÀNG (vd 'HCM13508' -> 'HCM' -> MN) —
# dùng làm fallback CHỈ khi khách hàng không map được vùng qua đường chính (JOIN DMS_KhachHang/
# BRV_KhachHang -> DIM_TinhThanhPho), ví dụ khách "mồ côi" không có hồ sơ trong bảng khách hàng
# (DMSId='0') như HCM13508 — phát hiện qua đối chiếu doanh thu OTC Miền Nam 2025 với số DNH báo,
# lệch đúng bằng khách này.
#
# Xây dựng bằng cách đối chiếu ~47.500 khách hàng ĐÃ xác định được vùng qua đường chính: với mỗi
# tiền tố chữ cái đầu mã khách hàng, kiểm tra khách hàng mang tiền tố đó rơi vào vùng nào nhiều
# nhất — CHỈ giữ lại tiền tố có độ thuần >=95% (ít nhất 95% khách mang tiền tố đó cùng 1 vùng) VÀ
# có ít nhất 5 khách hàng mẫu, để tránh tiền tố hiếm/mơ hồ. Đây rõ ràng là mã viết tắt tỉnh/thành
# (HCM=Hồ Chí Minh, HNO=Hà Nội, AGI=An Giang, DNI=Đồng Nai...) — quy ước đặt mã ổn định, không cần
# cập nhật thường xuyên trừ khi DNH đổi cách đặt mã khách hàng mới.
#
# CHỈ dùng để SUY LUẬN vùng cho khách KHÔNG map được qua đường chính — không bao giờ override vùng
# đã xác định đúng qua CityId/DMS_KhachHang (đường chính luôn ưu tiên, đáng tin hơn).
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
    """Suy luận AreaCode (MB/MT/MN) từ tiền tố chữ cái đầu của mã khách hàng — trả None nếu tiền tố
    không nằm trong bảng đã kiểm chứng (an toàn hơn là đoán bừa). CHỈ nên gọi khi khách hàng không
    map được vùng qua đường chính (CityId/DMS_KhachHang)."""
    import re
    if not customer_code:
        return None
    m = re.match(r'^([A-Za-z]+)', str(customer_code))
    if not m:
        return None
    return CUSTOMER_CODE_PREFIX_TO_REGION.get(m.group(1).upper())


def customer_code_prefix_sql_or(column_expr):
    """15/07/2026: trả về mảnh SQL "{column_expr} LIKE 'AGI%' OR {column_expr} LIKE 'BDI%' OR ..."
    liệt kê cả 63 tiền tố đã kiểm chứng — dùng làm ĐIỀU KIỆN GIỮ LẠI khách hàng "mồ côi" (không có
    hồ sơ trong DMS_KhachHang/DMSSX_KhachHang) khi phải LEFT JOIN thay vì JOIN thường trong các
    truy vấn Bravo (vd check_customer_churn_alert/check_revenue_concentration_alert).

    QUAN TRỌNG: các hàm này trước đó dùng JOIN thường (INNER) KHÔNG PHẢI chỉ vì lười — có lý do
    thật: bravo_hoadonhdr/brvsx_hoadonhdr chứa lẫn nhiều "CustomerCode" không phải khách hàng thật
    (mã nội bộ 'P000001', mã nhà cung cấp 'NCC*', mã chi phí 'I000001'...) — xác nhận thực tế mã
    '1001136' có 274 tỷ đồng/197 hóa đơn nhưng không khớp bất kỳ khách hàng nào. Đổi thẳng sang
    LEFT JOIN không lọc gì sẽ lộ lại đúng vấn đề đó. Cách đúng: LEFT JOIN (không mất khách mồ côi
    CÓ tiền tố tỉnh/thành hợp lệ, vd HCM13508) NHƯNG vẫn yêu cầu "có hồ sơ khách hàng HOẶC tiền tố
    mã khớp tỉnh/thành đã biết" — mã rác kiểu P000001/NCC*/1001136 không khớp tiền tố nào trong
    bảng nên vẫn bị loại đúng như trước, chỉ khách hàng thật bị "mồ côi" mới được giữ lại.

    Dùng: f"k.Code IS NOT NULL OR {customer_code_prefix_sql_or('v.CustomerCode')}" trong WHERE."""
    return " OR ".join(f"{column_expr} LIKE '{prefix}%'" for prefix in CUSTOMER_CODE_PREFIX_TO_REGION)
