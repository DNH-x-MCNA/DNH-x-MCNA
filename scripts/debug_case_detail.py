# -*- coding: utf-8 -*-
"""In toan bo chi tiet (cau hoi, nguyen van cau tra loi, tools_called, ground_truth, tat ca
problems) cho 1 vai case_id CU THE tu 1 file ket qua - bat ky loai P0 nao (khong chi sai_so_lieu
nhu debug_sai_so_lieu.py). Dung khi can xem "khong_goi_tool"/"lo_du_bao" lan "sai_so_lieu" cung luc.

Chay: python scripts\\debug_case_detail.py <duong_dan_file.json> Q070 Q072 Q073
"""
import io
import json
import sys


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit("Dung: python scripts\\debug_case_detail.py <file.json> <case_id> [case_id...]")
    path, case_ids = args[0], set(args[1:])

    data = json.load(io.open(path, encoding="utf-8"))
    by_id = {r["case"]["id"]: r for r in data["results"]}

    for cid in case_ids:
        r = by_id.get(cid)
        if not r:
            print(f"\n!! Khong tim thay {cid} trong {path}")
            continue
        print(f"\n{'='*100}")
        print(f"{cid} ({r['case']['audience']}) checker_id={r['case']['checker_id']!r}")
        print(f"Cau hoi: {r['case']['question']}")
        print(f"Pass rule: {r['case'].get('pass_rule')}")
        print(f"{'='*100}")
        print(f"[tools_called]: {r.get('tools_called')}")
        print(f"[error]: {r.get('error')}")
        print(f"[problems]:")
        for p in r["grade"]["problems"]:
            print(f"  - [{p['severity']}] {p['code']}: {p['detail']}")
        print(f"\n[Nguyen van cau tra loi]:\n{r['answer']}")
        gt = r.get("ground_truth", {})
        print(f"\n[ground_truth status={gt.get('status')}] columns={gt.get('columns')}")
        for row in gt.get("rows", [])[:15]:
            print(f"    {row}")


if __name__ == "__main__":
    main()
