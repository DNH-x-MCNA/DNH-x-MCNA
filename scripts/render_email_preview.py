"""Render trước form email Weekly/Monthly ra file HTML để xem ngay bằng trình duyệt,
KHÔNG gửi mail thật và KHÔNG cần kết nối Bravo/Supabase (dùng dữ liệu mẫu).

Mục đích: chỉnh sửa DIGEST_EMAIL_TEMPLATE (src/notifier.py) xong là xem được kết quả
mọi biến thể (Monthly/Weekly x Toan quoc/OTC/ETC) thay vì đợi lịch chạy hoặc tự gửi
mail thử. File xuất vào results/email_preview/ (thu muc /results/ da gitignore).

Cách dùng:
    python scripts/render_email_preview.py            # render 6 file, in duong dan
    python scripts/render_email_preview.py --open     # render xong tu dong mo file Monthly

Luu y do chinh xac: trinh duyet render GIONG Gmail/webmail; Outlook Desktop dung Word
engine (khong ho tro mot so CSS). Muon gan nhu dung Outlook, mo file .html bang
Microsoft Word (Open with > Word) - cung nen engine voi Outlook.
"""

import os
import sys
import argparse
import webbrowser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.notifier import build_digest_email

OUT_DIR = PROJECT_ROOT / "results" / "email_preview"

BANNER = (
    '<div style="background:#7a2119; color:#fff; text-align:center; padding:8px 12px;'
    ' font-family:Segoe UI,Arial,sans-serif; font-size:13px; font-weight:600;">'
    'PREVIEW - DU LIEU MAU (khong phai bao cao that) - bien the: {label}</div>'
)


def _sample_metrics(period_label, channel=None):
    """Metrics gia lap day du moi section cua template de nhin du toan bo form."""
    monthly = period_label == "Monthly"
    return {
        "date": "21/08/2026",
        "period_range": (
            "Tháng 08/2026 (01/08 - 21/08/2026 — đang chạy)"
            if monthly else "Tuần 17/08/2026 - 21/08/2026 (đang chạy)"
        ),
        "updated_at": "17:45 21/08/2026",
        "region": None,
        "channel": channel,
        "has_critical": True,
        "highlights": [
            {"label": "Tỷ lệ nợ quá hạn OTC vượt ngưỡng", "sent_at_display": "09:12 21/08",
             "value_display": "82.4%"},
            {"label": "Khách lớn sụt giảm doanh số", "sent_at_display": "10:40 20/08",
             "value_display": "-55%"},
        ],
        "operational_quality_items": [],
        "revenue": {
            "otc": 12345678900, "etc": 5432100000, "total": 17777778900,
            "invoice_count": 321, "otc_invoice_count": 250, "etc_invoice_count": 71,
            "prev_total": 15000000000, "change_pct": 18.5,
            "prev_period_label": ("01/07-31/07/2026" if monthly else "10/08-16/08/2026"),
        },
        # Chỉ Monthly có channel_share (cờ bật card chỉ tiêu tháng) — giống etl.py thật
        "channel_share": {"otc_pct": 69.4, "etc_pct": 30.6} if (monthly and channel is None) else None,
        "trend": [
            {"label": lbl, "revenue": rev}
            for lbl, rev in (
                [("01-05/08", 3100000000), ("06-12/08", 5900000000),
                 ("13-19/08", 6200000000), ("20-21/08", 2577789000)]
                if monthly else
                [("Mon 17/08", 2900000000), ("Tue 18/08", 3300000000),
                 ("Wed 19/08", 3100000000), ("Thu 20/08", 3600000000), ("Fri 21/08", 4877789000)]
            )
        ],
        "region_growth": (
            [
                {"region": "Miền Bắc", "revenue": 7200000000, "prev_revenue": 6500000000, "growth_pct": 10.8},
                {"region": "Miền Nam", "revenue": 8100000000, "prev_revenue": 7000000000, "growth_pct": 15.7},
                {"region": "Miền Trung", "revenue": 2477789000, "prev_revenue": 1500000000, "growth_pct": 65.2},
            ]
            if (monthly and channel is None) else []
        ),
        "region_breakdown": [],
        "kpi_summary": {
            "achieved_threshold_pct": 80, "achieved_count": 7, "total_count": 10,
            "kpi_achieved_count": 6, "kpi_threshold_pct": 90,
            "full_target_count": 4, "team_pct": 87.3,
            "total_amount": 12000000000,
            "total_target": 15000000000 if monthly else None,
        },
        "kpi_breakdown": [
            {
                "region": "Miền Bắc",
                "qlvs": [
                    {"employee_name": "Nguyen Van A", "employee_code": "MB001",
                     "target": 5000000000, "amount": 4300000000, "pct": 86.0,
                     "tdvs": [
                         {"employee_name": "Tran Thi B", "employee_code": "MB011",
                          "target": 2000000000, "amount": 1900000000, "pct": 95.0},
                         {"employee_name": "Le Van C", "employee_code": "MB012",
                          "target": 1500000000, "amount": 900000000, "pct": 60.0},
                     ]},
                    {"employee_name": "Pham Van D", "employee_code": "MB002",
                     "target": 3000000000, "amount": 2600000000, "pct": 86.7, "tdvs": []},
                ],
            },
        ],
        "etc_by_employee": (
            [] if channel == "OTC" else
            [{
                "region": "Miền Nam",
                "employees": [
                    {"employee_name": "Hoang Thi E", "employee_code": "MN031",
                     "revenue": 2100000000, "invoices": 34},
                    {"employee_name": "Vu Van F", "employee_code": "MN032",
                     "revenue": 1800000000, "invoices": 27},
                ],
            }]
        ),
        "receivables": {
            "period": "Tức thời (đến 21/08/2026 17:45)",
            "total_overdue": 4200000000, "balance_end": 9000000000,
            "aging": [], "by_channel": [], "by_region": [], "top_overdue_customers": [],
        },
        "inventory": {
            "dead_stock_available": True, "dead_stock_count": 3,
            "near_stockout_available": True, "near_stockout_count": 5,
            "dead_stock_items": [
                {"item_code": "TH0231", "item_name": "Thuoc mau A 10v", "closing_value": 62000000,
                 "months_to_sell": 14.5, "channel": "OTC"},
            ],
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Render preview HTML form email Weekly/Monthly")
    parser.add_argument("--open", action="store_true", help="Mo file Monthly-Toan quoc bang trinh duyet sau khi render")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for period_label, p_tag in [("Monthly", "Thang"), ("Weekly", "Tuan")]:
        for channel, c_tag in [(None, "Toanquoc"), ("OTC", "OTC"), ("ETC", "ETC")]:
            label = f"{period_label} - {c_tag}"
            html = build_digest_email(
                _sample_metrics(period_label, channel),
                period_label=period_label,
                audience=f"[MAU] Quan ly {c_tag}" if channel else "[MAU] C-Level (Toan quoc)",
                scope_label=("Kênh " + channel) if channel else "Toàn quốc, tất cả kênh",
            )
            html = html.replace("</body>", BANNER.format(label=label) + "</body>", 1)
            out_file = OUT_DIR / f"preview_{p_tag}_{c_tag}.html"
            out_file.write_text(html, encoding="utf-8")
            written.append(out_file)
            print(f"[OK] {out_file}")

    print(f"\nHoan thanh {len(written)} file trong: {OUT_DIR}")
    if args.open:
        target = OUT_DIR / "preview_Thang_Toanquoc.html"
        webbrowser.open(target.as_uri())
        print(f"Da mo: {target}")


if __name__ == "__main__":
    main()
