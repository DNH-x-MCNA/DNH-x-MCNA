# Dang ky hai dich vu cho web chatbot chay thang tren may 24:
#   DNH_Chatbot_Web    - Next.js (node next start) nghe 127.0.0.1:3000, thu muc C:\dnh_web\current
#   DNH_Chatbot_Proxy  - Caddy nhan HTTPS cong 443, chuyen ve 127.0.0.1:3000 (deploy\may24_truc_tiep\Caddyfile)
# Ca hai chay bang tai khoan LOCAL SERVICE (khong phai SYSTEM): day la phan duy nhat nhan ket noi tu Internet.
#
#   .\cai_dat_lan_dau.ps1                      # CHI KIEM, khong doi gi (mac dinh)
#   .\cai_dat_lan_dau.ps1 -ApDung              # dang ky/cap nhat dich vu cho chat.namhatrading.com, chung chi that
#   .\cai_dat_lan_dau.ps1 -ApDung -ChayThu     # cung ten mien nhung xin chung chi THU (staging): dung de do loi xin
#                                              # chung chi ma khong ton han muc Let's Encrypt; trinh duyet se canh bao
#   .\cai_dat_lan_dau.ps1 -GoBo                # dung va xoa hai dich vu (khong xoa C:\dnh_web)
# -ApDung / -GoBo phai chay trong PowerShell "Run as Administrator". Script KHONG tai file nao ve may:
# caddy.exe phai duoc dat san o $Caddy (tai ban Windows amd64 tu caddyserver.com, doi chieu checksum).
# Thu tu lan dau: tao C:\dnh_web\web.env -> deploy_web.ps1 (build) -> tuong_lua_truc_tiep.ps1 -ApDung -> script nay
# -ApDung -> khoa_quyen_truc_tiep.ps1 -ApDung. Tuong lua phai di TRUOC: Let's Encrypt kiem ten mien bang cach goi
# vao cong 443 cua may nay; chua co rule cho 443 thi lan xin chung chi dau tien chac chan hong.
param(
    [switch]$ApDung,
    [switch]$GoBo,
    [switch]$ChayThu,
    [switch]$BoQuaKiemTruoc,
    [string]$TenMien = 'chat.namhatrading.com',
    [string]$TenMienThu = '',
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
# Cung ten nhom voi tuong_lua_truc_tiep.ps1.
$NHOM_TUONG_LUA = 'DNH chatbot truc tiep'

function Assert-Admin {
    $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can chay PowerShell bang "Run as Administrator".'
    }
}

function Get-TenMienDung {
    if ($ChayThu -and $TenMienThu) { return $TenMienThu }
    return $TenMien
}

