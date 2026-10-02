# Thu hep quyen cua tai khoan chay web + Caddy (LOCAL SERVICE) tren may 24. Chay SAU KHI hai dich vu web da chay on.
#
# VI SAO: LOCAL SERVICE thuoc nhom Users. Voi quyen mac dinh cua o C:, nhom nay DOC duoc ca C:\dnh_chatbot (.env va
# backend\.env: tai khoan doc Bravo, khoa API model, mat khau SMTP, URL webhook; kho du lieu; nhat ky cau hoi) va TAO
# duoc file moi canh code / nssm.exe dang chay bang SYSTEM. Web la phan duy nhat nhan ket noi tu Internet: neu
# Next.js hoac Caddy bi khai thac, ke tan cong co dung cac quyen do. Script them ACE TU CHOI rieng cho LOCAL SERVICE:
#   C:\dnh_chatbot (ca cay)                      tu choi MOI quyen
#   ...\tools va ...\deploy\may24_truc_tiep      cho DOC + CHAY (node.exe, caddy.exe, Caddyfile), tu choi GHI
#   C:\nssm (ca cay)                             tu choi GHI (van chay duoc nssm.exe)
# Khong dung toi quyen cua SYSTEM, Administrators hay Users: backend, dich vu canh bao, task dinh ky, git pull va nguoi
# quan tri KHONG doi gi. git khong theo doi ACL nen "git status" van sach. File tao sau nay tu thua huong.
# Ngu nghia da thu tren may dev (02/10/2026): ACE cho o thu muc con (gan hon) duoc xet TRUOC ACE tu choi thua huong tu
# goc, nen node.exe/caddy.exe/Caddyfile van doc duoc trong khi phan con lai bi tu choi.
#
#   .\khoa_quyen_truc_tiep.ps1            # CHI KIEM, khong doi gi (mac dinh)
#   .\khoa_quyen_truc_tiep.ps1 -ApDung    # them ACE, khoi dong lai 2 dich vu web roi kiem; web khong len thi TU GO
#   .\khoa_quyen_truc_tiep.ps1 -GoBo      # go het ACE da them
# -ApDung / -GoBo phai chay trong PowerShell "Run as Administrator". Cay C:\dnh_chatbot lon nen co the mat 1-2 phut.
# -ApDung lam web ngung vai giay (khoi dong lai de kiem): chay truoc khi bao nguoi dung dia chi moi.
param(
    [switch]$ApDung,
    [switch]$GoBo,
    [switch]$BoQuaKhungGio,
    [string]$Repo = 'C:\dnh_chatbot',
    [string]$ThuMucNssm = 'C:\nssm',
    [string]$TaiKhoan = 'LOCAL SERVICE'
)
$ErrorActionPreference = 'Stop'
$WEB = 'DNH_Chatbot_Web'
$PROXY = 'DNH_Chatbot_Proxy'
# Tao/ghi/sua thuoc tinh/xoa/doi quyen/doi chu so huu.
$QUYEN_GHI = '(WD,AD,WEA,WA,DC,DE,WDAC,WO)'
$NGOAI_LE = @((Join-Path $Repo 'tools'), (Join-Path $Repo 'deploy\may24_truc_tiep'))

function Assert-Admin {
    $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can chay PowerShell bang "Run as Administrator".'
    }
}

function Invoke-Icacls([string[]]$thamSo) {
    $ra = & icacls @thamSo
    if ($LASTEXITCODE -ne 0) { throw "icacls $($thamSo -join ' ') loi: $(($ra | Select-Object -Last 2) -join ' ')" }
}

# ACE rieng (khong thua huong) cua $TaiKhoan tren mot thu muc, dang "Deny FullControl; Allow ReadAndExecute".
function Get-AceRieng([string]$duongDan) {
    if (-not (Test-Path -LiteralPath $duongDan)) { return 'KHONG CO thu muc nay' }
    $ace = @((Get-Acl -LiteralPath $duongDan).Access | Where-Object {
            -not $_.IsInherited -and "$($_.IdentityReference)" -like "*$TaiKhoan" })
    if ($ace.Count -eq 0) { return 'chua khoa' }
    return ($ace | ForEach-Object { "$($_.AccessControlType) $($_.FileSystemRights)" }) -join '; '
}

function Show-TrangThai {
    "=== ACE rieng cua $TaiKhoan"
    foreach ($d in @($Repo) + $NGOAI_LE + @($ThuMucNssm)) { "   {0,-42} {1}" -f $d, (Get-AceRieng $d) }
    "=== Quyen hien co tren $Repo (nhom Users / Authenticated Users co gi thi LOCAL SERVICE co nay)"
    if (Test-Path -LiteralPath $Repo) {
        (Get-Acl -LiteralPath $Repo).Access | ForEach-Object {
            "   {0,-34} {1,-5} {2}" -f $_.IdentityReference, $_.AccessControlType, $_.FileSystemRights
        }
    } else { '   KHONG CO thu muc nay' }
    '=== Dich vu web'
    foreach ($s in $WEB, $PROXY) {
        $sv = Get-CimInstance Win32_Service -Filter "Name='$s'" -ErrorAction SilentlyContinue
        if ($sv) { "   {0,-20} {1,-8} chay bang {2}" -f $s, $sv.State, $sv.StartName }
        else { "   {0,-20} chua dang ky" -f $s }
    }
}

