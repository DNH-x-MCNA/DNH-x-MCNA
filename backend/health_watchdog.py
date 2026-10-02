# -*- coding: utf-8 -*-
"""
Watchdog ha tang cho chatbot DNH - KIEM TRA DINH KY (chay qua Task Scheduler rieng, xem
register_health_watchdog_schedule.bat), KHONG can thiep vao sync_scheduler.ps1/cloudflared_supervisor.ps1
dang chay that (tranh dung vao code production da on dinh).

Boi canh (11/08/2026): trong qua trinh van hanh thuc te da phat hien 2 loai su co AM THAM (khong
co dau hieu ro rang cho nguoi dung/AI phat hien, chi lo ra khi tinh co debug viec khac):
  1. sync_scheduler.ps1 chet (vd loi path Python sai) nhung KHONG bao gio bao dong - warehouse.db
     dung im ~24-96 gio ma khong ai biet, 25 nguoi dung van xem duoc chatbot tra loi (dung du lieu
     cu) tuong nham la du lieu moi.
  2. cloudflared tunnel doi URL (binh thuong moi lan service restart) nhung buoc tu dong cap nhat
     Vercel (npx vercel redeploy) bi loi cu phap CLI - he thong chi ghi ">>> HAY SUA TAY" vao log,
     KHONG co ai doc log chu dong nen chatbot production co the "chet" (frontend goi URL cu da mat)
     ma khong ai biet cho toi khi nguoi dung bao loi.

Watchdog nay kiem tra 2 dieu kien do va gui CANH BAO THAT (Teams webhook C-Level co san, dung
chung ha tang voi canh bao cong no trong src/notifier.py) khi phat hien - CHI gui 1 lan/su co (luu
trang thai da canh bao vao file JSON nho, xem _load_state/_save_state) de tranh spam Teams neu su
co keo dai nhieu chu ky kiem tra lien tiep; tu dong gui lai NEU su co da het roi tai xuat hien
(tin hieu MOI, dang quan tam) hoac loai su co khac voi lan truoc.

KHONG import truc tiep src/notifier.py (repo khac cay thu muc - src/ chay tu goc repo, dependency
rieng nhu jinja2/dotenv, PROJECT_ROOT khac backend/) - copy lai phan TOI THIEU can thiet (adaptive
card don gian, khong bang/section phuc tap) de watchdog nay DOC LAP hoan toan, khong vo tinh hong
neu src/notifier.py doi cau truc.
"""
import os
import re
import sys
import json
import math
import time
import datetime as dt
import socket
import sqlite3
import ssl
import urllib.parse
import urllib.request

# Chay qua Task Scheduler (console cp1252 tren Windows) - log co the chua URL/ky tu dac biet (vd
# BOM ﻿ dau file .txt) gay UnicodeEncodeError khi print thang. Ep stdout/stderr sang UTF-8
# giong cach main.py/nl2sql.py da lam o cac module khac trong repo nay.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BACKEND_DIR, "logs")
STATE_PATH = os.path.join(LOG_DIR, "health_watchdog_state.json")
WAREHOUSE_DB = os.path.join(BACKEND_DIR, "warehouse.db")
CLOUDFLARED_LAST_URL_PATH = os.path.join(LOG_DIR, "cloudflared_last_url.txt")
CLOUDFLARED_SUPERVISOR_LOG = os.path.join(LOG_DIR, "cloudflared_supervisor.log")
COST_LOG_PATH = os.path.join(LOG_DIR, "cost_log.jsonl")
MEMORY_DB = os.path.join(BACKEND_DIR, "memory.db")

