import pandas as pd
from datetime import datetime


def get_sales_and_kpi_analytics():
    """
    Phân tích so sánh hiệu suất KPI doanh số theo cấp bậc quản lý (TP/PP/QLV) và Top/Bottom
    TDV-CTV-CS — đọc thẳng kpi_summary trên Supabase (snapshot hiện tại, không có cột kỳ/period
    lịch sử).

    LƯU Ý: trước đây hàm này còn suy luận thêm phần chia theo KÊNH (OTC/ETC) bằng cách join
    receivable_etc/kpi_sales_customer — 2 bảng này chỉ tồn tại trong CSDL trung gian SQLite cũ
    (dnh_intermediate.db, đã phát hiện bị đóng băng dữ liệu, không dùng nữa), không có trên
    Supabase. Bản cũ còn có fallback tự chế số liệu giả (nhân 0.65/0.62) khi dữ liệu chỉ ra 1
    kênh — không đủ tin cậy để đưa vào báo cáo thật nên đã bỏ hẳn. Cần DNH xác nhận cách xác
    định kênh theo nhân sự trên dữ liệu Bravo thật trước khi thêm lại phần này.
    """
    from sqlalchemy import text
    try:
        from src.database import _get_cloud_engine
    except Exception as e:
        return {"error": f"Không import được engine dữ liệu: {e}"}

    engine = _get_cloud_engine()
    if engine is None:
        return {"error": "Chưa cấu hình CLOUD_DB_URL."}

    try:
        with engine.connect() as conn:
            rows = conn.execute(text('''
                SELECT employee_code, employee_name, position_code,
                       month_sale_target, month_sale_amount, month_sale_percent
                FROM kpi_summary
            ''')).fetchall()
    except Exception as e:
        return {"error": f"Lỗi truy vấn kpi_summary: {e}"}

    if not rows:
        return {"error": "kpi_summary rỗng."}

    df_kpi = pd.DataFrame(rows, columns=[
        "employee_code", "employee_name", "position_code",
        "month_sale_target", "month_sale_amount", "month_sale_percent"
    ])

    # So sánh hiệu suất nội bộ giữa các Trưởng phòng (TP), Phó phòng (PP), Quản lý vùng (QLV)
    df_tp = df_kpi[df_kpi['position_code'] == 'TP'].sort_values(by='month_sale_percent', ascending=False)
    df_pp = df_kpi[df_kpi['position_code'] == 'PP'].sort_values(by='month_sale_percent', ascending=False)
    df_qlv = df_kpi[df_kpi['position_code'] == 'QLV'].sort_values(by='month_sale_percent', ascending=False)

    # Top/Bottom Trình dược viên & Cộng tác viên (TDV, CTV, CS)
    df_reps = df_kpi[df_kpi['position_code'].isin(['TDV', 'CTV', 'CS'])]
    top_reps = df_reps.sort_values(by='month_sale_percent', ascending=False).head(3)
    bottom_reps = df_reps.sort_values(by='month_sale_percent', ascending=True).head(3)

    return {
        "latest_period": datetime.now().strftime("%m/%Y"),
        "tps": df_tp.to_dict(orient='records'),
        "pps": df_pp.to_dict(orient='records'),
        "qlvs": df_qlv.to_dict(orient='records'),
        "top_reps": top_reps.to_dict(orient='records'),
        "bottom_reps": bottom_reps.to_dict(orient='records')
    }
