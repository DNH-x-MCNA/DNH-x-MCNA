import pandas as pd
from datetime import datetime, timedelta
from src.database import get_db_engines, load_config

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

def get_digest_metrics(start_dt, end_dt, period_label):
    """
    Tổng hợp dữ liệu trong khoảng [start_dt, end_dt) phục vụ digest định kỳ
    (dùng chung cho daily/weekly/monthly — xem get_daily_digest_metrics() etc. bên dưới).
    """
    erp_engine, crm_engine = get_db_engines()

    # 1. ERP - Số lượng và doanh thu đơn hàng hoàn thành trong kỳ
    orders_query = """
        SELECT status, amount
        FROM orders
        WHERE order_date >= :start_dt AND order_date < :end_dt
    """
    df_orders = pd.read_sql(orders_query, erp_engine, params={"start_dt": start_dt, "end_dt": end_dt})

    if not df_orders.empty:
        total_orders = len(df_orders)
        completed_orders = len(df_orders[df_orders['status'] == 'Completed'])
        failed_orders = len(df_orders[df_orders['status'] == 'Failed'])
        total_revenue = df_orders[df_orders['status'] == 'Completed']['amount'].sum()
    else:
        total_orders = 0
        completed_orders = 0
        failed_orders = 0
        total_revenue = 0.0

    # 2. ERP - Danh sách tồn kho thấp hiện tại (snapshot tại thời điểm chạy)
    config = load_config()
    inv_limit = config['thresholds']['erp']['low_inventory_limit']
    df_low_inv = get_low_inventory(erp_engine, inv_limit)

    # 3. CRM - Tổng hợp ticket trong kỳ
    tickets_query = """
        SELECT priority, status
        FROM support_tickets
        WHERE (created_at >= :start_dt AND created_at < :end_dt)
           OR (updated_at >= :start_dt AND updated_at < :end_dt)
    """
    df_tickets = pd.read_sql(tickets_query, crm_engine, params={"start_dt": start_dt, "end_dt": end_dt})

    total_tickets = len(df_tickets)
    resolved_tickets = len(df_tickets[df_tickets['status'] == 'Resolved'])
    open_tickets = len(df_tickets[df_tickets['status'] != 'Resolved'])

    urgent_open = len(df_tickets[(df_tickets['status'] != 'Resolved') & (df_tickets['priority'] == 'Urgent')])
    high_open = len(df_tickets[(df_tickets['status'] != 'Resolved') & (df_tickets['priority'] == 'High')])

    return {
        "date": end_dt.strftime("%d/%m/%Y"),
        "period_range": period_label,
        "erp": {
            "total_orders": total_orders,
            "completed_orders": completed_orders,
            "failed_orders": failed_orders,
            "total_revenue": round(total_revenue, 2),
            "low_inventory_count": len(df_low_inv),
            "low_inventory_items": df_low_inv.to_dict(orient='records')
        },
        "crm": {
            "total_tickets": total_tickets,
            "resolved_tickets": resolved_tickets,
            "open_tickets": open_tickets,
            "urgent_open": urgent_open,
            "high_open": high_open
        }
    }

def get_daily_digest_metrics():
    """Tổng hợp dữ liệu trong ngày phục vụ Daily Digest (Teams/Telegram)."""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    return get_digest_metrics(today_start, today_end, today_start.strftime("%d/%m/%Y"))

def get_weekly_digest_metrics():
    """Tổng hợp dữ liệu 7 ngày gần nhất phục vụ Weekly Report (Email)."""
    today_end = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    week_start = today_end - timedelta(days=7)
    label = f"Tuần {week_start.strftime('%d/%m/%Y')} - {(today_end - timedelta(days=1)).strftime('%d/%m/%Y')}"
    return get_digest_metrics(week_start, today_end, label)

def get_monthly_digest_metrics():
    """Tổng hợp dữ liệu từ đầu tháng hiện tại phục vụ Monthly Report (Email)."""
    now = datetime.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    label = f"Tháng {month_start.strftime('%m/%Y')} ({month_start.strftime('%d/%m')} - {(today_end - timedelta(days=1)).strftime('%d/%m/%Y')})"
    return get_digest_metrics(month_start, today_end, label)

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
