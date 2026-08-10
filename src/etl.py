import os
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from src.database import get_db_engines, load_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'alerts_state.db')

# Ngưỡng % chỉ tiêu tháng để tính là "đạt" — LẤY THEO ĐÚNG CẤU HÌNH THẬT CỦA DNH.
#
# Lịch sử: ban đầu hardcode 1.0 (100%); 23/07/2026 đổi sang 0.80 cho khớp chatbot (chatbot đang dùng
# 80) — nhưng CẢ HAI đều là con số MCNA tự đặt, không có căn cứ nghiệp vụ.
#
# 23/07/2026 (cùng ngày, sau khi đọc mã nguồn SP tính lương): tìm được ngưỡng THẬT trong bảng cấu
# hình bậc thưởng `dbo.DIM_BacThuong` của Bravo — bảng mà chính `usp_SaleSalary_Calculation_Ver2`
# (thủ tục DNH dùng tính lương thật) đọc để quyết định tỷ lệ thưởng. Bậc đầu tiên có `Earn1 > 0`
# chính là mốc "bắt đầu được ghi nhận/được thưởng":
#     TDV                          -> 65%   (bậc: 65 / 75 / 85 / 95%)
#     QLV, CS, TP, PP, TBP, TK     -> 70%   (bậc: 70 / 80 / 90 / 100 / 120%)
# Đã kiểm chứng: giống nhau ở CẢ 3 miền MB/MT/MN (không có ngoại lệ theo vùng).
#
# LƯU Ý 1: bản chất DNH dùng BẬC THANG (càng vượt càng hưởng tỷ lệ cao), không phải ngưỡng nhị phân
# đạt/không đạt. Con số dưới đây chỉ là mốc SÀN để đếm "bao nhiêu người đạt" cho báo cáo tóm tắt —
# nếu sau này cần thể hiện đúng bậc thang thì phải đọc thẳng DIM_BacThuong, không dùng hằng số này.
# LƯU Ý 2: khi đọc con số giữa tháng, xem docstring get_digest_metrics — chỉ tiêu là CẢ THÁNG còn
# doanh số là lũy kế tới hiện tại, nên đầu tháng tỷ lệ đạt luôn gần 0 dù ngưỡng nào.
# 23/07/2026 (chiều): xác nhận thêm bằng VĂN BẢN GỐC, không chỉ suy từ DIM_BacThuong nữa —
# QĐ 0429-1 (MB) phụ lục 02, QĐ 0429-2 (MN), QĐ 0429-3 (MT), đều có chữ ký, đều chặn dưới 70% cho
# QLV. TDV thì đã chuyển sang QĐ 0107/2026 (hiệu lực 01/07/2026) nên chặn dưới 65%.
# ⚠️⚠️⚠️ 27/07/2026 — XÁC NHẬN VỚI DNH: có BA MỐC KHÁC NHAU, TUYỆT ĐỐI KHÔNG GỘP:
#   >= 100%  ĐẠT CHỈ TIÊU   — làm đủ chỉ tiêu tháng được giao (nghĩa đen).
#   >=  80%  ĐẠT KPI        — mốc đánh giá HIỆU QUẢ CÔNG VIỆC, ÁP DỤNG CHUNG cho MỌI vai trò.
#   >=65/70% TỚI MỨC THƯỞNG — CỔNG bắt đầu được tính THƯỞNG NHÓM HÀNG (DM1/DM2/DM3), theo
#                             DIM_BacThuong: TDV 65% (QĐ 0107/2026), quản lý 70% (QĐ 0429/.25).
# Lỗi từng mắc: 65/70 bị đặt tên KPI_ACHIEVED_* và gọi là "đạt KPI", khiến người đạt 67% bị báo là
# "đã đạt KPI" trong khi thực tế mới qua cổng thưởng, CHƯA đạt KPI (80%). Nay tách hẳn tên gọi.
BONUS_THRESHOLD_TDV = 0.65          # Trình dược viên — cổng thưởng nhóm hàng
BONUS_THRESHOLD_MGR = 0.70          # QLV và các vai trò quản lý/kênh khác — cổng thưởng
KPI_ACHIEVED_THRESHOLD = 0.80       # ĐẠT KPI — chung cho mọi vai trò
KPI_FULL_TARGET = 1.00              # ĐẠT CHỈ TIÊU đúng nghĩa đen


def bonus_threshold_for(position_code):
    """Ngưỡng TỚI MỨC THƯỞNG NHÓM HÀNG theo VAI TRÒ (tỷ lệ, không phải %). TDV 0.65, vai trò khác
    0.70. KHÔNG PHẢI ngưỡng "đạt KPI" — đạt KPI là 0.80 chung cho mọi vai trò (KPI_ACHIEVED_THRESHOLD).

    Dùng hàm này thay vì gọi thẳng hằng số ở bất kỳ chỗ nào đếm/phân loại "tới mức thưởng hay chưa".
    Lý do có hàm: bên chatbot (D:\\DNH-x-MCNA) từng khai báo đủ 2 hằng số nhưng KHÔNG gọi tới hằng số
    quản lý ở đâu cả, nên mọi vai trò đều bị chấm ở 65% — một QLV đạt 67% được gắn nhãn "đã đạt"
    trong khi theo QĐ 0429 họ hưởng 0% thưởng danh mục. Phát hiện 23/07/2026.

    position_code rỗng/None -> ngưỡng TDV: giữ nguyên hành vi cũ, và không gắn nhãn "chưa tới mức
    thưởng" cho người thật chỉ vì thiếu dữ liệu vai trò."""
    if position_code and str(position_code).strip().upper() != 'TDV':
        return BONUS_THRESHOLD_MGR
    return BONUS_THRESHOLD_TDV

def get_low_inventory(erp_engine, limit):
    """
    Trích xuất các sản phẩm có tồn kho thấp dưới ngưỡng limit
    """
    query = """
        SELECT sku, item_name, quantity, updated_at
        FROM inventory
        WHERE quantity < :limit
    """
    # Sử dụng pandas.read_sql với parameter bind
    df = pd.read_sql(query, erp_engine, params={"limit": limit})
    return df

def get_recent_failed_orders(erp_engine, lookback_hours):
    """
    Trích xuất danh sách và số lượng đơn hàng lỗi trong khoảng thời gian lookback
    """
    lookback_time = datetime.now() - timedelta(hours=lookback_hours)

    # Do SQLite và SQL Server có cú pháp so sánh ngày khác nhau,
    # ta có thể dùng định dạng ISO string hoặc parameter binding chuẩn để SQLAlchemy xử lý
    query = """
        SELECT id, customer_id, amount, order_date, status
        FROM orders
        WHERE status = 'Failed' AND order_date >= :lookback_time
    """
    df = pd.read_sql(query, erp_engine, params={"lookback_time": lookback_time})
    return df

def get_unresolved_urgent_tickets(crm_engine):
    """
    Trích xuất danh sách support ticket ưu tiên Urgent chưa giải quyết
    """
    query = """
        SELECT id, customer_id, priority, status, created_at
        FROM support_tickets
        WHERE priority = 'Urgent' AND status = 'Open'
    """
    df = pd.read_sql(query, crm_engine)
    return df

def _region_markers(region):
    """region: None hoặc 'bac'/'nam'/'trung' -> danh sách mã AreaCode tương ứng, dùng chung quy
    ước với src/region_map.py::REGION_SQL_MARKERS (nguồn chuẩn duy nhất cho mapping vùng/mã)."""
    if not region:
        return None
    from src.region_map import REGION_SQL_MARKERS
    return REGION_SQL_MARKERS.get(region)

def _region_label(area_code):
    """Map area_code thô sang tên miền tiếng Việt — bản sao gọn của
    src/alerts.py::normalize_region_label, tách riêng để tránh vòng lặp import (alerts.py đã
    import từ etl.py). Cả 2 đều đọc từ cùng 1 nguồn src/region_map.py::REGION_SQL_MARKERS/REGION_NAMES_VI."""
    if not area_code:
        return "Không rõ"
    from src.region_map import REGION_SQL_MARKERS, REGION_NAMES_VI
    val = str(area_code).strip().upper()
    for region_key, markers in REGION_SQL_MARKERS.items():
        if val in markers:
            return REGION_NAMES_VI[region_key]
    return str(area_code)

def _latest_period_key(period):
    """Sort key cho receivable_detail.period (text 'M_YYYY', không đệm số 0).

    So sánh chuỗi thuần là sai ở đây: '9_2025' > '1_2026' theo thứ tự chữ (tháng '9' thắng mọi
    tháng bắt đầu bằng '1'), nên 1 câu SQL MAX(period) đơn giản sẽ âm thầm chọn nhầm kỳ cũ mỗi khi
    kỳ mới nhất bắt đầu bằng số 1.

    14/07/2026: chuyển từ ai_agent/chatbot.py sang đây — src/alerts.py trước đó import thẳng hàm
    này từ file chatbot, khiến service báo cáo/cảnh báo phụ thuộc runtime vào 1 file thuộc phần
    chatbot."""
    try:
        month_str, year_str = str(period).split('_')
        return (int(year_str), int(month_str))
    except (ValueError, AttributeError):
        return (0, 0)

