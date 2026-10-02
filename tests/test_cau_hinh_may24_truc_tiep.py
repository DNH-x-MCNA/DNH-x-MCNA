# -*- coding: utf-8 -*-
"""02/10/2026 - web chatbot chay THANG tren may 24 (deploy/may24_truc_tiep/): DNS -> NAT 443 -> Caddy -> Next.js.

May 24 la may dang giu kho du lieu va tai khoan doc Bravo, nen khoa cac dieu kien ma sai mot cai la ho:
- Caddy GHI DE X-Real-IP/X-Forwarded-For (web lay IP tu do de chong do mat khau) cho MOI duong vao web;
- chi mo 443, khong nghe cong 80, khong mo cong quan tri; web chi nghe 127.0.0.1;
- stream chat khong bi gom; tuong lua dong 3000/8010 tu ngoai may; script mac dinh chi kiem;
- dich vu khong chay bang SYSTEM, va tai khoan chay web khong doc/ghi duoc phan con lai cua C:\\dnh_chatbot;
- mau khong chua khoa that; file .ps1 thuan ASCII va dung cu phap.
Phan lon chi doc file (+ nho PowerShell phan tich cu phap). Hai test co chay lenh that nhung khong doi gi tren may:
sc.exe voi mot ten dich vu KHONG ton tai, va icacls tren thu muc tam cua pytest. Khong chay Caddy/NSSM."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TT = ROOT / "deploy" / "may24_truc_tiep"
PS1 = ["deploy_web.ps1", "cai_dat_lan_dau.ps1", "tuong_lua_truc_tiep.ps1", "khoa_quyen_truc_tiep.ps1"]
CO_POWERSHELL = shutil.which("powershell") is not None


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


def _powershell(lenh, **kw):
    # CI chay pytest tu PowerShell 7: bien PSModulePath cua no tro vao module ban 7, Windows PowerShell 5.1 ke thua
    # bien do thi khong nap duoc Microsoft.PowerShell.Security (Get-Acl). Bo bien de 5.1 dung duong dan mac dinh.
    moi_truong = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"] + lenh,
                          capture_output=True, text=True, env=moi_truong, **kw)


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
    # -ChayThu: cung ten mien, chi doi sang chung chi staging.
    assert "if ($ChayThu) { $ca = $ACME_THU }" in text and "acme-staging-v02" in text
    assert '"DNH_WEB_HOST=$(Get-TenMienDung)", "DNH_ACME_CA=$ca"' in text
    assert "[string]$TenMienThu = ''" in text and "uat-chatbot" not in text


def test_kiem_caddyfile_khong_chet_vi_stderr_va_chi_tra_dung_sai():
    """02/10/2026, lan dau chay tren may 24: Caddy ghi nhat ky ra stderr, PS 5.1 + ErrorActionPreference=Stop bien
    dong do thanh loi dung script truoc khi co ket qua. Va ham tung tra kem cac dong chu nen `if` luon dung."""
    text = _doc(TT / "cai_dat_lan_dau.ps1")
    ham = text.split("function Test-Caddyfile {", 1)[1].split("\n}\n", 1)[0]
    assert ham.index("$ErrorActionPreference = 'Continue'") < ham.index("& $Caddy validate")
    assert "$ma = $LASTEXITCODE" in ham and "return ($ma -eq 0)" in ham
    assert "Write-Host" in ham and 'ForEach-Object { "   $_" }' not in ham      # khong tha chuoi vao gia tri tra ve
    assert ham.count("$ErrorActionPreference = $uuTienCu") == 2                  # tra lai ca khi loi


def _tham_so_sc():
    """Danh sach tham so ma cai_dat_lan_dau.ps1 truyen cho sc.exe (nguyen van trong script)."""
    text = _doc(TT / "cai_dat_lan_dau.ps1")
    m = re.search(r"\$sc = Start-Process -FilePath sc\.exe -Wait -NoNewWindow -PassThru -ArgumentList `\r?\n\s*(.+)", text)
    assert m, "khong thay lenh doi tai khoan dich vu"
    return text, m.group(1).strip()


def test_doi_tai_khoan_dich_vu_giu_tham_so_mat_khau_rong():
    """02/10/2026, thu tren may dev truoc khi -ApDung lan dau: `& sc.exe config X obj= '...' password= ''` trong
    PS 5.1 BO MAT tham so rong, sc.exe in huong dan va thoat 1639 -> script dung ngay o dich vu dau tien, web khong
    len. Phai truyen qua Start-Process voi cap password= "" va kiem lai tai khoan sau khi doi."""
    text, tham_so = _tham_so_sc()
    assert tham_so == """'config', $ten, 'obj=', '"NT AUTHORITY\\LocalService"', 'password=', '""'"""
    lenh = "\n".join(d for d in text.splitlines() if not d.lstrip().startswith("#"))
    assert "& sc.exe" not in lenh
    assert "$chayBang -notmatch 'Local\\s?Service'" in text and "$sc.ExitCode -ne 0" in text


@pytest.mark.skipif(not CO_POWERSHELL, reason="khong co Windows PowerShell")
def test_sc_exe_nhan_dung_dang_tham_so_cua_script():
    """Chay dung dang tham so do voi mot dich vu KHONG ton tai: 1060 (khong co dich vu) = sc.exe da hieu tham so;
    1639 = sai cu phap dong lenh (dang cu). Khong doi gi tren may."""
    _, tham_so = _tham_so_sc()
    moi = ("$ten = 'DNH_Khong_Ton_Tai_Kiem_Thu'; $p = Start-Process -FilePath sc.exe -Wait -NoNewWindow -PassThru "
           f"-ArgumentList {tham_so}; exit $p.ExitCode")
    cu = "& sc.exe config DNH_Khong_Ton_Tai_Kiem_Thu obj= 'NT AUTHORITY\\LocalService' password= ''; exit $LASTEXITCODE"
    assert _powershell(["-Command", moi]).returncode == 1060
    assert _powershell(["-Command", cu]).returncode == 1639


def test_cai_dat_doi_tuong_lua_va_dns_truoc_khi_xin_chung_chi():
    """Let's Encrypt kiem ten mien bang cach goi vao cong 443 cua may 24. Thieu rule tuong lua hoac ban ghi DNS thi
    lan xin dau tien chac chan hong va tinh vao han muc -> -ApDung dung lai, tru khi -BoQuaKiemTruoc."""
    text = _doc(TT / "cai_dat_lan_dau.ps1")
    ap_dung = text.split("\nAssert-Admin\n", 1)[1]
    kiem = _khoi(ap_dung, r"if \(-not \$BoQuaKiemTruoc\)")
    assert "$dns.Count -eq 0" in kiem and "$null -ne $dns" in kiem           # khong hoi duoc DNS thi KHONG chan
    assert "Test-CoRuleTuongLua" in kiem and kiem.count("throw ") == 2
    assert ap_dung.index("if (-not $BoQuaKiemTruoc)") < ap_dung.index("Set-DichVu $WEB")
    # Hai script dung chung mot ten nhom rule.
    nhom = re.search(r"\$NHOM = '([^']+)'", _doc(TT / "tuong_lua_truc_tiep.ps1")).group(1)
    assert f"$NHOM_TUONG_LUA = '{nhom}'" in text
    # Sau khi khoi dong: doi toi khi Caddy phuc vu chung chi, khong thi in nhat ky de tim nguyen nhan.
    assert "Get-ChungChi $tenMienDung" in ap_dung and "$PROXY.err.log" in ap_dung
    assert "[Security.Authentication.SslProtocols]::Tls12" in text            # PS 5.1 mac dinh TLS cu, Caddy tu choi


def test_tuong_lua_cho_443_cho_caddy_va_dong_3000_8010():
    text = _doc(TT / "tuong_lua_truc_tiep.ps1")
    assert re.search(r"-Action Allow -Protocol TCP -LocalPort 443 -Program \$Caddy", text)
    assert re.search(r"-Action Block -Protocol TCP -LocalPort \$CONG_DONG", text)
    assert "$CONG_DONG = @('3000', '8010')" in text


@pytest.mark.parametrize("script", ["cai_dat_lan_dau.ps1", "tuong_lua_truc_tiep.ps1", "khoa_quyen_truc_tiep.ps1"])
def test_script_mac_dinh_chi_kiem(script):
    text = _doc(TT / script)
    assert "[switch]$ApDung" in text
    # Phan chay khi KHONG co -ApDung/-GoBo: chi in trang thai roi return.
    mac_dinh = text.split("if (-not $ApDung) {", 1)[1].split("\n}\n", 1)[0]
    assert "Show-TrangThai" in mac_dinh and "return" in mac_dinh
    for lenh in ("New-NetFirewallRule", "Remove-NetFirewallRule", "$Nssm", "icacls", "Start-Service", "sc.exe",
                 "Restart-Service", "Set-Khoa", "Remove-Khoa", "Invoke-Icacls"):
        assert lenh not in mac_dinh, lenh
    # Moi thao tac doi he thong deu nam SAU doan mac dinh hoac trong nhanh -GoBo, va deu doi quyen admin.
    assert text.count("Assert-Admin") >= 3


def test_khoa_quyen_tu_choi_ca_cay_chi_tru_cho_can_doc_va_tu_go_khi_web_khong_len():
    text = _doc(TT / "khoa_quyen_truc_tiep.ps1")
    assert "$NGOAI_LE = @((Join-Path $Repo 'tools'), (Join-Path $Repo 'deploy\\may24_truc_tiep'))" in text
    khoa = _khoi(text, r"function Set-Khoa")
    assert 'Invoke-Icacls @($Repo, \'/deny\', "${TaiKhoan}:(OI)(CI)F")' in khoa
    assert 'Invoke-Icacls @($ThuMucNssm, \'/deny\', "${TaiKhoan}:(OI)(CI)$QUYEN_GHI")' in khoa
    assert 'Invoke-Icacls @($d, \'/grant\', "${TaiKhoan}:(OI)(CI)RX")' in khoa
    assert "/grant" not in khoa.replace("'/grant', \"${TaiKhoan}:(OI)(CI)RX\"", "")   # khong cap gi rong hon DOC+CHAY
    # Chi THEM ACE cho mot tai khoan: khong go ke thua, khong dat lai quyen hay chu so huu cua ai.
    assert "[string]$TaiKhoan = 'LOCAL SERVICE'" in text
    for cam in ("/inheritance", "/reset", "/setowner", "/grant:r"):
        assert cam not in text, cam
    # Web khong len voi quyen moi -> go ACE, khoi dong lai, bao loi. Them ACE do dang cung phai go.
    ap_dung = text.split("\nAssert-Admin\n$gio", 1)[1]
    hong = _khoi(ap_dung, r"if \(-not \(Test-WebSauKhoiDongLai\)\)")
    assert hong.index("Remove-Khoa") < hong.index("throw ")
    do_dang = _khoi(ap_dung, r"try \{ Set-Khoa \} catch")
    assert do_dang.index("Remove-Khoa") < do_dang.index("throw ")
    assert "'17:15'" in ap_dung and "'18:15'" in ap_dung


# Chay CAC HAM THAT cua khoa_quyen_truc_tiep.ps1 (Set-Khoa / Remove-Khoa) tren mot cay thu muc tam, voi dung tai
# khoan LOCAL SERVICE, roi in cac ACE cua tai khoan do theo DUNG thu tu trong DACL - Windows xet ACE theo thu tu nay.
# KHONG dung chinh tai khoan dang chay test de dong vai: thu muc tam cua pytest co ACE "OWNER RIGHTS", nen tu tu choi
# chinh minh thi khong go lai duoc (02/10/2026 da de lai mot thu muc ket nhu vay tren may dev).
_IN_ACE = r'''param([string]$Script, [string]$Goc)
$ErrorActionPreference = 'Stop'
$Repo = Join-Path $Goc 'dnh_chatbot'
$ThuMucNssm = Join-Path $Goc 'nssm'
$TaiKhoan = 'LOCAL SERVICE'
New-Item -ItemType Directory -Force -Path "$Repo\backend", "$Repo\tools\node", "$Repo\deploy\may24_truc_tiep",
    "$Repo\deploy\cloud_server", "$ThuMucNssm\win64" | Out-Null
$FILE = [ordered]@{
    env = "$Repo\.env"; env_backend = "$Repo\backend\.env"; node = "$Repo\tools\node\node.txt"
    caddyfile = "$Repo\deploy\may24_truc_tiep\Caddyfile"; deploy_khac = "$Repo\deploy\cloud_server\x.txt"
    nssm = "$ThuMucNssm\win64\nssm.txt"
}
foreach ($f in $FILE.Values) { 'x' | Set-Content $f }
$src = Get-Content -Raw $Script
$ast = [System.Management.Automation.Language.Parser]::ParseInput($src, [ref]$null, [ref]$null)
$ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] }, $false) |
    Where-Object { $_.Name -in 'Invoke-Icacls', 'Get-AceRieng', 'Set-Khoa', 'Remove-Khoa' } |
    ForEach-Object { Invoke-Expression $_.Extent.Text }
foreach ($ten in 'QUYEN_GHI', 'NGOAI_LE') {
    Invoke-Expression ($src -split "`r?`n" | Where-Object { $_ -match "^\`$$ten = " } | Select-Object -First 1)
}
function In-Ace([string]$nhan) {
    foreach ($ten in $FILE.Keys) {
        $ds = @((Get-Acl -LiteralPath $FILE[$ten]).Access |
            Where-Object { "$($_.IdentityReference)" -like '*LOCAL SERVICE' } |
            ForEach-Object { "$($_.AccessControlType):$($_.FileSystemRights)" })
        "$nhan.$ten=" + ($ds -join ' > ')
    }
    "$nhan.rieng_goc=$(Get-AceRieng $Repo)"
    "$nhan.rieng_tools=$(Get-AceRieng "$Repo\tools")"
    "$nhan.rieng_nssm=$(Get-AceRieng $ThuMucNssm)"
}
try {
    Set-Khoa
    Set-Khoa
    In-Ace 'khoa'
} finally {
    Remove-Khoa
}
In-Ace 'go'
'''
_GHI = "Deny:DeleteSubdirectoriesAndFiles, Write, Delete, ChangePermissions, TakeOwnership"
_DOC = "Allow:ReadAndExecute, Synchronize"
_HET = "Deny:FullControl"


@pytest.mark.skipif(os.name != "nt" or not CO_POWERSHELL, reason="can Windows (icacls) va Windows PowerShell")
def test_khoa_quyen_chay_that_tren_thu_muc_tam(tmp_path):
    """Dieu can dung tren may 24: .env / kho du lieu / thu muc deploy khac chi con ACE tu choi; con node.exe,
    caddy.exe, Caddyfile co ACE CHO DOC dung TRUOC ACE tu choi thua huong tu goc (khong thi hai dich vu web khong
    khoi dong duoc) va van bi tu choi ghi. Chay hai lan khong sinh ACE trung. Go ra thi khong con ACE nao.
    Ket qua truy cap that voi thu tu ACE nay da do tay tren may dev 02/10/2026 (xem mo ta PR)."""
    do = tmp_path / "in_ace.ps1"
    do.write_text(_IN_ACE, encoding="ascii")
    kq = _powershell(["-File", str(do), "-Script", str(TT / "khoa_quyen_truc_tiep.ps1"), "-Goc", str(tmp_path / "cay")],
                     timeout=180)
    assert kq.returncode == 0, (kq.stdout, kq.stderr)
    ra = dict(d.split("=", 1) for d in kq.stdout.splitlines() if "=" in d)
    for bi_mat in ("env", "env_backend", "deploy_khac"):
        assert ra[f"khoa.{bi_mat}"] == _HET, (bi_mat, ra)
    for can_doc in ("node", "caddyfile"):
        assert ra[f"khoa.{can_doc}"] == f"{_GHI} > {_DOC} > {_HET}", (can_doc, ra)
    assert ra["khoa.nssm"] == _GHI
    assert ra["khoa.rieng_goc"] == _HET.replace(":", " ")
    assert ra["khoa.rieng_tools"] == f"{_GHI}; {_DOC}".replace(":", " ")
    assert ra["khoa.rieng_nssm"] == _GHI.replace(":", " ")
    for ten in ("env", "env_backend", "node", "caddyfile", "deploy_khac", "nssm"):
        assert ra[f"go.{ten}"] == "", (ten, ra)
    for ten in ("rieng_goc", "rieng_tools", "rieng_nssm"):
        assert ra[f"go.{ten}"] == "chua khoa", (ten, ra)


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
    # Thong bao loi chi dung file nhat ky ma cai_dat_lan_dau.ps1 that su tao (logs\<dich vu>.err.log).
    assert '"logs\\$DichVu.err.log"' in text and "web.err.log" not in text
    assert 'Join-Path $LOGS "$ten.err.log"' in _doc(TT / "cai_dat_lan_dau.ps1")


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


@pytest.mark.skipif(not CO_POWERSHELL, reason="khong co Windows PowerShell")
@pytest.mark.parametrize("script", PS1)
def test_ps1_dung_cu_phap(script):
    lenh = ("$loi = $null; [void][System.Management.Automation.Language.Parser]::ParseFile("
            f"'{TT / script}', [ref]$null, [ref]$loi); $loi | ForEach-Object {{ $_.ToString() }}; exit $loi.Count")
    kq = _powershell(["-Command", lenh])
    assert kq.returncode == 0, (kq.stdout, kq.stderr)
