# -*- coding: utf-8 -*-
"""Lay SQL tu do THAT ma chatbot da chay cho 1 vai case cu the, doi chieu voi audit_log.jsonl.
Dung de dieu tra vi sao Q016 tra loi khac huong voi Q024/Q062 dung chung 1 loai cau hoi
(quan ly truc tiep / ManagerCode) - can biet SQL that de xem model suy dien sai o dau, khong
doan mo.

Chay: python scripts\\debug_sql_for_cases.py Q016 Q012 Q044 [duong_dan_file.json]
"""
import glob
import io
import json
import os
import sys

RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
AUDIT_LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "backend", "logs", "audit_log.jsonl")


def newest_result_file():
    files = glob.glob(os.path.join(RESULTS_DIR, "business-eval-*.json"))
    if not files:
        raise SystemExit(f"Khong tim thay file nao trong {RESULTS_DIR}")
    return max(files, key=os.path.getmtime)


def main():
    args = sys.argv[1:]
    json_candidates = [a for a in args if a.lower().endswith(".json")]
    case_ids = [a for a in args if not a.lower().endswith(".json")]
    if not case_ids:
        raise SystemExit("Truyen it nhat 1 ma case, vd: python scripts\\debug_sql_for_cases.py Q016")
    path = json_candidates[0] if json_candidates else newest_result_file()
    data = json.load(io.open(path, encoding="utf-8"))
    results = {r["case"]["id"]: r for r in data["results"]}

    wanted_sessions = {}
    for cid in case_ids:
        r = results.get(cid)
        if r is None:
            print(f"!! Khong tim thay case {cid} trong {path}")
            continue
        wanted_sessions[r["session_id"]] = cid
        print(f"{cid}: session_id={r['session_id']} | question={r['case']['question']}")

    print(f"\nDoc audit log: {AUDIT_LOG}")
    if not os.path.isfile(AUDIT_LOG):
        raise SystemExit(f"Khong tim thay file audit log tai {AUDIT_LOG}")

    found_any = set()
    with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            sid = item.get("session_id")
            if sid not in wanted_sessions:
                continue
            cid = wanted_sessions[sid]
            found_any.add(sid)
            print(f"\n=== {cid} | db={item.get('db')} | status={item.get('status')} | "
                  f"row_count={item.get('row_count')} ===")
            print(item.get("sql"))

    missing = set(wanted_sessions) - found_any
    for sid in missing:
        print(f"\n!! Khong tim thay dong audit log nao cho session {sid} ({wanted_sessions[sid]})")


if __name__ == "__main__":
    main()