# Nguong: gap ~4-5 lan chu ky sync binh thuong (20 phut/lan, xem sync_scheduler.ps1) truoc khi coi
# la "sync da chet" - tranh bao dong gia khi 1-2 chu ky don le bi cham/retry binh thuong.
SYNC_STALE_THRESHOLD_MIN = 90
# Tunnel URL lech Vercel qua 10 phut - du dai hon nhieu so voi thoi gian redeploy binh thuong
# (~20-40s do quan sat thuc te) de tranh bao dong gia trong luc dang tu cap nhat.
TUNNEL_MISMATCH_THRESHOLD_MIN = 10

# 02/10/2026: web chatbot chay THANG tren may 24 (deploy/may24_truc_tiep): Caddy :443 -> Next.js 127.0.0.1:3000.
# Khi web con o Vercel thi watchdog khong canh gi phan web. Chi canh khi CA HAI dung: CHATBOT_WEB_URL (link trong the
# Teams/email) da tro ve ten mien rieng, va ban web co tren may nay. Truoc luc chuyen, hoac khi quay ve Vercel: bo qua.
WEB_DIR = r"C:\dnh_web\current"
WEB_URL_NOI_BO = "http://127.0.0.1:3000/"
WEB_LOG_DIR = r"C:\dnh_web\logs"
# deploy_web.ps1 va viec khoi dong lai dich vu lam web/Caddy ngung vai giay: thu lai truoc khi coi la su co.
WEB_SO_LAN_THU = 3
WEB_CHO_GIUA_LAN_S = 10
# Caddy tu gia han khi con 1/3 thoi han chung chi. Con duoi 1/6 (chung chi 90 ngay: duoi 15 ngay) nghia la viec gia
# han da loi mot thoi gian dang ke.
CERT_PHAN_CON_LAI_BAO_DONG = 1 / 6

# Webhook C-Level (Toan quoc) - dung chung kenh voi canh bao cong no hien co (TEAMS_WEBHOOK_C_LEVEL trong .env).
# Co the ghi de qua bien moi truong WATCHDOG_TEAMS_WEBHOOK neu sau nay can tach kenh rieng.
# 28/09/2026: URL KHONG viet trong code nua (repo tung de public 07-28/09 va lo URL nay). Watchdog chay qua Task
# Scheduler rieng, KHONG nap .env, nen tu doc dung ten bien can tu .env o goc repo roi backend/.
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)


def _doc_bien_env(ten: str) -> str:
    gia_tri = (os.environ.get(ten) or "").strip()
    if gia_tri:
        return gia_tri
    for duong_dan in (os.path.join(PROJECT_ROOT, ".env"), os.path.join(BACKEND_DIR, ".env")):
        try:
            with open(duong_dan, "r", encoding="utf-8-sig") as f:
                for dong in f:
                    khoa, dau, gia_tri = dong.partition("=")
                    if dau and khoa.strip() == ten and gia_tri.strip():
                        return gia_tri.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _webhook_canh_bao() -> str:
    return _doc_bien_env("WATCHDOG_TEAMS_WEBHOOK") or _doc_bien_env("TEAMS_WEBHOOK_C_LEVEL")


def _tach_upn(gia_tri) -> tuple:
    """"a@x" / "a@x; b@x" (bien env) / ["a@x", "b@x"] (bang JSON) -> ("a@x", "b@x"), bo trung, giu thu tu."""
    ds = gia_tri if isinstance(gia_tri, list) else re.split(r"[;,\s]+", str(gia_tri or ""))
    return tuple(dict.fromkeys(str(u).strip() for u in ds if "@" in str(u)))


def _upn_c_level() -> tuple:
    """UPN nhom C-Level trong bang nguoi nhan cua che do mot Flow dung chung (TEAMS_RECIPIENTS_FILE) - 28/09/2026:
    mot hoac nhieu nguoi."""
    duong_dan = _doc_bien_env("TEAMS_RECIPIENTS_FILE")
    if not duong_dan:
        return ()
    if not os.path.isabs(duong_dan):
        duong_dan = os.path.join(PROJECT_ROOT, duong_dan)
    try:
        with open(duong_dan, "r", encoding="utf-8-sig") as f:
            bang = json.load(f)
    except (OSError, ValueError):
        return ()
    return next((_tach_upn(upn) for ten, upn in (bang.items() if isinstance(bang, dict) else [])
                 if str(ten).strip().lower().startswith("c-level")), ())


