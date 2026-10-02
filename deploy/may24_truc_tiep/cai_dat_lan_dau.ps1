# Dang ky hai dich vu cho web chatbot chay thang tren may 24:
#   DNH_Chatbot_Web    - Next.js (node next start) nghe 127.0.0.1:3000, thu muc C:\dnh_web\current
#   DNH_Chatbot_Proxy  - Caddy nhan HTTPS cong 443, chuyen ve 127.0.0.1:3000 (deploy\may24_truc_tiep\Caddyfile)
# Ca hai chay bang tai khoan LOCAL SERVICE (khong phai SYSTEM): day la phan duy nhat nhan ket noi tu Internet.
#
#   .\cai_dat_lan_dau.ps1                      # CHI KIEM, khong doi gi (mac dinh)
#   .\cai_dat_lan_dau.ps1 -ApDung -ChayThu     # dang ky/cap nhat dich vu cho uat-chatbot + chung chi THU (staging)
#   .\cai_dat_lan_dau.ps1 -ApDung              # dang ky/cap nhat dich vu cho chatbot.namhatrading.com, chung chi that
#   .\cai_dat_lan_dau.ps1 -GoBo                # dung va xoa hai dich vu (khong xoa C:\dnh_web)
# -ApDung / -GoBo phai chay trong PowerShell "Run as Administrator". Script KHONG tai gi tu Internet:
# caddy.exe phai duoc dat san o $Caddy (tai ban Windows amd64 tu caddyserver.com, doi chieu checksum).
# Thu tu lan dau: tao C:\dnh_web\web.env -> deploy_web.ps1 (build) -> script nay -ApDung -> tuong_lua_truc_tiep.ps1.
param(
    [switch]$ApDung,
    [switch]$GoBo,
    [switch]$ChayThu,
    [string]$TenMien = 'chatbot.namhatrading.com',
    [string]$TenMienThu = 'uat-chatbot.namhatrading.com',
    [string]$GocWeb = 'C:\dnh_web',
    [string]$Repo = 'C:\dnh_chatbot',
    [string]$Node = 'C:\dnh_chatbot\tools\node\node.exe',
    [string]$Caddy = 'C:\dnh_chatbot\tools\caddy\caddy.exe',
    [string]$Nssm = 'C:\nssm\nssm-2.24\win64\nssm.exe'
)
$ErrorActionPreference = 'Stop'
$WEB = 'DNH_Chatbot_Web'
$PROXY = 'DNH_Chatbot_Proxy'
$CADDYFILE = Join-Path $Repo 'deploy\may24_truc_tiep\Caddyfile'
$ACME_THU = 'https://acme-staging-v02.api.letsencrypt.org/directory'
$ACME_THAT = 'https://acme-v02.api.letsencrypt.org/directory'
$LOGS = Join-Path $GocWeb 'logs'
$CURRENT = Join-Path $GocWeb 'current'

function Assert-Admin {
    $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can chay PowerShell bang "Run as Administrator".'
    }
}

function Get-MoiTruongProxy {
    if ($ChayThu) { return @("DNH_WEB_HOST=$TenMienThu", "DNH_ACME_CA=$ACME_THU") }
    return @("DNH_WEB_HOST=$TenMien", "DNH_ACME_CA=$ACME_THAT")
}

function Test-Caddyfile {
    $cu = $env:DNH_WEB_HOST, $env:DNH_ACME_CA
    $uuTienCu = $ErrorActionPreference
    try {
        foreach ($kv in Get-MoiTruongProxy) { $k, $v = $kv -split '=', 2; Set-Item -Path "env:$k" -Value $v }
        # 02/10/2026 (lan dau chay tren may 24): Caddy ghi nhat ky ra stderr; PS 5.1 voi ErrorActionPreference=Stop
        # bien dong stderr DAU TIEN cua lenh ngoai thanh loi dung script, chua kip co ket qua. Ha xuong Continue
        # trong luc goi. Ket qua in bang Write-Host de ham CHI tra ve dung/sai (truoc day tra kem ca cac dong chu,
        # nen "if (Test-Caddyfile)" luon dung).
        $ErrorActionPreference = 'Continue'
        $ra = & $Caddy validate --config $CADDYFILE --adapter caddyfile 2>&1 | ForEach-Object { "$_" }
        $ma = $LASTEXITCODE
        $ErrorActionPreference = $uuTienCu
        $ra | Select-Object -Last 3 | ForEach-Object { Write-Host "   $_" }
        return ($ma -eq 0)
    } finally {
        $ErrorActionPreference = $uuTienCu
        $env:DNH_WEB_HOST, $env:DNH_ACME_CA = $cu
    }
}

