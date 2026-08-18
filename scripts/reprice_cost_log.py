# -*- coding: utf-8 -*-
r"""Tinh lai cost_log DeepSeek theo bang gia chinh thuc da khai bao trong backend/pricing.py.

Mac dinh chi XEM TRUOC, khong sua file:
    python scripts\reprice_cost_log.py

Chi khi da duyet tong tien va backup, moi sua log:
    python scripts\reprice_cost_log.py --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from cost_logger import LOG_PATH
from cost_repricing import DEFAULT_MODELS, reprice_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true",
                        help="Ghi log da tinh lai. Mac dinh la dry-run, khong ghi gi.")
    parser.add_argument("--path", default=LOG_PATH,
                        help="Duong dan cost_log.jsonl can xu ly.")
    parser.add_argument("--model", action="append", choices=sorted(DEFAULT_MODELS),
                        help="Chi tinh lai model nay; co the lap lai tham so.")
    args = parser.parse_args()

    result = reprice_jsonl(args.path, apply=args.apply, models=args.model or DEFAULT_MODELS)
    print(f"Cost log       : {result['path']}")
    print(f"Dong hop le    : {result['rows']}")
    print(f"Dong DeepSeek  : {result['eligible']}")
    print(f"Dong se doi    : {result['changed']}")
    print(f"Chi phi cu     : ${result['old_cost_usd']:.6f}")
    print(f"Chi phi moi    : ${result['new_cost_usd']:.6f}")
    print(f"Chenh lech     : ${result['delta_cost_usd']:.6f}")
    if result["invalid_json"]:
        print(f"Canh bao       : {result['invalid_json']} dong JSON hong duoc giu nguyen")
    if result["applied"]:
        print(f"DA GHI LOG. Backup: {result['backup_path']}")
    else:
        print("DRY-RUN: chua sua log. Dung --apply sau khi duyet tong tien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
