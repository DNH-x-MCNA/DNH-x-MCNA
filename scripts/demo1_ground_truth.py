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
from src.alerts import get_bravo_kpi_tdv_snapshot, get_bravo_receivables_snapshot

# Ngưỡng "đạt chỉ tiêu" — CỐ Ý in ra cả 2 vì 2 hệ thống đang dùng 2 ngưỡng khác nhau:
#   - Báo cáo định kỳ (src/etl.py:899):                >= 100%
#   - Chatbot (DNH-x-MCNA/backend/report_templates.py): >= 80%  (KPI_ACHIEVED_THRESHOLD)
# Chưa có xác nhận nghiệp vụ từ DNH ngưỡng nào đúng (đã bổ sung thành mục hỏi trong
# docs/Cau_hoi_can_DNH_xac_nhan.md). Trong lúc chờ, in cả 2 để biết chênh lệch THẬT là bao nhiêu
# người — có con số cụ thể thì mới hỏi khách được, và tại demo mới giải thích được vì sao lệch.
KPI_THRESHOLDS = (1.00, 0.80)

SEP = "=" * 78


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


def periods():
    """Các kỳ TƯƠNG ĐỐI dùng chung. Trả dict {tên: (start_dt, end_dt_exclusive, nhãn_cho_chatbot)}.

    LƯU Ý về quy ước ngày — 2 hệ thống viết khác nhau nhưng CÙNG nghĩa:
      - D:\\DNH dùng nửa khoảng [start, end)  (end KHÔNG tính)
      - chatbot dùng BETWEEN date_from AND date_to (cả 2 đầu ĐỀU tính)
    Đã kiểm 23/07/2026: DocDate trong Bravo là kiểu `date` thuần (không có phần giờ), nên
    [start, end) == BETWEEN start AND end-1ngày, không lệch. 'nhãn_cho_chatbot' bên dưới đã trừ sẵn
    1 ngày để hỏi chatbot đúng phạm vi — KHÔNG tự đổi lại khi copy câu hỏi.
    """
    now = datetime.now()
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


def _top_by(field, start_dt, end_dt, limit=10):
    """Top N theo doanh thu, gộp OTC+ETC, từ 2 view gốc Bravo. field: 'CustomerCode' | 'ItemCode'.

    KHÔNG có hàm sẵn trong src/ cho phần này (báo cáo định kỳ không có mục top khách/top sản phẩm),
    nên query trực tiếp — nhưng dùng ĐÚNG 2 view mà _period_revenue đã dùng, để tổng vẫn nhất quán
    với mọi con số khác trong file này. Chatbot tính cùng nghĩa nhưng trên kho local đồng bộ từ
    chính 2 view này (xem DNH-x-MCNA/backend/sync_warehouse.py) — nên LẼ RA phải khớp.
    """
    from sqlalchemy import text
    from src.database import _get_bravo_engine

    engine = _get_bravo_engine()
    if engine is None:
        raise RuntimeError("Không có Bravo engine (thiếu BRAVO_SQL_* trong .env)")

    name_join, name_col = "", "NULL"
    if field == "ItemCode":
        name_join = "LEFT JOIN BRV_SanPham sp ON sp.Code = t.k"
        name_col = "MAX(sp.Name)"

    sql = text(f'''
        WITH combined AS (
            SELECT v.{field} AS k, v.Amount9 AS amt FROM dbo.vHoaDonTotal v
                WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
            UNION ALL
            SELECT v.{field} AS k, v.Amount9 AS amt FROM dbo.vHoaDonETCTotal v
                WHERE v.DocDate >= :start_dt AND v.DocDate < :end_dt
        )
        SELECT TOP {int(limit)} t.k AS code, {name_col} AS name, SUM(t.amt) AS rev
        FROM combined t
        {name_join}
        GROUP BY t.k
        ORDER BY SUM(t.amt) DESC
    ''')
    with engine.connect() as conn:
        rows = conn.execute(sql, {"start_dt": start_dt, "end_dt": end_dt}).fetchall()
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
    answer("C2", f"So với tháng trước ({pm_lbl}) tăng/giảm bao nhiêu %?", [
        f"Tháng này:  {money(cur_total)}",
        f"Tháng trước: {money(prev_total)}",
        f"Chênh lệch: {'(không tính được)' if growth is None else f'{growth:+.1f}%'}",
        "LƯU Ý: tháng này mới chạy dở, so với tháng trước TRỌN VẸN nên tất nhiên thấp hơn —",
        "       tại demo phải nói rõ điều này, đừng để khách hiểu là doanh thu đang sụt.",
    ])

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