def _period_revenue(start_dt, end_dt, region=None):
    """Doanh thu OTC+ETC thuần trong [start_dt, end_dt). region: None (không lọc) hoặc
    'bac'/'nam'/'trung' — lọc theo AreaCode qua CityId -> DIM_TinhThanhPho.
    Trả (otc_rev, etc_rev, otc_invoice_count, etc_invoice_count) — tách riêng số hóa đơn từng
    kênh (13/07/2026, trước đó gộp chung 1 số duy nhất, không rõ ràng khi xem báo cáo).

    14/07/2026: đổi hẳn sang query THẲNG 2 view gốc Bravo (dbo.vHoaDonTotal cho OTC,
    dbo.vHoaDonETCTotal cho ETC) thay vì tự ráp lại logic từ bảng thô — xác nhận thực tế:
    công thức tự ráp trước đó (JOIN brv_hoadonct/brv_hoadonhdr + loại CTKM/hủy) lệch ETC ~4%/ngày
    so với 2 view này, vì view gốc còn TRỪ hàng trả lại (BRVSX_TraLai), lọc theo trạng thái đã ghi
    thẻ kho (Post_TheKho=1), loại thêm 1 số mã khách hàng cụ thể, và CỘNG THÊM nhóm chứng từ "HC"
    (đọc từ BRV_HoaDonHCCt/BRVSX_HoaDonHCCt — 2 bảng CHƯA được đồng bộ sang Supabase) cùng ~10
    trường hợp đặc biệt hardcode theo mã khách hàng — quá phức tạp và rủi ro để tự dịch lại đúng
    100%, nên dùng thẳng view đã được xác nhận là nguồn đúng của DNH.

    HỆ QUẢ: bỏ hẳn failover Postgres/Supabase cho hàm này — 2 view trên CHỈ tồn tại ở Bravo, không
    có bản tương đương bên Supabase. Nếu Bravo mất kết nối, hàm raise lỗi (không âm thầm trả số
    liệu Postgres cũ/gần đúng) — ưu tiên "báo lỗi rõ ràng" hơn "hiện số có thể sai" cho con số quan
    trọng nhất của mọi báo cáo. Các hàm gọi _period_revenue nên tự try/except nếu cần chạy tiếp dù
    thiếu doanh thu (đã áp dụng ở get_digest_metrics/_revenue_trend qua đường try/except sẵn có).

    14/07/2026: khi có lọc vùng (region), đổi JOIN -> LEFT JOIN + COALESCE với CASE suy luận vùng
    theo tiền tố mã khách hàng (src/region_map.py::CUSTOMER_CODE_PREFIX_TO_REGION) — cùng lý do với
    _revenue_by_region: khách "mồ côi" (không có hồ sơ trong DMS_KhachHang, vd HCM13508) bị INNER
    JOIN loại thẳng khỏi doanh thu theo vùng, gây thiếu số thật (xác nhận: HCM13508 riêng năm 2024
    đã thiếu 762.287.986đ khỏi doanh thu OTC Miền Nam). Xây CASE trong SQL (thay vì lọc ở Python)
    để giữ hiệu năng — hàm này gọi rất thường xuyên (digest hàng ngày, vòng lặp trend nhiều ngày).
    """
    from sqlalchemy import text, bindparam
    from src.database import _get_bravo_engine
    from src.region_map import customer_region_resolve_sql

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError(
            "Chưa cấu hình BRAVO_SQL_* trong .env — không còn nguồn nào khác cho doanh thu "
            "(đã bỏ failover Postgres, xem docstring _period_revenue)."
        )

    markers = _region_markers(region)
    params = {"start_dt": start_dt, "end_dt": end_dt}
    # OTC (vHoaDonTotal) KHÔNG lộ sẵn CityId trong cột output -> join thêm qua CustomerCode.
    # ETC (vHoaDonETCTotal) ĐÃ lộ sẵn CityId -> join thẳng DIM_TinhThanhPho, không cần thêm bảng.
    # 16/07/2026: JOIN + biểu thức CASE suy luận vùng chuyển sang customer_region_resolve_sql()
    # dùng chung (src/region_map.py) — trước đó viết inline riêng ở đây, cùng dạng logic với
    # check_customer_churn_alert/check_revenue_concentration_alert (src/alerts.py) nhưng khác biến
    # thể, dễ lệch nếu sửa 1 chỗ quên chỗ kia.
    otc_region_join, etc_region_join, otc_where, etc_where = "", "", "", ""
    if markers:
        otc_region_join, otc_area_expr = customer_region_resolve_sql("v", "OTC")
        etc_region_join, etc_area_expr = customer_region_resolve_sql("v", "ETC")
        otc_where = f" AND {otc_area_expr} IN :region_markers"
        etc_where = f" AND {etc_area_expr} IN :region_markers"
        params["region_markers"] = tuple(markers)

    otc_sql = text(f'''
        SELECT COALESCE(SUM(v.Amount9), 0), COUNT(DISTINCT v.Stt)
        FROM dbo.vHoaDonTotal v
        {otc_region_join}
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        {otc_where}
    ''')
    etc_sql = text(f'''
        SELECT COALESCE(SUM(v.Amount9), 0), COUNT(DISTINCT v.Stt)
        FROM dbo.vHoaDonETCTotal v
        {etc_region_join}
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        {etc_where}
    ''')
    if markers:
        otc_sql = otc_sql.bindparams(bindparam("region_markers", expanding=True))
        etc_sql = etc_sql.bindparams(bindparam("region_markers", expanding=True))

    with engine.connect() as conn:
        otc_row = conn.execute(otc_sql, params).fetchone()
        etc_row = conn.execute(etc_sql, params).fetchone()

    return float(otc_row[0]), float(etc_row[0]), int(otc_row[1]), int(etc_row[1])


def _revenue_by_region(start_dt, end_dt, channel=None):
    """Breakdown doanh thu theo VÙNG (Bắc/Nam/Trung) trong [start_dt, end_dt) — chỉ gọi cho
    weekly/monthly (không tính hàng ngày, tốn thêm query join). channel=None -> cả 2 kênh.

    14/07/2026: đổi sang query view gốc Bravo (vHoaDonTotal/vHoaDonETCTotal), cùng lý do và cách
    làm với _period_revenue — công thức tự ráp cũ (JOIN bảng thô + loại CTKM/hủy) dùng chung
    logic với _period_revenue nên chắc chắn dính đúng lỗi tương tự (thiếu trừ hàng trả lại...).
    Không còn failover Postgres (view chỉ có ở Bravo, xem docstring _period_revenue).

    14/07/2026: đổi JOIN -> LEFT JOIN — xác nhận thực tế có khách hàng phát sinh hóa đơn nhưng
    KHÔNG tồn tại trong DMS_KhachHang/BRV_KhachHang (DMSId='0', dữ liệu "mồ côi" phía DNH, vd
    HCM13508 — lệch đúng 3.962.720đ so với số DNH báo cho OTC Miền Nam 2025). Dùng JOIN thường sẽ
    ÂM THẦM LOẠI các khách này khỏi breakdown vùng (không có dòng "Không rõ" nào xuất hiện, tổng
    breakdown thấp hơn tổng doanh thu thật) — LEFT JOIN đảm bảo khoản này luôn được tính vào, không
    mất khỏi tổng.

    14/07/2026 (tiếp): với khách "mồ côi" (area_code NULL từ đường JOIN chính), thử suy luận vùng
    qua tiền tố mã khách hàng (src/region_map.py::region_from_customer_code — vd 'HCM13508' -> MN,
    đã kiểm chứng khớp 100% với số DNH báo cho trường hợp HCM13508). Chỉ khách nào tiền tố KHÔNG
    nằm trong bảng đã kiểm chứng mới thực sự rơi vào "Không rõ" — nhờ vậy GROUP BY phải chuyển từ
    theo AreaCode (gộp sẵn trong SQL) sang theo CustomerCode (gộp ở Python sau khi suy luận vùng),
    tốn thêm 1 chút nhưng vẫn nhẹ vì hàm này chỉ gọi cho weekly/monthly."""
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    from src.region_map import region_from_customer_code, customer_region_resolve_sql

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError(
            "Chưa cấu hình BRAVO_SQL_* trong .env — không còn nguồn nào khác cho breakdown vùng."
        )

    # 16/07/2026: JOIN clause dùng chung customer_region_resolve_sql() (src/region_map.py) —
    # chỉ lấy phần join_clause, KHÔNG dùng area_expr (hàm này vẫn tự suy luận vùng ở PYTHON qua
    # region_from_customer_code() như cũ, không đổi — group theo customer_code trước rồi mới suy
    # luận, giữ nguyên hành vi/độ chính xác đã kiểm chứng, chỉ hợp nhất phần JOIN bị lặp).
    otc_join, _ = customer_region_resolve_sql("v", "OTC")
    etc_join, _ = customer_region_resolve_sql("v", "ETC")
    parts = []
    if channel is None or channel == "OTC":
        parts.append(f'''
            SELECT v.CustomerCode AS customer_code, rt.AreaCode AS area_code, SUM(v.Amount9) AS rev
            FROM dbo.vHoaDonTotal v
            {otc_join}
            WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
            GROUP BY v.CustomerCode, rt.AreaCode
        ''')
    if channel is None or channel == "ETC":
        parts.append(f'''
            SELECT v.CustomerCode AS customer_code, rt.AreaCode AS area_code, SUM(v.Amount9) AS rev
            FROM dbo.vHoaDonETCTotal v
            {etc_join}
            WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
            GROUP BY v.CustomerCode, rt.AreaCode
        ''')
    if not parts:
        return []
    union_sql = text(f'''
        SELECT customer_code, area_code, SUM(rev) AS rev FROM ({" UNION ALL ".join(parts)}) x
        GROUP BY customer_code, area_code
    ''')
    try:
        with engine.connect() as conn:
            raw_rows = conn.execute(union_sql, {"start_dt": start_dt, "end_dt": end_dt}).fetchall()
    except Exception as e:
        print(f"[DIGEST] Lỗi truy vấn breakdown vùng: {e}")
        return []

    agg = {}
    for r in raw_rows:
        area = r.area_code or region_from_customer_code(r.customer_code)
        agg[area] = agg.get(area, 0.0) + float(r.rev or 0)
    return [{"region": _region_label(area), "revenue": round(rev, 2)}
            for area, rev in sorted(agg.items(), key=lambda x: -x[1])]


def _revenue_trend(start_dt, end_dt, granularity, region=None, channel=None):
    """Xu hướng doanh thu trong kỳ: 'weekly' -> theo TỪNG NGÀY (7 điểm), 'monthly' -> theo TỪNG
    TUẦN (4-5 điểm). Chạy thêm N truy vấn _period_revenue nhỏ — chấp nhận được vì weekly/monthly
    chỉ chạy 1 lần/tuần hoặc 1 lần/tháng (không nằm trong luồng cảnh báo tần suất cao 5 lần/ngày).

    13/07/2026: kẹp end_dt tại hết hôm nay — get_weekly/monthly_digest_metrics giờ dùng kỳ ĐANG
    CHẠY (chưa hết), nếu không kẹp thì vòng lặp bucket vẽ cả các ngày TƯƠNG LAI (không có dữ liệu,
    toàn số 0), khiến biểu đồ rối/vô nghĩa (vd gửi thứ 2 mà vẽ luôn cả thứ 3 - chủ nhật trống).

    14/07/2026: `channel` trước đó nhận vào nhưng KHÔNG được dùng — mọi điểm trend đều cộng CẢ
    OTC+ETC bất kể channel gì, trong khi phần "Tổng Doanh Thu" chính (get_digest_metrics) đã ép
    đúng kênh được lọc. Hậu quả: audience chỉ được cấp quyền xem 1 kênh (vd "Quản lý Kênh OTC")
    thấy đúng Tổng Doanh Thu (chỉ OTC) nhưng bảng Xu Hướng bên dưới lại lộ cả doanh thu ETC — vừa
    sai số liệu vừa lộ dữ liệu ngoài phạm vi audience được cấp. Sửa: ép về 0 đúng kênh không được
    chọn, khớp với cách get_digest_metrics đã làm cho phần tổng."""
    today_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = min(end_dt, today_end)
    buckets = []
    if granularity == "weekly":
        cur = start_dt
        while cur < end_dt:
            nxt = cur + timedelta(days=1)
            buckets.append((cur, nxt, cur.strftime("%a %d/%m")))
            cur = nxt
    elif granularity == "monthly":
        # 16/07/2026: chia theo TUẦN LỊCH thật (căn Thứ 2 - Chủ Nhật), KHÔNG phải "7 ngày kể từ
        # mùng 1" như trước (01-07/08-14/... — không khớp tuần thật, gây khó đối chiếu với báo cáo
        # Tuần). Tuần đầu/cuối tháng cắt theo biên tháng (partial). Ví dụ tháng 7/2026 (mùng 1 rơi
        # Thứ 4): 01-05/07 (Thứ 4-CN), 06-12/07, 13-19/07... — trùng đúng kỳ báo cáo Tuần.
        cur = start_dt
        while cur < end_dt:
            days_to_next_monday = 7 - cur.weekday()  # weekday(): Thứ 2 = 0 ... Chủ nhật = 6
            nxt = min(cur + timedelta(days=days_to_next_monday), end_dt)
            buckets.append((cur, nxt, f"{cur.strftime('%d/%m')}-{(nxt - timedelta(days=1)).strftime('%d/%m')}"))
            cur = nxt
    else:
        return []

    trend = []
    for b_start, b_end, label in buckets:
        otc_rev, etc_rev, _, _ = _period_revenue(b_start, b_end, region=region)
        if channel == "OTC":
            etc_rev = 0.0
        elif channel == "ETC":
            otc_rev = 0.0
        trend.append({
            "label": label,
            "revenue": round(otc_rev + etc_rev, 2),
            "otc": round(otc_rev, 2),
            "etc": round(etc_rev, 2)
        })
    return trend


