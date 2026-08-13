# -*- coding: utf-8 -*-
"""
"Đáp án đúng" cho Demo #1 Chatbot (09/08/2026) — lấy thẳng từ Bravo bằng ĐÚNG các hàm mà báo cáo
định kỳ đang dùng, để đối chiếu với câu trả lời của chatbot (dnh-bot.vercel.app).

VÌ SAO CẦN: chatbot (D:\\DNH-x-MCNA) và báo cáo (D:\\DNH) là 2 nhánh mã nguồn độc lập, đọc dữ liệu
theo 2 đường khác nhau (chatbot đọc kho SQLite local đồng bộ định kỳ; báo cáo đọc thẳng Bravo).
Tuần 20-24/07/2026 đã kiểm định xong độ chính xác của NHÁNH BÁO CÁO (15/15 hạng mục, lệch 0đ) —
nhưng nhánh chatbot thì chưa. Tại demo, khách hỏi chatbot rồi đối chiếu với báo cáo: 2 số khác nhau
là mất niềm tin của cả tuần làm việc. Script này tạo ra "đáp án đúng" để phát hiện lệch TRƯỚC demo.

NGUYÊN TẮC: chỉ GỌI LẠI hàm sẵn có (src/etl.py, src/alerts.py), KHÔNG viết lại logic tính toán —
viết lại là tự tạo ra nguồn số thứ ba, mất luôn ý nghĩa đối chiếu. Riêng "top khách hàng"/"top sản
phẩm" chưa có hàm tương ứng trong D:\\DNH nên query thẳng 2 view gốc đã được xác nhận là nguồn đúng
của DNH (dbo.vHoaDonTotal / dbo.vHoaDonETCTotal — xem docstring src/etl.py::_period_revenue).

KỲ TÍNH LÀ TƯƠNG ĐỐI (tháng này đến hôm nay / tháng trước / tuần trước / hôm qua) — chạy lại sáng
09/08 là ra số đúng của ngày đó, không phải sửa gì.

Chạy:  set PYTHONIOENCODING=utf-8 && python scripts/demo1_ground_truth.py
       (thiếu PYTHONIOENCODING thì console cp1252 sẽ vỡ tiếng Việt)
"""
import sys
import os
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta

from src.etl import (
    get_monthly_digest_metrics,
    _period_revenue,
    _revenue_by_region,
    _build_etc_revenue_by_employee,
    _build_kpi_hierarchy,
    _region_markers,
)
from src.alerts import get_bravo_receivables_snapshot

# BA mốc KHÁC NHAU, tuyệt đối không gộp (xác nhận với DNH 27/07/2026):
#   >= 100%  ĐẠT CHỈ TIÊU  — làm đủ chỉ tiêu tháng được giao, đúng nghĩa đen.
#   >=  80%  ĐẠT KPI       — mốc đánh giá hiệu quả công việc.
#   >=  65%  TỚI MỨC THƯỞNG NHÓM HÀNG (TDV; QLV và các cấp quản lý là 70%) — CỔNG bắt đầu được
#            tính thưởng nhóm hàng DM1/DM2/DM3, lấy theo bảng `dbo.DIM_BacThuong` mà thủ tục tính
#            lương thật của DNH đang đọc (QĐ 0107/2026 cho TDV, QĐ 0429/.25 cho cấp quản lý).
# 65%/70% CHỈ là cổng của thưởng nhóm hàng — DNH còn V15/V22/V25/ASO/thưởng quý/năm mốc khác hẳn,
# và lương cơ bản từ 60% trở lên vẫn hưởng 100%. Nên người dưới 65% VẪN có thể được các khoản kia:
# TUYỆT ĐỐI không diễn đạt thành "không được thưởng"/"không đạt KPI".
KPI_THRESHOLDS = (1.00, 0.80, 0.65)

SEP = "=" * 78