def _dich_den_canh_bao() -> tuple:
    """(webhook, (nguoi_nhan, ...)). 28/09/2026: che do mot Flow dung chung (TEAMS_DELIVERY_MODE=shared) - Flow doc
    triggerBody()?['recipient'] de gui chat ca nhan, nen watchdog PHAI gui kem nguoi nhan: WATCHDOG_TEAMS_RECIPIENT
    (nhieu nguoi cach nhau dau ;), khong co thi UPN nhom C-Level. Che do cu: khong kem nguoi nhan - tuple rong."""
    if _doc_bien_env("TEAMS_DELIVERY_MODE").lower() == "shared":
        webhook = _doc_bien_env("WATCHDOG_TEAMS_WEBHOOK") or _doc_bien_env("TEAMS_SHARED_WEBHOOK_URL")
        return webhook, _tach_upn(_doc_bien_env("WATCHDOG_TEAMS_RECIPIENT")) or _upn_c_level()
    return _webhook_canh_bao(), ()


def _log(msg: str):
    print(f"[{dt.datetime.now().isoformat()}] {msg}")


def _load_state() -> dict:
    if os.path.exists(STATE_PATH):
        try:
            with open(STATE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict):
    os.makedirs(LOG_DIR, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _send_teams_alert(title: str, summary: str, severity: str = "CRITICAL") -> bool:
    """Ban TOI GIAN cua send_teams_alert() (xem src/notifier.py) - chi Container + TextBlock, du
    dung cho canh bao ha tang dang van ban ngan, khong can bang/anh nhu bao cao cong no."""
    webhook_url, nguoi_nhan = _dich_den_canh_bao()
    if not webhook_url:
        _log("KHONG co Teams webhook cau hinh - bo qua gui canh bao (chi ghi log).")
        return False
    if _doc_bien_env("TEAMS_DELIVERY_MODE").lower() == "shared" and not nguoi_nhan:
        _log("Che do mot Flow dung chung nhung KHONG xac dinh duoc nguoi nhan (WATCHDOG_TEAMS_RECIPIENT hoac nhom "
             "C-Level trong TEAMS_RECIPIENTS_FILE) - bo qua gui canh bao (chi ghi log).")
        return False

    style = {"CRITICAL": "attention", "WARNING": "warning"}.get(severity.upper(), "good")
    label = {"CRITICAL": "NGHIEM TRONG", "WARNING": "CANH BAO"}.get(severity.upper(), "THONG TIN")
    payload = {
        "type": "message",
        "attachments": [{
            "contentType": "application/vnd.microsoft.card.adaptive",
            "content": {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {
                        "type": "Container",
                        "style": style,
                        "bleed": True,
                        "items": [
                            {"type": "TextBlock", "text": f"[{label}] {title}",
                             "weight": "Bolder", "size": "Medium", "wrap": True},
                        ],
                    },
                    {"type": "TextBlock", "text": summary, "wrap": True, "spacing": "Medium"},
                    {"type": "TextBlock",
                     "text": f"Thoi diem: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                     "size": "Small", "isSubtle": True, "spacing": "Medium"},
                ],
            },
        }],
    }
    # Nhieu nguoi nhan: moi nguoi mot lan gui. True neu it nhat mot nguoi nhan duoc - de canh bao khong bi
    # gui lai lien tuc cho nhung nguoi da nhan chi vi mot dia chi loi.
    da_gui = False
    for upn in nguoi_nhan or (None,):
        goi = dict(payload, recipient=upn, audience="Watchdog ha tang") if upn else payload
        try:
            data = json.dumps(goi, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(webhook_url.strip(), data=data,
                                          headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10):
                _log(f"Da gui canh bao Teams: {title}")
                da_gui = True
        except Exception as e:
            _log(f"LOI gui Teams: {e}")
    return da_gui


def _check_sync_stale() -> tuple:
    """Tra ve (is_stale: bool, minutes_since_write: float hoac None neu khong doc duoc file)."""
    if not os.path.exists(WAREHOUSE_DB):
        return True, None
    mtime = dt.datetime.fromtimestamp(os.path.getmtime(WAREHOUSE_DB))
    minutes = (dt.datetime.now() - mtime).total_seconds() / 60
    return minutes > SYNC_STALE_THRESHOLD_MIN, minutes


def _check_tunnel_mismatch() -> tuple:
    """Tra ve (is_mismatch: bool, last_saved_url: str, latest_log_url: str hoac None) - so sanh
    URL trong cloudflared_last_url.txt (URL DA duoc luu/cap nhat vao Vercel lan cuoi) voi URL MOI
    NHAT xuat hien trong cloudflared_supervisor.log (URL tunnel THAT dang chay). Lech nhau lau =
    Vercel dang tro toi URL da chet."""
    if not os.path.exists(CLOUDFLARED_LAST_URL_PATH) or not os.path.exists(CLOUDFLARED_SUPERVISOR_LOG):
        return False, None, None

    # encoding="utf-8-sig" tu dong bo BOM neu file duoc PowerShell ghi bang Set-Content/Out-File
    # mac dinh (UTF-8 with BOM) - thieu dong nay se so sanh URL sai lech (BOM la 1 ky tu vo hinh
    # o dau chuoi) va gay UnicodeEncodeError khi in ra console cp1252 cua Windows.
    with open(CLOUDFLARED_LAST_URL_PATH, "r", encoding="utf-8-sig") as f:
        saved_url = f.read().strip()

    latest_url = None
    latest_ts = None
    with open(CLOUDFLARED_SUPERVISOR_LOG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if "Tunnel URL: " in line:
                try:
                    ts_str = line[:19]
                    ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                url = line.split("Tunnel URL: ", 1)[1].strip()
                latest_url = url
                latest_ts = ts

    if latest_url is None or latest_url == saved_url:
        return False, saved_url, latest_url

    minutes_since = (dt.datetime.now() - latest_ts).total_seconds() / 60 if latest_ts else 0
    return minutes_since > TUNNEL_MISMATCH_THRESHOLD_MIN, saved_url, latest_url


def _check_api_credit() -> tuple:
    """Return (estimated remaining USD, low threshold USD, snapshot key).

    Anthropic exposes usage/cost reports, but no supported balance endpoint. Operators must
    capture a Console balance and its local timestamp in WATCHDOG_API_CREDIT_SNAPSHOT_USD and
    WATCHDOG_API_CREDIT_SNAPSHOT_AT. Only this backend's Anthropic cost log is deducted, so the
    value is an estimate; external API/Console spend and auto-reloads are invisible here.
    Missing/invalid configuration or cost log means UNKNOWN, not a healthy balance.
    """
    balance_text = os.environ.get("WATCHDOG_API_CREDIT_SNAPSHOT_USD", "").strip()
    at_text = os.environ.get("WATCHDOG_API_CREDIT_SNAPSHOT_AT", "").strip()
    if not balance_text or not at_text:
        return None, None, None
    try:
        balance = float(balance_text)
        threshold = float(os.environ.get("WATCHDOG_API_CREDIT_LOW_USD", "5"))
        snapshot_at = dt.datetime.fromisoformat(at_text)
        if (not math.isfinite(balance) or not math.isfinite(threshold)
                or balance < 0 or threshold <= 0 or snapshot_at.tzinfo is not None):
            raise ValueError("snapshot must be a nonnegative USD balance and a local naive timestamp")
    except ValueError as exc:
        _log(f"Credit check: cau hinh khong hop le: {exc}")
        return None, None, None
    if not os.path.exists(COST_LOG_PATH):
        _log("Credit check: khong co cost_log.jsonl, khong the uoc tinh so du")
        return None, None, None

    spent = 0.0
    try:
        with open(COST_LOG_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    ts = dt.datetime.fromisoformat(row["ts"])
                    if ts.tzinfo is not None or ts < snapshot_at:
                        continue
                    if row.get("provider") == "Anthropic":
                        cost = float(row["cost_usd"])
                        if not math.isfinite(cost) or cost < 0:
                            raise ValueError("invalid Anthropic cost")
                        spent += cost
                except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    _log(f"Credit check: cost_log.jsonl khong doc duoc day du: {exc}")
                    return None, None, None
    except OSError as exc:
        _log(f"Credit check: khong doc duoc cost_log.jsonl: {exc}")
        return None, None, None
    return balance - spent, threshold, f"{at_text}|{balance_text}"


def _recent_credit_rejection() -> tuple | None:
    """Fallback signal when no balance snapshot exists: a real rejected web request."""
    if not os.path.exists(MEMORY_DB):
        return None
    try:
        with sqlite3.connect(f"file:{MEMORY_DB}?mode=ro", uri=True, timeout=5) as conn:
            row = conn.execute("""
                SELECT created_at, username FROM query_runs
                WHERE status IN ('error', 'api_credit_exhausted')
                  AND (LOWER(error_message) LIKE '%credit balance is too low%'
                       OR LOWER(error_message) LIKE '%insufficient_credit%')
                ORDER BY created_at DESC LIMIT 1
            """).fetchone()
    except sqlite3.Error as exc:
        _log(f"Credit rejection check: khong doc duoc query_runs: {exc}")
        return None
    if not row:
        return None
    try:
        created_at = dt.datetime.fromisoformat(row[0].replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None
    age_seconds = (dt.datetime.now(dt.timezone.utc) - created_at).total_seconds()
    if not 0 <= age_seconds <= 1800:  # watchdog runs every 15 minutes
        return None
    return row[0], row[1]


def _ten_mien_web_truc_tiep():
    """Ten mien can canh, hoac None khi web khong chay tren may nay (con o Vercel / chua chuyen / da quay ve)."""
    url = _doc_bien_env("CHATBOT_WEB_URL")
    host = (urllib.parse.urlsplit(url).hostname or "").lower() if url else ""
    if not host or host.endswith(".vercel.app"):
        return None
    if not os.path.isdir(_doc_bien_env("WATCHDOG_WEB_DIR") or WEB_DIR):
        return None
    return host


def _bay_gio_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def _goi_web_noi_bo():
    """Goi web Next.js qua loopback, bo qua proxy he thong. Khong 200 -> nem loi."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(WEB_URL_NOI_BO, timeout=10) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
    return True


def _lay_chung_chi_der(host: str, may: str = "127.0.0.1", cong: int = 443) -> bytes:
    """Bat tay TLS voi Caddy tren chinh may nay (SNI = ten mien) va tra ve chung chi dang phuc vu (DER).
    Khong xac thuc chuoi chung chi: Python tren Windows dung kho CA cua may, kho do co the chua co goc cua
    Let's Encrypt va se bao dong gia. O day chi can biet Caddy co phuc vu chung chi va no het han ngay nao."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((may, cong), timeout=10) as s:
        with ctx.wrap_socket(s, server_hostname=host) as t:
            der = t.getpeercert(binary_form=True)
    if not der:
        raise RuntimeError("may chu khong gui chung chi")
    return der


def _der_phan_tu(buf: bytes, vi_tri: int) -> tuple:
    """(tag, dau_noi_dung, cuoi_noi_dung) cua phan tu DER bat dau tai vi_tri."""
    tag = buf[vi_tri]
    do_dai = buf[vi_tri + 1]
    vi_tri += 2
    if do_dai & 0x80:
        so_byte = do_dai & 0x7F
        do_dai = int.from_bytes(buf[vi_tri:vi_tri + so_byte], "big")
        vi_tri += so_byte
    return tag, vi_tri, vi_tri + do_dai


def _han_chung_chi(der: bytes) -> tuple:
    """(notBefore, notAfter) theo gio UTC cua mot chung chi X.509 dang DER. Tu doc cau truc de watchdog khong phu
    thuoc thu vien ngoai: Certificate -> tbsCertificate -> [version] serial, signature, issuer, validity."""
    _, p, _ = _der_phan_tu(der, 0)
    _, p, _ = _der_phan_tu(der, p)
    tag, _, cuoi = _der_phan_tu(der, p)
    if tag == 0xA0:                         # [0] version - chung chi v1 khong co
        p = cuoi
    for _ in range(3):                      # serialNumber, signature, issuer
        _, _, p = _der_phan_tu(der, p)
    _, p, _ = _der_phan_tu(der, p)          # validity
    moc = []
    for _ in range(2):
        tag, dau, p = _der_phan_tu(der, p)
        dinh_dang = "%y%m%d%H%M%SZ" if tag == 0x17 else "%Y%m%d%H%M%SZ"   # UTCTime / GeneralizedTime
        moc.append(dt.datetime.strptime(der[dau:p].decode("ascii"), dinh_dang))
    return moc[0], moc[1]


def _thu_nhieu_lan(viec) -> tuple:
    """(ket_qua, None) neu mot lan thu dat; (None, loi_cuoi) neu ca WEB_SO_LAN_THU lan deu loi."""
    loi = "khong ro"
    for lan in range(WEB_SO_LAN_THU):
        if lan:
            time.sleep(WEB_CHO_GIUA_LAN_S)
        try:
            return viec(), None
        except Exception as exc:
            loi = f"{type(exc).__name__}: {exc}"
    return None, loi


def _bao_khi_doi(state: dict, khoa: str, dang_loi: bool, bao_loi: tuple, bao_het: tuple):
    """Gui MOT canh bao khi bat dau loi va MOT tin khi het loi, ghi nho vao state[khoa]. bao_loi = (tieu de, noi
    dung, muc do); bao_het = (tieu de, noi dung). Chi ghi nho "da bao" khi Teams nhan, de canh bao khong mat vi mot
    lan gui loi."""
    da_bao = state.get(khoa, False)
    if dang_loi and not da_bao:
        if _send_teams_alert(bao_loi[0], bao_loi[1], severity=bao_loi[2]):
            state[khoa] = True
    elif not dang_loi and da_bao:
        _send_teams_alert(bao_het[0], bao_het[1], severity="INFO")
        state[khoa] = False


def _kiem_web_truc_tiep(state: dict):
    """Canh web chay thang tren may 24: Next.js (3000), Caddy (443) va han chung chi. Ghi ket qua vao state."""
    host = _ten_mien_web_truc_tiep()
    if not host:
        _log("Web check: BO QUA (CHATBOT_WEB_URL chua tro ve ten mien rieng, hoac may nay khong co ban web)")
        return

    _, loi_web = _thu_nhieu_lan(_goi_web_noi_bo)
    _bao_khi_doi(
        state, "web_local_down_alerted", loi_web is not None,
        ("Web chatbot DNH không trả lời",
         f"Web (Next.js, cổng 3000 trên máy 24) không trả lời sau {WEB_SO_LAN_THU} lần thử: {loi_web}. "
         f"Người dùng mở https://{host} sẽ gặp lỗi 502. Kiểm tra dịch vụ DNH_Chatbot_Web trên máy 24; "
         f"nhật ký ở {WEB_LOG_DIR}\\DNH_Chatbot_Web.err.log.",
         "CRITICAL"),
        ("Web chatbot DNH đã trả lời lại", "Web (cổng 3000 trên máy 24) trả lời bình thường."),
    )

    der, loi_tls = _thu_nhieu_lan(lambda: _lay_chung_chi_der(host))
    _bao_khi_doi(
        state, "web_proxy_down_alerted", loi_tls is not None,
        ("Cổng HTTPS của chatbot DNH không nhận kết nối",
         f"Caddy (cổng 443 trên máy 24) không bắt tay TLS được cho {host} sau {WEB_SO_LAN_THU} lần thử: "
         f"{loi_tls}. Người dùng không mở được https://{host}. Kiểm tra dịch vụ DNH_Chatbot_Proxy trên "
         f"máy 24; nhật ký ở {WEB_LOG_DIR}\\DNH_Chatbot_Proxy.err.log.",
         "CRITICAL"),
        ("Cổng HTTPS của chatbot DNH đã nhận kết nối lại", f"Caddy phục vụ {host} bình thường."),
    )

    con_lai = None
    if der:
        try:
            tu, den = _han_chung_chi(der)
        except (ValueError, IndexError) as exc:
            _log(f"Web check: khong doc duoc han chung chi: {type(exc).__name__}: {exc}")
            return
        con_lai = (den - _bay_gio_utc()).total_seconds() / 86400
        thoi_han = (den - tu).total_seconds() / 86400
        _bao_khi_doi(
            state, "web_cert_expiring_alerted", con_lai < thoi_han * CERT_PHAN_CON_LAI_BAO_DONG,
            ("Chứng chỉ HTTPS của chatbot DNH sắp hết hạn",
             f"Chứng chỉ của {host} hết hạn ngày {den:%d/%m/%Y} (còn {max(con_lai, 0):.0f} ngày). Caddy tự gia "
             "hạn khi còn 1/3 thời hạn, nên còn ít thế này nghĩa là việc gia hạn đang lỗi — thường do cổng 443 "
             "từ Internet vào máy 24 bị chặn hoặc bản ghi DNS đã đổi. Hết hạn thì trình duyệt chặn trang. "
             f"Xem {WEB_LOG_DIR}\\DNH_Chatbot_Proxy.err.log.",
             "WARNING"),
            ("Chứng chỉ HTTPS của chatbot DNH đã được gia hạn", f"Hạn mới của {host}: {den:%d/%m/%Y}."),
        )
    _log(f"Web check: host={host}, web_loi={loi_web}, tls_loi={loi_tls}, "
         f"chung_chi_con_ngay={None if con_lai is None else round(con_lai, 1)}")


def run_check():
    state = _load_state()
    changed = False

    is_stale, minutes = _check_sync_stale()
    prev_sync_alerted = state.get("sync_stale_alerted", False)
    if is_stale and not prev_sync_alerted:
        minutes_txt = f"{minutes:.0f} phut" if minutes is not None else "khong xac dinh (file khong ton tai)"
        _send_teams_alert(
            "Dong bo du lieu chatbot DNH da NGUNG",
            f"warehouse.db khong duoc cap nhat trong {minutes_txt} qua "
            f"(nguong canh bao: {SYNC_STALE_THRESHOLD_MIN} phut). "
            "Chatbot co the dang tra loi bang du lieu CU. Kiem tra sync_scheduler.ps1 tren may .24.",
            severity="CRITICAL",
        )
        state["sync_stale_alerted"] = True
        changed = True
    elif not is_stale and prev_sync_alerted:
        _send_teams_alert(
            "Dong bo du lieu chatbot DNH da PHUC HOI",
            f"warehouse.db da duoc cap nhat lai binh thuong ({minutes:.0f} phut truoc).",
            severity="INFO",
        )
        state["sync_stale_alerted"] = False
        changed = True
    _log(f"Sync check: is_stale={is_stale}, minutes={minutes}")

    is_mismatch, saved_url, latest_url = _check_tunnel_mismatch()
    prev_tunnel_alerted = state.get("tunnel_mismatch_alerted", False)
    if is_mismatch and not prev_tunnel_alerted:
        _send_teams_alert(
            "URL Backend chatbot DNH tren Vercel co the DA CU",
            f"Tunnel that dang chay: {latest_url}\n"
            f"URL da luu vao Vercel lan cuoi: {saved_url}\n"
            "Buoc tu dong cap nhat Vercel (npx vercel redeploy) co the da loi - xem "
            "logs/cloudflared_supervisor.log tren may .24 de xac nhan, roi cap nhat tay "
            "BACKEND_API_URL tren Vercel + redeploy.",
            severity="CRITICAL",
        )
        state["tunnel_mismatch_alerted"] = True
        changed = True
    elif not is_mismatch and prev_tunnel_alerted:
        _send_teams_alert(
            "URL Backend chatbot DNH tren Vercel da DUOC CAP NHAT",
            f"Vercel va tunnel that da khop URL ({latest_url}).",
            severity="INFO",
        )
        state["tunnel_mismatch_alerted"] = False
        changed = True
    _log(f"Tunnel check: is_mismatch={is_mismatch}, saved={saved_url}, latest={latest_url}")

    remaining, threshold, snapshot_key = _check_api_credit()
    if remaining is None:
        _log("Credit check: CHUA GIAM SAT (can snapshot so du va cost log)")
    else:
        if state.get("api_credit_snapshot_key") != snapshot_key:
            state["api_credit_snapshot_key"] = snapshot_key
            state["api_credit_low_alerted"] = False
            changed = True
        if remaining <= threshold and not state.get("api_credit_low_alerted", False):
            sent = _send_teams_alert(
                "Han muc API Claude sap can",
                f"Số dư ước tính còn ${remaining:.2f}, dưới ngưỡng ${threshold:.2f}. "
                "Đối chiếu số dư thực trong Anthropic Console > Settings > Billing và nạp thêm "
                "trước khi chatbot ngừng trả lời. Ước tính chỉ trừ chi phí Anthropic trong "
                "backend/logs/cost_log.jsonl từ mốc số dư đã cấu hình; chi phí ngoài chatbot "
                "và tự nạp tiền không được tính.",
                severity="WARNING",
            )
            if sent:
                state["api_credit_low_alerted"] = True
                changed = True
        elif remaining > threshold and state.get("api_credit_low_alerted", False):
            state["api_credit_low_alerted"] = False
            changed = True
        _log(f"Credit check: estimated_remaining_usd={remaining:.2f}, low_usd={threshold:.2f}")

    rejection = _recent_credit_rejection()
    if rejection and not state.get("api_credit_exhausted_alerted", False):
        sent = _send_teams_alert(
            "API Claude da HET credit",
            f"Anthropic vua tu choi cau hoi cua {rejection[1]} luc {rejection[0]} UTC vi het credit. "
            "Kiem tra Anthropic Console > Settings > Billing va nap them credit; "
            "nguoi dung da duoc bao khong can hoi lai.",
            severity="CRITICAL",
        )
        if sent:
            state["api_credit_exhausted_alerted"] = True
            changed = True
    elif not rejection and state.get("api_credit_exhausted_alerted", False):
        state["api_credit_exhausted_alerted"] = False
        changed = True

    # Loi o phan canh web khong duoc lam mat trang thai cua cac kiem tra phia tren; canh bao nao da gui thi van
    # duoc ghi nho (so state truoc/sau thay vi tin gia tri tra ve).
    truoc = dict(state)
    try:
        _kiem_web_truc_tiep(state)
    except Exception as exc:
        _log(f"Web check: LOI khong luong truoc: {type(exc).__name__}: {exc}")
    changed = changed or state != truoc

    if changed:
        _save_state(state)


if __name__ == "__main__":
    run_check()
