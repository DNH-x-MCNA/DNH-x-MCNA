"""Cham lai UAT 24/09 muc 02: hoi khong neu ky thi phan tich chat luong khach moi phai dung THANG TRON.

Truoc do tool lay thang cua snapshot moi nhat (09/2026, moi den 24/09): 221 khach moi MB, mua lai 11,3% trong
24 ngay - thap gia tao - trong khi tieu chi la ky 8/2026 (627 khach, MB 328). Va cau tra loi khong noi khach
moi lay tu co IsNC cua Bravo. Du lieu gia: snapshot moi nhat 01/09 (thang 9 chua tron)."""
import report_templates as rt
from test_m24_isnc_quality import kho  # noqa: F401  (fixture)


def test_khong_neu_ky_va_thang_moi_nhat_chua_tron_thi_dung_thang_tron_gan_nhat(kho):
    out = rt.new_customer_list(mode="quality", scope_area_code="MB")
    assert out["month"] == "2026-08"
    assert "2026-09 chua tron" in out["ky_mac_dinh"] and "2026-08" in out["ky_mac_dinh"]
    assert "IsNC" in out["nguon_khach_moi"]


def test_nguoi_hoi_neu_ky_thi_giu_nguyen_ky_do(kho):
    out = rt.new_customer_list(year_month="2026-08", mode="quality", scope_area_code="MB")
    assert out["month"] == "2026-08" and out["ky_mac_dinh"] is None
