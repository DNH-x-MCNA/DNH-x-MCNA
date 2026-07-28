# === Giam sat & tu khoi dong lai: Backend (FastAPI) + Telegram Bot + Sync Scheduler + Cloudflared
#     Supervisor cho DNH AI Chatbot ===
# Chay thuong tru, "giam sat cua giam sat" - giu ca 4 tien trinh nen song, tu restart neu bi crash.
# Tu khoi dong cung Windows qua shortcut trong Startup folder (day la script DUY NHAT can shortcut -
# 3 tien trinh con lai deu do chinh script nay khoi dong va theo doi).
$BACKEND_DIR = "C:\Users\DANG TRIEU\dnh_chatbot\backend"
$LOG_DIR = "$BACKEND_DIR\logs"
$SUPERVISOR_LOG = "$LOG_DIR\supervisor.log"
$CHECK_INTERVAL_SEC = 30

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Path $LOG_DIR -Force | Out-Null }

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $SUPERVISOR_LOG -Value $line -Encoding utf8
}

function Start-Backend {
    Start-Process -FilePath "py" -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000" `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput "$LOG_DIR\uvicorn.log" -RedirectStandardError "$LOG_DIR\uvicorn.err.log"
}

function Start-SyncScheduler {
    Start-Process -FilePath "powershell.exe" `
        -ArgumentList @("-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", "`"$BACKEND_DIR\sync_scheduler.ps1`"") `
        -WorkingDirectory $BACKEND_DIR -WindowStyle Hidden -PassThru
}

Log "=== Supervisor khoi dong ==="
Log "(LUU Y 7/2026: Telegram bot + Cloudflared tunnel da CHUYEN het sang may chu DNH (ket noi Bravo"
Log " truc tiep, khong VPN). May PC nay CHI con giu backend+sync o che do DU PHONG (khong phuc vu"
Log " traffic that) - KHONG con chay cloudflared tunnel nua de tranh tu dong ghi de BACKEND_API_URL"
Log " tren Vercel (da tung gay bug: PC ghi de URL may chu bang URL cua chinh no)."
$backendProc = Start-Backend
Log "Backend (uvicorn :8000) started, PID=$($backendProc.Id)"
$syncProc = Start-SyncScheduler
Log "Sync scheduler started, PID=$($syncProc.Id)"

while ($true) {
    Start-Sleep -Seconds $CHECK_INTERVAL_SEC

    if ($backendProc.HasExited) {
        Log "CANH BAO: Backend da thoat (ExitCode=$($backendProc.ExitCode)) -> khoi dong lai"
        $backendProc = Start-Backend
        Log "Backend restarted, PID=$($backendProc.Id)"
    }
    if ($syncProc.HasExited) {
        Log "CANH BAO: Sync scheduler da thoat (ExitCode=$($syncProc.ExitCode)) -> khoi dong lai"
        $syncProc = Start-SyncScheduler
        Log "Sync scheduler restarted, PID=$($syncProc.Id)"
    }
}