# Tên tiếng Việt + kiểu định dạng giá trị cho từng loại alert_key (prefix trước dấu ":" đầu
# tiên) — dùng để "dịch" các dòng "Điểm Nổi Bật Trong Kỳ" từ key/số thô sang câu chữ đọc được.
# Kiểu giá trị: money (tiền VNĐ) | ratio/percent (0-1 -> %) | qty (số lượng) | count (số nguyên)
# | hours (giờ) | customer (mã khách hàng) | status (chuỗi trạng thái) | raw (giữ nguyên).
_HIGHLIGHT_LABELS = {
    "low_inventory": ("Tồn kho thấp", "qty"),
    "failed_orders_peak": ("Đơn hàng lỗi/hủy tăng đột biến", "count"),
    "crm_urgent_overload": ("Ticket CRM khẩn cấp quá tải", "count"),
    "smart_debt_overdue_top5": ("Top 5 khách nợ quá hạn cao nhất", "money"),
    "smart_inventory_depletion_top5": ("Top 5 mặt hàng sắp cạn kho", "qty"),
    "smart_kpi_low_progress_top5": ("Top 5 KPI tiến độ thấp nhất", "ratio"),
    "sales_kpi_insights_report": ("Báo cáo phân tích KPI doanh số đã gửi", "status"),
    "revenue_drop": ("Doanh thu sụt giảm bất thường", "ratio"),
    "credit_limit_exceeded_top10": ("Top 10 khách vượt hạn mức tín dụng", "money"),
    "company_overdue_ratio": ("Tỷ lệ nợ quá hạn toàn công ty", "percent"),
    "overdue_customer_new_orders": ("Khách quá hạn vẫn phát sinh đơn mới (tổng giá trị đơn)", "money"),
    "aging_migration_gt45": ("Nợ mới chuyển nhóm quá hạn > 45 ngày", "money"),
    "dead_stock_top10": ("Top 10 tồn kho chết (giá trị)", "money"),
    "customer_churn": ("Khách hàng lớn sụt giảm/rời bỏ", "customer"),
    "revenue_concentration": ("Rủi ro tập trung doanh thu", "percent"),
    "etc_return_rate": ("Tỷ lệ hàng trả về ETC cao", "percent"),
    "zero_sales_rep": ("Số nhân sự có doanh số bằng 0", "count"),
    "kpi_sales_force_risk": ("Số nhân sự rủi ro KPI", "count"),
    "kpi_daily_pace_red": ("Số TDV có nhịp KPI ngày mức Đỏ", "count"),
    "kpi_milestone_channel": ("Mốc KPI kênh giảm so TB 5 tháng trước", "percent"),
    "kpi_milestone_tdv": ("Số TDV giảm KPI so TB 5 tháng trước", "count"),
    "data_sanity_zero": ("Dữ liệu rỗng/bất thường — đã chặn cảnh báo", "status"),
    "etl_stale": ("ETL nghi đứng (dữ liệu không mới)", "hours"),
    "kpi_revenue_reconciliation": ("Doanh thu KPI lệch so với hóa đơn thực tế (OTC)", "money"),
}

# 16/07/2026: các prefix KHÔNG nên vào "Điểm Nổi Bật Trong Kỳ" dù có trong _HIGHLIGHT_LABELS —
# data_sanity_zero/etl_stale là cảnh báo SỨC KHỎE HỆ THỐNG (guard kỹ thuật), không phải vấn đề
# nghiệp vụ; sales_kpi_insights_report chỉ là thông báo "đã gửi báo cáo định kỳ" (status luôn
# "Đã gửi"), không phản ánh bất thường gì — liệt kê chung với các cảnh báo thật (nợ quá hạn, khách
# rời bỏ...) sẽ làm loãng phần nội dung thực sự đáng chú ý.
_HIGHLIGHT_EXCLUDE_PREFIXES = {"data_sanity_zero", "etl_stale", "sales_kpi_insights_report"}

def _highlight_matches_channel(alert_key, channel):
    """17/07/2026: True nếu highlight này nên hiện cho audience đang lọc theo `channel` (None =
    không giới hạn kênh, C-Level/Toàn quốc — luôn hiện tất cả). Phát hiện qua báo cáo Daily Digest
    "Quản lý Kênh OTC" vẫn hiện cảnh báo ETC thật (khách rời bỏ, nợ quá hạn...) — get_digest_metrics
    đã lọc đúng channel cho doanh thu/công nợ/tồn kho, nhưng _get_period_highlights đọc thẳng
    sent_alerts KHÔNG biết gì về scope audience.

    Các alert_key có gắn kênh đều dùng đúng 1 quy ước: segment sau dấu ':' là literal 'OTC'/'ETC'
    (vd 'company_overdue_ratio:ETC:2026-07-16', 'customer_churn:OTC') — xem revenue_drop/
    company_overdue_ratio/overdue_customer_new_orders/customer_churn/revenue_concentration/
    kpi_milestone_channel trong src/alerts.py, tất cả dùng channel_label='OTC'/'ETC' y hệt. Alert
    KHÔNG gắn kênh nào (vd kpi_daily_pace_red, smart_debt_overdue_top5 — vốn đã gộp cả 2 kênh) thì
    luôn hiện cho mọi audience kênh, không có gì để lọc."""
    if channel is None:
        return True
    if alert_key.startswith("sales_kpi_insights_report_"):
        return True
    segments = alert_key.split(":")[1:]
    if "OTC" in segments:
        return channel == "OTC"
    if "ETC" in segments:
        return channel == "ETC"
    return True

def _highlight_matches_region(region, alert_region):
    """17/07/2026: True nếu highlight này nên hiện cho audience đã lọc theo `region` (None = không
    giới hạn vùng, C-Level/Toàn quốc — luôn hiện tất cả). Phát hiện qua Daily Digest "Quản lý Miền
    Trung" 17/07/2026 vẫn hiện thẳng mã khách hàng NGOÀI vùng (HNA00274, HCM04298) từ cảnh báo
    customer_churn.

    21/07/2026: TRƯỚC ĐÂY bảng sent_alerts không lưu vùng của alert đã fire, nên hàm này fail-closed
    TRIỆT ĐỂ (ẩn HẲN mọi highlight khỏi báo cáo theo vùng, bất kể alert nào — kể cả loại THẬT SỰ có
    tính vùng như zero_sales_rep/kpi_daily_pace_red/kpi_milestone_tdv). Phát hiện qua báo cáo Weekly
    "Quản lý Miền Nam" 13-19/07/2026: mục "Điểm Nổi Bật" trống dù tuần đó có cảnh báo thật liên quan
    Miền Nam. Giờ record_alert_sent(..., region=...) đã ghi lại vùng THẬT (CHỈ khi alert quy được về
    đúng 1 vùng cụ thể — xem docstring record_alert_sent trong src/alerts.py; alert gộp nhiều vùng/
    toàn công ty vẫn ghi "Toàn quốc"/"Nhiều miền"/None), nên so khớp trực tiếp `alert_region` với tên
    Việt hoá của `region` — vẫn giữ đúng tinh thần fail-closed cũ (KHÔNG chắc chắn -> ẩn), chỉ khác
    là giờ hiện ĐÚNG khi thật sự xác định được, thay vì luôn luôn ẩn."""
    if region is None:
        return True
    from src.region_map import REGION_NAMES_VI
    return alert_region == REGION_NAMES_VI.get(region)

def _company_wide_alert_visible_to(region, alert_region):
    """1.4d Hàm mới _company_wide_alert_visible_to() — audience cấp vùng thấy tiêu đề + số tổng của alert toàn quốc."""
    if region is None:
        return True
    if alert_region in (None, "Toàn quốc", "Nhiều miền"):
        return True
    from src.region_map import REGION_NAMES_VI
    return alert_region == REGION_NAMES_VI.get(region)

def _format_highlight_date_part(part):
    """Nếu 1 mảnh suffix của alert_key là ngày/tháng (YYYY-MM-DD, YYYY-MM, hoặc "M_YYYY" — định
    dạng period dùng ở receivable_detail/check_debt_aging_migration_alert), đổi sang định dạng
    Việt Nam (DD/MM/YYYY hoặc MM/YYYY) — các mảnh khác (mã kênh OTC/ETC, SKU...) giữ nguyên."""
    for fmt_in, fmt_out in (("%Y-%m-%d", "%d/%m/%Y"), ("%Y-%m", "%m/%Y")):
        try:
            return datetime.strptime(part, fmt_in).strftime(fmt_out)
        except ValueError:
            continue
    if "_" in part:
        month_str, _, year_str = part.partition("_")
        if month_str.isdigit() and year_str.isdigit() and len(year_str) == 4:
            return f"{int(month_str):02d}/{year_str}"
    return part

def _is_date_like_segment(part):
    """True nếu 1 mảnh suffix của alert_key là ngày/tháng nhận dạng được (xem
    _format_highlight_date_part) — dùng để loại các mảnh NGÀY khỏi khóa gộp nhóm trong
    _get_period_highlights, để "Tỷ lệ nợ quá hạn... (OTC, 11/07)" và "...(OTC, 12/07)" được coi
    là CÙNG 1 loại cảnh báo (chỉ khác ngày) thay vì liệt kê riêng từng ngày."""
    for fmt_in in ("%Y-%m-%d", "%Y-%m"):
        try:
            datetime.strptime(part, fmt_in)
            return True
        except ValueError:
            continue
    if "_" in part:
        month_str, _, year_str = part.partition("_")
        if month_str.isdigit() and year_str.isdigit() and len(year_str) == 4:
            return True
    return False

def _highlight_group_key(alert_key):
    """Khóa gộp nhóm cho 1 alert_key — bỏ các mảnh NGÀY (xem _is_date_like_segment), giữ lại
    prefix + các mảnh khác (kênh OTC/ETC, mã SKU...). 2 alert_key cùng khóa gộp -> coi là CÙNG
    1 loại cảnh báo lặp lại theo ngày, chỉ giữ lần gần nhất (xem _get_period_highlights)."""
    if alert_key.startswith("sales_kpi_insights_report_"):
        return "sales_kpi_insights_report"
    segments = alert_key.split(":")
    prefix, parts = segments[0], segments[1:]
    kept = [p for p in parts if not _is_date_like_segment(p)]
    return ":".join([prefix] + kept)

