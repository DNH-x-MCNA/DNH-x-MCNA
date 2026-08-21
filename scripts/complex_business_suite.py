# -*- coding: utf-8 -*-
"""Mười câu tổng hợp cho gate planner ngày 22/08/2026.

Mỗi ``expected_tool_groups`` là một nhóm lựa chọn: chatbot phải gọi ít nhất một tool trong từng
nhóm. Không khóa cứng đúng một đường đi vì composite tool có thể thay nhiều truy vấn nhỏ. SQL
ground truth vẫn dùng checker độc lập của bộ golden 90 câu và luôn giao người kiểm đối chiếu phần
top/list; runner chỉ tự chấm những điều kiến trúc có thể chứng minh chắc chắn.
"""
from __future__ import annotations

from dataclasses import dataclass
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


@dataclass(frozen=True)
class ComplexCase:
    id: str
    group: str
    audience: str
    question: str
    expected_domains: tuple[str, ...]
    expected_tool_groups: tuple[tuple[str, ...], ...]
    reconciliation_rules: tuple[str, ...]
    checker_ids: tuple[str, ...]
    min_completed_steps: int = 2
    max_rounds: int = 10
    timeout: int = 120
    allow_partial: bool = False
    simulated_failure_tool: str | None = None


CASES = [
    ComplexCase(
        "C001", "Điều hành đa nguồn", "c_level",
        "Tháng 7/2026, so sánh doanh thu, mức hoàn thành KPI và nợ quá hạn theo ba miền; "
        "chỉ ra miền cần ưu tiên và đối chiếu tổng vùng với tổng công ty trước khi kết luận.",
        ("revenue", "kpi", "debt"),
        (("get_revenue_by_region",), ("get_kpi_ranking", "get_revenue_tree"),
         ("get_receivables_overview",)),
        ("revenue_totals", "team_employee_rollup", "debt_aging"),
        ("REV_REGION", "KPI_MANAGER", "DEBT_AREA"),
        min_completed_steps=3,
    ),
    ComplexCase(
        "C002", "Khách hàng giảm mua", "c_level",
        "Từ doanh thu tháng 7/2026, tìm nhóm khách hàng giảm mua so với giai đoạn trước, nêu mức "
        "ảnh hưởng lên tổng doanh thu và tách rõ phần đã kiểm chứng với phần chưa đủ dữ liệu.",
        ("revenue", "customer"),
        (("get_revenue_by_channel", "get_revenue_by_region"),
         ("get_top_customers", "get_customer_revenue_debt_risk", "query_database", "query_sql_server")),
        ("revenue_totals",),
        ("REV_COMPARE", "CUS_TREND"),
    ),
    ComplexCase(
        "C003", "KPI và lương thưởng", "c_level",
        "Đối chiếu KPI tháng 7/2026 với điều kiện thưởng V25 và ASO: nhóm nào đạt KPI nhưng chưa "
        "phát sinh thưởng, chính sách nào áp dụng và có bất thường dữ liệu nào cần kiểm tra?",
        ("kpi", "salary"),
        (("get_kpi_ranking", "get_employee_kpi"),
         ("get_salary_bonus_policy",),
         ("get_salary_achievement_summary", "get_salary_data_quality", "get_salary_detail")),
        ("team_employee_rollup", "salary_policy_effective"),
        ("KPI_THRESHOLDS", "SALARY_RULES", "SALARY_ACHIEVEMENT"),
        min_completed_steps=3,
    ),
    ComplexCase(
        "C004", "CTKM đa chiều", "c_level",
        "Trong tháng 12/2025, phân tích chương trình khuyến mãi theo khách tham gia, sản phẩm điều "
        "kiện/quà tặng và doanh thu gắn với đơn; không cộng chồng doanh thu và không gọi đó là ROI.",
        ("promotion", "customer", "product", "revenue"),
        (("get_promotion_effectiveness",),),
        ("promotion_deduplicate_orders",),
        ("PROMO_EFFECT", "PROMO_CUSTOMERS", "PROMO_PRODUCTS"),
        min_completed_steps=4,
    ),
    ComplexCase(
        "C005", "Nhiều vùng nhiều kỳ", "c_level",
        "So sánh doanh thu ba miền giữa tháng 6 và tháng 7/2026, tách OTC/ETC, nêu miền thay đổi "
        "mạnh nhất và đối chiếu tổng các miền với tổng công ty ở từng kỳ.",
        ("revenue",),
        (("get_revenue_by_region",), ("get_revenue_by_channel",)),
        ("revenue_totals",),
        ("REV_REGION", "REV_COMPARE"),
        min_completed_steps=2,
    ),
    ComplexCase(
        "C006", "Phạm vi đội QLV", "qlv",
        "Trong đúng phạm vi đội tôi tháng 7/2026, đối chiếu doanh thu, KPI và thưởng kinh doanh; "
        "nêu người cần ưu tiên nhưng không để lộ dữ liệu cá nhân ngoài đội.",
        ("revenue", "kpi", "salary"),
        (("get_revenue_by_channel", "get_revenue_by_region"),
         ("get_revenue_tree", "get_kpi_ranking"),
         ("get_salary_ranking", "get_salary_detail", "get_salary_achievement_summary")),
        ("team_employee_rollup",),
        ("KPI_EMPLOYEE", "SALARY_RANK"),
        min_completed_steps=3,
    ),
    ComplexCase(
        "C007", "Warehouse và SQL live", "c_level",
        "Đối chiếu doanh thu tháng 7/2026 giữa warehouse và SQL Server live, chỉ rõ kỳ, nguồn, "
        "độ phủ cây nhân sự và mọi chênh lệch trước khi kết luận.",
        ("revenue", "freshness"),
        (("get_revenue_reconciliation",), ("query_sql_server", "get_audit_log")),
        ("revenue_totals", "source_freshness"),
        ("REV_RECONCILE", "SOURCE_FRESHNESS"),
    ),
    ComplexCase(
        "C008", "Bất thường dữ liệu", "c_level",
        "Phát hiện bất thường tháng 7/2026 khi tổng doanh thu theo tầng nhân sự, KPI và hóa đơn "
        "không khớp; phân biệt gap tổ chức đã biết với dấu hiệu đếm trùng thực sự.",
        ("revenue", "kpi"),
        (("get_revenue_reconciliation",), ("get_revenue_tree", "get_kpi_ranking")),
        ("revenue_totals", "team_employee_rollup"),
        ("KPI_LAYER_RECON", "REV_RECONCILE"),
    ),
    ComplexCase(
        "C009", "Freshness đa nguồn", "c_level",
        "So sánh timestamp và business date của doanh thu, KPI, lương và khuyến mãi; nguồn nào "
        "chậm hoặc thiếu coverage phải được cảnh báo riêng, không dùng timestamp nguồn khác thay thế.",
        ("freshness",),
        (("get_salary_data_quality",), ("get_promotion_data_quality",),
         ("get_audit_log", "query_sql_server", "query_database")),
        ("source_freshness",),
        ("SOURCE_FRESHNESS", "PROMO_COVERAGE", "SALARY_SNAPSHOTS"),
        min_completed_steps=3,
    ),
    ComplexCase(
        "C010", "Partial answer khi nguồn lỗi", "c_level",
        "So sánh doanh thu và công nợ theo miền trong tháng 7/2026. Nếu một nguồn lỗi giữa quy "
        "trình, vẫn trả phần đã kiểm chứng, nêu đúng bước/nguồn thất bại và tuyệt đối không đoán số.",
        ("revenue", "debt"),
        (("get_revenue_by_region", "get_revenue_by_channel"), ("get_receivables_overview",)),
        ("revenue_totals", "debt_aging"),
        ("REV_REGION", "DEBT_AREA"),
        allow_partial=True,
        simulated_failure_tool="get_receivables_overview",
    ),
]


def validate_catalog() -> list[str]:
    errors: list[str] = []
    expected_ids = [f"C{i:03d}" for i in range(1, 11)]
    if [case.id for case in CASES] != expected_ids:
        errors.append("Complex case ID phải liên tục C001..C010.")
    for case in CASES:
        if case.audience not in {"qlv", "regional_director", "c_level"}:
            errors.append(f"{case.id}: audience không hợp lệ.")
        if not case.expected_domains or not case.expected_tool_groups:
            errors.append(f"{case.id}: thiếu domain/tool expectation.")
        if case.max_rounds > 10 or case.timeout > 120:
            errors.append(f"{case.id}: vượt giới hạn vòng hoặc timeout.")
        if len(case.question) < 80:
            errors.append(f"{case.id}: câu hỏi chưa đủ tính tổng hợp.")
    return errors


if __name__ == "__main__":
    errors = validate_catalog()
    if errors:
        raise SystemExit("\n".join(errors))
    for case in CASES:
        print(f"{case.id} [{case.audience}] {case.question}")
    print(f"VALID: {len(CASES)} complex cases")
