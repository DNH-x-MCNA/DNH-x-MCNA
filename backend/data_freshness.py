# -*- coding: utf-8 -*-
"""Metadata do moi du lieu cho tung request chatbot.

Model chi duoc dung de tong hop noi dung nghiep vu. Backend ghi nhan nguon that
da duoc tool truy van, tu tinh moc du lieu/dong bo va tu gan footer. Cach nay
tranh timestamp cu trong lich su hoi thoai bi model sao chep sang cau tra loi moi.
"""
from __future__ import annotations

import os
import re
import sqlite3
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional


DEFAULT_STALE_MINUTES = 90


@dataclass(frozen=True)
class SourceFreshness:
    source_key: str
    source_type: str
    source_name: str
    business_data_date: Optional[str]
    sync_completed_at: Optional[str]
    snapshot_date: Optional[str]
    query_executed_at: str
    is_live: bool
    is_stale: bool
    warning: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _SourceSpec:
    key: str
    source_type: str
    name: str
    table: Optional[str] = None
    date_column: Optional[str] = None
    snapshot_column: Optional[str] = None
    live: bool = False


_SOURCES = {
    "sales_otc": _SourceSpec("sales_otc", "warehouse", "Doanh thu OTC", "vhoadon_otc", "doc_date"),
    "sales_etc": _SourceSpec("sales_etc", "warehouse", "Doanh thu ETC", "vhoadon_etc", "doc_date"),
    "kpi": _SourceSpec("kpi", "warehouse", "KPI kinh doanh", "fact_tonghopkhachhang", "save_date", "save_date"),
    "salary": _SourceSpec("salary", "warehouse", "Thưởng và phụ cấp", "fact_thongketinhluong", "save_date", "save_date"),
    "debt": _SourceSpec("debt", "warehouse", "Công nợ khách hàng", "fact_congno_khachhang", "snapshot_at", "snapshot_date"),
    "inventory": _SourceSpec("inventory", "warehouse", "Tồn kho", "brv_tonkhodk"),
    "employee": _SourceSpec("employee", "warehouse", "Danh mục nhân viên", "dim_nhanvien"),
    "warehouse": _SourceSpec("warehouse", "warehouse", "Kho dữ liệu chatbot"),
    "promotion_live": _SourceSpec("promotion_live", "sql_server", "Chương trình khuyến mãi DMS trên SQL Server", live=True),
    "salary_policy_live": _SourceSpec("salary_policy_live", "sql_server", "Quy tắc thưởng trên SQL Server", live=True),
    "sql_server": _SourceSpec("sql_server", "sql_server", "SQL Server NH_Report_TM", live=True),
    "audit": _SourceSpec("audit", "operational", "Nhật ký truy vấn nội bộ", live=True),
}


_TEMPLATE_SOURCES = {
    "get_revenue_by_channel": ("sales_otc", "sales_etc"),
    "get_top_products": ("sales_otc", "sales_etc"),
    "get_top_customers": ("sales_otc", "sales_etc"),
    "get_revenue_by_region": ("sales_otc", "sales_etc"),
    "compare_periods": ("sales_otc", "sales_etc"),
    "check_order_timing": ("sales_otc", "sales_etc"),
    "get_revenue_reconciliation": ("sales_otc", "sales_etc", "kpi"),
    "get_employee_kpi": ("kpi",),
    "get_employee_daily_kpi": ("sales_otc", "kpi"),
    "get_employee_directory": ("employee",),
    "get_qlv_change_history": ("employee",),
    "get_revenue_tree": ("sales_otc", "sales_etc", "kpi"),
    "get_kpi_ranking": ("kpi",),
    "get_inventory_by_region": ("inventory",),
    "get_receivables_overview": ("debt",),
    "get_customer_detail": ("sales_otc", "sales_etc", "debt"),
    "get_customer_revenue_debt_risk": ("sales_otc", "sales_etc", "debt"),
    "get_promotion_effectiveness": ("promotion_live",),
    "get_salary_bonus_policy": ("salary_policy_live", "salary"),
    "get_salary_detail": ("salary",),
    "get_salary_achievement_summary": ("salary",),
    "get_salary_ranking": ("salary",),
    "get_audit_log": ("audit",),
}


_LOCAL_TABLE_SOURCES = {
    spec.table.lower(): key
    for key, spec in _SOURCES.items()
    if spec.source_type == "warehouse" and spec.table
}


def _default_warehouse_path() -> str:
    try:
        import local_warehouse
    except ImportError:  # package import trong pytest
        from . import local_warehouse
    return local_warehouse.DB_PATH


def _local_now() -> datetime:
    return datetime.now().astimezone()


