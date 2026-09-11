"""Khoa cac chot chan cua runner 138 cau de khong tao hang loat loi gia."""

import importlib.util
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "run_bo_138_cau.py"


def _load_runner(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-used")
    monkeypatch.setitem(sys.modules, "nl2sql", types.SimpleNamespace())
    spec = importlib.util.spec_from_file_location("run_bo_138_cau_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_het_credit_phai_dung_ngay(monkeypatch):
    runner = _load_runner(monkeypatch)

    marker = runner.loi_provider_can_dung(
        "BadRequestError: Your credit balance is too low to access the Anthropic API."
    )

    assert marker == "credit balance is too low"


def test_loi_nghiep_vu_mot_cau_khong_lam_dung_ca_vong(monkeypatch):
    runner = _load_runner(monkeypatch)

    assert runner.loi_provider_can_dung("OperationalError: no such column: x") is None


# ---------------- 11/09/2026: pham vi 126, tai khoan theo nhom, tran chi phi ----------------

def _args(**kw):
    base = dict(qlv_employee_code=None, qlv_v01_v32="MBKV2", qlv_v33_v40="TM25010183",
                qlv_area_code="MB", rd_area_code="MB")
    base.update(kw)
    return types.SimpleNamespace(**base)


def test_mac_dinh_chi_chay_126_cau_trong_pham_vi(monkeypatch):
    runner = _load_runner(monkeypatch)
    cases = runner.doc_bo_cau_hoi()
    chon = runner.chon_cau(cases)
    ma = {c["id"] for c in chon}
    assert len(cases) == 138 and len(chon) == 126
    assert not (ma & runner.NGOAI_PHAM_VI_126)
    theo_vai = {v: sum(1 for c in chon if c["role"] == v) for v in ("c_level", "regional_director", "qlv")}
    assert theo_vai == {"c_level": 46, "regional_director": 42, "qlv": 38}
    assert len(runner.chon_cau(cases, ca_138=True)) == 138


def test_only_cau_ngoai_pham_vi_bi_bo_va_canh_bao(monkeypatch, capsys):
    runner = _load_runner(monkeypatch)
    chon = runner.chon_cau(runner.doc_bo_cau_hoi(), only="C04,C05")
    assert [c["id"] for c in chon] == ["C05"]
    assert "C04" in capsys.readouterr().out


def test_gan_tai_khoan_theo_nhom(monkeypatch):
    runner = _load_runner(monkeypatch)
    vai = lambda ma: {"C": "c_level", "M": "regional_director", "V": "qlv"}[ma[0]]
    pv = lambda ma, **kw: runner.pham_vi_cho({"id": ma, "role": vai(ma)}, _args(**kw))
    assert pv("C05") == ("c_level", None, None)
    assert pv("M16") == ("regional_director", "MB", None)
    assert pv("V05") == ("qlv", "MB", "MBKV2")
    assert pv("V32") == ("qlv", "MB", "MBKV2")
    assert pv("V33") == ("qlv", "MB", "TM25010183")
    assert pv("V34", qlv_employee_code="XYZ") == ("qlv", "MB", "XYZ")


def _chuan_bi_main(monkeypatch, tmp_path, argv, chi_phi_moi_cau):
    runner = _load_runner(monkeypatch)
    goi = []

    def fake_ask(question, **kw):
        goi.append(kw["session_id"])
        return {"answer": "tra loi co so lieu"}

    runner.nl2sql = types.SimpleNamespace(ask=fake_ask)
    fake_helpers = types.SimpleNamespace(
        COST_LOG=None, AUDIT_LOG=None,
        _cost_by_session=lambda sids: {s: chi_phi_moi_cau for s in sids},
        _audit_by_session=lambda sids: {s: set() for s in sids},
    )
    monkeypatch.setattr(runner, "_load_eval_helpers", lambda: fake_helpers)
    monkeypatch.setattr(runner, "_kiem_api_key", lambda: True)
    monkeypatch.setitem(sys.modules, "cost_logger", types.SimpleNamespace(LOG_PATH=str(tmp_path / "c.jsonl")))
    monkeypatch.setitem(sys.modules, "query_engine", types.SimpleNamespace(LOG_PATH=str(tmp_path / "a.jsonl")))
    out = tmp_path / "kq.json"
    monkeypatch.setattr(sys, "argv", ["run_bo_138_cau.py", "--resume", str(out), "--delay", "0"] + argv)
    return runner, goi, out


def test_goi_model_that_ma_thieu_tran_thi_khong_goi_luot_nao(monkeypatch, tmp_path):
    runner, goi, _ = _chuan_bi_main(monkeypatch, tmp_path, ["--only", "C05,C06"], 0.1)
    assert runner.main() == 2
    assert goi == []


def test_goi_model_that_ma_thieu_nguoi_duyet_thi_khong_goi_luot_nao(monkeypatch, tmp_path):
    runner, goi, _ = _chuan_bi_main(monkeypatch, tmp_path, ["--only", "C05", "--tran-chi-usd", "5"], 0.1)
    assert runner.main() == 2
    assert goi == []


def test_chay_thu_khong_goi_model(monkeypatch, tmp_path):
    runner, goi, out = _chuan_bi_main(monkeypatch, tmp_path, ["--thu"], 0.1)
    assert runner.main() == 0
    assert goi == [] and not out.exists()


def test_cham_tran_thi_dung_truoc_cau_ke_tiep(monkeypatch, tmp_path):
    # Moi cau ton 0,30 USD, tran 0,50: cau 1 chay (0,30), cau 2 du kien 0,30 -> 0,60 > 0,50 -> dung.
    runner, goi, out = _chuan_bi_main(
        monkeypatch, tmp_path,
        ["--only", "C05,C06,C07", "--tran-chi-usd", "0.5", "--nguoi-duyet", "Dang",
         "--uoc-tinh-usd-moi-cau", "0.3"], 0.30)
    assert runner.main() == 6
    assert len(goi) == 1
    luu = json.loads(out.read_text(encoding="utf-8"))
    assert [r["id"] for r in luu] == ["C05"] and luu[0]["cost_usd"] == 0.3
    meta = json.loads(out.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["nguoi_duyet"] == "Dang" and meta["tran_chi_usd"] == 0.5


def test_khong_do_duoc_chi_phi_thi_dung_khong_chay_mu(monkeypatch, tmp_path):
    runner, goi, _ = _chuan_bi_main(
        monkeypatch, tmp_path,
        ["--only", "C05,C06", "--tran-chi-usd", "5", "--nguoi-duyet", "Dang"], 0.0)
    assert runner.main() == 5
    assert len(goi) == 1
