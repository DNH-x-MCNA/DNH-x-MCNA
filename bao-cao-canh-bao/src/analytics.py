from datetime import datetime


def get_sales_and_kpi_analytics():
    """
    Phân tích so sánh hiệu suất KPI doanh số theo cấp bậc quản lý (TP/PP/QLV) và Top/Bottom
    TDV-CTV-CS.

    20/07/2026: bỏ hẳn Supabase `kpi_summary` — đối chiếu thực tế phát hiện bảng đó CHỈ có 6/20 QLV
    thật (dữ liệu import 1 lần từ đầu dự án, không bao giờ refresh — không phải lỗi 1 node đơn lẻ
    như từng nghĩ ở check_kpi_revenue_reconciliation_alert). Chuyển hẳn sang đọc TRỰC TIẾP Bravo:
    TDV/QLV/CTV/CS qua get_bravo_kpi_tdv_snapshot (FACT_TongHopKhachHang), TP/PP/TBP qua
    get_bravo_management_kpi_snapshot (FACT_ThongKeTinhLuong, xem docstring hàm đó về mức độ tin
    cậy). Không còn fallback Supabase — nếu Bravo lỗi, trả {"error": ...} thay vì hiện số liệu cũ/
    thiếu mà không ai biết là sai (cùng nguyên tắc với _period_revenue/get_bravo_receivables_
    snapshot: thà báo lỗi rõ ràng còn hơn số liệu có thể sai).

    LƯU Ý: trước đây hàm này còn suy luận thêm phần chia theo KÊNH (OTC/ETC) — đã bỏ hẳn từ trước
    (dữ liệu suy luận không đáng tin cậy), giữ nguyên quyết định đó.
    """
    from src.alerts import get_bravo_kpi_tdv_snapshot, get_bravo_management_kpi_snapshot

    try:
        reps_snapshot = get_bravo_kpi_tdv_snapshot(position_codes=('TDV', 'QLV', 'CTV', 'CS'))
    except Exception as e:
        return {"error": f"Lỗi lấy KPI TDV/QLV/CTV/CS từ Bravo: {e}"}

    try:
        mgmt_snapshot = get_bravo_management_kpi_snapshot(position_codes=('TP', 'PP', 'TBP'))
    except Exception as e:
        return {"error": f"Lỗi lấy KPI TP/PP/TBP từ Bravo: {e}"}

    def _sorted_by_pct(rows, reverse=True):
        return sorted(rows, key=lambda r: (r.month_sale_percent if r.month_sale_percent is not None else -1), reverse=reverse)

    def _to_dict(r):
        return {
            "employee_code": r.employee_code, "employee_name": r.employee_name,
            "position_code": r.position_code,
            "month_sale_target": r.month_sale_target, "month_sale_amount": r.month_sale_amount,
            "month_sale_percent": r.month_sale_percent,
        }

    tps = [r for r in mgmt_snapshot if r.position_code == 'TP']
    pps = [r for r in mgmt_snapshot if r.position_code == 'PP']
    qlvs = [r for r in reps_snapshot if r.position_code == 'QLV']
    reps = [r for r in reps_snapshot if r.position_code in ('TDV', 'CTV', 'CS')]

    top_reps = _sorted_by_pct(reps, reverse=True)[:3]
    bottom_reps = _sorted_by_pct(reps, reverse=False)[:3]

    return {
        "latest_period": datetime.now().strftime("%m/%Y"),
        "tps": [_to_dict(r) for r in _sorted_by_pct(tps)],
        "pps": [_to_dict(r) for r in _sorted_by_pct(pps)],
        "qlvs": [_to_dict(r) for r in _sorted_by_pct(qlvs)],
        "top_reps": [_to_dict(r) for r in top_reps],
        "bottom_reps": [_to_dict(r) for r in bottom_reps],
    }
