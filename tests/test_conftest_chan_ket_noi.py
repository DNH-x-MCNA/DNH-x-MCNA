# -*- coding: utf-8 -*-
"""Khoa lop chan ket noi that trong tests/conftest.py (29/09/2026: test tung quet metadata Bravo tren may 26)."""
import socket

import pytest

from conftest import KetNoiThatBiChan


def test_chan_ket_noi_sql_server_qua_pyodbc():
    pyodbc = pytest.importorskip("pyodbc")
    with pytest.raises(KetNoiThatBiChan):
        pyodbc.connect("DRIVER={SQL Server};SERVER=172.16.0.26;DATABASE=x;UID=x;PWD=x")


def test_chan_socket_ra_ngoai_nhung_cho_phep_loopback():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        with pytest.raises(KetNoiThatBiChan):
            s.connect(("172.16.0.26", 1433))

    may_chu = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    may_chu.bind(("127.0.0.1", 0))
    may_chu.listen(1)
    try:
        with socket.create_connection(may_chu.getsockname(), timeout=2):
            pass
    finally:
        may_chu.close()


def test_loi_bi_chan_la_loi_mat_ket_noi_de_code_chay_nhanh_ngoai_tuyen():
    assert issubclass(KetNoiThatBiChan, ConnectionRefusedError) and issubclass(KetNoiThatBiChan, OSError)
