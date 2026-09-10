# -*- coding: utf-8 -*-
"""Kiem dinh tuyen ca 138 cau hoi dieu hanh - KHONG goi API, chay vai giay.

Vi sao can: bo 138 cau chay that ton ~8-10 USD va ~90 phut nen khong the chay moi lan sua code.
Nhung phan LON loi da gap khong nam o cau tra loi, ma nam o cho cau hoi bi day sang sai tool -
M22 tung bi day vao get_customer_movement (khong co khoang cach mua trung binh) nen khong bao gio
tra loi duoc ve "keo dai chu ky". Kiem dinh tuyen bat duoc dung lop loi do voi chi phi bang 0.

Nguon cau hoi doc THANG tu docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md - khong chep lai.

Chay tu root repository:
    python scripts/kiem_dinh_tuyen_138.py
    python scripts/kiem_dinh_tuyen_138.py --hien-het
"""
from __future__ import annotations

import argparse
import collections
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "backend"), ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

TAI_LIEU = os.path.join(ROOT, "docs", "bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md")
DONG_CAU_HOI = re.compile(
    r"^\| *([CMV][0-9]{1,2}) *\| *(.+?) *\| *(S[0-9]+[a-z]?) *\| *([A-Z_]+) *\|\s*$")

# S35 la nhom cau du bao: chu dich KHONG ep tool, de model tu tra loi hoac tu choi.
CHECKER_MIEN_TRU = {"S35"}
NGUON_BI_CHAN = {"BLOCKED", "BLOCKED_HISTORY"}


def doc_bo_cau_hoi():
    cau = []
    for dong in io.open(TAI_LIEU, encoding="utf-8"):
        m = DONG_CAU_HOI.match(dong)
        if m:
            cau.append(m.groups())
    return cau


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hien-het", action="store_true",
                    help="In dinh tuyen cua tung cau, khong chi phan bat thuong")
    args = ap.parse_args()

    cau = doc_bo_cau_hoi()
    if not cau:
        print("KHONG doc duoc cau hoi nao tu %s" % TAI_LIEU)
        return 1

    theo_tool = collections.Counter()
    khong_ep_tool = []
    dinh_tuyen = {}

    for ma, noi_dung, checker, trang_thai in cau:
        tool = nl2sql._required_tool_for_question(noi_dung)
        dinh_tuyen[ma] = (tool, checker, trang_thai, noi_dung)
        if tool:
            theo_tool[tool] += 1
        else:
            khong_ep_tool.append((ma, checker, trang_thai, noi_dung))

    print("Bo cau hoi: %d cau." % len(cau))
    print("  Co tool bat buoc      : %d" % (len(cau) - len(khong_ep_tool)))
    print("  Roi ve free-SQL       : %d" % len(khong_ep_tool))
    print()

    if args.hien_het:
        print("--- Dinh tuyen tung cau ---")
        for ma in sorted(dinh_tuyen, key=lambda x: (x[0], int(x[1:]))):
            tool, checker, trang_thai, _ = dinh_tuyen[ma]
            print("  %-4s %-5s %-16s %s" % (ma, checker, trang_thai, tool or "(free-SQL)"))
        print()

    print("--- Phan bo tool ---")
    for tool, n in theo_tool.most_common():
        print("  %3d  %s" % (n, tool))
    print()

    ngoai_y_muon = [r for r in khong_ep_tool if r[1] not in CHECKER_MIEN_TRU]
    print("--- Cau roi ve free-SQL ---")
    for ma, checker, trang_thai, noi_dung in khong_ep_tool:
        ghi_chu = ""
        if checker in CHECKER_MIEN_TRU:
            ghi_chu = "  (cau du bao - chu dich khong ep tool)"
        elif trang_thai in NGUON_BI_CHAN:
            ghi_chu = "  (nguon bi chan - chatbot phai tu choi)"
        print("  %-4s %-5s %-16s %s%s" % (ma, checker, trang_thai, noi_dung[:60], ghi_chu))
    print()

    thua = set(rt.TEMPLATES) - set(theo_tool)
    print("--- Tool da dang ky nhung khong cau nao ep toi (%d) ---" % len(thua))
    print("    Day KHONG phai loi: router chi ep cac y dinh rui ro cao, cac tool con lai de model")
    print("    tu chon. Chi dang ngo neu mot tool vua duoc them cho MOT cau cu the ma lai nam day.")
    for t in sorted(thua):
        print("   ", t)
    print()

    if ngoai_y_muon:
        print("KET LUAN: CHUA DAT - %d cau roi ve free-SQL ngoai nhom du bao S35:" % len(ngoai_y_muon))
        for ma, checker, _, _ in ngoai_y_muon:
            print("   ", ma, checker)
        return 1
    print("KET LUAN: DAT - moi cau ngoai nhom du bao S35 deu co tool bat buoc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
