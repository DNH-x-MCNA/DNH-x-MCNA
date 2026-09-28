"""28/09/2026: mot nhom Teams co the nhieu nguoi nhan (vd 2-3 C-Level). Bang nguoi nhan ghi chuoi hoac danh sach
JSON; moi nguoi nhan mot tin 1-1 rieng qua Flow dung chung, mot nguoi loi khong chan nguoi con lai. Du lieu gia."""
import json

import pytest

import main
from src import notifier
from src.teams_routing import TeamsRoutingError, load_shared_routes

CLEVEL = {"audience": "C-Level (Toàn quốc)"}
GD_MB = {"audience": "GD MB", "role": "regional_director", "region": "bac"}
FLOW = "https://flow.example.invalid/chung"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(notifier.urllib.request, "urlopen", lambda *a, **k: pytest.fail("Khong goi mang that"))


def _shared(monkeypatch, tmp_path, mapping):
    path = tmp_path / "nguoi_nhan.local.json"
    path.write_text(json.dumps(mapping, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("TEAMS_DELIVERY_MODE", "shared")
    monkeypatch.setenv("TEAMS_SHARED_WEBHOOK_URL", FLOW)
    monkeypatch.setenv("TEAMS_RECIPIENTS_FILE", str(path))


def _metrics(**kw):
    return {"date": "2026-09-28", "freshness_note": "", "insights": None,
            "revenue": {"otc": 10, "etc": 20, "total": 30, "otc_invoice_count": 1,
                        "etc_invoice_count": 2, "invoice_count": 3},
            "inventory": {"dead_stock_available": False, "near_stockout_available": False}}


def test_chuoi_hoac_danh_sach_bo_trung_khong_phan_biet_hoa_thuong(monkeypatch, tmp_path):
    _shared(monkeypatch, tmp_path, {"C-Level (Toàn quốc)": ["sep1@dnh.test", "SEP1@dnh.test", " sep2@dnh.test "],
                                    "GD MB": "gd.mb@dnh.test"})
    routes = load_shared_routes({"report_recipients": [CLEVEL, GD_MB]})
    assert routes["C-Level (Toàn quốc)"] == (FLOW, ("sep1@dnh.test", "sep2@dnh.test"))
    assert routes["GD MB"] == (FLOW, ("gd.mb@dnh.test",))


@pytest.mark.parametrize("gia_tri", [[], ["khong-phai-email"], "a@dnh.test;b@dnh.test", "a@dnh.test, b@dnh.test",
                                     [f"n{i}@dnh.test" for i in range(11)], [123], {"a": "a@dnh.test"}])
def test_danh_sach_sai_thi_dung_han_khong_gui_ai(monkeypatch, tmp_path, gia_tri):
    """Chuoi "a;b" cung bi tu choi: nhieu nguoi phai ghi dang danh sach, loi go khong am tham thanh gui nham."""
    _shared(monkeypatch, tmp_path, {"C-Level (Toàn quốc)": gia_tri})
    with pytest.raises(TeamsRoutingError):
        load_shared_routes({"report_recipients": [CLEVEL]})


def test_daily_clevel_nhieu_nguoi_moi_nguoi_mot_tin_cung_noi_dung(monkeypatch, tmp_path):
    _shared(monkeypatch, tmp_path, {"C-Level (Toàn quốc)": ["sep1@dnh.test", "sep2@dnh.test", "sep3@dnh.test"]})
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [CLEVEL]})
    goi_so_lieu, sent = [], []
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: goi_so_lieu.append(kw) or _metrics())
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: sent.append(kw) or True)
    monkeypatch.setattr(main, "send_email", lambda *a, **kw: pytest.fail("C-Level Daily la Teams"))
    assert main.send_daily_digest()
    assert len(goi_so_lieu) == 1, "tinh so lieu mot lan cho ca nhom, khong lap theo tung nguoi"
    assert [s["recipient"] for s in sent] == ["sep1@dnh.test", "sep2@dnh.test", "sep3@dnh.test"]
    assert len({s["title"] for s in sent}) == 1 and {s["audience"] for s in sent} == {"C-Level (Toàn quốc)"}
    assert {s["webhook_url_override"] for s in sent} == {FLOW}


def test_daily_mot_nguoi_loi_van_gui_nguoi_con_lai_va_bao_that_bai(monkeypatch, tmp_path, capsys):
    _shared(monkeypatch, tmp_path, {"C-Level (Toàn quốc)": ["loi@dnh.test", "sep2@dnh.test"]})
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [CLEVEL]})
    monkeypatch.setattr(main, "get_daily_digest_metrics", _metrics)
    sent = []
    monkeypatch.setattr(main, "send_teams_alert",
                        lambda **kw: sent.append(kw["recipient"]) or kw["recipient"] != "loi@dnh.test")
    assert not main.send_daily_digest()
    assert sent == ["loi@dnh.test", "sep2@dnh.test"]
    assert "1/2" in capsys.readouterr().out


def test_canh_bao_nghiep_vu_moi_nguoi_mot_dich_mot_nguoi_chi_nhan_mot_lan(monkeypatch, tmp_path):
    _shared(monkeypatch, tmp_path, {"C-Level (Toàn quốc)": ["sep1@dnh.test", "sep2@dnh.test"],
                                    "GD MB": ["SEP1@dnh.test", "gd.mb@dnh.test"]})
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_recipients": [CLEVEL, GD_MB]})
    ket = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    assert [(a, r) for _, a, r in ket] == [("C-Level (Toàn quốc)", "sep1@dnh.test"),
                                           ("C-Level (Toàn quốc)", "sep2@dnh.test"),
                                           ("GD MB", "gd.mb@dnh.test")]
    assert {u for u, _, _ in ket} == {FLOW}
