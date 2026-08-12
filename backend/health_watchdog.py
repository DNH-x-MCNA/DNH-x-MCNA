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
import sys
import json
import time
import datetime as dt
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

# Nguong: gap ~4-5 lan chu ky sync binh thuong (20 phut/lan, xem sync_scheduler.ps1) truoc khi coi
# la "sync da chet" - tranh bao dong gia khi 1-2 chu ky don le bi cham/retry binh thuong.
SYNC_STALE_THRESHOLD_MIN = 90
# Tunnel URL lech Vercel qua 10 phut - du dai hon nhieu so voi thoi gian redeploy binh thuong
# (~20-40s do quan sat thuc te) de tranh bao dong gia trong luc dang tu cap nhat.
TUNNEL_MISMATCH_THRESHOLD_MIN = 10

# Webhook C-Level (Toan quoc) - lay tu config/config.yaml::report_recipients, audience "C-Level
# (Toan quoc)" - dung chung kenh voi canh bao cong no hien co, KHONG can thiet lap webhook rieng.
# Co the ghi de qua bien moi truong WATCHDOG_TEAMS_WEBHOOK neu sau nay can tach kenh rieng.
DEFAULT_TEAMS_WEBHOOK = (
    "https://default44841e983bfb4f7091c1f177b036a1.f3.environment.api.powerplatform.com:443/"
    "powerautomate/automations/direct/cu/30/workflows/77995731b9a84a0ca215405a9a0aa44a/"
    "triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&"
    "sig=ua0ANvQq4GN3pX8LVmOJ0z124HWtaLB3rAWdZ5V6cpo"
)


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
    webhook_url = os.environ.get("WATCHDOG_TEAMS_WEBHOOK", DEFAULT_TEAMS_WEBHOOK)
    if not webhook_url:
        _log("KHONG co Teams webhook cau hinh - bo qua gui canh bao (chi ghi log).")
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
    try:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(webhook_url.strip(), data=data,
                                      headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10):
            _log(f"Da gui canh bao Teams: {title}")
            return True
    except Exception as e:
        _log(f"LOI gui Teams: {e}")
        return False


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

    if changed:
        _save_state(state)


if __name__ == "__main__":
    run_check()
