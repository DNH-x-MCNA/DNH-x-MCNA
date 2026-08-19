# -*- coding: utf-8 -*-
"""Phan loai cac cau 'sai_so_lieu' trong 1 file ket qua DA CO SAN - khong goi lai chatbot.

Muc dich: kiem tra gia thuyet "nhieu case dung CHUNG 1 checker ground-truth" (bang chung: mot vai
case bao thieu DUNG mot tap so giong het nhau). Neu dung, day KHONG phai N loi doc lap ma la 1 vai
nguyen nhan goc. Kem theo in nguyen van cau tra loi (khong cat 200 ky tu) va bang ground_truth de
xem chatbot co dang TRA LOI DUNG NOI DUNG (vd dem so luong) nhung khong liet ke lai tung ma so tho -
checker co the doi hoi qua muc can thiet cho cau hoi dang DEM.

Chay: python scripts\\debug_sai_so_lieu.py [duong_dan_file.json]
"""
import glob
import io
import json
import os
import sys

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")


def newest_result_file():
    files = glob.glob(os.path.join(RESULTS_DIR, "business-eval-*.json"))
    if not files:
        raise SystemExit(f"Khong tim thay file nao trong {RESULTS_DIR}")
    return max(files, key=os.path.getmtime)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else newest_result_file()
    data = json.load(io.open(path, encoding="utf-8"))
    results = data["results"]

    sai_so = []
    for r in results:
        probs = [p for p in r["grade"]["problems"] if p["code"] == "sai_so_lieu"]
        if probs:
            sai_so.append((r, probs[0]))

    print(f"File: {path}")
    print(f"Tong so cau: {len(results)}")
    print(f"So cau 'sai_so_lieu': {len(sai_so)}")
    print()

    # Nhom theo TAP SO BI THIEU (chinh xac) - neu >1 case chung 1 tap, do la bang chung
    # cung mot checker ground-truth, khong phai loi doc lap.
    groups: dict[tuple, list] = {}
    for r, p in sai_so:
        detail = p["detail"]
        nums_part = detail.split(":", 1)[-1].strip()
        key = (r["case"]["checker_id"], nums_part)
        groups.setdefault(key, []).append(r)

    shared = {k: v for k, v in groups.items() if len(v) > 1}
    solo = {k: v for k, v in groups.items() if len(v) == 1}

    print(f"=== Nhom CHUNG checker_id + chung tap so thieu (nghi la 1 nguyen nhan goc) ===")
    print(f"So nhom: {len(shared)}, gom {sum(len(v) for v in shared.values())} case")
    for (checker_id, nums), rs in shared.items():
        print(f"\n--- checker_id={checker_id!r} | so thieu: {nums} | {len(rs)} case ---")
        for r in rs:
            print(f"  {r['case']['id']} ({r['case']['audience']}) - {r['case']['question']}")
        # In chi tiet CASE DAU TIEN trong nhom de xem cau tra loi that
        r0 = rs[0]
        print(f"\n  [Nguyen van cau tra loi cua {r0['case']['id']}]:")
        print(f"  {r0['answer']!r}")
        gt = r0.get("ground_truth", {})
        print(f"\n  [Ground truth rows cua checker nay] (columns={gt.get('columns')}):")
        for row in gt.get("rows", [])[:10]:
            print(f"    {row}")
        print(f"  [tools_called]: {r0.get('tools_called')}")

    print(f"\n\n=== Case KHONG chung nhom (moi case 1 checker/1 tap so rieng) ===")
    print(f"So case: {len(solo)}")
    for (checker_id, nums), rs in solo.items():
        r = rs[0]
        print(f"\n--- {r['case']['id']} ({r['case']['audience']}) checker_id={checker_id!r} ---")
        print(f"  Cau hoi: {r['case']['question']}")
        print(f"  So thieu: {nums}")
        print(f"  [Nguyen van cau tra loi]: {r['answer']!r}")
        gt = r.get("ground_truth", {})
        print(f"  [Ground truth rows] (columns={gt.get('columns')}):")
        for row in gt.get("rows", [])[:10]:
            print(f"    {row}")
        print(f"  [tools_called]: {r.get('tools_called')}")


if __name__ == "__main__":
    main()
