# === Giam sat Cloudflare Quick Tunnel: tu khoi dong lai khi chet, tu cap nhat URL moi vao Vercel ===
# Quick tunnel (trycloudflare.com) MIEN PHI nhung URL doi moi lan khoi dong lai (vd sau khi may
# restart/ngu). Script nay chay thuong tru, tu phat hien tunnel chet -> khoi dong lai -> doc URL moi
# tu log -> neu khac URL cu thi tu cap nhat vao Vercel (BACKEND_API_URL) + deploy lai - KHONG can
# can thiep thu cong nhu truoc. Tu khoi dong cung Windows qua shortcut trong Startup folder.
$BACKEND_DIR = "C:\Users\DANG TRIEU\dnh_chatbot\backend"
$FRONTEND_DIR = "C:\Users\DANG TRIEU\dnh_chatbot\frontend"
$CLOUDFLARED = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$LOG_DIR = "$BACKEND_DIR\logs"
$SUP_LOG = "$LOG_DIR\cloudflared_supervisor.log"
$RUN_LOG = "$LOG_DIR\cloudflared_run.log"
$RUN_OUT_LOG = "$LOG_DIR\cloudflared_run_out.log"
$LAST_URL_FILE = "$LOG_DIR\cloudflared_last_url.txt"

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUP_LOG -Value $line -Encoding utf8
}

function Update-VercelUrl($url) {
    Log "URL tunnel moi: $url - dang cap nhat Vercel..."
    Push-Location $FRONTEND_DIR
    try {
        & npx vercel env rm BACKEND_API_URL production --yes *> $null
        $url | & npx vercel env add BACKEND_API_URL production *> $null
        & npx vercel deploy --prod --yes *> "$LOG_DIR\cloudflared_deploy.log"
        Set-Content -Path $LAST_URL_FILE -Value $url -Encoding utf8
        Log "Da cap nhat Vercel + deploy xong."
    } catch {
        Log "LOI khi cap nhat Vercel: $_"
    } finally {
        Pop-Location
    }
}

Log "=== Cloudflared supervisor khoi dong ==="

while ($true) {
    if (Test-Path $RUN_LOG) { Remove-Item $RUN_LOG -Force }

    $proc = Start-Process -FilePath $CLOUDFLARED -ArgumentList "tunnel", "--url", "http://localhost:8000" `
        -WindowStyle Hidden -PassThru -RedirectStandardOutput $RUN_OUT_LOG -RedirectStandardError $RUN_LOG

    Log "Cloudflared khoi dong, PID=$($proc.Id)"

    $url = $null
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $RUN_LOG) {
            $content = Get-Content $RUN_LOG -Raw -ErrorAction SilentlyContinue
            if ($content -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
                $url = $matches[0]
                break
            }
        }
    }

    if ($url) {
        Log "Tunnel URL: $url"
        $lastUrl = if (Test-Path $LAST_URL_FILE) { (Get-Content $LAST_URL_FILE -Raw).Trim() } else { "" }
        if ($url -ne $lastUrl) {
            Update-VercelUrl $url
        } else {
            Log "URL khong doi so voi lan truoc - khong can cap nhat Vercel."
        }
    } else {
        Log "CANH BAO: khong tim thay URL tunnel sau 20s - cloudflared co the loi."
    }

    $proc.WaitForExit()
    Log "Cloudflared da thoat (ExitCode=$($proc.ExitCode)) - khoi dong lai sau 5s..."
    Start-Sleep -Seconds 5
}
