# -*- coding: utf-8 -*-
"""02/10/2026 - web chatbot chay THANG tren may 24 (deploy/may24_truc_tiep/): DNS -> NAT 443 -> Caddy -> Next.js.

May 24 la may dang giu kho du lieu va tai khoan doc Bravo, nen khoa cac dieu kien ma sai mot cai la ho:
- Caddy GHI DE X-Real-IP/X-Forwarded-For (web lay IP tu do de chong do mat khau) cho MOI duong vao web;
- chi mo 443, khong nghe cong 80, khong mo cong quan tri; web chi nghe 127.0.0.1;
- stream chat khong bi gom; tuong lua dong 3000/8010 tu ngoai may; script mac dinh chi kiem;
- dich vu khong chay bang SYSTEM; mau khong chua khoa that; file .ps1 thuan ASCII va dung cu phap.
Chi doc file (+ nho PowerShell phan tich cu phap), khong chay Caddy/NSSM, khong doi gi tren may."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TT = ROOT / "deploy" / "may24_truc_tiep"
PS1 = ["deploy_web.ps1", "cai_dat_lan_dau.ps1", "tuong_lua_truc_tiep.ps1"]


def _doc(path):
    return path.read_text(encoding="utf-8")


def _caddy():
    """Caddyfile bo comment (dong bat dau bang #)."""
    return "\n".join(d for d in _doc(TT / "Caddyfile").splitlines() if not d.lstrip().startswith("#"))


def _khoi(text, mo_dau):
    """Noi dung khoi { } dau tien co dong mo dau khop `mo_dau` (dem ngoac long nhau)."""
    m = re.search(mo_dau + r"\s*\{", text)
    assert m, mo_dau
    sau, i, d = m.end(), m.end(), 1
    while d:
        d += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[sau:i - 1]


def test_caddy_ghi_de_header_ip_cho_moi_duong_vao_web():
    text = _caddy()
    chung = _khoi(text, r"\(proxy_web\)")
    assert re.search(r"header_up\s+X-Real-IP\s+\{remote_host\}", chung)
    assert re.search(r"header_up\s+X-Forwarded-For\s+\{remote_host\}", chung)
    # Moi reverse_proxy deu phai nhap doan chung do va chi tro vao web tren loopback.
    cac_proxy = re.findall(r"reverse_proxy\s+(\S+)\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", text)
    assert len(cac_proxy) == 2
    for dich, than in cac_proxy:
        assert dich == "127.0.0.1:3000" and "import proxy_web" in than
    # Web doc dung hai header do, x-real-ip truoc.
    proxy = _doc(ROOT / "src" / "app" / "api" / "_proxy.ts")
    assert re.search(r'headers\.get\("x-real-ip"\)\s*\|\|\s*request\.headers\.get\("x-forwarded-for"\)', proxy)


def test_caddy_chi_443_khong_cong_80_khong_cong_quan_tri():
    text = _caddy()
    toan_cuc = text[text.index("{") + 1:text.index("(proxy_web)")]
    assert re.search(r"auto_https\s+disable_redirects", toan_cuc)         # khong mo cong 80 de chuyen huong
    assert re.search(r"admin\s+off", toan_cuc)
    assert re.search(r"protocols\s+h1\s+h2\s*$", toan_cuc, re.M)          # NAT chi TCP: khong quang cao HTTP/3
    assert re.search(r"storage\s+file_system\s+C:/dnh_web/caddy_data", toan_cuc)
    tls = _khoi(text, r"issuer\s+acme")
    assert "disable_http_challenge" in tls                                 # lay chung chi qua 443 (TLS-ALPN-01)
    assert "{$DNH_ACME_CA:https://acme-v02.api.letsencrypt.org/directory}" in tls
    # Chi MOT site, ten lay tu bien moi truong, mac dinh la ten that; khong co site ":80" hay "http://".
    assert "{$DNH_WEB_HOST:chatbot.namhatrading.com} {" in text
    assert not re.search(r"^\s*(:80|http://)", text, re.M)


def test_caddy_stream_khong_gom_va_du_thoi_gian():
    text = _caddy()
    stream = _khoi(text, r"handle\s+@stream")
    assert re.search(r"@stream\s+path\s+/api/chat/stream", text) and re.search(r"flush_interval\s+-1", stream)
    assert re.search(r"response_header_timeout\s+300s", _khoi(text, r"\(proxy_web\)"))
    assert "encode" not in text                                            # khong nen lai: gom manh stream
    assert re.search(r'Strict-Transport-Security\s+"max-age=31536000"', text) and "includeSubDomains" not in text
    route = _doc(ROOT / "src" / "app" / "api" / "chat" / "stream" / "route.ts")
    assert '"X-Accel-Buffering": "no"' in route and "no-transform" in route


def test_web_chi_nghe_localhost_va_dich_vu_khong_chay_system():
    text = _doc(TT / "cai_dat_lan_dau.ps1")
    assert "next start --hostname 127.0.0.1 --port 3000" in text
    assert "0.0.0.0" not in text
    assert "NT AUTHORITY\\LocalService" in text
    # Thu muc chua khoa backend + khoa rieng chung chi: bo ke thua, LOCAL SERVICE chi doc o goc.
    assert "/inheritance:r" in text and "'LOCAL SERVICE:(OI)(CI)RX'" in text
    assert "DNH_ACME_CA=$ACME_THU" in text and "acme-staging-v02" in text   # chay thu dung chung chi staging


def test_kiem_caddyfile_khong_chet_vi_stderr_va_chi_tra_dung_sai():
    """02/10/2026, lan dau chay tren may 24: Caddy ghi nhat ky ra stderr, PS 5.1 + ErrorActionPreference=Stop bien
    dong do thanh loi dung script truoc khi co ket qua. Va ham tung tra kem cac dong chu nen `if` luon dung."""
    text = _doc(TT / "cai_dat_lan_dau.ps1")
    ham = text.split("function Test-Caddyfile {", 1)[1].split("function Show-TrangThai", 1)[0]
    assert ham.index("$ErrorActionPreference = 'Continue'") < ham.index("& $Caddy validate")
    assert "$ma = $LASTEXITCODE" in ham and "return ($ma -eq 0)" in ham
    assert "Write-Host" in ham and 'ForEach-Object { "   $_" }' not in ham      # khong tha chuoi vao gia tri tra ve
    assert ham.count("$ErrorActionPreference = $uuTienCu") == 2                  # tra lai ca khi loi


def test_tuong_lua_cho_443_cho_caddy_va_dong_3000_8010():
    text = _doc(TT / "tuong_lua_truc_tiep.ps1")
    assert re.search(r"-Action Allow -Protocol TCP -LocalPort 443 -Program \$Caddy", text)
    assert re.search(r"-Action Block -Protocol TCP -LocalPort \$CONG_DONG", text)
    assert "$CONG_DONG = @('3000', '8010')" in text


@pytest.mark.parametrize("script", ["cai_dat_lan_dau.ps1", "tuong_lua_truc_tiep.ps1"])
def test_script_mac_dinh_chi_kiem(script):
    text = _doc(TT / script)
    assert "[switch]$ApDung" in text
    # Phan chay khi KHONG co -ApDung/-GoBo: chi in trang thai roi return.
    mac_dinh = text.split("if (-not $ApDung) {", 1)[1].split("\n}\n", 1)[0]
    assert "Show-TrangThai" in mac_dinh and "return" in mac_dinh
    for lenh in ("New-NetFirewallRule", "Remove-NetFirewallRule", "$Nssm", "icacls", "Start-Service", "sc.exe"):
        assert lenh not in mac_dinh, lenh
    # Moi thao tac doi he thong deu nam SAU doan mac dinh hoac trong nhanh -GoBo, va deu doi quyen admin.
    assert text.count("Assert-Admin") >= 3


def test_deploy_build_rieng_va_tu_quay_ve():
    text = _doc(TT / "deploy_web.ps1")
    assert ".build-ok" in text and "mklink /J" in text and "[switch]$QuayLai" in text
    assert "--max-old-space-size=1536" in text                 # may 24 chi con trong ~2,8 GB RAM
    assert "'17:15'" in text and "'18:15'" in text             # khong build luc bao cao 17:45
    assert "git -C $Repo archive" in text                      # chi file da commit, khong keo .env/kho du lieu
    assert "DAN_KHOA_TU_BACKEND_ENV" in text                   # tu choi chay khi web.env con khoa mau
    # Khoa chi duoc chep vao ban build SAU khi build xong.
    assert "'.env.production.local'" in text
    assert text.index("& $npm run build") < text.index("Copy-Item -LiteralPath $ENV_FILE")
    loi = text.split("if (-not (Test-WebLen)) {", 1)[1].split("Log \"DAT: web chay ban", 1)[0]
    assert "Set-BanChay $truoc" in loi


def test_mau_khong_chua_khoa_that():
    mau = _doc(TT / "web.env.mau")
    assert re.search(r"^BACKEND_API_KEY=DAN_KHOA_TU_BACKEND_ENV_VAO_DAY$", mau, re.M)
    assert re.search(r"^BACKEND_API_URL=http://127\.0\.0\.1:8010$", mau, re.M)
    for path in TT.rglob("*"):
        if path.is_file():
            assert not re.search(r"(sk-ant-|sig=[A-Za-z0-9_%-]{20,}|PRIVATE KEY)", _doc(path)), path


def test_ps1_thuan_ascii():
    for script in PS1:
        assert _doc(TT / script).isascii(), script              # PS 5.1 doc file khong BOM theo codepage


@pytest.mark.skipif(shutil.which("powershell") is None, reason="khong co Windows PowerShell")
@pytest.mark.parametrize("script", PS1)
def test_ps1_dung_cu_phap(script):
    lenh = ("$loi = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{TT / script}', [ref]$null, [ref]$loi); $loi | ForEach-Object {{ $_.ToString() }}; exit $loi.Count")
    kq = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", lenh],
                        capture_output=True, text=True)
    assert kq.returncode == 0, (kq.stdout, kq.stderr)