function Show-TrangThai {
    '=== File can co'
    foreach ($f in @($Node, $Caddy, $Nssm, $CADDYFILE, (Join-Path $GocWeb 'web.env'))) {
        "   {0}  {1}" -f $(if (Test-Path $f) { 'CO   ' } else { 'THIEU' }), $f
    }
    $envFile = Join-Path $GocWeb 'web.env'
    if ((Test-Path $envFile) -and (Select-String -Path $envFile -Pattern 'DAN_KHOA_TU_BACKEND_ENV' -Quiet)) {
        '   CANH BAO: web.env con khoa mau'
    }
    '=== Ban web dang tro (current)'
    if (Test-Path $CURRENT) { "   $((Get-Item $CURRENT -Force).Target | Select-Object -First 1)" }
    else { '   CHUA CO - chay deploy_web.ps1 truoc' }
    '=== Cong dang nghe (443/80 phai TRONG truoc khi cai, hoac do caddy giu; 3000 do node giu)'
    foreach ($cong in 80, 443, 3000, 8010) {
        $l = Get-NetTCPConnection -LocalPort $cong -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($l) {
            $p = Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue
            "   {0,-5} {1} (PID {2}, {3})" -f $cong, $l.LocalAddress, $l.OwningProcess, $p.ProcessName
        } else { "   {0,-5} trong" -f $cong }
    }
    '=== Dich vu'
    foreach ($s in $WEB, $PROXY, 'DNH_Chatbot_Backend', 'DNH_Chatbot_Tunnel') {
        $sv = Get-CimInstance Win32_Service -Filter "Name='$s'" -ErrorAction SilentlyContinue
        if ($sv) { "   {0,-20} {1,-8} {2,-7} chay bang {3}" -f $s, $sv.State, $sv.StartMode, $sv.StartName }
        else { "   {0,-20} chua dang ky" -f $s }
    }
    if ((Test-Path $Caddy) -and (Test-Path $CADDYFILE)) {
        "=== Kiem Caddyfile ($(if ($ChayThu) { 'CHAY THU' } else { 'THAT' }): $((Get-MoiTruongProxy)[0]))"
        if (Test-Caddyfile) { '   Caddyfile hop le' } else { '   LOI: Caddyfile khong hop le' }
    }
}

function Set-DichVu([string]$ten, [string]$exe, [string]$thamSo, [string]$thuMuc, [string[]]$moiTruong) {
    if (Get-Service -Name $ten -ErrorAction SilentlyContinue) {
        & $Nssm stop $ten confirm | Out-Null
        & $Nssm set $ten Application $exe | Out-Null
    } else {
        & $Nssm install $ten $exe | Out-Null
    }
    & $Nssm set $ten AppParameters $thamSo | Out-Null
    & $Nssm set $ten AppDirectory $thuMuc | Out-Null
    & $Nssm set $ten AppEnvironmentExtra @moiTruong | Out-Null
    & $Nssm set $ten AppStdout (Join-Path $LOGS "$ten.out.log") | Out-Null
    & $Nssm set $ten AppStderr (Join-Path $LOGS "$ten.err.log") | Out-Null
    & $Nssm set $ten AppRotateFiles 1 | Out-Null
    & $Nssm set $ten AppRotateBytes 10485760 | Out-Null
    & $Nssm set $ten Start SERVICE_AUTO_START | Out-Null
    # Khong chay bang SYSTEM: tien trinh nhan ket noi Internet chi co quyen cua LOCAL SERVICE.
    & sc.exe config $ten obj= 'NT AUTHORITY\LocalService' password= '' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "khong doi duoc tai khoan chay cua $ten" }
}

if ($GoBo) {
    Assert-Admin
    foreach ($s in $PROXY, $WEB) {
        if (Get-Service -Name $s -ErrorAction SilentlyContinue) {
            & $Nssm stop $s confirm | Out-Null
            & $Nssm remove $s confirm | Out-Null
            "Da xoa dich vu $s"
        }
    }
    'Thu muc C:\dnh_web va rule tuong lua KHONG bi xoa (tuong_lua_truc_tiep.ps1 -GoBo).'
    return
}

if (-not $ApDung) {
    Show-TrangThai
    ''
    'CHI KIEM - chua doi gi. Them -ApDung (va -ChayThu khi thu voi uat-chatbot) de dang ky dich vu.'
    return
}

Assert-Admin
foreach ($f in @($Node, $Caddy, $Nssm, $CADDYFILE)) { if (-not (Test-Path $f)) { throw "Thieu $f" } }
if (-not (Test-Path (Join-Path $CURRENT 'package.json'))) { throw "Chua co ban web o $CURRENT - chay deploy_web.ps1 truoc." }
if (-not (Test-Caddyfile)) { throw 'Caddyfile khong hop le - khong dang ky dich vu.' }

New-Item -ItemType Directory -Force -Path $LOGS, (Join-Path $GocWeb 'caddy_data') | Out-Null
# C:\dnh_web chua khoa backend (web.env, .env.production.local) va khoa rieng cua chung chi: chi Administrators,
# SYSTEM duoc toan quyen; LOCAL SERVICE chi DOC ma nguon, va GHI vao logs, caddy_data, .next\cache.
& icacls $GocWeb /inheritance:r /grant:r 'Administrators:(OI)(CI)F' 'SYSTEM:(OI)(CI)F' 'LOCAL SERVICE:(OI)(CI)RX' | Out-Null
& icacls $LOGS /grant 'LOCAL SERVICE:(OI)(CI)M' | Out-Null
& icacls (Join-Path $GocWeb 'caddy_data') /grant 'LOCAL SERVICE:(OI)(CI)M' | Out-Null
$cache = Join-Path ((Get-Item $CURRENT -Force).Target | Select-Object -First 1) '.next\cache'
New-Item -ItemType Directory -Force -Path $cache | Out-Null
& icacls $cache /grant 'LOCAL SERVICE:(OI)(CI)M' | Out-Null

Set-DichVu $WEB $Node 'node_modules\next\dist\bin\next start --hostname 127.0.0.1 --port 3000' $CURRENT `
    @('NODE_ENV=production', 'NEXT_TELEMETRY_DISABLED=1')
Set-DichVu $PROXY $Caddy "run --config `"$CADDYFILE`" --adapter caddyfile" $GocWeb (Get-MoiTruongProxy)

Start-Service -Name $WEB
Start-Service -Name $PROXY
Start-Sleep -Seconds 8
Show-TrangThai
''
"Da dang ky cho: $((Get-MoiTruongProxy)[0]). Buoc tiep: tuong_lua_truc_tiep.ps1 (kiem) roi -ApDung."
