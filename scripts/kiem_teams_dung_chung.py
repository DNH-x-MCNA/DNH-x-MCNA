# -*- coding: utf-8 -*-
"""Kiem cau hinh Teams MOT Flow dung chung (TEAMS_DELIVERY_MODE=shared) tren may chay. Mac dinh CHI DOC.

    python scripts/kiem_teams_dung_chung.py                      # kiem: nhom -> UPN (da che), watchdog
    python scripts/kiem_teams_dung_chung.py --gui-thu "C-Level (Toàn quốc)"   # gui the thu toi tung nguoi nhan nhom do

Khong in URL webhook; UPN in dang da che (vd tr***@ten-mien). --gui-thu gui THAT mot the ngan "thu nghiem" qua Flow
dung chung - dung o buoc thu, khi bang nguoi nhan con tro ve UPN cua chinh nguoi van hanh.
Ma thoat 0 = san sang; 1 = cau hinh sai (he thong se DUNG gui Teams, khong gui nham nguoi).
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

GOC = Path(__file__).resolve().parents[1]
for _p in (str(GOC), str(GOC / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _nap_env():
    """Cung thu tu va override voi main.py."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for ten in (".env", "backend/.env", "config/.env"):
        if (GOC / ten).exists():
            load_dotenv(GOC / ten, override=True)


def che(upn) -> str:
    ten, _, mien = str(upn or "").partition("@")
    return f"{ten[:2]}***@{mien}" if mien else "***"


def gui_thu(webhook: str, upn: str, audience: str) -> None:
    the = {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json", "type": "AdaptiveCard", "version": "1.4",
           "body": [{"type": "TextBlock", "weight": "Bolder", "wrap": True,
                     "text": "[THU NGHIEM] Flow Teams dung chung DNH - bo qua tin nay"},
                    {"type": "TextBlock", "wrap": True, "text": f"Nhom: {audience}"}]}
    payload = {"type": "message", "recipient": upn, "audience": audience,
               "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": the}]}
    req = urllib.request.Request(webhook, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"   da gui the thu toi {che(upn)} (HTTP {resp.status})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gui-thu", metavar="TEN_NHOM", help="gui 1 the thu toi nguoi nhan cua nhom nay")
    args = ap.parse_args(argv)
    _nap_env()
    from src.database import load_config
    from src.teams_routing import TeamsRoutingError, delivery_mode, load_shared_routes
    try:
        mode = delivery_mode()
    except TeamsRoutingError as exc:
        print("LOI:", exc)
        return 1
    print("TEAMS_DELIVERY_MODE:", mode)
    if mode != "shared":
        print("Dang o che do cu (moi nhom mot Flow) - chua bat Flow dung chung.")
        return 0
    try:
        routes = load_shared_routes(load_config())
    except TeamsRoutingError as exc:
        print("LOI CAU HINH (he thong se DUNG gui Teams, khong gui nham):", exc)
        return 1
    for audience, (_, upns) in routes.items():
        print(f"   {audience:<24} -> {', '.join(che(u) for u in upns)}")
    import health_watchdog
    wd_url, wd_upns = health_watchdog._dich_den_canh_bao()
    print(f"   {'Watchdog ha tang':<24} -> {', '.join(che(u) for u in wd_upns) if wd_upns else 'THIEU nguoi nhan'}"
          f"{'' if wd_url else ' (THIEU webhook)'}")
    if args.gui_thu:
        if args.gui_thu not in routes:
            print(f"Khong co nhom '{args.gui_thu}'. Ten nhom phai dung nhu tren.")
            return 1
        webhook, upns = routes[args.gui_thu]
        for upn in upns:
            gui_thu(webhook, upn, args.gui_thu)
    return 0 if routes and wd_url and wd_upns else 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
