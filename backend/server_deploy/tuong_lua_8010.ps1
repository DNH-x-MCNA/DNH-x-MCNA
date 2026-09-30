# Tuong lua cong 8010 (backend chatbot) tren may 24, dung khi web chuyen sang Cloud Server Mat Bao.
#
# Hien uvicorn nghe 0.0.0.0:8010 (run_supervisor.ps1), nen neu Windows Firewall dang cho python vao thi ca
# mang noi bo DNH goi thang duoc backend (van phai co khoa API). Sau khi chuyen: CHI Cloud Server, di qua
# duong ham WireGuard (10.88.24.1), duoc vao 8010. localhost (tunnel tam cloudflared, watchdog) KHONG bi
# anh huong vi Windows Firewall khong loc loopback. uvicorn chi nghe IPv4 nen khong can rule IPv6.
#
#   .\tuong_lua_8010.ps1             # CHI KIEM, khong doi gi (mac dinh)
#   .\tuong_lua_8010.ps1 -ApDung     # tao 2 rule: CHO 10.88.24.1, CHAN moi dia chi khac vao 8010
#   .\tuong_lua_8010.ps1 -GoBo       # xoa 2 rule do, quay ve nhu cu
#   .\tuong_lua_8010.ps1 -InDaiChan  # chi in cac dai dia chi se bi chan (de doc lai truoc khi ap dung)
# -ApDung / -GoBo phai chay trong PowerShell "Run as Administrator".
param(
    [switch]$ApDung,
    [switch]$GoBo,
    [switch]$InDaiChan,
    [string]$IpCloudServer = '10.88.24.1'
)
$ErrorActionPreference = 'Stop'
$NHOM = 'DNH chatbot 8010'
$CONG = 8010

function ConvertTo-Ip([uint32]$n) {
    $b = [BitConverter]::GetBytes($n)
    [Array]::Reverse($b)
    return (New-Object System.Net.IPAddress (, $b)).ToString()
}

# Moi IPv4 TRU $ip. Windows Firewall uu tien rule CHAN hon rule CHO, nen rule chan phai loai dung IP nay ra.
function Get-DaiChan([string]$ip) {
    $b = ([System.Net.IPAddress]::Parse($ip)).GetAddressBytes()
    [Array]::Reverse($b)
    $n = [BitConverter]::ToUInt32($b, 0)
    $dai = @()
    if ($n -gt 0) { $dai += "0.0.0.0-$(ConvertTo-Ip ($n - 1))" }
    if ($n -lt [uint32]::MaxValue) { $dai += "$(ConvertTo-Ip ($n + 1))-255.255.255.255" }
    return , $dai
}

function Assert-Admin {
    $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can chay PowerShell bang "Run as Administrator".'
    }
}

function Show-TrangThai {
    '=== Windows Firewall theo profile (Enabled=False thi moi rule deu khong co tac dung)'
    Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction -AutoSize | Out-String

    '=== Dia chi uvicorn dang nghe cong 8010'
    Get-NetTCPConnection -LocalPort $CONG -State Listen -ErrorAction SilentlyContinue |
        Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize | Out-String

    '=== Rule dang CHO vao cong 8010 hoac chuong trinh python (chieu vao)'
    $theoCong = Get-NetFirewallPortFilter -Protocol TCP -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -contains "$CONG" } | Get-NetFirewallRule
    $theoPython = Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue |
        Where-Object { $_.Program -match 'python' } | Get-NetFirewallRule
    @($theoCong) + @($theoPython) | Where-Object { $_ -and $_.Direction -eq 'Inbound' -and $_.Enabled -eq 'True' } |
        Sort-Object Name -Unique | Format-Table DisplayName, Action, Profile, Group -AutoSize | Out-String

    '=== Ket noi DANG MO vao 8010 theo dia chi nguon (127.0.0.1 = tunnel tam/watchdog, khong bi anh huong)'
    Get-NetTCPConnection -LocalPort $CONG -State Established -ErrorAction SilentlyContinue |
        Group-Object RemoteAddress | Sort-Object Count -Descending | Format-Table Count, Name -AutoSize | Out-String

    $wg = Get-NetIPAddress -IPAddress '10.88.24.2' -ErrorAction SilentlyContinue
    if ($wg) { "=== Duong ham WireGuard: CO (10.88.24.2 tren '$($wg.InterfaceAlias)')" }
    else { '=== Duong ham WireGuard: CHUA CO dia chi 10.88.24.2 (chua Activate tunnel dnh-cloud?)' }
}

if ($InDaiChan) {
    "Se CHO: $IpCloudServer"
    'Se CHAN:'
    Get-DaiChan $IpCloudServer
    return
}

if ($GoBo) {
    Assert-Admin
    Get-NetFirewallRule -Group $NHOM -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    "Da xoa cac rule nhom '$NHOM'. Cong 8010 quay ve nhu truoc khi ap dung."
    return
}

if ($ApDung) {
    Assert-Admin
    [void][System.Net.IPAddress]::Parse($IpCloudServer)
    Get-NetFirewallRule -Group $NHOM -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -DisplayName 'DNH 8010 - cho Cloud Server qua duong ham' -Group $NHOM -Direction Inbound `
        -Protocol TCP -LocalPort $CONG -RemoteAddress $IpCloudServer -Action Allow -Profile Any | Out-Null
    New-NetFirewallRule -DisplayName 'DNH 8010 - chan moi dia chi khac' -Group $NHOM -Direction Inbound `
        -Protocol TCP -LocalPort $CONG -RemoteAddress (Get-DaiChan $IpCloudServer) -Action Block -Profile Any | Out-Null
    "Da ap dung. Kiem tu Cloud Server: curl -s http://10.88.24.2:8010/health ; tu may khac trong LAN phai KHONG vao duoc."
    Get-NetFirewallRule -Group $NHOM | Format-Table DisplayName, Action, Enabled, Profile -AutoSize | Out-String
    return
}

Show-TrangThai
'CHUA DOI GI. Doc ky muc "Ket noi DANG MO" o tren: dia chi LAN nao dang dung 8010 se bi chan sau khi -ApDung.'
