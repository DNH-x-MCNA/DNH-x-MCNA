# -*- coding: utf-8 -*-
"""Xem truoc bo canh bao kiem thu nguoc SE GUI GI - khong gui Teams/email, khong dong vao DB trang thai that.

Chay tren may 24 TRUOC khi khoi dong lai DNH_Realtime_Alerts:
    set PYTHONIOENCODING=utf-8
    python scripts\\xem_truoc_canh_bao.py

Chi doc Bravo. DB chong lap duoc CHEP sang file tam, nen cac canh bao da gui gan day van duoc tinh la
"da gui" (dung nhu lan chay that dau tien) ma khong ghi gi vao ban that.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import main  # noqa: E402,F401  (nap .env)
import src.alerts as alerts  # noqa: E402
from src import insights  # noqa: E402


def main_run():
    tam = tempfile.mkdtemp(prefix="xem_truoc_canh_bao_")
    that = alerts.STATE_DB_PATH
    ban_sao = os.path.join(tam, "alerts_state.db")
    if os.path.exists(that):
        shutil.copyfile(that, ban_sao)
    alerts.STATE_DB_DIR, alerts.STATE_DB_PATH = tam, ban_sao

    se_gui = []

    def ghi_lai(**kw):
        se_gui.append(kw)
        return True

    alerts.send_alert_to_all_channels = ghi_lai
    bundle = insights.build_insight_bundle(force=True)
    print(f"Du lieu den {bundle['as_of']} | loi tung phan: {bundle['errors'] or 'khong'}")
    for check in (alerts.check_channel_month_pace_alert, alerts.check_team_pace_alert,
                  alerts.check_silent_regular_customers_alert, alerts.check_new_over45_debtors_alert,
                  alerts.check_overdue_over45_still_ordering_alert):
        check(bundle)
    alerts.check_etc_return_rate_30d_alert()

    print("\n" + "=" * 90)
    print(f"SE GUI {len(se_gui)} thong bao (khong gui that):")
    for kw in se_gui:
        noi_nhan = "Teams ngay" if kw.get("severity") == "CRITICAL" or kw.get("require_critical_for_teams") is False else "chi ghi log"
        print(f"\n[{kw.get('severity')}] {kw.get('alert_name')} | {kw.get('region')} | kenh {kw.get('channel')} | {noi_nhan}")
        print("  " + str(kw.get("summary"))[:300])
        for row in (kw.get("table_rows") or [])[:10]:
            print("   - " + " | ".join(str(c) for c in row))
    shutil.rmtree(tam, ignore_errors=True)


if __name__ == "__main__":
    main_run()
