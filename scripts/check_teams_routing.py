"""Validate Teams destinations without databases/models; sending a dummy card is opt-in."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.teams_routing import (
    TeamsRoutingError, load_shared_routes, load_teams_environment, resolve_destination,
)


def main(argv=None):
    import os
    import yaml

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shared", action="store_true", help="Kiểm cấu hình shared chỉ trong tiến trình này")
    parser.add_argument("--send-probe", action="store_true", help="GỬI THẬT một card thử, không có dữ liệu nghiệp vụ")
    parser.add_argument("--audience", help="Audience nhận card thử (bắt buộc khi --send-probe)")
    args = parser.parse_args(argv)
    if args.send_probe and not args.audience:
        parser.error("--send-probe cần --audience để xác định đúng người nhận")

    load_teams_environment()
    if args.shared:
        os.environ["TEAMS_DELIVERY_MODE"] = "shared"
    try:
        config_path = ROOT / "config.yaml"
        if not config_path.exists():
            config_path = ROOT / "config/config.yaml"
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        shared = load_shared_routes(config)
        audiences = config.get("report_recipients") or []
        if args.audience:
            audiences = [r for r in audiences if r.get("audience") == args.audience]
        if not audiences:
            raise TeamsRoutingError("Không tìm thấy audience.")
        if args.send_probe and shared is None:
            raise TeamsRoutingError("Card thử này yêu cầu chế độ shared; không gửi tới Flow cũ.")
        print(f"Teams mode: {'shared' if shared is not None else 'legacy'}")
        for row in audiences:
            webhook, recipient = resolve_destination(row, shared)
            print(f"{row['audience']} | region={row.get('region') or 'all'} | "
                  f"channel={row.get('channel') or 'all'} | Teams={recipient or '(do Flow cũ quyết định)'}")
            if args.send_probe:
                from src.notifier import send_teams_alert
                sent = send_teams_alert(
                    title=f"[KIỂM TRA FLOW CHUNG] {row['audience']}",
                    summary="Card kiểm tra định tuyến, không có số liệu kinh doanh. Hãy xác nhận đúng tài khoản nhận.",
                    webhook_url_override=webhook,
                    recipient=recipient,
                    audience=row["audience"],
                )
                if not sent:
                    return 1
        print("Webhook đã nhận; kiểm Run history và Teams để xác nhận thực nhận."
              if args.send_probe else "PASS cấu hình — chưa gọi webhook, chưa gửi tin, chưa kiểm thực nhận.")
        return 0
    except TeamsRoutingError as exc:
        print(f"FAIL: {exc}")
        return 1
    except (OSError, ValueError, yaml.YAMLError):
        print("FAIL: Không đọc được cấu hình. Không in nội dung file hoặc webhook.")
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
