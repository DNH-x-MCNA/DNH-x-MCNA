# -*- coding: utf-8 -*-
"""30/09/2026 - web chatbot chuyen tu Vercel sang Cloud Server Mat Bao (deploy/cloud_server/).

Khoa cac dieu kien ma sai mot cai la hong hoac ho, nhung khong ai thay cho toi khi co su co:
- Nginx GHI DE X-Real-IP/X-Forwarded-For (web lay IP tu do de chong do mat khau);
- stream chat khong bi buffer/nen; web chi nghe 127.0.0.1; backend chi qua duong ham;
- dia chi duong ham khop nhau o moi file; mau khong chua khoa that; file chay tren Linux dung LF.
Chi doc file, khong chay nginx/systemd/WireGuard."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CS = ROOT / "deploy" / "cloud_server"
NGINX = CS / "nginx" / "chatbot.namhatrading.com.conf"
SERVICE = CS / "systemd" / "dnh-web.service"
DOMAIN = "chatbot.namhatrading.com"
IP_CLOUD, IP_MAY24 = "10.88.24.1", "10.88.24.2"


def _doc(path):
    return path.read_text(encoding="utf-8")


def _khong_comment(text):
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def _server_https():
    text = _khong_comment(_doc(NGINX))
    khoi = [k for k in re.split(r"\bserver\s*\{", text) if f"server_name {DOMAIN};" in k and "ssl_certificate" in k]
    assert len(khoi) == 1
    return khoi[0]


def _location(khoi, mau):
    m = re.search(r"location\s+" + mau + r"\s*\{(.*?)\}", khoi, re.S)
    assert m, mau
    return m.group(1)


def test_nginx_ghi_de_header_ip_ma_web_dung_de_chong_do_mat_khau():
    khoi = _server_https()
    assert re.search(r"proxy_set_header\s+X-Real-IP\s+\$remote_addr;", khoi)
    assert re.search(r"proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;", khoi)
    assert "$proxy_add_x_forwarded_for" not in khoi      # noi them = nguoi dung tu dat IP gia
    # Web doc dung hai header do, x-real-ip truoc.
    proxy = _doc(ROOT / "src" / "app" / "api" / "_proxy.ts")
    assert re.search(r'headers\.get\("x-real-ip"\)\s*\|\|\s*request\.headers\.get\("x-forwarded-for"\)', proxy)
    # proxy_set_header trong location se xoa toan bo header cap server -> location khong duoc tu dat.
    for mau in (r"=\s*/api/chat/stream", r"/"):
        assert "proxy_set_header" not in _location(khoi, mau)


def test_nginx_stream_khong_buffer_va_du_thoi_gian():
    khoi = _server_https()
    stream = _location(khoi, r"=\s*/api/chat/stream")
    assert "proxy_buffering off;" in stream and "gzip off;" in stream
    for loc in (stream, _location(khoi, r"/")):
        assert int(re.search(r"proxy_read_timeout\s+(\d+)s;", loc).group(1)) >= 300
        assert re.search(r"proxy_pass\s+http://127\.0\.0\.1:3000;", loc)
    # add_header trong location lam mat HSTS cap server.
    assert "add_header" not in stream and "add_header" not in _location(khoi, r"/")
    assert re.search(r'add_header\s+Strict-Transport-Security\s+"max-age=\d+"\s+always;', khoi)
    assert "includeSubDomains" not in khoi


def test_nginx_tu_choi_ip_tran_va_ten_mien_khac():
    text = _khong_comment(_doc(NGINX))
    assert re.search(r"listen 443 ssl default_server;.*?ssl_reject_handshake on;", text, re.S)
    assert re.search(r"listen 80 default_server;.*?return 444;", text, re.S)
    assert re.findall(r"server_name\s+([^;]+);", text) == ["_", "_", DOMAIN, DOMAIN]


def test_route_stream_tat_nen_cua_next_va_buffer_cua_nginx():
    route = _doc(ROOT / "src" / "app" / "api" / "chat" / "stream" / "route.ts")
    assert '"Cache-Control": "no-cache, no-transform"' in route
    assert '"X-Accel-Buffering": "no"' in route


def test_service_web_chi_nghe_localhost_va_khong_chay_root():
    text = _doc(SERVICE)
    assert "--hostname 127.0.0.1 --port 3000" in text
    assert re.search(r"^User=dnhweb$", text, re.M) and "EnvironmentFile=/etc/dnh-web/web.env" in text
    for dong in ("NoNewPrivileges=true", "ProtectSystem=strict", "ReadWritePaths=/opt/dnh-web/releases"):
        assert dong in text


def test_dia_chi_duong_ham_khop_o_moi_file():
    env = _doc(CS / "web.env.mau")
    assert re.search(rf"^BACKEND_API_URL=http://{re.escape(IP_MAY24)}:8010$", env, re.M)
    vps = _doc(CS / "wireguard" / "wg0.conf.mau")
    assert f"Address = {IP_CLOUD}/30" in vps and f"AllowedIPs = {IP_MAY24}/32" in vps
    may24 = _doc(CS / "wireguard" / "may24.conf.mau")
    assert f"Address = {IP_MAY24}/32" in may24
    # May 24 CHI dinh tuyen dia chi Cloud Server qua duong ham, khong doi tuyen/DNS khac.
    assert re.findall(r"^AllowedIPs = (.+)$", may24, re.M) == [f"{IP_CLOUD}/32"]
    assert not re.search(r"^DNS\s*=", may24, re.M)
    tuong_lua = _doc(ROOT / "backend" / "server_deploy" / "tuong_lua_8010.ps1")
    assert f"[string]$IpCloudServer = '{IP_CLOUD}'" in tuong_lua
    assert f"'{IP_MAY24}'" in tuong_lua
    assert f"MAY24_IP={IP_MAY24}" in _doc(CS / "cai_wireguard.sh")


def test_mau_khong_chua_khoa_that():
    khoa_wg = re.compile(r"[A-Za-z0-9+/]{42}[AEIMQUYcgkosw048]=")
    for path in CS.rglob("*"):
        if path.is_file():
            assert not khoa_wg.search(_doc(path)), path
    assert not re.search(r"^\s*PrivateKey\s*=", _doc(CS / "wireguard" / "wg0.conf.mau"), re.M)
    assert re.search(r"^BACKEND_API_KEY=DAN_KHOA_TU_MAY_24_VAO_DAY$", _doc(CS / "web.env.mau"), re.M)
    # deploy_web.sh tu choi chay khi web.env con khoa mau.
    assert "DAN_KHOA_TU_MAY_24" in _doc(CS / "deploy_web.sh")


def test_tuong_lua_may24_mac_dinh_chi_kiem():
    text = _doc(ROOT / "backend" / "server_deploy" / "tuong_lua_8010.ps1")
    assert "[switch]$ApDung" in text
    # Chi tao/xoa rule trong nhanh -ApDung / -GoBo; cuoi file (mac dinh) chi goi Show-TrangThai.
    mac_dinh = text.rsplit("if ($ApDung) {", 1)[1].split("\n}\n", 1)[1]
    assert "New-NetFirewallRule" not in mac_dinh and "Remove-NetFirewallRule" not in mac_dinh
    assert "Show-TrangThai" in mac_dinh
    assert text.isascii()                                   # PS 5.1 doc file khong BOM theo codepage


@pytest.mark.parametrize("script", ["deploy_web.sh", "cai_dat_lan_dau.sh", "cai_wireguard.sh"])
def test_script_bash_an_toan_khi_bi_doi_giua_chung(script):
    text = _doc(CS / script)
    assert "set -euo pipefail" in text
    assert text.rstrip().endswith('main "$@"; exit')         # bash doc tron dong cuoi truoc khi chay


def test_deploy_build_rieng_va_tu_quay_ve_khi_web_moi_khong_len():
    text = _doc(CS / "deploy_web.sh")
    assert "npm ci" in text and "npm run build" in text and "npm install" not in text
    assert 'switch_to "$prev"' in text                      # web moi khong len -> ve ban cu
    assert "--rollback" in text and "flock -n 9" in text


def test_file_chay_tren_linux_dung_lf():
    for path in CS.rglob("*"):
        if path.is_file():
            assert b"\r" not in path.read_bytes(), path


@pytest.mark.skipif(shutil.which("bash") is None, reason="khong co bash")
@pytest.mark.parametrize("script", ["deploy_web.sh", "cai_dat_lan_dau.sh", "cai_wireguard.sh"])
def test_script_bash_dung_cu_phap(script):
    kq = subprocess.run(["bash", "-n", str(CS / script)], capture_output=True, text=True)
    assert kq.returncode == 0, kq.stderr
