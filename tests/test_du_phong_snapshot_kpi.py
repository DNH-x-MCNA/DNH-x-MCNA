# -*- coding: utf-8 -*-
"""30/09/2026 - loi tim thay khi test that tren may 24 (bat DNH_BAT_DU_PHONG + DNH_BAT_BIEU_DO):

1) "Du phong KPI cuoi thang theo QLV" -> "Khong co snapshot KPI dung thang/ngay yeu cau". Kho chi giu 1 snapshot
   KPI/thang; thang dang chay mang ngay dong bo gan nhat (thuong la HOM NAY), con code hoi snapshot <= hom qua nen
   luon roi ve snapshot cuoi thang truoc. V09 / M43 / KPI theo QLV vi the chua bao gio chay duoc. Test cu khong bat
   duoc vi du lieu gia tra dung ngay duoc hoi.
2) C50 (4 bang): phuong phap/gia dinh va ghi chu ETC lap lai sau moi bang; dong "Nguon" lap 4 lan.
3) Bang "Xem so lieu bieu do" hien so le ("21.761.085.237,931 d").
Du lieu gia, khong goi model, khong cham Bravo."""
import datetime as dt
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / "backend"))
import conversation_memory as memory  # noqa: E402
import nl2sql  # noqa: E402
import period_projection as pp  # noqa: E402
import report_templates as rt  # noqa: E402


class Ngay(dt.date):
    @classmethod
    def today(cls):
        return cls(2026, 9, 16)


@pytest.fixture
def kho(monkeypatch, tmp_path):
    monkeypatch.setenv("DNH_BAT_DU_PHONG", "1")
    monkeypatch.setattr(pp.dt, "date", Ngay)
    monkeypatch.setattr(rt, "latest_data_date", lambda: "2026-09-15")
    monkeypatch.setattr(rt, "_detail_cutoff", lambda: "2025-09-01")
    monkeypatch.setattr(rt, "_write_log", lambda *a, **k: None)
    monkeypatch.setattr(rt, "_q_bravo", lambda *a, **k: pytest.fail("du phong khong duoc doc Bravo"))
    monkeypatch.setattr(nl2sql, "sync_freshness_note", lambda: "")
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    goi = []

    def doanh_thu(first, last, **scope):
        goi.append((first, last[:10]))
        ngay = (dt.date.fromisoformat(last[:10]) - dt.date.fromisoformat(first)).days + 1
        return {"total": {"revenue": ngay * 10.0}, "data_coverage": {"complete": True}}

    monkeypatch.setattr(rt, "revenue_by_channel", doanh_thu)
    monkeypatch.setattr(rt, "_ytd_plan", lambda *a, **k: {"total": 600.0, "note": None})
    return goi


def _kpi_theo_snapshot(monkeypatch, cac_snapshot):
    """Gia lap dung _fact_date_le: snapshot moi nhat KHONG VUOT QUA ngay duoc hoi."""
    hoi = []

    def kpi(day, group, limit, **scope):
        hoi.append(day)
        hop_le = [s for s in cac_snapshot if s <= day[:10]]
        if not hop_le:
            return {"error": "Khong co snapshot KPI phu hop."}
        return {"as_of": max(hop_le), "rows": [{"group_code": "QLV1", "group_name": "Đội 1", "actual": 100.0,
                                                "target": 300.0, "linear_run_rate": 190.0}]}

    monkeypatch.setattr(rt, "kpi_gap_run_rate", kpi)
    return hoi


def test_snapshot_kpi_mang_ngay_hom_nay_van_du_phong_duoc(kho, monkeypatch):
    hoi = _kpi_theo_snapshot(monkeypatch, ["2026-08-31", "2026-09-16"])   # thang dang chay = ngay dong bo hom nay
    kq = pp.current_period_projection(group_by="qlv")
    assert "error" not in kq, kq.get("error")
    assert hoi == ["2026-09-16"]                        # hoi theo hom nay, khong phai hom qua
    assert kq["as_of"] == "2026-09-15"                   # cung moc voi du lieu doanh thu (het hom qua)
    row = kq["rows"][0]
    assert row["linear"] == 190.0 and row["scenarios"] is not None   # van dung run-rate S35 cua tool KPI
    assert pp.render_projection(kq).count("snapshot ngày 16/09/2026") == 1


def test_snapshot_kpi_cu_hon_du_lieu_doanh_thu_thi_tinh_theo_snapshot(kho, monkeypatch):
    _kpi_theo_snapshot(monkeypatch, ["2026-08-31", "2026-09-10"])
    kq = pp.current_period_projection(group_by="qlv")
    assert kq["as_of"] == "2026-09-10"
    assert ("2026-08-01", "2026-08-10") in kho           # nhip lich su so cung ngay 10 cua thang truoc


def test_chua_co_snapshot_thang_hien_tai_bao_ro(kho, monkeypatch):
    _kpi_theo_snapshot(monkeypatch, ["2026-08-31"])
    assert pp.current_period_projection(group_by="qlv")["error"] == "Chưa có snapshot KPI của tháng hiện tại trong kho."


def test_c50_nhieu_bang_phuong_phap_va_ghi_chu_chi_in_mot_lan(kho):
    kq = nl2sql.ask("Dự báo doanh thu cuối tháng/quý theo kênh/miền là bao nhiêu; khoảng tin cậy và giả định chính là gì?",
                    session_id="c50", scope_role="c_level")
    tra_loi = kq["answer"]
    assert tra_loi.count("| Phạm vi |") == 4                          # du 4 bang
    for doan in ("Tháng: lũy kế", "Xấu/cơ sở/tốt dùng", "Giả định nhịp bán", "Kế hoạch ETC chỉ có toàn quốc"):
        assert tra_loi.count(doan) == 1, doan
    assert tra_loi.rstrip().endswith("chương trình mới.")            # phuong phap o cuoi cau tra loi
    assert tra_loi.count("Lịch sử hợp lệ") == 4                       # van gan voi tung bang
    assert len(kq["freshness"]) == 1                                   # dong "Nguon" khong lap
    assert memory.get_session_history("c50")[-1]["content"] == tra_loi


def test_mot_bang_van_co_du_phuong_phap(kho):
    tra_loi = nl2sql.ask("Dự báo doanh thu cuối tháng này là bao nhiêu?", session_id="mot-bang",
                         scope_role="c_level")["answer"]
    assert tra_loi.count("| Phạm vi |") == 1
    for doan in ("Tháng: lũy kế", "Xấu/cơ sở/tốt dùng", "Giả định nhịp bán"):
        assert tra_loi.count(doan) == 1, doan


def test_bang_so_lieu_bieu_do_lam_tron_toi_dong():
    nguon = (ROOT / "src" / "app" / "ReportChart.tsx").read_text(encoding="utf-8")
    dong = next(l for l in nguon.splitlines() if l.startswith("const full ="))
    assert 'toLocaleString("vi-VN", { maximumFractionDigits: 0 })' in dong