def section_kpi(p):
    """KPI — phần dễ lệch nhất giữa 2 hệ thống (ngưỡng đạt + cách gộp tầng TDV/QLV)."""
    print(f"\n{SEP}\nKPI ĐỘI (câu C6, C7, C8, Q1)\n{SEP}")

    snap_all = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV'))
    snap = [r for r in snap_all if r.month_sale_target > 0]
    tdv_rows = [r for r in snap if r.position_code == 'TDV']
    qlv_rows = [r for r in snap if r.position_code == 'QLV']

    # --- C7: ngưỡng đạt chỉ tiêu — BẰNG CHỨNG cho mâu thuẫn 80% vs 100% ---
    lines = [f"Tổng TDV có chỉ tiêu tháng: {len(tdv_rows)} người", ""]
    for th in KPI_THRESHOLDS:
        ok = sum(1 for r in tdv_rows if (r.month_sale_percent or 0) >= th)
        note = "  <<< NGƯỠNG ĐANG DÙNG (cả báo cáo lẫn chatbot)" if th == 0.80 else ""
        lines.append(f"Ngưỡng >= {th*100:.0f}%:  ĐẠT {ok}/{len(tdv_rows)}  —  "
                     f"CHƯA đạt {len(tdv_rows) - ok}/{len(tdv_rows)}{note}")
    lines += [
        "",
        ">>> 2 hệ thống ĐÃ thống nhất ngưỡng 80% (23/07/2026). Vẫn in cả 2 ngưỡng vì DNH CHƯA xác",
        "    nhận 80% có đúng quy ước nghiệp vụ không (mục A6, docs/Cau_hoi_can_DNH_xac_nhan.md) —",
        "    có sẵn cả 2 con số thì lúc DNH hỏi mới trả lời được ngay là đổi ngưỡng thì lệch bao nhiêu.",
        ">>> Tại demo VẪN phải nói rõ đang dùng ngưỡng 80%, đừng đưa số trần.",
    ]
    answer("C7", "Hiện có bao nhiêu TDV chưa đạt chỉ tiêu tháng?", lines)

    # --- C6: xếp hạng vùng theo % đạt KPI ---
    # Cộng tiền ở TẦNG LÁ: mọi TDV + những QLV không có TDV nào dưới quyền. Không cộng cả 2 tầng
    # (QLV.month_sale_amount ĐÃ là rollup của TDV dưới quyền -> gấp đôi), cũng không cộng thuần TDV
    # (bỏ sót QLV tự ôm khách, vd MBKV12). Cách này đã thống nhất cho CẢ báo cáo (src/etl.py) lẫn
    # chatbot (report_templates.py::kpi_ranking) ngày 23/07/2026 — xem docs/kich_ban_demo1_chatbot.md
    # mục R-D. Nếu sửa cách gộp thì phải sửa đủ 3 chỗ, nếu không lại lệch như trước.
    managers_with_team = {t.manager_code for t in snap_all if t.position_code == 'TDV'}
    childless_qlv_rows = [q for q in qlv_rows if q.employee_code not in managers_with_team]
    money_rows = tdv_rows + childless_qlv_rows
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
    """Vai regional_director — dữ liệu vùng, để đối chiếu câu R1/R4 và kiểm tra rò rỉ ở R5."""
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
      CHATBOT ĐANG ĐỌC NGUỒN KHÁC: Supabase receivable_detail/receivable_etc — dữ liệu Excel nhập
      1 lần đầu dự án, KHÔNG tự làm mới (DNH-x-MCNA/backend/report_templates.py::_customer_receivable).
      Chính công thức cũ đó từng thổi nợ 1 khách lên 9,17 tỷ trong khi thật là 0,61 tỷ.
      => Nếu tại demo khách hỏi chatbot về công nợ, con số sẽ MÂU THUẪN với báo cáo. Phải xử lý
         trước 09/08 (xem kế hoạch: vá tạm bằng cảnh báo, hoặc port hẳn SP gốc sang chatbot).""")


def section_crosscheck(p):
    """Đối chiếu chéo: các con số trong file này phải khớp báo cáo định kỳ. Lệch = script sai."""
    print(f"\n{SEP}\nĐỐI CHIẾU CHÉO VỚI BÁO CÁO ĐỊNH KỲ (tự kiểm tra script này)\n{SEP}")
    m = get_monthly_digest_metrics(region=None, channel=None)
    r = m["revenue"]
    m_start, m_end, _ = p["thang_nay"]
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
    p = periods()
    print(SEP)
    print("ĐÁP ÁN ĐÚNG CHO DEMO #1 CHATBOT — nguồn: Bravo (qua đúng hàm của báo cáo định kỳ)")
    print(f"Chạy lúc: {datetime.now().strftime('%H:%M %d/%m/%Y')}")
    print(f"Kỳ 'tháng này':  {p['thang_nay'][2]}")
    print(f"Kỳ 'tháng trước': {p['thang_truoc'][2]}")
    print(f"Kỳ 'tuần trước':  {p['tuan_truoc'][2]}")
    print(f"Kỳ 'hôm qua':     {p['hom_qua'][2]}")
    print("Dùng ĐÚNG các mốc ngày trên khi hỏi chatbot — hỏi lệch ngày thì lệch số là đương nhiên.")
    print(SEP)

    ok = True
    for fn in (section_clevel, section_kpi, section_regional, section_etc, section_receivables):
        try:
            fn(p)
        except Exception as e:
            ok = False
            print(f"\n  [LỖI] {fn.__name__}: {e}")
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
