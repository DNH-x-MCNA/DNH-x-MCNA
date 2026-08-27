# -*- coding: utf-8 -*-
"""Dựng và in báo cáo một QLV; không có mã nguồn nào gửi Teams/email hay gọi LLM/API.

Ví dụ::

    python scripts/dry_run_qlv_digest.py --employee-code TM25010183 --region MB --channel OTC
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.qlv_digest import build_qlv_digest_metrics, build_qlv_teams_content  # noqa: E402


def _money(value) -> str:
    amount = float(value or 0.0)
    if abs(amount) >= 1_000_000_000:
        return f"{amount / 1_000_000_000:,.2f} tỷ đồng"
    if abs(amount) >= 1_000_000:
        return f"{amount / 1_000_000:,.2f} triệu đồng"
    return f"{amount:,.0f} đồng"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run báo cáo đội QLV, không gửi ra ngoài")
    parser.add_argument("--employee-code", required=True, help="Mã nhân viên QLV trên Bravo")
    parser.add_argument("--region", required=True, help="MB/MN/MT hoặc bac/nam/trung")
    parser.add_argument("--channel", default="OTC", choices=("OTC", "ETC"))
    parser.add_argument("--as-of", help="Ngày báo cáo YYYY-MM-DD; mặc định hôm nay")
    args = parser.parse_args()

    metrics = build_qlv_digest_metrics(
        employee_code=args.employee_code,
        region=args.region,
        channel=args.channel,
        as_of_date=args.as_of,
    )
    headers, rows, sections = build_qlv_teams_content(metrics, _money)
    preview = {
        "mode": "DRY_RUN_ONLY_NO_SEND",
        "scope": {
            "employee_code": metrics["employee_code"],
            "area_code": metrics["area_code"],
            "channel": metrics["channel"],
            "date": metrics["date"],
        },
        "inventory_included": metrics["inventory_included"],
        "freshness_note": metrics.get("freshness_note"),
        "table_headers": headers,
        "table_rows": rows,
        "sections": sections,
    }
    print(json.dumps(preview, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
