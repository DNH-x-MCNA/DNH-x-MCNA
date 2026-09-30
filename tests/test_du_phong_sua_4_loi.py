# -*- coding: utf-8 -*-
"""30/09/2026 - review commit 26da32e (du phong ky hien tai), sua 4 loi:

1) Dong theo mien khong co chi tieu: ke hoach ETC chi co toan quoc -> _ytd_plan theo mien total=None, trong khi
   thuc te la OTC+ETC. Loc mien ma khong chi kenh -> chi tinh OTC cho khop ke hoach OTC cua mien.
2) Kich ban doi/TDV (V09) khong bao gio co: kho chi giu snapshot KPI cuoi thang -> lay nhip hoa don OTC cung pham vi.
3) M43 "vung nao kha nang khong dat cao nhat": them xep hang % du phong/ke hoach thap nhat (khong phai xac suat).
4) Cau du phong tra loi tat dinh, khong goi model -> khong tru quota tuan.
Du lieu gia, khong goi model, khong cham Bravo."""
import datetime as dt
import importlib.util
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.append(str(BACKEND))
import auth  # noqa: E402
import conversation_memory as cm  # noqa: E402
import period_projection as pp  # noqa: E402
import report_templates as rt  # noqa: E402

DOANH_THU_NGAY = {"MB": 20.0, "MT": 5.0, "MN": 10.0}
KE_HOACH_OTC = {"MB": 600.0, "MT": 300.0, "MN": 300.0}


class NgayCoDinh(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 16)


@pytest.fixture
def kho(monkeypatch):
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    monkeypatch.setattr(pp.dt, "date", NgayCoDinh)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-15")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-09-01")
    goi = []

    def doanh_thu(first, last, **scope):
        goi.append(scope)
        ngay = (dt.date.fromisoformat(last[:10]) - dt.date.fromisoformat(first)).days + 1
        vung = scope.get("scope_area_code")
        moi_ngay = DOANH_THU_NGAY[vung] if vung else sum(DOANH_THU_NGAY.values())
        if str(scope.get("scope_channel") or "ALL").upper() == "ALL":
            moi_ngay += 3.0                                  # phan ETC (khong co ke hoach theo mien)
        return {"total": {"revenue": ngay * moi_ngay}, "data_coverage": {"complete": True}}

    def ke_hoach(year, m1, m2, scope_area_code=None, scope_channel=None, scope_employee_code=None):
        kenh = str(scope_channel or "ALL").upper()
        if scope_area_code:
            # Nhu _ytd_plan that: ETC khong tach mien -> total None khi hoi ca hai kenh.
            return {"total": KE_HOACH_OTC[scope_area_code] if kenh == "OTC" else None,
                    "note": None if kenh == "OTC" else "Ke hoach ETC chua tach theo vung trong nguon hien co."}
        return {"total": sum(KE_HOACH_OTC.values()) + (0 if kenh == "OTC" else 100.0), "note": None}

    monkeypatch.setattr(rt, "revenue_by_channel", doanh_thu)
    monkeypatch.setattr(rt, "_ytd_plan", ke_hoach)
    return goi


def test_dong_mien_tinh_otc_co_du_chi_tieu(kho):
    kq = pp.current_period_projection(group_by="area")
    dong = {r["key"]: r for r in kq["rows"]}
    assert [dong[m]["label"] for m in ("MB", "MT", "MN")] == ["MB · OTC", "MT · OTC", "MN · OTC"]
    assert dong["MB"]["target"] == 600.0 and dong["MB"]["actual"] == 15 * 20.0   # chi OTC, khong cong ETC
    assert dong["MT"]["gap"] is not None and dong["MT"]["linear_pct"] is not None
    assert all(s["scope_channel"] == "OTC" for s in kho if s.get("scope_area_code"))
    assert any("chỉ tính OTC" in n for n in kq["notes"])


def test_giam_doc_mien_hoi_tong_cung_co_chi_tieu(kho):
    row = pp.current_period_projection(scope_area_code="MB")["rows"][0]
    assert row["label"] == "Tổng phạm vi · OTC" and row["target"] == 600.0


