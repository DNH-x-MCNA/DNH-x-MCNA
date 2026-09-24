"""scripts/cham_lai_uat.py: dung truoc khi ton tien neu khong ket noi duoc model; cau noi tiep hoi cau truoc.

24/09/2026: cua so PowerShell tren may 24 con sot LLM_BASE_URL=http://127.0.0.1:9 -> 18/18 luot
APIConnectionError. Va muc 06/08 la cau noi tiep ("bo sung ... tu ket qua tren") nen chay don thi chatbot hoi
lai - khong cham duoc."""
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

GOC = Path(__file__).resolve().parents[1]
if str(GOC / "backend") not in sys.path:
    sys.path.insert(0, str(GOC / "backend"))

import conversation_memory as memory  # noqa: E402

_spec = importlib.util.spec_from_file_location("cham_lai_uat_test", GOC / "scripts" / "cham_lai_uat.py")
cl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)


class _Loi(Exception):
    pass


def _nl2sql(base="", anthropic=True, models_loi=None):
    def models_list(limit=1):
        if models_loi:
            raise models_loi
        return SimpleNamespace(data=[SimpleNamespace(id="m")])
    return SimpleNamespace(LLM_BASE_URL=base, IS_ANTHROPIC=anthropic,
                           _llm_client=lambda: SimpleNamespace(models=SimpleNamespace(list=models_list)))


def test_cong_tac_chan_127_0_0_1_bi_bat_truoc_khi_goi_mang():
    loi = cl._kiem_ket_noi_model(_nl2sql(base="http://127.0.0.1:9", anthropic=False))
    assert loi and "127.0.0.1:9" in loi and "cua so moi" in loi


def test_models_list_loi_thi_tra_ca_loi_goc():
    goc = ConnectionRefusedError("[WinError 10061] refused")
    try:
        raise _Loi("Connection error.") from goc
    except _Loi as e:
        loi = cl._kiem_ket_noi_model(_nl2sql(models_loi=e))
    assert "Connection error." in loi and "WinError 10061" in loi


def test_ket_noi_duoc_thi_khong_chan():
    assert cl._kiem_ket_noi_model(_nl2sql()) is None


def test_hoi_ghi_dung_query_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "DB_PATH", str(tmp_path / "memory.db"))
    memory.init()
    goi = []
    fake = SimpleNamespace(ask=lambda q, **k: goi.append((q, k["session_id"])) or {"answer": "ok " + q})
    tra_loi, loi, _, _ = cl._hoi(fake, "cau A", "chamlai-x", {"username": "u1", "role": "c_level"},
                                 (None, None, None))
    assert (tra_loi, loi) == ("ok cau A", None) and goi == [("cau A", "chamlai-x")]
    st = sqlite3.connect(memory.DB_PATH).execute("SELECT status, username FROM query_runs").fetchall()
    assert st == [("completed", "u1")]


def test_danh_sach_co_cau_truoc_cho_06_va_08():
    muc = {m["ma"]: m for m in json.load(open(GOC / "scripts" / "cham_lai_20_luot.json", encoding="utf-8"))["muc"]}
    assert muc["06"]["cau_truoc"].startswith("Doanh so thuc hien kenh MT")
    assert muc["08"]["cau_truoc"] == muc["07"]["cau_hoi"]