def _kpi_snapshot_asof(as_of_date, position_codes=('TDV', 'QLV'), include_duplicates=False):
    """Ban SAO CO CHU DICH cua src.alerts.get_bravo_kpi_tdv_snapshot, chi khac 1 diem: SaveDate
    duoc GHIM vao snapshot moi nhat KHONG SAU as_of_date, thay vi MAX(SaveDate) tren TOAN BO bang
    (ham goc luon lay "bay gio", khong nhan tham so ngay). Can rieng ham nay vi demo #1 (09/08)
    se hoi chatbot RO RANG ve thang 7 (xem R-A, docs/kich_ban_demo1_chatbot.md) - chay script nay
    sang 09/08 ma khong ghim ngay se lay nham snapshot thang 8 moi 9 ngay, khong doi chieu duoc.
    Chay dung ngay that (as_of=hom nay) cho ra KET QUA GIONG HET ham goc, vi luc do khong co
    snapshot nao trong tuong lai de MAX() chon nham - chi khac nhau khi dung de TAP DUOT cho 1
    ngay da qua. KHONG sua ham goc trong alerts.py vi no con phuc vu alert/digest song, luon can
    "bay gio" that."""
    from sqlalchemy import text
    import types
    from src.database import _get_bravo_engine
    from src.alerts import _is_duplicate_filter_sql
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    placeholders = ",".join(f"'{p}'" for p in position_codes)
    sql = text(f'''
        WITH snap AS (
            SELECT MAX([SaveDate]) AS d FROM [FACT_TongHopKhachHang] WHERE [SaveDate] <= :as_of
        ),
        tdv_actual AS (
            SELECT [EmployeeCode], SUM([Amount_Cus]) AS TotalActual
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] = (SELECT d FROM snap)
            GROUP BY [EmployeeCode]
        ),
        tdv_target AS (
            SELECT DISTINCT [EmployeeCode], [AreaCode], [MonthSaleTarget], [ManagerCode]
            FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] = (SELECT d FROM snap)
        )
        SELECT n.[EmployeeCode] AS employee_code, n.[Name] AS employee_name, t.[AreaCode] AS area_code,
               n.[PositionCode] AS position_code, t.[ManagerCode] AS manager_code,
               t.[MonthSaleTarget] AS month_sale_target, ISNULL(a.TotalActual, 0) AS month_sale_amount,
               (SELECT d FROM snap) AS snapshot_date
        FROM tdv_target t
        JOIN [DIM_NhanVien] n ON t.[EmployeeCode] = n.[EmployeeCode]
        LEFT JOIN tdv_actual a ON t.[EmployeeCode] = a.[EmployeeCode]
        WHERE n.[PositionCode] IN ({placeholders})
              {"" if include_duplicates else "AND " + _is_duplicate_filter_sql('n')}
    ''')
    with engine.connect() as conn:
        # str(...) CO CHU DICH: driver ODBC "SQL Server" (ban cu, dang dung tren may dev) khong
        # bind duoc kieu datetime.date -> 'Optional feature not implemented (SQLBindParameter)'.
        # Chuoi 'YYYY-MM-DD' chay dung tren CA driver cu lan Driver 17.
        rows = conn.execute(sql, {"as_of": str(as_of_date)}).fetchall()
    result = []
    snap_date = rows[0].snapshot_date if rows else None
    for r in rows:
        target = float(r.month_sale_target) if r.month_sale_target else 0.0
        amount = float(r.month_sale_amount or 0)
        pct = (amount / target) if target > 0 else None
        result.append(types.SimpleNamespace(
            employee_code=r.employee_code, employee_name=r.employee_name, area_code=r.area_code,
            position_code=r.position_code, manager_code=r.manager_code,
            month_sale_target=target, month_sale_amount=amount, month_sale_percent=pct))
    return result, snap_date


