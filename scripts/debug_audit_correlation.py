# -*- coding: utf-8 -*-
"""Chan doan rieng: vi sao run_business_evaluation.py bao 'khong goi tool' cho nhung cau
DA BIET la co goi tool that (vd Q001 - da kiem chung nhieu lan truoc do trong phien lam viec).
Doc file ket qua moi nhat + audit_log.jsonl, in thang du lieu tho de doi chieu bang mat, KHONG
suy doan.

Chay tren may 24:
    cd C:\\dnh_chatbot
    python scripts\\debug_audit_correlation.py
    python scripts\\debug_audit_correlation.py --case Q001 Q003 Q037
"""
import argparse
import glob
import io
import json
import os

BACKEND_DIR = os.environ.get("DNH_BACKEND_DIR", r"C:\dnh_chatbot\backend")
AUDIT_LOG = os.path.join(BACKEND_DIR, "logs", "audit_log.jsonl")
RESULTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")


def newest_result_file():
    files = glob.glob(os.path.join(RESULTS_DIR, "business-eval-*.json"))
    if not files:
        raise SystemExit(f"Khong tim thay file ket qua nao trong {RESULTS_DIR}")
    return max(files, key=os.path.getmtime)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--case", nargs="*", default=["Q001", "Q003", "Q037"])
    p.add_argument("--file", default=None)
    args = p.parse_args()

    path = args.file or newest_result_file()
    print(f"Doc file: {path}\n")
    data = json.load(io.open(path, encoding="utf-8"))
    by_id = {r["case"]["id"]: r for r in data["results"]}

    print(f"So dong trong audit_log.jsonl: ", end="")
    total_lines = 0
    if os.path.exists(AUDIT_LOG):
        with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as f:
            for _ in f:
                total_lines += 1
    print(total_lines)
    print(f"Duong dan audit_log dang doc: {AUDIT_LOG}\n")

    for case_id in args.case:
        r = by_id.get(case_id)
        if not r:
            print(f"=== {case_id}: KHONG CO trong file ket qua ===\n")
            continue
        sid = r["session_id"]
        print(f"=== {case_id} ===")
        print(f"  session_id   : {sid}")
        print(f"  tools_called : {r['tools_called']}")
        print(f"  error        : {r['error']}")
        print(f"  answer (300 ky tu dau):")
        print(f"    {(r['answer'] or '')[:300]!r}")

        matches = []
        if os.path.exists(AUDIT_LOG):
            with io.open(AUDIT_LOG, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if sid in line:
                        matches.append(line.rstrip())
        print(f"  So dong audit_log chua dung session_id nay: {len(matches)}")
        for m in matches[:5]:
            print(f"    RAW: {m[:250]}")
        print()


if __name__ == "__main__":
    main()
