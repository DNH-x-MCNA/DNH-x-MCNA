# === Giam sat Cloudflare Quick Tunnel tren may chu DNH: tu khoi dong lai + ghi log URL hien tai ===
# (Phan tu dong cap nhat Vercel tam thoi BO QUA theo yeu cau - co the noi lai sau)
$CLOUDFLARED = "C:\dnh_chatbot\tools\cloudflared.exe"
$LOG_DIR = "C:\dnh_chatbot\backend\logs"
$SUP_LOG = "$LOG_DIR\cloudflared_supervisor.log"
$RUN_LOG = "$LOG_DIR\cloudflared_run.log"
$RUN_OUT_LOG = "$LOG_DIR\cloudflared_run_out.log"
$LAST_URL_FILE = "$LOG_DIR\cloudflared_last_url.txt"

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUP_LOG -Value $line -Encoding utf8
}

Log "=== Cloudflared supervisor (may chu DNH) khoi dong ==="

while ($true) {
    if (Test-Path $RUN_LOG) { Remove-Item $RUN_LOG -Force }

    $proc = Start-Process -FilePath $CLOUDFLARED -ArgumentList "tunnel", "--url", "http://localhost:8010" `
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
        Set-Content -Path $LAST_URL_FILE -Value $url -Encoding utf8
    } else {
        Log "CANH BAO: khong tim thay URL tunnel sau 20s - cloudflared co the loi."
    }

    $proc.WaitForExit()
    Log "Cloudflared da thoat (ExitCode=$($proc.ExitCode)) - khoi dong lai sau 5s..."
    Start-Sleep -Seconds 5
}