def _manager_codes_asof(as_of_date):
    """Ban sao co chu dich cua src.alerts.get_bravo_manager_codes, ghim SaveDate <= as_of_date -
    xem docstring _kpi_snapshot_asof. PHAI dung CUNG as_of_date voi _kpi_snapshot_asof o tren de 2
    truy van roi vao CUNG 1 snapshot (khac snapshot se lam tap QLV va so tien lech nhau)."""
    from sqlalchemy import text
    from src.database import _get_bravo_engine
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT DISTINCT [ManagerCode] FROM [FACT_TongHopKhachHang]
            WHERE [SaveDate] = (SELECT MAX([SaveDate]) FROM [FACT_TongHopKhachHang] WHERE [SaveDate] <= :as_of)
              AND [ManagerCode] IS NOT NULL AND [ManagerCode] <> ''
        '''), {"as_of": str(as_of_date)}).fetchall()
    return {r[0] for r in rows}


def money(v):
    """Định dạng tiền cho dễ đọc nhanh khi đối chiếu bằng mắt với câu trả lời chatbot."""
    if v is None:
        return "(không có)"
    if abs(v) >= 1e9:
        return f"{v:,.0f} đ  (~{v/1e9:.2f} tỷ)"
    if abs(v) >= 1e6:
        return f"{v:,.0f} đ  (~{v/1e6:.1f} triệu)"
    return f"{v:,.0f} đ"


def answer(code, question, lines):
    """In 1 khối 'câu hỏi demo -> đáp án đúng'. lines: str hoặc list[str]."""
    print(f"\n[{code}] {question}")
    for ln in ([lines] if isinstance(lines, str) else lines):
        print(f"     {ln}")


def periods(as_of=None):
    """Các kỳ TƯƠNG ĐỐI dùng chung. Trả dict {tên: (start_dt, end_dt_exclusive, nhãn_cho_chatbot)}.

    LƯU Ý về quy ước ngày — 2 hệ thống viết khác nhau nhưng CÙNG nghĩa:
      - D:\\DNH dùng nửa khoảng [start, end)  (end KHÔNG tính)
      - chatbot dùng BETWEEN date_from AND date_to (cả 2 đầu ĐỀU tính)
    Đã kiểm 23/07/2026: DocDate trong Bravo là kiểu `date` thuần (không có phần giờ), nên
    [start, end) == BETWEEN start AND end-1ngày, không lệch. 'nhãn_cho_chatbot' bên dưới đã trừ sẵn
    1 ngày để hỏi chatbot đúng phạm vi — KHÔNG tự đổi lại khi copy câu hỏi.

    as_of: 28/07/2026 (R-A) — mặc định None = hôm nay thật. Truyền 1 ngày TRONG THÁNG CẦN TẬP DƯỢT
    (vd 2026-07-31) để "tháng này" tính đúng tháng đó, thay vì tháng đang chạy script. Cần thiết vì
    demo #1 (09/08) sẽ hỏi chatbot RÕ RÀNG về tháng 7 — chạy script không ép ngày vào sáng 09/08 sẽ
    tính "tháng này" = tháng 8 mới 9 ngày, không đối chiếu được với câu hỏi demo.
    """
    now = as_of or datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    month_start = today.replace(day=1)
    ny, nm = (month_start.year + 1, 1) if month_start.month == 12 else (month_start.year, month_start.month + 1)
    month_end = month_start.replace(year=ny, month=nm)
    # Kỳ "tháng này" chạy tới HẾT HÔM NAY (không tới cuối tháng) — đúng phạm vi dữ liệu đã có thật,
    # và khớp cách khách sẽ hỏi chatbot ("doanh thu tháng này đến giờ").
    month_to_now_end = today + timedelta(days=1)

    prev_month_end = month_start
    pm = month_start - timedelta(days=1)
    prev_month_start = pm.replace(day=1)

    week_start = today - timedelta(days=today.weekday())
    last_week_start = week_start - timedelta(days=7)
    last_week_end = week_start

    yesterday = today - timedelta(days=1)

    def lbl(s, e):
        return f"{s.strftime('%Y-%m-%d')} .. {(e - timedelta(days=1)).strftime('%Y-%m-%d')}"

    return {
        "thang_nay": (month_start, month_to_now_end, lbl(month_start, month_to_now_end)),
        "thang_truoc": (prev_month_start, prev_month_end, lbl(prev_month_start, prev_month_end)),
        "tuan_truoc": (last_week_start, last_week_end, lbl(last_week_start, last_week_end)),
        "hom_qua": (yesterday, today, lbl(yesterday, today)),
        "_thang_full": (month_start, month_end),
    }


def _top_by(field, start_dt, end_dt, limit=10, region=None):
    """Top N theo doanh thu, gộp OTC+ETC, từ 2 view gốc Bravo. field: 'CustomerCode' | 'ItemCode'.

    KHÔNG có hàm sẵn trong src/ cho phần này (báo cáo định kỳ không có mục top khách/top sản phẩm),
    nên query trực tiếp — nhưng dùng ĐÚNG 2 view mà _period_revenue đã dùng, để tổng vẫn nhất quán
    với mọi con số khác trong file này. Chatbot tính cùng nghĩa nhưng trên kho local đồng bộ từ
    chính 2 view này (xem DNH-x-MCNA/backend/sync_warehouse.py) — nên LẼ RA phải khớp.

    region: None (không lọc, mặc định) hoặc 'bac'/'trung'/'nam' — dùng LẠI đúng
    customer_region_resolve_sql() mà _period_revenue đã dùng (28/07/2026, cho câu R2 "top khách
    hàng vùng tôi") thay vì tự viết CASE suy luận vùng riêng — khách "mồ côi" (không có hồ sơ trong
    DMS_KhachHang) phải được suy ra qua tiền tố mã, giống mọi chỗ lọc vùng khác trong dự án.
    """
    from sqlalchemy import text, bindparam
    from src.database import _get_bravo_engine
    from src.region_map import customer_region_resolve_sql

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")

    name_join, name_col = "", "NULL"
    if field == "ItemCode":
        name_join = "LEFT JOIN BRV_SanPham sp ON sp.Code = t.k"
        name_col = "MAX(sp.Name)"

    params = {"start_dt": start_dt, "end_dt": end_dt}
    otc_region_join, otc_where, etc_region_join, etc_where = "", "", "", ""
    markers = _region_markers(region)
    if markers:
        otc_region_join, otc_area_expr = customer_region_resolve_sql("v", "OTC")
        etc_region_join, etc_area_expr = customer_region_resolve_sql("v", "ETC")
        otc_where = f" AND {otc_area_expr} IN :region_markers"
        etc_where = f" AND {etc_area_expr} IN :region_markers"
        params["region_markers"] = tuple(markers)

    sql = text(f'''
        WITH combined AS (
            SELECT v.{field} AS k, v.Amount9 AS amt FROM dbo.vHoaDonTotal v
                {otc_region_join}
                WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt {otc_where}
            UNION ALL
            SELECT v.{field} AS k, v.Amount9 AS amt FROM dbo.vHoaDonETCTotal v
                {etc_region_join}
                WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt {etc_where}
        )
        SELECT TOP {int(limit)} t.k AS code, {name_col} AS name, SUM(t.amt) AS rev
        FROM combined t
        {name_join}
        GROUP BY t.k
        ORDER BY SUM(t.amt) DESC
    ''')
    if markers:
        sql = sql.bindparams(bindparam("region_markers", expanding=True))
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [(r.code, r.name, float(r.rev or 0)) for r in rows]


def section_clevel(p):
    """Vai c_level — toàn quốc. Mã câu khớp docs/kich_ban_demo1_chatbot.md."""
    print(f"\n{SEP}\nVAI: c_level (toàn quốc)\n{SEP}")

    m_start, m_end, m_lbl = p["thang_nay"]
    pm_start, pm_end, pm_lbl = p["thang_truoc"]

    # --- C1: doanh thu tháng này tách OTC/ETC ---
    otc, etc, n_otc, n_etc = _period_revenue(m_start, m_end)
    answer("C1", f"Doanh thu tháng này đến hôm nay ({m_lbl}), tách OTC và ETC?", [
        f"OTC:  {money(otc)}  —  {n_otc:,} hóa đơn",
        f"ETC:  {money(etc)}  —  {n_etc:,} hóa đơn",
        f"TỔNG: {money(otc + etc)}  —  {n_otc + n_etc:,} hóa đơn",
    ])

    # --- C2: so tháng trước ---
    p_otc, p_etc, _, _ = _period_revenue(pm_start, pm_end)
    cur_total, prev_total = otc + etc, p_otc + p_etc
    growth = ((cur_total - prev_total) / prev_total * 100) if prev_total else None
    # Lưu ý "tháng này mới chạy dở" CHỈ đúng khi kỳ đang xét là tháng đang chạy. Với --as-of trỏ về
    # một tháng đã trọn (vd 31/07) thì hai vế đều trọn vẹn, in cảnh báo đó ra là dặn sai người trình
    # bày — họ sẽ giải thích một hiện tượng không tồn tại trước mặt khách.
    ky_da_tron = m_end.date() < datetime.now().date()
    luu_y = ([
        "LƯU Ý: cả hai kỳ đều TRỌN VẸN nên so sánh này là so ngang bằng, không cần trừ hao.",
    ] if ky_da_tron else [
        "LƯU Ý: tháng này mới chạy dở, so với tháng trước TRỌN VẸN nên tất nhiên thấp hơn —",
        "       tại demo phải nói rõ điều này, đừng để khách hiểu là doanh thu đang sụt.",
    ])
    answer("C2", f"So với tháng trước ({pm_lbl}) tăng/giảm bao nhiêu %?", [
        f"Tháng này:  {money(cur_total)}",
        f"Tháng trước: {money(prev_total)}",
        f"Chênh lệch: {'(không tính được)' if growth is None else f'{growth:+.1f}%'}",
    ] + luu_y)

    # --- C3: doanh thu theo miền ---
    by_region = _revenue_by_region(m_start, m_end)
    lines = [f"{r['region']}: {money(r['revenue'])}" for r in by_region]
    lines.append(f"Cộng lại: {money(sum(r['revenue'] for r in by_region))}  (phải khớp TỔNG ở C1)")
    answer("C3", f"Doanh thu tháng này ({m_lbl}) chia theo ba miền thế nào?", lines)

    # --- C4/C5: top khách hàng, top sản phẩm ---
    answer("C4", f"Top 10 khách hàng lớn nhất tháng này ({m_lbl})?",
           [f"{i:>2}. {code}  —  {money(rev)}" for i, (code, _n, rev) in
            enumerate(_top_by("CustomerCode", m_start, m_end), 1)])
    answer("C5", f"Top 10 sản phẩm bán chạy nhất tháng này ({m_lbl})?",
           [f"{i:>2}. {code} {(name or '')[:38]}  —  {money(rev)}" for i, (code, name, rev) in
            enumerate(_top_by("ItemCode", m_start, m_end), 1)])


def section_kpi(p, as_of_date):
    """KPI — phần dễ lệch nhất giữa 2 hệ thống (ngưỡng đạt + cách gộp tầng TDV/QLV).

    28/07/2026 (R-A): dùng snapshot GHIM vào as_of_date (_kpi_snapshot_asof), không phải
    get_bravo_kpi_tdv_snapshot() "bây giờ" nữa — nếu không, chạy sáng 09/08 sẽ lấy snapshot tháng 8
    (mới vài ngày) thay vì tháng 7 mà demo hỏi. Chạy đúng ngày thật thì 2 cách cho CÙNG kết quả."""
    print(f"\n{SEP}\nKPI ĐỘI (câu C6, C7, C8, Q1)\n{SEP}")

    snap_all, snap_date = _kpi_snapshot_asof(as_of_date, position_codes=('TDV', 'QLV'))
    print(f"  (snapshot FACT_TongHopKhachHang dùng cho KPI: SaveDate={snap_date})")
    snap = [r for r in snap_all if r.month_sale_target > 0]
    tdv_rows = [r for r in snap if r.position_code == 'TDV']
    qlv_rows = [r for r in snap if r.position_code == 'QLV']

    # --- C7: PHÂN BIỆT "đạt chỉ tiêu" (>=100%) với "tới mức thưởng nhóm hàng" (>=65% TDV) ---
    lines = [f"Tổng TDV có chỉ tiêu tháng: {len(tdv_rows)} người", ""]
    for th in KPI_THRESHOLDS:
        ok = sum(1 for r in tdv_rows if (r.month_sale_percent or 0) >= th)
        note = {1.00: "  <<< ĐẠT CHỈ TIÊU (làm đủ chỉ tiêu tháng)",
                0.80: "  <<< ĐẠT KPI (mốc đánh giá hiệu quả công việc)",
                0.65: "  <<< TỚI MỨC THƯỞNG NHÓM HÀNG (TDV 65%)"}.get(th, "")
        lines.append(f"Ngưỡng >= {th*100:.0f}%:  ĐẠT {ok}/{len(tdv_rows)}  —  "
                     f"CHƯA đạt {len(tdv_rows) - ok}/{len(tdv_rows)}{note}")
    lines.append("")
    # 28/07/2026: mốc quản lý (QLV/TP/PP/TBP) là 70%, KHÁC 65% của TDV — qlv_rows tồn tại từ đầu
    # nhưng chưa từng được dùng ở đây (biến chết), nên bảng C7 trước giờ CHỈ nói được về TDV dù
    # R-C đã chốt cả 2 vai trò. Chỉ đếm ở đúng 1 mốc thưởng nhóm hàng của quản lý (70%) — không lặp
    # lại 100%/80% cho QLV vì "đạt chỉ tiêu"/"đạt KPI" đã là khái niệm chung, không tách vai trò.
    QLV_BONUS_THRESHOLD = 0.70
    qlv_ok = sum(1 for r in qlv_rows if (r.month_sale_percent or 0) >= QLV_BONUS_THRESHOLD)
    lines.append(f"Tổng QLV có chỉ tiêu tháng: {len(qlv_rows)} người")
    lines.append(f"Ngưỡng >= {QLV_BONUS_THRESHOLD*100:.0f}%:  ĐẠT {qlv_ok}/{len(qlv_rows)}  —  "
                 f"CHƯA đạt {len(qlv_rows) - qlv_ok}/{len(qlv_rows)}  <<< TỚI MỨC THƯỞNG NHÓM HÀNG (quản lý 70%)")
    lines += [
        "",
        ">>> BA mốc này KHÁC NHAU, khi trả lời PHẢI nói rõ đang dùng mốc nào:",
        "      100% = đạt chỉ tiêu · 80% = đạt KPI · 65%(TDV)/70%(quản lý) = tới mức thưởng nhóm hàng.",
        ">>> 65%/70% CHỈ là cổng thưởng nhóm hàng (DM1/DM2/DM3), lấy theo DIM_BacThuong — KHÔNG phải",
        "    'đạt KPI'. Người dưới mốc vẫn có thể được V15/ASO và vẫn đủ lương cơ bản (>=60%).",
        ">>> Giữa tháng, số đạt >=100% gần như luôn ~0 và ĐÓ LÀ ĐÚNG (lũy kế tới hôm nay so với chỉ",
        "    tiêu CẢ tháng) — phải giải thích, đừng để người đọc tưởng hệ thống hỏng.",
    ]
    answer("C7", "Hiện có bao nhiêu TDV chưa đạt chỉ tiêu tháng?", lines)

    # --- C6: xếp hạng vùng theo % đạt KPI ---
    # 27/07/2026: cộng tiền ở TẦNG ROLLUP QLV (mỗi QLV đã gồm đội của họ + chỉ tiêu cá nhân của
    # chính họ), thay cho "tầng lá" dùng từ 23/07. Lý do đổi: tầng lá VỀ BẢN CHẤT không đếm đủ —
    # người có chỉ tiêu nhưng chưa được giao khách nào thì không có dòng nào trong
    # FACT_TongHopKhachHang nên vô hình (riêng MB mất 626.173.042đ); và phần chênh 1,75 tỷ từng ghi
    # là "chưa giải thích được" NAY ĐÃ RÕ: đó là tổng 5 dòng chỉ tiêu cá nhân của QLV, hợp lệ.
    # Kiểm chứng: tầng rollup khớp TUYỆT ĐỐI báo cáo gốc "Tiến độ doanh số tháng theo NVKD" và bảng
    # DIM_TargetVungMien ở cả 3 miền (MB 30,78 / MN 13,19 / MT 7,00 tỷ; tổng 50.967.586.921đ), và
    # khớp suốt 7 tháng 2026-01..07 (21/21 cặp tháng×vùng lệch 0 đồng).
    # Tầng rollup xác định bằng ManagerCode lấy từ TOÀN BỘ FACT (get_bravo_manager_codes) — CỐ Ý
    # không lọc PositionCode/IsDuplicate: cấp dưới của 'Kênh MT'/'Chợ sỉ' mang chức danh TK/CS, lọc
    # theo chức danh sẽ làm 2 QLV này biến mất (hụt 6,79 tỷ Miền Nam).
    # ĐÃ SỬA ĐỦ CẢ 3 CHỖ (23/07 dặn: sót 1 chỗ là lệch lại): src/etl.py::get_digest_metrics,
    # backend/report_templates.py::kpi_ranking (repo DNH-x-MCNA), và file này.
    money_snap, _ = _kpi_snapshot_asof(as_of_date, position_codes=('TDV', 'QLV'), include_duplicates=True)
    managers_with_team = _manager_codes_asof(as_of_date)
    money_rows = [r for r in money_snap if r.employee_code in managers_with_team]
    by_area = {}
    for r in money_rows:
        a = by_area.setdefault(r.area_code or "(không rõ)", {"target": 0.0, "amount": 0.0})
        a["target"] += r.month_sale_target
        a["amount"] += r.month_sale_amount
    lines = []
    for area, v in sorted(by_area.items(), key=lambda kv: -(kv[1]["amount"] / kv[1]["target"] if kv[1]["target"] else 0)):
        pct = (v["amount"] / v["target"] * 100) if v["target"] else None
        lines.append(f"{area:<12} {('%.1f%%' % pct) if pct is not None else '(chưa có chỉ tiêu)':>8}   "
                     f"đạt {money(v['amount'])} / chỉ tiêu {money(v['target'])}")
    tot_t = sum(v["target"] for v in by_area.values())
    tot_a = sum(v["amount"] for v in by_area.values())
    lines.append(f"{'TOÀN ĐỘI':<12} {(tot_a/tot_t*100 if tot_t else 0):>7.1f}%   "
                 f"đạt {money(tot_a)} / chỉ tiêu {money(tot_t)}")
    answer("C6", "Xếp hạng các vùng theo mức đạt KPI?", lines)

    # --- C8 / Q1: cây Vùng -> QLV -> TDV, lấy miền Bắc làm mẫu ---
    # _build_kpi_hierarchy KHÔNG tự lọc vùng — người gọi phải lọc trước rồi mới truyền region
    # (xem docstring: "region đã set ... snap đã lọc sẵn đúng 1 vùng"). Lọc y hệt get_digest_metrics.
    markers = _region_markers("bac")
    snap_bac = [r for r in snap_all if r.area_code in markers] if markers else snap_all
    tree = _build_kpi_hierarchy(snap_bac, "bac")
    lines = []
    for node in tree:
        lines.append(f"VÙNG {node['region']}:")
        for qlv in node["qlvs"]:
            lines.append(f"  QLV {qlv['employee_name']} ({qlv['employee_code']}) — "
                         f"đạt {money(qlv['amount'])} / chỉ tiêu {money(qlv['target'])} = "
                         f"{qlv['pct'] if qlv['pct'] is not None else '(chưa có chỉ tiêu)'}% — "
                         f"{len(qlv['tdvs'])} TDV dưới quyền")
            for tdv in qlv["tdvs"][:3]:
                lines.append(f"      · {tdv['employee_name']} ({tdv['employee_code']}): "
                             f"{money(tdv['amount'])} = {tdv['pct']}%")
            if len(qlv["tdvs"]) > 3:
                lines.append(f"      · ... còn {len(qlv['tdvs']) - 3} TDV nữa")
    answer("C8", "Cây doanh thu miền Bắc theo QLV và TDV?",
           lines or ["(không có dữ liệu — kiểm tra lại kết nối Bravo)"])


def section_regional(p):
    """Vai regional_director — dữ liệu vùng, để đối chiếu câu R1/R2 và kiểm tra rò rỉ ở R5."""
    print(f"\n{SEP}\nVAI: regional_director (mẫu: miền Bắc) — câu R1..R5\n{SEP}")

    m_start, m_end, m_lbl = p["thang_nay"]
    for key, vi in (("bac", "Miền Bắc"), ("trung", "Miền Trung"), ("nam", "Miền Nam")):
        otc, etc, n_otc, n_etc = _period_revenue(m_start, m_end, region=key)
        answer(f"R1-{key}", f"Doanh thu {vi} tháng này ({m_lbl})?", [
            f"OTC {money(otc)} ({n_otc:,} HĐ) · ETC {money(etc)} ({n_etc:,} HĐ)",
            f"TỔNG {vi}: {money(otc + etc)}",
        ])
    print("\n     >>> DÙNG CHO CÂU BẢO MẬT R5: tài khoản scope 'MB' hỏi doanh thu Miền Nam PHẢI bị")
    print("         chặn. Nếu chatbot trả đúng con số Miền Nam ở trên = RÒ RỈ DỮ LIỆU, dừng mọi")
    print("         việc khác để xử lý trước khi demo.")

    # --- R2: top khách hàng vùng tôi (28/07/2026 — trước đây "chạy script để lấy", chưa có gì) ---
    top_mb = _top_by("CustomerCode", m_start, m_end, region="bac")
    answer("R2", f"Top 10 khách hàng lớn nhất Miền Bắc tháng này ({m_lbl})?",
           [f"{i:>2}. {code}  —  {money(rev)}" for i, (code, _n, rev) in enumerate(top_mb, 1)] or
           ["(không có khách hàng nào phát sinh doanh thu ở MB trong kỳ)"])
    print("     >>> Tổng top 10 phải <= TỔNG doanh thu MB ở R1-bac (không thể vượt tổng vùng).")


_AREA_TO_BRANCH = {"MB": "B02", "MT": "B03", "MN": "B04"}
_BRANCH_LABEL = {"B01": "Sản xuất", "B02": "Miền Bắc", "B03": "Miền Trung", "B04": "Miền Nam"}


def section_inventory(_p):
    """Tồn kho theo vùng — câu R4, 28/07/2026 (trước đây "chạy script để lấy", KHÔNG có code nào).

    KHÔNG dùng get_bravo_inventory_snapshot()/build_inventory_dataframe() (src/alerts.py,
    scripts/sync_from_bravo_to_supabase.py): hàm đó đặt warehouse=None (gộp hết kho), không thể
    tách vùng. Query trực tiếp BRV_TonKhoDK JOIN BRV_Kho.BranchCode — ĐÚNG khuôn mẫu chatbot đang
    dùng (DNH-x-MCNA/backend/report_templates.py::inventory_by_region qua bảng local
    brv_tonkhodk/brv_kho đồng bộ nguyên văn từ 2 bảng Bravo này, xem sync_warehouse.py dòng 222-224)
    — số ở đây PHẢI khớp con số chatbot trả cho get_inventory_by_region, đây là lần đối chiếu ĐẦU
    TIÊN cho tool này kể từ khi viết (17/07/2026)."""
    from sqlalchemy import text
    from src.database import _get_bravo_engine

    print(f"\n{SEP}\nTỒN KHO THEO VÙNG (câu R4)\n{SEP}")
    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")
    with engine.connect() as conn:
        rows = conn.execute(text('''
            SELECT k.BranchCode AS area_code, COUNT(DISTINCT t.ItemId) AS so_mat_hang,
                   SUM(t.Quantity) AS tong_so_luong, SUM(t.Amount) AS tong_gia_tri
            FROM BRV_TonKhoDK t LEFT JOIN BRV_Kho k ON k.Id = t.WarehouseId
            WHERE t.IsActive = 1
            GROUP BY k.BranchCode
        ''')).fetchall()
    by_branch = {r.area_code: r for r in rows}
    lines = []
    for branch in ("B02", "B03", "B04", "B01"):
        r = by_branch.get(branch)
        label = _BRANCH_LABEL[branch]
        if r is None:
            lines.append(f"{label:<12} (không có dòng tồn kho)")
        else:
            lines.append(f"{label:<12} {r.so_mat_hang:>5,} mặt hàng · SL {r.tong_so_luong:>14,.0f} · "
                         f"giá trị {money(float(r.tong_gia_tri or 0))}")
    answer("R4", "Tồn kho vùng tôi (mẫu: 3 vùng kinh doanh + sản xuất)?", lines)
    print("     >>> Đối chiếu với get_inventory_by_region() của chatbot — LẦN KIỂM ĐẦU TIÊN cho")
    print("         tool này, có thể lộ lệch chưa từng biết. B01 (Sản xuất) không thuộc vùng nào,")
    print("         tài khoản bị giới hạn vùng KHÔNG được thấy dòng này (đã chặn ở report_templates.py).")


def section_etc(p):
    """Doanh số ETC theo nhân viên — mục mới thêm 21/07, chatbot CHƯA có tool tương ứng."""
    print(f"\n{SEP}\nDOANH SỐ ETC THEO NHÂN VIÊN (tháng này)\n{SEP}")
    m_start, m_end, m_lbl = p["thang_nay"]
    groups = _build_etc_revenue_by_employee(m_start, m_end)
    total = 0.0
    for g in groups:
        print(f"\n  {g['region']}:")
        for e in g["employees"][:5]:
            print(f"    {e['employee_name'][:32]:<34} {money(e['revenue']):>28}  ({e['invoices']} HĐ)")
        rest = len(g["employees"]) - 5
        if rest > 0:
            print(f"    ... còn {rest} nhân viên nữa")
        total += sum(e["revenue"] for e in g["employees"])
    print(f"\n  Cộng tất cả: {money(total)}  (phải khớp ETC ở câu C1)")
    print("  LƯU Ý: chatbot KHÔNG có tool cho mục này — nếu khách hỏi, chatbot sẽ tự ghép SQL hoặc")
    print("         trả lời thiếu. Cân nhắc không đưa vào demo, hoặc chỉ trình qua báo cáo email.")


def section_receivables(p):
    """Công nợ — MÂU THUẪN ĐÃ BIẾT giữa chatbot và báo cáo."""
    print(f"\n{SEP}\nCÔNG NỢ (câu X1 — CÂU RỦI RO, cân nhắc không demo)\n{SEP}")
    snap = get_bravo_receivables_snapshot()

    def _sum(rows, f):
        return sum(float(getattr(r, f) or 0) for r in rows)

    def _overdue(rows):
        return sum(_sum(rows, f) for f in ("overdue_1_15", "overdue_15_30", "overdue_30_45", "overdue_gt_45"))

    for label, rows in (("TOÀN CÔNG TY", snap),
                        ("OTC", [r for r in snap if r.sales_channel == 'OTC']),
                        ("ETC", [r for r in snap if r.sales_channel == 'ETC'])):
        bal, od = _sum(rows, "balance_end"), _overdue(rows)
        pct = (od / bal * 100) if bal else 0
        print(f"  {label:<14} dư nợ {money(bal):>30}   quá hạn {money(od):>30}   ({pct:.1f}%)")

    print("""
  >>> ĐÂY LÀ SỐ ĐÚNG (gọi thẳng usp_DeptAccDueDate_GetData — báo cáo gốc của DNH).
      27/07/2026 (R-B): CHATBOT GIỜ ĐỌC CÙNG NGUỒN NÀY (bảng local fact_congno_khachhang, đồng bộ
      từ chính usp_DeptAccDueDate_GetData — DNH-x-MCNA/backend/sync_warehouse.py::sync_fact_congno,
      report_templates.py::_customer_receivable). KHÔNG còn đọc Supabase receivable_detail/
      receivable_etc (bảng Excel cũ đã bị chặn cứng ở query_engine.py). Câu X1 có thể đưa vào demo.
      MỐC PHÁT HIỆN HỒI QUY: nếu tỷ lệ quá hạn OTC/ETC ra lại ~92,9%/81,1% là đang đọc nhầm nguồn
      Excel cũ (số đó từng thổi nợ 1 khách lên 9,17 tỷ trong khi thật là 0,61 tỷ) — dừng demo, báo lỗi.""")


def section_crosscheck(p):
    """Đối chiếu chéo: các con số trong file này phải khớp báo cáo định kỳ. Lệch = script sai."""
    print(f"\n{SEP}\nĐỐI CHIẾU CHÉO VỚI BÁO CÁO ĐỊNH KỲ (tự kiểm tra script này)\n{SEP}")
    m_start, m_end, _ = p["thang_nay"]

    # 13/08/2026 SỬA BÁO ĐỘNG GIẢ: get_monthly_digest_metrics() KHÔNG nhận as-of, nó luôn tính
    # tháng ĐANG CHẠY. Khi dùng --as-of để lấy số của tháng đã qua, phép so này đem tháng 7 so với
    # tháng 8 dở dang rồi kết luận "LỆCH — script sai". Sai ở phép so, không phải ở số liệu:
    # lần chạy 13/08 báo lệch 48,5 tỷ trong khi cả hai vế đều đúng với kỳ của mình.
    thang_hien_tai = datetime.now().strftime("%Y-%m")
    if m_start.strftime("%Y-%m") != thang_hien_tai:
        print(f"  BỎ QUA: đang dùng --as-of nên kỳ của script là {m_start.strftime('%m/%Y')}, còn báo")
        print(f"          cáo định kỳ luôn tính tháng đang chạy ({thang_hien_tai}) — hai kỳ khác nhau,")
        print("          so với nhau là vô nghĩa. Muốn đối chiếu thật thì chạy KHÔNG kèm --as-of.")
        return True

    m = get_monthly_digest_metrics(region=None, channel=None)
    r = m["revenue"]
    otc, etc, _, _ = _period_revenue(m_start, m_end)

    print(f"  Kỳ báo cáo tháng: {m['period_range']}")
    print(f"  Digest tháng:  OTC {money(r['otc'])} · ETC {money(r['etc'])}")
    print(f"  Script này:    OTC {money(otc)} · ETC {money(etc)}")
    # Digest tính hết THÁNG (ngày tương lai đóng góp 0đ) còn script kẹp tới hết hôm nay — cùng kỳ
    # thực tế nên PHẢI bằng nhau. Lệch nghĩa là script sai, KHÔNG phải Bravo sai.
    diff = abs((r["otc"] + r["etc"]) - (otc + etc))
    print(f"  Chênh lệch:    {money(diff)}  ->  {'KHỚP' if diff <= 1.0 else 'LỆCH — script sai, phải sửa trước khi dùng'}")
    return diff <= 1.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", dest="as_of", default=None,
                         help="Ngày YYYY-MM-DD để TẬP DƯỢT ground truth của 1 ngày đã qua (vd chạy "
                              "hôm nay để lấy số của tháng 7 dùng cho demo 09/08). Mặc định: hôm nay "
                              "thật — dùng mặc định khi chạy đúng sáng demo.")
    args = parser.parse_args()
    as_of_dt = datetime.strptime(args.as_of, "%Y-%m-%d") if args.as_of else None
    as_of_date = (as_of_dt or datetime.now()).date()

    p = periods(as_of_dt)
    print(SEP)
    print("ĐÁP ÁN ĐÚNG CHO DEMO #1 CHATBOT — nguồn: Bravo (qua đúng hàm của báo cáo định kỳ)")
    print(f"Chạy lúc: {datetime.now().strftime('%H:%M %d/%m/%Y')}")
    if as_of_dt:
        print(f">>> TẬP DƯỢT: đang tính như thể HÔM NAY LÀ {as_of_date} (--as-of) <<<")
    print(f"Kỳ 'tháng này':  {p['thang_nay'][2]}")
    print(f"Kỳ 'tháng trước': {p['thang_truoc'][2]}")
    print(f"Kỳ 'tuần trước':  {p['tuan_truoc'][2]}")
    print(f"Kỳ 'hôm qua':     {p['hom_qua'][2]}")
    print("Dùng ĐÚNG các mốc ngày trên khi hỏi chatbot — hỏi lệch ngày thì lệch số là đương nhiên.")
    print(SEP)

    ok = True
    for fn in (section_clevel, section_regional, section_inventory, section_etc, section_receivables):
        try:
            fn(p)
        except Exception as e:
            ok = False
            print(f"\n  [LỖI] {fn.__name__}: {e}")
    try:
        section_kpi(p, as_of_date)
    except Exception as e:
        ok = False
        print(f"\n  [LỖI] section_kpi: {e}")
    try:
        ok = section_crosscheck(p) and ok
    except Exception as e:
        ok = False
        print(f"\n  [LỖI] section_crosscheck: {e}")

    print(f"\n{SEP}")
    print("XONG." if ok else "XONG — CÓ MỤC LỖI/LỆCH Ở TRÊN, xem lại trước khi dùng làm đáp án.")
    print(SEP)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
