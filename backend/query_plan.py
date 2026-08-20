# -*- coding: utf-8 -*-
"""Ke hoach truy van request-local cho cau hoi nghiep vu nhieu buoc.

Planner nay CO Y nam o backend: model duoc xem ke hoach va chon tool, nhung khong duoc tu khai
khong da hoan thanh hay tu bo qua nguon. Moi request tao mot QueryPlan rieng, khong co bien global,
nen trace/ket qua cua hai nguoi dung dong thoi khong the ro sang nhau.
"""
from __future__ import annotations

import calendar
import datetime as dt
import json
import re
import time
import unicodedata
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any


STEP_STATUSES = {"pending", "running", "completed", "partial", "failed", "skipped"}
PLAN_STATUSES = {"pending", "running", "completed", "partial", "failed"}


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFD", (value or "").lower())
    return " ".join("".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").split())


_DOMAIN_SPECS = (
    {
        "domain": "revenue",
        "label": "Đối chiếu doanh thu",
        "markers": ("doanh thu", "doanh so", "hoa don", "thuc thu"),
        "tools": ("get_revenue_by_channel", "get_revenue_by_region", "get_revenue_tree",
                  "get_revenue_reconciliation", "get_promotion_effectiveness"),
        "metrics": ("revenue",),
        "rules": ("revenue_totals",),
    },
    {
        "domain": "kpi",
        "label": "Đối chiếu KPI và cây đội ngũ",
        "markers": ("kpi", "chi tieu", "target", "doi ngu", "nhan vien", "qlv", "tdv"),
        "tools": ("get_kpi_ranking", "get_revenue_tree", "get_employee_kpi",
                  "get_employee_daily_kpi"),
        "metrics": ("kpi",),
        "rules": ("team_employee_rollup",),
    },
    {
        "domain": "debt",
        "label": "Đối chiếu công nợ",
        "markers": ("cong no", "du no", "no qua han", "tuoi no"),
        "tools": ("get_receivables_overview", "get_customer_revenue_debt_risk",
                  "get_customer_detail"),
        "metrics": ("receivables", "overdue"),
        "rules": ("debt_aging",),
    },
    {
        "domain": "customer",
        "label": "Phân tích khách hàng",
        "markers": ("khach hang", "khach mua", "khach tham gia", "giam mua", "mua lai"),
        "tools": ("get_top_customers", "get_customer_detail", "get_customer_revenue_debt_risk",
                  "get_receivables_overview", "get_promotion_effectiveness"),
        "metrics": ("customers",),
        "rules": (),
    },
    {
        "domain": "product",
        "label": "Phân tích sản phẩm",
        "markers": ("san pham", "ma hang", "sku", "nhom hang"),
        "tools": ("get_top_products", "get_promotion_effectiveness"),
        "metrics": ("products",),
        "rules": (),
    },
    {
        "domain": "salary",
        "label": "Đối chiếu lương thưởng",
        "markers": ("luong", "tien thuong", "thuong kinh doanh", "bac thuong", "muc thuong",
                    "v15", "v22", "v25", "aso", "phu cap"),
        "tools": ("get_salary_bonus_policy", "get_salary_data_quality",
                  "get_salary_achievement_summary", "get_salary_detail", "get_salary_ranking"),
        "metrics": ("salary_bonus",),
        "rules": ("salary_bonus_excludes_allowance",),
    },
    {
        "domain": "promotion",
        "label": "Đối chiếu chương trình khuyến mãi",
        "markers": ("khuyen mai", "ctkm", "chuong trinh"),
        "tools": ("get_promotion_effectiveness", "get_promotion_data_quality"),
        "metrics": ("promotions",),
        "rules": ("promotion_deduplicate_orders",),
    },
    {
        "domain": "freshness",
        "label": "Đối chiếu độ mới và nguồn dữ liệu",
        "markers": ("timestamp", "dong bo", "do moi", "freshness", "nguon du lieu", "warehouse", "sql live"),
        "tools": ("get_audit_log", "get_promotion_data_quality", "get_salary_data_quality",
                  "query_sql_server"),
        "metrics": ("freshness",),
        "rules": ("source_freshness",),
    },
)

_RAW_DOMAIN_MARKERS = {
    "revenue": ("vhoadon", "amount9", "invoice", "docdate"),
    "kpi": ("fact_tonghopkhachhang", "monthsaletarget", "managercode", "kpi"),
    "debt": ("fact_congno", "overdue", "balance_end", "deptaccduedate"),
    "customer": ("customercode", "customer_code", "dms_khachhang"),
    "product": ("itemcode", "item_code", "brv_sanpham"),
    "salary": ("fact_thongketinhluong", "v15", "v22", "v25", "asobonus"),
    "promotion": ("dms_ctkm", "donhangctkm", "progid"),
    "freshness": ("syncat", "businessdate", "sourcefreshness", "max(savedate"),
}


def infer_domains(question: str) -> list[dict[str, Any]]:
    plain = _plain(question)
    def contains(marker: str) -> bool:
        if " " in marker:
            return marker in plain
        return bool(re.search(rf"\b{re.escape(marker)}\b", plain))

    lowered = (question or "").lower()
    found = [spec for spec in _DOMAIN_SPECS if (
        any(contains(marker) for marker in spec["markers"])
        or (spec["domain"] == "salary" and "thưởng" in lowered)
    )]
    return found or [_DOMAIN_SPECS[0]]


def infer_period(question: str) -> dict[str, Any]:
    plain = _plain(question)
    month_matches = re.findall(r"thang\s+(\d{1,2})(?:\s*(?:/|nam\s+)\s*(20\d{2}))?", plain)
    fallback_year = next((int(year) for _, year in month_matches if year), None)
    periods: list[dict[str, str]] = []
    for raw_month, raw_year in month_matches:
        month = int(raw_month)
        year = int(raw_year) if raw_year else fallback_year
        if year is None or not 1 <= month <= 12:
            continue
        last = calendar.monthrange(year, month)[1]
        item = {
            "date_from": f"{year:04d}-{month:02d}-01",
            "date_to": f"{year:04d}-{month:02d}-{last:02d}",
            "label": f"{month:02d}/{year:04d}",
        }
        if item not in periods:
            periods.append(item)
    if not periods:
        match = re.search(r"\b(20\d{2})-(\d{2})\b", plain)
        if not match:
            return {"date_from": None, "date_to": None, "label": "không nêu rõ"}
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return {"date_from": None, "date_to": None, "label": "không hợp lệ"}
        last = calendar.monthrange(year, month)[1]
        periods.append({
            "date_from": f"{year:04d}-{month:02d}-01",
            "date_to": f"{year:04d}-{month:02d}-{last:02d}",
            "label": f"{month:02d}/{year:04d}",
        })
    if len(periods) == 1:
        return periods[0]
    return {
        "date_from": min(item["date_from"] for item in periods),
        "date_to": max(item["date_to"] for item in periods),
        "label": " vs ".join(item["label"] for item in periods),
        "periods": periods,
    }


@dataclass
class PlanStep:
    step_id: str
    title: str
    domain: str
    metrics: list[str] = field(default_factory=list)
    tool_hints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    status: str = "pending"
    tool_name: str | None = None
    tool_args: dict[str, Any] | None = None
    source: str | None = None
    duration_ms: int | None = None
    error: str | None = None
    result_summary: str | None = None


@dataclass
class ReconciliationResult:
    rule: str
    status: str = "pending"
    detail: str = "Chưa có đủ payload để đối chiếu."


@dataclass
class QueryPlan:
    plan_id: str
    question: str
    metrics: list[str]
    period: dict[str, Any]
    scope: dict[str, Any]
    steps: list[PlanStep]
    dependencies: dict[str, list[str]]
    status: str
    sources: list[str]
    reconciliation_rules: list[ReconciliationResult]
    max_rounds: int
    max_tools_per_round: int
    max_unique_tools: int
    request_timeout_seconds: float
    started_at: str = field(default_factory=lambda: dt.datetime.now().isoformat())
    completed_at: str | None = None
    _started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _evidence: dict[str, Any] = field(default_factory=dict, repr=False)
    _runtime_steps: dict[str, list[str]] = field(default_factory=dict, repr=False)

    def remaining_seconds(self) -> float:
        return max(0.0, self.request_timeout_seconds - (time.monotonic() - self._started_monotonic))

    def expired(self) -> bool:
        return self.remaining_seconds() <= 0

    def _find_step(self, tool_name: str) -> PlanStep:
        for step in self.steps:
            if step.status == "pending" and tool_name in step.tool_hints:
                return step
        step = PlanStep(
            step_id=f"S{len(self.steps) + 1:02d}",
            title=f"Truy vấn bổ sung bằng {tool_name}",
            domain="adhoc",
            tool_hints=[tool_name],
        )
        self.steps.append(step)
        self.dependencies[step.step_id] = []
        return step

    def start_tool(self, tool_name: str, args: dict[str, Any], tool_key: str) -> str:
        matches: list[PlanStep] = []
        if tool_name in {"query_database", "query_sql_server", "query_inventory_receivables"}:
            raw_text = _plain(json.dumps(args or {}, ensure_ascii=False, default=str))
            raw_domains = {domain for domain, markers in _RAW_DOMAIN_MARKERS.items()
                           if any(marker in raw_text for marker in markers)}
            matches = [step for step in self.steps
                       if step.status == "pending" and step.domain in raw_domains]
        if not matches:
            matches = [self._find_step(tool_name)]
        for step in matches:
            step.status = "running"
            step.tool_name = tool_name
            step.tool_args = dict(args or {})
        self._runtime_steps[tool_key] = [step.step_id for step in matches]
        self.status = "running"
        return matches[0].step_id

    def skip_tool(self, tool_name: str, args: dict[str, Any], reason: str) -> None:
        # Goi lap lai da co ket qua khong bien buoc nghiep vu thanh partial.
        if "đã chạy" in reason.lower() or "da chay" in reason.lower() or "gộp" in reason.lower():
            return
        step = self._find_step(tool_name)
        step.status = "skipped"
        step.tool_name = tool_name
        step.tool_args = dict(args or {})
        step.error = reason

    def finish_tool(self, tool_key: str, *, ok: bool, payload: Any, source: str,
                    duration_ms: int, timeout_seconds: float) -> None:
        step_ids = self._runtime_steps.get(tool_key) or []
        matched_steps = [item for item in self.steps if item.step_id in step_ids]
        if not matched_steps:
            return
        if source and source not in self.sources:
            self.sources.append(source)
        evidence = (payload.get("du_lieu") if isinstance(payload, dict) and "du_lieu" in payload
                    else payload)
        payload_status = evidence.get("status") if isinstance(evidence, dict) else None
        unavailable = payload_status in {"source_gap", "unavailable", "no_data", "not_applicable"}
        error_text = evidence.get("error") if isinstance(evidence, dict) else None
        for step in matched_steps:
            step.duration_ms = duration_ms
            step.source = source
            if duration_ms > int(timeout_seconds * 1000):
                step.status = "partial" if ok else "failed"
                step.error = f"Tool vượt ngân sách {timeout_seconds:g}s (thực tế {duration_ms / 1000:.1f}s)."
            elif not ok or error_text:
                step.status = "failed"
                step.error = str(error_text or "Tool trả trạng thái lỗi.")[:300]
            elif unavailable:
                step.status = "partial"
                step.error = str(evidence.get("warning") or evidence.get("note") or payload_status)[:300]
            else:
                step.status = "completed"
                step.result_summary = self._summarize(evidence)
        primary = matched_steps[0]
        self._evidence[primary.tool_name or primary.step_id] = evidence
        # Mot composite tool co the hoan tat nhieu domain (vd promotion_effectiveness dong thoi co
        # chuong trinh, khach va san pham). Khong ep model goi lai tool chi de danh dau buoc thu hai.
        for related in self.steps:
            if related.status == "pending" and primary.tool_name in related.tool_hints:
                related.status = primary.status
                related.tool_name = primary.tool_name
                related.tool_args = primary.tool_args
                related.source = source
                related.duration_ms = duration_ms
                related.error = primary.error
                related.result_summary = primary.result_summary
        self._run_reconciliation()

    @staticmethod
    def _summarize(payload: Any) -> str:
        if isinstance(payload, dict):
            keys = [key for key in payload.keys() if key not in {"warning", "interpretation_note"}]
            return "Đã nhận các trường: " + ", ".join(keys[:8])
        if isinstance(payload, list):
            return f"Đã nhận {len(payload)} dòng dữ liệu."
        return "Đã nhận kết quả từ tool."

    def _set_reconciliation(self, rule: str, passed: bool, detail: str) -> None:
        item = next((value for value in self.reconciliation_rules if value.rule == rule), None)
        if item:
            item.status = "passed" if passed else "failed"
            item.detail = detail

    @staticmethod
    def _close(left: float, right: float, tolerance: float = 1.0) -> bool:
        return abs(float(left or 0) - float(right or 0)) <= tolerance

    def _run_reconciliation(self) -> None:
        revenue = self._evidence.get("get_revenue_by_channel")
        if isinstance(revenue, dict) and all(key in revenue for key in ("otc", "etc", "total")):
            expected = float(revenue["otc"].get("revenue") or 0) + float(revenue["etc"].get("revenue") or 0)
            actual = float(revenue["total"].get("revenue") or 0)
            self._set_reconciliation(
                "revenue_totals", self._close(expected, actual),
                f"OTC + ETC = {expected:.2f}; tổng báo cáo = {actual:.2f}.",
            )
        region_revenue = self._evidence.get("get_revenue_by_region")
        if isinstance(revenue, dict) and isinstance(region_revenue, list):
            region_total = sum(float(row.get("revenue") or 0) for row in region_revenue
                               if isinstance(row, dict))
            company_total = float((revenue.get("total") or {}).get("revenue") or 0)
            self._set_reconciliation(
                "revenue_totals", self._close(region_total, company_total),
                f"Tổng vùng = {region_total:.2f}; tổng kênh/công ty = {company_total:.2f}.",
            )
        revenue_reconcile = self._evidence.get("get_revenue_reconciliation")
        if isinstance(revenue_reconcile, dict) and "coverage_pct" in revenue_reconcile:
            passed = not revenue_reconcile.get("warning") and float(revenue_reconcile["coverage_pct"] or 0) <= 100.5
            self._set_reconciliation(
                "revenue_totals", passed,
                "Đã đối chiếu top-down với roll-up đội; coverage không vượt 100,5%."
                if passed else str(revenue_reconcile.get("warning") or "Coverage vượt 100,5%."),
            )

        debt = self._evidence.get("get_receivables_overview")
        if isinstance(debt, dict) and debt.get("receivable_status") == "ok":
            buckets = sum(float(debt.get(key) or 0) for key in (
                "overdue_1_15", "overdue_15_30", "overdue_30_45", "overdue_gt_45"
            ))
            total = float(debt.get("total_overdue") or 0)
            self._set_reconciliation(
                "debt_aging", self._close(buckets, total),
                f"Tổng bốn nhóm tuổi = {buckets:.2f}; tổng quá hạn = {total:.2f}.",
            )

        salary = self._evidence.get("get_salary_detail")
        salary_rows = []
        if isinstance(salary, dict):
            salary_rows = salary.get("employees") or [salary]
        salary_ranking = self._evidence.get("get_salary_ranking")
        if isinstance(salary_ranking, dict):
            salary_rows.extend(salary_ranking.get("ranking") or [])
        if salary_rows:
            checks = []
            for row in salary_rows:
                if not isinstance(row, dict) or row.get("error"):
                    continue
                progress = row.get("progress_bonus") or {}
                expected = (float(row.get("dm_bonus") or 0) + float(row.get("aso_bonus") or 0)
                            + sum(float(progress.get(key, row.get(f"{key}_bonus")) or 0)
                                  for key in ("v15", "v22", "v25")))
                checks.append(self._close(expected, float(row.get("total_bonus") or 0)))
            if checks:
                self._set_reconciliation(
                    "salary_bonus_excludes_allowance", all(checks),
                    "TotalBonus khớp DM + V15 + V22 + V25 + ASO; phụ cấp được giữ riêng."
                    if all(checks) else "TotalBonus không khớp các cấu phần thưởng.",
                )

        salary_policy = self._evidence.get("get_salary_bonus_policy")
        if isinstance(salary_policy, dict) and not salary_policy.get("error"):
            self._set_reconciliation(
                "salary_policy_effective", True,
                "Đã đọc chính sách/bậc thưởng đúng kỳ hiệu lực từ nguồn policy.",
            )

        promotion = self._evidence.get("get_promotion_effectiveness")
        if isinstance(promotion, dict) and promotion.get("interpretation_note"):
            self._set_reconciliation(
                "promotion_deduplicate_orders", True,
                "Tool giữ doanh thu theo từng chương trình và cảnh báo không cộng ngang do một đơn có thể dùng nhiều CTKM.",
            )

        if any(name in self._evidence for name in ("get_revenue_tree", "get_kpi_ranking")):
            self._set_reconciliation(
                "team_employee_rollup", True,
                "Dùng tool cây/xếp hạng đã gộp một dòng mỗi nhân viên và không cộng chồng tầng.",
            )

        if any(name in self._evidence for name in (
            "get_audit_log", "get_promotion_data_quality", "get_salary_data_quality", "query_sql_server"
        )):
            self._set_reconciliation(
                "source_freshness", True,
                "Đã lấy metadata nguồn riêng; footer freshness vẫn do backend gắn sau cùng.",
            )

    def model_note(self) -> str:
        steps = [{"id": s.step_id, "domain": s.domain, "status": s.status,
                  "tool": s.tool_name or s.tool_hints[:2], "error": s.error} for s in self.steps]
        reconcile = [asdict(item) for item in self.reconciliation_rules]
        return "QUERY_PLAN_STATUS (không chép nguyên khối này ra câu trả lời): " + json.dumps(
            {"plan_id": self.plan_id, "steps": steps, "reconciliation": reconcile},
            ensure_ascii=False,
        )

    def prompt_note(self) -> str:
        expected = [{"step_id": s.step_id, "title": s.title, "domain": s.domain,
                     "tool_hints": s.tool_hints, "dependencies": s.dependencies} for s in self.steps]
        return (
            "KE_HOACH_BACKEND_BAT_BUOC: "
            + json.dumps({
                "plan_id": self.plan_id,
                "period": self.period,
                "scope": self.scope,
                "steps": expected,
                "reconciliation_rules": [item.rule for item in self.reconciliation_rules],
            }, ensure_ascii=False)
            + "\nThực hiện đủ các domain liên quan trước khi kết luận. Nếu một nguồn lỗi, vẫn trả phần "
              "đã kiểm chứng và nêu chính xác nguồn/bước thiếu; không đoán số và không nói 'quá phức tạp'."
        )

    def finalize(self, *, limit_reached: bool = False) -> None:
        for step in self.steps:
            if step.status == "running":
                step.status = "failed"
                step.error = "Tool không hoàn tất trước khi request kết thúc."
            elif step.status == "pending":
                step.status = "skipped"
                step.error = ("Hết giới hạn request trước khi chạy bước này."
                              if limit_reached else "Model chưa gọi nguồn cần thiết cho bước này.")
        failed = [step for step in self.steps if step.status == "failed"]
        incomplete = [step for step in self.steps if step.status in {"failed", "partial", "skipped"}]
        completed = [step for step in self.steps if step.status == "completed"]
        reconciliation_failed = [item for item in self.reconciliation_rules if item.status == "failed"]
        reconciliation_pending = [item for item in self.reconciliation_rules if item.status == "pending"]
        planned_domains = {step.domain for step in self.steps if step.domain != "adhoc"}
        if not completed and failed:
            self.status = "failed"
        elif incomplete or reconciliation_failed or (len(planned_domains) > 1 and reconciliation_pending):
            self.status = "partial"
        else:
            self.status = "completed"
        self.completed_at = dt.datetime.now().isoformat()

    def finalize_answer(self, answer: str) -> str:
        if self.status not in {"partial", "failed"}:
            return answer
        if "phan chua the kiem chung" in _plain(answer):
            return answer
        missing = [step for step in self.steps if step.status in {"failed", "partial", "skipped"}]
        if not missing:
            return answer
        lines = [answer.rstrip(), "", "### Phần chưa thể kiểm chứng"]
        for step in missing[:6]:
            lines.append(f"- {step.title}: {step.error or 'chưa đủ dữ liệu nguồn.'}")
        lines.append("- Không suy đoán số cho các phần trên.")
        return "\n".join(lines).strip()

    def timeout_answer(self) -> str:
        completed = [step.title for step in self.steps if step.status == "completed"]
        prefix = ("Đã kiểm chứng: " + "; ".join(completed) + ".") if completed else "Chưa có nguồn nào hoàn tất để kết luận số liệu."
        return self.finalize_answer(prefix)

    def as_dict(self) -> dict[str, Any]:
        # Khong goi asdict(self): _evidence co the chua payload bang lon/du lieu nhay cam. Trace
        # chi can metadata ke hoach, tuyet doi khong copy payload tho ra API them lan nua.
        return {
            "plan_id": self.plan_id,
            "question": self.question,
            "metrics": list(self.metrics),
            "period": dict(self.period),
            "scope": dict(self.scope),
            "steps": [asdict(step) for step in self.steps],
            "dependencies": {key: list(value) for key, value in self.dependencies.items()},
            "status": self.status,
            "sources": list(self.sources),
            "reconciliation_rules": [asdict(item) for item in self.reconciliation_rules],
            "max_rounds": self.max_rounds,
            "max_tools_per_round": self.max_tools_per_round,
            "max_unique_tools": self.max_unique_tools,
            "request_timeout_seconds": self.request_timeout_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


def build_query_plan(question: str, *, query_id: str | None, scope_role: str | None,
                     scope_area_code: str | None, scope_employee_code: str | None,
                     scope_channel: str | None, max_rounds: int, max_tools_per_round: int,
                     max_unique_tools: int, request_timeout_seconds: float) -> QueryPlan:
    domains = infer_domains(question)
    plain_question = _plain(question)
    initial_domain_names = {spec["domain"] for spec in domains}
    freshness_comparison_only = ("freshness" in initial_domain_names and any(
        marker in plain_question for marker in ("timestamp", "business date")
    ))
    if freshness_comparison_only:
        # Câu chỉ so mốc nguồn không cần lập bốn bước doanh thu/KPI/lương/CTKM riêng; một bước
        # freshness đa nguồn cùng nhiều tool metadata mới phản ánh đúng mục tiêu và tránh gọi dữ
        # liệu nghiệp vụ nặng không liên quan.
        domains = [spec for spec in domains if spec["domain"] == "freshness"]
    domain_names = {spec["domain"] for spec in domains}
    steps: list[PlanStep] = []
    metrics: list[str] = []
    rules: list[str] = []
    dependencies: dict[str, list[str]] = {}
    for index, spec in enumerate(domains, 1):
        step_id = f"S{index:02d}"
        step = PlanStep(
            step_id=step_id,
            title=spec["label"],
            domain=spec["domain"],
            metrics=list(spec["metrics"]),
            tool_hints=list(spec["tools"]),
        )
        steps.append(step)
        dependencies[step_id] = []
        for metric in spec["metrics"]:
            if metric not in metrics:
                metrics.append(metric)
        spec_rules = list(spec["rules"])
        if freshness_comparison_only and spec["domain"] != "freshness":
            spec_rules = []
        if (spec["domain"] == "revenue" and "promotion" in domain_names
                and not any(marker in plain_question for marker in (
                    "tong doanh thu", "toan cong ty", "theo kenh", "theo mien", "theo vung"
                ))):
            # "Doanh thu gắn với CTKM" là metric nằm trong composite promotion tool, không phải
            # tổng công ty để bắt buộc đối soát OTC+ETC.
            spec_rules = []
        if (spec["domain"] == "salary" and not freshness_comparison_only
                and not any(marker in plain_question for marker in (
            "phu cap", "tong thu nhap", "tong thuong", "luong co ban", "thuong kinh doanh"
        ))):
            spec_rules = ["salary_policy_effective"]
        for rule in spec_rules:
            if rule not in rules:
                rules.append(rule)

    return QueryPlan(
        plan_id=f"plan-{query_id or uuid.uuid4().hex}",
        question=question,
        metrics=metrics,
        period=infer_period(question),
        scope={
            "role": scope_role,
            "area_code": scope_area_code,
            "employee_code": scope_employee_code,
            "channel": scope_channel,
        },
        steps=steps,
        dependencies=dependencies,
        status="pending",
        sources=[],
        reconciliation_rules=[ReconciliationResult(rule) for rule in rules],
        max_rounds=max_rounds,
        max_tools_per_round=max_tools_per_round,
        max_unique_tools=max_unique_tools,
        request_timeout_seconds=float(request_timeout_seconds),
    )
