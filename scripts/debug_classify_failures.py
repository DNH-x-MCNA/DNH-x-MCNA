# -*- coding: utf-8 -*-
"""Phan loai CHINH XAC cac cau 'khong_goi_tool' trong 1 file ket qua DA CO SAN - khong goi lai
chatbot, khong ton them 1 dong nao. Tach ra: bao nhieu cau dinh dung loi thieu API key (loi ha
tang cua evaluator, khong phai chatbot), con lai la gi.

Chay: python scripts\\debug_classify_failures.py [duong_dan_file.json]
"""
import glob
import io
import json
import os
import sys

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
NO_KEY_MARKER = "Chưa cấu hình API Key"


def newest_result_file():
    files = glob.glob(os.path.join(RESULTS_DIR, "business-eval-*.json"))
    if not files:
        raise SystemExit(f"Khong tim thay file nao trong {RESULTS_DIR}")
    return max(files, key=os.path.getmtime)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else newest_result_file()
    data = json.load(io.open(path, encoding="utf-8"))
    results = data["results"]

    khong_tool = [r for r in results if "khong_goi_tool" in [p["code"] for p in r["grade"]["problems"]]]
    thieu_key = [r for r in khong_tool if NO_KEY_MARKER in (r.get("answer") or "")]
    khac = [r for r in khong_tool if r not in thieu_key]

    print(f"File: {path}")
    print(f"Tong so cau: {len(results)}")
    print(f"So cau dinh 'khong_goi_tool': {len(khong_tool)}")
    print(f"  - Trong do dinh dung LOI THIEU API KEY (ha tang evaluator): {len(thieu_key)}")
    print(f"    -> ID: {[r['case']['id'] for r in thieu_key]}")
    print(f"  - Con lai (KHONG phai loi thieu key, can xem tung cau): {len(khac)}")
    print()

    if thieu_key:
        ts = [r["session_id"] for r in thieu_key]
        print("Khoang thoi gian dinh loi thieu key (dua vao thu tu case, khong phai ts that):")
        print(f"  Tu {thieu_key[0]['case']['id']} den {thieu_key[-1]['case']['id']}")
        print()

    if khac:
        print("=== Cac cau 'khong_goi_tool' KHONG phai do thieu API key - can nguoi xem ===")
        for r in khac:
            print(f"\n- {r['case']['id']} ({r['case']['audience']}) - {r['case']['question'][:80]}")
            print(f"  answer (200 ky tu dau): {(r['answer'] or '')[:200]!r}")


if __name__ == "__main__":
    main()
