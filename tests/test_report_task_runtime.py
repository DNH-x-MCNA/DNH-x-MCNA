from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import main
from scripts import run_digest_task


@pytest.mark.parametrize(
    ("flag", "function_name"),
    [
        ("--send-daily", "send_daily_digest"),
        ("--send-weekly", "send_weekly_report"),
        ("--send-monthly", "send_monthly_report"),
    ],
)
def test_main_cli_tra_ma_loi_khi_report_that_bai(monkeypatch, flag, function_name):
    monkeypatch.setattr(main, "load_config", lambda: {"environment": "production"})
    monkeypatch.setattr(main, function_name, lambda **kwargs: False)
    monkeypatch.setattr(sys, "argv", ["main.py", flag])

    with pytest.raises(SystemExit) as exc:
        main.main()

    assert exc.value.code == 1


def test_task_runner_tra_dung_trang_thai_va_truyen_scope():
    calls = []
    app = SimpleNamespace(
        send_daily_digest=lambda **kw: calls.append(("daily", kw)) or True,
        send_weekly_report=lambda **kw: calls.append(("weekly", kw)) or False,
        send_monthly_report=lambda **kw: calls.append(("monthly", kw)) or True,
    )

    assert run_digest_task.run_digest(
        "daily", dry_run=True, audience="C-Level", webhook_override="DRY_RUN", app_module=app,
    ) is True
    assert run_digest_task.run_digest("weekly", audience="Miền Bắc", app_module=app) is False
    assert calls == [
        ("daily", {"dry_run": True, "audience_filter": "C-Level", "webhook_override": "DRY_RUN"}),
        ("weekly", {"dry_run": False, "audience_filter": "Miền Bắc"}),
    ]
