# -*- coding: utf-8 -*-
"""29/09/2026 - ra soat bao mat: khoa API so sanh thoi gian hang, tat trang tai lieu API tren tunnel,
va khong tra nguyen van exception (IP may chu, duong dan, cau SQL) cho nguoi dung cuoi.
Khong goi model, khong cham Bravo: ask() bi thay bang ham gia nem loi."""
import importlib.util
import json
import os
import sys

import pytest

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.append(BACKEND)

import auth
import conversation_memory as cm

LOI_NOI_BO = ("[Microsoft][ODBC Driver 17 for SQL Server]TCP Provider: 172.16.0.26,1433 "
              "C:\\dnh_chatbot\\backend\\query_engine.py SELECT Amount9 FROM dbo.vHoaDonTotal")


def _nap_main(tmp_path, monkeypatch, ten, **env):
    monkeypatch.setattr(auth, "DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setattr(cm, "DB_PATH", str(tmp_path / "memory.db"))
    for key in ("BACKEND_API_KEY", "DNH_BAT_API_DOCS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    cm.init()
    spec = importlib.util.spec_from_file_location(ten, os.path.join(BACKEND, "main.py"))
    chatbot_main = importlib.util.module_from_spec(spec)
    sys.modules[ten] = chatbot_main
    spec.loader.exec_module(chatbot_main)
    # main.py nap .env cua may dev luc import: ghi de lai gia tri test sau khi nap.
    monkeypatch.setattr(chatbot_main, "API_KEY", env.get("BACKEND_API_KEY", ""))
    return chatbot_main


def test_khoa_api_dung_moi_qua(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "cung_co_khoa", BACKEND_API_KEY="khoa-that-dai-32-ky-tu")

    chatbot_main.require_api_key("khoa-that-dai-32-ky-tu")
    for sai in ("khoa-that-dai-32-ky-tuX", "khoa", "", None):
        with pytest.raises(chatbot_main.HTTPException) as loi:
            chatbot_main.require_api_key(sai)
        assert loi.value.status_code == 401


def test_trang_tai_lieu_api_tat_mac_dinh_va_bat_duoc_tren_may_dev(tmp_path, monkeypatch):
    tat = _nap_main(tmp_path, monkeypatch, "cung_co_docs_tat")
    assert (tat.app.docs_url, tat.app.redoc_url, tat.app.openapi_url) == (None, None, None)
    duong_dan = {getattr(r, "path", "") for r in tat.app.routes}
    assert not duong_dan & {"/docs", "/redoc", "/openapi.json"}

    bat = _nap_main(tmp_path, monkeypatch, "cung_co_docs_bat", DNH_BAT_API_DOCS="1")
    assert bat.app.openapi_url == "/openapi.json"


def _nguoi_hoi():
    return {"id": 1, "username": "ceo", "name": "CEO", "role": "c_level", "scope_value": None,
            "employee_code": None, "scope_channel": None, "status": "approved", "is_active": 1,
            "must_change_password": 0}


def _loi_da_ghi(query_id):
    return cm.get_query_run(query_id)["error_message"]


def test_chat_loi_he_thong_khong_tra_nguyen_van_exception(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "cung_co_chat_loi")

    def ask_gia(*args, **kwargs):
        raise RuntimeError(LOI_NOI_BO)

    monkeypatch.setattr(chatbot_main, "ask", ask_gia)
    with pytest.raises(chatbot_main.HTTPException) as loi:
        chatbot_main.chat(chatbot_main.ChatRequest(question="Doanh thu?", session_id="s-loi"), _nguoi_hoi())

    assert loi.value.status_code == 500
    assert "172.16.0.26" not in loi.value.detail and "SELECT" not in loi.value.detail
    query_id = cm.list_query_runs(limit=5)[0]["query_id"]
    assert query_id in loi.value.detail                  # nguoi dung co ma tra cuu de bao admin
    assert LOI_NOI_BO in _loi_da_ghi(query_id)           # chi tiet van con cho admin doi chieu


def test_chat_stream_loi_he_thong_khong_tra_nguyen_van_exception(tmp_path, monkeypatch):
    chatbot_main = _nap_main(tmp_path, monkeypatch, "cung_co_stream_loi")

    def ask_stream_gia(*args, **kwargs):
        yield {"type": "status", "message": "Dang doc du lieu"}
        raise RuntimeError(LOI_NOI_BO)

    monkeypatch.setattr(chatbot_main, "ask_stream", ask_stream_gia)
    response = chatbot_main.chat_stream(
        chatbot_main.ChatRequest(question="Doanh thu?", session_id="s-stream"), _nguoi_hoi())

    async def _doc_het():
        return [chunk async for chunk in response.body_iterator]

    import asyncio
    events = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in asyncio.run(_doc_het())]
    loi = events[-1]
    assert loi["type"] == "error"
    assert "172.16.0.26" not in loi["message"] and "query_engine.py" not in loi["message"]
    assert loi["query_id"] in loi["message"]
    assert LOI_NOI_BO in _loi_da_ghi(loi["query_id"])
