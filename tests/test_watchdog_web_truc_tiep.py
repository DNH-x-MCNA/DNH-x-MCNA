# -*- coding: utf-8 -*-
"""02/10/2026 - web chatbot chay thang tren may 24 (Caddy 443 -> Next.js 3000). Khi web con o Vercel, watchdog khong
canh phan web; chuyen ve may 24 ma khong canh thi web/Caddy chet hoac chung chi het han chi lo ra khi nguoi dung bao.

Khoa cac dieu kien:
- CHI canh khi CHATBOT_WEB_URL da tro ve ten mien rieng VA may nay co ban web (truoc luc chuyen: khong bao dong gia);
- moi su co bao MOT lan, het thi bao MOT lan; gui Teams loi thi lan sau bao lai;
- thu lai vai lan truoc khi coi la su co (deploy web khoi dong lai mat vai giay);
- han chung chi doc thang tu DER, khong xac thuc chuoi (kho CA cua Windows co the thieu goc Let's Encrypt);
- loi o phan canh web khong lam hong cac kiem tra cu.
Khong mo ket noi that: moi lan goi web/Caddy deu duoc thay bang ham gia."""
import base64
import datetime as dt
import sys
from pathlib import Path

import pytest

GOC = Path(__file__).resolve().parents[1]
# Them backend/ vao CUOI sys.path, khong chen len dau: chen len dau thi file test nap sau do ma `import main` se nhan
# backend/main.py thay cho main.py o goc repo (02/10/2026: 2 test cua test_tien_do_thang_chuyen_thang.py hong tren
# may 24 chi vi duoc chay sau file nay).
for _p in (str(GOC), str(GOC / "backend")):
    if _p not in sys.path:
        sys.path.append(_p)

import health_watchdog as wd  # noqa: E402

# Chung chi tu ky dung mot lan (CN = chatbot.example.test), tao bang openssl; khoa rieng da xoa, khong nam trong repo.
# notBefore = 02/10/2026 07:22:45 UTC, notAfter = 31/12/2026 07:22:45 UTC (90 ngay).
CHUNG_CHI_DER = base64.b64decode(
    "MIIBtDCCAVqgAwIBAgIUUAlq89hEbR4u0SazGNCvCnBNGegwCgYIKoZIzj0EAwIwHzEdMBsGA1UEAwwUY2hhdGJvdC5leGFtcGxl"
    "LnRlc3QwHhcNMjYxMDAyMDcyMjQ1WhcNMjYxMjMxMDcyMjQ1WjAfMR0wGwYDVQQDDBRjaGF0Ym90LmV4YW1wbGUudGVzdDBZMBMG"
    "ByqGSM49AgEGCCqGSM49AwEHA0IABBqBzlBmr3HzuxPQKL7kGEH7zD94GDVwwN/ISk6pdbV8K94ds+6vSDGVUSMnetklJ1xch2mQ"
    "Jskvvz9Gt7bw7iajdDByMB0GA1UdDgQWBBS2fxNKDvVUZixkJOitn/3a5dK9ijAfBgNVHSMEGDAWgBS2fxNKDvVUZixkJOitn/3a"
    "5dK9ijAPBgNVHRMBAf8EBTADAQH/MB8GA1UdEQQYMBaCFGNoYXRib3QuZXhhbXBsZS50ZXN0MAoGCCqGSM49BAMCA0gAMEUCIBov"
    "6MVzgv2cliUsiisimJ4L1HKJqH/DPe5wJrsJNJxtAiEAtJQeeGzfYloZRGC5AjLal2HNUxmyRZhM7KAy8+Es9HE=")
TU = dt.datetime(2026, 10, 2, 7, 22, 45)
DEN = dt.datetime(2026, 12, 31, 7, 22, 45)
TEN = "chatbot.example.test"