def _format_highlight_value(value, value_type):
    try:
        if value_type == "money":
            from src.alerts import format_vietnamese_money
            return format_vietnamese_money(float(value))
        if value_type in ("ratio", "percent"):
            return f"{float(value) * 100:.1f}%"
        if value_type == "qty":
            return f"{float(value):,.0f}".replace(",", ".")
        if value_type == "count":
            return f"{int(float(value)):,}".replace(",", ".")
        if value_type == "hours":
            return f"{int(float(value))} giờ"
        if value_type == "customer":
            return f"Mã KH {value}"
        if value_type == "status":
            return {"sent": "Đã gửi", "zero": "Không phát hiện bất thường"}.get(str(value), str(value))
    except (ValueError, TypeError):
        pass
    return str(value)

def _humanize_highlight(alert_key, sent_at, value):
    """Dịch 1 dòng sent_alerts thô (alert_key/sent_at/value) sang câu chữ đọc được cho email —
    xem _HIGHLIGHT_LABELS. Trước 13/07/2026, "Điểm Nổi Bật Trong Kỳ" hiển thị thẳng alert_key kỹ
    thuật (vd "smart_debt_overdue_top5") và timestamp/số thô, không ai đọc hiểu được."""
    # sales_kpi_insights_report nối kỳ báo cáo bằng "_" (không phải ":" như các key khác)
    if alert_key.startswith("sales_kpi_insights_report_"):
        prefix = "sales_kpi_insights_report"
        parts = [alert_key[len("sales_kpi_insights_report_"):]]
    else:
        segments = alert_key.split(":")
        prefix, parts = segments[0], segments[1:]

    label, value_type = _HIGHLIGHT_LABELS.get(prefix, (prefix, "raw"))
    formatted_parts = [_format_highlight_date_part(p) for p in parts]
    suffix = f" ({', '.join(formatted_parts)})" if formatted_parts else ""

    try:
        sent_at_display = datetime.strptime(str(sent_at).split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%H:%M %d/%m/%Y")
    except ValueError:
        sent_at_display = str(sent_at)

    return {
        "label": label + suffix,
        "sent_at_display": sent_at_display,
        "value_display": _format_highlight_value(value, value_type),
    }

_HIGHLIGHTS_MAX_ROWS = 15  # xem _get_period_highlights — trần số dòng hiển thị sau khi đã gộp nhóm

def _get_period_warning_alerts(start_dt, end_dt, region=None):
    """1.4c Hàm mới _get_period_warning_alerts() — đọc alert_severity_log, GROUP BY alert_name, COUNT(*)"""
    if not os.path.exists(STATE_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT alert_name, region, COUNT(*) FROM alert_severity_log "
            "WHERE severity = 'WARNING' AND sent_at >= ? AND sent_at < ? "
            "GROUP BY alert_name, region",
            (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"[DIGEST] Lỗi đọc warning từ alerts_state.db: {e}")
        return []

    results = []
    seen = set()
    for alert_name, alert_region, count in rows:
        if alert_name in seen:
            continue
            
        excluded = False
        for prefix in _HIGHLIGHT_EXCLUDE_PREFIXES:
            label = _HIGHLIGHT_LABELS.get(prefix, (prefix, ""))[0]
            if label.lower() in alert_name.lower() or prefix.lower() in alert_name.lower():
                excluded = True
                break
            if prefix == "data_sanity_zero" and "DỮ LIỆU BẤT THƯỜNG" in alert_name.upper():
                excluded = True
            if prefix == "etl_stale" and "ETL" in alert_name.upper():
                excluded = True
            if prefix == "sales_kpi_insights_report" and "BÁO CÁO PHÂN TÍCH" in alert_name.upper():
                excluded = True
        
        if excluded:
            continue
            
        if not _company_wide_alert_visible_to(region, alert_region):
            continue
            
        seen.add(alert_name)
        results.append({
            "label": alert_name,
            "value_display": f"đã lặp {_format_highlight_value(count, 'count')} lần hôm nay"
        })
    return results

def _get_period_highlights(start_dt, end_dt, channel=None, region=None):
    """"Điểm nổi bật trong kỳ": các cảnh báo nghiệp vụ đã THỰC SỰ fire trong [start_dt, end_dt),
    đọc từ data/alerts_state.db (bảng sent_alerts, ghi bởi src/alerts.py::record_alert_sent) —
    nối luồng cảnh báo thời gian thực với báo cáo định kỳ thành 1 câu chuyện liền mạch. Mỗi dòng
    được "dịch" qua _humanize_highlight() sang tên tiếng Việt + giá trị định dạng đúng kiểu.

    14/07/2026: gộp theo _highlight_group_key() (bỏ mảnh NGÀY khỏi alert_key) — trước đó các cảnh
    báo lặp lại theo ngày (vd "Tỷ lệ nợ quá hạn... (OTC)" tự bắn mỗi sáng) liệt kê riêng TỪNG NGÀY
    trong kỳ báo cáo Monthly, có thể ra 40-50 dòng cho 1 kỳ — chỉ giữ lần gần nhất mỗi nhóm, rồi
    giới hạn tối đa _HIGHLIGHTS_MAX_ROWS dòng (ưu tiên mới nhất, đã ORDER BY last_sent_at DESC).

    17/07/2026: thêm `channel` — lọc bỏ highlight thuộc kênh KHÁC audience đang xem (xem
    _highlight_matches_channel). channel=None giữ nguyên hành vi cũ (không lọc gì, dùng cho
    audience C-Level/Toàn quốc). Thêm `region` cùng đợt — lọc bỏ highlight LỘ DANH TÍNH khách hàng
    cụ thể khi audience đã scope theo vùng (xem _highlight_matches_region)."""
    if not os.path.exists(STATE_DB_PATH):
        return []
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT alert_key, last_sent_at, last_value, region FROM sent_alerts "
            "WHERE last_sent_at >= ? AND last_sent_at < ? ORDER BY last_sent_at DESC",
            (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
        )
        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        print(f"[DIGEST] Lỗi đọc điểm nổi bật từ alerts_state.db: {e}")
        return []

    seen_groups = set()
    deduped = []
    for r in rows:
        prefix = "sales_kpi_insights_report" if r[0].startswith("sales_kpi_insights_report_") else r[0].split(":")[0]
        if prefix in _HIGHLIGHT_EXCLUDE_PREFIXES:
            continue
        if not _highlight_matches_channel(r[0], channel):
            continue
        if not _highlight_matches_region(region, r[3]):
            continue
        group_key = _highlight_group_key(r[0])
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        deduped.append(r)
        if len(deduped) >= _HIGHLIGHTS_MAX_ROWS:
            break
    return [_humanize_highlight(r[0], r[1], r[2]) for r in deduped]


def _period_has_critical(start_dt, end_dt, region=None):
    """
    True nếu có >=1 alert CRITICAL THỰC SỰ được gửi trong [start_dt, end_dt) — đọc bảng
    alert_severity_log (ghi bởi src/notifier.py::send_alert_to_all_channels, LỊCH SỬ đầy đủ theo
    thời gian, khác bảng sent_alerts chỉ giữ trạng thái mới nhất). Dùng để gắn cờ Outlook
    Importance:High cho email digest Weekly/Monthly (xem main.py::_send_periodic_email_report), và
    để hiện banner "Kỳ này có cảnh báo mức nghiêm trọng — xem mục Điểm Nổi Bật" trong template.

    21/07/2026: thêm `region`. Phát hiện qua báo cáo Weekly "Quản lý Miền Nam" 13-19/07/2026:
    banner "có cảnh báo nghiêm trọng, xem mục Điểm Nổi Bật" vẫn hiện dù mục đó trống rỗng — vì
    has_critical đọc alert CRITICAL TOÀN CÔNG TY, không biết gì về scope vùng. Bản vá đầu tiên
    (region is not None -> luôn False) chỉ tránh được banner NÓI DỐI, nhưng cũng khiến banner IM
    LẶNG SAI khi có CRITICAL thật đúng vùng audience. Giờ alert_severity_log đã lưu vùng thật (xem
    _log_alert_severity trong src/notifier.py, cùng cơ chế với record_alert_sent(..., region=...)
    trong src/alerts.py — CHỈ ghi tên vùng cụ thể khi alert quy được về đúng 1 vùng, còn lại ghi
    "Toàn quốc"/"Nhiều miền"/None), nên so khớp trực tiếp thay vì fail-closed mù.
    """
    if not os.path.exists(STATE_DB_PATH):
        return False
    try:
        conn = sqlite3.connect(STATE_DB_PATH)
        cursor = conn.cursor()
        if region is None:
            cursor.execute(
                "SELECT COUNT(*) FROM alert_severity_log WHERE severity = 'CRITICAL' "
                "AND sent_at >= ? AND sent_at < ?",
                (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"))
            )
        else:
            from src.region_map import REGION_NAMES_VI
            cursor.execute(
                "SELECT COUNT(*) FROM alert_severity_log WHERE severity = 'CRITICAL' "
                "AND sent_at >= ? AND sent_at < ? AND region = ?",
                (start_dt.strftime("%Y-%m-%d %H:%M:%S"), end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                 REGION_NAMES_VI.get(region))
            )
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        print(f"[DIGEST] Lỗi đọc alert_severity_log (bảng có thể chưa tồn tại nếu chưa có alert nào gửi): {e}")
        return False


def _build_kpi_hierarchy(snap, region):
    """Dựng cây Vùng -> QLV -> TDV từ snapshot KPI Bravo (get_bravo_kpi_tdv_snapshot, có
    manager_code từ 21/07/2026) — phục vụ báo cáo Weekly/Monthly của Trưởng kênh OTC/ETC (thấy rõ
    từng vùng) và Quản lý Vùng (thấy rõ từng QLV/TDV trong vùng mình), thay vì chỉ 1 dòng tổng gộp
    (kpi_summary) không phân biệt được ai đang kéo/ai đang tụt. Thêm 21/07/2026 theo yêu cầu người
    dùng ("các miền phải chia rõ ra theo từng lớp qlv-tdv để biết rõ thông tin về doanh số").

    Dùng `snap` CHƯA lọc target>0 (khác kpi_summary — xem get_digest_metrics) — mục đích khác
    nhau: kpi_summary là con số tổng để đối chiếu % hoàn thành đội, còn cây này là để XEM DANH
    SÁCH đầy đủ ai thuộc QLV nào; ẩn bớt người (dù target=0) sẽ làm cây trông "thiếu" người, gây
    hiểu lầm là họ không tồn tại/không thuộc quyền quản lý của QLV đó.

    region=None (audience kênh, không giới hạn vùng): nhóm theo VÙNG trước, thứ tự đọc tự nhiên
    Bắc-Trung-Nam, mỗi vùng liệt kê QLV rồi TDV dưới quyền (sắp theo doanh số đạt giảm dần).
    region đã set (audience vùng): snap đã lọc sẵn đúng 1 vùng nên bỏ qua lớp nhóm vùng, trả thẳng
    1 nhóm duy nhất mang tên vùng đó.

    TDV có manager_code KHÔNG khớp QLV nào trong `snap` (QLV nghỉ việc/thiếu dữ liệu — hiếm, xác
    minh thực tế 21/07/2026 là 0/148, nhưng không giả định mãi đúng) gộp vào 1 dòng giả
    "(Chưa xác định QLV quản lý)" trong đúng vùng của họ — KHÔNG âm thầm bỏ qua, để phát hiện được
    nếu dữ liệu tương lai có thay đổi. Tương tự, QLV có area_code không khớp 3 vùng đã biết rơi vào
    nhóm "Không rõ vùng" thay vì bị loại khỏi cây.

    Trả list [{"region": "Miền Nam", "qlvs": [{"employee_code", "employee_name", "target",
    "amount", "pct", "tdvs": [{"employee_code", "employee_name", "target", "amount", "pct"}, ...]},
    ...]}, ...] — rỗng nếu snap rỗng."""
    from src.region_map import REGION_SQL_MARKERS, REGION_NAMES_VI

    def _leaf(r):
        pct = round(r.month_sale_percent * 100, 1) if r.month_sale_percent is not None else None
        return {"employee_code": r.employee_code, "employee_name": r.employee_name,
                "target": round(r.month_sale_target, 2), "amount": round(r.month_sale_amount, 2),
                "pct": pct}

    def _region_key(area_code):
        val = (area_code or "").strip().upper()
        for key, markers in REGION_SQL_MARKERS.items():
            if val in markers:
                return key
        return None

    def _unresolved_entry(orphans):
        leaves = sorted([_leaf(t) for t in orphans], key=lambda e: e["amount"], reverse=True)
        return {"employee_code": None, "employee_name": "(Chưa xác định QLV quản lý)",
                "target": round(sum(t.month_sale_target for t in orphans), 2),
                "amount": round(sum(t.month_sale_amount for t in orphans), 2),
                "pct": None, "tdvs": leaves}

    qlvs = [r for r in snap if r.position_code == 'QLV']
    tdvs = [r for r in snap if r.position_code == 'TDV']
    qlv_codes = {q.employee_code for q in qlvs}
    tdvs_by_manager = {}
    orphan_tdvs = []
    for t in tdvs:
        if t.manager_code in qlv_codes:
            tdvs_by_manager.setdefault(t.manager_code, []).append(t)
        else:
            orphan_tdvs.append(t)

    def _qlv_entry(q):
        children = sorted(tdvs_by_manager.get(q.employee_code, []),
                           key=lambda t: t.month_sale_amount, reverse=True)
        entry = _leaf(q)
        entry["tdvs"] = [_leaf(t) for t in children]
        return entry

    if region is not None:
        qlv_list = sorted([_qlv_entry(q) for q in qlvs], key=lambda e: e["amount"], reverse=True)
        if orphan_tdvs:
            qlv_list.append(_unresolved_entry(orphan_tdvs))
        return [{"region": REGION_NAMES_VI.get(region, region), "qlvs": qlv_list}] if qlv_list else []

    groups_out = []
    assigned_qlv_codes = set()
    assigned_orphan_ids = set()
    for region_key in ("bac", "trung", "nam"):
        region_qlvs = [q for q in qlvs if _region_key(q.area_code) == region_key]
        region_orphans = [t for t in orphan_tdvs if _region_key(t.area_code) == region_key]
        assigned_qlv_codes.update(q.employee_code for q in region_qlvs)
        assigned_orphan_ids.update(id(t) for t in region_orphans)
        qlv_list = sorted([_qlv_entry(q) for q in region_qlvs], key=lambda e: e["amount"], reverse=True)
        if region_orphans:
            qlv_list.append(_unresolved_entry(region_orphans))
        if qlv_list:
            groups_out.append({"region": REGION_NAMES_VI[region_key], "qlvs": qlv_list})

    leftover_qlvs = [q for q in qlvs if q.employee_code not in assigned_qlv_codes]
    leftover_orphans = [t for t in orphan_tdvs if id(t) not in assigned_orphan_ids]
    if leftover_qlvs or leftover_orphans:
        qlv_list = sorted([_qlv_entry(q) for q in leftover_qlvs], key=lambda e: e["amount"], reverse=True)
        if leftover_orphans:
            qlv_list.append(_unresolved_entry(leftover_orphans))
        groups_out.append({"region": "Không rõ vùng", "qlvs": qlv_list})
    return groups_out


def _month_tuple(dt):
    return (dt.year, dt.month)


def _prev_month_tuple(dt):
    return (dt.year - 1, 12) if dt.month == 1 else (dt.year, dt.month - 1)


def _build_etc_revenue_by_employee(start_dt, end_dt, region=None):
    """Doanh số ETC theo nhân viên trong [start_dt, end_dt) — nhóm theo vùng, trong mỗi vùng liệt
    kê nhân viên theo doanh số giảm dần. Thêm 21/07/2026 theo yêu cầu (trước đó báo cáo ETC hoàn
    toàn không có mục nhân sự).

    KHÁC HẲN mục KPI của OTC (_build_kpi_hierarchy):
      - ETC KHÔNG có chỉ tiêu cá nhân theo tháng (kế hoạch ETC đặt theo NHÓM HÀNG — FACT_KeHoachTongETC,
        xác nhận 21/07/2026), nên CHỈ hiện doanh số + số hóa đơn, KHÔNG có target/% hoàn thành.
      - ETC KHÔNG có tầng QLV (DMSSX_NhanVien không có cột quản lý) — chỉ 1 lớp nhân viên phẳng.
      - Nhân viên bán ở nhiều vùng xuất hiện 1 lần MỖI vùng (group theo AreaCode) — đúng cho báo
        cáo theo vùng; ở báo cáo toàn quốc/kênh thì họ hiện ở đúng các vùng họ có bán.
      - SCOPE THEO ĐÚNG KỲ báo cáo (hóa đơn trong [start_dt, end_dt)) — khác OTC (snapshot lũy kế
        tháng), nên tuần/tháng KHÁC nhau (đúng bản chất doanh số theo kỳ).

    Join: vHoaDonETCTotal.EmpDMSCode -> DMSSX_NhanVien.DMSCode (lấy tên); vùng qua CityId ->
    DIM_TinhThanhPho.AreaCode (đã kiểm chứng 21/07/2026: 0 mã không tra được tên). Trả list
    [{"region": "Miền Bắc", "employees": [{"employee_name","employee_code","revenue","invoices"}]}]."""
    from sqlalchemy import text, bindparam
    from src.database import _get_bravo_engine
    from src.region_map import REGION_SQL_MARKERS, REGION_NAMES_VI

    engine = _get_bravo_engine()
    if engine is None:
        return []
    markers = _region_markers(region)
    where_region = ""
    params = {"start_dt": start_dt, "end_dt": end_dt}
    if markers:
        where_region = " AND tp.AreaCode IN :markers"
        params["markers"] = tuple(markers)
    sql = text(f'''
        SELECT nv.Name AS emp_name, v.EmpDMSCode AS emp_code, tp.AreaCode AS area_code,
               SUM(v.Amount9) AS rev, COUNT(DISTINCT v.Stt) AS so_hd
        FROM dbo.vHoaDonETCTotal v
        LEFT JOIN DMSSX_NhanVien nv ON nv.DMSCode = v.EmpDMSCode
        LEFT JOIN DIM_TinhThanhPho tp ON tp.CityId = v.CityId
        WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt{where_region}
        GROUP BY nv.Name, v.EmpDMSCode, tp.AreaCode
        HAVING SUM(v.Amount9) <> 0
        ORDER BY SUM(v.Amount9) DESC
    ''')
    if markers:
        sql = sql.bindparams(bindparam("markers", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    def _region_name(area):
        val = (area or "").strip().upper()
        for key, ms in REGION_SQL_MARKERS.items():
            if val in ms:
                return REGION_NAMES_VI[key]
        return "Không rõ vùng"

    groups = {}
    for r in rows:
        rn = _region_name(r.area_code)
        groups.setdefault(rn, []).append({
            "employee_name": r.emp_name or f"(mã {r.emp_code})",
            "employee_code": r.emp_code,
            "revenue": round(float(r.rev), 2),
            "invoices": int(r.so_hd),
        })
    region_order = ["Miền Bắc", "Miền Trung", "Miền Nam", "Không rõ vùng"]
    return [{"region": rn, "employees": groups[rn]}
            for rn in sorted(groups, key=lambda x: region_order.index(x) if x in region_order else 99)]


def get_digest_metrics(start_dt, end_dt, period_label, granularity=None, region=None, channel=None):
    """
    Tổng hợp dữ liệu THẬT trong khoảng [start_dt, end_dt) phục vụ digest định kỳ (dùng chung cho
    daily/weekly/monthly). 20/07/2026: doanh thu/công nợ/tồn kho/KPI đội đều đọc Bravo trực tiếp
    — không còn phụ thuộc Supabase (brv_*/brvsx_*/receivable_detail/inventory/kpi_summary).

    granularity: None (Daily — giữ nguyên hành vi/cấu trúc cũ) hoặc "weekly"/"monthly" (bật thêm
    trend theo ngày/tuần, breakdown vùng, tóm tắt KPI, điểm nổi bật — xem Phần 2 kế hoạch báo cáo).
    region/channel: lọc phạm vi báo cáo theo audience (Phần 3 — phân quyền gửi theo cấp quản lý).
      - region: None hoặc 'bac'/'nam'/'trung'. channel: None hoặc 'OTC'/'ETC'.
      - Áp dụng cho doanh thu/top khách hàng/tóm tắt KPI. Công nợ và tồn kho GIỮ NGUYÊN không lọc
        (tồn kho không có chiều vùng/kênh; công nợ theo vùng cần join thêm qua sales_channon vẫn
        chưa xác nhận định dạng gốc — để nguyên toàn công ty, tránh suy đoán sai).
    """
    from sqlalchemy import text

    # 13/07/2026: kẹp end_dt tại hết hôm nay ngay từ đầu hàm. Từ khi get_weekly/monthly_digest_metrics
    # dùng kỳ ĐANG CHẠY (chưa hết tuần/tháng), end_dt truyền vào có thể là ngày TƯƠNG LAI — phát
    # hiện thực tế: 1 chứng từ ETC ngày 18/07/2026 (tương lai) đã có sẵn trong hệ thống khiến "Tổng
    # Doanh Thu" cao hơn hẳn tổng bảng "Xu Hướng Doanh Thu Trong Kỳ" (đã kẹp ở _revenue_trend) — 2
    # con số trong CÙNG 1 báo cáo lệch nhau. Kẹp 1 lần ở đây áp dụng nhất quán cho MỌI phần dùng
    # end_dt bên dưới (doanh thu, top khách hàng, breakdown vùng, kỳ so sánh liền trước).
    today_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    end_dt = min(end_dt, today_end)

    config = load_config()
    dead_months = float(config['thresholds']['business'].get('dead_stock_months', 12.0))
    dead_min_value = float(config['thresholds']['business'].get('dead_stock_min_value', 50000000))
    region_markers = _region_markers(region)

    # 1. Doanh thu kỳ này + kỳ liền trước (cùng độ dài) để so sánh tăng/giảm — theo đúng phạm vi
    #    region/channel của audience đang xem báo cáo. Tự failover Supabase -> Bravo nội bộ (xem
    #    _period_revenue) nên KHÔNG cần mở connection ở đây nữa.
    otc_rev, etc_rev, otc_invoice_count, etc_invoice_count = _period_revenue(start_dt, end_dt, region=region)
    period_len = end_dt - start_dt
    # 14/07/2026: "kỳ trước" phải CĂN THEO LỊCH tuần/tháng (cùng vị trí ngày trong tuần/tháng
    # trước), không phải lùi lại đúng period_len ngày kể từ start_dt. Bug cũ: start_dt luôn là
    # thứ 2 đầu tuần/ngày 1 đầu tháng, nên "lùi period_len ngày" cho báo cáo ĐẦU tuần/tháng (còn
    # ít ngày trôi qua) rơi vào ĐUÔI của tuần/tháng trước (vd thứ 7-CN) thay vì cùng vị trí đầu
    # tuần/tháng trước — so sánh lệch pha, ngày cuối tuần doanh thu thấp tự nhiên khiến % tăng ảo
    # rất cao (xác nhận thực tế: +465.5% khi so sai thứ 2-3 với thứ 7-CN tuần trước).
    if granularity == "weekly":
        prev_start = start_dt - timedelta(days=7)  # đúng 1 tuần trước, cùng thứ trong tuần
    elif granularity == "monthly":
        prev_year, prev_month = _prev_month_tuple(start_dt)
        prev_start = start_dt.replace(year=prev_year, month=prev_month, day=1)  # ngày 1 tháng trước
    else:
        prev_start = start_dt - period_len  # Daily: giữ nguyên "hôm qua"
    prev_end = prev_start + period_len
    prev_otc_rev, prev_etc_rev, _, _ = _period_revenue(prev_start, prev_end, region=region)
    if channel == "OTC":
        etc_rev = prev_etc_rev = 0.0
        etc_invoice_count = 0
    elif channel == "ETC":
        otc_rev = prev_otc_rev = 0.0
        otc_invoice_count = 0
    invoice_count = otc_invoice_count + etc_invoice_count
    total_rev = otc_rev + etc_rev
    prev_total_rev = prev_otc_rev + prev_etc_rev
    change_pct = ((total_rev - prev_total_rev) / prev_total_rev) if prev_total_rev > 0 else None


    # 3. Công nợ — TỨC THỜI từ Bravo (get_bravo_receivables_snapshot). 20/07/2026: bỏ hẳn fallback
    #    Supabase receivable_detail (dữ liệu Excel tĩnh, không tự làm mới) — Bravo lỗi thì để None.
    receivables = None
    try:
        from src.alerts import get_bravo_receivables_snapshot
        snap = get_bravo_receivables_snapshot()
        # 14/07/2026: lọc theo vùng NGAY TỪ ĐẦU (trước khi tách kênh) — trước đó công nợ luôn
        # tính TOÀN CÔNG TY dù báo cáo đã lọc vùng (audience "Quản lý Miền Bắc/Nam/Trung"), vì
        # chưa xác nhận được cách join khách hàng -> vùng cho công nợ. Đã xác nhận thực tế: join
        # qua DMSId khớp 99,6% (OTC)/95,9% (ETC) khách hàng, tổng 4 vùng (gồm "Không rõ" cho phần
        # không khớp) cộng lại khớp CHÍNH XÁC tổng công ty — xem docstring
        # get_bravo_receivables_snapshot. Lọc ở đây áp dụng luôn cho total/otc/etc bên dưới.
        if region_markers:
            snap = [r for r in snap if r.area_code in region_markers]

        otc_snap = [r for r in snap if r.sales_channel == 'OTC']
        etc_snap = [r for r in snap if r.sales_channel == 'ETC']
        
        total_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in snap)
        balance_end = sum(float(r.balance_end or 0) for r in snap)
        
        otc_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in otc_snap)
        otc_balance = sum(float(r.balance_end or 0) for r in otc_snap)
        
        etc_overdue = sum(
            float(r.overdue_1_15 or 0) + float(r.overdue_15_30 or 0) + float(r.overdue_30_45 or 0) + float(r.overdue_gt_45 or 0)
            for r in etc_snap)
        etc_balance = sum(float(r.balance_end or 0) for r in etc_snap)
        
        receivables = {
            "total_overdue": round(total_overdue, 2),
            "balance_end": round(balance_end, 2),
            "otc_overdue": round(otc_overdue, 2),
            "otc_balance": round(otc_balance, 2),
            "etc_overdue": round(etc_overdue, 2),
            "etc_balance": round(etc_balance, 2),
            "period": f"Tức thời (đến {datetime.now().strftime('%d/%m/%Y %H:%M')})",
        }
    except Exception as e:
        print(f"[DIGEST] Bravo lỗi khi lấy công nợ ({e}) — bỏ trống mục này.")

    # 14/07/2026: khi báo cáo đã lọc theo 1 kênh cụ thể (audience "Quản lý Kênh OTC/ETC"),
    # total_overdue/balance_end (2 field hiển thị chính trong email — mục "Công Nợ") phải đúng
    # PHẠM VI kênh đó, không phải tổng công ty — đã tính sẵn otc_overdue/etc_overdue/otc_balance/
    # etc_balance, chỉ cần chọn đúng cặp thay cho tổng.
    if receivables and channel in ("OTC", "ETC"):
        receivables["total_overdue"] = receivables[f"{channel.lower()}_overdue"]
        receivables["balance_end"] = receivables[f"{channel.lower()}_balance"]

    # 4. Tồn kho — 20/07/2026: chuyển sang Bravo-first qua get_bravo_inventory_snapshot() (src/
    #    alerts.py), bỏ hẳn bảng Supabase `inventory` (thiếu cột channel, chưa từng nhận đúng dữ
    #    liệu sau khi công thức được sửa 17/07/2026 — xem docstring get_bravo_inventory_snapshot).
    #    KPI đội — Bravo trực tiếp (TDV/QLV, get_bravo_kpi_tdv_snapshot); bỏ hẳn fallback
    #    Supabase kpi_summary (xác nhận chỉ có 6/20 QLV thật, thiếu nghiêm trọng).
    dead_stock_count = near_stockout_count = 0
    dead_items = []
    kpi_summary = None
    try:
        from src.alerts import get_bravo_inventory_snapshot
        inv_snapshot = get_bravo_inventory_snapshot()
        if channel in ("OTC", "ETC"):
            inv_snapshot = [r for r in inv_snapshot if r.channel == channel]

        dead_filtered = [r for r in inv_snapshot if r.months_to_sell >= dead_months and r.closing_value > dead_min_value]
        dead_stock_count = len(dead_filtered)
        near_stockout_count = sum(1 for r in inv_snapshot if 0 < r.months_to_sell <= 1.0 and r.closing_qty > 0)
        dead_items = sorted(dead_filtered, key=lambda r: r.closing_value, reverse=True)[:5]
    except Exception as e:
        print(f"[DIGEST] Lỗi lấy tồn kho từ Bravo — bỏ trống mục này: {e}")

    # 14/07/2026: bỏ qua hẳn mục KPI đội khi báo cáo lọc riêng kênh ETC — kpi_summary/TDV/QLV
    # BẢN CHẤT chỉ có ở OTC (nhân viên bán hàng field-force; brvsx_hoadonhdr/ETC không có cột
    # nhân viên trên hóa đơn, xác nhận thực tế trong docstring check_daily_kpi_pace_alert), nên
    # hiện "164 TDV/QLV" cho audience "Quản lý Kênh ETC" là dữ liệu hoàn toàn không liên quan tới
    # họ. channel=None (toàn công ty)/channel="OTC" vẫn hiện như cũ (đúng phạm vi sẵn có).
    kpi_breakdown = []
    if granularity in ("weekly", "monthly") and channel != "ETC":
        try:
            from src.alerts import get_bravo_kpi_tdv_snapshot
            raw_snap = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV'))
            markers = _region_markers(region)
            if markers:
                raw_snap = [r for r in raw_snap if r.area_code in markers]
            snap = [r for r in raw_snap if r.month_sale_target > 0]
            if snap:
                qlv_rows = [r for r in snap if r.position_code == 'QLV']
                tdv_rows = [r for r in snap if r.position_code == 'TDV']
                # 21/07/2026 (mục 2): "Đạt Chỉ Tiêu N/M" ĐẾM Ở TẦNG CÁ NHÂN (TDV) — chỉ tiêu của
                # QLV là mức rollup CẢ ĐỘI, không phải hạn mức cá nhân, nên gộp QLV vào phép đếm
                # đầu người làm con số vô nghĩa (trước đây len(snap) trộn cả TDV lẫn QLV -> vd
                # "0/36" = 31 TDV + 5 QLV). Giờ đếm riêng: bao nhiêu TDV đạt ngưỡng chỉ tiêu cá
                # nhân / tổng TDV có chỉ tiêu — con số quản lý cần để biết mấy nhân viên on-track.
                # Ngưỡng lấy theo vai trò của TỪNG dòng (bonus_threshold_for) chứ không dùng hằng số
                # phẳng: hiện tdv_rows chỉ có TDV nên kết quả y hệt, nhưng nếu sau này phép đếm mở
                # rộng sang QLV thì tự động chấm ở 70% thay vì âm thầm chấm sai ở 65%.
                achieved = sum(1 for r in tdv_rows
                               if (r.month_sale_percent or 0) >= bonus_threshold_for(r.position_code))
                # 27/07/2026: ĐẠT KPI = >=80%, mốc riêng, chung cho mọi vai trò — KHÁC hẳn cổng
                # thưởng 65/70 ở trên và khác "đạt chỉ tiêu" (>=100%) ở dưới. Ba con số, ba nhãn.
                kpi_achieved = sum(1 for r in tdv_rows
                                   if (r.month_sale_percent or 0) >= KPI_ACHIEVED_THRESHOLD)
                # 23/07/2026 (chiều): tách hẳn 2 khái niệm từng bị gộp làm một. `achieved` ở trên là
                # số người TỚI MỨC THƯỞNG NHÓM HÀNG (65%/70%) — KHÔNG phải "đạt chỉ tiêu", và cũng
                # KHÔNG phải "được thưởng" nói chung: 65%/70% chỉ là cổng của thưởng nhóm hàng
                # (DM1/DM2/DM3). DNH còn V15/V22/V25, ASO (tính theo SỐ LƯỢNG khách hàng chứ không
                # phải %), thưởng quý, thưởng năm — mốc khác hẳn. Lương cơ bản từ 60% trở lên vẫn
                # hưởng 100%. Nên người dưới 65% VẪN có thể được các khoản kia và vẫn có đủ lương
                # cơ bản; đừng để nhãn báo cáo ám chỉ họ không được gì.
                # Đạt chỉ tiêu đúng nghĩa đen là làm được ≥100% chỉ tiêu tháng. Nhãn cũ
                # "Đạt Chỉ Tiêu (≥65%)" tự nó đã mâu thuẫn: đạt chỉ tiêu mà mới làm được 65% chỉ tiêu.
                # Giữa tháng con số 100% gần như luôn ~0 và ĐÓ LÀ ĐÚNG (doanh số lũy kế tới hôm nay
                # so với chỉ tiêu cả tháng) — đưa ra cả hai để người đọc thấy được bức tranh thật.
                full_target = sum(1 for r in tdv_rows if (r.month_sale_percent or 0) >= 1.0)
                total_count = len(tdv_rows)
                # 21/07/2026: SỬA BUG CỘNG TRÙNG tiền — TDV và QLV là 2 cách CẮT LÁT SONG SONG của
                # CÙNG 1 khoản doanh thu (QLV.month_sale_amount ĐÃ LÀ rollup của các TDV dưới quyền
                # — verify qua ManagerCode, xem _build_kpi_hierarchy), không phải 2 phần cộng dồn.
                # Cộng cả 2 -> gấp ~2× thật (phát hiện qua Monthly "Quản lý Miền Nam" 21/07/2026:
                # "Tổng Doanh Số Đạt" 4,45 tỷ > Doanh Thu OTC thật cả tháng 3,32 tỷ — vô lý).
                #
                # 27/07/2026: đổi từ "TẦNG LÁ" sang "TẦNG ROLLUP QLV" — và đổi ĐỒNG THỜI bên chatbot
                # (backend/report_templates.py::kpi_ranking nhánh region), 2 hệ thống PHẢI gộp giống
                # nhau, nếu không khách mở song song email và chatbot sẽ thấy 2 bộ số khác nhau.
                #
                # Vì sao bỏ tầng lá: bản ghi chú 23/07 chọn tầng lá vì phần chênh ~1,75 tỷ ở MB
                # "chưa giải thích được". NAY ĐÃ GIẢI THÍCH ĐƯỢC (27/07, đối chiếu từng dòng với báo
                # cáo gốc "Tiến độ doanh số tháng theo NVKD" tháng 7): đó là tổng 5 dòng CHỈ TIÊU CÁ
                # NHÂN CỦA CHÍNH QLV (QLV vừa quản đội vừa tự ôm một địa bàn) — 1.744.361.395đ, hoàn
                # toàn hợp lệ, KHÔNG phải chỉ tiêu cấp vùng chồng lên. Kiểm chứng: target rollup của
                # tungtx 3.016.493.346 = tổng 10 TDV dưới quyền 2.756.994.289 + phần tự thân 259.499.057.
                #
                # Tầng lá VỀ BẢN CHẤT không thể đếm đủ: người có chỉ tiêu nhưng không được giao khách
                # nào thì KHÔNG có dòng nào trong FACT_TongHopKhachHang (bảng này chỉ có dòng theo
                # từng khách), nên vô hình với mọi cách cộng từ dưới lên — riêng MB mất 626.173.042đ.
                #
                # Đối chiếu thực tế 27/07/2026 (target cả tháng) với báo cáo gốc + DIM_TargetVungMien:
                #   tầng lá   : MB 23,75 tỷ | MN  5,26 tỷ | MT 6,79 tỷ  -> lệch rất lớn
                #   tầng rollup: MB 30,78 tỷ | MN 13,19 tỷ | MT 7,00 tỷ -> KHỚP TUYỆT ĐỐI cả 3 miền,
                #   tổng toàn quốc 50.967.586.921đ = đúng dòng Total của báo cáo gốc. Kiểm thêm 7
                #   tháng (2026-01..07): 21/21 cặp tháng×vùng khớp 0 đồng.
                #
                # Tầng rollup xác định bằng MANAGER_CODE (quan hệ dữ liệu THẬT), CỐ Ý không dùng
                # position_code lẫn IsDuplicate — cả hai đều sai nhãn trên Bravo: Dương Thị Hồng Huệ
                # (Modern Trade, 5,29 tỷ) mang chức danh 'TK', và 4 QLV thật bị gắn cờ IsDuplicate=1.
                # Vì vậy phải lấy snapshot include_duplicates=True cho phép gộp TIỀN này (an toàn: các
                # dòng "tự thân QLV" cũng IsDuplicate=1 nhưng KHÔNG quản lý ai nên tự bị loại khỏi
                # tầng rollup, không gây cộng trùng). Các phép ĐẾM ĐẦU NGƯỜI ở trên vẫn dùng snap đã
                # lọc trùng như cũ — không đổi.
                # Tập quản lý phải lấy từ TOÀN BỘ FACT (get_bravo_manager_codes, KHÔNG lọc chức danh)
                # chứ không suy từ chính money_snap: cấp dưới của một số QLV mang chức danh ngoài
                # ('TDV','QLV') nên bị snapshot lọc mất, khiến QLV đó không bao giờ được nhận ra là
                # quản lý (MN1 'Kênh MT' và MN4 'Chợ sỉ' — hụt 6,79 tỷ chỉ tiêu Miền Nam).
                from src.alerts import get_bravo_manager_codes
                money_snap = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV'),
                                                        include_duplicates=True)
                if markers:
                    money_snap = [r for r in money_snap if r.area_code in markers]
                managers_with_team = get_bravo_manager_codes()
                money_rows = [r for r in money_snap if r.employee_code in managers_with_team]
                # CHỐT AN TOÀN — chống LỒNG TẦNG: nếu sau này Bravo thêm cấp trên (vd TP quản lý QLV)
                # thì cộng cả 2 cấp sẽ GẤP ĐÔI âm thầm. Hiện 21/21 đều là QLV, không ai bị lồng.
                nested = [r.employee_code for r in money_rows
                          if r.manager_code and r.manager_code in managers_with_team]
                if nested:
                    print(f"[DIGEST][kpi_summary] CẢNH BÁO CẤU TRÚC: {len(nested)} người ở tầng quản lý "
                          f"lại có cấp trên ({', '.join(nested[:5])}) — cây tổ chức đã có thêm tầng, "
                          f"tổng chỉ tiêu vùng CÓ THỂ bị đếm trùng. Cần kiểm tra lại cách gộp.")
                total_target = sum(r.month_sale_target for r in money_rows)
                total_amount = sum(r.month_sale_amount for r in money_rows)
                team_pct = (total_amount / total_target) if total_target else None
                kpi_summary = {
                    # achieved_count = số người TỚI MỨC THƯỞNG NHÓM HÀNG (65%/70% tuỳ vai trò).
                    "achieved_count": achieved, "total_count": total_count,
                    # 23/07/2026: đưa ngưỡng ra tận email — 2 hệ thống từng dùng 2 ngưỡng khác nhau
                    # và không chỗ nào ghi rõ đang dùng ngưỡng nào, nên người đọc không có cách nào
                    # biết vì sao 2 con số lệch. Số khác nhau mà giải thích được thì không phá niềm
                    # tin; số khác nhau mà im lặng thì có.
                    "achieved_threshold_pct": round(BONUS_THRESHOLD_TDV * 100),
                    # 27/07/2026: ĐẠT KPI (≥80%) — mốc RIÊNG, chung mọi vai trò. Đừng nhầm với 2 cái kia.
                    "kpi_achieved_count": kpi_achieved,
                    "kpi_threshold_pct": round(KPI_ACHIEVED_THRESHOLD * 100),
                    # Số người ĐẠT CHỈ TIÊU đúng nghĩa (≥100%) — khác cả 2 con số trên.
                    "full_target_count": full_target,
                    "team_pct": round(team_pct * 100, 1) if team_pct is not None else None,
                    "total_target": round(total_target, 2), "total_amount": round(total_amount, 2),
                }
            # 21/07/2026: cây Vùng->QLV->TDV cho báo cáo Trưởng kênh OTC (thấy rõ từng vùng) và
            # Quản lý Vùng (thấy rõ từng QLV/TDV) — dùng raw_snap (CHƯA lọc target>0, khác
            # kpi_summary ở trên) để không "biến mất" người chỉ vì họ chưa có chỉ tiêu tháng này.
            if raw_snap:
                kpi_breakdown = _build_kpi_hierarchy(raw_snap, region)
        except Exception as e:
            # 20/07/2026: bỏ fallback Supabase kpi_summary — xác nhận bảng đó chỉ có 6/20 QLV
            # thật (import 1 lần từ đầu dự án, không refresh), hiện số liệu đó còn tệ hơn bỏ trống
            # mục này (cùng nguyên tắc "báo lỗi rõ ràng hơn số liệu có thể sai" đã áp dụng cho
            # doanh thu/công nợ/tồn kho).
            print(f"[DIGEST] Bravo lỗi khi lấy KPI đội ({e}) — bỏ trống mục này.")

    # 21/07/2026: doanh số ETC theo nhân viên — bổ sung cho các báo cáo CÓ kênh ETC (channel != OTC:
    # tức C-Level, các vùng, và riêng Kênh ETC). Đối xứng với KPI OTC ở trên nhưng đơn giản hơn
    # (không target/%, không tầng QLV — xem docstring _build_etc_revenue_by_employee).
    etc_by_employee = []
    if granularity in ("weekly", "monthly") and channel != "OTC":
        try:
            etc_by_employee = _build_etc_revenue_by_employee(start_dt, end_dt, region)
        except Exception as e:
            print(f"[DIGEST] Bravo lỗi khi lấy doanh số ETC theo nhân viên ({e}) — bỏ trống mục này.")

    # 5. Phần mở rộng CHỈ cho weekly/monthly (không đổi hành vi/tải truy vấn của daily). Trend +
    #    region_breakdown tự failover nội bộ (xem _revenue_trend/_revenue_by_region).
    trend, region_breakdown = [], []
    if granularity in ("weekly", "monthly"):
        # 16/07/2026: ĐỐI CHIẾU bảng xu hướng với Tổng Doanh Thu đã tính riêng (total_rev) — 2 con
        # số này LẼ RA bằng nhau (doanh thu cộng dồn được theo ngày, cả 2 cùng kẹp end_dt/region/
        # channel giống nhau). Nếu lệch: 1 truy vấn con của _revenue_trend đã trả RỖNG do lỗi Bravo
        # tạm thời (COALESCE SUM = 0), sinh bug "1 ngày = 0 dù tổng vẫn đúng" — phát hiện thực tế
        # 16/07: báo cáo OTC hiện Wed 15/07 = 0 dù Tổng Doanh Thu gồm cả ngày đó (do chạy Weekly+
        # Monthly đồng thời gây nghẽn Bravo). Thử lại 1 lần; vẫn lệch thì BỎ bảng xu hướng — thà
        # không có biểu đồ còn hơn gửi biểu đồ sai/nội bộ mâu thuẫn cho quản lý.
        for _attempt in range(2):
            trend = _revenue_trend(start_dt, end_dt, granularity, region=region, channel=channel)
            trend_sum = round(sum(t["revenue"] for t in trend), 2)
            if abs(trend_sum - round(total_rev, 2)) <= 1.0:
                break
            print(f"[DIGEST] Xu hướng lệch tổng ({trend_sum:,.0f} vs {total_rev:,.0f}) — "
                  f"{'thử lại' if _attempt == 0 else 'BỎ bảng xu hướng lần này'}.")
        else:
            trend = []
        if region is None:
            region_breakdown = _revenue_by_region(start_dt, end_dt, channel=channel)

    # 16/07/2026: phân tích tăng trưởng theo vùng + tỷ trọng kênh — CHỈ cho Monthly (theo yêu
    # cầu "thêm phân tích rõ ràng hơn cho báo cáo monthly"), để phân biệt rõ với Weekly thay vì
    # chỉ khác màu tiêu đề. So sánh cùng prev_start/prev_end đã tính ở trên (kỳ liền trước cùng
    # độ dài) — tái dùng, không query thêm ngoài _revenue_by_region cho kỳ trước.
    region_growth = []
    channel_share = None
    if granularity == "monthly":
        if region is None:
            try:
                prev_region_breakdown = _revenue_by_region(prev_start, prev_end, channel=channel)
                prev_by_name = {r["region"]: r["revenue"] for r in prev_region_breakdown}
                for r in region_breakdown:
                    prev_rev = prev_by_name.get(r["region"], 0.0)
                    growth_pct = ((r["revenue"] - prev_rev) / prev_rev * 100) if prev_rev > 0 else None
                    region_growth.append({
                        "region": r["region"], "revenue": r["revenue"],
                        "prev_revenue": round(prev_rev, 2), "growth_pct": round(growth_pct, 1) if growth_pct is not None else None,
                    })
            except Exception as e:
                print(f"[DIGEST] Lỗi tính tăng trưởng theo vùng: {e}")
        # 16/07/2026: chỉ tính khi báo cáo KHÔNG lọc sẵn theo 1 kênh — nếu đã lọc (audience "Quản
        # lý Kênh OTC/ETC"), etc_rev/otc_rev đã bị ép về 0 ở trên nên tỷ trọng luôn ra 100%/0% vô
        # nghĩa, không nên hiện cho những audience đó.
        if channel is None and total_rev > 0:
            channel_share = {
                "otc_pct": round(otc_rev / total_rev * 100, 1),
                "etc_pct": round(etc_rev / total_rev * 100, 1),
            }

    # 16/07/2026: TRƯỚC ĐÂY chỉ tính cho weekly/monthly — Daily Digest hoàn toàn không có mục
    # "Điểm Nổi Bật Trong Kỳ" dù trong ngày có cảnh báo CRITICAL thật (vd tỷ lệ nợ quá hạn, khách
    # nợ quá hạn vẫn lên đơn mới...) đã bắn qua Teams. Bật cho mọi granularity — chi phí không đáng
    # kể (1 query SQLite cục bộ, không đụng Bravo/Supabase).
    highlights = _get_period_highlights(start_dt, end_dt, channel=channel, region=region)
    has_critical = _period_has_critical(start_dt, end_dt, region=region)

    result = {
        "date": start_dt.strftime("%d/%m/%Y"),
        "period_range": period_label,
        "updated_at": datetime.now().strftime("%H:%M %d/%m/%Y"),
        "region": region,
        "channel": channel,
        "revenue": {
            "otc": round(otc_rev, 2),
            "etc": round(etc_rev, 2),
            "total": round(total_rev, 2),
            "invoice_count": invoice_count,
            "otc_invoice_count": otc_invoice_count,
            "etc_invoice_count": etc_invoice_count,
            "prev_total": round(prev_total_rev, 2),
            "change_pct": round(change_pct * 100, 1) if change_pct is not None else None,
            # 14/07/2026: nhãn ngày cụ thể của "kỳ trước" — "so kỳ trước" đơn thuần không rõ là so
            # với gì (kỳ trước = cùng ĐỘ DÀI ngày ngay trước start_dt, không nhất thiết là "tháng
            # trước"/"tuần trước" trọn vẹn, nhất là khi kỳ hiện tại đang chạy dở/chưa hết).
            "prev_period_label": f"{prev_start.strftime('%d/%m')}-{(prev_end - timedelta(days=1)).strftime('%d/%m/%Y')}",
        },
        "receivables": receivables,
        "inventory": {
            "dead_stock_count": dead_stock_count,
            "near_stockout_count": near_stockout_count,
            "dead_stock_items": [
                {"item_code": r.item_code, "item_name": r.item_name, "closing_value": round(float(r.closing_value), 2),
                 "months_to_sell": round(float(r.months_to_sell), 1), "channel": r.channel}
                for r in dead_items
            ],
        },
        "highlights": highlights,
        "has_critical": has_critical,
    }
    if granularity in ("weekly", "monthly"):
        result["trend"] = trend
        result["region_breakdown"] = region_breakdown
        result["kpi_summary"] = kpi_summary
        result["kpi_breakdown"] = kpi_breakdown
        result["etc_by_employee"] = etc_by_employee
    if granularity == "monthly":
        result["region_growth"] = region_growth
        result["channel_share"] = channel_share
    return result

def get_daily_digest_metrics(region=None, channel=None, show_operational_quality=False):
    """Tổng hợp dữ liệu trong ngày phục vụ Daily Digest (Teams).
    13/07/2026: thêm region/channel (trước đó luôn None — chỉ có 1 bản toàn công ty gửi cho
    audience C-Level, 5 audience còn lại không nhận Daily Digest). Xem send_daily_digest()
    trong main.py — giờ lặp qua report_recipients, gọi hàm này riêng cho từng audience.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    metrics = get_digest_metrics(today_start, today_end, today_start.strftime("%d/%m/%Y"), region=region, channel=channel)
    
    if show_operational_quality:
        from src.alerts import get_kpi_pace_summary, get_revenue_reconciliation_diff, get_etc_return_rate
        metrics["operational_quality"] = {
            "kpi_pace": get_kpi_pace_summary(),
            "reconciliation": get_revenue_reconciliation_diff(),
            "etc_return": get_etc_return_rate()
        }
        
    return metrics

def get_weekly_digest_metrics(region=None, channel=None):
    """Tổng hợp dữ liệu TUẦN ĐANG CHẠY (thứ 2 tới hiện tại) phục vụ Weekly Report (Email).
    13/07/2026: đổi từ "tuần TRƯỚC đã kết thúc trọn vẹn" sang tuần hiện tại — lịch chạy
    DNH_Weekly_Report là thứ Bảy 17:45 (scripts/register_digest_schedule.bat), nghĩa là tuần
    hiện tại (thứ 2 - hiện tại) CHƯA hết Chủ Nhật; logic cũ lùi thêm 1 tuần nữa để lấy tuần
    "đã kết thúc trọn vẹn", khiến báo cáo trễ tới gần 2 tuần so với thời điểm gửi (vd gửi 11/07
    mà báo cáo tuần 29/06-05/07). ĐÁNH ĐỔI (giống Monthly Report): thiếu dữ liệu chiều/tối thứ
    Bảy và cả ngày Chủ Nhật của tuần — chấp nhận được để đổi lấy báo cáo tươi hơn nhiều.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())  # weekday(): Thứ 2 = 0
    week_end = week_start + timedelta(days=7)  # exclusive — hết Chủ nhật tuần này (kể cả nếu chưa tới)
    # 21/07/2026: nhãn hiện đúng khoảng ĐÃ CÓ DỮ LIỆU, không phải cả khung tuần theo lịch — trước
    # đây ghi "Tuần 20/07 - 26/07" ngay cả khi gửi thử vào thứ Ba (21/07), nhìn như báo cả tuần
    # trong khi 5/7 ngày chưa xảy ra. Lấy min(hôm nay, Chủ nhật) làm ngày cuối hiển thị; gắn thêm
    # "(đang chạy)" nếu tuần chưa trọn (dữ liệu vẫn tính trên [week_start, week_end) như cũ — ngày
    # tương lai đóng góp 0đ nên tổng không đổi, chỉ NHÃN trung thực hơn).
    last_shown = min(today_start, week_end - timedelta(days=1))
    running_suffix = " (đang chạy)" if today_start < week_end - timedelta(days=1) else ""
    label = f"Tuần {week_start.strftime('%d/%m/%Y')} - {last_shown.strftime('%d/%m/%Y')}{running_suffix}"
    return get_digest_metrics(week_start, week_end, label, granularity="weekly", region=region, channel=channel)

def get_monthly_digest_metrics(region=None, channel=None):
    """Tổng hợp dữ liệu THÁNG ĐANG CHẠY (chứa ngày gọi hàm) phục vụ Monthly Report (Email).
    10/07/2026: đổi lịch DNH_Monthly_Report từ "ngày 1 tháng sau" sang "ngày cuối tháng, 17h45"
    (xem scripts/register_digest_schedule.bat) để báo cáo tháng vừa xong được gửi SỚM HƠN 1 ngày
    — ĐÁNH ĐỔI: thiếu vài giờ cuối ngày cuối tháng (17h45 → 24h), chấp nhận được theo yêu cầu.
    TRƯỚC ĐÂY hàm này tính "tháng TRƯỚC tháng chứa ngày gọi" (đúng khi lịch chạy là ngày 1 tháng
    sau) — giữ nguyên logic cũ trong khi đổi lịch chạy sẽ khiến báo cáo bị TRỄ THÊM 1 THÁNG (vd
    gửi 31/7 mà vẫn nói về tháng 6), nên phải sửa cả 2 cùng lúc, không chỉ đổi lịch schtasks.
    region/channel: lọc phạm vi báo cáo theo audience (xem get_digest_metrics)."""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    next_year, next_month = (month_start.year + 1, 1) if month_start.month == 12 else (month_start.year, month_start.month + 1)
    month_end = month_start.replace(year=next_year, month=next_month)  # exclusive — hết ngày cuối tháng này
    # 21/07/2026: cùng lý do với Weekly — nhãn hiện đúng khoảng đã có dữ liệu (min(hôm nay, ngày
    # cuối tháng)) thay vì luôn ghi hết tháng theo lịch (vd "01/07 - 31/07" khi mới 21/07).
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    last_shown = min(today_start, month_end - timedelta(days=1))
    running_suffix = " — đang chạy" if today_start < month_end - timedelta(days=1) else ""
    label = f"Tháng {month_start.strftime('%m/%Y')} ({month_start.strftime('%d/%m')} - {last_shown.strftime('%d/%m/%Y')}{running_suffix})"
    return get_digest_metrics(month_start, month_end, label, granularity="monthly", region=region, channel=channel)

if __name__ == '__main__':
    # Chạy thử kiểm tra việc trích xuất
    erp_eng, crm_eng = get_db_engines()
    config = load_config()

    print("--- Kiêm tra dữ liệu ERP ---")
    limit = config['thresholds']['erp']['low_inventory_limit']
    lookback = config['thresholds']['erp']['failed_orders_lookback_hours']

    print(f"Sản phẩm tồn kho thấp (ngưỡng < {limit}):")
    print(get_low_inventory(erp_eng, limit))

    print(f"\nĐơn hàng lỗi gần đây (lookback {lookback}h):")
    print(get_recent_failed_orders(erp_eng, lookback))

    print("\n--- Kiểm tra dữ liệu CRM ---")
    print("Tickets Urgent chưa giải quyết:")
    print(get_unresolved_urgent_tickets(crm_eng))

    print("\n--- Báo cáo tổng hợp Daily Digest Metrics ---")
    import pprint
    pprint.pprint(get_daily_digest_metrics())
