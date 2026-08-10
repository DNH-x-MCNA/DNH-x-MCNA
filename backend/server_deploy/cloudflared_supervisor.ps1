# === Giam sat Cloudflare Quick Tunnel: tu khoi dong lai + tu cap nhat URL moi vao Vercel ===
#
# !!! FILE NAY CO 2 BAN GIONG HET NHAU TRONG REPO - SUA THI PHAI SUA CA HAI:
#       backend/cloudflared_supervisor.ps1
#       backend/server_deploy/cloudflared_supervisor.ps1
#     Chinh viec 2 ban LECH NHAU la nguyen nhan su co 10/08/2026 (xem duoi).
#
# Quick tunnel (trycloudflare.com) MIEN PHI nhung URL DOI moi lan khoi dong lai. Script nay chay
# thuong tru: tunnel chet -> khoi dong lai -> doc URL moi tu log -> neu khac URL cu thi tu cap nhat
# vao Vercel (BACKEND_API_URL) + deploy lai.
#
# --- SU CO 10/08/2026, va 4 loi da sua o day ---
# Trieu chung: man hinh dang nhap dnh-bot.vercel.app bao "Failed to execute 'json' on 'Response':
# Unexpected end of JSON input". Backend HOAN TOAN KHOE (service Running, cong 8010, /health = ok).
# Nguyen nhan: tunnel chet tu 27/07 (dong log cuoi 27/07 15:26), supervisor KHONG khoi dong lai,
# va Vercel van tro vao hostname cu da bi Cloudflare thu hoi -> fetch that bai -> body rong.
# KHONG AI BIET SUOT 14 NGAY vi script chet IM LANG.
#
#   (1) SAI CONG: ban backend/ tro "--url http://localhost:8000" trong khi backend chay o 8010
#       (cong 8000 da bi mot du an WebChatbot khac cua dong nghiep chiem tren may nay - xem
#       run_supervisor.ps1). Nay ep dung $BACKEND_PORT, khai bao mot cho duy nhat.
#   (2) SAI DUONG DAN cloudflared.exe: 2 ban ghi 2 cho khac nhau ("C:\dnh_chatbot\tools\..." va
#       "C:\Program Files (x86)\cloudflared\..."). Start-Process khong thay file -> vong lap loi
#       ngay -> khong kip ghi dong log nao -> chet im lang. Nay TU DO nhieu vi tri + PATH, va neu
#       van khong thay thi GHI LOG THAT TO roi thoat han (thay vi quay vong vo ich).
#   (3) MAT TU DONG CAP NHAT VERCEL: ban server_deploy da go phan nay ("tam thoi BO QUA theo yeu
#       cau") nen URL moi chi nam trong file log, khong ai day len Vercel. Nay bat lai, va neu
#       khong cap nhat duoc thi ghi ro URL can sua tay + de lai file CAN_SUA_VERCEL.txt.
#   (4) TIEN TRINH MO COI: 23/07/2026 tung co 4 tien trinh cloudflared song song (4 dong "Tunnel
#       URL" trung nhau trong log). Nay don sach tien trinh cu truoc khi khoi dong ban moi.

$BACKEND_PORT   = 8010                              # PHAI khop uvicorn trong run_supervisor.ps1
$BASE_DIR       = "C:\dnh_chatbot"
$FRONTEND_DIR   = "$BASE_DIR\frontend"
$LOG_DIR        = "$BASE_DIR\backend\logs"
$SUP_LOG        = "$LOG_DIR\cloudflared_supervisor.log"
$RUN_LOG        = "$LOG_DIR\cloudflared_run.log"
$RUN_OUT_LOG    = "$LOG_DIR\cloudflared_run_out.log"
$LAST_URL_FILE  = "$LOG_DIR\cloudflared_last_url.txt"
$NEEDS_FIX_FILE = "$LOG_DIR\CAN_SUA_VERCEL.txt"

# Loi (2): do nhieu vi tri thay vi ghi cung mot cho.
$CLOUDFLARED_CANDIDATES = @(
    "$BASE_DIR\tools\cloudflared.exe",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
)

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUP_LOG -Value $line -Encoding utf8
}

