"""28/09/2026: repo DNH-x-MCNA public tu 07/2026 - da lo mat khau Supabase (54 script, da xoa) va 6 URL webhook Power
Automate (da chuyen sang .env). Test nay chan khoa MOI bi commit: quet moi file git dang theo doi, bao file:dong, KHONG
in gia tri. Gia tri mau (<...>, ${...}, {bien}, x..., password...) duoc bo qua."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parents[1]
MAU = re.compile(r"^(<.*>|\$\{.*\}|\{.*\}|%.*|x+|\*+|\.{3}|password|pass|mat_?khau|your.*|changeme|example.*|user|secret)$",
                 re.I)
KIEU = {
    "mat khau trong URL CSDL": re.compile(r"(?:postgres(?:ql)?|mssql\+pyodbc|mssql|mysql)://[^:@/\s'\"]+:([^@/\s'\"]+)@"),
    "chu ky webhook (sig=)": re.compile(r"[?&]sig=([A-Za-z0-9_%\-]{20,})"),
    "mat khau chuoi ket noi ODBC": re.compile(r"(?i)\b(?:PWD|Password)=([^;\"'\s{}<>$]+);"),
}
BO_QUA_DUOI = {".db", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".accdb", ".ico", ".woff",
               ".woff2"}


def _la_mau(gia_tri: str) -> bool:
    return bool(MAU.match(gia_tri)) or len(set(gia_tri)) <= 2


def test_khong_file_nao_trong_repo_chua_khoa_that():
    if not shutil.which("git"):
        pytest.skip("can git de liet ke file dang theo doi")
    files = subprocess.run(["git", "-C", str(GOC), "ls-files"], capture_output=True, text=True,
                           encoding="utf-8").stdout.splitlines()
    assert files, "git ls-files rong - kiem sai thu muc"
    loi = []
    for ten_file in files:
        path = GOC / ten_file
        if path.suffix.lower() in BO_QUA_DUOI or not path.is_file():
            continue
        try:
            noi_dung = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for so_dong, dong in enumerate(noi_dung.splitlines(), 1):
            for loai, kieu in KIEU.items():
                if any(not _la_mau(m.group(1)) for m in kieu.finditer(dong)):
                    loi.append(f"{ten_file}:{so_dong} ({loai})")
    assert not loi, ("Co khoa that trong file dang duoc git theo doi - dua gia tri vao .env, file nay chi ghi ten bien:\n"
                     + "\n".join(loi[:30]))


# Chuoi mau duoc GHEP tu nhieu doan de chinh file nay khong bi bo quet o tren bat (dau nhay cat ngang mau).
@pytest.mark.parametrize("dong, co_khoa", [
    ("postgresql://" + "postgres.abcdefghijklmnopqrst:" + "Trang12345@aws-1.pooler.supabase.com:5432/postgres", True),
    ("CLOUD_DB_URL=postgresql://" + "postgres:password@host:5432/postgres", False),
    ("mssql+pyodbc://" + "{uid}:{encoded_pwd}@{server}/{database}", False),
    ("https://flow.example/invoke?api-version=1&" + "sig=" + "Ab3dEf6hIj9kLm2nOp5qRs8tUv", True),
    ("sig=" + "x" * 43, False),
    ("PWD=" + "Mk@thatSu123;", True),
    ("PWD=" + "<MAT_KHAU>;", False),
])
def test_bo_quet_phan_biet_khoa_that_voi_gia_tri_mau(dong, co_khoa):
    thay = any(not _la_mau(m.group(1)) for kieu in KIEU.values() for m in kieu.finditer(dong))
    assert thay is co_khoa
