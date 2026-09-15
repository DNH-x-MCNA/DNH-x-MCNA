"""Phân công khách cho đội OTC, dùng chung giữa chatbot và báo cáo QLV."""

import datetime as dt


TEAM_CUSTOMER_WINDOW_DAYS = 200


def team_customer_codes(query, employee_code: str, day: dt.date,
                        window_days: int = TEAM_CUSTOMER_WINDOW_DAYS) -> set[str]:
    """Lấy phân công gần nhất của từng khách trước khi lọc đội, gồm khách QLV tự giữ.

    Không dùng danh sách khách mua trong tháng: khách ngừng mua vẫn có thể còn nợ.
    Tập rỗng chỉ có nghĩa chưa xác định được khách của đội; caller phải xử lý rõ.
    """
    rows = query(
        "WITH gan AS (SELECT customer_code, MAX(save_date) d FROM fact_tonghopkhachhang "
        "WHERE save_date<=? AND save_date>=? GROUP BY customer_code) "
        "SELECT DISTINCT f.customer_code FROM fact_tonghopkhachhang f "
        "JOIN gan ON gan.customer_code=f.customer_code AND gan.d=f.save_date "
        "WHERE f.manager_code=? OR f.employee_code=?",
        (day.isoformat(), (day - dt.timedelta(days=window_days)).isoformat(),
         employee_code, employee_code),
    )
    return {str(r["customer_code"]).strip() for r in rows
            if r.get("customer_code") and str(r["customer_code"]).strip()}
