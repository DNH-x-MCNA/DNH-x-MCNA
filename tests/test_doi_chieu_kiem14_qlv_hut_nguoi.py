"""Phep kiem 14 cua scripts/doi_chieu_so_lieu_tool_moi.py phai BAO LECH khi QLV hut nguoi, khong duoc vo.

Truoc 29/09/2026 chuoi chi tiet viet `"..." + chr(10) + "%s" % (3 gia tri)`: "%" tinh truoc "+" nen chi
"%s" nhan ca bo 3 -> TypeError dung luc phat hien doi thieu nguoi (script chay tren may 24 ngay 09/10 de
lay so cho bien ban nghiem thu).
"""

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "doi_chieu_so_lieu_tool_moi_kiem14", ROOT / "scripts" / "doi_chieu_so_lieu_tool_moi.py")
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def _gia_doi(monkeypatch, so_dms):
    monkeypatch.setattr(checker, "_wq", lambda sql, params=(): [{"c": "QL1"}, {"c": "QL2"}])
    monkeypatch.setattr(checker.rt, "_team_of_qlv",
                        lambda ma: [{"employee_code": "TDV%d" % i} for i in range(3)])
    monkeypatch.setattr(checker.rt, "_get_team_dms_ids", lambda ma: ["D"] * so_dms[ma])
    monkeypatch.setattr(checker, "_loi", [])
    monkeypatch.setattr(checker, "_dat", [0])


def test_qlv_hut_nguoi_bao_lech_kem_chi_tiet_khong_vo(monkeypatch, capsys):
    _gia_doi(monkeypatch, {"QL1": 3, "QL2": 1})

    checker.kiem_14_moi_QLV_phan_giai_du_doi()

    out = capsys.readouterr().out
    assert checker._loi == ["2 QLV: phan giai du doi"]
    assert "1/2 QLV bi hut nguoi" in out
    assert "QL2: cay to chuc 3 TDV nhung chi phan giai 1 DMSId (hut 2 nguoi)" in out


def test_qlv_du_doi_thi_dat(monkeypatch, capsys):
    _gia_doi(monkeypatch, {"QL1": 3, "QL2": 3})

    checker.kiem_14_moi_QLV_phan_giai_du_doi()

    assert checker._loi == [] and checker._dat == [1]
    assert "[DAT ] 2 QLV: phan giai du doi" in capsys.readouterr().out
