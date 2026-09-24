"""fact_thongketinhluong phai dong bo TOAN BO lich su, khong cat theo cua so ngay.

24/09/2026: bang nay la nguon CHOT DOI cho ky qua khu (_team_of_qlv_tu_luong, PR #63/#80). Cua so
400 ngay cu bat dau 17/08/2025, nen cau hoi QLV "so cung ky nam ngoai" cho ky truoc do roi ve doi
SAU ky. Do bang Bravo lam doi chung, thang 07/2025: 15/16 QLV lech, sai so tuyet doi 6,27 ty (18,7%);
sau khi nap du lich su: 0/25 lech. Du lieu gia, khong cham Bravo that.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import sync_warehouse as sw  # noqa: E402


class _GiaConn:
    def execute(self, *a, **k):
        return self

    def executemany(self, *a, **k):
        return self

    def commit(self):
        pass

    def close(self):
        pass


def _bat_moc(monkeypatch):
    goi = {}

    def gia_bravo_query(sql, **params):
        goi["sql"], goi["params"] = sql, params
        return [], []

    monkeypatch.setattr(sw, "bravo_query", gia_bravo_query)
    monkeypatch.setattr(sw, "get_conn", lambda: _GiaConn())
    return goi


def test_mac_dinh_lay_toan_bo_lich_su(monkeypatch):
    goi = _bat_moc(monkeypatch)
    sw.sync_fact_thongketinhluong()
    moc = str(goi["params"]["a"])
    assert moc <= "2025-01-01", (
        "Mac dinh phai lay tu truoc 01/2025 (moc dau tien tren Bravo). Neu ra mot ngay gan day thi "
        "da quay lai cua so co dinh - cau hoi QLV so cung ky nam ngoai se chot sai doi.")


def test_van_gioi_han_duoc_neu_truyen_days(monkeypatch):
    goi = _bat_moc(monkeypatch)
    sw.sync_fact_thongketinhluong(days=30)
    import datetime as dt
    assert str(goi["params"]["a"]) == str(dt.date.today() - dt.timedelta(days=30))