@pytest.fixture
def may(tmp_path, monkeypatch):
    """Mot "may 24" gia: .env o thu muc tam, ban web co san, moi lan goi mang deu la ham gia, khong ngu."""
    (tmp_path / "backend").mkdir()
    (tmp_path / "web" / "current").mkdir(parents=True)
    monkeypatch.setattr(wd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(wd, "BACKEND_DIR", str(tmp_path / "backend"))
    monkeypatch.setattr(wd, "WEB_DIR", str(tmp_path / "web" / "current"))
    for bien in ("CHATBOT_WEB_URL", "WATCHDOG_WEB_DIR"):
        monkeypatch.delenv(bien, raising=False)

    class May:
        web_loi = None            # None = web tra 200; khac = loi nem ra
        tls_loi = None
        der = CHUNG_CHI_DER
        bay_gio = TU + dt.timedelta(days=1)
        teams_nhan = True
        da_gui = []
        lan_goi_web = 0

        def dat_url(self, url):
            (tmp_path / ".env").write_text(f"BRAVO_SQL_UID=x\nCHATBOT_WEB_URL={url}\n", encoding="utf-8")

    m = May()
    m.da_gui = []

    def goi_web():
        m.lan_goi_web += 1
        if m.web_loi:
            raise m.web_loi
        return True

    def lay_der(host, *a, **k):
        assert host == TEN
        if m.tls_loi:
            raise m.tls_loi
        return m.der

    def gui(tieu_de, noi_dung, severity="CRITICAL"):
        m.da_gui.append((tieu_de, noi_dung, severity))
        return m.teams_nhan

    monkeypatch.setattr(wd, "_goi_web_noi_bo", goi_web)
    monkeypatch.setattr(wd, "_lay_chung_chi_der", lay_der)
    monkeypatch.setattr(wd, "_send_teams_alert", gui)
    monkeypatch.setattr(wd, "_bay_gio_utc", lambda: m.bay_gio)
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    m.dat_url(f"https://{TEN}")
    return m


def test_doc_han_chung_chi_tu_der():
    assert wd._han_chung_chi(CHUNG_CHI_DER) == (TU, DEN)
    with pytest.raises((ValueError, IndexError)):
        wd._han_chung_chi(CHUNG_CHI_DER[:40])


@pytest.mark.parametrize("url", ["", "https://dnh-bot.vercel.app", "https://DNH-BOT.vercel.app/?q=x"])
def test_con_o_vercel_thi_khong_canh(may, url):
    may.dat_url(url)
    state = {}
    wd._kiem_web_truc_tiep(state)
    assert wd._ten_mien_web_truc_tiep() is None
    assert state == {} and may.da_gui == [] and may.lan_goi_web == 0


def test_ten_mien_rieng_nhung_may_khong_co_ban_web_thi_khong_canh(may, monkeypatch, tmp_path):
    """Phuong an du phong Cloud Server: cung ten mien nhung web KHONG nam tren may nay -> khong goi 127.0.0.1."""
    monkeypatch.setattr(wd, "WEB_DIR", str(tmp_path / "khong_co"))
    assert wd._ten_mien_web_truc_tiep() is None
    monkeypatch.setenv("WATCHDOG_WEB_DIR", str(tmp_path / "web" / "current"))
    assert wd._ten_mien_web_truc_tiep() == TEN


def test_moi_thu_binh_thuong_thi_im_lang(may):
    state = {}
    wd._kiem_web_truc_tiep(state)
    assert state == {} and may.da_gui == [] and may.lan_goi_web == 1


def test_web_chet_bao_mot_lan_roi_bao_khi_song_lai(may):
    state = {}
    may.web_loi = ConnectionRefusedError("tu choi ket noi")
    wd._kiem_web_truc_tiep(state)
    wd._kiem_web_truc_tiep(state)
    assert may.lan_goi_web == 2 * wd.WEB_SO_LAN_THU          # moi luot thu du so lan truoc khi ket luan
    assert [g[0] for g in may.da_gui] == ["Web chatbot DNH không trả lời"]
    tieu_de, noi_dung, muc = may.da_gui[0]
    assert muc == "CRITICAL" and "DNH_Chatbot_Web" in noi_dung and "tu choi ket noi" in noi_dung
    assert f"https://{TEN}" in noi_dung
    assert state == {"web_local_down_alerted": True}

    may.web_loi = None
    wd._kiem_web_truc_tiep(state)
    assert may.da_gui[-1][0] == "Web chatbot DNH đã trả lời lại" and may.da_gui[-1][2] == "INFO"
    assert state == {"web_local_down_alerted": False} and len(may.da_gui) == 2


def test_loi_thoang_qua_khong_bao(may, monkeypatch):
    """Lan thu dau loi (web dang khoi dong lai), lan sau dat -> khong phai su co."""
    loi = [OSError("dang khoi dong lai")]

    def goi():
        if loi:
            raise loi.pop()
        return True

    monkeypatch.setattr(wd, "_goi_web_noi_bo", goi)
    state = {}
    wd._kiem_web_truc_tiep(state)
    assert may.da_gui == [] and state == {}


def test_caddy_khong_bat_tay_duoc_thi_bao_rieng(may):
    state = {}
    may.tls_loi = ConnectionResetError("khong co chung chi")
    wd._kiem_web_truc_tiep(state)
    assert [g[0] for g in may.da_gui] == ["Cổng HTTPS của chatbot DNH không nhận kết nối"]
    assert "DNH_Chatbot_Proxy" in may.da_gui[0][1] and may.da_gui[0][2] == "CRITICAL"
    assert state == {"web_proxy_down_alerted": True}


def test_chung_chi_bao_khi_con_duoi_mot_phan_sau_thoi_han(may):
    state = {}
    may.bay_gio = DEN - dt.timedelta(days=16)                 # 90 ngay: nguong 15 ngay
    wd._kiem_web_truc_tiep(state)
    assert may.da_gui == [] and state == {}

    may.bay_gio = DEN - dt.timedelta(days=14)
    wd._kiem_web_truc_tiep(state)
    wd._kiem_web_truc_tiep(state)
    assert [g[0] for g in may.da_gui] == ["Chứng chỉ HTTPS của chatbot DNH sắp hết hạn"]
    assert "31/12/2026" in may.da_gui[0][1] and "còn 14 ngày" in may.da_gui[0][1] and may.da_gui[0][2] == "WARNING"
    assert state == {"web_cert_expiring_alerted": True}

    may.bay_gio = TU + dt.timedelta(days=1)                   # Caddy da gia han
    wd._kiem_web_truc_tiep(state)
    assert may.da_gui[-1][0] == "Chứng chỉ HTTPS của chatbot DNH đã được gia hạn"
    assert state == {"web_cert_expiring_alerted": False}


def test_teams_khong_nhan_thi_lan_sau_bao_lai(may):
    state = {}
    may.web_loi = ConnectionRefusedError("x")
    may.teams_nhan = False
    wd._kiem_web_truc_tiep(state)
    assert len(may.da_gui) == 1 and state == {}
    may.teams_nhan = True
    wd._kiem_web_truc_tiep(state)
    assert len(may.da_gui) == 2 and state == {"web_local_down_alerted": True}


def test_run_check_luu_trang_thai_va_khong_hong_kiem_tra_cu(may, monkeypatch):
    """run_check: canh bao web duoc ghi vao state; loi bat ngo o phan web khong lam mat state cua kiem tra khac."""
    luu = {}
    monkeypatch.setattr(wd, "_check_sync_stale", lambda: (False, 0))
    monkeypatch.setattr(wd, "_check_tunnel_mismatch", lambda: (False, None, None))
    monkeypatch.setattr(wd, "_check_api_credit", lambda: (None, None, None))
    monkeypatch.setattr(wd, "_recent_credit_rejection", lambda: None)
    monkeypatch.setattr(wd, "_load_state", lambda: dict(luu))
    monkeypatch.setattr(wd, "_save_state", lambda moi: luu.update(moi))

    may.web_loi = ConnectionRefusedError("x")
    wd.run_check()
    assert luu == {"web_local_down_alerted": True}

    def no(state):
        state["web_proxy_down_alerted"] = True               # da gui mot canh bao roi moi loi
        raise RuntimeError("bat ngo")

    monkeypatch.setattr(wd, "_kiem_web_truc_tiep", no)
    wd.run_check()
    assert luu == {"web_local_down_alerted": True, "web_proxy_down_alerted": True}