def _iso(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return str(value)


def _parse_datetime(value: Any, *, end_of_day: bool = False) -> Optional[datetime]:
    if value in (None, ""):
        return None
    raw = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if len(raw) == 10 and end_of_day:
        parsed = parsed.replace(hour=23, minute=59, second=59)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def _first_value(payload: Any, keys: Iterable[str]) -> Optional[str]:
    wanted = {key.lower() for key in keys}
    stack = [payload]
    while stack:
        current = stack.pop(0)
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() in wanted and value not in (None, ""):
                    return _iso(value)
            stack.extend(value for value in current.values() if isinstance(value, (dict, list)))
        elif isinstance(current, list):
            stack.extend(current[:20])
    return None


def _format_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    return str(value)


def _format_datetime(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    parsed = _parse_datetime(value)
    if parsed:
        return parsed.strftime("%H:%M %d/%m/%Y")
    return str(value)


def _plain(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn").lower()


_TRAILING_MODEL_FRESHNESS = re.compile(
    r"(?:\r?\n|^)\s*[_*]{0,2}\s*(?:Dữ|Du)\s+liệu\s+(?:cập\s+nhật|cap\s+nhat)"
    r"[^\r\n]*[.!]?\s*[_*]{0,2}\s*$",
    re.IGNORECASE,
)


def strip_model_freshness_footer(answer: str) -> str:
    """Bo footer timestamp do model tu sinh, chi khi no nam o CUOI cau tra loi."""
    cleaned = (answer or "").rstrip()
    while True:
        updated = _TRAILING_MODEL_FRESHNESS.sub("", cleaned).rstrip()
        if updated == cleaned:
            break
        cleaned = updated

    # Idempotent khi finalize bi goi lai: bo footer backend cu o cuoi, khong xoa noi dung nghiep vu.
    lines = cleaned.splitlines()
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:
        tail = _plain(lines[-1].strip().strip("_* "))
        if tail.startswith("du lieu cap nhat"):
            lines.pop()
            cleaned = "\n".join(lines).rstrip()
            lines = cleaned.splitlines()
            while lines and not lines[-1].strip():
                lines.pop()
            tail = _plain(lines[-1].strip().strip("_* ")) if lines else ""
        if ("nguon du lieu:" in tail or "du lieu truc tiep:" in tail or
                "canh bao do moi:" in tail):
            lines.pop()
            while lines and _plain(lines[-1]).startswith("⚠️ canh bao do moi:"):
                lines.pop()
            cleaned = "\n".join(lines).rstrip()
    return cleaned


def render_freshness_footer(items: Iterable[SourceFreshness]) -> str:
    records = list(items)
    if not records:
        return ""
    rendered = []
    warnings = []
    for item in records:
        details = []
        data_date = _format_date(item.snapshot_date or item.business_data_date)
        if data_date:
            label = "snapshot" if item.snapshot_date else "dữ liệu đến"
            details.append(f"{label} {data_date}")
        if item.is_live:
            details.append(f"truy vấn lúc {_format_datetime(item.query_executed_at)}")
        elif item.sync_completed_at:
            details.append(f"đồng bộ lúc {_format_datetime(item.sync_completed_at)}")
        else:
            details.append(f"đọc lúc {_format_datetime(item.query_executed_at)}")
        rendered.append(f"{item.source_name} ({', '.join(details)})")
        if item.warning:
            warnings.append(item.warning)
    prefix = "Dữ liệu trực tiếp" if all(item.is_live for item in records) else "Nguồn dữ liệu"
    footer = f"_{prefix}: {'; '.join(rendered)}._"
    if warnings:
        footer = f"⚠️ Cảnh báo độ mới: {'; '.join(dict.fromkeys(warnings))}\n{footer}"
    return footer


class FreshnessCollector:
    """Bo gom cuc bo theo request; moi instance doc lap nen an toan khi chay dong thoi."""

    def __init__(
        self,
        *,
        warehouse_path: Optional[str] = None,
        stale_minutes: Optional[int] = None,
        now: Optional[Callable[[], datetime]] = None,
    ):
        self.warehouse_path = warehouse_path or _default_warehouse_path()
        configured = os.getenv("CHAT_FRESHNESS_STALE_MINUTES", str(DEFAULT_STALE_MINUTES))
        try:
            self.stale_minutes = max(1, int(stale_minutes if stale_minutes is not None else configured))
        except (TypeError, ValueError):
            self.stale_minutes = DEFAULT_STALE_MINUTES
        self._now = now or _local_now
        self._items: dict[str, SourceFreshness] = {}

    def _query_local_source(
        self, spec: _SourceSpec
    ) -> tuple[Optional[str], Optional[str], Optional[str], bool]:
        business_date = None
        snapshot_date = None
        sync_completed = None
        table_specific_sync = False
        path = Path(self.warehouse_path)
        if path.exists():
            sync_completed = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
        if not path.exists() or not spec.table:
            return business_date, snapshot_date, sync_completed, table_specific_sync
        try:
            conn = sqlite3.connect(str(path), timeout=5)
            try:
                if spec.date_column:
                    row = conn.execute(
                        f'SELECT MAX("{spec.date_column}") FROM "{spec.table}"'
                    ).fetchone()
                    business_date = _iso(row[0]) if row and row[0] is not None else None
                if spec.snapshot_column:
                    row = conn.execute(
                        f'SELECT MAX("{spec.snapshot_column}") FROM "{spec.table}"'
                    ).fetchone()
                    snapshot_date = _iso(row[0]) if row and row[0] is not None else None
                meta_exists = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sync_meta'"
                ).fetchone()
                if meta_exists:
                    row = conn.execute(
                        "SELECT last_synced_at, latest_synced_date FROM sync_meta WHERE table_name=?",
                        (spec.table,),
                    ).fetchone()
                    if row:
                        sync_completed = _iso(row[0]) or sync_completed
                        table_specific_sync = bool(row[0])
                        business_date = business_date or _iso(row[1])
            finally:
                conn.close()
        except (OSError, sqlite3.Error):
            pass
        return business_date, snapshot_date, sync_completed, table_specific_sync

    def _record_spec(self, spec: _SourceSpec, result: Any = None) -> None:
        if spec.key in self._items:
            return
        now = self._now()
        if now.tzinfo is None:
            now = now.astimezone()
        query_at = now.isoformat(timespec="seconds")
        business_date = _first_value(
            result,
            ("data_as_of", "actual_snapshot_date", "promotion_link_coverage_to", "coverage_date"),
        )
        snapshot_date = _first_value(
            result,
            ("snapshot_date", "save_date", "receivable_as_of", "receivable_snapshot_at"),
        )
        sync_completed = _first_value(result, ("promotion_link_synced_at", "link_synced_at"))
        table_specific_sync = False
        if spec.source_type == "warehouse":
            local_business, local_snapshot, local_sync, table_specific_sync = self._query_local_source(spec)
            # Moc bao phu phai doc RIENG tung bang. Khong de data_as_of chung cua tool doanh thu
            # (hien duoc tinh tu OTC) vo tinh gan sang ETC.
            business_date = local_business or business_date
            snapshot_date = snapshot_date or local_snapshot
            sync_completed = sync_completed or local_sync

        warning = None
        is_stale = False
        if not spec.live:
            sync_dt = _parse_datetime(sync_completed)
            if sync_dt is None:
                is_stale = True
                warning = f"{spec.name}: chưa xác định được thời điểm đồng bộ gần nhất."
            else:
                age_minutes = max(0, (now - sync_dt).total_seconds() / 60)
                if age_minutes > self.stale_minutes:
                    is_stale = True
                    warning = (
                        f"{spec.name}: lần đồng bộ gần nhất đã cách {age_minutes:.0f} phút "
                        f"(ngưỡng tạm thời {self.stale_minutes} phút)."
                    )
                elif spec.table and not table_specific_sync:
                    warning = (
                        f"{spec.name}: chưa có mốc đồng bộ riêng cho bảng; giờ hiển thị là "
                        "thời điểm cập nhật file warehouse."
                    )

        self._items[spec.key] = SourceFreshness(
            source_key=spec.key,
            source_type=spec.source_type,
            source_name=spec.name,
            business_data_date=business_date,
            sync_completed_at=sync_completed,
            snapshot_date=snapshot_date,
            query_executed_at=query_at,
            is_live=spec.live,
            is_stale=is_stale,
            warning=warning,
        )

    @staticmethod
    def _effective_channel(args: Optional[dict], scope_channel: Optional[str]) -> str:
        return str(scope_channel or (args or {}).get("channel") or "ALL").upper()

    def record_template(
        self,
        name: str,
        result: Any,
        *,
        args: Optional[dict] = None,
        scope_channel: Optional[str] = None,
    ) -> None:
        source_keys = list(_TEMPLATE_SOURCES.get(name, ()))
        channel = self._effective_channel(args, scope_channel)
        if channel in {"OTC", "ETC"}:
            excluded = "sales_etc" if channel == "OTC" else "sales_otc"
            source_keys = [key for key in source_keys if key != excluded]
        for source_key in source_keys:
            self._record_spec(_SOURCES[source_key], result)

    def record_raw(self, db: str, result: Any, sql: str = "") -> None:
        if db == "bravo":
            self._record_spec(_SOURCES["sql_server"], result)
            return
        matched = []
        lowered = (sql or "").lower()
        for table, source_key in _LOCAL_TABLE_SOURCES.items():
            if re.search(rf"\b{re.escape(table)}\b", lowered):
                matched.append(source_key)
        for source_key in dict.fromkeys(matched or ["warehouse"]):
            self._record_spec(_SOURCES[source_key], result)

    def records(self) -> list[SourceFreshness]:
        return list(self._items.values())

    def as_dicts(self) -> list[dict[str, Any]]:
        return [item.to_dict() for item in self.records()]

    def finalize_answer(self, answer: str) -> str:
        cleaned = strip_model_freshness_footer(answer)
        footer = render_freshness_footer(self.records())
        if not footer:
            return cleaned
        return f"{cleaned}\n\n{footer}" if cleaned else footer
