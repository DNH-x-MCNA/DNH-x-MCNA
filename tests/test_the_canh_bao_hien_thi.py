# -*- coding: utf-8 -*-
"""02/10/2026 - hai loi hien thi thay tren the canh bao that ngay 01/10/2026:
- ghi chu "Lan thu N trong thang" dem theo TEN canh bao, khong theo vung: the DAU TIEN cua Mien Bac bi ghi "lan thu
  2 ... da lap lai" chi vi Mien Nam vua co mot the cung ten;
- phan tram in dau cham ("40.7%") trong khi so tien cung the dung dau phay ("1,25 ty").
Du lieu gia, khong gui gi ra ngoai."""
import pytest

from src import notifier


@pytest.fixture
def kho(tmp_path, monkeypatch):
    monkeypatch.setattr(notifier, "STATE_DB_PATH", str(tmp_path / "alerts_state.db"))
    monkeypatch.setattr(notifier, "_resolve_teams_webhooks", lambda region, channel: ["https://flow.example.test"])
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [])
    return notifier._pending_critical_teams_alerts


@pytest.mark.parametrize("vao, ra", [
    ("giảm 40.7% (vượt ngưỡng 30%)", "giảm 40,7% (vượt ngưỡng 30%)"),
    ("-1,25 tỷ đ (40.7%)", "-1,25 tỷ đ (40,7%)"),
    ("đạt 0.05 %", "đạt 0,05 %"),
    ("1.250,5% và 1.234.567 đ", "1.250,5% và 1.234.567 đ"),       # đã đúng kiểu Việt: giữ nguyên
    ("ngày 10.07.2026, bản v2.5", "ngày 10.07.2026, bản v2.5"),   # không đứng trước dấu %: không đụng
])
def test_phan_tram_dung_dau_phay(vao, ra):
    assert notifier._phan_tram_kieu_viet(vao) == ra


def test_phan_tram_doi_ca_trong_bang_va_giu_kieu_du_lieu():
    bang = [["Kỳ", "12.5%"], ("x", 3, None), {"a": "7.25%"}]
    assert notifier._phan_tram_kieu_viet(bang) == [["Kỳ", "12,5%"], ("x", 3, None), {"a": "7,25%"}]
    assert notifier._phan_tram_kieu_viet(None) is None


def test_dem_lan_lap_theo_tung_vung_va_kenh(kho):
    ten = "CẢNH BÁO DOANH THU SỤT GIẢM MẠNH (OTC)"
    notifier._log_alert_severity(ten, "CRITICAL", region="Miền Nam", channel="OTC")
    notifier._log_alert_severity(ten, "CRITICAL", region="Miền Bắc", channel="OTC")
    assert notifier._count_alert_occurrences_this_month(ten, region="Miền Bắc", channel="OTC") == 1
    assert notifier._count_alert_occurrences_this_month(ten, region="Miền Nam", channel="OTC") == 1
    notifier._log_alert_severity(ten, "CRITICAL", region="Miền Bắc", channel="OTC")
    assert notifier._count_alert_occurrences_this_month(ten, region="Miền Bắc", channel="OTC") == 2
    # Cảnh báo toàn quốc (không vùng) đếm riêng; WARNING không tính.
    notifier._log_alert_severity(ten, "CRITICAL")
    notifier._log_alert_severity(ten, "WARNING", region="Miền Bắc", channel="OTC")
    assert notifier._count_alert_occurrences_this_month(ten) == 1
    assert notifier._count_alert_occurrences_this_month(ten, region="Miền Bắc", channel="OTC") == 2


def test_the_dau_tien_cua_mot_vung_khong_bi_ghi_la_lap_lai(kho):
    def gui(vung):
        notifier.send_alert_to_all_channels(
            alert_name="CẢNH BÁO DOANH THU SỤT GIẢM MẠNH (OTC)", severity="CRITICAL",
            summary="Doanh thu kênh OTC giảm 40.7% so với kỳ trước (vượt ngưỡng cảnh báo 30%).",
            table_headers=["Kỳ", "Chênh lệch"], table_rows=[["01/10", "-1,25 tỷ đ (40.7%)"]],
            channels=("teams",), channel="OTC", region=vung)

    gui("Miền Nam")
    gui("Miền Bắc")
    gui("Miền Bắc")
    nam, bac_1, bac_2 = kho
    for the in (nam, bac_1):
        assert "Lần thứ" not in the["summary"], the["summary"]
    assert "Lần thứ 2 trong tháng" in bac_2["summary"] and "cùng phạm vi" in bac_2["summary"]
    for the in kho:
        assert "giảm 40,7% so với" in the["summary"] and "40.7" not in the["summary"]
        assert the["table_rows"] == [["01/10", "-1,25 tỷ đ (40,7%)"]]