function Find-Cloudflared {
    foreach ($p in $CLOUDFLARED_CANDIDATES) {
        if (Test-Path $p) { return $p }
    }
    $cmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# Loi (4): don tien trinh cu truoc khi khoi dong ban moi.
function Stop-OrphanCloudflared {
    $procs = @(Get-Process cloudflared -ErrorAction SilentlyContinue)
    if ($procs.Count -gt 0) {
        Log "Phat hien $($procs.Count) tien trinh cloudflared cu (PID: $($procs.Id -join ', ')) - dung het truoc khi khoi dong lai."
        $procs | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}

# Loi (3): bat lai tu dong cap nhat Vercel; that bai thi phai ON AO, khong duoc im lang.
function Update-VercelUrl($url) {
    if (-not (Test-Path $FRONTEND_DIR)) {
        Log "KHONG cap nhat duoc Vercel: khong thay thu muc frontend '$FRONTEND_DIR'."
        Set-Content -Path $NEEDS_FIX_FILE -Value "CAN SUA TAY tren Vercel: BACKEND_API_URL = $url" -Encoding utf8
        Log ">>> HAY SUA TAY: Vercel > Settings > Environment Variables > BACKEND_API_URL = $url  (roi Redeploy)"
        return
    }
    Log "URL tunnel moi: $url - dang cap nhat Vercel..."
    Push-Location $FRONTEND_DIR
    try {
        & npx vercel env rm BACKEND_API_URL production --yes *> $null
        $url | & npx vercel env add BACKEND_API_URL production *> $null
        & npx vercel deploy --prod --yes *> "$LOG_DIR\cloudflared_deploy.log"
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $LAST_URL_FILE -Value $url -Encoding utf8
            if (Test-Path $NEEDS_FIX_FILE) { Remove-Item $NEEDS_FIX_FILE -Force }
            Log "Da cap nhat Vercel + deploy xong."
        } else {
            Log "LOI: vercel deploy tra ve ma loi $LASTEXITCODE (xem cloudflared_deploy.log). Nhieu kha nang npx vercel CHUA dang nhap tren may nay."
            Set-Content -Path $NEEDS_FIX_FILE -Value "CAN SUA TAY tren Vercel: BACKEND_API_URL = $url" -Encoding utf8
            Log ">>> HAY SUA TAY: Vercel > Settings > Environment Variables > BACKEND_API_URL = $url  (roi Redeploy)"
        }
    } catch {
        Log "LOI khi cap nhat Vercel: $_"
        Set-Content -Path $NEEDS_FIX_FILE -Value "CAN SUA TAY tren Vercel: BACKEND_API_URL = $url" -Encoding utf8
        Log ">>> HAY SUA TAY: Vercel > Settings > Environment Variables > BACKEND_API_URL = $url  (roi Redeploy)"
    } finally {
        Pop-Location
    }
}

Log "=== Cloudflared supervisor khoi dong (cong dich: $BACKEND_PORT) ==="

$CLOUDFLARED = Find-Cloudflared
if ($null -eq $CLOUDFLARED) {
    # Loi (2): truoc day cho nay that bai im lang suot 14 ngay. Nay ghi ro roi thoat.
    Log "LOI NGHIEM TRONG: KHONG TIM THAY cloudflared.exe. Da tim: $($CLOUDFLARED_CANDIDATES -join ' | ') va ca PATH."
    Log "Tunnel SE KHONG CHAY -> chatbot khong the truy cap tu Internet. Cai cloudflared hoac sua \$CLOUDFLARED_CANDIDATES roi chay lai."
    exit 1
}
Log "Dung cloudflared tai: $CLOUDFLARED"

while ($true) {
    Stop-OrphanCloudflared
    foreach ($lg in @($RUN_LOG, $RUN_OUT_LOG)) {
        if (Test-Path $lg) { Remove-Item $lg -Force -ErrorAction SilentlyContinue }
    }

    $proc = Start-Process -FilePath $CLOUDFLARED `
        -ArgumentList "tunnel", "--url", "http://localhost:$BACKEND_PORT" `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $RUN_OUT_LOG -RedirectStandardError $RUN_LOG

    Log "Cloudflared khoi dong, PID=$($proc.Id)"

    # Doc CA hai log: cloudflared co the ghi URL ra stdout hoac stderr tuy phien ban.
    $url = $null
    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 1
        foreach ($lg in @($RUN_LOG, $RUN_OUT_LOG)) {
            if (Test-Path $lg) {
                $content = Get-Content $lg -Raw -ErrorAction SilentlyContinue
                if ($content -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
                    $url = $matches[0]
                    break
                }
            }
        }
        if ($url) { break }
    }

    if ($url) {
        Log "Tunnel URL: $url"
        $lastUrl = ""
        if (Test-Path $LAST_URL_FILE) { $lastUrl = (Get-Content $LAST_URL_FILE -Raw).Trim() }
        if ($url -ne $lastUrl) {
            Update-VercelUrl $url
        } else {
            Log "URL khong doi so voi lan truoc - khong can cap nhat Vercel."
        }
    } else {
        Log "CANH BAO: khong tim thay URL tunnel sau 40s - cloudflared co the loi. Xem $RUN_LOG va $RUN_OUT_LOG."
    }

    $proc.WaitForExit()
    Log "Cloudflared da thoat (ExitCode=$($proc.ExitCode)) - khoi dong lai sau 5s..."
    Start-Sleep -Seconds 5
}
