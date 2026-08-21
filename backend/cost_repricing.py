# -*- coding: utf-8 -*-
"""Tinh lai co kiem soat cac dong chi phi DeepSeek da ghi theo bang gia cu.

Module nay khong tu dong chay khi backend khoi dong. Lich su chi phi la du lieu audit; viec sua
phai la thao tac chu dong, co dry-run va backup trong scripts/reprice_cost_log.py.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Iterable

from pricing import compute_cost_usd, pricing_source_for_model, pricing_version_for_model


DEFAULT_MODELS = {"deepseek-v4-pro", "deepseek-v4-flash"}


def _token_count(value) -> int:
    """Log cu co the chua so duoi dang chuoi; gia tri loi thi an toan coi la 0."""
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def reprice_entry(entry: dict, models: Iterable[str] = DEFAULT_MODELS) -> tuple[dict, bool]:
    """Tra ve (dong_moi, da_thay_doi). Chi DeepSeek V4 duoc phep tinh lai mac dinh."""
    models = {str(m).strip().lower() for m in models}
    model = str(entry.get("model") or "").strip().lower()
    if model not in models:
        return dict(entry), False

    recalculated = round(compute_cost_usd(
        model,
        _token_count(entry.get("input_tokens")),
        _token_count(entry.get("output_tokens")),
        _token_count(entry.get("cache_read_tokens")),
        _token_count(entry.get("cache_write_tokens")),
    ), 6)
    previous = entry.get("cost_usd")
    try:
        previous_number = round(float(previous), 6)
    except (TypeError, ValueError):
        previous_number = None

    updated = dict(entry)
    # Giu nguyen gia da ghi lan dau, de sau nay audit duoc vi sao tong dashboard thay doi.
    updated.setdefault("cost_usd_before_reprice", previous)
    updated["cost_usd"] = recalculated
    updated["pricing_version"] = pricing_version_for_model(model)
    updated["pricing_source"] = pricing_source_for_model(model)
    changed = (
        previous_number != recalculated
        or entry.get("pricing_version") != updated["pricing_version"]
        or entry.get("pricing_source") != updated["pricing_source"]
        or "cost_usd_before_reprice" not in entry
    )
    return updated, changed


def reprice_jsonl(path: str | Path, apply: bool = False,
                  models: Iterable[str] = DEFAULT_MODELS) -> dict:
    """Doc va (neu apply=True) thay the JSONL bang atomic, kem ban sao .bak.

    Dong JSON hong khong bi xoa va khong duoc dua vao tong ket. Ham nay khong ghi timestamp vao
    tung dong, nen chay lai la idempotent va diff audit de kiem tra.
    """
    log_path = Path(path)
    if not log_path.is_file():
        raise FileNotFoundError(f"Khong tim thay cost log: {log_path}")

    raw_lines = log_path.read_text(encoding="utf-8").splitlines()
    output_lines: list[str] = []
    summary = {"path": str(log_path), "rows": 0, "eligible": 0, "changed": 0,
               "invalid_json": 0, "old_cost_usd": 0.0, "new_cost_usd": 0.0,
               "applied": False, "backup_path": None}
    normalized_models = {str(m).strip().lower() for m in models}

    for line in raw_lines:
        if not line.strip():
            output_lines.append(line)
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            summary["invalid_json"] += 1
            output_lines.append(line)
            continue
        if not isinstance(entry, dict):
            summary["invalid_json"] += 1
            output_lines.append(line)
            continue

        summary["rows"] += 1
        model = str(entry.get("model") or "").strip().lower()
        if model not in normalized_models:
            output_lines.append(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
            continue

        summary["eligible"] += 1
        try:
            summary["old_cost_usd"] += float(entry.get("cost_usd") or 0.0)
        except (TypeError, ValueError):
            pass
        updated, changed = reprice_entry(entry, normalized_models)
        summary["new_cost_usd"] += float(updated["cost_usd"])
        summary["changed"] += int(changed)
        output_lines.append(json.dumps(updated, ensure_ascii=False, separators=(",", ":")))

    summary["old_cost_usd"] = round(summary["old_cost_usd"], 6)
    summary["new_cost_usd"] = round(summary["new_cost_usd"], 6)
    summary["delta_cost_usd"] = round(summary["new_cost_usd"] - summary["old_cost_usd"], 6)

    if apply and summary["changed"]:
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = log_path.with_name(f"{log_path.name}.bak-{stamp}")
        shutil.copy2(log_path, backup)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{log_path.name}.", suffix=".tmp", dir=log_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as output:
                output.write("\n".join(output_lines))
                if raw_lines:
                    output.write("\n")
            os.replace(temporary_name, log_path)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        summary["applied"] = True
        summary["backup_path"] = str(backup)
    return summary
