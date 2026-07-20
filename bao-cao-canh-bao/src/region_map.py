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


def customer_keep_filter_sql(invoice_alias, channel, customer_alias='k'):
    """16/07/2026: hợp nhất logic "JOIN + điều kiện giữ lại khách mồ côi/loại mã rác" — trước đó
    lặp lại độc lập 4 lần (2 nhánh OTC/ETC x 2 hàm check_customer_churn_alert/
    check_revenue_concentration_alert trong src/alerts.py), rủi ro lệch dần theo thời gian nếu
    sửa 1 chỗ quên sửa chỗ kia (đúng lớp lỗi đã gặp — vd mốc tuổi nợ từng lệch giữa chatbot và
    alert vì sửa 1 nơi không sửa nơi kia).

    Trả (join_clause, keep_where) — LEFT JOIN sang đúng bảng khách hàng theo kênh + điều kiện GIỮ
    LẠI dòng hợp lệ (có hồ sơ khách hàng HOẶC tiền tố mã khớp tỉnh/thành đã biết trong
    CUSTOMER_CODE_PREFIX_TO_REGION) để loại mã rác (vd 'P000001'/'NCC*'/'1001136' — xác nhận thực
    tế 08/07/2026 không khớp bất kỳ khách hàng nào) mà KHÔNG mất khách hàng "mồ côi" thật.
    channel: 'OTC' -> dbo.DMS_KhachHang, 'ETC' -> dbo.DMSSX_KhachHang.

    Dùng:
        join_clause, keep_where = customer_keep_filter_sql('v', 'OTC')
        f"FROM dbo.vHoaDonTotal v {join_clause} WHERE {keep_where} AND ..."
    """
    kh_table = "dbo.DMS_KhachHang" if channel == "OTC" else "dbo.DMSSX_KhachHang"
    join_clause = f"LEFT JOIN {kh_table} {customer_alias} ON {invoice_alias}.CustomerCode = {customer_alias}.Code"
    keep_where = f"({customer_alias}.Code IS NOT NULL OR {customer_code_prefix_sql_or(f'{invoice_alias}.CustomerCode')})"
    return join_clause, keep_where


def customer_region_resolve_sql(invoice_alias, channel, customer_alias='k', city_alias='rt'):
    """16/07/2026: hợp nhất logic "JOIN + suy luận AreaCode" — trước đó chỉ có ở
    src/etl.py::_period_revenue (nhánh SQL, khi lọc theo vùng), nhưng cùng 1 dạng biểu thức CASE
    lẽ ra nên dùng chung với các chỗ suy luận vùng khác thay vì viết lại mỗi lần cần.

    Trả (join_clause, area_expr) — LEFT JOIN(s) + biểu thức CASE ưu tiên AreaCode qua CityId
    (DIM_TinhThanhPho), fallback tiền tố mã KH khi khách "mồ côi" (area_code NULL từ đường JOIN
    chính). channel='OTC': vHoaDonTotal không lộ sẵn CityId -> cần join thêm DMS_KhachHang trước
    khi join DIM_TinhThanhPho. channel='ETC': vHoaDonETCTotal đã lộ sẵn CityId -> join thẳng
    DIM_TinhThanhPho, không cần bảng khách hàng.

    Dùng:
        join_clause, area_expr = customer_region_resolve_sql('v', 'OTC')
        f"FROM dbo.vHoaDonTotal v {join_clause} WHERE {area_expr} IN :region_markers"
    """
    prefix_case = " ".join(
        f"WHEN {invoice_alias}.CustomerCode LIKE '{prefix}%' THEN '{area}'"
        for prefix, area in CUSTOMER_CODE_PREFIX_TO_REGION.items()
    )
    area_expr = f"COALESCE({city_alias}.AreaCode, CASE {prefix_case} ELSE NULL END)"
    if channel == "OTC":
        join_clause = (
            f"LEFT JOIN dbo.DMS_KhachHang {customer_alias} ON {invoice_alias}.CustomerCode = {customer_alias}.Code "
            f"LEFT JOIN dbo.DIM_TinhThanhPho {city_alias} ON {customer_alias}.CityId = {city_alias}.CityId"
        )
    else:
        join_clause = f"LEFT JOIN dbo.DIM_TinhThanhPho {city_alias} ON {invoice_alias}.CityId = {city_alias}.CityId"
    return join_clause, area_expr
