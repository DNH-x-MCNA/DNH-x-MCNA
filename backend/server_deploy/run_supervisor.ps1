# === Giam sat & tu khoi dong lai: Backend + Telegram Bot + Sync Scheduler + Cloudflared ===
# (May chu DNH - ket noi Bravo TRUC TIEP, khong qua VPN)
$BACKEND_DIR = "C:\dnh_chatbot\backend"
$LOG_DIR = "$BACKEND_DIR\logs"
$SUPERVISOR_LOG = "$LOG_DIR\supervisor.log"
$CHECK_INTERVAL_SEC = 30

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUPERVISOR_LOG -Value $line -Encoding utf8
}

function Start-Backend {
    # Cong 8010 (KHONG dung 8000 - da bi 1 du an WebChatbot khac cua dong nghiep chiem tren may nay)
    Start-Process -FilePath "python" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8010" `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$LOG_DIR\uvicorn.log" -RedirectStandardError "$LOG_DIR\uvicorn.err.log"
}

function Start-Bot {
    Start-Process -FilePath "python" -ArgumentList "telegram_bot.py" `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$LOG_DIR\telegram_bot.log" -RedirectStandardError "$LOG_DIR\telegram_bot.err.log"
}

function Start-SyncScheduler {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$BACKEND_DIR\sync_scheduler.ps1`"") `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru
}

function Start-CloudflaredSupervisor {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$BACKEND_DIR\cloudflared_supervisor.ps1`"") `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru
}

Log "=== Supervisor khoi dong ==="
$backendProc = Start-Backend
Log "Backend (uvicorn :8000) started, PID=$($backendProc.Id)"
$botProc = Start-Bot
Log "Telegram bot started, PID=$($botProc.Id)"
$syncProc = Start-SyncScheduler
Log "Sync scheduler started, PID=$($syncProc.Id)"
$cfProc = Start-CloudflaredSupervisor
Log "Cloudflared supervisor started, PID=$($cfProc.Id)"

while ($true) {
    Start-Sleep -Seconds $CHECK_INTERVAL_SEC

    if ($backendProc.HasExited) {
        Log "CANH BAO: Backend da thoat (ExitCode=$($backendProc.ExitCode)) -> khoi dong lai"
        $backendProc = Start-Backend
        Log "Backend restarted, PID=$($backendProc.Id)"
    }
    if ($botProc.HasExited) {
        Log "CANH BAO: Telegram bot da thoat (ExitCode=$($botProc.ExitCode)) -> khoi dong lai"
        $botProc = Start-Bot
        Log "Telegram bot restarted, PID=$($botProc.Id)"
    }
    if ($syncProc.HasExited) {
        Log "CANH BAO: Sync scheduler da thoat (ExitCode=$($syncProc.ExitCode)) -> khoi dong lai"
        $syncProc = Start-SyncScheduler
        Log "Sync scheduler restarted, PID=$($syncProc.Id)"
    }
    if ($cfProc.HasExited) {
        Log "CANH BAO: Cloudflared supervisor da thoat (ExitCode=$($cfProc.ExitCode)) -> khoi dong lai"
        $cfProc = Start-CloudflaredSupervisor
        Log "Cloudflared supervisor restarted, PID=$($cfProc.Id)"
    }
}
