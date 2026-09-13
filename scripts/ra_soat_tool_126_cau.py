# -*- coding: utf-8 -*-
"""Ra soat TOAN BO cau hoi UAT o tang TOOL: goi dung tool ma tung cau dinh tuyen vao, theo dung vai
tro va pham vi cua nguoi hoi, roi bao cao cau nao tool loi / khong co du lieu / thieu truong.

KHONG goi model, KHONG ton API. Muc dich la bat cac loi CHAC CHAN sai truoc khi chay vong do that:
  - Tool nem loi hoac tra {"error": ...}  -> cau do khong the tra loi dung.
  - Tool chay nhung khong co dong du lieu nao -> phai kiem lai pham vi/ky hoac nguon.
  - Cau hoi doi mot chieu (theo NV, theo thang, ty le, nguyen nhan...) ma ket qua khong co truong
    nao ung voi chieu do -> dau hieu tool chua du de tra loi tron cau.

Vai tro mac dinh theo tien to ma cau: C = C-Level, M = Giam doc mien MB, V = QLV MBKV2 (MB) - dung
dung bo tai khoan dang cham UAT.

    python scripts/ra_soat_tool_126_cau.py --ra outputs/ra_soat_tool_126.md
    python scripts/ra_soat_tool_126_cau.py --ma V15,V21   # chi vai cau
"""

import argparse
import io
import os
import re
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.append(str(BACKEND))
os.chdir(str(BACKEND))

import nl2sql  # noqa: E402
import report_templates as rt  # noqa: E402

TAI_LIEU = ROOT / "docs" / "bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md"
DONG_CAU_HOI = re.compile(r"^\|\s*([CMV][0-9]{1,2})\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")

# Cac cau da loai khoi pham vi (du bao/loi nhuan) va cau tam loai - xem ke hoach 11-20/09.
DA_LOAI = {"C04", "C14", "C15", "C19", "C50", "C51", "M39", "M43", "V09", "C25", "C49", "V16"}

PHAM_VI = {
    "C": {"scope_role": "c_level"},
    "M": {"scope_role": "regional_director", "scope_area_code": "MB"},
    "V": {"scope_role": "qlv", "scope_area_code": "MB", "scope_employee_code": "MBKV2"},
}

# Cau hoi doi chieu nao -> tim truong tuong ung trong ket qua. Chi de GOI Y ra soat, khong phai luat.
CHIEU = [
    (("theo từng nhân viên", "từng tdv", "theo nhân viên", "ai mở", "ai tái", "nhân viên nào"),
     ("employee", "by_employee", "nhan_vien", "tdv", "rows")),
    (("theo tháng", "từng tháng", "mỗi tháng", "xu hướng"), ("month", "thang", "months", "series")),
    (("tỷ lệ", "%", "phần trăm"), ("pct", "percent", "ty_le", "rate", "ratio")),
    (("nguyên nhân", "vì sao", "do đâu", "lý do"), ("cause", "nguyen_nhan", "reason", "fail_reasons")),
    (("theo vùng", "từng vùng", "theo miền"), ("area", "vung", "mien", "region")),
    (("theo kênh",), ("channel", "kenh", "otc", "etc")),
]


def _ky_mac_dinh():
    """(thang tron gan nhat, ngay dau thang do, ngay cuoi thang do, ngay du lieu moi nhat)."""
    thang = rt._latest_complete_revenue_month()
    tu, den = rt._month_bounds(thang)
    return thang, tu, den, str(rt.latest_data_date())[:10]


