# -*- coding: utf-8 -*-
"""29/09/2026 - khoi dong lai backend (moi lan deploy) khong duoc dong bo Bravo ngay neu vua dong bo xong.

sync_scheduler.ps1 dat $lastRunTime = nam 2000 khi khoi dong nen moi lan Restart-Service DNH_Chatbot_Backend
deu doc Bravo them mot lan ngoai lich (29/09: 14:10 va 14:39, dung luc DNH dang soi tai may chu Bravo).
Test chay THAT phan khoi dong cua script bang PowerShell (cat truoc vong lap vo han), voi duong dan tam."""
import datetime as dt
import os
import shutil
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "backend", "sync_scheduler.ps1")
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")

pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Can PowerShell de chay script scheduler")


def _thay_dong(src, bat_dau, dong_moi):
    """Thay dong gan bien dau tien bat dau bang `bat_dau` (vd '$LOG = ')."""
    dong = src.splitlines()
    i = next(n for n, d in enumerate(dong) if d.startswith(bat_dau))
    dong[i] = dong_moi
    return "\n".join(dong)


def _moc_khoi_dong(tmp_path, noi_dung_ket_qua=None, cach_day_phut=10):
    ket_qua = tmp_path / "_sync_result.txt"
    if noi_dung_ket_qua is not None:
        ket_qua.write_text(noi_dung_ket_qua, encoding="utf-8")
        moc = (dt.datetime.now() - dt.timedelta(minutes=cach_day_phut)).timestamp()
        os.utime(ket_qua, (moc, moc))
    src = open(SCRIPT, encoding="utf-8").read()
    src = _thay_dong(src, "$LOG = ", '$LOG = "%s"' % (tmp_path / "scheduler.log"))
    src = _thay_dong(src, "$RESULT_FILE = ", '$RESULT_FILE = "%s"' % ket_qua)
    phan_dau = src.split("while ($true)")[0]      # bo vong lap vo han, khong goi Do-Sync
    ban_thu = tmp_path / "thu.ps1"
    ban_thu.write_text(phan_dau + "\nWrite-Output $lastRunTime.ToString('yyyy-MM-ddTHH:mm')\n",
                       encoding="utf-8-sig")
    out = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ban_thu)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip().splitlines()[-1]


def test_vua_dong_bo_ok_thi_khoi_dong_lai_khong_dong_bo_ngay(tmp_path):
    moc = _moc_khoi_dong(tmp_path, "OK", cach_day_phut=10)
    assert moc == (dt.datetime.now() - dt.timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
    assert "cho toi dung lich" in (tmp_path / "scheduler.log").read_text(encoding="utf-8-sig")


def test_lan_truoc_loi_thi_dong_bo_ngay(tmp_path):
    assert _moc_khoi_dong(tmp_path, "FAIL").startswith("2000-01-01")


def test_chua_co_file_ket_qua_thi_dong_bo_ngay(tmp_path):
    assert _moc_khoi_dong(tmp_path, None).startswith("2000-01-01")
