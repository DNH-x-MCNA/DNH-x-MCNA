# -*- coding: utf-8 -*-
"""Chan moi ket noi THAT ra ngoai khi chay test: SQL Server (Bravo), SMTP, HTTP, API model.

29/09/2026: chay pytest tren may dev trong luc thu muc co file .env that (Bravo, SMTP, khoa API model). Nhieu module
tu nap .env ngay khi import (sync_warehouse, notifier, backend/main.py), nen 15 lan goi search_sql_catalog trong
test da QUET TOAN BO metadata Bravo tren may 26 (may chua DB) - trung dot may 26 len 94% CPU luc 10:34. Test phai
chay duoc khong can mang (CI khong co .env van xanh). Test nao that su can ket noi thi danh dau
@pytest.mark.integration (mac dinh bi loai qua addopts trong pyproject.toml) - lop chan nay bo qua cac test do.

Chan o hai tang:
- pyodbc.connect / psycopg2.connect: hai driver viet bang C, khong di qua socket cua Python (Bravo dung pyodbc).
- socket.connect toi dia chi khong phai loopback: bao SMTP, requests, httpx (SDK anthropic/openai goi model).
Loi nem ra la ConnectionRefusedError de code dang xu ly "mat ket noi" (OSError/Exception) chay dung nhanh ngoai tuyen.
"""
import ipaddress
import socket

import pytest

_BI_CHAN = []


class KetNoiThatBiChan(ConnectionRefusedError):
    """Test vua co ket noi that ra ngoai - da chan."""


def _la_loopback(dia_chi) -> bool:
    host = dia_chi[0] if isinstance(dia_chi, tuple) and dia_chi else dia_chi
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    host = str(host or "")
    if host in ("localhost", "testserver", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _chan_ket_noi_that(request, monkeypatch):
    if request.node.get_closest_marker("integration"):
        yield
        return

    def chan(loai):
        def _ham(*args, **kwargs):
            _BI_CHAN.append((request.node.nodeid, loai))
            raise KetNoiThatBiChan(
                f"[tests/conftest.py] Test khong duoc {loai} that. Gia lap ham goi, hoac danh dau "
                "@pytest.mark.integration neu that su can.")
        return _ham

    for ten_module, ham in (("pyodbc", "connect"), ("psycopg2", "connect")):
        try:
            module = __import__(ten_module)
        except ImportError:
            continue
        monkeypatch.setattr(module, ham, chan(f"ket noi CSDL qua {ten_module}"))

    goc_connect, goc_connect_ex = socket.socket.connect, socket.socket.connect_ex
    bao_chan = chan("mo ket noi mang ra ngoai")

    def connect(self, dia_chi):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _la_loopback(dia_chi):
            bao_chan()
        return goc_connect(self, dia_chi)

    def connect_ex(self, dia_chi):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not _la_loopback(dia_chi):
            bao_chan()
        return goc_connect_ex(self, dia_chi)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    yield


def pytest_terminal_summary(terminalreporter):
    if _BI_CHAN:
        test_bi_chan = sorted({nodeid for nodeid, _ in _BI_CHAN})
        terminalreporter.write_line(
            f"[tests/conftest.py] Da chan {len(_BI_CHAN)} lan ket noi that ra ngoai tu {len(test_bi_chan)} test "
            "(test van chay ngoai tuyen). Nen gia lap ham goi trong cac test nay:", yellow=True)
        for nodeid in test_bi_chan[:15]:
            terminalreporter.write_line(f"  - {nodeid}", yellow=True)
