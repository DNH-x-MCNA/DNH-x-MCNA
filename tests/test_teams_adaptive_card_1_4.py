# -*- coding: utf-8 -*-
"""26/08/2026: ha Adaptive Card tu 1.5 xuong 1.4, go thanh phan "Table" (schema 1.5).

BOI CANH. Commit 217dc07 (04/08/2026, tren nhanh `main`, KHONG nam trong lich su `master`) sua
dung loi that: Power Automate Teams connector "size limit and schema error" voi Table (them ngay
15/07 boi 910c375). master va main tach nhanh truoc/quanh thoi diem do nen master CHUA BAO GIO
nhan ban va - phat hien khi ra soat 15 commit chi co tren main de dua vao ke hoach RC (26/08).

Da kiem tren log production may 24: 30/30 lan gui gan day deu in "[TEAMS] ... thanh cong". NHUNG
urlopen() CHI raise khi Power Automate tra loi HTTP loi NGAY LUC NHAN webhook - no KHONG thay duoc
loi ben trong Flow xay ra SAU do (card bi Teams tu choi vi sai schema), vi webhook trigger chay
BAT DONG BO (tra 202 ngay, roi moi thuc thi Flow). Tuc 30 dong log "thanh cong" do CHUNG MINH
duoc "webhook da nhan", KHONG chung minh duoc "card da hien thi trong Teams" - dung loai bao dong
gia da gap nhieu lan trong du an nay.

KHAC voi 217dc07 (xoa han bang chi tiet): o day THAY the bang FactSet/TextBlock (native tu 1.0,
khong can 1.5) vi bang 2 cot cua Daily Digest (main.py::_digest_table - doanh thu, so hoa don, ton
kho) di qua CUNG duong table_headers/table_rows. Xoa nhu ban goc se lam Daily Digest mat het so
lieu cot loi, chi con dong tom tat rong.

Cac test duoi day khoa: (1) card la 1.4 o CA HAI noi dung; (2) payload KHONG con "type": "Table";
(3) FactSet/TextBlock thay the giu duoc noi dung (khong mat so lieu nhu cach lam cu); (4) recipient/
audience (them 26/08/2026, commit 15f7ec2) van hoat dong sau khi ha version; (5) response.status
duoc doc dung, khong vo khi mock/that te tra ve doi tuong khac nhau.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import src.notifier as notifier


def _bat_payload(monkeypatch, http_status=202):
    da_gui = {}

    def _gia(req, timeout=None):
        da_gui["payload"] = json.loads(req.data.decode("utf-8"))

        class _Resp:
            status = http_status
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()

    monkeypatch.setattr(notifier.urllib.request, "urlopen", _gia)
    return da_gui


def _the_trong_body(payload, kieu):
    """Tim tat ca item co "type" == kieu trong body cua card, ke ca long trong Container/items."""
    ket = []
    def _di(node):
        if isinstance(node, dict):
            if node.get("type") == kieu:
                ket.append(node)
            for v in node.values():
                _di(v)
        elif isinstance(node, list):
            for v in node:
                _di(v)
    _di(payload)
    return ket


# ---------------------------------------------------------------------------------------
# Version va Table
# ---------------------------------------------------------------------------------------

def test_card_don_la_1_4(monkeypatch):
    da_gui = _bat_payload(monkeypatch)
    notifier.send_teams_alert("Sut giam doanh thu", "Tom tat", webhook_url_override="https://flow",
                              table_headers=["Chi so", "Gia tri"], table_rows=[["Doanh thu", "1 ty"]])
    card = da_gui["payload"]["attachments"][0]["content"]
    assert card["version"] == "1.4"


def test_card_gop_la_1_4(monkeypatch):
    da_gui = {}
    def _gia(req, timeout=None):
        da_gui["payload"] = json.loads(req.data.decode("utf-8"))
        class _Resp:
            status = 202
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return _Resp()
    monkeypatch.setattr(notifier, "_post_teams_webhook",
                        lambda url, payload: _gia(type("R", (), {"data": json.dumps(payload).encode()})(), None) or True)
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [
        {"alert_name": "Vuot han muc", "summary": "x", "period": None, "channel": None,
         "region": None, "issue": None, "table_headers": ["Ma", "So tien"],
         "table_rows": [["KH01", "500tr"]],
         "webhooks": [("https://flow", "C-Level", None)]},
    ])
    notifier.flush_critical_teams_queue()
    card = da_gui["payload"]["attachments"][0]["content"]
    assert card["version"] == "1.4"


def test_payload_khong_con_type_table_card_don(monkeypatch):
    """Diem chinh cua ban va: khong con thanh phan Table nao trong payload gui di."""
    da_gui = _bat_payload(monkeypatch)
    notifier.send_teams_alert(
        "Khach no qua han", "Tom tat", webhook_url_override="https://flow",
        table_headers=["Khach hang", "Ma", "Vung", "So tien"],
        table_rows=[["Cong ty A", "KH01", "MB", "500 trieu"],
                    ["Cong ty B", "KH02", "MN", "300 trieu"]])
    assert _the_trong_body(da_gui["payload"], "Table") == []


def test_payload_khong_con_type_table_card_gop(monkeypatch):
    da_gui = {}
    def _gia_url(url, payload):
        da_gui["payload"] = payload
        return True
    monkeypatch.setattr(notifier, "_post_teams_webhook", _gia_url)
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [
        {"alert_name": "Ton kho chet", "summary": "x", "period": None, "channel": None,
         "region": None, "issue": None,
         "table_headers": ["San pham", "Ma", "Ton kho"],
         "table_rows": [["Thuoc A", "SP01", "1000"], ["Thuoc B", "SP02", "800"]],
         "webhooks": [("https://flow", "C-Level", None)]},
    ])
    notifier.flush_critical_teams_queue()
    assert _the_trong_body(da_gui["payload"], "Table") == []


# ---------------------------------------------------------------------------------------
# Thay the giu duoc noi dung (khac 217dc07 - khong xoa trang)
# ---------------------------------------------------------------------------------------

def test_bang_2_cot_thanh_factset_giu_du_so_lieu(monkeypatch):
    """Day chinh la hinh dang cua main.py::_digest_table() - bang "Chi so | Gia tri" cua Daily
    Digest. Phai giu du so lieu qua FactSet, KHONG duoc mat noi dung nhu cach xoa trang cua
    217dc07."""
    da_gui = _bat_payload(monkeypatch)
    notifier.send_teams_alert(
        "Bao cao tong hop hang ngay", "Tom tat", webhook_url_override="https://flow",
        table_headers=["Chi so", "Gia tri"],
        table_rows=[["Doanh thu OTC", "2,5 ty"], ["Doanh thu ETC", "1,2 ty"],
                    ["Tong so hoa don", "48"]])
    factsets = _the_trong_body(da_gui["payload"], "FactSet")
    assert len(factsets) >= 1
    facts = factsets[-1]["facts"]  # FactSet cuoi la cua bang chi tiet (FactSet dau la Ky/Kenh/Khu vuc)
    gia_tri = {f["title"]: f["value"] for f in facts}
    assert gia_tri == {"Doanh thu OTC": "2,5 ty", "Doanh thu ETC": "1,2 ty", "Tong so hoa don": "48"}


def test_bang_nhieu_cot_thanh_textblock_giu_du_so_lieu(monkeypatch):
    """Bang >2 cot (vd danh sach khach no qua han co ten/ma/vung/tien) khong map duoc vao FactSet
    (title/value don) - phai xuong dong TextBlock, moi dong 1 ban ghi, khong duoc bo sot."""
    da_gui = _bat_payload(monkeypatch)
    notifier.send_teams_alert(
        "Top khach no qua han", "Tom tat", webhook_url_override="https://flow",
        table_headers=["Khach hang", "Vung", "So tien"],
        table_rows=[["Cong ty A", "MB", "500tr"], ["Cong ty B", "MN", "300tr"]])
    chu = " ".join(t["text"] for t in _the_trong_body(da_gui["payload"], "TextBlock"))
    assert "Khach hang: Cong ty A" in chu and "So tien: 500tr" in chu
    assert "Khach hang: Cong ty B" in chu and "So tien: 300tr" in chu
    assert "Vung: MB" in chu and "Vung: MN" in chu


def test_card_don_factset_textblock_rat_dai_van_duoi_28kb(monkeypatch):
    """Cơ chế cũ chỉ cắt Table.rows nên card 1.4 dùng TextBlock/FactSet vẫn có thể vượt 28 KB.
    Test qua đúng đường gửi thật, kể cả recipient/audience được gắn sau khi dựng card."""
    da_gui = _bat_payload(monkeypatch)
    dai = "Nội dung cảnh báo rất dài " * 500
    rows = [[dai, dai, dai, dai] for _ in range(40)]
    ok = notifier.send_teams_alert(
        "Cảnh báo " + dai, dai, severity="CRITICAL", webhook_url_override="https://flow",
        table_headers=["Khách hàng", "Mã", "Vùng", "Số tiền"], table_rows=rows,
        sections=[{"id": "chi_tiet", "title": "Chi tiết", "items": [dai] * 30}],
        recipient="gd.mienbac@dnh.vn", audience="Miền Bắc")
    assert ok is True
    payload = da_gui["payload"]
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 28000
    assert _the_trong_body(payload, "TextBlock")
    assert "payloadTruncatedNotice" in json.dumps(payload, ensure_ascii=False)


def test_card_gop_nhieu_canh_bao_van_duoi_28kb(monkeypatch):
    """Khóa đường card gộp riêng; đây là đường có thể phình nhanh nhất khi nhiều CRITICAL dồn lại."""
    da_gui = {}
    monkeypatch.setattr(notifier, "_post_teams_webhook",
                        lambda url, payload: da_gui.setdefault("payload", payload) is payload)
    dai = "Diễn giải cảnh báo dài " * 300
    rows = [[dai, dai, dai, dai] for _ in range(20)]
    monkeypatch.setattr(notifier, "_pending_critical_teams_alerts", [
        {"alert_name": f"Cảnh báo {i} {dai}", "summary": dai, "period": "08/2026",
         "channel": "OTC", "region": "MB", "issue": dai,
         "table_headers": ["Khách hàng", "Mã", "Vùng", "Số tiền"], "table_rows": rows,
         "webhooks": [("https://flow", "Miền Bắc", "gd.mienbac@dnh.vn")]}
        for i in range(35)
    ])
    notifier.flush_critical_teams_queue()
    payload = da_gui["payload"]
    assert payload["recipient"] == "gd.mienbac@dnh.vn"
    assert len(json.dumps(payload, ensure_ascii=False).encode("utf-8")) <= 28000
    assert "payloadTruncatedNotice" in json.dumps(payload, ensure_ascii=False)


def test_qua_max_rows_thi_bao_ro_con_bao_nhieu_dong_bi_cat(monkeypatch):
    """Thay vi im lang cat bot (nhu Table cu voi max_rows), phai NOI RO con bao nhieu dong khong
    hien - dung nguyen tac "tha noi khong biet con hon giau" xuyen suot du an."""
    da_gui = _bat_payload(monkeypatch)
    rows = [["KH%02d" % i, "%d trieu" % (i * 10)] for i in range(15)]
    notifier.send_teams_alert("Danh sach dai", "Tom tat", webhook_url_override="https://flow",
                              table_headers=["Ma", "So tien"], table_rows=rows)
    chu = " ".join(t["text"] for t in _the_trong_body(da_gui["payload"], "TextBlock"))
    assert "5 dòng khác" in chu  # 15 dong - _TEAMS_DETAIL_MAX_ROWS(10) = con 5 chua hien


# ---------------------------------------------------------------------------------------
# recipient/audience van hoat dong sau khi ha version (khong pha commit 15f7ec2 cung ngay)
# ---------------------------------------------------------------------------------------

def test_recipient_van_hoat_dong_sau_khi_ha_version(monkeypatch):
    da_gui = _bat_payload(monkeypatch)
    ok = notifier.send_teams_alert("Tieu de", "Tom tat", webhook_url_override="https://flow",
                                    recipient="gd.mienbac@dnh.vn", audience="Mien Bac")
    assert ok
    assert da_gui["payload"]["recipient"] == "gd.mienbac@dnh.vn"
    assert da_gui["payload"]["attachments"][0]["content"]["version"] == "1.4"


# ---------------------------------------------------------------------------------------
# Doc response.status an toan
# ---------------------------------------------------------------------------------------

def test_http_202_van_bao_thanh_cong(monkeypatch):
    """Power Automate webhook tra 202 (da nhan, xu ly Flow bat dong bo sau) - phai van coi la
    gui thanh cong o tang nay, KHONG duoc coi 202 la loi."""
    _bat_payload(monkeypatch, http_status=202)
    ok = notifier.send_teams_alert("Tieu de", "Tom tat", webhook_url_override="https://flow")
    assert ok is True


def test_http_200_van_bao_thanh_cong(monkeypatch):
    _bat_payload(monkeypatch, http_status=200)
    ok = notifier.send_teams_alert("Tieu de", "Tom tat", webhook_url_override="https://flow")
    assert ok is True
