# Build va chay web chatbot (Next.js) NGAY TREN may 24, tu code da git pull o C:\dnh_chatbot.
#
#   .\deploy_web.ps1             # build ban HEAD hien tai cua repo roi chuyen web sang ban do
#   .\deploy_web.ps1 -QuayLai    # quay ve ban build truoc
#
# Moi ban build vao thu muc rieng (releases\<gio>-<commit>); "current" la junction tro toi ban dang chay va chi
# doi khi build XONG, nen trong luc build web cu van phuc vu. Web moi khong len thi tu quay ve ban cu.
# Build khong can khoa: BACKEND_API_URL / BACKEND_API_KEY chi doc luc chay, tu $GocWeb\web.env (duoc chep thanh
# .env.production.local cua ban build). May 24 chi con trong ~2,8 GB RAM (do 30/09): build bi gioi han 1,5 GB va
# KHONG chay trong khung 17:15-18:15 (bao cao Daily/Weekly/Monthly).
# Chay trong PowerShell "Run as Administrator" (doi junction + khoi dong lai dich vu).
param(
    [switch]$QuayLai,
    [string]$GocWeb = 'C:\dnh_web',
    [string]$Repo = 'C:\dnh_chatbot',
    [string]$ThuMucNode = 'C:\dnh_chatbot\tools\node',
    [string]$DichVu = 'DNH_Chatbot_Web',
    [int]$GiuLai = 3,
    [switch]$BoQuaKhungGio
)
$ErrorActionPreference = 'Stop'
$RELEASES = Join-Path $GocWeb 'releases'
$CURRENT = Join-Path $GocWeb 'current'
$ENV_FILE = Join-Path $GocWeb 'web.env'
$KHOA = Join-Path $GocWeb 'deploy.lock'
# Ten file do cai_dat_lan_dau.ps1 dat cho NSSM: logs\<ten dich vu>.err.log
$NHAT_KY_LOI = Join-Path $GocWeb "logs\$DichVu.err.log"

