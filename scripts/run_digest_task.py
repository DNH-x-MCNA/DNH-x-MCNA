# -*- coding: utf-8 -*-
"""Scheduled Task entry point for Daily/Weekly/Monthly reports.

The old Task Scheduler action wrapped ``main.py`` in a long ``cmd.exe /c``
expression.  Reports were delivered but Task Scheduler recorded exit code 255,
and the redirected Vietnamese log used the SYSTEM account's legacy code page.
This runner owns the UTF-8 log file and returns the report function's real
success/failure status to Task Scheduler.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_NAMES = {
    "daily": "daily_digest.log",
    "weekly": "weekly_report.log",
    "monthly": "monthly_report.log",
}


class _Tee:
    """Write the same Unicode text to the console and the task log."""

    def __init__(self, *streams: Any):
        self.streams = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
            stream.flush()
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def run_digest(period: str, *, dry_run: bool = False, audience: str | None = None,
               webhook_override: str | None = None, app_module: Any | None = None) -> bool:
    """Run exactly one report period and return its aggregate delivery status."""
    app = app_module or importlib.import_module("main")
    if period == "daily":
        return bool(app.send_daily_digest(
            dry_run=dry_run,
            audience_filter=audience,
            webhook_override=webhook_override,
        ))
    if period == "weekly":
        return bool(app.send_weekly_report(dry_run=dry_run, audience_filter=audience))
    if period == "monthly":
        return bool(app.send_monthly_report(dry_run=dry_run, audience_filter=audience))
    raise ValueError(f"Kỳ báo cáo không hợp lệ: {period}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy một báo cáo định kỳ và ghi log UTF-8")
    parser.add_argument("period", choices=tuple(LOG_NAMES))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audience")
    parser.add_argument("--teams-webhook-override")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / LOG_NAMES[args.period]
    with log_path.open("a", encoding="utf-8", newline="") as log_file:
        out = _Tee(sys.stdout, log_file)
        err = _Tee(sys.stderr, log_file)
        with redirect_stdout(out), redirect_stderr(err):
            print(f"\n===== {datetime.now():%Y-%m-%d %H:%M:%S} --send-{args.period} =====")
            try:
                ok = run_digest(
                    args.period,
                    dry_run=args.dry_run,
                    audience=args.audience,
                    webhook_override=args.teams_webhook_override,
                )
            except Exception:
                traceback.print_exc()
                return 1
            if not ok:
                print(f"[TASK] Báo cáo {args.period} có ít nhất một người nhận thất bại.")
                return 1
            print(f"[TASK] Báo cáo {args.period} hoàn tất thành công.")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
