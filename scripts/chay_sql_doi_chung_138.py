# -*- coding: utf-8 -*-
"""Chay bo SQL doi chung cho 138 cau hoi dieu hanh, doc thang tu tai lieu.

Nguon su that duy nhat la docs/bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md:
script khong chep lai SQL, chi doc block ma muc 2 va muc 3 dang giu.

Chi doc: khong goi LLM/API, khong gui Teams/email, khong ghi vao du lieu DNH.
Chi tao bang tam #sales trong tempdb theo dung block muc 2.

Chay tu root repository:
    python scripts/chay_sql_doi_chung_138.py
    python scripts/chay_sql_doi_chung_138.py --thang 2026-07 --checker S49,S50
    python scripts/chay_sql_doi_chung_138.py --liet-ke
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TAI_LIEU = os.path.join(ROOT, "docs", "bo_cau_hoi_dieu_hanh_kinh_doanh_sql_check.md")

# BLOCKED chi kiem muc san sang nen khong chay; cac nhan con lai deu ra so.
NHAN_BO_QUA = {"BLOCKED", "BLOCKED_HISTORY"}

# Chan moi thao tac ghi vao du lieu that. #sales trong tempdb duoc mien tru
# vi block muc 2 bat buoc phai tao no.
_TU_KHOA_GHI = re.compile(
    r"\b(INSERT|UPDATE|MERGE|TRUNCATE|ALTER|CREATE\s+(?!TABLE\s+#)|GRANT)\b",
    re.I,
)
_XOA_NGOAI_TEMP = re.compile(r"\bDELETE\s+FROM\s+(?!#)", re.I)
_CHON_VAO_NGOAI_TEMP = re.compile(r"\bINTO\s+(?!#)\w", re.I)
_GOI_SP = re.compile(r"\bEXEC(?:UTE)?\s+(?:dbo\.)?(\w+)", re.I)

# SP duy nhat duoc phep goi: nguon cong no chuan cua DNH, chi doc.
# Cong thuc tu tinh tu BRV_HTTDuDK tung thoi no len 4-15 lan nen khong duoc thay the.
_SP_DUOC_PHEP = {"usp_deptaccduedate_getdata"}

# Bang cua kho local (SQLite warehouse.db), khong ton tai tren Bravo.
_BANG_KHO_LOCAL = re.compile(r"\bfact_congno_khachhang\b", re.I)


def doc_tai_lieu() -> str:
    with open(TAI_LIEU, encoding="utf-8") as fh:
        return fh.read()


def _go_thut_dau(khoi: str) -> str:
    """Lay dong thut 4 dau cach trong markdown thanh SQL tho, noi lam mot batch."""
    return "\n".join(d[4:] for d in khoi.splitlines() if d.startswith("    "))


def _tach_cau_lenh(khoi: str) -> "list[str]":
    """Tach khoi markdown thanh tung cau lenh rieng.

    Moi cum dong thut lien tiep la mot cau lenh; dong trong hoac dong van xuoi
    ket thuc cum. Can tach that vi co checker (vd S24) gom nhieu cau lenh chay
    tren nguon khac nhau - noi lam mot batch thi mot cau hong keo ca khoi hong.
    """
    nhom, hien_tai = [], []
    for dong in khoi.splitlines():
        if dong.startswith("    "):
            hien_tai.append(dong[4:])
        elif hien_tai:
            nhom.append("\n".join(hien_tai).rstrip())
            hien_tai = []
    if hien_tai:
        nhom.append("\n".join(hien_tai).rstrip())
    return [n for n in nhom if n.strip()]


def tach_muc(noi_dung: str, so: int) -> str:
    dau = noi_dung.find("## %d." % so)
    cuoi = noi_dung.find("## %d." % (so + 1))
    if dau < 0:
        raise SystemExit("Khong tim thay muc %d trong tai lieu." % so)
    return noi_dung[dau:cuoi if cuoi > 0 else len(noi_dung)]


def lay_khai_bao_va_sales(noi_dung: str) -> tuple[str, str]:
    """Tra ve (cac dong DECLARE, phan con lai cua block muc 2).

    DECLARE khong song qua batch trong SQL Server nen phai gan lai truoc tung
    checker; phan tao #sales thi chi chay mot lan.
    """
    sql = _go_thut_dau(tach_muc(noi_dung, 2))
    khai_bao, con_lai = [], []
    for dong in sql.splitlines():
        (khai_bao if dong.strip().upper().startswith("DECLARE ") else con_lai).append(dong)
    if not khai_bao:
        raise SystemExit("Khong doc duoc dong DECLARE nao o muc 2.")
    return "\n".join(khai_bao), "\n".join(con_lai)


def doi_tham_so(khai_bao: str, thay: dict) -> str:
    for ten, gia_tri in thay.items():
        if gia_tri is None:
            continue
        moi, so_lan = re.subn(
            r"(DECLARE\s+@%s\s+\w+(?:\(\d+\))?\s*=\s*)[^;\r\n]+" % ten,
            lambda m: "%s'%s'" % (m.group(1), gia_tri),
            khai_bao,
            count=1,
        )
        if not so_lan:
            raise SystemExit("Khong doi duoc @%s trong khoi DECLARE." % ten)
        khai_bao = moi
    return khai_bao


def xac_dinh_as_of(cur, khai_bao: str) -> str:
    """Chốt ngày dữ liệu chung, không mặc định nhảy tới cuối tháng đang chạy.

    Với tháng hiện tại, lấy ngày mới nhất chung của ba nguồn chính. MIN của các
    mốc MAX giúp không dùng doanh thu ngày 28 để so với snapshot mới chỉ tới 27.
    Với tháng đã đóng, dùng ngày cuối tháng.
    """
    sql = """