function Log([string]$s) { Write-Host ("{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $s) }
function Dung([string]$s) { Log "DUNG: $s"; throw $s }

function Get-BanDangChay {
    if (-not (Test-Path $CURRENT)) { return $null }
    $muc = Get-Item $CURRENT -Force
    if ($muc.LinkType -ne 'Junction') { Dung "$CURRENT khong phai junction - khong tu dong vao" }
    return ($muc.Target | Select-Object -First 1)
}

# Ban build hoan chinh (co danh dau .build-ok), cu -> moi.
function Get-BanDaBuild {
    if (-not (Test-Path $RELEASES)) { return @() }
    return @(Get-ChildItem $RELEASES -Directory | Where-Object { Test-Path (Join-Path $_.FullName '.build-ok') } |
        Sort-Object Name | ForEach-Object { $_.FullName })
}

function Test-CoDichVu { return [bool](Get-Service -Name $DichVu -ErrorAction SilentlyContinue) }

function Test-WebLen {
    for ($i = 0; $i -lt 45; $i++) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/' -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Set-BanChay([string]$dich) {
    $co = Test-CoDichVu
    if ($co) { Stop-Service -Name $DichVu -Force }
    # rmdir tren junction chi go lien ket, khong xoa noi dung ban build.
    if (Test-Path $CURRENT) { cmd /c rmdir "$CURRENT" | Out-Null }
    cmd /c mklink /J "$CURRENT" "$dich" | Out-Null
    if (-not (Test-Path (Join-Path $CURRENT 'package.json'))) { Dung "khong tao duoc junction $CURRENT -> $dich" }
    if ($co) { Start-Service -Name $DichVu }
}

function Test-Backend {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:8010/health' -TimeoutSec 10
        if ($r.Content -match '"status"\s*:\s*"ok"') { Log 'Backend 127.0.0.1:8010 tra loi: OK'; return }
    } catch { }
    Log 'CANH BAO: khong goi duoc http://127.0.0.1:8010/health - kiem dich vu DNH_Chatbot_Backend'
}

function Remove-BanCu {
    $dangChay = Get-BanDangChay
    $tatCa = @(Get-ChildItem $RELEASES -Directory | Sort-Object Name -Descending)
    if ($tatCa.Count -le $GiuLai) { return }
    foreach ($d in $tatCa[$GiuLai..($tatCa.Count - 1)]) {
        if ($d.FullName -eq $dangChay) { continue }
        Remove-Item -Recurse -Force -LiteralPath $d.FullName
    }
}

function Invoke-QuayLai {
    $dangChay = Get-BanDangChay
    $truoc = Get-BanDaBuild | Where-Object { -not $dangChay -or ($_ -lt $dangChay) } | Select-Object -Last 1
    if (-not $truoc) { Dung "khong co ban build truoc de quay ve (dang chay: $dangChay)" }
    Log "Quay ve $truoc (dang chay: $dangChay)"
    Set-BanChay $truoc
    if ((Test-CoDichVu) -and -not (Test-WebLen)) { Dung "ban truoc cung khong len - xem $NHAT_KY_LOI" }
    Log "DAT: web chay lai ban $truoc"
}

function Invoke-Deploy {
    if (-not (Test-Path $ENV_FILE)) { Dung "chua co $ENV_FILE (tao tu deploy\may24_truc_tiep\web.env.mau)" }
    if (Select-String -Path $ENV_FILE -Pattern 'DAN_KHOA_TU_BACKEND_ENV' -Quiet) {
        Dung "$ENV_FILE con khoa mau - dan BACKEND_API_KEY that truoc"
    }
    $node = Join-Path $ThuMucNode 'node.exe'
    $npm = Join-Path $ThuMucNode 'npm.cmd'
    if (-not (Test-Path $node) -or -not (Test-Path $npm)) { Dung "khong thay node.exe/npm.cmd trong $ThuMucNode" }

    $sha = (& git -C $Repo rev-parse --short HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $sha) { Dung "khong doc duoc commit cua $Repo" }
    & git -C $Repo log -1 --oneline
    $dich = Join-Path $RELEASES ("{0}-{1}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'), $sha)
    $truoc = Get-BanDangChay
    New-Item -ItemType Directory -Force -Path $dich | Out-Null

    # Chi lay file da commit (khong keo theo .env, kho du lieu, node_modules cua thu muc dang chay).
    $zip = "$dich.zip"
    & git -C $Repo archive --format=zip -o $zip HEAD
    if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force $dich; Dung 'git archive loi' }
    Expand-Archive -LiteralPath $zip -DestinationPath $dich -Force
    Remove-Item -Force $zip

    Log "Build $sha trong $dich (npm ci + next build + kiem CSS)..."
    $pathCu, $optCu, $telCu = $env:PATH, $env:NODE_OPTIONS, $env:NEXT_TELEMETRY_DISABLED
    $loiBuild = $null
    Push-Location $dich
    try {
        $env:PATH = "$ThuMucNode;$env:PATH"
        $env:NODE_OPTIONS = '--max-old-space-size=1536'
        $env:NEXT_TELEMETRY_DISABLED = '1'
        & $npm ci --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { $loiBuild = 'npm ci loi' }
        else {
            & $npm run build
            if ($LASTEXITCODE -ne 0) { $loiBuild = 'npm run build loi' }
        }
    } finally {
        Pop-Location
        $env:PATH, $env:NODE_OPTIONS, $env:NEXT_TELEMETRY_DISABLED = $pathCu, $optCu, $telCu
    }
    if ($loiBuild) {
        Remove-Item -Recurse -Force -LiteralPath $dich
        Dung "$loiBuild - web van chay ban cu ($truoc)"
    }

    Copy-Item -LiteralPath $ENV_FILE -Destination (Join-Path $dich '.env.production.local') -Force
    # Tien trinh web (LOCAL SERVICE) chi duoc ghi .next\cache cua ban build.
    $cache = Join-Path $dich '.next\cache'
    New-Item -ItemType Directory -Force -Path $cache | Out-Null
    if (Test-CoDichVu) { & icacls $cache /grant 'LOCAL SERVICE:(OI)(CI)M' | Out-Null }
    Set-Content -LiteralPath (Join-Path $dich '.build-ok') -Value $sha -Encoding ascii

    Set-BanChay $dich
    if (-not (Test-CoDichVu)) {
        Log "DAT (chua co dich vu $DichVu): da build $sha va tro current vao $dich. Chay cai_dat_lan_dau.ps1 -ApDung."
        return
    }
    if (-not (Test-WebLen)) {
        Log "LOI: web ban $sha khong len - quay ve ban cu"
        if ($truoc -and (Test-Path $truoc)) {
            Set-BanChay $truoc
            if (Test-WebLen) { Log "Da quay ve $truoc" }
        }
        Dung "deploy $sha that bai - xem $NHAT_KY_LOI (ban loi giu lai o $dich de xem)"
    }
    Log "DAT: web chay ban $sha ($dich)"
    Test-Backend
    Remove-BanCu
}

$gio = (Get-Date).ToString('HH:mm')
if (-not $BoQuaKhungGio -and $gio -ge '17:15' -and $gio -le '18:15') {
    Dung "gan gio bao cao 17:45 ($gio) - chay lai sau 18:15"
}
New-Item -ItemType Directory -Force -Path $RELEASES | Out-Null
if (Test-Path $KHOA) { Dung "dang co mot lan deploy khac chay ($KHOA); neu chac chan khong co thi xoa file nay" }
Set-Content -LiteralPath $KHOA -Value $PID -Encoding ascii
try {
    if ($QuayLai) { Invoke-QuayLai } else { Invoke-Deploy }
} finally {
    Remove-Item -Force -LiteralPath $KHOA -ErrorAction SilentlyContinue
}