def test_hoi_rieng_etc_theo_mien_van_bao_thieu_ke_hoach(kho):
    row = pp.current_period_projection(scope_area_code="MB", scope_channel="ETC")["rows"][0]
    assert row["target"] is None and row["label"] == "Tổng phạm vi"


def test_ca_cong_ty_khong_bi_ep_otc(kho):
    row = pp.current_period_projection()["rows"][0]
    assert row["label"] == "Tổng phạm vi" and row["target"] == 1300.0


def test_kich_ban_doi_lay_nhip_hoa_don_otc_cung_pham_vi(kho, monkeypatch):
    def kpi(day, group, limit, **scope):
        return {"as_of": day, "rows": [{"group_code": "QLV1", "group_name": "Đội", "actual": 100,
                                         "target": 250, "linear_run_rate": 200}]}
    monkeypatch.setattr(rt, "kpi_gap_run_rate", kpi)
    kq = pp.current_period_projection(scope_employee_code="QLV1", scope_area_code="MB")
    row = kq["rows"][0]
    assert row["scenarios"] is not None and row["history_count"] == 6
    lich_su = [s for s in kho if s.get("scope_employee_code") == "QLV1"]
    assert lich_su and all(s["scope_channel"] == "OTC" and s["scope_area_code"] == "MB" for s in lich_su)


def test_xep_hang_du_phong_thap_nhat_va_so_thang_du_dat(kho):
    kq = pp.current_period_projection(group_by="area")
    xh = kq["ranking_lowest_first"]
    # MT: 5/ngay x 30 = 150 / 300 = 50%; MN: 300/300 = 100%; MB: 600/600 = 100% -> MT dung dau.
    assert xh[0]["label"] == "MT · OTC" and round(xh[0]["linear_pct"], 6) == 50.0
    assert [x["linear_pct"] for x in xh] == sorted(x["linear_pct"] for x in xh)
    assert xh[0]["months_pace_reaching_target"] == 0
    van_ban = pp.render_projection(kq)
    assert "Dự phóng đạt thấp nhất so với kế hoạch trước" in van_ban
    assert "KHÔNG phải xác suất" in van_ban and "chỉ tính OTC" in van_ban


def test_mot_dong_thi_khong_co_xep_hang(kho):
    assert pp.current_period_projection()["ranking_lowest_first"] == []


def _nap_main(tmp_path, monkeypatch, ten):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(cm, "DB_PATH", str(tmp_path / "memory.db"))
    cm.init()
    spec = importlib.util.spec_from_file_location(ten, os.path.join(BACKEND, "main.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ten] = mod
    spec.loader.exec_module(mod)
    return mod


def test_cau_du_phong_khong_tru_quota(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "du_phong_quota")
    monkeypatch.setattr(chatbot_main, "check_and_consume_weekly_quota",
                        lambda *a, **k: pytest.fail("cau du phong tat dinh khong duoc tru quota"))
    nguoi = {"username": "ceo", "role": "c_level"}
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    kq = chatbot_main._quota_for_question(nguoi, "Dự báo doanh thu cuối tháng theo miền")
    assert "quota_used" in kq
    # Tat co: cau nay bi chan nhu cau du bao cu, van khong tru quota.
    monkeypatch.delenv("DNH_BAT_DU_PHONG")
    chatbot_main._quota_for_question(nguoi, "Dự báo doanh thu cuối tháng theo miền")


def test_cau_thuong_van_tru_quota(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "du_phong_quota_thuong")
    goi = []
    monkeypatch.setattr(chatbot_main, "check_and_consume_weekly_quota",
                        lambda u, lim: goi.append(u) or {"allowed": True, "used": 1, "limit": lim,
                                                        "resets_at": "2026-10-05T00:00:00"})
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    chatbot_main._quota_for_question({"username": "ceo", "role": "c_level"}, "Doanh thu tháng này bao nhiêu?")
    assert goi == ["ceo"]
