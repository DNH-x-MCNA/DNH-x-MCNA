# -*- coding: utf-8 -*-
"""Chuyen URL webhook Teams tu config/config.yaml cu sang .env o goc repo. CHI in ten bien, KHONG in URL.

28/09/2026: repo DNH-x-MCNA de public tu 07/2026 va lo 6 URL webhook Power Automate trong config.yaml.
config.yaml nay ghi "${TEAMS_WEBHOOK_*}"; gia tri that nam trong .env cua may chay (src/database.py thay luc
doc, backend/health_watchdog.py doc TEAMS_WEBHOOK_C_LEVEL). Chay tren may 24 NGAY SAU git pull:

    python scripts/chuyen_webhook_sang_env.py          # them bien con thieu vao .env (sao luu truoc)
    python scripts/chuyen_webhook_sang_env.py --kiem   # chi kiem, khong ghi

URL cu lay tu chinh config.yaml neu file van con URL, hoac tu commit ngay truoc commit bo URL trong git.
Bien da co gia tri trong .env thi GIU NGUYEN (DNH tao lai Flow thi sua thang .env roi khoi dong lai
DNH_Realtime_Alerts). Ma thoat 0 = moi audience da co webhook; 1 = con thieu.
"""
import argparse
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

GOC = Path(__file__).resolve().parents[1]
BIEN = re.compile(r"^\$\{([A-Z][A-Z0-9_]*)\}$")


def ten_bien(recipient: dict) -> str:
    if recipient.get("region"):
        return f"TEAMS_WEBHOOK_MIEN_{str(recipient['region']).upper()}"
    if recipient.get("channel"):
        return f"TEAMS_WEBHOOK_KENH_{str(recipient['channel']).upper()}"
    return "TEAMS_WEBHOOK_C_LEVEL"


def _url_theo_audience(text: str) -> dict:
    cfg = yaml.safe_load(text) or {}
    return {r.get("audience"): str(r.get("teams_webhook") or "").strip()
            for r in cfg.get("report_recipients") or [] if isinstance(r, dict)}


def url_cu(goc: Path, hien_tai: str) -> dict:
    tu_file = {a: u for a, u in _url_theo_audience(hien_tai).items() if u.startswith("https://")}
    if tu_file:
        return tu_file
    # Commit gan nhat co dong teams_webhook la URL bi them/bo = commit bo URL; cha cua no con URL.
    commit = subprocess.run(["git", "-C", str(goc), "log", "-1", "--format=%H", "-G", 'teams_webhook: "*https://',
                             "--", "config/config.yaml"], capture_output=True, text=True).stdout.strip()
    if not commit:
        return {}
    cu = subprocess.run(["git", "-C", str(goc), "show", f"{commit}^:config/config.yaml"],
                        capture_output=True, text=True, encoding="utf-8").stdout
    return {a: u for a, u in _url_theo_audience(cu).items() if u.startswith("https://")}


def doc_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for dong in path.read_text(encoding="utf-8-sig").splitlines():
            khoa, dau, gia_tri = dong.partition("=")
            if dau and not khoa.lstrip().startswith("#"):
                out[khoa.strip()] = gia_tri.strip().strip('"').strip("'")
    return out


def main(argv=None, goc: Path = GOC) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kiem", action="store_true", help="chi kiem, khong ghi .env")
    args = ap.parse_args(argv)
    hien_tai = (goc / "config" / "config.yaml").read_text(encoding="utf-8")
    recipients = [r for r in (yaml.safe_load(hien_tai) or {}).get("report_recipients") or [] if isinstance(r, dict)]
    can = {}
    for r in recipients:
        gia_tri = str(r.get("teams_webhook") or "").strip()
        m = BIEN.match(gia_tri)
        if m or gia_tri.startswith("https://"):
            can[r.get("audience")] = m.group(1) if m else ten_bien(r)
    env_path = goc / ".env"
    env = doc_env(env_path)
    cu = url_cu(goc, hien_tai)
    them = {}
    for audience, bien in can.items():
        if env.get(bien):
            print(f"   {audience:<24} {bien:<28} da co trong .env (giu nguyen)")
        elif cu.get(audience):
            them[bien] = cu[audience]
            print(f"   {audience:<24} {bien:<28} {'se them' if args.kiem else 'them'} (URL cu, {len(cu[audience])} ky tu)")
        else:
            print(f"   {audience:<24} {bien:<28} THIEU - khong tim thay URL cu")
    if them and not args.kiem:
        # Doc byte: read_text tren Windows doi CRLF thanh LF va se ghi lai ca file bang LF.
        noi_dung = env_path.read_bytes().decode("utf-8-sig") if env_path.exists() else ""
        if env_path.exists():
            sao_luu = env_path.with_name(f".env.bak-webhook-{dt.datetime.now():%Y%m%d%H%M}")
            shutil.copy2(env_path, sao_luu)
            print(f"   sao luu .env -> {sao_luu.name}")
        xuong_dong = "\r\n" if "\r\n" in noi_dung else "\n"
        if noi_dung and not noi_dung.endswith(("\n", "\r")):
            noi_dung += xuong_dong
        noi_dung += xuong_dong.join(
            ["# Webhook Teams (28/09/2026: chuyen khoi config.yaml; DNH tao lai Flow thi sua o day)"]
            + [f"{k}={v}" for k, v in them.items()]) + xuong_dong
        env_path.write_bytes(noi_dung.encode("utf-8"))  # UTF-8 KHONG BOM: BOM lam hong ten bien dau tien
        env = doc_env(env_path)
    thieu = [a for a, b in can.items() if not (env.get(b) or (args.kiem and b in them))]
    print("KET QUA:", "du webhook cho %d audience" % len(can) if not thieu else "THIEU: " + ", ".join(thieu))
    return 1 if thieu else 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
