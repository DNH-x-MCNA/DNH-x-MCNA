"""28/09/2026: gop 6 Flow Teams thanh MOT Flow dung chung (TEAMS_DELIVERY_MODE=shared) - Flow doc
triggerBody()?['recipient'] de gui chat ca nhan. Watchdog truoc day gui thang vao Flow C-Level khong kem nguoi nhan,
o che do moi se khong toi ai. Du lieu gia."""
import importlib
import json
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

import health_watchdog as wd  # noqa: E402
from src.teams_routing import teams_audience_allowed  # noqa: E402

kiem = importlib.import_module("scripts.kiem_teams_dung_chung")
BIEN = ("TEAMS_DELIVERY_MODE", "TEAMS_SHARED_WEBHOOK_URL", "TEAMS_RECIPIENTS_FILE", "WATCHDOG_TEAMS_WEBHOOK",
        "WATCHDOG_TEAMS_RECIPIENT", "TEAMS_WEBHOOK_C_LEVEL")


@pytest.fixture
def goc_gia(tmp_path, monkeypatch):
    for ten in BIEN:
        monkeypatch.delenv(ten, raising=False)
    (tmp_path / "backend").mkdir()
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(wd, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(wd, "BACKEND_DIR", str(tmp_path / "backend"))
    return tmp_path


def _shared(goc, upn_c_level="clevel@example.test", them=""):
    (goc / "config" / "teams_recipients.local.json").write_text(
        json.dumps({"C-Level (Toàn quốc)": upn_c_level, "Quản lý Miền Bắc": "mb@example.test"}, ensure_ascii=False),
        encoding="utf-8")
    (goc / ".env").write_text("TEAMS_DELIVERY_MODE=shared\nTEAMS_SHARED_WEBHOOK_URL=https://shared.example.test/x\n"
                              "TEAMS_RECIPIENTS_FILE=config/teams_recipients.local.json\n"
                              "TEAMS_WEBHOOK_C_LEVEL=https://cu.example.test/c\n" + them, encoding="utf-8")


def test_watchdog_che_do_cu_giu_nguyen(goc_gia):
    (goc_gia / ".env").write_text("TEAMS_WEBHOOK_C_LEVEL=https://cu.example.test/c\n", encoding="utf-8")
    assert wd._dich_den_canh_bao() == ("https://cu.example.test/c", ())


def test_watchdog_mot_flow_gui_kem_upn_c_level(goc_gia, monkeypatch):
    _shared(goc_gia)
    assert wd._dich_den_canh_bao() == ("https://shared.example.test/x", ("clevel@example.test",))
    monkeypatch.setenv("WATCHDOG_TEAMS_RECIPIENT", "ops@example.test")
    assert wd._dich_den_canh_bao()[1] == ("ops@example.test",)


class _Resp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_watchdog_nhieu_nguoi_nhan_gui_tung_nguoi_mot_nguoi_loi_khong_chan(goc_gia, monkeypatch):
    """28/09: C-Level co the 2-3 nguoi (danh sach trong bang), WATCHDOG_TEAMS_RECIPIENT nhieu nguoi cach nhau ;"""
    goi = []

    def _urlopen(req, timeout=10):
        goi.append(json.loads(req.data.decode("utf-8"))["recipient"])
        if goi[-1] == "loi@x.test":
            raise OSError("mang loi")
        return _Resp()

    monkeypatch.setattr(wd.urllib.request, "urlopen", _urlopen)
    _shared(goc_gia)
    (goc_gia / "config" / "teams_recipients.local.json").write_text(
        json.dumps({"C-Level (Toàn quốc)": ["a@x.test", "b@x.test"]}, ensure_ascii=False), encoding="utf-8")
    assert wd._send_teams_alert("Sync dung", "x") is True
    assert goi == ["a@x.test", "b@x.test"]

    goi.clear()
    monkeypatch.setenv("WATCHDOG_TEAMS_RECIPIENT", "loi@x.test; ops@x.test")
    assert wd._send_teams_alert("Sync dung", "x") is True
    assert goi == ["loi@x.test", "ops@x.test"]


def test_watchdog_payload_co_recipient_va_thieu_nguoi_nhan_thi_khong_gui(goc_gia, monkeypatch):
    goi = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(wd.urllib.request, "urlopen",
                        lambda req, timeout=10: goi.append(json.loads(req.data.decode("utf-8"))) or _Resp())
    _shared(goc_gia)
    assert wd._send_teams_alert("Sync dung", "Kho chua cap nhat 2 gio") is True
    assert goi[-1]["recipient"] == "clevel@example.test" and goi[-1]["audience"] == "Watchdog ha tang"

    goi.clear()
    _shared(goc_gia, upn_c_level="")
    (goc_gia / "config" / "teams_recipients.local.json").write_text(json.dumps({"Quản lý Miền Bắc": "mb@x.test"}),
                                                                   encoding="utf-8")
    assert wd._send_teams_alert("Sync dung", "x") is False and goi == []


def test_bang_nguoi_nhan_local_bi_gitignore_file_mau_thi_khong():
    if not shutil.which("git"):
        pytest.skip("can git")
    chay = lambda f: subprocess.run(["git", "-C", str(GOC), "check-ignore", "-q", f]).returncode  # noqa: E731
    assert chay("config/teams_recipients.local.json") == 0
    assert chay("config/teams_recipients.example.json") == 1


def test_file_mau_co_dung_ten_cac_nhom_teams_trong_config():
    cfg = yaml.safe_load((GOC / "config" / "config.yaml").read_text(encoding="utf-8"))
    ten_nhom = {r["audience"] for r in cfg["report_recipients"] if teams_audience_allowed(r)}
    mau = json.loads((GOC / "config" / "teams_recipients.example.json").read_text(encoding="utf-8"))
    assert set(mau) == ten_nhom, "Chep file mau la dung ngay - ten nhom phai khop tung chu voi config.yaml."


def test_script_kiem_in_upn_da_che_va_bao_thieu(goc_gia, monkeypatch, capsys):
    _shared(goc_gia)
    for k, v in (("TEAMS_DELIVERY_MODE", "shared"), ("TEAMS_SHARED_WEBHOOK_URL", "https://shared.example.test/x"),
                 ("TEAMS_RECIPIENTS_FILE", str(goc_gia / "config" / "teams_recipients.local.json"))):
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(kiem, "_nap_env", lambda: None)
    import src.database as database
    monkeypatch.setattr(database, "load_config", lambda: {"report_recipients": [
        {"audience": "C-Level (Toàn quốc)", "region": None, "channel": None},
        {"audience": "Quản lý Miền Bắc", "region": "bac", "channel": None}]})

    assert kiem.main([]) == 0
    out = capsys.readouterr().out
    assert "cl***@example.test" in out and "clevel@example.test" not in out and "shared.example.test" not in out

    monkeypatch.setattr(database, "load_config", lambda: {"report_recipients": [
        {"audience": "Quản lý Miền Trung", "region": "trung", "channel": None}]})
    assert kiem.main([]) == 1
    assert "LOI CAU HINH" in capsys.readouterr().out


def test_script_kiem_in_du_nhieu_nguoi_da_che(goc_gia, monkeypatch, capsys):
    _shared(goc_gia)
    bang = goc_gia / "config" / "teams_recipients.local.json"
    bang.write_text(json.dumps({"C-Level (Toàn quốc)": ["an.a@x.test", "binh.b@x.test"]}, ensure_ascii=False),
                    encoding="utf-8")
    for k, v in (("TEAMS_DELIVERY_MODE", "shared"), ("TEAMS_SHARED_WEBHOOK_URL", "https://shared.example.test/x"),
                 ("TEAMS_RECIPIENTS_FILE", str(bang))):
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(kiem, "_nap_env", lambda: None)
    import src.database as database
    monkeypatch.setattr(database, "load_config", lambda: {"report_recipients": [
        {"audience": "C-Level (Toàn quốc)", "region": None, "channel": None}]})
    assert kiem.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("an***@x.test, bi***@x.test") == 2, "ca nhom C-Level lan watchdog (mac dinh = C-Level)"
    assert "an.a@" not in out and "binh.b@" not in out