function Set-Khoa {
    foreach ($d in $NGOAI_LE) {
        Invoke-Icacls @($d, '/grant', "${TaiKhoan}:(OI)(CI)RX")
        Invoke-Icacls @($d, '/deny', "${TaiKhoan}:(OI)(CI)$QUYEN_GHI")
    }
    Invoke-Icacls @($Repo, '/deny', "${TaiKhoan}:(OI)(CI)F")
    Invoke-Icacls @($ThuMucNssm, '/deny', "${TaiKhoan}:(OI)(CI)$QUYEN_GHI")
}

function Remove-Khoa {
    foreach ($d in @($Repo, $ThuMucNssm) + $NGOAI_LE) {
        if (-not (Test-Path -LiteralPath $d)) { continue }
        Invoke-Icacls @($d, '/remove:d', $TaiKhoan)
        if ($NGOAI_LE -contains $d) { Invoke-Icacls @($d, '/remove:g', $TaiKhoan) }
    }
}

# Khoi dong lai hai dich vu web roi kiem: web tra 200 qua loopback va Caddy dang nghe 443.
function Test-WebSauKhoiDongLai {
    try {
        Restart-Service -Name $WEB -Force
        Restart-Service -Name $PROXY -Force
    } catch {
        Write-Host "   khong khoi dong lai duoc dich vu: $($_.Exception.Message)"
        return $false
    }
    $web = $false
    $caddy = $false
    for ($i = 0; $i -lt 30 -and -not ($web -and $caddy); $i++) {
        Start-Sleep -Seconds 2
        if (-not $web) {
            try {
                $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 5
                $web = ($r.StatusCode -eq 200)
            } catch { }
        }
        $caddy = [bool](Get-NetTCPConnection -LocalPort 443 -State Listen -ErrorAction SilentlyContinue)
    }
    Write-Host "   web 127.0.0.1:3000 tra 200: $web; Caddy nghe 443: $caddy"
    return ($web -and $caddy)
}

if ($GoBo) {
    Assert-Admin
    Remove-Khoa
    "Da go ACE cua $TaiKhoan."
    Show-TrangThai
    return
}

if (-not $ApDung) {
    Show-TrangThai
    ''
    'CHI KIEM - chua doi gi. Them -ApDung de khoa (chay sau khi hai dich vu web da chay on).'
    return
}

Assert-Admin
$gio = (Get-Date).ToString('HH:mm')
if (-not $BoQuaKhungGio -and $gio -ge '17:15' -and $gio -le '18:15') {
    throw "Gan gio bao cao 17:45 ($gio) - chay lai sau 18:15."
}
foreach ($d in @($Repo, $ThuMucNssm) + $NGOAI_LE) { if (-not (Test-Path -LiteralPath $d)) { throw "Thieu $d" } }

Write-Host "Them ACE cho $TaiKhoan (co the mat 1-2 phut)..."
try { Set-Khoa } catch {
    # Mot file con khong nhan duoc ACE (vd bi khoa quyen rieng) -> khong de may o trang thai khoa do dang.
    Write-Host "Them ACE loi: $($_.Exception.Message)"
    Write-Host 'Go lai cac ACE da them...'
    try { Remove-Khoa } catch { Write-Host "   go lai cung loi: $($_.Exception.Message)" }
    throw 'KHONG khoa duoc - xem dong loi phia tren (icacls neu ro file nao).'
}
$coDichVu = @($WEB, $PROXY | Where-Object { Get-Service -Name $_ -ErrorAction SilentlyContinue })
if ($coDichVu.Count -lt 2) {
    Show-TrangThai
    ''
    'DA KHOA nhung CHUA KIEM duoc: chua co du hai dich vu web. Sau cai_dat_lan_dau.ps1 -ApDung, neu dich vu khong'
    'len thi chay -GoBo o day roi thu lai.'
    return
}
Write-Host 'Khoi dong lai hai dich vu web de kiem voi quyen moi...'
if (-not (Test-WebSauKhoiDongLai)) {
    Write-Host 'Web khong len voi quyen moi -> go ACE va khoi dong lai.'
    Remove-Khoa
    $lai = Test-WebSauKhoiDongLai
    Show-TrangThai
    throw "KHONG khoa duoc: web khong len khi bi khoa quyen. Da go ACE; web len lai sau khi go: $lai."
}
Show-TrangThai
''
"DAT: $TaiKhoan khong con doc/ghi duoc $Repo (tru tools va deploy\may24_truc_tiep chi doc), web van chay."
