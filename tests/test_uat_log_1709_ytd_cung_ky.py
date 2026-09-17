# -*- coding: utf-8 -*-
"""UAT nhat ky 17/09/2026 - cau C03 bao "YTD 2026 thap hon cung ky 2025 -8,7%" nhung phep so do
KHONG PHAI cung ky.

revenue_ytd_cumulative() dung date_to = ngay CUOI THANG cho MOI nam. Khi thang dang chay chua tron
(du lieu den 17/09) thi nam nay chi co 17 ngay cua thang 9, con nam truoc duoc tinh TRON 30 ngay ->
phan chenh lech bi thoi phong. Do tren du lieu that (kho local, du lieu den 15/09): bao cu -9,5%,
cung ky that -3,1% - thoi phong 6,4 diem phan tram, tuc hon gap 3 lan muc giam that.

Tool CHI canh bao ve ke hoach (ke hoach tron thang) chu khong canh bao ve phep so cung ky, nen model
khong co cach nao biet. Cac tool anh em da co co che nay (month_to_is_partial, comparison_valid) -
rieng ham nay con thieu.

Test thuan logic ngay thang, khong cham DB (da monkeypatch nguon doanh thu/ke hoach)."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import report_templates as rt


def _gan_nguon(monkeypatch, moc_du_lieu: str):
    """Doanh thu gia: moi NGAY trong ky dong gop deu 1 ty, de so lieu phu thuoc DUNG so ngay duoc
    tinh - nho vay test do chinh xac anh huong cua viec cat/khong cat ngay."""
    import datetime as dt

    def gia_revenue_by_channel(date_from, date_to, *a, **k):
        d1 = dt.date.fromisoformat(str(date_from)[:10])
        d2 = dt.date.fromisoformat(str(date_to)[:10])
        # Kho chi co du lieu den moc_du_lieu - ngay sau do khong phat sinh (giong thuc te).
        moc = dt.date.fromisoformat(moc_du_lieu)
        d2 = min(d2, moc)
        so_ngay = max(0, (d2 - d1).days + 1)
        return {"total": {"revenue": so_ngay * 1e9, "invoices": so_ngay},
                "otc": {"revenue": so_ngay * 0.6e9}, "etc": {"revenue": so_ngay * 0.4e9}}

    monkeypatch.setattr(rt, "revenue_by_channel", gia_revenue_by_channel)
    monkeypatch.setattr(rt, "latest_data_date", lambda: moc_du_lieu)
    monkeypatch.setattr(rt, "_revenue_data_month_range", lambda: ("2024-01", moc_du_lieu[:7]))
    monkeypatch.setattr(rt, "_ytd_plan",
                        lambda *a, **k: {"total": 300e9, "otc": 180e9, "etc": 120e9})


def test_thang_chua_tron_thi_co_khoi_so_cung_ky_cat_dung_ngay(monkeypatch):
    _gan_nguon(monkeypatch, "2026-09-17")

    kq = rt.revenue_ytd_cumulative("2026-09", years_back=2)

    assert kq["ky_chua_tron"] is True and kq["du_lieu_den_ngay"] == "2026-09-17"
    ck = kq["so_cung_ky_dung_ngay"]
    assert ck["cat_den_ngay"] == 17
    assert [r["date_to"] for r in ck["cac_nam"]] == ["2026-09-17", "2025-09-17"]
    # Cat dung ngay thi hai nam BANG NHAU ve so ngay (1/1..17/9) -> khong con chenh lech gia tao.
    assert ck["cac_nam"][0]["pct_change_vs_prev_year"] == 0.0


def test_so_cu_van_giu_nguyen_va_van_lech_de_doi_chieu(monkeypatch):
    """cac_nam GIU NGUYEN cach cu (het thang moi nam) de khong pha nhung noi dang dung - nhung
    chinh no la cho sinh ra con so sai neu model dung de noi 've cung ky'."""
    _gan_nguon(monkeypatch, "2026-09-17")

    kq = rt.revenue_ytd_cumulative("2026-09", years_back=2)

    nam_nay, nam_truoc = kq["cac_nam"][0], kq["cac_nam"][1]
    assert nam_nay["date_to"] == "2026-09-30" and nam_truoc["date_to"] == "2025-09-30"
    # Nam nay bi cat o 17/09 (kho het du lieu), nam truoc du 30 ngay -> am gia tao.
    assert nam_nay["pct_change_vs_prev_year"] < 0
    # Con so cung ky dung ngay thi khong am.
    assert kq["so_cung_ky_dung_ngay"]["cac_nam"][0]["pct_change_vs_prev_year"] == 0.0


def test_bat_buoc_dung_so_cung_ky_khi_ky_chua_tron(monkeypatch):
    _gan_nguon(monkeypatch, "2026-09-17")

    rule = rt.revenue_ytd_cumulative("2026-09", years_back=2)["answer_rule_cung_ky"]

    assert "BAT BUOC dung so trong so_cung_ky_dung_ngay" in rule
    assert "khong phai cung ky" in rule


def test_thang_da_tron_thi_khong_them_khoi_nao(monkeypatch):
    """Thang da tron (du lieu den ngay cuoi thang) - KHONG duoc bao dong gia, khong them khoi thua."""
    _gan_nguon(monkeypatch, "2026-08-31")

    kq = rt.revenue_ytd_cumulative("2026-08", years_back=2)

    assert "ky_chua_tron" not in kq
    assert "so_cung_ky_dung_ngay" not in kq
    assert "answer_rule_cung_ky" not in kq


def test_thang_2_chua_tron_cat_dung_ngay_o_ca_hai_nam(monkeypatch):
    """Thang 2 (nam nhuan) chua tron: ca hai nam deu phai cat ve dung ngay 20, khong duoc de nam
    truoc lay tron 28 ngay. Ham con co chot min(ngay_cat, ngay cuoi thang cua nam do) de khong bao
    gio sinh ra ngay khong ton tai (vd 29/02 cua nam thuong)."""
    _gan_nguon(monkeypatch, "2028-02-20")       # 2028 nhuan, thang 2 co 29 ngay -> 20 la chua tron

    kq = rt.revenue_ytd_cumulative("2028-02", years_back=2)

    ngay = [r["date_to"] for r in kq["so_cung_ky_dung_ngay"]["cac_nam"]]
    assert ngay == ["2028-02-20", "2027-02-20"]
    assert kq["so_cung_ky_dung_ngay"]["cac_nam"][0]["pct_change_vs_prev_year"] == 0.0