function Get-MoiTruongProxy {
    $ca = $ACME_THAT
    if ($ChayThu) { $ca = $ACME_THU }
    return @("DNH_WEB_HOST=$(Get-TenMienDung)", "DNH_ACME_CA=$ca")
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

# Hoi DNS cong khai qua HTTPS: may 24 co the bi chan UDP 53 ra ngoai, con DNS noi bo co the tra dia chi khac.
# Tra ve $null khi khong hoi duoc; mang dia chi IPv4 (co the RONG = chua co ban ghi A) khi hoi duoc.
function Get-DnsCongKhai([string]$ten) {
    try {
        $tls = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
        [Net.ServicePointManager]::SecurityProtocol = $tls
        $r = Invoke-RestMethod -Uri "https://dns.google/resolve?name=$ten&type=A" -TimeoutSec 10
        return , @($r.Answer | Where-Object { $_.type -eq 1 } | ForEach-Object { "$($_.data)" })
    } catch { return $null }
}

# Bat tay TLS voi Caddy tren chinh may nay (SNI = ten mien) va tra ve chung chi dang phuc vu, hoac $null. Chi doc.
function Get-ChungChi([string]$ten, [string]$may = '127.0.0.1', [int]$cong = 443) {
    $tcp = New-Object Net.Sockets.TcpClient
    $ssl = $null
    try {
        $tcp.Connect($may, $cong)
        $khongKiem = [Net.Security.RemoteCertificateValidationCallback] { $true }
        $ssl = New-Object Net.Security.SslStream($tcp.GetStream(), $false, $khongKiem)
        # Ghi ro TLS 1.2: PowerShell 5.1 mac dinh con thu SSL3/TLS 1.0, Caddy tu choi.
        $ssl.AuthenticateAsClient($ten, $null, [Security.Authentication.SslProtocols]::Tls12, $false)
        return New-Object Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
    } catch { return $null }
    finally {
        if ($ssl) { $ssl.Dispose() }
        $tcp.Close()
    }
}

function Show-TenMien {
    $ten = Get-TenMienDung
    "=== Ten mien $ten"
    $dns = Get-DnsCongKhai $ten
    if ($null -eq $dns) { '   DNS cong khai : khong hoi duoc (may nay khong goi duoc dns.google)' }
    elseif ($dns.Count -eq 0) { '   DNS cong khai : CHUA CO ban ghi A (DNH chua tao, hoac chua lan toi)' }
    else { "   DNS cong khai : $($dns -join ', ')" }
    # Nguoi trong mang DNH dung DNS nay: neu ra IP public thi firewall phai cho vong lai (hairpin NAT), neu khong
    # thi DNH them ban ghi noi bo tro thang 172.16.0.24.
    try { $noiBo = @([Net.Dns]::GetHostAddresses($ten) | ForEach-Object { $_.IPAddressToString }) -join ', ' }
    catch { $noiBo = 'khong phan giai duoc' }
    "   DNS may nay   : $noiBo"
    $cc = Get-ChungChi $ten
    if (-not $cc) {
        "   Chung chi     : CHUA CO tren cong 443 (Caddy chua chay hoac chua xin duoc; xem $LOGS\$PROXY.err.log)"
        return
    }
    $loai = 'KHONG phai cua Let''s Encrypt'
    if ($cc.Issuer -match 'STAGING') { $loai = 'chung chi THU - trinh duyet se canh bao' }
    elseif ($cc.Issuer -match 'Let''s Encrypt') { $loai = 'chung chi THAT' }
    $capCho = $cc.GetNameInfo([Security.Cryptography.X509Certificates.X509NameType]::DnsName, $false)
    $conLai = [int]($cc.NotAfter - (Get-Date)).TotalDays
    "   Chung chi     : $loai; cap cho $capCho; het han $($cc.NotAfter.ToString('dd/MM/yyyy')) (con $conLai ngay)"
    "   Noi cap       : $($cc.Issuer)"
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
    "=== Rule tuong lua cho 443 (nhom '$NHOM_TUONG_LUA')"
    if (Test-CoRuleTuongLua) { '   CO' } else { '   CHUA CO - chay tuong_lua_truc_tiep.ps1 -ApDung truoc khi -ApDung o day' }
    if ((Test-Path $Caddy) -and (Test-Path $CADDYFILE)) {
        "=== Kiem Caddyfile ($(if ($ChayThu) { 'CHAY THU' } else { 'THAT' }): $((Get-MoiTruongProxy)[0]))"
        if (Test-Caddyfile) { '   Caddyfile hop le' } else { '   LOI: Caddyfile khong hop le' }
    }
    Show-TenMien
}

function Test-CoRuleTuongLua {
    $r = Get-NetFirewallRule -Group $NHOM_TUONG_LUA -ErrorAction SilentlyContinue |
        Where-Object { "$($_.Action)" -eq 'Allow' -and "$($_.Enabled)" -eq 'True' }
    return [bool]$r
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
    # 02/10/2026 (thu tren may dev, PS 5.1): viet "& sc.exe ... password= ''" thi PowerShell BO MAT tham so rong,
    # sc.exe in huong dan roi thoat 1639 va script dung ngay o dich vu dau tien. Start-Process giu nguyen tung
    # tham so, ke ca cap password= "" ma sc.exe doi cho tai khoan khong co mat khau.
    $sc = Start-Process -FilePath sc.exe -Wait -NoNewWindow -PassThru -ArgumentList `
        'config', $ten, 'obj=', '"NT AUTHORITY\LocalService"', 'password=', '""'
    $chayBang = (Get-CimInstance Win32_Service -Filter "Name='$ten'").StartName
    if ($sc.ExitCode -ne 0 -or $chayBang -notmatch 'Local\s?Service') {
        throw "khong doi duoc tai khoan chay cua $ten (sc.exe thoat $($sc.ExitCode); dang chay bang '$chayBang')"
    }
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
    'Con nguyen: thu muc C:\dnh_web, rule tuong lua (tuong_lua_truc_tiep.ps1 -GoBo), ACE (khoa_quyen_truc_tiep.ps1 -GoBo).'
    return
}

if (-not $ApDung) {
    Show-TrangThai
    ''
    'CHI KIEM - chua doi gi. Them -ApDung de dang ky dich vu (-ChayThu: xin chung chi thu).'
    return
}

Assert-Admin
foreach ($f in @($Node, $Caddy, $Nssm, $CADDYFILE)) { if (-not (Test-Path $f)) { throw "Thieu $f" } }
if (-not (Test-Path (Join-Path $CURRENT 'package.json'))) { throw "Chua co ban web o $CURRENT - chay deploy_web.ps1 truoc." }
if (-not (Test-Caddyfile)) { throw 'Caddyfile khong hop le - khong dang ky dich vu.' }
$tenMienDung = Get-TenMienDung
if (-not $BoQuaKiemTruoc) {
    # Thieu mot trong hai thu nay thi Let's Encrypt khong kiem duoc ten mien: Caddy xin hong, phai cho thu lai, va
    # moi lan hong tinh vao han muc (5 lan/gio cho mot ten).
    $dns = Get-DnsCongKhai $tenMienDung
    if ($null -ne $dns -and $dns.Count -eq 0) {
        throw "DNS cong khai chua co ban ghi A cho $tenMienDung - cho DNH tao roi chay lai (bo qua: -BoQuaKiemTruoc)."
    }
    $bat = @(Get-NetFirewallProfile | Where-Object { "$($_.Enabled)" -eq 'True' })
    if ($bat.Count -gt 0 -and -not (Test-CoRuleTuongLua)) {
        throw 'Chua co rule tuong lua cho 443 - chay tuong_lua_truc_tiep.ps1 -ApDung truoc (bo qua: -BoQuaKiemTruoc).'
    }
}

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
Write-Host "Da khoi dong hai dich vu. Cho Caddy xin chung chi cho $tenMienDung (toi da 90 giay)..."
$cc = $null
for ($i = 0; $i -lt 18 -and -not $cc; $i++) {
    Start-Sleep -Seconds 5
    $cc = Get-ChungChi $tenMienDung
}
Show-TrangThai
''
if ($cc) {
    "DAT: da dang ky cho $tenMienDung va Caddy dang phuc vu chung chi. Buoc tiep: kiem tu ngoai mang DNH, roi"
    'khoa_quyen_truc_tiep.ps1 (kiem) va -ApDung.'
} else {
    "CHUA co chung chi cho $tenMienDung sau 90 giay. 12 dong cuoi cua $LOGS\$PROXY.err.log:"
    Get-Content -LiteralPath (Join-Path $LOGS "$PROXY.err.log") -Tail 12 -Encoding UTF8 -ErrorAction SilentlyContinue |
        ForEach-Object { "   $_" }
    'Thuong gap: NAT 443 chua vao toi may nay; hoac firewall cua DNH chan dia chi nuoc ngoai (may chu kiem tra cua'
    'Let''s Encrypt o nuoc ngoai). Caddy tu thu lai; sua xong co the Restart-Service DNH_Chatbot_Proxy de thu ngay.'
}
