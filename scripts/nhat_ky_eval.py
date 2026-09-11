# -*- coding: utf-8 -*-
"""Doc nhat ky chatbot theo session: tool nao da chay, ton bao nhieu. CHI DOC, khong goi model.

11/09/2026: tach tu scripts/run_business_evaluation.py truoc khi go bo business-eval. run_bo_138_cau.py
va run_tool_routing_sample.py muon dung hai ham duoi day qua duong nap file cua business-eval; xoa file
do ma khong tach truoc thi hai runner kia hong theo.

Nguoi goi phai GAN LAI AUDIT_LOG / COST_LOG theo module dang GHI log (cost_logger.LOG_PATH,
query_engine.LOG_PATH) truoc khi goi - xem ghi chu 25/08 trong run_tool_routing_sample.py.
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = Path(os.environ.get("DNH_BACKEND_DIR", ROOT / "backend"))
AUDIT_LOG = BACKEND / "logs" / "audit_log.jsonl"
COST_LOG = BACKEND / "logs" / "cost_log.jsonl"


def _audit_by_session(session_ids: set[str]) -> dict[str, set[str]]:
    """Tool nao da chay cho tung session, doc tu audit_log.jsonl.

    Hai dang ban ghi: call_template() ghi sql dang <template:TEN>(...) va KHONG co khoa "db";
    run_query() (SQL tu do) LUON ghi khoa "db". SQL tu do van la tool that chay tren du lieu that,
    nen phai tinh - bo sot no tung khien 48/49 ca bi cham "khong goi tool" oan (18/08/2026).
    """
    found: dict[str, set[str]] = {sid: set() for sid in session_ids}
    if not AUDIT_LOG.is_file():
        return found
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid not in found:
                continue
            match = re.search(r"<template:([a-zA-Z_]+)>", str(item.get("sql") or ""))
            if match:
                found[sid].add(match.group(1))
            elif "db" in item and item.get("status") == "ok":
                found[sid].add(f"sql_tu_do:{item['db']}")
    return found


def _cost_by_session(session_ids: set[str]) -> dict[str, float]:
    """Tong cost_usd theo session, doc tu cost_log.jsonl."""
    cost: dict[str, float] = {sid: 0.0 for sid in session_ids}
    if not COST_LOG.is_file():
        return cost
    with io.open(COST_LOG, encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid in cost:
                cost[sid] += float(item.get("cost_usd") or 0.0)
    return cost
