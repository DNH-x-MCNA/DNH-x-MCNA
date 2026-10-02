# Windows Firewall cho may 24 khi web chatbot chay thang tren may nay (DNS -> NAT 443 -> Caddy).
#   CHO  : TCP 443 vao, CHI cho chuong trinh caddy.exe
#   CHAN : TCP 3000 (Next.js) va 8010 (FastAPI) tu moi dia chi ngoai may
# Windows Firewall khong loc loopback, nen Caddy -> 127.0.0.1:3000 -> 127.0.0.1:8010, watchdog va tunnel tam
# cloudflared (goi localhost:8010) KHONG bi anh huong. Rule CHAN thang rule CHO, nen dong 8010 o day la dong han,
# ke ca khi dang co rule cho python.exe. uvicorn van nghe 0.0.0.0:8010 (run_supervisor.ps1) - khong can sua code.
# Firewall/NAT cua DNH la lop ngoai: chi duoc NAT TCP 443; day la lop trong tren chinh may 24.
# Chay -ApDung TRUOC cai_dat_lan_dau.ps1 -ApDung: Let's Encrypt kiem ten mien bang cach goi vao cong 443 cua may nay,
# chua co rule CHO thi lan xin chung chi dau tien hong. Rule gan theo duong dan caddy.exe nen tao truoc duoc.
#
#   .\tuong_lua_truc_tiep.ps1            # CHI KIEM, khong doi gi (mac dinh)
#   .\tuong_lua_truc_tiep.ps1 -ApDung    # tao 2 rule tren
#   .\tuong_lua_truc_tiep.ps1 -GoBo      # xoa 2 rule do, quay ve nhu cu
# -ApDung / -GoBo phai chay trong PowerShell "Run as Administrator".
param(
    [switch]$ApDung,
    [switch]$GoBo,
    [string]$Caddy = 'C:\dnh_chatbot\tools\caddy\caddy.exe'
)
$ErrorActionPreference = 'Stop'
$NHOM = 'DNH chatbot truc tiep'
$CONG_DONG = @('3000', '8010')

function Assert-Admin {
    $id = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $id.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Can chay PowerShell bang "Run as Administrator".'
    }
}

function Show-TrangThai {
    '=== Windows Firewall theo profile (Enabled=False thi moi rule deu khong co tac dung)'
    Get-NetFirewallProfile | Format-Table Name, Enabled, DefaultInboundAction -AutoSize | Out-String

    '=== Tien trinh dang nghe 443 / 3000 / 8010'
    Get-NetTCPConnection -LocalPort 443, 3000, 8010 -State Listen -ErrorAction SilentlyContinue |
        Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize | Out-String

    '=== Ket noi DANG MO vao 3000/8010 theo dia chi nguon'
    '    (chi nen thay 127.0.0.1; dia chi khac = co may trong mang dang goi thang, se bi chan khi -ApDung)'
    Get-NetTCPConnection -LocalPort 3000, 8010 -State Established -ErrorAction SilentlyContinue |
        Group-Object LocalPort, RemoteAddress | Sort-Object Count -Descending |
        Format-Table Count, Name -AutoSize | Out-String

    "=== Rule cua nhom '$NHOM'"
    $r = Get-NetFirewallRule -Group $NHOM -ErrorAction SilentlyContinue
    if ($r) { $r | Format-Table DisplayName, Direction, Action, Enabled -AutoSize | Out-String }
    else { '   (chua co)' }
}

if ($GoBo) {
    Assert-Admin
    Get-NetFirewallRule -Group $NHOM -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    "Da xoa rule nhom '$NHOM'."
    Show-TrangThai
    return
}

if (-not $ApDung) {
    Show-TrangThai
    'CHI KIEM - chua doi gi. Them -ApDung de tao rule.'
    return
}

Assert-Admin
if (-not (Test-Path $Caddy)) { throw "Thieu $Caddy" }
Get-NetFirewallRule -Group $NHOM -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName 'DNH chatbot - cho HTTPS 443 vao Caddy' -Group $NHOM -Direction Inbound `
    -Action Allow -Protocol TCP -LocalPort 443 -Program $Caddy -Profile Any | Out-Null
New-NetFirewallRule -DisplayName 'DNH chatbot - chan 3000 va 8010 tu ngoai may' -Group $NHOM -Direction Inbound `
    -Action Block -Protocol TCP -LocalPort $CONG_DONG -Profile Any | Out-Null
"Da tao rule nhom '$NHOM'."
Show-TrangThai
