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
    assert run_digest_task.run_digest(
        "weekly",
        audience="Miền Bắc",
        email_override="approved@example.invalid",
        app_module=app,
    ) is False
    assert calls == [
        ("daily", {"dry_run": True, "audience_filter": "C-Level", "webhook_override": "DRY_RUN",
                   "email_override": None}),
        ("weekly", {
            "dry_run": False,
            "audience_filter": "Miền Bắc",
            "email_override": "approved@example.invalid",
        }),
    ]


@pytest.mark.parametrize(
    ("role", "sent_ok", "dry_run"),
    [("qlv", True, False), ("asm", True, False), ("rm", True, False),
     ("qlv", False, False), ("qlv", True, True)],
)
def test_daily_cli_override_chi_gui_hop_thu_thu_va_giu_ma_thoat(
    monkeypatch, tmp_path, role, sent_ok, dry_run,
):
    """Exercise CLI -> runner -> real Daily routing, with transport/data mocked."""
    monkeypatch.setattr(run_digest_task, "ROOT", tmp_path)
    monkeypatch.setattr(run_digest_task, "importlib", SimpleNamespace(import_module=lambda name: main))
    monkeypatch.setattr(main, "load_shared_routes", lambda config: None)
    monkeypatch.setattr(main, "load_config", lambda: {"report_recipients": [
        {"audience": "Đội thử", "role": role, "employee_code": "QLV01", "region": "bac",
         "channel": "OTC", "emails": ["configured@example.invalid"]},
        {"audience": "C-Level", "role": "c_level", "region": None, "channel": None},
    ]})
    scopes, recipients = [], []
    monkeypatch.setattr(main, "build_qlv_digest_metrics", lambda **kw: scopes.append(kw) or
                        {"date": "2026-09-28"})
    monkeypatch.setattr(main, "build_qlv_daily_email", lambda *args: "<p>Đội thử</p>")
    monkeypatch.setattr(main, "get_daily_digest_metrics", lambda **kw: pytest.fail("Sai phạm vi đội"))
    monkeypatch.setattr(main, "send_teams_alert", lambda **kw: pytest.fail("Không gửi Teams"))
    monkeypatch.setattr(main, "send_email", lambda *args, **kw:
                        recipients.append(kw["recipient_override"]) or sent_ok)
    argv = ["daily", "--audience", "Đội thử", "--email-override", "approved@example.invalid"]
    if dry_run:
        argv.append("--dry-run")

    assert run_digest_task.main(argv) == (0 if dry_run or sent_ok else 1)
    assert scopes == [{"employee_code": "QLV01", "region": "bac", "channel": "OTC"}]
    assert recipients == ([] if dry_run else [["approved@example.invalid"]])
    log = (tmp_path / "logs" / "daily_digest.log").read_text(encoding="utf-8")
    assert "Đội thử" in log
    assert ("hoàn tất thành công" in log) == (dry_run or sent_ok)


def test_runner_exception_tra_1_va_ghi_log(monkeypatch, tmp_path):
    monkeypatch.setattr(run_digest_task, "ROOT", tmp_path)

    def fail(*args, **kwargs):
        raise RuntimeError("Lỗi dựng báo cáo giả")

    monkeypatch.setattr(run_digest_task, "run_digest", fail)
    assert run_digest_task.main(["monthly"]) == 1
    log = (tmp_path / "logs" / "monthly_report.log").read_text(encoding="utf-8")
    assert "RuntimeError" in log
    assert "hoàn tất thành công" not in log