def tham_so_bat_buoc(ten_tool, ma_cau):
    """Dien cac tham so BAT BUOC theo input_schema. Model luon truyen chung (schema ghi required),
    nen bo ra soat cung phai truyen - neu khong se bao loi gia cho ~9 cau."""
    tool = next((t for t in nl2sql.ALL_TOOLS if t["name"] == ten_tool), None)
    if not tool:
        return {}
    schema = tool.get("input_schema") or {}
    thang, tu, den, ngay = _ky_mac_dinh()
    args = {}
    for ten in schema.get("required", []):
        thuoc_tinh = (schema.get("properties") or {}).get(ten, {})
        if ten in ("date_from", "from_date", "start_date"):
            args[ten] = tu
        elif ten in ("date_to", "to_date", "end_date"):
            args[ten] = den
        elif ten in ("as_of_date", "as_of"):
            args[ten] = ngay
        elif ten in ("year_month", "year_month_to", "month", "month_to"):
            args[ten] = thang
        elif ten == "employee_code":
            doi = rt._team_of_qlv("MBKV2") if ma_cau.startswith("V") else []
            args[ten] = doi[0]["employee_code"] if doi else "TM25010183"
        elif thuoc_tinh.get("enum"):
            args[ten] = thuoc_tinh["enum"][0]
        elif thuoc_tinh.get("type") == "integer":
            args[ten] = 6
        else:
            args[ten] = thang
    return args


def doc_cau_hoi():
    cau = []
    for dong in io.open(TAI_LIEU, encoding="utf-8"):
        m = DONG_CAU_HOI.match(dong)
        if m:
            ma, noi_dung, checker = m.group(1), m.group(2).strip(), m.group(3).strip()
            cau.append((ma, noi_dung, checker))
    # Bo trung ma (tai lieu co bang tom tat lap lai)
    da_co, ket_qua = set(), []
    for ma, noi_dung, checker in cau:
        if ma in da_co:
            continue
        da_co.add(ma)
        ket_qua.append((ma, noi_dung, checker))
    return ket_qua


def _co_du_lieu(kq):
    """True neu ket qua co it nhat mot dong/so lieu that."""
    if not isinstance(kq, dict):
        return bool(kq)
    for khoa, gt in kq.items():
        if isinstance(gt, list) and gt:
            return True
        if isinstance(gt, dict) and gt:
            for v in gt.values():
                if isinstance(v, (int, float)) and v:
                    return True
                if isinstance(v, (list, dict)) and v:
                    return True
        if isinstance(gt, (int, float)) and gt and khoa not in {"limit", "months_back"}:
            return True
    return False


def _thieu_chieu(noi_dung, kq):
    """Cac chieu cau hoi doi ma ket qua khong co truong nao ung voi."""
    text = repr(kq).lower()
    hoi = noi_dung.lower()
    thieu = []
    for tu_khoa_hoi, truong in CHIEU:
        if any(t in hoi for t in tu_khoa_hoi) and not any(t in text for t in truong):
            thieu.append(tu_khoa_hoi[0])
    return thieu


def ra_soat(ma_loc=None):
    ket_qua = []
    for ma, noi_dung, checker in doc_cau_hoi():
        if ma_loc and ma not in ma_loc:
            continue
        if ma in DA_LOAI and not ma_loc:
            continue
        tool = nl2sql._required_tool_for_question(noi_dung)
        muc = {"ma": ma, "cau_hoi": noi_dung, "checker": checker, "tool": tool,
               "trang_thai": "", "chi_tiet": "", "thieu_chieu": [], "giay": 0.0}
        if not tool:
            muc["trang_thai"] = "KHONG_EP_TOOL"
            muc["chi_tiet"] = "Cau nay khong bi ep tool nao - model tu chon."
            ket_qua.append(muc)
            continue
        t0 = time.time()
        try:
            args = tham_so_bat_buoc(tool, ma)
            muc["tham_so"] = args
            r = rt.call_template(tool, dict(args), question=noi_dung, username="ra-soat-tool",
                                 **PHAM_VI[ma[0]])
            kq = r.get("result", r) if isinstance(r, dict) else r
            if isinstance(r, dict) and r.get("ok") is False:
                muc["trang_thai"] = "TOOL_BAO_LOI"
                muc["chi_tiet"] = str(r.get("error"))[:300]
            elif isinstance(kq, dict) and kq.get("error"):
                muc["trang_thai"] = "TOOL_BAO_LOI"
                muc["chi_tiet"] = str(kq["error"])[:300]
            elif not _co_du_lieu(kq):
                muc["trang_thai"] = "KHONG_CO_DU_LIEU"
                muc["chi_tiet"] = str(list(kq)[:8] if isinstance(kq, dict) else kq)[:200]
            else:
                muc["trang_thai"] = "CHAY_DUOC"
                muc["thieu_chieu"] = _thieu_chieu(noi_dung, kq)
        except Exception as exc:
            muc["trang_thai"] = "NEM_NGOAI_LE"
            muc["chi_tiet"] = "%s: %s" % (type(exc).__name__, str(exc)[:250])
            muc["vet"] = traceback.format_exc()[-600:]
        muc["giay"] = round(time.time() - t0, 1)
        ket_qua.append(muc)
        print("  %-4s %-34s %-16s %.1fs" % (ma, tool or "-", muc["trang_thai"], muc["giay"]),
              flush=True)
    return ket_qua


