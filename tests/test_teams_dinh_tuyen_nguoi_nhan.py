# -*- coding: utf-8 -*-
"""26/08/2026: mo duong cho MOT Flow Power Automate dinh tuyen nhieu nguoi nhan.

BOI CANH. Cach lam hien tai la MOT Flow cho MOI audience - 6 audience, 6 Flow, moi Flow mot webhook
rieng dien trong config.yaml. Muon gui toi tung QLV (28 nguoi) thi phai dung 28 Flow bang tay, va
moi lan nhan su thay doi lai phai vao Power Automate sua. Khong mo rong noi.

Huong di thay the: MOT Flow duy nhat, doc truong `recipient` trong payload roi tu dinh tuyen. Doi
nguoi chi can sua config.yaml, khong dung toi Power Automate.

NUT THAT PHAI GO. Ca hai duong gui Teams deu khu trung/gom nhom theo URL:
  - _resolve_teams_webhooks()  -> `seen_urls`
  - flush_critical_teams_queue() -> `by_webhook[webhook_url]`
Neu nhieu audience cung tro vao MOT Flow dinh tuyen thi hai cho do gop tat ca thanh MOT luot gui -
mot nguoi nhan duoc tin, nhung nguoi con lai bien mat AM THAM, khong loi, khong canh bao. Dung loai
hong nguy hiem nhat trong du an nay: he thong bao thanh cong trong khi viec khong xay ra.

Nay khu trung/gom theo CAP (url, nguoi_nhan).

Cac test duoi PHAI TRUOT tren code cu va DAT tren code moi. Rieng nhom "tuong thich nguoc" phai DAT
tren ca hai - do la phan bao dam 6 Flow dang chay khong bi anh huong.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.notifier as notifier


def _dat_audience(monkeypatch, danh_sach, webhook_mac_dinh="https://mac-dinh"):
    monkeypatch.setattr(notifier, "load_config", lambda: {"report_recipients": danh_sach})
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", webhook_mac_dinh)


# ---------------------------------------------------------------------------------------
# Tuong thich nguoc - phai giu nguyen hanh vi cua 6 Flow dang chay
# ---------------------------------------------------------------------------------------

def test_khong_dien_nguoi_nhan_thi_khu_trung_y_het_truoc_day(monkeypatch):
    """Ba audience cung tro chung mot webhook, khong ai dien teams_recipient -> van chi gui MOT lan,
    dung nhu truoc khi co thay doi nay. Day la truong hop cua he thong luc chua co Flow rieng."""
    _dat_audience(monkeypatch, [
        {"audience": "C-Level", "region": None, "channel": None, "teams_webhook": "https://chung"},
        {"audience": "Mien Bac", "region": "bac", "channel": None, "teams_webhook": "https://chung"},
        {"audience": "Kenh OTC", "region": None, "channel": "OTC", "teams_webhook": "https://chung"},
    ])
    ket = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    assert len(ket) == 1, "cung URL, khong ai co nguoi nhan rieng -> phai gop lam mot"
    assert ket[0][0] == "https://chung"


def test_moi_audience_mot_webhook_rieng_van_gui_du(monkeypatch):
    """Cach lam HIEN TAI tren production: 6 Flow, 6 webhook khac nhau. Khong duoc thay doi."""
    _dat_audience(monkeypatch, [
        {"audience": "C-Level", "region": None, "channel": None, "teams_webhook": "https://flow-clevel"},
        {"audience": "Mien Bac", "region": "bac", "channel": None, "teams_webhook": "https://flow-mb"},
        {"audience": "Mien Nam", "region": "nam", "channel": None, "teams_webhook": "https://flow-mn"},
    ])
    ket = notifier._resolve_teams_webhooks("Miền Bắc", None)
    urls = {r[0] for r in ket}
    assert urls == {"https://flow-clevel", "https://flow-mb"}, \
        "alert Mien Bac phai toi C-Level va Mien Bac, KHONG toi Mien Nam"


def test_khong_co_report_recipients_van_tra_ve_webhook_mac_dinh(monkeypatch):
    """Moi truong cu chua khai bao report_recipients - khong duoc vo."""
    monkeypatch.setattr(notifier, "load_config", lambda: {})
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", "https://mac-dinh")
    ket = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    assert len(ket) == 1 and ket[0][0] == "https://mac-dinh"
    assert len(ket[0]) == 3, "phai tra ve bo ba (url, audience, recipient) de cho goi khong phai doan"


# ---------------------------------------------------------------------------------------
# Nut that: nhieu nguoi nhan CHUNG mot Flow dinh tuyen
# ---------------------------------------------------------------------------------------

def test_cung_mot_flow_nhung_khac_nguoi_nhan_thi_KHONG_duoc_gop(monkeypatch):
    """Day la nut that. Ba audience tro chung MOT Flow dinh tuyen nhung khac nguoi nhan - phai ra
    DU BA luot gui. Code cu khu trung theo URL nen chi ra MOT: hai nguoi mat tin am tham."""
    _dat_audience(monkeypatch, [
        {"audience": "C-Level", "region": None, "channel": None,
         "teams_webhook": "https://flow-dinh-tuyen", "teams_recipient": "sep@dnh.vn"},
        {"audience": "Mien Bac", "region": "bac", "channel": None,
         "teams_webhook": "https://flow-dinh-tuyen", "teams_recipient": "gd.mienbac@dnh.vn"},
        {"audience": "Kenh OTC", "region": None, "channel": "OTC",
         "teams_webhook": "https://flow-dinh-tuyen", "teams_recipient": "gd.otc@dnh.vn"},
    ])
    ket = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")
    assert len(ket) == 3, "ba nguoi nhan khac nhau tren cung mot Flow -> phai ra ba luot"
    assert {r[2] for r in ket} == {"sep@dnh.vn", "gd.mienbac@dnh.vn", "gd.otc@dnh.vn"}


def test_trung_ca_flow_lan_nguoi_nhan_thi_van_gop(monkeypatch):
    """Khu trung van phai lam viec: cung Flow VA cung nguoi nhan thi khong gui hai lan."""
    _dat_audience(monkeypatch, [
        {"audience": "C-Level", "region": None, "channel": None,
         "teams_webhook": "https://flow", "teams_recipient": "sep@dnh.vn"},
        {"audience": "Kenh OTC", "region": None, "channel": "OTC",
         "teams_webhook": "https://flow", "teams_recipient": "sep@dnh.vn"},
    ])
    ket = notifier._resolve_teams_webhooks(None, "OTC")
    assert len(ket) == 1, "cung Flow, cung nguoi nhan -> mot luot"


def test_alert_theo_mien_khong_gui_cho_qlv_vi_chua_co_scope_doi(monkeypatch):
    """Thêm QLV vào report_recipients không được biến alert toàn miền thành tin riêng của đội."""
    _dat_audience(monkeypatch, [
        {"audience": "C-Level", "region": None, "channel": None,
         "teams_webhook": "https://flow-clevel"},
        {"audience": "QLV A", "role": "qlv", "region": "bac", "channel": "OTC",
         "employee_code": "QLV01", "teams_webhook": "https://flow-dinh-tuyen",
         "teams_recipient": "qlv.a@dnh.vn"},
    ])

    ket = notifier._resolve_teams_webhooks("Miền Bắc", "OTC")

    assert ket == [("https://flow-clevel", "C-Level", None)]


def test_alert_cung_khong_gui_khi_qlv_quen_truong_role(monkeypatch):
    """employee_code là dấu hiệu dữ liệu theo đội; thiếu role phải fail-closed, không được lọt alert."""
    _dat_audience(monkeypatch, [{
        "audience": "QLV quên role", "region": "bac", "channel": "OTC",
        "employee_code": "QLV01", "teams_webhook": "https://flow-dinh-tuyen",
        "teams_recipient": "qlv.a@dnh.vn",
    }])

    assert notifier._resolve_teams_webhooks("Miền Bắc", "OTC") == []


# ---------------------------------------------------------------------------------------
# Payload
# ---------------------------------------------------------------------------------------

def _bat_payload(monkeypatch):
    da_gui = {}

    def _gia(req, timeout=None):
        import json
        da_gui["payload"] = json.loads(req.data.decode("utf-8"))

        class _Resp:
            status = 202  # Power Automate tra ve 202 khi nhan webhook, xu ly Flow bat dong bo sau
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()

    monkeypatch.setattr(notifier.urllib.request, "urlopen", _gia)
    return da_gui


def test_payload_kem_nguoi_nhan_khi_duoc_truyen(monkeypatch):
    """Flow doc bang triggerBody()?['recipient'] - truong phai nam o TANG NGOAI CUNG cua payload."""
    da_gui = _bat_payload(monkeypatch)
    ok = notifier.send_teams_alert("Tieu de", "Tom tat", webhook_url_override="https://flow",
                                    recipient="gd.mienbac@dnh.vn", audience="Mien Bac")
    assert ok
    assert da_gui["payload"]["recipient"] == "gd.mienbac@dnh.vn"
    assert da_gui["payload"]["audience"] == "Mien Bac"
    assert "attachments" in da_gui["payload"], "khong duoc lam hong the card"


def test_payload_KHONG_co_truong_la_khi_khong_truyen(monkeypatch):
    """6 Flow hien tai chi doc `attachments`. Them truong thua vo co la thay doi hop dong khong can
    thiet - bo trong thi payload phai y het truoc day."""
    da_gui = _bat_payload(monkeypatch)
    notifier.send_teams_alert("Tieu de", "Tom tat", webhook_url_override="https://flow")
    assert "recipient" not in da_gui["payload"]
    assert "audience" not in da_gui["payload"]


# ---------------------------------------------------------------------------------------
# Hang doi gop card CRITICAL - duong gui thu hai, cung nut that
# ---------------------------------------------------------------------------------------

def test_hang_doi_gop_card_cung_tach_theo_nguoi_nhan(monkeypatch):
    """flush_critical_teams_queue() gom theo by_webhook[url]. Cung loi: nhieu nguoi nhan chung mot
    Flow bi dồn thanh mot card, gui mot lan. Phai gom theo cap (url, nguoi nhan)."""
    da_gui = []
    monkeypatch.setattr(notifier, "_post_teams_webhook",
                        lambda url, payload: da_gui.append((url, payload.get("recipient"))) or True)
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [
        {"alert_name": "Canh bao A", "summary": "x", "period": None, "channel": None,
         "region": None, "issue": None, "table_headers": None, "table_rows": None,
         "webhooks": [("https://flow", "C-Level", "sep@dnh.vn"),
                      ("https://flow", "Mien Bac", "gd.mienbac@dnh.vn")]},
    ])
    notifier.flush_critical_teams_queue()
    assert len(da_gui) == 2, "hai nguoi nhan chung mot Flow -> phai gui hai card rieng"
    assert {r[1] for r in da_gui} == {"sep@dnh.vn", "gd.mienbac@dnh.vn"}
