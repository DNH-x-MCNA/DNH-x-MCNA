# -*- coding: utf-8 -*-
"""Tim schema SQL Server lien quan theo tung cau hoi, khong nhan ca catalog vao prompt.

Catalog day du co gan 2.000 cot, qua lon de gui cho model moi luot. Module nay doc snapshot
metadata neu co, hoac build live mot lan va cache trong RAM, sau do xep hang object theo ten,
cot, mo ta va cac alias nghiep vu. Khong doc dong du lieu kinh doanh.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CATALOG_PATH = PROJECT_ROOT / "data" / "sql_catalog" / "latest.json"
DEFAULT_POLICY_PATH = PROJECT_ROOT / "config" / "sql_catalog_policy.json"
CATALOG_CACHE_TTL_SEC = 3600
MAX_CONTEXT_CHARS = 5000

_cache_lock = threading.Lock()
_catalog_cache: dict[str, Any] | None = None
_catalog_cache_source: str | None = None
_catalog_cache_loaded_at = 0.0


_STOP_WORDS = {
    "ai", "bao", "cac", "cai", "cho", "co", "cong", "cua", "duoc", "gi", "han", "hay", "hoi",
    "khong", "la", "lay", "mot", "nao", "nhieu", "nhung", "no", "o", "qua", "theo", "thi",
    "thong", "tin", "toi", "tong", "trong", "tu", "va", "ve", "voi",
}

_DOMAIN_ALIASES = {
    "doanh thu": ("hoadon", "amount9", "sales", "donhang"),
    "doanh so": ("hoadon", "amount", "sales", "tonghopkhachhang"),
    "cong no": ("deptacc", "dudk", "phatsinh", "htt", "ut", "due", "overdue"),
    "no qua han": ("deptacc", "due", "overdue", "htt", "ut"),
    "khach hang": ("khachhang", "customer"),
    "nhan vien": ("nhanvien", "employee", "chucvu"),
    "san pham": ("sanpham", "item", "nhomsanpham"),
    "ton kho": ("tonkho", "thekho", "lot", "stock", "inventory"),
    "don hang": ("donhang", "order"),
    "khuyen mai": ("ctkm", "dkkm", "trakm", "promotion"),
    "hop dong": ("hopdong", "contract"),
    "kpi": ("tonghopkhachhang", "tonghopsanpham", "target", "khtheothang"),
    "chi tieu": ("target", "kehoach", "khtheothang"),
    "thuong": ("thuong", "thongketinhluong", "bangluong", "bacthuong"),
    "luong": ("luong", "thongketinhluong", "chamcong", "congtinhluong"),
    "cham cong": ("chamcong", "employee"),
    "tra hang": ("tralai", "hoadonhc", "return"),
    "dia ban": ("diaban", "tinhthanhpho", "area"),
}

def _plain(value: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", value or "")
    normalized = unicodedata.normalize("NFD", value.lower())
    no_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    no_accents = no_accents.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", no_accents).strip()


def _query_terms(query: str) -> set[str]:
    plain = _plain(query)
    terms = {token for token in plain.split() if len(token) >= 2 and token not in _STOP_WORDS}
    compact = plain.replace(" ", "")
    for phrase, aliases in _DOMAIN_ALIASES.items():
        if _plain(phrase) in plain:
            terms.update(aliases)
    if compact:
        terms.add(compact)
    return terms


def _load_policy():
    try:
        from .sql_catalog import load_policy
    except ImportError:
        from sql_catalog import load_policy
    path = os.getenv("SQL_CATALOG_POLICY_PATH", "").strip()
    policy_path = Path(path) if path else DEFAULT_POLICY_PATH
    return load_policy(policy_path if policy_path.exists() else None)


def _build_live_catalog() -> dict[str, Any]:
    try:
        from .query_engine import _get_engine
        from .sql_catalog import extract_sql_server_catalog
    except ImportError:
        from query_engine import _get_engine
        from sql_catalog import extract_sql_server_catalog
    return extract_sql_server_catalog(_get_engine("bravo"), _load_policy())


def load_runtime_catalog(force_refresh: bool = False) -> dict[str, Any]:
    """Doc snapshot neu co; fallback metadata live. Cache de khong cham SQL moi cau hoi."""
    global _catalog_cache, _catalog_cache_loaded_at, _catalog_cache_source
    now = time.time()
    if (
        not force_refresh
        and _catalog_cache is not None
        and now - _catalog_cache_loaded_at < CATALOG_CACHE_TTL_SEC
    ):
        return _catalog_cache

    with _cache_lock:
        now = time.time()
        if (
            not force_refresh
            and _catalog_cache is not None
            and now - _catalog_cache_loaded_at < CATALOG_CACHE_TTL_SEC
        ):
            return _catalog_cache

        configured = os.getenv("SQL_CATALOG_PATH", "").strip()
        catalog_path = Path(configured) if configured else DEFAULT_CATALOG_PATH
        if catalog_path.exists():
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            source = str(catalog_path)
        else:
            catalog = _build_live_catalog()
            source = "live_metadata"

        # Luoi an toan runtime: snapshot cu duoc tao truoc khi co policy cung khong
        # duoc phep dua object bi deny vao prompt/tool tim schema.
        policy = _load_policy()
        catalog = dict(catalog)
        allowed_objects = []
        for original in catalog.get("objects", []):
            if not policy.allows_object(original.get("schema", ""), original.get("name", "")):
                continue
            obj = dict(original)
            obj["columns"] = [dict(column) for column in original.get("columns", [])]
            for column in obj["columns"]:
                column["data_classification"] = (
                    policy.classification_for(obj.get("schema", ""), obj.get("name", ""), column.get("name", ""))
                    or column.get("data_classification")
                )
            allowed_objects.append(obj)
        catalog["objects"] = allowed_objects
        _catalog_cache = catalog
        _catalog_cache_source = source
        _catalog_cache_loaded_at = now
        return catalog


def _object_score(obj: dict[str, Any], terms: set[str], query: str) -> float:
    full_name = _plain(obj.get("full_name", ""))
    object_name = _plain(obj.get("name", ""))
    compact_name = object_name.replace(" ", "")
    query_plain = _plain(query)
    query_compact = query_plain.replace(" ", "")
    columns = obj.get("columns", [])
    column_text = " ".join(_plain(col.get("name", "")) for col in columns)
    description_text = _plain(" ".join(
        str(value or "") for value in [obj.get("description"), *[col.get("description") for col in columns]]
    ))
    definition_text = _plain((obj.get("definition") or "")[:8000])

    score = 0.0
    if query_compact and query_compact in compact_name:
        score += 40
    if compact_name and compact_name in query_compact:
        score += 30
    for term in terms:
        compact_term = term.replace(" ", "")
        if compact_term and compact_term in compact_name:
            score += 12
        elif term in full_name:
            score += 8
        if term in column_text:
            score += 4
        if term in description_text:
            score += 2
        if term in definition_text:
            score += 0.5

    # View thuong la lop da chuan hoa de bao cao; uu tien nhe khi diem noi dung ngang nhau.
    if obj.get("object_type") == "V":
        score += 0.25
    normalized_full_name = str(obj.get("full_name", "")).lower()
    if "doanh thu" in query_plain or "doanh so" in query_plain:
        if normalized_full_name in {"dbo.vhoadontotal", "dbo.vhoadonetctotal"}:
            score += 24
        if "pbi" in normalized_full_name:
            score -= 20
        if normalized_full_name in {"dbo.vhoadon", "dbo.vhoadonetc"}:
            score -= 10
    if "cong no" in query_plain or "no qua han" in query_plain:
        if normalized_full_name in {
            "dbo.usp_deptaccduedate_getdata",
            "dbo.usp_deptaccduedateetc_getdata",
        }:
            score += 20
    if "kpi" in query_plain and normalized_full_name == "dbo.fact_tonghopkhachhang":
        score += 12
    if ("thuong" in query_plain or "luong" in query_plain) and normalized_full_name == "dbo.fact_thongketinhluong":
        score += 12
    return score


def _public_object(obj: dict[str, Any], include_definition: bool) -> dict[str, Any]:
    columns = []
    for col in obj.get("columns", []):
        columns.append({
            "name": col.get("name"),
            "data_type": col.get("data_type"),
            "nullable": col.get("nullable"),
            "description": col.get("description"),
            "data_classification": col.get("data_classification"),
        })
    output = {
        "full_name": obj.get("full_name"),
        "type": obj.get("type_desc"),
        "row_count_estimate": obj.get("row_count_estimate"),
        "description": obj.get("description"),
        "has_read_permission": obj.get("has_read_permission"),
        "columns": columns,
        "foreign_keys": obj.get("foreign_keys", []),
    }
    if include_definition and obj.get("definition"):
        definition = str(obj["definition"])
        output["definition"] = definition[:5000]
        output["definition_truncated"] = len(definition) > 5000
    elif include_definition and obj.get("object_type") in ("V", "P", "FN", "IF", "TF"):
        output["definition_unavailable"] = True
    return output


def search_sql_catalog(query: str, limit: int = 6, include_definition: bool = True) -> dict[str, Any]:
    catalog = load_runtime_catalog()
    terms = _query_terms(query)
    ranked = sorted(
        (
            (_object_score(obj, terms, query), obj)
            for obj in catalog.get("objects", [])
            if obj.get("has_read_permission")
        ),
        key=lambda item: (-item[0], str(item[1].get("full_name", "")).lower()),
    )
    selected = [(score, obj) for score, obj in ranked if score > 0][:max(1, min(int(limit or 6), 12))]
    summary = catalog.get("summary", {})
    return {
        "database": catalog.get("source", {}).get("database"),
        "catalog_generated_at": catalog.get("generated_at"),
        "catalog_object_count": len(catalog.get("objects", [])),
        "metadata_gaps": summary.get("metadata_gaps", []),
        "query": query,
        "matches": [
            {"relevance_score": round(score, 2), **_public_object(obj, include_definition)}
            for score, obj in selected
        ],
    }


def relevant_schema_context(question: str, limit: int = 6) -> str:
    """Context gon cho model; definition chi lay khi model chu dong goi tool search."""
    result = search_sql_catalog(question, limit=limit, include_definition=False)
    if not result["matches"]:
        return ""
    lines = [
        "SCHEMA SQL SERVER LIVE LIEN QUAN (tu catalog metadata, chi dung khi warehouse/tool chuan chua phu):"
    ]
    for obj in result["matches"]:
        columns = ", ".join(
            f"{col['name']} {col['data_type']}" for col in obj.get("columns", [])
        )
        lines.append(f"- {obj['full_name']} [{obj['type']}]: {columns}")
        if sum(len(line) + 1 for line in lines) >= MAX_CONTEXT_CHARS:
            break
    lines.append(
        "SQL Server dung T-SQL (TOP, dbo.[TenObject]); khong dung LIMIT. Khong SELECT *; chi lay cot can thiet."
    )
    return "\n".join(lines)[:MAX_CONTEXT_CHARS]
