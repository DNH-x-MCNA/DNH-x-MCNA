"""28/09/2026: repo DNH-x-MCNA de public tu 07/2026 va lo 6 URL webhook Power Automate (config.yaml) + mot ban sao
trong backend/health_watchdog.py. URL that nay nam trong .env cua may chay; config.yaml ghi "${TEAMS_WEBHOOK_*}".
Du lieu gia."""
import importlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

GOC = Path(__file__).resolve().parents[1]
for _p in (str(GOC), str(GOC / "backend")):
    if _p not in sys.path:
        sys.path.append(_p)

from src import database  # noqa: E402

chuyen = importlib.import_module("scripts.chuyen_webhook_sang_env")

URL_GIA = {a: f"https://flow.example.test/{i}?sp=%2Ftriggers&sig={'x' * 43}" for i, a in enumerate(
    ("C-Level (Toàn quốc)", "Quản lý Miền Bắc", "Quản lý Miền Nam", "Quản lý Miền Trung",
     "Quản lý Kênh OTC", "Quản lý Kênh ETC"))}
PHAM_VI = {"C-Level (Toàn quốc)": (None, None), "Quản lý Miền Bắc": ("bac", None), "Quản lý Miền Nam": ("nam", None),
           "Quản lý Miền Trung": ("trung", None), "Quản lý Kênh OTC": (None, "OTC"), "Quản lý Kênh ETC": (None, "ETC")}


def _cau_hinh(dung_bien: bool) -> str:
    ds = []
    for a, (mien, kenh) in PHAM_VI.items():
        r = {"audience": a, "region": mien, "channel": kenh, "emails": []}
        r["teams_webhook"] = "${%s}" % chuyen.ten_bien(r) if dung_bien else URL_GIA[a]
        ds.append(r)
    return yaml.safe_dump({"environment": "production", "report_recipients": ds}, allow_unicode=True)


def test_load_config_thay_bien_env_va_bao_thieu_mot_lan(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.yaml"
    cfg.write_text('a: "${WEBHOOK_THU_A}"\nds: ["${WEBHOOK_THU_B}", "giu nguyen"]\nnoi: "tien to ${WEBHOOK_THU_A}"\n',
                   encoding="utf-8")
    monkeypatch.setattr(database, "CONFIG_PATH", str(cfg))
    monkeypatch.setattr(database, "_bien_da_bao_thieu", set())
    monkeypatch.setenv("WEBHOOK_THU_A", "https://a.example.test")
    monkeypatch.delenv("WEBHOOK_THU_B", raising=False)

    lan1, lan2 = database.load_config(), database.load_config()

    assert lan1["a"] == "https://a.example.test"
    assert lan1["ds"] == ["", "giu nguyen"]
    assert lan1["noi"] == "tien to ${WEBHOOK_THU_A}", "Chi thay khi ca gia tri la mot bien."
    assert lan2 == lan1
    assert capsys.readouterr().out.count("WEBHOOK_THU_B") == 1


def test_repo_khong_con_url_webhook_hay_mat_khau_that():
    cfg = yaml.safe_load((GOC / "config" / "config.yaml").read_text(encoding="utf-8"))
    for r in cfg["report_recipients"]:
        assert r["teams_webhook"] == "${%s}" % chuyen.ten_bien(r), r["audience"]
    for f in ("config/config.yaml", "backend/health_watchdog.py", ".env.example",
              "scripts/etl_airflow_templates/dnh_daily_etl.py"):
        noi_dung = (GOC / f).read_text(encoding="utf-8")
        assert "powerplatform.com" not in noi_dung and "sig=" not in noi_dung, f
    mau = (GOC / "scripts/etl_airflow_templates/dnh_daily_etl.py").read_text(encoding="utf-8")
    assert '"PWD=<MAT_KHAU>;"' in mau


def test_watchdog_doc_webhook_c_level_tu_env_file(tmp_path, monkeypatch):
    import health_watchdog as wd
    (tmp_path / "backend").mkdir()
    (tmp_path / ".env").write_text("BRAVO_SQL_UID=x\nTEAMS_WEBHOOK_C_LEVEL=https://c.example.test\n", encoding="utf-8")
    monkeypatch.setattr(wd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(wd, "BACKEND_DIR", str(tmp_path / "backend"))
    monkeypatch.delenv("WATCHDOG_TEAMS_WEBHOOK", raising=False)
    monkeypatch.delenv("TEAMS_WEBHOOK_C_LEVEL", raising=False)

    assert wd._webhook_canh_bao() == "https://c.example.test"
    monkeypatch.setenv("WATCHDOG_TEAMS_WEBHOOK", "https://rieng.example.test")
    assert wd._webhook_canh_bao() == "https://rieng.example.test"
    assert not hasattr(wd, "DEFAULT_TEAMS_WEBHOOK")


def _goc_gia(tmp_path, dung_bien):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(_cau_hinh(dung_bien), encoding="utf-8")
    (tmp_path / ".env").write_bytes(b"BRAVO_SQL_UID=abc\r\nSMTP_USER=x@example.test")
    return tmp_path


def test_chuyen_truoc_khi_pull_ghi_du_6_bien_khong_bom_khong_in_url(tmp_path, capsys):
    goc = _goc_gia(tmp_path, dung_bien=False)

    assert chuyen.main([], goc=goc) == 0

    raw = (goc / ".env").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf") and raw.startswith(b"BRAVO_SQL_UID=abc\r\nSMTP_USER=x@example.test\r\n")
    env = chuyen.doc_env(goc / ".env")
    assert env["TEAMS_WEBHOOK_MIEN_BAC"] == URL_GIA["Quản lý Miền Bắc"]
    assert env["TEAMS_WEBHOOK_C_LEVEL"] == URL_GIA["C-Level (Toàn quốc)"]
    assert len(list(goc.glob(".env.bak-webhook-*"))) == 1
    out = capsys.readouterr().out
    assert "flow.example.test" not in out and "sig=" not in out


def test_chuyen_sau_khi_pull_lay_url_tu_lich_su_git_va_chay_lai_khong_nhan_ban(tmp_path, capsys):
    if not shutil.which("git"):
        pytest.skip("can git")
    goc = _goc_gia(tmp_path, dung_bien=False)
    git = lambda *a: subprocess.run(["git", "-C", str(goc), *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@example.test", "add", "config/config.yaml")
    git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-m", "cu")
    (goc / "config" / "config.yaml").write_text(_cau_hinh(dung_bien=True), encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@example.test", "commit", "-q", "-am", "bo url")

    assert chuyen.main(["--kiem"], goc=goc) == 0
    assert "TEAMS_WEBHOOK" not in (goc / ".env").read_text(encoding="utf-8"), "--kiem khong duoc ghi."
    assert chuyen.main([], goc=goc) == 0
    assert chuyen.doc_env(goc / ".env")["TEAMS_WEBHOOK_KENH_ETC"] == URL_GIA["Quản lý Kênh ETC"]
    assert chuyen.main([], goc=goc) == 0
    assert (goc / ".env").read_text(encoding="utf-8").count("TEAMS_WEBHOOK_KENH_ETC=") == 1
    assert len(list(goc.glob(".env.bak-webhook-*"))) == 1


def test_chuyen_thieu_url_thi_bao_ma_1(tmp_path):
    goc = _goc_gia(tmp_path, dung_bien=True)  # khong co git, khong co URL cu
    assert chuyen.main([], goc=goc) == 1