def viet_bao_cao(ket_qua, duong_dan):
    nhom = {}
    for m in ket_qua:
        nhom.setdefault(m["trang_thai"], []).append(m)
    out = ["# Rà soát tầng tool cho bộ câu hỏi UAT", ""]
    out.append("Chạy `scripts/ra_soat_tool_126_cau.py` — gọi đúng tool mà từng câu định tuyến vào, "
               "theo đúng vai trò/phạm vi của người hỏi. Không gọi model, không tốn API.")
    out.append("")
    out.append("| Trạng thái | Số câu |")
    out.append("|---|---:|")
    for trang_thai in ("NEM_NGOAI_LE", "TOOL_BAO_LOI", "KHONG_CO_DU_LIEU", "KHONG_EP_TOOL", "CHAY_DUOC"):
        if trang_thai in nhom:
            out.append("| %s | %d |" % (trang_thai, len(nhom[trang_thai])))
    out.append("")
    for trang_thai in ("NEM_NGOAI_LE", "TOOL_BAO_LOI", "KHONG_CO_DU_LIEU", "KHONG_EP_TOOL"):
        if trang_thai not in nhom:
            continue
        out.append("## %s" % trang_thai)
        out.append("")
        out.append("| Mã | Tool | Chi tiết |")
        out.append("|---|---|---|")
        for m in nhom[trang_thai]:
            out.append("| %s | `%s` | %s |" % (m["ma"], m["tool"] or "-",
                                               (m["chi_tiet"] or "").replace("|", "/")[:220]))
        out.append("")
    thieu = [m for m in nhom.get("CHAY_DUOC", []) if m["thieu_chieu"]]
    if thieu:
        out.append("## Chạy được nhưng có thể thiếu chiều câu hỏi yêu cầu")
        out.append("")
        out.append("| Mã | Tool | Câu hỏi đòi | Câu hỏi |")
        out.append("|---|---|---|---|")
        for m in thieu:
            out.append("| %s | `%s` | %s | %s |" % (m["ma"], m["tool"], ", ".join(m["thieu_chieu"]),
                                                    m["cau_hoi"][:70].replace("|", "/")))
        out.append("")
    io.open(duong_dan, "w", encoding="utf-8", newline="").write("\n".join(out) + "\n")


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Ra soat tang tool cho bo cau hoi UAT")
    ap.add_argument("--ma", help="Chi ra soat cac ma nay, cach nhau dau phay")
    ap.add_argument("--ra", default=str(ROOT / "outputs" / "ra_soat_tool_126.md"))
    args = ap.parse_args(argv)
    # Script da os.chdir sang backend/, nen duong dan tuong doi phai neo lai vao goc repo.
    duong_ra = Path(args.ra)
    if not duong_ra.is_absolute():
        duong_ra = ROOT / duong_ra
    duong_ra.parent.mkdir(parents=True, exist_ok=True)
    ma_loc = {x.strip().upper() for x in args.ma.split(",")} if args.ma else None
    rt._write_log = lambda entry: None  # khong lam ban audit log that
    ket_qua = ra_soat(ma_loc)
    viet_bao_cao(ket_qua, str(duong_ra))
    print("\nDa ghi bao cao: %s (%d cau)" % (args.ra, len(ket_qua)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