SELECT CASE
  WHEN CONVERT(date,GETDATE())>=@MonthStart AND CONVERT(date,GETDATE())<@MonthEnd THEN
    COALESCE((
      SELECT CONVERT(date,MIN(MaxDate)) FROM (
        SELECT MAX(DocDate) MaxDate FROM #sales
          WHERE DocDate>=@MonthStart AND DocDate<@MonthEnd
        UNION ALL
        SELECT MAX(SaveDate) FROM dbo.FACT_ThongKeTinhLuong
          WHERE SaveDate>=@MonthStart AND SaveDate<@MonthEnd
        UNION ALL
        SELECT MAX(SaveDate) FROM dbo.FACT_TongHopKhachHang
          WHERE SaveDate>=@MonthStart AND SaveDate<@MonthEnd
      ) freshness WHERE MaxDate IS NOT NULL
    ),CONVERT(date,GETDATE()))
  ELSE DATEADD(day,-1,@MonthEnd)
END EffectiveAsOfDate;
"""
    cur.execute(khai_bao + "\n" + sql)
    gia_tri = cur.fetchone()[0]
    return gia_tri.isoformat() if hasattr(gia_tri, "isoformat") else str(gia_tri)


def lay_checker(noi_dung: str) -> "list[dict]":
    muc3 = tach_muc(noi_dung, 3)
    ra = []
    for m in re.finditer(r"^### (S\d+) . (.+?)$(.*?)(?=^### S|\Z)", muc3, flags=re.M | re.S):
        ma, tieu_de, than = m.group(1), m.group(2).strip(), m.group(3)
        nhan = tieu_de.rsplit(" ", 1)[-1] if " " in tieu_de else ""
        if nhan not in {"READY", "READY_CURRENT", "PARTIAL", "DERIVED", "BLOCKED", "BLOCKED_HISTORY"}:
            nhan = "KHONG_RO"
        ra.append({
            "ma": ma, "tieu_de": tieu_de, "nhan": nhan,
            "cau_lenh": _tach_cau_lenh(than),
        })
    if not ra:
        raise SystemExit("Khong doc duoc checker nao o muc 3.")
    return ra


def lay_mapping(noi_dung: str) -> "dict[str, list[str]]":
    muc4 = tach_muc(noi_dung, 4)
    theo_checker: "dict[str, list[str]]" = {}
    for cau, ck in re.findall(
        r"^\|\s*([CMV]\d{2})\s*\|.*\|\s*(S\d+)\s*\|\s*\w+\s*\|\s*$", muc4, flags=re.M
    ):
        theo_checker.setdefault(ck, []).append(cau)
    return theo_checker


def lay_cau_hoi(noi_dung: str) -> "list[dict]":
    """Doc 138 cau hoi kem noi dung va checker phu trach, giu nguyen thu tu bang."""
    muc4 = tach_muc(noi_dung, 4)
    ra = []
    for ma, chu, ck in re.findall(
        r"^\|\s*([CMV]\d{2})\s*\|\s*(.+?)\s*\|\s*(S\d+)\s*\|\s*\w+\s*\|\s*$", muc4, flags=re.M
    ):
        ra.append({"ma": ma, "noi_dung": chu, "checker": ck})
    return ra


def kiem_chi_doc(sql: str, ma: str) -> None:
    for bieu_thuc, ly_do in (
        (_TU_KHOA_GHI, "co tu khoa ghi du lieu"),
        (_XOA_NGOAI_TEMP, "co DELETE ngoai bang tam"),
        (_CHON_VAO_NGOAI_TEMP, "co SELECT INTO ngoai bang tam"),
    ):
        m = bieu_thuc.search(sql)
        if m:
            raise SystemExit(
                "Tu choi chay %s: %s (%r). Script nay chi duoc phep doc."
                % (ma, ly_do, m.group(0))
            )
    for m in _GOI_SP.finditer(sql):
        if m.group(1).lower() not in _SP_DUOC_PHEP:
            raise SystemExit(
                "Tu choi chay %s: goi SP ngoai danh sach cho phep (%r)." % (ma, m.group(1))
            )


def _commit_hien_tai() -> str:
    try:
        ra = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        return ra.stdout.strip() or "khong-ro"
    except Exception:
        return "khong-ro"


def chay(cur, sql: str, gioi_han_dong: int) -> "list[dict]":
    """Chay mot batch, gom moi result set tra ve."""
    cur.execute(sql)
    ket_qua = []
    while True:
        if cur.description:
            cot = [c[0] for c in cur.description]
            so_dong = 0
            dong_mau = []
            while True:
                lo = cur.fetchmany(1000)
                if not lo:
                    break
                so_dong += len(lo)
                if len(dong_mau) < gioi_han_dong:
                    dong_mau.extend(lo[:gioi_han_dong - len(dong_mau)])
            mau = [
                {c: (v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else
                     float(v) if hasattr(v, "as_tuple") else v)
                 for c, v in zip(cot, d)}
                for d in dong_mau
            ]
            ket_qua.append({"cot": cot, "so_dong": so_dong, "mau": mau})
        if not cur.nextset():
            break
    return ket_qua


_TEN_TRANG_THAI = {
    "CHAY_DUOC": "Chạy được",
    "CHAY_MOT_PHAN": "Chạy một phần",
    "KHO_LOCAL": "Cần kho local",
    "LOI": "Lỗi SQL",
    "BO_QUA": "Chưa có dữ liệu",
}

_MUC_SAN_SANG = {
    "READY": "Đủ nguồn để kiểm tra",
    "READY_CURRENT": "Chỉ có số hiện tại",
    "PARTIAL": "Thiếu một phần dữ liệu",
    "DERIVED": "Cần DNH chốt công thức",
    "BLOCKED": "Chưa có nguồn dữ liệu",
    "BLOCKED_HISTORY": "Chưa đủ dữ liệu lịch sử",
    "KHONG_RO": "Chưa phân loại",
}


def _o_markdown(gia_tri) -> str:
    if gia_tri is None:
        return "—"
    if isinstance(gia_tri, float):
        if gia_tri.is_integer():
            gia_tri = f"{gia_tri:,.0f}"
        else:
            gia_tri = f"{gia_tri:,.4f}".rstrip("0").rstrip(".")
    chu = str(gia_tri).replace("\r", " ").replace("\n", "<br>")
    return chu.replace("|", "\\|")


def _tong_dong(muc: dict) -> int:
    return sum(
        bang.get("so_dong", 0)
        for cau_lenh in muc.get("cau_lenh", [])
        for bang in cau_lenh.get("bang", [])
    )


def _ly_do_than_thien(muc: dict) -> str:
    if muc["trang_thai"] == "BO_QUA":
        if muc.get("nhan") == "BLOCKED_HISTORY":
            return "Chưa tích lũy đủ snapshot lịch sử để trả lời theo tháng."
        return "Chưa có nguồn dữ liệu đã được DNH xác nhận."
    if muc["trang_thai"] == "KHO_LOCAL":
        return "Cần đồng bộ dữ liệu vào kho local trước khi đối chiếu."
    if muc["trang_thai"] == "CHAY_MOT_PHAN":
        return "Nguồn Bravo đã chạy; phần tổng hợp ở kho local chưa sẵn sàng."
    for cau_lenh in muc.get("cau_lenh", []):
        if cau_lenh.get("loi"):
            return cau_lenh["loi"]
    return muc.get("ly_do") or "Cần kiểm tra thủ công."


def _ghi_bao_cao_markdown(bao_cao: dict, duong_dan: str) -> None:
    """Ghi báo cáo đọc được bởi người nghiệp vụ; không xuất JSON thô."""
    dong = [
        "# Báo cáo kiểm tra đáp án cho 138 câu hỏi điều hành",
        "",
        "> **Lưu ý:** “Chạy được” chỉ xác nhận truy vấn thực thi thành công. Đáp án chỉ được dùng "
        "cho UAT khi công thức nghiệp vụ đã được DNH xác nhận.",
        "",
        f"- Thời điểm chạy: **{_o_markdown(bao_cao['chay_luc'])}**",
        f"- Phiên bản mã nguồn: **{_o_markdown(bao_cao['commit'])}**",
        f"- Số dòng lớp bán hàng `#sales`: **{bao_cao.get('so_dong_sales', 0):,}**",
        f"- Tổng thời gian: **{bao_cao.get('thoi_gian_giay', 0):,.1f} giây**",
        "",
        "## Tổng quan",
        "",
        "| Kết quả | Số nhóm kiểm tra | Số câu hỏi liên quan |",
        "|---|---:|---:|",
    ]
    for trang_thai, so_luong in sorted(bao_cao["tong_hop"].items()):
        so_cau = sum(
            len(muc.get("cau_hoi", []))
            for muc in bao_cao["ket_qua"]
            if muc["trang_thai"] == trang_thai
        )
        dong.append(
            f"| {_TEN_TRANG_THAI.get(trang_thai, trang_thai)} | {so_luong} | {so_cau} |"
        )

    can_xu_ly = [m for m in bao_cao["ket_qua"] if m["trang_thai"] != "CHAY_DUOC"]
    dong += [
        "",
        "## Các mục cần xử lý trước UAT",
        "",
        "| Mã kiểm tra | Câu hỏi | Mức sẵn sàng | Kết quả chạy | Lý do |",
        "|---|---|---|---|---|",
    ]
    if not can_xu_ly:
        dong.append("| — | — | — | Tất cả chạy được | — |")
    for muc in can_xu_ly:
        dong.append(
            "| {ma} | {cau} | {nhan} | {chay} | {ly_do} |".format(
                ma=_o_markdown(muc["ma"]),
                cau=_o_markdown(", ".join(muc.get("cau_hoi", [])) or "Không có câu sử dụng"),
                nhan=_o_markdown(_MUC_SAN_SANG.get(muc["nhan"], muc["nhan"])),
                chay=_o_markdown(_TEN_TRANG_THAI.get(muc["trang_thai"], muc["trang_thai"])),
                ly_do=_o_markdown(_ly_do_than_thien(muc)),
            )
        )

    dong += [
        "",
        "## Danh sách kết quả",
        "",
        "| Mã kiểm tra | Câu hỏi | Mức sẵn sàng | Kết quả | Số dòng | Thời gian |",
        "|---|---|---|---|---:|---:|",
    ]
    for muc in bao_cao["ket_qua"]:
        dong.append(
            "| {ma} | {cau} | {nhan} | {chay} | {so_dong:,} | {giay:,.2f}s |".format(
                ma=_o_markdown(muc["ma"]),
                cau=_o_markdown(", ".join(muc.get("cau_hoi", [])) or "—"),
                nhan=_o_markdown(_MUC_SAN_SANG.get(muc["nhan"], muc["nhan"])),
                chay=_o_markdown(_TEN_TRANG_THAI.get(muc["trang_thai"], muc["trang_thai"])),
                so_dong=_tong_dong(muc),
                giay=muc.get("thoi_gian_giay", 0),
            )
        )

    dong += ["", "## Dữ liệu mẫu", ""]
    for muc in bao_cao["ket_qua"]:
        cac_bang = [
            bang
            for cau_lenh in muc.get("cau_lenh", [])
            for bang in cau_lenh.get("bang", [])
        ]
        if not cac_bang:
            continue
        dong += [
            f"<details><summary><strong>{muc['ma']}</strong> — "
            f"{_o_markdown(', '.join(muc.get('cau_hoi', [])) or 'không có câu sử dụng')}"
            f" — {_tong_dong(muc):,} dòng</summary>",
            "",
        ]
        for thu_tu, bang in enumerate(cac_bang, 1):
            cot_hien = bang.get("cot", [])[:10]
            if len(cac_bang) > 1:
                dong += [f"Kết quả #{thu_tu}:", ""]
            if not bang.get("mau"):
                dong += ["*Truy vấn không trả về dòng dữ liệu nào.*", ""]
                continue
            dong.append("| " + " | ".join(_o_markdown(c) for c in cot_hien) + " |")
            dong.append("|" + "|".join("---" for _ in cot_hien) + "|")
            for mau in bang["mau"]:
                dong.append("| " + " | ".join(_o_markdown(mau.get(c)) for c in cot_hien) + " |")
            if len(bang.get("cot", [])) > len(cot_hien):
                dong += ["", f"*Đã ẩn {len(bang['cot']) - len(cot_hien)} cột phụ để báo cáo dễ đọc.*"]
            if bang.get("so_dong", 0) > len(bang.get("mau", [])):
                dong += ["", f"*Chỉ hiển thị {len(bang['mau'])}/{bang['so_dong']:,} dòng.*"]
            dong.append("")
        dong += ["</details>", ""]

    os.makedirs(os.path.dirname(os.path.abspath(duong_dan)), exist_ok=True)
    with open(duong_dan, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(dong).rstrip() + "\n")


def _bang_markdown(bang: dict) -> "list[str]":
    """Vẽ bảng mẫu đầy đủ cột, không diễn giải mẫu thành đáp án hoàn chỉnh."""
    cot = bang.get("cot", [])
    if not bang.get("mau"):
        return ["*Truy vấn chạy được nhưng không trả về dòng nào.*", ""]
    dong = [
        "| " + " | ".join(_o_markdown(c) for c in cot) + " |",
        "|" + "|".join("---" for _ in cot) + "|",
    ]
    for mau in bang["mau"]:
        dong.append("| " + " | ".join(_o_markdown(mau.get(c)) for c in cot) + " |")
    if bang.get("so_dong", 0) > len(bang["mau"]):
        dong += ["", "*Truy vấn có %s dòng; bảng này chỉ hiển thị %d dòng mẫu, không phải toàn bộ đáp án.*"
                 % (format(bang["so_dong"], ","), len(bang["mau"]))]
    dong.append("")
    return dong


def _ghi_dap_an_theo_cau_hoi(bao_cao: dict, cau_hoi: "list[dict]", duong_dan: str) -> None:
    """Ghi mot file duy nhat: moi cau hoi kem SQL kiem tra va dap an chay ra.

    To chuc theo CAU HOI chu khong theo checker, va lap lai SQL o moi cau de tung
    muc doc duoc doc lap - day la file de doi chieu cau tra loi cua chatbot.
    """
    theo_ma = {m["ma"]: m for m in bao_cao["ket_qua"]}
    dung = [c for c in cau_hoi if c["checker"] in theo_ma]

    dem_nhan = {}
    for c in dung:
        nhan = theo_ma[c["checker"]]["nhan"]
        dem_nhan[nhan] = dem_nhan.get(nhan, 0) + 1
    du_san_sang = sum(
        1 for c in dung
        if theo_ma[c["checker"]]["nhan"] == "READY"
        and theo_ma[c["checker"]]["trang_thai"] == "CHAY_DUOC"
    )
    chi_hien_tai = dem_nhan.get("READY_CURRENT", 0)
    can_chot = dem_nhan.get("PARTIAL", 0) + dem_nhan.get("DERIVED", 0)
    chua_co = dem_nhan.get("BLOCKED", 0) + dem_nhan.get("BLOCKED_HISTORY", 0)

    dong = [
        "# Kết quả đối chiếu bộ câu hỏi điều hành kinh doanh",
        "",
        "Mỗi mục gồm câu hỏi, SQL kiểm tra và kết quả mẫu chạy trực tiếp trên Bravo.",
        "Dùng file này làm bằng chứng đối chiếu; chỉ các mục đủ nguồn và đã chốt công thức mới được dùng làm đáp án UAT.",
        "",
        "> **Lưu ý:** đáp án chỉ đúng tới mức công thức trong SQL đúng. Các mục ghi *Cần DNH chốt "
        "công thức* hoặc *Thiếu một phần dữ liệu* thì con số chưa được dùng làm chuẩn nghiệm thu.",
        "",
        f"- Thời điểm chạy: **{_o_markdown(bao_cao['chay_luc'])}**",
        f"- Phiên bản mã nguồn: **{_o_markdown(bao_cao['commit'])}**",
        f"- Nguồn SQL: `{bao_cao['tai_lieu']}`",
        f"- Lớp bán hàng `#sales`: **{bao_cao.get('so_dong_sales', 0):,} dòng**",
        f"- Tổng số câu được liệt kê: **{len(dung)}**",
        f"- Đủ nguồn và truy vấn chạy được: **{du_san_sang}**",
        f"- Chỉ có số hiện tại: **{chi_hien_tai}**",
        f"- Cần DNH chốt công thức hoặc còn thiếu một phần: **{can_chot}**",
        f"- Chưa có nguồn hoặc chưa đủ lịch sử: **{chua_co}**",
        "",
        "Tham số kỳ dùng cho mọi truy vấn:",
        "",
        "```sql",
        bao_cao["khai_bao_tham_so"],
        "```",
        "",
        "---",
        "",
    ]

    for c in dung:
        muc = theo_ma[c["checker"]]
        dong += [
            "## %s — %s" % (c["ma"], c["noi_dung"]),
            "",
            "- Mã kiểm tra: `%s` — %s" % (
                c["checker"], _MUC_SAN_SANG.get(muc["nhan"], muc["nhan"])),
            "- Kết quả chạy: %s" % _TEN_TRANG_THAI.get(muc["trang_thai"], muc["trang_thai"]),
        ]
        if muc["trang_thai"] != "CHAY_DUOC":
            dong.append("- Lý do: %s" % _o_markdown(_ly_do_than_thien(muc)))
        dong.append("")

        cac_sql = muc.get("sql", [])
        ghi_chay = muc.get("cau_lenh", [])
        for thu_tu, sql in enumerate(cac_sql, 1):
            nhieu = len(cac_sql) > 1
            dong += ["### SQL kiểm tra" + (" #%d" % thu_tu if nhieu else ""), "",
                     "```sql", sql, "```", ""]
            ghi = ghi_chay[thu_tu - 1] if thu_tu <= len(ghi_chay) else {}
            dong += ["### Kết quả đối chiếu" + (" #%d" % thu_tu if nhieu else ""), ""]
            if ghi.get("trang_thai") == "CHAY_DUOC":
                for bang in ghi.get("bang", []):
                    dong += _bang_markdown(bang)
            else:
                dong += ["*Chưa có đáp án: %s*" % _o_markdown(
                    ghi.get("ly_do") or ghi.get("loi")
                    or muc.get("ly_do") or "chưa chạy"), ""]
        if not cac_sql:
            dong += ["*Không có SQL trong tài liệu cho mã kiểm tra này.*", ""]
        dong += ["---", ""]

    os.makedirs(os.path.dirname(os.path.abspath(duong_dan)), exist_ok=True)
    with open(duong_dan, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(dong).rstrip() + "\n")


def main() -> int:
    # May van hanh Windows co the mac dinh CP1252; help/bao cao co tieng Viet phai in duoc.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--thang", help="Thang can doi chung, dang YYYY-MM (mac dinh: theo tai lieu)")
    ap.add_argument("--tu-ngay", help="Ghi de @FromDate, dang YYYY-MM-DD")
    ap.add_argument("--den-ngay", help="Ghi de @ToDate, dang YYYY-MM-DD")
    ap.add_argument("--as-of", help="Ghi de ngay chot du lieu, dang YYYY-MM-DD")
    ap.add_argument("--checker", help="Chi chay cac ma nay, cach nhau bang dau phay")
    ap.add_argument("--gioi-han-dong", type=int, default=5, help="So dong mau giu lai moi bang")
    ap.add_argument(
        "--ra",
        default=os.path.join(ROOT, "docs", "bao_cao_sql_doi_chung_138.md"),
        help="File báo cáo Markdown thân thiện với người đọc",
    )
    ap.add_argument(
        "--dap-an",
        nargs="?",
        const=os.path.join(ROOT, "docs", "dap_an_bo_cau_hoi_dieu_hanh.md"),
        help="Xuat file doi chieu theo cau hoi: cau hoi + SQL + ket qua mau",
    )
    ap.add_argument("--liet-ke", action="store_true", help="Chi liet ke checker, khong ket noi DB")
    tham_so = ap.parse_args()

    noi_dung = doc_tai_lieu()
    checker = lay_checker(noi_dung)
    mapping = lay_mapping(noi_dung)
    cau_hoi = lay_cau_hoi(noi_dung)

    chon = None
    if tham_so.checker:
        chon = {x.strip().upper() for x in tham_so.checker.split(",") if x.strip()}
        thieu = chon - {c["ma"] for c in checker}
        if thieu:
            raise SystemExit("Khong co checker: %s" % ", ".join(sorted(thieu)))
        checker = [c for c in checker if c["ma"] in chon]

    if tham_so.liet_ke:
        for c in checker:
            cau = mapping.get(c["ma"], [])
            print("%-5s %-16s %2d cau  %s" % (
                c["ma"], c["nhan"], len(cau), ", ".join(cau) or "(mo coi)"))
        print("\nTong: %d checker, %d cau duoc phu."
              % (len(checker), sum(len(v) for v in mapping.values())))
        return 0

    for ten, gia_tri in (("--tu-ngay", tham_so.tu_ngay),
                         ("--den-ngay", tham_so.den_ngay),
                         ("--as-of", tham_so.as_of)):
        if gia_tri:
            try:
                dt.datetime.strptime(gia_tri, "%Y-%m-%d")
            except ValueError:
                raise SystemExit("%s phai dang YYYY-MM-DD." % ten)

    thay = {"FromDate": tham_so.tu_ngay, "ToDate": tham_so.den_ngay,
            "AsOfDate": tham_so.as_of}
    if tham_so.thang:
        try:
            dau_thang = dt.datetime.strptime(tham_so.thang + "-01", "%Y-%m-%d").date()
        except ValueError:
            raise SystemExit("--thang phai dang YYYY-MM.")
        thay["MonthStart"] = dau_thang.isoformat()
        if not tham_so.den_ngay:
            if dau_thang.month == 12:
                dau_thang_sau = dt.date(dau_thang.year + 1, 1, 1)
            else:
                dau_thang_sau = dt.date(dau_thang.year, dau_thang.month + 1, 1)
            thay["ToDate"] = dau_thang_sau.isoformat()

    khai_bao, tao_sales = lay_khai_bao_va_sales(noi_dung)
    khai_bao = doi_tham_so(khai_bao, thay)

    from src.database import _get_bravo_engine  # noqa: E402

    try:
        from main import load_env  # noqa: E402
        load_env()
    except Exception as loi:
        print("Canh bao: khong nap duoc load_env tu main.py (%s)." % loi)

    engine = _get_bravo_engine()
    if engine is None:
        raise SystemExit(
            "Thieu bien BRAVO_SQL_* trong .env nen khong ket noi duoc Bravo. "
            "Script nay phai chay tren may co ket noi Bravo."
        )

    bat_dau = time.perf_counter()
    bao_cao = {
        "chay_luc": dt.datetime.now().isoformat(timespec="seconds"),
        "commit": _commit_hien_tai(),
        "tai_lieu": os.path.relpath(TAI_LIEU, ROOT).replace("\\", "/"),
        "khai_bao_tham_so": khai_bao,
        "tong_checker": len(checker),
        "ket_qua": [],
    }

    try:
        raw = engine.raw_connection()
    except Exception as loi:
        raise SystemExit(
            "Không kết nối được Bravo. Kiểm tra VPN/mạng hoặc trạng thái máy 24 rồi chạy lại. "
            "Chi tiết: %s" % str(loi)[:300]
        ) from None
    try:
        cur = raw.cursor()
        kiem_chi_doc(tao_sales, "block #sales muc 2")
        print("Tao #sales theo block muc 2 ...")
        cur.execute(khai_bao + "\n" + tao_sales)
        while cur.nextset():
            pass
        cur.execute("SELECT COUNT(1) FROM #sales")
        so_dong_sales = cur.fetchone()[0]
        bao_cao["so_dong_sales"] = so_dong_sales
        print("  #sales co %s dong.\n" % format(so_dong_sales, ","))

        if not tham_so.as_of:
            as_of = xac_dinh_as_of(cur, khai_bao)
            khai_bao = doi_tham_so(khai_bao, {"AsOfDate": as_of})
            print("  Ngay chot du lieu chung: %s.\n" % as_of)
        bao_cao["khai_bao_tham_so"] = khai_bao

        for c in checker:
            muc = {
                "ma": c["ma"], "tieu_de": c["tieu_de"], "nhan": c["nhan"],
                "cau_hoi": mapping.get(c["ma"], []),
                "sql": c["cau_lenh"],
            }
            if c["nhan"] in NHAN_BO_QUA:
                muc["trang_thai"] = "BO_QUA"
                muc["ly_do"] = "Nhan %s: chi kiem muc san sang, khong ra so." % c["nhan"]
                print("%-5s BO QUA (%s)" % (c["ma"], c["nhan"]))
            else:
                muc["cau_lenh"] = []
                bat_dau_checker = time.perf_counter()
                for thu_tu, cau in enumerate(c["cau_lenh"], 1):
                    ghi = {"thu_tu": thu_tu}
                    if _BANG_KHO_LOCAL.search(cau):
                        ghi["trang_thai"] = "KHO_LOCAL"
                        ghi["ly_do"] = ("Truy van bang cua warehouse.db, khong co tren Bravo; "
                                        "chay bang scripts/business_stress_suite.py.")
                    else:
                        try:
                            kiem_chi_doc(cau, c["ma"])
                            ghi["bang"] = chay(cur, khai_bao + "\n" + cau,
                                               tham_so.gioi_han_dong)
                            ghi["trang_thai"] = "CHAY_DUOC"
                        except SystemExit:
                            raise
                        except Exception as loi:
                            ghi["trang_thai"] = "LOI"
                            ghi["loi"] = str(loi)[:500]
                    muc["cau_lenh"].append(ghi)
                muc["thoi_gian_giay"] = round(time.perf_counter() - bat_dau_checker, 3)
                tt = {g["trang_thai"] for g in muc["cau_lenh"]}
                muc["trang_thai"] = ("LOI" if "LOI" in tt
                                     else "CHAY_MOT_PHAN" if "KHO_LOCAL" in tt and len(tt) > 1
                                     else "KHO_LOCAL" if tt == {"KHO_LOCAL"}
                                     else "CHAY_DUOC")
                tong = sum(b["so_dong"] for g in muc["cau_lenh"]
                           for b in g.get("bang", []))
                loi_dau = next((g.get("loi", "") for g in muc["cau_lenh"]
                                if g["trang_thai"] == "LOI"), "")
                print("%-5s %-14s %d cau lenh, %s dong %s"
                      % (c["ma"], muc["trang_thai"], len(muc["cau_lenh"]), tong,
                         loi_dau[:80]))
            bao_cao["ket_qua"].append(muc)
    finally:
        raw.close()

    dem = {}
    for muc in bao_cao["ket_qua"]:
        dem[muc["trang_thai"]] = dem.get(muc["trang_thai"], 0) + 1
    bao_cao["tong_hop"] = dem
    bao_cao["thoi_gian_giay"] = round(time.perf_counter() - bat_dau, 3)

    _ghi_bao_cao_markdown(bao_cao, tham_so.ra)
    if tham_so.dap_an:
        _ghi_dap_an_theo_cau_hoi(bao_cao, cau_hoi, tham_so.dap_an)

    print("\n" + "-" * 58)
    for k in sorted(dem):
        print("%-12s %d" % (k, dem[k]))
    print("Bao cao Markdown: %s" % os.path.relpath(tham_so.ra, ROOT).replace("\\", "/"))
    if tham_so.dap_an:
        print("File dap an     : %s"
              % os.path.relpath(tham_so.dap_an, ROOT).replace("\\", "/"))
    return 1 if dem.get("LOI") else 0


if __name__ == "__main__":
    raise SystemExit(main())
